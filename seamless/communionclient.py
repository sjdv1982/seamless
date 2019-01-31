from .core.cache.cache_task import (
    remote_checksum_from_label_servers, 
    remote_transformer_result_servers
)    

class CommunionClient: 
    """wraps a remote servant"""
    destroyed = False
    cache_task_servers = None
    config_type = None

    def __init__(self, servant):
        self.servant = servant
        self.cache_task_servers.append(self.submit)
    
    async def submit(self, argument, origin):
        #print("SUBMIT")
        from .communionserver import communionserver
        if origin is not None and origin == communionserver.peers[self.servant]["id"]:
            return None
        if not communionserver.config_master.get(self.config_type):
            return
        message = self._prepare_message(argument)
        result = await communionserver.client_submit(message, self.servant)        
        return result
    
    def destroy(self):
        if self.destroyed:
            return
        self.destroyed = True
        self.cache_task_servers.remove(self.submit)
    
    def __del__(self):
        try:
            self.destroy()
        except:
            pass

class CommunionLabelClient(CommunionClient):
    config_type = "label"
    cache_task_servers = remote_checksum_from_label_servers
    def _prepare_message(self, label):
        return {
            "type": self.config_type,
            "content": label,
        }

class CommunionTransformerResultClient(CommunionClient):
    config_type = "transformer_result"
    cache_task_servers = remote_transformer_result_servers
    def _prepare_message(self, checksum):
        return {
            "type": self.config_type,
            "content": checksum,
        }


communion_client_types = (
    CommunionLabelClient,
    CommunionTransformerResultClient,
)