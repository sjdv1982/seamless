import seamless
from seamless.core import macro_mode_on, context, cell
from seamless.midlevel.translate import translate
import math
import json

graph = [
    {
        "path": ("pi",),
        "type": "cell",
        "celltype": "structured",
        "datatype": "mixed",
        "silk": False,
        "buffered": False,
        "checksum": '9809b7dfcfe29dd194c71c7d2da94af3aeef98f079eeff8e1d9e5099acef737c',
        ###"value": math.pi,
        ###"schema": {'validators': [{'code': 'def validate(self):\n    assert self > 0\n', 'language': 'python'}]},
    },
    {
        "path": ("doubleit",),
        "type": "transformer",
        "language": "python",
        "pins": {"a":{"submode": "mixed"}},
        "code": None,
        "RESULT": "result",
        "INPUT": "inp",
        "SCHEMA": False,
        "with_schema": False,
        "with_result": False,
        "buffered": False,
        "plain": True,
        "plain_result": True,
        "compiled": False,  
        "debug": False,      
    },
    {
        "path": ("twopi",),
        "type": "cell",
        "celltype": "mixed",
        
        "silk": False,
        "buffered": False,
        ###"value": None,
        ###"schema": None,
    },
    {
        "path": ("code",),
        "type": "cell",
        "celltype": "code",
        "language": "python",        
        "transformer": True,
        ###"value": None,
    },
    {
        "type": "connection",
        "source": ("pi",),
        "target": ("doubleit", "a"),
    },
    {
        "type": "connection",
        "source": ("doubleit",),
        "target": ("twopi",),
    },
    {
        "type": "connection",
        "source": ("code",),
        "target": ("doubleit", "code"),
    },

]

ctx0 = context(toplevel=True)
ctx0.pi = cell("mixed").set(math.pi)

with macro_mode_on():
    ctx = context(toplevel=True, manager=ctx0._get_manager())    
    translate(graph, ctx, [], False)

print(ctx.pi)
print(ctx.pi.value)
ctx.code.set("result = a * 2")
ctx.equilibrate()
print(ctx.twopi.value)
