"""
contents of the buffer info:
- checksum
- buffer length: note that float, int, bool have a max length of 1000.
- is_utf8
- is_json: json.loads will work (implies is_utf8, not is_numpy, not is_seamless_mixed)
- json_type (dict, list, str, bool, float; implies is_json)
- is_json_numeric_array: homogeneous numeric json array. implies json_type=list.
- is_json_numeric_scalar: conversion to int/float/bool will work. implies json_type=str/int/float/bool.
- is_numpy (implies not is_json, not is_seamless_mixed)
- dtype, shape (implies is_numpy)
- is_seamless_mixed (magic Seamless mixed string; implies not is_json, not is_numpy)
- "str2text" conversion field. If the buffer can be a str, stores its checksum-as-text
- "text2str" conversion field. If the buffer can be a text, stores its checksum-as-str
- "binary2bytes" conversion field (see below)
- "bytes2binary" conversion field (see below)
- "binary2json" conversion field. Result of ("binary", "plain") conversion.
- "json2binary" conversion field. Result of ("plain", "binary") conversion.
For conversions ("valid" means "preserves checksum". "not valid" means a failure. "possible" means "changes checksum"):
- is_utf8: bytes to text is valid. otherwise, not valid.
- is_json: bytes/text/cson/yaml/mixed to plain is valid. otherwise, not valid.
- json_type: bytes/text/cson/yaml/mixed to that particular type is valid.
   if "dict" or "list", conversion to str/int/float/bool is not valid. 
   otherwise, conversion to str is possible.
- is_json_numeric_scalar: conversion to int, float, bool is possible.  
- is_json_numeric_array: conversion to Numpy array is possible
- is_numpy: mixed to binary is valid. Otherwise, not valid.
  if dtype is S and empty shape:
      bytes to mixed is valid. Otherwise (but is_numpy), it is possible.
      Same for bytes to binary.
      Reformatted checksum can be stored under "binary2bytes" field
      This is just for caching, as this conversion is always possible.
- is_seamless_mixed:
   bytes to mixed is valid. Otherwise, (and not is_numpy, not is_json), invalid
- bytes2binary: gives the checksum of the np.dtype(S...) array corresponding to the bytes.
  This is just for caching, as this conversion is always possible.

buffer_info contains nothing about valid conversion to python/ipython/cson/yaml.
This is stored in evaluate.py:text_validation_celltype_cache
Likewise, nothing is stored about subcelltypes, this is also stored in evaluate.py
Finally, celltype "checksum" is out-of-scope for buffer info; validate this elsewhere.
"""
class BufferInfo:
    __slots__ = (
        "checksum", "length", "is_utf8", "is_json", "json_type", 
        "is_json_numeric_array", "is_json_numeric_scalar",
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

    def __setitem__(self, item, value):
        return setattr(self, item, value)

    def __getitem__(self, item):
        return getattr(self, item)

    def update(self, other):
        if not isinstance(other, BufferInfo):
            raise TypeError
        for attr in self.__slots__:
            v = getattr(other, attr)
            if v is not None:
                setattr(self, attr, v)
    
    def get(self, attr, default):
        value = getattr(self, attr)
        if value is None:
            return default
        else:
            return value

def validate_buffer_info(buffer_info:BufferInfo, celltype):
    """Raises an ValueError exception if buffer_info is certainly incompatible with celltype"""
    self = buffer_info   
    if celltype == "bytes":
        pass
    elif celltype == "checksum":
        # Not validated by buffer_info
        pass
    elif celltype == "mixed":
        if self.is_json == False and self.is_numpy == False and self.is_seamless_mixed == False:
            raise ValueError
    elif celltype == "binary":
        if self.is_json or self.is_seamless_mixed:
            raise ValueError
    elif celltype in ("plain", "str", "int", "float", "bool"):
        if self.is_utf8 == False:
            raise ValueError
        if self.is_numpy or self.is_seamless_mixed:
            raise ValueError
        if celltype != "plain":
            if self.json_type in ("dict", "list"):
                raise ValueError
            if celltype in ("int", "float", "bool"):
                if self.is_json_numeric_scalar == False:
                    raise ValueError
    elif celltype in ("text", "cson", "yaml", "ipython", "python", "checksum"):
        if self.is_utf8 == False:
            raise ValueError
        if celltype == "checksum":
          if self.json_type in ("dict", "list", "int", "float", "bool"):
              raise ValueError

def verify_buffer_info(buffer_info:BufferInfo, celltype:str):
    """Returns True if buffer_info is certainly compatible with celltype"""
    try:
        validate_buffer_info(buffer_info, celltype)
    except ValueError:
        return False
    self = buffer_info
    if celltype == "bytes":
        return True
    elif celltype == "checksum":
        # Not validated by buffer_info; return True
        return True
    elif celltype == "mixed":
        if self.is_json or self.is_numpy or self.is_seamless_mixed:
            return True
    elif celltype == "binary":
        if self.is_numpy:
            return True
    elif celltype in ("plain", "str", "int", "float", "bool"):
        if self.is_json:
            if celltype == "plain":
                return True
            if celltype == self.json_type:
                return True
            if celltype == "str":
                if self.json_type is not None:
                    if self.json_type not in ("list", "dict"):
                        return True
            if celltype in ("int", "float", "bool"):
                if self.is_json_numeric_scalar:
                    return True
    elif celltype == "text":
        if self.is_utf8:
            return True
    return False

def convert_from_buffer_info(buffer_info:BufferInfo, celltype:str, target_celltype:str):
    """Try to convert using buffer info alone.
    Return True if the conversion is possible and does not change checksum
    Return the checksum (bytes format, not hex) if the checksum is different but
     stored in the buffer info
    Return -1 if the conversion is surely possible, but the converted checksum is not known
    Return None if the conversion may or may not be possible
    Return False if the conversion is surely not possible
    Raise an SeamlessConversionError if buffer_info may not have source celltype at all
    """ 
    try:
        validate_buffer_info(buffer_info, celltype)
    except ValueError:
        raise SeamlessConversionError("source celltype is incompatible with buffer info") from None

    conv = (celltype, target_celltype)

    if conv in conversion_equivalent:
        conv = conversion_equivalent[conv]
        celltype, target_celltype = conv

    if conv in conversion_chain:
        raise SeamlessConversionError("Chained conversions must be handled upstream")

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
    elif conv in conversion_reinterpret:
        try:
            validate_buffer_info(self, target_celltype)
        except ValueError:
            return False
        if verify_buffer_info(self, target_celltype):
            return True
        return None
    elif conv in conversion_possible:
        if target_celltype in ("int", "float", "bool"):
            if self.length is not None and self.length > 1000:
                return False
            if self.is_json_numeric_scalar:
                return True
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
        elif target_celltype in ("float", "int", "bool"):
            if self.is_json_numeric_scalar:
                return True
        if result is None:
            result = -1
        elif isinstance(result, str):
            result = bytes.fromhex(result)
        return result
    else:
        raise AssertionError

        
from .conversion import (
    conversion_trivial,
    conversion_reformat,
    conversion_reinterpret,
    conversion_possible,
    conversion_equivalent,
    conversion_chain,
    conversion_values,
    conversion_forbidden,
    SeamlessConversionError
)