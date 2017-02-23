import asyncio
import datetime
import random
import websockets

async def time(websocket, path):
    identifier = await websocket.recv()
    print("Connection from", identifier)
    while True:
        now = datetime.datetime.utcnow().isoformat() + 'Z'
        try:
            await websocket.send(identifier + " : " + now)
            await asyncio.sleep(random.random() * 3)
        except websockets.exceptions.ConnectionClosed:
            break

async def start_server(server_future):
    server = await websockets.serve(time, '127.0.0.1', 5678)
    server_future.set_result(server)

loop = asyncio.get_event_loop()
server_future = asyncio.Future()
asyncio.ensure_future(start_server(server_future))
loop.run_until_complete(server_future)
server = server_future.result()
