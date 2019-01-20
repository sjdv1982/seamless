import linecache
import functools
from ast import PyCF_ONLY_AST, FunctionDef, Expr, Lambda

@functools.lru_cache(maxsize=1000)
def cached_compile(code, identifier, mode="exec", flags=None, \
  dont_inherit=0):
    if flags is not None:
        astree = compile(code, identifier, mode, flags, dont_inherit)
    else:
        astree = compile(code, identifier, mode, dont_inherit=dont_inherit)
    cache_entry = (
        len(code), None,
        [line+'\n' for line in code.splitlines()], identifier
    )
    linecache.cache[identifier] = cache_entry
    return astree


def analyze_code(code, codename):
    astree = cached_compile(code, codename, "exec", PyCF_ONLY_AST)
    mode = "block"
    func_name = None
    if len(astree.body) == 1:
        if isinstance(astree.body[0], FunctionDef):
            mode = "function"
            func_name = astree.body[0].name
        elif isinstance(astree.body[0], Expr):
            if len(code.splitlines()) == 1:
                if isinstance(astree.body[0].value, Lambda):
                    mode = "lambda"
                else:
                    mode = "expression"
            else:
                err = "no multiline expressions or lambdas, may give indentation syntax errors"
                raise SyntaxError((codename, err))
    return mode, func_name