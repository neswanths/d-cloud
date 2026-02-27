import asyncio, msgpack, websockets
import sys, os

async def test():
    async with websockets.connect('ws://127.0.0.1:9000', open_timeout=10, origin='http://localhost') as ws:
        await ws.send(msgpack.packb({'id': 1, 'type': 'request', 'data': msgpack.packb({'type': 'generate_agent_pub_key'})}))
        resp = msgpack.unpackb(await ws.recv())
        agent_key = msgpack.unpackb(resp['data'])['data']
        
        # Test 6: Full explicit InstallAppPayload structure 
        # (source, agent_key, installed_app_id, network_seed, membrane_proofs)
        payload = {
            'source': {'type': 'path', 'path': os.path.abspath('d-cloud.happ')},
            'agent_key': agent_key,
            'installed_app_id': 'd-cloud',
            'network_seed': None,
            'membrane_proofs': {}
        }
        await ws.send(msgpack.packb({'id': 6, 'type': 'request', 'data': msgpack.packb({'type': 'install_app', 'data': payload})}))
        try:
            print('Test 6:', msgpack.unpackb(await ws.recv()))
        except Exception as e:
            print('Test 6 Failed:', e)

asyncio.run(test())
