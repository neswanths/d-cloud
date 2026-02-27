import asyncio
import websockets
import msgpack
import sys

async def run():
    try:
        async with websockets.connect('ws://127.0.0.1:8001', origin='http://localhost', open_timeout=5) as ws:
            print("Connected")
            # Create our payload
            inner = msgpack.packb({'type': 'app_info'}, use_bin_type=True)
            env = {'id': 1, 'type': 'request', 'data': inner}
            await ws.send(msgpack.packb(env, use_bin_type=True))
            print("Sent request, waiting for response...")
            try:
                res = await asyncio.wait_for(ws.recv(), timeout=5)
                print('Rx:', msgpack.unpackb(res, raw=False))
            except asyncio.TimeoutError:
                print('Timeout waiting for response')
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(run())
