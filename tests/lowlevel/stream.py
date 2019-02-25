from seamless.core import context, cell, transformer

ctx = context(toplevel=True)
ctx.a = cell().set([10, 20, 50, 100, 200])
def triple_it(aa):
    return 3 * aa
ctx.code = cell("python").set(triple_it)    
tf_params = {"aa": "input", "result": "output"}
stream_params = {"aa": "map"}
ctx.tf = transformer(tf_params, stream_params)
ctx.code.connect(ctx.tf.code)
ctx.a.connect(ctx.tf.aa)
ctx.result = cell()
ctx.tf.result.connect(ctx.result)

ctx.equilibrate()
print(ctx.result.value)

ctx.a.set({"first": 1, "second": 2, "third": 3})
ctx.equilibrate()
print(ctx.result.value)
