# run with https://codepen.io/sjdv1982/pen/MzNvJv
# copy-paste seamless-client.js

from seamless.workflow import Context
ctx = Context()
ctx.cell1 = "test!"
ctx.cell1.share()
ctx.translate()
ctx.compute()

from seamless import shareserver
print(shareserver.namespaces["ctx"].shares)
print(shareserver.namespaces["ctx"].shares["cell1"].bound)
print(shareserver.namespaces["ctx"].shares["cell1"].bound.cell)
ctx.cell1.celltype = "plain"
ctx.translate(force=True)
ctx.compute()
print(shareserver.namespaces["ctx"].shares)
print(shareserver.namespaces["ctx"].shares["cell1"].bound)
print(shareserver.namespaces["ctx"].shares["cell1"].bound.cell)
