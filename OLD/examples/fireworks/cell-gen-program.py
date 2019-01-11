program = program_template
attributes = {}
for propname, prop in VertexData._props.items():
    attributes[propname] = {
        "dtype": prop["typename"].lower(),
        "array": "vertexdata",
        "rae": "['%s']" % propname,
    }
program["render"]["attributes"] = attributes
return program
