# TODO # livegraph branch
"""
from .core.events.cache_task import (
    remote_transformer_result_servers,
    remote_transformer_result_level2_servers,
    remote_checksum_value_servers
)    
from .core.events.jobscheduler import remote_job_servers
from .core.build_module import remote_build_model_servers
"""

class CommunionClient: 
    """wraps a remote servant"""
    destroyed = False
    cache_task_servers = None
    config_type = None

    def __init__(self, servant):
        raise NotImplementedError # livegraph branch
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
        except Exception:
            pass

class CommunionPairClient: 
    """wraps a remote servant with two funcmodes; one to check, one to give the results"""
    destroyed = False
    cache_task_servers = None
    config_type = None

    def __init__(self, servant):
        self.servant = servant
        self.cache_task_servers.append((self.check, self.run))
    
    async def submit(self, funcmode, argument, origin):
        #print("SUBMIT", mode)
        from .communionserver import communionserver
        if origin is not None and origin == communionserver.peers[self.servant]["id"]:
            return None
        if not communionserver.config_master.get(self.config_type):
            return
        message = self._prepare_message(funcmode, argument)
        result = await communionserver.client_submit(message, self.servant)        
        return result
    
    async def check(self, argument, origin):
        return await self.submit("check", argument, origin)

    async def run(self, argument, origin):
        return await self.submit("run", argument, origin)

    def destroy(self):
        if self.destroyed:
            return
        self.destroyed = True
        self.cache_task_servers.remove((self.check, self.run))
    
    def __del__(self):
        try:
            self.destroy()
        except Exception:
            pass

# TODO # livegraph branch
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

class CommunionTransformerResultL2Client(CommunionClient):
    config_type = "transformer_result_level2"
    cache_task_servers = remote_transformer_result_level2_servers
    def _prepare_message(self, checksum):
        return {
            "type": self.config_type,
            "content": checksum,
        }


class CommunionBufferCacheClient(CommunionPairClient):
    config_type = "value"
    cache_task_servers = remote_checksum_value_servers
    def _prepare_message(self, funcmode, checksum):
        if funcmode == "check":
            return {
                "type": "buffer_check",
                "content": checksum,
            }
        elif funcmode == "run":
            return {
                "type": "value_get",
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


communion_client_types = (
    CommunionLabelClient,
    CommunionBuildModuleClient,
    CommunionTransformerResultClient,
    CommunionTransformerResultL2Client,
    CommunionBufferCacheClient,
    CommunionTransformerJobClient,
)
"""