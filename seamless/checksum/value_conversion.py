"""Machinery for conversions where the value of the input may be required
"""

import warnings
from typing import Coroutine
import numpy as np
from seamless import Buffer, Checksum, CacheMissError
from seamless.checksum.celltypes import text_types2
from seamless.checksum.cached_compile import analyze_code
from seamless.checksum.buffer_info import verify_buffer_info
from seamless.checksum.json import json_encode
from seamless.checksum.buffer_cache import buffer_cache
from seamless.checksum.get_buffer import get_buffer
from seamless.checksum.serialize import serialize
from seamless.checksum.conversion import conversion_values
from seamless.checksum.convert import (
    validate_checksum,
    validate_text,
    make_conversion_chain,
    try_convert,
    try_convert_single,
    SeamlessConversionError,
)

text_validation_celltype_cache = set()


def validate_text_celltype(text, checksum: Checksum, celltype: str):
    """Validate that 'text' is a valid value of 'celltype'.
    The checksum is provided for caching purposes."""
    assert celltype in text_types2
    checksum = Checksum(checksum)
    if checksum:
        if (checksum, celltype) in text_validation_celltype_cache:
            return
    validate_text(text, celltype, "value_conversion")
    if checksum:
        text_validation_celltype_cache.add((checksum, celltype))


def has_validated_evaluation(checksum: Checksum, celltype: str) -> bool:
    """Checks if a celltype has been validated to be a valid value of celltype"""
    checksum = Checksum(checksum)
    if not checksum:
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
    buffer_info = buffer_cache.get_buffer_info(
        checksum, sync_remote=False, buffer_from_remote=False, force_length=False
    )
    return verify_buffer_info(buffer_info, celltype)


text_subcelltype_validation_cache = set()


def has_validated_evaluation_subcelltype(
    checksum: Checksum, celltype: str, subcelltype: str
) -> bool:
    """Checks if a celltype has been validated to be a valid value of subcelltype"""
    checksum = Checksum(checksum)
    if not checksum:
        return True
    if subcelltype is None:
        return True
    if not has_validated_evaluation(checksum, celltype):
        # Should never happen
        return False
    if celltype != "python":
        return True
    if subcelltype not in ("reactor", "macro", "transformer"):
        return True
    key = (checksum, celltype, subcelltype)
    if key in text_subcelltype_validation_cache:
        return True
    return False


def validate_evaluation_subcelltype(
    checksum: Checksum,
    buffer: bytes,
    celltype: str,
    subcelltype: str,
    codename: str | None,
):
    """Validate that 'buffer' corresponds to a valid value of 'celltype'.
    A 'codename' can be provided for code buffers, to mark them with a
    temporary source code filename.
    The checksum is provided for caching purposes."""
    assert buffer is not None
    assert has_validated_evaluation(
        checksum, celltype
    ), celltype  # buffer_cache.guarantee_buffer_info(checksum, celltype) must have been called!
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
            err = "subcelltype '%s' does not support code mode '%s'" % (
                subcelltype,
                mode,
            )
            raise SyntaxError((codename, err))

    text_subcelltype_validation_cache.add(key)


async def conversion(
    checksum: Checksum,
    celltype: str,
    target_celltype: str,
    *,
    perform_fingertip: bool,
    value_conversion_callback: Coroutine | None = None,
    buffer: bytes | None = None
) -> Checksum:
    """Convert a checksum from 'celltype' to 'target_celltype'.

    If the underlying buffer is not supplied and not available,
      fingertipping may be performed.

    Unlike convert.try_convert, value conversions are supported.
    A callback coroutine for value conversions may be supplied; else,
     the default 'value_conversion' coroutine is used.

    Hash pattern (deep checksum) conversions are not supported,
     use an Expression + EvaluateExpressionTask for that.
    """
    if not checksum:
        return Checksum(None)
    if value_conversion_callback is None:
        value_conversion_callback = value_conversion
    if buffer is not None:
        buffer_cache.cache_buffer(checksum, buffer)
    result = try_convert(checksum, celltype, target_celltype)

    if isinstance(result, Checksum):
        buffer_cache.update_buffer_info_conversion(
            checksum, celltype, result, target_celltype, sync_remote=True
        )
        return result
    elif result == True:  # pylint: disable=singleton-comparison
        return checksum
    elif result == False:  # pylint: disable=singleton-comparison
        raise SeamlessConversionError("Checksum cannot be converted")

    buffer_info = None
    if not perform_fingertip:
        buffer_info = buffer_cache.get_buffer_info(
            checksum, sync_remote=True, buffer_from_remote=False, force_length=False
        )
    conv_chain = make_conversion_chain(celltype, target_celltype)

    curr_celltype = celltype
    curr_checksum = checksum
    for next_celltype in conv_chain:
        conv = (curr_celltype, next_celltype)
        result = try_convert_single(
            curr_checksum,
            curr_celltype,
            next_celltype,
            buffer_info=buffer_info,
            get_buffer_local=True,
        )
        if isinstance(result, Checksum):
            pass
        elif result == True:  # pylint: disable=singleton-comparison
            pass
        elif result is None or result == -1:
            if conv in conversion_values:
                result = await value_conversion_callback(
                    curr_checksum, curr_celltype, next_celltype
                )
            else:
                raise CacheMissError(curr_checksum)
        else:
            raise SeamlessConversionError("Unexpected conversion error")

        if isinstance(result, Checksum):
            buffer_cache.update_buffer_info_conversion(
                curr_checksum, curr_celltype, result, next_celltype, sync_remote=True
            )
            curr_checksum = result

        curr_celltype = next_celltype

    if isinstance(result, Checksum):
        return result
    elif result == True:  # pylint: disable=singleton-comparison
        return checksum
    else:
        raise SeamlessConversionError("Checksum cannot be converted")


async def value_conversion(
    checksum: Checksum, source_celltype: str, target_celltype: str
):
    """Reference implementation of value conversion
    Is used as the default callback coroutine in 'conversion'
    Does no heroic (i.e. fingertipping) efforts to get a buffer
    Does not use the Task system, so no fine-grained coalescence/cancellation"""
    checksum = Checksum(checksum)
    if target_celltype == "checksum":
        target_buffer = checksum.hex().encode()
        target_checksum = await Buffer(target_buffer).get_checksum_async()
        buffer_cache.cache_buffer(target_checksum, target_buffer)
        return target_checksum

    if source_celltype == "checksum":
        buffer = get_buffer(checksum, remote=True, deep=False)
        if buffer is None:
            raise CacheMissError(checksum)
        checksum_text = Checksum(buffer)
        validate_checksum(checksum_text)
        if not isinstance(checksum_text, str):
            if target_celltype == "plain":
                return checksum
            else:
                raise SeamlessConversionError(
                    "Cannot convert deep cell in value conversion"
                )
        # return try_convert(checksum, "bytes", target_celltype)
        #  # No, for now trust the "checksum" type
        return checksum

    buffer = get_buffer(checksum, remote=True, deep=False)
    if buffer is None:
        raise CacheMissError(checksum)
    msg = buffer
    if len(msg) > 1000:
        msg = msg[:920] + "..." + msg[-50:]
    source_value = await Buffer(buffer, checksum=checksum).deserialize_async(
        source_celltype, copy=False
    )
    conv = (source_celltype, target_celltype)
    try:
        if conv == ("binary", "plain"):
            target_value = json_encode(source_value)
        elif conv == ("plain", "binary"):
            try:
                if isinstance(source_value, (int, float, bool)):
                    target_value = np.array(source_value)
                    buffer_cache.update_buffer_info(
                        checksum, "is_json_numeric_scalar", True, sync_remote=True
                    )
                else:
                    if not isinstance(source_value, list):
                        raise ValueError(msg)
                    with warnings.catch_warnings():
                        warnings.simplefilter("ignore")
                        target_value = np.array(source_value)
                        if target_value.dtype == object:
                            raise ValueError(msg)
                    buffer_cache.update_buffer_info(
                        checksum, "is_json_numeric_array", True, sync_remote=True
                    )
            except ValueError as exc:
                buffer_cache.update_buffer_info(
                    checksum, "is_json_numeric_scalar", False, sync_remote=False
                )
                buffer_cache.update_buffer_info(
                    checksum, "is_json_numeric_array", False, sync_remote=True
                )
                raise exc from None
    except Exception as exc:
        msg0 = "%s cannot be converted from %s to %s"
        msg = msg0 % (checksum.hex(), source_celltype, target_celltype)
        full_msg = msg + "\n\nOriginal exception:\n\n" + str(exc)
        raise SeamlessConversionError(full_msg) from None
    target_buffer = await serialize(target_value, target_celltype)
    target_checksum = await Buffer(target_buffer).get_checksum_async()
    buffer_cache.cache_buffer(target_checksum, target_buffer)

    if conv == ("plain", "binary"):
        buffer_cache.update_buffer_info(
            target_checksum, "shape", target_value.shape, sync_remote=False
        )
        buffer_cache.update_buffer_info(
            target_checksum, "dtype", str(target_value.dtype), sync_remote=False
        )
        buffer_cache.update_buffer_info(
            target_checksum, "binary2json", checksum, sync_remote=False
        )
        buffer_cache.update_buffer_info(
            checksum, "json2binary", target_checksum, sync_remote=True
        )
    elif conv == ("binary", "plain"):
        buffer_cache.update_buffer_info(
            checksum, "binary2json", target_checksum, sync_remote=True
        )
        buffer_cache.update_buffer_info(
            target_checksum, "json2binary", checksum, sync_remote=False
        )

    buffer_cache.guarantee_buffer_info(
        target_checksum, target_celltype, sync_to_remote=True
    )
    return target_checksum
