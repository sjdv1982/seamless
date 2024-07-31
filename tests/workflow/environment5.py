"""Test loading environment from graph
1. Context environment (adds Cython, should succeed)
2. Transformer environment (if loaded correctly, should fail unless extra packages are installed)
"""

import seamless
seamless.delegate(False)

from seamless.highlevel import load_graph
ctx = load_graph("environment3.seamless", zip="environment3.zip")
ctx.compute()
print(ctx.tf.result.value)

ctx = load_graph("environment4.seamless", zip="environment4.zip")
ctx.compute()
print(ctx.tf.exception)
print(ctx.tf.result.value)
