import requests
import asyncio
import functools
from concurrent.futures import ThreadPoolExecutor
import seamless
from seamless.workflow import Context, Cell
from seamless.workflow.metalevel.bind_status_graph import bind_status_context

seamless.delegate(False)

pool = ThreadPoolExecutor()


def run_in_thread(func, *args, **kwargs):
    # Run a function in a separate thread,
    #  while the asyncio event loop remains running
    #  (i.e Seamless doesn't freeze)
    # Block until the function is complete
    loop = asyncio.get_event_loop()
    bound_func = functools.partial(func, *args, **kwargs)
    future = loop.run_in_executor(pool, bound_func)
    loop.run_until_complete(future)
    return future.result()


status_ctx = Context()
status_ctx.graph = Cell("plain")
status_ctx.graph.share()
status_ctx.graph.mount("/tmp/graph.json", authority="cell")
status_ctx.status_ = Cell("plain")
status_ctx.status_.share("status")
status_ctx.status_.mount("/tmp/status.json", authority="cell")

status_ctx.compute()

ctx = Context()
bind_status_context(ctx, status_ctx)


def report():
    for url in "http://localhost:5813/ctx/graph", "http://localhost:5813/ctx/status":
        response = run_in_thread(requests.get, url)
        print(url)
        print(response.text)
        print()


def sleep(sec):
    loop = asyncio.get_event_loop()
    loop.run_until_complete(asyncio.sleep(sec))


ctx.compute()
print(
    "Graph is written to /tmp/graph.json and accessible as http://localhost:5813/ctx/graph"
)
print(
    "Status is written to /tmp/status.json and accessible as http://localhost:5813/ctx/status"
)
sleep(10)
print("***Initial state***")
sleep(1)
report()
sleep(4)

print("***ctx.a = 42***")
ctx.a = 42
ctx.compute()
sleep(1)
report()
sleep(4)

print("***ctx.b = Cell('int').set(88)***")
ctx.b = Cell("int").set(88)
ctx.compute()
sleep(1)
report()
sleep(4)

print("***ctx.b.set('nonsense')***")
ctx.b.set("nonsense")
ctx.compute()
sleep(1)
report()
sleep(4)


def delay_func():
    import time

    time.sleep(10)
    return 42


print("***ctx.tf = delay_func***")
ctx.tf = delay_func
ctx.translate()
sleep(1)
report()
sleep(8)
report()
sleep(2)
report()


def delay_func():
    import time

    return 48


ctx.tf.code = delay_func
ctx.compute()
sleep(1)
report()
print(ctx.get_graph()["nodes"][-1]["checksum"]["code"])
print(ctx.get_graph(runtime=True)["nodes"][-1]["checksum"]["code"])
