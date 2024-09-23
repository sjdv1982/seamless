import seamless
from seamless.workflow.core import context, cell

seamless.delegate(level=1)
ctx = context(toplevel=True)
ctx.result = cell("int")
ctx.result.set_checksum(
    "ba6ba8dcc8a2d9789f1221df37b27ca157b1b40817cde05eadb5c6075e5dd1c3"
)
ctx.compute()
print(ctx.result.checksum)
try:
    buf = ctx.result.buffer
except seamless.CacheMissError:
    print("Buffer 1 CANNOT be read from buffer server")
else:
    print("Buffer 1 CAN be read from buffer server")

import seamless
from seamless.workflow.core import context, cell

seamless.delegate(level=1)
ctx = context(toplevel=True)
ctx.result = cell("str")
ctx.result.set_checksum(
    "3a5e4e816160d53828641e0f45a9f8c7fcb29c7c27b5afeed016769b5b182911"
)
ctx.compute()
print(ctx.result.checksum)
try:
    buf = ctx.result.buffer
except seamless.CacheMissError:
    print("Buffer 2 CANNOT be read from buffer server")
else:
    print("Buffer 2 CAN be read from buffer server")
