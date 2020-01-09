from ...mixed import _array_types
def _set_subpath(value, path, subvalue):
    head = path[0]
    if len(path) == 1:
        if isinstance(value, list) and head >= len(value):
            value.insert(head, subvalue)
        elif isinstance(value, list) and \
          subvalue is None and len(value) == head + 1:
            value.pop(-1)
        else:
            value[head] = subvalue
        return
    if head not in value:
        head2 = path[1]
        if isinstance(head2, int):
            item = []
        elif isinstance(head2, str):
            item = {}
        if isinstance(value, list):
            value.insert(head, item)
        else:
            value[head] = item
    sub_curr_value = value[head]
    _set_subpath(sub_curr_value, path[1:], subvalue)

def _get_subpath(value, path):
    if value is None:
        return None
    if not len(path):
        return value
    head = path[0]
    if isinstance(value, _array_types):
        if head >= len(value):
            sub_curr_value = None
        else:
            sub_curr_value = value[head]
    else:
        sub_curr_value = value.get(head)
    if sub_curr_value is None:
        return None
    return _get_subpath(sub_curr_value, path[1:])

def get_subpath_sync(value, hash_pattern, path):
    """This function can be executed if the asyncio event loop is already running"""
    if hash_pattern is None:
        return _get_subpath(value, path)
    deep_structure = value
    result, post_path = access_deep_structure(
        deep_structure, hash_pattern, path
    )
    if post_path is None:
        if result is None:
            return None
        elif isinstance(result, str):            
            checksum = bytes.fromhex(result)
            buffer = get_buffer_sync(checksum, buffer_cache)
            value = deserialize_sync(buffer, checksum, "mixed", copy=True)
            return value
        else:
            sub_structure, sub_hash_pattern = result
            checksums = deep_structure_to_checksums(
               sub_structure, sub_hash_pattern
            )
            buffer_dict = {}
            for checksum in checksums:
                cs = checksum
                if checksum is not None:
                    cs = bytes.fromhex(checksum)
                buffer = get_buffer_sync(cs, buffer_cache)
                buffer_dict[checksum] = buffer
            value = deep_structure_to_value_sync(
                sub_structure, sub_hash_pattern,
                buffer_dict, copy=True
            )
            return value
    else:
        checksum = bytes.fromhex(result)
        buffer = get_buffer_sync(checksum, buffer_cache)
        value = deserialize_sync(buffer, checksum, "mixed", copy=True)
        return _get_subpath(value, post_path)

async def get_subpath(value, hash_pattern, path):
    if hash_pattern is None:
        return ("value", _get_subpath(value, path))
    deep_structure = value
    result, post_path = access_deep_structure(
        deep_structure, hash_pattern, path
    )
    if post_path is None:
        if result is None:
            return "value", None
        elif isinstance(result, str):            
            checksum = bytes.fromhex(result)
            return ("checksum", checksum)
            #buffer = await get_buffer(checksum, buffer_cache)
            #value = await deserialize(buffer, checksum, "mixed", copy=True)
            #return value
        else:
            sub_structure, sub_hash_pattern = result
            checksums = deep_structure_to_checksums(
               sub_structure, sub_hash_pattern
            )
            buffer_dict = {}
            for checksum in checksums: # TODO: optimize by running in parallel
                cs = checksum
                if checksum is not None:
                    cs = bytes.fromhex(checksum)
                buffer = await get_buffer(cs, buffer_cache)  
                buffer_dict[checksum] = buffer
            value = await deep_structure_to_value(
                sub_structure, sub_hash_pattern,
                buffer_dict, copy=True
            )
            return ("value", value)
    else:
        checksum = bytes.fromhex(result)
        buffer = await get_buffer(checksum, buffer_cache)
        value = await deserialize(buffer, checksum, "mixed", copy=True)
        value = _get_subpath(value, post_path)
        return ("value", value) 

def set_subpath_sync(value, hash_pattern, path, subvalue):
    """This function can be executed if the asyncio event loop is already running"""
    if hash_pattern is None:
        _set_subpath(value, path, subvalue)
        return
    deep_structure = value
    if value is None:
        cs = None
    else:
        buffer = serialize_sync(subvalue, "mixed")
        checksum = calculate_checksum_sync(buffer)
        cs = checksum.hex()
    result = write_deep_structure(
        cs, deep_structure, hash_pattern, path
    )
    mode = result[0]
    if mode == 0:
        _, old_checksum = result
        if checksum is not None:
            buffer_cache.cache_buffer(checksum, buffer)
            buffer_cache.incref(checksum)
        if old_checksum is not None:
            buffer_cache.decref(bytes.fromhex(old_checksum))
    elif mode == 1:
        _, sub_hash_pattern = result
        sub_structure, _ = value_to_deep_structure_sync(
            subvalue, sub_hash_pattern
        )
        if not len(path):
            if isinstance(deep_structure, list):
                deep_structure[:] = sub_structure
            elif isinstance(deep_structure, dict):
                deep_structure.clear()
                deep_structure.update(sub_structure)
        else:            
            old_sub_structure = set_deep_structure(
                sub_structure, deep_structure, sub_hash_pattern, path
            )

    elif mode == 2:
        _, pre_path, curr_sub_checksum, post_path = result
        
        curr_sub_value = None
        if len(post_path):
            if curr_sub_checksum is not None:
                curr_sub_checksum = bytes.fromhex(curr_sub_checksum)
                curr_sub_buffer = get_buffer_sync(curr_sub_checksum, buffer_cache)
                curr_sub_value = deserialize_sync(
                    curr_sub_buffer, curr_sub_checksum, "mixed", copy=True
                )
            _set_subpath(curr_sub_value, post_path, subvalue)
            new_sub_value = curr_sub_value
        else:
            new_sub_value = subvalue

        new_sub_cs = None
        if new_sub_value is not None:
            new_sub_buffer = serialize_sync(
                new_sub_value, "mixed", use_cache=(len(post_path) == 0)
            )
            new_sub_checksum = calculate_checksum_sync(new_sub_buffer)
            buffer_cache.cache_buffer(new_sub_checksum, new_sub_buffer)
            new_sub_cs = new_sub_checksum.hex()

        result = write_deep_structure(
            new_sub_cs, deep_structure, hash_pattern, pre_path,
            create=True
        )
        assert result[0] == 0, result
        if new_sub_checksum is not None:
            buffer_cache.incref(new_sub_checksum)
        if curr_sub_checksum is not None:
            buffer_cache.decref(curr_sub_checksum)
    else:
        raise ValueError(result)
            

async def set_subpath(value, hash_pattern, path, subvalue):
    if hash_pattern is None:
        _set_subpath(value, path, subvalue)
        return    
    deep_structure = value
    if value is None:
        cs = None
    else:
        buffer = await serialize(subvalue, "mixed")
        checksum = await calculate_checksum(buffer)
        cs = checksum.hex()
    result = write_deep_structure(
        cs, deep_structure, hash_pattern, path
    )
    mode = result[0]
    if mode == 0:
        _, old_checksum = result
        if checksum is not None:
            buffer_cache.cache_buffer(checksum, buffer)
            buffer_cache.incref(checksum)
        if old_checksum is not None:
            buffer_cache.decref(bytes.fromhex(old_checksum))
    elif mode == 1:
        _, sub_hash_pattern = result
        sub_structure, _ = await value_to_deep_structure(
            subvalue, sub_hash_pattern
        )
        if not len(path):
            if isinstance(deep_structure, list):
                deep_structure[:] = sub_structure
            elif isinstance(deep_structure, dict):
                deep_structure.clear()
                deep_structure.update(sub_structure)
        else:            
            old_sub_structure = set_deep_structure(
                sub_structure, deep_structure, sub_hash_pattern, path
            )

    elif mode == 2:
        _, pre_path, curr_sub_checksum, post_path = result
        
        curr_sub_value = None
        if len(post_path):
            if curr_sub_checksum is not None:
                curr_sub_checksum = bytes.fromhex(curr_sub_checksum)
                curr_sub_buffer = await get_buffer(curr_sub_checksum, buffer_cache)
                curr_sub_value = await deserialize(
                    curr_sub_buffer, curr_sub_checksum, "mixed", copy=True
                )
            _set_subpath(curr_sub_value, post_path, subvalue)
            new_sub_value = curr_sub_value
        else:
            new_sub_value = subvalue

        new_sub_cs = None
        if new_sub_value is not None:
            new_sub_buffer = await serialize(
                new_sub_value, "mixed", use_cache=(len(post_path) == 0)
            )
            new_sub_checksum = await calculate_checksum(new_sub_buffer)
            buffer_cache.cache_buffer(new_sub_checksum, new_sub_buffer)
            new_sub_cs = new_sub_checksum.hex()

        result = write_deep_structure(
            new_sub_cs, deep_structure, hash_pattern, pre_path,
            create=True
        )
        assert result[0] == 0, result
        if new_sub_checksum is not None:
            buffer_cache.incref(new_sub_checksum)
        if curr_sub_checksum is not None:
            buffer_cache.decref(curr_sub_checksum)
    else:
        raise ValueError(result)


from .deep_structure import (
    write_deep_structure, set_deep_structure, 
    value_to_deep_structure, value_to_deep_structure_sync,
    deep_structure_to_value, deep_structure_to_value_sync,
    deep_structure_to_checksums, access_deep_structure
)    
from ..cache.buffer_cache import buffer_cache
from .calculate_checksum import calculate_checksum, calculate_checksum_sync
from .deserialize import deserialize_sync
from .serialize import serialize, serialize_sync
from .get_buffer import get_buffer, get_buffer_sync