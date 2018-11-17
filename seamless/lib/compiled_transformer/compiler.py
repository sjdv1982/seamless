from seamless.compiler import compile
from copy import deepcopy
import os, tempfile, shutil

m = deepcopy(main_module)
if not "objects" in m:
    m["objects"] = {}
if not "main" in m["objects"]:
    m["objects"]["main"] = {}
mm =  m["objects"]["main"]
mm["code"] = compiled_code
mm["language"] = lang
m["public_header"] = {
    "language": "c",
    "code": header
}

tempdir = tempfile.gettempdir()
build_dir = os.path.join(tempdir, __fullname__.replace(".","__"))
binary_module = compile(m, build_dir, compiler_verbose=compiler_verbose)

result = binary_module
