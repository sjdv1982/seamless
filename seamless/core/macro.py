print("STUB: macro.py")

from contextlib import contextmanager

_macro_mode = False
def get_macro_mode():
    return _macro_mode

@contextmanager
def macro_mode_on():
    global _macro_mode
    old_macro_mode = _macro_mode
    _macro_mode = True
    try:
        yield
    finally:
        _macro_mode = old_macro_mode
