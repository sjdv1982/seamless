from seamless.highlevel import Context, Cell, Transformer

ctx = Context()
def calc_arr(period, npoints):
    import numpy as np
    points = np.arange(npoints)
    phase = points/period*np.pi*2
    return np.sin(phase)

ctx.period = 200
ctx.npoints = 1100
ctx.calc_arr = calc_arr
ctx.calc_arr.period = ctx.period
ctx.calc_arr.npoints = ctx.npoints
ctx.translate()
ctx.calc_arr.example = {}
ctx.calc_arr.example.period = 100
ctx.calc_arr.example.npoints = 200

c = ctx.calc_arr_schema = Cell()
c.celltype = "plain"
c.mount("/tmp/calc_arr_schema.json")
ctx.link(c, ctx.calc_arr.schema)

ctx.arr = ctx.calc_arr
###ctx.arr.celltype = "binary" # TODO: bug! => later
ctx.compute()
print(ctx.calc_arr.status)

"""
from matplotlib import pyplot as plt
plt.plot(ctx.arr.data)
plt.show()
"""

ctx.tf = lambda arr, fac, offset: 42
ctx.tf.arr = ctx.arr
ctx.tf.fac = 3
ctx.tf.offset = 12
ctx.tf.language = "cpp"
ctx.compute()
ctx.tf.example.set({})
ctx.tf.example.fac = 3
ctx.tf.example.offset = 12
ctx.compute()

print("\nSTEP 1\n")
print(ctx.tf.status)
print(ctx.tf.header.value)

ctx.header = ctx.tf.header

ctx.tf_schema = Cell()
ctx.tf_schema.celltype = "plain"
ctx.tf_schema.mount("/tmp/schema.json")
ctx.link(ctx.tf_schema, ctx.tf.schema)
ctx.tf_result_schema = Cell()
ctx.tf_result_schema.celltype = "plain"
ctx.tf_result_schema.mount("/tmp/result_schema.json")
ctx.link(ctx.tf_result_schema, ctx.tf.result.schema)
ctx.compute()

ctx.tf.example.arr = ctx.arr.value

print("\nSTEP 2\n")
ctx.compute()
print(ctx.tf.status)
ctx.tf.result.example.set(0)

print("\nSTEP 3\n")
ctx.compute()
print(ctx.tf.status)

print(ctx.header.value)

### Continue in interactive mode...
