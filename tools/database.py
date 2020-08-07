from aiohttp import web

import os, sys, asyncio, functools, json, traceback, socket
import database_backends
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
    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.db_sources = []
        self.db_sinks = []

    async def _start(self):
        if is_port_in_use(self.host, self.port): # KLUDGE
            print("ERROR: %s port %d already in use" % (self.host, self.port))
            raise Exception

        app = web.Application()
        app.add_routes([
            web.get('/{tail:.*}', self._handle_get),
            web.put('/{tail:.*}', self._handle_put),
        ])
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, self.host, self.port)
        await site.start()

    def start(self):
        if self.future is not None:
            return
        coro = self._start()
        self.future = asyncio.ensure_future(coro)

    async def _handle_get(self, request):
        data = await request.read()
        status = 200
        try:
            try:
                rq, _ = deserialize(data)
            except:
                raise DatabaseError("Malformed request") from None
            try:
                checksum = rq["checksum"]
                subtype = rq["subtype"]
                if subtype not in subtypes:
                    raise KeyError
            except KeyError:
                raise DatabaseError("Malformed request") from None
            response = await self.backend_get(subtype, checksum, rq)
        except DatabaseError as exc:
            status = 400
            response = "ERROR:" + exc.args[0]
        if response is None:
            status = 400
            response = "ERROR: No response"
        return web.Response(
            status=status,
            body=response
        )

    async def _handle_put(self, request):
        data = await request.read()
        status = 200
        try:
            try:
                rq, _ = deserialize(data)
            except:
                raise DatabaseError("Malformed request") from None
            try:
                checksum = rq["checksum"]
                subtype = rq["subtype"]
                if subtype not in subtypes:
                    raise KeyError
                value = rq["value"].tobytes()
            except KeyError:
                raise DatabaseError("Malformed request") from None
            response = await self.backend_set(subtype, checksum, value, rq)
        except DatabaseError as exc:
            status = 400
            response = "ERROR:" + exc.args[0]
        if response is None:
            status = 400
            response = "ERROR: No response"
        return web.Response(
            status=status,
            body=response
        )


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
            if not isinstance(value, bytes):
                raise DatabaseError("Malformed SET buffer request: value must be bytes")
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
                raise DatabaseError("Malformed SET semantic-to-syntactic request")
            try:
                celltype, subcelltype = request["celltype"], request["subcelltype"]
            except KeyError:
                raise DatabaseError("Malformed SET semantic-to-syntactic request")
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

if __name__ == "__main__":
    import ruamel.yaml
    yaml = ruamel.yaml.YAML(typ='safe')
    config = yaml.load(open(sys.argv[1]).read())

    database_server = DatabaseServer(config["host"], int(config["port"]))
    database_server.start()

    for backend in config["backends"]:
        try:
            backend_module = getattr(database_backends, backend["backend"])
        except AttributeError:
            raise ValueError(backend["backend"]) from None

        global_backend = config.get(backend["backend"], {})
        a = global_backend.copy()
        a.update(backend)
        del a["backend"]

        if backend["type"] == "source":
            source_config = a
            source = backend_module.get_source(source_config)
            database_server.db_sources.append((source, source_config))
        elif backend["type"] == "sink":
            sink_config = a
            sink = backend_module.get_sink(sink_config)
            database_server.db_sinks.append((sink, sink_config))
        else:
            raise ValueError(backend["type"])
    try:
        print("Press Ctrl+C to end")
        asyncio.get_event_loop().run_forever()
    except KeyboardInterrupt:
        pass
