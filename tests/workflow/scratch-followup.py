import seamless
seamless.delegate(level=3)

from seamless.workflow import Context, Cell

ctx = Context()
ctx.result2 = Cell("str")
ctx.result2.scratch = True
ctx.translate()
ctx.result2.checksum = "3a5e4e816160d53828641e0f45a9f8c7fcb29c7c27b5afeed016769b5b182911"
ctx.compute()
print("Value 2:")
print(ctx.result2.value)

ctx.result = Cell("int")
ctx.result.scratch = True
ctx.translate()
ctx.result.checksum = "ba6ba8dcc8a2d9789f1221df37b27ca157b1b40817cde05eadb5c6075e5dd1c3"
ctx.compute()
print("Value 1:")
print(ctx.result.value)
