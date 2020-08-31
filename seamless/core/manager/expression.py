import weakref
import json
from ...get_hash import get_hash
import numpy as np
from weakref import WeakValueDictionary

_expressions = WeakValueDictionary()

_hash_slots = [
    "_checksum",
    "_path",
    "_celltype",
    "_hash_pattern",
    "_target_celltype",
    "_target_subcelltype",
]
class Expression:
    __slots__ = [ "__weakref__", "exception"] + _hash_slots
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
        *, hash_pattern
    ):
        if hash_pattern is not None:
            assert celltype == "mixed"
        self._hash_pattern = hash_pattern
        self._checksum = checksum
        self._path = path
        self._celltype = celltype
        self._target_celltype = target_celltype
        self._target_subcelltype = target_subcelltype
        self.exception = None

    @property
    def checksum(self):
        return self._checksum

    @property
    def path(self):
        return self._path

    @property
    def celltype(self):
        return self._celltype

    @property
    def target_celltype(self):
        return self._target_celltype

    @property
    def target_subcelltype(self):
        return self._target_subcelltype

    @property
    def hash_pattern(self):
        return self._hash_pattern

    @property
    def result_hash_pattern(self):
        if self.target_celltype != "mixed":
            return None
        if self.hash_pattern is not None:
            validate_hash_pattern(self.hash_pattern)
        if self.path is None or not len(self.path):
            return self.hash_pattern
        ###  Code below will only work for simple hash patterns (see validate_hash_pattern)
        ###
        if self.hash_pattern is None:
            return None
        if len(self.path) == 1:
            return '#'
        elif len(self.path) > 1:
            return None
        ###

    def _hash_dict(self):
        d = {}
        for slot in _hash_slots:
            v = getattr(self, slot)
            if slot == "_checksum":
                if v is not None:
                    v = v.hex()
            d[slot] = v
        return d

    def __str__(self):
        d = self._hash_dict()
        return json.dumps(d, indent=2, sort_keys=True)

    def _get_hash(self):
        return get_hash(str(self)+"\n").hex()

from ..protocol.deep_structure import validate_hash_pattern