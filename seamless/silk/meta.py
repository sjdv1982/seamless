from .Silk import Silk
import json

def meta(name, bases, d):
    # For now, ignore __module__ and __qualname__
    d.pop("__module__")
    d.pop("__qualname__")
    schema = d.pop("schema")
    s = Silk()
    s.schema.update(schema)
    prototype = {}
    for key, value in d.items():
        if isinstance(value, Validator):
            s.add_validator(value.func, attr=None, name=None)
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

    return Silk(schema=s.schema)

def prep(name, bases):
    return {
        "schema": {},
    }

meta.__prepare__ = prep


class Validator:
    def __init__(self, func):
        self.func = func

def validator(func):
    return Validator(func)
