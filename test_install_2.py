import asyncio, msgpack, websockets
import sys, os

async def test():
    async with websockets.connect('ws://127.0.0.1:9000', open_timeout=10, origin='http://localhost') as ws:
        await ws.send(msgpack.packb({'id': 1, 'type': 'request', 'data': msgpack.packb({'type': 'generate_agent_pub_key'})}))
        resp = msgpack.unpackb(await ws.recv())
        agent_key = msgpack.unpackb(resp['data'])['data']
        
        # Test 2: 'path' format without nesting
        payload = {
            'installed_app_id': 'd-cloud', 
            'agent_key': agent_key, 
            'source': {'type': 'path', 'path': os.path.abspath('d-cloud.happ')}
        }
        await ws.send(msgpack.packb({'id': 2, 'type': 'request', 'data': msgpack.packb({'type': 'install_app', 'data': payload})}))
        try:
            print('Test 2:', msgpack.unpackb(await ws.recv()))
        except Exception as e:
            print('Test 2 Failed:', e)

asyncio.run(test())
