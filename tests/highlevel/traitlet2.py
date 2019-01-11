from seamless.highlevel import Context
ctx = Context()
ctx.pdbcodes = ["1AVX", "1ACB"]
t = ctx.pdbcodes.traitlet()
ctx.translate()

def obs(change):
    print("OBS", change)
t.observe(obs)

print("start")
t.value = ["1ZZZ"]
print(t.value)
print(ctx.pdbcodes.value)
print("again") # This will notify once (bug in traitlets?)
ctx.pdbcodes = ["1AAA"]
print(t.value)
print(ctx.pdbcodes.value)
print("again3")
t.receive_update(["1BBB"]) # This will notify twice (bug doesn't trigger here)