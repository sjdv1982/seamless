from copy import deepcopy

assert header is not None

m = deepcopy(main_module)
m["type"] = "compiled"
if not "objects" in m:
    m["objects"] = {}
if not "main" in m["objects"]:
    m["objects"]["main"] = {}
mm =  m["objects"]["main"]
if len(mm):
    print("WARNING: main module will be overwritten")
mm["code"] = compiled_code
mm["language"] = lang
if "public_header" in m:
    print("WARNING: public header will be overwritten")
m["public_header"] = {
    "language": "c",
    "code": header
}

result = m