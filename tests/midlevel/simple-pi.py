raise NotImplementedError

import seamless
from seamless.core import macro_mode_on, context, cell
from seamless.midlevel.translate import translate
import math
import json

graph = {
    "nodes": [{
        "path": ("pi",),
        "type": "cell",
        "celltype": "structured",
        "datatype": "mixed",
        "silk": False,
        "buffered": False,
        "checksum": '9809b7dfcfe29dd194c71c7d2da94af3aeef98f079eeff8e1d9e5099acef737c',
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
        "compiled": False,  
        "debug": False,      
    },
    {
        "path": ("twopi",),
        "type": "cell",
        "celltype": "mixed",        
        "silk": False,
        "buffered": False,
        ###"schema": None,
    },
    {
        "path": ("code",),
        "type": "cell",
        "celltype": "code",
        "language": "python",        
        "transformer": True,
        "checksum": 'b0480c66eb4dbb31f5311e09e89b9414c880360842b9d5ef7b6621fc31a5ab99',
    }],
    "connections": [{
        "source": ("pi",),
        "target": ("doubleit", "a"),
    },
    {
        "source": ("doubleit",),
        "target": ("twopi",),
    },
    {
        "source": ("code",),
        "target": ("doubleit", "code"),
    }],
}

ctx0 = context(toplevel=True)
ctx0.pi = cell("mixed").set(math.pi)
assert ctx0.pi.checksum == '9809b7dfcfe29dd194c71c7d2da94af3aeef98f079eeff8e1d9e5099acef737c'
ctx0.code = cell("python").set("result = a * 2")
assert ctx0.code.checksum == 'b0480c66eb4dbb31f5311e09e89b9414c880360842b9d5ef7b6621fc31a5ab99'

with macro_mode_on():
    ctx = context(toplevel=True, manager=ctx0._get_manager())    
    translate(graph, ctx, [], False)

ctx.equilibrate()
print(ctx.twopi.value)
