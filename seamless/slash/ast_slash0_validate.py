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
        symbols[node["name"]]["noderefs"].append(noderef)
    import pprint; pprint.pprint(symbols)
