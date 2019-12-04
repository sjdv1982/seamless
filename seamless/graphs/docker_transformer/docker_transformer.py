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
    ctx.docker_command = "bash -c 'head -$lines testdata'"
    ctx.executor = lambda docker_command, docker_image, docker_options, testdata, pins, lines: None
    ctx.executor.pins = ["lines", "testdata"]
    ctx.executor.code = ctx.executor_code
    ctx.executor.docker_command = ctx.docker_command
    ctx.executor.docker_image = "ubuntu"
    ctx.executor.docker_options = {}
    ctx.executor.testdata = ctx.testdata
    ctx.executor.lines = 3
    ctx.result = ctx.executor
    ctx.equilibrate()
    print(ctx.result.value)
    ctx.executor_code = ctx.executor_code.value + "\npass"
    ctx.equilibrate()
    print(ctx.result.value)
else:
    stdlib.docker_transformer = ctx
