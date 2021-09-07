from seamless.highlevel import Context, Transformer
from seamless.metalevel import stdgraph
import asyncio

bash_graph, bash_zip = stdgraph.get("bash_transformer")

bash_ctx = Context()
bash_ctx.add_zip(bash_zip)
bash_ctx.set_graph(bash_graph)
bash_ctx.executor_code.mount("/tmp/execute.py", authority="cell")

testctx = Context()
testctx.tf = Transformer()
testctx.tf.language = "bash"
testctx.tf.code = "echo 1 2 3; touch RESULT"
testctx.translate()

def update_stdgraph(*args, **kwargs):
    new_graph = bash_ctx.get_graph()
    new_zip = bash_ctx.get_zip()
    stdgraph.set("bash_transformer", new_graph, new_zip)
    async def do_translate():
        await testctx.translation(force=True)
    coro = do_translate()
    asyncio.ensure_future(coro)

t = bash_ctx.executor_code.traitlet()
t.observe(update_stdgraph)

bash_ctx.compute()