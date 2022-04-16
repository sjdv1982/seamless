from copy import deepcopy
from tkinter import E
from aiohttp import web
import aiofiles
import os, sys, asyncio, json, socket
from seamless.util import parse_checksum
from seamless.core.buffer_info import BufferInfo
from collections import deque
import gc
import signal
def raise_system_exit(*args, **kwargs): 
    raise SystemExit
signal.signal(signal.SIGTERM, raise_system_exit)
signal.signal(signal.SIGHUP, raise_system_exit)
signal.signal(signal.SIGINT, raise_system_exit)

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
    if not os.path.exists(filename):
        return None
    async with aiofiles.open(filename, "rb") as f:
        buffer = await f.read()
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
    
class DatabaseServer:
    future = None
    PROTOCOL = ("seamless", "database", "0.1")
    def __init__(self, host, port, *, database_dir, external_dir=None):
        """external_dir: name of the database dir for clients (outside the container)
This is for get_filename and get_directory requests"""
        self.host = host
        self.port = port
        self.database_dir = database_dir
        if external_dir is None:
            external_dir = database_dir
        self.external_dir = external_dir
        self.buckets = {}
        for bucketname in bucketnames:
            subdir = os.path.abspath(os.path.join(database_dir, bucketname))
            bucket = TopBucket(subdir)
            self.buckets[bucketname] = bucket

    def _get_filename(self, checksum):
        if checksum is None:
            return None
        return os.path.join(self.external_dir, "buffers", checksum)

    def _get_directory(self, checksum):
        if checksum is None:
            return None
        return os.path.join(self.external_dir, "shared-directories", checksum)

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


    def _get_from_bucket(self, bucket, checksum):
        result = bucket.get(checksum)
        if result is None:
            raise DatabaseError("Unknown key")
        return result

    async def _get(self, type, checksum, request):
        if type == "has_buffer":
            found = False
            if checksum in buffer_cache:
                found = True
            else:
                filename = self._get_filename(checksum)
                if os.path.exists(filename):
                    found = True
            return found

        elif type == "filename":
            filename = self._get_filename(checksum)
            if os.path.exists(filename):
                return filename
            return None # None is also a valid response

        elif type == "directory":
            directory = self._get_directory(checksum)
            if os.path.exists(directory):
                return directory
            return None # None is also a valid response

        elif type == "buffer":
            filename = self._get_filename(checksum)
            result = await read_buffer(checksum, filename)
            return result # None is also a valid response

        elif type == "buffer_info":
            bucket = self.buckets["buffer_info"]
            return self._get_from_bucket(bucket, checksum)

        elif type == "semantic_to_syntactic":
            try:
                celltype, subcelltype = request["celltype"], request["subcelltype"]
            except KeyError:
                raise DatabaseError("Malformed semantic-to-syntactic request")
            bucket = self.buckets["semantic_to_syntactic"]
            all_results = self._get_from_bucket(bucket, checksum)
            results = all_results.get(celltype + "-" + subcelltype)
            if not len(results):
                raise DatabaseError("Unknown key")
            return list(results)

        elif type == "compilation":
            bucket = self.buckets["compilations"]
            result = self._get_from_bucket(bucket, checksum)
            return parse_checksum(result) # None is also a valid response

        elif type == "transformation":
            bucket = self.buckets["transformations"]
            result = self._get_from_bucket(bucket, checksum)
            return parse_checksum(result) # None is also a valid response

        elif type == "elision":
            bucket = self.buckets["elisions"]
            result = self._get_from_bucket(bucket, checksum)
            json.dumps(result)
            return result # None is also a valid response

        else:
            raise DatabaseError("Unknown request type")

    async def _set(self, type, checksum, value, request):
        if type == "buffer":
            if isinstance(value, str):
                value = value.encode()
            independent = bool(request.get("independent", False))
            bucket = self.buckets["buffer_independence"]
            bucket.set(checksum, independent)
            filename = self._get_filename(checksum)
            await write_buffer(checksum, value, filename)

        elif type == "delete_key":
            try:
                key_type = request["key_type"]
                if key_type in ("transformation", "compilation"):
                    key_type += "s"
                bucket = self.buckets[key_type]
            except KeyError:
                raise DatabaseError("Malformed SET delete key request: invalid key_type")
            deleted = bucket.set(checksum, None)
            return deleted


        elif type == "buffer_info":
            try:
                if not isinstance(value, dict):
                    raise TypeError
                BufferInfo(checksum, value)
            except Exception:
                raise DatabaseError("Malformed SET buffer info request") from None
            
            bucket = self.buckets["buffer_info"]
            bucket.set(checksum, value)

        elif type == "semantic_to_syntactic":
            if not isinstance(value, list):
                raise DatabaseError("Malformed SET semantic-to-syntactic request")
            try:
                celltype, subcelltype = request["celltype"], request["subcelltype"]
            except KeyError:
                raise DatabaseError("Malformed SET semantic-to-syntactic request")
            bucket = self.buckets["semantic_to_syntactic"]
            try:
                all_results = self._get_from_bucket(bucket, checksum)
                all_results = deepcopy(all_results)
            except DatabaseError:
                all_results = {}
            key = celltype + "-" + subcelltype
            existing_results = all_results.get(key, [])
            all_results[key] = existing_results + value
            bucket.set(checksum, all_results)
            
        elif type == "compilation":
            try:
                checksum = parse_checksum(checksum)
                value = parse_checksum(value)
            except ValueError:
                raise DatabaseError("Malformed SET compilation result request: value must be a checksum")
            bucket = self.buckets["compilations"]
            bucket.set(checksum, value)

        
        elif type == "transformation":
            try:
                checksum = parse_checksum(checksum)
                value = parse_checksum(value)
            except ValueError:
                raise DatabaseError("Malformed SET transformation result request: value must be a checksum")
            bucket = self.buckets["transformations"]
            bucket.set(checksum, value)

        elif type == "elision":
            try:
                checksum = parse_checksum(checksum)
            except ValueError:
                raise DatabaseError("Malformed SET elision result request: value must be a checksum")
            bucket = self.buckets["elisions"]
            bucket.set(checksum, value)

        else:
            raise DatabaseError("Unknown request type")
        return "OK"

if __name__ == "__main__":
    from database_bucket import TopBucket
    env = os.environ
    SDB = env.get("SEAMLESS_DATABASE_DIR")
    if SDB is None:
        err("SEAMLESS_DATABASE_DIR undefined")
    if not os.path.exists(SDB):
        err("Directory '{}' does not exist".format(SDB))
    SDB_external_dir = env.get("SEAMLESS_DATABASE_EXTERNAL_DIR")

    db_host = env.get("SEAMLESS_DATABASE_HOST")
    if db_host is None:
        err("SEAMLESS_DATABASE_HOST undefined")
    db_port = env.get("SEAMLESS_DATABASE_PORT")
    if db_port is None:
        err("SEAMLESS_DATABASE_PORT undefined")
    else:
        db_port = int(db_port)

    buffer_dir = os.path.join(SDB, "buffers")
    if not os.path.exists(buffer_dir):
        os.mkdir(buffer_dir)

    database_server = DatabaseServer(
        db_host, db_port, 
        database_dir=SDB, external_dir=SDB_external_dir
    )
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
    from .database_bucket import TopBucket
