"""Here, support for PHP is added via a Python bridge
The actual bridge is implemented using python-bond
"""
from seamless.highlevel import Cell, Context
from seamless.highlevel.Transformer import Transformer

import traceback

ctx = Context()
env = ctx.environment

ctx.tf = Transformer()

# Code for the bridge. All values are read from PINS
# NOTE: python-bond supports no keyword arguments
#  argument order is alphabetical
def bridge_php(**kwargs):
    import json
    from bond import make_bond
    php = make_bond('PHP')
    code = PINS["code"]
    php.eval_block(code)
    transform = php.callable("transform")
    args = []
    for pinname in sorted(PINS.keys()): # alphabetical sort
        if pinname == "code":
            continue
        pinvalue = PINS[pinname]
        try:
            json.dumps(pinvalue)
        except Exception:
            msg = "Pin '{}': not JSON-serializable"
            raise ValueError(msg.format(pinname)) from None
        args.append(pinvalue)
    return transform(*args)

ctx.tf.code = bridge_php
ctx.tf.environment.set_conda("""
channels:
  - pypi
dependencies:
  - python-bond
""", "yaml")
ctx.tf.environment.set_which(["php"], "plain")

ctx.php_code = """function transform($a, $b){
    return $a.$b;
}"""
ctx.tf.a = "This is a test string"
ctx.tf.b = " and this too"
ctx.tf.code_ = ctx.php_code
ctx.tf.code_.as_ = "code"
ctx.compute()
print(ctx.tf.status)
print(ctx.tf.exception)
print(ctx.tf.logs)
print(ctx.tf.result.value)

# Define it as a PHP transformer
del ctx.tf.pins.code_
ctx.tf.code = ctx.php_code
ctx.translate()

# Set the language as PHP
#   => fail, unknown language
try:
    ctx.tf.language = "php"
except KeyError as exc:
    traceback.print_exc(limit=0)
    print()

# Have a look how languages are defined...
languages = env.get_languages("cson")
print("\n".join(languages.splitlines()[:10]))
print()

# Create a new language "php"
languages = env.get_languages("plain")
languages["php"] = {
    "extension": "php",
    "mode": "interpreted",
}
env.set_languages(languages, "plain")

# Set the language as php => success
ctx.tf.language = "php"

# Seamless will refuse to translate a graph
# that contains unimplemented interpreted languages
try:
    ctx.translate()
except NotImplementedError as exc:
    traceback.print_exc(limit=0)
    print()

# Define bridge_php as a Python bridge
env.set_py_bridge("php", bridge_php)

# Define an environment for the PHP bridge
from seamless.highlevel.Environment import Environment
bridge_env = Environment()
bridge_env.set_conda("""
channels:
  - pypi
dependencies:
  - python-bond
""", "yaml")
bridge_env.set_which(["php"], format="plain")
env.set_py_bridge_environment("php", bridge_env)

ctx.tf.b = " and this is another one"
ctx.translate(force=True)
ctx.compute()
print(ctx.tf.status)
print(ctx.tf.exception)
print(ctx.tf.result.value)
