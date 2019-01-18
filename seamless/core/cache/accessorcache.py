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

class Accessor:
    __slots__ = [
        "cell_type",
        "storage_type",
        "cell_id",
        "subpath",
        "source_access_type", # optional
        "source_content_type" # optional
        "target_access_type", # optional
        "target_content_type" # optional
    ]
    def __init__(self):
        self.source_access_type = None
        self.source_content_type = None
        self.target_access_type = None
        self.target_content_type = None
    
class AccessorCache:
    
    def __init__(self, manager):
        self.manager = weakref.ref(manager)
        self.tree_to_buffer_checksum = {} # only for tree depth > 0
        self.tree_to_semantic_key = {}
        self.accessor_to_cells = {} # input accessor => list of output cellids