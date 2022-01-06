"""
Conversions. Note that they operate at a checksum/buffer level.
  Conversions that always require a value-level evaluation are considered "forbidden",
   as they must be done elsewhere.
  Values are not built, unless the deserialization is really simple (e.g. json.loads)
  Conversions imply that that there is neither a access path not a hash pattern.
  In contrast, expressions with a path or a hash pattern operate at a value level.
  VALUE-LEVEL CONVERSION IS NOT DEALT WITH HERE: it is evaluate_expression that does that.
   (Both source and target object are deserialized, and target_object[path] = source,
    taking into account hash pattern.)
  THEREFORE, DEEP CELLS ARE ALSO NOT HANDLED HERE.
  REASON: conversion.py does not handle any kind of caching.


Type hierarchy:

bytes: Buffer and value are the same.
 mixed: combination of plain and binary.
  binary: value is Numpy array/struct. Buffer is value with np.save.
   binary-bytes (1D array of dtype S). NOT a subtype of bytes!
    If you convert them to bytes, do value.tobytes() .
  plain: Buffer is JSON. Value is what is trivially JSON-serializable. 
   str (with double quotes around *the buffer*), int, float, bool
 text (with no double quotes around *the buffer*). 
 Buffer is UTF-8. Value is Python string (read buffer in text mode / buffer.decode())
  cson: special case, as it is a superset of JSON, i.e "plain" is a subtype
  yaml: also a superset of JSON
  ipython
    python 
checksum. Special case: the *value* is a checksum string (checksum.hex())
  The *checksum* of a checksum cell is therefore the checksum-of a checksum string.
  Deep cells: when converted to a checksum cell, the checksum of a deep cell remains the same.
  However, as all hash patterns, this is handled by evaluate_expression and not here.
  Note that a checksum never holds a reference to the checksum value(s) it contains.

In principle, all conversion from a subclass to a superclass is trivial.
This includes str to plain.
All conversion from a superclass to a subclass is "reinterpret", including plain to str.
One exception is between binary/mixed and bytes, since bytes is not a strict superclass.
This one is "forbidden", as it requires a value.
Another exception is plain and cson/yaml.
These conversions are indeed trivial/forbidden for "plain", but not
 for the subclasses of plain (str, bool, int, float), which are forbidden.
Finally, "mixed" to a subtype of "mixed" requires a value evaluation, hence forbidden.

("bytes", "binary") *normally* doesn't change checksum,
but it does if it a single Numpy array of dtype "S".
Hence, the same for ("bytes", "mixed").
This requires also a value evaluation, hence forbidden.

Text conversion rules:
- Texts are UTF-8-encoded byte strings. So conversion to bytes is trivial.
  Conversion from bytes is "reinterpret", dependent on the success of buffer.decode()
  (UTF-8 is default in Python)
- Between text and str works as expected. 
  The value remains unchanged, the buffer gets quotes added/removed (json.dumps)
- Text to plain tries to interpret the text as JSON. Failure gives an exception.
  (i.e. "reinterpret") . 
  Text to a subclass-of-plain then checks for the data type.
- Plain to text dumps the cell as JSON text, i.e. "trivial"

Checksum cells: the *value* of the checksum cell:
- If a checksum string, it can be promoted to any celltype
- If a dict or list, it can be promoted to plain or to mixed.
  Mixed cells must have the correct hash pattern.
  This is only validated for simple hash patterns.
All of these promotions are value-based and therefore "forbidden" 
(handled by evaluate_expression)

TODO: impose limits of 1000 chars for buffers of int, float, bool

TODO: get_buffer_info.
./core/protocol/evaluate.py needs to be reworked.
On top of the evaluation caches, a "buffer info" dict is needed.
Unlike the evaluation caches, this is shared via database cache/sinks
 whenever appropriate.
contents of the buffer info:
- buffer length: note that float, int, bool have a max length of 1000.
- is_utf8
- is_json: json.loads will work (implies is_utf8, not is_numpy, not is_seamless_mixed)
- json_type (dict, list, str, bool, float; implies is_json)
- json_array: homogeneous json array. implies json_type=list.
- is_numpy (implies not is_json, not is_seamless_mixed)
- dtype, shape (implies is_numpy)
- is_seamless_mixed (magic Seamless mixed string; implies not is_json, not is_numpy)
- "str-text" conversion field. If the buffer can be a text, stores its checksum-as-str
- "text-str" conversion field. If the buffer can be a str, stores its checksum-as-text
- "binary-bytes" conversion field (see below)
- "bytes-binary" conversion field (see below)
- "binary-json" conversion field. Result of ("binary", "plain") conversion.
- "json-binary" conversion field. Result of ("plain", "binary") conversion.
For conversions ("valid" means "preserves checksum". not valid means a failure):
- is_utf8: bytes to text is valid. otherwise, not valid.
- is_json: bytes/text/cson/yaml/mixed to plain is valid. otherwise, not valid.
- json_type: bytes/text/cson/yaml/mixed to that particular type is valid.
   otherwise, not valid for conversion-to-float/int/bool, unless str/float/int/bool
- json_array: conversion to Numpy array will work.
- is_numpy: mixed to binary is valid. Otherwise, not valid.
  if dtype is S and empty shape:
      bytes to mixed is valid. Otherwise (but is_numpy), reformat.
      Same for bytes to binary.
      Reformatted checksum can be stored under "binary-bytes" field
      This is just for caching, as this conversion is always valid.
- is_seamless_mixed:
   bytes to mixed is valid. Otherwise, (and not is_numpy, not is_json), invalid
- bytes-binary: gives the checksum of the np.dtype(S...) array corresponding to the bytes.
  This is just for caching, as this conversion is always valid.

buffer_info contains nothing about valid conversion to python/ipython/cson/yaml.
=> 
The database may return other fields as well.
TODO: high-level classes on top of deep cells. See https://github.com/sjdv1982/seamless/issues/108
"""

class SeamlessConversionError(ValueError):
    def __str__(self):
        args = [str(arg) for arg in self.args]
        return "\n".join(args)
    def __repr__(self):
        args = [str(arg) for arg in self.args]
        return "\n".join(args)

import numpy as np

conversion_trivial = set([ # conversions that do not change checksum and are guaranteed to work (if the input is valid)    
    ("text", "bytes"), 
    ("ipython", "text"),
    ("python", "text"),
    ("python", "ipython"),
    ("cson", "text"),
    ("yaml", "text"),
    ("plain", "cson"),
    ("plain", "yaml"),

    ("plain", "bytes"),

    ("binary", "mixed"),
    ("plain", "mixed"),
    ("str", "plain"),
    ("int", "plain"),
    ("float", "plain"),
    ("bool", "plain"),
])

conversion_reinterpret = set() # conversions that do not change checksum, but are not guaranteed to work (raise exception).
for source, target in conversion_trivial:
    conversion_reinterpret.add((target, source))
conversion_reinterpret.difference_update(set([
    ("ipython", "python"),
    ("cson", "plain"),
    ("yaml", "plain"),
]))

conversion_reformat = set([ # conversions that are guaranteed to work (if the input is valid), but may change checksum
    # special cases:
    ("bytes", "binary"), # for numpy buffer format (magic numpy string), trivial. Else, create np.dtype(S) array from bytes buffer.
    ("bytes", "mixed"), # as above, but Seamless-mixed buffer format (MAGIC_SEAMLESS_MIXED string) is also trivial.
    ("binary", "bytes"), # for np.dtype(S..), get value.tobytes(); else trivial 
    ("mixed", "bytes"), # ("binary", "bytes") if binary (magic numpy string); else trivial

    ("plain", "text"), # if value is a string, value stays the same; else checksum stays the same
    ("text", "plain"), # if json.loads works, checksum stays the same; else value stays the same (becomes str).
    ("text", "str"),   # value stays the same
    ("str", "text"),   # value stays the same
    ("cson", "plain"), # run CSON parser
    ("yaml", "plain"), # run YAML parser
    
    ("ipython", "python"),  # convert to Python code
    
    # simple value conversions:
    ("int", "str"), ("float", "str"), ("bool", "str"),
    ("int", "float"), ("bool", "int"),
    ("float", "int"), ("int", "bool"), 
    ("float", "bool"), ("bool", "float"),
])

conversion_possible = set([ # conversions that (may) change checksum and are not guaranteed to work (raise exception)    
    # simple value conversions:                       
    ("binary", "int"), ("binary", "float"), ("binary", "bool"),
    ("str", "int"), ("str", "float"), ("str", "bool"),    
    ("mixed", "str"), ("mixed", "int"), ("mixed", "float"), ("mixed", "bool"),
])

###

conversion_equivalent = { #equivalent conversions
    # special cases
    # 1. text_subtype-to-str. Do not promote to text-to-plain!
    ("cson", "str"): ("text", "str"),
    ("yaml", "str"): ("text", "str"),
    ("text", "mixed"): ("text", "str"), # NOT text-to-plain. 
                                        # But mixed => text does go mixed => plain => text
    ("cson", "mixed"): ("text", "str"), # NOT cson-to-plain
    ("yaml", "mixed"): ("text", "str"), # NOT yaml-to-plain
    ("python", "str"): ("text", "str"),
    ("ipython", "str"): ("text", "str"),
    ("python", "mixed"): ("text", "str"),
    ("ipython", "mixed"): ("text", "str"),
    ("python", "plain"): ("text", "str"),
    ("ipython", "plain"): ("text", "str"),    
    # 2. str-to-text_subtype. Plain-to-text or str-to-text are the same here.
    ("str", "cson"): ("str", "text"),
    ("str", "yaml"): ("str", "text"),
    ("str", "python"): ("str", "text"),
    ("str", "ipython"): ("str", "text"),

    # apply specific converter to generalized outputs    
    ("python", "bytes"): ("python", "text"),
    ("ipython", "bytes"): ("ipython", "text"),
    ("str", "mixed"): ("str", "binary"),
    ("int", "mixed"): ("int", "plain"),
    ("float", "mixed"): ("float", "plain"),
    ("bool", "mixed"): ("bool", "plain"),
            
    # apply generic converter to specified inputs
    ("str", "binary"): ("plain", "binary"),
    ("float", "binary"): ("plain", "binary"),
    ("int", "binary"): ("plain", "binary"),
    ("bool", "binary"): ("plain", "binary"),    
    ("python", "binary"): ("text", "binary"),
    ("ipython", "binary"): ("text", "binary"),
    ("cson", "bytes"): ("text", "bytes"),
    ("yaml", "bytes"): ("text", "bytes"),
    ("str", "bytes"): ("plain", "bytes"),
    ("int", "bytes"): ("plain", "bytes"),
    ("float", "bytes"): ("plain", "bytes"),
    ("bool", "bytes"): ("plain", "bytes"),
    ("int", "text"): ("plain", "text"),
    ("float", "text"): ("plain", "text"),
    ("bool", "text"): ("plain", "text"),

}

conversion_chain = { #(A,C): B means convert A => B => C
    ("mixed", "text"): "plain",   # special case
    ("mixed", "cson"): "text",
    ("mixed", "yaml"): "text",
    ("mixed", "ipython"): "text",
    ("mixed", "python"): "text",

    ("binary", "text"): "plain", # special case
    ("binary", "cson"): "text",
    ("binary", "yaml"): "text",
    ("binary", "ipython"): "text",
    ("binary", "python"): "text",

    ("bytes", "str"): "plain",
    ("bytes", "float"): "plain",
    ("bytes", "int"): "plain",
    ("bytes", "bool"): "plain",

    ("bytes", "cson"): "text",
    ("bytes", "yaml"): "text",
    ("bytes", "ipython"): "text",
    ("bytes", "python"): "text",
    ("binary", "str"): "bytes",  # binary => bytes (special case) => plain => str
    ("plain", "python"): "text",
    ("plain", "ipython"): "text",

    ("text", "binary"): "mixed",
    ("text", "float"): "plain",
    ("text", "int"): "plain",
    ("text", "bool"): "plain",

    ("cson", "binary"): "plain",
    ("yaml", "binary"): "plain",
    ("cson", "yaml"): "plain",
    ("yaml", "cson"): "plain",
    ("cson", "int"): "plain",
    ("cson", "float"): "plain",
    ("cson", "bool"): "plain",
    ("yaml", "int"): "plain",
    ("yaml", "float"): "plain",
    ("yaml", "bool"): "plain",

    ("int", "cson"): "plain",
    ("int", "yaml"): "plain",
    ("float", "cson"): "plain",
    ("float", "yaml"): "plain",
    ("bool", "cson"): "plain",
    ("bool", "yaml"): "plain",

}

conversion_values = set([ 
    # These conversions must be handled elsewhere (with caching and/or values)

    # value conversions. Invalid for many values.
    ("binary", "plain"),  # use json_encode
    ("plain", "binary"),  # value must be a list; parse with numpy, and dtype must not be "object"
                          # or: value must be a scalar

    # conversions from/to checksum.
    ("checksum", "bytes"),
    ("checksum", "mixed"),
    ("checksum", "binary"),
    ("checksum", "plain"),
    ("checksum", "str"),
    ("checksum", "int"),
    ("checksum", "float"),
    ("checksum", "bool"),
    ("checksum", "text"),
    ("checksum", "cson"),
    ("checksum", "yaml"),
    ("checksum", "python"),
    ("checksum", "ipython"),
    ("bytes", "checksum"),
    ("mixed", "checksum"),
    ("binary", "checksum"),
    ("plain", "checksum"),
    ("str", "checksum"),
    ("int", "checksum"),
    ("float", "checksum"),
    ("bool", "checksum"),
    ("text", "checksum"),
    ("cson", "checksum"),
    ("yaml", "checksum"),
    ("python", "checksum"),
    ("ipython", "checksum"),

])

conversion_forbidden = set([ 
    # completely forbidden conversions.
    ("python", "cson"),
    ("python", "yaml"),
    ("python", "int"),
    ("python", "float"),
    ("python", "bool"),
    ("ipython", "cson"),
    ("ipython", "yaml"),
    ("ipython", "int"),
    ("ipython", "float"),
    ("ipython", "bool"),
    ("cson", "python"),
    ("cson", "ipython"),
    ("yaml", "python"),
    ("yaml", "ipython"),
    ("int", "python"), ("int", "ipython"),
    ("float", "python"), ("float", "ipython"),
    ("bool", "python"), ("bool", "ipython"),
])

def check_conversions():
    categories = (
        conversion_trivial,
        conversion_reformat,
        conversion_reinterpret,
        conversion_possible,
        conversion_equivalent,
        conversion_chain,
        conversion_values,
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
                if conv not in conversion_equivalent and conv not in conversion_chain:
                    break
                if conv in conversion_equivalent and conv in conversion_chain:
                    raise Exception("Duplicate conversion mapping: %s" % str(conv))                
                if conv in conversion_equivalent:
                    conv = conversion_equivalent[conv]
                elif conv in conversion_chain:
                    conv = (conversion_chain[conv], conv[1])
                if conv in done:
                    raise Exception("Circular equivalence: %s" % str(conv))
                done.append(conv)

async def reinterpret(checksum, buffer, celltype, target_celltype):
    try:
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
    done = False
    if key == ("text", "checksum"):
        if checksum is None:
            value = None
        else:
            value = checksum.hex()
        new_buffer = await serialize(value, "plain")
        done = True
    elif key == ("text", "plain"):
        try:
            await deserialize(buffer, checksum, "plain", copy=False)
            return checksum
        except Exception:
            done = False
    if not done:
        value = await deserialize(buffer, checksum, celltype, copy=False)
        if key == ("plain", "str"):
            if isinstance(value, str):
                new_buffer = await serialize(value, target_celltype)
            else:
                if fingertip_mode:
                    buffer_cache.cache_buffer(checksum, buffer)
                return checksum
        elif key == ("plain", "text"):
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
    if len(buffer) > 1000 and celltype in ("plain", "mixed") \
        and target_celltype in ("int", "float", "bool"):
            raise SeamlessConversionError
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
            from ...ipython import ipython2python
            value00 = ipython2python(buffer.decode()) # TODO: needs to bind get_ipython() to the user namespace! see issue 25
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
from silk.mixed import MAGIC_NUMPY, MAGIC_SEAMLESS_MIXED, is_numpy_buffer
from .cson import cson2json
from ..cache.buffer_cache import buffer_cache

check_conversions()