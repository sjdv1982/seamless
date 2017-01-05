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

def get_macro_mode():
    return _macro_mode

def set_macro_mode(macro_mode):
    global _macro_mode
    _macro_mode = macro_mode

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
                    if is_incoming:
                        external_connections.append((True, cell, (pinname,), cell.path))
                    else:
                        external_connections.append((False, (pinname,), cell, cell.path))

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
            #print("CONNECTION: is_incoming {0}, source {1}, dest {2}".format(is_incoming, source, dest))
            err = "Connection {0}::(is_incoming {1}, source {2}, dest {3}) points to a destroyed external cell"
            if is_incoming:
                if source._destroyed:
                    print("ERROR:", err.format(new_parent.path, is_incoming, ext_path, dest) + " (source)")
                dest_target = resolve_path(new_parent, dest, 0)
                if dest_target is not None:
                    source.connect(dest_target)
            else:
                if dest._destroyed:
                    print(dest.path)
                    print("ERROR:", err.format(new_parent.path, is_incoming, source, ext_path) + " (dest)")
                    continue
                source_target = resolve_path(new_parent, source, 0)
                if source_target is not None:
                    source_target.connect(dest)

    def __del__(self):
        if self._parent is None:
            return
        for k in self.cell_args:
            cell = self.cell_args[k]
            cell.remove_macro_object(self, k)

class Macro:
    def __init__(self, type=None, with_context=True, func=None):
        self.with_context = with_context
        self.type_args = None
        if type is None:
            return
        if isinstance(type, tuple) or isinstance(type, str):
            self.type_args = dict(
             _order=["_arg1"],
             _required=["_arg1"],
             _default={},
             _arg1=type,
            )
            return

        if not isinstance(type, dict):
            raise TypeError(type.__class__)
        order = []
        required = set()
        default = {}
        ret = dict(_order=order, _required=required, _default=default)
        last_nonreq = None
        for k in type:
            if k.startswith("_"): assert k.startswith("_arg"), k
            v = type[k]
            is_req = True
            if isinstance(v, dict) and \
             (v.get("optional", False) or "default" in v):
                is_req = False
            if isinstance(type, OrderedDict):
                order.append(k)
                if is_req and last_nonreq:
                    exc = "Cannot specify required argument '{0}' after non-required argument '{1}'"
                    raise Exception(exc.format(k, last_nonreq))

            vtype = v
            if isinstance(v, dict):
                vtype = v["type"]
                if "default" in v:
                    #TODO: checking regarding type <=> default
                    #TODO: check that the default can be serialised, or at least pickled
                    default[k] = v["default"]
            ret[k] = vtype

            if is_req:
                required.add(k)
            else:
                last_nonreq = k
        ret = copy.deepcopy(ret)
        self.type_args = ret

    def resolve(self, a):
        #TODO: allow CellLike contexts as well (also in cell_args in resolve_type_args)
        from .cell import Cell
        from ..dtypes import parse
        if isinstance(a, Cell):
            return parse(a.dtype, a._data, trusted=True)
        else:
            return a

    def resolve_type_args(self, args0, kwargs0):
        """
        #TODO: When macro object is created and attached to context X, verify that all resolved
         cells and X have a common ancestor (._root)
        """
        from .cell import Cell

        macro_object = None
        args = [self.resolve(a) for a in args0]
        kwargs = {k: self.resolve(v) for k, v in kwargs0.items()}
        if self.type_args is None:
            return args, kwargs, None

        #TODO: take and adapt corresponding routine from Hive
        cell_args = {}
        args2, kwargs2 = [], {}
        order = self.type_args["_order"]
        assert len(args) <= len(order)
        positional_done = set()
        for anr in range(len(args)):
            argname = order[anr]
            arg = args[anr]
            arg0 = args0[anr]
            #TODO: type validation
            if argname.startswith("_arg"):
                args2.append(arg)
                positional_done.add(argname)
            else:
                kwargs2[argname] = arg
            if isinstance(arg0, Cell):
                cell_args[argname] = arg0
        for argname in kwargs:
            assert not argname.startswith("_"), argname #not supported
            assert argname in self.type_args, (argname, [v for v in self.type_args.keys() if not v.startswith("_")])
            arg = kwargs[argname]
            #TODO: type validation
            arg0 = kwargs0[argname]
            kwargs2[argname] = arg
            if isinstance(arg0, Cell):
                cell_args[argname] = arg0

        default = self.type_args["_default"]
        required = self.type_args["_required"]
        for argname in required:
            if argname.startswith("_arg"):
                assert argname in positional_done, argname #TODO: error message
            else:
                assert argname in kwargs2, argname #TODO: error message
        for argname in self.type_args:
            if argname.startswith("_"):
                continue
            if argname in kwargs2 and kwargs2[argname] is not None:
                continue
            arg_default = default.get(argname, None)
            kwargs2[argname] = arg_default
        if len(cell_args):
            macro_object = MacroObject(self, args0, kwargs0, cell_args)
        return args2, kwargs2, macro_object


    def __call__(self, *args, **kwargs):
        return self.evaluate(args, kwargs, None)

    def evaluate(self, args, kwargs, macro_object):
        from .cell import Cell, CellLike
        from .process import Process, ProcessLike, InputPinBase, OutputPinBase
        from .registrar import RegistrarObject

        args2, kwargs2, mobj = self.resolve_type_args(args, kwargs)
        func = self.func
        if macro_object is not None:
            mobj = macro_object
            parent = macro_object._parent()
            if isinstance(parent, RegistrarObject):
                func = parent.re_register
                args2 = args2[1:] #TODO: bound object because of hack...
        previous_macro_mode = get_macro_mode()
        if self.with_context:
            from seamless.core.context import get_active_context
            print("ACTIVE", get_active_context())
            #import sys
            #sys.exit()

            ctx = get_active_context()._new_subcontext()
            ret = None
            try:
                set_macro_mode(True)
                ret = func(ctx, *args2, **kwargs2)
                if ret is not None:
                    raise TypeError("Context macro must return None")
                ctx._set_macro_object(mobj)
                if macro_object is None: #this is a new construction, not a re-evaluation
                    if mobj is not None:
                        mobj.connect(ctx)
                ret = ctx
            finally:
                if ret is None:
                    ctx.destroy()
                set_macro_mode(previous_macro_mode)
        else:
            try:
                set_macro_mode(True)
                ret = func(*args2, **kwargs2)
                assert (isinstance(ret, CellLike) and ret._like_cell) or \
                 (isinstance(ret, ProcessLike) and ret._like_process) or \
                 isinstance(ret, RegistrarObject), (func, type(ret))
                if isinstance(ret, Cell):
                    manager = ret._get_manager()
                    cell_id = manager.get_cell_id(ret)
                    incons = manager.cells[cell_id]
                    for incon in incons:
                        process = incon.process_ref()
                        ret.own(process)
                    outcons = manager.listeners[ret]
                    for outcon in outcons:
                        process = outcon.process_ref()
                        ret.own(process)
                elif isinstance(ret, Process):
                    for pinname, pin in ret._pins.items():
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
                            ret.own(cell)
                elif isinstance(ret, RegistrarObject):
                    pass
                else:
                    raise NotImplementedError(type(ret))
                ret._set_macro_object(mobj)
                if macro_object is None: #this is a new construction, not a re-evaluation
                    if mobj is not None:
                        mobj.connect(ret)
            finally:
                set_macro_mode(previous_macro_mode)
        return ret

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
    if len(args) == 1 and callable(args[0]) and not len(kwargs):
        new_macro = _parse_init_args(func=args[0])
        #TODO: functools.wraps/update_wrapper on new_macro
        return new_macro
    else:
        new_macro = Macro(*args, **kwargs)
        def func_macro_wrapper(func):
            new_macro.func = func
            #TODO: functools.wraps/update_wrapper on new_macro
            return new_macro
        return func_macro_wrapper
