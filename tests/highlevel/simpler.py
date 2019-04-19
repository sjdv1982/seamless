from seamless.highlevel import Context

ctx = Context()
ctx.mount("/tmp/mount-test")

ctx.a = 12

def triple_it(a):
    return 3 * a

def triple_it_b(a, b):
    return 3 * a + b

ctx.transform = triple_it
ctx.transform.a = ctx.a
ctx.myresult = ctx.transform
ctx.equilibrate()
print(ctx.myresult.value)
inp = ctx.transform._get_tf().inp

ctx.tfcode >> ctx.transform.code
print(ctx.tfcode.value)
ctx.transform.b = 100
print(ctx.transform.inp.value)
ctx.tfcode = triple_it_b
ctx.equilibrate()
print(ctx.myresult.value)
print("START")
ctx.a = 13
ctx.equilibrate()
print(ctx.myresult.value)

"""
# Schema testing, variation 1
ctx.transform.example.b = "test"  # modification of schema
ctx.transform.b = 120             # ValidationError => update refused!
print(ctx.transform.inp.value)    # {'a': 13, 'b': 100}
ctx.transform.b = "testing"
print(ctx.transform.inp.value)    # {'a': 13, 'b': 'testing'}
"""

"""
# Schema testing, variation 2
ctx.transform.example.b = "test"  # modification of schema
ctx.transform.b = 120             # ValidationError => update refused!
print(ctx.transform.inp.value)    # {'a': 13, 'b': 100}
ctx.transform.schema["properties"].pop("b") # KLUDGE
ctx.transform.example.b = 999     # modification of schema
print(ctx.transform.inp.value)    # {'a': 13, 'b': 120}
"""