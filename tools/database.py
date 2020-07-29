import os, sys, asyncio, functools, json, traceback, socket, websockets
from database_backends import redis_backend
from seamless.mixed.io.serialization import deserialize

buffercodes = (
    "buf", # authoritative buffer
    "nbf", # non-authoritative buffer (may be evicted; should be stored in Redis with an expiry)
    "bfl", # buffer length (for large buffers; 1 for small buffers)
    "s2s", # semantic-to-syntactic
    "cpl", # compile result (for compiled modules and objects)
    "tfr", # transformation result
)

subtypes = (
    "buffer",
    "buffer length",
    "semantic-to-syntactic",
    "compile result",
    "transformation result"
)

class DatabaseError(Exception):
    pass

def is_port_in_use(address, port): # KLUDGE: For some reason, websockets does not test this??
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex((address, port)) == 0


class DatabaseServer:
    future = None
    PROTOCOL = ("seamless", "database", "0.0.1")
    _started = False
    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.clients = set()
        self.db_sources = []
        self.db_sinks = []


    async def _listen_client(self, websocket, client_config):
        if client_config["protocol"] != list(self.PROTOCOL):
            print("Protocol mismatch, client '%s': %s, our protocol: %s" % (client_config["id"], client_config["protocol"], self.PROTOCOL))
            await websocket.send("Protocol mismatch: %s" % str(self.PROTOCOL))
            websocket.close()
            return
        else:
            await websocket.send("Protocol OK")
        protocol_message = await websocket.recv()
        if protocol_message != "Protocol OK":
            return
        self.clients.add(websocket)

        try:
            while 1:
                request = await websocket.recv()
                await self._process_request_from_client(websocket, request)
        except (websockets.exceptions.ConnectionClosed, ConnectionResetError):
            pass
        except Exception:
            traceback.print_exc()
        finally:
            self.clients.remove(websocket)


    async def _serve(self, config, websocket, path):
        client_config = await websocket.recv()
        client_config = json.loads(client_config)
        await websocket.send(json.dumps(config))
        await self._listen_client(websocket, client_config)

    async def _start(self):
        if self._started:
            return
        config = {
            "protocol": self.PROTOCOL,
        }

        if is_port_in_use(self.host, self.port): # KLUDGE
            print("ERROR: %s port %d already in use" % (self.host, self.port))
            raise Exception
        server = functools.partial(self._serve, config)
        coro_server = websockets.serve(server, self.host, self.port)
        print("Set up a database server on port %d" % self.port)
        await coro_server
        self._started = True

    def start(self):
        if self.future is not None:
            return
        coro = self._start()
        self.future = asyncio.ensure_future(coro)


    async def _process_request_from_client(self, client, request):
        try:
            response = None
            try:
                rq, _ = deserialize(request)
            except:
                raise DatabaseError("Malformed request") from None
            rqtype = rq["type"]
            if rqtype == "get":
                try:
                    checksum = rq["checksum"]
                    subtype = rq["subtype"]
                    if subtype not in subtypes:
                        raise KeyError
                except KeyError:
                    raise DatabaseError("Malformed request") from None
                response = await self.backend_get(subtype, checksum, rq)
            elif rqtype == "set":
                try:
                    checksum = rq["checksum"]
                    subtype = rq["subtype"]
                    if subtype not in subtypes:
                        raise KeyError
                    value = rq["value"].tobytes()
                except KeyError:
                    raise DatabaseError("Malformed request") from None
                response = await self.backend_set(subtype, checksum, value, rq)
            else:
                raise DatabaseError("Unknown request type %s" % rqtype)

        except DatabaseError as exc:
            response = "ERROR:" + exc.args[0]
        if response is None:
            response = "ERROR: No response"
        await client.send(response)

    async def backend_get(self, subtype, checksum, request):
        if subtype == "buffer":
            key1 = "buf:" + checksum
            key2 = "nbf:" + checksum
            result = None
            for source, source_config in self.db_sources:
                result = await source.get(key1)
                if result is not None:
                    source_id = source.id
                    authoritative = True
                    break
            if result is None:
                for source, source_config in self.db_sources:
                    result = await source.get(key2)
                    if result is not None:
                        source_id = source.id
                        authoritative = False
                        break
            if result is None:
                raise DatabaseError("Unknown key")

            for sink, sink_config in self.db_sinks:
                if sink.id == source_id:
                    continue
                if not sink_config.get("cache"):
                    continue
                has_key1 = await sink.has_key(key1)
                if has_key1:
                    continue
                has_key2 = await sink.has_key(key2)
                if has_key2:
                    continue
                if authoritative:
                    key = key1
                    importance = None
                else:
                    key = key2
                    importance = request.get("importance", 0)
                await sink.set(key, result, authoritative, importance)

            return result
        elif subtype == "buffer length":
            key = "bfl:" + checksum
            result = None
            for source, source_config in self.db_sources:
                result = await source.get(key)
                if result is not None:
                    source_id = source.id
                    break
                is_small_buffer = await source.is_small_buffer(checksum)
                if is_small_buffer:
                    result = 1
                    source_id = source.id
                    break
            if result is None:
                raise DatabaseError("Unknown key")
            for sink, sink_config in self.db_sinks:
                if sink.id == source_id:
                    continue
                if not sink_config.get("cache"):
                    continue
                if result == 1:
                    await sink.add_small_buffer(checksum)
                else:
                    await sink.set(key, result)
        elif subtype == "semantic-to-syntactic":
            try:
                celltype, subcelltype = request["celltype"], request["subcelltype"]
            except KeyError:
                raise DatabaseError("Malformed semantic-to-syntactic request")
            key = "s2s:{},{},{}".format(checksum, celltype, subcelltype)
            results = set()
            source_ids = set()
            for source, source_config in self.db_sources:
                result = await source.get_sem2syn(key)
                if result is not None:
                    for key in result:
                        if key not in results:
                            source_ids.add(source.id)
                        results.add(key)
            if not len(results):
                raise DatabaseError("Unknown key")
            source_id = list(source_ids)[0] if len(source_ids) == 1 else None
            for sink, sink_config in self.db_sinks:
                if sink.id == source_id:
                    continue
                if not sink_config.get("cache"):
                    continue
                for value in results:
                    await sink.add_sem2syn(key, value)
            return results
        elif subtype == "compile result":
            key = "cpl:" + checksum
            for source, source_config in self.db_sources:
                result = await source.get(key)
                if result is not None:
                    source_id = source.id
                    break
            if result is None:
                raise DatabaseError("Unknown key")
            for sink, sink_config in self.db_sinks:
                if sink.id == source_id:
                    continue
                if not sink_config.get("cache"):
                    continue
                await sink.set(key, result)
            return result
        elif subtype == "transformation result":
            key = "tfr:" + checksum
            for source, source_config in self.db_sources:
                result = await source.get(key)
                if result is not None:
                    source_id = source.id
                    break
            if result is None:
                raise DatabaseError("Unknown key")
            for sink, sink_config in self.db_sinks:
                if sink.id == source_id:
                    continue
                if not sink_config.get("cache"):
                    continue
                await sink.set(key, result)
            return result
        else:
            raise DatabaseError("Unknown request subtype")

    async def backend_set(self, subtype, checksum, value, request):
        if subtype == "buffer":
            key1 = "buf:" + checksum
            key2 = "nbf:" + checksum
            authoritative = request.get("authoritative", False)
            for sink, sink_config in self.db_sinks:
                has_key1 = await sink.has_key(key1)
                if has_key1:
                    continue
                has_key2 = await sink.has_key(key2)
                if has_key2:
                    if authoritative:
                        await sink.rename(key2, key1)
                    continue
                if authoritative:
                    key = key1
                    importance = None
                else:
                    key = key2
                    importance = request.get("importance", 0)
                await sink.set(key, value, authoritative, importance)
        elif subtype == "buffer length":
            length = int(value)
            key = "bfl:" + checksum
            for sink, sink_config in self.db_sinks:
                if length == 1: # small buffer
                    await sink.add_small_buffer(checksum)
                else:
                    await sink.set(key, length)
        elif subtype == "semantic-to-syntactic":
            if not isinstance(value, list):
                raise DatabaseError("Malformed semantic-to-syntactic request")
            try:
                celltype, subcelltype = request["celltype"], request["subcelltype"]
            except KeyError:
                raise DatabaseError("Malformed semantic-to-syntactic request")
            key = "s2s:{},{},{}".format(checksum, celltype, subcelltype)
            for sink, sink_config in self.db_sinks:
                await sink.add_sem2syn(key, value)
        elif subtype == "compile result":
            key = "cpl:" + checksum
            for sink, sink_config in self.db_sinks:
                await sink.set(key, value)
        elif subtype == "transformation result":
            key = "tfr:" + checksum
            for sink, sink_config in self.db_sinks:
                await sink.set(key, value)
        else:
            raise DatabaseError("Unknown request subtype")
        return "OK"

"""
subtypes = (
    "buffer",
    "buffer length",
    "semantic-to-syntactic",
    "compile result",
    "transformation result"
)

buffercodes = (
    "buf", # authoritative buffer
    "nbf", # non-authoritative buffer (may be evicted; should be stored in Redis with an expiry)
    "bfl", # buffer length (for large buffers; 1 for small buffers)
    "s2s", # semantic-to-syntactic
    "cpl", # compile result (for compiled modules and objects)
    "tfr", # transformation result
)

"""

if __name__ == "__main__":
    import ruamel.yaml
    yaml = ruamel.yaml.YAML(typ='safe')
    config = yaml.load(open(sys.argv[1]).read())

    database_server = DatabaseServer(config["host"], int(config["port"]))
    database_server.start()

    redis_config = config.get("redis", {})
    for backend in config["backends"]:
        a = {}
        if backend["backend"] == "redis":
            for key in ("host", "port"):
                a[key] = redis_config.get(key)
                a[key] = backend.get(key, a[key])
        if backend["type"] == "source":
            if backend["backend"] == "redis":
                source_config = backend.copy()
                source_config.update(a)
                source = redis_backend.get_source(source_config)
                database_server.db_sources.append((source, source_config))
            else:
                raise ValueError(backend["backend"])
        elif backend["type"] == "sink":
            if backend["backend"] == "redis":
                sink_config = backend.copy()
                sink_config.update(a)
                sink = redis_backend.get_sink(sink_config)
                database_server.db_sinks.append((sink, sink_config))
            else:
                raise ValueError(backend["backend"])
        else:
            raise ValueError(backend["type"])
    try:
        print("Press Ctrl+C to end")
        asyncio.get_event_loop().run_forever()
    except KeyboardInterrupt:
        pass
