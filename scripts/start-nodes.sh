#!/usr/bin/env bash
# ─── D-Cloud Demo Startup — Uses Nix Store Binaries Directly ─────────────────
#
# Works WITHOUT nix being on PATH — uses the absolute nix store paths found in
# this environment.  Run from WSL (Ubuntu):
#
#   bash /mnt/c/Users/neswa/.gemini/antigravity/scratch/d-cloud/scripts/start-nodes.sh
#
# Prerequisites:
#   • d-cloud.happ bundle must exist (already built at project root)
#   • Nix store at /nix/store (already present)
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

# ── Absolute binary paths (from nix store) ───────────────────────────────────
HC_STORE_DIR="/nix/store/2bpx02w4h86h1mx369wm9xswmrk71l1m-holochain-0.3.6/bin"
HOLOCHAIN="${HC_STORE_DIR}/holochain"
HC="${HC_STORE_DIR}/hc"

# ── Project paths ─────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
HAPP_BUNDLE="${PROJECT_DIR}/d-cloud.happ"
APP_ID="d-cloud"
BOOTSTRAP_URL="https://bootstrap.holo.host"

# ── Port assignments ──────────────────────────────────────────────────────────
#       Admin WS   App WS    Data dir
# Node 1:  9000     9001     /tmp/d-cloud-demo/node1
# Node 2:  9100     9101     /tmp/d-cloud-demo/node2
# Node 3:  9200     9201     /tmp/d-cloud-demo/node3

declare -A ADMIN_PORTS=([1]=9000 [2]=9100 [3]=9200)
declare -A APP_PORTS=(  [1]=9001 [2]=9101 [3]=9201)
declare -A DATA_DIRS=(
    [1]="/tmp/d-cloud-demo/node1"
    [2]="/tmp/d-cloud-demo/node2"
    [3]="/tmp/d-cloud-demo/node3"
)
declare -A PID_FILES=(
    [1]="/tmp/d-cloud-demo/node1.pid"
    [2]="/tmp/d-cloud-demo/node2.pid"
    [3]="/tmp/d-cloud-demo/node3.pid"
)

# ── Pre-flight checks ─────────────────────────────────────────────────────────
if [[ ! -x "${HOLOCHAIN}" ]]; then
    echo "❌  holochain binary not found at ${HOLOCHAIN}"
    exit 1
fi

if [[ ! -x "${HC}" ]]; then
    echo "❌  hc binary not found at ${HC}"
    exit 1
fi

if [[ ! -f "${HAPP_BUNDLE}" ]]; then
    echo "❌  hApp bundle not found at ${HAPP_BUNDLE}"
    echo "    Build it with: cargo build --release --target wasm32-unknown-unknown"
    echo "    Then (in nix-shell): hc dna pack dnas/file_storage/workdir/ && hc app pack ."
    exit 1
fi

echo "✅  holochain: ${HOLOCHAIN}"
echo "✅  happ:      ${HAPP_BUNDLE}"
echo ""

# ── Clean any previous run ────────────────────────────────────────────────────
rm -rf "/tmp/d-cloud-demo"
mkdir -p "/tmp/d-cloud-demo"

# ── Helpers ───────────────────────────────────────────────────────────────────

wait_for_port() {
    local port="$1"
    local label="${2:-port ${port}}"
    echo -n "    Waiting for ${label} on :${port} "
    for i in $(seq 1 30); do
        if 2>/dev/null </dev/tcp/localhost/"${port}"; then
            echo " ✓"
            return 0
        fi
        echo -n "."
        sleep 1
    done
    echo ""
    echo "⚠️   Timed out waiting for :${port}" >&2
    return 1
}

# Decode the agent key printed by hc sandbox call new-agent-pub-key
get_agent_key() {
    local admin_port="$1"
    "${HC}" sandbox call --running "${admin_port}" new-agent-pub-key 2>/dev/null \
        | grep -o 'uhCAk[A-Za-z0-9_-]*' | head -1 || echo ""
}

# ── start_node: write config, launch conductor, install app ──────────────────
start_node() {
    local N="$1"
    local DATA_DIR="${DATA_DIRS[$N]}"
    local ADMIN_PORT="${ADMIN_PORTS[$N]}"
    local APP_PORT="${APP_PORTS[$N]}"
    local PID_FILE="${PID_FILES[$N]}"
    local CONFIG_FILE="${DATA_DIR}/conductor-config.yaml"

    mkdir -p "${DATA_DIR}"

    # ── Write conductor config (Holochain 0.3.x format) ──────────────────────
    cat > "${CONFIG_FILE}" <<EOF
---
data_root_path: ${DATA_DIR}
keystore:
  type: lair_server_in_proc
network:
  network_type: quic_bootstrap
  bootstrap_service: ${BOOTSTRAP_URL}
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

    # Launch conductor — pipe empty passphrase to stdin for lair keystore
    echo "" | "${HOLOCHAIN}" -p -c "${CONFIG_FILE}" \
        >> "${DATA_DIR}/conductor.log" 2>&1 &
    local HC_PID=$!
    echo "${HC_PID}" > "${PID_FILE}"
    echo "    PID=${HC_PID} | log: ${DATA_DIR}/conductor.log"

    # Wait for admin interface to be ready
    wait_for_port "${ADMIN_PORT}" "admin WS"

    # Generate agent key
    echo "📦  Installing hApp on Node ${N} …"
    local AGENT_KEY
    AGENT_KEY=$(get_agent_key "${ADMIN_PORT}")

    if [[ -z "${AGENT_KEY}" ]]; then
        echo "⚠️   No agent key returned — installing without explicit key"
        "${HC}" sandbox call --running "${ADMIN_PORT}" install-app \
            --app-id "${APP_ID}" \
            "${HAPP_BUNDLE}" 2>/dev/null || true
    else
        echo "    Agent key: ${AGENT_KEY:0:20}…"
        "${HC}" sandbox call --running "${ADMIN_PORT}" install-app \
            --app-id "${APP_ID}" \
            --agent-key "${AGENT_KEY}" \
            "${HAPP_BUNDLE}" 2>/dev/null || true
    fi

    # Enable the app (required before attaching app interfaces in 0.3.x)
    "${HC}" sandbox call --running "${ADMIN_PORT}" enable-app "${APP_ID}" 2>/dev/null || true

    # Attach App WebSocket interface
    "${HC}" sandbox call --running "${ADMIN_PORT}" add-app-ws "${APP_PORT}" \
        --allowed-origins "*" \
        --installed-app-id "${APP_ID}" 2>/dev/null || true

    echo "✅  Node ${N} ready — ws://localhost:${APP_PORT}"
    echo ""
}

# ── Launch nodes 1, 2, 3 ─────────────────────────────────────────────────────
for N in 1 2 3; do
    start_node "${N}"
done

echo "════════════════════════════════════════════════"
echo "  D-Cloud demo network is LIVE 🟢"
echo "════════════════════════════════════════════════"
echo ""
echo "  Node 1  ws://localhost:9001  (PID $(cat "${PID_FILES[1]}" 2>/dev/null || echo '?'))"
echo "  Node 2  ws://localhost:9101  (PID $(cat "${PID_FILES[2]}" 2>/dev/null || echo '?'))"
echo "  Node 3  ws://localhost:9201  (PID $(cat "${PID_FILES[3]}" 2>/dev/null || echo '?'))"
echo ""
echo "  Now restart the bridge to reconnect:"
echo "    (in WSL)  cd /mnt/c/Users/neswa/.gemini/antigravity/scratch/d-cloud/api-bridge"
echo "              .venv/bin/uvicorn main:app --port 3000 --reload"
echo ""
echo "  Quick test:"
echo "    curl http://localhost:3000/api/health"
echo "    curl -F 'file=@README.md' http://localhost:3000/api/upload"
echo "════════════════════════════════════════════════"
