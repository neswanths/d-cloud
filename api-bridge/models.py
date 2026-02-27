"""
Pydantic models for D-Cloud FastAPI bridge.
These mirror the Rust entry types in the integrity zome
so JSON serialization is consistent across the stack.

Version: cryptography==42.0.5 | fastapi==0.110.0 | pydantic (via fastapi)
"""

from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Optional


# ─────────────────────────────────────────────────────────────────────────────
# Upload request / response
# ─────────────────────────────────────────────────────────────────────────────

class UploadResponse(BaseModel):
    manifest_hash:    str = Field(description="Base64 ActionHash of the FileManifest entry")
    file_hash:        str = Field(description="SHA-256 of the original plaintext file")
    root_hash:        str = Field(description="Merkle-style SHA-256 of all chunk hashes")
    name:             str
    size:             int = Field(description="Plaintext file size in bytes")
    mime_type:        str
    total_chunks:     int
    redundancy_factor: int
    recipient_pubkey: str = Field(description="X25519 pubkey used for DEK wrapping")
    dek_algorithm:    str = "AES-256-GCM"


# ─────────────────────────────────────────────────────────────────────────────
# File listing
# ─────────────────────────────────────────────────────────────────────────────

class FileEntry(BaseModel):
    action_hash:      str
    name:             str
    size:             int
    mime_type:        str
    file_hash:        str
    root_hash:        str
    total_chunks:     int
    redundancy_factor: int
    uploader_pubkey:  str
    recipient_pubkey: str
    dek_algorithm:    str


# ─────────────────────────────────────────────────────────────────────────────
# Node status
# ─────────────────────────────────────────────────────────────────────────────

class NodeStatusResponse(BaseModel):
    action_hash:  str
    node_id:      str
    agent_pubkey: str
    status:       str   # "online" | "degraded" | "offline"
    timestamp:    int
    chunks_held:  int


class RegisterNodeRequest(BaseModel):
    node_id:     str
    status:      str = "online"
    chunks_held: int = 0


# ─────────────────────────────────────────────────────────────────────────────
# Health
# ─────────────────────────────────────────────────────────────────────────────

class HealthResponse(BaseModel):
    status:             str
    bridge_pubkey_hex:  str = Field(description="Ed25519 signing pubkey fingerprint")
    recipient_pubkey_hex: str = Field(description="X25519 recipient pubkey fingerprint")
    connected_conductors: int
    version:            str = "D-Cloud Bridge v1.0"


# ─────────────────────────────────────────────────────────────────────────────
# Error
# ─────────────────────────────────────────────────────────────────────────────

class ErrorResponse(BaseModel):
    error:   str
    detail:  Optional[str] = None
