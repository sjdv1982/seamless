"""
Accessors are joint description of:
  cell + outchannel (if exists) + connection + inputpin/inchannel
Accessor param

Cell-to-cell connections do not create an accessor (TODO?)
Outputpin-to-cell connections do not create an accessor. 
Transformers maintain a list of cells to which they write.
Reactors do the same, but then for every outputpin.

Accessors are converted to expressions when the underlying cell changes.
This fills in the buffer checksum of the cell.
Normally, every cell change leads to conversion for all accessors.
But:
- Non-buffered, non-forked StructuredCells may report the path that has changed.
- some cells have a expression depth, which leads to higher granularity of buffer checksums
  (cell items are stored as simplified expressions with their own buffer checksum)
"""

import weakref
import json
from collections import OrderedDict

from .expression import Expression

class Accessor:
    __slots__ = [
        "celltype",
        "storage_type",
        "cell",
        "subpath", # optional
        "access_mode",
        "content_type",
        "source_access_mode", # optional
        "source_content_type", # optional
        "last_buffer_checksum", # optional
    ]
    def __init__(self):
        self.subpath = None
        self.source_access_mode = None
        self.source_content_type = None
        self.last_buffer_checksum = None

    def to_expression(self, buffer_checksum):
        expression = Expression()
        expression.celltype = self.celltype
        expression.storage_type = self.storage_type
        expression.buffer_checksum = buffer_checksum
        expression.subpath = self.subpath
        expression.access_mode = self.access_mode
        expression.content_type = self.content_type
        expression.source_access_mode = self.source_access_mode
        expression.source_content_type = self.source_content_type
        self.last_buffer_checksum = buffer_checksum
        return expression
    
    def __str__(self):
        d = OrderedDict()
        for slot in self.__slots__:
            d[slot] = getattr(self, slot)
        d["cell"] = self.cell.path
        return json.dumps(d, indent=2)

    def __hash__(self):
        # Hash is NOT unique! useful for haccessor bucketing
        return hash((self.celltype, self.storage_type, self.cell.path, self.subpath))


class AccessorCache:
    
    def __init__(self, manager):
        self.manager = weakref.ref(manager)
        self.haccessor_to_workers = {} # hash of input accessor => list of output workers