import seamless

seamless.delegate(False)

import inspect

from seamless.workflow import Context


def hhelp(obj):
    # Similar to doing obj? in IPython
    # Standard Python help() does not work with Python 3.8. Fixed in Python 3.9
    print("*" * 80)
    print(inspect.getdoc(obj))
    print("*" * 80)


ctx2 = Context()
ctx2.help = "Subcontext 2 help"
ctx = Context()
ctx.help = "Main context help"
ctx.compute()
ctx2.compute()
hhelp(ctx)
ctx.sub = Context()
ctx.sub.help = "Subcontext 1 help"
ctx.compute()
ctx2.compute()
ctx.sub2 = ctx2
ctx.compute()
hhelp(ctx)
hhelp(ctx.sub)
hhelp(ctx.sub2)

from seamless.workflow.highlevel.Help import HelpCell

hc = HelpCell(ctx.sub)
