from ast import PyCF_ONLY_AST, FunctionDef
from abc import ABCMeta, abstractmethod

from ..core.utils import find_return_in_scope
from . import parse, serialize


class DataObject:

    def __init__(self, name, data_type, data = None):
        self.name = name
        self.data_type = data_type
        self.data = None

        if data is not None:
            self.parse(data)

    def parse(self, data):
        self.data = parse(self.data_type, data, trusted=True)

    def serialize(self):
        return serialize(self.data_type, self.data)

    def validate(self):
        pass


class PythonCodeObject(DataObject, metaclass=ABCMeta):
    code = None
    ast = None

    def parse(self, data):
        self.data = data
        self.ast = compile(data, self.name, "exec", PyCF_ONLY_AST)

    def serialize(self):
        return self.data

    @abstractmethod
    def validate(self):
        pass


class PythonExpressionObject(PythonCodeObject):

    def validate(self):
        self.code = compile(self.data, self.name, "eval")


class PythonBlockObject(PythonCodeObject):

    def validate(self):
        self.code = compile(self.data, self.name, "exec")


class PythonTransformerCodeObject(PythonCodeObject):
    """Python code object used for transformers (accepts one argument)"""
    func_name = "transform"

    def validate(self):
        is_function = (len(self.ast.body) == 1 and isinstance(self.ast.body[0], FunctionDef))

        if is_function:
            self.code = compile(self.ast, self.name, "exec")
            self.func_name = self.ast.body[0].name

        else:
            try:
                return_node = find_return_in_scope(self.ast)

            except ValueError:
                raise SyntaxError("Block must contain return statement(s)")

            patched_src = "def transform(value):\n    " + self.data.replace("\n", "\n    ").rstrip()

            self.code = compile(patched_src, self.name, "exec")
            self.func_name = "transform"


def data_type_to_data_object(data_type):
    from . import is_registered
    assert is_registered(data_type)

    if data_type[:2] == ("text", "code"):
        return DataObject #by default, code is just text!

    elif data_type[:3] == ("text", "data", "json"):
        raise NotImplementedError

    elif data_type[:3] == ("text", "data", "xml"):
        raise NotImplementedError

    elif data_type[:3] == ("text", "data", "spyder"):
        raise NotImplementedError

    else:
        return DataObject
