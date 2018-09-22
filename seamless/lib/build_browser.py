from seamless.highlevel import Context, Reactor, stdlib
from seamless.lib import set_resource

ctx = Context()
b = ctx.browser = Reactor()

b.code_start = set_resource("cell-browser.py")
b.code_update = set_resource("cell-browser_UPDATE.py")
b.code_stop = "widget.destroy()"

b.mimetype = "text"
b.title = "Seamless browser"
b.val = "Hello world!"
ctx.equilibrate()

if __name__ == "__main__":
    print(b._get_rc().status())
    print(b._get_rc().io.outchannels)
    print(b._get_rc().io.value)
    pass
else:
    stdlib.browser = ctx
