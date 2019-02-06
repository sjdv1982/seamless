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

@functools.lru_cache(maxsize=1000)
def analyze_code(code, identifier):
    astree = cached_compile(code, identifier, "exec", PyCF_ONLY_AST)
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
                raise SyntaxError((identifier, err))
    return mode, func_name

def exec_code(code, identifier, namespace, inputs, output):
    mode, func_name = analyze_code(code, identifier)
    input_params = ",".join(["{0}={0}".format(inp) for inp in sorted(list(inputs))])
    if mode == "block":
        code2 = code
    elif mode == "function":
        code2 = code + "\n\n"
        if output is None:
            code2 += "%s(%s)" % (func_name, input_params)
        else:
            code2 += "%s = %s(%s)" % (output, func_name, input_params)
    elif mode == "lambda":
        assert output is not None
        code2 = "LAMBDA = " + code + "\n\n"
        code2 += "%s = LAMBDA(%s)" % (output, input_params)
    elif mode == "expression":
        assert output is not None
        code2 = "%s = " % output + code 
    code_obj = cached_compile(code2, identifier)
    exec(code_obj, namespace)
    
    