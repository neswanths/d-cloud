# D-Cloud

> Decentralized storage with cryptographic proof at every step. No central authority. No vendor lock-in. No single point of failure.

![Demo](assets/demo.gif)

[Watch full demo (2:45) →] https://drive.google.com/file/d/1_mv_s_McooPA5eOnclQVtpPp7hXJhhSR/view?usp=sharing

---

## What is D-Cloud?

D-Cloud distributes your files across a mesh of independent nodes. Every chunk is encrypted, signed, and content-addressed before it ever leaves your machine. There is no master key, no control plane, and no trusted intermediary — just math.


---

## How it works

When you upload a file:

1. The file is split into **64 KB chunks**, each assigned a SHA-256 content address
2. Each chunk is encrypted with a per-file **AES-256-GCM** key (DEK)
3. Every chunk is **Ed25519 signed** — unforgeable proof of custody
4. The DEK is wrapped uniquely for each peer's **X25519 public key** and stored in the manifest — no central key server
5. The manifest (a Merkle root of all chunk hashes) is broadcast to all live nodes

On retrieval, the bridge unwraps the DEK using its private key, fetches chunks from any available node, verifies every signature and hash, and reassembles the file. A dead or compromised node is automatically skipped.

---

## Architecture
┌─────────────────────────────────────────────┐
│                  Frontend                    │
│           React + Vite + TypeScript          │
│              localhost:5173                  │
└──────────────────┬──────────────────────────┘
│ REST
┌──────────────────▼──────────────────────────┐
│               FastAPI Bridge                 │
│   Chunking · Encryption · Node Routing       │
│              localhost:3000                  │
└───────┬──────────┬───────────────┬───────────┘
│          │               │
┌────▼───┐ ┌────▼───┐    ┌─────▼──┐
│ Node 1 │ │ Node 2 │    │ Node 3 │
│ :8001  │ │ :8002  │    │ :8003  │
└────────┘ └────────┘    └────────┘
SQLite · Ed25519 Identity · Chunk Store

Each node is an independently addressable peer with its own cryptographic identity. The bridge orchestrates chunking, encryption, and distribution — but holds no permanent authority over the data.

---

## Stack

| Layer | Technology |
|---|---|
| Frontend | React 19, Vite 7, TypeScript, Tailwind CSS |
| Bridge API | Python, FastAPI, Uvicorn |
| Cryptography | AES-256-GCM, Ed25519, X25519/ECDH, HKDF, SHA-256 |
| Node Server | Python, SQLite |
| Launcher | PowerShell with subnet auto-discovery |

---

## Security Model

- **AES-256-GCM** — authenticated encryption for every chunk; tampering is detected before decryption completes
- **Ed25519 signatures** — each chunk carries an unforgeable proof of which node stored it
- **X25519 + HKDF key wrapping** — the DEK is encrypted per-recipient; no node ever sees another peer's plaintext key
- **Merkle root verification** — the full file hash is recomputed on retrieval and compared against the manifest; any corruption is caught before the file is served
- **Zero trust retrieval** — every chunk is independently verified at the bridge before reassembly

---

## Running locally

**Prerequisites:** Python 3.11+, Node.js 18+, PowerShell 7+

```powershell
# Clone the repo
git clone https://github.com/neswanths/d-cloud.git
cd d-cloud

# Install bridge dependencies
cd api-bridge
pip install -r requirements.txt
cd ..

# Install frontend dependencies
cd frontend
npm install
cd ..

# Launch everything
./start.ps1
```

The launcher first scans for LAN nodes. If none are reachable, it automatically switches to single-machine mode and spins up 3 local nodes. Once running:

- Frontend → http://localhost:5173  
- Bridge API → http://localhost:3000/api/health

---

## Project Structure
d-cloud/
├── api-bridge/          # FastAPI bridge — chunking, crypto, node routing
│   ├── main.py          # REST endpoints and orchestration
│   ├── crypto.py        # AES-GCM, Ed25519, X25519 implementation
│   ├── node_pool.py     # Fault-tolerant node management
│   └── keys/            # Generated Ed25519/X25519 keypairs
├── frontend/            # React/Vite UI
├── js-client/           # JS client library for Conductor API
├── node_server.py       # Standalone DHT node (SQLite-backed)
├── scripts/             # Setup and test utilities
└── start.ps1            # Smart launcher with LAN/local fallback

---

## Current Status

Working local prototype with a fully implemented cryptographic pipeline. The system handles real encryption, real signing, real fault-tolerant retrieval, and real multi-node distribution on a single machine or across a LAN.

**What's working:**
- Full encrypt → sign → chunk → distribute → verify → reassemble pipeline
- Automatic dead-node failover during retrieval
- Multi-recipient DEK wrapping (each peer gets an independently wrapped key)
- LAN auto-discovery with single-machine fallback
- Persistent chunk storage across node restarts (SQLite)

**What's next:**
- True DHT gossip protocol replacing broadcast replication
- Node registration and dynamic peer discovery
- Public testnet deployment

---

## License

MIT
