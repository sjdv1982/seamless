import numpy as np
import warnings

text_validation_celltype_cache = set()

def validate_text_celltype(text, checksum, celltype):
    assert celltype in text_types2
    if checksum is not None:
        if (checksum, celltype) in text_validation_celltype_cache:
            return
    validate_text(text, celltype, "evaluate")
    if checksum is not None:
        text_validation_celltype_cache.add((checksum, celltype))

def has_validated_evaluation(checksum, celltype):
    if checksum is None:
        return True
    if celltype == "bytes":
        return True
    if celltype == "checksum":
        return True  # celltype=checksum is never validated
    if celltype in ("ipython", "python", "cson", "yaml"):
        # parsability as IPython/python/cson/yaml is out-of-scope for buffer info
        celltype = "text"
    if (checksum, celltype) in text_validation_celltype_cache:
        return True
    buffer_info = buffer_cache.get_buffer_info(checksum, remote=False)
    if buffer_info is None:
        return False
    return verify_buffer_info(buffer_info, celltype)
        
text_subcelltype_validation_cache = set()

def has_validated_evaluation_subcelltype(checksum, celltype, subcelltype):
    if not has_validated_evaluation(checksum, celltype):
        # Should never happen
        return False
    if checksum is None:
        return True
    if celltype != "python":
        return True
    if subcelltype not in ("reactor", "macro", "transformer"):
        return True
    key = (checksum, celltype, subcelltype)
    if key in text_subcelltype_validation_cache:
        return True
    return False
        
def validate_evaluation_subcelltype(checksum, buffer, celltype, subcelltype, codename):
    assert buffer is not None
    assert has_validated_evaluation(checksum, celltype), celltype  # buffer_cache.guarantee_buffer_info(checksum, celltype) must have been called!
    if has_validated_evaluation_subcelltype(checksum, celltype, subcelltype):
        return
    if codename is None:
        codename = "<Unknown>"
    key = (checksum, celltype, subcelltype)
    value = buffer.decode()[:-1]

    mode, _ = analyze_code(value, codename)
    if subcelltype == "transformer":
        pass
    elif subcelltype in ("reactor", "macro"):
        if mode == "lambda":
            err = "subcelltype '%s' does not support code mode '%s'" % (subcelltype, mode)
            raise SyntaxError((codename, err))

    text_subcelltype_validation_cache.add(key)

async def conversion(
    checksum, celltype, target_celltype, 
    *, fingertip_mode, value_conversion_callback=None,buffer=None
):
    if checksum is None:
        return None
    if value_conversion_callback is None:
        value_conversion_callback = value_conversion
    if buffer is not None:
        buffer_cache.cache_buffer(checksum, buffer)
    result = try_convert(checksum, celltype, target_celltype)
    if result == True:
        return checksum
    elif isinstance(result, bytes):
        return result
    elif result == False:
        raise SeamlessConversionError("Checksum cannot be converted")

    buffer_info = None
    if not fingertip_mode:
        buffer_info = buffer_cache.get_buffer_info(checksum, force_length=False)
    conv_chain = make_conversion_chain(celltype, target_celltype)

    curr_celltype = celltype  
    curr_checksum = checksum 
    for next_celltype in conv_chain:
        conv = (curr_celltype, next_celltype)
        result = try_convert_single(
            curr_checksum, curr_celltype, next_celltype,
            buffer_info=buffer_info, get_buffer_local=True,
        )
        if result == True:
            pass
        elif isinstance(result, bytes):
            curr_checksum = result
        elif (result is None or result == -1):
            if conv in conversion_values:
                result = await value_conversion_callback(curr_checksum, curr_celltype, next_celltype)
            else:
                raise CacheMissError(curr_checksum.hex())
        else:
            raise SeamlessConversionError("Unexpected conversion error")

        curr_celltype = next_celltype

    if result == True:
        return checksum
    elif isinstance(result, bytes):
        return result
    else:
        raise SeamlessConversionError("Checksum cannot be converted")


async def value_conversion(checksum, source_celltype, target_celltype):
    """Reference implementation of value conversion
    Does no heroic (i.e. fingertipping) efforts to get a buffer
    Does not use the Task system, so no fine-grained coalescence/cancellation"""
    if target_celltype == "checksum":
        target_buffer = checksum.hex().encode()
        target_checksum = await calculate_checksum(target_buffer)
        buffer_cache.cache_buffer(target_checksum, target_buffer)
        return target_checksum

    if source_celltype == "checksum":
        buffer = buffer_cache.get_buffer(checksum)
        if buffer is None:
            raise CacheMissError(checksum)
        checksum_text = await deserialize(buffer, "checksum", copy=False)
        validate_checksum(checksum_text)
        if not isinstance(checksum_text, str):
            if target_celltype == "plain":
                return checksum
            else:
                raise SeamlessConversionError("Cannot convert deep cell in value conversion")
        checksum2 = bytes.fromhex(checksum_text)        
        #return try_convert(checksum2, "bytes", target_celltype) # No, for now trust the "checksum" type
        return checksum2

    buffer = buffer_cache.get_buffer(checksum)
    if buffer is None:
        raise CacheMissError(checksum)
    msg = buffer
    if len(msg) > 1000:
        msg = msg[:920] + "..." + msg[-50:]
    source_value = await deserialize(buffer, source_celltype, copy=False)
    conv = (source_celltype, target_celltype)
    try:
        if conv == ("binary", "plain"):
            target_value = json_encode(source_value)
        elif conv == ("plain", "binary"):
            try:
                if isinstance(source_value, (int, float, bool)):
                    target_value = np.array(source_value)
                    buffer_cache.update_buffer_info(checksum, "is_json_numeric_scalar", True)
                else:         
                    if not isinstance(source_value, list):
                        raise ValueError(msg)
                    with warnings.catch_warnings():
                        warnings.simplefilter("ignore")  
                        target_value = np.array(source_value)
                        if target_value.dtype == object:
                            raise ValueError(msg)
                    buffer_cache.update_buffer_info(checksum, "is_json_numeric_array", True)
            except ValueError as exc:
                buffer_cache.update_buffer_info(checksum, "is_json_numeric_scalar", False, update_remote=False)
                buffer_cache.update_buffer_info(checksum,"is_json_numeric_array", False)
                raise exc from None
    except Exception as exc:
        msg0 = "%s cannot be converted from %s to %s"
        msg = msg0 % (checksum.hex(), source_celltype, target_celltype)
        full_msg = msg + "\n\nOriginal exception:\n\n" + str(exc)
        raise SeamlessConversionError(full_msg) from None
    target_buffer = await serialize(target_value, target_celltype)
    target_checksum = await calculate_checksum(target_buffer)
    buffer_cache.cache_buffer(target_checksum, target_buffer)
    
    if conv == ("plain", "binary"):
        buffer_cache.update_buffer_info(target_checksum, "shape", target_value.shape, update_remote=False)
        buffer_cache.update_buffer_info(target_checksum, "dtype", str(target_value.dtype))
        buffer_cache.update_buffer_info(checksum, "json2binary", target_checksum)
        buffer_cache.update_buffer_info(target_checksum, "binary2json", checksum)
    elif conv == ("binary", "plain"): 
        buffer_cache.update_buffer_info(checksum, "binary2json", target_checksum)
        buffer_cache.update_buffer_info(target_checksum, "json2binary", checksum)

    buffer_cache.guarantee_buffer_info(target_checksum, target_celltype)
    return target_checksum
    

from ..convert import make_conversion_chain, try_convert, try_convert_single, SeamlessConversionError
from ..cache import CacheMissError
from ..cache.buffer_cache import buffer_cache
from ..cell import text_types2
from ..convert import validate_checksum, validate_text
from ..conversion import conversion_values
from ..cached_compile import analyze_code
from ..buffer_info import verify_buffer_info
from ..protocol.serialize import serialize
from ..protocol.deserialize import deserialize
from ..protocol.calculate_checksum import calculate_checksum
from ..protocol.json import json_encode
