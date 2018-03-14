def find_symbols(nodes):
    symbols = {} #variables, docs and contexts
    for symbol_type in ("doc", "variable", "context"):
        for node in nodes[symbol_type]:
            name = node["name"]
            if name in symbols:
                other_symbol_type = symbols[name]["type"]
                msg = "Duplicate symbol name: %s (%s and %s)"
                raise Exception(msg % (name, symbol_type, other_symbol_type))
            symbols[name] = {
                "type": symbol_type,
                "node": node,
                "noderefs": [],
            }
    return symbols

def find_noderefs(ast):
    noderefs = []
    noderefs += ast["exports"]
    def mine_noderefs(d):
        if isinstance(d, list) and not isinstance(d, (str, bytes)):
            for dd in d:
                mine_noderefs(dd)
        if not isinstance(d, dict):
            return
        if "command_index" in d and \
          "index" in d and \
          "type" in d:
            noderefs.append(d)
        for field in d.keys():
            mine_noderefs(d[field])
    for command in ast["commands"]:
        mine_noderefs(command)
    return noderefs



def ast_slash0_validate(ast):
    def validate_head():
        splits = head.split("/")
        for n in reversed(range(len(splits))):
            sub = "/".join(splits[:n+1])
            if sub not in symbols:
                msg = "%s '%s' is declared, but not context '%s'"
                raise Exception(msg % (node_type.capitalize(), name, sub))

    nodes = ast["nodes"]
    symbols = find_symbols(nodes)
    noderefs = find_noderefs(ast)
    for noderef in noderefs:
        node_type = noderef["type"]
        node_index = noderef["index"]
        if node_index == -1:
            continue
        if node_type == "env":
            continue
        node = nodes[node_type][node_index]
        name = node["name"]
        if node_type == "doc":
            last_slash = name.rfind("/")
            if last_slash > -1:
                head = name[:last_slash]
                validate_head()
        if node_type == "context":
            head = name
            validate_head()
        symbols[name]["noderefs"].append(noderef)
    for symbol_name in symbols:
        symbol = symbols[symbol_name]
        nr_inputs = len([n for n in symbol["noderefs"] if n["mode"] == "input"])
        nr_outputs = len([n for n in symbol["noderefs"] if n["mode"] == "output"])
        if nr_outputs > 1:
            raise Exception("Multiple assigments to '%s'" % symbol_name)
        if nr_inputs == 0:
            print("WARNING: unused %s '%s'" % (symbol["type"], symbol_name))
        if symbol["type"] == "doc":
            node = symbol["node"]
            if node["origin"] in ("input", "extern") and nr_outputs > 0:
                raise Exception("Cannot assign to %s doc '%s'" % (node["origin"], symbol_name))
    return symbols
