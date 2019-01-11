import jsonschema
from seamless.silk import Silk
import json

def validate(self):
    assert self.x > self.y

s = Silk()
s.x = 10
s.y = 2
print(s.schema)
s.add_validator(validate)
s.schema.additionalProperties =  {"type": "string"}
schema = dict(s.schema._dict)
jsonschema.validate(dict(s.data), schema)

s.schema.policy = {}
s.schema.policy.infer_new_property = False
s.z = "OK"
print(s.schema)
s.err = 1 #error
