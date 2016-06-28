import traceback
import inspect
import ast

from .. import datatypes
from ..utils import find_return_in_scope
from . import manager


class Cell:

    class StatusFlags:
        UNINITIALISED, ERROR, OK = range(3)

    _data_type = None
    _data = None #data, always in text format

    _error_message = None
    _status = StatusFlags.UNINITIALISED

    _name = "cell"

    def __init__(self, data_type):
        assert datatypes.check_registered(data_type)
        self._data_type = data_type

    @property
    def name(self):
        return self._name

    @name.setter
    def name(self, value):
        self._name = value

    def set(self, text_or_object):
        """This method is used to update cell data from Python code
        in the main thread"""
        if isinstance(text_or_object, (str, bytes)):
            self._text_set(text_or_object, trusted=False)

        else:
            self._object_set(text_or_object, trusted=False)

    def _text_set(self, data, trusted):
        try:
            """Check if we can parse the text"""
            datatypes.parse(self._data_type, data, trusted=trusted)

        except datatypes.ParseError:
            self._set_error_state(traceback.format_exc())

            if not trusted:
                raise
        else:
            self._data = data
            self._status = self.__class__.StatusFlags.OK

            if not trusted:
                manager.manager.update_from_code(self)

    def _object_set(self, object_, trusted):
        try:
            """
            Construct the object:
             If the object is already of the correct type,
               then constructed_object is object_
             Some datatypes (i.e. Spyder) can construct the object from
              heterogenous input
            """
            constructed_object = datatypes.construct(self._data_type, object_)

        except datatypes.ConstructionError:
            self._set_error_state(traceback.format_exc())

            if not trusted:
                raise
        else:
            data = datatypes.serialize(self._data_type, object_) #Normally NOT_REQUIRED error here...
            self._data = data
            self._status = self.__class__.StatusFlags.OK

            if not trusted:
                manager.manager.update_from_code(self)

    def _update(self, data):
        """This method is invoked when cell data is updated by controllers"""
        self._text_set(data, trusted=True)

    def connect(self, target):
        manager.connect(self, target)

    @property
    def data_type(self):
        return self._data_type

    @property
    def data(self):
        return self._data

    @property
    def status(self):
        return self._status

    @property
    def exception(self):
        return self._exception

    def _on_connect(self, controller):
        pass

    def _on_disconnect(self, controller):
        pass

    def _set_error_state(self, error_message=None):
        self._error_message = error_message
        self._status = self.StatusFlags.ERROR


class PythonCell(Cell):
    """
    Python cells may contain either a code block or a function
    Controllers that are connected to it may require either a code block or a
     function
    Mismatch between the two is not a problem, unless:
          Connected controllers have conflicting requirements
        OR
            A function is required (typically, true for transformers)
          AND
            The cell contains a code block
          AND
            The code block contains NOT_REQUIRED return statement
    """

    class CodeTypes:
        ANY, FUNCTION, BLOCK = range(3)

    _connections = 0
    _data_type = ("text", "python")

    _code_type = CodeTypes.ANY
    _required_code_type = CodeTypes.ANY

    def _text_set(self, data, trusted):
        try:
            """Check if the code is valid Python syntax"""
            ast_tree = compile(data, self._name, "exec", ast.PyCF_ONLY_AST)

        except SyntaxError:
            if not trusted:
                raise

            else:
                self._set_error_state(traceback.format_exc())

        else:
            is_function = (len(ast_tree.body) == 1 and isinstance(ast_tree.body[0], ast.FunctionDef))

            # If this cell requires a function, but wasn't provided with a def block
            if not is_function and self._required_code_type == self.CodeTypes.FUNCTION:
                # Look for return node in AST
                try:
                    return_node = find_return_in_scope(ast_tree)

                except ValueError:
                    exception = SyntaxError("Block must contain return statement(s)")

                    if trusted:
                        self._set_error_state("{}: {}".format(exception.__class__.__name__, exception.msg))
                        return

                    else:
                        raise exception

            self._data = data
            self._code_type = self.CodeTypes.FUNCTION if is_function else self.CodeTypes.BLOCK
            self._status = self.StatusFlags.OK

            if not trusted:
                manager.manager.update_from_code(self)

    def _object_set(self, object_, trusted):
        try:
            """
            Try to retrieve the source code
            Will only work if code is a function
            """
            if not inspect.isfunction(object_):
                raise Exception("Python object must be a function")

            code = inspect.getsource(object_)

        except:
            self._set_error_state(traceback.format_exc())

            if not trusted:
                raise

        else:
            self._code_type = self.CodeTypes.FUNCTION
            self._data = code
            self._status = self.__class__.StatusFlags.OK

            if not trusted:
                manager.manager.update_from_code(self)

    def _on_connect(self, controller):
        if self._code_type == self.CodeTypes.BLOCK and controller._required_code_type == self.CodeTypes.FUNCTION:
            raise Exception(
                """Cannot connect to %s: controller_ref requires a code function
                 whereas other connected controllers require a code block""" % type(controller)
            )
        elif self._code_type == self.CodeTypes.FUNCTION and controller._required_code_type == self.CodeTypes.BLOCK:
            raise Exception(
                """Cannot connect to %s: controller_ref requires a code block
                 whereas other connected controllers require a function""" % type(controller)
            )

        self._required_code_type = controller._required_code_type
        self._connections += 1

    def _on_disconnect(self, controller):
        self._connections -= 1
        if self._connections == 0:
            self._required_code_type = self.CodeTypes.ANY


_handlers = {
    ("text", "code", "python"): PythonCell
}


def cell(data_type, text_or_object=None):
    cell_cls = Cell
    if data_type in _handlers:
        cell_cls = _handlers[data_type]

    newcell = cell_cls(data_type)
    if text_or_object is not None:
        newcell.set(text_or_object)

    return newcell


def python_cell(text_or_object=None):
    return cell(("text", "code", "python"), text_or_object)

