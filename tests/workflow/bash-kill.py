from seamless.workflow import Context

import seamless.workflow.core.execute

code = """
sleep $delay &
echo OK > RESULT
wait
"""

ctx = Context()
ctx.code = code
ctx.code.celltype = "text"
ctx.tf = lambda delay: None
ctx.tf.language = "bash"
ctx.tf.delay = 20
ctx.tf.code = ctx.code

ctx.compute(1)
print(ctx.tf.status)
print(ctx.tf.exception)


ctx.tf.delay = 2  # This will cancel the old transformer, and hopefully the sleep processes
ctx.compute()
print(ctx.tf.status)
print(ctx.tf.exception)
print(ctx.tf.result.value)