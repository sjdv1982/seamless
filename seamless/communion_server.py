"""
Seamless communion server
Upon startup:
- Reads all comma-separated URLs in SEAMLESS_COMMUNION_INCOMING and tries to establish communion with them
- Reads the port in SEAMLESS_COMMUNION_OUTGOING and listens on that port for incoming communion attempts
- Every Seamless instance has a unique and random identifier; communion is only established once for each ID
"""


"""
Servable things:
- Checksum to buffer (very generic; make it that incref is done for tf_checksum-to-transformation-JSON)
For this, there is a buffer status API, which can return:
    -1: checksum unknown
    0: buffer available remotely
    1: buffer available locally

- Checksum to bufferlength 
- Syntactic-to-semantic checksum
- transformation jobs
- build module jobs
Jobs are submitted by checksum. There is also a job status API, which can return
    a code and a return value. The return value depends on the code:
    -3: Job checksum is unknown (cache miss in the server's checksum to buffer)
        None is returned.
    -2: Job input checksums are unknown. None is returned.
    -1: Job is not runnable. None is returned.
    0: Job has exception. None is returned.
    1: Job is runnable. None is returned.
    2: Job is running; progress and preliminary checksum are returned as a single tuple
    3: Job is known; job checksum is returned.
Finally, the job API has an (async) wait method, that blocks until the job updates
(final result, preliminary result, or new progress)

Submitting a job is quick. After submission, the wait method is called.
Finally, the results are retrieved, resulting in a code 0, a code 3, or 
 occasionally a negative code (leading to re-evaluation).
The server may allow hard cancel of a job (by checksum)
Checksum-to-buffer requests can be forwarded to remote Seamless instances,
 but job requests are not.
Submitting a job clears any exception associated with that job.
Submitting a job may include a small dict of meta-data,
 containing e.g. information about required packages, memory requirements,
 estimated CPU time, etc.
 But Seamless servants ignore these meta-data.
A supervisor might accept job requests and forward them to registered
 Seamless servants, based on the meta-data.
Likewise, the job status API may return an exception checksum, but
 Seamless servants never do. A provenance server might store
 exceptions based on the job checksum and meta-data. These may be
 managed by a supervisor, which may decide its status responses based
 on it.
"""

import logging
logger = logging.getLogger('websockets.server')
logger.setLevel(logging.ERROR)
logger.addHandler(logging.StreamHandler())

def is_port_in_use(port): # KLUDGE: For some reason, websockets does not test this??
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('localhost', port)) == 0

WAIT_TIME = 1.5 # time to wait for network connections after a new manager

import os, sys, asyncio, time, functools, json, traceback, base64, websockets
from weakref import WeakSet
from .communion_client import communion_client_manager
from .core.build_module import build_compiled_module

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
    "buffer": True,
    "buffer_available": True,
    "buffer_length": True,
    "transformer_job": False,
    "transformer_status": False,
    "build_module_job": False,
    "build_module_status": False,
}

# Default configuration for being a servant, i.e. on providing services to other peers
default_servant_config = {
    "buffer": False,
    "buffer_available": False,
    "buffer_length": True,
    "transformer_job": False,
    "transformer_status": False,
    "build_module_job": False,
    "build_module_status": False,
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
        nrem = np.uint32(len(rem)).tobytes()
        m += nrem
        m += rem
    else:
        m += b'\x00\x00\x00\x00'
    content = msg["content"]
    if content is None:
        m += b'\x00'
    else:
        assert isinstance(content, (str, bytes, bool)), content
        if isinstance(content, bool):
            is_str = b'\x01'
        else:
            is_str = b'\x03' if isinstance(content, str) else b'\x02'
        m += is_str
        if isinstance(content, str):
            content = content.encode()
        elif isinstance(content, bool):
            content = b'\x01' if content else b'\x00'
        m += content
    #assert communion_decode(m) == msg, (communion_decode(m), msg)
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
    elif is_str == b'\x01':
        content = True if m[1:] == b'\x01' else False
    else:
        assert is_str == b'\x03' or is_str == b'\x02'
        content = m[1:]    
        if is_str == b'\x03':
            content = content.decode()
    message["content"] = content
    return message
    
class CommunionServer:
    future = None
    PROTOCOL = ("seamless", "communion", "0.2")
    def __init__(self):
        raise NotImplementedError # livegraph branch   
        self.config_master = default_master_config.copy()
        self.config_servant = default_servant_config.copy()
        cid = os.environ.get("SEAMLESS_COMMUNION_ID")
        if cid is None:
            cid = hash(int(id(self)) + int(10000*time.time()))
        self.id = cid
        self.peers = {}
        self.message_count = {}
        self.futures = {}
        self.ready = WeakSet()
            
    def configure_master(self, config=None, **update):
        if self.future is not None and any(update.values()):
            print("Warning: CommunionServer has already started, added functionality will not be taken into account for existing peers", file=sys.stderr)
        if config is not None:
            for key in config:
                assert key in default_master_config, key
            self.config_master = config.copy()
        self.config_master.update(update)
        
    def configure_servant(self, config=None, **update):
        if self.future is not None:
            raise Exception("Cannot configure CommunionServer, it has already started")
        if config is not None:
            for key in config:
                assert key in default_servant_config, key
            self.config_servant = config.copy()
        self.config_servant.update(update)

    def _add_clients(self, servant, peer_config):
        config = peer_config["servant"]
        for communion_type in sorted(config.keys()):
            if not self.config_master.get(communion_type):
                continue
            communion_client_manager.add_client(communion, servant)
            print("ADD SERVANT", config_type)

            
    async def _listen_peer(self, websocket, peer_config, incoming=False):
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
        self.message_count[websocket] = 1000 if incoming else 0
        self.futures[websocket] = {}
        self._add_clients(websocket, peer_config)
        try:
            while 1:
                message = await websocket.recv()
                asyncio.ensure_future(self._process_message_from_peer(websocket, message))
        except (websockets.exceptions.ConnectionClosed, ConnectionResetError):
            pass
        except Exception:
            traceback.print_exc()
        finally:
            self.peers.pop(websocket)
            self.message_count.pop(websocket)
            self.futures.pop(websocket)
            communion_client_manager.remove_servant(websocket)

    async def _connect_incoming(self, config, url):
        import websockets
        async with websockets.connect(url) as websocket:            
            await websocket.send(json.dumps(config))
            peer_config = await websocket.recv()
            peer_config = json.loads(peer_config)
            print("INCOMING", self.id, peer_config["id"])
            await self._listen_peer(websocket, peer_config, incoming=True)

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
            if is_port_in_use(outgoing): # KLUDGE
                print("ERROR: outgoing port %d already in use" % outgoing)
                raise Exception
            server = functools.partial(self._serve_outgoing, config)
            coro = websockets.serve(server, 'localhost', outgoing)
            coros.append(coro)
            print("Set up a communion outgoing port %d" % outgoing)            
        for url in incoming:
            if not url.startswith("ws://") and not url.startswith("wss://"):
                url = "ws://" + url
            coro = self._connect_incoming(config, url)
            coros.append(coro)

        await asyncio.gather(*coros)
    
    async def _process_request_from_peer(self, peer, message):
        type = message["type"]
        message_id = message["id"]
        content = message["content"]
        result = None
        try:
            # Local cache
            if type == "transformation_result":
                cache_name = "transform_cache"
                method_name = "get_result"
            elif type == "buffer_check":
                cache_name = "buffer_cache"
                method_name = "buffer_check"
            elif type == "value_get":
                cache_name = None
                method_name = "value_get"
            elif type == "transformation_job_check":
                ###level1 = TransformerLevel1.deserialize(content)
                ###result = True  # TODO: analyze transformer, configure acceptance criteria
                raise NotImplementedError
            elif type == "transformation_job_run":
                ###level1 = TransformerLevel1.deserialize(content)
                ###content = level1
                raise NotImplementedError
            elif type == "transformation_cancel":
                raise NotImplementedError
            elif type == "transformation_full_cancel":
                raise NotImplementedError
            elif type == "build_module":
                d_content = json.loads(content)
                full_module_name = d_content["full_module_name"]
                checksum = bytes.fromhex(d_content["checksum"])
                module_definition = d_content["module_definition"]                
            else:
                raise NotImplementedError(type)
            if result is None:
                for manager in self.managers:
                    if type == "transformer_job_run":
                        result = await manager.run_remote_transform_job(content)
                    elif type == "build_module":                      
                        build_compiled_module(full_module_name, checksum, module_definition)
                        break
                    else:
                        if cache_name is None:                            
                            method = getattr(manager, method_name)
                        else:
                            cache = getattr(manager, cache_name)
                            method = getattr(cache, method_name)
                        result = method(content)
                        if type.endswith("check"):
                            if result == True:
                                break
                        else:
                            if result is not None:
                                break
            # Remote cache
            if result is None:
                cache_task = None
                peer_id = self.peers[peer]["id"]
                if type == "transformation":
                    raise NotImplementedError # livegraph branch
                    checksum = bytes.fromhex(content)
                    cache_task = cache_task_manager.remote_transform_result(checksum, origin=peer_id)
                elif type == "buffer_check":
                    raise NotImplementedError # livegraph branch
                    pass #TODO: forward buffer_check requests
                    #checksum = bytes.fromhex(content)
                    #cache_task = cache_task_manager.remote_value(checksum, origin=peer_id)
                elif type == "buffer_get":
                    raise NotImplementedError # livegraph branch
                    pass #TODO: forward value_get requests
                    #checksum = bytes.fromhex(content)
                    #cache_task = cache_task_manager.remote_value(checksum, origin=peer_id)
                elif type == "transformer_job_check":
                    pass #TODO: forward transform_job_check requests
                elif type == "transformer_job_run":
                    pass #TODO: forward transform_job_run requests
                elif type == "build_module":
                    pass #TODO: forward build_module requests
                else:
                    raise ValueError(type)
                if cache_task is not None:
                    await cache_task.future
                    if cache_name is None:
                        method = getattr(manager, method_name)
                    else:
                        cache = getattr(manager, cache_name)
                        method = getattr(cache, method_name)
                    result = method(content)
        finally:
            #print("REQUEST", message_id)
            response = {
                "mode": "response",
                "id": message_id,
                "content": result
            }
            msg = communion_encode(response)
            assert isinstance(msg, bytes)
            peer_id = self.peers[peer]["id"]
            print("  Communion response: send %d bytes to peer '%s' (#%d)" % (len(msg), peer_id, response["id"]))
            await peer.send(msg)
        
    def _process_response_from_peer(self, peer, message):
        message_id = message["id"]
        content = message["content"]
        #print("RESPONSE", message_id)
        self.futures[peer][message_id].set_result(content)
        
    async def _process_message_from_peer(self, peer, msg):        
        message = communion_decode(msg)
        report = "  Communion %s: receive %d bytes from peer '%s' (#%d)"
        peer_id = self.peers[peer]["id"]
        print(report  % (message["mode"], len(msg), peer_id, message["id"]), message.get("type"))
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
        print("  Communion request: send %d bytes to peer '%s' (#%d)" % (len(msg), peer_id, message["id"]), message["type"])
        await peer.send(msg)
        result = await future        
        self.futures[peer].pop(message_id)
        return result


# TODO # livegraph branch
"""
communion_server = CommunionServer()

from .core.events.cache_task import cache_task_manager
"""