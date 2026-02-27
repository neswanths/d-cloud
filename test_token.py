import asyncio
import websockets
import msgpack

async def get_token():
    # connect to Admin interface
    async with websockets.connect("ws://localhost:8000", origin="http://localhost") as ws:
        # request token for d-cloud
        req = {
            "type": "issue_app_authentication_token",
            "data": {
                "installed_app_id": "d-cloud"
            }
        }
        
        envelope = {
            "id": 1,
            "type": "request",
            "data": msgpack.packb(req, use_bin_type=True)
        }
        
        await ws.send(msgpack.packb(envelope, use_bin_type=True))
        
        response = await ws.recv()
        resp_data = msgpack.unpackb(response, raw=False)
        print("Raw response:", resp_data)
        
        if "data" in resp_data:
            inner = msgpack.unpackb(resp_data["data"], raw=False)
            print("Inner response:", inner)

asyncio.run(get_token())
