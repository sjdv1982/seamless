# Run this in Python, IPython, Jupyter.. to see if transformer print works well
import seamless
seamless.delegate(False)

from seamless.workflow import Context
from pprint import pprint

ctx = Context()

ctx.a = 12

def triple_it(a):
    print("RUN!")
    assert a > 0
    return 3 * a

ctx.transform = triple_it
ctx.transform.a = ctx.a
ctx.transform.debug.direct_print = True
print("START")
ctx.compute()
ctx.a = 20
ctx.compute()

# ctx.a = 22

# ctx.a = -2
