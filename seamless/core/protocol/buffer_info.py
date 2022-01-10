"""
contents of the buffer info:
- checksum
- buffer length: note that float, int, bool have a max length of 1000.
- is_utf8
- is_json: json.loads will work (implies is_utf8, not is_numpy, not is_seamless_mixed)
- json_type (dict, list, str, bool, float; implies is_json)
- is_json_array: homogeneous json array. implies json_type=list.
- is_numpy (implies not is_json, not is_seamless_mixed)
- dtype, shape (implies is_numpy)
- is_seamless_mixed (magic Seamless mixed string; implies not is_json, not is_numpy)
- "str2text" conversion field. If the buffer can be a text, stores its checksum-as-str
- "text2str" conversion field. If the buffer can be a str, stores its checksum-as-text
- "binary2bytes" conversion field (see below)
- "bytes2binary" conversion field (see below)
- "binary2json" conversion field. Result of ("binary", "plain") conversion.
- "json2binary" conversion field. Result of ("plain", "binary") conversion.
For conversions ("valid" means "preserves checksum". not valid means a failure):
- is_utf8: bytes to text is valid. otherwise, not valid.
- is_json: bytes/text/cson/yaml/mixed to plain is valid. otherwise, not valid.
- json_type: bytes/text/cson/yaml/mixed to that particular type is valid.
   otherwise, not valid for conversion-to-float/int/bool, unless str/float/int/bool
- is_json_array: conversion to Numpy array will work.
- is_numpy: mixed to binary is valid. Otherwise, not valid.
  if dtype is S and empty shape:
      bytes to mixed is valid. Otherwise (but is_numpy), reformat.
      Same for bytes to binary.
      Reformatted checksum can be stored under "binary2bytes" field
      This is just for caching, as this conversion is always valid.
- is_seamless_mixed:
   bytes to mixed is valid. Otherwise, (and not is_numpy, not is_json), invalid
- bytes2binary: gives the checksum of the np.dtype(S...) array corresponding to the bytes.
  This is just for caching, as this conversion is always valid.

buffer_info contains nothing about valid conversion to python/ipython/cson/yaml.
"""
class BufferInfo:
    __slots__ = (
        "checksum", "length", "is_utf8", "is_json", "json_type", "is_json_array",
        "is_numpy", "dtype", "shape", "is_seamless_mixed", 
        "str2text", "text2str", "binary2bytes", "bytes2binary",
        "binary2json", "json2binary"
    )
    def __init__(self, checksum, params:dict):
        for slot in self.__slots__:            
            setattr(self, slot, params.get(slot))
        self.checksum = checksum
    
    def __setattr__(self, attr, value):
        if value is not None:                
            if attr == "length":
                if not isinstance(value, int):
                    raise TypeError(type(value))
                if not value > 0:
                    raise ValueError
            if attr.startswith("is_"):
                if not isinstance(value, bool):
                    raise TypeError(type(value))
        super().__setattr__(attr, value)

def validate_buffer_info(buffer_info, celltype):
    """Raises an ValueError exception if buffer_info is incompatible with celltype"""
    self = buffer_info   
    if celltype == "bytes":
        pass
    elif celltype == "mixed":
        if self.is_json == False and self.is_numpy == False and self.is_seamless_dict == False:
            raise ValueError
    elif celltype == "binary":
        if self.is_json or self.is_seamless_dict:
            raise ValueError
    elif celltype in ("plain", "str", "int", "float", "bool"):
        if self.is_utf8 == False:
            raise ValueError
        if self.is_numpy or self.is_seamless_dict:
            raise ValueError
        if celltype != "plain":
          if self.json_type in ("dict", "list"):
              raise ValueError
    elif celltype in ("text", "cson", "yaml", "ipython", "python", "checksum"):
        if self.is_utf8 == False:
            raise ValueError
        if celltype == "checksum":
          if self.json_type in ("dict", "list", "int", "float", "bool"):
              raise ValueError
    
def conversion_from_buffer_info(buffer_info:BufferInfo, celltype:str, target_celltype:str):
    """Tries to convert using buffer info alone.
    Returns True if the conversion is possible and does not change checksum
    Returns the checksum (bytes format, not hex) if the checksum is different but
     stored in the buffer info
    Returns -1 is the conversion is surely possible, but the converted checksum is not known
    Return None if the conversion may or may not be possible
    Returns False the conversion is surely not possible
    Raises an ValueError exception if buffer_info may not have celltype at all
    """ 
    validate_buffer_info(buffer_info, celltype)
    conv = (celltype, target_celltype)

    if conv in conversion_equivalent:
        conv = conversion_equivalent[conv]
        celltype, target_celltype = conv

    self = buffer_info

    if conv in conversion_trivial:
        return True
    elif conv in conversion_forbidden:
        return False
    elif conv in conversion_values:
        if conv == ("binary", "plain"):
            if self.binary2json:
                return self.binary2json
            if self.is_json is not None:
                if self.is_json:
                    return -1
                return False
        elif conv == ("plain", "binary"):
            if self.json2binary:
                return self.json2binary
            if self.json_type is not None:
                if self.json_type == "dict":
                    return False
                elif self.json_type in ("int", "float", "bool"):
                    return -1
        return None
    if conv in conversion_chain:
        raise ValueError("Chained conversions must be handled upstream")
    
    if conv in conversion_reinterpret:
        try:
            validate_buffer_info(self, target_celltype)
        except ValueError:
            return False
        if target_celltype == "bytes":
            return True
        elif target_celltype == "mixed":
            if self.is_json or self.is_numpy or self.is_seamless_dict:
                return True
        elif target_celltype == "binary":
            if self.is_numpy:
                return True
        elif target_celltype in ("plain", "str", "int", "float", "bool"):
            if self.is_json:
                if target_celltype == "plain":
                    return True
                if target_celltype == self.json_type:
                    return True
        elif celltype == "text":
            if self.is_utf8:
                return True
        return None
    elif conv in conversion_possible:
        if target_celltype in ("int", "float", "bool"):
            if self.length > 1000:
                return False
        return None 
    elif conv in conversion_reformat:
        result = None  # -1
        if conv == ("bytes", "binary") or conv == ("bytes", "mixed"):
            if self.is_numpy:
                return True
            if conv == ("bytes", "mixed") and self.is_seamless_mixed:
                return True
            result = self.bytes2binary
        elif conv == ("binary", "bytes") or conv == ("mixed", "bytes"):
            if conv == ("mixed", "bytes") and self.is_numpy == False:
                return True
            if self.shape is not None:
                if self.shape not in ((),[]):
                    return True
            if self.dtype is not None:
                if self.dtype[0] != "S":
                    return True
            result = self.binary2bytes
        elif conv == ("plain", "text"):
            if self.json_type is not None:
                if self.json_type != "str":
                    return True
        elif conv == ("text", "plain"):
            if self.is_json:
                return True
        elif conv == ("text", "str"):
            result = self.text2str
        elif conv == ("str", "text"):
            result = self.str2text

        if result is None:
            result = -1
        elif isinstance(result, str):
            result = bytes.fromhex(result)
        return result
    else:
        raise AssertionError

        
from ..conversion import (
    conversion_trivial,
    conversion_reformat,
    conversion_reinterpret,
    conversion_possible,
    conversion_equivalent,
    conversion_chain,
    conversion_values,
    conversion_forbidden,
)