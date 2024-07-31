import seamless
seamless.delegate(False)

from seamless.workflow import Context
from seamless.library import LibraryContainer
from pprint import pprint

lib = LibraryContainer("lib")

subctx = Context()
subctx.x = 20
subctx.y = 5
subctx.minus = lambda x,y: x - y
subctx.minus.x = subctx.x
subctx.minus.y = subctx.y
subctx.result = subctx.minus
subctx.compute()
print(subctx.result.value)

#  Simplified version of lib.instantiate
lib.instantiate0 = Context()
def constructor(ctx, libctx, context_graph, copies):
    for n in range(copies):
        name = "copy{}".format(n+1)
        subctx = Context()
        subctx.set_graph(context_graph)
        setattr(ctx, name, subctx)
lib.instantiate0.constructor = constructor
lib.instantiate0.params = {
    "copies": "value",
    "context_graph": "context"
}

ctx = Context()
ctx.subcontext = subctx
ctx.include(lib.instantiate0)
ctx.inst = ctx.lib.instantiate0(
    copies=2,
    context_graph=ctx.subcontext
)

ctx.compute()
#print(ctx.inst.ctx.copy1.status) # Not implemented at the Context level
print(ctx.inst.ctx.copy1.result.value)
print(ctx.inst.ctx.copy2.result.value)
print(ctx.inst.ctx.copy2.result.status)