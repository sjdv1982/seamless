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
    -2: checksum unknown
    -1: buffer too large
    0: buffer available remotely
    1: buffer available locally

- Checksum to bufferlength
- Semantic-to-syntactic checksum
- transformation jobs
- build module jobs
Jobs are submitted by checksum. There is also a job status API, which can return
    a code and a return value. The return value depends on the code:
    -3: Job checksum is unknown (cache miss in the server's checksum to buffer)
        None is returned.
    -2: Job input checksums are unknown. None is returned.
    -1: Job is not runnable. None is returned.
    0: Job has exception. Exception is returned as a string
    1: Job is runnable. None is returned.
    2: Job is running; progress and preliminary checksum are returned
    3: Job is known; job checksum is returned.
Finally, the job API has an (async) wait method, that blocks until the job updates
(final result, preliminary result, or new progress)

Submitting a job is quick. After submission, the wait method is called.
Finally, the results are retrieved, resulting in a code 0, a code 3, or
 occasionally a negative code (leading to re-evaluation).

The server may allow hard cancel/clear exception of a job (by checksum).
Normally, this is only done for servers behind a supervisor front-end, where
 the supervisor can do load-balancing and retries where needed.

Checksum-to-buffer requests can be forwarded to remote Seamless instances,
 (servant acting as a master) but job requests are not.

Jobs may include meta-data,
 containing e.g. information about required packages, memory requirements,
 estimated CPU time, etc.
However, this is beyond the scope of communion.
Meta-data for a job may be stored in a provenance server.
A supervisor might accept job requests and forward them to registered
 Seamless servants, based on the meta-data that it retrieves from this server.
Likewise, the job status API never return an exception value or checksum.
 A provenance server might store these exceptions based on the job checksum
 and meta-data. These may be managed by a supervisor, which may decide its

 """

import time

from seamless.core.cache import CacheMissError

MAX_STARTUP = 5

class CommunionError(Exception):
    pass


import logging
logger = logging.getLogger("seamless")

def print_info(*args):
    msg = " ".join([str(arg) for arg in args])
    logger.info(msg)

def print_warning(*args):
    msg = " ".join([str(arg) for arg in args])
    logger.warning(msg)

def print_debug(*args):
    msg = " ".join([str(arg) for arg in args])
    logger.debug(msg)

def print_error(*args):
    msg = " ".join([str(arg) for arg in args])
    logger.error(msg)

def is_port_in_use(address, port): # KLUDGE: For some reason, websockets does not test this??
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex((address, port)) == 0

WAIT_TIME = 1.5 # time to wait for network connections after a new manager

import os, sys, asyncio, time, functools, json, traceback, base64
from weakref import WeakSet
from .communion_client import communion_client_manager

incoming = []

communion_ip = os.environ.get("SEAMLESS_COMMUNION_IP")
if communion_ip:
    _communion_port = os.environ["SEAMLESS_COMMUNION_PORT"]
    try:
        communion_port = int(_communion_port)
    except TypeError:
        print_error("SEAMLESS_COMMUNION_PORT: invalid port '%s'" % _communion_port)
    url = '{}:{}'.format(communion_ip, communion_port)
    incoming.append(url)

_incoming = os.environ.get("SEAMLESS_COMMUNION_INCOMING")
if _incoming:
    for url in _incoming.split(","):
        try:
            # TODO: validate URL
            incoming.append(url)
        except TypeError:
            print_error("SEAMLESS_COMMUNION_INCOMING: invalid URL '%s'" % url)

outgoing_port = None
_outgoing_port = os.environ.get("SEAMLESS_COMMUNION_OUTGOING_PORT")
if _outgoing_port:
    try:
        outgoing_port = int(_outgoing_port)
    except TypeError:
        print_error("SEAMLESS_COMMUNION_OUTGOING_PORT: invalid port '%s'" % _outgoing_port)
    outgoing_ip = os.environ["SEAMLESS_COMMUNION_OUTGOING_IP"]

# Default configuration for being a master, i.e. on using other peers as a service
default_master_config = {
    "buffer": True,
    "buffer_status": True,
    "buffer_info": True,
    "transformation_job": True,
    "transformation_status": True,
    "semantic_to_syntactic": True,
}

# Default configuration for being a servant, i.e. on providing services to other peers
default_servant_config = {
    "buffer": "small", # only return small buffers (< 10 000 bytes)
    "buffer_status": "small",
    "buffer_info": True,
    "transformation_job": False,
    "transformation_status": False,
    "semantic_to_syntactic": True,
    "hard_cancel": False,  # allow others to hard cancel our jobs
    "clear_exception": False, # allow others to clear exceptions on our jobs
}

from .communion_encode import communion_encode, communion_decode
import numpy as np

class CommunionServer:
    future = None
    server = None
    startup = None
    peers = {}
    PROTOCOL = ("seamless", "communion", "0.3")
    _started = False
    _started_outgoing = False
    _to_start_incoming = None
    _restarted = False
    def __init__(self):
        self.config_master = default_master_config.copy()
        self.config_servant = default_servant_config.copy()
        self._init()
        self._restarted = False

    def _init(self):
        self._restarted = True
        cid = os.environ.get("SEAMLESS_COMMUNION_ID", "")
        if cid == "":
            cid = hash(int(id(self)) + int(10000*time.time()))
        self.id = cid
        self.peers = {}
        self.message_count = {}
        self.futures = {}
        self.ready = WeakSet()
        self._started = False
        self._started_outgoing = False
        self._to_start_incoming = None
        if self.future is not None:
            self.future.cancel()
            self.future = None
        if self.server is not None:
            self.server.cancel()
            self.server = None
        if self.startup is not None:
            self.startup.cancel()
            self.startup = None

    def configure_master(self, config=None, **update):
        if self._started_outgoing and any(list(update.values())):
            print_warning("CommunionServer has already started, added functionality will not be taken into account for existing peers")
        if config is not None:
            for key in config:
                assert key in default_master_config, key
            self.config_master = config.copy()
        for key in update:
            assert key in default_master_config, key
        self.config_master.update(update)

    def configure_servant(self, config=None, **update):
        if self.future is not None:
            raise Exception("Cannot configure CommunionServer, it has already started")
        if config is not None:
            for key in config:
                assert key in default_servant_config, key
            self.config_servant = config.copy()
        self.config_servant.update(update)

    async def _listen_peer(self, websocket, peer_config, incoming=False):
        import websockets
        all_peer_ids = [peer["id"] for peer in self.peers.values()]
        if peer_config["id"] in all_peer_ids:
            return
        if peer_config["protocol"] != list(self.PROTOCOL):
            print_warning("Protocol mismatch, peer '%s': %s, our protocol: %s" % (peer_config["id"], peer_config["protocol"], self.PROTOCOL))
            await websocket.send("Protocol mismatch: %s" % str(self.PROTOCOL))
            websocket.close()
            return
        else:
            await websocket.send("Protocol OK")
        protocol_message = await websocket.recv()
        if protocol_message != "Protocol OK":
            return
        print_debug("listen_peer", peer_config)
        self.peers[websocket] = peer_config
        self.message_count[websocket] = 1000 if incoming else 0
        self.futures[websocket] = {}
        communion_client_manager.add_servant(
            websocket,
            peer_config["id"],
            config_servant=peer_config["servant"],
            config_master=self.config_master
        )

        try:
            while 1:
                message = await websocket.recv()
                asyncio.ensure_future(self._process_message_from_peer(websocket, message))
        except (websockets.exceptions.ConnectionClosed, ConnectionResetError):
            pass
        except Exception:
            print_error(traceback.format_exc())
        finally:            
            if websocket not in self.peers:
                return  # communion server reset
            self.peers.pop(websocket)
            self.message_count.pop(websocket)
            self.futures.pop(websocket)
            communion_client_manager.remove_servant(websocket)

    async def _connect_incoming(self, config, url, url0):
        import websockets
        def start_incoming():
            try:
                self._to_start_incoming.remove(url0)
            except (ValueError, AttributeError):
                pass
        try:
            ok = False
            async with websockets.connect(url) as websocket:
                await websocket.send(json.dumps(config))
                peer_config = await websocket.recv()
                peer_config = json.loads(peer_config)
                if not self._restarted:
                    print_warning("INCOMING", self.id, peer_config["id"])
                start_incoming()
                ok = True
                await self._listen_peer(websocket, peer_config, incoming=True)
        finally:
            if not ok:
                start_incoming()

    async def _serve_outgoing(self, config, websocket, path):
        peer_config = await websocket.recv()
        peer_config = json.loads(peer_config)
        print_warning("OUTGOING", self.id, peer_config["id"])
        await websocket.send(json.dumps(config))
        await self._listen_peer(websocket, peer_config)

    async def _start(self):
        if self._started:
            return
        config = {
            "protocol": self.PROTOCOL,
            "id": self.id,
            "master": self.config_master,
            "servant": self.config_servant
        }
        import websockets

        coros = []
        if outgoing_port is not None:
            if is_port_in_use(outgoing_ip, outgoing_port): # KLUDGE
                print("ERROR: outgoing port %d already in use" % outgoing_port)
                raise Exception
            server = functools.partial(self._serve_outgoing, config)
            self.server = websockets.serve(server, outgoing_ip, outgoing_port)
            print("Set up a communion outgoing port {}, listening on {}".format(outgoing_port, outgoing_ip))
        if len(incoming):
            for n in range(len(incoming)):
                url = incoming[n]
                try:
                    int(url)
                    url = "localhost:" + url
                except ValueError:
                    pass
                incoming[n] = url                
            self._to_start_incoming = incoming.copy()
        else:
            self._to_start_incoming = []
        for url in incoming:
            url0 = url
            if not url.startswith("ws://") and not url.startswith("wss://"):
                url = "ws://" + url
            coro = self._connect_incoming(config, url, url0)
            coros.append(asyncio.ensure_future(coro))

        if outgoing_port is not None:
            await self.server
        self._started_outgoing = True
        self._started = True
        if len(coros):
            try:
                await asyncio.gather(*coros)
            finally:
                for coro in coros:
                    if coro.done():
                        try:
                            coro.result()
                        except Exception:
                            pass
                    else:
                        try:
                            coro.cancel()
                        except Exception:
                            pass

    async def _startup(self):
        print_debug("Communion server startup commencing")
        try:
            t = time.time()
            while 1:
                if communion_server._started_outgoing:
                    if communion_server._to_start_incoming is None or not len(communion_server._to_start_incoming):
                        break
                await asyncio.sleep(0.05)
                print_debug("Communion server startup waiting")
                if time.time() - t > MAX_STARTUP:
                    print_error("Communion server startup timed out")
                    break
        except:
            import traceback
            print_error("Communion server startup exception")
            print_error(traceback.format_exc())
        finally:
            print_info("Communion server startup complete")

    async def start_async(self):
        if self.future is not None:
            return
        coro = self._start()        
        self.startup = asyncio.ensure_future(self._startup())
        self.future = asyncio.ensure_future(coro)
        await self.startup
        while 1:
            if self._started and not len(self._to_start_incoming):
                break
            await asyncio.sleep(0.1)

    def start(self):
        import websockets
        from seamless import running_in_jupyter
        if running_in_jupyter:
            raise RuntimeError("'communion_server.start()' cannot be called from within Jupyter. Use 'await communion_server.start_async()' instead")
        elif asyncio.get_event_loop().is_running():
            raise RuntimeError("'communion_server.start()' cannot be called from within a coroutine. Use 'await communion_server.start_async()' instead")

        if self.future is not None:
            return
        coro = self._start()        
        self.startup = asyncio.ensure_future(self._startup())
        self.future = asyncio.ensure_future(coro)
        loop = asyncio.get_event_loop()
        loop.run_until_complete(self.startup)
        while 1:
            if self._started and not len(self._to_start_incoming):
                break
            loop.run_until_complete(asyncio.sleep(0.1))

    @property
    def started(self):
        return self._started

    async def _process_transformation_request(self, transformation, transformer, peer):
        try:
            tcache = transformation_cache
            remote_pins = []
            for pinname in transformation:
                if pinname.startswith("__"):
                    continue
                celltype, subcelltype, sem_checksum0 = transformation[pinname]
                sem_checksum = bytes.fromhex(sem_checksum0) if sem_checksum0 is not None else None
                checksum2 = await tcache.serve_semantic_to_syntactic(
                    sem_checksum, celltype, subcelltype,
                    peer
                )
                checksum2 = checksum2[0]
                assert isinstance(checksum2, bytes)
                buffer = get_buffer(checksum2, remote=True)
                if buffer is not None:
                    continue
                coro = get_buffer_remote(
                    checksum2,
                    peer
                )
                remote_pins.append((checksum2, coro))
            if len(remote_pins):
                buffers = await asyncio.gather(*[rp[1] for rp in remote_pins])
                for n in range(len(buffers)):
                    buffer = buffers[n]
                    if buffer is not None:
                        buffer_cache.cache_buffer(remote_pins[n][0], buffer)
            result = await tcache.incref_transformation(
                transformation, transformer,
                transformation_build_exception=None
            )
            if result is not None:
                tf_checksum, tf_exc, result_checksum, prelim = result
                if tf_exc is not None:
                    raise tf_exc
                if result_checksum is None or prelim:
                    job = tcache.run_job(transformation, tf_checksum)
                    if job is not None:
                        await asyncio.shield(job.future)

        except Exception as exc:
            tcache.transformation_exceptions[transformer.tf_checksum] = exc


    async def _process_request_from_peer(self, peer, message):
        type = message["type"]
        message_id = message["id"]
        content = message["content"]
        result = None
        error = False

        try:
            if type == "transformation_hard_cancel":
                assert self.config_servant["hard_cancel"]
                checksum = bytes.fromhex(content)
                transformation_cache.hard_cancel(tf_checksum=checksum)
                result = "OK"

            elif type == "transformation_clear_exception":
                assert self.config_servant["clear_exception"]
                checksum = bytes.fromhex(content)
                transformation_cache.clear_exception(tf_checksum=checksum)
                result = "OK"

            elif type == "buffer_status":
                assert self.config_servant[type]
                checksum = bytes.fromhex(content)
                async def func():
                    has_buffer = buffer_cache.buffer_check(checksum)
                    status = self.config_servant["buffer_status"]
                    try:
                        buffer_info = buffer_cache.get_buffer_info(
                            checksum, force_length=True, 
                            sync_remote=True, buffer_from_remote=True
                        )
                    except CacheMissError:
                        buffer_info = None
                    length = None
                    if buffer_info is not None:
                        length = buffer_info.length                        
                        print_debug("STATUS SERVE BUFFER", length, checksum.hex())
                        if length is None:
                            length = 0 
                        if length <= 10000 or status != "small":
                            if has_buffer:
                                return 1
                            else:
                                return 0
                        return -1                    
                    peer_id = self.peers[peer]["id"]
                    result = await communion_client_manager.remote_buffer_status(
                        checksum, peer_id
                    )
                    if result == True:
                        if length is None or length <= 10000 or status != "small":
                            return 0
                        else:
                            return -1
                    else:
                        return -2
                result = await func()
                print_info("BUFFER STATUS", checksum.hex(), result)

            elif type == "buffer":
                assert self.config_servant[type]
                checksum = bytes.fromhex(content)
                result = get_buffer(
                    checksum, remote=False
                )
                if result is None:
                    peer_id = self.peers[peer]["id"]
                    result = await get_buffer_remote(
                        checksum,
                        remote_peer_id=peer_id
                    )
                print_debug("BUFFER", checksum.hex(), result)

            elif type == "buffer_info":
                assert self.config_servant[type]
                checksum = bytes.fromhex(content)
                result = buffer_cache.get_buffer_info(checksum, force_length=False, buffer_from_remote=False, sync_remote=False)
                if result is None or not len(result.as_dict()):
                    peer_id = self.peers[peer]["id"]
                    result = await get_buffer_info_remote(
                        checksum,
                        remote_peer_id=peer_id
                    )
                print_info("BUFFERINFO", checksum.hex(), result)


            elif type == "semantic_to_syntactic":
                assert self.config_servant["semantic_to_syntactic"]
                checksum, celltype, subcelltype = content
                checksum = bytes.fromhex(checksum)
                peer_id = self.peers[peer]["id"]
                tcache = transformation_cache
                result = await tcache.serve_semantic_to_syntactic(
                    checksum, celltype, subcelltype,
                    peer_id
                )
                if isinstance(result, list):
                    result = tuple([r.hex() for r in result])

            elif type == "transformation_status":
                assert self.config_servant[type]
                checksum = bytes.fromhex(content)
                peer_id = self.peers[peer]["id"]
                tcache = transformation_cache
                result = await tcache.serve_transformation_status(
                    checksum, peer_id
                )
                if isinstance(result[-1], bytes):
                    result = (*result[:-1], result[-1].hex())

            elif type == "transformation_job":
                assert self.config_servant[type]
                checksum = bytes.fromhex(content)
                peer_id = self.peers[peer]["id"]
                transformer = RemoteTransformer(
                    checksum, peer_id
                )
                tcache = transformation_cache
                transformation = await tcache.serve_get_transformation(checksum, peer_id)
                coro = self._process_transformation_request(
                    transformation, transformer, peer
                )
                asyncio.ensure_future(coro)
                result = "OK"

            elif type == "transformation_wait":
                checksum = bytes.fromhex(content)
                peer_id = self.peers[peer]["id"]
                tcache = transformation_cache
                await tcache.remote_wait(checksum, peer_id)
                result = "OK"

            elif type == "transformation_cancel":
                assert self.config_servant["transformation_job"]
                checksum = bytes.fromhex(content)
                peer_id = self.peers[peer]["id"]
                tcache = transformation_cache
                key = checksum, peer_id
                transformation = await tcache.serve_get_transformation(checksum, peer_id)
                rem_transformer = tcache.remote_transformers.get(key)
                if key is not None:
                    tcache.decref_transformation(transformation, rem_transformer)
            elif type == "transformation_status_with_meta":
                raise NotImplementedError
            elif type == "transformation_job_with_meta":
                raise NotImplementedError
            else:
                raise Exception("Unknown communion message type '{}'".format(type))

        except NotImplementedError as exc:
            error = True
            result = repr(exc)
        except Exception as exc:
            print_error(traceback.format_exc())
            error = True
            result = repr(exc)
        finally:
            print_debug("REQUEST", message_id)
            response = {
                "mode": "response",
                "id": message_id,
                "content": result
            }
            if error:
                response["error"] = True
            msg = communion_encode(response)
            assert isinstance(msg, bytes)
            try:
                peer_id = self.peers[peer]["id"]
                print_info("  Communion response: send %d bytes to peer '%s' (#%d)" % (len(msg), peer_id, response["id"]))
                print_debug("  RESPONSE:", msg, "/RESPONSE")
            except KeyError:
                pass
            else:
                await peer.send(msg)

    def _process_response_from_peer(self, peer, message):
        message_id = message["id"]
        content = message["content"]
        print_debug("RESPONSE", message_id)
        if message_id not in self.futures[peer]:
            print("Unknown message", message_id)
            return
        future = self.futures[peer][message_id]
        if message.get("error"):
            future.set_exception(CommunionError(content))
        else:
            if not future.cancelled():
                future.set_result(content)

    async def _process_message_from_peer(self, peer, msg):
        message = communion_decode(msg)
        peer_id = self.peers[peer]["id"]
        report = "  Communion %s: receive %d bytes from peer '%s' (#%d)"
        print_info(report  % (message["mode"], len(msg), peer_id, message["id"]), message.get("type"))
        print_debug("message from peer", self.peers[peer]["id"], ": ", message)
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
        print_info("  Communion request: send %d bytes to peer '%s' (#%d)" % (len(msg), peer_id, message["id"]), message["type"])
        await peer.send(msg)
        result = await future
        self.futures[peer].pop(message_id)
        return result


communion_server = CommunionServer()
from .core.cache.transformation_cache import transformation_cache, RemoteTransformer
from .core.cache.buffer_cache import buffer_cache
from .core.protocol.get_buffer import get_buffer, get_buffer_remote, get_buffer_info_remote