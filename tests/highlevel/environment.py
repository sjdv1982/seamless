"""
Simple examples on how to modify the Seamless environment
- Add an example conda requirement
- Add Rust support via rustc
"""

import traceback

from seamless.highlevel import Context, Cell, Transformer
ctx = Context()
env = ctx.environment

# Define an environment that requires Python
conda_environment ="""
dependencies:
   - python
"""
env.set_conda(conda_environment, "yaml")
ctx.translate()  # success

# Define an environment that requires Python 10 or higher (fail)
conda_environment = """
dependencies:
   - python>=10
"""
env = ctx.environment
env.set_conda(conda_environment, "yaml")
try:
    ctx.translate()
except ValueError as exc:
    traceback.print_exc(limit=0)
    print()

# Reset the environment
env.set_conda(None, "yaml")
ctx.translate()


# Define a transformer with signature 
#    (a: int, b: int) -> int
#    and a=13, b=16
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

# Set the language as Rust
#   => fail, unknown language
try:
    ctx.tf.language = "rust"
except KeyError as exc:
    traceback.print_exc(limit=0)
    print()

# Have a look how languages are defined...
languages = env.get_languages("cson")
print("\n".join(languages.splitlines()[:10]))
print()

# Create a new language "rust"
languages = env.get_languages("plain")
languages["rust"] = {
    "extension": "rs",
    "mode": "compiled",
}
env.set_languages(languages, "plain")

# Set the language as rust => success
ctx.tf.language = "rust"

# Generate C header
ctx.compute()
print(ctx.tf.header.value)
print()

# Write some Rust code
# Unlike Go, Rust cannot import C header declarations
# So we must take care ourselves that the function signature
#  of transform() is correct
ctx.tf.code = """
#[no_mangle] pub unsafe extern "C"
fn transform (a: i32, b: i32,  c: *mut i32) -> i32
{
    (*c) = a + b;
    return 0;
}
"""
ctx.compute()
print(ctx.tf.exception)  # failure: no Rust compiler
print()

# Have a look how compilers are defined...
compilers = env.get_compilers("cson")
print("\n".join(compilers.splitlines()[:20]))
print()

# Set up "rustc" as the Rust compiler
# rustc will produce one archive (.a file)
#  for each crate (.rs file).
# Therefore, the compiler mode is "archive"
languages = env.get_languages("plain")
languages["rust"] = {
    "extension": "rs",
    "mode": "compiled",
    "compiler": "rustc"
}
env.set_languages(languages, "plain")
compilers = env.get_compilers("plain")
compilers["rustc"] = {
    "mode": "archive", 
    "options": ["--crate-type=staticlib"],
    "debug_options": ["--crate-type=staticlib"],
    "profile_options": [],
    "release_options": [],
    "compile_flag": "",
    "output_flag": "-o",
}
env.set_compilers(compilers, "plain")
ctx.translate()
ctx.tf.clear_exception()
ctx.compute()

# If rustc is installed, there will be no exception
# else, the error message will be a bit long..
print(ctx.tf.exception)
ctx.tf.clear_exception()

# This will give a much nicer error is rustc is not there
#  as Seamless will now refuse to translate
env.set_which(["rustc"], "plain")
try:
    ctx.translate()
except ValueError:
    traceback.print_exc(limit=0)
    exit(0)

# If we get here, then everything should be fine
print(ctx.tf.exception)  # None
print(ctx.tf.result.value) # 29

ctx.tf.a = 18
ctx.compute()
print(ctx.tf.result.value) # 34

# We can also provide linker options (not needed here)
ctx.tf.link_options = ["-lm"]  # no effect
ctx.compute()
print(ctx.tf.exception) # None
print(ctx.tf.result.value) # 34
