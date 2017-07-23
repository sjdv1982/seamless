import copy
import inspect
import sys
import weakref
from collections import OrderedDict
from contextlib import contextmanager
import functools

from .cached_compile import cached_compile
from .context import get_active_context
from .macro_object import MacroObject
from ..dtypes.cson import cson2json

# macros = weakref.WeakValueDictionary()
_macros = {}

_activation_mode = True
_macro_mode = False
_macro_registrar = []
_activate = []


def add_activate(obj):
    if _activation_mode:
        obj.activate()
    else:
        _activate.append(obj)


def set_activation_mode(activation_mode):
    global _activation_mode
    if activation_mode and not _activation_mode:
        try:
            for obj in _activate:
                if obj._destroyed:
                    continue
                try:
                    p = obj.parent()
                except AttributeError:
                    p = obj
                obj.activate()
        finally:
            _activate[:] = []
    _activation_mode = activation_mode


def get_activation_mode():
    return _activation_mode


@contextmanager
def activation_mode_as(mode):
    old_mode = get_activation_mode()
    set_activation_mode(mode)
    yield
    set_activation_mode(old_mode)


def get_macro_mode():
    return _macro_mode


@contextmanager
def macro_mode_on():
    global _macro_mode
    old_macro_mode = _macro_mode
    old_activation_mode = _activation_mode
    set_activation_mode(False)
    _macro_mode = True
    try:
        yield
    finally:
        _macro_mode = old_macro_mode
        set_activation_mode(old_activation_mode)


class Macro:
    module_name = None
    func_name = None
    code = None
    dtype = ("text", "code", "python")
    registrar = None

    def __init__(self, type=None, *args, with_context=True, with_caching=False,
                 registrar=None, func=None):
        self.with_context = with_context
        if with_caching: assert with_context == True
        self.with_caching = with_caching

        self.registrar = registrar
        self._type_args = None
        self._type_args_unparsed = type
        self._type_args_processed = type
        self.macro_objects = weakref.WeakValueDictionary()  # "WeakList"
        if func is not None:
            assert callable(func)
            self.set_func(func)

        if type is None:
            return

        if isinstance(type, tuple) or isinstance(type, str):
            self._type_args = {'_order': ["_arg1"], '_required': ["_arg1"], '_default': {}, '_arg1': type}
            if len(args):
                for tnr, t in enumerate(args):
                    assert isinstance(t, tuple) or isinstance(t, str), t
                    a = "_arg" + str(tnr+2)
                    self._type_args["_order"].append(a)
                    self._type_args["_required"].append(a)
                    self._type_args[a] = t
            return
        assert not len(args)

        if not isinstance(type, dict):
            raise TypeError(type.__class__)

        self._type_args = self._get_type_args_from_dict(type)
        type_args_processed = copy.deepcopy(type)
        if isinstance(type, OrderedDict):
            type_args_processed["_order"] = self._type_args.get("_order", [])
        self._type_args_processed = type_args_processed

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
                    # TODO: checking regarding type <=> default
                    # TODO: check that the default can be serialised, or at least pickled
                    default[name] = value["default"]
            type_args[name] = value_type

            if is_required:
                required.add(name)

            else:
                last_non_required_name = name

        return copy.deepcopy(type_args)

    def set_func(self, func):
        if self.registrar:
            # self.registrar = func.__self__
            self.func = func
            return self

        code = inspect.getsource(func)
        module = inspect.getmodule(func)
        # HACK:
        # I don't know how to get a module's import path in another way,
        # and apparently a module is in sys.modules already during import
        for k, v in sys.modules.items():
            if v is module:
                module_name = k
                break
        else:
            raise ValueError  # module is not in sys.modules...
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
        """ #interferes with resource.fromfile
        if self.module_name in sys.modules:
            try:
                identifier = inspect.getsourcefile(
                  sys.modules[self.module_name]
                )
            except TypeError:
                pass
        """
        code = strip_source(code)
        identifier2 = "macro <= " + identifier + " <= " + self.func_name
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

    def resolve(self, obj):
        # TODO: allow CellLike contexts as well (also in cell_args in resolve_type_args)
        from .cell import Cell
        from ..dtypes import parse

        if isinstance(obj, Cell):
            result = parse(obj.dtype, obj._data, trusted=True)
            if result is None:
                raise Exception("Cell macro argument '%s' cannot be undefined" % obj)
        else:
            result = obj
        return result

    def resolve_type_args(self, args, kwargs):
        """
        #TODO: When macro object is created and attached to context X, verify that all resolved
         cells and X have a common ancestor (._root)
        """
        from .cell import Cell

        macro_object = None
        resolved_args = [self.resolve(a) for a in args]
        resolved_kwargs = {k: self.resolve(v) for k, v in kwargs.items()}

        if self._type_args is None:
            return resolved_args, resolved_kwargs, None

        order = self._type_args["_order"]
        assert len(resolved_args) <= len(order), (order, args, kwargs)

        # TODO: take and adapt corresponding routine from Hive
        new_args, new_kwargs = [], {}
        positional_done = set()

        for name, arg, arg0 in zip(order, resolved_args, args):
            dtype = self._type_args[name]
            # TODO: type validation

            # STUB:
            if isinstance(arg0, Cell):
                if dtype is not None and \
                        (dtype == "json" or dtype[0] == "json") and \
                                arg0.dtype is not None and \
                        (arg0.dtype == "cson" or arg0.dtype[0] == "cson"):
                    arg = cson2json(arg)
            if name.startswith("_arg"):
                new_args.append(arg)
                positional_done.add(name)
            else:
                new_kwargs[name] = arg

        new_kwargs.update(resolved_kwargs)

        for name, arg in resolved_kwargs.items():
            assert not name.startswith("_"), name  # not supported
            assert name in self._type_args, (name, [v for v in self._type_args.keys() if not v.startswith("_")])
            # TODO: type validation

        default = self._type_args["_default"]
        required = self._type_args["_required"]

        default = self._type_args["_default"]
        required = self._type_args["_required"]
        for argname in required:
            if argname.startswith("_arg"):
                assert argname in positional_done, (argname, order, len(args))  # TODO: error message
            else:
                assert argname in new_kwargs, argname  # TODO: error message

        for name in self._type_args:
            if name.startswith("_"):
                continue
            if name in new_kwargs and new_kwargs[name] is not None:
                continue

            arg_default = default.get(name, None)
            new_kwargs[name] = arg_default

        cell_args = {}
        for pos, arg0 in enumerate(args):
            if isinstance(arg0, Cell):
                cell_args[pos] = arg0
        for name, arg0 in kwargs.items():
            if isinstance(arg0, Cell):
                cell_args[name] = arg0

        if cell_args:
            macro_object = MacroObject(self, args, kwargs, cell_args)
        return new_args, new_kwargs, macro_object

    def evaluate(self, args, kwargs, macro_object):
        from .cell import Cell, CellLike
        from .worker import Worker, WorkerLike, InputPinBase, \
            OutputPinBase, EditPinBase
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
                resolved_args = resolved_args[1:]  # TODO: bound object because of hack...

        if self.with_context:
            ctx = get_active_context()._new_subcontext()
            result = None
            with active_context_as(ctx), macro_mode_on():
                try:
                    ret = func(ctx, *resolved_args, **resolved_kwargs)
                    if ret is not None:
                        raise TypeError("Context macro must return None")
                    if _macro_registrar:
                        if mobj is None:
                            mobj = MacroObject(self, args, kwargs, {})
                        mobj.set_registrar_listeners(_macro_registrar)
                    ctx._set_macro_object(mobj)

                    if macro_object is None:  # this is a new construction, not a re-evaluation
                        if mobj is not None:
                            mobj.connect(ctx)
                    result = ctx
                finally:
                    _macro_registrar.clear()
                    if result is None:
                        ctx.destroy()
        else:
            with macro_mode_on():
                result = func(*resolved_args, **resolved_kwargs)
                assert (isinstance(result, CellLike) and result._like_cell) \
                       or (isinstance(result, WorkerLike) and result._like_worker) \
                       or isinstance(result, RegistrarObject), (func, type(result))

                if isinstance(result, Cell):
                    manager = result._get_manager()
                    cell_id = manager.get_cell_id(result)

                    in_pins = manager.cells[cell_id]
                    for in_pin in in_pins:
                        worker = in_pin.worker_ref()
                        result.own(worker)

                    out_pins = manager.listeners[result]
                    for out_pin in out_pins:
                        worker = out_pin.worker_ref()
                        result.own(worker)

                elif isinstance(result, Worker):
                    for pinname, pin in result._pins.items():
                        manager = pin._get_manager()
                        pin_id = pin.get_pin_id()

                        if isinstance(pin, (InputPinBase, EditPinBase)):
                            cell_ids = manager.pin_to_cells.get(pin_id, [])

                        elif isinstance(pin, OutputPinBase):
                            cell_ids = pin._cell_ids

                        else:
                            raise TypeError((pinname, pin))

                        for cell_id in cell_ids:  # TODO: indirect ownage
                            cell = manager.cells.get(cell_id, None)
                            if cell is None:
                                continue
                            result.own(cell)
                elif isinstance(result, RegistrarObject):
                    pass
                else:
                    raise NotImplementedError(type(result))

                result._set_macro_object(mobj)
                if macro_object is None:  # this is a new construction, not a re-evaluation
                    if mobj is not None:
                        mobj.connect(result)

        if not get_macro_mode():
            run_work()
        return result

    def __call__(self, *args, **kwargs):
        assert hasattr(self, "func"), (self.module_name, self.func_name)
        return self.evaluate(args, kwargs, None)


def macro(*args, **kwargs):
    """Macro decorator,  wraps a macro function

Macro functions construct new seamless objects (contexts, cells, workers).

In their code, macro functions may themselves invoke macros.

Macro function arguments can be either values or cells.

If any argument to the the macro function is a cell, then all cell arguments
are automatically converted to their values, and a live macro object is created:
whenever one of the cells changes value, the macro function is re-executed.

The macro function object is never executed directly: instead, its source
code is extracted and used to build a new function object.
This is so that macro source can be included when the context is saved.
Therefore, the function source MUST be self-contained, i.e. not rely on
other variables defined or imported by code outside the function.
Only registrar methods deviate from this rule, since registrar code is
never stored in the saved context. The `registrar` parameter indicates
that the macro is a registrar method.

Macros are identified by the name of the module (in ``sys.modules``) that
defined them, and the name of the macro function.
If a new macro is defined with the same module name and function name,
the old macro is updated and returned instead.

Parameters
----------

type: a single type tuple, a list of type tuples, or a dict/OrderedDict
  if type is a dict, then:

    - every key is a parameter name
    - every value is either a dtype, or a dict, where:

        - `type` is the dtype
        - `optional` (optional) is a boolean
        - `default` (optional) is a default value.

    The type dict is parsed from `**kwargs` (keyword arguments)
    Unspecified optional arguments default to ``None``, unless `default` is
    specified.
  if type is an OrderedDict, then:
    as above, but the type dict is parsed from `*args` (positional arguments)
    and `**kwargs` (keyword arguments).

  As an additional value for `dtype`, "self" is allowed. This indicates
  that the macro is a method decorator, and the first argument
  is a bound object. In this case, the macro source is never stored.

  Currently, macro method decorators are only used for registrar methods.

with_context: bool
  if `ctx` is True, the function is passed a context object `ctx` as additional
  first parameter, and is expected to return None.

  The macro may invoke ``ctx.export(w)``, where `w` is one of the workers
  of `ctx`. In that case, all unconnected pins of `w` are exported, and `ctx`
  becomes a worker-like context, for the purposes of ``shell``
  for example. ``ctx.export(w, force)`` forces the export of all pins in
  `force`.

  if `ctx` is False, the function is expected to return a cell or worker.
  This cell or worker (together with any other cells or workers
  created by the macro) is automatically added to the active context.

  As of seamless 0.1, there are no macros that return a cell,
  i.e. this is untested!

with_caching: bool
  if True, whenever the macro is re-invoked, it tries to salvage as much as
  possible from the previously created context.

  Requires that `with_context` is True.

  As of seamless 0.1, only the slash0 macro has `with_caching` enabled.

Examples
--------

Example 1::

    @macro

Defines a macro with ``with_context=True``, no type checking.

Example 2::

    @macro("str")

Defines a macro with a single argument, which must be of type `str`,
and ``with_context=True``.

Example 3::

    @macro({
      "spam": { "type":"str", "optional":True },
      "ham": ("code", "python"),
      "eggs": "int"
    }, with_context=False)

Defines a macro with a three arguments. The arguments must be defined as
keyword arguments, `spam` is optional,and ``with_context=False``.
"""
    if len(args) == 1 and not kwargs:
        arg, = args
        if callable(arg):
            result = Macro(func=arg)
            functools.update_wrapper(result, arg)
            return result

    new_macro = Macro(*args, **kwargs)
    if new_macro.registrar is not None:
        def func_macro_wrapper_registrar(func):
            new_macro2 = new_macro.set_func(func)
            return new_macro2
        return func_macro_wrapper_registrar

    def func_macro_wrapper(func):
        new_macro2 = new_macro.set_func(func)

        # The following does not work:
        #functools.update_wrapper(new_macro2, func)
        #return new_macro2

        @functools.wraps(func)
        def macro_caller(*args, **kwargs):
            return new_macro2(*args, **kwargs )
        return macro_caller

    return func_macro_wrapper
