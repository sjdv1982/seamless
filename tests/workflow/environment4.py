# Execute a transformer only if:
# - ifconfig is available from the command line
# - sympy is version 1.9
import seamless
seamless.delegate(False)

from seamless.highlevel import Context, Transformer
ctx = Context()
ctx.tf = Transformer()
ctx.tf.code = "42"
ctx.tf.environment.set_which(["ifconfig"], "plain")
ctx.tf.environment.set_conda("""
dependencies:
- sympy==1.9.*
""", "yaml")
ctx.compute()
print(ctx.tf.exception)
print(ctx.tf.result.value)

ctx.save_graph("environment4.seamless")
ctx.save_zip("environment4.zip")