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
        if not await self._send(websocket, list(d.keys())):
            return
        for k,v in d.items():
            _, checksum, marker = v
            if not await self._send(websocket, (k, checksum, marker)):
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
        namespace, key = tail.split("/")
        try:
            ns = self.namespaces[namespace]
            cell, checksum, marker = ns[key]
            cell = cell()
            if cell is None:
                raise KeyError
            value = cell.serialize("ref", "text", "json")
            return web.Response(text=json.dumps(value))
        except KeyError:
            return web.Response(text=json.dumps(None))
        

    async def _handle_put(self, request):        
        text = await request.text()   
        data = json.loads(text)
        value = data["value"]
        #TODO: marker
        tail = request.match_info.get('tail')
        namespace, key = tail.split("/")
        try:
            ns = self.namespaces[namespace]
            cell, checksum, marker = ns[key]
            cell = cell()
            if cell is None:
                raise KeyError
            cell.set(value)
            return web.Response(text=json.dumps(marker+1))
        except KeyError:
            return web.Response(text=json.dumps(None))

        

    async def serve_rest(self):
        global web
        from aiohttp import web
        app = web.Application()
        app.add_routes([
            web.get('/{tail:.*}', self._handle_get),
            web.put('/{tail:.*}', self._handle_put),
            #TODO: POST with equilibrate
        ])
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

    def share(self, namespace, key, cell):
        #TODO: support cells that are inchannels/outchannels
        from .core.structured_cell import StructuredCell
        from .core.cell import Cell
        assert namespace in self.namespaces
        ns = self.namespaces[namespace]
        if isinstance(cell, StructuredCell):
            datacell = cell.data
        elif isinstance(cell, Cell):
            datacell = cell
        else:
            raise TypeError(cell)
        checksum = None
        if datacell.value is not None:
            checksum = datacell.checksum()
        if key not in ns:
            marker = 0
        else:
            _, _, marker = ns[key]
        ns[key] = [weakref.ref(cell), checksum, marker]

    async def _send_update(self, namespace, key):
        assert namespace in self.namespaces
        ns = self.namespaces[namespace]
        cell, old_checksum, marker = ns[key]
        if cell is None:
            return
        cell = cell()
        if cell is None:
            return
        checksum = cell.checksum()
        if old_checksum == checksum:
            return
        marker += 1
        ns[key][1:3] = checksum, marker

        await self._future_start

        coros = []
        for websocket in self.connections[namespace]:
            s = self._send(websocket, (key, checksum, marker))
            coros.append(s)
        await asyncio.gather(*coros)
    
    def send_update(self, namespace, key):
        asyncio.ensure_future(self._send_update(namespace, key))
        
shareserver = ShareServer()