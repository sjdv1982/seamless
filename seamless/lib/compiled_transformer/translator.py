args = []
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
    args.append(kwargs[prop])

simple_result = True
if result_schema["type"] in ("object", "array"):
    simple_result = False
    raise NotImplementedError

if simple_result:
    result = binary_module.lib.transform(*args)

print(result)
