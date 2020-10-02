# Conversions. Note that they operate at a checksum/buffer level, and only used for no-path write accessors.
#   In contrast, write accessors with a path operate at a value level.
#   Both source and target object are deserialized, and target_object[path] = source.

# text (with no double quotes around *the buffer*),
# python, ipython, cson, yaml, plain, binary, mixed
# str (with double quotes around *the buffer*), bytes, int, float, bool

class SeamlessConversionError(ValueError):
    def __str__(self):
        args = [str(arg) for arg in self.args]
        return "\n".join(args)
    def __repr__(self):
        args = [str(arg) for arg in self.args]
        return "\n".join(args)

import numpy as np

conversion_trivial = set([ # conversions that do not change checksum and are guaranteed to work (if the input is valid)
    ("text", "bytes"), # Use UTF-8, which can encode any Unicode string. This is already what Seamless uses internally
    ("python", "text"),
    ("python", "ipython"),
    ("ipython", "text"),
    ("cson", "text"),
    ("yaml", "text"),
    ("plain", "cson"),
    ("plain", "yaml"),
    ("plain", "mixed"),
    ("str", "plain"),
    ("str", "mixed"),
    ("binary", "mixed"),
])

# buffer-to-nothing

conversion_reinterpret = set([ # conversions that do not change checksum, but are not guaranteed to work (raise exception).
    ("text", "python"),
    ("text", "ipython"),
    ("text", "cson"),
    ("text", "yaml"),
    ("text", "int"), ("text", "float"), ("text", "bool"),
    ("plain", "str"), ("plain", "int"), ("plain", "float"), ("plain", "bool"),
    ("mixed", "plain"), ("mixed", "binary"),
    ("mixed", "str"), ("mixed", "int"), ("mixed", "float"), ("mixed", "bool"),
    ("int", "text"), ("float", "text"), ("bool", "text"),
    ("int", "plain"), ("float", "plain"), ("bool", "plain"),
])

# buffer-to-buffer

conversion_reformat = set([ # conversions that are guaranteed to work (if the input is valid), but may change checksum
    ("plain", "text"), # if old value is a string: new buffer is old value; else: no change
    ("text", "plain"),   # use json.dumps, or repr
    ("str", "text"),   # use json.loads, or eval. assert isinstance(str)
    ("str", "bytes"),   # str => text => bytes
    ("bytes", "str"),    # bytes => text => str
    ("int", "str"), ("float", "str"), ("bool", "str"),
    ("int", "float"), ("bool", "int"),
    ("float", "int"), ("int", "bool"),
    ("text", "checksum"),
    ("checksum", "plain"),
])

conversion_possible = set([ # conversions that (may) change checksum and are not guaranteed to work (raise exception)
    ("mixed", "python"), ("mixed", "ipython"), ("plain", "python"), ("plain", "ipython"),
    ("str", "python"), ("str", "ipython"),
    ("ipython", "python"),
    ("cson", "plain"),
    ("yaml", "plain"),
    ("binary", "str"), ("binary", "int"), ("binary", "float"), ("binary", "bool"),
    ("bytes", "text"), # Assume UTF-8 (being a subset of UTF-8, ASCII is fine too)
                       # If this is not so, an error is typically raised (UTF-8 is not a charmap!)
    ("str", "int"), ("str", "float"), ("str", "bool"),
    ("int", "binary"), ("float", "binary"), ("bool", "binary"),
    ("mixed", "text"),
    ("plain", "python"), ("plain", "ipython"),
    ("binary", "bytes"), ("mixed", "bytes"),# mixed must be pure-binary
                                            # This will dump the binary buffer in numpy format
                                            # np.dtype(S..) is a special case:
                                            #   it dumps a pure buffer, not numpy format
    ("bytes", "binary"),  ("bytes", "mixed"),  # inverse of the above
])

###

conversion_equivalent = { #equivalent conversions
    ("text", "mixed"): ("text", "plain"),
    ("text", "str"): ("text", "plain"),
    ("python", "str"): ("text", "plain"),
    ("ipython", "str"): ("text", "plain"),
    ("python", "mixed"): ("text", "plain"),
    ("ipython", "mixed"): ("text", "plain"),
    ("cson", "mixed"): ("cson", "plain"),
    ("yaml", "mixed"): ("yaml", "plain"),
    ("int", "mixed"): ("int", "plain"),
    ("float", "mixed"): ("float", "plain"),
    ("bool", "mixed"): ("bool", "plain"),

    ("binary", "checksum"): ("text", "checksum"),
    ("python", "checksum"): ("text", "checksum"),
    ("ipython", "checksum"): ("text", "checksum"),
    ("transformer", "checksum"): ("text", "checksum"),
    ("reactor", "checksum"): ("text", "checksum"),
    ("macro", "checksum"): ("text", "checksum"),
    ("plain", "checksum"): ("text", "checksum"),
    ("cson", "checksum"): ("text", "checksum"),
    ("mixed", "checksum"): ("text", "checksum"),  # if no hash pattern!
    ("yaml", "checksum"): ("text", "checksum"),
    ("str", "checksum"): ("text", "checksum"),
    ("bytes", "checksum"): ("text", "checksum"),
    ("int", "checksum"): ("text", "checksum"),
    ("float", "checksum"): ("text", "checksum"),
    ("bool", "checksum"): ("text", "checksum"),

    ("checksum", "mixed"): ("checksum", "plain")
}

conversion_forbidden = set([ # forbidden conversions.
    ("text", "binary"),
    ("python", "cson"), ("python", "yaml"), ("python", "plain"), ("python", "binary"),
    ("python", "bytes"), ("python", "int"), ("python", "float"), ("python", "bool"),
    ("ipython", "cson"), ("ipython", "yaml"), ("ipython", "plain"), ("ipython", "binary"),
    ("ipython", "bytes"), ("ipython", "int"), ("ipython", "float"), ("ipython", "bool"),
    ("cson", "python"), ("cson", "ipython"), ("cson", "yaml"), ("cson", "binary"),
    ("cson", "bytes"), ("cson", "str"), ("cson", "int"), ("cson", "float"), ("cson", "bool"),
    ("yaml", "python"), ("yaml", "ipython"), ("yaml", "cson"), ("yaml", "binary"),
    ("yaml", "bytes"), ("yaml", "str"), ("yaml", "int"), ("yaml", "float"), ("yaml", "bool"),
    ("plain", "binary"), ("plain", "bytes"),
    ("binary", "text"), ("binary", "python"), ("binary", "ipython"),
    ("binary", "cson"), ("binary", "yaml"), ("binary", "plain"),
    ("mixed", "cson"), ("mixed", "yaml"),
    ("str", "cson"), ("str", "yaml"),
    ("str", "binary"),
    ("bytes", "python"), ("bytes", "ipython"), ("bytes", "cson"), ("bytes", "yaml"), ("bytes", "plain"),
    ("bytes", "float"), ("bytes", "int"), ("bytes", "bool"),
    ("int", "python"), ("float", "python"), ("bool", "python"),
    ("int", "ipython"), ("float", "ipython"), ("bool", "ipython"),
    ("int", "cson"), ("float", "cson"), ("bool", "cson"),
    ("int", "yaml"), ("float", "yaml"), ("bool", "yaml"),
    ("int", "bytes"), ("float", "bytes"), ("bool", "bytes"),
    ("bool", "float"), ("float", "bool"),
    ("checksum", "binary"),
    ("checksum", "text"),
    ("checksum", "python"),
    ("checksum", "ipython"),
    ("checksum", "transformer"),
    ("checksum", "reactor"),
    ("checksum", "macro"),
    ("checksum", "cson"),
    ("checksum", "yaml"),
    ("checksum", "str"),
    ("checksum", "bytes"),
    ("checksum", "int"),
    ("checksum", "float"),
    ("checksum", "bool"),

])

def check_conversions():
    categories = (
        conversion_trivial,
        conversion_reformat,
        conversion_reinterpret,
        conversion_possible,
        conversion_equivalent,
        conversion_forbidden
    )
    for celltype1 in celltypes:
        for celltype2 in celltypes:
            if celltype1 == celltype2:
                continue
            conv = (celltype1, celltype2)
            done = [conv]
            while 1:
                covered = 0
                for category in categories:
                    if conv in category:
                        covered += 1
                if covered == 0:
                    raise Exception("Missing conversion: %s" % str(conv))
                elif covered > 1:
                    raise Exception("Duplicate conversion: %s" % str(conv))
                if conv not in conversion_equivalent:
                    break
                conv = conversion_equivalent[conv]
                if conv in done:
                    raise Exception("Circular equivalence: %s" % str(conv))
                done.append(conv)

async def reinterpret(checksum, buffer, celltype, target_celltype):

    try:
        if len(buffer) > 1000 and celltype in ("plain", "mixed") \
            and target_celltype in ("int", "float", "bool"):
                raise SeamlessConversionError

        # Special cases
        key = (celltype, target_celltype)
        if key == ("mixed", "plain"):
            assert not buffer.startswith(MAGIC_NUMPY)
            assert not buffer.startswith(MAGIC_SEAMLESS_MIXED)
        elif key == ("mixed", "binary"):
            assert buffer.startswith(MAGIC_NUMPY)
        else:
            value = await deserialize(buffer, checksum, celltype, copy=False)
            if key == ("plain", "str"):
                assert isinstance(value, str)
            elif key[0] in ("mixed", "plain") and key[1] in ("python", "ipython"):
                assert isinstance(value, str)
            _ = await serialize(value, target_celltype)
    except Exception as exc:
        msg0 = "%s cannot be re-interpreted from %s to %s"
        msg = msg0 % (checksum.hex(), celltype, target_celltype)
        full_msg = msg + "\n\nOriginal exception:\n\n" + str(exc)
        raise SeamlessConversionError(full_msg) from None
    return

async def reformat(checksum, buffer, celltype, target_celltype, fingertip_mode=False):
    key = (celltype, target_celltype)
    if key == ("text", "checksum"):
        if checksum is None:
            value = None
        else:
            value = checksum.hex()
        new_buffer = await serialize(value, "plain")
    else:
        value = await deserialize(buffer, checksum, celltype, copy=False)
        if key == ("plain", "text"):
            if isinstance(value, str):
                new_buffer = await serialize(value, target_celltype)
            else:
                if fingertip_mode:
                    buffer_cache.cache_buffer(checksum, buffer)
                return checksum
        else:
            new_buffer = await serialize(value, target_celltype)
    result = await calculate_checksum(new_buffer)
    buffer_cache.cache_buffer(result, new_buffer)
    return result

async def convert(checksum, buffer, celltype, target_celltype, fingertip_mode=False):
    key = (celltype, target_celltype)
    try:
        if key == ("cson", "plain"):
            value = cson2json(buffer.decode())
        elif key == ("yaml", "plain"):
            value = yaml.load(buffer.decode())
        elif key == ("mixed", "text"):
            value = await deserialize(buffer, checksum, "plain", copy=False)
            if isinstance(value, str):
                new_buffer = await serialize(value, target_celltype)
                result = await calculate_checksum(new_buffer)
                buffer_cache.cache_buffer(result, new_buffer)
                return result
            else:
                if fingertip_mode:
                    buffer_cache.cache_buffer(checksum, buffer)
                return checksum
        elif key in (("bytes", "binary"), ("bytes", "mixed")):
            if is_numpy_buffer(buffer):
                if fingertip_mode:
                    buffer_cache.cache_buffer(checksum, buffer)
                return checksum
            value = np.array(buffer)
        elif key in (("binary", "bytes"), ("mixed", "bytes")):
            value = await deserialize(buffer, checksum, celltype, copy=False)
            if not isinstance(value, (np.ndarray, np.void)):
                raise TypeError
            if isinstance(value, np.ndarray) and value.dtype.char == "S":
                new_buffer = value.tobytes()
                result = await calculate_checksum(new_buffer)
                buffer_cache.cache_buffer(result, new_buffer)
                return result
        else:
            value = await deserialize(buffer, checksum, celltype, copy=False)

        if key == ("ipython", "python"):
            from nbconvert.filters import ipython2python
            value00 = ipython2python(buffer.decode()) # TODO: needs to bind get_ipython() to the user namespace!
            value0 = value00.splitlines()
            while len(value0):
                if len(value0[0].strip()):
                    break
                value0 = value0[1:]
            while len(value0):
                if len(value0[-1].strip()):
                    break
                value0 = value0[:-1]
            value = "\n".join(value0)
            new_buffer = await serialize(value, target_celltype)
        else:
            new_buffer = await serialize(value, target_celltype)
    except Exception as exc:
        msg0 = "%s cannot be converted from %s to %s"
        msg = msg0 % (checksum.hex(), celltype, target_celltype)
        full_msg = msg + "\n\nOriginal exception:\n\n" + str(exc)
        raise SeamlessConversionError(full_msg) from None
    result = await calculate_checksum(new_buffer)
    buffer_cache.cache_buffer(result, new_buffer)
    return result

import ruamel.yaml
yaml = ruamel.yaml.YAML(typ='safe')

from ..cell import celltypes
from .deserialize import deserialize
from .serialize import serialize
from .calculate_checksum import calculate_checksum
from ...mixed import MAGIC_NUMPY, MAGIC_SEAMLESS_MIXED, is_numpy_buffer
from .cson import cson2json
from ..cache.buffer_cache import buffer_cache

check_conversions()