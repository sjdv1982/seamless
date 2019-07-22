from collections import OrderedDict
import sys
import json
from .json import json_encode
from copy import deepcopy
from ...silk import Silk

"""
A connection declaration may have up to four parts
- io: the type of the connection. Can be "input", "output" or "edit".
  Only pins declare this.
- transfer mode: this declares how the data is transferred.
  - "buffer": the data is transferred as a buffer that can be directly written
    to/from file. It depends on the content type whether the file should be opened
    in text or in binary mode.
  - "copy": the data is transferred as a deep copy that is safe against modifications
    (however, only for edit pins such modifications would be appropriate)
  - "ref": the data is transferred as a reference that should not be modified.
    "ref" merely indicates that a copy is not necessary.
    If transfer-by-reference is not possible for any reason, a copy is transferred instead.
  - "signal": the connection is a signal, no data whatsoever is transferred
- access mode: this declares in which form the data will be accessible to the recipient
    Also the format of set_cell
  - pythoncode: a string that can be exec'ed by Python
  - plain: nested dicts, lists and basic types (str/float/int/bool).
  - silk: a Silk object
  - text: a text string
  - module: a Python module
  - binary_module: a tree of binary objects (.o / .obj) for compilation
  - default (only transformer inputpins). "silk" if the source is "plain" or "mixed", else "object"
- content type: the semantic content of the data
  - text: text
  - python: generic python code
  - ipython: IPython code
  - transformer: transformer code
  - reactor: reactor code
  - macro: macro code
  - plain: plain data
  - cson: CSON data
  - mixed: seamless.mixed data
  - binary: Numpy data

Note that content types are closely related to (low-level) cell types.
They will never be something as rich as MIME types;
  support for this must be in some high-level annotation/schema field.
"""

transfer_modes = ("buffer", "copy", "ref", "module")
access_modes = ("pythoncode", "plain", "mixed", "silk", "text", "module", "binary_module", "binary") # how the data is accessed
content_types = ("text",
  "python", "ipython", "transformer", "reactor", "macro",
  "plain", "cson", "mixed", "binary"
)
text_types = ("text", "python", "ipython", "transformer", "reactor", "macro", "cson")

from .deserialize import deserialize


'''
class ValueDummy:
    def __init__(self, value):
        self.value = value
        self.is_function = False

class TransferredCell:
    is_function = False
    def __init__(self, cell):
        for attr in dir(cell):
            if attr.startswith("_"):
                continue
            setattr(self, attr, getattr(cell, attr))

def set_cell(cell, value, *,
  default, from_buffer, force, from_pin=False
):
    transfer_mode = "buffer" if from_buffer else "ref"
    different, text_different = cell.deserialize(value, transfer_mode,
      "object", None,
      from_pin=from_pin, default=default,force=force
    )
    return different, text_different

def compile_binary_module(binary_module):
    from ...compiler.build_extension import build_extension_cffi
    compiler_verbose = False
    if binary_module.get("target") == "debug":
        compiler_verbose = True
    #TODO: other compilation than cffi (Numpy or Cython)
    module_name = build_extension_cffi(binary_module, compiler_verbose=compiler_verbose)
    return sys.modules[module_name]

def substitute_default(source_mode, target_mode):
    if target_mode[1] != "default":
        return target_mode
    access_mode, content_type = source_mode[1:]
    if access_mode == "object":
        if content_type in ("plain", "mixed"):
            result = "silk"
        elif content_type == "object":
            if content_type in text_types:
                result = "text"
            else:
                result = "object"
        else:
            result = "object"
    elif access_mode in ("plain", "silk"):
        result = "silk"
    else:
        result = access_mode
    return target_mode[0], result, target_mode[2]

#################################
#   Adapters
#################################

def adapt_cson_json(source):
    assert isinstance(source, str), source
    return cson2json(source)

def adapt_to_silk(source):
    from ...silk import Silk, Scalar
    if isinstance(source, Scalar):
        return source
    else:
        return Silk(data=source)

def adapt_from_silk(source):
    if not isinstance(source, Silk):  #HACK: should have been covered by protocol
        print("Warning, adapt_from_silk, should have been Silk, is %s" % type(source))
        return source
    return deepcopy(source.data)

def assert_text(source):
    source = json.loads(source)
    assert isinstance(source, str) or source is None, type(source)
    return source

def assert_mixed_text(source):
    assert isinstance(source, str) or source is None, type(source)
    return source

def assert_plain(source):
    json_encode(source)
    return source

def adapt_ipython(source):
    result = "code = %r\n" % source
    result +=  """
import seamless.ipython
seamless.ipython.execute(code, globals())
if not "result" in globals():
    result = _
"""
    return ValueDummy(result)


adapters = OrderedDict()
adapters[("copy", "object", "mixed"), ("copy", "text", "text")] = assert_mixed_text
adapters[("copy", "object", "mixed"), ("copy", "plain", "plain")] = assert_plain
adapters[("copy", "text", "cson"), ("copy", "plain", "cson")] = adapt_cson_json
adapters[("copy", "text", "cson"), ("copy", "plain", "plain")] = adapt_cson_json
for content_type1 in text_types:
    adapters[("copy", "text", content_type1), ("copy", "text", "plain")] = True
    adapters[("copy", "text", content_type1), ("copy", "text", "mixed")] = True
    adapters[("copy", "text", content_type1), ("copy", "object", "plain")] = True
    adapters[("copy", "text", content_type1), ("copy", "object", "mixed")] = True
    for content_type2 in text_types:
        if content_type1 == content_type2:
            continue
        adapters[("copy", "text", content_type1), ("copy", "text", content_type2)] = True

for content_type in ("text", "python", "ipython", "transformer", "reactor", "macro"):
    adapters[("copy", "text", "plain"), ("copy", "text", content_type)] = assert_text
    adapters[("copy", "text", content_type), ("copy", "text", "plain")] = json_encode
    adapters[("copy", "text", content_type), ("copy", "plain", content_type)] = True
adapters[("copy", "object", "mixed"), ("copy", "text", "mixed")] = assert_mixed_text
adapters[("copy", "object", "mixed"), ("copy", "plain", "mixed")] = assert_plain

for content_type in content_types:
    adapters[("copy", "object", content_type), ("copy", "object", "object")] = True
    adapters[("copy", "object", "object"), ("copy", "object", content_type)] = True
for content_type in ("plain", "mixed"):
    adapters[("ref", "object", content_type), ("ref", "object", "mixed")] = True
    adapters[("copy", "plain", content_type), ("copy", "object", "mixed")] = True
adapters[("copy", "object", "text"), ("copy", "object", "mixed")] = True
adapters[("ref", "plain", "plain"), ("ref", "silk", "plain")] = adapt_to_silk
adapters[("copy", "plain", "plain"), ("copy", "silk", "plain")] = adapt_to_silk
adapters[("copy", "plain", "cson"), ("copy", "silk", "cson")] = adapt_to_silk
adapters[("ref", "object", "mixed"), ("ref", "silk", "mixed")] = adapt_to_silk
adapters[("copy", "object", "mixed"), ("copy", "silk", "mixed")] = adapt_to_silk
adapters[("copy", "silk", "mixed"), ("copy", "object", "mixed")] = adapt_from_silk
adapters[("copy", "silk", "plain"), ("copy", "object", "plain")] = adapt_from_silk
for access_mode in "object", "text":
    adapters[("copy", access_mode, "python"), ("copy", access_mode, "ipython")] = True
adapters[("copy", "text", "python"), ("copy", "module", "python")] = True
adapters[("copy", "text", "python"), ("copy", "module", "ipython")] = True
adapters[("copy", "text", "ipython"), ("copy", "module", "ipython")] = True
for pymode in ("transformer", "reactor", "macro"):
    for lang in ("python", "ipython"):
        adapters[("ref", "pythoncode", lang), ("ref", "pythoncode", pymode)] = True
        adapters[("copy", "pythoncode", lang), ("copy", "pythoncode", pymode)] = True
    adapters[("copy", "text", "ipython"), ("copy", "pythoncode", pymode)] = adapt_ipython
adapters[("copy", "object", "mixed"), ("copy", "binary_module", "mixed")] = compile_binary_module
adapters[("ref", "object", "mixed"), ("ref", "binary_module", "mixed")] = compile_binary_module

def select_adapter(transfer_mode, source, target, source_modes, target_modes):
    #print("select_adapter", transfer_mode, source, target, source_modes, target_modes)
    if transfer_mode == "ref":
        transfer_modes = ["ref", "copy"]
    else:
        transfer_modes = [transfer_mode]
    for trans_mode in transfer_modes:
        for source_mode0 in source_modes:
            if source_mode0[0] != trans_mode:
                continue
            for target_mode in target_modes:
                source_mode = source_mode0
                target_mode = substitute_default(source_mode, target_mode)
                if target_mode[0] != trans_mode:
                    continue
                if source_mode[1] is None:
                    source_mode = (trans_mode, target_mode[1], source_mode[2])
                if source_mode[2] is None:
                    source_mode = (trans_mode, source_mode[1], target_mode[2])
                if target_mode[1] is None:
                    target_mode = (trans_mode, source_mode[1], target_mode[2])
                if target_mode[2] is None:
                    target_mode = (trans_mode, target_mode[1], source_mode[2])
                if source_mode == target_mode:
                    return None, (source_mode, target_mode)
                adapter = adapters.get((source_mode, target_mode))
                if adapter is not None:
                    if adapter is True:
                        return None, (source_mode, target_mode)
                    else:
                        return adapter, (source_mode, target_mode)
    raise Exception("""Could not find adapter between %s and %s

Supported source modes: %s

Supported target modes: %s

""" % (source, target, source_modes, target_modes))

def serialize(cell, transfer_mode, access_mode, content_type):    
    source_modes = list(cell._supported_modes)
    if transfer_mode == "ref":
        transfer_modes = ["ref", "copy"]
    else:
        transfer_modes = [transfer_mode]
    for trans_mode in transfer_modes:
        target_mode0 = trans_mode, access_mode, content_type
        for source_mode0 in source_modes:
            if source_mode0[0] != trans_mode:
                continue
            source_mode = source_mode0
            target_mode = substitute_default(source_mode, target_mode0)
            if target_mode[0] != trans_mode:
                continue
            if source_mode[1] is None:
                source_mode = (trans_mode, target_mode[1], source_mode[2])
            if source_mode[2] is None:
                source_mode = (trans_mode, source_mode[1], target_mode[2])
            if target_mode[1] is None:
                target_mode = (trans_mode, source_mode[1], target_mode[2])
            if target_mode[2] is None:
                target_mode = (trans_mode, target_mode[1], source_mode[2])
            if source_mode == target_mode:
                adapter = True
            else:
                adapter = adapters.get((source_mode, target_mode))
            if adapter is not None:
                value = cell.serialize(*source_mode)
                if value is None:
                    return None
                if adapter is True:
                    return value
                else:
                    return adapter(value)
    target_mode = transfer_mode, access_mode, content_type                    
    raise Exception("""Could not find adapter for cell %s

Requested mode: %s

Supported modes: %s

""" % (cell, target_mode, source_modes))

from .cson import cson2json
'''