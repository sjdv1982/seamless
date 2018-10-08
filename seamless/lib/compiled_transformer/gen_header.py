json_to_c = {
    "integer": "int", #TODO: storage size
    "number": "double", #TODO: storage size
    "str": "const char*",
}

###print("input schema:", input_schema)
###print("result schema:", result_schema)

input_args = ""
input_jtype = input_schema["type"]
if input_jtype == "array":
    raise NotImplementedError
elif input_jtype == "object":
    input_props = input_schema["properties"]
else:
    input_props = {"input": input_schema}

order = input_schema.get("order", [])
for prop in sorted(input_props.keys()):
    if prop not in order:
        order.append(prop)
for propnr, prop in enumerate(order):
    propschema = input_props[prop]
    prop_jtype = propschema["type"]
    prop_ctype = json_to_c[prop_jtype]
    input_args += prop_ctype + " " + prop
    if propnr + 1 < len(order):
        input_args += ", "


if "type" not in result_schema:
    raise TypeError("Result schema needs to be defined")

return_jtype = result_schema["type"]
if return_jtype in ("object", "array"):
    raise NotImplementedError
return_ctype = json_to_c[return_jtype]

result = "{0} transform({1});".format(return_ctype, input_args)
