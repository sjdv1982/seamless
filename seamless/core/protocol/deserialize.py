import json
import ast
import inspect
from collections.abc import Container
import numpy as np

from .cson import cson2json
from ...get_hash import get_hash
from ...silk import Silk
from ...silk.validation import Scalar
from ..cached_compile import cached_compile, analyze_code
from ..utils import strip_source


def deserialize(
    celltype, subcelltype, cellpath,
    value, from_buffer, buffer_checksum,
    source_access_mode, source_content_type
):
    if source_access_mode is None:
        if isinstance(value, Silk):
            source_access_mode = "silk"
        elif isinstance(value, (np.void, np.ndarray)):
            source_access_mode = "binary"
        elif isinstance(value, (Scalar, Container)):
            source_access_mode = "plain"
        else:
            raise TypeError(type(value))

    if celltype == "plain":
        return deserialize_plain(
            value, from_buffer, buffer_checksum,
            source_access_mode, source_content_type
        )
    elif celltype  == "python":
        return deserialize_pythoncode(
            value, subcelltype, cellpath,
            from_buffer, buffer_checksum,
            source_access_mode, source_content_type
        )

    else:
        raise NotImplementedError ### cache branch


def deserialize_plain(
    value, 
    from_buffer, buffer_checksum,
    source_access_mode, source_content_type
):
    if from_buffer:
        load_from_text = True
    elif source_access_mode == "text":
        if source_content_type == "cson":
            value = cson2json(value)
        else:
            load_from_text = True
    elif source_access_mode == "binary":
        if isinstance(value, np.ndtype):
            value = value.tolist()
        else:
            raise TypeError(type(value))
    else:
        load_from_text = False
        
    if load_from_text:    
        buffer = str(value).rstrip("\n") + "\n"
        obj = json.loads(buffer)        
    else:
        obj = value
        buffer = json.dumps(value).rstrip("\n") + "\n"
    
    if buffer_checksum is None:
        buffer_checksum = get_hash(buffer)
    semantic_checksum = buffer_checksum
    return buffer, buffer_checksum, obj, semantic_checksum
        
def deserialize_pythoncode(
    value, subcelltype, codename, 
    from_buffer, buffer_checksum,
    source_access_mode, source_content_type
):
    if not from_buffer:
        if inspect.isfunction(value):
            code = inspect.getsource(value)
            code = strip_source(code)
            value = code
        value = str(value)

    buffer = value.rstrip("\n") + "\n"
    if buffer_checksum is None:
        buffer_checksum = get_hash(buffer)

    tree = ast.parse(value)
    dump = ast.dump(tree).encode("utf-8")
    semantic_checksum = get_hash(dump)

    if subcelltype in ("reactor", "macro"):
        mode, _ = analyze_code(code, codename)
        if mode in ("expr", "lambda"):
            err = "subcelltype '%s' does not support code mode '%s'" % (subcelltype, mode)
            raise SyntaxError((codename, err))

    return buffer, buffer_checksum, buffer, semantic_checksum    
