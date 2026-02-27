"""
D-Cloud Standalone Node Server
================================
Zero-dependency Python 3.8+ HTTP server. Each physical machine runs one instance.

Usage:
    python node_server.py --port 8001 --node-id node1
    python node_server.py --port 8001 --node-id node2 --host 0.0.0.0

Endpoints:
    POST   /chunk                 Store a chunk (JSON body)
    GET    /chunk/{chunk_hash}    Retrieve a chunk by hash
    POST   /manifest              Store a file manifest (JSON body)
    GET    /manifest/{hash}       Retrieve a manifest by hash
    GET    /health                Node health + stats
    GET    /list                  List all stored manifest hashes
    DELETE /chunk/{chunk_hash}    Delete a chunk (testing only)
    DELETE /all                   Wipe all data (testing only)

Storage:
    Chunks and manifests are kept in memory and also written to
    `node_data_<node_id>.json` on disk so they survive restarts.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import socket
import sys
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Lock
from typing import Any, Dict, Optional
from urllib.parse import urlparse

# ─── P2P Identity (optional — graceful fallback if 'cryptography' not installed)
try:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
    from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat, PublicFormat
    _CRYPTO_OK = True
except ImportError:
    _CRYPTO_OK = False


def _lan_ip() -> str:
    """Return the machine's primary LAN IP (not 127.0.0.1)."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "<unknown>"

# ─── Logging ─────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("d-cloud.node")

# ─── Global State ─────────────────────────────────────────────────────────────

_lock = Lock()
_chunks: Dict[str, Any] = {}     # chunk_hash → chunk payload dict
_manifests: Dict[str, Any] = {}  # manifest_hash → manifest dict
_node_id: str = "node1"
_data_file: str = "node_data_node1.json"
_started_at: float = time.time()

# ─── P2P Node Identity ────────────────────────────────────────────────────────
# Populated by _load_or_create_identity() at startup
_identity: Dict[str, str] = {}   # keys: signing_pubkey_hex, recipient_pubkey_hex


def _load_or_create_identity() -> None:
    """Generate or load this node's Ed25519 + X25519 keypairs. Shares keys with the Bridge."""
    global _identity
    if not _CRYPTO_OK:
        log.warning("'cryptography' package not found — P2P identity disabled. Install with: pip install cryptography")
        return

    # Share the keys directory with the bridge so the Node advertises the Bridge's decryption keys
    keys_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "api-bridge", "keys")
    os.makedirs(keys_dir, exist_ok=True)
    
    signing_key_path   = os.path.join(keys_dir, "bridge_ed25519.key")
    recipient_key_path = os.path.join(keys_dir, "recipient_x25519.key")

    # ── Ed25519 signing keypair ──
    if os.path.exists(signing_key_path):
        signing_privkey = Ed25519PrivateKey.from_private_bytes(open(signing_key_path, "rb").read())
        log.info("Loaded existing Ed25519 signing key")
    else:
        signing_privkey = Ed25519PrivateKey.generate()
        raw = signing_privkey.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
        open(signing_key_path, "wb").write(raw)
        log.info("🔑  Generated NEW Ed25519 signing key → %s", signing_key_path)

    signing_pubkey_hex = signing_privkey.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw).hex()

    # ── X25519 recipient keypair ──
    if os.path.exists(recipient_key_path):
        recipient_privkey = X25519PrivateKey.from_private_bytes(open(recipient_key_path, "rb").read())
        log.info("Loaded existing X25519 recipient key")
    else:
        recipient_privkey = X25519PrivateKey.generate()
        raw = recipient_privkey.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
        open(recipient_key_path, "wb").write(raw)
        log.info("🔑  Generated NEW X25519 recipient key → %s", recipient_key_path)

    recipient_pubkey_hex = recipient_privkey.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw).hex()

    _identity = {
        "signing_pubkey_hex":   signing_pubkey_hex,
        "recipient_pubkey_hex": recipient_pubkey_hex,
    }
    log.info("🆔  Node identity — signing:   %s…", signing_pubkey_hex[:16])
    log.info("🆔  Node identity — recipient: %s…", recipient_pubkey_hex[:16])

# ─── Persistence ─────────────────────────────────────────────────────────────

def _save() -> None:
    """Persist state to disk (called under _lock)."""
    try:
        os.makedirs(os.path.dirname(os.path.abspath(_data_file)), exist_ok=True)
        with open(_data_file, "w") as fh:
            json.dump({"chunks": _chunks, "manifests": _manifests}, fh)
    except Exception as exc:
        log.warning("Failed to persist data: %s", exc)


def _load() -> None:
    """Load persisted state from disk at startup."""
    global _chunks, _manifests
    if not os.path.exists(_data_file):
        return
    try:
        with open(_data_file) as fh:
            data = json.load(fh)
        _chunks = data.get("chunks", {})
        _manifests = data.get("manifests", {})
        log.info(
            "Loaded %d chunks, %d manifests from %s",
            len(_chunks), len(_manifests), _data_file,
        )
    except Exception as exc:
        log.warning("Could not load persisted data: %s — starting fresh", exc)

# ─── HTTP Handler ─────────────────────────────────────────────────────────────

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, DELETE, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, Authorization",
}


class NodeHandler(BaseHTTPRequestHandler):
    """HTTP request handler for D-Cloud node server."""

    # suppress default request log (we do our own)
    def log_message(self, fmt, *args):  # type: ignore[override]
        pass

    def log_error(self, fmt, *args):  # type: ignore[override]
        # Suppress noisy ConnectionAbortedError / ConnectionResetError that occur
        # when the bridge's 2-second health-poll closes mid-connection. These are
        # harmless and would otherwise flood the terminal during demos.
        msg = fmt % args if args else str(fmt)
        if "ConnectionAbortedError" in msg or "ConnectionResetError" in msg or "10053" in msg or "10054" in msg:
            return
        log.warning("HTTP error: %s", msg)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _send(self, code: int, body: Any, content_type: str = "application/json") -> None:
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        for k, v in CORS_HEADERS.items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def _read_json(self) -> Optional[dict]:
        try:
            length = int(self.headers.get("Content-Length", 0))
            return json.loads(self.rfile.read(length))
        except Exception:
            return None

    def _path_parts(self) -> list[str]:
        return [p for p in urlparse(self.path).path.split("/") if p]

    # ── OPTIONS (CORS preflight) ───────────────────────────────────────────────

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        for k, v in CORS_HEADERS.items():
            self.send_header(k, v)
        self.end_headers()

    # ── GET ───────────────────────────────────────────────────────────────────

    def do_GET(self) -> None:
        parts = self._path_parts()

        # GET /health
        if parts == ["health"]:
            with _lock:
                chunk_count = len(_chunks)
                manifest_count = len(_manifests)
            health_resp = {
                "node_id":          _node_id,
                "status":           "online",
                "chunks_held":      chunk_count,
                "manifests_held":   manifest_count,
                "uptime_seconds":   round(time.time() - _started_at, 1),
                # P2P identity — public keys only, never private keys
                "signing_pubkey":   _identity.get("signing_pubkey_hex", ""),
                "recipient_pubkey": _identity.get("recipient_pubkey_hex", ""),
            }
            self._send(200, health_resp)
            return

        # GET /list
        if parts == ["list"]:
            with _lock:
                manifest_hashes = list(_manifests.keys())
            self._send(200, {
                "node_id": _node_id,
                "manifest_hashes": manifest_hashes,
                "total": len(manifest_hashes),
            })
            return

        # GET /chunk/{chunk_hash}
        if len(parts) == 2 and parts[0] == "chunk":
            chunk_hash = parts[1]
            with _lock:
                chunk = _chunks.get(chunk_hash)
            if chunk is None:
                self._send(404, {"error": f"Chunk {chunk_hash!r} not found"})
            else:
                log.info("GET /chunk/%s … 200", chunk_hash[:12])
                self._send(200, chunk)
            return

        # GET /manifest/{manifest_hash}
        if len(parts) == 2 and parts[0] == "manifest":
            manifest_hash = parts[1]
            with _lock:
                manifest = _manifests.get(manifest_hash)
            if manifest is None:
                self._send(404, {"error": f"Manifest {manifest_hash!r} not found"})
            else:
                log.info("GET /manifest/%s … 200", manifest_hash[:12])
                self._send(200, manifest)
            return

        self._send(404, {"error": "Not found"})

    # ── POST ──────────────────────────────────────────────────────────────────

    def do_POST(self) -> None:
        parts = self._path_parts()

        # POST /chunk
        if parts == ["chunk"]:
            body = self._read_json()
            if not body:
                self._send(400, {"error": "Invalid JSON body"})
                return
            chunk_hash = body.get("chunk_hash")
            if not chunk_hash:
                self._send(400, {"error": "Missing chunk_hash field"})
                return
            with _lock:
                _chunks[chunk_hash] = body
                _save()
            log.info("POST /chunk  stored %s", chunk_hash[:12])
            self._send(201, {"status": "stored", "chunk_hash": chunk_hash, "node_id": _node_id})
            return

        # POST /manifest
        if parts == ["manifest"]:
            body = self._read_json()
            if not body:
                self._send(400, {"error": "Invalid JSON body"})
                return
            manifest_hash = body.get("manifest_hash")
            if not manifest_hash:
                self._send(400, {"error": "Missing manifest_hash field"})
                return
            with _lock:
                _manifests[manifest_hash] = body
                _save()
            log.info("POST /manifest  stored %s", manifest_hash[:12])
            self._send(201, {
                "status": "stored",
                "manifest_hash": manifest_hash,
                "node_id": _node_id,
            })
            return

        self._send(404, {"error": "Not found"})

    # ── DELETE ────────────────────────────────────────────────────────────────

    def do_DELETE(self) -> None:
        parts = self._path_parts()

        # DELETE /all  (wipe everything — for testing)
        if parts == ["all"]:
            with _lock:
                _chunks.clear()
                _manifests.clear()
                _save()
            log.warning("DELETE /all  — all data wiped")
            self._send(200, {"status": "wiped", "node_id": _node_id})
            return

        # DELETE /chunk/{chunk_hash}
        if len(parts) == 2 and parts[0] == "chunk":
            chunk_hash = parts[1]
            with _lock:
                removed = _chunks.pop(chunk_hash, None)
                if removed:
                    _save()
            if removed:
                self._send(200, {"status": "deleted", "chunk_hash": chunk_hash})
            else:
                self._send(404, {"error": f"Chunk {chunk_hash!r} not found"})
            return

        self._send(404, {"error": "Not found"})


# ─── Entry Point ──────────────────────────────────────────────────────────────

def main() -> None:
    global _node_id, _data_file

    parser = argparse.ArgumentParser(description="D-Cloud Node Server")
    parser.add_argument("--port",    type=int, default=8001,    help="TCP port to listen on (default: 8001)")
    parser.add_argument("--host",    type=str, default="0.0.0.0", help="Bind address (default: 0.0.0.0)")
    parser.add_argument("--node-id", type=str, default="node1",  help="Node identifier (default: node1)")
    parser.add_argument("--data-dir",type=str, default=".",      help="Directory for node_data_<id>.json")
    args = parser.parse_args()

    _node_id  = args.node_id
    _data_file = os.path.join(args.data_dir, f"node_data_{_node_id}.json")
    data_dir   = args.data_dir

    # ── P2P Identity: generate or load keypairs for this machine ──
    _load_or_create_identity()

    _load()

    server = HTTPServer((args.host, args.port), NodeHandler)
    lan_ip = _lan_ip()

    W = 54  # inner width between the box walls

    def row(text: str = "") -> str:
        return "║  " + text.ljust(W) + "║"

    def sep() -> str:
        return "╠" + "═" * (W + 2) + "╣"

    addr = f"http://{lan_ip}:{args.port}"
    df   = os.path.abspath(_data_file)

    print()
    print("╔" + "═" * (W + 2) + "╗")
    print(row(f"D-Cloud Node Server — {_node_id}"))
    print(sep())
    print(row(f"Listening on  http://0.0.0.0:{args.port}"))
    print(row(f"Node ID       {_node_id}"))
    print(row(f"Data file     {df[:W - 14]}"))
    print(sep())
    print(row())
    print(row(f"✅  This machine's LAN IP : {lan_ip}"))
    print(row())
    print(row("  Add to bridge api-bridge/.env:"))
    print(row(f"  NODE_URLS=...{addr}..."))
    print(row())
    print(sep())
    print(row("Endpoints:"))
    print(row(f"  GET   {addr}/health"))
    print(row(f"  POST  {addr}/chunk"))
    print(row(f"  GET   {addr}/chunk/{{hash}}"))
    print(row(f"  POST  {addr}/manifest"))
    print("╚" + "═" * (W + 2) + "╝")
    print()
    print("  Press Ctrl+C to stop.")

    print()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Node server stopped.")
        sys.exit(0)


if __name__ == "__main__":
    main()
