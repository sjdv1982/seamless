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

    def __new__(self, s):
        if s is None:
            raise ValueError
        if isinstance(s, String):
            return str.__new__(self, s)
        s = str(s)
        if len(s) and s[0] == s[-1]:
            if s[0] in ("'", '"'):
                try:
                    astree = ast.parse(s)
                    s = list(ast.iter_fields(astree))[0][1][0].value.s
                except:
                    pass
        ret = str.__new__(self, s)
        ret._validate()
        return ret

    def _validate(self):
        pass

    def json(self):
        return self

    def __eq__(self, other):
        return str(self) == other

    def __hash__(self):
        return str.__hash__(self)

    def _print(self, spaces):
        return str.__repr__(self)


class Bool(int, SilkObject):
    """Class that emulates a Python bool
    Unlike bool,
    "True" is equivalent to True
    and "False" is equivalent to False"""
    def __new__(self, b):
        if b == "True" or b == "\'True\'" or b == "\"True\"":
            return int.__new__(self, True)
        elif b == "False" or b == "\'False\'" or b == "\"False\"":
            return int.__new__(self, False)
        else:
            return int.__new__(self, bool(b))

    def __str__(self):
        if self is False:
            return "False"
        else:
            return "True"

    def json(self):
        if self:
            return True
        else:
            return False

    def __eq__(self, other):
        return bool(self) == other

    def _print(self, spaces):
        return str(self)
