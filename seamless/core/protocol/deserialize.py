import json
from collections.abc import Container
import numpy as np

from .cson import cson2json
from ...get_hash import get_hash
from ...silk import Silk
from ...silk.validation import Scalar


def deserialize(
    celltype, value, from_buffer, 
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
            value, from_buffer,
            source_access_mode, source_content_type
        )
    else:
        raise NotImplementedError ### cache branch


def deserialize_plain(
    value, from_buffer, 
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
    
    buffer_checksum = get_hash(buffer, hex=False)
    semantic_checksum = buffer_checksum
    return buffer, buffer_checksum, obj, semantic_checksum
        
