#!/bin/bash
rm -rf webinterface-files
mkdir webinterface-files
cd webinterface-files
python3 ~/seamless-scripts/new-project.py testproject
IPY='ipython3'  # change to 'ipython3 -i' for interactive test
$IPY -c '%run -i load-project.py
await load()
ctx.a = Cell("int").set(12).share()
await ctx.translation()
await webctx.computation()
print(webctx.webform, webctx.webform.buffer)
print()
print(webctx.webform0, webctx.webform0.buffer)
print()
print(webctx.autogen_webform, webctx.autogen_webform.buffer)
print()
print(webctx.autogen_webform0, webctx.autogen_webform0.buffer)
print()

# for interactive use...
import asyncio
import seamless.workflow

loop = seamless.workflow._original_event_loop
asyncio.set_event_loop(loop)
'
cd ..
rm -rf webinterface-files