#STUB
import functools
from .context import context, get_active_context

def _parse_init_args(type=None, with_context=True):
    return type, with_context

def _resolve(a):
    from .cell import Cell
    if isinstance(a, Cell):
        return a._data
    else:
        return a

def _func_macro(func, type, with_context, *args, **kwargs):
    args2 = [_resolve(a) for a in args]
    kwargs2 = {k:_resolve(v) for k,v in kwargs.items()}
    if with_context:
        ctx = context(parent=get_active_context(), active_context=False)
        ret = func(ctx, *args2, **kwargs2)
        if ret is not None:
            raise TypeError("Context macro must return None")
    else:
        return func(*args2, **kwargs2)

def macro(*args, **kwargs):
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
        def func_macro_wrapper(func):
            return functools.update_wrapper(functools.partial(
             _func_macro,
             func,
             type,
             with_context
            ), func)
        return func_macro_wrapper
