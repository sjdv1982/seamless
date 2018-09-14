from ..mixed import MixedBase
from ..silk import Silk
from ..silk.validation import _allowed_types

ConstantTypes = _allowed_types + (Silk, MixedBase, tuple)

from .Context import Context
from .Library import stdlib

from copy import deepcopy

def set_hcell(cell, value):
    from ..core.structured_cell import StructuredCellState
    if cell["celltype"] == "structured":
        cell["stored_state"] = StructuredCellState.from_data(value)
    else:
        cell["stored_value"] = value
