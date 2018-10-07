from seamless.compiler import compile
from copy import deepcopy

m = deepcopy(main_module)
if not "code" in m["objects"]:
    m["objects"]["code"] = {}
mm =  m["objects"]["code"]
mm["code"] = compiled_code
mm["language"] = language
m["public_header"] = {
    "language": "c",
    "code": header
}

binary_module = compile(m, compiler_verbose=compiler_verbose)

result = binary_module
