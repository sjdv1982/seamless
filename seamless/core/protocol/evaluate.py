"""
Caches:
"""

"""
1: (deserialization)
- set of (checksum, celltype) tuples
=> means that the buffer with the checksum can be deserialized for "celltype"
"""
evaluation_cache_1 = set()

"""
2: (reinterpretation)
- set of (checksum, celltype, target_celltype) tuples
=> Means that the value (deserialized from the buffer with the checksum using
celltype) can be re-interpreted, without a change of checksum
For example: "2" (plain) can be interpreted as "2" (int), which have the same checksum.
"""

evaluation_cache_2 = set()

"""
3: (conversion)
- pairs of (checksum, celltype, target_celltype) => converted_checksum
=> Means that the value (deserialized from the buffer with the checksum using
celltype) can be converted to target_celltype , with a change in checksum.
For example: "'2'" (text) can be converted to "2" (int), but this has a different checksum.
"""
evaluation_cache_3 = {}


def needs_buffer_evaluation(checksum, celltype, target_celltype):
    if celltype == target_celltype:
        return False
    if (checksum, celltype) not in evaluation_cache_1:
        # TODO: promotion
        # e.g. a buffer that correctly evaluates as plain, will also compute to mixed
        return True
    if (celltype, target_celltype) in conversion_equivalent:
        celltype, target_celltype = conversion_equivalent[celltype, target_celltype]
    if (celltype, target_celltype) in conversion_trivial:
        return False
    key = (checksum, celltype, target_celltype)
    if (celltype, target_celltype) in conversion_reinterpret:
        return key not in evaluation_cache_2 
    elif (celltype, target_celltype) in conversion_reformat:
        return key not in evaluation_cache_3
    elif (celltype, target_celltype) in conversion_possible:
        return key not in evaluation_cache_3
    elif (celltype, target_celltype) in conversion_forbidden:
        raise TypeError((celltype, target_celltype))
    else:
        raise TypeError((celltype, target_celltype)) # should never happen

async def evaluate_from_checksum(checksum, celltype, target_celltype):
    if celltype == target_celltype:
        return checksum
    assert (checksum, celltype) in evaluation_cache_1
    if (celltype, target_celltype) in conversion_equivalent:
        celltype, target_celltype = conversion_equivalent[celltype, target_celltype]
    if (celltype, target_celltype) in conversion_trivial:
        return checksum

    key = (checksum, celltype, target_celltype)
    if (celltype, target_celltype) in conversion_reinterpret:
        assert key in evaluation_cache_2
        return checksum
    elif (celltype, target_celltype) in conversion_reformat:
        return evaluation_cache_3[key]
    elif (celltype, target_celltype) in conversion_possible:
        return evaluation_cache_3[key]
    elif (celltype, target_celltype) in conversion_forbidden:
        raise TypeError((celltype, target_celltype))
    else:
        raise TypeError((celltype, target_celltype)) # should never happen

async def evaluate_from_buffer(checksum, buffer, celltype, target_celltype, buffer_cache):
    if (celltype, target_celltype) in conversion_equivalent:
        celltype, target_celltype = conversion_equivalent[celltype, target_celltype]
    if celltype == target_celltype:
        return checksum
    if (celltype, target_celltype) in conversion_trivial:
        return checksum

    key = (checksum, celltype, target_celltype)
    if (celltype, target_celltype) in conversion_reinterpret:        
        await reinterpret(checksum, buffer, celltype, target_celltype)
        evaluation_cache_2.add(key)
        return checksum
    elif (celltype, target_celltype) in conversion_reformat:
        result = await reformat(checksum, buffer, celltype, target_celltype)
        evaluation_cache_3[key] = result
        return result
    elif (celltype, target_celltype) in conversion_possible:
        result = await convert(checksum, buffer, celltype, target_celltype)
        evaluation_cache_3[key] = result
        return result
    elif (celltype, target_celltype) in conversion_forbidden:
        raise TypeError((celltype, target_celltype))
    else:
        raise TypeError((celltype, target_celltype)) # should never happen

from .conversion import (
    conversion_trivial, 
    conversion_reformat,
    conversion_reinterpret,
    conversion_possible,
    conversion_equivalent,
    conversion_forbidden,
    reinterpret,
    reformat,
    convert
)    
