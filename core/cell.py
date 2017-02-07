"""Module containing the Cell class."""

import traceback
import inspect
import ast
import os
import copy

from .. import dtypes
from .utils import find_return_in_scope
from .process import Managed
from . import libmanager
from .resource import Resource

class CellLike(object):
    """Base class for cells and contexts
    CellLikes are captured by context.cells"""
    _like_cell = True

class Cell(Managed, CellLike):
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

    _dependent = False

    _incoming_connections = 0
    _outgoing_connections = 0

    _resource = None

    def __init__(self, dtype, *, naming_pattern="cell"):
        """TODO: docstring."""
        super().__init__()
        from .macro import get_macro_mode
        from .context import get_active_context
        assert dtypes.check_registered(dtype), dtype
        self._dtype = dtype
        self._last_object = None
        self._resource = Resource(self)
        if get_macro_mode():
            ctx = get_active_context()
            ctx._add_new_cell(self, naming_pattern)

    @property
    def resource(self):
        return self._resource

    @property
    def dependent(self):
        """Indicate if the cell is dependent.

        Property is true if the cell has a hard incoming connection,
        e.g. the output of a process.
        """
        return self._dependent

    def set(self, text_or_object):
        """Update cell data from Python code in the main thread."""
        if isinstance(text_or_object, (str, bytes)):
            self._text_set(text_or_object, trusted=False)
        else:
            self._object_set(text_or_object, trusted=False)
        return self

    def fromfile(self, filename):
        return self.resource.fromfile(filename, frames_back=2)

    def _text_set(self, data, trusted):
        try:
            if self._status == self.__class__.StatusFlags.OK \
                    and (data is self._data or data is self._data_last or
                         data == self._data or data == self._data_last):
                return False
        except:
            pass

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
                and object_ == self._last_object:
            return False
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
            self._last_object = copy.deepcopy(object_)

            if not trusted and self._context is not None:
                manager = self._get_manager()
                manager.update_from_code(self)
        return True

    def touch(self):
        if self._status != self.__class__.StatusFlags.OK:
            return
        if self._context is not None:
            manager = self._get_manager()
            manager.update_from_code(self)

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
        return copy.deepcopy(self._data)

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
        from .process import OutputPinBase
        if incoming:
            if self._dependent and isinstance(pin, OutputPinBase):
                raise Exception(
                 "Cell is already the output of another process"
                )
            if isinstance(pin, OutputPinBase):
                self._dependent = True
            self._incoming_connections += 1
        else:
            self._outgoing_connections += 1

    def _on_disconnect(self, pin, process, incoming):
        from .process import OutputPinBase
        if incoming:
            if isinstance(pin, OutputPinBase):
                self._dependent = False
            self._incoming_connections -= 1
        else:
            self._outgoing_connections -= 1

    def _set_error_state(self, error_message=None):
        if error_message is not None:
            self._status = self.StatusFlags.ERROR
            if error_message != self._error_message:
                print(error_message)
        self._error_message = error_message

    def add_macro_object(self, macro_object, macro_arg):
        manager = self._get_manager()
        manager.add_macro_listener(self, macro_object, macro_arg)

    def remove_macro_object(self, macro_object, macro_arg):
        manager = self._get_manager()
        manager.remove_macro_listener(self, macro_object, macro_arg)

    def destroy(self):
        if self._destroyed:
            return
        #print("CELL DESTROY", self)
        self.resource.destroy()
        super().destroy()

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
            ast_tree = compile(data, str(self), "exec", ast.PyCF_ONLY_AST)

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
        from .utils import strip_source
        try:
            """
            Try to retrieve the source code
            Will only work if code is a function
            """
            if not inspect.isfunction(object_):
                raise Exception("Python object must be a function")

            code = inspect.getsource(object_)
            code = strip_source(code)

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
