from .primitives import String


class Enum(String):
    _enum = None

    def _validate(self):
        assert self in self._enum, (self, self._enum)


def make_enum(enum):
    enum = tuple([String(e) for e in enum])
    class_name = "Enum{}".format(enum)
    return type(class_name, (Enum,), {"_enum": enum})
