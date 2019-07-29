from .schemawrapper import SchemaWrapper
from .Silk import Silk
import json

def meta(name, bases, d):
    # For now, ignore __module__ and __qualname__
    d.pop("__module__")
    d.pop("__qualname__")
    schema = d.pop("schema").dict
    s = Silk()
    s.schema.dict.update(schema)
    prototype = {}
    with s.fork():
        for key, value in d.items():
            if isinstance(value, Validator):
                s._add_validator(value.func, attr=None, from_meta=True, name=None)
            elif callable(value) or isinstance(value, property):
                setattr(s, key, value)
            else:
                try:
                    json.dumps(value)
                except Exception:
                    raise ValueError("'%s' is not JSON-serializable" % key)
                prototype[key] = value
        if len(prototype):            
            s.schema["__prototype__"] = prototype

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
