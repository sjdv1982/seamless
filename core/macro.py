from collections import OrderedDict
import functools
import copy
import weakref
from .context import context, get_active_context
from contextlib import contextmanager as _pystdlib_contextmanager

#TODO: implement lib system, and let pins connect to CellProxies instead of
# cells. CellProxies work exactly the same as cells
# (pass-through attribute access), except that they can be forked
#TODO: get the source of the macro, store this in a cell, and make sure that
# 1. it gets properly captured by the lib system
# 2. if the source of the macro is different from the lib cell content,
# fork any cellproxies linking to the old lib cell, then update the lib cell,
# and issue a warning

_macro_mode = False
_macro_registrar = []

def get_macro_mode():
    return _macro_mode

def set_macro_mode(macro_mode):
    global _macro_mode
    _macro_mode = macro_mode

@_pystdlib_contextmanager
def macro_mode_as(macro_mode):
    global _macro_mode
    old_macro_mode = _macro_mode
    _macro_mode = macro_mode
    yield
    _macro_mode = old_macro_mode


class MacroObject:
    macro = None
    args = []
    kwargs = {}
    cell_args = {}
    _parent = None

    def __init__(self, macro, args, kwargs, cell_args):
        self.macro = macro
        self.args = args
        self.kwargs = kwargs
        self.cell_args = cell_args

    def connect(self, parent):
        from .cell import CellLike
        from .process import ProcessLike
        from .registrar import RegistrarObject
        assert (isinstance(parent, CellLike) and parent._like_cell) or \
         (isinstance(parent, ProcessLike) and parent._like_process) or \
         isinstance(parent, RegistrarObject), type(parent)
        #TODO: check that all cells and parent share a common root
        self._parent = weakref.ref(parent)
        for k in self.cell_args:
            cell = self.cell_args[k]
            cell.add_macro_object(self, k)

    def update_cell(self, cellname):
        from .context import Context
        from .cell import Cell
        from .process import Process, InputPinBase, OutputPinBase
        parent = self._parent()
        grandparent = parent.context
        assert isinstance(grandparent, Context), grandparent
        for parent_childname in grandparent._children:
            if grandparent._children[parent_childname] is parent:
                break
        else:
            exc = "Cannot identify parent-child relationship of macro context {0}"
            raise AttributeError(exc.format(parent))
        external_connections = []

        def find_external_connections_cell(cell, path, parent_path, parent_owns):
            owns = parent_owns
            if owns is None:
                owns = cell._owns_all()
            manager = cell._get_manager()
            cell_id = manager.get_cell_id(cell)
             #no macro listeners or registrar listeners; these the macro should re-create
            incons = manager.cell_to_output_pin.get(cell, [])
            for incon in incons:
                output_pin = incon()
                if output_pin is None:
                    continue
                process = output_pin.process_ref()
                if process is None or process in owns:
                    continue
                if parent_path is not None:
                    if output_pin.path[:len(parent_path)] == parent_path:
                        continue
                external_connections.append((True, output_pin, path, output_pin.path))
            outcons = manager.listeners[cell_id]
            for outcon in outcons:
                input_pin = outcon()
                if input_pin is None:
                    continue
                process = input_pin.process_ref()
                if process is None or process in owns:
                    continue
                if parent_path is not None:
                    if input_pin.path[:len(parent_path)] == parent_path:
                        continue
                assert len(input_pin.path)
                external_connections.append((False, path, input_pin, input_pin.path))

        def find_external_connections_process(process, path, parent_path, parent_owns):
            if path is None:
                path = ()
            owns = parent_owns
            if owns is None:
                owns = process._owns_all()
            for pinname, pin in process._pins.items():
                manager = pin._get_manager()
                pin_id = pin.get_pin_id()
                if isinstance(pin, InputPinBase):
                    is_incoming = True
                    cell_ids = manager.pin_to_cells.get(pin_id, [])
                elif isinstance(pin, OutputPinBase):
                    is_incoming = False
                    cell_ids = pin._cell_ids
                else:
                    raise TypeError((pinname, pin))
                for cell_id in cell_ids:
                    cell = manager.cells.get(cell_id, None)
                    if cell is None:
                        continue
                    if cell in owns:
                        continue
                    if parent_path is not None:
                        if cell.path[:len(parent_path)] == parent_path:
                            continue
                    path2 = path + (pinname,)
                    if is_incoming:
                        external_connections.append((True, cell, path2, cell.path))
                    else:
                        external_connections.append((False, path2, cell, cell.path))

        def find_external_connections_context(ctx, path, parent_path, parent_owns):
            parent_path2 = parent_path
            if parent_path is None:
                parent_path2 = ctx.path
            owns = parent_owns
            if owns is None:
                owns = ctx._owns_all()
            for childname, child in ctx._children.items():
                if path is not None:
                    path2 = path + (childname,)
                else:
                    path2 = (childname,)
                if isinstance(child, Cell):
                    find_external_connections_cell(child, path2, parent_path2, owns)
                elif isinstance(child, Process):
                    find_external_connections_process(child, path2, parent_path2, owns)
                elif isinstance(child, Context):
                    find_external_connections_context(child, path2, parent_path2, owns)
                else:
                    raise TypeError((childname, child))

        if isinstance(parent, Cell):
            find_external_connections_cell(parent, None, None, None)
        elif isinstance(parent, Process):
            find_external_connections_process(parent, None, None, None)
        elif isinstance(parent, Context):
            find_external_connections_context(parent, None, None, None)
        elif parent is None:
            pass

        new_parent = self.macro.evaluate(self.args, self.kwargs, self)
        setattr(grandparent, parent_childname, new_parent) #destroys parent and connections
        self._parent = weakref.ref(new_parent)

        def resolve_path(target, path, index):
            if path is not None and len(path) > index:
                try:
                    new_target = getattr(target, path[index])
                except AttributeError:
                    warn = "WARNING: cannot reconstruct connections for '{0}', target no longer exists"
                    subpath = "." + ".".join(target.path + path[:index+1])
                    print(warn.format(subpath))
                    return None
                return resolve_path(new_target, path, index+1)
            return target
        for is_incoming, source, dest, ext_path in external_connections:
            print("CONNECTION: is_incoming {0}, source {1}, dest {2}".format(is_incoming, source, dest))
            err = "Connection {0}::(is_incoming {1}, source {2}, dest {3}) points to a destroyed external cell"
            if is_incoming:
                if source._destroyed:
                    print("ERROR:", err.format(new_parent.path, is_incoming, ext_path, dest) + " (source)")
                dest_target = resolve_path(new_parent, dest, 0)
                if dest_target is not None:
                    source.connect(dest_target)
            else:
                if dest._destroyed:
                    print("ERROR:", err.format(new_parent.path, is_incoming, source, ext_path) + " (dest)")
                    continue
                source_target = resolve_path(new_parent, source, 0)
                if source_target is not None:
                    source_target.connect(dest)

    def set_registrar_listeners(self, registrar_listeners):
        for registrar, manager, key in registrar_listeners:
            manager.add_registrar_listener(registrar, key, self, None)

    def __del__(self):
        if self._parent is None:
            return
        for k in self.cell_args:
            cell = self.cell_args[k]
            cell.remove_macro_object(self, k)


class Macro:

    def __init__(self, type=None, with_context=True, func=None):
        self.with_context = with_context
        self._type_args = None
        self.func = func

        if type is None:
            return

        if isinstance(type, tuple) or isinstance(type, str):
            self._type_args = {'_order': ["_arg1"], '_required': ["_arg1"], '_default': {}, '_arg1': type}
            return

        if not isinstance(type, dict):
            raise TypeError(type.__class__)

        self._type_args = self._get_type_args_from_dict(type)

    @staticmethod
    def _get_type_args_from_dict(type):
        order = []
        if "_order" in type:
            order = type["_order"]
            assert sorted(order) == sorted([k for k in type.keys() if not k.startswith("_")])
        required = set()
        default = {}
        type_args = {'_order': order, '_required': required, '_default': default}
        last_non_required_name = None

        for name, value in type.items():
            if name.startswith("_"):
                if name == "_order":
                    continue
                assert name.startswith("_arg"), k

            is_required = True
            if isinstance(value, dict) and (value.get("optional", False) or "default" in value):
                is_required = False

            if isinstance(type, OrderedDict):
                order.append(name)
                if is_required and last_non_required_name:
                    message = "Cannot specify required argument '{0}' after non-required argument '{1}'"
                    raise Exception(message.format(name, last_non_required_name))

            value_type = value
            if isinstance(value, dict):
                value_type = value["type"]
                if "default" in value:
                    #TODO: checking regarding type <=> default
                    #TODO: check that the default can be serialised, or at least pickled
                    default[name] = value["default"]
            type_args[name] = value_type

            if is_required:
                required.add(name)

            else:
                last_non_required_name = name

        return copy.deepcopy(type_args)

    def resolve(self, obj):
        #TODO: allow CellLike contexts as well (also in cell_args in resolve_type_args)
        from .cell import Cell
        from ..dtypes import parse

        if isinstance(obj, Cell):
            return parse(obj.dtype, obj._data, trusted=True)

        else:
            return obj

    def resolve_type_args(self, args, kwargs):
        """
        #TODO: When macro object is created and attached to context X, verify that all resolved
         cells and X have a common ancestor (._root)
        """
        from .cell import Cell

        macro_object = None
        resolved_args = [self.resolve(a) for a in args]
        resolved_kwargs = {k: self.resolve(v) for k, v in kwargs.items()}

        order = self._type_args["_order"]
        assert len(resolved_args) <= len(order)

        if self._type_args is None:
            return resolved_args, resolved_kwargs, None

        #TODO: take and adapt corresponding routine from Hive
        cell_args = {}
        new_args, new_kwargs = [], {}
        positional_done = set()

        for name, arg, arg0 in zip(order, resolved_args, args):
            #TODO: type validation
            if name.startswith("_arg"):
                new_args.append(arg)
                positional_done.add(name)
            else:
                new_kwargs[name] = arg

            if isinstance(arg0, Cell):
                cell_args[name] = arg0

        new_kwargs.update(resolved_kwargs)

        for name, arg in resolved_kwargs.items():
            assert not name.startswith("_"), name  # not supported
            assert name in self._type_args, (name, [v for v in self._type_args.keys() if not v.startswith("_")])
            #TODO: type validation
            arg0 = kwargs[name]

            if isinstance(arg0, Cell):
                cell_args[name] = arg0

        default = self._type_args["_default"]
        required = self._type_args["_required"]

        for name in required:
            if name.startswith("_arg"):
                assert name in positional_done, name  #TODO: error message
            else:
                assert name in new_kwargs, name  # TODO: error message

        for name in self._type_args:
            if name.startswith("_"):
                continue
            if name in new_kwargs and new_kwargs[name] is not None:
                continue

            arg_default = default.get(name, None)
            new_kwargs[name] = arg_default

        if cell_args:
            macro_object = MacroObject(self, args, kwargs, cell_args)
        return new_args, new_kwargs, macro_object

    def evaluate(self, args, kwargs, macro_object):
        from .cell import Cell, CellLike
        from .process import Process, ProcessLike, InputPinBase, OutputPinBase
        from .registrar import RegistrarObject
        from .context import active_context_as
        from .. import run_work

        resolved_args, resolved_kwargs, mobj = self.resolve_type_args(args, kwargs)
        func = self.func
        if macro_object is not None:
            mobj = macro_object
            parent = macro_object._parent()
            if isinstance(parent, RegistrarObject):
                func = parent.re_register
                resolved_args = resolved_args[1:]  #TODO: bound object because of hack...

        if self.with_context:
            ctx = get_active_context()._new_subcontext()
            result = None
            with active_context_as(ctx), macro_mode_as(True):
                try:
                    ret = func(ctx, *args2, **kwargs2)
                    if ret is not None:
                        raise TypeError("Context macro must return None")
                    if _macro_registrar:
                        if mobj is None:
                            mobj = MacroObject(self, args, kwargs, {})
                        mobj.set_registrar_listeners(_macro_registrar)
                    ctx._set_macro_object(mobj)

                    if macro_object is None: #this is a new construction, not a re-evaluation
                        if mobj is not None:
                            mobj.connect(ctx)
                    result = ctx
                finally:
                    _macro_registrar.clear()
                    if result is None:
                        ctx.destroy()
        else:
            with macro_mode_as(True):
                result = func(*resolved_args, **resolved_kwargs)
                assert (isinstance(result, CellLike) and result._like_cell) \
                       or (isinstance(result, ProcessLike) and result._like_process) \
                       or isinstance(result, RegistrarObject), (func, type(result))

                if isinstance(result, Cell):
                    manager = result._get_manager()
                    cell_id = manager.get_cell_id(result)

                    in_pins = manager.cells[cell_id]
                    for in_pin in in_pins:
                        process = in_pin.process_ref()
                        result.own(process)

                    out_pins = manager.listeners[result]
                    for out_pin in out_pins:
                        process = out_pin.process_ref()
                        result.own(process)

                elif isinstance(result, Process):
                    for pinname, pin in result._pins.items():
                        manager = pin._get_manager()
                        pin_id = pin.get_pin_id()

                        if isinstance(pin, InputPinBase):
                            is_incoming = True
                            cell_ids = manager.pin_to_cells.get(pin_id, [])

                        elif isinstance(pin, OutputPinBase):
                            is_incoming = False
                            cell_ids = pin._cell_ids

                        else:
                            raise TypeError((pinname, pin))

                        for cell_id in cell_ids: #TODO: indirect ownage
                            cell = manager.cells.get(cell_id, None)
                            if cell is None:
                                continue
                            result.own(cell)
                elif isinstance(result, RegistrarObject):
                    pass
                else:
                    raise NotImplementedError(type(result))

                result._set_macro_object(mobj)
                if macro_object is None: #this is a new construction, not a re-evaluation
                    if mobj is not None:
                        mobj.connect(result)

        if not get_macro_mode():
            run_work()
        return result

    def __call__(self, *args, **kwargs):
        return self.evaluate(args, kwargs, None)


def macro(*args, **kwargs):
    """
    Macro decorator

    type: a single type tuple, or a dict/OrderedDict
      if type is a dict, then
        every key is a parameter name
        every value is either a type tuple, or
         a dict, where:
            "type" is the type tuple,
            "optional" (optional) is a boolean
            "default" (optional) is a default value
        the type dict is parsed from **kwargs (keyword arguments)
        unspecified optional arguments default to None, unless "default" is
         specified
      if type is an OrderedDict, then
       as above, but
       the type dict is parsed from *args (positional arguments)
        and **kwargs (keyword arguments)

    As an additional value for type tuple, "self" is allowed. This indicates
     that the macro is a method decorator, and the first argument
     is a bound object. In this case, the macro source is never stored

    with_context: bool
      if True, the function is passed a context object as additional
       first parameter, and is expected to return None
      if False, the function is expected to return a cell or process.
       This cell or process (together with any other cells or processes
       created by the macro) is automatically added to the active context.

    Example 1:
    @macro
    defines a macro with with_context = True, no type checking

    Example 2:
    @macro("str")
    defines a macro with a single argument, which must be of type "str",
     and with_context is True.

    Example 2:
    @macro({
      "spam": { "type":"str", "optional":True },
      "ham": ("code", "python"),
      "eggs": "int"
    })
    defines a macro with a three arguments. The arguments must be defined as
     keyword arguments, and "spam" is optional
    """
    if len(args) == 1 and not kwargs:
        arg, = args
        if callable(arg):
            return Macro(func=arg)
            # TODO: functools.wraps/update_wrapper on new_macro

    new_macro = Macro(*args, **kwargs)

    def func_macro_wrapper(func):
        new_macro.func = func
        # TODO: functools.wraps/update_wrapper on new_macro
        return new_macro

    return func_macro_wrapper
