import asyncio

REMOTE_TIMEOUT = 5.0

class CommunionClient:
    pass

class CommunionBufferClient(CommunionClient):
    config_type = "buffer"

    def __init__(self, servant, config):
        self.servant = servant
        self.config_buffer = config["buffer"]
        self.config_status = config["buffer_status"]

    async def status(self, checksum):
        assert checksum is not None
        if not self.config_status:
            return
        message = {
            "type": "buffer_status",
            "content": checksum.hex()
        }
        result = await communion_server.client_submit(message, self.servant)
        if result is not None:
            try:
                status = result
                if status in (0, 1):
                    communion_client_manager.remote_checksum_available.add(
                        checksum
                    )
            except:
                pass
        return result
    
    async def submit(self, checksum):
        assert checksum is not None
        if not self.config_buffer:
            return
        message = {
            "type": "buffer",
            "content": checksum.hex()
        }
        result = await communion_server.client_submit(message, self.servant)
        return result


class CommunionBufferLengthClient(CommunionClient):
    config_type = "buffer_length"

    def __init__(self, servant, config):
        self.servant = servant

    async def submit(self, checksum):
        assert checksum is not None
        message = {
            "type": "buffer_length",
            "content": checksum.hex()
        }
        result = await communion_server.client_submit(message, self.servant)
        return result

class CommunionSemanticToSyntacticChecksumClient(CommunionClient):
    config_type = "semantic_to_syntactic"

    def __init__(self, servant, config):
        self.servant = servant

    async def submit(self, checksum, celltype, subcelltype):
        assert checksum is not None
        message = {
            "type": "semantic_to_syntactic",
            "content": (checksum.hex(), celltype, subcelltype)
        }
        result = await communion_server.client_submit(message, self.servant)
        if result is not None:
            result = [bytes.fromhex(r) for r in result]
        return result

class CommunionTransformationClient(CommunionClient):
    config_type = "transformation"

    def __init__(self, servant, config):
        self.servant = servant
        self.config_job = config["transformation_job"]
        self.config_status = config["transformation_status"]
        self.config_hard_cancel = config["hard_cancel"]
        self.config_clear_exception = config["clear_exception"]
        self.future_clear_exception = None

    async def status(self, checksum): 
        if self.future_clear_exception is not None:
            await self.future_clear_exception
        assert checksum is not None
        if not self.config_status:
            return None, None
        message = {
            "type": "transformation_status",
            "content": checksum.hex()
        }        
        result = await communion_server.client_submit(message, self.servant)        
        if result is not None and isinstance(result[-1], str):
            result = (*result[:-1], bytes.fromhex(result[-1]))
        return result

    async def wait(self, checksum):
        if self.future_clear_exception is not None:
            await self.future_clear_exception
        if not self.config_job:
            return
        message = {
            "type": "transformation_wait",
            "content": checksum.hex()
        }
        await communion_server.client_submit(message, self.servant)

    async def submit(self, checksum):
        if self.future_clear_exception is not None:
            await self.future_clear_exception
        if not self.config_job:
            return
        message = {
            "type": "transformation_job",
            "content": checksum.hex()
        }
        result = await communion_server.client_submit(message, self.servant)
        return result

    async def cancel(self, checksum):
        if self.future_clear_exception is not None:
            await self.future_clear_exception
        if not self.config_job:
            return
        message = {
            "type": "transformation_cancel",
            "content": checksum.hex()
        }
        await communion_server.client_submit(message, self.servant)

    async def hard_cancel(self, checksum):
        if self.future_clear_exception is not None:
            await self.future_clear_exception
        if not self.config_hard_cancel:
            return
        message = {
            "type": "transformation_hard_cancel",
            "content": checksum.hex()
        }
        await communion_server.client_submit(message, self.servant)

    async def clear_exception(self, checksum):
        message = {
            "type": "transformation_clear_exception",
            "content": checksum.hex()
        }
        await communion_server.client_submit(message, self.servant)
        self.future_clear_exception = None


class CommunionClientManager:
    _clientclasses = [klass for klass in globals().values() if isinstance(klass, type) \
      and issubclass(klass, CommunionClient) and klass is not CommunionClient]

    _clientclasses = {klass.config_type:klass for klass in _clientclasses}

    def __init__(self):
        self.clients = {k:[] for k in self._clientclasses}
        self.remote_checksum_available = set()
        self.servant_to_clients = {}
        self.servant_to_peer_id = {}

    def add_servant(self, servant, peer_id, *,
            config_servant, config_master
    ):
        servid = id(servant)
        self.servant_to_clients[servid] = []
        self.servant_to_peer_id[servid] = peer_id
        communion_types = {
            "buffer": ["buffer", "buffer_status"],
            "buffer_length": ["buffer_length"],
            "semantic_to_syntactic": ["semantic_to_syntactic"],
            "transformation": [
                "transformation_job", "transformation_status",
                "hard_cancel", "clear_exception",
            ],
        }
        for communion_type in communion_types:
            sub_communion_types = {}
            for sub_communion_type in communion_types[communion_type]:
                if sub_communion_type in ("hard_cancel", "clear_exception"):
                    c_master = True
                else:
                    c_master = config_master[sub_communion_type]
                c_servant = config_servant[sub_communion_type]               
                if not c_master or not c_servant:
                    c = False
                elif sub_communion_type == "buffer":
                    if c_servant == "small" or c_master == "small":
                        c = "small"
                    else:
                        c = True
                else:
                    c = True
                sub_communion_types[sub_communion_type] = c
            if not any(sub_communion_types.values()):
                continue
            print("ADD SERVANT", communion_type)
            clientclass = self._clientclasses[communion_type]
            client = clientclass(servant, sub_communion_types)
            self.clients[communion_type].append(client)
            self.servant_to_clients[servid].append((communion_type, client))

    def remove_servant(self, servant):
        self.remote_checksum_available.clear()
        clients = self.servant_to_clients.pop(id(servant))
        self.servant_to_peer_id.pop(id(servant))
        for communion_type, client in clients:
            print("REMOVE SERVANT", communion_type)
            self.clients[communion_type].remove(client)

    async def remote_semantic_to_syntactic(self, checksum, celltype, subcelltype, peer_id):
        clients = []
        for client in self.clients["semantic_to_syntactic"]:
            client_peer_id = self.servant_to_peer_id[id(client.servant)]
            if client_peer_id != peer_id:
                clients.append(client)
        if not len(clients):
            return None
        coros = [client.submit(checksum, celltype, subcelltype) for client in clients]
        results = await asyncio.gather(*coros)
        result = []
        for r in results:
            if r is not None:
                result += r
        if not len(result):
            return None
        return result

    async def remote_buffer_status(self, checksum, peer_id):
        if checksum in self.remote_checksum_available:
            return True
        clients = []
        for client in self.clients["buffer"]:
            client_peer_id = self.servant_to_peer_id[id(client.servant)]
            if client_peer_id != peer_id:
                clients.append(client)
        if not len(clients):
            return False
        coros = [client.status(checksum) for client in clients]
        futures = [asyncio.ensure_future(coro) for coro in coros]
        while 1:
            done, pending = await asyncio.wait(futures, 
                timeout=REMOTE_TIMEOUT,
                return_when=asyncio.FIRST_COMPLETED
            )
            for future in done:
                try:
                    result = future.result()
                    status = result
                    if status > 0:
                        return True
                except:
                    import traceback
                    traceback.print_exc()
                    continue
            if not len(pending):
                return False         

    async def remote_transformation_status(self, checksum, peer_id):
        clients = []        
        for client in self.clients["transformation"]:
            client_peer_id = self.servant_to_peer_id[id(client.servant)]
            if client_peer_id != peer_id:
                clients.append(client)
        if not len(clients):
            return 
        coros = [client.status(checksum) for client in clients]
        futures = [asyncio.ensure_future(coro) for coro in coros]
        best_status, best_result = None, None
        while 1:
            done, pending = await asyncio.wait(futures, 
                timeout=REMOTE_TIMEOUT,
                return_when=asyncio.FIRST_COMPLETED
            )            
            for future in done:
                try:
                    status, result = future.result()
                    if status < 0:
                        continue
                    if best_status is None or status > best_status:
                        best_status = status
                except:
                    import traceback
                    traceback.print_exc()
                    continue
            if not len(pending):
                break
        if best_status is None:
            return None
        return best_status, best_result

communion_client_manager = CommunionClientManager()
from .communion_server import communion_server