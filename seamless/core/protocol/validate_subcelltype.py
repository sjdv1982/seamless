"""
- sets of (checksum, celltype, subcelltype)
Means that the value (deserialized from the buffer with the checksum using
  celltype) validates against subcelltype.
Meaningful values of (celltype, subcelltype):
("python", "transformer"/"reactor"/"macro").
"""
import ast
import json

validation_cache = set()

async def validate_subcelltype(checksum, celltype, subcelltype, codename):
    if celltype != "python":
        if celltype == "plain" and subcelltype == "module":
            pass
        else:
            return

    if codename is None:
        codename = "<Unknown>"
    key = (checksum, celltype, subcelltype)
    if key in validation_cache:
        return
    try:
        buffer = get_buffer(checksum)
    except CacheMissError:
        return # TODO: for now, tolerate cache misses. In the future, try to get validation cache remotely
    value = buffer.decode()

    if celltype == "plain" and subcelltype == "module":
        v = json.loads(value)
        await build_module_async(v)
    else:
        tree = ast.parse(value, filename=codename)

        if subcelltype in ("reactor", "macro"):
            mode, _ = analyze_code(value, codename)
            if mode in ("expression", "lambda"):
                err = "subcelltype '%s' does not support code mode '%s'" % (subcelltype, mode)
                raise SyntaxError((codename, err))

    validation_cache.add(key)

from .get_buffer import get_buffer, CacheMissError
from ..cached_compile import analyze_code
from ..build_module import build_module, build_module_async