import seamless

seamless.delegate(False)

from seamless import transformer


@transformer(return_transformation=True)
def add(a, b):
    import time

    time.sleep(1)
    return a + b


@transformer(return_transformation=True)
def mul(a, b):
    import time

    time.sleep(1)
    return a * b


print(add(10, 20).compute().value)
print(mul(10, 20).compute().value)

tfm1 = mul(8, 9)
tfm2 = add(tfm1, 4)
print(tfm2.compute().value)
print(tfm1.status, tfm1.exception)
print(tfm2.status, tfm2.exception)

print(mul(13, add(2, 2)).compute().value)

print()
print("Error run 0")
tfm = add("zzz", 80)
tfm.compute()
print(tfm.exception)
print()

import time


def run(p, q, x, y, z):
    pq = add(p, q)
    pq_z = mul(pq, z)
    xy = mul(x, y)
    xy_z = add(xy, z)
    result = mul(xy_z, pq_z)

    result.compute()
    if result.exception is not None:
        msg = f"""Something went wrong.

Status and exceptions:        
pq: {pq.status}, {pq.exception}
pq_z: {pq_z.status}, {pq_z.exception}
xy: {xy.status}, {xy.exception}
xy_z: {xy_z.status}, {xy_z.exception}
result: {result.status}, {result.exception}
"""
        raise RuntimeError(msg)
    ret = result.value
    return ret


t = time.time()
result = run(2, 3, 4, 5, 6)  # (2+3 * 6) * (4*5 + 6) = 30 * 26 = 780
print("run() result", result)
print(
    "{:.1f} seconds elapsed".format(time.time() - t)
)  # should be 3 seconds, rather than 5

print()
print("Error run 1")
import traceback

try:
    run("p", "q", 4, "y", 6)  # errors in xy_z, propagating to result
except RuntimeError:
    traceback.print_exc(1)
print()

print("Error run 2")
try:
    run(  # errors in pq_z and xy, propagating to xy_z and result
        "pp", "qq", "x", "y", "z"
    )
except RuntimeError:
    traceback.print_exc(1)
