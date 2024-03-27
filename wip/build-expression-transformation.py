import sys
import seamless
from seamless.highlevel import Checksum
from seamless.core.manager.expression import Expression
from seamless.core.manager.tasks.evaluate_expression import build_expression_transformation

checksum = Checksum(sys.argv[1])
# WIP tool to re-evaluate expressions with run-transformation

path = []
celltype = "mixed"
target_celltype = "mixed"
hash_pattern = None
if "--deep" in sys.argv:
    hash_pattern = {"*": "#"}
target_hash_pattern = None

expression = Expression(
        checksum.bytes(), path, celltype,
        target_celltype, None,
        hash_pattern=hash_pattern, target_hash_pattern=target_hash_pattern
)
print(expression)       
expression_transformation = build_expression_transformation(expression)
print(expression_transformation.hex())
if len(sys.argv) > 2 and not sys.argv[-1].startswith("-"):
    from seamless.core.cache.buffer_cache import buffer_cache
    d = buffer_cache.get_buffer(expression_transformation)
    assert d is not None
    with open(sys.argv[-1], "wb") as f:
        f.write(d)
