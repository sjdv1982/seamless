import weakref
import json
from ...get_hash import get_hash
import numpy as np
from weakref import WeakValueDictionary

_expressions = WeakValueDictionary()

_hash_slots = [
    "checksum",
    "path",
    "celltype",
    "hash_pattern",
    "target_celltype",
    "target_cell_path",
    "target_subcelltype",
    "target_hash_pattern",
]

class Expression:
    __slots__ = [ "__weakref__"] + _hash_slots
    def __new__(cls, *args, **kwargs):
        expression = super().__new__(cls)
        cls.__init__(expression, *args, **kwargs)
        hexpression = expression._get_hash()
        existing_expression = _expressions.get(hexpression)
        if existing_expression is not None:
            return existing_expression
        else:
            _expressions[hexpression] = expression
            return expression

    def __init__(
        self, checksum, path, celltype, 
        target_celltype, target_subcelltype,
        *, hash_pattern, target_hash_pattern,
        target_cell_path=None
    ):
        if hash_pattern is not None:
            assert celltype == "mixed"
        self.hash_pattern = hash_pattern
        if target_hash_pattern is not None:
            assert target_celltype == "mixed"
        self.target_hash_pattern = target_hash_pattern
        self.checksum = checksum
        self.path = path
        self.celltype = celltype
        self.target_celltype = target_celltype
        self.target_subcelltype = target_subcelltype
        self.target_cell_path = target_cell_path   

    def __str__(self):
        d = {}
        for slot in _hash_slots:
            v = getattr(self, slot)
            if slot == "checksum":
                if v is not None:
                    v = v.hex()
            d[slot] = v
        return json.dumps(d, indent=2, sort_keys=True)

    def _get_hash(self):
        return get_hash(str(self)+"\n").hex()
    
