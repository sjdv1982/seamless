"""Utilities specific for workflows"""

import json
from multiprocessing import current_process

from seamless import Checksum

try:
    from multiprocessing import parent_process
except ImportError:
    parent_process = None


def as_tuple(v):
    """Cast a string or to a one-member tuple.
    Cast a list to a tuple."""
    if isinstance(v, str):
        return (v,)
    else:
        return tuple(v)


_unforked_process_name = None


def set_unforked_process():
    """Sets the current process as the unforked Seamless process"""
    global _unforked_process_name
    _unforked_process_name = current_process().name


def is_forked() -> bool:
    """Are we running in a forked process?"""
    if _unforked_process_name:
        if current_process().name != _unforked_process_name:
            return True
    else:
        if parent_process() is not None:  # forked process
            return True
    return False


def verify_transformation_success(
    transformation_checksum: Checksum, transformation_dict=None
):
    from seamless.checksum.database_client import database
    from seamless.checksum.buffer_cache import buffer_cache
    from seamless.checksum import Expression

    assert database.active
    transformation_checksum = Checksum(transformation_checksum)
    if not transformation_checksum:
        return None
    tf_checksum = Checksum(transformation_checksum)
    if transformation_dict is None:
        tf_buffer = buffer_cache.get_buffer(tf_checksum.hex())
        if tf_buffer is None:
            return None

        transformation_dict = json.loads(tf_buffer.decode())
    assert isinstance(transformation_dict, dict)
    language = transformation_dict["__language__"]
    if language == "<expression>":
        expression_dict = transformation_dict["expression"]
        d = expression_dict.copy()
        d["target_subcelltype"] = None
        d["hash_pattern"] = d.get("hash_pattern")
        d["target_hash_pattern"] = d.get("target_hash_pattern")
        d["checksum"] = bytes.fromhex(d["checksum"])
        expression = Expression(**d)
        # print("LOOK FOR EXPRESSION", expression.checksum.hex(), expression.path)
        result = database.get_expression(expression)
        # print("/LOOK FOR EXPRESSION", expression.checksum.hex(), expression.path, parse_checksum(result) )
        return result
    elif language == "<structured_cell_join>":
        join_dict = transformation_dict["structured_cell_join"].copy()
        inchannels0 = join_dict.get("inchannels", {})
        inchannels = {}
        for path0, cs in inchannels0.items():
            path = json.loads(path0)
            if isinstance(path, list):
                path = tuple(path)
            inchannels[path] = cs

        # print("LOOK FOR SCELL JOIN", calculate_dict_checksum(join_dict,hex=True))
        result = database.get_structured_cell_join(join_dict)
        # print("/LOOK FOR SCELL JOIN", calculate_dict_checksum(join_dict,hex=True), parse_checksum(result))
        return result
    else:
        # print("LOOK FOR TRANSFORMATION", tf_checksum)
        result = database.get_transformation_result(tf_checksum.bytes())
        # print("/LOOK FOR TRANSFORMATION", tf_checksum)
        return result
