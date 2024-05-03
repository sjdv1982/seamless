"""Another example on how to modify the Seamless environment,
adding Go support via "go build"
"""

import traceback

import seamless
seamless.delegate(False)

from seamless.highlevel import Context, Cell, Transformer
ctx = Context()
env = ctx.environment

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

# Set the language as Go
#   => fail, unknown language
try:
    ctx.tf.language = "go"
except KeyError as exc:
    traceback.print_exc(limit=0)
    print()

# Have a look how languages are defined...
languages = env.get_languages("cson")
print("\n".join(languages.splitlines()[:10]))
print()

# Create a new language "go"
languages = env.get_languages("plain")
languages["go"] = {
    "extension": "go",
    "mode": "compiled",
}
env.set_languages(languages, "plain")

# Set the language as Go => success
ctx.tf.language = "go"

# Generate C header
ctx.compute()
print(ctx.tf.header.value)
print()

# Write some Go code
# Go can directly use C header declarations
# Here, we make deliberately a mistake, and the compiler will catch it
ctx.tf.code = """
package main

/*
int transform(int a, int b, int *result); //copied from ctx.tf.header.value
*/
import "C"

//export transform
func transform(a C.int, b C.int) C.int {  //wrong signature! will give compiler error
    return a + b + 2000
}
func main(){}
"""
ctx.compute()

# ... but first, we get a complaint that there is no Go compiler
print(ctx.tf.exception)
print()

# Have a look how compilers are defined...
compilers = env.get_compilers("cson")
print("\n".join(compilers.splitlines()[:20]))
print()

# Set up "go build" as the Go compiler
# "go build" will produce a single archive (.a file)
#  for the entire package (all .go files).
# Therefore, the compiler mode is "package"

languages = env.get_languages("plain")
languages["go"] = {
    "extension": "go",
    "mode": "compiled",
    "compiler": "go build"
}
env.set_languages(languages, "plain")
compilers = env.get_compilers("plain")
compilers["go build"] = {
    "mode": "package",
    "options": ["-buildmode=c-archive"],
    "debug_options": ["-buildmode=c-archive", '-gcflags "all=-N -l"'],
    "profile_options": [],
    "public_options": [],
    "compile_flag": "",
    "output_flag": "-o",

}
env.set_compilers(compilers, "plain")
ctx.translate()
ctx.tf.clear_exception()
ctx.compute()

# Now we get either:
# 1. The compiler error mentioned above (conflicting types for "transform")
# or:
# 2. A complaint that 'go' is not available
print(ctx.tf.exception)
ctx.tf.clear_exception()
print()

# This will give a much nicer error for case 2.
#  as Seamless will now refuse to translate
env.set_which(["go"], "plain")
try:
    ctx.translate()
except ValueError:
    traceback.print_exc(limit=0)
    exit(0)

# If we get here, then there is a working compiler
#   all we need to do is fix the function signature
print("OK")
ctx.tf.code = """
package main

/*
int transform(int a, int b, int *result); //copied from ctx.tf.header.value
*/
import "C"

//export transform
func transform(a C.int, b C.int, result *C.int) C.int {  //correct
    *result = a + b + 2000
    return 0
}
func main(){}
"""
ctx.compute()
print(ctx.tf.exception) # None
print(ctx.tf.result.value) # 2029

ctx.tf.a = 80
ctx.compute()
print(ctx.tf.result.value) # 2096

'''
# We can even launch debugging 
#  GDB is not very good, but other debuggers (Delve) exist
# TODO: source file mapping (Seamless only does this for gcc compilers)

ctx.tf.code.mount("/tmp/x.go")
ctx.compute()
ctx.tf.debug.enable("light")
ctx.tf.a = 18
ctx.compute()
print(ctx.tf.result.value)
'''