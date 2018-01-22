"""
Typedefs are either a string or a typedict with a "type" field containing such a string.
Type strings can be JSON schema types or "tuple", in which case "shape" must be defined
An "array" or "tuple" type contains a field "items", and a field "identical". If "identical" is True, then "items" contains only a single type/typedict,
"object" typedef always contain a field "properties"
In a typedict, "storage" is stored by the parent into a child typedict, but only if mixed.

else a list of them.
"""

from ..silk.SilkBase import SilkHasForm
from ..silk.validation import _array_types, _integer_types, _float_types, _string_types, Scalar

class MixedBase(SilkHasForm):
    def _get_silk_form(self):
        return self._form

def get_form_scalar(scalar):
    if isinstance(value, _integer_types):
        typedef = "integer"
    elif isinstance(value, _float_types):
        typedef = "number"
    elif isinstance(value, _string_types):
        typedef = "string"
    elif isinstance(value, bool):
        typedef = "boolean"
    elif value is None:
        typedef = "null"
    else:
        raise TypeError(type(value))
    return typedef

def visit_typedef_numpy(typedef, data):
    #to visit and fill in mixed-binary typedefs
    raise NotImplementedError

def get_form_numpy(dt):
    if dt.isbuiltin:
        if dt == object:
            storage = "mixed-binary"
            typedef = None #to be visited
        else:
            storage = "pure-binary"
            if any([dt == t for t in _integer_types]):
                typedef = "integer"
            elif any([dt == t for t in _float_types]):
                typedef = "number"
            elif any([dt == t for t in _string_types]):
                typedef = "string"
            elif dt == bool:
                typedef = "boolean"
            else:
                raise TypeError(dt)

        if dt.ndim:
            typedef = {
                "type": "tuple",
                "items": type_,
                "identical": True,
                "shape": dt.shape,
            }
        return storage, typedef

    if not dt.isalignedstruct:
        raise TypeError("Composite dtypes must be memory-aligned")
    if not dt.isnative:
        raise TypeError("Composite dtypes must be native")

    storages = {}
    typedef = {}
    for fieldname in dt.fields:
        cstorage, ctypedef = get_from_numpy(dt[fieldname])
        storages[fieldname] = cstorage
        typedef[fieldname] = ctypedef
    storage_set = set(storages.keys())
    if len(storage_set) == 1 and storage_set.pop() == "pure-binary":
        storage = "pure-binary"
    else:
        storage = "mixed-binary"
        for fieldname in dt.fields:
            cstorage = storages[fieldname]
            if cstorage == "pure-binary":
                continue
            ctypedef = typedef[fieldname]
            if isinstance(ctypedef, str):
                ctypedef = {"type": ctypedef}
                typedef[fieldname] = ctypedef

        typedef["storage"] = storage
    return storage, typedef



from .MixedDict import MixedDict
