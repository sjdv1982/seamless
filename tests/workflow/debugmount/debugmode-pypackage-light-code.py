def func(a, b):
    from .pypackage import get_square
    aa = get_square(a)
    bb = get_square(b)
    return aa+bb
