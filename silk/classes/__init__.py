class SilkObject:
    def __ne__(self, other):
        return not self.__eq__(other)

from . import primitives
