# pylint: disable=ungrouped-imports

"""Handles all conversions that can be done using checksum and buffer alone,
 i.e. without value conversion.
Conversions involving paths or hash patterns are also out-of-scope
"""

import ast
import builtins
import orjson
import numpy as np
import ruamel.yaml

from silk.mixed import MAGIC_NUMPY, MAGIC_SEAMLESS_MIXED

from seamless import Buffer, Checksum

from seamless.util.cson import cson2json
from seamless.util.ipython import ipython2python
from seamless.checksum.conversion import (
    conversion_trivial,
    conversion_reformat,
    conversion_reinterpret,
    conversion_possible,
    conversion_equivalent,
    conversion_chain,
    conversion_values,
    conversion_forbidden,
    SeamlessConversionError,
)
from seamless.checksum.buffer_info import convert_from_buffer_info
from seamless.checksum.buffer_cache import buffer_cache
from seamless.checksum.deserialize import deserialize_sync
from seamless.checksum.serialize import serialize_sync
from seamless.checksum.get_buffer import get_buffer

yaml = ruamel.yaml.YAML(typ="safe")


def validate_text(text: str, celltype: str, code_filename):
    """Validate that 'text' is a valid value of 'celltype'.
    A 'code_filename' can be provided for code buffers, to mark them with a
    temporary source code filename.
    """
    try:
        if text is None:
            return
        if celltype == "python":
            ast.parse(text, filename=code_filename)
        elif celltype == "ipython":
            ipython2python(text)
        elif celltype == "cson":
            cson2json(text)
        elif celltype == "yaml":
            yaml.load(text)
    except Exception:
        msg = text
        if len(text) > 1000:
            msg = text[:920] + "..." + text[-50:]
        raise ValueError(msg) from None


def validate_checksum(v):
    """Validate a checksum, list or dict recursively"""
    if isinstance(v, str):
        if len(v) != 64:
            msg = v
            if len(v) > 1000:
                msg = v[:920] + "..." + v[-50:]
            raise ValueError(msg)
        Checksum(v)
    elif isinstance(v, list):
        for vv in v:
            validate_checksum(vv)
    elif isinstance(v, dict):
        for vv in v.values():
            validate_checksum(vv)
    else:
        raise TypeError(type(v))


def make_conversion_chain(source_celltype, target_celltype):
    """Returns a chain of conversions to go from source to target celltype"""
    conv = (source_celltype, target_celltype)
    chain = []
    while conv in conversion_equivalent:
        conv = conversion_equivalent[conv]
        if conv[0] != source_celltype:
            source_celltype = conv[0]
            chain.append(source_celltype)
    if conv in conversion_chain:
        intermediate = conversion_chain[conv]
        chain += make_conversion_chain(source_celltype, intermediate)
        chain += make_conversion_chain(intermediate, target_celltype)
    else:
        chain.append(target_celltype)
    return chain


def try_convert(
    checksum, source_celltype, target_celltype, *, buffer=None, buffer_info=None
):
    """
    try_convert may return:
    True (trivial success)
    A checksum (success) (as Checksum object)
    -1 (future success)
    None (future success or failure)
    False (unconditional failure)
    An SeamlessConversionError is raised if a "reinterpret" or "possible" conversion fails
    """

    checksum = Checksum(checksum)
    if source_celltype == target_celltype:
        return checksum

    """
    Convert conversion to a chain of conversions. Iterate over each. 
    First don't pass on buffer (to quickly find undoable chains)
     and don't break on value conversion (again, to detect undoable steps after)
    Then, if None or -1, re-run with the buffer if there, and try to obtain the buffer.
    """
    conv_chain = make_conversion_chain(source_celltype, target_celltype)

    try_convert_params = (
        {"buffer": None, "buffer_info": None, "break_on_value": False},
        {
            "buffer": True,
            "buffer_info": buffer_info,
            "get_buffer_local": True,
            "break_on_value": True,
        },
        {
            "buffer": True,
            "buffer_info": buffer_info,
            "get_buffer_local": True,
            "get_buffer_remote": True,
            "break_on_value": True,
        },
    )

    for params in try_convert_params:
        curr_celltype = source_celltype
        curr_checksum = checksum
        curr_buffer = buffer
        for next_celltype in conv_chain:
            curr_params = params.copy()
            if curr_params["buffer"]:
                curr_params["buffer"] = curr_buffer
            break_on_value = curr_params.pop("break_on_value")
            result = try_convert_single(
                curr_checksum, curr_celltype, next_celltype, **curr_params
            )
            if isinstance(result, Checksum):
                curr_checksum = result
                curr_buffer = None
            elif result == True:  # pylint: disable=singleton-comparison
                pass
            elif result is None or result == -1:
                if break_on_value:
                    conv = (curr_celltype, next_celltype)
                    if conv in conversion_values:
                        return None
            elif result == False:  # pylint: disable=singleton-comparison
                return False

            curr_celltype = next_celltype

        if result is not None and result != -1:
            break

    return result


def try_convert_single(
    checksum,
    source_celltype,
    target_celltype,
    *,
    buffer=None,
    buffer_info=None,
    get_buffer_local=False,
    get_buffer_remote=False
):
    """ "Does a single step of a try_convert chain.
    Return values are the same as for try_convert"""

    conv = (source_celltype, target_celltype)

    if conv in conversion_equivalent:
        conv = conversion_equivalent[conv]
        source_celltype, target_celltype = conv

    if conv in conversion_chain:
        raise SeamlessConversionError("Chained conversions must be handled upstream")

    if buffer_info:
        result = convert_from_buffer_info(buffer_info, source_celltype, target_celltype)
        if result is not None and result != -1:
            return Checksum(result)
    else:
        if conv in conversion_trivial:
            return True
        elif conv in conversion_values:
            result = None
        elif conv in conversion_reinterpret or conv in conversion_possible:
            result = None
        elif conv in conversion_reformat:
            result = -1
        elif conv in conversion_forbidden:
            return False
        else:
            raise AssertionError(conv)

    if result is None:
        if conv in conversion_values:
            return None

    # "result" is now None or -1, and not a value conversion

    if buffer is None and (get_buffer_local or get_buffer_remote):
        buffer = get_buffer(checksum, remote=get_buffer_remote)
    if buffer is not None:
        result = _convert_from_buffer(
            checksum, buffer, source_celltype, target_celltype
        )

    if isinstance(result, bytes):
        result = Checksum(result)

    assert not isinstance(result, str)
    if isinstance(result, Checksum):
        buffer_cache.guarantee_buffer_info(result, target_celltype, sync_to_remote=True)
    return result


def _convert_reinterpret(checksum, buffer, target_celltype, *, source_celltype):
    # conversions that do not change checksum, but are not guaranteed to work (raise exception).
    exc = None
    if target_celltype == "binary":
        ok = buffer.startswith(MAGIC_NUMPY)
        buffer_cache.update_buffer_info(checksum, "is_numpy", ok, sync_remote=True)
        if not ok:
            exc = "Buffer is not a Numpy buffer"
    else:
        assert target_celltype in ("plain", "text", "python", "ipython", "cson", "yaml")
        try:
            text = buffer.decode().rstrip("\n")
            ok = True
        except Exception as exc0:
            exc = exc0
            ok = False
        buffer_cache.update_buffer_info(checksum, "is_utf8", ok, sync_remote=True)
        if ok:
            if target_celltype == "plain":
                try:
                    orjson.loads(text)
                    ok = True
                except Exception as exc0:
                    exc = exc0
                    ok = False
                buffer_cache.update_buffer_info(
                    checksum, "is_json", ok, sync_remote=True
                )
            else:
                validate_text(text, target_celltype, "convert_from_buffer")
    if ok:
        return checksum
    else:
        msg0 = "%s cannot be re-interpreted from %s to %s"
        msg = msg0 % (checksum.hex(), source_celltype, target_celltype)
        full_msg = msg + "\n\nOriginal exception:\n\n" + str(exc)
        raise SeamlessConversionError(full_msg) from None


def _convert_reformat(checksum, buffer, source_celltype, target_celltype):
    # conversions that are guaranteed to work (if the input is valid), but may change checksum
    target_buffer = None
    target_checksum = None
    conv_attr = None
    if target_celltype in ("int", "float", "bool") or (
        source_celltype in ("int", "float", "bool") and target_celltype == "str"
    ):
        source_value = deserialize_sync(buffer, checksum, source_celltype, copy=False)
        type_class = getattr(builtins, target_celltype)
        target_value = type_class(source_value)
    else:
        conv = (source_celltype, target_celltype)
        if conv == ("bytes", "binary") or conv == ("bytes", "mixed"):
            if buffer.startswith(MAGIC_NUMPY):
                buffer_cache.guarantee_buffer_info(
                    checksum, "binary", sync_to_remote=True
                )
                return checksum
            elif target_celltype == "mixed" and buffer.startswith(MAGIC_SEAMLESS_MIXED):
                buffer_cache.guarantee_buffer_info(
                    checksum, "mixed", sync_to_remote=True
                )
                return checksum
            else:
                target_value = None
                if target_celltype == "mixed":
                    try:
                        textvalue = deserialize_sync(
                            buffer, checksum, "text", copy=False
                        )
                        buffer_cache.guarantee_buffer_info(
                            checksum, "text", sync_to_remote=True
                        )
                        try:
                            deserialize_sync(buffer, checksum, "plain", copy=False)
                            buffer_cache.guarantee_buffer_info(
                                checksum, "plain", sync_to_remote=True
                            )
                            return checksum
                        except Exception:
                            target_buffer = serialize_sync(textvalue, "str")
                            target_checksum = Buffer(target_buffer).get_checksum()
                            conv_attr = ("text2str", "str2text")
                            buffer_cache.update_buffer_info(
                                checksum,
                                conv_attr[0],
                                target_checksum,
                                sync_remote=True,
                            )
                            buffer_cache.update_buffer_info(
                                target_checksum,
                                conv_attr[1],
                                checksum,
                                sync_remote=False,
                            )
                            buffer_cache.guarantee_buffer_info(
                                target_checksum, "str", sync_to_remote=True
                            )
                    except Exception:
                        pass

                if target_value is None:
                    # byte array
                    target_value = np.array(buffer)

        elif conv == ("binary", "bytes") or conv == ("mixed", "bytes"):
            if source_celltype == "binary" or buffer.startswith(MAGIC_NUMPY):
                source_value = deserialize_sync(buffer, checksum, "binary", copy=False)
                if source_value.dtype.char == "S":
                    target_buffer = source_value.tobytes()
                    assert target_buffer is not None
                conv_attr = ("binary2bytes", "bytes2binary")
            if target_buffer is None:
                return checksum
        elif conv == ("plain", "text"):
            source_value = deserialize_sync(
                buffer, checksum, source_celltype, copy=False
            )
            if isinstance(source_value, str):
                target_value = source_value
                conv_attr = ("str2text", "text2str")
            else:
                buffer_cache.guarantee_buffer_info(
                    checksum, target_celltype, sync_to_remote=True
                )
                return checksum
        elif conv == ("text", "plain"):
            try:
                deserialize_sync(buffer, checksum, "plain", copy=False)
                buffer_cache.guarantee_buffer_info(
                    checksum, target_celltype, sync_to_remote=True
                )
                return checksum
            except Exception:
                text = deserialize_sync(buffer, checksum, "text", copy=False)
                target_buffer = serialize_sync(text, "str")
                assert target_buffer is not None
                conv_attr = ("text2str", "str2text")
        elif conv == ("text", "str") or conv == ("str", "text"):
            target_value = deserialize_sync(
                buffer, checksum, source_celltype, copy=False
            )
            conv_attr = conv[0] + "2" + conv[1], conv[1] + "2" + conv[0]
        elif (
            conv == ("cson", "plain")
            or conv == ("yaml", "plain")
            or conv == ("ipython", "python")
        ):
            text = deserialize_sync(buffer, checksum, "text", copy=False)
            if source_celltype == "cson":
                target_value = cson2json(text)
            elif conv == ("ipython", "python"):
                target_value = ipython2python(text)
            else:  # yaml
                target_value = yaml.load(text)
        else:
            raise AssertionError
    if target_buffer is None:
        target_buffer = serialize_sync(target_value, target_celltype)
    target_checksum = Checksum(target_checksum)
    if not target_checksum:
        target_checksum = Buffer(target_buffer).get_checksum()
    buffer_cache.cache_buffer(target_checksum, target_buffer)
    if conv_attr is not None:
        buffer_cache.update_buffer_info(
            checksum, conv_attr[0], target_checksum, sync_remote=True
        )
        buffer_cache.update_buffer_info(
            target_checksum, conv_attr[1], checksum, sync_remote=False
        )
    buffer_cache.guarantee_buffer_info(
        target_checksum, target_celltype, sync_to_remote=True
    )
    return target_checksum


def _convert_possible(checksum, buffer, source_celltype, target_celltype):
    exc = None
    try:
        if (source_celltype, target_celltype) == ("mixed", "str"):
            if buffer.startswith(MAGIC_NUMPY):
                raise TypeError("Numpy format")
            if buffer.startswith(MAGIC_SEAMLESS_MIXED):
                raise TypeError("Seamless mixed buffer format")
        source_value = deserialize_sync(buffer, checksum, source_celltype, copy=False)
        if isinstance(source_value, (dict, list)):
            raise TypeError(type(source_value))
        elif isinstance(source_value, np.ndarray):
            if source_value.ndim:
                raise TypeError((type(source_value), source_value.ndim))
        type_class = getattr(builtins, target_celltype)
        target_value = type_class(source_value)
    except Exception as exc:
        msg0 = "%s cannot be converted from %s to %s"
        msg = msg0 % (checksum.hex(), source_celltype, target_celltype)
        full_msg = msg + "\n\nOriginal exception:\n\n" + str(exc)
        raise SeamlessConversionError(full_msg) from None

    target_buffer = serialize_sync(target_value, target_celltype)
    target_checksum = Buffer(target_buffer).get_checksum()
    buffer_cache.cache_buffer(target_checksum, target_buffer)
    buffer_cache.guarantee_buffer_info(
        target_checksum, target_celltype, sync_to_remote=True
    )
    return target_checksum


def _convert_from_buffer(checksum, buffer, source_celltype, target_celltype):
    if len(buffer) > 1000 and target_celltype in ("int", "float", "bool"):
        raise SeamlessConversionError("Buffer too long")
    conv = (source_celltype, target_celltype)
    if conv in conversion_reinterpret:
        return _convert_reinterpret(
            checksum, buffer, target_celltype, source_celltype=source_celltype
        )
    elif conv in conversion_reformat:
        return _convert_reformat(checksum, buffer, source_celltype, target_celltype)
    elif conv in conversion_possible:
        return _convert_possible(checksum, buffer, source_celltype, target_celltype)
    else:
        return None
