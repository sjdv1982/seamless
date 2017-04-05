class SilkObject:
    __slots__ = []
    def __ne__(self, other):
        return not self.__eq__(other)

class SilkStringLike(SilkObject):
    __slots__ = []

from . import primitives
