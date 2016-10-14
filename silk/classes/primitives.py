# Copyright 2007-2016, Sjoerd de Vries

# TODO: primitive arrays

import ast
import numpy as np
from . import SilkObject, SilkStringLike


class Float(float, SilkObject):
    """Wrapper class around a Python float
    Uses float32 as numpy representation"""
    _dtype = np.float32

    def json(self):
        return self

    def __eq__(self, other):
        return float(self) == other

    def _print(self, spaces):
        return str(self)


class Integer(int, SilkObject):
    """Wrapper class around a Python int
    Uses int32 as numpy representation"""

    _dtype = np.int32
    def json(self):
        return self

    def __eq__(self, other):
        return int(self) == other

    def _print(self, spaces):
        return str(self)


class String(str, SilkStringLike):
    """Wrapper class around a Python string
    Numpy representation is an UTF-8-encoded 255-length byte string"""
    _dtype = '|S255'
    def __new__(self, value):
        if value is None:
            raise ValueError

        if isinstance(value, String):
            return str.__new__(self, value)
        if isinstance(value, bytes):
            return str.__new__(self, value.decode())
            value = str(value)
        if len(value) and value[0] == value[-1]:
            if value[0] in ("'", '"'):
                try:
                    astree = ast.parse(value)
                    value = list(ast.iter_fields(astree))[0][1][0].value.s

                except:
                    pass

        ret = str.__new__(self, value)
        ret._validate()

        return ret

    def _validate(self):
        pass

    def json(self):
        return self

    def __eq__(self, other):
        return str.__eq__(self, other)

    def __hash__(self):
        return str.__hash__(self)

    def _print(self, spaces):
        return '"' + str.__str__(self) + '"'


class Bool(int, SilkObject):
    """Class that emulates a Python bool
    Unlike bool, "True" is equivalent to True
    and "False" is equivalent to False"""
    _dtype = np.bool

    def __new__(self, value):
        if value == "True" or value == "\'True\'" or value == "\"True\"":
            return int.__new__(self, True)

        elif value == "False" or value == "\'False\'" or value == "\"False\"":
            return int.__new__(self, False)

        else:
            return int.__new__(self, bool(value))

    def __str__(self):
        if self:
            return "True"
        return "False"

    def json(self):
        return bool(self)

    def _print(self, spaces):
        return str(self)


class Double(Float):
    """Wrapper class around a Python float
    Uses float64 as binary representation"""
    _dtype = np.float64


class Long(Integer):
    """Wrapper class around a Python integer
    Uses int64 as binary representation"""
    _dtype = np.int64
