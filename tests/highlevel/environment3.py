"""A third example on how to modify the Seamless environment,
adding direct Cython support via an ipy template

The graph is then saved and re-loaded
"""

import traceback

from seamless.highlevel import Context, Cell, Transformer
ctx = Context()
env = ctx.environment

# Define a transformer in IPython format that uses Cython magic 
ctx.tf = Transformer()
ctx.tf.a = 123
ctx.tf.language = "ipython"
ctx.tf.code = """
%load_ext Cython

%%cython
from libc.math cimport log
def func(int i):
    cdef int n
    cdef int nn
    cdef double s = 0
    for n in range(i):
        for nn in range(i):
            s += log(n*nn+1)/10000.0
    return s

result = func(a)
"""
ctx.compute()
print(ctx.tf.result.value)

# For good measure, define an execution environment
# This should give no problem, as Cython is installed in the Seamless Docker image
ctx.tf.environment.set_conda("""
dependencies:
  - cython
""", "yaml")
ctx.tf.environment.set_which(["cython"], format="plain")
ctx.compute()
print(ctx.tf.status)
print(ctx.tf.result.value)

# Now set the transformer as pure Cython code
# - We must call it "transform"
# - The argument must be "a", the pin name
# - Cython arguments with a C type cannot be both positional and keyword
#   Therefore, it must be declared as keyword-only 
ctx.tf.code = """
from libc.math cimport log
def transform(*, int a): 
    cdef int n
    cdef int nn
    cdef double s = 0
    for n in range(a):
        for nn in range(a):
            s += log(n*nn+1)/10000.0
    return s
"""

# Set the language as Cython
#   => fail, unknown language
try:
    ctx.tf.language = "cython"
except KeyError as exc:
    traceback.print_exc(limit=0)
    print()

# Have a look how languages are defined...
languages = env.get_languages("cson")
print("\n".join(languages.splitlines()[:10]))
print()

# Create a new language "cython"
languages = env.get_languages("plain")
languages["cython"] = {
    "extension": "pyx",
    "mode": "interpreted",
}
env.set_languages(languages, "plain")

# Set the language as cython => success
ctx.tf.language = "cython"

# Seamless will refuse to translate a graph
# that contains unimplemented interpreted languages
try:
    ctx.translate()
except NotImplementedError as exc:
    traceback.print_exc(limit=0)
    print()

#### help(env.set_ipy_template)   # for interactive use

# TODO: make sure that PINS is documented
def wrap_cython(code, parameters):    
    tmpl = """
get_ipython().run_line_magic("load_ext", "Cython")
get_ipython().run_cell_magic("cython", "", {})
if "transform" not in globals():
    raise Exception("Cython code must define a function 'transform'")
result = transform(**PINS)  
"""
    return tmpl.format(repr(code))

env.set_ipy_template("cython", wrap_cython)

# Define an environment for the Cython code generator
from seamless.highlevel.Environment import Environment
tmpl_env = Environment()
tmpl_env.set_conda("""
dependencies:
  - cython
""", "yaml")
tmpl_env.set_which(["cython"], format="plain")
env.set_ipy_template_environment("cython", tmpl_env)

ctx.compute()
print(ctx.tf.status)
print(ctx.tf.exception)
print(ctx.tf.result.value)

ctx.save_graph("environment3.seamless")
ctx.save_zip("environment3.zip")