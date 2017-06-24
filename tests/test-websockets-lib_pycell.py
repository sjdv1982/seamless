from seamless.websocketserver import BaseWebSocketServer

class DemoWebSocketServer(BaseWebSocketServer):

    async def _serve(self, websocket, path):
        import datetime
        import random
        import asyncio

        identifier = await websocket.recv()
        print("Connection from", identifier)
        while True:
            now = datetime.datetime.utcnow().isoformat() + 'Z'
            try:
                await websocket.send(identifier + " : " + now)
                await asyncio.sleep(random.random() * 3)
            except websockets.exceptions.ConnectionClosed:
                break

server = DemoWebSocketServer()
server.start()
PINS.socket.set(server.socket)
