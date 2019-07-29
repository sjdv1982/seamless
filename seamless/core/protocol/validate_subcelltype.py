"""
- sets of (checksum, celltype, subcelltype)
Means that the value (deserialized from the buffer with the checksum using
  celltype) validates against subcelltype.
Meaningful values of (celltype, subcelltype):
("python", "transformer"/"reactor"/"macro").
"""
import ast

validation_cache = set()

async def validate_subcelltype(checksum, celltype, subcelltype, codename, value_cache):
    if celltype != "python":
        return
    key = (checksum, celltype, subcelltype)
    if key in validation_cache:
        return
    buffer = await get_buffer_async(checksum, value_cache)
    value = buffer.decode()
    
    tree = ast.parse(value, filename=codename)
    # TODO: => semantic checksum calculation
    ###dump = ast.dump(tree).encode("utf-8")
    ###semantic_checksum = get_hash(dump)

    if subcelltype in ("reactor", "macro"):
        mode, _ = analyze_code(value, codename)
        if mode in ("expression", "lambda"):
            err = "subcelltype '%s' does not support code mode '%s'" % (subcelltype, mode)
            raise SyntaxError((codename, err))

    validation_cache.add(key)
    
from .get_buffer import get_buffer_async
from ..cached_compile import analyze_code