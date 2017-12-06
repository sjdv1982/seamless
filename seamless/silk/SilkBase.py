from functools import partialmethod
import json
import textwrap

class SilkBase:

    def __delitem__(self, item):
        data = super().__getattribute__("data")
        return data.__delitem__(item)

    def __contains__(self, item):
        try:
            method = self._get("__contains__")
        except AttributeError:
            return NotImplementedError
        return method(item)

    def __str__(self):
        # TODO: proper string representation
        data = super().__getattribute__("data")
        return str(data)

    def __repr__(self):
        # TODO: proper string representation
        data = super().__getattribute__("data")
        return repr(data)

def silk_unary_method(self, name):
    #print("METHOD", name)
    method = self._get(name)
    if method is NotImplemented:
        return NotImplemented
    return method()

unary_special_method_names = (
    "__len__",
    "__neg__", "__pos__", "__abs__",
    "__invert__", "__complex__",
    "__int__", "__float__",
    "__round__",
)

for name in unary_special_method_names:
    m = partialmethod(silk_unary_method, name=name)
    setattr(SilkBase, name, m)


def silk_unary_method_optional(self, name):
    #print("METHOD", name)
    try:
        method = self._get(name)
    except AttributeError:
        return NotImplementedError
    return method()

unary_special_method_names_optional = (
    "__length_hint__", "__index__",
    "__iter__", "__reversed__", "__bool__"
)

for name in unary_special_method_names_optional:
    m = partialmethod(silk_unary_method_optional, name=name)
    setattr(SilkBase, name, m)


def silk_binary_method(self, other, name):
    #print("METHOD", name)
    method = self._get(name)
    if method is NotImplemented:
        return NotImplemented
    return method(other)

binary_special_method_names = (
    "__add__", "__sub__", "__mul__", "__matmul__", "__truediv__",
    "__floordiv__", "__mod__", "__divmod__", "__pow__", "__lshift__",
    "__rshift__", "__and__", "__xor__", "__or__",

    "__radd__", "__rsub__", "__rmul__", "__rmatmul__", "__rtruediv__",
    "__rfloordiv__", "__rmod__", "__rdivmod__", "__rpow__", "__rlshift__",
    "__rrshift__", "__rand__", "__rxor__", "__ror__",

    "__iadd__", "__isub__", "__imul__", "__imatmul__", "__itruediv__",
    "__ifloordiv__", "__imod__", "__ipow__", "__ilshift__",
    "__irshift__", "__iand__", "__ixor__", "__ior__",

    "__lt__" , "__le__", "__eq__", "__gt__", "__ge__",
    #TODO: __ne__ (optional)
)
for name in binary_special_method_names:
    m = partialmethod(silk_binary_method, name=name)
    setattr(SilkBase, name, m)

#TODO: methods that modify the data:
# - append, insert, pop, etc.
# These must be followed by .validate()

####

import ast
from functools import lru_cache

def compile_function(code_dict, mode="method"):
    assert isinstance(code_dict, dict)
    assert code_dict["language"] == "python"
    code = code_dict["code"]
    return compile_function_(code, mode)

@lru_cache(10000)
def compile_function_(code, mode):
    code = textwrap.dedent(code)
    #import astdump
    #print(astdump.indented(code))
    ast_tree = compile(code, "<string>", "exec", ast.PyCF_ONLY_AST)
    assert len(ast_tree.body) == 1
    func = ast_tree.body[0]

    if isinstance(func, ast.FunctionDef):
        func_name = ast_tree.body[0].name
        namespace = {}
        code = compile(ast_tree, "<string>", "exec")
        exec(code, namespace)
        return namespace[func_name]
    elif mode == "method":
        assert isinstance(func, ast.Assign)
        fv = func.value
        assert isinstance(fv, ast.Lambda)
        code = compile(ast.Expression(fv), "<string>", "eval")
        return eval(code)
    elif mode == "property-getter":
        if isinstance(func.value, ast.Call):
            fv = func.value.args[0]
        elif isinstance(func, ast.Assign):
            fv = func.value
        else:
            raise AssertionError
        assert isinstance(fv, ast.Lambda)
        code = compile(ast.Expression(fv), "<string>", "eval")
        return eval(code)
    elif mode == "property-setter":
        raise SyntaxError(code)
    else:
        raise SyntaxError(code)

class AlphabeticDict(dict):
    def __iter__(self):
        return iter(sorted(super().__iter__()))
    def __str__(self):
        return json.dumps(self, sort_keys=True, indent=2)
