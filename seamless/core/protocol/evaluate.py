"""
There are three ways evaluations can be made in Seamless.
All three are wrapped by the manager (and Cell), which checks for 
  cache hits that make the entire evaluation superfluous.
1. A Python value is assigned to something directly
   This is taken care of by "deserialize". 
2. A tree is evaluated from the buffer
3. A tree is evaluated from the object

The following scenarios exist

- Command-line assignment to a cell: 
1. only.

- Command-line assignment to (part of) a StructuredCell:
Dealt with internally by StructuredCell.

- Inchannel assignment from outputpin:
A bit of a hybrid. First, the outputpin value is converted using 3.,
to either "silk", "mixed" or "plain" format (depending on the StructuredCell).
After that, the assignment is dealt with internally by StructuredCell, 
 in the same way as command-line assignment.

- Asking the value of a cell.
2. only. Never 3., because that would be a direct cache hit.

- Cell-cell connections (of the same type)
Same as asking for the value of a cell. Or, essentially, a no-op.
All cells with the same checksum(as stored in cell_cache) point to the same data.

- Cell-cell connections (of different types)
3. if there is a cache hit, 2. if not.
Note that "type" is essentially the combination of access mode and content type,
 not so much the cell type. But every cell type has a unique combination of those.

- Cell - inchannel connections
3. if there is a cache hit, 2. if not.

- Outchannel - cell connections
3. if there is a cache hit, 2. if not.
Note that if the StructuredCell has tree depth, the cache hits may be for individual outchannels

- Cell - inputpin connections
3. if there is a cache hit, 2. if not.

- Outputpin-cell and editpin-cell connections
3. only.

"""

from .deserialize import deserialize

def evaluate_from_buffer(tree, buffer):
    from ..cache import SemanticKey
    result = deserialize(
        tree.celltype, 
        buffer, from_buffer = True,
        source_access_mode = tree.source_access_mode,
        source_content_type = tree.source_content_type
    )
    _, _, obj, semantic_checksum = result
    if tree.subpath is not None:
        raise NotImplementedError
    else:
        semantic_key = SemanticKey(
            semantic_checksum, 
            tree.access_mode, 
            tree.content_type,
            None
        )
    return obj, semantic_key
