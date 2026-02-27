"""
D-Cloud Cryptographic Utilities
================================
All cryptographic operations for the FastAPI bridge.

Locked versions (per golden rule):
  cryptography == 42.0.5   (AES-256-GCM, X25519, HKDF, Ed25519)
  Standard library:         hashlib (SHA-256), os (random), base64, pathlib

Design decisions:
  - Ed25519 keypair:   bridge SIGNS every chunk_hash before upload (non-repudiation)
  - AES-256-GCM:       encrypts plaintext chunks. Nonce is 96-bit random, unique per chunk.
  - X25519 ECDH:       wraps the per-file DEK for a specific recipient's pubkey.
  - HKDF-SHA256:       derives the Key Encryption Key (KEK) from the ECDH shared secret.
  - SHA-256:           content-addresses each ciphertext chunk (chunk_hash).
  - Merkle-style root: SHA-256(all chunk_hashes concatenated) stored in FileManifest.
"""

from __future__ import annotations

import base64
import hashlib
import os
import struct
from pathlib import Path
from typing import NamedTuple

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.asymmetric.x25519 import (
    X25519PrivateKey,
    X25519PublicKey,
)
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)


# ─────────────────────────────────────────────────────────────────────────────
# Key file paths
# ─────────────────────────────────────────────────────────────────────────────

KEYS_DIR = Path(__file__).parent / "keys"
SIGNING_KEY_PATH    = KEYS_DIR / "bridge_ed25519.key"
RECIPIENT_KEY_PATH  = KEYS_DIR / "recipient_x25519.key"

# ─────────────────────────────────────────────────────────────────────────────
# Ed25519 Signing keypair  (bridge identity)
# ─────────────────────────────────────────────────────────────────────────────

class SigningKeyPair(NamedTuple):
    private_key: Ed25519PrivateKey
    public_key:  Ed25519PublicKey
    pubkey_hex:  str   # 32-byte verifying key as hex — stored in FileChunk.signer_pubkey


def generate_signing_keypair() -> SigningKeyPair:
    """Generate a new Ed25519 keypair and persist it to KEYS_DIR."""
    KEYS_DIR.mkdir(parents=True, exist_ok=True)
    private_key = Ed25519PrivateKey.generate()
    raw_private = private_key.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
    SIGNING_KEY_PATH.write_bytes(raw_private)
    public_key = private_key.public_key()
    pubkey_hex = public_key.public_bytes(Encoding.Raw, PublicFormat.Raw).hex()
    return SigningKeyPair(private_key, public_key, pubkey_hex)


def load_or_create_signing_keypair() -> SigningKeyPair:
    """Load existing Ed25519 keypair from disk, or create one if absent."""
    if SIGNING_KEY_PATH.exists():
        raw = SIGNING_KEY_PATH.read_bytes()
        private_key = Ed25519PrivateKey.from_private_bytes(raw)
    else:
        return generate_signing_keypair()
    public_key = private_key.public_key()
    pubkey_hex = public_key.public_bytes(Encoding.Raw, PublicFormat.Raw).hex()
    return SigningKeyPair(private_key, public_key, pubkey_hex)


def sign_chunk(chunk_hash: str, private_key: Ed25519PrivateKey) -> str:
    """
    Sign the chunk_hash string (UTF-8) with Ed25519.
    Returns the 64-byte signature as hex.

    IMPORTANT: We sign the chunk_hash string bytes, not the raw ciphertext.
    The integrity zome verifies the same way: message = chunk_hash.encode('utf-8').
    """
    signature_bytes = private_key.sign(chunk_hash.encode("utf-8"))
    return signature_bytes.hex()


def verify_chunk_signature(chunk_hash: str, signature_hex: str, pubkey_hex: str) -> bool:
    """
    Verify an Ed25519 signature over chunk_hash.
    Returns True if valid, False if invalid (never raises on bad signatures).
    """
    try:
        pubkey_bytes = bytes.fromhex(pubkey_hex)
        public_key   = Ed25519PublicKey.from_public_bytes(pubkey_bytes)
        public_key.verify(bytes.fromhex(signature_hex), chunk_hash.encode("utf-8"))
        return True
    except Exception:
        return False


# ─────────────────────────────────────────────────────────────────────────────
# X25519 Recipient keypair  (E2EE)
# ─────────────────────────────────────────────────────────────────────────────

class RecipientKeyPair(NamedTuple):
    private_key: X25519PrivateKey
    public_key:  X25519PublicKey
    pubkey_hex:  str   # 32-byte X25519 pubkey as hex — stored in FileManifest


def generate_recipient_keypair() -> RecipientKeyPair:
    """Generate a new X25519 keypair and persist private key to KEYS_DIR."""
    KEYS_DIR.mkdir(parents=True, exist_ok=True)
    private_key = X25519PrivateKey.generate()
    raw_private = private_key.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
    RECIPIENT_KEY_PATH.write_bytes(raw_private)
    public_key = private_key.public_key()
    pubkey_hex = public_key.public_bytes(Encoding.Raw, PublicFormat.Raw).hex()
    return RecipientKeyPair(private_key, public_key, pubkey_hex)


def load_or_create_recipient_keypair() -> RecipientKeyPair:
    """Load existing X25519 recipient keypair, or create one if absent."""
    if RECIPIENT_KEY_PATH.exists():
        raw = RECIPIENT_KEY_PATH.read_bytes()
        private_key = X25519PrivateKey.from_private_bytes(raw)
    else:
        return generate_recipient_keypair()
    public_key = private_key.public_key()
    pubkey_hex = public_key.public_bytes(Encoding.Raw, PublicFormat.Raw).hex()
    return RecipientKeyPair(private_key, public_key, pubkey_hex)


# ─────────────────────────────────────────────────────────────────────────────
# AES-256-GCM chunk encryption / decryption
# ─────────────────────────────────────────────────────────────────────────────

AES_KEY_BYTES  = 32   # 256-bit key
AES_NONCE_BYTES = 12  # 96-bit nonce (GCM standard)


def generate_dek() -> bytes:
    """Generate a random 256-bit Data Encryption Key for one file."""
    return os.urandom(AES_KEY_BYTES)


def encrypt_chunk(dek: bytes, plaintext: bytes) -> tuple[bytes, str]:
    """
    Encrypt a plaintext chunk with AES-256-GCM using the given DEK.

    Returns:
        (ciphertext_bytes, nonce_hex)

    A fresh 96-bit nonce is generated for every chunk — NEVER reuse a nonce
    with the same key.
    """
    nonce = os.urandom(AES_NONCE_BYTES)
    aesgcm = AESGCM(dek)
    ciphertext = aesgcm.encrypt(nonce, plaintext, associated_data=None)
    return ciphertext, nonce.hex()


def decrypt_chunk(dek: bytes, nonce_hex: str, ciphertext: bytes) -> bytes:
    """
    Decrypt an AES-256-GCM ciphertext chunk.

    Raises cryptography.exceptions.InvalidTag if the ciphertext is tampered.
    """
    nonce  = bytes.fromhex(nonce_hex)
    aesgcm = AESGCM(dek)
    return aesgcm.decrypt(nonce, ciphertext, associated_data=None)


# ─────────────────────────────────────────────────────────────────────────────
# DEK wrapping / unwrapping via X25519 ECDH + HKDF
# ─────────────────────────────────────────────────────────────────────────────
#
# Wire format of wrapped_dek (all concatenated, then hex-encoded):
#   ephemeral_pubkey  [32 bytes] — X25519 ephemeral pubkey for ECDH
#   nonce             [12 bytes] — AES-256-GCM nonce for DEK encryption
#   dek_ciphertext    [48 bytes] — AES-256-GCM ciphertext (32 DEK + 16 tag)
#   ─────────────────────────────
#   total             [92 bytes] → 184 hex chars
#
HKDF_INFO    = b"d-cloud-dek-v1"
HKDF_SALT    = b"d-cloud-salt-2026"
WRAPPED_LEN  = 32 + 12 + 32 + 16   # 92 bytes


def wrap_dek(dek: bytes, recipient_pubkey_hex: str) -> str:
    """
    Encrypt the DEK for a recipient identified by their X25519 public key.

    Steps:
      1. Generate ephemeral X25519 keypair
      2. ECDH: shared_secret = ephemeral_privkey × recipient_pubkey
      3. HKDF-SHA256: kek = derive(shared_secret, info=HKDF_INFO)
      4. AES-256-GCM: wrapped = encrypt(kek, dek)
      5. Return hex(ephemeral_pubkey || nonce || wrapped)
    """
    recipient_pubkey_bytes = bytes.fromhex(recipient_pubkey_hex)
    recipient_pubkey       = X25519PublicKey.from_public_bytes(recipient_pubkey_bytes)

    ephemeral_privkey  = X25519PrivateKey.generate()
    ephemeral_pubkey   = ephemeral_privkey.public_key()
    shared_secret      = ephemeral_privkey.exchange(recipient_pubkey)

    kek = HKDF(
        algorithm=SHA256(),
        length=AES_KEY_BYTES,
        salt=HKDF_SALT,
        info=HKDF_INFO,
    ).derive(shared_secret)

    nonce  = os.urandom(AES_NONCE_BYTES)
    aesgcm = AESGCM(kek)
    dek_ciphertext = aesgcm.encrypt(nonce, dek, associated_data=None)

    ephemeral_pubkey_bytes = ephemeral_pubkey.public_bytes(Encoding.Raw, PublicFormat.Raw)
    payload = ephemeral_pubkey_bytes + nonce + dek_ciphertext   # 92 bytes total
    return payload.hex()


def unwrap_dek(wrapped_dek_hex: str, recipient_privkey: X25519PrivateKey) -> bytes:
    """
    Recover the DEK from wrapped_dek_hex using the recipient's private key.

    Raises ValueError on malformed input.
    Raises cryptography.exceptions.InvalidTag if the wrapped DEK was tampered.
    """
    payload = bytes.fromhex(wrapped_dek_hex)
    if len(payload) != WRAPPED_LEN:
        raise ValueError(
            f"wrapped_dek must be {WRAPPED_LEN} bytes, got {len(payload)}"
        )

    ephemeral_pubkey_bytes = payload[:32]
    nonce                  = payload[32:44]
    dek_ciphertext         = payload[44:]

    ephemeral_pubkey = X25519PublicKey.from_public_bytes(ephemeral_pubkey_bytes)
    shared_secret    = recipient_privkey.exchange(ephemeral_pubkey)

    kek = HKDF(
        algorithm=SHA256(),
        length=AES_KEY_BYTES,
        salt=HKDF_SALT,
        info=HKDF_INFO,
    ).derive(shared_secret)

    aesgcm = AESGCM(kek)
    return aesgcm.decrypt(nonce, dek_ciphertext, associated_data=None)


# ─────────────────────────────────────────────────────────────────────────────
# Hashing utilities
# ─────────────────────────────────────────────────────────────────────────────

def sha256_hex(data: bytes) -> str:
    """Return SHA-256 of data as a lowercase hex string."""
    return hashlib.sha256(data).hexdigest()


def sha256_file(data: bytes) -> str:
    """
    SHA-256 of the PLAINTEXT file (computed before encryption).
    Used as the canonical file identity in FileChunk.file_hash and FileManifest.file_hash.
    """
    return sha256_hex(data)


def compute_root_hash(chunk_hashes: list[str]) -> str:
    """
    Compute a merkle-style root hash: SHA-256 of all chunk_hash strings concatenated.
    Order matters — this matches the chunk order in FileManifest.chunk_action_hashes.
    """
    combined = "".join(chunk_hashes).encode("utf-8")
    return sha256_hex(combined)


# ─────────────────────────────────────────────────────────────────────────────
# Chunk splitting
# ─────────────────────────────────────────────────────────────────────────────

def split_into_chunks(data: bytes, chunk_size: int = 65536) -> list[bytes]:
    """Split raw file bytes into fixed-size chunks (last chunk may be smaller)."""
    return [data[i: i + chunk_size] for i in range(0, len(data), chunk_size)]


# ─────────────────────────────────────────────────────────────────────────────
# Full pipeline helpers (used directly by main.py)
# ─────────────────────────────────────────────────────────────────────────────

class EncryptedChunkBundle(NamedTuple):
    """Everything needed to call upload_chunk for one chunk."""
    chunk_index:  int
    total_chunks: int
    ciphertext:   bytes
    nonce_hex:    str
    chunk_hash:   str    # SHA-256(ciphertext)
    signature:    str    # Ed25519 sig over chunk_hash
    signer_pubkey: str


def prepare_chunks(
    file_data: bytes,
    dek: bytes,
    signing_keypair: SigningKeyPair,
    chunk_size: int = 65536,
) -> list[EncryptedChunkBundle]:
    """
    Encrypt, hash, and sign all chunks of a file.

    Returns a list of EncryptedChunkBundle ready to be passed to upload_chunk.
    """
    raw_chunks  = split_into_chunks(file_data, chunk_size)
    total       = len(raw_chunks)
    bundles     = []

    for idx, plaintext_chunk in enumerate(raw_chunks):
        ciphertext, nonce_hex = encrypt_chunk(dek, plaintext_chunk)
        chunk_hash             = sha256_hex(ciphertext)
        signature              = sign_chunk(chunk_hash, signing_keypair.private_key)

        bundles.append(EncryptedChunkBundle(
            chunk_index   = idx,
            total_chunks  = total,
            ciphertext    = ciphertext,
            nonce_hex     = nonce_hex,
            chunk_hash    = chunk_hash,
            signature     = signature,
            signer_pubkey = signing_keypair.pubkey_hex,
        ))

    return bundles


def verify_and_decrypt_chunk(
    ciphertext: bytes,
    nonce_hex: str,
    chunk_hash: str,
    signature: str,
    signer_pubkey: str,
    dek: bytes,
) -> bytes:
    """
    Full retrieval-side verification pipeline for one chunk:
    1. Verify SHA-256(ciphertext) == chunk_hash
    2. Verify Ed25519 signature over chunk_hash
    3. AES-256-GCM decrypt ciphertext → plaintext

    Raises ValueError if any check fails.
    """
    # Step 1: integrity check
    computed = sha256_hex(ciphertext)
    if computed != chunk_hash:
        raise ValueError(
            f"Chunk hash mismatch: stored={chunk_hash}, computed={computed}"
        )

    # Step 2: authenticity check
    if not verify_chunk_signature(chunk_hash, signature, signer_pubkey):
        raise ValueError("Ed25519 signature verification failed for chunk")

    # Step 3: decrypt
    return decrypt_chunk(dek, nonce_hex, ciphertext)
