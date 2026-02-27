//! D-Cloud File Storage — Integrity Zome
//!
//! Defines all entry types and validation rules for the D-Cloud hApp.
//! Rules here are immutable once the DNA is deployed — they form the shared
//! "constitution" every DHT peer enforces independently.
//!
//! Crate versions (locked):
//!   hdi = 0.4.6 | sha2 = 0.10.8 | ed25519-dalek = 2.1.1 | hex = 0.4.3

use hdi::prelude::*;
use sha2::{Digest, Sha256};
use ed25519_dalek::{Signature, VerifyingKey, Verifier};

// ─────────────────────────────────────────────────────────────────────────────
// Entry type definitions
// ─────────────────────────────────────────────────────────────────────────────

/// A single AES-256-GCM encrypted chunk of a file.
/// The `data` field contains CIPHERTEXT — plaintext NEVER touches the DHT.
/// Every chunk is independently signed so tampered chunks are rejected at
/// the DHT gossip layer before they can even reach a consumer.
#[hdk_entry_helper]
#[derive(Clone)]
pub struct FileChunk {
    /// SHA-256 of the original plaintext file — binds chunk to its file.
    pub file_hash: String,
    /// Zero-based position of this chunk within the file.
    pub chunk_index: u32,
    /// Total number of chunks the file was split into.
    pub total_chunks: u32,
    /// AES-256-GCM ciphertext bytes — raw encrypted content.
    pub data: Vec<u8>,
    /// 96-bit AES-GCM nonce, hex-encoded. Unique per chunk; required for decryption.
    pub nonce: String,
    /// SHA-256(ciphertext bytes) — hex-encoded. Integrity check of stored ciphertext.
    pub chunk_hash: String,
    /// Ed25519 signature over `chunk_hash` bytes, hex-encoded.
    /// Proves the chunk was uploaded by the authorised bridge key.
    pub signature: String,
    /// Ed25519 verifying (public) key of the uploader bridge, hex-encoded.
    pub signer_pubkey: String,
}

/// File metadata record — the root of the file retrieval tree.
/// Contains the E2EE key-wrapping material so only the recipient can decrypt.
#[hdk_entry_helper]
#[derive(Clone)]
pub struct FileManifest {
    /// Human-readable filename.
    pub name: String,
    /// Original plaintext file size in bytes.
    pub size: u64,
    /// MIME type string, e.g. "application/pdf".
    pub mime_type: String,
    /// SHA-256 of the original plaintext file (computed before encryption).
    pub file_hash: String,
    /// SHA-256(chunk_hash_0 || chunk_hash_1 || ...) — merkle-style root.
    /// Lets a client verify the full set of chunks matches what was uploaded.
    pub root_hash: String,
    /// Total chunk count — must equal chunk_action_hashes.len().
    pub total_chunks: u32,
    /// Ordered list of ActionHash (base64) for each FileChunk entry on the DHT.
    pub chunk_action_hashes: Vec<String>,
    /// Mirrors the conductor `replication_factor` so clients know the
    /// fault-tolerance guarantee at upload time.
    pub redundancy_factor: u8,
    /// Ed25519 pubkey (hex) of the bridge that signed all chunks.
    pub uploader_pubkey: String,
    // ── E2EE fields ──────────────────────────────────────────────────────────
    /// DEK (Data Encryption Key) encrypted for the recipient via X25519 ECDH
    /// + AES-256-GCM. Format: hex( ephemeral_pubkey[32] || nonce[12] || ciphertext[32+16] ).
    /// Only the holder of `recipient_pubkey`'s private key can unwrap this.
    pub wrapped_dek: String,
    /// Recipient X25519 public key, hex-encoded.
    pub recipient_pubkey: String,
    /// Encryption algorithm identifier — MUST be "AES-256-GCM".
    /// Stored for forward-compatibility; unknown algorithms are rejected.
    pub dek_algorithm: String,
}

/// Heartbeat / presence record written by each node on startup and periodically.
/// Stored on the DHT so the dashboard can display live node health.
#[hdk_entry_helper]
#[derive(Clone)]
pub struct NodeStatus {
    /// Human-readable node label, e.g. "node-1".
    pub node_id: String,
    /// Holochain AgentPubKey (base64) of this node's conductor cell.
    pub agent_pubkey: String,
    /// "online" | "degraded" | "offline"
    pub status: String,
    /// Unix timestamp (seconds) when this record was created.
    pub timestamp: i64,
    /// Number of FileChunk entries currently held by this node.
    pub chunks_held: u32,
}

// ─────────────────────────────────────────────────────────────────────────────
// Entry & link type registrations (required by HDI)
// ─────────────────────────────────────────────────────────────────────────────

#[hdk_entry_types]
#[unit_enum(EntryTypesUnit)]
pub enum EntryTypes {
    FileChunk(FileChunk),
    FileManifest(FileManifest),
    NodeStatus(NodeStatus),
}

#[hdk_link_types]
pub enum LinkTypes {
    /// Links from the "all_files" Path anchor to each FileManifest ActionHash.
    AllFiles,
    /// Links from the "all_nodes" Path anchor to each NodeStatus ActionHash.
    AllNodes,
}

// ─────────────────────────────────────────────────────────────────────────────
// Top-level validation callback
// ─────────────────────────────────────────────────────────────────────────────

#[hdk_extern]
pub fn validate(op: Op) -> ExternResult<ValidateCallbackResult> {
    match op.flattened::<EntryTypes, LinkTypes>()? {
        FlatOp::StoreEntry(store_entry) => match store_entry {
            OpEntry::CreateEntry { app_entry, .. } => match app_entry {
                EntryTypes::FileChunk(chunk)       => validate_create_chunk(chunk),
                EntryTypes::FileManifest(manifest) => validate_create_manifest(manifest),
                EntryTypes::NodeStatus(status)     => validate_node_status(status),
            },
            // FileChunk and FileManifest are write-once / immutable.
            OpEntry::UpdateEntry { app_entry, .. } => match app_entry {
                EntryTypes::FileChunk(_)    =>
                    Ok(ValidateCallbackResult::Invalid(
                        "FileChunk entries are immutable and cannot be updated".into()
                    )),
                EntryTypes::FileManifest(_) =>
                    Ok(ValidateCallbackResult::Invalid(
                        "FileManifest entries are immutable and cannot be updated".into()
                    )),
                EntryTypes::NodeStatus(status) => validate_node_status(status),
            },
            _ => Ok(ValidateCallbackResult::Valid),
        },
        // Links, agent activity, etc. — currently unrestricted (future: ACL).
        _ => Ok(ValidateCallbackResult::Valid),
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// Validation rules: FileChunk
// ─────────────────────────────────────────────────────────────────────────────

fn validate_create_chunk(chunk: FileChunk) -> ExternResult<ValidateCallbackResult> {
    // Rule 1 — Ciphertext must be non-empty.
    if chunk.data.is_empty() {
        return Ok(ValidateCallbackResult::Invalid(
            "FileChunk.data (ciphertext) must not be empty".into()
        ));
    }

    // Rule 2 — AES-GCM nonce must be present.
    if chunk.nonce.is_empty() {
        return Ok(ValidateCallbackResult::Invalid(
            "FileChunk.nonce must not be empty".into()
        ));
    }

    // Rule 3 — chunk_hash must equal SHA-256(ciphertext).
    //           This binds the stored ciphertext to its content address.
    let computed_hash = sha256_hex(&chunk.data);
    if computed_hash != chunk.chunk_hash {
        return Ok(ValidateCallbackResult::Invalid(format!(
            "FileChunk.chunk_hash mismatch: stored={}, computed={}",
            chunk.chunk_hash, computed_hash
        )));
    }

    // Rule 4 — Ed25519 signature over chunk_hash must be valid.
    //           This proves the bridge (not an attacker) wrote this chunk.
    match verify_ed25519_signature(&chunk.signature, &chunk.chunk_hash, &chunk.signer_pubkey) {
        Ok(true)  => {}
        Ok(false) => return Ok(ValidateCallbackResult::Invalid(
            "FileChunk Ed25519 signature is invalid".into()
        )),
        Err(e)    => return Ok(ValidateCallbackResult::Invalid(
            format!("FileChunk signature verification error: {}", e)
        )),
    }

    // Rule 5 — chunk_index must be in-bounds.
    if chunk.chunk_index >= chunk.total_chunks {
        return Ok(ValidateCallbackResult::Invalid(format!(
            "FileChunk.chunk_index ({}) >= total_chunks ({})",
            chunk.chunk_index, chunk.total_chunks
        )));
    }

    // Rule 6 — signer_pubkey must decode to 32 bytes (valid Ed25519 key).
    match hex::decode(&chunk.signer_pubkey) {
        Ok(bytes) if bytes.len() == 32 => {}
        Ok(bytes) => return Ok(ValidateCallbackResult::Invalid(format!(
            "FileChunk.signer_pubkey must be 32 bytes, got {}", bytes.len()
        ))),
        Err(_) => return Ok(ValidateCallbackResult::Invalid(
            "FileChunk.signer_pubkey is not valid hex".into()
        )),
    }

    Ok(ValidateCallbackResult::Valid)
}

// ─────────────────────────────────────────────────────────────────────────────
// Validation rules: FileManifest
// ─────────────────────────────────────────────────────────────────────────────

fn validate_create_manifest(manifest: FileManifest) -> ExternResult<ValidateCallbackResult> {
    // Rule 1 — Name must not be blank.
    if manifest.name.trim().is_empty() {
        return Ok(ValidateCallbackResult::Invalid(
            "FileManifest.name must not be empty".into()
        ));
    }

    // Rule 2 — chunk_action_hashes count must match total_chunks.
    if manifest.chunk_action_hashes.len() != manifest.total_chunks as usize {
        return Ok(ValidateCallbackResult::Invalid(format!(
            "FileManifest.chunk_action_hashes.len() ({}) != total_chunks ({})",
            manifest.chunk_action_hashes.len(), manifest.total_chunks
        )));
    }

    // Rule 3 — E2EE fields must be present.
    if manifest.wrapped_dek.is_empty() {
        return Ok(ValidateCallbackResult::Invalid(
            "FileManifest.wrapped_dek must not be empty (E2EE required)".into()
        ));
    }
    if manifest.recipient_pubkey.is_empty() {
        return Ok(ValidateCallbackResult::Invalid(
            "FileManifest.recipient_pubkey must not be empty".into()
        ));
    }

    // Rule 4 — Only AES-256-GCM is accepted; reject unknown algorithms.
    if manifest.dek_algorithm != "AES-256-GCM" {
        return Ok(ValidateCallbackResult::Invalid(format!(
            "FileManifest.dek_algorithm '{}' is not supported; only 'AES-256-GCM' is allowed",
            manifest.dek_algorithm
        )));
    }

    // Rule 5 — redundancy_factor must be at least 1.
    if manifest.redundancy_factor == 0 {
        return Ok(ValidateCallbackResult::Invalid(
            "FileManifest.redundancy_factor must be >= 1".into()
        ));
    }

    Ok(ValidateCallbackResult::Valid)
}

// ─────────────────────────────────────────────────────────────────────────────
// Validation rules: NodeStatus
// ─────────────────────────────────────────────────────────────────────────────

fn validate_node_status(status: NodeStatus) -> ExternResult<ValidateCallbackResult> {
    let allowed = ["online", "degraded", "offline"];
    if !allowed.contains(&status.status.as_str()) {
        return Ok(ValidateCallbackResult::Invalid(format!(
            "NodeStatus.status '{}' is invalid; must be one of: online, degraded, offline",
            status.status
        )));
    }
    if status.node_id.trim().is_empty() {
        return Ok(ValidateCallbackResult::Invalid(
            "NodeStatus.node_id must not be empty".into()
        ));
    }
    Ok(ValidateCallbackResult::Valid)
}

// ─────────────────────────────────────────────────────────────────────────────
// Crypto helpers (pure functions, deterministic, wasm32-safe)
// ─────────────────────────────────────────────────────────────────────────────

/// Compute SHA-256 of `bytes` and return as lowercase hex string.
fn sha256_hex(bytes: &[u8]) -> String {
    let digest = Sha256::digest(bytes);
    hex::encode(digest)
}

/// Verify an Ed25519 signature.
///
/// * `signature_hex` — 64-byte signature, hex-encoded
/// * `message`       — the exact bytes that were signed (chunk_hash string as UTF-8)
/// * `pubkey_hex`    — 32-byte Ed25519 verifying key, hex-encoded
///
/// Returns `Ok(true)` if valid, `Ok(false)` if signature doesn't match,
/// `Err(...)` if the hex or key bytes are malformed.
fn verify_ed25519_signature(
    signature_hex: &str,
    message: &str,
    pubkey_hex: &str,
) -> Result<bool, String> {
    // Decode pubkey
    let pubkey_bytes = hex::decode(pubkey_hex)
        .map_err(|e| format!("pubkey hex decode failed: {}", e))?;
    let pubkey_array: [u8; 32] = pubkey_bytes
        .try_into()
        .map_err(|_| "pubkey must be exactly 32 bytes".to_string())?;
    let verifying_key = VerifyingKey::from_bytes(&pubkey_array)
        .map_err(|e| format!("invalid Ed25519 pubkey: {}", e))?;

    // Decode signature
    let sig_bytes = hex::decode(signature_hex)
        .map_err(|e| format!("signature hex decode failed: {}", e))?;
    let sig_array: [u8; 64] = sig_bytes
        .try_into()
        .map_err(|_| "signature must be exactly 64 bytes".to_string())?;
    let signature = Signature::from_bytes(&sig_array);

    // Verify — message is the chunk_hash string encoded as UTF-8
    Ok(verifying_key.verify(message.as_bytes(), &signature).is_ok())
}
