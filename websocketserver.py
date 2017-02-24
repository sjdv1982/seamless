import asyncio
#from queue import Queue, Empty as QueueEmpty
from asyncio.queues import Queue, QueueEmpty
from threading import Lock, Event
import json

class BaseWebSocketServer:
    address = '127.0.0.1'
    _DEFAULT_SOCKET = 5678

    def __init__(self):
        self.socket = None
        self._server = None

    async def _serve(self, websocket, path):
        raise NotImplementedError

    async def start_async(self):
        import websockets
        if self._server is not None:
            return
        socket = self._DEFAULT_SOCKET
        while 1:
            try:
                server = await websockets.serve(self._serve, self.address, socket)
                break
            except OSError:
                socket += 1
        print("Opened a server at socket {0}".format(socket))
        self._server = server
        self.socket = socket

    def start(self):
        loop = asyncio.get_event_loop()
        loop.run_until_complete(self.start_async())

    def close(self):
        if self._server is None:
            return
        loop = asyncio.get_event_loop()
        self._server.close()
        loop.run_until_complete(self._server.wait_closed())
        self._server = None

class MessageSendServer(BaseWebSocketServer):
    def __init__(self):
        self._message_queues = {}
        self._pending_message_queues = {}
        self._connections = {}
        self._closing = False
        self.queue_lock = Lock()

        #connections that are closed before they were ever opened
        self._preclosed_connections = {}

        super().__init__()

    async def _serve(self, websocket, path):
        connection_id = await websocket.recv()
        assert connection_id not in self._message_queues
        with self.queue_lock:
            if connection_id in self._preclosed_connections:
                self._preclosed_connections[connection_id].set()
                return
            self._connections[connection_id] = websocket
            myqueue = self._pending_message_queues.pop(connection_id, None)
            if myqueue is None:
                myqueue = Queue()
            self._message_queues[connection_id] = myqueue
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
            self._message_queues.pop(connection_id)
            self._connections.pop(connection_id)

    async def _send_message(self, connection_id, message):
        assert connection_id is not None
        assert message is not None #has special meaning as terminating message
        if self._closing:
            return
        if connection_id not in self._message_queues:
            with self.queue_lock:
                if connection_id not in self._message_queues:
                    queue = self._pending_message_queues.get(connection_id, None)
                    if queue is None:
                        queue = Queue()
                        self._pending_message_queues[connection_id] = queue
                else: #connection was *just* opened
                    queue = self._message_queues[connection_id]
        else:
            queue = self._message_queues[connection_id]
            #theoretically , this could fail, since another thread
            # could simultaneously close the connection
            # However, in seamless, only one process knows the connection_id,
            # so only one thread may send messages and close the connection
            # RULE: never share connection_ids using cells or registrars!
        #print("PUT", message)
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
        event = None
        with self.queue_lock:
            #don't pop, the _serve function will do that
            queue = self._message_queues.get(connection_id, None)
            if queue is None: #connection is not yet opened
                self._pending_message_queues.pop(connection_id, None)
                event = Event()
                self._preclosed_connections[connection_id] = event
        if event is not None:
            event.wait() #wait until the connection is opened...
            return

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

        Note that if a connection is not yet opened, close_connection will
         wait for it to be opened

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
