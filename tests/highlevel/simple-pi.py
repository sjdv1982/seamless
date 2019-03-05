import math
from seamless.highlevel import Context, Cell
import json
from pprint import pprint
ctx = Context()
ctx.pi = math.pi
ctx.pi._get_hcell()["silk"] = False
ctx.pi._get_hcell()["buffered"] = False
ctx.doubleit = lambda a: 2 * a
ctx.doubleit._get_htf()["plain"] = True
ctx.doubleit._get_htf()["buffered"] = False
ctx.doubleit._get_htf()["with_result"] = False
ctx.doubleit.a = ctx.pi
ctx.twopi = ctx.doubleit
ctx.twopi._get_hcell()["silk"] = False
ctx.twopi._get_hcell()["buffered"] = False
ctx.translate()


ctx.equilibrate()
print(ctx.pi.value)
print(ctx.twopi.value)

ctx.doubleit.code = lambda a: 42
ctx.equilibrate()
print(ctx.pi.value)
print(ctx.twopi.value)

ctx.translate(force=True)
ctx.equilibrate()
print(ctx.pi.value)
print(ctx.twopi.value)
print()

ctx.doubleit.code = lambda a: 2 * a
ctx.equilibrate()
print(ctx.pi.value)
print(ctx.twopi.value)