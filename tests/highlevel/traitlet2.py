from seamless.highlevel import Context
import time

ctx = Context()
ctx.pdbcodes = ["1AVX", "1ACB"]
#ctx.pdbcodes.celltype = "plain"
ctx.test = ["1BBB"]
#ctx.test.celltype = "plain"
t = ctx.pdbcodes.traitlet()
ctx.compute()

def obs(change):
    print("OBS", change)
t.observe(obs)

print("start")
print(t.value)
t.value = ["1ZZZ"]
time.sleep(0.2) #value update takes 0.1 sec
ctx.compute()
print(t.value)
print(ctx.pdbcodes.value)
print("#2")
ctx.pdbcodes = ["1AAA"]
ctx.compute()
print(t.value)
print(ctx.pdbcodes.value)
print("#3")
t.value = ["1QQQ"]
time.sleep(0.2) #value update takes 0.1 sec
ctx.compute()
print(t.value)
print(ctx.pdbcodes.value)