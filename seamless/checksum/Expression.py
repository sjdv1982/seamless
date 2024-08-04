"""Seamless Expression class"""

from weakref import WeakValueDictionary
import json

from seamless import Checksum, Buffer

_expressions = WeakValueDictionary()

_hash_slots = [
    "_checksum",
    "_path",
    "_celltype",
    "_hash_pattern",
    "_target_celltype",
    "_target_subcelltype",
    "_target_hash_pattern",
]


class Expression:
    """Seamless Expression class"""

    __slots__ = ["__weakref__", "exception"] + _hash_slots

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
        self,
        checksum: Checksum,
        path,
        celltype,
        target_celltype,
        target_subcelltype,
        *,
        hash_pattern,
        target_hash_pattern
    ):
        checksum = Checksum(checksum)
        if hash_pattern in ("", "#"):
            hash_pattern = None
        if hash_pattern is not None:
            assert celltype == "mixed", (hash_pattern, celltype)
        self._hash_pattern = hash_pattern
        if target_hash_pattern in ("", "#"):
            target_hash_pattern = None
        if target_hash_pattern is not None:
            assert target_celltype == "mixed", (hash_pattern, celltype)
        self._target_hash_pattern = target_hash_pattern
        self._checksum = checksum
        if path is None:
            path = ()
        if isinstance(path, str) and path.startswith("["):
            path = json.loads(path)
        if path == []:
            path = ()
        if len(path):
            assert celltype in ("mixed", "plain", "binary")
            path = tuple(path)
        self._path = path
        self._celltype = celltype
        self._target_celltype = target_celltype
        self._target_subcelltype = target_subcelltype
        self.exception = None

    @property
    def checksum(self) -> Checksum:
        """Return the origin checksum"""
        return self._checksum

    @property
    def path(self) -> tuple[str]:
        """Return the evaluation path"""
        return self._path

    @property
    def celltype(self) -> str:
        """Return the origin celltype"""
        return self._celltype

    @property
    def target_celltype(self) -> str:
        """Return the target celltype"""
        return self._target_celltype

    @property
    def target_subcelltype(self) -> str | None:
        """Return the target subcelltype"""
        return self._target_subcelltype

    @property
    def hash_pattern(self) -> dict[str, str] | None:
        """Return the origin checksum's hash pattern.
        Only deep checksums have a hash pattern."""
        return self._hash_pattern

    @property
    def target_hash_pattern(self):
        """Return the result checksum's hash pattern.
        This may or may not be the same as the "result hash pattern".
        Only deep checksums have a hash pattern."""
        return self._target_hash_pattern

    @property
    def result_hash_pattern(self):
        """Return the result hash pattern.
        This is obtained by applying the evaluation path on
        the origin checksum's hash pattern.
        This may or may not be the same as the target hash pattern.
        """
        from seamless.workflow.core.protocol.deep_structure import access_hash_pattern

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
        from seamless.checksum.json import json_dumps

        d = self._hash_dict()
        return json_dumps(d)

    def __repr__(self):
        return str(self)

    def _get_hash(self):
        strbuf = str(self) + "\n"
        return Buffer(strbuf.encode()).get_checksum()
