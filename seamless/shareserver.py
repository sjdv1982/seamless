"""
Seamless shareserver REST protocol

Short version:
ctx.a.share() =>
- http://localhost:5813/ctx/a gives the value of the cell (HTTP GET)
- At the same address, the value of the cell can be changed with a HTTP PUT request
- An update to ctx.a sends a notification to ws://localhost:5138/ctx
- http://localhost:5813/ctx/compute with an HTTP PATCH request does 'await ctx.computation()' .
  A timeout can be specified.

Long version:
There is a singleton ShareServer instance at localhost

It opens an update websocket server, and a REST server.

Shares are of the form http://<address>:<port>/<namespace>/<path>
By default, namespace is "ctx", address is localhost, port is 5813

All GET requests have a mode URL parameter (default: "buffer"), which can have
one of the following values.
1. mode=marker:
returns a JSON with 3 modes:
- marker
- checksum, as hex
- the content type,
2. mode=buffer:
Just returns the buffer
3. mode=checksum:
Just returns the checksum
4. mode=value
Same as buffer, but with mimetype

PUT messages are in JSON. They must contain a mode "buffer"
(although the final newline is optional) OR a mode "checksum"
They may contain a marker. If there is one, the PUT is only
 accepted if the current marker is equal (or lower).
If there is no marker, a new marker will be created, which is
 the existing marker plus one. 
If the PUT was successful, the marker is returned, else None.

A share may be read-only, in which case it never accepts PUT requests.

Updates are on ws://<address>:<port>/<namespace>
By default, port is 5138.
The server only sends, never receives. 
Upon connection, a client receives a handshake message: ["Seamless share update server", "0.01"]
Then, it receives a list of share keys (normally, each share key is bound to a cell).
Then, it receives all checksums and markers. 

"""
import os
import asyncio
import weakref
import traceback
import json

from asyncio import CancelledError
from websockets.exceptions import ConnectionClosed

DEBUG = False

def is_bound_port_error(exc):
    args = exc.args
    if not len(args) == 2:
        return False
    if args[0] != 98:
        return False
    msg = args[1]
    if not isinstance(msg, str):
        return False
    return msg.endswith("address already in use")

def tailsplit(tail):
    pos = tail.index("/")
    return tail[:pos], tail[pos+1:]

class Share:
    _destroyed = False
    def __init__(self, namespace, key, readonly, celltype, mimetype):
        assert isinstance(namespace, ShareNamespace)
        self.namespace = weakref.ref(namespace)
        self.key = key
        self.readonly = readonly
        self.celltype = celltype
        self.mimetype = mimetype
        self._checksum = None
        self._marker = 0
        self._calc_checksum_task = None
        self._send_checksum_task = None       
        self.requests = []
        self.bound = None # bound ShareItem

    def bind(self, share_item):
        assert self.bound is None
        self.bound = share_item
    
    def unbind(self):
        self.bound = None

    async def read(self, marker=None):
        if marker is not None and marker <= self._marker:
            return
        while 1:
            if self._calc_checksum_task is None:
                break
            await self._calc_checksum_task
        return self._checksum, self._marker
    
    def set_checksum(self, checksum, marker=None):
        if marker is not None and marker <= self._marker:
            return None
        if checksum == self._checksum:
            return
        if marker is None:
            marker = self._marker + 1
        self._cancel()        
        if self._checksum is not None:
            buffer_cache.decref(self._checksum)
        self._checksum = checksum
        if self.bound is not None:
            self.bound.update(checksum)
        if self._checksum is not None:
            buffer_cache.incref(self._checksum)
        self._marker = marker
        send_checksum_task = self._send_checksum()
        send_checksum_task = asyncio.ensure_future(send_checksum_task)
        self._send_checksum_task = send_checksum_task
        
        return marker

    async def set_buffer(self, buffer, marker=None):
        from .core.protocol.calculate_checksum import calculate_checksum
        if marker is not None and marker <= self._marker:
            return None
        if marker is None:
            marker = self._marker + 1
        self._cancel()
        if buffer is None:
            self._checksum = None
            self._marker = marker
            return marker
        
        if isinstance(buffer, str):
            buffer = buffer.encode()
        if not isinstance(buffer, bytes):
            raise TypeError(type(buffer))
        buffer = buffer.rstrip(b'\n') + b'\n'
        task = self._calc_checksum(buffer)
        task = asyncio.ensure_future(task)
        self._calc_checksum_task = task
        await task

        checksum = task.result()
        buffer_cache.cache_buffer(checksum, buffer)
        return self.set_checksum(checksum, marker)

    async def _calc_checksum(self, buffer):
        init = self._calc_checksum_task
        try:
            return await calculate_checksum(buffer)
        finally:
            if self._calc_checksum_task is init:
                self._calc_checksum_task = None

    async def _send_checksum(self):
        init = self._send_checksum_task 
        try:        
            await self.namespace().send_checksum(
                self.key, self._checksum, self._marker
            )
        finally:
            if self._send_checksum is init:
                self._send_checksum_task = None

    def _cancel(self):
        if self._calc_checksum_task is not None:
            self._calc_checksum_task.cancel()
        if self._send_checksum_task is not None:
            self._send_checksum_task.cancel()

    def destroy(self):
        if self._destroyed:
            return
        self._destroyed = True
        if self._checksum is not None:
            buffer_cache.decref(self._checksum)
        self._cancel()
        for rq in self.requests:
            rq.cancel()

        
class ShareNamespace:
    def __init__(self, name, manager, share_evaluate):
        from .core.manager import Manager
        if not isinstance(manager, Manager): 
            raise TypeError(manager)
        self.name = name
        self.manager = weakref.ref(manager)
        self._share_evaluate = share_evaluate

        self.shares = dict()
        self.update_connections = []
        self._send_sharelist_task = None
        

    def add_share(self, key, readonly, celltype, mimetype):
        shareserver.start()
        if key in self.shares:
            self.shares[key].destroy()
        newshare = Share(self, key, readonly, celltype, mimetype)
        self.shares[key] = newshare
        self.refresh_sharelist()
        return newshare
    
    def remove_share(self, key):
        share = self.shares.pop(key)
        share.destroy()
        self.refresh_sharelist()

    @property
    def sharelist(self):
        sharelist = list(self.shares.keys())
        if self._share_evaluate:
            sharelist.append("self")
        return sorted(sharelist)

    def refresh_sharelist(self):
        if self._send_sharelist_task is not None:
            self._send_sharelist_task.cancel()            
        task = self.send_sharelist()
        task = asyncio.ensure_future(task)
        self._send_sharelist_task = task

    async def send_sharelist(self):
        init = self._send_sharelist_task
        try:
            sharelist = sorted(list(self.shares.keys()))
            coros = []
            for connection in self.update_connections:
                coro = shareserver._send_sharelist(self, connection)
                coros.append(coro)
            await asyncio.gather(*coros)
        finally:
            self._send_sharelist_task = None

    async def _get(self, key, mode):
        assert mode in ("checksum", "buffer", "value", "marker")
        share = self.shares[key]
        checksum, marker = await share.read()
        if checksum is not None:
            checksum2 = checksum.hex()
        else:
            checksum2 = None
        if mode == "checksum":
            return checksum2, 'text/plain'

        if share.mimetype is not None:
            content_type = share.mimetype
        else:
            content_type = get_mime(share.celltype)
        manager = self.manager()
        buffer = await manager.cachemanager.fingertip(checksum, must_have_cell=True)
        if mode == "buffer":
            if buffer is None:
                return None, None
            return buffer, "text/plain"
        if mode == "value":
            if buffer is None:
                return None, None
            return buffer, content_type
        result = {
            "checksum": checksum2,
            "marker": marker,
            "content_type": content_type,
        }
        result = json.dumps(result, indent=2, sort_keys=True)
        return result, 'application/json'

    async def get(self, key, mode):
        coro = self._get(key, mode)
        share = self.shares[key]
        fut = asyncio.ensure_future(coro)
        share.requests.append(fut)
        return await fut

    async def _put(self, share, value, mode, marker):
        assert mode in ("checksum", "buffer")
        if mode == "checksum":
            checksum = value
            if checksum is not None:
                checksum = bytes.fromhex(checksum)
            return await share.set_checksum(checksum, marker)
        else:
            buffer = value
            return await share.set_buffer(buffer, marker)

    async def put(self, key, value, mode, marker):        
        share = self.shares[key]
        assert not share.readonly
        coro = self._put(share, value, mode, marker)
        fut = asyncio.ensure_future(coro)
        share.requests.append(fut)
        return await fut

    async def send_checksum(self, key, checksum, marker):
        coros = []
        for connection in self.update_connections:
            coro = shareserver._send_checksum(self, connection, key, checksum, marker)
            coros.append(coro)
        await asyncio.gather(*coros)

    async def computation(self, timeout):
        assert self._share_evaluate
        manager = self.manager()
        if manager is None or manager._destroyed:
            return
        result = []
        for ctx in self.manager().contexts:
            if ctx._destroyed:
                continue            
            waiting, background = await ctx.computation(timeout)
            result += sorted(list(waiting))
        return result

class ShareServer(object):
    DEFAULT_ADDRESS = '127.0.0.1'
    DEFAULT_SHARE_UPDATE_PORT = 5138
    DEFAULT_SHARE_REST_PORT = 5813
    DEFAULT_NAMESPACE = "ctx"

    # TODO: read from os.environ
    address = DEFAULT_ADDRESS
    update_port = DEFAULT_SHARE_UPDATE_PORT
    rest_port = DEFAULT_SHARE_REST_PORT
    _update_server_started = False
    _rest_server_started = False
    _future_start = None

    def __init__(self):
        self.started = False
        self.namespaces = {}
        self.manager_to_ns = weakref.WeakKeyDictionary()

    def _new_namespace(
        self, manager, 
        share_evaluate, 
        name=None
    ):
        if name is None:
            name = self.DEFAULT_NAMESPACE
        if name in self.namespaces:
            count = 1
            name0 = name
            while 1:
                name = name0 + str(count)
                if name not in self.namespaces:
                    break
                count += 1
        self.namespaces[name] = ShareNamespace(
            name, manager, share_evaluate
        )
        self.manager_to_ns[manager] = name
        return name
    
    def destroy_manager(self, manager):
        name = self.manager_to_ns.get(manager)
        if name is None:
            return
        namespace = self.namespaces.pop(name)
        # policy for now: 
        # - close existing update connections
        # - don't touch existing requests
        for con in namespace.update_connections:
            closing = con.close()
            try:
                asyncio.ensure_future(closing)
            except:
                pass

    async def _send(self, websocket, message):
        message = json.dumps(message)
        await websocket.send(message)

    async def _send_sharelist(self, namespace, websocket):
        sharelist = namespace.sharelist
        try:
            return await self._send(websocket, ("sharelist", sharelist))
        except CancelledError:
            raise
        except ConnectionClosed:
            try:
                namespace.update_connections.remove(websocket)
            except ValueError:
                pass
        except Exception as exc:                        
            if DEBUG:
                print("DEBUG shareserver._send_sharelist")
                traceback.print_exc()

    async def _send_checksum(self, namespace, websocket, key, checksum, marker, prior=None):
        if prior is not None:
            await prior
        if checksum is None:
            return
        checksum = checksum.hex()
        try:
            return await self._send(websocket, ("update", (key, checksum, marker)))
        except ConnectionClosed:
            try:
                namespace.update_connections.remove(websocket)
            except ValueError:
                pass
        except Exception as exc:                        
            if DEBUG:
                print("DEBUG shareserver._send_checksum")
                traceback.print_exc()

    async def _serve_update(self, websocket, path):
        if path:
            path = path.lstrip("/")
        assert path in self.namespaces, path #TODO
        """
        In the future, path can be empty (=> get all namespaces)
         or longer than a namespace (=> get part of a namespace)
        Combined with proxying, this can be used to effectively hide part of the shares from access through the proxy
        """
        namespace = self.namespaces[path]
        try:
            await self._send(websocket, ("Seamless share update server", "0.01"))
            namespace.update_connections.append(websocket)
            await self._send_sharelist(namespace, websocket)
        except ConnectionClosed:
            return        
        try:
            async for message in websocket: #keep connection open forever, ignore all messages
                pass
        except ConnectionClosed:
            pass
        finally:
            try:
                namespace.update_connections.remove(websocket)
            except ValueError:
                pass

    async def serve_update(self):
        if self._update_server_started:
            return
        global websockets
        import websockets
        while 1:
            try:
                server = await websockets.serve(
                    self._serve_update,
                    self.address,
                    self.update_port
                )
                break
            except OSError as exc:
                if not is_bound_port_error(exc):
                    raise
                self.update_port += 1
        print("Opened the seamless share update server at port {0}".format(self.update_port))
        self._update_server_started = True

    async def _handle_get(self, request):
        try:
            tail = request.match_info.get('tail')        
            if tail == "favicon.ico":
                return web.Response(
                    status=404
                )
            ns, key = tailsplit(tail)
        except:
            if DEBUG:
                traceback.print_exc()
            return web.Response(
                status=404,
                text="Invalid request",
            )
        
        try:
            namespace = self.namespaces[ns]
            share = namespace.shares[key]
        except KeyError:
            if DEBUG:
                traceback.print_exc()
            return web.Response(
                status=404,
                body=json.dumps({'not found': 404}),
                content_type='application/json'
            )

        mode = request.rel_url.query.get("mode", "value")

        if mode not in ("buffer", "checksum", "value", "marker"):
            err = 'if specified, mode must be "buffer", "checksum", "value", or "marker"'
            if DEBUG:
                print("shareserver _handle.get", err, ns, key, mode)
            return web.Response(
                status=404,
                text=err,
            )

        try:
            result = await namespace.get(key, mode)
            body, content_type = result
            return web.Response(
                status=200,
                body=body,
                content_type=content_type,
            )            
        except CacheMissError:
            if DEBUG:
                checksum = share._checksum
                if checksum is not None:
                    checksum = checksum.hex()  
                print("shareserver GET request, cache miss:", checksum)
            err = "Cache miss"
            return web.Response(
                status=404,
                text=err,
            )
        except CancelledError:
            if DEBUG:
                print("Share was destroyed", ns, key)
            return web.Response(
                status=404,
                text="Share was destroyed"
            )
        except:
            if DEBUG:
                traceback.print_exc()
            return web.Response(
                status=404,
                text="Unknown error"
            )


    async def _handle_put(self, request):
        try:
            tail = request.match_info.get('tail')        
            ns, key = tailsplit(tail)        
            text = await request.text()
            data = json.loads(text)
            assert isinstance(data, dict)
        except:
            if DEBUG:
                traceback.print_exc()
            return web.Response(
                status=404,
                text="Invalid request",
            )

        if "buffer" in data:
            if "checksum" in data:
                if DEBUG:
                    print("shareserver PUT: contains buffer AND checksum")
                return web.Response(
                    status=404,
                    text="contains buffer AND checksum",
                )
            value = data["buffer"]
            mode = "buffer"
        elif "checksum" in data:
            value = data["checkum"]
            mode = "checksum"            
        marker = data.get("marker")

        tail = request.match_info.get('tail')
        ns, key = tailsplit(tail)
        try:
            namespace = self.namespaces[ns]
            share = namespace.shares[key]
        except KeyError:
            if DEBUG:
                traceback.print_exc()
            return web.Response(
                status=404,
                body=json.dumps({'not found': 404}),
                content_type='application/json'
            )

        if share.readonly:
            return web.Response(
                status=404,
                text="Refused, share is read-only",
            )
        try:
            newmarker = await namespace.put(key, value, mode, marker)
            if newmarker is not None:
                newmarker = str(newmarker)
            return web.Response(
                status=200,
                text=newmarker,
            )
        except CancelledError:
            if DEBUG:
                print("Share was destroyed", ns, key)
            return web.Response(
                status=404,
                text="Share was destroyed"
            )
        except:
            if DEBUG:
                traceback.print_exc()
            return web.Response(
                status=404,
                text="Unknown error"
            )


    async def _handle_evaluate(self, request):
        try:
            tail = request.match_info.get('tail')        
            ns, key = tailsplit(tail)        
            text = await request.text()
            data = json.loads(text)
            timeout = data.get("timeout")
            if timeout is not None:
                timeout = float(timeout)
        except:
            if DEBUG:
                traceback.print_exc()
            return web.Response(
                status=404,
                text="Invalid request",
            )
            
        if ns not in self.namespaces or key != "compute":
            return web.Response(
                status=404,
                body=json.dumps({'not found': 404}),
                content_type='application/json'
            )
        namespace = self.namespaces[ns]
        if not namespace._share_evaluate:
            return web.Response(
                status=404,
                body=json.dumps({'compute is not shared': 404}),
                content_type='application/json'
            )
    
        try:
            result = await namespace.computation(timeout)
            return web.Response(
                status=200,
                body=json.dumps(result),
                content_type='application/json'
            )
        except:
            if DEBUG:
                traceback.print_exc()
            return web.Response(
                status=404,
                text="Unknown error"
            )

    async def serve_rest(self):
        global web
        from aiohttp import web
        import aiohttp_cors
        app = web.Application()
        app.add_routes([
            web.get('/{tail:.*}', self._handle_get),
            web.put('/{tail:.*}', self._handle_put),
            web.patch('/{tail:.*}', self._handle_evaluate),
        ])

        # Configure default CORS settings.
        cors = aiohttp_cors.setup(app, defaults={
            "*": aiohttp_cors.ResourceOptions(
                    allow_credentials=True,
                    expose_headers="*",
                    allow_headers="*",
                    allow_methods=["GET", "PATCH", "PUT"]
                )
        })

        # Configure CORS on all routes.
        for route in list(app.router.routes()):
            cors.add(route)

        runner = web.AppRunner(app)
        await runner.setup()
        while 1:
            site = web.TCPSite(runner, self.address, self.rest_port) #TODO: try more ports
            try:
                await site.start()
                break
            except OSError as exc:
                if not is_bound_port_error(exc):
                    raise
                self.rest_port += 1
        print("Opened the seamless REST server at port {0}".format(self.rest_port))

    async def _start(self):
        s1 = self.serve_update()
        s2 = self.serve_rest()
        await s1
        await s2
        self.started = True

    def start(self):
        if not self.started:
            if self._future_start is None:
                self._future_start = asyncio.ensure_future(self._start())
        return self._future_start

shareserver = ShareServer()

from .core.cache.buffer_cache import buffer_cache
from .core.protocol.calculate_checksum import calculate_checksum
from .core.protocol.get_buffer import get_buffer, CacheMissError
from .mime import get_mime