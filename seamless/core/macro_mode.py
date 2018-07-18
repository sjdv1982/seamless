import atexit
from weakref import WeakSet
from contextlib import contextmanager

toplevel_register = set()

def _destroy_toplevels():
    for ctx in list(toplevel_register):
        ctx.destroy(from_del=True)

atexit.register(_destroy_toplevels)



class MacroRegister:
    def __init__(self):
        self.stack = []
        self.curr_macro_stack = []
    def push(self, curr_macro):
        self.curr_macro_stack.append(curr_macro)
        self.stack.append(WeakSet())
    def pop(self):
        self.curr_macro_stack.pop()
        return self.stack.pop()
    def add(self, item):
        self.stack[-1].add(item)

macro_register = MacroRegister()

_macro_mode = False
def get_macro_mode():
    return _macro_mode

def curr_macro():
    if not _macro_mode:
        return None
    return macro_register.curr_macro_stack[-1]

def outer_macro():
    if not _macro_mode:
        return None
    return macro_register.curr_macro_stack[0]

@contextmanager
def macro_mode_on(macro=None):
    from . import Context
    from .layer import fill_objects, check_async_macro_contexts
    global _macro_mode
    old_macro_mode = _macro_mode
    _macro_mode = True
    macro_register.push(macro)
    try:
        yield
    finally:
        _macro_mode = old_macro_mode
    curr_macro_register = macro_register.pop()
    if not _macro_mode:
        mount.resolve_register(curr_macro_register)
    else:
        macro_register.stack[-1].update(curr_macro_register)
    if macro is None:
        filled = fill_objects(None, None)
        for obj in filled:
            obj.activate(only_macros=False)
        check_async_macro_contexts(None, None)
        created_contexts = []
        for ctx in curr_macro_register:
            if not isinstance(ctx, Context):
                continue
            for c in created_contexts:
                if c._part_of(ctx):
                    created_contexts.remove(c)
                    created_contexts.append(ctx)
                    break
                if ctx._part_of(c):
                    break
            else:
                created_contexts.append(ctx)
        for ctx in created_contexts:
            ctx._get_manager().activate(only_macros=False)


from . import mount
