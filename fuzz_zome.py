import asyncio
import msgpack
import websockets

ADMIN_URL = "ws://127.0.0.1:9000"
APP_URL = "ws://127.0.0.1:9001"

async def test_combos():
    # 2. Setup WS
    async def try_payload(payload):
        # Fetch token
        async with websockets.connect(ADMIN_URL, origin="http://localhost") as aws:
            admin_req = {
                "type": "issue_app_authentication_token",
                "data": {"installed_app_id": "d-cloud"}
            }
            envelope = {"id": 1, "type": "request", "data": msgpack.packb(admin_req, use_bin_type=True)}
            await aws.send(msgpack.packb(envelope, use_bin_type=True))
            resp = msgpack.unpackb(await aws.recv(), raw=False)
            inner = msgpack.unpackb(resp["data"], raw=False)
            token = inner["data"]["token"]

        async with websockets.connect(APP_URL, origin="http://localhost") as ws:
            auth_frame = {"type": "authenticate", "data": msgpack.packb({"token": token}, use_bin_type=True)}
            await ws.send(msgpack.packb(auth_frame, use_bin_type=True))
            await asyncio.sleep(0.5)
            
            # send app_info to get cell_id
            env = {"id": 2, "type": "request", "data": msgpack.packb({"type": "app_info"}, use_bin_type=True)}
            await ws.send(msgpack.packb(env, use_bin_type=True))
            resp = msgpack.unpackb(await ws.recv(), raw=False)
            app_info = msgpack.unpackb(resp["data"], raw=False)
            cell_id = tuple(app_info["data"]["cell_info"]["file_storage"][0]["provisioned"]["cell_id"])
            
            # Now try custom zome call payload
            data_dict = {}
            for k,v in payload["data"].items():
                if v == "%CELL_ID%": data_dict[k] = list(cell_id)
                elif v == "%PROVENANCE%": data_dict[k] = cell_id[1]
                else: data_dict[k] = v
                
            env = {"id": 3, "type": "request", "data": msgpack.packb({"type": payload["type"], "data": data_dict}, use_bin_type=True)}
            await ws.send(msgpack.packb(env, use_bin_type=True))
            try:
                out = await ws.recv()
                print(f"SUCCESS with {payload['type']}: {msgpack.unpackb(out, raw=False)}")
            except Exception as e:
                print(f"FAILED with {payload['type']}: {e} (payload: {payload})")

    dummy_payload = msgpack.packb({"ignored": True}, use_bin_type=True)
    
    combos = [
        # Option A: ZomeCallInvocation (0.3.x / 0.4)
        {
            "type": "zome_call_invocation", 
            "data": {"cell_id": "%CELL_ID%", "zome_name": "file_storage", "fn_name": "upload_chunk", "payload": dummy_payload, "cap_secret": None, "provenance": "%PROVENANCE%"}
        },
        # Option B: call_zome with cell_id
        {
            "type": "call_zome",
            "data": {"cell_id": "%CELL_ID%", "zome_name": "file_storage", "fn_name": "upload_chunk", "payload": dummy_payload, "cap_secret": None, "provenance": "%PROVENANCE%"}
        },
        # Option C: call_zome with role_name
        {
            "type": "call_zome",
            "data": {"role_name": "file_storage", "zome_name": "file_storage", "fn_name": "upload_chunk", "payload": dummy_payload, "cap_secret": None, "provenance": "%PROVENANCE%"}
        },
        # Option D: call_zome with role_name, no prov
        {
            "type": "call_zome",
            "data": {"role_name": "file_storage", "zome_name": "file_storage", "fn_name": "upload_chunk", "payload": dummy_payload}
        },
        # Option E: zome_call with cell_id
        {
            "type": "zome_call",
            "data": {"cell_id": "%CELL_ID%", "zome_name": "file_storage", "fn_name": "upload_chunk", "payload": dummy_payload, "cap_secret": None, "provenance": "%PROVENANCE%"}
        },
        # Option F: ZomeCallInvocation with role_name
        {
            "type": "zome_call_invocation",
            "data": {"role_name": "file_storage", "zome_name": "file_storage", "fn_name": "upload_chunk", "payload": dummy_payload, "cap_secret": None, "provenance": "%PROVENANCE%"}
        },
        # Option G: call_zome with cell_id but without cap_secret
        {
            "type": "call_zome",
            "data": {"cell_id": "%CELL_ID%", "zome_name": "file_storage", "fn_name": "upload_chunk", "payload": dummy_payload, "provenance": "%PROVENANCE%"}
        },
        # Option H: ZomeCallInvocation with capability
        {
            "type": "zome_call",
            "data": {"cell_id": "%CELL_ID%", "zome_name": "file_storage", "fn_name": "upload_chunk", "payload": dummy_payload, "provenance": "%PROVENANCE%"}
        },
        # Option I: call_zome with signature
        {
            "type": "call_zome",
            "data": {"cell_id": "%CELL_ID%", "zome_name": "file_storage", "fn_name": "upload_chunk", "payload": dummy_payload, "provenance": "%PROVENANCE%", "signature": b"0"*64}
        },
    ]
    
    for c in combos:
        await try_payload(c)

asyncio.run(test_combos())
