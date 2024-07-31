"""Run PyTorch tests with Seamless in delegation.

This is a good test for delegation since as of Seamless 0.12,
PyTorch cannot be added to the Seamless Docker image using conda
(the openmp versions are mutually exclusive).
"""
import json
import seamless
if seamless.delegate():
     exit(1)

from seamless.highlevel import Context, Transformer
ctx = Context()
ctx.tf = Transformer()
ctx.tf.code = open("pytorch_test1.py").read()
ctx.tf.datapoints = 2000
ctx.tf.iterations = 2000
ctx.tf.learning_rate = 1e-03
ctx.tf.environment.set_conda("pytorch-environment.yml")
ctx.result = ctx.tf
ctx.result.celltype = "str"
ctx.compute()
print("Transformation:", ctx.tf.get_transformation_checksum())
tf_dict = ctx.tf.get_transformation_dict()
tf_dunder = {}
for k in "env", "meta", "compilers", "languages":
    key = "__" + k + "__"
    v = tf_dict.get(key)
    if v is not None:
          tf_dunder[key] = v
with open("environment7-dunder.json", "w") as f:
    json.dump(tf_dunder, f, sort_keys=True, indent=2)
print("Transformation dunder stored in environment7-dunder.json")
print(ctx.tf.logs)
print(ctx.result.value)