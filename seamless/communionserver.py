"""
Seamless communion server
Upon startup:
- Reads all comma-separated URLs in SEAMLESS_COMMUNION_INCOMING and tries to establish communion with them
- Reads the port in SEAMLESS_COMMUNION_OUTGOING and listens on that port for incoming communion attempts
- Every Seamless instance has a unique and random identifier; communion is only established once for each ID
"""

import os, sys, asyncio, time, functools, json
from weakref import WeakSet

incoming = []
_incoming = os.environ.get("SEAMLESS_COMMUNION_INCOMING")
if _incoming:
    for url in _incoming.split(","):
        try:
            # TODO: validate URL
            incoming.append(url)
        except TypeError:
            print("SEAMLESS_COMMUNION_INCOMING: invalid URL '%s'" % url)

outgoing = None
_outgoing = os.environ.get("SEAMLESS_COMMUNION_OUTGOING")
if _outgoing:
        try:
           outgoing = int(_outgoing)
        except TypeError:
            print("SEAMLESS_COMMUNION_OUTGOING: invalid port '%s'" % outgoing)


# Default configuration for being a master, i.e. on using other peers as a service
default_master_config = {
    "label": True,
    "transformer_result": False,
    "value_cache": True,
    "transformer_jobs": True,
}

# Default configuration for being a servant, i.e. on providing services to other peers
default_servant_config = {
    "label": True,
    "transformer_result": True,
    "value_cache": False,
    "transformer_jobs": False,
}

class CommunionServer:
    future = None
    def __init__(self):        
        self.managers = WeakSet()
        self.config_master = default_master_config.copy()
        self.config_servant = default_servant_config.copy()
        cid = os.environ.get("SEAMLESS_COMMUNION_ID")
        if cid is None:
            cid = hash(int(id(self)) + int(10000*time.time()))
        self.id = cid
        self.peers = {}
    
    def register_manager(self, manager):
        if self.future is None:
            self.future = asyncio.ensure_future(self._start())
        self.managers.add(manager)

    def configure_master(self, config=None, **update):
        if self.future is not None:
            raise Exception("Cannot configure CommunionServer, it has already started")
        if config is not None:
            self.config_master = config.copy()
        self.config_master.update(update)
        
    def configure_servant(self, config=None, **update):
        if self.future is not None:
            raise Exception("Cannot configure CommunionServer, it has already started")
        if config is not None:
            self.config_servant = config.copy()
        self.config_servant.update(update)

    async def _listen_peer(self, websocket, peer_config):
        all_peer_ids = [peer["id"] for peer in self.peers.values()]
        if peer_config["id"] in all_peer_ids:
            return
        self.peers[websocket] = peer_config
        try:
            async for message in websocket:
                print("MSG!!!")
                self._process_message_from_peer(websocket, message)
        finally:
            self.peers.pop(websocket)

    async def _connect_incoming(self, config, url):
        import websockets
        async with websockets.connect(url) as websocket:            
            await websocket.send(json.dumps(config))
            peer_config = await websocket.recv()
            peer_config = json.loads(peer_config)
            print("INCOMING", self.id, peer_config["id"])
            await self._listen_peer(websocket, peer_config)

    async def _serve_outgoing(self, config, websocket, path):
        peer_config = await websocket.recv()
        peer_config = json.loads(peer_config)
        print("OUTGOING", self.id, peer_config["id"])
        await websocket.send(json.dumps(config))
        await self._listen_peer(websocket, peer_config)

    async def _start(self):
        config = {
            "protocol": ("seamless", "communion", "0.1"),
            "id": self.id,
            "master": self.config_master,
            "servant": self.config_servant
        }
        import websockets

        coros = []  
        if outgoing is not None:
            async def server(websocket, path):
                await self._serve_outgoing(config, websocket, path)
            server = functools.partial(self._serve_outgoing, config)
            coro = websockets.serve(server, 'localhost', outgoing)
            coros.append(coro)
            print("Set up a communion outgoing port %d, waiting 5 secs..." % outgoing)            
            await asyncio.sleep(5)
        for url in incoming:
            if not url.startswith("ws://"):
                url = "ws://" + url
            coro = self._connect_incoming(config, url)
            coros.append(coro)

        await asyncio.gather(*coros)
    
    def _process_message_from_peer(self, websocket, msg):
        print("message from peer", self.peers[websocket]["id"], ": ", msg)

    async def _send_message(self, msg):
        # TODO: filter destinations...
        print("SEND", msg, "Peers:", len(self.peers))
        coros = []
        for websocket, peer_config in self.peers.items():
            coros.append(websocket.send(msg))
        await asyncio.gather(*coros)

    def send_message(self, msg):
        asyncio.ensure_future(self._send_message(msg))

communionserver = CommunionServer()