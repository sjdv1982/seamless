import weakref
import json
from ...get_hash import get_hash
import numpy as np

class Expression:
    __slots__ = [
        "checksum",
        "path",
        "celltype",
        "target_celltype",
        "target_subcelltype",
        "target_cell_path",
    ]
    def __init__(
        self, checksum, path, celltype, 
        target_celltype, target_subcelltype,
        *, target_cell_path=None
    ):
        self.checksum = checksum
        self.path = path
        self.celltype = celltype
        self.target_celltype = target_celltype
        self.target_subcelltype = target_subcelltype
        self.target_cell_path = target_cell_path   

    def __str__(self):
        d = {}
        for slot in self.__slots__:
            v = getattr(self, slot)
            if slot == "target_cell_path":
                continue
            if slot == "checksum":
                if v is not None:
                    v = v.hex()
            d[slot] = v
        return json.dumps(d, indent=2, sort_keys=True)

    def __hash__(self):
        checksum = get_hash(str(self)+"\n")
        return int(np.frombuffer(checksum, int)[0])

    def get_hash(self):
        return get_hash(str(self)+"\n").hex()
    
