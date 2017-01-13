from ast import FunctionDef, Return, iter_child_nodes

def strip_source(source):
    init = 99999999
    indent = init
    for l in source.splitlines():
        i = len(l) - len(l.lstrip())
        if i < indent:
            indent = i
    if indent == init:
        return source
    ret = ""
    for l in source.splitlines():
        ret += l[indent:] + "\n"
    return ret

def find_return_in_scope(node):
    """Find return ast Node in current scope

    :param node: ast.Node instance
    """
    from collections import deque
    todo = deque([node])

    while todo:
        node = todo.popleft()

        if isinstance(node, FunctionDef):
            continue

        elif isinstance(node, Return):
            return node

        todo.extend(iter_child_nodes(node))

    raise ValueError("Return not found")
