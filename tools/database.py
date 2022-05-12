from copy import deepcopy
from aiohttp import web
import aiofiles
import os, sys, asyncio, json, socket
from seamless import calculate_checksum
from seamless.util import parse_checksum
from seamless.core.buffer_info import BufferInfo
from collections import deque
import gc
import signal

MAX_BUFFER_CACHE_SIZE = 5*1e8  # 500 million bytes
buffer_cache = {}
buffer_cache_size = 0
buffer_cache_keys = deque()

def cache_buffer(checksum, buffer):
    global buffer_cache_size
    l = len(buffer)
    if l > MAX_BUFFER_CACHE_SIZE:
        return
    while l + buffer_cache_size > MAX_BUFFER_CACHE_SIZE:
        k = buffer_cache_keys.popleft()
        klen, _ = buffer_cache.pop(k)
        buffer_cache_size -= klen
    buffer_cache_keys.append(checksum)
    buffer_cache[checksum] = l, buffer
    buffer_cache_size += l

async def read_buffer(checksum, filename):
    hit = buffer_cache.get(checksum)
    if hit is not None:
        _, buffer = hit
        return buffer
    if filename is None or not os.path.exists(filename):
        return None
    async with aiofiles.open(filename, "rb") as f:
        buffer = await f.read()
        cs = calculate_checksum(buffer, hex=True)
        if cs != checksum: # database corruption!
            return None
    cache_buffer(checksum, buffer)
    return buffer

async def write_buffer(checksum, buffer, filename):
    async with aiofiles.open(filename, "wb") as f:
        await f.write(buffer)
    cache_buffer(checksum, buffer)


def err(*args, **kwargs):
    print("ERROR: " + args[0], *args[1:], **kwargs)
    exit(1)


class DatabaseError(Exception):
    pass

def is_port_in_use(address, port): # KLUDGE: For some reason, websockets does not test this??
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex((address, port)) == 0

types = (
    "protocol",
    "has_buffer",
    "has_key",
    "delete_key",
    "buffer",
    "buffer_info",
    "semantic_to_syntactic",
    "compilation",
    "transformation",
    "elision",
    "filename",
    "directory",
)
bucketnames = [
    "buffer_info", 
    "transformations",
    "compilations",
    "buffer_independence", 
    "semantic_to_syntactic",
    "elisions"
]
def format_response(response, *, none_as_404=False):
    status = None
    if response is None:
        if not none_as_404:
            status = 400
            response = "ERROR: No response"
        else:
            status = 404
            response = "ERROR: Unknown key"
    elif isinstance(response, (bool, dict, list)):
        response = json.dumps(response)
    elif not isinstance(response, (str, bytes)):
        status = 400
        print("ERROR: wrong response format")
        print(type(response), response)
        print("/ERROR: wrong response format")
        response = "ERROR: wrong response format"
    return status, response

class DatabaseStore:
    def __init__(self, config):
        self.path = config["path"]
        assert os.path.exists(self.path)
        self.readonly = config["readonly"]
        if not self.readonly:
            buffer_dir = os.path.join(self.path, "buffers")
            if not os.path.exists(buffer_dir):
                os.mkdir(buffer_dir)
        self.serve_filenames = config["serve_filenames"]
        self.filezone = str(config.get("filezone", "local"))
        self.external_path = config.get("external_path", self.path)        
        self.buckets = {}
        for bucketname in bucketnames:
            subdir = os.path.abspath(os.path.join(self.path, bucketname))
            bucket = TopBucket(subdir)
            self.buckets[bucketname] = bucket

    def _get_filename(self, checksum, as_external_path):
        if not self.serve_filenames:
            return None
        if checksum is None:
            return None
        dir = self.external_path if as_external_path else self.path
        return os.path.join(dir, "buffers", checksum)

    def _get_directory(self, checksum, as_external_path):
        if not self.serve_filenames:
            return None
        if checksum is None:
            return None
        dir = self.external_path if as_external_path else self.path
        return os.path.join(dir, "shared-directories", checksum)

    def _get_from_bucket(self, bucket, checksum):
        result = bucket.get(checksum)
        return result

class DatabaseServer:
    future = None
    PROTOCOL = ("seamless", "database", "0.1")
    def __init__(self, config):
        self.host = config.get("host", "0.0.0.0")
        self.port = int(config.get("port", 5522))        
        stores = []
        for store_config in config["stores"]:
            store = DatabaseStore(store_config)
            stores.append(store)
        self.stores = stores


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
            #print("NEW GET REQUEST", data)
            status = 200
            type = None
            try:
                try:
                    rq = json.loads(data)
                except Exception:
                    raise DatabaseError("Malformed request") from None
                #print("NEW GET REQUEST DATA", rq)
                try:
                    type = rq["type"]
                    if type not in types:
                        raise KeyError
                    if type != "protocol":
                        checksum = rq["checksum"]
                except KeyError:
                    raise DatabaseError("Malformed request") from None
                if type == "protocol":
                    response = list(self.PROTOCOL)
                else:
                    response = await self._get(type, checksum, rq)
            except DatabaseError as exc:
                status = 400
                if exc.args[0] == "Unknown key":
                    status = 404
                response = "ERROR: " + exc.args[0]
            none_as_404 = (type != "has_buffer")
            status2, response = format_response(response, none_as_404=none_as_404)
            if status == 200 and status2 is not None:
                status = status2
            ###if status != 200: print(response)
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
            #print("NEW PUT REQUEST", data)
            status = 200
            try:
                try:
                    if data[:len(b"SEAMLESS_BUFFER")] == b"SEAMLESS_BUFFER":
                        data = data[len(b"SEAMLESS_BUFFER"):]
                        rq = {"type": "buffer"}
                        rq["checksum"] = data[:64].decode()
                        rq["independent"] = bool(ord(data[64:65].decode()))
                        rq["value"] = data[65:]
                    else:
                        rq = json.loads(data)
                except Exception:
                    import traceback; traceback.print_exc()
                    #raise DatabaseError("Malformed request") from None
                if not isinstance(rq, dict):
                    #import traceback; traceback.print_exc()
                    raise DatabaseError("Malformed request")

                #print("NEW PUT REQUEST DATA", rq)
                try:
                    type = rq["type"]
                    if type not in types:
                        raise KeyError
                    checksum = rq["checksum"]
                    value = None
                    if type != "delete_key":
                        value = rq["value"]
                except KeyError:
                    #import traceback; traceback.print_exc()
                    raise DatabaseError("Malformed request") from None
                 
                try:
                    checksum = parse_checksum(checksum)
                except ValueError:
                    #import traceback; traceback.print_exc()
                    raise DatabaseError("Malformed request") from None

                response = await self._set(type, checksum, value, rq)
                if type == "buffer":
                    gc.collect()
            except DatabaseError as exc:
                status = 400
                response = "ERROR: " + exc.args[0]
            status2, response = format_response(response)
            if status == 200 and status2 is not None:
                status = status2
            #if status != 200: print(response)
            return web.Response(
                status=status,
                body=response
            )
        finally:
            #print("END PUT REQUEST", hex(id(request)))
            pass

    async def _get(self, type, checksum, request):
        if type == "has_buffer":
            found = False
            if checksum in buffer_cache:
                found = True
            else:
                for store in self.stores:
                    filename = store._get_filename(checksum, as_external_path=False)
                    if filename is not None and os.path.exists(filename):
                        found = True
            return found

        elif type == "filename":
            filezones = request.get("filezones", [])
            if not isinstance(filezones, list):
                raise DatabaseError("Malformed filename request")
            for store in self.stores:
                if not store.serve_filenames:
                    continue
                if len(filezones):
                    if store.filezone not in filezones:
                        continue
                filename = store._get_filename(checksum, as_external_path=False)
                if filename is not None and os.path.exists(filename):
                    filename2 = store._get_filename(checksum, as_external_path=True)
                    return filename2
            return None # None is also a valid response

        elif type == "directory":
            filezones = request.get("filezones", [])
            if not isinstance(filezones, list):
                raise DatabaseError("Malformed directory request")
            for store in self.stores:
                if not store.serve_filenames:
                    continue
                if len(filezones):
                    if store.filezone not in filezones:
                        continue
                directory = store._get_directory(checksum, as_external_path=False)
                if directory is not None and os.path.exists(directory):
                    return store._get_directory(checksum, as_external_path=True)
            return None # None is also a valid response

        elif type == "buffer":
            for store in self.stores:
                filename = store._get_filename(checksum, as_external_path=False)
                if filename is not None and os.path.exists(filename):
                    result = await read_buffer(checksum, filename)
                    if result is not None:
                        return result 
            return None # None is also a valid response

        elif type == "buffer_info":
            for store in self.stores:
                bucket = store.buckets["buffer_info"]
                result = store._get_from_bucket(bucket, checksum)
                if result is not None:
                    return result
            raise DatabaseError("Unknown key")

        elif type == "semantic_to_syntactic":
            try:
                celltype, subcelltype = request["celltype"], request["subcelltype"]
            except KeyError:
                raise DatabaseError("Malformed semantic-to-syntactic request")
            for store in self.stores:
                bucket = store.buckets["semantic_to_syntactic"]
                all_results = store._get_from_bucket(bucket, checksum)
                if all_results is not None:
                    results = all_results.get(celltype + "-" + subcelltype)
                    if len(results):
                        return list(results)
            raise DatabaseError("Unknown key")

        elif type == "compilation":
            for store in self.stores:
                bucket = store.buckets["compilations"]
                result = store._get_from_bucket(bucket, checksum)
                if result is not None:
                    parse_checksum(result) 
            return None # None is also a valid response

        elif type == "transformation":
            for store in self.stores:
                bucket = store.buckets["transformations"]
                result = store._get_from_bucket(bucket, checksum)
                if result is not None:
                    return parse_checksum(result) 
            return None # None is also a valid response

        elif type == "elision":
            for store in self.stores:
                bucket = store.buckets["elisions"]
                result = store._get_from_bucket(bucket, checksum)
                if result is not None:
                    json.dumps(result)
                    return result
            return None # None is also a valid response

        else:
            raise DatabaseError("Unknown request type")

    async def _set(self, type, checksum, value, request):
        if type == "buffer":
            if isinstance(value, str):
                value = value.encode()
            independent = bool(request.get("independent", False))
            for store in self.stores:
                if store.readonly:
                    continue
                bucket = store.buckets["buffer_independence"]
                bucket.set(checksum, independent)
                filename = store._get_filename(checksum, as_external_path=False)
                await write_buffer(checksum, value, filename)

        elif type == "delete_key":
            deleted = False
            for store in self.stores:
                if store.readonly:
                    continue
                try:
                    key_type = request["key_type"]
                    if key_type in ("transformation", "compilation"):
                        key_type += "s"
                    bucket = store.buckets[key_type]
                except KeyError:
                    raise DatabaseError("Malformed SET delete key request: invalid key_type")
                store_deleted = bucket.set(checksum, None)
                if store_deleted:
                    deleted = True
            return deleted


        elif type == "buffer_info":
            try:
                if not isinstance(value, dict):
                    raise TypeError
                BufferInfo(checksum, value)
            except Exception:
                raise DatabaseError("Malformed SET buffer info request") from None
            
            for store in self.stores:
                if store.readonly:
                    continue
                bucket = store.buckets["buffer_info"]
                bucket.set(checksum, value)

        elif type == "semantic_to_syntactic":
            if not isinstance(value, list):
                raise DatabaseError("Malformed SET semantic-to-syntactic request")
            try:
                celltype, subcelltype = request["celltype"], request["subcelltype"]
            except KeyError:
                raise DatabaseError("Malformed SET semantic-to-syntactic request")
            all_results = {}
            for store in self.stores:
                bucket = store.buckets["semantic_to_syntactic"]
                try:
                    all_results0 = store._get_from_bucket(bucket, checksum)
                    if all_results0 is not None:
                        all_results.update(all_results0)
                except DatabaseError:
                    pass
            key = celltype + "-" + subcelltype
            existing_results = all_results.get(key, [])
            new_results = existing_results + value
            new_results = list(set(new_results))
            all_results[key] = new_results
            for store in self.stores:
                if store.readonly:
                    continue
                bucket = store.buckets["semantic_to_syntactic"]
                bucket.set(checksum, all_results)
        
        elif type == "compilation":
            try:
                checksum = parse_checksum(checksum)
                value = parse_checksum(value)
            except ValueError:
                raise DatabaseError("Malformed SET compilation result request: value must be a checksum")
            for store in self.stores:
                if store.readonly:
                    continue
                bucket = store.buckets["compilations"]
                bucket.set(checksum, value)

        
        elif type == "transformation":
            try:
                checksum = parse_checksum(checksum)
                value = parse_checksum(value)
            except ValueError:
                raise DatabaseError("Malformed SET transformation result request: value must be a checksum")
            for store in self.stores:
                if store.readonly:
                    continue
                bucket = store.buckets["transformations"]
                bucket.set(checksum, value)

        elif type == "elision":
            try:
                checksum = parse_checksum(checksum)
            except ValueError:
                raise DatabaseError("Malformed SET elision result request: value must be a checksum")
            for store in self.stores:
                if store.readonly:
                    continue
                bucket = store.buckets["elisions"]
                bucket.set(checksum, value)

        else:
            raise DatabaseError("Unknown request type")
        return "OK"

if __name__ == "__main__":
    from database_bucket import TopBucket
    import ruamel.yaml
    yaml = ruamel.yaml.YAML(typ='safe')

    config = yaml.load(open(sys.argv[1]))
    # TODO: schema

    def raise_system_exit(*args, **kwargs): 
        raise SystemExit
    signal.signal(signal.SIGTERM, raise_system_exit)
    signal.signal(signal.SIGHUP, raise_system_exit)
    signal.signal(signal.SIGINT, raise_system_exit)

    database_server = DatabaseServer(config)
    database_server.start()

    """
    import logging
    logging.basicConfig()
    logging.getLogger("seamless").setLevel(logging.DEBUG)
    """
    
    try:
        print("Press Ctrl+C to end")
        asyncio.get_event_loop().run_forever()
    except KeyboardInterrupt:
        pass
else:
    from database_bucket import TopBucket
