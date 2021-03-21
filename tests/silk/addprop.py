from pprint import pprint
import jsonschema
from silk import Silk
import json

def validate(self):
    assert self.x > self.y

s = Silk()
s.x = 10
s.y = 2
pprint(s.schema)
s.add_validator(validate)
s.validate()
s.schema["additionalProperties"] =  {"type": "string"}
jsonschema.validate(s.data, s.schema)

s.schema["policy"] = {}
s.schema["policy"]["infer_new_property"] = False
s.z = "OK"
pprint(s.schema)
s.validate()

print(s.items()) # NOTE: values are NOT wrapped in a Silk object!

try:
    s.err = 1 #error
    s.validate()
except Exception as exc:
    print(exc)
