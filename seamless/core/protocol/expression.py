def _set_subpath(value, path, subvalue):
    head = path[0]
    if len(path) == 1:
        value[head] = subvalue
        return
    if head not in value:
        head2 = path[1]
        if isinstance(head2, int):
            value[head] = []
        elif isinstance(head2, str):
            value[head] = {}
    sub_curr_value = value[head]
    _set_subpath(sub_curr_value, path[1:], subvalue)

def _get_subpath(value, path):
    if value is None:
        return None
    if not len(path):
        return value
    head = path[0]
    sub_curr_value = value[head]
    return _get_subpath(sub_curr_value, path[1:])

def get_subpath_sync(value, hash_pattern, path):
    if hash_pattern is None:
        return _get_subpath(value, path)
    deep_structure = value
    result, post_path = access_deep_structure(
        deep_structure, hash_pattern, path
    )
    if remaining_path is None:
        if isinstance(result, bytes):
            checksum = result
            value = get_buffer_sync(checksum)
            return value
        else:
            sub_structure, sub_hash_pattern = result
            raise NotImplementedError # buffer dict...
            value = deep_structure_to_value_sync(
                sub_structure, sub_hash_pattern,
                buffer_dict, copy=True
            )
    else:
        raise NotImplementedError
    

def set_subpath_sync(value, hash_pattern, path, subvalue):
    if hash_pattern is None:
        _set_subpath(value, path, subvalue)
        return
    deep_structure = value
    buffer = serialize_sync(subvalue, "mixed")
    checksum = calculate_checksum_sync(buffer)
    result = write_deep_structure(
        checksum, deep_structure, hash_pattern, path
    )
    mode = result[0]
    if mode == 0:
        _, old_checksum = result
        buffer_cache.cache_buffer(checksum, buffer)
        buffer_cache.incref(checksum)
        buffer_cache.decref(old_checksum)
    elif mode == 1:
        _, sub_hash_pattern = result
        sub_structure, new_checksums = value_to_deep_structure_sync(
            value, sub_hash_pattern
        )
        old_sub_structure = set_deep_structure(
            sub_structure, deep_structure, sub_hash_pattern, path
        )
        old_checksums = deep_structure_to_checksums(
            old_sub_structure, sub_hash_pattern
        )

        for new_checksum in new_checksums:
            buffer_cache.incref(new_checksum)
        for old_checksum in old_checksums:
            buffer_cache.decref(old_checksum)
    elif mode == 2:
        _, pre_path, curr_sub_checksum, post_path = result
        
        new_sub_value = _get_subpath(subvalue, post_path)        
        new_sub_buffer = serialize_sync(new_subvalue, "mixed")
        new_sub_checksum = calculate_checksum_sync(new_sub_buffer)
        buffer_cache.cache_buffer(new_sub_checksum, new_sub_buffer)

        result = write_deep_structure(
            new_sub_checksum, deep_structure, hash_pattern, pre_path
        )
        assert result == 0, curr_sub_checksum
        buffer_cache.incref(new_sub_checksum)
        buffer_cache.decref(curr_sub_checksum)
    else:
        raise ValueError(result)
            
            

from .deep_structure import (
    write_deep_structure, set_deep_structure, value_to_deep_structure_sync,
    deep_structure_to_value_sync,
    deep_structure_to_checksums
)    
from ..cache import buffer_cache
from .calculate_checksum import calculate_checksum_sync
from .deserialize import deserialize_sync
from .serialize import serialize_sync
from .get_buffer import get_buffer_sync