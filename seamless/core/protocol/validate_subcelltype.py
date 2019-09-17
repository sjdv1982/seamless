"""
- sets of (checksum, celltype, subcelltype)
Means that the value (deserialized from the buffer with the checksum using
  celltype) validates against subcelltype.
Meaningful values of (celltype, subcelltype):
("python", "transformer"/"reactor"/"macro").
"""
import ast

validation_cache = set()

async def validate_subcelltype(checksum, celltype, subcelltype, codename, buffer_cache):    
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
    buffer = await get_buffer(checksum, buffer_cache)
    value = buffer.decode()
    
    if celltype == "plain" and subcelltype == "module":
        await build_module_async(value)
    else:    
        tree = ast.parse(value, filename=codename)

        if subcelltype in ("reactor", "macro"):
            mode, _ = analyze_code(value, codename)
            if mode in ("expression", "lambda"):
                err = "subcelltype '%s' does not support code mode '%s'" % (subcelltype, mode)
                raise SyntaxError((codename, err))

    validation_cache.add(key)
    
from .get_buffer import get_buffer
from ..cached_compile import analyze_code
from ..build_module import build_module