import seamless
seamless.delegate(False)

from seamless.core import macro_mode_on
from seamless.core import context, cell, transformer, unilink, macro
from seamless.shareserver import shareserver
from seamless.core.share import sharemanager
from functools import partial

import websockets
import requests
import asyncio
import json
import time

shareserver_started = shareserver.start()

def define_ctx():
    with macro_mode_on():
        ctx = context(toplevel=True)
        ctx.cell1 = cell().set(1)
        ctx.cell2 = cell().set(2)
    ctx.compute()
    with macro_mode_on():
        ctx.result = cell()
        ctx.tf = transformer({
            "a": "input",
            "b": "input",
            "c": "output"
        })
        ctx.cell1_unilink = unilink(ctx.cell1)
        ctx.cell1_unilink.connect(ctx.tf.a)
        ctx.cell2.connect(ctx.tf.b)
        ctx.code = cell("transformer").set("c = a + b")
        ctx.code.connect(ctx.tf.code)
        ctx.result_unilink = unilink(ctx.result)
        ctx.tf.c.connect(ctx.result_unilink)
    return ctx

ctx = define_ctx()
ctx.compute()
name = sharemanager.new_namespace(ctx._get_manager(), True, name="ctx")
ctx.compute()
print("OK1", name)

print(ctx.cell1.value, ctx.cell2.value)
ctx.cell1.share(readonly=False)
ctx.cell2.share(readonly=False)
ctx.compute()

async def echo(uri):
    async with websockets.connect(uri) as websocket:
        async for message in websocket:
            print("WS ECHO", message)

ws = echo('ws://localhost:5138/ctx')
asyncio.ensure_future(ws)

loop = asyncio.get_event_loop()
loop.run_until_complete(shareserver_started)
loop.run_until_complete(asyncio.sleep(0.1))

def thread(func, *args, **kwargs):
    from threading import Thread
    from queue import Queue
    def func2(func, q, args, kwargs):
        result = func(*args, **kwargs)
        q.put(result)
    q = Queue()
    t = Thread(target=func2, args=(func, q, args, kwargs))
    t.start()
    while t.is_alive():
        t.join(0.05)
        loop.run_until_complete(asyncio.sleep(0.01))
    return q.get()

r = thread(requests.get, 'http://localhost:5813/ctx/cell1')
print(r.json())

r = thread(
    requests.put, 'http://localhost:5813/ctx/cell1',
    data=json.dumps({"buffer": "20\n"})
)

r = thread(requests.get, 'http://localhost:5813/ctx/cell1')
print(r.json())

ctx.cell1.set(99)
loop.run_until_complete(asyncio.sleep(0.1))

r = thread(requests.get, 'http://localhost:5813/ctx/cell1')
print(r.json())

ctx._get_manager().destroy()

ctx = context(toplevel=True)
name = sharemanager.new_namespace(ctx._get_manager(), True, name="ctx")
print("OK2", name)
assert name == "ctx"

ws = echo('ws://localhost:5138/ctx')
asyncio.ensure_future(ws)

def macro_code(ctx, param_a):
    ctx.a = cell().set(param_a + 1000)
    ctx.a.share()
    ctx.a0 = cell().set(999)
    ctx.a0.share()

def define_ctx2():
    ctx.macro = macro({"param_a": "int"})
    ctx.macro.code.cell().set(macro_code)
    ctx.param_a = cell().set(42)
    ctx.param_a.share(readonly=False)
    ctx.param_a.connect(ctx.macro.param_a)

define_ctx2()
import asyncio; asyncio.get_event_loop().run_until_complete(asyncio.ensure_future(asyncio.sleep(1)))
print(r.text)
print(ctx.param_a.value)
print(ctx.macro.ctx.a.value)

r = thread(requests.get, 'http://localhost:5813/ctx/macro/ctx/a')
print(r.json())

print("OK3")

r = thread(
    requests.put, 'http://localhost:5813/ctx/param_a',
    data=json.dumps({"buffer": "43\n"})
)
print(r.json())
asyncio.get_event_loop().run_until_complete(asyncio.sleep(0.5))  # to get the request processed
print("OK3a")
ctx.compute()

print(ctx.param_a.value)
print("OK3b")

ctx.compute()

print(ctx.param_a.value)
print(ctx.macro.ctx.a.value)
