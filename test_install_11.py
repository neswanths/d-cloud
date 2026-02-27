import asyncio, msgpack, websockets
import sys, os

async def test():
    try:
        async with websockets.connect('ws://127.0.0.1:9000', open_timeout=10, origin='http://localhost') as ws:
            await ws.send(msgpack.packb({'id': 1, 'type': 'request', 'data': msgpack.packb({'type': 'generate_agent_pub_key'})}))
            resp = msgpack.unpackb(await ws.recv())
            agent_key = msgpack.unpackb(resp['data'])['data']
            
            # Test 11: Mimic JS client `AppBundleSource` structure
            payload = {
                'source': {'type': 'path', 'path': os.path.abspath('d-cloud.happ')},
                'agent_key': agent_key,
                'installed_app_id': 'd-cloud',
            }
            await ws.send(msgpack.packb({'id': 2, 'type': 'request', 'data': msgpack.packb({'type': 'install_app', 'data': payload})}))
            try:
                res = msgpack.unpackb(await ws.recv())
                print('INSTALL API RESPONSE:', res)
                if 'data' in res:
                    inner = msgpack.unpackb(res['data'])
                    print('INNER DECODED:', inner)
            except Exception as e:
                print('Error during recv:', e)
    except Exception as exc:
        print('Outer exception:', exc)

asyncio.run(test())
