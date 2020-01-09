from seamless.highlevel import Context, Reactor, stdlib
from seamless.highlevel import set_resource

ctx = Context()
b = ctx.browser = Reactor()

b.code_start = set_resource("cell-browser.py")
b.code_update = set_resource("cell-browser_UPDATE.py")
b.code_stop = "widget.destroy()"

b.mimetype = "text"
b.charset = "UTF-8" #for text/ ; otherwise, the browser must figure it out
b.title = "Seamless browser"
b.val = "Hello world!"
ctx.compute()

if __name__ == "__main__":
    print(b._get_rc().status())
    print(b._get_rc().io.outchannels)
    print(b._get_rc().io.value)
    print(b.val.mimetype)
    pass
else:
    stdlib.browser = ctx
