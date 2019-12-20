from seamless.highlevel import Context
ctx = Context()
ctx.pdbcodes = ["1AVX", "1ACB"]
#ctx.pdbcodes.celltype = "plain"
ctx.test = ["1BBB"]
#ctx.test.celltype = "plain"
t = ctx.pdbcodes.traitlet()
ctx.equilibrate()

def obs(change):
    print("OBS", change)
t.observe(obs)

print("start")
print(t.value)
t.value = ["1ZZZ"]
ctx.equilibrate()
print(t.value)
print(ctx.pdbcodes.value)
print("#2")
ctx.pdbcodes = ["1AAA"]
ctx.equilibrate()
print(t.value)
print(ctx.pdbcodes.value)
print("#3")
t.value = ["1QQQ"]
ctx.equilibrate()
print(t.value)
print(ctx.pdbcodes.value)