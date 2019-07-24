import weakref
import json
from ...get_hash import get_hash

class Expression:
    __slots__ = [
        "checksum",
        "path",
        "celltype",
        "subcelltype",
    ]
    def __init__(self, checksum, path, celltype, subcelltype):
        self.checksum = checksum
        self.path = path
        self.celltype = celltype
        self.subcelltype = subcelltype

    def __str__(self):
        d = {}
        for slot in self.__slots__:
            v = getattr(self, slot)
            if slot == "checksum":
                if v is not None:
                    v = v.hex()
            d[slot] = v
        return json.dumps(d, indent=2, sort_keys=True)

    def __hash__(self):
        return hash(str(self))

    def get_hash(self):
        return get_hash(str(self)+"\n").hex()
    
