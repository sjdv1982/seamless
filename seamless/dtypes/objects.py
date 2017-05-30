from ast import PyCF_ONLY_AST, FunctionDef
from abc import ABCMeta, abstractmethod

from ..core.utils import find_return_in_scope
from . import parse, serialize
from ..core.cached_compile import cached_compile

class DataObject:
    store = None

    def __init__(self, name, data_type, data = None):
        self.name = name
        self.data_type = data_type
        self.data = None

        if data is not None:
            self.parse(data)

    def parse(self, data, resource_name):
        if self.data_type == "signal":
            return
        # TODO: exception message that displays resource_name
        self.data = parse(self.data_type, data, trusted=True)

    def serialize(self):
        if self.data_type == "signal":
            return None
        return serialize(self.data_type, self.data)

    def validate(self):
        pass


class PythonCodeObject(DataObject, metaclass=ABCMeta):
    code = None
    ast = None

    def parse(self, data, resource_name):
        self.data = data
        if resource_name is None:
            resource_name = self.name + "-%d" % id(self)
        self.resource_name = resource_name
        self.ast = cached_compile(data, resource_name,
                                  "exec", PyCF_ONLY_AST)

    def serialize(self):
        return self.data

    @abstractmethod
    def validate(self):
        pass


class PythonExpressionObject(PythonCodeObject):

    def validate(self):
        self.code = cached_compile(self.data, self.resource_name,
                                   "eval")


class PythonBlockObject(PythonCodeObject):

    def validate(self):
        self.code = cached_compile(self.data, self.resource_name,
                                   "exec")


class PythonTransformerCodeObject(PythonCodeObject):
    """Python code object used for transformers (accepts one argument)"""
    func_name = "transform"

    def validate(self):
        self.func_name = type(self).func_name
        is_function = (len(self.ast.body) == 1 and
                       isinstance(self.ast.body[0], FunctionDef))

        if is_function:
            self.code = cached_compile(self.data, self.resource_name,
                                       "exec")
            self.func_name = self.ast.body[0].name

        else:
            try:
                return_node = find_return_in_scope(self.ast)

            except ValueError:
                raise SyntaxError("Block must contain return statement(s)")

            patched_src = "def {0}():\n    ".format(self.func_name) + \
              self.data.replace("\n", "\n    ").rstrip()

            self.code = cached_compile(patched_src,
                                       self.resource_name, "exec")

class PythonReactorCodeObject(PythonTransformerCodeObject):
    func_name = None

    def validate(self):
        self.func_name = None
        self.code = cached_compile(self.data, self.resource_name,
                                   "exec")

        is_function = (len(self.ast.body) == 1 and
                       isinstance(self.ast.body[0], FunctionDef))

        if is_function:
            self.func_name = self.ast.body[0].name

class ArrayDataObject(DataObject):
    def parse(self, data, resource_name):
        from . import TransportedArray
        assert isinstance(data, TransportedArray)
        # TODO: exception message that displays resource_name
        self.data = parse(self.data_type, data.array, trusted=True)
        self.store = data.store

def data_type_to_data_object(data_type):
    #TODO: stub!
    from . import check_registered
    if isinstance(data_type, list):
        data_type = tuple(data_type)
    assert check_registered(data_type), data_type
    if data_type == "array":
        return ArrayDataObject
    return DataObject

    """
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
    """
