from silk import Silk
from functools import partial


class meta_test(dict):
    def __getitem__(self, attr):
        print("GET", attr)
        if attr == "print":
            return print
        return 42
    def __setitem__(self, attr, value):
        print("SET", attr)

exec("a = 5; print(a)", meta_test())

class SchemaClass:
    def __getattr__(self, attr):
        sc = SchemaClass()
        setattr(self, attr, sc)
        return sc
    def _get(self):
        d = {}
        for k,v in self.__dict__.items():
            if k.startswith("__"):
                continue
            if isinstance(v, SchemaClass):
                v = v._get()
            d[k] = v
        return d

class Validator:
    def __init__(self, func):
        self.func = func

def silk_meta(name, bases, d):
    # For now, ignore __module__ and __qualname__
    d.pop("__module__")
    d.pop("__qualname__")
    schema = d.pop("schema")
    schema = schema._get()
    s = Silk()
    s.schema.update(schema)
    with s.fork():
        for key, value in d.items():
            if isinstance(value, Validator):
                #s.add_validator(value.func)  #compile_function does not work on this...
                # HACK
                import inspect, textwrap, ast
                code =  inspect.getsource(value.func)
                code = code[code.find("    def "):]
                code = textwrap.dedent(code)
                validators = s.schema.get("validators", None)
                if validators is None:
                    validators = []
                    s.schema["validators"] = validators
                validators.append(code)
                # /HACK
            elif isinstance(value, property):
                setattr(s, key, value) #compile_function does not work on this...
                # HACK
                import inspect, textwrap, ast
                code =  inspect.getsource(value.fget)
                code = code[code.find("    def "):]
                code = textwrap.dedent(code)

                methods = s.schema.get("methods", None)
                if methods is None:
                    methods = {}
                    s.schema["methods"] = methods
                methods[key] = {"getter": code}
                # /HACK, also TODO setter
            else:
                setattr(s, key, value)

    return s.schema

def validator(func):
    return Validator(func)

def prep(name, bases):
    return {
        "schema": SchemaClass(),
    }
    # More fancy would be a very smart dict that does real-time Silk modification
    #  (see meta-test above)
    #  however, this would make *all* newly defined variables Silk properties

silk_meta.__prepare__ = prep


class Coordinate(metaclass=silk_meta):

    a = 10
    schema.properties.a.type = "integer" #not necessary if type inference is on

    def aa(self):
        return(self.a+1)

    @validator
    def ok(self):
        assert self.a < 11

    @property
    def a2(self):
        return self.a + 1000

c = Silk(schema=Coordinate)
print(c.schema)
c.a = 10
print(c.aa())
print(c.a2)
c.a = 11
