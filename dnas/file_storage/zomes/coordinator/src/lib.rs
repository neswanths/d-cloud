//! D-Cloud File Storage — Coordinator Zome
//!
//! Provides the public API of the hApp: CRUD operations against the DHT,
//! anchor-based file listing, and node health registration.
//!
//! Entry / link type definitions live in file_storage_integrity — imported
//! here via the path dependency so there is a single source of truth.
//!
//! Crate versions (locked): hdk = 0.3.6 | hdi = 0.4.6 | hex = 0.4.3

use hdk::prelude::*;
use file_storage_integrity::{EntryTypes, LinkTypes, FileChunk, FileManifest, NodeStatus};

// ─────────────────────────────────────────────────────────────────────────────
// Input / output wire types (serialised over the conductor AppWebSocket)
// ─────────────────────────────────────────────────────────────────────────────

/// Input for upload_chunk — mirrors FileChunk but carries raw bytes over the
/// wire so the coordinator can create the entry on behalf of the caller.
#[derive(Serialize, Deserialize, Debug, Clone)]
pub struct UploadChunkInput {
    pub file_hash: String,
    pub chunk_index: u32,
    pub total_chunks: u32,
    pub data: Vec<u8>,
    pub nonce: String,
    pub chunk_hash: String,
    pub signature: String,
    pub signer_pubkey: String,
}

/// Input for create_manifest.
#[derive(Serialize, Deserialize, Debug, Clone)]
pub struct CreateManifestInput {
    pub name: String,
    pub size: u64,
    pub mime_type: String,
    pub file_hash: String,
    pub root_hash: String,
    pub total_chunks: u32,
    pub chunk_action_hashes: Vec<String>,
    pub redundancy_factor: u8,
    pub uploader_pubkey: String,
    pub wrapped_dek: String,
    pub recipient_pubkey: String,
    pub dek_algorithm: String,
}

/// Input for register_node.
#[derive(Serialize, Deserialize, Debug, Clone)]
pub struct RegisterNodeInput {
    pub node_id: String,
    pub status: String,
    pub timestamp: i64,
    pub chunks_held: u32,
}

/// Output shape returned for a single file listing entry.
#[derive(Serialize, Deserialize, Debug)]
pub struct FileListEntry {
    pub action_hash: String,
    pub manifest: FileManifest,
}

/// Output shape for a node listing entry.
#[derive(Serialize, Deserialize, Debug)]
pub struct NodeListEntry {
    pub action_hash: String,
    pub status: NodeStatus,
}

/// Output from upload_chunk / create_manifest — base64-encoded ActionHash.
#[derive(Serialize, Deserialize, Debug)]
pub struct HashResult {
    pub action_hash: String,
}

// ─────────────────────────────────────────────────────────────────────────────
// Zome function: upload_chunk
// ─────────────────────────────────────────────────────────────────────────────

/// Store a single AES-256-GCM encrypted file chunk on the DHT.
///
/// The integrity zome validates the chunk_hash and Ed25519 signature before
/// the entry is accepted by any peer. Returns the ActionHash of the new entry.
#[hdk_extern]
pub fn upload_chunk(input: UploadChunkInput) -> ExternResult<HashResult> {
    let chunk = FileChunk {
        file_hash:    input.file_hash,
        chunk_index:  input.chunk_index,
        total_chunks: input.total_chunks,
        data:         input.data,
        nonce:        input.nonce,
        chunk_hash:   input.chunk_hash,
        signature:    input.signature,
        signer_pubkey: input.signer_pubkey,
    };

    let action_hash = create_entry(EntryTypes::FileChunk(chunk))?;
    Ok(HashResult {
        action_hash: action_hash_to_b64(&action_hash),
    })
}

// ─────────────────────────────────────────────────────────────────────────────
// Zome function: get_chunk
// ─────────────────────────────────────────────────────────────────────────────

/// Retrieve a FileChunk from the DHT by its ActionHash (base64-encoded string).
#[hdk_extern]
pub fn get_chunk(action_hash_b64: String) -> ExternResult<Option<FileChunk>> {
    let action_hash = b64_to_action_hash(&action_hash_b64)?;
    match get(action_hash, GetOptions::default())? {
        Some(record) => {
            let chunk: FileChunk = record
                .entry()
                .to_app_option()
                .map_err(|e| wasm_error!(WasmErrorInner::Guest(format!(
                    "Failed to deserialize FileChunk: {:?}", e
                ))))?
                .ok_or_else(|| wasm_error!(WasmErrorInner::Guest(
                    "Record has no app entry".to_string()
                )))?;
            Ok(Some(chunk))
        }
        None => Ok(None),
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// Zome function: create_manifest
// ─────────────────────────────────────────────────────────────────────────────

/// Register a FileManifest entry on the DHT and link it from the global
/// "all_files" anchor so it can be discovered by list_files.
#[hdk_extern]
pub fn create_manifest(input: CreateManifestInput) -> ExternResult<HashResult> {
    let manifest = FileManifest {
        name:                 input.name,
        size:                 input.size,
        mime_type:            input.mime_type,
        file_hash:            input.file_hash,
        root_hash:            input.root_hash,
        total_chunks:         input.total_chunks,
        chunk_action_hashes:  input.chunk_action_hashes,
        redundancy_factor:    input.redundancy_factor,
        uploader_pubkey:      input.uploader_pubkey,
        wrapped_dek:          input.wrapped_dek,
        recipient_pubkey:     input.recipient_pubkey,
        dek_algorithm:        input.dek_algorithm,
    };

    let action_hash = create_entry(EntryTypes::FileManifest(manifest))?;

    // Anchor the manifest under the well-known "all_files" path so any agent
    // can discover it without knowing the hash ahead of time.
    let path = Path::from("all_files");
    path.clone().typed(LinkTypes::AllFiles)?.ensure()?;
    create_link(
        path.path_entry_hash()?,
        action_hash.clone(),
        LinkTypes::AllFiles,
        (),
    )?;

    Ok(HashResult {
        action_hash: action_hash_to_b64(&action_hash),
    })
}

// ─────────────────────────────────────────────────────────────────────────────
// Zome function: get_manifest
// ─────────────────────────────────────────────────────────────────────────────

/// Retrieve a FileManifest from the DHT by its ActionHash (base64).
#[hdk_extern]
pub fn get_manifest(action_hash_b64: String) -> ExternResult<Option<FileManifest>> {
    let action_hash = b64_to_action_hash(&action_hash_b64)?;
    match get(action_hash, GetOptions::default())? {
        Some(record) => {
            let manifest: FileManifest = record
                .entry()
                .to_app_option()
                .map_err(|e| wasm_error!(WasmErrorInner::Guest(format!(
                    "Failed to deserialize FileManifest: {:?}", e
                ))))?
                .ok_or_else(|| wasm_error!(WasmErrorInner::Guest(
                    "Record has no app entry".to_string()
                )))?;
            Ok(Some(manifest))
        }
        None => Ok(None),
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// Zome function: list_files
// ─────────────────────────────────────────────────────────────────────────────

/// Return all FileManifest records visible via the "all_files" anchor.
/// Chunks are NOT included — callers fetch them individually via get_chunk.
#[hdk_extern]
pub fn list_files(_: ()) -> ExternResult<Vec<FileListEntry>> {
    let path = Path::from("all_files");
    let links = get_links(
        GetLinksInputBuilder::try_new(path.path_entry_hash()?, LinkTypes::AllFiles)?.build(),
    )?;

    let mut entries: Vec<FileListEntry> = Vec::new();
    for link in links {
        if let Some(action_hash) = link.target.into_action_hash() {
            if let Some(record) = get(action_hash.clone(), GetOptions::default())? {
                if let Ok(Some(manifest)) = record
                    .entry()
                    .to_app_option::<FileManifest>()
                {
                    entries.push(FileListEntry {
                        action_hash: action_hash_to_b64(&action_hash),
                        manifest,
                    });
                }
            }
        }
    }
    Ok(entries)
}

// ─────────────────────────────────────────────────────────────────────────────
// Zome function: register_node
// ─────────────────────────────────────────────────────────────────────────────

/// Publish a NodeStatus entry for this agent, linked from "all_nodes".
/// Called on conductor startup and periodically as a heartbeat.
#[hdk_extern]
pub fn register_node(input: RegisterNodeInput) -> ExternResult<HashResult> {
    let agent_info = agent_info()?;
    let status = NodeStatus {
        node_id:      input.node_id,
        agent_pubkey: format!("{:?}", agent_info.agent_latest_pubkey),
        status:       input.status,
        timestamp:    input.timestamp,
        chunks_held:  input.chunks_held,
    };

    let action_hash = create_entry(EntryTypes::NodeStatus(status))?;

    let path = Path::from("all_nodes");
    path.clone().typed(LinkTypes::AllNodes)?.ensure()?;
    create_link(
        path.path_entry_hash()?,
        action_hash.clone(),
        LinkTypes::AllNodes,
        (),
    )?;

    Ok(HashResult {
        action_hash: action_hash_to_b64(&action_hash),
    })
}

// ─────────────────────────────────────────────────────────────────────────────
// Zome function: get_network_nodes
// ─────────────────────────────────────────────────────────────────────────────

/// Return all NodeStatus records currently on the DHT under "all_nodes".
#[hdk_extern]
pub fn get_network_nodes(_: ()) -> ExternResult<Vec<NodeListEntry>> {
    let path = Path::from("all_nodes");
    let links = get_links(
        GetLinksInputBuilder::try_new(path.path_entry_hash()?, LinkTypes::AllNodes)?.build(),
    )?;

    let mut nodes: Vec<NodeListEntry> = Vec::new();
    for link in links {
        if let Some(action_hash) = link.target.into_action_hash() {
            if let Some(record) = get(action_hash.clone(), GetOptions::default())? {
                if let Ok(Some(status)) = record
                    .entry()
                    .to_app_option::<NodeStatus>()
                {
                    nodes.push(NodeListEntry {
                        action_hash: action_hash_to_b64(&action_hash),
                        status,
                    });
                }
            }
        }
    }
    Ok(nodes)
}

// ─────────────────────────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────────────────────────

/// Encode an ActionHash to base64 string (URL-safe, no padding).
fn action_hash_to_b64(hash: &ActionHash) -> String {
    use base64::{Engine as _, engine::general_purpose::URL_SAFE_NO_PAD};
    URL_SAFE_NO_PAD.encode(hash.get_raw_39())
}

/// Decode a base64 ActionHash string back to ActionHash.
fn b64_to_action_hash(b64: &str) -> ExternResult<ActionHash> {
    use base64::{Engine as _, engine::general_purpose::URL_SAFE_NO_PAD};
    let bytes = URL_SAFE_NO_PAD.decode(b64).map_err(|e| {
        wasm_error!(WasmErrorInner::Guest(format!(
            "Invalid base64 ActionHash '{}': {}", b64, e
        )))
    })?;
    ActionHash::from_raw_39(bytes).map_err(|e| {
        wasm_error!(WasmErrorInner::Guest(format!(
            "Invalid ActionHash bytes: {:?}", e
        )))
    })
}
