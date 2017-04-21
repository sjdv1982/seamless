from ..core.macro import macro

@macro(("text", "code", "slash-0"))
def slash0(ctx, code):
    import os
    from seamless.slash.parse_slash0 import parse_slash0
    from seamless.slash.ast_slash0_validate import ast_slash0_validate
    ast = parse_slash0(code)
    symbols = ast_slash0_validate(ast)
    for node_type in ast["nodes"]:
        nodes = ast["nodes"][node_type]
        for node in nodes:
            if node_type == "env":
                print(node)
