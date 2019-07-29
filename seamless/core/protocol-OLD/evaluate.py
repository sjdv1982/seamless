"""
TODO: adapt from old protocol.py.
BUT: Do not return adapter when negotiating source/target modes, simply fix the modes.
     Adapters will be invoked on-the-fly.

There are three ways evaluations can be made in Seamless.
All three are wrapped by the manager (and Cell), which checks for 
  cache hits that make the entire evaluation superfluous.
1. A Python value is assigned to something directly
   This is taken care of by "deserialize". 
2. A expression is evaluated from the buffer
3. A expression is evaluated from the object

The following scenarios exist:

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
Note that if the StructuredCell has expression depth, the cache hits may be for individual outchannels

- Cell - inputpin connections
3. if there is a cache hit, 2. if not.
2. is enforced if transfer_mode = "buffer"

- Outputpin-cell and editpin-cell connections
In principle, 3. only.
However: 
- 2. is enforced if the outputpin/editpin has transfer_mode = "buffer"
- 2. is an option since the buffer is computed anyway 
  (for the buffer checksum under which the results are cached in transform cache)
   [TODO: to think about...]

"""
import json

from .deserialize import deserialize
from ...mixed.io import to_stream, get_form, serialize
from ...get_hash import get_hash

def calc_buffer(value):
    storage, form = get_form(value)
    stream = serialize(value, storage=storage, form=form)
    if isinstance(stream, bytearray):
        stream = bytes(stream)
    return get_hash(stream), stream
    """
    if storage == "pure-plain":
        data = json.dumps(value).encode()
        return get_hash(data + b"\n"), data
    else:
        stream = to_stream(value, storage, form)
        if isinstance(stream, bytearray):
            stream = bytes(stream)
        else:
            stream 
        return get_hash(stream), stream
    """

def evaluate_from_buffer(expression, buffer):
    from ..cache import SemanticKey
    result = deserialize(
        expression.celltype, None, "random_code_path", #TODO
        buffer, from_buffer = True, buffer_checksum = expression.buffer_checksum,
        source_access_mode = expression.source_access_mode,
        source_content_type = expression.source_content_type
    )
    _, _, obj, semantic_obj, semantic_checksum = result
    if expression.access_mode is not None:
        if expression.access_mode == "text" and expression.celltype == "cson":
            semantic_obj = obj
        elif expression.access_mode == "module":
            semantic_obj = obj # build module later
        elif expression.celltype == "python":
            semantic_obj = obj
        
        # TODO
    if expression.celltype == "mixed":
        semantic_obj = semantic_obj[2]

    if expression.content_type is not None and expression.content_type != expression.celltype:
        pass # TODO?
    if expression.subpath is not None:
        try:                        
            result = semantic_obj
            for path in expression.subpath:
                result = result[path]
            result2 = deserialize(
                expression.celltype, None, "random_code_path", #TODO
                result, from_buffer = False, buffer_checksum = None,
                source_access_mode = expression.source_access_mode,
                source_content_type = expression.source_content_type
            )
            _, _, obj, semantic_obj, semantic_checksum = result2
            if expression.access_mode is not None:
                if expression.access_mode == "text" and expression.celltype == "cson":
                    semantic_obj = obj
                elif expression.access_mode == "module":
                    semantic_obj = obj # build module later
                elif expression.celltype == "python":
                    semantic_obj = obj
            #TODO
            if expression.celltype == "mixed":
                semantic_obj = semantic_obj[2]
            
        except Exception:
            ###if result is not None and result != {}:  ###TODO: dirty 
            ###    import traceback;traceback.print_exc()  ###TODO
            semantic_checksum = None
            semantic_obj = None
    semantic_key = SemanticKey(
        semantic_checksum, 
        expression.access_mode,
        None
    )
    return semantic_obj, semantic_key
