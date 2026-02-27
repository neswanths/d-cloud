#!/usr/bin/env bash
# ─── D-Cloud — Run Everything (Nodes + Bridge) ───────────────────────────────
#
# Run this from a persistent WSL terminal:
#
#   bash /mnt/c/Users/neswa/.gemini/antigravity/scratch/d-cloud/scripts/run-all.sh
#
# This script:
#   1. Starts 3 Holochain conductor nodes (ports 9001, 9101, 9201)
#   2. Waits for them to be ready
#   3. Starts the FastAPI bridge (port 3000)
#   4. Keeps everything alive in this terminal (Ctrl+C = graceful shutdown)
#
# Prerequisites: Run from inside WSL (Ubuntu)
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

# ── Binary / project paths ────────────────────────────────────────────────────
HC_STORE_DIR="/nix/store/2bpx02w4h86h1mx369wm9xswmrk71l1m-holochain-0.3.6/bin"
HOLOCHAIN="${HC_STORE_DIR}/holochain"
HC="${HC_STORE_DIR}/hc"

PROJECT_DIR="/mnt/c/Users/neswa/.gemini/antigravity/scratch/d-cloud"
API_DIR="${PROJECT_DIR}/api-bridge"
HAPP_BUNDLE="${PROJECT_DIR}/d-cloud.happ"
APP_ID="d-cloud"

declare -A ADMIN_PORTS=([1]=9000 [2]=9100 [3]=9200)
declare -A APP_PORTS=(  [1]=9001 [2]=9101 [3]=9201)
declare -A DATA_DIRS=(
    [1]="/tmp/d-cloud-demo/node1"
    [2]="/tmp/d-cloud-demo/node2"
    [3]="/tmp/d-cloud-demo/node3"
)

PIDS=()

# ── Graceful shutdown ─────────────────────────────────────────────────────────
cleanup() {
    echo ""
    echo "🛑  Shutting down D-Cloud …"
    for pid in "${PIDS[@]}"; do
        kill "${pid}" 2>/dev/null || true
    done
    wait 2>/dev/null || true
    echo "    All processes stopped."
    exit 0
}
trap cleanup INT TERM

# ── Wait for TCP port ─────────────────────────────────────────────────────────
wait_for_port() {
    local port="$1"
    for i in $(seq 1 30); do
        if 2>/dev/null </dev/tcp/localhost/"${port}"; then return 0; fi
        sleep 1
    done
    echo "⚠️   Timed out waiting for :${port}" >&2
    return 1
}

# ── Start a conductor node ────────────────────────────────────────────────────
start_node() {
    local N="$1"
    local DATA_DIR="${DATA_DIRS[$N]}"
    local ADMIN_PORT="${ADMIN_PORTS[$N]}"
    local APP_PORT="${APP_PORTS[$N]}"
    local CONFIG="${DATA_DIR}/conductor-config.yaml"

    mkdir -p "${DATA_DIR}"
    cat > "${CONFIG}" <<EOF
---
data_root_path: ${DATA_DIR}
keystore:
  type: lair_server_in_proc
network:
  network_type: quic_bootstrap
  bootstrap_service: https://bootstrap.holo.host
  transport_pool:
    - type: webrtc
      signal_url: wss://signal.holo.host
db_sync_strategy: Fast
admin_interfaces:
  - driver:
      type: websocket
      port: ${ADMIN_PORT}
      allowed_origins: "*"
EOF

    echo "🚀  Starting Node ${N} (admin=:${ADMIN_PORT}, app=:${APP_PORT})"
    echo "" | "${HOLOCHAIN}" -p -c "${CONFIG}" \
        >> "${DATA_DIR}/conductor.log" 2>&1 &
    local PID=$!
    PIDS+=("${PID}")
    echo "    PID=${PID}"

    # Wait for admin port
    if ! wait_for_port "${ADMIN_PORT}"; then
        echo "❌  Node ${N} failed to start. Check: ${DATA_DIR}/conductor.log"
        exit 1
    fi

    # Install, enable, attach app interface
    "${HC}" sandbox call --running "${ADMIN_PORT}" install-app \
        --app-id "${APP_ID}" "${HAPP_BUNDLE}" 2>/dev/null || true
    "${HC}" sandbox call --running "${ADMIN_PORT}" enable-app "${APP_ID}" 2>/dev/null || true
    "${HC}" sandbox call --running "${ADMIN_PORT}" add-app-ws "${APP_PORT}" \
        --allowed-origins "*" 2>/dev/null || true

    echo "✅  Node ${N} ready — ws://localhost:${APP_PORT}"
}

# ── Pre-flight ────────────────────────────────────────────────────────────────
[[ -x "${HOLOCHAIN}" ]] || { echo "❌  holochain not found at ${HOLOCHAIN}"; exit 1; }
[[ -f "${HAPP_BUNDLE}" ]] || { echo "❌  happ not found at ${HAPP_BUNDLE}"; exit 1; }
[[ -f "${API_DIR}/.venv/bin/uvicorn" ]] || { echo "❌  uvicorn not found in .venv"; exit 1; }

# ── Clean slate ───────────────────────────────────────────────────────────────
rm -rf "/tmp/d-cloud-demo"
mkdir -p "/tmp/d-cloud-demo"

# ── Start nodes ───────────────────────────────────────────────────────────────
echo "════════════════════════════════════════════════"
echo "  D-Cloud — Starting 3 Holochain Nodes"
echo "════════════════════════════════════════════════"
for N in 1 2 3; do
    start_node "${N}"
done
echo ""

# ── Start bridge ──────────────────────────────────────────────────────────────
echo "🌉  Starting FastAPI bridge on :3000 …"
cd "${API_DIR}"
.venv/bin/uvicorn main:app --host 0.0.0.0 --port 3000 > /tmp/uvicorn.log 2>&1 &
BRIDGE_PID=$!
PIDS+=("${BRIDGE_PID}")
sleep 2

echo ""
echo "════════════════════════════════════════════════"
echo "  D-Cloud is LIVE 🟢"
echo "════════════════════════════════════════════════"
echo ""
echo "  Node 1   ws://localhost:9001"
echo "  Node 2   ws://localhost:9101"
echo "  Node 3   ws://localhost:9201"
echo "  Bridge   http://localhost:3000"
echo ""
echo "  Test commands (from Windows PowerShell or another WSL tab):"
echo ""
echo "  # Health check:"
echo "  curl http://localhost:3000/api/health"
echo ""
echo "  # Upload a file:"
echo "  curl -F 'file=@README.md' http://localhost:3000/api/upload"
echo ""
echo "  # List files:"
echo "  curl http://localhost:3000/api/files"
echo ""
echo "  # Kill a node (fault-tolerance demo):"
echo "  bash ${PROJECT_DIR}/scripts/kill-node.sh 1"
echo ""
echo "  Press Ctrl+C to stop everything."
echo "════════════════════════════════════════════════"

# ── Keep alive ────────────────────────────────────────────────────────────────
wait "${BRIDGE_PID}"
