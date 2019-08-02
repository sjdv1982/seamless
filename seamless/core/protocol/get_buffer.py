async def get_buffer_async(checksum, buffer_cache):
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

        buffer = checksum_cache.get(checksum)
        if buffer is not None:
            return buffer
        buffer = buffer_cache.get_buffer(checksum)
        if buffer is not None:
            return buffer
        # TODO: remote # livegraph branch
        # TODO: provenance # livegraph branch
        raise CacheMissError(checksum)

from .calculate_checksum import checksum_cache
from ..cache import CacheMissError