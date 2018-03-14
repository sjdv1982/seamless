import re, shlex
from ..silk.typeparse.parse import mask_characters
from .parse_slash0_utils import syntax_error, tokenize, doc_name, literal, \
 append_node, find_node, quote_match

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

def parse_doc_name(word, lineno, l):
    if doc_name.match(word) is None:
        msg = "Invalid doc name: '%s'" % word
        syntax_error(lineno, l, msg)
    return word

varsplit = re.compile(r"([/\-]+)")
match_dollar = re.compile(r"(?<![\\])\$")
def parse_variable_expression(cmd_index, word, lineno, l, nodes, noderefs):
    #noderefs are appended
    def parse_variable_subexpr(subexpr, masked_subexpr):
        dollars = list(match_dollar.finditer(masked_subexpr))
        if not len(dollars):
            return subexpr
        pos = None
        for dollar in dollars + [None]:
            if dollar is None:
                newpos = len(subexpr)
            else:
                newpos = dollar.start()
            if pos is None:
                result = subexpr[:newpos]
                pos = newpos
                continue
            varname = subexpr[pos+1:newpos]
            try:
                node_index = find_node(varname, "variable", nodes)[1]
            except NameError:

                if varname.isupper(): #environment variable
                    node = {
                        "name": varname
                    }
                    node_index = append_node(nodes, "env", node)
                    noderef = {
                        "command_index": cmd_index,
                        "type": "env",
                        "index": node_index,
                    }
                    noderefs.append(noderef)
                    result += "{%d}" % (len(noderefs)-1)
                    continue

                msg = "Unknown variable name '%s'" % varname
                syntax_error(lineno, l, msg)
            noderef = {
                "command_index": cmd_index,
                "type": "variable",
                "index": node_index,
                "mode": "input",
            }
            noderefs.append(noderef)
            result += "{%d}" % (len(noderefs)-1)
        return result

    masked_word = mask_characters(quote_match, word, word, '*')[0]
    pos = 0
    varexpr = ""
    for match in varsplit.finditer(masked_word):
        subexpr = word[pos:match.start()]
        masked_subexpr = masked_word[pos:match.start()]
        varexpr += parse_variable_subexpr(subexpr, masked_subexpr)
        varexpr += word[match.start():match.end()]
        pos = match.end()
    subexpr = word[pos:]
    masked_subexpr = masked_word[pos:]
    varexpr += parse_variable_subexpr(subexpr, masked_subexpr)
    return varexpr

def parse_command_name(cmd_index, word, lineno, l, nodes, noderefs):
    #nodes and noderefs are appended
    if word.startswith("/") or word.startswith("./") or word.startswith("~/"):
        dollar = word.find("$")
        if dollar > -1:
            msg = "Environment variables in command names must be at the beginning"
            syntax_error(lineno, l, msg)
        noderef = {"type": "file", "value": word}
        command_name_str = "{%d}" % len(noderefs)
        noderefs.append(noderef)
        return command_name_str
    subwords = re.split(r"([/\-]+)", word)
    assert len(subwords) % 2
    command_name_str = ""
    for subwordnr, subword in enumerate(subwords):
        if subwordnr % 2:
            command_name_str += subword
            continue
        if not len(subword):
            continue
        dollar = subword.find("$")
        if subwordnr > 0 and dollar > 0:
            msg = "Environment variables in command names must be at the beginning"
            syntax_error(lineno, l, msg)
        if subwordnr == 0 and dollar == 0:
            envname = subword[1:]
            if not envname.isupper():
                msg = "Only environment variables (all-capital) are allowed in command names"
                syntax_error(lineno, l, msg)
            node = {
                "name": envname
            }
            node_index = append_node(nodes, "env", node)
            noderef = {
                "command_index": cmd_index,
                "type": "env",
                "index": node_index,
            }
            command_name_str += "{%d}" % len(noderefs)
            noderefs.append(noderef)
        else:
            command_name_str += subword
    return command_name_str

def parse_command_argument(cmd_index, word, lineno, l, nodes, noderefs):
    #nodes and noderefs are appended
    if quote_match.match(word):
        v = parse_literal(word, lineno, l)
        v = v.replace("{", "{{").replace("}", "}}")
        return shlex.quote(v)
    has_dollars = False
    for pos0 in re.finditer(r"\$", word):
        pos = pos0.start()
        if pos == 0 or word[pos-1] != "\\":
            has_dollars = True
            break
    if word[0] == "!":
        if has_dollars:
            msg = "Slash-0 doc expressions cannot contain $"
            syntax_error(lineno, l, msg)
        v = parse_doc_name(word[1:], lineno, l)
        try:
            node_type, node_index = find_node(v, "doc", nodes)
        except NameError:
            msg = "Unknown doc name '%s'" % v
            syntax_error(lineno, l, msg)
        noderef = {
            "command_index": cmd_index,
            "type": node_type,
            "index": node_index,
            "mode": "input",
        }
        noderefs.append(noderef)
        return "{%d}" % (len(noderefs) - 1)
    else:
        if not has_dollars:
            if word.startswith("/") or word.startswith("./") or word.startswith("~/"):
                noderef = {"type": "file", "value": word}
                noderefs.append(noderef)
                return "{%d}" % (len(noderefs) - 1)
            if word[0].isdigit() or word[0] == "-":
                pass #variable expression
            else:
                msg = """Ambiguous expression: {0}
If a doc name is meant, write as !{0}
If a variable name is meant, write as ${0}
If a literal is meant, write as "{0}" """.format(word)
                syntax_error(lineno, l, msg)
        varexp_noderefs = []
        v = parse_variable_expression(cmd_index, word, lineno, l, nodes, varexp_noderefs)
        noderefs.append({"type": "varexp", "value": v, "noderefs": varexp_noderefs})
        return "{%d}" % (len(noderefs) - 1)


##################################
#firstpass = ["input_doc", "input_var", "subcontext", "doc_array",
#"doc_var_list", "doc_var", "intern", "intern_json", "extern"]

def cmd_input_doc(line, nodes):
    command, lineno, l, words = line
    assert len(words) == 2, l
    doc_name = parse_doc_name(words[1], lineno, l)
    node = {
        "name": doc_name,
        "origin": "input",
        "is_array": False
    }
    append_node(nodes, "doc", node)

def cmd_input_var(line, nodes):
    command, lineno, l, words = line
    assert len(words) == 2, l
    var_name = parse_doc_name(words[1], lineno, l)
    node = {
        "name": var_name,
        "origin": "input",
        "is_array": False
    }
    append_node(nodes, "variable", node)


def cmd_subcontext(line, nodes):
    command, lineno, l, words = line
    assert len(words) == 2, l
    context_name = parse_doc_name(words[1], lineno, l)
    node = {
        "name": context_name,
        "is_json": False
    }
    append_node(nodes, "context", node)

def cmd_doc_array(line, nodes):
    raise NotImplementedError

def cmd_var(line, nodes):
    raise NotImplementedError

def cmd_var_list(line, nodes):
    raise NotImplementedError

def cmd_intern(line, nodes):
    command, lineno, l, words = line
    assert len(words) == 2, l
    doc_name = parse_doc_name(words[1], lineno, l)
    node = {
        "name": doc_name,
        "origin": "intern",
        "is_array": False
    }
    append_node(nodes, "doc", node)

def cmd_intern_json(line, nodes):
    command, lineno, l, words = line
    assert len(words) == 2, l
    context_name = parse_doc_name(words[1], lineno, l)
    node = {
        "name": context_name,
        "is_json": True
    }
    append_node(nodes, "context", node)

def cmd_extern(line, nodes):
    command, lineno, l, words = line
    assert len(words) == 2, l
    doc_name = parse_doc_name(words[1], lineno, l)
    node = {
        "name": doc_name,
        "origin": "extern",
        "is_array": False
    }
    append_node(nodes, "doc", node)

###############################

def cmd_export(line, nodes):
    command, lineno, l, words = line
    assert len(words) == 2, l
    name = parse_doc_name(words[1], lineno, l)
    try:
        node_type, node_index = find_node(name, ["doc", "context", "variable"], nodes)
    except NameError:
        msg = "Unknown symbol '%s'" % name
        syntax_error(lineno, l, msg)
    noderef = {
        "command_index": None,
        "type": node_type,
        "index": node_index,
        "mode": "input",
    }
    return noderef

###############################

def cmd_standard(cmd_index, line, nodes):
    def parse_pragma(pragma0):
        pnr = 0
        pragma = []
        while 1:
            #TODO: use argparse
            if pnr == len(pragma0): break
            p = pragma0[pnr]
            if p == "monitor":
                pragma.append(p)
                try:
                    delay = float(pragma0[pnr+1])
                    pnr += 1
                except (ValueError, IndexError):
                    delay = 2 #default monitor every 2 secs
                pragma.append(delay)
            else:
                msg = "unknown pragma '%s'"
                syntax_error(lineno, l, msg % p)
            pnr += 1
        pragma0[:] = pragma
    command, lineno, l, words = line
    noderefs = []
    parsed = []
    outputs = []
    capture = None
    pragma = []
    mode = "command"
    capt_stdout, capt_stderr = False, False
    for word in words:
        if word in ("|", ";"):
            assert mode == "arg" #TODO: nicer error message
            if len(outputs) or capture is not None:
               msg = "'>' must be in the last subcommand, no '|' or ';' may follow"
               syntax_error(lineno, l, msg)
            mode = "command"
            parsed.append(word)
        elif word in (">", "2>", ">&", "!>"):
            assert mode in ("arg", "arg-redirect") #TODO: nicer error message
            mode = "output"
            submode = word
        elif mode == "command":
            p = parse_command_name(cmd_index, word, lineno, l, nodes, noderefs)
            parsed.append(p)
            mode = "arg"
        elif mode == "arg":
            p = parse_command_argument(cmd_index, word, lineno, l, nodes, noderefs)
            parsed.append(p)
        elif mode == "output":
            doc_name = parse_doc_name(word, lineno, l)
            if doc_name == "NULL":
                node_type, node_index = "doc", -1
            else:
                try:
                    node_type, node_index = find_node(doc_name, ["doc", "context"], nodes)
                except NameError:
                    syntax_error(lineno, l, "Unknown doc name: %s" % doc_name)
            noderef = {
                "command_index": None,
                "type": node_type,
                "index": node_index,
                "mode": "output",
            }
            if submode == "!>":
                if node_type != "context":
                   msg = "!> must assign to context"
                   syntax_error(lineno, l, msg)
                if capture is not None:
                    syntax_error(lineno, l, "Multiple !> in command")
                node = nodes["context"][node_index]
                if not node["is_json"]:
                    syntax_error(lineno, l, "!> must assign to JSON context")
                capture = noderef
            else:
                if node_type == "context":
                    msg = "Cannot assign to context '%s'" % doc_name
                    syntax_error(lineno, l, msg)
                output_types = {
                    ">": "stdout",
                    "2>": "stderr",
                    ">&": "stdout+stderr",
                }
                capt_mode = output_types[submode]
                if "stdout" in capt_mode:
                    if capt_stdout:
                        msg = "Multiple capture of stdout (other than |)"
                        syntax_error(lineno, l, msg)
                    capt_stdout = True
                if "stderr" in capt_mode:
                    if capt_stderr:
                        msg = "Multiple capture of stderr"
                        syntax_error(lineno, l, msg)
                    capt_stdout = True
                output_type = capt_mode
                outputs.append({
                    "type": output_type,
                    "noderef": noderef
                })
            mode = "arg-redirect"
        elif mode == "arg-redirect":
            if word.startswith("@"):
                mode = "pragma"
                word = word[1:].strip()
                if len(word):
                    pragma.append(word)
                continue
            if capture:
                msg = "Expected >, 2> or >&"
            else:
                msg = "Expected >, 2>, >& or !>"
            syntax_error(lineno, l, msg)
        elif mode == "pragma":
            pragma.append(word)
        else:
            msg = "Malformed command"
            syntax_error(lineno, l, msg)
    result = {
        "cmd" : {
            "command": command,
            #"lineno": lineno,
            "lineno": "X", #disable for caching purposes (re-arranging lines shouldn't be a cache miss)
            "source": l,
        },
        "parsed": parsed,
        "noderefs": noderefs,
        "outputs": outputs
    }
    if capture is not None:
        result["capture"] = capture
    if len(pragma):
        parse_pragma(pragma)
        result["pragma"] = pragma
    return result

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

def cmd_doc(cmd_index, line, nodes):
    raise NotImplementedError
    """
    command, lineno, l, words = line
    assert len(words) == 2, l
    doc_name = parse_doc_name(words[1], lineno, l)
    assert doc_name in nodes["doc"], doc_name
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



cmd_funcs = {
    "standard": cmd_standard,
    "assign": cmd_assign,

    "cat": cmd_cat,
    "read": cmd_read,
    "lines": cmd_lines,
    "fields": cmd_fields,
    "doc": cmd_doc,
    "load": cmd_load,
    "map": cmd_map,

    "input_doc": cmd_input_doc,
    "input_var": cmd_input_var,
    "export": cmd_export,
    "subcontext": cmd_subcontext,
    "doc_array": cmd_doc_array,
    "doc_var_list": cmd_var,
    "doc_var": cmd_var_list,
    "intern": cmd_intern,
    "intern_json": cmd_intern_json,
    "extern": cmd_extern,
}
firstpass = ["input_doc", "input_var", "subcontext", "doc_array",
"doc_var_list", "doc_var", "intern", "intern_json", "extern"]
