import seamless
seamless.delegate(False)

from seamless.core import context, cell, transformer, macro, reactor, path
from seamless.core import macro_mode_on
with macro_mode_on():
    ctx = context(toplevel=True)
    ctx.header = cell("str").set("HEADER+")
    ctx.code = cell("str").set("CODE")
    ctx.tf_code = cell("transformer").set("'TRANSFORMER: ' + header + code")
    ctx.result = cell("str")
    ctx.tf = transformer({
        "header": "input",
        "code_": {
            "io": "input",
            "as": "code",
        },
        "result": "output"
    })
    ctx.header.connect(ctx.tf.header)
    ctx.code.connect(ctx.tf.code_)
    ctx.tf_code.connect(ctx.tf.code)
    ctx.tf.result.connect(ctx.result)

    ctx.macro = macro({
        "header": "str",
        "code_": {
            "celltype": "str",
            "as": "code",
        },
    })
    def run(ctx, code, header):
        ctx.result = cell("str").set("MACRO: " + header + code)
    ctx.macro.code.set(run)
    ctx.code.connect(ctx.macro.code_)
    ctx.header.connect(ctx.macro.header)
    ctx.result2 = cell("str")    
    mctx = path(ctx.macro.ctx)
    mctx.result.connect(ctx.result2)

    ctx.reactor = reactor({
        "header": "input",
        "code_": {
            "io": "input",
            "as": "code",
        },
        "result": "output"
    })
    ctx.code.connect(ctx.reactor.code_)
    ctx.header.connect(ctx.reactor.header)
    ctx.reactor.code_start.cell().set("")
    ctx.reactor.code_update.cell().set(
        "PINS.result.set('REACTOR: ' + PINS.header.value + PINS.code.value)"
    )
    ctx.reactor.code_stop.set("")
    ctx.result3 = cell("str")
    ctx.reactor.result.connect(ctx.result3)

ctx.compute()
print(ctx.tf.status)
print(ctx.tf.exception)
print(ctx.result.value)
print(ctx.macro.status)
print(ctx.macro.exception)
print(ctx.result2.value)
print(ctx.reactor.status)
print(ctx.reactor.exception)
print(ctx.result3.value)
