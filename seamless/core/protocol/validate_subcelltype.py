"""
- sets of (checksum, celltype, subcelltype)
Means that the value (deserialized from the buffer with the checksum using
  celltype) validates against subcelltype.
Meaningful values of (celltype, subcelltype):
("python", "transformer"/"reactor"/"macro").
"""

validation_cache = set()

async def validate_subcelltype(checksum, celltype, subcelltype, value_cache):
    if subcelltype is None:
        return
    if celltype != "python":
        return
    key = (checksum, celltype, subcelltype)
    if key in validation_cache:
        return
    buffer = await get_buffer_async(checksum, value_cache)
    #...
    raise NotImplementedError #livegraph branch
    validation_cache.add(key)
    
from .get_buffer import get_buffer_async