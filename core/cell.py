import traceback
import inspect
import ast

from .. import dtypes
from .utils import find_return_in_scope
from . import manager


class Cell:

    class StatusFlags:
        UNINITIALISED, ERROR, OK = range(3)
    StatusFlagNames = ["UNINITIALISED", "ERROR", "OK"]

    _data_type = None
    _data = None #data, always in text format

    _error_message = None
    _status = StatusFlags.UNINITIALISED

    _name = "cell"
    _dependent = False

    _incoming_connections = 0
    _outgoing_connections = 0

    def __init__(self, data_type):
        assert dtypes.check_registered(data_type)
        self._data_type = data_type

    @property
    def name(self):
        return self._name

    @property
    def dependent(self):
        """Property is true if the cell has a hard incoming connection,
         e.g. the output of a process"""
        return self._dependent

    @name.setter
    def name(self, value):
        self._name = value

    def set(self, text_or_object):
        """This method is used to update cell data from Python code
        in the main thread"""
        #TODO: support for liquid (lset)
        if isinstance(text_or_object, (str, bytes)):
            self._text_set(text_or_object, trusted=False)

        else:
            self._object_set(text_or_object, trusted=False)

    def _text_set(self, data, trusted):
        try:
            """Check if we can parse the text"""
            dtypes.parse(self._data_type, data, trusted=trusted)

        except dtypes.ParseError:
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
             Some datatypes (i.e. silk) can construct the object from
              heterogenous input
            """
            constructed_object = dtypes.construct(self._data_type, object_)

        except dtypes.ConstructionError:
            self._set_error_state(traceback.format_exc())

            if not trusted:
                raise
        else:
            data = dtypes.serialize(self._data_type, object_) #Normally NOT_REQUIRED error here...
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
        return self.StatusFlagNames[self._status]

    @property
    def exception(self):
        return self._exception

    def _on_connect(self, pin, controller, incoming):
        #TODO: support for liquid connections: check pin!
        if incoming:
            if self._dependent:
                raise Exception("Cell is already the output of another controller")
            self._dependent = True
            self._incoming_connections += 1
        else:
            self._outgoing_connections += 1

    def _on_disconnect(self, controller):
        if incoming:
            self._dependent = False
            self._incoming_connections -= 1
        else:
            self._outgoing_connections -= 1

    def _set_error_state(self, error_message=None):
        self._error_message = error_message
        self._status = self.StatusFlags.ERROR


class PythonCell(Cell):
    """
    Python cells may contain either a code block or a function
    Controllers that are connected to it may require either a code block or a
     function
    Mismatch between the two is not a problem, unless:
          Connected controllers have conflicting block/function requirements
        OR
            A function is required (typically, true for transformers)
          AND
            The cell contains a code block
          AND
            The code block contains no return statement
    """

    class CodeTypes:
        ANY, FUNCTION, BLOCK = range(3)

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
                        self._set_error_state("{}: {}".format(
                         exception.__class__.__name__, exception.msg)
                        )
                        return

                    else:
                        raise exception

            self._data = data
            self._code_type = self.CodeTypes.FUNCTION if is_function \
             else self.CodeTypes.BLOCK
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

    def _on_connect(self, pin, controller, incoming):
        if not incoming:
            if self._required_code_type == self.CodeTypes.BLOCK and \
             controller._required_code_type == self.CodeTypes.FUNCTION:
                raise Exception(
                    """Cannot connect to %s: controller_ref requires a code function
                     whereas other connected controllers require a code block""" % \
                      type(controller)
                )
            elif self._required_code_type == self.CodeTypes.FUNCTION and \
             controller._required_code_type == self.CodeTypes.BLOCK:
                raise Exception(
                    """Cannot connect to %s: controller_ref requires a code block
                     whereas other connected controllers require a function""" % \
                      type(controller)
                )

        Cell._on_connect(self, pin, controller, incoming)
        if not incoming:
            self._required_code_type = controller._required_code_type



    def _on_disconnect(self, pin, controller, incoming):
        Cell._on_disconnect(self, pin, controller, incoming)
        if self._outgoing_connections == 0:
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


def pythoncell(text_or_object=None):
    return cell(("text", "code", "python"), text_or_object)
