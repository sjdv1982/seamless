from seamless.highlevel import Context
from pprint import pprint

ctx = Context()
###ctx.mount("/tmp/mount-test")

ctx.a = 12
ctx.compute()
print(ctx.a.value)
print(ctx.a.schema) # None

def triple_it(a):
    return 3 * a

def triple_it_b(a, b):
    print("RUN!")
    return 3 * a + b

ctx.transform = triple_it
ctx.transform.hash_pattern = {"*": "#"}
ctx.transform.a = 1
print("START")
ctx.translate()
print(ctx.transform.inp.value, ctx.transform.result.value)
ctx.transform.a = ctx.a
ctx.transform.example.a = 99
ctx.compute()
print(ctx.a.value, ctx.transform.inp.value)
print(ctx.transform.inp.schema)

ctx.myresult = ctx.transform
ctx.compute()
print(ctx.a.value, ctx.transform.inp.value)
print(ctx.transform.result.value)

ctx.tfcode >> ctx.transform.code
ctx.compute()
print(ctx.transform.result.value, ctx.myresult.value)

ctx.tfcode = triple_it_b
ctx.compute()
'''
#or:
ctx.transform = triple_it_b
ctx.transform.a = ctx.a
ctx.myresult = ctx.transform
'''
ctx.compute()
print(ctx.transform.inp.value)
print("NO RESULT", ctx.transform.result.value, ctx.myresult.value)
print("TRANSFORMER EXCEPTION", ctx.transform.exception)

ctx.transform.b = 100
ctx.compute()
print(ctx.transform.inp.value)
print("RESULT", ctx.transform.result.value, ctx.myresult.value)

print("START")

ctx.a = 13
ctx.compute()
print(ctx.a.value)
print(ctx.transform.inp.value)
print("RESULT", ctx.transform.result.value, ctx.myresult.value)

ctx.transform.example.b = "test"  # modification of schema => .inp exception
ctx.translate()
print(ctx.transform.inp.value)
print("TRANSFORMER INPUT EXCEPTION", ctx.transform.inp.exception) # None
ctx.compute()
###print("TF STATUS", ctx.transform.status)
###ctx.translate(force=True); ctx.compute()  ### ERROR
print(ctx.transform.inp.schema)
###print("INPUT EXCEPTION", ctx.transform.inp.exception)
print(ctx.transform.inp.value)    # None
print(ctx.transform._get_tf().inp.auth.value)   #  As of Seamless 0.2, this gives {'a': 1, 'b': 100}  
                                                #  The a=1 is not cleared when the connection is broken!
print("TRANSFORMER STATUS", ctx.transform.status)
ctx.transform.b = "testing"
print("START!")
ctx.compute()
print(ctx.transform._get_tf().inp.auth.value)    # {'a': 1, 'b': "testing"}
print(ctx.transform._get_tf().inp.buffer.value)    # {'a': 13, 'b': "testing"}
print(ctx.transform.inp.value)    # {'a': 13, 'b': 'testing'}
print(ctx.myresult.value) # None
print("TRANSFORMER INPUT EXCEPTION", ctx.transform.inp.exception) # None
print("TRANSFORMER STATUS", ctx.transform.status)
print("TRANSFORMER EXCEPTION", ctx.transform.exception)

print("START2")
ctx.translate(force=True); ctx.compute()
print(ctx.myresult.value) # None
print("TRANSFORMER INPUT EXCEPTION", ctx.transform.inp.exception) # None
print("TRANSFORMER STATUS", ctx.transform.status)
print("TRANSFORMER EXCEPTION", ctx.transform.exception)

print("START3")
ctx.tfcode = triple_it
ctx.transform._get_htf()["pins"].pop("b"); ctx._translate() ### KLUDGE
ctx.compute()
print(ctx.myresult.value)
print("TRANSFORMER INPUT STATUS", ctx.transform.inp.status)
print("TRANSFORMER STATUS", ctx.transform.status)

print(ctx.transform.inp.schema)
print(ctx.transform.inp.data)