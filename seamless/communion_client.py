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
            "content": checksum
        }
        result = await communion_server.client_submit(message, self.servant)
        if result is not None:
            try:
                status, result_checksum = result
                if status in (0, 1):
                    communion_client_manager.remote_checksum_available.add(
                        result_checksum
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
            "content": checksum
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
            "content": checksum
        }
        result = await communion_server.client_submit(message, self.servant)
        return result

class CommunionTransformationClient(CommunionClient):
    config_type = "transformation"

    def __init__(self, servant, config):
        self.servant = servant
        self.config_job = config["transformation_job"]
        self.config_status = config["transformation_status"]

    async def status(self, checksum):
        assert checksum is not None
        if not self.config_status:
            return
        message = {
            "type": "transformation_status",
            "content": checksum
        }
        result = await communion_server.client_submit(message, self.servant)
        return result
    
    async def submit(self, checksum):
        if not self.config_job:
            return
        message = {
            "type": "transformation_job",
            "content": checksum
        }
        result = await communion_server.client_submit(message, self.servant)
        return result


class CommunionBuildModuleClient(CommunionClient):
    config_type = "build_module"

    def __init__(self, servant, config):
        self.servant = servant
        self.config_job = config["build_module_job"]
        self.config_status = config["build_module_status"]

    async def status(self, checksum):
        assert checksum is not None
        if not self.config_status:
            return
        message = {
            "type": "build_module_status",
            "content": checksum
        }
        result = await communion_server.client_submit(message, self.servant)
        return result
    
    async def submit(self, checksum):
        if not self.config_job:
            return
        message = {
            "type": "transformation_job",
            "content": checksum
        }
        result = await communion_server.client_submit(message, self.servant)
        return result

"""
class CommunionBuildModuleClient(CommunionClient):
    config_type = "build_module"
    cache_task_servers = remote_build_model_servers
    def _prepare_message(self, content):
        return {
            "type": self.config_type,
            "content": content,
        }

class CommunionTransformerResultClient(CommunionClient):
    config_type = "transformer_result"
    cache_task_servers = remote_transformer_result_servers
    def _prepare_message(self, checksum):
        return {
            "type": self.config_type,
            "content": checksum,
        }


class CommunionTransformerJobClient(CommunionPairClient):
    config_type = "transformer_job"
    cache_task_servers = remote_job_servers
    def _prepare_message(self, funcmode, checksum):
        if funcmode == "check":
            return {
                "type": "transformer_job_check",
                "content": checksum,
            }
        elif funcmode == "run":
            return {
                "type": "transformer_job_run",
                "content": checksum,
            }


"""

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
            "transformation": ["transformation_job", "transformation_status"],
            "build_module": ["build_module_job", "build_module_status"],
        }
        for communion_type in communion_types:
            sub_communion_types = {}
            for sub_communion_type in communion_types[communion_type]:
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
            done, pending = await asyncio.wait(*futures, 
                timeout=REMOTE_TIMEOUT,
                return_when=asyncio.FIRST_COMPLETED
            )
            for future in done:
                try:
                    result = future.result()
                    if result > 0:
                        return True
                except:
                    continue
            if not len(pending):
                return False         


communion_client_manager = CommunionClientManager()
from .communion_server import communion_server