import orjson

def json_encode(obj):
    dump = orjson.dumps(obj, option=orjson.OPT_SERIALIZE_NUMPY)
    return dump.decode()

def json_dumps(obj, as_bytes=False):
    dump = orjson.dumps(obj, option=orjson.OPT_INDENT_2 | orjson.OPT_SORT_KEYS)
    if not as_bytes:
        dump = dump.decode()
    return dump