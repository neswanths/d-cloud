#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════
#  D-Cloud Node Server — Mac/Linux One-Click Starter
#  Run this on each machine.
#
#  Usage:  ./start_node.sh [node-id] [port]
#  Example: ./start_node.sh node2 8001
#
#  Default: node1 on port 8001
# ═══════════════════════════════════════════════════════

NODE_ID="${1:-node1}"
PORT="${2:-8001}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NODE_SERVER="${SCRIPT_DIR}/../node_server.py"

echo ""
echo "  ╔════════════════════════════════════════╗"
echo "  ║  D-Cloud Node Server — Mac/Linux       ║"
echo "  ║  Node: ${NODE_ID}   Port: ${PORT}                ║"
echo "  ╚════════════════════════════════════════╝"
echo ""

# Check Python
if ! command -v python3 &>/dev/null && ! command -v python &>/dev/null; then
    echo "  ERROR: Python 3.8+ required. Install from https://python.org"
    exit 1
fi

PY=$(command -v python3 || echo python)

if [[ ! -f "${NODE_SERVER}" ]]; then
    echo "  ERROR: node_server.py not found at ${NODE_SERVER}"
    exit 1
fi

echo "  Starting... This terminal must stay open."
echo "  Press Ctrl+C to stop."
echo ""

"${PY}" "${NODE_SERVER}" --port "${PORT}" --node-id "${NODE_ID}" --host 0.0.0.0
