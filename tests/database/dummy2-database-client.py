import websockets, json
import numpy as np
from seamless.mixed.io.serialization import serialize

url = "ws://localhost:5522"


config = {
    "protocol": ("seamless", "database", "0.0.1"),
}

async def main():
    async with websockets.connect(url) as websocket:
        await websocket.send(json.dumps(config))
        server_config = await websocket.recv()
        server_config = json.loads(server_config)
        server_handshake = await websocket.recv()
        if server_handshake != "Protocol OK":
            await websocket.send("Protocol mismatch")
            raise Exception("Server handshake error: %s" % server_handshake)
        if server_config["protocol"] != list(config["protocol"]):
            await websocket.send("Protocol mismatch")
            raise Exception("Protocol mismatch")
        await websocket.send("Protocol OK")
        checksum = "fa2fe6c9c0556871073be9a00d6d29bd3b9b6dd560587ee6e8c163755bf669d3"

        request = {
            "type": "get",
            "subtype": "buffer",
            "checksum": checksum,
        }
        await websocket.send(serialize(request))
        response = await websocket.recv()
        print(response)

import asyncio
asyncio.get_event_loop().run_until_complete(main())