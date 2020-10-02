from aiohttp import web
import numpy as np

import os, sys, asyncio, functools, json, traceback, socket
import database_backends
from seamless.mixed.io.serialization import deserialize
import gc

buffercodes = (
    "buf", # persistent buffer
    "nbf", # non-persistent buffer (may be evicted; should be stored in Redis with an expiry)
    "bfl", # buffer length
    "s2s", # semantic-to-syntactic
    "cpl", # compile result (for compiled modules and objects)
    "tfr", # transformation result
)

types = (
    "protocol",
    "has buffer",
    "has key",
    "delete key",
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
    PROTOCOL = ("seamless", "database", "0.0.2")
    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.db_sources = []
        self.db_sinks = []

    async def _start(self):
        if is_port_in_use(self.host, self.port): # KLUDGE
            print("ERROR: %s port %d already in use" % (self.host, self.port))
            raise Exception

        app = web.Application(client_max_size=10e9)
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
        try:
            #print("NEW GET REQUEST", hex(id(request)))
            data = await request.read()
            status = 200
            try:
                try:
                    rq, _ = deserialize(data)
                except:
                    raise DatabaseError("Malformed request") from None
                try:
                    type = rq["type"]
                    if type not in types:
                        raise KeyError
                    if type not in ("protocol", "has key"):
                        checksum = rq["checksum"]
                        key = None
                    elif type == "has key":
                        key = rq["key"]
                        checksum = None
                except KeyError:
                    raise DatabaseError("Malformed request") from None
                if type == "protocol":
                    response = json.dumps(self.PROTOCOL)
                else:
                    response = await self.backend_get(type, checksum, key, rq)
            except DatabaseError as exc:
                status = 400
                if exc.args[0] == "Unknown key":
                    status = 404
                response = "ERROR:" + exc.args[0]
            if response is None:
                status = 400
                response = "ERROR: No response"
            return web.Response(
                status=status,
                body=response
            )
        finally:
            #print("END GET REQUEST", hex(id(request)))
            pass

    async def _handle_put(self, request):
        try:
            #print("NEW PUT REQUEST", hex(id(request)))
            data = await request.read()
            status = 200
            try:
                try:
                    rq, _ = deserialize(data)
                except:
                    raise DatabaseError("Malformed request") from None
                try:
                    type = rq["type"]
                    if type not in types:
                        raise KeyError
                    if type == "delete key":
                        key = rq["key"]
                        checksum = None
                        value = None
                    else:
                        checksum = rq["checksum"]
                        value = rq["value"]
                        key = None
                except KeyError:
                    raise DatabaseError("Malformed request") from None
                response = await self.backend_set(type, checksum, key, value, rq)
                if type == "buffer":
                    gc.collect()
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
        finally:
            #print("END PUT REQUEST", hex(id(request)))
            pass


    async def backend_get(self, type, checksum, key, request):
        if type == "has buffer":
            key1 = "buf-" + checksum
            key2 = "nbf-" + checksum
            for source, source_config in self.db_sources:
                has_key1 = await source.has_key(key1)
                if has_key1:
                    return "1"
                has_key2 = await source.has_key(key2)
                if has_key2:
                    return "1"
            return "0"
        elif type == "has key":
            key = key.encode()
            for source, source_config in self.db_sources:
                has_key = await source.has_key(key)
                if has_key:
                    return "1"
            return "0"
        elif type == "buffer":
            key1 = "buf-" + checksum
            key2 = "nbf-" + checksum
            result = None
            for source, source_config in self.db_sources:
                result = await source.get(key1)
                if result is not None:
                    source_id = source.id
                    persistent = True
                    break
            if result is None:
                for source, source_config in self.db_sources:
                    result = await source.get(key2)
                    if result is not None:
                        source_id = source.id
                        persistent = False
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
                if persistent:
                    key = key1
                    importance = None
                else:
                    key = key2
                    importance = request.get("importance", 0)
                await sink.set(key, result, persistent, importance)

            return result
        elif type == "buffer length":
            key = "bfl-" + checksum
            result = None
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
            result = int(result)
        elif type == "semantic-to-syntactic":
            try:
                celltype, subcelltype = request["celltype"], request["subcelltype"]
            except KeyError:
                raise DatabaseError("Malformed semantic-to-syntactic request")
            key = "s2s-{},{},{}".format(checksum, celltype, subcelltype)
            results = set()
            source_ids = set()
            for source, source_config in self.db_sources:
                result = await source.get_sem2syn(key)
                if result is not None:
                    for r in result:
                        assert isinstance(r, bytes)
                        if r not in results:
                            source_ids.add(source.id)
                        results.add(r)
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
            results = [r.decode() for r in results]
            return json.dumps(list(results))
        elif type == "compile result":
            key = "cpl-" + checksum
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
            return result.decode()
        elif type == "transformation result":
            key = "tfr-" + checksum
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
            return result.decode()
        else:
            raise DatabaseError("Unknown request type")

    async def backend_set(self, type, checksum, key, value, request):
        if type == "buffer":
            if not isinstance(value, np.ndarray):
                raise DatabaseError("Malformed SET buffer request: value must be numpy bytes")
            value = value.tobytes()
            key1 = "buf-" + checksum
            key2 = "nbf-" + checksum
            persistent = request.get("persistent", False)
            for sink, sink_config in self.db_sinks:
                has_key1 = await sink.has_key(key1)
                if has_key1:
                    continue
                has_key2 = await sink.has_key(key2)
                if has_key2:
                    if persistent:
                        await sink.rename(key2, key1)
                    continue
                if persistent:
                    key = key1
                    importance = None
                else:
                    key = key2
                    importance = request.get("importance", 0)
                await sink.set(key, value, persistent, importance)
        elif type == "delete key":
            key = key.encode()
            done = set()
            for source, source_config in self.db_sources:
                if source.id in done:
                    continue
                done.add(source.id)
                has_key = await source.has_key(key)
                if has_key:
                    await source.delete_key(key)
            for sink, sink_config in self.db_sinks:
                if sink.id in done:
                    continue
                done.add(source.id)
                has_key = await sink.has_key(key)
                if has_key:
                    await sink.delete_key(key)
        elif type == "buffer length":
            if not isinstance(value, int):
                raise DatabaseError("Malformed SET buffer length request")
            length = bytes(value)
            key = "bfl-" + checksum
            for sink, sink_config in self.db_sinks:
                await sink.set(key, length)
        elif type == "semantic-to-syntactic":
            if not isinstance(value, list):
                raise DatabaseError("Malformed SET semantic-to-syntactic request")
            try:
                celltype, subcelltype = request["celltype"], request["subcelltype"]
            except KeyError:
                raise DatabaseError("Malformed SET semantic-to-syntactic request")
            key = "s2s-{},{},{}".format(checksum, celltype, subcelltype)
            for sink, sink_config in self.db_sinks:
                await sink.add_sem2syn(key, [v.encode() for v in value])
        elif type == "compile result":
            if not isinstance(value, np.ndarray):
                raise DatabaseError("Malformed SET compile result request: value must be numpy bytes")
            value = value.tobytes()
            key = "cpl-" + checksum
            for sink, sink_config in self.db_sinks:
                await sink.set(key, value)
        elif type == "transformation result":
            key = "tfr-" + checksum
            for sink, sink_config in self.db_sinks:
                await sink.set(key, value.encode())
        else:
            raise DatabaseError("Unknown request type")
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
