#!/usr/bin/env bash
set -euo pipefail
HC_STORE_DIR="/nix/store/2bpx02w4h86h1mx369wm9xswmrk71l1m-holochain-0.3.6/bin"
HOLOCHAIN="${HC_STORE_DIR}/holochain"
HC="${HC_STORE_DIR}/hc"
APP_ID="d-cloud"
HAPP_BUNDLE="/mnt/c/Users/neswa/.gemini/antigravity/scratch/d-cloud/d-cloud.happ"

rm -rf "/tmp/d-cloud-demo-trace"
mkdir -p "/tmp/d-cloud-demo-trace"

cat > "/tmp/d-cloud-demo-trace/config.yaml" <<EOF
---
data_root_path: /tmp/d-cloud-demo-trace
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
      port: 8000
      allowed_origins: "*"
EOF

echo "Starting holochain with RUST_LOG=trace..."
export RUST_LOG=debug,holochain=trace,hc_websocket=trace,lair_keystore=error,wasmer=error
echo "" | "${HOLOCHAIN}" -p -c "/tmp/d-cloud-demo-trace/config.yaml" > /tmp/hc_trace.log 2>&1 &
HC_PID=$!

sleep 5

echo "Installing app..."
"${HC}" sandbox call --running 8000 install-app --app-id "${APP_ID}" "${HAPP_BUNDLE}" >/dev/null 2>&1 || true
"${HC}" sandbox call --running 8000 enable-app "${APP_ID}" >/dev/null 2>&1 || true
"${HC}" sandbox call --running 8000 add-app-ws 8001 --allowed-origins "*" >/dev/null 2>&1 || true

echo "Running python test..."
cd /mnt/c/Users/neswa/.gemini/antigravity/scratch/d-cloud/api-bridge
.venv/bin/python3 /mnt/c/Users/neswa/.gemini/antigravity/scratch/d-cloud/test_token.py

echo "Killing holochain..."
kill "${HC_PID}"
wait "${HC_PID}" || true

echo "Extracting relevant trace logs for app port:"
grep -i -C 5 "9001" /tmp/hc_trace.log | tail -n 30
echo "Extracting relevant trace logs for msgpack or app_info error:"
grep -i -E "error|msgpack|app_info|websocket|reject" /tmp/hc_trace.log | grep -v "webrtc" | tail -n 20
