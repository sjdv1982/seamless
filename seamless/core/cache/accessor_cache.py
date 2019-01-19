"""
Accessors are joint description of:
  cell + outchannel (if exists) + connection + inputpin/inchannel
Accessor param

Cell-to-cell connections also create an accessor
 (maintained as accessor_to_cells)
Outputpin-to-cell connections do not create an accessor. 
Transformers maintain a list of cells to which they write.
Reactors do the same, but then for every outputpin.

Accessors are converted to trees when the underlying cell changes.
This fills in the buffer checksum of the cell.
Normally, every cell change leads to conversion for all accessors.
But:
- Non-buffered, non-forked StructuredCells may report the path that has changed.
- some cells have a tree depth, which leads to higher granularity of buffer checksums
  (cell items are stored as simplified trees with their own buffer checksum)
"""

import weakref
import json
from collections import OrderedDict

from .tree_cache import Tree

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
    ]
    def __init__(self):
        self.subpath = None
        self.source_access_mode = None
        self.source_content_type = None

    def to_tree(self, buffer_checksum):
        tree = Tree()
        tree.celltype = self.celltype
        tree.storage_type = self.storage_type
        tree.buffer_checksum = buffer_checksum
        tree.access_mode = self.access_mode
        tree.content_type = self.content_type
        tree.source_access_mode = self.source_access_mode
        tree.source_content_type = self.source_content_type
        return tree
    
    def __str__(self):
        d = OrderedDict()
        for slot in self.__slots__:
            d[slot] = getattr(self, slot)
        d["cell"] = self.cell.path
        return json.dumps(d, indent=2)

    def __hash__(self):
        return hash(str(self))


class AccessorCache:
    
    def __init__(self, manager):
        self.manager = weakref.ref(manager)
        self.accessor_to_cells = {} # input accessor => list of output cellids
        self.accessor_to_workers = {} # input accessor => list of output worker IDs (input/edit pins)
