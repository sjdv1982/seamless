import numpy as np
import warnings

text_validation_celltype_cache = set()

def validate_text_celltype(text, checksum, celltype):
    assert celltype in text_types2
    if (checksum, celltype) in text_validation_celltype_cache:
        return
    validate_text(text, celltype, "evaluate")
    text_validation_celltype_cache.add((checksum, celltype))

def has_validated_evaluation(checksum, celltype):
    if checksum is None:
        return True
    if celltype == "bytes":
        return True
    if celltype == "checksum":
        return True  # celltype=checksum is never validated
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
    assert has_validated_evaluation(checksum, celltype)  # buffer_cache.guarantee_buffer_info(checksum, celltype) must have been called!
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

async def conversion(checksum, celltype, target_celltype, value_conversion_callback=value_conversion):
    result = try_convert(checksum, celltype, target_celltype)
    if result == True:
        return checksum
    elif isinstance(result, bytes):
        return result
    elif result == False:
        raise SeamlessConversionError("Checksum cannot be converted")

    buffer_info = buffer_cache.get_buffer_info(checksum)
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
        elif (result is None or result == -1) and conv in conversion_values:
            result = await value_conversion_callback(curr_checksum, curr_celltype, next_celltype)
        else:
            raise SeamlessConversionError("Unexpected conversion error")

        curr_celltype = next_celltype

    return result

async def value_conversion(checksum, source_celltype, target_celltype):
    """Reference implementation of value conversion
    Does no heroic (i.e. fingertipping) efforts to get a buffer
    Does not use the Task system, so no fine-grained coalescence/cancellation"""
    if source_celltype == "checksum":
        buffer = buffer_cache.get_buffer(checksum)
        if buffer is None:
            raise CacheMissError(checksum)
        checksum_text = await deserialize(buffer, "plain", copy=False)
        validate_checksum(checksum_text)
        if not isinstance(checksum_text, str):
            raise SeamlessConversionError("Cannot convert deep cell in value conversion")
        checksum2 = bytes.fromhex(checksum_text)
        return try_convert(checksum2, "bytes", target_celltype)

    buffer = buffer_cache.get_buffer(checksum)
    if buffer is None:
        raise CacheMissError(checksum)
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
                        raise ValueError
                    with warnings.catch_warnings():
                        warnings.simplefilter("ignore")  
                        target_value = np.array(source_value)
                        if target_value.dtype == object:
                            raise ValueError
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

    buffer_cache.guarantee_buffer_info(target_checksum, target_celltype)
    return target_checksum
    
"""
TODO: evaluate_expression: 
copy and adapt from tasks/evaluate_expression.py. Copy back the value-based conversion (worst case, line 131)

All functions here are co-routines and require a cachemanager.

1. check if expression is completely trivial 
  (same celltype, same hash pattern, no path)
  if so, return
2.
- If source celltype is "checksum", get the value checksum, and consider source celltype = "bytes"
- Consider target celltype "checksum" as celltype "mixed" with target hash pattern = source hash pattern
- Define result hash pattern = source hash pattern with path applied
3. 
If path, result hash pattern and target hash pattern are all non-empty:
Check if result hash pattern is target hash pattern.
If this description succeeds, get the deep cell buffer and apply the path, and return the checksum directly.
4. 
Try to describe the expression as A => B => C:
A. Checksum + source hash pattern + path => result checksum + no source hash pattern + no path
B. convert result checksum to target checksum
C. encode target checksum using target hash pattern.  
If this description fails, a value-based conversion is needed.       
If this description succeeds:
Conversion is done in convert.py
The conversion may return True (trivial success), a checksum (success), False (unconditional failure),
or None/-1 (conditional failure). In case of conditional failure, a value-based conversion is needed.
5. Value-based conversion. 
Not done here, but in evaluate_expression, as a series of tasks.


"""

#raise NotImplementedError # TODO: rip below. 
# Only use validate_text_evaluation_cache, 
#  since for all others, successful deserialization means value validation!

'''
"""
Caches:
"""

"""
1: (deserialization)
- set of (checksum, celltype) tuples
=> means that the buffer with the checksum can be deserialized for "celltype"
"""
evaluation_cache_1 = set()

"""
2: (reinterpretation)
- set of (checksum, celltype, target_celltype) tuples
=> Means that the value (deserialized from the buffer with the checksum using
celltype) can be re-interpreted, without a change of checksum
For example: "2" (plain) can be interpreted as "2" (int), which have the same checksum.
"""

evaluation_cache_2 = set()

"""
3: (conversion)
- pairs of (checksum, celltype, target_celltype) => converted_checksum
=> Means that the value (deserialized from the buffer with the checksum using
celltype) can be converted to target_celltype , with a change in checksum.
For example: "'2'" (text) can be converted to "2" (int), but this has a different checksum.
"""
evaluation_cache_3 = {}

celltype_mapping = {
    "silk": "mixed",
    "transformer": "python",
    "reactor": "python",
    "macro": "python",
}

def needs_buffer_evaluation(checksum, celltype, target_celltype, fingertip_mode=False):
    celltype = celltype_mapping.get(celltype, celltype)
    target_celltype = celltype_mapping.get(target_celltype, target_celltype)
    raise NotImplementedError # conversion_chain, conversion_values
    # TODO: buffer_info!

    if celltype == target_celltype:
        return False
    if (checksum, celltype) not in evaluation_cache_1:
        # TODO: promotion
        # e.g. a buffer that correctly evaluates as plain, will also compute to mixed
        return True
    if (celltype, target_celltype) in conversion_equivalent:
        celltype, target_celltype = conversion_equivalent[celltype, target_celltype]
    if (celltype, target_celltype) in conversion_trivial:
        return False
    key = (checksum, celltype, target_celltype)
    if (celltype, target_celltype) in conversion_reinterpret:
        if fingertip_mode:
            return True
        return key not in evaluation_cache_2
    elif (celltype, target_celltype) in conversion_reformat:
        if fingertip_mode:
            return True
        return key not in evaluation_cache_3
    elif (celltype, target_celltype) in conversion_possible:
        if fingertip_mode:
            return True
        return key not in evaluation_cache_3
    elif (celltype, target_celltype) in conversion_forbidden:
        raise TypeError((celltype, target_celltype))
    else:
        raise TypeError((celltype, target_celltype)) # should never happen

async def evaluate_from_checksum(checksum, celltype, target_celltype):
    celltype = celltype_mapping.get(celltype, celltype)
    target_celltype = celltype_mapping.get(target_celltype, target_celltype)
    raise NotImplementedError # conversion_chain, conversion_values
    if celltype == target_celltype:
        return checksum
    assert (checksum, celltype) in evaluation_cache_1
    if (celltype, target_celltype) in conversion_equivalent:
        celltype, target_celltype = conversion_equivalent[celltype, target_celltype]
    if (celltype, target_celltype) in conversion_trivial:
        return checksum

    key = (checksum, celltype, target_celltype)
    if (celltype, target_celltype) in conversion_reinterpret:
        assert key in evaluation_cache_2
        return checksum
    elif (celltype, target_celltype) in conversion_reformat:
        return evaluation_cache_3[key]
    elif (celltype, target_celltype) in conversion_possible:
        return evaluation_cache_3[key]
    elif (celltype, target_celltype) in conversion_forbidden:
        raise TypeError((celltype, target_celltype))
    else:
        raise TypeError((celltype, target_celltype)) # should never happen

async def evaluate_from_buffer(checksum, buffer, celltype, target_celltype, fingertip_mode=False):
    celltype = celltype_mapping.get(celltype, celltype)
    target_celltype = celltype_mapping.get(target_celltype, target_celltype)
    raise NotImplementedError # conversion_chain, conversion_values
    if (celltype, target_celltype) in conversion_equivalent:
        celltype, target_celltype = conversion_equivalent[celltype, target_celltype]
    if celltype == target_celltype or (celltype, target_celltype) in conversion_trivial:
        if fingertip_mode:
            buffer_cache.cache_buffer(checksum, buffer)
        return checksum

    key = (checksum, celltype, target_celltype)
    if (celltype, target_celltype) in conversion_reinterpret:
        await reinterpret(checksum, buffer, celltype, target_celltype)
        evaluation_cache_2.add(key)
        if fingertip_mode:
            buffer_cache.cache_buffer(checksum, buffer)
        return checksum
    elif (celltype, target_celltype) in conversion_reformat:
        result = await reformat(checksum, buffer, celltype, target_celltype, fingertip_mode=fingertip_mode)
        evaluation_cache_3[key] = result
        return result
    elif (celltype, target_celltype) in conversion_possible:
        result = await convert(checksum, buffer, celltype, target_celltype, fingertip_mode=fingertip_mode)
        evaluation_cache_3[key] = result
        return result
    elif (celltype, target_celltype) in conversion_forbidden:
        raise TypeError((celltype, target_celltype))
    else:
        raise TypeError((celltype, target_celltype)) # should never happen
'''

from ..conversion import (
    SeamlessConversionError,
    conversion_trivial,
    conversion_reformat,
    conversion_reinterpret,
    conversion_possible,
    conversion_equivalent,
    conversion_chain,
    conversion_values,
    conversion_forbidden,
    ###reinterpret,
    ###reformat,
    ###convert
)

from ..convert import make_conversion_chain, try_convert, try_convert_single
from ..cache import CacheMissError
from ..cache.buffer_cache import buffer_cache
from ..cell import cell, text_types2
from ..convert import try_conversion, validate_checksum, validate_text
from ..cached_compile import analyze_code
from ..buffer_info import verify_buffer_info
from ..protocol.serialize import serialize
from ..protocol.deserialize import deserialize
from ..protocol.calculate_checksum import calculate_checksum
from ..protocol.json import json_encode
