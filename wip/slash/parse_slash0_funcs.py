from parse_slash0_utils import syntax_error, tokenize, cell_name, literal

def parse_literal(word, lineno, l):
    if word[0] == word[-1] == "'":
        v = word[1:-1]
    elif word[0] == word[-1] == '"':
        v = word[1:-1]
    else:
        v = word
    if literal.match(v) is None:
        msg = "Invalid literal: '%s'" % v
        syntax_error(lineno, l, msg)
    return v

def parse_cell_name(word, lnr, l):
    if cell_name.match(word) is None:
        msg = "Invalid cell name: '%s'" % word
        syntax_error(lineno, l, msg)
    return word

##################################
#firstpass = ["input_cell", "input_var", "subcontext", "cell_array",
#"cell_var_list", "cell_var", "intern", "intern_json", "extern"]

def cmd_input_cell(line, nodes):
    command, lineno, l, words = line
    assert len(words) == 2, l
    cell_name = parse_cell_name(words[1], lineno, l)
    node = {
        "name": cell_name,
        "origin": "input",
        "is_array": False
    }
    nodes["cell"].append(node)

def cmd_input_var(line, nodes):
    raise NotImplementedError

def cmd_subcontext(line, nodes):
    raise NotImplementedError

def cmd_cell_array(line, nodes):
    raise NotImplementedError

def cmd_var(line, nodes):
    raise NotImplementedError

def cmd_var_list(line, nodes):
    raise NotImplementedError

def cmd_intern(line, nodes):
    raise NotImplementedError

def cmd_intern_json(line, nodes):
    command, lineno, l, words = line
    assert len(words) == 2, l
    context_name = parse_cell_name(words[1], lineno, l)
    node = {
        "name": context_name,
        "is_json": True
    }
    nodes["context"].append(node)

def cmd_extern(line, nodes):
    raise NotImplementedError

###############################

def cmd_standard(cmd_index, line, nodes):
    raise NotImplementedError

def cmd_assign(cmd_index, line, nodes):
    raise NotImplementedError

def cmd_cat(cmd_index, line, nodes):
    raise NotImplementedError

def cmd_read(cmd_index, line, nodes):
    raise NotImplementedError

def cmd_lines(cmd_index, line, nodes):
    raise NotImplementedError

def cmd_fields(cmd_index, line, nodes):
    raise NotImplementedError

def cmd_cell(cmd_index, line, nodes):
    raise NotImplementedError
    """
    command, lineno, l, words = line
    assert len(words) == 2, l
    cell_name = parse_cell_name(words[1], lineno, l)
    assert cell_name in nodes["cell"], cell_name
    return {
        "index": cmd_index,
        "lineno": line+1,
        "type": words[0],

    }
    """

def cmd_load(cmd_index, line, nodes):
    raise NotImplementedError

def cmd_map(cmd_index, line, nodes):
    raise NotImplementedError

########

def cmd_export(line, nodes):
    raise NotImplementedError


cmd_funcs = {
    "standard": cmd_standard,
    "assign": cmd_assign,

    "cat": cmd_cat,
    "read": cmd_read,
    "lines": cmd_lines,
    "fields": cmd_fields,
    "cell": cmd_cell,
    "load": cmd_load,
    "map": cmd_map,

    "input_cell": cmd_input_cell,
    "input_var": cmd_input_var,
    "export": cmd_export,
    "subcontext": cmd_subcontext,
    "cell_array": cmd_cell_array,
    "cell_var_list": cmd_var,
    "cell_var": cmd_var_list,
    "intern": cmd_intern,
    "intern_json": cmd_intern_json,
    "extern": cmd_extern,
}
firstpass = ["input_cell", "input_var", "subcontext", "cell_array",
"cell_var_list", "cell_var", "intern", "intern_json", "extern"]
