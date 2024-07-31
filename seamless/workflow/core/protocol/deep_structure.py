import asyncio
from copy import deepcopy
import numpy as np
from io import BytesIO
from silk.mixed import MAGIC_NUMPY, MAGIC_SEAMLESS_MIXED
from seamless import Checksum

class DeepStructureError(ValueError):
    def __str__(self):
        val = str(self.args[1])
        if len(val) > 300:
            val = val[:220] + "..." + val[-50:]
        return """
  Invalid deep structure: %s
  Hash pattern: %s""" % (val, self.args[0])

_supported_hash_patterns = "#", {"*": "#"}, {"!": "#"}, "##", {"*": "##"}
def validate_hash_pattern(hash_pattern):
    assert hash_pattern is not None
    ###  To support complicated hash patterns, code must be changed in other places as well
    ###  In particular: the Expression class and Accessor update tasks    
    if hash_pattern not in _supported_hash_patterns:
        err = """For now, Seamless supports only the following hash patterns:

  {}

Hash pattern {} is not supported.
"""
        sup = "\n  ".join([str(p) for p in _supported_hash_patterns])
        raise NotImplementedError(err.format(sup, hash_pattern))
    ###

    if isinstance(hash_pattern, str):
        return
    for key, value in hash_pattern.items():
        if not isinstance(key, str):
            raise TypeError((key, type(key)))
        validate_hash_pattern(value)

def validate_deep_structure(deep_structure, hash_pattern):
    try:
        assert hash_pattern is not None
        validate_hash_pattern(hash_pattern)
        if deep_structure is None:
            return
        if hash_pattern in ("#", "##"):
            try:
                bytes.fromhex(deep_structure)
            except:
                raise AssertionError from None
            return
        assert isinstance(hash_pattern, dict)
        single_key = len(hash_pattern)
        has_star = "*" in hash_pattern
        if not single_key:
            assert isinstance(deep_structure, dict)
            for key in hash_pattern:
                assert not key.startswith("!")
            for key in deep_structure:
                assert not key.startswith("!")
                if key in hash_pattern:
                    validate_deep_structure(deep_structure[key], hash_pattern[key])
                else:
                    assert has_star
                    validate_deep_structure(deep_structure[key], hash_pattern["*"])
        else:
            key = list(hash_pattern.keys())[0]
            if has_star:
                assert isinstance(deep_structure, dict)
                for key2 in deep_structure:
                    validate_deep_structure(deep_structure[key2], hash_pattern["*"])
            elif key == "!":
                assert isinstance(deep_structure, list)
                sub_hash_pattern = hash_pattern[key]
                for sub_deep_structure in deep_structure:
                    validate_deep_structure(sub_deep_structure, sub_hash_pattern)
            elif key.startswith("!"):
                assert key[1:].isnumeric()
                step = int(key[1:])
                assert isinstance(deep_structure, list)
                assert hash_pattern[key] == "#"
            else:
                assert isinstance(deep_structure, dict)
                assert list(deep_structure.keys()) == [key]
                validate_deep_structure(deep_structure[key], hash_pattern[key])
    except AssertionError:
        raise DeepStructureError(hash_pattern, deep_structure) from None

def access_hash_pattern(hash_pattern, path):
    """Access a hash pattern using path, returning the sub-hash pattern"""
    
    ###  To support complicated hash patterns, code must be changed in other places as well
    ###  In particular: the Expression class and Accessor update tasks
    ###
    if hash_pattern is None:
        if path is None or not len(path):
            return hash_pattern
        return None

    validate_hash_pattern(hash_pattern)
    if path is None or not len(path):
        return hash_pattern
    if len(path) == 1:
        if hash_pattern in ("#", "##"):
            return None
        else:
            if "!" in hash_pattern:
                return access_hash_pattern(hash_pattern["!"], ())
            else:
                return access_hash_pattern(hash_pattern["*"], ())
    else:
        return None
    ###


def access_deep_structure(deep_structure, hash_pattern, path):
    """Access a deep structure using path, returning result and remaining path

    If path and deep structure are equally deep, the result is a checksum,
     and the remaining path is None
    If the structure is deeper than path, the result is a tuple of
    deep sub-structure and sub-hashpattern,
     and the remaining path is None
    If the path is deeper than the structure, the result is a checksum,
     and the remaining path is what could not be accessed
    """
    assert hash_pattern is not None
    validate_deep_structure(deep_structure, hash_pattern)
    if deep_structure is None:
        return None, None

    if path is not None and not len(path):
        path = None
    if hash_pattern in ("#", "##"):
        result = deep_structure
    elif path is None:
        result = deep_structure, hash_pattern
    else:
        assert isinstance(path, tuple)
        attribute = path[0]
        single_key = len(hash_pattern)
        has_star = "*" in hash_pattern
        if not single_key:
            assert isinstance(attribute, str)
            sub_deep_structure = deep_structure.get(attribute)
            if attribute in hash_pattern:
                sub_hash_pattern = hash_pattern[attribute]
            else:
                assert has_star, (path, list(deep_structure.keys()))
                sub_hash_pattern = hash_pattern["*"]
            return access_deep_structure(sub_deep_structure, sub_hash_pattern, path[1:])
        else:
            key = list(hash_pattern.keys())[0]
            if has_star:
                assert isinstance(attribute, str)
                sub_deep_structure = deep_structure.get(attribute)
                sub_hash_pattern = hash_pattern["*"]
                return access_deep_structure(sub_deep_structure, sub_hash_pattern, path[1:])
            elif key == "!":
                assert isinstance(attribute, int)
                if attribute >= len(deep_structure):
                    return None, None
                sub_deep_structure = deep_structure[attribute]
                sub_hash_pattern = hash_pattern[key]
                return access_deep_structure(sub_deep_structure, sub_hash_pattern, path[1:])
            elif key.startswith("!"):
                assert isinstance(attribute, int)
                step = int(key[1:])
                chunk = int(attribute / step)
                remainder = attribute % step
                result = deep_structure[chunk]
                path = None
                if result is not None:
                    path = remainder
            else:
                sub_deep_structure = deep_structure[attribute]
                sub_hash_pattern = hash_pattern[attribute]
                return access_deep_structure(sub_deep_structure, sub_hash_pattern, path[1:])
    return result, path


def _deep_structure_to_checksums(deep_structure, hash_pattern, checksums, with_raw):
    if deep_structure is None:
        return
    if hash_pattern in ("#", "##"):
        checksum = deep_structure
        if with_raw:
            raw = (hash_pattern == "##")
            checksums.add((checksum, raw))
        else:
            checksums.add(checksum)
        return
    single_key = len(hash_pattern)
    has_star = "*" in hash_pattern
    if has_star or not single_key:
        for key in deep_structure:
            if key in hash_pattern:
                sub_hash_pattern = hash_pattern[key]
            else:
                sub_hash_pattern = hash_pattern["*"]
            _deep_structure_to_checksums(
                deep_structure[key], sub_hash_pattern, checksums,
                with_raw
            )
    else:
        for key in hash_pattern:
            if key.startswith("!"):
                sub_hash_pattern = hash_pattern[key]
                for sub_deep_structure in deep_structure:
                    _deep_structure_to_checksums(
                        sub_deep_structure, sub_hash_pattern, checksums,
                        with_raw
                    )
            else:
                assert list(deep_structure.keys()) == [key]
                _deep_structure_to_checksums(
                    deep_structure[key], hash_pattern[key], checksums,
                    with_raw
                )

def deep_structure_to_checksums(deep_structure, hash_pattern, with_raw=False):
    """Collects all checksums that are being referenced in a deep structure"""    
    from seamless import fair
    validate_deep_structure(deep_structure, hash_pattern)
    checksums = set()
    _deep_structure_to_checksums(deep_structure, hash_pattern, checksums, with_raw)
    if hash_pattern in ({"*": "#"}, {"*": "#"}):
        classification = "mixed_item"
    elif hash_pattern in ({"*": "##"}, {"*": "##"}):
        classification = "bytes_item"
    else:
        classification = None
    if classification is not None:
        for checksum0 in checksums:
            if with_raw:
                checksum, _  = checksum0
            else:
                checksum = checksum0
            fair._classify(checksum, classification)
    return checksums

def _deep_structure_to_value(deep_structure, hash_pattern, value_dict, copy):
    """ build value from deep structure, using value_dict
    if copy is True, use deepcopies from the value dict, else just refer to the items
    """

    #if isinstance(hash_pattern, dict): raise Exception ### useful for debugging, to find out when a whole deep structure is converted to a value

    if deep_structure is None:
        return None

    if hash_pattern in ("#", "##"):
        checksum = deep_structure
        value = value_dict[checksum]
        if copy:
            value = deepcopy(value)
        return value
    single_key = len(hash_pattern)
    has_star = "*" in hash_pattern
    if has_star or not single_key:
        result = {}
        for key in deep_structure:
            if key in hash_pattern:
                sub_hash_pattern = hash_pattern[key]
            else:
                sub_hash_pattern = hash_pattern["*"]
            sub_result = _deep_structure_to_value(
                deep_structure[key], sub_hash_pattern,
                value_dict, copy=copy
            )
            result[key] = sub_result
    else:
        for key in hash_pattern:
            if key.startswith("!"):
                result = []
                sub_hash_pattern = hash_pattern[key]
                for sub_deep_structure in deep_structure:
                    sub_result = _deep_structure_to_value(
                        sub_deep_structure, sub_hash_pattern,
                        value_dict, copy=copy
                    )
                    result.append(sub_result)
            else:
                assert list(deep_structure.keys()) == [key]
                sub_result = _deep_structure_to_value(
                    deep_structure[key], sub_hash_pattern,
                    value_dict, copy=copy
                )
                result = {key: sub_result}
    return result

def deserialize_raw(buffer):
    if buffer.startswith(MAGIC_SEAMLESS_MIXED):                                    
        return np.array(buffer)
    if buffer.startswith(MAGIC_NUMPY):
        # From silk.mixed.io.from_stream
        b = BytesIO(buffer)
        arr0 = np.load(b, allow_pickle=False)
        if arr0.ndim == 0 and arr0.dtype.char != "S":
            arr = np.frombuffer(arr0,arr0.dtype)
            return arr[0]
        else:
            return arr0
    try:
        return buffer.decode()
    except UnicodeDecodeError:
        return buffer

async def _deserialize_raw_async(buffer):
    return deserialize_raw(buffer)

def serialize_raw(value, use_cache=True):
    if isinstance(value, np.ndarray) and value.dtype.char == "S":
        return value.tobytes()
    elif isinstance(value, bytes):
        return value
    elif isinstance(value, str):
        return serialize_sync(value, "text", use_cache=use_cache)
    else:
        return serialize_sync(value, "mixed", use_cache=use_cache)

async def serialize_raw_async(value, use_cache=True):
    if isinstance(value, np.ndarray) and value.dtype.char == "S":
        return value.tobytes()
    elif isinstance(value, bytes):
        return value
    elif isinstance(value, str):
        return await serialize(value, "text", use_cache=use_cache)
    else:
        return await serialize(value, "mixed", use_cache=use_cache)

async def deep_structure_to_value(deep_structure, hash_pattern, buffer_dict, copy):
    """Converts deep structure to a mixed value
    Requires buffer_dict, a checksum-to-buffer cache for all checksums in the deep structure
    Use copy=True for a value that will be modified

    If the deep structure is raw (i.e. uses ##), the buffer
    will be interpreted differently:
    - as text value if UTF-8 decoding is possible.
      The raw buffer can be retrieved with the .encode() method.
    - as binary (Numpy) value otherwise. 
      The raw buffer can be retrieved with the .tobytes() method.
    """
    checksums0 = deep_structure_to_checksums(deep_structure, hash_pattern, with_raw=True)
    futures = {}
    checksums = set()
    for checksum0 in checksums0:
        checksum, is_raw  = checksum0
        checksums.add(checksum)
        assert checksum in buffer_dict
        buf = buffer_dict[checksum]
        if is_raw: 
            coro = _deserialize_raw_async(buf) 
        else:
            coro = deserialize(buf, bytes.fromhex(checksum), "mixed", copy=copy)
        futures[checksum] = asyncio.ensure_future(coro)
    await asyncio.gather(*futures.values())
    value_dict = {checksum:futures[checksum].result() for checksum in checksums}
    return _deep_structure_to_value(deep_structure, hash_pattern, value_dict, copy)


def deep_structure_to_value_sync(deep_structure, hash_pattern, buffer_dict, copy):
    """Converts deep structure to a mixed value
    Requires buffer_dict, a checksum-to-buffer cache for all checksums in the deep structure
    Use copy=True for a value that will be modified

    This function can be executed if the asyncio event loop is already running"""
    if not asyncio.get_event_loop().is_running():
        coro = deep_structure_to_value(
            deep_structure, hash_pattern, buffer_dict, copy
        )
        fut = asyncio.ensure_future(coro)
        asyncio.get_event_loop().run_until_complete(fut)
        return fut.result()

    checksums0 = deep_structure_to_checksums(deep_structure, hash_pattern, with_raw=True)
    value_dict = {}
    for checksum0 in checksums0:
        checksum, is_raw  = checksum0
        assert checksum in buffer_dict
        buf = buffer_dict[checksum]
        if not is_raw: 
            value = deserialize_sync(buf, bytes.fromhex(checksum), "mixed", copy=copy)
        else:
            value = deserialize_raw(buf) 
        value_dict[checksum] = value
    return _deep_structure_to_value(deep_structure, hash_pattern, value_dict, copy)

def _build_deep_structure(hash_pattern, d, c):
    if d is None:
        return None
    if hash_pattern in ("#", "##"):
        obj_id = d
        checksum = c[obj_id]
        return checksum
    single_key = len(hash_pattern)
    has_star = "*" in hash_pattern
    if has_star or not single_key:
        result = {}
        for key in d:
            if key in hash_pattern:
                sub_hash_pattern = hash_pattern[key]
            else:
                sub_hash_pattern = hash_pattern["*"]
            sub_result = _build_deep_structure(
                sub_hash_pattern, d[key],
                c
            )
            result[key] = sub_result
    else:
        for key in hash_pattern:
            if key.startswith("!"):
                result = []
                sub_hash_pattern = hash_pattern[key]
                for sub_d in d:
                    sub_result = _build_deep_structure(
                        sub_hash_pattern, sub_d,
                        c
                    )
                    result.append(sub_result)
            else:
                assert list(d.keys()) == [key]
                sub_result = _deep_structure_to_value(
                    d[key], sub_hash_pattern,
                    c
                )
                result = {key: sub_result}
    return result

def _value_to_objects(value, hash_pattern, objects):
    if value is None:
        return
    if hash_pattern in ("#", "##"):
        obj_id = id(value)
        objects[obj_id] = value
        return obj_id
    single_key = len(hash_pattern)
    has_star = "*" in hash_pattern
    if has_star or not single_key:
        result = {}
        if not isinstance(value, dict):
            raise TypeError(value)
        for key in value:
            if key in hash_pattern:
                sub_hash_pattern = hash_pattern[key]
            else:
                sub_hash_pattern = hash_pattern["*"]
            result[key] = _value_to_objects(
                value[key], sub_hash_pattern, objects
            )
        return result
    else:
        for key in hash_pattern:
            if key.startswith("!"):
                result = []
                sub_hash_pattern = hash_pattern[key]
                assert isinstance(value, (list, np.ndarray)), value
                for sub_value in value:
                    sub_result = _value_to_objects(
                        sub_value, sub_hash_pattern, objects
                    )
                    result.append(sub_result)
                return result
            else:
                assert list(value.keys()) == [key]
                sub_result = _value_to_objects(
                    value[key], hash_pattern[key], objects
                )
                return {key: sub_result}


async def value_to_deep_structure(value, hash_pattern, *, cache_buffers=True, sync_remote_buffer_info=False):
    """build deep structure from value"""
    try:
        objects = {}
        deep_structure0 = _value_to_objects(
            value, hash_pattern, objects
        )
    except (TypeError, ValueError):
        raise DeepStructureError(hash_pattern, value) from None
    obj_id_to_checksum = {}
    new_checksums = set()
    async def conv_obj_id_to_checksum(obj_id, raw):
        obj = objects[obj_id]
        if raw:
            obj_buffer = await serialize_raw_async(obj)
        else:
            obj_buffer = await serialize(obj, "mixed")
        obj_checksum = await cached_calculate_checksum(obj_buffer)
        new_checksums.add(obj_checksum.hex())
        if cache_buffers:
            buffer_cache.cache_buffer(obj_checksum, obj_buffer)
        obj_id_to_checksum[obj_id] = obj_checksum.hex()
        buffer_cache.guarantee_buffer_info(obj_checksum, "mixed", sync_to_remote=sync_remote_buffer_info)

    coros = []
    raw = (hash_pattern == {"*": "##"})
    for obj_id in objects:
        coro = conv_obj_id_to_checksum(obj_id, raw=raw)
        coros.append(coro)
    await asyncio.gather(*coros)
    deep_structure = _build_deep_structure(
        hash_pattern, deep_structure0, obj_id_to_checksum
    )
    return deep_structure, new_checksums

def value_to_deep_structure_sync(value, hash_pattern, *, cache_buffers=True, sync_remote_buffer_info=False):
    """This function can be executed if the asyncio event loop is already running"""

    if not asyncio.get_event_loop().is_running():
        coro = value_to_deep_structure(
            value, hash_pattern,
            cache_buffers=cache_buffers,
            sync_remote_buffer_info=sync_remote_buffer_info
        )
        fut = asyncio.ensure_future(coro)
        asyncio.get_event_loop().run_until_complete(fut)
        return fut.result()

    try:
        objects = {}
        deep_structure0 = _value_to_objects(
            value, hash_pattern, objects
        )
    except (TypeError, ValueError):
        raise DeepStructureError(hash_pattern, value) from None
    obj_id_to_checksum = {}
    new_checksums = set()
    def conv_obj_id_to_checksum(obj_id):
        obj = objects[obj_id]
        obj_buffer = serialize_sync(obj, "mixed")
        obj_checksum = cached_calculate_checksum_sync(obj_buffer)
        new_checksums.add(obj_checksum.hex())
        if cache_buffers:
            buffer_cache.cache_buffer(obj_checksum, obj_buffer)
        buffer_cache.guarantee_buffer_info(obj_checksum, "mixed", sync_to_remote=sync_remote_buffer_info)
        obj_id_to_checksum[obj_id] = obj_checksum.hex()

    for obj_id in objects:
        conv_obj_id_to_checksum(obj_id)
    deep_structure = _build_deep_structure(
        hash_pattern, deep_structure0, obj_id_to_checksum
    )
    return deep_structure, new_checksums


def set_deep_structure(substructure, deep_structure, hash_pattern, path):
    """Writes substructure into deep structure, at the given path

    Returns the old substructure at the given path: the caller is supposed to decref
    all checksums in it"""
    assert len(path)
    attribute = path[0]

    single_key = len(hash_pattern)
    has_star = "*" in hash_pattern
    if not single_key:
        assert isinstance(attribute, str)
        sub_deep_structure = deep_structure.get(attribute)
        if attribute in hash_pattern:
            sub_hash_pattern = hash_pattern[attribute]
        else:
            assert has_star, (path, list(deep_structure.keys()))
            sub_hash_pattern = hash_pattern["*"]
    else:
        key = list(hash_pattern.keys())[0]
        if has_star:
            assert isinstance(attribute, str)
            sub_deep_structure = deep_structure.get(attribute)
            sub_hash_pattern = hash_pattern["*"]
        elif key == "!":
            assert isinstance(attribute, int)
            assert not attribute >= len(deep_structure)
            sub_deep_structure = deep_structure.get(attribute)
            sub_hash_pattern = hash_pattern[key]
        elif key.startswith("!"):
            assert isinstance(attribute, int)
            step = int(key[1:])
            chunk = int(attribute / step)
            sub_hash_pattern = hash_pattern[key]
        else:
            sub_deep_structure = deep_structure[attribute]
            sub_hash_pattern = hash_pattern[attribute]

    if len(path) == 1:
        assert sub_hash_pattern in ("#", "##")
        if not single_key and not has_star and key.startswith("!"):
            old_substructure = deep_structure[chunk]
            deep_structure[chunk] = substructure
        else:
            old_substructure = deep_structure[attribute]
            deep_structure[attribute] = substructure
        return old_substructure

    return set_deep_structure(
        substructure, sub_deep_structure, sub_hash_pattern, path[1:]
    )

def write_deep_structure(checksum:Checksum, deep_structure, hash_pattern, path):
    """Writes checksum into deep structure, at the given path.
    If the deep structure has missing values in path, they will be inserted as None values into the deep structure

    If the deep structure has the same depth as path,
      the checksum is written directly, and (0, x) is returned
       where x is the old checksum.
    If the structure is deeper than the path:
        (1, x) is returned, where x is the sub-hash-pattern
        The caller is supposed to convert the checksum into a substructure
         using this sub-hash-pattern (checksum => buffer => value
          => value_to_deep_structure(value, sub_hash_pattern)
        and then invoke set_deep_structure
    If the path is deeper than the structure:
        (2, p1, x, p2, is_raw) is returned.
        p1 is the sub-path that was accessed until # was encountered
         in the deep structure
        x is the checksum at p1
        p2 is the sub-path that remains (p1 + p2 = path)
        is_raw indicates if the hash was raw (##) or normal (#)
        The caller is supposed to convert x to a value v1, and checksum to a value v2
         then apply _set_subpath(v1, p2, v2) => compute checksum of modified v1 => c
         and then invoke write_deep_structure(c, deep_structure, hash_pattern, p1)
    """

    assert hash_pattern is not None
    checksum = Checksum(checksum)

    if hash_pattern in ("#", "##"):
        assert len(path)
        old_checksum = deep_structure
        assert isinstance(old_checksum, str)
        bytes.fromhex(old_checksum)
        return 2, (), old_checksum, path, (hash_pattern == "##")

    validate_deep_structure(deep_structure, hash_pattern)
    assert isinstance(deep_structure, (list, dict)), deep_structure

    if not len(path):
        return 1, hash_pattern

    attribute = path[0]
    single_key = len(hash_pattern)
    has_star = "*" in hash_pattern
    if not single_key:
        assert isinstance(attribute, str)
        sub_deep_structure = deep_structure.get(attribute)
        if attribute in hash_pattern:
            sub_hash_pattern = hash_pattern[attribute]
        else:
            assert has_star, (path, list(deep_structure.keys()))
            sub_hash_pattern = hash_pattern["*"]
    else:
        key = list(hash_pattern.keys())[0]
        if has_star:
            assert isinstance(attribute, str)
            sub_deep_structure = deep_structure.get(attribute)
            sub_hash_pattern = hash_pattern["*"]
        elif key.startswith("!"):
            assert isinstance(attribute, int)
            if key == "!":
                step = 1
            else:
                step = int(key[1:])
            chunk = int(attribute / step)
            for n in range(len(deep_structure),chunk+1):
                deep_structure.append(None)
            sub_deep_structure = deep_structure[chunk]
            sub_hash_pattern = hash_pattern[key]
        else:
            if attribute not in deep_structure:
                deep_structure[attribute] = None
            sub_deep_structure = deep_structure[attribute]
            sub_hash_pattern = hash_pattern[attribute]

    if len(path) == 1 and sub_hash_pattern in ("#", "##"):
        attr = path[0]
        if isinstance(attr, int):
            old_checksum = deep_structure[attr]
        else:
            old_checksum = deep_structure.pop(attr, None)
        if checksum:
            deep_structure[attr] = checksum
        return 0, old_checksum

    result = write_deep_structure(
        checksum, sub_deep_structure, sub_hash_pattern,
        path[1:]
    )
    if result[0] == 2:
        _, pre_path, old_checksum, post_path, is_raw = result
        pre_path = pre_path + (path[0],)
        return 2, pre_path, old_checksum, post_path, is_raw
    else:
        return result

async def apply_hash_pattern(checksum:Checksum, hash_pattern):
    """Converts a checksum to a checksum that represents a deep structure"""
    checksum = Checksum(checksum)
    if hash_pattern == "#":
        return checksum
    else:
        buffer = get_buffer(checksum, remote=True)
        if hash_pattern == "##":
            if not buffer.startswith(MAGIC_SEAMLESS_MIXED):                                    
                if not buffer.startswith(MAGIC_NUMPY):
                    try:
                        buffer.decode()
                    except UnicodeDecodeError:
                        pass
                    return checksum
        value = await deserialize(
            buffer, checksum, "mixed", False
        )
        if hash_pattern == "##":
            if isinstance(value, np.ndarray) and value.dtype.char == "S":
                deep_buffer = value.tobytes()
            else:  # probably a truly mixed Seamless object, or a true Numpy array. Just return the buffer
                return checksum
        else:
            deep_structure, _ = await value_to_deep_structure(value, hash_pattern)
            deep_buffer = await serialize(deep_structure, "plain")
    deep_checksum = await cached_calculate_checksum(deep_buffer)
    buffer_cache.cache_buffer(deep_checksum, deep_buffer)
    buffer_cache.guarantee_buffer_info(deep_checksum, "plain", sync_to_remote=False)
    return Checksum(deep_checksum)

def apply_hash_pattern_sync(checksum, hash_pattern):
    """Converts a checksum to a checksum that represents a deep structure

    This function can be executed if the asyncio event loop is already running"""

    if not asyncio.get_event_loop().is_running():
        coro = apply_hash_pattern(checksum, hash_pattern)
        fut = asyncio.ensure_future(coro)
        asyncio.get_event_loop().run_until_complete(fut)
        return fut.result()

    buffer = get_buffer(checksum, remote=True)
    value = deserialize_sync(
        buffer, checksum, "mixed", False
    )
    deep_structure, _ = value_to_deep_structure_sync(value, hash_pattern)
    deep_buffer = serialize_sync(deep_structure, "plain")
    deep_checksum = cached_calculate_checksum_sync(deep_buffer)
    buffer_cache.cache_buffer(deep_checksum, deep_buffer)
    return Checksum(deep_checksum)


from seamless.buffer.cached_calculate_checksum import cached_calculate_checksum, cached_calculate_checksum_sync
from seamless.buffer.serialize import serialize, serialize_sync
from seamless.buffer.deserialize import deserialize, deserialize_sync
from seamless.buffer.buffer_cache import buffer_cache
from seamless.buffer.get_buffer import get_buffer