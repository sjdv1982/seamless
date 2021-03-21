from pprint import pprint
from silk import Silk
from functools import partial
from silk.meta import meta, validator
class Coordinate(metaclass=meta):

    a = 1 # not a class default, but a type inference!
    # It is equivalent to: schema.properties.a.type = "integer"
    # If you want class default instead:
    #   - set schema.policy.infer_type to False
    #   - set schema.policy.infer_default to True
    # Note that the schema is only built *after* the class statement is complete
    #  but the direct schema manipulations are evaluated *first*

    def __init__(self, a=None):
        if a is not None:
            self.a = a

    def aa(self):
        return(self.a+1)

    @validator
    def ok(self):
        print("VALIDATE!", self.a.unsilk)
        assert self.a < 11

    @property
    def a2(self):
        return self.a + 1000

    @a2.setter
    def a2(self, value):
        self.a = value - 1000

pprint(Coordinate.schema)
c = Coordinate()
c.validate()
c = Coordinate(3)
pprint(c.schema)
print(c.unsilk)
c.a = 10
print(c.aa())
print(c.a2)
c.a2 = 1002
c.validate()
print(c.a.unsilk)
c.validate()
c.a = 11 # Error
c.validate()