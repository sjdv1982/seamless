"""
Seamless communion server
Upon startup:
- Reads all comma-separated URLs in SEAMLESS_COMMUNION_INCOMING and tries to establish communion with them
- Reads the port in SEAMLESS_COMMUNION_OUTGOING and listens on that port for incoming communion attempts
- Every Seamless instance has a unique and random identifier; communion is only established once for each ID
"""

import os, sys, asyncio, time, functools, json, traceback, base64, websockets
from weakref import WeakSet
from .communionclient import communion_client_types

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
    "transformer_jobs": False,
}

# Default configuration for being a servant, i.e. on providing services to other peers
default_servant_config = {
    "label": True,
    "transformer_result": True,
    "value_cache": False,
    "transformer_jobs": False,
}

import numpy as np
def communion_encode(msg):
    assert msg["mode"] in ("request", "response")
    m = 'SEAMLESS'.encode()
    tip = b'\x00' if msg["mode"] == "request" else b'\x01'
    m += tip

    m += np.uint32(msg["id"]).tobytes()
    remainder = msg.copy()
    remainder.pop("mode")
    remainder.pop("id")
    remainder.pop("content")    
    if len(remainder.keys()):
        rem = json.dumps(remainder).encode()
        nrem = np.uint32(len(rem))
        m += nrem
        m += rem
    else:
        m += b'\x00\x00\x00\x00'
    content = msg["content"]
    if content is None:
        m += b'\x00'
    else:
        assert isinstance(content, (str, bytes)), content
        is_str = b'\x02' if isinstance(content, str) else b'\x01'
        m += is_str
        if isinstance(content, str):
            content = content.encode()
        m += content
    assert communion_decode(m) == msg, (communion_decode(m), msg)
    return m

def communion_decode(m):    
    assert isinstance(m, bytes)
    message = {}
    head = 'SEAMLESS'.encode()
    assert m[:len(head)] == head
    m = m[len(head):]
    tip = m[:1]
    m = m[1:]
    assert tip == b'\x01' or tip == b'\x00', tip
    message["mode"] = "request" if tip == b'\x00' else "response"
    l1, l2 = m[:4], m[4:8]
    m = m[8:]
    message["id"] = np.frombuffer(l1,np.uint32)[0]
    nrem = np.frombuffer(l2,np.uint32)[0] 
    if nrem:
        rem = m[:nrem]
        rem = rem.decode()
        rem = json.loads(rem)
        message.update(rem)
        m = m[nrem:]
    is_str = m[:1]
    if is_str == b'\x00':
        content = None
    else:
        assert is_str == b'\x02' or is_str == b'\x01'
        content = m[1:]    
        if is_str == b'\x02':
            content = content.decode()
    message["content"] = content
    return message
    
class CommunionServer:
    future = None
    PROTOCOL = ("seamless", "communion", "0.1")
    def __init__(self):        
        self.managers = WeakSet()
        self.config_master = default_master_config.copy()
        self.config_servant = default_servant_config.copy()
        cid = os.environ.get("SEAMLESS_COMMUNION_ID")
        if cid is None:
            cid = hash(int(id(self)) + int(10000*time.time()))
        self.id = cid
        self.peers = {}
        self.message_count = {}
        self.clients = {}
        self.futures = {}
    
    def register_manager(self, manager):
        if self.future is None:
            self.future = asyncio.ensure_future(self._start())
        self.managers.add(manager)

    def configure_master(self, config=None, **update):
        if self.future is not None and any(update.values()):
            print("Warning: CommunionServer has already started, added functionality will not be taken into account for existing peers", file=sys.stderr)
        if config is not None:
            self.config_master = config.copy()
        self.config_master.update(update)
        
    def configure_servant(self, config=None, **update):
        if self.future is not None:
            raise Exception("Cannot configure CommunionServer, it has already started")
        if config is not None:
            self.config_servant = config.copy()
        self.config_servant.update(update)

    def _add_clients(self, servant, peer_config):
        config = peer_config["servant"]
        for client_type in communion_client_types:
            config_type = client_type.config_type
            if not config.get(config_type):
                continue
            if not self.config_master.get(config_type):
                continue
            client = client_type(servant)
            print("ADD SERVANT", config_type)
            self.clients[servant].add(client)

            
    async def _listen_peer(self, websocket, peer_config):
        all_peer_ids = [peer["id"] for peer in self.peers.values()]
        if peer_config["id"] in all_peer_ids:
            return
        if peer_config["protocol"] != list(self.PROTOCOL):
            print("Protocol mismatch, peer '%s': %s, our protocol: %s" % (peer_config["id"], peer_config["protocol"], self.PROTOCOL))
            await websocket.send("Protocol mismatch: %s" % str(self.PROTOCOL))
            websocket.close()
            return
        else:
            await websocket.send("Protocol OK")
        protocol_message = await websocket.recv()
        if protocol_message != "Protocol OK":
            return
        #print("LISTEN")
        self.peers[websocket] = peer_config
        self.message_count[websocket] = 0
        self.futures[websocket] = {}
        self.clients[websocket] = set()
        self._add_clients(websocket, peer_config)
        try:
            async for message in websocket:
                try:
                    await self._process_message_from_peer(websocket, message)
                except:
                    traceback.print_exc()
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            #print("END CONNECTION", websocket)
            self.peers.pop(websocket)
            self.message_count.pop(websocket)
            self.futures.pop(websocket)
            clients = self.clients.pop(websocket)
            for client in clients:
                client.destroy()

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
            "protocol": self.PROTOCOL,
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
            print("Set up a communion outgoing port %d" % outgoing)            
        for url in incoming:
            if not url.startswith("ws://"):
                url = "ws://" + url
            coro = self._connect_incoming(config, url)
            coros.append(coro)

        await asyncio.gather(*coros)
    
    async def _process_request_from_peer(self, peer, message):        
        type = message["type"]
        message_id = message["id"]
        content = message["content"]
        result = None                
        if type == "label":
            cache_name = "label_cache"
            method_name = "get_checksum"
        elif type == "transformer_result":
            cache_name = "transform_cache"
            method_name = "get_result"
        else:
            raise NotImplementedError
        for manager in self.managers:
            cache = getattr(manager, cache_name)
            method = getattr(cache, method_name)
            result = method(content)
            if result is not None:
                break
        if result is None:
            peer_id = self.peers[peer]["id"]
            if type == "label":
                cache_task = cache_task_manager.remote_checksum_from_label(content, origin=peer_id)
            elif type == "transformer_result":
                checksum = bytes.fromhex(content)
                cache_task = cache_task_manager.remote_transform_result(checksum, origin=peer_id)
            else:
                raise NotImplementedError 
            await cache_task.future

            manager = next(iter(self.managers))
            cache = getattr(manager, cache_name)
            method = getattr(cache, method_name)
            result = method(content)        
        #print("REQUEST", message_id)
        response = {
            "mode": "response",
            "id": message_id,
            "content": result
        }
        msg = communion_encode(response)
        assert isinstance(msg, bytes)
        peer_id = self.peers[peer]["id"]
        print("Communion response: send %d bytes to peer '%s' (#%d)" % (len(msg), peer_id, response["id"]))
        await peer.send(msg)
        return result
        
    def _process_response_from_peer(self, peer, message):
        message_id = message["id"]
        content = message["content"]
        #print("RESPONSE", message_id)
        self.futures[peer][message_id].set_result(content)
        
    async def _process_message_from_peer(self, peer, msg):        
        message = communion_decode(msg)
        report = "Communion %s: receive %d bytes from peer '%s' (#%d)"
        peer_id = self.peers[peer]["id"]
        print(report  % (message["mode"], len(msg), peer_id, message["id"]))
        #print("message from peer", self.peers[peer]["id"], ": ", message)
        mode = message["mode"]
        assert mode in ("request", "response"), mode
        if mode == "request":
            return await self._process_request_from_peer(peer, message)
        else:
            return self._process_response_from_peer(peer, message)

    async def client_submit(self, message, peer):
        assert peer in self.peers, (peer, self.peers.keys())
        message_id = self.message_count[peer] + 1
        self.message_count[peer] = message_id
        future = asyncio.Future()
        self.futures[peer][message_id] = future
        message = message.copy()
        message.update({
            "mode": "request",
            "id": message_id,
        })
        msg = communion_encode(message)
        peer_id = self.peers[peer]["id"]
        print("Communion request: send %d bytes to peer '%s' (#%d)" % (len(msg), peer_id, message["id"]))
        await peer.send(msg)
        result = await future        
        self.futures[peer].pop(message_id)
        return result


communionserver = CommunionServer()

from .core.cache.cache_task import cache_task_manager