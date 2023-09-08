"""Run PyTorch tests with Seamless in delegation.

This is a good test for delegation since as of Seamless 0.12,
PyTorch cannot be added to the Seamless Docker image using conda
(the openmp versions are mutually exclusive).
"""
import seamless
seamless.config.delegate()

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
print(ctx.tf.logs)
print(ctx.result.value)