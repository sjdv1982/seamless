import seamless
from seamless.core import macro_mode_on
from seamless.core import context, cell, transformer, link, macro
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
    ctx.equilibrate()
    with macro_mode_on():
        ctx.result = cell()
        ctx.tf = transformer({
            "a": "input",
            "b": "input",
            "c": "output"
        })
        ctx.cell1_link = link(ctx.cell1)
        ctx.cell1_link.connect(ctx.tf.a)
        ctx.cell2.connect(ctx.tf.b)
        ctx.code = cell("transformer").set("c = a + b")
        ctx.code.connect(ctx.tf.code)
        ctx.result_link = link(ctx.result)
        ctx.tf.c.connect(ctx.result_link)
    return ctx

ctx = define_ctx()
name = sharemanager.new_namespace(ctx, True, name="ctx")
print("OK1", name)

print(ctx.cell1.value, ctx.cell2.value)
ctx.cell1.share()
ctx.cell2.share()

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

ctx.destroy()

ctx = context(toplevel=True)
name = sharemanager.new_namespace(ctx, True, name="ctx")
print("OK2", name)

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
    ctx.param_a.share()
    ctx.param_a.connect(ctx.macro.param_a)

define_ctx2()

r = thread(
    requests.patch, 'http://localhost:5813/ctx/equilibrate', 
    json={"timeout": None}
)
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
print("OK3a")
sharemanager.tick()

print(ctx.param_a.value)
print("OK3b")

ctx.equilibrate()

print(ctx.param_a.value)
print(ctx.macro.ctx.a.value)

sharemanager.tick()

import sys; sys.exit()
