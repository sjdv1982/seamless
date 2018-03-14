max_array_depth = 2

reserved_types = (
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
  "validate", "data", "dict", "fromfile", "tofile",
  "set", "make_numpy"
)


def is_valid_silktype(type_name, permit_array=False):
    """Tests if a string is a valid silk type"""
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
