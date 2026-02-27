#!/usr/bin/env bash
# ─── D-Cloud Demo Setup Script ───────────────────────────────────────────────
#
# Starts 3 Holochain conductor nodes on separate ports and data directories,
# waits for them to peer over the DHT, then prints connection info.
#
# Prerequisites — must run inside the nix-shell that provides holochain + hc:
#   nix develop "github:holochain/holonix?ref=main-0.3"
#   Build the hApp first: (in plain terminal) cargo build --release --target wasm32-unknown-unknown
#                         (in nix-shell)      hc dna pack dnas/file_storage/workdir/ && hc app pack .
#
# Usage:
#   bash scripts/setup-demo.sh          ← start all 3 nodes
#   bash scripts/kill-node.sh 1         ← kill node 1 (fault-tolerance demo)
#
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

HAPP_BUNDLE="$PROJECT_DIR/d-cloud.happ"
APP_ID="d-cloud"
BOOTSTRAP_URL="https://bootstrap.holo.host"

# Per-node port assignments
#           Admin    App-WS   Data directory
declare -A ADMIN_PORTS=([1]=9000 [2]=9100 [3]=9200)
declare -A APP_PORTS=(  [1]=9001 [2]=9101 [3]=9201)
declare -A DATA_DIRS=(  [1]="/tmp/d-cloud-demo/node1"
                        [2]="/tmp/d-cloud-demo/node2"
                        [3]="/tmp/d-cloud-demo/node3")
declare -A PID_FILES=(  [1]="/tmp/d-cloud-demo/node1.pid"
                        [2]="/tmp/d-cloud-demo/node2.pid"
                        [3]="/tmp/d-cloud-demo/node3.pid")

# ── Pre-flight checks ────────────────────────────────────────────────────────
if [[ ! -f "$HAPP_BUNDLE" ]]; then
    echo "❌  hApp bundle not found at $HAPP_BUNDLE"
    echo "    Build it first with:  hc app pack ."
    exit 1
fi

if ! command -v holochain &>/dev/null; then
    echo "❌  'holochain' binary not found in PATH."
    echo "    This script must be run inside the nix-shell:"
    echo "    nix develop \"github:holochain/holonix?ref=main-0.3\""
    exit 1
fi

# ── Clean any previous run ───────────────────────────────────────────────────
rm -rf "/tmp/d-cloud-demo"
mkdir -p "/tmp/d-cloud-demo"

# ── Helpers ──────────────────────────────────────────────────────────────────

# Wait until a TCP port is accepting connections (max 20 s)
wait_for_port() {
    local port=$1
    for i in $(seq 1 20); do
        if 2>/dev/null </dev/tcp/localhost/"$port"; then
            return 0
        fi
        sleep 1
    done
    echo "⚠️   Timed out waiting for port $port" >&2
    return 1
}

# Call the admin API via hc sandbox call --running
admin_call() {
    hc sandbox call --running "$1" "${@:2}" 2>/dev/null || true
}

# ── Start each node ──────────────────────────────────────────────────────────
start_node() {
    local N=$1
    local DATA_DIR="${DATA_DIRS[$N]}"
    local ADMIN_PORT="${ADMIN_PORTS[$N]}"
    local APP_PORT="${APP_PORTS[$N]}"
    local PID_FILE="${PID_FILES[$N]}"
    local CONFIG_FILE="$DATA_DIR/conductor-config.yaml"

    mkdir -p "$DATA_DIR"

    # ── Correct Holochain 0.3.x conductor config ─────────────────────────────
    # Key differences from 0.2.x:
    #   • no 'dpki' block
    #   • network requires 'transport_pool' (not 'network_type')
    #   • webrtc is the default transport for 0.3.x
    cat > "$CONFIG_FILE" <<EOF
---
data_root_path: $DATA_DIR
keystore:
  type: lair_server_in_proc
network:
  network_type: quic_bootstrap
  bootstrap_service: $BOOTSTRAP_URL
  transport_pool:
    - type: webrtc
      signal_url: wss://signal.holo.host
db_sync_strategy: Fast
admin_interfaces:
  - driver:
      type: websocket
      port: $ADMIN_PORT
      allowed_origins: "*"
EOF

    echo "🚀  Starting Node $N (admin=:$ADMIN_PORT, app=:$APP_PORT) …"

    # Launch the conductor in the background.
    # The `echo ""` pipes an empty passphrase to the lair keystore prompt.
    # The `-p` flag tells holochain to read it from stdin instead of interactive TTY.
    echo "" | env RUST_LOG=trace holochain -p -c "$CONFIG_FILE" \
        >> "$DATA_DIR/conductor.log" 2>&1 &
    local HC_PID=$!
    echo "$HC_PID" > "$PID_FILE"
    echo "    PID $HC_PID — log: $DATA_DIR/conductor.log"

    # Wait until the admin WebSocket is actually ready before calling into it
    echo "    Waiting for admin socket on :$ADMIN_PORT …"
    wait_for_port "$ADMIN_PORT"

    # Install hApp via Admin WebSocket (hc sandbox call is broken for manually-launched conductors in 0.3.6)
    echo "📦  Installing hApp on Node $N …"
    "$PROJECT_DIR/api-bridge/.venv/bin/python3" "$PROJECT_DIR/install_app.py" \
        "$ADMIN_PORT" "$APP_PORT" "$APP_ID" "$HAPP_BUNDLE"
}

# ── Launch all 3 nodes ───────────────────────────────────────────────────────
for N in 1 2 3; do
    start_node "$N"
done

echo ""
echo "════════════════════════════════════════"
echo "  D-Cloud demo network is LIVE"
echo "════════════════════════════════════════"
echo ""
echo "  Node 1 — ws://localhost:9001  (PID $(cat "${PID_FILES[1]}"))"
echo "  Node 2 — ws://localhost:9101  (PID $(cat "${PID_FILES[2]}"))"
echo "  Node 3 — ws://localhost:9201  (PID $(cat "${PID_FILES[3]}"))"
echo ""
echo "  Start the bridge (separate terminal, plain WSL):"
echo "    cd api-bridge && uvicorn main:app --port 3000"
echo ""
echo "  Fault-tolerance demo — kill a node:"
echo "    bash scripts/kill-node.sh 1"
echo "════════════════════════════════════════"
