"""
D-Cloud NodePool — HTTP-based node client
==========================================
Replaces the Holochain WebSocket ConductorPool with a simple HTTP client
that talks to D-Cloud standalone node servers (node_server.py).

Each NodePool instance manages N nodes. It:
  • Tracks which nodes are "live" (reachable) vs "killed" (manually disabled)
  • Broadcasts chunks/manifests to ALL live nodes (max replication)
  • Retries fetches across all live nodes (fault tolerance)
  • Reports node status for the dashboard

Compatible interface with the old ConductorPool so main.py changes are minimal.
"""

from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import httpx

log = logging.getLogger("d-cloud.node-pool")

# ─── Node ─────────────────────────────────────────────────────────────────────


@dataclass
class Node:
    """Represents one physical D-Cloud node server."""
    url: str            # e.g. "http://192.168.1.10:8001"
    node_id: str        # e.g. "node1"
    _live: bool = field(default=True, repr=False)
    _health: dict = field(default_factory=dict, repr=False)
    # P2P identity — populated from /health on each ping
    recipient_pubkey: str = field(default="", repr=False)  # X25519 hex pubkey
    signing_pubkey:   str = field(default="", repr=False)  # Ed25519 hex pubkey

    @property
    def live(self) -> bool:
        return self._live

    @property
    def status(self) -> str:
        return "online" if self._live else "offline"

    async def ping(self, client: httpx.AsyncClient) -> bool:
        """Ping the /health endpoint. Returns True if reachable."""
        try:
            r = await client.get(f"{self.url}/health", timeout=3.0)
            if r.status_code == 200:
                self._health = r.json()
                # Cache the node's P2P public keys for DEK wrapping
                self.recipient_pubkey = self._health.get("recipient_pubkey", "")
                self.signing_pubkey   = self._health.get("signing_pubkey", "")
                return True
        except Exception:
            pass
        return False

    def kill(self) -> None:
        """Manually mark this node as killed (bridge stops using it)."""
        self._live = False
        log.warning("Node %s (%s) marked KILLED", self.node_id, self.url)

    def revive(self) -> None:
        """Re-enable a killed node."""
        self._live = True
        log.info("Node %s (%s) marked ONLINE", self.node_id, self.url)

    @property
    def chunks_held(self) -> int:
        return self._health.get("chunks_held", 0)


# ─── NodePool ─────────────────────────────────────────────────────────────────


class NodePool:
    """
    Manages a pool of D-Cloud node servers.

    Upload:   store_chunk_on_all()    — POST chunk to every live node
              store_manifest_on_all() — POST manifest to every live node
    Retrieve: fetch_chunk(hash)       — GET chunk, failover across nodes
              fetch_manifest(hash)    — GET manifest, failover across nodes
    Dashboard: status_all()           — health snapshot of all nodes
    """

    def __init__(self, node_urls: List[str]) -> None:
        self.nodes: List[Node] = []
        for i, url in enumerate(node_urls):
            url = url.rstrip("/")
            node_id = f"node{i + 1}"
            self.nodes.append(Node(url=url, node_id=node_id))
        # Shared async HTTP client (created lazily in async context)
        self._client: Optional[httpx.AsyncClient] = None

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def startup(self) -> None:
        """Ping all nodes at startup; log which are reachable."""
        self._client = httpx.AsyncClient(timeout=10.0)
        alive = 0
        for node in self.nodes:
            reachable = await node.ping(self._client)
            if reachable:
                alive += 1
                log.info("✅  Node %s reachable at %s (%d chunks stored)",
                         node.node_id, node.url, node.chunks_held)
            else:
                log.warning("⚠️   Node %s unreachable at %s", node.node_id, node.url)
        log.info("NodePool online: %d / %d nodes reachable", alive, len(self.nodes))

    async def shutdown(self) -> None:
        if self._client:
            await self._client.aclose()

    # ── Helpers ───────────────────────────────────────────────────────────────

    @property
    def live_nodes(self) -> List[Node]:
        return [n for n in self.nodes if n.live]

    @property
    def connected_count(self) -> int:
        return len(self.live_nodes)

    def peer_pubkeys(self) -> List[str]:
        """Return X25519 public keys of all nodes that have announced their P2P identity."""
        return [n.recipient_pubkey for n in self.nodes if n.recipient_pubkey]

    def _client_or_raise(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError("NodePool not started — call startup() first")
        return self._client

    # ── Store (broadcast to all live nodes) ───────────────────────────────────

    async def store_chunk_on_all(self, chunk_payload: dict) -> List[str]:
        """
        POST chunk payload to all live nodes.
        Returns list of node_ids that accepted it.
        Raises RuntimeError if no node accepted.
        """
        client = self._client_or_raise()
        accepted: List[str] = []
        errors: List[str] = []

        for node in self.live_nodes:
            try:
                r = await client.post(f"{node.url}/chunk", json=chunk_payload, timeout=10.0)
                if r.status_code in (200, 201):
                    accepted.append(node.node_id)
                    log.debug("Chunk stored on %s", node.node_id)
                else:
                    errors.append(f"{node.node_id}: HTTP {r.status_code}")
            except Exception as exc:
                errors.append(f"{node.node_id}: {exc}")

        if not accepted:
            raise RuntimeError(
                f"Failed to store chunk on any node. Errors: {'; '.join(errors)}"
            )
        if errors:
            log.warning("Chunk stored on %d/%d nodes. Failures: %s",
                        len(accepted), len(self.nodes), "; ".join(errors))
        return accepted

    async def store_manifest_on_all(self, manifest_payload: dict) -> None:
        """POST manifest to all live nodes."""
        client = self._client_or_raise()
        accepted: List[str] = []

        for node in self.live_nodes:
            try:
                r = await client.post(f"{node.url}/manifest", json=manifest_payload, timeout=10.0)
                if r.status_code in (200, 201):
                    accepted.append(node.node_id)
            except Exception as exc:
                log.warning("Failed to store manifest on %s: %s", node.node_id, exc)

        if not accepted:
            raise RuntimeError("Failed to store manifest on any node")

    # ── Fetch (failover across nodes) ─────────────────────────────────────────

    async def fetch_chunk(self, chunk_hash: str) -> dict:
        """
        GET chunk by hash. Tries all live nodes (in order).
        Raises RuntimeError if no node has the chunk.
        """
        client = self._client_or_raise()
        for node in self.live_nodes:
            try:
                r = await client.get(f"{node.url}/chunk/{chunk_hash}", timeout=10.0)
                if r.status_code == 200:
                    log.debug("Chunk %s fetched from %s", chunk_hash[:12], node.node_id)
                    return r.json()
            except Exception as exc:
                log.debug("Node %s error fetching chunk: %s", node.node_id, exc)
        raise RuntimeError(
            f"Chunk {chunk_hash[:16]}… not found on any live node "
            f"(tried: {[n.node_id for n in self.live_nodes]})"
        )

    async def fetch_manifest(self, manifest_hash: str) -> Optional[dict]:
        """
        GET manifest by hash. Tries all live nodes.
        Returns None if not found anywhere.
        """
        client = self._client_or_raise()
        for node in self.live_nodes:
            try:
                r = await client.get(f"{node.url}/manifest/{manifest_hash}", timeout=10.0)
                if r.status_code == 200:
                    log.debug("Manifest %s fetched from %s", manifest_hash[:12], node.node_id)
                    return r.json()
            except Exception as exc:
                log.debug("Node %s error fetching manifest: %s", node.node_id, exc)
        return None

    async def list_manifests(self) -> List[dict]:
        """
        Aggregate manifest list from all live nodes.
        Deduplicates by manifest_hash.
        """
        client = self._client_or_raise()
        seen: Dict[str, dict] = {}

        for node in self.live_nodes:
            try:
                r = await client.get(f"{node.url}/list", timeout=10.0)
                if r.status_code != 200:
                    continue
                data = r.json()
                for mhash in data.get("manifest_hashes", []):
                    if mhash not in seen:
                        # Fetch the full manifest
                        mr = await client.get(f"{node.url}/manifest/{mhash}", timeout=10.0)
                        if mr.status_code == 200:
                            seen[mhash] = mr.json()
            except Exception as exc:
                log.debug("Node %s error listing: %s", node.node_id, exc)

        return list(seen.values())

    # ── Status ────────────────────────────────────────────────────────────────

    async def status_all(self) -> List[dict]:
        """
        Ping all nodes and return their status dicts.
        Used by GET /api/agents/status.
        """
        client = self._client_or_raise()
        result = []
        for node in self.nodes:
            if node.live:
                reachable = await node.ping(client)
                if not reachable:
                    # Still "live" unless manually killed, but report degraded
                    status_str = "degraded"
                else:
                    status_str = "online"
            else:
                status_str = "offline"

            result.append({
                "agent_id":    node.node_id,
                "url":         node.url,
                "status":      status_str,
                "chunks_held": node.chunks_held,
                "node_id":     node.node_id,
            })
        return result

    # ── Kill / Revive (demo) ──────────────────────────────────────────────────

    def kill_node(self, node_id: str) -> bool:
        """Mark a node as killed (bridge stops routing to it)."""
        for node in self.nodes:
            if node.node_id == node_id or node_id in node.url:
                node.kill()
                return True
        return False

    def revive_node(self, node_id: str) -> bool:
        """Re-enable a killed node."""
        for node in self.nodes:
            if node.node_id == node_id or node_id in node.url:
                node.revive()
                return True
        return False

    def get_node(self, node_id: str) -> Optional[Node]:
        for node in self.nodes:
            if node.node_id == node_id or node_id in node.url:
                return node
        return None
