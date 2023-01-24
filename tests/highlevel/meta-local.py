import sys, os
os.environ["SEAMLESS_COMMUNION_ID"] = "test-meta-local"

from seamless.highlevel import Context
import seamless

currdir=os.path.dirname(os.path.abspath(__file__))

if "--database" in sys.argv[1:]:
    seamless.database_sink.connect()
    seamless.database_cache.connect()
    seamless.database_sink.connect()
    seamless.database_cache.connect()
    db_logfile = currdir + "/test-outputs/meta-local.log"
    db_loghandle = open(db_logfile, "w")
    seamless.database_sink.set_log(db_loghandle)
    seamless.database_cache.set_log(db_loghandle)

if "--communion" in sys.argv[1:]:
    seamless.communion_server.start()

ctx = Context()
def func1():
    return 42
ctx.func1 = func1
ctx.compute()
print("#1", ctx.func1.result.value, "exception:", ctx.func1.exception)

seamless.set_ncores(0)
def func2():
    return 88
ctx.func2 = func2
ctx.compute()
print("#2", ctx.func2.result.value, "exception:", ctx.func2.exception)

def func3():
    return 777
ctx.func3 = func3
ctx.func3.meta = {"local": True}
ctx.compute()
print("#3", ctx.func3.result.value, "exception:", ctx.func3.exception)
