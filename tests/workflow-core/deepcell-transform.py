import seamless

seamless.delegate(False)

from seamless.workflow.core import macro_mode_on
from seamless.workflow.core import context, cell, transformer
from seamless.checksum.json import json_dumps

with macro_mode_on():
    ctx = context(toplevel=True)
    ctx.d = cell("mixed", hash_pattern={"*": "#"})
    ctx.d.set({"a": 102, "b": 103})

    def func(d):
        result = {}
        for k, v in d.items():
            result[k] = v + 1000
        return result

    ctx.func = transformer(
        params={
            "d": {
                "io": "input",
                "celltype": "mixed",
                "hash_pattern": {"*": "#"},
            },
            "result": {
                "io": "output",
                "celltype": "mixed",
                "hash_pattern": {"*": "#"},
            },
        }
    )
    ctx.code = cell("python").set(func)
    ctx.code.connect(ctx.func.code)
    ctx.d.connect(ctx.func.d)
    ctx.result = cell("mixed", hash_pattern={"*": "#"})
    ctx.func.result.connect(ctx.result)

ctx.compute()
man = ctx._get_manager()
transformation = man.resolve(ctx.func.get_transformation_checksum(), "plain")
print(json_dumps(transformation))
print(ctx.d.data)
print(ctx.d.checksum)
print(transformation["d"][2])
print()
cs = man.cachemanager.transformer_to_result_checksum.get(ctx.func)
if cs:
    cs = cs.hex()
print(cs)
data = ctx._get_manager().resolve(cs, "plain") if cs else None
print(ctx.result.checksum)
print(data)
print(ctx.result.data)
