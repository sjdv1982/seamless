max_array_depth = 2


reserved_types = (
  "Spyder",
  "Type",
  "Object",
  "Delete",
  "Include",
  "None",
  "True",
  "False",
)

reserved_endings = (
  "Error",
  "Exit",
  "Exception",
)

reserved_membernames = (
  "type", "typename", "length", "name",
  "convert", "cast", "validate",
  "data", "str", "repr", "dict", "fromfile", "tofile",
  "listen", "block", "unblock", "buttons", "form",
  "invalid",
)


# Todo - memoize
def is_valid_spydertype(type_name, permit_array=False):
    """Tests if a string is a valid Spyder type"""
    if not type_name.replace("_", "x").isalnum():
        return False

    if not type_name[0].isupper():
        return False

    if len(type_name) > 1 and type_name == type_name.upper():
        return False

    if permit_array:
        array_depth = 0
        while type_name.endswith("Array"):
            type_name = type_name[:-len("Array")]
            array_depth += 1

        if array_depth > max_array_depth:
            return False

    elif type_name.endswith("Array"):
        return False

    if type_name in reserved_types:
        return False

    for ending in reserved_endings:
        if type_name.endswith(ending):
            return False
    return True
