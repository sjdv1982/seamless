"""Module containing the Cell class."""

import traceback
import inspect
import ast

from .. import dtypes
from .utils import find_return_in_scope
from .process import Managed

class Cell(Managed):
    """Default class for cells.

    Cells contain all the state in text form
    """

    class StatusFlags:
        UNINITIALISED, ERROR, OK = range(3)
    StatusFlagNames = ["UNINITIALISED", "ERROR", "OK"]

    _dtype = None
    _data = None  # data, always in text format
    _data_last = None

    _error_message = None
    _status = StatusFlags.UNINITIALISED

    _name = "cell"
    _dependent = False

    _incoming_connections = 0
    _outgoing_connections = 0

    def __init__(self, dtype):
        """TODO: docstring."""
        assert dtypes.check_registered(dtype)
        self._dtype = dtype
        self._last_object = None

    @property
    def name(self):
        """TODO: docstring."""
        return self._name

    @property
    def dependent(self):
        """Indicate if the cell is dependent.

        Property is true if the cell has a hard incoming connection,
        e.g. the output of a process.
        """
        return self._dependent

    @name.setter
    def name(self, value):
        self._name = value

    def set(self, text_or_object):
        """Update cell data from Python code in the main thread."""
        # TODO: support for liquid (lset)
        if isinstance(text_or_object, (str, bytes)):
            self._text_set(text_or_object, trusted=False)
        else:
            self._object_set(text_or_object, trusted=False)
        return self

    def _text_set(self, data, trusted):
        if self._status == self.__class__.StatusFlags.OK \
                and (data == self._data or data == self._data_last):
            return False
        try:
            """Check if we can parse the text"""
            dtypes.parse(self._dtype, data, trusted=trusted)

        except dtypes.ParseError:
            self._set_error_state(traceback.format_exc())

            if not trusted:
                raise
        else:
            self._data_last = data
            self._data = data
            self._status = self.__class__.StatusFlags.OK

            if not trusted and self._context is not None:
                manager = self._get_manager()
                manager.update_from_code(self)
        return True

    def _object_set(self, object_, trusted):
        if self._status == self.__class__.StatusFlags.OK \
                and (object_ == self._last_object or
                     object_ == self._last_object2):
            return False
        print("_object_set", object_)
        try:
            """
            Construct the object:
             If the object is already of the correct type,
               then constructed_object is object_
             Some datatypes (i.e. silk) can construct the object from
              heterogenous input
            """
            dtypes.construct(self._dtype, object_)

        except dtypes.ConstructionError:
            self._set_error_state(traceback.format_exc())

            if not trusted:
                raise
        else:
            data = dtypes.serialize(self._dtype, object_)
            # Normally no error here...
            self._data = data
            self._status = self.__class__.StatusFlags.OK
            self._last_object2 = self._last_object
            self._last_object = object_

            if not trusted and self._context is not None:
                manager = self._get_manager()
                manager.update_from_code(self)
        return True

    def _update(self, data):
        """Invoked when cell data is updated by a process."""
        return self._text_set(data, trusted=True)

    def connect(self, target):
        """Connect the cell to a process's input pin."""
        manager = self._get_manager()
        manager.connect(self, target)

    @property
    def dtype(self):
        """The cell's data type."""
        return self._dtype

    @property
    def data(self):
        """The cell's data in text format."""
        return self._data

    @property
    def status(self):
        """The cell's current status."""
        return self.StatusFlagNames[self._status]

    @property
    def error_message(self):
        """The cell's current error message.

        Returns None is there is no error
        """
        return self._error_message

    def _on_connect(self, pin, process, incoming):
        # TODO: support for liquid connections: check pin!
        if incoming:
            if self._dependent:
                raise Exception(
                 "Cell is already the output of another process"
                )
            self._dependent = True
            self._incoming_connections += 1
        else:
            self._outgoing_connections += 1

    def _on_disconnect(self, pin, process, incoming):
        if incoming:
            self._dependent = False
            self._incoming_connections -= 1
        else:
            self._outgoing_connections -= 1

    def _set_error_state(self, error_message=None):
        self._error_message = error_message
        if error_message is not None:
            self._status = self.StatusFlags.ERROR

class PythonCell(Cell):
    """
    A cell containing Python code.

    Python cells may contain either a code block or a function
    Processes that are connected to it may require either a code block or a
     function
    Mismatch between the two is not a problem, unless:
          Connected processes have conflicting block/function requirements
        OR
            A function is required (typically, true for transformers)
          AND
            The cell contains a code block
          AND
            The code block contains no return statement
    """

    class CodeTypes:
        ANY, FUNCTION, BLOCK = range(3)

    _dtype = ("text", "python")

    _code_type = CodeTypes.ANY
    _required_code_type = CodeTypes.ANY

    def _text_set(self, data, trusted):
        if data == self._data:
            return False
        try:
            """Check if the code is valid Python syntax"""
            ast_tree = compile(data, self._name, "exec", ast.PyCF_ONLY_AST)

        except SyntaxError:
            if not trusted:
                raise

            else:
                self._set_error_state(traceback.format_exc())

        else:
            is_function = (
             len(ast_tree.body) == 1 and
             isinstance(ast_tree.body[0], ast.FunctionDef)
            )

            # If this cell requires a function, but wasn't provided
            #  with a def block
            if not is_function and \
                    self._required_code_type == self.CodeTypes.FUNCTION:
                # Look for return node in AST
                try:
                    find_return_in_scope(ast_tree)
                except ValueError:
                    exception = SyntaxError(
                     "Block must contain return statement(s)"
                    )

                    if trusted:
                        self._set_error_state("{}: {}".format(
                         exception.__class__.__name__, exception.msg)
                        )
                        return

                    else:
                        raise exception

            self._data = data
            self._code_type = self.CodeTypes.FUNCTION if is_function else \
                self.CodeTypes.BLOCK
            self._set_error_state(None)
            self._status = self.StatusFlags.OK

            if not trusted and self._context is not None:
                manager = self._get_manager()
                manager.update_from_code(self)
            return True

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
            oldcode = self._data
            self._data = code
            self._status = self.__class__.StatusFlags.OK

            if not trusted and self._context is not None:
                manager = self._get_manager()
                manager.update_from_code(self)
            return code != oldcode

    def _on_connect(self, pin, process, incoming):
        exc1 = """Cannot connect to %s: process requires a code function
        whereas other connected processes require a code block"""
        exc2 = """Cannot connect to %s: process requires a code block
        whereas other connected processes require a code function"""

        if not incoming:
            if self._required_code_type == self.CodeTypes.BLOCK and \
                    process._required_code_type == self.CodeTypes.FUNCTION:
                raise Exception(exc1 % type(process))
            elif self._required_code_type == self.CodeTypes.FUNCTION and \
                    process._required_code_type == self.CodeTypes.BLOCK:
                raise Exception(exc2 % type(process))

        Cell._on_connect(self, pin, process, incoming)
        if not incoming:
            self._required_code_type = process._required_code_type

    def _on_disconnect(self, pin, process, incoming):
        Cell._on_disconnect(self, pin, process, incoming)
        if self._outgoing_connections == 0:
            self._required_code_type = self.CodeTypes.ANY


_handlers = {
    ("text", "code", "python"): PythonCell
}


def cell(dtype):
    """Factory function for a Cell object."""
    cell_cls = Cell
    if dtype in _handlers:
        cell_cls = _handlers[dtype]

    newcell = cell_cls(dtype)
    return newcell


def pythoncell():
    """Factory function for a PythonCell object."""
    return cell(("text", "code", "python"))

from .context import Context
