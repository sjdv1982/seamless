
from seamless.core.transformation import SeamlessTransformationError


header = """
/*
The following C header has been auto-generated from the transformer schema
It will be used to generate bindings, but it will not be automatically
added to the compiled transformer code.

If your transformer code is written in C/C++, you may do so yourself.
For C, you may need to include "stdint.h" and "stdbool.h".
If your transform() function is written in C++, don't forget to add 'extern "C" '
*/

"""

if "type" not in input_schema:
    raise SeamlessTransformationError("Input schema (transformer.inp.schema) needs to be defined in JSON schema format, containing at least 'type'")

json_to_c = {
    "integer": "int",
    ("integer", 1): "int8_t",
    ("integer", 2): "int16_t",
    ("integer", 4): "int32_t",
    ("integer", 8): "int64_t",
    "number": "double",
    ("number", 4): "float",
    ("number", 8): "double",
    "boolean": "bool",
    "string": "char",
}

def gen_struct_name(name, postfix="Struct"):
    def capitalize(subname):
        return "".join([subsubname.capitalize() for subsubname in subname.split("_")])
    if isinstance(name, str):
        name = (name,)
    return "".join([capitalize(subname) for subname in name]) + postfix

def gen_basic_type(name, schema, *, verify_integer_bytesize, item=False):
    name2 = name
    if isinstance(name, (tuple, list)):
        name2 = ".".join(name)
    warnings = []
    has_form = "form" in schema
    if has_form:
        form = schema["form"]
        err = "'{0}' form schema does not provide ".format(name2)
    else:
        err = "'{0}' has no form schema that provides ".format(name2)
    if item:
        if "type" in schema:
            type = schema["type"]
        else:
            if not has_form or "type" not in form:
                raise SeamlessTransformationError("Item schema {0} must contain 'type' in its schema or form schema".format(name2))
            type = form["type"]
    else:
        type = schema["type"]
    ctype = json_to_c[type]
    result = ctype
    if type in ("integer", "number"):
        if not has_form or "bytesize" not in form:
            if type != "integer" or verify_integer_bytesize:
                warnings.append(err + "'bytesize', assuming default type ('%s')" % ctype)
            result = ctype
        else:
            result = json_to_c[type, form["bytesize"]]
    if type == "integer":
        if not has_form or "unsigned" not in form:
            warnings.append(err + "'unsigned', assuming False")
        else:
            if form["unsigned"]:
                if result.endswith("_t"):
                    result = "u" + result
                else:
                    result = "unsigned " +  result
    ###for warning in warnings:
    ###    print("WARNING: " + warning)
    return result

def gen_array(name, schema, *, verify_shape, const):
    name2 = name
    if isinstance(name, (tuple, list)):
        name2 = ".".join(name)

    if "form" not in schema:
        raise SeamlessTransformationError("'{0}' schema must have form schema".format(name2))

    form = schema["form"]
    array_struct_name = gen_struct_name(name)
    array_struct_members = []
    if verify_shape and "shape" not in form:
        raise SeamlessTransformationError("'{0}' form schema must have 'shape'".format(name2))
    if "ndim" not in form:
        raise SeamlessTransformationError("'{0}' form schema must have 'ndim'".format(name2))
    array_struct_members.append(("unsigned int", "shape[%d]" % form["ndim"]))

    warnings = []
    if not verify_shape:
        if "contiguous" not in form or not form["contiguous"]:
            if "contiguous" not in form or "strides" not in form:
                warn = "'{0}' form schema does not contain 'contiguous'. \
     Explicit stride values will be provided.".format(name2)
                warnings.append(warn)
            array_struct_members.append(("unsigned int", "strides[%d]" % form["ndim"]))

    itemschema = schema["items"]
    if isinstance(itemschema, list):
        raise NotImplementedError(name2) #heterogeneous arrays (tuples)

    tname = name
    struct_code = ""
    if isinstance(name, str):
        tname = (name,)
    if type == "array":
        raise NotImplementedError(name2) #nested array
    elif type == "object":
        req_storage = "pure-binary"
        ctype, nested_struct_code = gen_struct(
          tname+ ("item",), itemschema,
          verify_pure_binary=True,
          const=const
        )
        if const:
            ctype = "const " + ctype
        ctype += " *"
        struct_code += nested_struct_code + "\n"
    else:
        req_storage = "binary"
        ctype = gen_basic_type(
            tname+ ("item",),
            itemschema,
            verify_integer_bytesize=True,
            item=True
        )
    if "storage" not in schema or not schema["storage"].endswith(req_storage):
        raise SeamlessTransformationError("'{0}' schema must have {1} storage defined".format(name2, req_storage))
    ctype2 = ctype
    if const and not ctype2.startswith("const "):
        ctype2 = "const " + ctype
    array_struct_members.insert(0, (ctype2, "*data"))
    array_struct_code = gen_struct_code(array_struct_name, array_struct_members)
    for warning in warnings:
        print("WARNING: " + warning)
    struct_code += array_struct_code
    return array_struct_name, struct_code

def gen_struct_code(name, members):
    struct_code = "typedef struct {0} {{\n".format(name)
    for type, member_name in members:
        type = type.strip()
        if type[-1] != "*":
            type += " "
        struct_code += "  {0}{1};\n".format(type, member_name)
    struct_code += "}} {0};\n\n".format(name)
    return struct_code

def gen_struct(name, schema, *, verify_pure_binary, const):
    name2 = name
    if isinstance(name, (tuple, list)):
        name2 = ".".join(name)
    if verify_pure_binary is not None:
        req_storage = "pure-binary" if verify_pure_binary else "binary"
        if "storage" not in schema or not schema["storage"].endswith(req_storage):
            raise SeamlessTransformationError("'{0}' schema must have {1} storage defined".format(name2, req_storage))
    struct_name = gen_struct_name(name)
    struct_members = []
    tname = name
    if isinstance(name, str):
        tname = (name,)
    struct_code = ""
    for propname, propschema in schema["properties"].items():
        type = propschema["type"]
        pname = tname + (propname,)
        if type == "array":
            ctype, nested_struct_code = gen_array(
              pname, propschema,
              verify_shape=True,
              const=const
            )
            if const:
                ctype = "const " + ctype
            ctype += " *"
            struct_code += nested_struct_code
        elif type == "object":
            ctype, nested_struct_code = gen_struct(
              pname, propschema,
              verify_pure_binary=True
            )
            if const:
                ctype = "const " + ctype
            ctype += " *"
            struct_code += nested_struct_code
        else:
            ctype = gen_basic_type(propname, propschema, verify_integer_bytesize=True)
        struct_members.append((ctype, propname))

    struct_code += gen_struct_code(struct_name, struct_members)
    return struct_name, struct_code

###print("input schema:", input_schema)
###print("result schema:", result_schema)

input_args = []
input_jtype = input_schema["type"]
if input_jtype == "array":
    raise NotImplementedError
elif input_jtype == "object":
    input_props = input_schema["properties"]
else:
    input_props = {input_name: input_schema}

for pin in inputpins:
    if pin not in input_props:
        raise SeamlessTransformationError("Input pin '%s' is not in input schema" % pin)

order = input_schema.get("order", [])
for propname in sorted(input_props.keys()):
    if propname not in order:
        order.append(propname)
for propnr, propname in enumerate(order):
    propschema = input_props[propname]
    if "type" not in propschema:
        raise SeamlessTransformationError("Property '%s' needs to have its type defined" % propname)
    prop_jtype = propschema["type"]
    if prop_jtype == "object":
        raise NotImplementedError #input structs
    elif prop_jtype == "array":
        prop_ctype, array_struct_header = gen_array(propname, propschema, verify_shape=False, const=True)
        prop_ctype = "const " + prop_ctype + "*"
        header += array_struct_header
    else:
        prop_ctype = gen_basic_type(propname, propschema, verify_integer_bytesize=False)
    input_args.append(prop_ctype + " " + propname)


if "type" not in result_schema:
    raise SeamlessTransformationError("Result schema (transformer.result.schema) needs to be defined in JSON schema format, containing at least 'type'")    

return_jtype = result_schema["type"]
if return_jtype == "object":
    return_ctype = "void"
    output_ctype, struct_header = gen_struct(result_name, result_schema, verify_pure_binary=None, const=False)
    header += struct_header
    input_args.append(output_ctype + " *" + result_name)
elif return_jtype == "array":
    return_ctype = "void"
    output_ctype, struct_header = gen_array(
        result_name, result_schema, 
        verify_shape=True, const=False
    )
    header += struct_header
    input_args.append(output_ctype + " *" + result_name)
else:
    output_ctype = gen_basic_type(result_name, result_schema, verify_integer_bytesize=False)
    input_args.append(output_ctype + " *" + result_name)

input_args = ", ".join(input_args)
result = header
result += "int transform({});".format(input_args)
