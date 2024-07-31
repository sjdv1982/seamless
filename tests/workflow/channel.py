import seamless
seamless.delegate(False)

from seamless.workflow import Context
from seamless.highlevel import stdlib

ctx = Context()
ctx.include(stdlib.channel)

ctx.channel = (ctx.lib.channel()
    .fromList([10, 17, 12, 9, 30, 2, 27])
    .filter("lambda it: it >= 10")
)
ctx.result = ctx.channel.result
ctx.compute()
print(ctx.result.value)
ctx.channel.first(lambda it: str(it)[0] == "3")
ctx.compute()
print(ctx.result.value)
