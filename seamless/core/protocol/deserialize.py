import json
import ast
from collections.abc import Container
import numpy as np
from io import BytesIO

from .cson import cson2json
from ...get_hash import get_hash
from ...silk import Silk
from ...silk.validation import Scalar
from ..cached_compile import cached_compile, analyze_code
from ...mixed.io import (
    deserialize as mixed_deserialize, serialize as mixed_serialize
)
from ...mixed.get_form import get_form

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
        elif celltype in ("plain", "mixed") or from_buffer:
            source_access_mode = celltype
        elif celltype == "cson":
            source_access_mode = "plain"
        elif isinstance(value, str):
            try:
                json.loads(value)
                source_access_mode = "plain"
            except:
                source_access_mode = "text"
        elif isinstance(value, (Scalar, Container)):
            source_access_mode = "plain"
        else:
            raise TypeError(type(value))

    if celltype == "plain":
        return deserialize_plain(
            value, from_buffer, buffer_checksum,
            source_access_mode, source_content_type
        )
    elif celltype == "text":
        return deserialize_text(
            value, from_buffer, buffer_checksum,
            source_access_mode, source_content_type
        )
    elif celltype  == "python":
        return deserialize_pythoncode(
            value, subcelltype, cellpath,
            from_buffer, buffer_checksum,
            source_access_mode, source_content_type
        )
    elif celltype == "cson":
        return deserialize_cson(
            value, from_buffer, buffer_checksum,
            source_access_mode, source_content_type
        )
    elif celltype == "mixed":
        return deserialize_mixed(
            value, from_buffer, buffer_checksum,
            source_access_mode, source_content_type
        )
    else:
        raise NotImplementedError(celltype) ### cache branch


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
            load_from_text = False
        else:
            load_from_text = True
    elif source_access_mode == "binary":
        if isinstance(value, np.ndtype):
            value = value.tolist()
            load_from_text = False
        else:
            raise TypeError(type(value))
    else:
        load_from_text = False
        
    if load_from_text:
        if isinstance(value, bytes):
            value = value.decode()
        buffer = str(value).rstrip("\n") + "\n"
        b = buffer.rstrip("\n")
        if source_access_mode != "text":            
            obj = json.loads(b)
        else:
            obj = b
    else:
        obj = value
        buffer = json.dumps(value) + "\n"
    
    if buffer_checksum is None:
        buffer_checksum = get_hash(buffer)
    semantic_checksum = buffer_checksum
    return buffer, buffer_checksum, obj, obj, semantic_checksum
        
def deserialize_pythoncode(
    value, subcelltype, cellpath, 
    from_buffer, buffer_checksum,
    source_access_mode, source_content_type
):
    if not from_buffer:
        value = str(value)

    if isinstance(value, bytes):
        value = value.decode()
    buffer = str(value).rstrip("\n") + "\n"
    if buffer_checksum is None:
        buffer_checksum = get_hash(buffer)

    tree = ast.parse(value)
    dump = ast.dump(tree).encode("utf-8")
    semantic_checksum = get_hash(dump)

    if subcelltype in ("reactor", "macro"):
        codename = ".".join(cellpath)
        mode, _ = analyze_code(value, codename)
        if mode in ("expr", "lambda"):
            err = "subcelltype '%s' does not support code mode '%s'" % (subcelltype, mode)
            raise SyntaxError((codename, err))

    return buffer, buffer_checksum, buffer, None, semantic_checksum    


def deserialize_text(
    value, 
    from_buffer, buffer_checksum,
    source_access_mode, source_content_type
):
    if source_access_mode in ("text", "python", "cson"):
        if from_buffer:
            value = value.rstrip("\n")
    elif source_access_mode == "binary":
        if isinstance(value, np.ndtype):
            value = value.tolist()
        else:
            raise TypeError(type(value))
    elif source_access_mode == "plain":        
        if from_buffer:
            value = str(json.loads(value.rstrip("\n")))
    else:
        raise TypeError(source_access_mode)
        
    if isinstance(value, bytes):
        value = value.decode()
    value = str(value)
    buffer = value.rstrip("\n") + "\n"

    if buffer_checksum is None:
        buffer_checksum = get_hash(buffer)
    semantic_checksum = buffer_checksum
    return buffer, buffer_checksum, value, value, semantic_checksum

def deserialize_cson(
    value, 
    from_buffer, buffer_checksum,
    source_access_mode, source_content_type
):
    if source_access_mode in ("text", "python", "cson"):
        pass
    elif source_access_mode == "plain":
        if from_buffer:
            value = json.dumps(value)
    else:
        raise TypeError(source_access_mode)
        
    if isinstance(value, bytes):
        value = value.decode()
    value = str(value)
    plainvalue = cson2json(value)
    plainbuffer = json.dumps(plainvalue).rstrip("\n") + "\n"
    buffer = value.rstrip("\n") + "\n"

    if buffer_checksum is None:
        buffer_checksum = get_hash(buffer)
    semantic_checksum = get_hash(plainbuffer)
    return buffer, buffer_checksum, value, plainvalue, semantic_checksum

def deserialize_mixed(
    value, 
    from_buffer, buffer_checksum,
    source_access_mode, source_content_type
):
    if source_access_mode == "text":
        data = value
        if source_content_type == "cson":
            data = cson2json(value)
        elif source_content_type == "plain":
            data = json.loads(value)
        storage, form = get_form(data)
    elif source_access_mode in ("binary", "plain"):
        if from_buffer:
            if source_access_mode == "binary":
                b = BytesIO(value)
                value = np.load(b)
            else:
                data = json.loads(value)
        else:
            data = value
        storage, form = get_form(data)
    elif source_access_mode == "mixed":        
        if from_buffer:
            data, storage, form = mixed_deserialize(value)
        else:
            storage, form, data = value
    else:
        raise ValueError(source_access_mode)

    buffer = None
    if from_buffer:
        if source_access_mode in ("mixed", "binary", "plain"):
            buffer = value
    if buffer is None and data is not None:
        buffer = mixed_serialize(data, storage=storage,form=form)
    if buffer_checksum is None:
        buffer_checksum = get_hash(buffer)

    obj = storage, form, data
    semantic_checksum = buffer_checksum
    return buffer, buffer_checksum, obj, obj, semantic_checksum
