import asyncio
from copy import deepcopy

class DeepStructureError(ValueError):
    def __str__(self):
        return """
  Invalid deep structure: %s
  Hash pattern: %s""" % (self.args[1], self.args[0])

def validate_hash_pattern(hash_pattern):
    assert hash_pattern is not None
    if hash_pattern == "#":
        return
    if not isinstance(hash_pattern, dict):
        raise TypeError
    for key, value in hash_pattern.items():
        if not isinstance(key, str):
            raise TypeError((key, type(key)))
        ok = False
        if key.isalpha():
            ok = True
        elif key == "*":
            ok = True
        elif key == "!":
            ok = True
        elif key.startswith("!"):
            if key[1:].isnumeric():
                ok = True
        if not ok:
            raise TypeError((key, type(key)))
        validate_hash_pattern(value)

def validate_deep_structure(deep_structure, hash_pattern):
    try:
        assert hash_pattern is not None
        validate_hash_pattern(hash_pattern)
        if deep_structure is None:
            return
        if hash_pattern == "#":
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
                assert key == "*" or key.isalpha()
            for key in deep_structure:
                assert key.isalpha()
                if key in hash_pattern:
                    validate_deep_structure(deep_structure[key], hash_pattern[key])
                else:
                    assert has_star
                    validate_deep_structure(deep_structure[key], hash_pattern["*"])
        else:
            key = list(hash_pattern.keys())[0]
            if has_star:
                assert isinstance(deep_structure, dict)
                for key in deep_structure:
                    assert key.isalpha()
                    validate_deep_structure(deep_structure[key], hash_pattern["*"])
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
            elif key.isalpha():
                assert isinstance(deep_structure, dict)
                assert list(deep_structure.keys()) == [key]
                validate_deep_structure(deep_structure[key], hash_pattern[key])
            else:
                raise AssertionError(key)
    except AssertionError:
        raise DeepStructureError(hash_pattern, deep_structure) from None
    
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
    if hash_pattern == "#":
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
                sub_deep_structure = deep_structure.get(attribute)
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
            elif key.isalpha():
                sub_deep_structure = deep_structure[attribute]
                sub_hash_pattern = hash_pattern[attribute]
                return access_deep_structure(sub_deep_structure, sub_hash_pattern, path[1:])
            else:
                raise AssertionError(key)
    return result, path


def _deep_structure_to_checksums(deep_structure, hash_pattern, checksums):
    if deep_structure is None:
        return
    if hash_pattern == "#":        
        checksum = deep_structure
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
                deep_structure[key], sub_hash_pattern, checksums
            )
    else:
        if key.startswith("!"):
            sub_hash_pattern = hash_pattern[key]
            for sub_deep_structure in deep_structure:
                _deep_structure_to_checksums(
                    sub_deep_structure, sub_hash_pattern, checksums
                )
        elif key.isalpha():
            assert list(deep_structure.keys()) == [key]
            _deep_structure_to_checksums(
                deep_structure[key], hash_pattern[key], checksums
            )
        else:
            raise AssertionError(key)

def deep_structure_to_checksums(deep_structure, hash_pattern):
    """Collects all checksums that are being referenced in a deep structure"""
    validate_deep_structure(deep_structure, hash_pattern)
    checksums = set()
    _deep_structure_to_checksums(deep_structure, hash_pattern, checksums)
    return checksums

def _deep_structure_to_value(deep_structure, hash_pattern, value_dict, copy):
    """ build value from deep structure, using value_dict
    if copy is True, use deepcopies from the value dict, else just refer to the items
    """
    assert deep_structure is not None

    if hash_pattern == "#":        
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
        if key.startswith("!"):
            result = []
            sub_hash_pattern = hash_pattern[key]
            for sub_deep_structure in deep_structure:
                sub_result = _deep_structure_to_value(
                    sub_deep_structure, sub_hash_pattern,
                    value_dict, copy=copy 
                )   
                result.append(sub_result)
        elif key.isalpha():
            assert list(deep_structure.keys()) == [key]
            sub_result = _deep_structure_to_value(
                deep_structure[key], sub_hash_pattern,
                value_dict, copy=copy 
            )
            result = {key: sub_result}   
        else:
            raise AssertionError(key)
    return result

async def deep_structure_to_value(deep_structure, hash_pattern, buffer_dict, copy):
    """Converts deep structure to a mixed value
    Requires buffer_dict, a checksum-to-buffer cache for all checksums in the deep structure
    Use copy=True for a value that will be modified
    """
    checksums = deep_structure_to_checksums(deep_structure, hash_pattern)
    futures = {}
    for checksum in checksums:
        assert checksum in buffer_dict
        coro = deserialize(buffer_dict[checksum], checksum, "mixed", copy=copy)
        futures[checksum] = asyncio.ensure_future(coro)
    await asyncio.gather(*futures.values())
    value_dict = {checksum:futures[checksum].result() for checksum in checksums}
    return _deep_structure_to_value(deep_structure, hash_pattern, value_dict, copy)
    

def deep_structure_to_value_sync(deep_structure, hash_pattern, buffer_dict, copy):
    coro = deep_structure_to_value(
        deep_structure, hash_pattern, buffer_dict, copy
    )
    fut = asyncio.ensure_future(coro)
    asyncio.get_event_loop().run_until_complete(fut)
    return fut.result()

def _build_deep_structure(hash_pattern, d, c):
    if hash_pattern == "#":        
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
        if key.startswith("!"):
            result = []
            sub_hash_pattern = hash_pattern[key]
            for sub_d in d:
                sub_result = _build_deep_structure(
                    sub_hash_pattern, sub_d,
                    c
                )   
                result.append(sub_result)
        elif key.isalpha():
            assert list(d.keys()) == [key]
            sub_result = _deep_structure_to_value(
                d[key], sub_hash_pattern,
                c
            )
            result = {key: sub_result}   
        else:
            raise AssertionError(key)
    return result

def _value_to_objects(value, hash_pattern, objects):
    if value is None:
        return
    if hash_pattern == "#":        
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
        if key.startswith("!"):
            result = []
            sub_hash_pattern = hash_pattern[key]
            assert isinstance(value, list), value
            for sub_value in value:
                sub_result = _value_to_objects(
                    sub_value, sub_hash_pattern, objects
                )
                result.append(sub_result)
            return result
        elif key.isalpha():
            assert list(value.keys()) == [key]
            sub_result = _value_to_objects(
                value[key], hash_pattern[key], objects
            )
            return {key: sub_result}
        else:
            raise AssertionError(key)


async def value_to_deep_structure(value, hash_pattern):
    """build deep structure from value"""
    try:
        objects = {}    
        deep_structure0 = _value_to_objects(
            value, hash_pattern, objects
        )
    except (TypeError, ValueError):
        raise DeepStructureError(hash_pattern, value)
    obj_id_to_checksum = {}
    new_checksums = set()
    async def conv_obj_id_to_checksum(obj_id):
        obj = objects[obj_id]
        obj_buffer = await serialize(obj, "mixed")
        obj_checksum = await calculate_checksum(obj_buffer)
        new_checksums.add(obj_checksum.hex())
        buffer_cache.cache_buffer(obj_checksum, obj_buffer)
        obj_id_to_checksum[obj_id] = obj_checksum.hex()

    coros = []
    for obj_id in objects:
        coro = conv_obj_id_to_checksum(obj_id)
        coros.append(coro)
    await asyncio.gather(*coros)
    deep_structure = _build_deep_structure(
        hash_pattern, deep_structure0, obj_id_to_checksum
    )
    return deep_structure, new_checksums

def value_to_deep_structure_sync(value, hash_pattern):
    coro = value_to_deep_structure(
        value, hash_pattern
    )
    fut = asyncio.ensure_future(coro)
    asyncio.get_event_loop().run_until_complete(fut)
    return fut.result()


def set_deep_structure(substructure, deep_structure, hash_pattern, path):
    """Writes substructure into deep structure, at the given path
    
    Returns the old substructure: the caller is supposed to decref 
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
        elif key.isalpha():
            sub_deep_structure = deep_structure[attribute]
            sub_hash_pattern = hash_pattern[attribute]
        else:
            raise AssertionError(key)

    if len(path) == 1:
        assert sub_hash_pattern == "#"
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

def write_deep_structure(checksum, deep_structure, hash_pattern, path,
    *, create=False):
    """Writes checksum into deep structure, at the given path.
    If the structure has the same depth as path, 
      the checksum is written directly, and (0, x) is returned
       where x is the old checksum.
      The caller is supposed to incref the new checksum and decref the old one
    If the structure is deeper than the path:
        (1, x) is returned, where x is the sub-hash-pattern
        The caller is supposed to convert the checksum into a substructure
         using this sub-hash-pattern (checksum => buffer => value 
          => value_to_deep_structure(value, sub_hash_pattern)
        and then invoke set_deep_structure
    If the path is deeper than the structure:
        (2, p1, x, p2) is returned.
        p1 is the sub-path that was accessed until # was encountered
         in the deep structure
        x is the checksum at p1
        p2 is the sub-path that remains (p1 + p2 = path)
        The caller is supposed to invoke expression_target(checksum, p2, x) => c
         and then invoke write_deep_structure(c, deep_structure, hash_pattern, p1) 

    If the deep structure has missing values, they are treated as None
    However, if "create" is True, they will be inserted into the deep structure
    """

    assert hash_pattern is not None
    if checksum is not None:
        assert isinstance(checksum, str)
        bytes.fromhex(checksum)    
          
    if hash_pattern == "#":
        assert len(path)
        old_checksum = deep_structure
        assert isinstance(old_checksum, str)
        bytes.fromhex(old_checksum)    
        return 2, (), old_checksum, path
    
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
            if chunk >= len(deep_structure):
                sub_deep_structure = None
            else:
                sub_deep_structure = deep_structure[chunk]
            sub_hash_pattern = hash_pattern[key]
        elif key.isalpha():
            sub_deep_structure = deep_structure.get(attribute)
            sub_hash_pattern = hash_pattern[attribute]
        else:
            raise AssertionError(key)

    if sub_deep_structure is None:
        if create:
            set_subpath(deep_structure, None, path, checksum)
            return write_deep_structure(
                checksum, deep_structure, hash_pattern,
                path, create=False
            )
        else:
            return 2, path[:1], None, path[1:]

    if len(path) == 1 and sub_hash_pattern == "#":
        attr = path[0]
        old_checksum = deep_structure.pop(attr, None)
        if checksum is not None:
            deep_structure[attr] = checksum
        return 0, old_checksum

    result = write_deep_structure(
        checksum, sub_deep_structure, sub_hash_pattern,
        path[1:]
    )
    if result[0] == 2:
        _, pre_path, old_checksum, post_path = result
        pre_path = pre_path + (path[0],)
        return 2, pre_path, old_checksum, post_path
    else:
        return result




from .calculate_checksum import calculate_checksum
from .serialize import serialize
from .deserialize import deserialize
from ..cache.buffer_cache import buffer_cache
from ..protocol.expression import set_subpath_sync as set_subpath