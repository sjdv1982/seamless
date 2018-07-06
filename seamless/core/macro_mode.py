from weakref import WeakSet
from contextlib import contextmanager

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

@contextmanager
def macro_mode_on(macro=None):
    from .layer import fill_objects
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
        fill_objects(None)


from . import mount
