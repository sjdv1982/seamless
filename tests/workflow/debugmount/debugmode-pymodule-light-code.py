def func(a, b):
    from .pymodule import get_square
    aa = get_square(a)
    bb = get_square(b)
    return aa+bb
