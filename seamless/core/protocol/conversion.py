# Conversions. Note that they operate at a checksum/buffer level, and only used for no-path write accessors. 
#   In contrast, write accessors with a path operate at a value level. 
#   Both source and target object are deserialized, and target_object[path] = source.

# text (with no double quotes around value), 
# python, ipython, cson, yaml, plain, binary, mixed
# str (with double quotes around value), bytes, int, float, bool

from nbconvert.filters import ipython2python

conversion_trivial = set([ # conversions that do not change checksum and are guaranteed to work (if the input is valid)
    ("text", "bytes"), # Use UTF-8, which can encode any Unicode string. This is already what Seamless uses internally
    ("python", "text"),
    ("python", "ipython"),
    ("python", "mixed"), # but not to plain! e.g. mixed cells can hold Python cell values directly, whereas plain cells must have them first converted to text    
    ("ipython", "text"),
    ("ipython", "mixed"), # see above
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
    ("text", "str"),
    ("text", "int"), ("text", "float"), ("text", "bool"),
    ("plain", "str"), ("plain", "int"), ("plain", "float"), ("plain", "bool"),    
    ("mixed", "plain"), ("mixed", "binary"),
    ("mixed", "str"), ("mixed", "int"), ("mixed", "float"), ("mixed", "bool"),
    ("int", "text"), ("float", "text"), ("bool", "text"),
    ("int", "plain"), ("float", "plain"), ("bool", "plain"),    
])

# buffer-to-buffer

conversion_reformat = set([ # conversions that are guaranteed to work (if the input is valid), but change checksum
    ("plain", "text"), # trivial if not a string, else chop off quotes
    ("text", "plain"),   # use json.dumps, or repr
    ("str", "text"),   # use json.loads, or eval. assert isinstance(str)
    ("str", "bytes"),   # str => text => bytes
    ("binary", "bytes"), # this will dump the binary buffer as bytes; note that this is not allowed for mixed
    ("bytes", "binary"), # inverse of the above; also not allowed for mixed
    ("bytes", "str"),    # bytes => text => str
    ("int", "str"), ("float", "str"), ("bool", "str"),
    ("int", "float"), ("bool", "int"),
    ("float", "int"), ("int", "bool"),
])

conversion_possible = set([ # conversions that (may) change checksum and are not guaranteed to work (raise exception)
    ("ipython", "python"),
    ("cson", "plain"),
    ("yaml", "plain"),
    ("binary", "str"), ("binary", "int"), ("binary", "float"), ("binary", "bool"),
    ("bytes", "text"), # Assume UTF-8 (being a subset of UTF-8, ASCII is fine too)
                       # If this is not so, an error is typically raised (UTF-8 is not a charmap!)
    ("str", "int"), ("str", "float"), ("str", "bool"),
    ("int", "binary"), ("float", "binary"), ("bool", "binary"),   
])

###

conversion_equivalent = { #equivalent conversions
    ("text", "mixed"): ("text", "plain"),
    ("python", "str"): ("text", "str"),
    ("ipython", "str"): ("text", "str"),
    ("cson", "mixed"): ("cson", "plain"),
    ("yaml", "mixed"): ("yaml", "plain"),
    ("mixed", "text"): ("mixed", "plain"),
    ("mixed", "python"): ("text", "python"), # but not from plain! e.g. mixed cells can convert to Python cell values directly, whereas plain cells must have them first converted to text
    ("mixed", "ipython"): ("text", "ipython"), # see above    
    ("int", "mixed"): ("int", "plain"), 
    ("float", "mixed"): ("float", "plain"), 
    ("bool", "mixed"): ("bool", "plain"),
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
    ("plain", "python"), ("plain", "ipython"), ("plain", "binary"), ("plain", "bytes"),
    ("binary", "text"), ("binary", "python"), ("binary", "ipython"), 
    ("binary", "cson"), ("binary", "yaml"), ("binary", "plain"),
    ("mixed", "cson"), ("mixed", "yaml"),
    ("mixed", "bytes"), # dumping the buffer as bytes is not allowed, even for pure-binary mixed data. Convert to binary celltype, first.
    ("str", "python"), ("str", "ipython"), ("str", "cson"), ("str", "yaml"), 
    ("str", "binary"),
    ("bytes", "python"), ("bytes", "ipython"), ("bytes", "cson"), ("bytes", "yaml"), ("bytes", "plain"), 
    ("bytes", "mixed"), # loading the bytes into a pure-binary buffer is not allowed. Convert to binary celltype, first.
    ("bytes", "float"), ("bytes", "int"), ("bytes", "bool"),
    ("int", "python"), ("float", "python"), ("bool", "python"),
    ("int", "ipython"), ("float", "ipython"), ("bool", "ipython"),
    ("int", "cson"), ("float", "cson"), ("bool", "cson"),
    ("int", "yaml"), ("float", "yaml"), ("bool", "yaml"),
    ("int", "bytes"), ("float", "bytes"), ("bool", "bytes"),
    ("bool", "float"), ("float", "bool"),
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
                raise ValueError        

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
            _ = await serialize(value, target_celltype)
    except Exception:
        msg = "%s cannot be re-interpreted from %s to %s"
        raise ValueError(msg % (checksum.hex(), celltype, target_celltype))
    return

async def reformat(checksum, buffer, celltype, target_celltype):
    value = await deserialize(buffer, checksum, celltype, copy=False)
    new_buffer = await serialize(value, target_celltype)
    result = await calculate_checksum(new_buffer)
    return result

async def convert(checksum, buffer, celltype, target_celltype):
    key = (celltype, target_celltype)        
    try:
        if key == ("cson", "plain"):
            value = cson2json(buffer.decode())
        elif key == ("yaml", "plain"):
            value = yaml.load(buffer.decode())
        else:
            value = await deserialize(buffer, checksum, celltype, copy=False)
        
        if key == ("ipython", "python"):
            value = ipython2python(buffer) # TODO: needs to bind get_ipython() to the user namespace!
            new_buffer = await serialize(value, target_celltype)
        elif key == ("plain", "text"):
            if not isinstance(value, str):
                new_buffer = buffer
            else:
                new_buffer = await serialize(value, target_celltype)    
        else:
            new_buffer = await serialize(value, target_celltype)
    except Exception:
        msg = "%s cannot be converted from %s to %s"
        raise ValueError(msg % (checksum.hex(), celltype, target_celltype))
    result = await calculate_checksum(new_buffer)
    return result

import ruamel.yaml
yaml = ruamel.yaml.YAML(typ='safe')

from ..cell import celltypes
from .deserialize import deserialize
from .serialize import serialize
from .calculate_checksum import calculate_checksum
from ...mixed import MAGIC_NUMPY, MAGIC_SEAMLESS_MIXED
from .cson import cson2json


check_conversions()