from lxml import etree
from lxml.builder import E
from lxml import objectify
import json

from ..exceptions import SilkError


_type_map = {
  "Float": "number",
  "float": "number",
  "Bool": "boolean",
  "bool": "boolean",
  "Integer": "integer",
  "int": "integer",
  "String": "string",
  "str": "string"
}

default_silk_space = {
  "Float": float,
  "Bool": bool,
  "String": str,
  "Integer": int,
}


class Empty:
    pass


def schema_to_json(xml, namespace=None, silk_space=default_silk_space):
    """Converts silk-schema XML to JSON schema"""
    container = Empty()
    container.__dict__.update(
      {
        "$schema": "http://json-schema.org/schema#",
        "type": "object",
        "properties": {},
        "required": [],
      }
    )
    obj_from_xml = objectify.fromstring(xml)
    container.title = str(obj_from_xml.typename)

    # TODO: Delete, Include
    # deleting a member also deletes the optional!
    # delete always comes after include, and before everything else

    if hasattr(obj_from_xml, "optional"):
        optionals = [member.strip() for optional in obj_from_xml.optional for member in optional.splitlines()]

    else:
        optionals = []

    member_names = [str(member.name) for member in obj_from_xml.member]

    for optional in optionals:
        if optional not in member_names:
            raise SilkError("Unknown optional: {0}".format(optional))

    for member in obj_from_xml.member:
        try:
            json_type = _type_map[member.type]

        except KeyError:
            if namespace is not None and hasattr(namespace, member.type):
                json_type = getattr(namespace, member.type)

            else:
                raise SilkError("Unknown type: {0}".format(member.type))

        silk_space_type = silk_space[str(member.type)]

        container.properties[str(member.name)] = {"type": json_type}

        if not hasattr(member, "init") and member.name not in optionals:
            container.required.append(str(member.name))

    return json.dumps(container.__dict__, sort_keys=True, indent=2)
