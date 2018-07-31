from collections import OrderedDict

"""
modes and submodes that a *pin* can have, and that must be supported by a cell
These are specific for the low-level.
At the mid-level, the modes would be annotations/hints (i.e. not core),
 and the submodes would be cell languages: JSON, CSON, Silk, Python
"""
modes = ("buffer", "copy", "ref", "signal") # how the data is transferred; ref means that a copy is not necessary, a copy may still be given!
submodes = ("pythoncode", "json", "silk", "text") # how the data is accessed
celltypes = ("text", "python", "pytransformer", "json", "cson", "mixed", "binary") # the format of the data

def set_cell(cell, value, *,
  default, from_buffer, force
):
    mode = "buffer" if from_buffer else "ref"
    different, text_different = cell.deserialize(value, mode, None,
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
