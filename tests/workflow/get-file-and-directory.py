import seamless
seamless.delegate(level=1)
from seamless.workflow import Context, FolderCell, Transformer, Cell
ctx = Context()

print("Stage 1")
print()
ctx.tf = Transformer()
ctx.tf.language = "bash"
ctx.tf.code = "cat inputf > RESULT"
ctx.inputf = Cell("bytes")
ctx.translate()
ctx.inputf.set_checksum("0f36a467f10f7512e3642138f49435587c2b14379845e8b8cbb4b0cc27a9871e")
ctx.tf.inputf = ctx.inputf
ctx.compute()
print(ctx.tf.exception)
print(ctx.tf.result.value.unsilk)

print("Stage 2")
print()
ctx.tf = Transformer()
ctx.tf.language = "bash"
ctx.tf.code = "head inputfolder/* > RESULT"
ctx.inputfolder = FolderCell()
ctx.translate()
ctx.inputfolder.set_checksum("069a577ce64ff98c9730e55b8f13f94ba3eaba9f3066be0df90942ed0f7096e5")
ctx.tf.inputfolder = ctx.inputfolder
ctx.compute()
print(ctx.tf.status)
print(ctx.tf.exception)
print(ctx.tf.result.value.unsilk)

print("Stage 3")
print()
ctx.tf.code = "echo 'START' > RESULT; head inputfolder/* >> RESULT"
ctx.tf.docker_image = "ubuntu"
ctx.compute()
print(ctx.tf.status)
print(ctx.tf.exception)
print(ctx.tf.result.value.unsilk)
