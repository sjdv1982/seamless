from collections import OrderedDict
import functools
from .context import context, get_active_context

#TODO: implement lib system, and let pins connect to CellProxies instead of
# cells. CellProxies work exactly the same as cells
# (pass-through attribute access), except that they can be forked
#TODO: get the source of the macro, store this in a cell, and make sure that
# 1. it gets properly captured by the lib system
# 2. if the source of the macro is different from the lib cell content,
# fork any cellproxies linking to the old lib cell, then update the lib cell,
# and issue a warning

def _parse_init_args(type=None, with_context=True):
    return type, with_context

def _parse_type_args(type):
    if type is None:
        return None
    if not isinstance(type, dict):
        raise TypeError(type.__class__)
    order = []
    required = {}


def _resolve(a):
    from .cell import Cell
    if isinstance(a, Cell):
        return a._data
    else:
        return a

def _func_macro(func, type, with_context, *args, **kwargs):
    args2 = [_resolve(a) for a in args] #TODO: type validation
    kwargs2 = {k:_resolve(v) for k,v in kwargs.items()}
    if with_context:
        ctx = context(parent=get_active_context(), active_context=False)
        ret = func(ctx, *args2, **kwargs2)
        if ret is not None:
            raise TypeError("Context macro must return None")
        return ctx
    else:
        return func(*args2, **kwargs2)

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

    with_context: bool
      if True, the function is passed a context object as additional
       first parameter, and is expected to return None
      if False, the function is expected to return a cell or process.
       This cell or process must be added manually to the context
       The returned cell or process is marked as "owner" of any other cells
       or processes created by the macro. When the owner is deleted, the owned
       cells and processes are deleted as well
       (TODO!)

    Example 1:
    @macro
    defines a macro with with_context = True, no type checking

    Example 2:
    @macro("string")
    defines a macro with a single argument, which must be of type "string",
     and with_context is True.

    Example 2:
    @macro({
      "spam": { "type":"string", "optional":True },
      "ham": ("code", "python"),
      "eggs": "int"
    })
    defines a macro with a three arguments. The arguments must be defined as
     keyword arguments, and "spam" is optional


    """
    if len(args) == 1 and callable(args[0]) and not len(kwargs):
        type, with_context = _parse_init_args()
        func = args[0]
        return functools.update_wrapper(functools.partial(
         _func_macro,
         func,
         type,
         with_context
        ),func)
    else:
        type, with_context = _parse_init_args(*args, **kwargs)
        type = _parse_type_args(type)
        def func_macro_wrapper(func):
            return functools.update_wrapper(functools.partial(
             _func_macro,
             func,
             type,
             with_context
            ), func)
        return func_macro_wrapper
