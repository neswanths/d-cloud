import asyncio, msgpack, websockets
import sys, os

async def test():
    async with websockets.connect('ws://127.0.0.1:9000', open_timeout=10, origin='http://localhost') as ws:
        await ws.send(msgpack.packb({'id': 1, 'type': 'request', 'data': msgpack.packb({'type': 'generate_agent_pub_key'})}))
        resp = msgpack.unpackb(await ws.recv())
        agent_key = msgpack.unpackb(resp['data'])['data']
        
        # Test 7: Flattened Source (keys inline) + Default properties
        payload = {
            'agent_key': agent_key,
            'installed_app_id': 'd-cloud',
            'membrane_proofs': {},
            'network_seed': None,
            # AppBundleSource is #[serde(flatten)]
            # meaning its fields are moved to the root payload.
            # #[derive(Serialize, Deserialize)] on AppBundleSource:
            'path': os.path.abspath('d-cloud.happ')
        }
        await ws.send(msgpack.packb({'id': 7, 'type': 'request', 'data': msgpack.packb({'type': 'install_app', 'data': payload})}))
        try:
            print('Test 7:', msgpack.unpackb(await ws.recv()))
        except Exception as e:
            print('Test 7 Failed:', e)

asyncio.run(test())
