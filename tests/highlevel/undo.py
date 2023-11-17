import os
import seamless

if "DELEGATE" in os.environ:
    seamless.delegate()
else:
    seamless.delegate(level=3)
    from seamless.core.transformation import get_global_info
    get_global_info()  # avoid timing errors

from seamless.highlevel import Context

def func(a,b,c):
    import time
    time.sleep(3)
    return (a+b) * c

ctx = Context()
ctx.tf = func
tf = ctx.tf
tf.a = 2
tf.b = 3
tf.c = 4
import time
t = time.time()
ctx.compute()
print("{:.1f} seconds".format(time.time() - t))
print(tf.result.value)

tf_checksum = tf.get_transformation_checksum()
print("Transformation:", tf_checksum)
result_checksum = tf.result.checksum
print("Result:", result_checksum)

error_msg = tf.undo()
print("Error:", error_msg)
print()

ctx.translate(force=True)  # delete tf.result.checksum
t = time.time()
ctx.compute()
print("{:.1f} seconds".format(time.time() - t))
print(tf.result.value)

error_msg = tf.undo()
print("Error:", error_msg)
print()
