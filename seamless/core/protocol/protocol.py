from collections import OrderedDict

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
  - object: generic Python object (only with "object", "binary" or "mixed" content type)
  - pythoncode: a string that can be exec'ed by Python
  - json: the result of json.load, i.e. nested dicts, lists and basic types (str/float/int/bool).
  - silk: a Silk object
  - text: a text string
  TODO: code_object
- content type: the semantic content of the data
  - object: generic Python object
  - text: text
  - python: generic python code
  - transformer: transformer code
  - reactor: reactor code
  - macro: macro code
  - json: JSON data
  - cson: CSON data
  - mixed: seamless.mixed data
  - binary: Numpy data

Note that content types are closely related to (low-level) cell types.
They will never be something as rich as MIME types;
  support for this must be in some high-level annotation/schema field.
"""

transfer_modes = ("buffer", "copy", "ref", "signal")
access_modes = ("object", "pythoncode", "json", "silk", "text") # how the data is accessed
content_types = ("object", "text",
  "python", "transformer", "reactor", "macro",
  "json", "cson", "mixed", "binary"
)


def set_cell(cell, value, *,
  default, from_buffer, force
):
    transfer_mode = "buffer" if from_buffer else "ref"
    different, text_different = cell.deserialize(value, transfer_mode, None,
      from_pin=False, default=default,force=force
    )
    return different, text_different

def adapt_cson_json(source):
    return cson2json(source)

def check_adapt_cson_json(source_mode, target_mode):
    if source_mode[1] != target_mode[1]:
        return False
    if source_mode[1] not in (None, "text"):
        return False
    if target_mode[1] not in (None, "json"):
        return False
    return source_mode[2] == "cson" and target_mode[2] == "json"

adapters = OrderedDict()
adapters[check_adapt_cson_json] = adapt_cson_json

def select_adapter(source, target, source_modes, target_modes):
    for checkfunc, adapter in adapters.items():
        for source_mode in source_modes:
            for target_mode in target_modes:
                if checkfunc(source_mode, target_mode):
                    return adapter
    raise Exception("Could not find adapter between %s and %s" % (source, target))

from .cson import cson2json
