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
        buffer_cache = self.manager().cachemanager.buffer_cache
        result = await get_buffer_async(self.checksum, buffer_cache)
        assert result is None or isinstance(result, bytes)
        return result

from ...protocol.get_buffer import get_buffer_async