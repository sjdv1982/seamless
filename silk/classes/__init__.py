class SilkObject:
    _has_optional = False
    def __ne__(self, other):
        return not self.__eq__(other)

class SilkStringLike(SilkObject):
    pass

from . import primitives
