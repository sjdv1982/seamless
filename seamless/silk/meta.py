from .schemawrapper import SchemaWrapper
from .Silk import Silk


def meta(name, bases, d):
    # For now, ignore __module__ and __qualname__
    d.pop("__module__")
    d.pop("__qualname__")
    schema = d.pop("schema").dict
    s = Silk()
    s.schema.dict.update(schema)
    with s.fork():
        for key, value in d.items():
            if isinstance(value, Validator):
                s._add_validator(value.func, attr=None, from_meta=True)
            else:
                setattr(s, key, value)

    return Silk(schema=s.schema.dict)

def prep(name, bases):
    return {
        "schema": SchemaWrapper(None, {}, None),
    }

meta.__prepare__ = prep


class Validator:
    def __init__(self, func):
        self.func = func

def validator(func):
    return Validator(func)
