import asyncio, msgpack, websockets

async def test():
    async with websockets.connect('ws://127.0.0.1:9000', open_timeout=10, origin='http://localhost') as ws:
        await ws.send(msgpack.packb({'id': 1, 'type': 'request', 'data': msgpack.packb({'type': 'generate_agent_pub_key'})}))
        resp = msgpack.unpackb(await ws.recv())
        agent_key = msgpack.unpackb(resp['data'])['data']
        with open('d-cloud.happ', 'rb') as f: bundle = f.read()
        
        # Test 1: Bundle format 
        payload = {'installed_app_id': 'd-cloud', 'agent_key': agent_key, 'source': {'type': 'bundle', 'data': bundle}}
        await ws.send(msgpack.packb({'id': 2, 'type': 'request', 'data': msgpack.packb({'type': 'install_app', 'data': payload})}))
        try:
            print('Test 1:', msgpack.unpackb(await ws.recv()))
        except Exception as e:
            print('Test 1 Failed:', e)

asyncio.run(test())
