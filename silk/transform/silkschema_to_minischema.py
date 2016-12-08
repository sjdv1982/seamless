from lxml import etree
from lxml.builder import E
from lxml import objectify
import json

from seamless.silk.exceptions import SilkError
from seamless.silk.stringparse import stringparse
from collections import OrderedDict

class Empty:
    def __init__(self):
        self._dic = OrderedDict()
    def __getattr__(self, attr):
        return self._dic[attr]
    def __setattr__(self, attr, value):
        if attr == "_dic":
            return super(Empty, self).__setattr__(attr, value)
        self._dic[attr] = value
    def __delattr__(self, attr):
        self._dic.pop(attr)

def silkschema_to_minischema(xml):
    """Converts silk-schema XML to JSON minischema"""
    obj_from_xml = objectify.fromstring(xml)
    schemas = []
    for schema in obj_from_xml.iterchildren(tag="silk"):
        container = Empty()
        container.type = str(schema.get("typename"))
        base = schema.find("base")
        if base:
            base = base[0]
            container.base = str(base)
        container.properties = OrderedDict()
        container.required = []
        container.init = []
        container.order = []

        def parse_enum(txt):
            options = stringparse(txt)
            ret = []
            for option in options:
                if len(option) >= 2 \
                 and option[0] == option[-1] \
                 and option[0] in ("'", '"'):
                   option = option[1:-1]
                ret.append(option)
            return ret
        # TODO: Delete, Include
        for member in schema.iterchildren(tag="member"):
            name = str(member.name)
            if hasattr(member, "enum"):
                container.properties[name] = { "Enum": parse_enum(member.enum.text) }
            else:
                container.properties[name] = str(member.type)
            if not hasattr(member, "init") and not member.get("optional", False):
                container.required.append(name)
            if hasattr(member, "init"):
                container.init.append(name)
            container.order.append(name)
        for attr in "properties", "required", "init", "order":
            if not len(getattr(container, attr)):
                delattr(container, attr)
        schemas.append(container._dic)
    return schemas

if __name__ == "__main__":
    import sys
    xml = open(sys.argv[1]).read().encode('UTF8')
    schemas = silkschema_to_minischema(xml)
    if len(schemas) == 1:
        schemas = schemas[0]
    print(json.dumps(schemas, indent=2))
