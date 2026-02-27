"""
D-Cloud FastAPI Bridge — Main Application (Node Server Edition)
===============================================================
REST API between the web UI and D-Cloud node servers (node_server.py).

Stores chunks + manifests on ALL live nodes simultaneously (broadcast).
Retrieves from any live node, automatically failing over (fault tolerance).

All cryptographic logic (E2EE, AES-256-GCM, Ed25519 signing) is unchanged.

Locked versions:
  fastapi==0.110.0 | uvicorn==0.29.0 | python-multipart==0.0.9
  cryptography==42.0.5 | httpx==0.27.0 | msgpack==1.0.8
"""

from __future__ import annotations

import hashlib
import logging
import mimetypes
import os
import time
from contextlib import asynccontextmanager
from typing import List, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

import crypto as cr
from node_pool import NodePool
from models import (
    ErrorResponse,
    FileEntry,
    HealthResponse,
    NodeStatusResponse,
    RegisterNodeRequest,
    UploadResponse,
)

# ─── Config ───────────────────────────────────────────────────────────────────

load_dotenv()

NODE_URLS     = os.getenv("NODE_URLS", "http://127.0.0.1:8001,http://127.0.0.1:8002,http://127.0.0.1:8003").split(",")
CHUNK_SIZE    = int(os.getenv("CHUNK_SIZE", "65536"))   # 64 KB
REDUNDANCY    = int(os.getenv("REDUNDANCY_FACTOR", "3"))
APP_PORT      = int(os.getenv("APP_PORT", "3000"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("d-cloud.api")

# ─── App State ────────────────────────────────────────────────────────────────

class AppState:
    signing_keypair:   cr.SigningKeyPair   = None   # type: ignore
    recipient_keypair: cr.RecipientKeyPair = None   # type: ignore
    pool: NodePool                         = None   # type: ignore

app_state = AppState()

# ─── Lifespan ─────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("D-Cloud bridge starting up …")

    app_state.signing_keypair   = cr.load_or_create_signing_keypair()
    app_state.recipient_keypair = cr.load_or_create_recipient_keypair()
    log.info("Ed25519 signing pubkey  : %s", app_state.signing_keypair.pubkey_hex[:16] + "…")
    log.info("X25519 recipient pubkey : %s", app_state.recipient_keypair.pubkey_hex[:16] + "…")

    app_state.pool = NodePool(node_urls=NODE_URLS)
    await app_state.pool.startup()
    log.info(
        "Connected to %d / %d nodes",
        app_state.pool.connected_count,
        len(NODE_URLS),
    )

    yield  # ←── app is running

    log.info("Shutting down …")
    await app_state.pool.shutdown()


# ─── FastAPI App ──────────────────────────────────────────────────────────────

app = FastAPI(
    title="D-Cloud Bridge API",
    description="Decentralised cloud storage — 3-node fault-tolerant demo",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _require_nodes() -> None:
    if app_state.pool.connected_count == 0:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No D-Cloud nodes are currently reachable",
        )


# ─── POST /api/upload ─────────────────────────────────────────────────────────

@app.post("/api/upload", response_model=UploadResponse, summary="Upload a file")
async def upload_file(file: UploadFile = File(...)) -> UploadResponse:
    """
    Splits the file into 64 KB chunks, encrypts each chunk, signs the hash,
    and broadcasts to ALL live node servers (max replication).
    Returns the manifest_hash for later retrieval.
    """
    _require_nodes()

    file_data = await file.read()
    if not file_data:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    file_name = file.filename or "unknown"
    mime_type = file.content_type or (
        mimetypes.guess_type(file_name)[0] or "application/octet-stream"
    )

    log.info("Upload request: '%s' (%d bytes, %s)", file_name, len(file_data), mime_type)

    # Canonical file identity hash (pre-encryption)
    file_hash = cr.sha256_file(file_data)

    # Per-file DEK (AES-256-GCM key)
    dek = cr.generate_dek()

    # Encrypt + sign all chunks
    bundles = cr.prepare_chunks(file_data, dek, app_state.signing_keypair, CHUNK_SIZE)

    chunk_hashes: List[str] = []
    chunk_manifest_refs: List[str] = []   # chunk_hash used as stable reference

    for bundle in bundles:
        chunk_payload = {
            "chunk_hash":    bundle.chunk_hash,
            "file_hash":     file_hash,
            "chunk_index":   bundle.chunk_index,
            "total_chunks":  bundle.total_chunks,
            "data":          list(bundle.ciphertext),  # bytes → list[int] (JSON-safe)
            "nonce":         bundle.nonce_hex,
            "signature":     bundle.signature,
            "signer_pubkey": bundle.signer_pubkey,
        }

        # Broadcast to all live nodes
        accepted_nodes = await app_state.pool.store_chunk_on_all(chunk_payload)
        log.info(
            "Chunk %d/%d stored on %s",
            bundle.chunk_index + 1, bundle.total_chunks, accepted_nodes,
        )

        chunk_hashes.append(bundle.chunk_hash)
        chunk_manifest_refs.append(bundle.chunk_hash)   # use hash as stable ref

    log.info("Uploaded %d chunks for '%s'", len(bundles), file_name)

    # Merkle-style root hash over ciphertext hashes
    root_hash = cr.compute_root_hash(chunk_hashes)

    # Wrap DEK for the recipient (X25519 ECDH)
    wrapped_dek = cr.wrap_dek(dek, app_state.recipient_keypair.pubkey_hex)

    # Build manifest dict (used as the canonical record)
    manifest_hash = hashlib.sha256(
        (file_hash + root_hash + file_name).encode()
    ).hexdigest()

    manifest_payload = {
        "manifest_hash":       manifest_hash,
        "name":                file_name,
        "size":                len(file_data),
        "mime_type":           mime_type,
        "file_hash":           file_hash,
        "root_hash":           root_hash,
        "total_chunks":        len(bundles),
        "chunk_action_hashes": chunk_manifest_refs,   # chunk_hash list
        "redundancy_factor":   REDUNDANCY,
        "uploader_pubkey":     app_state.signing_keypair.pubkey_hex,
        "wrapped_dek":         wrapped_dek,
        "recipient_pubkey":    app_state.recipient_keypair.pubkey_hex,
        "dek_algorithm":       "AES-256-GCM",
        "uploaded_at":         int(time.time()),
    }

    # Store manifest on all nodes
    await app_state.pool.store_manifest_on_all(manifest_payload)
    log.info("FileManifest stored — hash=%s", manifest_hash)

    return UploadResponse(
        manifest_hash     = manifest_hash,
        file_hash         = file_hash,
        root_hash         = root_hash,
        name              = file_name,
        size              = len(file_data),
        mime_type         = mime_type,
        total_chunks      = len(bundles),
        redundancy_factor = REDUNDANCY,
        recipient_pubkey  = app_state.recipient_keypair.pubkey_hex,
        dek_algorithm     = "AES-256-GCM",
    )


# ─── GET /api/file/{manifest_hash} ────────────────────────────────────────────

@app.get("/api/file/{manifest_hash}", summary="Retrieve and decrypt a file")
async def retrieve_file(manifest_hash: str) -> Response:
    """
    Fetches the FileManifest from any live node, then retrieves each chunk
    from any live node that has it. Decrypts and reassembles the file.
    Works even if 1 or 2 nodes are offline.
    """
    _require_nodes()

    # 1. Fetch manifest (retry across nodes)
    manifest = await app_state.pool.fetch_manifest(manifest_hash)
    if manifest is None:
        raise HTTPException(
            status_code=404,
            detail=f"No file found for manifest hash {manifest_hash}",
        )

    log.info("Retrieving '%s' — %d chunks", manifest.get("name"), manifest.get("total_chunks"))

    # 2. Unwrap DEK
    try:
        dek = cr.unwrap_dek(
            manifest["wrapped_dek"],
            app_state.recipient_keypair.private_key,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=422,
            detail=f"DEK unwrap failed: {exc}",
        )

    # 3. Retrieve, verify, decrypt each chunk
    chunk_hashes: List[str] = []
    plaintext_chunks: List[bytes] = []

    for idx, chunk_hash_ref in enumerate(manifest.get("chunk_action_hashes", [])):
        try:
            chunk = await app_state.pool.fetch_chunk(chunk_hash_ref)
        except RuntimeError as exc:
            raise HTTPException(
                status_code=503,
                detail=f"Chunk {idx} unavailable: {exc}",
            )

        ciphertext = bytes(chunk["data"])
        nonce_hex  = chunk["nonce"]
        chunk_hash = chunk["chunk_hash"]
        signature  = chunk["signature"]
        signer_pub = chunk["signer_pubkey"]

        try:
            plaintext = cr.verify_and_decrypt_chunk(
                ciphertext, nonce_hex, chunk_hash, signature, signer_pub, dek
            )
        except Exception as exc:
            raise HTTPException(
                status_code=422,
                detail=f"Chunk {idx} crypto verification failed: {exc}",
            )

        chunk_hashes.append(chunk_hash)
        plaintext_chunks.append(plaintext)

    # 4. Verify root hash (end-to-end integrity check)
    computed_root = cr.compute_root_hash(chunk_hashes)
    if computed_root != manifest["root_hash"]:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Root hash mismatch — file tampered. "
                f"Expected {manifest['root_hash']}, got {computed_root}"
            ),
        )

    # 5. Reassemble
    file_data = b"".join(plaintext_chunks)
    log.info("✅ Retrieved '%s' (%d bytes) — all chunks verified", manifest.get("name"), len(file_data))

    return Response(
        content   = file_data,
        media_type= manifest.get("mime_type", "application/octet-stream"),
        headers   = {
            "Content-Disposition": f'attachment; filename="{manifest.get("name", "file")}"',
            "X-File-Hash":         manifest.get("file_hash", ""),
            "X-Root-Hash":         manifest.get("root_hash", ""),
            "X-Total-Chunks":      str(manifest.get("total_chunks", 0)),
        },
    )


# ─── GET /api/files ───────────────────────────────────────────────────────────

@app.get("/api/files", response_model=list[FileEntry], summary="List all files")
async def list_files() -> list[FileEntry]:
    """Return all stored file manifests aggregated across live nodes."""
    _require_nodes()
    manifests = await app_state.pool.list_manifests()
    entries = []
    for m in manifests:
        entries.append(FileEntry(
            action_hash      = m.get("manifest_hash", ""),
            name             = m.get("name", ""),
            size             = m.get("size", 0),
            mime_type        = m.get("mime_type", ""),
            file_hash        = m.get("file_hash", ""),
            root_hash        = m.get("root_hash", ""),
            total_chunks     = m.get("total_chunks", 0),
            redundancy_factor= m.get("redundancy_factor", 0),
            uploader_pubkey  = m.get("uploader_pubkey", ""),
            recipient_pubkey  = m.get("recipient_pubkey", ""),
            dek_algorithm    = m.get("dek_algorithm", "AES-256-GCM"),
        ))
    return entries


# ─── GET /api/agents/status ───────────────────────────────────────────────────

@app.get("/api/agents/status", summary="Live status of all node servers")
async def get_agent_status() -> list[dict]:
    """Returns live health status of each node server (ping-based)."""
    return await app_state.pool.status_all()


# ─── POST /api/agents/{agent_id}/kill ─────────────────────────────────────────

@app.post("/api/agents/{agent_id}/kill", summary="Kill a node (demo fault injection)")
async def kill_agent(agent_id: str) -> dict:
    """
    Marks a node as killed — the bridge stops routing traffic to it.
    The node process itself is NOT killed (it keeps running on the physical machine).
    This simulates the BRIDGE losing access to a node (network partition / outage).
    """
    ok = app_state.pool.kill_node(agent_id)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Node '{agent_id}' not found")
    log.warning("🔴 DEMO FAULT: Node %s killed", agent_id)
    return {"status": "offline", "agent_id": agent_id}


# ─── POST /api/agents/{agent_id}/restart ──────────────────────────────────────

@app.post("/api/agents/{agent_id}/restart", summary="Revive a killed node")
async def restart_agent(agent_id: str) -> dict:
    """Re-enables a killed node — the bridge resumes routing to it."""
    ok = app_state.pool.revive_node(agent_id)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Node '{agent_id}' not found")
    log.info("🟢 DEMO RECOVERY: Node %s revived", agent_id)
    return {"status": "online", "agent_id": agent_id}


# ─── GET /api/nodes ───────────────────────────────────────────────────────────

@app.get("/api/nodes", summary="DHT node status list")
async def get_nodes() -> list[dict]:
    """Same as /api/agents/status but named for DHT semantics."""
    return await app_state.pool.status_all()


# ─── GET /api/health ─────────────────────────────────────────────────────────

@app.get("/api/health", response_model=HealthResponse, summary="Bridge health check")
async def health() -> HealthResponse:
    return HealthResponse(
        status               = "ok" if app_state.pool.connected_count > 0 else "degraded",
        bridge_pubkey_hex    = app_state.signing_keypair.pubkey_hex,
        recipient_pubkey_hex = app_state.recipient_keypair.pubkey_hex,
        connected_conductors = app_state.pool.connected_count,
    )


# ─── POST /api/nodes/register (kept for backwards compat) ────────────────────

@app.post("/api/nodes/register", summary="Register a node (no-op in node-server mode)")
async def register_node(body: RegisterNodeRequest) -> dict:
    """No-op — node server handles its own registration via /health polling."""
    return {"action_hash": "", "note": "Node server handles registration automatically"}
