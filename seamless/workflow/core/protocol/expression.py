from seamless import Checksum, CacheMissError
from seamless.checksum.cached_calculate_checksum import (
    cached_calculate_checksum,
    cached_calculate_checksum_sync,
)


from seamless.checksum.deserialize import deserialize, deserialize_sync
from seamless.checksum.serialize import serialize, serialize_sync

from seamless.checksum.get_buffer import get_buffer
from seamless.checksum.buffer_cache import buffer_cache


from .deep_structure import (
    deserialize_raw,
    serialize_raw,
    serialize_raw_async,
    write_deep_structure,
    set_deep_structure,
    value_to_deep_structure,
    value_to_deep_structure_sync,
    deep_structure_to_value,
    deep_structure_to_value_sync,
    deep_structure_to_checksums,
    access_deep_structure,
)


def _set_subpath(value, path, subvalue):
    head = path[0]
    if len(path) == 1:
        if isinstance(value, list) and head >= len(value):
            value.insert(head, subvalue)
        elif isinstance(value, list) and subvalue is None and len(value) == head + 1:
            value.pop(-1)
        elif isinstance(value, dict) and subvalue is None:
            value.pop(path[0])
        else:
            value[head] = subvalue
        return
    if isinstance(value, dict):
        in_value = head in value
    elif isinstance(value, list):
        in_value = len(value) > head
    else:
        raise TypeError(value)
    if not in_value:
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
    from silk.mixed import _array_types

    head = path[0]
    if isinstance(value, _array_types):
        if not isinstance(head, int):
            sub_curr_value = None
        elif head >= len(value):
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
    result, post_path = access_deep_structure(deep_structure, hash_pattern, path)
    if post_path is None:
        if result is None:
            return None
        elif isinstance(result, (str, Checksum)):
            checksum = Checksum(result)
            deep = hash_pattern is not None
            buffer = get_buffer(checksum, remote=True, deep=deep)
            if hash_pattern == {"*": "##"} and len(path) == 1:
                value = deserialize_raw(buffer)
            else:
                value = deserialize_sync(buffer, checksum, "mixed", copy=True)
            return value
        else:
            sub_structure, sub_hash_pattern = result
            checksums = deep_structure_to_checksums(sub_structure, sub_hash_pattern)
            buffer_dict = {}
            for checksum in checksums:
                checksum = Checksum(checksum)
                if not checksum:
                    continue
                buffer = get_buffer(checksum, remote=True, deep=False)
                if buffer is None:
                    raise CacheMissError(checksum)
                buffer_dict[checksum] = buffer
            value = deep_structure_to_value_sync(
                sub_structure, sub_hash_pattern, buffer_dict, copy=True
            )
            return value
    else:
        checksum = Checksum(result)
        buffer = get_buffer(checksum, remote=True, deep=False)
        value = deserialize_sync(buffer, checksum, "mixed", copy=True)
        return _get_subpath(value, post_path)


async def get_subpath(
    value, hash_pattern, path, *, manager=None, perform_fingertip=False
):
    if perform_fingertip:
        assert manager is not None
    if hash_pattern is None:
        return ("value", _get_subpath(value, path))
    deep_structure = value
    result, post_path = access_deep_structure(deep_structure, hash_pattern, path)
    if post_path is None:
        if result is None:
            return "value", None
        elif isinstance(result, (str, Checksum)):
            checksum = Checksum(result)
            return ("checksum", checksum)
        else:
            sub_structure, sub_hash_pattern = result
            checksums = deep_structure_to_checksums(sub_structure, sub_hash_pattern)
            buffer_dict = {}
            for checksum in checksums:  # TODO: optimize by running in parallel
                checksum = Checksum(checksum)
                if not checksum:
                    continue
                if perform_fingertip:
                    buffer = await manager.cachemanager.fingertip(checksum)
                else:
                    buffer = get_buffer(checksum, remote=True, deep=False)
                if buffer is None:
                    raise CacheMissError(checksum)
                buffer_dict[checksum] = buffer
            value = await deep_structure_to_value(
                sub_structure, sub_hash_pattern, buffer_dict, copy=True
            )
            return ("value", value)
    else:
        checksum = Checksum(result)
        if perform_fingertip:
            buffer = await manager.cachemanager.fingertip(checksum)
        else:
            buffer = get_buffer(checksum, remote=True, deep=False)
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
        if hash_pattern == {"*": "##"}:
            buffer = serialize_raw(subvalue)
        else:
            buffer = serialize_sync(subvalue, "mixed")
        checksum = cached_calculate_checksum_sync(buffer)
        buffer_cache.cache_buffer(checksum, buffer)
        cs = checksum.hex()
    result = write_deep_structure(cs, deep_structure, hash_pattern, path)
    mode = result[0]
    if mode == 0:
        pass
    elif mode == 1:
        _, sub_hash_pattern = result
        sub_structure, _ = value_to_deep_structure_sync(subvalue, sub_hash_pattern)
        if not len(path):
            if isinstance(deep_structure, list):
                deep_structure[:] = sub_structure
            elif isinstance(deep_structure, dict):
                deep_structure.clear()
                deep_structure.update(sub_structure)
        else:
            _old_sub_structure = set_deep_structure(
                sub_structure, deep_structure, sub_hash_pattern, path
            )

    elif mode == 2:
        _, pre_path, curr_sub_checksum, post_path, is_raw = result
        curr_sub_checksum = Checksum(curr_sub_checksum)

        curr_sub_value = None
        if len(post_path):
            if curr_sub_checksum:
                curr_sub_buffer = get_buffer(curr_sub_checksum, remote=True)
                if is_raw:
                    curr_sub_value = deserialize_raw(curr_sub_buffer)
                else:
                    curr_sub_value = deserialize_sync(
                        curr_sub_buffer, curr_sub_checksum, "mixed", copy=True
                    )
            _set_subpath(curr_sub_value, post_path, subvalue)
            new_sub_value = curr_sub_value
        else:
            new_sub_value = subvalue

        new_sub_cs = None
        if new_sub_value is not None:
            if hash_pattern == {"*": "##"}:
                new_sub_buffer = serialize_raw(new_sub_value)
            else:
                new_sub_buffer = serialize_sync(
                    new_sub_value, "mixed", use_cache=(len(post_path) == 0)
                )
            new_sub_checksum = cached_calculate_checksum_sync(new_sub_buffer)
            buffer_cache.cache_buffer(new_sub_checksum, new_sub_buffer)
            new_sub_cs = new_sub_checksum.hex()

        result = write_deep_structure(
            new_sub_cs, deep_structure, hash_pattern, pre_path
        )
        assert result[0] == 0, result
    else:
        raise ValueError(result)


async def set_subpath_checksum(
    value, hash_pattern, path, subchecksum: Checksum, sub_buffer
):
    """Sets the subpath of a mixed cell by its subchecksum
    subchecksum must already be encoded with the correct sub-hash-pattern
    sub_buffer corresponds to the buffer of subchecksum
    If the path has the same depth as the hash pattern, then sub_buffer may be None
    """
    subchecksum = Checksum(subchecksum)
    if hash_pattern is None or hash_pattern == "#" or hash_pattern == "##":
        if subchecksum:
            assert sub_buffer is not None
        if hash_pattern == "##":
            subvalue = deserialize_raw(sub_buffer)
        else:
            subvalue = await deserialize(sub_buffer, subchecksum, "mixed", copy=True)
        _set_subpath(value, path, subvalue)
        return
    deep_structure = value
    result = write_deep_structure(subchecksum, deep_structure, hash_pattern, path)
    mode = result[0]
    if mode == 0:
        pass
    elif mode == 1:
        _, sub_hash_pattern = result
        if subchecksum:
            assert sub_buffer is not None
        sub_structure = await deserialize(sub_buffer, subchecksum, "mixed", copy=True)
        if not len(path):
            if isinstance(deep_structure, list):
                deep_structure[:] = sub_structure
            elif isinstance(deep_structure, dict):
                deep_structure.clear()
                deep_structure.update(sub_structure)
        else:
            set_deep_structure(sub_structure, deep_structure, sub_hash_pattern, path)
    elif mode == 2:
        new_sub_cs = (
            subchecksum  # subchecksum is already in correct hash pattern encoding
        )
        _, pre_path, _, _ = result
        result = write_deep_structure(
            new_sub_cs, deep_structure, hash_pattern, pre_path
        )
        assert result[0] == 0, result
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
        if hash_pattern == {"*": "##"}:
            buffer = serialize_raw(subvalue)
        else:
            buffer = await serialize(subvalue, "mixed")
        checksum = await cached_calculate_checksum(buffer)
        buffer_cache.cache_buffer(checksum, buffer)
        cs = checksum.hex()
    result = write_deep_structure(cs, deep_structure, hash_pattern, path)
    mode = result[0]
    if mode == 0:
        pass
    elif mode == 1:
        _, sub_hash_pattern = result
        sub_structure, _ = await value_to_deep_structure(subvalue, sub_hash_pattern)
        if not len(path):
            if isinstance(deep_structure, list):
                deep_structure[:] = sub_structure
            elif isinstance(deep_structure, dict):
                deep_structure.clear()
                deep_structure.update(sub_structure)
        else:
            _old_sub_structure = set_deep_structure(
                sub_structure, deep_structure, sub_hash_pattern, path
            )

    elif mode == 2:
        _, pre_path, curr_sub_checksum, post_path, is_raw = result

        curr_sub_checksum = Checksum(curr_sub_checksum)
        curr_sub_value = None
        assert len(post_path)
        if curr_sub_checksum:
            curr_sub_buffer = get_buffer(curr_sub_checksum, remote=True)
            if is_raw:
                curr_sub_value = deserialize_raw(curr_sub_buffer)
            else:
                curr_sub_value = await deserialize(
                    curr_sub_buffer, curr_sub_checksum, "mixed", copy=True
                )
        _set_subpath(curr_sub_value, post_path, subvalue)
        new_sub_value = curr_sub_value
        new_sub_cs = None
        if new_sub_value is not None:
            if is_raw:
                new_sub_buffer = await serialize_raw_async(
                    new_sub_value, use_cache=False
                )
            else:
                new_sub_buffer = await serialize(
                    new_sub_value, "mixed", use_cache=False
                )
            new_sub_checksum = await cached_calculate_checksum(new_sub_buffer)
            buffer_cache.cache_buffer(new_sub_checksum, new_sub_buffer)
            # Don't write buffer_info for sub buffers, that would be too much...
            ## buffer_cache.guarantee_buffer_info(new_sub_checksum, "mixed", sync_to_remote=False)
            new_sub_cs = new_sub_checksum.hex()

        result = write_deep_structure(
            new_sub_cs, deep_structure, hash_pattern, pre_path
        )
        assert result[0] == 0, result
    else:
        raise ValueError(result)
