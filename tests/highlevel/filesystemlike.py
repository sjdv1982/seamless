from seamless.highlevel import Context
ctx = Context()
ctx.filesystem = {"test.txt": """
This
is
a
test
"""
}
ctx.job = lambda input: None
ctx.job.language = "bash"
ctx.job.code = "awk 'NF > 0{print $0 \" OK!\"}' input > RESULT"
ctx.job.input = ctx.filesystem["test.txt"]
ctx.result = ctx.job
ctx.compute()
print(ctx.result.value)
print("START")
ctx.filesystem["result.txt"] = ctx.result
ctx.compute()
print(ctx.result.value)
print(ctx.filesystem.value)
print(ctx.status)