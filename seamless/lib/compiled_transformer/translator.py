input_pins = []
for k,v in pins.items():
    vv = v if isinstance(v, str) else v["io"]
    if vv == "input":
        input_pins.append(k)
args = []
assert input_schema["type"] == "object"
input_props = input_schema["properties"]

for pin in input_pins:
    if pin not in input_props:
        raise TypeError("Missing schema for input pin .%s" % pin)

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
    translator_result_ = binary_module.lib.transform(*args)
