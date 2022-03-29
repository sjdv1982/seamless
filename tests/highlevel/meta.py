from seamless.highlevel import Context
import json

def get_meta(tf):
    from seamless.core.protocol.get_buffer import get_buffer
    ctx = tf._root()
    tf_cache = ctx._get_manager().cachemanager.transformation_cache
    tf_checksum = tf_cache.transformer_to_transformations[tf]
    transformation = tf_cache.transformations[tf_checksum]
    meta_checksum = transformation["__meta__"]
    meta = json.loads(get_buffer(meta_checksum,remote=True))
    return meta

ctx = Context()
def func(a):
    return a
ctx.func = func
ctx.a = 10
ctx.func.a = ctx.a
ctx.compute()
print(get_meta(ctx.func._get_tf().tf)) 

ctx.func.meta = {"somekey": "somevalue"}
ctx.a += 1 # else, there will be no new transformation...
ctx.compute()
print(get_meta(ctx.func._get_tf().tf)) 

def calc_meta():
    return {"calculated meta": 42}
ctx.calc_meta = calc_meta
ctx.meta = ctx.calc_meta.result
ctx.func.meta = ctx.meta
ctx.a += 1 # else, there will be no new transformation...
ctx.compute()
print(get_meta(ctx.func._get_tf().tf)) 

ctx.func.language = "bash"
ctx.func.meta = {"somekey": "somevalue2"}
ctx.func.code = "echo $a > RESULT"
ctx.compute()
print(get_meta(ctx.func._get_tf().tf)) 
print(ctx.func.exception)
print(ctx.func.result.value)

ctx.func.meta = ctx.meta
ctx.a += 1 # else, there will be no new transformation...
ctx.compute()
print(get_meta(ctx.func._get_tf().tf)) 

ctx.func.language = "c"
ctx.func.meta = {"somekey": "somevalue3"}
ctx.translate()
ctx.func.example.a = 0
ctx.func.result.example.set(0)
ctx.func.code = "int transform(int a, int *result){*result = 1000 + a; return 0;}"
ctx.compute()
print(get_meta(ctx.func._get_tf().tf.executor)) 
print(ctx.func.exception)
print(ctx.func.result.value)

ctx.func.meta = ctx.meta
ctx.a += 1 # else, there will be no new transformation...
ctx.compute()
print(get_meta(ctx.func._get_tf().tf.executor)) 
