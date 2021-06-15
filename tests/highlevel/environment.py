import traceback

from seamless.highlevel import Context, Cell, Transformer
ctx = Context()

conda_environment ="""
dependencies:
   - python
"""
env = ctx.environment
env.set_conda(conda_environment, "yaml")
ctx.translate()

conda_environment ="""
dependencies:
   - python>=10
"""
env = ctx.environment
env.set_conda(conda_environment, "yaml")
try:
    ctx.translate()
except ValueError as exc:
    print(traceback.format_exception_only(type(exc), exc)[0])

env.set_conda(None, "yaml")
ctx.translate()

ctx.tf = Transformer()
ctx.tf.a = 13
ctx.tf.b = 16
ctx.compute()
ctx.tf.example.a = 0
ctx.tf.example.b = 0
ctx.tf.result.example = 0

print(ctx.tf.schema)
print(ctx.tf.result.schema)
print(ctx.tf.a.value)

try:
    ctx.tf.language = "go"
except KeyError as exc:
    print(traceback.format_exception_only(type(exc), exc)[0])

languages = env.get_languages("plain")
languages["go"] = {
    "extension": "go",
    "mode": "compiled",
}
env.set_languages(languages, "plain")

ctx.tf.language = "go"  # will reset all inputs!
ctx.tf.code = """
package main

func transformer(a int, b int) int {
    return a + b
}
"""
ctx.compute()
LDFLAGS = -lgo -lgobegin

ctx.tf.a = 13
ctx.tf.b = 16
ctx.compute()
print(ctx.tf.exception)

languages = env.get_languages("plain")
languages["go"] = {
    "extension": "go",
    "mode": "compiled",
    "compiler": "gccgo"
}
env.set_languages(languages, "plain")
compilers = env.get_compilers("plain")
compilers["gccgo"] = compilers["gcc"]
env.set_compilers(compilers, "plain")
ctx.translate()
ctx.tf.clear_exception()
ctx.compute()

print(ctx.tf.exception)

env.set_which(["gccgo"], "plain")
ctx.compute()


# TODO: link options
