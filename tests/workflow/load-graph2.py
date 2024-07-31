import seamless
seamless.delegate(False)

from seamless.highlevel import Context
ctx = Context()
ctx.tf = lambda a: 42
ctx.tf.docker_image = "some_docker_image"
print(ctx.tf._get_htf()["environment"])
print(ctx.tf.environment.get_docker())
print(ctx.tf.docker_image)
ctx.translate()
print(ctx.tf._get_htf()["environment"])
print(ctx.tf.environment.get_docker())
print(ctx.tf.docker_image)
graph = ctx.get_graph()
ctx2 = Context()
ctx2.set_graph(graph)
ctx2.translate()
print(ctx2.tf.code.value)
print(ctx2.tf._get_htf()["environment"])
print(ctx2.tf.environment.get_docker())
print(ctx2.tf.docker_image)