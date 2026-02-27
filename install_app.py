#!/usr/bin/env python3
import asyncio, sys, msgpack, websockets

async def call(ws, req_id, payload):
    inner = msgpack.packb(payload, use_bin_type=True)
    await ws.send(msgpack.packb({"id": req_id, "type": "request", "data": inner}, use_bin_type=True))
    raw = await ws.recv()
    outer = msgpack.unpackb(raw, raw=False)
    data = outer.get("data", b"")
    return msgpack.unpackb(data, raw=False) if isinstance(data, (bytes, bytearray)) and data else data

async def main():
    admin_port, app_port, app_id, happ_path = int(sys.argv[1]), int(sys.argv[2]), sys.argv[3], sys.argv[4]
    async with websockets.connect(f"ws://127.0.0.1:{admin_port}", open_timeout=10, ping_interval=None, origin="http://localhost") as ws:
        resp = await call(ws, 1, {"type": "generate_agent_pub_key"})
        if not isinstance(resp, dict) or resp.get("type") == "error":
            print(f"[!] generate_agent_pub_key failed: {resp}", file=sys.stderr); sys.exit(1)
        agent_key = resp["data"]
        payload_data = {
            "installed_app_id": app_id,
            "agent_key": agent_key,
            "network_seed": None,
            "membrane_proofs": {},
            "path": happ_path  # AppBundleSource is #[serde(flatten)]
        }
        resp = await call(ws, 2, {"type": "install_app", "data": payload_data})
        if isinstance(resp, dict) and resp.get("type") == "error":
            msg = resp.get("data", {}).get("message", str(resp))
            if "already" not in msg.lower():
                print(f"[!] install_app failed: {msg}", file=sys.stderr); sys.exit(1)
        print(f"[*] App installed")
        resp = await call(ws, 3, {"type": "enable_app", "data": {"installed_app_id": app_id}})
        if isinstance(resp, dict) and resp.get("type") == "error":
            print(f"[!] enable_app failed: {resp}", file=sys.stderr); sys.exit(1)
        print(f"[*] App enabled")
        resp = await call(ws, 4, {"type": "attach_app_interface", "data": {"port": app_port, "allowed_origins": "*", "installed_app_id": app_id}})
        if isinstance(resp, dict) and resp.get("type") == "error":
            msg = resp.get("data", {}).get("message", str(resp))
            if "already" not in msg.lower() and "in use" not in msg.lower():
                print(f"[!] attach_app_interface failed: {msg}", file=sys.stderr); sys.exit(1)
        print(f"[✓] Node ready — ws://localhost:{app_port}")

asyncio.run(main())
