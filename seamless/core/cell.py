"""Module containing the Cell class."""

import traceback
import inspect
import ast
import os
import copy
import json
import weakref
from enum import Enum

from . import IpyString
from .. import dtypes
from .utils import find_return_in_scope
from . import Managed
from .resource import Resource

class CellLike(object):
    """Base class for cells and contexts
    CellLikes are captured by context.cells"""
    _like_cell = True

class Cell(Managed, CellLike):
    """Default class for cells.

Cells contain all the state in text form

Cells can be connected to inputpins, editpins, and other cells.
``cell.connect(pin)`` connects a cell to an inputpin or editpin

Output pins and edit pins can be connected to cells.
``pin.connect(cell)`` connects an outputpin or editpin to a cell

Use ``Cell.set()`` to set a cell's value.

Use ``Cell.value`` to get its value.

Use ``Cell.status()`` to get its status.
"""

    _dtype = None
    _data = None  # data, always in text format
    _data_last = None

    _error_message = None

    _dependent = False

    _incoming_connections = 0
    _outgoing_connections = 0

    _resource = None
    _preliminary = False

    def __init__(self, dtype, *, naming_pattern="cell"):
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

    def __str__(self):
        ret = "Seamless cell: " + self.format_path()
        return ret

    def _check_destroyed(self):
        if self._destroyed:
            raise AttributeError("Cell has been destroyed")

    @property
    def resource(self):
        self._check_destroyed()
        return self._resource

    @property
    def dependent(self):
        """Indicate if the cell is dependent.

        Property is true if the cell has a hard incoming connection,
        e.g. the output of a worker.
        """
        self._check_destroyed()
        return self._dependent

    def _set(self, text_or_object,propagate,*,preliminary=False):
        """Generic method to update cell; returns True if cell was changed"""
        self._check_destroyed()
        if isinstance(text_or_object, (str, bytes)):
            result = self._text_set(text_or_object,
                propagate=propagate,trusted=False, preliminary=preliminary)
        else:
            result = self._object_set(text_or_object,
                propagate=propagate,trusted=False, preliminary=preliminary)
        self.resource.dirty = False
        self.resource._hash = None
        return result

    def set(self, text_or_object):
        """Update cell data from Python code in the main thread."""
        self._set(text_or_object, propagate=True, preliminary=False)
        if text_or_object is None:
            self.resource.cache = None
        else:
            self.resource.cache = False
        import seamless
        seamless.run_work()
        return self

    def fromfile(self, filename):
        """Sets a file from filename.
        Also sets the filename as a resource:
          When the context is saved and re-loaded, the cell is again loaded
          from file"""
        self._check_destroyed()
        return self.resource.fromfile(filename, frames_back=2)

    def fromlibfile(self, lib, filename):
        """TODO: document"""
        self._check_destroyed()
        return self.resource.fromlibfile(lib, filename)

    def _text_set(self, data, *, propagate, trusted, preliminary):
        try:
            if self._status == self.__class__.StatusFlags.OK \
                    and (data is self._data or data is self._data_last or
                         data == self._data or data == self._data_last):
                return False
        except Exception:
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
            self._preliminary = preliminary
            self._status = self.__class__.StatusFlags.OK

            if not trusted and self._context is not None:
                if propagate:
                    manager = self._get_manager()
                    manager.update_from_code(self)
        return True

    def _object_set(self, object_, *, propagate, trusted, preliminary):
        if self._status == self.__class__.StatusFlags.OK:
            try:
                if object_ == self._last_object:
                    return False
            except ValueError:
                pass
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
            self._preliminary = preliminary
            self._status = self.__class__.StatusFlags.OK
            self._last_object = copy.deepcopy(object_)

            if not trusted and self._context is not None:
                if propagate:
                    manager = self._get_manager()
                    manager.update_from_code(self)
        return True

    def touch(self):
        """Forces a cell update, even though the value stays the same
        This triggers all workers that are connected to the cell"""
        self._check_destroyed()
        if self._status != self.__class__.StatusFlags.OK:
            return
        if self._context is not None:
            manager = self._get_manager()
            manager.update_from_code(self)

    def _update(self, data, *, propagate=False, preliminary=False):
        """Invoked when cell data is updated by a worker or an alias."""
        #result = self._text_set(data, propagate=False, trusted=True, preliminary=False)
        result = self._set(data, propagate=propagate,preliminary=preliminary) #for now, workers can also set with non-text...
        if data is None:
            self.resource.cache = None
        elif self.dependent:
            self.resource.cache = True
        return result

    def disconnect(self, target):
        """Break ane existing connection between the cell and a worker's input pin."""
        self._check_destroyed()
        manager = self._get_manager()
        manager.disconnect(self, target)

    def connect(self, target):
        """Connect the cell to a worker's input pin."""
        self._check_destroyed()
        manager = self._get_manager()
        manager.connect(self, target)

    @property
    def dtype(self):
        """The cell's data type."""
        return self._dtype

    @property
    def data(self):
        """The cell's data in text format."""
        self._check_destroyed()
        return copy.deepcopy(self._data)

    @property
    def value(self):
        """The cell's data as Python object"""
        if self._data is None:
            return None
        return dtypes.parse(self._dtype, self._data, trusted=True)

    def status(self):
        """The cell's current status."""
        self._check_destroyed()
        return self._status.name

    @property
    def error(self):
        """The cell's current error message.

        Returns None is there is no error
        """
        self._check_destroyed()
        err = self._error_message
        if err is None:
            return None
        return IpyString(err)

    def cell(self):
        return self

    def _on_connect(self, pin, worker, incoming):
        from .worker import OutputPinBase
        if incoming:
            if self._dependent and isinstance(pin, (OutputPinBase, Cell)) \
              and not isinstance(self, Signal):
                raise Exception(
                 "Cell is already the output of another worker"
                )
            if isinstance(pin, (OutputPinBase, Cell)):
                self._dependent = True
            self._incoming_connections += 1
        else:
            self._outgoing_connections += 1

    def _on_disconnect(self, pin, worker, incoming):
        from .worker import OutputPinBase
        if incoming:
            if isinstance(pin, (OutputPinBase, Cell)):
                self._dependent = False
                if not self._destroyed and self.resource is not None:
                    self.resource.cache = False
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
        self._check_destroyed()
        manager = self._get_manager()
        manager.add_macro_listener(self, macro_object, macro_arg)

    def remove_macro_object(self, macro_object, macro_arg):
        manager = self._get_manager()
        manager.remove_macro_listener(self, macro_object, macro_arg)

    def _unregister_listeners(self):
        if self._context is None:
            return
        manager = self._get_manager()
        manager.remove_aliases(self)
        manager.remove_listeners_cell(self)
        manager.remove_macro_listeners_cell(self)
        manager.remove_observers_cell(self)

    def destroy(self):
        """Removes the cell from its parent context"""
        if self._destroyed:
            return
        #print("CELL DESTROY", self)
        self.resource.destroy()
        self._unregister_listeners()
        super().destroy()


class PythonCell(Cell):
    """A cell containing Python code.

    Python cells have dtype ("text", "code", "python")
    Python cells may contain either a code block or a function.
    In both cases, the cell contains text, not a Python code object!

    Workers that are connected to it may require either a code block or a
     function.
    Mismatch between the two is not a problem, unless:
          Connected workers have conflicting block/function requirements
        OR
            A function is required (typically, true for transformers)
          AND
            The cell contains a code block
          AND
            The code block contains no return statement
    """

    CodeTypes = Enum('CodeTypes', ('ANY', 'FUNCTION', 'BLOCK'))
    _dtype = ("text", "code", "python")

    _code_type = CodeTypes.ANY
    _required_code_type = CodeTypes.ANY

    def _text_set(self, data, *, propagate, trusted, preliminary):
        if data == self._data:
            return False
        try:
            """Check if the code is valid Python syntax"""
            ast_tree = compile(data, self.format_path(), "exec", ast.PyCF_ONLY_AST)

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
            self._preliminary = preliminary
            self._status = self.StatusFlags.OK

            if not trusted and self._context is not None:
                if propagate:
                    manager = self._get_manager()
                    manager.update_from_code(self)
            return True

    def _object_set(self, object_, *, propagate, trusted, preliminary):
        from .utils import strip_source
        try:
            """
            Try to retrieve the source code
            Will only work if object_ is a function object
            """
            if not inspect.isfunction(object_):
                raise Exception("Python object must be a function")

            code = inspect.getsource(object_)
            code = strip_source(code)

        except Exception:
            self._set_error_state(traceback.format_exc())

            if not trusted:
                raise

        else:
            self._code_type = self.CodeTypes.FUNCTION
            oldcode = self._data
            self._data = code
            self._preliminary = preliminary
            self._status = self.__class__.StatusFlags.OK

            if not trusted and self._context is not None:
                if propagate:
                    manager = self._get_manager()
                    manager.update_from_code(self)
            return code != oldcode

    def _on_connect(self, pin, worker, incoming):
        exc1 = """Cannot connect to %s: worker requires a code function
        whereas other connected workers require a code block"""
        exc2 = """Cannot connect to %s: worker requires a code block
        whereas other connected worker require a code function"""

        if not incoming:
            if self._required_code_type == self.CodeTypes.BLOCK and \
                    worker._required_code_type == self.CodeTypes.FUNCTION:
                raise Exception(exc1 % type(worker))
            elif self._required_code_type == self.CodeTypes.FUNCTION and \
                    worker._required_code_type == self.CodeTypes.BLOCK:
                raise Exception(exc2 % type(worker))

        Cell._on_connect(self, pin, worker, incoming)
        if not incoming:
            self._required_code_type = worker._required_code_type

    def _on_disconnect(self, pin, worker, incoming):
        Cell._on_disconnect(self, pin, worker, incoming)
        if self._outgoing_connections == 0:
            self._required_code_type = self.CodeTypes.ANY


class Signal(Cell):
    """ A cell that does not contain any data
    When a signal is set, it is propagated as fast as possible:
      - If set from the main thread: immediately. Downstream workers are
         notified and activated (if synchronous) before set() returns
      - If set from another thread: as soon as run_work is called. Then,
         Downstream workers are notified and activated before any other
         non-signal notification.
    """
    def __init__(self, dtype, *, naming_pattern="signal"):
        assert dtype == "signal"
        Managed.__init__(self)

        from .macro import get_macro_mode
        from .context import get_active_context

        if get_macro_mode():
            ctx = get_active_context()
            ctx._add_new_cell(self, naming_pattern)

    def set(self):
        self._status = self.__class__.StatusFlags.OK
        self.touch()
        import seamless
        seamless.run_work()

    def fromfile(self, filename):
        raise AttributeError("fromfile")

    def _text_set(self, data, *, propagate, trusted, preliminary):
        raise AttributeError

    def _object_set(self, object_, *, propagate, trusted, preliminary):
        raise AttributeError

    def _update(self, data, *, propagate=False, preliminary=False):
        raise AttributeError

    @property
    def dtype(self):
        return None

    @property
    def data(self):
        return None

    @property
    def value(self):
        return None

    def status(self):
        return self.StatusFlags.OK.name

    def add_macro_object(self, macro_object, macro_arg):
        """Private; raises an error"""
        raise AttributeError

    def remove_macro_object(self, macro_object, macro_arg):
        """Private; raises an error"""
        raise AttributeError

    def destroy(self):
        """Removes the cell from its parent context"""
        if self._destroyed:
            return
        #print("CELL DESTROY", self)
        self._unregister_listeners()
        Managed.destroy(self)

class CsonCell(Cell):
    """A cell in CoffeeScript Object Notation (CSON) format
    When necessary, the contents of a CSON cell are automatically converted
    to JSON.
    """
    @property
    def value(self):
        """
        Converts the data to JSON and returns the dictionary
        """
        data = self._data
        from ..dtypes.cson import cson2json
        return cson2json(data)
    def _update(self, data, *, propagate=False, preliminary=False):
        """Invoked when cell data is updated by a worker."""
        if not isinstance(data, (str, bytes)):
            data = json.dumps(data, indent=2)
        return super()._update(data, propagate=propagate, preliminary=preliminary)

class ArrayCell(Cell):
    """A cell that contains a NumPy array"""
    _store = None
    def set_store(self, mode, *args, **kwargs):
        """
        Specify a store to be bound to the data, i.e. to hold an additional
         copy of the data in a different form
        Calling the store's bind() method will (re-)bind the data if it has
         changed, else it is a no-op
        mode:
            "GL": stores the data as an OpenGL buffer
            "GLTex": stores the data as an OpenGL texture
        """
        assert mode in ("GL", "GLTex"), mode
        from ..dtypes.gl import GLStore, GLTexStore
        if self._store is not None:
            if mode == "GL": assert isinstance(self._store, GLStore)
            if mode == "GLTex": assert isinstance(self._store, GLTexStore)
            return
        if mode == "GL":
            self._store = GLStore(self, *args, **kwargs)
        elif mode == "GLTex":
            self._store = GLTexStore(self, *args, **kwargs)
        self._store.set_dirty()
        self._store_mode = mode
        self.touch()
        return self
    def _set(self, text_or_object,*,propagate,preliminary):
        result = super()._set(text_or_object,
          propagate=propagate,preliminary=preliminary)
        if result and self._store is not None:
            self._store.set_dirty()
        return result
    def destroy(self):
        if self._destroyed:
            return
        if self._store is not None:
            # TODO: leads to segfault because there is no OpenGL context
            #  but omitting it is a GPU memory leak...
            #self._store.destroy()
            pass ###
        super().destroy()

_handlers = {
    ("text", "code", "python"): PythonCell,
    "signal": Signal,
    "cson": CsonCell,
    "array": ArrayCell
}


def cell(dtype):
    """Creates and returns a Cell object.

{0}

Parameters
----------

dtype: string or tuple of strings
    specifies the data type of the cell.
    As of seamless 0.1, the following data types are understood:

    -   "int", "float", "bool", "str", "json", "cson", "array", "signal"
    -   "text", ("text", "code", "python"), ("text", "code", "ipython")
    -   ("text", "code", "silk"), ("text", "code", "slash-0")
    -   ("text", "code", "vertexshader"), ("text", "code", "fragmentshader"),
    -   ("text", "html"),
    -   ("json", "seamless", "transformer_params"),
        ("cson", "seamless", "transformer_params"),
    -   ("json", "seamless", "reactor_params"),
        ("cson", "seamless", "reactor_params")
"""
    cell_cls = Cell
    if isinstance(dtype, type):
        dtype = dtype.__name__
    if dtype in _handlers:
        cell_cls = _handlers[dtype]

    newcell = cell_cls(dtype)
    return newcell
cell.__doc__ = cell.__doc__.format(Cell.__doc__)

def pythoncell():
    """Factory function for a PythonCell object."""
    return cell(("text", "code", "python"))
pythoncell.__doc__ += "\n\nPythonCell:" + PythonCell.__doc__

def arraycell():
    """Factory function for a ArrayCell object."""
    return cell("array")
arraycell.__doc__ += "\n\nArrayCell:" + ArrayCell.__doc__

def csoncell():
    """Factory function for a CsonCell object."""
    return cell("cson")
csoncell.__doc__ += "\n\nCsonCell:" + CsonCell.__doc__

def signal():
    """Factory function for a Signal object."""
    return cell("signal")
signal.__doc__ += "\n\nSignal:" + Signal.__doc__
