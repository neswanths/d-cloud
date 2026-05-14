"""
auto-discover.py
────────────────
Scans your local subnet for D-Cloud node servers (port 8001) and prints
the NODE_URLS line you need to paste into api-bridge/.env

Run this on the BRIDGE machine AFTER start-node.ps1 is running on all machines.

Usage:
    python auto-discover.py

Optional: scan a different subnet or port:
    python auto-discover.py --subnet 10.0.0 --port 8001

Requirements: only Python stdlib (socket, concurrent.futures). No pip needed.
"""

from __future__ import annotations
import argparse
import json
import socket
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.error import URLError


def check_node(ip: str, port: int, timeout: float = 1.5) -> dict | None:
    url = f"http://{ip}:{port}/health"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            data = json.loads(resp.read())
            if data.get("status") == "online":
                return {"ip": ip, "port": port, "node_id": data.get("node_id", "?"),
                        "chunks": data.get("chunks_held", 0)}
    except (URLError, OSError, json.JSONDecodeError, ValueError):
        return None
    return None


def my_subnet() -> str:
    """Guess our LAN subnet (first 3 octets of primary interface IP)."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ".".join(ip.split(".")[:3])
    except OSError:
        return "192.168.1"


def main() -> None:
    parser = argparse.ArgumentParser(description="D-Cloud node auto-discoverer")
    parser.add_argument("--subnet", default=None, help="Subnet to scan e.g. 192.168.1 (default: auto-detect)")
    parser.add_argument("--port",   default=8001, type=int, help="Node port to scan (default: 8001)")
    parser.add_argument("--timeout", default=1.5, type=float, help="Per-host timeout in seconds (default: 1.5)")
    args = parser.parse_args()

    subnet = args.subnet or my_subnet()
    port   = args.port

    print(f"\n  D-Cloud Auto-Discover  —  scanning {subnet}.1-254 on port {port}")
    print("  This takes about 5-10 seconds...\n")

    candidates = [f"{subnet}.{i}" for i in range(1, 255)]
    found: list[dict] = []

    with ThreadPoolExecutor(max_workers=64) as pool:
        futures = {pool.submit(check_node, ip, port, args.timeout): ip for ip in candidates}
        for fut in as_completed(futures):
            result = fut.result()
            if result:
                found.append(result)
                print(f"  [FOUND]  {result['ip']}:{result['port']}  — {result['node_id']}  "
                      f"({result['chunks']} chunks)")

    if not found:
        print("  No D-Cloud nodes found on this subnet.")
        print("  Make sure start-node.ps1 is running on the other machines.")
        sys.exit(1)

    found.sort(key=lambda x: x["ip"])

    node_urls = ",".join(f"http://{n['ip']}:{n['port']}" for n in found)
    print(f"\n  Found {len(found)} node(s). Copy this into api-bridge/.env:\n")
    print(f"  NODE_URLS={node_urls}")

    # Offer to patch .env directly
    import os
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "api-bridge", ".env")
    if os.path.exists(env_path):
        ans = input("\n  Patch api-bridge/.env automatically? (y/N): ").strip().lower()
        if ans == "y":
            content = open(env_path).read()
            import re
            patched = re.sub(r"(?m)^NODE_URLS=.*$", f"NODE_URLS={node_urls}", content)
            open(env_path, "w").write(patched)
            print(f"  Done — .env updated with {len(found)} discovered node(s).\n")
    else:
        print(f"\n  (Could not find {env_path} — please patch manually)\n")


if __name__ == "__main__":
    main()
