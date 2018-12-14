from seamless.highlevel import Context, Cell, stdlib
from seamless.highlevel import set_resource

executor_file = "executor.py"

print("START")
ctx = Context()
ctx.executor = lambda dummy: None
ctx.executor_code >> ctx.executor.code
ctx.executor_code = set_resource(executor_file)
del ctx.executor

if __name__ == "__main__":
    #ctx.mount("/tmp/seamless-test", persistent=False) #TODO: persistent=False (does not delete atm)
    ctx.testdata = "a\nb\nc\nd\ne\nf\n"    
    ctx.bashcode = "head -$lines testdata"
    ctx.executor = lambda bashcode, testdata, pins: None
    ctx.executor.pins = ["lines", "testdata"]
    ctx.executor.code = ctx.executor_code
    ctx.executor.bashcode = ctx.bashcode
    ctx.executor.testdata = ctx.testdata
    ctx.executor.lines = 3
    ctx.result = ctx.executor
    ctx.equilibrate()
    ctx.executor_code = ctx.executor_code.value + "\npass"
    ctx.equilibrate()
else:
    stdlib.bash_transformer = ctx
