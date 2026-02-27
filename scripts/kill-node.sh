#!/usr/bin/env bash
# ─── D-Cloud Node Killer — Demo Script ───────────────────────────────────────
#
# Simulates a node failure for the live demo.
# Usage:  bash scripts/kill-node.sh <1|2|3>
#
# Act 2: bash scripts/kill-node.sh 1   ← Node 1 goes red
# Act 4: bash scripts/kill-node.sh 2   ← Node 2 also dies
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

NODE=${1:-""}

if [[ -z "$NODE" || ! "$NODE" =~ ^[123]$ ]]; then
    echo "Usage: bash scripts/kill-node.sh <1|2|3>"
    exit 1
fi

PID_FILE="/tmp/d-cloud-demo/node${NODE}.pid"

if [[ ! -f "$PID_FILE" ]]; then
    echo "❌  PID file not found: $PID_FILE"
    echo "    Did you run setup-demo.sh first?"
    exit 1
fi

PID=$(cat "$PID_FILE")

if kill -0 "$PID" 2>/dev/null; then
    echo "💀  Killing Node $NODE (PID $PID) …"
    kill -SIGTERM "$PID"
    sleep 1
    # Force kill if it didn't stop
    kill -0 "$PID" 2>/dev/null && kill -SIGKILL "$PID" || true
    rm -f "$PID_FILE"
    echo "🔴  Node $NODE is DOWN"
    echo ""
    echo "  Remaining nodes can still serve the file."
    echo "  Try:  curl http://localhost:3000/api/file/<manifest_hash> -o retrieved.txt"
else
    echo "⚠️   Node $NODE (PID $PID) is already stopped."
    rm -f "$PID_FILE"
fi
