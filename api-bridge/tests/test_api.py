"""
test_api.py — Integration tests for D-Cloud FastAPI endpoints.
Uses httpx async test client and mocked ConductorPool.

Locked versions: pytest==8.1.1 | pytest-asyncio==0.23.6 | httpx==0.27.0
Run with: pytest tests/test_api.py -v
"""
from __future__ import annotations

import io
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import crypto as cr


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def signing_keypair():
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
    priv = Ed25519PrivateKey.generate()
    pub  = priv.public_key()
    pubhex = pub.public_bytes(Encoding.Raw, PublicFormat.Raw).hex()
    return cr.SigningKeyPair(priv, pub, pubhex)


@pytest.fixture
def recipient_keypair():
    from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
    priv = X25519PrivateKey.generate()
    pub  = priv.public_key()
    pubhex = pub.public_bytes(Encoding.Raw, PublicFormat.Raw).hex()
    return cr.RecipientKeyPair(priv, pub, pubhex)


@pytest_asyncio.fixture
async def test_client(signing_keypair, recipient_keypair, tmp_path):
    """
    Spin up the FastAPI app with:
      - real crypto keypairs
      - a mocked ConductorPool that short-circuits all zome calls

    We use lifespan="on" so FastAPI's startup/shutdown runs inside the test.
    We also patch app_state directly *after* lifespan has set it up, as a
    belt-and-suspenders guard against import-ordering quirks.
    """
    import main as main_module

    mock_pool = _make_mock_pool(signing_keypair, recipient_keypair)

    with patch.object(main_module.cr, "load_or_create_signing_keypair",
                      return_value=signing_keypair), \
         patch.object(main_module.cr, "load_or_create_recipient_keypair",
                      return_value=recipient_keypair), \
         patch("main.ConductorPool", return_value=mock_pool):

        async with AsyncClient(
            transport=ASGITransport(app=main_module.app, raise_app_exceptions=True),
            base_url="http://test",
        ) as client:
            # Belt-and-suspenders: directly set app_state fields in case lifespan
            # ordering differs across FastAPI versions.
            main_module.app_state.signing_keypair   = signing_keypair
            main_module.app_state.recipient_keypair = recipient_keypair
            main_module.app_state.pool              = mock_pool

            yield client, signing_keypair, recipient_keypair


def _make_mock_pool(signing_kp, recipient_kp):
    """
    Build a mock ConductorPool that simulates DHT storage in a plain dict.
    This validates the full upload→retrieve pipeline without needing a real conductor.
    """
    store: dict = {}          # action_hash → {chunk_record or manifest_record}
    manifests: list = []      # list of {action_hash, manifest}
    hash_counter = [0]

    def make_hash(prefix: str) -> str:
        hash_counter[0] += 1
        return f"{prefix}-{hash_counter[0]:04d}"

    async def call_zome_with_retry(zome, fn, payload, timeout=60):
        return await _dispatch(zome, fn, payload, store, manifests, make_hash)

    async def call_zome_on_all(zome, fn, payload, timeout=60):
        result = await _dispatch(zome, fn, payload, store, manifests, make_hash)
        return [result]

    async def connect_all():
        pass

    async def disconnect_all():
        pass

    pool = MagicMock()
    pool.connected_count = 3
    pool.connect_all     = AsyncMock(side_effect=connect_all)
    pool.disconnect_all  = AsyncMock(side_effect=disconnect_all)
    pool.call_zome_with_retry = AsyncMock(side_effect=call_zome_with_retry)
    pool.call_zome_on_all     = AsyncMock(side_effect=call_zome_on_all)
    return pool


async def _dispatch(zome, fn, payload, store, manifests, make_hash):
    if fn == "upload_chunk":
        h = make_hash("chunk")
        store[h] = {
            "data":         payload["data"],
            "nonce":        payload["nonce"],
            "chunk_hash":   payload["chunk_hash"],
            "signature":    payload["signature"],
            "signer_pubkey": payload["signer_pubkey"],
        }
        return {"action_hash": h}

    elif fn == "create_manifest":
        h = make_hash("manifest")
        store[h] = payload
        manifests.append({"action_hash": h, "manifest": payload})
        return {"action_hash": h}

    elif fn == "get_manifest":
        return store.get(payload)

    elif fn == "get_chunk":
        return store.get(payload)

    elif fn == "list_files":
        return manifests

    elif fn == "get_network_nodes":
        return []

    elif fn == "register_node":
        h = make_hash("node")
        return {"action_hash": h}

    return None


# ─────────────────────────────────────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_health_endpoint(test_client):
    client, _, _ = test_client
    r = await client.get("/api/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert data["connected_conductors"] == 3
    assert len(data["bridge_pubkey_hex"]) == 64


@pytest.mark.asyncio
async def test_upload_small_file(test_client):
    client, _, _ = test_client
    content = b"Hello, D-Cloud! This is a test file."
    r = await client.post(
        "/api/upload",
        files={"file": ("test.txt", io.BytesIO(content), "text/plain")},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert "manifest_hash" in data
    assert data["total_chunks"] == 1
    assert data["dek_algorithm"] == "AES-256-GCM"
    assert len(data["file_hash"]) == 64    # SHA-256 hex
    assert len(data["root_hash"]) == 64


@pytest.mark.asyncio
async def test_upload_then_retrieve(test_client):
    """Full round-trip: upload plaintext, retrieve and verify it matches."""
    client, _, _ = test_client
    original = b"The quick brown fox jumps over the lazy dog."

    # Upload
    up = await client.post(
        "/api/upload",
        files={"file": ("fox.txt", io.BytesIO(original), "text/plain")},
    )
    assert up.status_code == 200, up.text
    manifest_hash = up.json()["manifest_hash"]

    # Retrieve
    down = await client.get(f"/api/file/{manifest_hash}")
    assert down.status_code == 200, down.text
    assert down.content == original


@pytest.mark.asyncio
async def test_upload_large_file_multi_chunk(test_client):
    """File larger than CHUNK_SIZE should be split into multiple chunks."""
    client, _, _ = test_client
    # 200 KB file → 4 chunks at 64 KB default chunk size
    large = os.urandom(200 * 1024)

    up = await client.post(
        "/api/upload",
        files={"file": ("large.bin", io.BytesIO(large), "application/octet-stream")},
    )
    assert up.status_code == 200, up.text
    assert up.json()["total_chunks"] >= 3

    down = await client.get(f"/api/file/{up.json()['manifest_hash']}")
    assert down.status_code == 200
    assert down.content == large


@pytest.mark.asyncio
async def test_list_files_after_upload(test_client):
    client, _, _ = test_client
    await client.post(
        "/api/upload",
        files={"file": ("a.txt", io.BytesIO(b"file a"), "text/plain")},
    )
    r = await client.get("/api/files")
    assert r.status_code == 200
    files = r.json()
    assert len(files) >= 1


@pytest.mark.asyncio
async def test_retrieve_nonexistent_hash_returns_404(test_client):
    client, _, _ = test_client
    r = await client.get("/api/file/nonexistent-hash")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_register_node(test_client):
    client, _, _ = test_client
    r = await client.post("/api/nodes/register", json={"node_id": "node-1", "status": "online"})
    assert r.status_code == 200
    assert "action_hash" in r.json()


@pytest.mark.asyncio
async def test_empty_file_upload_rejected(test_client):
    client, _, _ = test_client
    r = await client.post(
        "/api/upload",
        files={"file": ("empty.txt", io.BytesIO(b""), "text/plain")},
    )
    assert r.status_code == 400
