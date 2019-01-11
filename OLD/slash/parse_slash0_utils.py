import re
quote_match = re.compile(r'(([\"\']).*?\2)')
double_quote = re.compile(r'(\A|[^\\])\"')
single_quote = re.compile(r"(\A|[^\\])\'")
doc_name = re.compile(r'^[A-Za-z_][A-Za-z0-9_/]*$')
token_separators=r'(?P<sep1>[\s]+)|[\s](?P<sep2>2>)[^&][^1]|[\s](?P<sep3>!>)[\s]|[\s](?P<sep4>2>&1)|(?P<sep5>(?<![2!])>)|(?P<sep6>[;|])'
token_separators = re.compile(token_separators)
literal = re.compile(r'.*') #rely on shlex.quote

def find_node(node_name, nodetypes, nodes):
    if isinstance(nodetypes, str):
        nodetypes = [nodetypes]
    for nodetype in nodetypes:
        for node_index, node in enumerate(nodes[nodetype]):
            if node["name"] == node_name:
                return nodetype, node_index
    raise NameError(node_name, nodetypes)

def append_node(nodes, nodetype, node):
    for curr_node_index, curr_node in enumerate(nodes[nodetype]):
        if curr_node:
            if curr_node["name"] == node["name"]:
                for field in curr_node:
                    assert field in node, field #TODO: more informative message...
                    assert node[field] == curr_node[field], field #TODO: more informative message...
                for field in node:
                    assert field in curr_node, field #TODO: more informative message...
                return curr_node_index
    for other_nodetype in nodes.keys():
        if other_nodetype == nodetype:
            continue
        for curr_node in nodes[other_nodetype]:
            assert curr_node["name"] != node["name"], (nodetype, other_nodetype, node["name"]) #TODO: nicer error message
    nodes[nodetype].append(node)
    return len(nodes[nodetype]) - 1

def syntax_error(lineno, line, message):
    message = "    " + "\n    ".join(message.splitlines())
    msg = """Line {0}:
    {1}
Error message:
{2}""".format(lineno, line, message)
    raise SyntaxError(msg)

def tokenize(text, masked_text):
    tokens = []
    pos = 0
    for match in token_separators.finditer(masked_text):
        seps = match.groupdict()
        split_tokens = [v for v in seps.values() if v is not None]
        assert len(split_tokens) == 1, seps
        split_token = split_tokens[0].strip()
        newpos = match.start()
        if pos != newpos:
            tokens.append(text[pos:newpos])
        pos = match.end()
        if len(split_token):
            tokens.append(split_token)
    tokens.append(text[pos:])
    return tokens
