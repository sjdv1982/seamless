from . import Task

class GetBufferTask(Task):
    @property
    def refkey(self):
        return self.checksum

    def __init__(self, manager, checksum):
        self.checksum = checksum
        super().__init__(manager)

    async def _run(self):
        if self.checksum is None:
            return None
        value_cache = self.manager().cachemanager.value_cache
        result = await get_buffer_async(self.checksum, value_cache)
        return result

from ...protocol.get_buffer import get_buffer_async