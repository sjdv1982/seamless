import seamless

seamless.delegate(False)

from seamless.workflow.core import context, transformer, cell


def get_meta(tf):
    ctx = tf._root()
    tf_cache = ctx._get_manager().cachemanager.transformation_cache
    tf_checksum = tf_cache.transformer_to_transformations[tf]
    transformation = tf_cache.transformations[tf_checksum]
    meta = transformation["__meta__"]
    return meta


ctx = context(toplevel=True)
ctx.tf = transformer(
    {
        "a": {
            "io": "input",
            "celltype": "int",
        },
        "result": {
            "io": "output",
            "celltype": "int",
        },
    }
)


def tf(a):
    import time

    time.sleep(a)
    return a + 42


ctx.tf.code.cell().set(tf)
ctx.a = cell("int").set(1)
ctx.a.connect(ctx.tf.a)
ctx.tf.meta = {"calculation_time": "2s"}
ctx.result = cell("int")
ctx.tf.result.connect(ctx.result)
ctx.compute()
print(get_meta(ctx.tf))


def calc_meta(a):
    return {"calculation_time": "{:d}s".format(a)}


ctx.calc_meta = transformer(
    {
        "a": {
            "io": "input",
            "celltype": "int",
        },
        "result": {
            "io": "output",
            "celltype": "plain",
        },
    }
)
ctx.calc_meta.code.cell().set(calc_meta)
ctx.a.connect(ctx.calc_meta.a)
ctx.meta = cell("plain")
ctx.calc_meta.result.connect(ctx.meta)
ctx.compute()
print(ctx.meta.value)
ctx.meta.connect(ctx.tf.META)
ctx.compute()
print(get_meta(ctx.tf))

print("SET 4")
ctx.a.set(4)
ctx.compute()
print(ctx.meta.value)
print(get_meta(ctx.tf))
