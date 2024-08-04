"""Seamless's implementation to convert from/to JSON
This is the basis of the "plain" celltype."""

import orjson


def json_encode(obj) -> str:
    """Encode as JSON, tolerating Numpy objects"""
    dump = orjson.dumps(obj, option=orjson.OPT_SERIALIZE_NUMPY)
    return dump.decode()


def json_dumps(obj, as_bytes: bool = False) -> str | bytes:
    """Encode as JSON, with two-space identation and sorted keys"""
    dump = orjson.dumps(obj, option=orjson.OPT_INDENT_2 | orjson.OPT_SORT_KEYS)
    if not as_bytes:
        dump = dump.decode()
    return dump
