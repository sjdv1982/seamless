import seamless
seamless.delegate(False)

from seamless.workflow import Context
ctx = Context()
ctx.tf = lambda cowtext: None
ctx.tf.language = "bash"
ctx.tf.code = 'cowsay -t "$cowtext" > RESULT'
ctx.tf.cowtext = "Boe moo meuh!"
ctx.tf.environment.set_conda_env("cowsay-environment")
ctx.compute()
print(ctx.tf.result.value.unsilk)