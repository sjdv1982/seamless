from seamless.highlevel import Context, Cell, stdlib
from seamless.highlevel import set_resource

executor_file = "executor.py"

ctx = Context()
ctx.executor_code = set_resource(executor_file)
ctx.executor_code._get_hcell()["language"] = "python"
ctx.executor_code._get_hcell()["transformer"] = True
ctx.executor_code.celltype = "code"
ctx.translate()

if __name__ == "__main__":
    #ctx.mount("/tmp/seamless-test", persistent=False) #TODO: persistent=False (does not delete atm)
    ctx.testdata = "a\nb\nc\nd\ne\nf\n"       
    ctx.bashcode = "head -$lines testdata"
    ctx.executor = lambda bashcode, testdata, pins, lines: None
    ctx.executor.pins = ["lines", "testdata"]
    ctx.executor.code = ctx.executor_code
    ctx.executor.bashcode = ctx.bashcode
    ctx.executor.testdata = ctx.testdata    
    ctx.executor.pins = ["lines", "testdata"] ### TODO! duplication should not be needed
    ctx.executor.lines = 3
    ctx.result = ctx.executor
    ctx.equilibrate()
    print(ctx.result.value)
    ctx.executor_code = ctx.executor_code.value + "\npass"
    ctx.equilibrate()
    print(ctx.result.value)
else:
    stdlib.bash_transformer = ctx
