import seamless
seamless.delegate(False)

from seamless.workflow import Context

ctx = Context()
def func(a):
    print("The value received is: %s" % a)
    return True
ctx.tf = func
ctx.tf.a = 100
ctx.compute()
print(ctx.tf.result.value)
print(ctx.tf.logs)