from ast import FunctionDef, Return, iter_child_nodes


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

    raise ValueError("Return AST node not found for the given node or its children: '{}'".format(node))
