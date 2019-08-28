class CommunionClient: 
    """wraps a remote servant"""
    config_type = None

    def __init__(self, servant):
        self.servant = servant
    
    async def submit(self, argument, origin):
        #print("SUBMIT")
        from .communion_server import communion_server
        if origin is not None and origin == communion_server.peers[self.servant]["id"]:
            return None
        if not communion_server.config_master.get(self.config_type):
            return
        message = self._prepare_message(argument)
        result = await communion_server.client_submit(message, self.servant)        
        return result
        


class CommunionBufferClient(CommunionClient):
    config_type = "buffer"
    def _prepare_message(self, checksum):
        return {
            "type": "buffer",
            "content": checksum,
        }

class CommunionTransformationClient(CommunionClient):
    config_type = "transformation"
    def __init__(self, *args, **kwargs):
        raise NotImplementedError
        #TODO: use communion_client_manager.remote_checksum_available

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

    def add_client(self, communion_type, servant):
        assert communion_type in self._clientclasses, \
          (communion_type, list(self._clientclasses.keys()))
        servid = id(servant)
        if servid not in self.servant_to_clients:
            self.servant_to_clients[servid] = []
        clientclass = self._clientclasses[communion_type]
        client = clientclass(servant)
        self.clients[communion_type].append(client)
        self.servant_to_clients[servid].append((communion_type, client))

    def remove_servant(self, servant):
        self.remote_checksum_available.clear()
        clients = self.servant_to_clients.pop(id(servant))
        for communion_type, client in clients:
            self.clients[communion_type].remove(client)


communion_client_manager = CommunionClientManager()