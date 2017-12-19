import asyncio
#from queue import Queue, Empty as QueueEmpty
from asyncio.queues import Queue, QueueEmpty
from threading import Lock, Event
import json
import copy
import warnings

class BaseWebSocketServer:
    address = '127.0.0.1'
    DEFAULT_PORT = 5678

    #when new connections are opened,
    # they receive the first 50 and the last 50 events
    CACHE_EVENTS_FIRST = 50
    CACHE_EVENTS_LAST = 50

    def __init__(self):
        self.port = None
        self._server = None
        self._public_address = None
        self._public_port = None
        self._started = False

    async def _serve(self, websocket, path):
        raise NotImplementedError

    async def start_async(self):
        import websockets
        if self._server is not None:
            return
        port = self.DEFAULT_PORT
        while 1:
            try:
                server = await websockets.serve(self._serve, self.address, port)
                break
            except OSError:
                port += 1
        print("Opened the seamless websocketserver at port {0}".format(port))
        self._server = server
        self.port = port

    def start(self, address = None):
        self._started = True
        if address is not None:
            self.address = address
        loop = asyncio.get_event_loop()
        loop.run_until_complete(self.start_async())
        self._started = False

    @property
    def public_address(self):
        """Returns the server's public address
        By default, it is the same as the (internal) address"""
        if self._public_address is not None:
            return self._public_address
        else:
            return self.address
    @public_address.setter
    def public_address(self, value):
        """Sets the server's public address (after NAT)
        By default, it is the same as the (internal) address"""
        if self._started:
            warnings.warn("""Changed the seamless websocketserver's public address after its has started.
            As of seamless 0.2, this will not auto-update any workers (notably dynamic_html) that use this value""")
        self._public_address = value

    @property
    def public_port(self):
        """Returns the server's public port
        By default, it is the same as the (internal) port"""
        if self._public_port is not None:
            return self._public_port
        else:
            return self.port

    @public_port.setter
    def public_port(self, value):
        """Sets the server's public port (after NAT)
        By default, it is the same as the (internal) port"""
        if self._started:
            warnings.warn("""Changed the seamless websocketserver's public port after its has started.
            As of seamless 0.2, this will not auto-update any workers (notably dynamic_html) that use this value""")
        self._public_port = value

    def close(self):
        if self._server is None:
            return
        loop = asyncio.get_event_loop()
        self._server.close()
        loop.run_until_complete(self._server.wait_closed())
        self._server = None

class MessageSendServer(BaseWebSocketServer):
    def __init__(self):
        self._message_queue_lists = {}
        self._pending_message_queues = {}
        self._closing = False
        self.queue_lock = Lock()

        super().__init__()

    async def _serve(self, websocket, path):
        import websockets
        connection_id = await websocket.recv()
        with self.queue_lock:
            #if connection_id in self._preclosed_connections:
            #    self._preclosed_connections[connection_id].set()
            #    return
            pmqueue = self._pending_message_queues.get(connection_id, None)
            myqueue = Queue()
            if pmqueue is not None:
                events = []
                while 1:
                    try:
                        e = pmqueue.get_nowait()
                    except QueueEmpty:
                        break
                    events.append(e)
                if len(events) > self.CACHE_EVENTS_FIRST + self.CACHE_EVENTS_LAST:
                    events = events[:self.CACHE_EVENTS_FIRST] + \
                        events[-self.CACHE_EVENTS_LAST:]
                for enr, e in enumerate(events):
                    swallow = False
                    if e.get("type", None) == "var":
                        varname = e.get("var", None)
                        if varname is not None:
                            for e2 in events[enr+1:]:
                                if e2.get("type", None) != "var":
                                    continue
                                if e2.get("var", None) != varname:
                                    continue
                                swallow = True
                                break
                    if swallow:
                        continue
                    myqueue.put_nowait(e)
                    pmqueue.put_nowait(e) #put the events back
            if connection_id not in self._message_queue_lists:
                self._message_queue_lists[connection_id] = []
            self._message_queue_lists[connection_id].append(myqueue)
        while True:
            #print("WAIT")
            try:
                message = await myqueue.get()
            except Exception:
                break
            message = json.dumps(message)
            #print("SEND?", message)
            if message is None: #terminating message
                break
            try:
                #print("SEND", message)
                await websocket.send(message)
            except websockets.exceptions.ConnectionClosed:
                break
        with self.queue_lock:
            self._message_queue_lists[connection_id].remove(myqueue)

    async def _send_message(self, connection_id, message):
        assert connection_id is not None
        assert message is not None #has special meaning as terminating message
        if self._closing:
            return

        pmqueue = self._pending_message_queues.get(connection_id, None)
        if pmqueue is None:
            pmqueue = Queue()
            self._pending_message_queues[connection_id] = pmqueue
        queues = [pmqueue] + self._message_queue_lists.get(connection_id, [])
        for queue in queues:
            await queue.put(message)

    def send_message(self, connection_id, message):
        """
        Send a message to a connection

        Make sure that no other thread is simultaneously closing the connection
        Simultaneously consuming connection messages queue is OK
        """
        loop = asyncio.get_event_loop()
        loop.run_until_complete(self._send_message(connection_id, message))

    async def _close_connection(self, connection_id):
        with self.queue_lock:
            queues = self._message_queue_lists.pop(connection_id, [])
            if queue is None: #connection is not yet opened
                self._pending_message_queues.pop(connection_id, None)

        for queue in queues:
            while 1: #flush the queue, discarding all items
                try:
                    await queue.get_nowait()
                except QueueEmpty:
                    #queue is empty and will remain empty
                    #we push now one final message, None, for termination
                    await queue.put(None)
                    break

    def close_connection(self, connection_id):
        """
        Close a connection

        Make sure that no other thread is simultaneously sending messages
         to the connection, or is simultaneously closing it
        """
        loop = asyncio.get_event_loop()
        loop.run_until_complete(self._close_connection(connection_id))

    def close(self):
        if self._closing:
            return
        self._closing = True
        super().close()
        all_connection_ids = list(self._pending_message_queues.keys()) + \
          list(self._message_queues.keys())
        for connection_id in all_connection_ids:
            self.close_connection(connection_id)


websocketserver = MessageSendServer()
