# Copyright 2007-2016, Sjoerd de Vries


def macro_bracket_length(name, content):
    original_content = content
    default = ""
    assign_index_start = original_content.find("=")

    if assign_index_start > -1:
        original_content = content[:assign_index_start].rstrip()
        default = content[assign_index_start:]

    if not original_content.endswith("]"):
        return

    assign_index_start = original_content.rfind("[")
    result = name + " " + original_content[:assign_index_start] + default
    length = original_content[assign_index_start+1:-1]
    attrib_name = original_content[:assign_index_start]

    result += "\nvalidate {\n  assert %s is None or len(%s) == %s\n}" % (attrib_name, attrib_name, length)
    result += "\nform {\n  %s.length = %s\n  %s.form = \"hard\"\n}\n" % (attrib_name, length, attrib_name)

    return result
