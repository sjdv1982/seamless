# two cascading Docker transformers, similar to share-pdb
# Making the first one invalid, and then valid again, shouldn't disable docker_image and docker_options on the second

from seamless.highlevel import Context
ctx = Context()
ctx.tf1 = lambda a: None
ctx.tf2 = lambda a: None
ctx.translate()
ctx.tf1.language = "docker"
ctx.tf2.language = "docker"
ctx.tf1.docker_image = "ubuntu"
ctx.tf2.docker_image = "ubuntu"
ctx.translate()
ctx.tf1.a = 10
ctx.tf1.code = "sleep 0.2; echo $a > RESULT"
ctx.tf1_result = ctx.tf1
ctx.tf2.a = ctx.tf1_result
ctx.tf2.code = "sleep 0.1; echo $a > RESULT"
ctx.compute()
print(ctx.status, ctx.tf2._get_tf().inp.auth.value)
ctx.tf1.code = "exit 1"
ctx.compute()
print(ctx.status, ctx.tf2._get_tf().inp.auth.value)
ctx.tf1.code = "sleep 0.11; echo $a > RESULT"
ctx.compute()
print(ctx.status, ctx.tf2._get_tf().inp.auth.value)