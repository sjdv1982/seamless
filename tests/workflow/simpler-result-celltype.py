import seamless

seamless.delegate(False)

from seamless.workflow import Context

ctx = Context()

ctx.a = 12
ctx.compute()
print(ctx.a.value)
print(ctx.a.schema)  # None


def triple_it(a):
    return 3 * a


ctx.transform = triple_it
ctx.transform.debug.direct_print = True
ctx.transform.a = 1
print("START")
ctx.compute()
print(ctx.transform.inp.value, ctx.transform.result.value)
ctx.transform.a = ctx.a
ctx.compute()
print(ctx.a.value, ctx.transform.inp.value)
print(ctx.transform.inp.schema)

ctx.myresult = ctx.transform


def change_celltypes():
    ctx.a = 12
    ctx.transform.result.celltype = "structured"
    ctx.compute()
    print(ctx.transform.result.value)
    ctx.transform.result.celltype = "int"
    ctx.compute()
    print(ctx.transform.result.value)
    ctx.a = 2.5
    ctx.compute()
    print(ctx.transform.result.value)
    ctx.transform.result.celltype = "str"
    ctx.compute()
    print("The result is: " + ctx.transform.result.value)
    ctx.a = "bork!"
    ctx.compute()
    print(ctx.transform.result.value)
    ctx.transform.result.celltype = "int"
    ctx.compute()
    print(ctx.transform.result.value)
    print(ctx.transform.exception)


change_celltypes()
print()
print("Bash")
ctx.transform.language = "bash"
ctx.transform.code = (
    "echo $a | awk '{result=5*$1} $1+0==0{result=$1$1$1$1$1}{print result}' > RESULT"
)
change_celltypes()
