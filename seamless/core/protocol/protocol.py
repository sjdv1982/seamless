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
