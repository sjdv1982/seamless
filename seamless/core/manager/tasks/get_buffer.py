from . import Task
from ...protocol import serialize
from ...protocol.calculate_checksum import checksum_cache

class GetBufferTask(Task):
    @property
    def refkey(self):
        return self.checksum

    def __init__(self, manager, checksum):
        self.checksum = checksum
        super().__init__(manager)

    async def _run(self):
        """  Gets the buffer from its checksum
- Check for a local checksum-to-buffer cache hit (synchronous)
- Else, check Redis cache (currently synchronous; make it async in a future version)
- Else, await remote checksum-to-buffer cache
- Else, if the checksum has provenance, the buffer may be obtained by launching a transformation.
    However, in this case, the transformation must be local OR it must be ensured that remote
    transformations lead to the result value being available (a misconfig here would lead to a
    infinite loop).
- If successful, add the buffer to local and/or Redis cache (with a tempref or a permanent ref).
- If all fails, raise Exception
"""     
        if self.checksum is None:
            return None
        buffer = checksum_cache.get(self.checksum)
        if buffer is not None:
            return buffer
        # ...
        raise NotImplementedError # livegraph branch

