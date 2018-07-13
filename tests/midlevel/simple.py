import seamless
from seamless.core import macro_mode_on, context
from seamless.midlevel.translate import translate
import math

tree = [
    {
        "path": ("pi",),
        "type": "cell",
        "celltype": "structured",
        "format": "mixed",
        "silk": True,
        "buffered": True,
        "value": math.pi,
        "schema": {'validators': [{'code': 'def validate(self):\n    assert self > 0\n', 'language': 'python'}]},
    },
    {
        "path": ("double",),
        "type": "transformer",
        "pins": {"a":{"submode": "silk"}},
        "RESULT": "result",
        "INPUT": "inp",
        "with_schema": False,
        "buffered": True,
        "plain": True,
        "plain_result": True,
    },
    {
        "path": ("twopi",),
        "type": "cell",
        "celltype": "json",
        "silk": False,
        "buffered": False,
        "value": None,
        "schema": None,
    },
    {
        "path": ("code",),
        "type": "cell",
        "celltype": "structured",
        "format": "mixed",
        "silk": True,
        "buffered": True,
        "value": None,
        "schema": None,
    },
    {
        "type": "connection",
        "source": ("pi",),
        "target": ("double", "a"),
    },
    {
        "type": "connection",
        "source": ("double",),
        "target": ("twopi",),
    },
    {
        "type": "connection",
        "source": ("code",),
        "target": ("double", "code"),
    },
]

with macro_mode_on():
    ctx = context(toplevel=True)
    translate(tree, ctx)

print(ctx.pi)
print(ctx.pi.value)
print(ctx.internal_children.double.inp.handle)
#print(ctx.internal_children.double.inp.handle.code)
ctx.code.set("result = a * 2")
print(ctx.internal_children.double.inp.handle)
ctx.equilibrate()
print(ctx.twopi.value)
