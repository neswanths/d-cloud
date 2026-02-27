# D-Cloud — Decentralised Cloud Storage

> **Agent-centric, peer-to-peer, end-to-end encrypted file storage powered by Holochain.**
> No centralized control plane. No vendor lock-in. No blockchain overhead.

---

## Architecture

```
Web UI  ──HTTPS──►  FastAPI Bridge  ──WebSocket──►  Holochain Conductor(s)
                        │                                  │
                 E2EE (X25519 + AES-256-GCM)        DHT (encrypted shards)
                 Ed25519 chunk signing               replication_factor = 5
```

Each file is:
1. Split into **64 KB chunks**
2. Each chunk **AES-256-GCM encrypted** with a per-file DEK
3. Each chunk **SHA-256 hashed** and **Ed25519 signed**
4. DEK **wrapped with recipient's X25519 pubkey** (only they can decrypt)
5. Chunks stored on the **Holochain DHT** — replicated across all peers

---

## Cryptographic Security Properties

| Property | Implementation |
|---|---|
| **Confidentiality** | AES-256-GCM — DHT nodes hold ciphertext only |
| **Key privacy** | X25519 ECDH + HKDF-SHA256 DEK wrapping |
| **Integrity** | SHA-256(ciphertext) per chunk + merkle root hash |
| **Authenticity** | Ed25519 signature per chunk — verified by integrity zome |
| **Tamper evidence** | Integrity zome rejects bad hashes/signatures at DHT gossip layer |

---

## Project Structure

```
d-cloud/
├── Cargo.toml                         # Rust workspace (locked versions)
├── happ.yaml                          # Holochain hApp manifest
├── dnas/file_storage/
│   ├── workdir/dna.yaml               # DNA manifest (replication_factor = 5)
│   └── zomes/
│       ├── integrity/src/lib.rs       # Entry types + validation rules (HDI)
│       └── coordinator/src/lib.rs     # Zome API functions (HDK)
├── api-bridge/
│   ├── main.py                        # FastAPI app (upload / retrieve / list)
│   ├── crypto.py                      # AES-256-GCM, X25519, Ed25519, SHA-256
│   ├── conductor_client.py            # Holochain WebSocket conductor pool
│   ├── models.py                      # Pydantic response models
│   ├── requirements.txt               # All packages pinned with ==
│   ├── .env.example                   # Config template
│   └── tests/
│       ├── test_crypto.py             # Crypto unit tests
│       └── test_api.py                # API integration tests (mock conductor)
└── scripts/
    ├── setup-demo.sh                  # Start 3 nodes for the demo
    ├── kill-node.sh                   # Kill a node live (Acts 2 & 4)
    └── generate-keys.py               # Generate Ed25519 + X25519 keypairs
```

---

## Prerequisites

| Tool | Version | Platform |
|---|---|---|
| **WSL2 + Ubuntu 22.04** | — | Windows (required for Holochain) |
| **Nix / Holonix** | Holochain 0.3.6 | WSL2 |
| **Rust toolchain** | 1.80.1 stable | WSL2 |
| **wasm32 target** | — | `rustup target add wasm32-unknown-unknown` |
| **Python** | 3.11.9 | Windows or WSL2 |
| **hc CLI** | 0.3.6 | WSL2 (via Nix) |

---

## Setup

### 1. Install Holochain dev environment (WSL2)

```bash
# Install Nix
sh <(curl -L https://nixos.org/nix/install) --daemon

# Install Holonix (Holochain 0.3.6 toolchain)
nix-shell https://holochain.love

# Verify
holochain --version   # holochain 0.3.6
hc --version          # hc 0.3.6
```

### 2. Build the Rust DNA

> **Important**: Run this in a **plain WSL2 terminal** (do NOT enter `nix-shell` first).
> The nix shell pins Rust to 1.81 which conflicts with newer crate editions.
> Only the `hc` packaging commands need nix — the WASM compiler does not.

```bash
cd d-cloud

# Delete any old target/ directory produced by previous nix-shell builds
rm -rf target/

# Add WASM target (once per machine)
rustup target add wasm32-unknown-unknown

# Verify Rust ≥ 1.85 is active (should print 1.93.x or later)
rustc --version

# Build both WASM zomes
cargo build --release --target wasm32-unknown-unknown
```

### 3. Package the DNA and hApp (nix-shell terminal)

Open a **separate** terminal and enter the nix-shell for this step only:

```bash
nix-shell https://holochain.love

cd d-cloud

# Pack the DNA bundle
hc dna pack dnas/file_storage/workdir/

# Pack the hApp bundle (happ.yaml is in the project root, use . not workdir/)
hc app pack .

# Expected output: d-cloud.happ in the project root
```

### 4. Set up the Python bridge

```bash
cd api-bridge
python3.11 -m venv .venv
source .venv/bin/activate        # Linux/WSL2
# or:  .venv\Scripts\activate    # Windows native

pip install -r requirements.txt

# Generate cryptographic keypairs
python ../scripts/generate-keys.py

# Copy and configure environment
cp .env.example .env
# Edit .env if you change ports
```

### 4. Run the tests (no conductor needed)

```bash
cd api-bridge
source .venv/bin/activate

# Crypto unit tests
pytest tests/test_crypto.py -v

# API integration tests (mocked conductor)
pytest tests/test_api.py -v
```

---

## Demo Walkthrough

### Act 1 — Upload

```bash
# Terminal 1: Start 3 nodes
bash scripts/setup-demo.sh

# Terminal 2: Start the bridge
cd api-bridge && uvicorn main:app --port 3000

# Terminal 3: Upload a file
curl -F "file=@demo.pdf" http://localhost:3000/api/upload
# → {"manifest_hash": "chunk-0001", "total_chunks": 4, "dek_algorithm": "AES-256-GCM", ...}

# View all files
curl http://localhost:3000/api/files | python3 -m json.tool

# View node health
curl http://localhost:3000/api/nodes | python3 -m json.tool
```

### Act 2 — Kill Node 1

```bash
bash scripts/kill-node.sh 1
# → 🔴  Node 1 is DOWN
```

### Act 3 — File still retrievable

```bash
HASH="<manifest_hash from upload>"
curl http://localhost:3000/api/file/$HASH -o retrieved.pdf
diff demo.pdf retrieved.pdf     # ← zero difference
```

### Act 4 — Kill Node 2 too

```bash
bash scripts/kill-node.sh 2
# → 🔴  Node 2 also DOWN

curl http://localhost:3000/api/file/$HASH -o retrieved2.pdf
diff demo.pdf retrieved2.pdf    # ← still identical — Node 3 serves it
```

---

## REST API Reference

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/upload` | Multipart upload — returns `manifest_hash` |
| `GET` | `/api/file/{hash}` | Retrieve + decrypt a file |
| `GET` | `/api/files` | List all files on the DHT |
| `GET` | `/api/nodes` | List all node status records |
| `POST` | `/api/nodes/register` | Register a node heartbeat |
| `GET` | `/api/health` | Bridge health + key fingerprints |

---

## Holochain Concepts Used

| Concept | Role in D-Cloud |
|---|---|
| **DNA** | Application rules — the shared constitution of the network |
| **Integrity Zome (HDI)** | Defines `FileChunk`, `FileManifest`, `NodeStatus` + validation |
| **Coordinator Zome (HDK)** | Public API: `upload_chunk`, `get_chunk`, `create_manifest`, etc. |
| **Source Chain** | Each node's tamper-evident personal action log |
| **DHT** | Shared content-addressed storage — chunks live here |
| **Anchors / Paths** | `"all_files"` and `"all_nodes"` paths act as DHT indexes |
| **ActionHash** | Content-addressed ID returned after each `create_entry` |
| **AgentPubKey** | Ed25519-based cryptographic identity of each conductor cell |
| **AppWebsocket** | API the bridge uses to call zome functions |
| **replication_factor** | DHT gossip ensures each chunk is held by ≥ 5 peers |

---

## Version Lock

All dependency versions are **pinned** and must not be changed without explicit instruction.
See [`Cargo.toml`](Cargo.toml) and [`api-bridge/requirements.txt`](api-bridge/requirements.txt).

| Toolchain | Version |
|---|---|
| holochain | 0.3.6 |
| hdi | 0.4.6 |
| hdk | 0.3.6 |
| Python | 3.11.9 |
| fastapi | 0.110.0 |
| cryptography | 42.0.5 |
