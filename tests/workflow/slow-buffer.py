import seamless

seamless.delegate()
# seamless.delegate(level=3)
# seamless.delegate(False)

from seamless import transformer


@transformer(return_transformation=True)
def reverse(buf):
    return buf[::-1]


reverse.celltypes["buf"] = "bytes"

import numpy as np

SIZE = 5e8
buf = np.random.default_rng().bytes(SIZE)
tf = reverse(buf)
print(tf.as_dict()["buf"][2])
tf.compute()
print(tf.checksum)
