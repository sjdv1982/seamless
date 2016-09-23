#TODO: primitive arrays
#TODO: silk methods

from . import SilkObject
class Integer(int, SilkObject): pass
class Float(float, SilkObject): pass
class String(str, SilkObject): pass

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

    def __repr__(self):
        if self is False:
            return "False"
        else:
            return "True"

    def dict(self):
        """Called by the dict function of silk classes
        that have Bool members
        For internal use only"""
        if self:
            return True
        else:
            return False

    def __eq__(self, other):
        return bool(self) == other
