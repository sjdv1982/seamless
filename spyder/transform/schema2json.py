from lxml import etree
from lxml.builder import E
from lxml import objectify
import json
if __name__ !=  "__main__":
    from ..exceptions import SpyderError
else:
    SpyderError = Exception

_typemap = {
  "Float" : "number",
  "float" : "number",
  "Bool" : "boolean",
  "bool" : "boolean",
  "Integer" :"integer",
  "int" :"integer",
  "String":"string",
  "str": "string"
}

default_spyderspace = {
  "Float": float,
  "Bool": bool,
  "String": str,
  "Integer": int,
}

def schema2json(xml, namespace=None, spyderspace=default_spyderspace):
    """Converts spyderschema XML to JSON schema"""
    class dummy: pass
    j = dummy()
    j.__dict__.update(
      {
        "$schema": "http://json-schema.org/schema#",
        "type": "object",
        "properties": {},
        "required": [],
      }
    )
    x = objectify.fromstring(xml)
    j.title = str(x.typename)

    #TODO: Delete, Include
    #deleting a member also deletes the optional!
    #delete always comes after include, and before everything else

    optionals = []
    if hasattr(x, "optional"):
        for optional in x.optional:
            for member in optional.splitlines():
                optionals.append(member.strip())
    membernames = [str(member.name) for member in x.member]
    for optional in optionals:
        if optional not in membernames:
            raise SpyderError("Unknown optional: {0}".format(optional))
    for member in x.member:
        try:
            jsontype = _typemap[member.type]
        except KeyError:
            if namespace is not None and hasattr(namespace, member.type):
                jsontype = getattr(namespace, member.type)
            else:
                raise SpyderError("Unknown type: {0}".format(member.type))
        spyderspacetype = spyderspace[str(member.type)]
        j.properties[str(member.name)] = {"type":jsontype}
        if not hasattr(member,"init") and member.name not in optionals:
            j.required.append(str(member.name))
    return json.dumps(j.__dict__, sort_keys=True,indent=2)

if __name__ == "__main__":
    import sys
    xml = open(sys.argv[1]).read().encode('UTF-8')
    jsontxt = schema2json(xml)
    print(jsontxt)
