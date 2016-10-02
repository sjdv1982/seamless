# Copyright 2007-2016, Sjoerd de Vries

# TODO: primitive arrays

import ast
from . import SilkObject


class Float(float, SilkObject):
    """Wrapper class around a Python float"""
    def json(self):
        return self

    def __eq__(self, other):
        return float(self) == other

    def _print(self, spaces):
        return str(self)


class Integer(int, SilkObject):
    """Wrapper class around a Python int"""

    def json(self):
        return self

    def __eq__(self, other):
        return int(self) == other

    def _print(self, spaces):
        return str(self)


class String(str, SilkObject):
    """Wrapper class around a Python str"""

    def __new__(self, value):
        if value is None:
            raise ValueError

        if isinstance(value, String):
            return str.__new__(self, value)

        value = str(value)

        if value and value[0] == value[-1]:
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

    def _print(self, spaces):
        return str.__repr__(self)


class Bool(int, SilkObject):
    """Class that emulates a Python bool
    Unlike bool,
    "True" is equivalent to True
    and "False" is equivalent to False"""
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
