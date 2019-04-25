"""
Seamless shareserver REST protocol

Extremely simple.

Short version:
ctx.a.share() =>
- http://localhost:5813/ctx/a gives the value of the cell (HTTP GET)
- At the same address, the value of the cell can be changed with a HTTP PUT request
- Updates to ctx.a send a notification to ws://localhost:5138/ctx
- http://localhost:5813/ctx/equilibrate with an HTTP PATCH request does ctx.equilibrate().
  A timeout can be specified.

Long version:
There is a singleton ShareServer instance at localhost

It opens an update websocket server, and a REST server.

If there is at least one share for a high-level Context,
a new namespace is created with shareserver.new_namespace(<name>) ("ctx" by default).
Every Cell.share() call is translated into a shareserver.share(<namespace>, <cell path>) call.
This adds that cell the variable list of the namespace.

Every webserver connection is namespace-specific. The server only sends, never receives.
All messages are JSON.
Upon connection, a client receives a handshake message: ["Seamless share update server", "0.01"]
Then, it receives a variable list

"""
import os
import json
import asyncio
import weakref

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

    def __init__(self):
        self.started = False
        self.namespaces = {} #TODO: some cleanup, can be memory leak
        self.connections = {} #TODO: some cleanup, can be (minor) memory leak

    def new_namespace(self, namespace=None):
        if namespace is None:
            namespace = self.DEFAULT_NAMESPACE
        if namespace in self.namespaces:
            count = 1
            while 1:
                ns = namespace + str(count)
                if ns not in self.namespaces:
                    break
                count += 1
            namespace = ns
        self.namespaces[namespace] = {}
        self.connections[namespace] = []
        return namespace

    def delete_namespace(self, namespace):
        self.namespaces.pop(namespace, None)
        self.connections.pop(namespace, None)

    async def _send(self, websocket, message):
        message = json.dumps(message)
        try:
            await websocket.send(message)
            return True
        except websockets.exceptions.ConnectionClosed:
            return False

    async def _send_varlist(self, websocket, varlist):
        varlist = [v for v in varlist if v != "self"]
        return await self._send(websocket, ("varlist", varlist))

    async def _send_checksum(self, websocket, key, checksum, marker, prior=None):
        if prior is not None:
            await prior
        if checksum is None:
            return
        return await self._send(websocket, ("update", (key, checksum, marker)))

    async def _serve_update(self, websocket, path):
        if path:
            path = path.lstrip("/")
        assert path in self.namespaces, path #TODO
        """
        In the future, path can be empty (=> get all namespaces)
         or longer than a namespace (=> get part of a namespace)
        Combined with proxying, this can be used to effectively hide part of the shares from access through the proxy
        """
        d = self.namespaces[path]
        if not await self._send(websocket, ("Seamless share update server", "0.01")):
            return
        if not await self._send_varlist(websocket, list(d.keys())):
            return
        for k,v in d.items():
            if k == "self":
                continue
            _, checksum, marker, _ = v
            if not await self._send_checksum(websocket, k, checksum, marker):
                break
        self.connections[path].append(websocket)
        async for message in websocket: #keep connection open forever
            pass
        if not path in self.connections:
            return
        self.connections[path].remove(websocket)

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
            except OSError:
                self.update_port += 1
        print("Opened the seamless share update server at port {0}".format(self.update_port))
        self._update_server_started = True

    async def _handle_get(self, request):
        tail = request.match_info.get('tail')
        if tail == "favicon.ico":
            return web.Response(
                status=404
            )

        namespace, key = tail.split("/")
        try:
            ns = self.namespaces[namespace]
            cell, checksum, marker, content_type = ns[key]
            cell = cell()
            if cell is None:
                raise KeyError
            celltype = cell._celltype
            # TODO (as well): allow paths into the data, if enabled
            value = cell.value
            if celltype == "plain":
                body = json.dumps(value)
            elif celltype in ("text", "python", "cson", "ipython"):
                body = value
            else:
                raise NotImplementedError ### cache branch
            return web.Response(
                status=200,
                body=body,
                content_type=content_type,
            )            
        except KeyError:
            return web.Response(
                status=404,
                body=json.dumps({'not found': 404}),
                content_type='application/json'
            )

    async def _handle_put(self, request):
        text = await request.text()
        data = json.loads(text)
        value = data["value"]
        rq_marker = data.get("marker")
        tail = request.match_info.get('tail')
        namespace, key = tail.split("/")
        try:
            ns = self.namespaces[namespace]
            cell, checksum, marker, _ = ns[key]
            cell = cell()
            if cell is None:
                raise KeyError
            if rq_marker is None or rq_marker >= marker:
                cell.set(value)
                up = self._send_update(namespace, key)
                asyncio.ensure_future(up)
                if rq_marker is None:
                    rq_marker = marker
                newmarker = rq_marker + 1
            else:
                newmarker = marker
            return web.Response(
                status=200,
                text=str(newmarker),
            )
        except KeyError:
            return web.Response(
                status=404,
                body=json.dumps({'not found': 404}),
                content_type='application/json'
            )

    async def _handle_equilibrate(self, request):
        tail = request.match_info.get('tail')
        namespace, key = tail.split("/")
        if namespace not in self.namespaces or key != "equilibrate":
            return web.Response(
                status=404,
                body=json.dumps({'not found': 404}),
                content_type='application/json'
            )
        ns = self.namespaces[namespace]
        if "self" not in ns:
            return web.Response(
                status=404,
                body=json.dumps({'equilibrate is not shared': 404}),
                content_type='application/json'
            )
        text = await request.text()
        data = json.loads(text)
        timeout = data.get("timeout")

        ctx = ns["self"]()
        result = sorted(list(ctx.equilibrate(timeout)))
        return web.Response(
            status=200,
            body=json.dumps(result),
            content_type='application/json'
        )

    async def serve_rest(self):
        global web
        from aiohttp import web
        import aiohttp_cors
        app = web.Application()
        app.add_routes([
            web.get('/{tail:.*}', self._handle_get),
            web.put('/{tail:.*}', self._handle_put),
            web.patch('/{tail:.*}', self._handle_equilibrate),
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
        site = web.TCPSite(runner, self.address, self.rest_port) #TODO: try more ports
        await site.start()
        print("Opened the seamless REST server at port {0}".format(self.rest_port))

    async def _start(self):
        s1 = self.serve_update()
        s2 = self.serve_rest()
        await s1
        await s2
        self.started = True

    def start(self):
        if self.started:
            return
        self._future_start = asyncio.ensure_future(self._start())
        return self._future_start

    async def _share(self, namespace, celldict):
        #TODO: support cells that are inchannels/outchannels
        from .core.structured_cell import StructuredCell
        from .core.cell import Cell
        assert namespace in self.namespaces

        for key, value in celldict.items():
            cell, content_type = value            
            if isinstance(cell, StructuredCell):
                datacell = cell.data
            elif isinstance(cell, Cell):
                datacell = cell
            if datacell._destroyed:
                return # destroy before share

        ns = self.namespaces[namespace]
        old_varlist = sorted(list(ns.keys()))
        varlist = sorted(list(celldict.keys()))
        diff_varlist = (varlist != old_varlist)
        fut = {}
        if diff_varlist:
            for websocket in self.connections[namespace]:
                coro = self._send_varlist(websocket, varlist)
                fut[websocket] = asyncio.ensure_future(coro)

        any_send_update = False
        coros = []
        for key, value in celldict.items():
            cell, content_type = value            
            if key == "self":
                ctx = cell
                ns[key] = weakref.ref(ctx)
                continue
            if isinstance(cell, StructuredCell):
                datacell = cell.data
            elif isinstance(cell, Cell):
                datacell = cell
            else:
                raise TypeError((cell, key))
            checksum = None
            if datacell.value is not None:
                checksum = datacell.checksum
            if key not in ns:
                send_update = True
                marker = 0
            else:
                _, old_checksum, old_marker, _ = ns[key]
                if checksum == old_checksum:
                    send_update = False
                    marker = old_marker
                else:
                    send_update = True
                    marker = old_marker + 1
            ns[key] = [weakref.ref(cell), checksum, marker, content_type]

            if send_update or diff_varlist:
                for websocket in self.connections[namespace]:
                    prior = None
                    if diff_varlist:
                        prior = fut[websocket]
                    if send_update:
                        any_send_update = True
                        coro = self._send_checksum(websocket, key, checksum, marker, prior=prior)
                        coros.append(coro)
        if not any_send_update:
            coros = fut.values()
        await asyncio.gather(*coros)

    def share(self, namespace, celldict):
        for key, value in celldict.items():
            cell, content_type = value            
            cell._get_manager() 
        return asyncio.ensure_future(self._share(namespace, celldict))

    def _get_update_marker(self, namespace, key):
        assert namespace in self.namespaces
        ns = self.namespaces[namespace]
        cell, old_checksum, marker, _ = ns[key]
        if cell is None:
            return
        cell = cell()
        if cell is None:
            return
        checksum = cell.checksum
        if old_checksum == checksum:
            return
        marker += 1
        ns[key][1:3] = checksum, marker
        return checksum, marker

    async def _send_update(self, namespace, key):
        if key not in self.namespaces[namespace]:
            return
        update_marker = self._get_update_marker(namespace, key)
        if update_marker is None:
            return
        checksum, marker = update_marker

        await self._future_start

        coros = []
        for websocket in self.connections[namespace]:
            s = self._send_checksum(websocket, key, checksum, marker)
            coros.append(s)
        await asyncio.gather(*coros)

    def send_update(self, namespace, key):
        asyncio.ensure_future(self._send_update(namespace, key))

shareserver = ShareServer()