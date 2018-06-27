from weakref import WeakSet
from contextlib import contextmanager

class MacroRegister:
    def __init__(self):
        self.stack = []
    def push(self):
        self.stack.append(WeakSet())
    def pop(self):
        return self.stack.pop()
    def add(self, item):
        self.stack[-1].add(item)

macro_register = MacroRegister()

_macro_mode = False
def get_macro_mode():
    return _macro_mode

@contextmanager
def macro_mode_on():
    global _macro_mode
    old_macro_mode = _macro_mode
    _macro_mode = True
    macro_register.push()
    try:
        yield
    finally:
        _macro_mode = old_macro_mode
    curr_macro_register = macro_register.pop()
    mount.resolve_register(curr_macro_register)

from . import mount
