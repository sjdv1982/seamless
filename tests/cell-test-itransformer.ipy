%load_ext Cython

%%cython
from libc.math cimport log
def func(i):
    cdef int n
    cdef int nn
    cdef double s = 0
    for n in range(i):
        for nn in range(i):
            s += log(n*nn+1)
    return s


def transform():
    return func(i)
