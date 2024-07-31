import seamless
seamless.delegate(False)
from seamless.workflow import Context, Cell, Transformer
import numpy as np

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
c.mount("/tmp/calc_arr_schema.json", authority="cell")
ctx.link(c, ctx.calc_arr.schema)

ctx.arr = ctx.calc_arr
ctx.arr.celltype = "binary"
ctx.compute()
print(ctx.calc_arr.status)

"""
from matplotlib import pyplot as plt
plt.plot(ctx.arr.value)
plt.show()
"""

ctx.tf = lambda arr, fac, offset: 42
ctx.tf.arr = ctx.arr
ctx.tf.fac = 0.001
ctx.tf.offset = 50
ctx.tf.language = "cpp"
ctx.compute()
ctx.tf.example.set({})
ctx.tf.example.fac = 3.0
ctx.tf.example.offset = 12.0
ctx.compute()

print("\nSTEP 1\n")
print(ctx.tf.status)
print(ctx.tf.header.value)

ctx.header = ctx.tf.header
ctx.header.celltype = "text"

ctx.tf_schema = Cell()
ctx.tf_schema.celltype = "plain"
ctx.tf_schema.mount("/tmp/schema.json", authority="cell")
ctx.link(ctx.tf_schema, ctx.tf.schema)
ctx.tf_result_schema = Cell()
ctx.tf_result_schema.celltype = "plain"
ctx.tf_result_schema.mount("/tmp/result_schema.json", authority="cell")
ctx.link(ctx.tf_result_schema, ctx.tf.result.schema)
ctx.compute()

ctx.tf.example.arr = ctx.arr.value

print("\nSTEP 2\n")
ctx.compute()
print(ctx.tf.status)
print(ctx.tf.exception)
ctx.tf.result.example.set(np.zeros(10))
ctx.tf.result.schema["form"]["shape"] = [[0, 100000]]   # maximum result size

print("\nSTEP 3\n")
ctx.compute()
print(ctx.tf.status)
print(ctx.tf.exception)
print(ctx.header.value)

ctx.tf.code.mount("/tmp/code.cpp", authority="cell")
ctx.compute()
### Continue in interactive mode...


# Possible code: paste into /tmp/code.cpp

"""
typedef struct ArrStruct {
  const double *data;
  unsigned int shape[1];
} ArrStruct;

typedef struct ResultStruct {
  double *data;
  unsigned int shape[1];
} ResultStruct;

extern "C" int transform(const ArrStruct* arr, double fac, double offset, ResultStruct *result) {
    unsigned int npoints = arr->shape[0];
    result->shape[0] = npoints;
    const double *input = arr->data;
    double *output = result->data;
    for (int n = 0; n < npoints; n++) {
        output[n] = input[n] + fac * n + offset;
    }
    return 0;
}
"""

# Possible follow-up: open /tmp/plot.png

"""
def get_plot(arr):
    import numpy as np
    from matplotlib import pyplot as plt
    from io import BytesIO
    plt.plot(arr)
    result = BytesIO()
    plt.savefig(result)
    return result.getvalue()

ctx.get_plot = get_plot
ctx.result = ctx.tf.result
ctx.get_plot.arr = ctx.result
ctx.plot = ctx.get_plot.result
ctx.plot.celltype = "bytes"
ctx.plot.mount("/tmp/plot.png", mode="w")
ctx.compute()
"""

# Possible follow-up (2): open /tmp/schema.json and add ' "minimum": 0.002 ' for fac
