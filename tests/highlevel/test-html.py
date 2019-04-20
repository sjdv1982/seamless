
from seamless.highlevel import Context
ctx = Context()
#ctx.mount("/tmp/mount-test")
ctx.a = "<b>Hello world!</b>"
ctx.a.mount("/tmp/mount-test/a.html")
ctx.a.share()
ctx.a.celltype = "text"
ctx.a.mimetype = "html"
ctx.translate()


import asyncio
import requests
loop = asyncio.get_event_loop()
loop.run_until_complete(asyncio.sleep(1))

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

r = thread(requests.get, 'http://localhost:5813/ctx/a')
print(r.text)
