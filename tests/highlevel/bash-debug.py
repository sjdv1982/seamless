from traitlets.traitlets import CRegExp
from seamless.highlevel import Context

ctx = Context()
ctx.pycode = """
import time, sys
print("START", file=sys.stderr)
#raise Exception
lines = int(sys.argv[1])
data = list(open("testdata").readlines())[:lines]
for lnr, l in enumerate(data):
    print(lnr, l.strip())
    print("PROGRESS", lnr, file=sys.stderr)
    time.sleep(1)
"""
ctx.code = "python -u pycode.py $lines > RESULT"
ctx.tf = lambda lines, testdata: None
ctx.tf.language = "bash"
ctx.tf.testdata = "a \nb \nc \nd \ne \nf \n"
ctx.tf.testdata.celltype = "text"
ctx.tf.lines = 3
ctx.tf.code = ctx.code
ctx.tf["pycode.py"] = ctx.pycode
ctx.tf.debug.direct_print = True
ctx.compute()
print(ctx.tf.logs)
print("Introduce error...")
ctx.code = "python -u pycode.py $lines > RESULT; exit 1"
ctx.compute()
print(ctx.tf.logs)
