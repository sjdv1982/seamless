"""
Seamless shareserver REST protocol

Short version:
ctx.a.share() =>
- http://localhost:5813/ctx/a gives the value of the cell (HTTP GET)
- At the same address, the value of the cell can be changed with a HTTP PUT request
- An update to ctx.a sends a notification to ws://localhost:5138/ctx

Long version:
There is a singleton ShareServer instance at localhost

It opens an update websocket server, and a REST server.

Shares are of the form http://<address>:<port>/<namespace>/<path>
By default, namespace is "ctx", address is localhost, port is 5813
Shares with toplevel=True do not share under /<namespace>/, but under
    http://<address>:<port>/<path> instead.

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

NOTE: The shareserver has a very liberal request size limit (i.e. file upload limit) of 1GB
In production, you will probably want to put Seamless behind a proxy server (e.g. nginx)
that enforces more sensible values
"""
import os
import sys
import asyncio
import weakref
import traceback
import json
import orjson
import base64

from seamless import Checksum

from asyncio import CancelledError
try:
    import aiohttp
    import aiohttp_cors
    from websockets.exceptions import ConnectionClosed
    miss_http_lib = False
except ImportError:
    miss_http_lib = True

class UnboundShareError(AttributeError):
    pass

DEBUG = False
import logging
logger = logging.getLogger(__name__)

def get_subkey(buffer, subkey):
    from seamless.workflow.core.protocol.json import json_dumps
    value = orjson.loads(buffer)
    path = subkey.split("/")
    try:
        for subpath in path:
            try:
                value = value[subpath]
            except:
                subpath = int(subpath)
                value = value[subpath]
    except:
        return None
    return json_dumps(value) + "\n"

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
    pos = tail.find("/")
    if pos == -1:
        return "", tail
    else:
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

    @property
    def binary(self):
        if self.celltype == "mixed":
            binary = "maybe"
            if self.mimetype is not None and (self.mimetype.startswith("text") or self.mimetype == "application/json"):
                binary = False
        elif self.celltype in ("bytes", "binary"):
            binary = True
        else:
            binary = False
        return binary

    def bind(self, share_item):
        assert self.bound is None
        self.bound = share_item

    def unbind(self):
        self.bound = None

    @property
    def toplevel(self):
        if self.bound is None:
            raise AttributeError
        return self.bound.toplevel

    async def read(self, marker=None):
        if marker is not None and marker < self._marker:
            raise CancelledError
        if self._calc_checksum_task is not None:
            if self._calc_checksum_task.cancelled():
                self._calc_checksum_task = None
        while 1:
            if self._calc_checksum_task is None:
                break
            await self._calc_checksum_task
        return self._checksum, self._marker

    def set_checksum(self, checksum:Checksum, marker=None):
        checksum = Checksum(checksum)
        if marker is not None and marker <= self._marker:
            if marker == self._marker:
                return None
            raise CancelledError
        if marker is None:
            marker = self._marker + 1
        if checksum == self._checksum:
            if checksum:
                return self._marker
            else:
                return None
        self._cancel()
        self._checksum = checksum
        if self.bound is None:
            raise AttributeError
        self.bound.update(checksum)
        if checksum:
            self._marker = marker
        send_checksum_task = self._send_checksum()
        send_checksum_task = asyncio.ensure_future(send_checksum_task)
        self._send_checksum_task = send_checksum_task

        return marker

    async def set_buffer(self, buffer, marker=None, *, binary_buffer):
        from .core.share import sharemanager
        if marker is not None and marker <= self._marker:
            if marker == self._marker:
                return marker
            raise CancelledError
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
        if not self.binary:
            buffer = buffer.rstrip(b'\n') + b'\n'
        task = self._calc_checksum(buffer)
        task = asyncio.ensure_future(task)
        self._calc_checksum_task = task
        await task

        checksum = task.result()
        value = await deserialize(buffer, checksum, self.celltype, False)
        new_buffer = await serialize(value, self.celltype)

        task = self._calc_checksum(new_buffer)
        task = asyncio.ensure_future(task)
        self._calc_checksum_task = task
        await task

        checksum = task.result()
        buffer_cache.cache_buffer(checksum, new_buffer)
        await sharemanager.run_once()
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

    async def _get(self, key, mode, subkey=None):
        from seamless.workflow.core.protocol.json import json_dumps
        assert mode in ("checksum", "buffer", "value", "marker")
        if subkey is not None:
            assert mode in ("buffer", "value")
        share = self.shares[key]
        try:
            checksum, marker = await share.read()
        except CancelledError as exc:
            if mode not in ("checksum", "marker"):
                raise Exception from None
            logging.debug(traceback.print_exc())
            raise CancelledError from None
        checksum = Checksum(checksum)
        if mode == "checksum":
            return checksum, 'text/plain'

        if share.mimetype is not None:
            content_type = share.mimetype
        else:
            content_type = get_mime(share.celltype)
        if mode in ("buffer", "value"):
            manager = self.manager()
            buffer = await manager.cachemanager.fingertip(checksum, must_have_cell=True)
            if subkey is not None:
                assert content_type == 'application/json'
                buffer = get_subkey(buffer, subkey)
            if mode == "buffer":
                if buffer is None:
                    return None, None
                content_type_buffer = "text/plain"
                if share.binary:
                    content_type_buffer = content_type
                return buffer, content_type_buffer
            if mode == "value":
                if buffer is None:
                    return None, None
                if share.celltype == "mixed" and content_type.startswith("text"):
                    try:
                        value0 = orjson.loads(buffer)
                        if isinstance(value0, str):
                            value = value0
                    except:
                        pass
                else:
                    value = buffer
                return value, content_type
        result = {
            "checksum": checksum2,
            "marker": marker,
            "content_type": content_type,
        }
        result = json_dumps(result)
        return result, 'application/json'

    async def get(self, key, mode, subkey=None):
        coro = self._get(key, mode, subkey)
        share = self.shares[key]
        fut = asyncio.ensure_future(coro)
        share.requests.append(fut)
        return await fut

    async def _put(self, share, value, mode, marker):
        assert mode in ("checksum", "buffer")
        if mode == "checksum":
            checksum = Checksum(value)
            return share.set_checksum(checksum, marker)
        else:            
            if share.binary:
                try:
                    buffer0 = value.encode("ascii")
                    buffer = base64.b64decode(buffer0)
                    binary_buffer = True
                except Exception as exc:
                    if share.binary == "maybe":
                        buffer = value
                        binary_buffer = False
                    else:
                        raise exc from None
            else:                
                buffer = value
                binary_buffer = False
            return await share.set_buffer(
                buffer, marker, binary_buffer=binary_buffer
            )

    async def put(self, key, value, mode, marker):
        share = self.shares[key]
        assert not share.readonly
        coro = self._put(share, value, mode, marker)
        fut = asyncio.ensure_future(coro)
        share.requests.append(fut)
        try:
            return await fut
        except UnboundShareError as exc:
            raise exc from None
        except CancelledError as exc:
            raise exc from None
        except Exception as exc:
            logger.debug(traceback.format_exc())
            raise exc from None

    async def send_checksum(self, key, checksum, marker):
        coros = []
        for connection in self.update_connections:
            coro = shareserver._send_checksum(self, connection, key, checksum, marker)
            coros.append(coro)
        await asyncio.gather(*coros)

    async def computation(self, timeout):
        try:
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
        except Exception as exc:
            traceback.print_exc()
            raise exc from None

class ShareServer(object):
    DEFAULT_ADDRESS = '0.0.0.0'
    DEFAULT_SHARE_UPDATE_PORT = 5138
    DEFAULT_SHARE_REST_PORT = 5813
    DEFAULT_NAMESPACE = "ctx"

    address = None
    update_port = None
    rest_port = None
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
        binary = [cell for cell in sharelist if cell != "self" and namespace.shares[cell].binary]
        try:
            await self._send(websocket, ("sharelist", sharelist))
            await self._send(websocket, ("binary", binary))
        except CancelledError:
            raise
        except ConnectionClosed:
            try:
                namespace.update_connections.remove(websocket)
            except ValueError:
                pass
        except Exception as exc:
            logger.debug("shareserver._send_sharelist")
            logger.debug(traceback.format_exc())

    async def _send_checksum(self, namespace, websocket, key, checksum:Checksum, marker, prior=None):
        checksum = Checksum(checksum)
        if prior is not None:
            await prior
        if not checksum:
            return
        try:
            return await self._send(websocket, ("update", (key, checksum, marker)))
        except ConnectionClosed:
            try:
                namespace.update_connections.remove(websocket)
            except ValueError:
                pass
        except Exception as exc:
            logger.debug("shareserver._send_checksum")
            logger.debug(traceback.format_exc())


    async def _serve_update_listen(self, websocket, path):
        #keep connection open forever, ignore all messages
        try:
            async for message in websocket:
                pass
        except ConnectionClosed:
            pass

    async def _serve_update_ping(self, websocket, path):
        #keep connection open forever, periodically send a ping
        # else, nginx will close the connection after a minute
        try:
            while 1:
                await asyncio.sleep(10)
                #await websocket.ping()   # is NOT sufficient!
                await self._send(websocket, ("ping",))
        except ConnectionClosed:
            pass

    async def _serve_update(self, websocket, path):
        if path:
            path = path.lstrip("/")
        if path not in self.namespaces:
            return
        """
        In the future, path can be empty (=> get all namespaces)
         or longer than a namespace (=> get part of a namespace)
        Combined with proxying, this can be used to effectively hide part of the shares from access through the proxy
        """
        namespace = self.namespaces[path]
        try:
            await self._send(websocket, ("Seamless share update server", "0.02"))
            namespace.update_connections.append(websocket)
            await self._send_sharelist(namespace, websocket)
        except ConnectionClosed:
            return
        try:
            task_listen = asyncio.ensure_future(self._serve_update_listen(websocket, path))
            task_ping = asyncio.ensure_future(self._serve_update_ping(websocket, path))
            done, pending = await asyncio.wait(
                [task_listen, task_ping],
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()
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
        if "SEAMLESS_SILENT" not in os.environ:
            print("Opened the seamless share update server at port {0}".format(self.update_port), file=sys.stderr)
        self._update_server_started = True

    def _find_toplevel(self, key):
        for name in sorted(list(self.namespaces.keys())):
            namespace = self.namespaces[name]
            share = namespace.shares.get(key)
            if share is not None and share.bound and share.toplevel:
                return namespace

    async def _handle_get(self, request):
        try:
            tail = request.match_info.get('tail')
            if tail == "favicon.ico":
                return web.Response(
                    status=404
                )
            ns, key = tailsplit(tail)
        except:
            logger.debug("shareserver._handle_get")
            logger.debug(traceback.format_exc())
            return web.Response(
                status=400,
                text="Invalid request",
            )
        if ns == "":
            if key == "":
                raise web.HTTPFound('/index.html')
            namespace = self._find_toplevel(key)
            if namespace is None:
                if key == "index.html" and "ctx" in self.namespaces:
                    await asyncio.sleep(2)
                    namespace = self._find_toplevel(key)
                    if namespace is None:
                        raise web.HTTPFound('/ctx/index.html')
                    else:
                        return await self._handle_get(request)
                else:
                    return web.Response(
                        status=404,
                        body=json.dumps({'not found': 404}),
                        content_type='application/json'
                    )
            share = namespace.shares[key]
            subkey = None
        else:
            try:
                namespace = self.namespaces[ns]
                if key == "":
                    raise web.HTTPFound('/{}/index.html'.format(ns))
                try:
                    share = namespace.shares[key]
                    subkey = None
                except KeyError:
                    ok = False
                    for pos in range(len(key)-1,0,-1):
                        if key[pos] != "/":
                            continue
                        key2, subkey = key[:pos], key[pos+1:]
                        try:
                            share = namespace.shares[key2]
                            ok = True
                            key = key2
                            break
                        except KeyError:
                            pass
                    if not ok:
                        raise KeyError(key) from None
            except KeyError:
                logger.debug("shareserver._handle_get")
                logger.debug(traceback.format_exc())
                return web.Response(
                    status=404,
                    body=json.dumps({'not found': 404}),
                    content_type='application/json'
                )

        mode = request.rel_url.query.get("mode", "value")

        if mode not in ("buffer", "checksum", "value", "marker"):
            err = 'if specified, mode must be "buffer", "checksum", "value", or "marker"'
            msg = "shareserver._handle_get", err, ns, key, mode
            logger.debug(" ".join([str(m) for m in msg]))
            logger.debug(traceback.format_exc())
            return web.Response(
                status=400,
                text=err,
            )

        try:
            result = await namespace.get(key, mode, subkey)
            body, content_type = result
            if body is None:
                return web.Response(
                    status=404,
                    text="empty",
                )
            if content_type is not None and content_type.startswith("text"):
                charset = "utf-8"
            else:
                charset = None
            return web.Response(
                status=200,
                body=body,
                content_type=content_type,
                charset=charset
            )
        except CacheMissError:
            checksum = Checksum(share._checksum)
            logger.debug("shareserver GET request, cache miss: {}".format(checksum))
            logger.debug(traceback.format_exc())
            err = "Cache miss"
            return web.Response(
                status=404,
                text=err,
            )
        except CancelledError as exc:
            msg = "Share was destroyed", ns, key
            logger.debug(" ".join([str(m) for m in msg]))
            logger.debug(traceback.format_exc())
            return web.Response(
                status=404,
                text="Share was destroyed"
            )
        except aiohttp.web_exceptions.HTTPClientError as exc:
            logger.debug("shareserver._handle_get")
            logger.debug(traceback.format_exc())
            return web.Response(
                status=exc.status_code,
                text=exc.reason,
            )
        except:
            logger.debug(traceback.format_exc())
            return web.Response(
                status=500,
                text="Unknown error"
            )


    async def _handle_put(self, request):
        try:
            tail = request.match_info.get('tail')
            ns, key = tailsplit(tail)
            text = await request.text()
            data = orjson.loads(text)
            assert isinstance(data, dict)
        except aiohttp.web_exceptions.HTTPClientError as exc:
            logger.debug(traceback.format_exc())
            return web.Response(
                status=exc.status_code,
                text=exc.reason,
            )
        except:
            logger.debug(traceback.format_exc())
            return web.Response(
                status=400,
                text="Invalid request",
            )

        if "buffer" in data:
            if "checksum" in data:
                logger.debug("shareserver PUT: contains buffer AND checksum")
                return web.Response(
                    status=400,
                    text="contains buffer AND checksum",
                )
            value = data["buffer"]
            mode = "buffer"
            if value is None or value == "null":
                marker = data.get("marker")
                return web.Response(
                    status=200,
                    text=str(marker),
                )
        elif "checksum" in data:
            value = data["checksum"]
            mode = "checksum"
        marker = data.get("marker")

        tail = request.match_info.get('tail')
        ns, key = tailsplit(tail)

        if ns == "":
            if key == "":
                raise web.HTTPFound('/index.html')
            namespace = self._find_toplevel(key)
            if namespace is None:
                if key == "index.html" and "ctx" in self.namespaces:
                    raise web.HTTPFound('/ctx/index.html')
                else:
                    return web.Response(
                        status=404,
                        body=json.dumps({'not found': 404}),
                        content_type='application/json'
                    )
            share = namespace.shares[key]
        else:
            try:
                namespace = self.namespaces[ns]
            except KeyError:
                logger.debug(traceback.format_exc())
                return web.Response(
                    status=404,
                    body=json.dumps({'not found': 404}),
                    content_type='application/json'
                )

        try:
            share = namespace.shares[key]
        except KeyError:
            logger.debug(traceback.format_exc())
            return web.Response(
                status=404,
                body=json.dumps({'not found': 404}),
                content_type='application/json'
            )

        if share.readonly:
            sharecell = None
            if share.bound is not None:
                sharecell = share.bound.cellname
            if sharecell is not None:
                msg = """Seamless just received a PUT request for {c}, but {c} is read-only.
Share {c} with readonly=False to allow HTTP PUT requests"""
                logger.warning(msg.format(c="cell " + sharecell))
            return web.Response(
                status=405,
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
        except UnboundShareError as exc:
            msg = "Share was destroyed", ns, key
            logger.debug(" ".join([str(m) for m in msg]))
            return web.Response(
                status=404,
                text="Share was destroyed"
            )
        except CancelledError:
            msg = "PUT was superseded", ns, key
            logger.debug(" ".join([str(m) for m in msg]))
            return web.Response(
                status=409,
                text="PUT was superseded"
            )
        except:
            logger.debug(traceback.format_exc())
            return web.Response(
                status=500,
                text="Unknown error"
            )

    async def serve_rest(self):
        global web
        from aiohttp import web
        import aiohttp_cors
        app = web.Application(
            client_max_size=1024**3,
            debug=DEBUG
        )
        app.add_routes([
            web.get('/{tail:.*}', self._handle_get),
            web.put('/{tail:.*}', self._handle_put)
        ])

        # Configure default CORS settings.
        cors = aiohttp_cors.setup(app, defaults={
            "*": aiohttp_cors.ResourceOptions(
                    allow_credentials=True,
                    expose_headers="*",
                    allow_headers="*",
                    allow_methods=["GET", "PUT"]
                )
        })

        # Configure CORS on all routes.
        for route in list(app.router.routes()):
            cors.add(route)

        runner = web.AppRunner(app)
        await runner.setup()
        while 1:
            site = web.TCPSite(runner, self.address, self.rest_port)
            try:
                await site.start()
                break
            except OSError as exc:
                if not is_bound_port_error(exc):
                    raise
                self.rest_port += 1
        if "SEAMLESS_SILENT" not in os.environ:
            print("Opened the seamless REST server at port {0}".format(self.rest_port), file=sys.stderr)

    async def _start(self):
        s1 = self.serve_update()
        s2 = self.serve_rest()
        await s1
        await s2
        self.started = True

    def start(self):
        if miss_http_lib:
            raise ImportError("aiohttp, aiohttp_cors and/or websockets are missing")
        if self.address is None:
            self.address = self.DEFAULT_ADDRESS
        if self.update_port is None:
            self.update_port = self.DEFAULT_SHARE_UPDATE_PORT
        if self.rest_port is None:
            self.rest_port = self.DEFAULT_SHARE_REST_PORT

        if not self.started:
            if self._future_start is None:
                self._future_start = asyncio.ensure_future(self._start())
        return self._future_start

shareserver = ShareServer()

from seamless import CacheMissError, Checksum
from seamless.buffer.buffer_cache import buffer_cache
from seamless.buffer.deserialize import deserialize
from seamless.buffer.serialize import serialize
from seamless.buffer.get_buffer import get_buffer
from seamless.buffer.mime import get_mime