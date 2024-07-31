# Special pins are all-capital.
# They do not show up in the transformation dict over which the 
# transformation checksum is computed.
# Therefore, they are assumed not to influence the computation result

import traceback

import seamless
seamless.delegate(False)

from seamless.highlevel import Context

ctx = Context()

try:
    def func(WRONG, a, b):
        pass
    ctx.tf = func
except Exception:
    traceback.print_exc(limit=1)

def func(a, b):
    return 42

ctx.tf = func
try:
    ctx.tf.SPECIAL__WRONG = 12
    print("WRONG, should be an error! (1)")
    exit(1)
except Exception:
    traceback.print_exc(limit=1)

try:
    ctx.tf["SPECIAL__WRONG"] = 12
    print("WRONG, should be an error! (2)")
    exit(1)
except Exception:
    traceback.print_exc(limit=1)

ctx.translate()
try:
    ctx.tf.SPECIAL__WRONG = 12
    print("WRONG, should be an error! (3)")
    exit(1)
except Exception:
    traceback.print_exc(limit=1)

try:
    ctx.tf["SPECIAL__WRONG"] = 12
    print("WRONG, should be an error! (4)")
    exit(1)
except Exception:
    traceback.print_exc(limit=1)

try:
    ctx.tf.add_special_pin("nonsense", "bool")
    print("WRONG, should be an error! (5)")
except Exception:
    traceback.print_exc(limit=1)

ctx.tf.add_special_pin("SPECIAL__X", "str")
def func(a, b, SPECIAL__X):
    print("SPECIAL__X:", SPECIAL__X)
    return a + b
ctx.tf.code = func
ctx.tf.a = 3
ctx.tf.b = 4
ctx.compute()
print(ctx.status)
try:
    ctx.tf.SPECIAL__X = 12
    print("WRONG, should be an error! (6)")
    exit(1)
except Exception:
    traceback.print_exc(limit=1)

ctx.tf["SPECIAL__X"] = "This must be printed"
print("OK")
ctx.compute()
print(ctx.tf.logs)
print(ctx.tf.get_transformation_checksum())

ctx.tf["SPECIAL__X"] = "This must NOT be printed"
ctx.compute()
print(ctx.tf.logs)
print(ctx.tf.get_transformation_checksum())

print('Nothing printed')
ctx.tf["SPECIAL__X"] = "This will be printed IN THE END"
ctx.tf.debug.direct_print = True 
ctx.compute()
cs = ctx.tf.get_transformation_checksum()
print('/Nothing printed')

# remove transformation from cache
tf_cache = ctx._manager.cachemanager.transformation_cache
result_cs, _ = tf_cache.transformation_results.pop(bytes.fromhex(cs))
from seamless.core.cache.buffer_cache import buffer_cache
buffer_cache.decref(result_cs)

# re-run
ctx.translate(force=True)
ctx.compute()
print(ctx.tf.logs)
print("/logs")