import seamless
from seamless.core import macro_mode_on
from seamless.core import context, cell, transformer, pytransformercell, link
from seamless import shareserver
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
        ctx.result = cell()
        ctx.tf = transformer({
            "a": "input",
            "b": "input",
            "c": "output"
        })
        ctx.cell1_link = link(ctx.cell1)
        ctx.cell1_link.connect(ctx.tf.a)
        ctx.cell2.connect(ctx.tf.b)
        ctx.code = pytransformercell().set("c = a + b")
        ctx.code.connect(ctx.tf.code)
        ctx.result_link = link(ctx.result)
        ctx.tf.c.connect(ctx.result_link)
    return ctx

ctx = define_ctx()
namespace = shareserver.new_namespace("ctx")
print("OK1")

def share(namespace, shareddict):
    shareddict2 = {}
    for key, cell in shareddict.items():
        shareddict2[key] = (cell, "application/json")        
    shareserver.share(namespace, shareddict2)
    for key, cell in shareddict.items():
        if key != "self":
            sharefunc = partial(shareserver.send_update, "ctx", key)
            cell._set_share_callback(sharefunc)


share(namespace,{
        "cell1": ctx.cell1,
        "cell2": ctx.cell2,
    }
)

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

r = thread(requests.put, 'http://localhost:5813/ctx/cell1',data=json.dumps({"value": 20}))

r = thread(requests.get, 'http://localhost:5813/ctx/cell1')
print(r.json())

ctx.cell1.set(99)
shareserver.send_update(namespace, "cell1")
loop.run_until_complete(asyncio.sleep(0.1))

print("OK2")

ctx.destroy()
ctx = define_ctx()
share(namespace,{
        "cell1": ctx.cell1,
        "code": ctx.code,
        "result": ctx.result,
        "self": ctx, #for equilibrate
    }
)
ctx.equilibrate()
loop.run_until_complete(asyncio.sleep(0.1))

print("OK3")
ctx.cell2.set(100)