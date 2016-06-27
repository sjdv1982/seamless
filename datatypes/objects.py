from . import parse, serialize
import os

class DataObject:
    def __init__(self, name, datatype, data = None):
        self.name = name
        self.datatype = datatype
        if data is not None:
            self.parse(data)
    def parse(self, data):
        self.data = parse(self.datatype, data, trusted=True)
    def serialize(self):
        return serialize(self.data)
    def validate(self):
        pass

import ast

class PythonCodeObject(DataObject):
    def parse(self, data):
        self.data = data
        self.ast = compile(data, self.name, "exec", ast.PyCF_ONLY_AST)
    def serialize(self):
        return self.data

class PythonExpressionObject(PythonCodeObject):
    def validate(self):
        src = self.data
        self.code = compile(src, self.name, "eval")

class PythonBlockObject(PythonCodeObject):
    def validate(self):
        src = self.data
        self.code = compile(src, self.name, "exec")

class PythonTransformerObject(PythonCodeObject):
    func_name = "transform"
    def validate(self):
        is_function  = (len(self.ast.body) == 1 and \
          isinstance(self.ast.body[0], ast.FunctionDef))
        if is_function:
            self.code = compile(self.ast, self.name, "exec")
            self.func_name = self.ast.body[0].name
        else:
            ok = False
            try:
                compile(self.ast, self.name, "exec")
            except SyntaxError as exc:
                if exc.args[0] == "'return' outside function":
                    ok = True
            if not ok:
                raise SyntaxError("Block must contain return statement(s)")
            patched_src = "def transform(input):\n    " + \
                          self.data.replace("\n", "\n    ").rstrip()
            self.code = compile(patched_src, self.name, "exec")
            self.func_name = "transform"

def datatype_to_dataobject(datatype):
    from . import check_registered
    assert check_registered(datatype)
    if datatype[:2] == ("text", "code"):
        return DataObject #by default, code is just text!
    elif datatype[:3] == ("text", "data", "json"):
        raise NotImplementedError
    elif datatype[:3] == ("text", "data", "xml"):
        raise NotImplementedError
    elif datatype[:3] == ("text", "data", "spyder"):
        raise NotImplementedError
    else:
        return DataObject
