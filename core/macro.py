from collections import OrderedDict
import functools
import copy
import inspect
import sys
import weakref
from .context import context, get_active_context
from contextlib import contextmanager as _pystdlib_contextmanager
from .macro_object import MacroObject
from .cached_compile import cached_compile

#macros = weakref.WeakValueDictionary()
_macros = {}

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

class Macro:
    module_name = None
    func_name = None
    code = None
    dtype = ("text", "code", "python")
    registrar = None

    def __init__(self, type=None, with_context=True,
            registrar=None,func=None):
        self.with_context = with_context
        self.registrar = registrar
        self.type_args = None
        self._type_args_unparsed = type
        self.macro_objects = weakref.WeakValueDictionary() #"WeakList"
        if func is not None:
            assert callable(func)
            self.set_func(func)

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
        if "_order" in type:
            order = type["_order"]
            assert sorted(order) == sorted([k for k in type.keys() if not k.startswith("_")])
        required = set()
        default = {}
        ret = dict(_order=order, _required=required, _default=default)
        last_nonreq = None
        for k in type:
            if k.startswith("_"):
                if k == "_order":
                    continue
                assert k.startswith("_arg"), k
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

    def set_func(self, func):
        if self.registrar:
            #self.registrar = func.__self__
            self.func = func
            return self

        code = inspect.getsource(func)
        module = inspect.getmodule(func)
        #HACK:
        # I don't know how to get a module's import path in another way,
        # and apparently a module is in sys.modules already during import
        for k, v in sys.modules.items():
            if v is module:
                module_name = k
                break
        else:
            raise ValueError #module is not in sys.modules...
        func_name = func.__name__
        if (module_name, func_name) in _macros:
            ret = _macros[module_name, func_name]
            ret.update_code(code)
        else:
            _macros[module_name, func_name] = self
            self.module_name = module_name
            self.func_name = func_name
            self.update_code(code)
            ret = self
        return ret

    def update_code(self, code):
        from .utils import strip_source
        if self.code is not None and self.code == code:
            return
        assert self.registrar is None
        assert self.module_name is not None
        assert self.func_name is not None

        def dummy_macro(*args, **kwargs):
            if len(args) == 1 and not kwargs:
                arg, = args
                if callable(arg):
                    return arg
            return lambda func: func

        namespace = {
          "OrderedDict": OrderedDict,
          "macro": dummy_macro
        }
        identifier = self.module_name
        if self.module_name in sys.modules:
            try:
                identifier = inspect.getsourcefile(
                  sys.modules[self.module_name]
                )
            except TypeError:
                pass
        code = strip_source(code)
        identifier2 = "macro <= "+identifier + " <= " + self.func_name
        ast = cached_compile(code, identifier2)
        exec(ast, namespace)
        self.code = code
        self.func = namespace[self.func_name]
        keys = sorted(self.macro_objects.keys())
        if len(keys):
            warn = "WARNING: changing the code of {0}, re-executing {1} live macros"
            print(warn.format(identifier2, len(keys)))
        for key in keys:
            if key not in self.macro_objects:
                continue
            macro_object = self.macro_objects[key]
            macro_object.update_cell(None)

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
        from .process import Process, ProcessLike, InputPinBase, \
         OutputPinBase, EditPinBase
        from .registrar import RegistrarObject
        from .context import active_context_as
        from .. import run_work

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
            ctx = get_active_context()._new_subcontext()
            ret = None
            try:
                with active_context_as(ctx):
                    set_macro_mode(True)

                    ret = func(ctx, *args2, **kwargs2)
                    if ret is not None:
                        raise TypeError("Context macro must return None")
                    if len(_macro_registrar):
                        if mobj is None:
                            mobj = MacroObject(self, args, kwargs, {})
                        mobj.set_registrar_listeners(_macro_registrar)
                    ctx._set_macro_object(mobj)

                    if macro_object is None: #this is a new construction, not a re-evaluation
                        if mobj is not None:
                            mobj.connect(ctx)
                    ret = ctx
            finally:
                _macro_registrar.clear()
                if ret is None:
                    ctx.destroy()
                set_macro_mode(previous_macro_mode)
        else:
            with macro_mode_as(True):
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
                        if isinstance(pin, (InputPinBase, EditPinBase)):
                            cell_ids = manager.pin_to_cells.get(pin_id, [])
                        elif isinstance(pin, OutputPinBase):
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

        if not get_macro_mode():
            run_work()
        return ret

def macro(*args, **kwargs):
    """Macro decorator,  wraps a macro function

    Any cell arguments to the function are automatically converted to their
     value, and a live macro object is created: whenever one of the cells
     changes value, the macro function is re-executed
    IMPORTANT:
    The macro function object is never executed directly: instead, its source
     code is extracted and used to build a new function object
    This is so that macro source can be included when the context is saved.
    Therefore, the function source MUST be self-contained, i.e. not rely on
     other variables defined or imported elsewhere in its module.
    Only registrar methods deviate from this rule, since registrar code is
     never stored in the saved context. The "registrar" parameter indicates
     that the macro is a registrar method.

    Macros are identified by the name of the module (in sys.modules) that
     defined them, and the name of the macro function.
    If a new macro is defined with the same module name and function name,
     the old macro is updated and returned instead

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
        new_macro2 = new_macro.set_func(func)
        # TODO: functools.wraps/update_wrapper on new_macro2
        return new_macro2

    return func_macro_wrapper
