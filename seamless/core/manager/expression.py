from ...calculate_checksum import calculate_checksum
from weakref import WeakValueDictionary

_expressions = WeakValueDictionary()

_hash_slots = [
    "_checksum",
    "_path",
    "_celltype",
    "_hash_pattern",
    "_target_celltype",
    "_target_subcelltype",
    "_target_hash_pattern"
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
        *, hash_pattern, target_hash_pattern
    ):
        assert checksum is None or isinstance(checksum, bytes)
        if hash_pattern is not None:
            assert celltype == "mixed"
        self._hash_pattern = hash_pattern
        if target_hash_pattern is not None:
            assert target_celltype == "mixed"
        self._target_hash_pattern = target_hash_pattern
        self._checksum = checksum
        if path is None:
            path = ()
        if len(path):
            assert celltype in ("mixed", "plain", "binary")
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
    def target_hash_pattern(self):
        return self._target_hash_pattern

    @property
    def result_hash_pattern(self):
        return access_hash_pattern(self.hash_pattern, self.path)

    def _hash_dict(self):
        d = {}
        for slot in _hash_slots:
            if slot == "exception":
                continue
            v = getattr(self, slot)
            if slot == "_checksum":
                if v is not None:
                    v = v.hex()
            d[slot] = v
        return d

    def __str__(self):
        from seamless.core.protocol.json import json_dumps
        d = self._hash_dict()
        return json_dumps(d)

    def __repr__(self):
        return str(self)

    def _get_hash(self):
        return calculate_checksum(str(self)+"\n").hex()

from ..protocol.deep_structure import access_hash_pattern