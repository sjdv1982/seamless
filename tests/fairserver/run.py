import os
import json

FAIRSERVER = os.environ["FAIRSERVER"]
import seamless

seamless.delegate(level=1)

seamless.fair.add_server(FAIRSERVER)

from seamless.workflow import Context, DeepFolderCell, Cell

distribution = DeepFolderCell.find_distribution("mydataset", version=1)
print(json.dumps(distribution, indent=2))

ctx = Context()
ctx.dataset = DeepFolderCell()
ctx.dataset.define(distribution)
ctx.compute()

print("Number of index keys (files):", ctx.dataset.nkeys)
index_size = "{:d} bytes".format(int(ctx.dataset.index_size))
print("Size of the checksum index file: ", index_size)
if ctx.dataset.content_size is None:
    datasize = "<Unknown>"
else:
    datasize = "{:d} bytes".format(int(ctx.dataset.content_size))
print("Total content size:", datasize)
print("checksum of 9.txt: ", ctx.dataset.data["9.txt"])

ctx.nine_cs = Cell("checksum")
ctx.nine_cs = ctx.dataset.data["9.txt"]
ctx.nine = Cell("bytes")
ctx.nine = ctx.nine_cs
ctx.compute()
print(ctx.nine.value)
