from parse_slash0_utils import tokenize, double_quote, single_quote

def parse_literal(word, maskpos):
    word_unmasked = "".join(
        [c1 for c1,c2 in zip(word, word_masked) if c1 != c2]
    )
    w1 = re.sub(single_quote, word, "")
    w2 = re.sub(double_quote, w1, "")
    return w2

def cmd_standard(line, nodes):
    raise NotImplementedError

def cmd_assign(line, nodes):
    raise NotImplementedError

def cmd_cat(line, nodes):
    raise NotImplementedError

def cmd_read(line, nodes):
    raise NotImplementedError

def cmd_lines(line, nodes):
    raise NotImplementedError

def cmd_fields(line, nodes):
    raise NotImplementedError

def cmd_cell(line, nodes):
    raise NotImplementedError

def cmd_load(line, nodes):
    raise NotImplementedError

def cmd_map(line, nodes):
    raise NotImplementedError

def cmd_input_cell(line, nodes):
    command, lnr, l, words = line
    assert len(words) == 2, l
    cell_name = parse_cell_name(words[1])
    node = {
        "name": cell_name,
        "origin": "input",
        "is_array": False
    }
    nodes["cell"].append(node)


def cmd_input_var(line, nodes):
    raise NotImplementedError

def cmd_export(line, nodes):
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
    raise NotImplementedError

def cmd_extern(line, nodes):
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
