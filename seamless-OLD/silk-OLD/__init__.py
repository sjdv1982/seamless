"""
OUTDATED!

Spyder consists of three parts:
- A schema format (.spy) to define rich data models (validation, inline formatting definitions)
- A toolchain to convert a data model defined in .spy into a Python class,
   together with meta-information (dependency list, type schema tree, form tree)
- A data format (.web) to define instances of data models. Spyder Python classes can automatically
  parse the format


The toolchain applies the following transformations
.spy => SpyXML
SpyXML => Spyder dependency list
SpyXML => JSON schema
  subset of JSON schema
  Fully expanded to the level of Spyder primitives.
  Spyder primitives are mapped, e.g Integer => int
SpyXML => code sheet (validation rules and their error messages, extra methods) (JSON)
SpyXML => form instructions (XML)
JSON schema + validation sheet => Python class

This leads to the following ATC definitions:

Conversions:

("spyder", "schema")            => ("xml", "schema", "spyder")
("xml", "schema", "spyder")     =>
    ("spyder", "depslist") +
    ("json", "schema") +
    ("json", "codesheet", "python") +
    ("xml", "schema", "form")
("json", "schema") +
("json", "codesheet", "python")   =>
    ("code", "python")

Operations:
("code", "python") => register(typename)
("xml",  "schema", "form")  => register(typename)
("spyder", "depslist") => register(typename)
The schema is a class attribute of the Spyder class
The form() class attribute of the Spyder class returns dynamically the registered form

ATC chains:

- Primary chain
atc.operator (
    (open("Bla.spy").read(),
    ("spyder", "schema"),
    "register",
    "Bla"
)

- Only as data:
result = atc.convert
    (open("Bla.spy").read(),
    ("spyder", "schema"),
    [
        ("spyder", "depslist"),
        ("json", "codesheet", "python"),
        ("json", "schema"),
        ("xml",  "schema", "form"),
    ]
)

The way to import is *always* from seamless.spyder import MySpyderModel
There is a Spyder import hook;
whenever there is a statement "from seamless.spyder import Bla",
  the dependencies of Bla and then Bla itself is being imported from Bla.spy
NOTE: whenever a Spyder type is updated, all of its dependencies are regenerated
 the old classes are marked as invalid:
 this is a class attribute against which certain methods check (__init__, validate)
 and an Exception is raised if they are used


TODO:
- eliminate string parsing, simplify File (only file and format, NOT_REQUIRED more modes)
- get rid of ObjectList
    Do make a little convenience function to load and save a Python list/dict of Spyder objects. No nesting.
- don't forget Resource and Array
- No more .fly
- __copydict__ with defaults:
    x = (0,0,0)
    if isinstance(_a, dict) and "x" in _a
  =>
    try:
        x = _a["x"]
    except ValueError:
        x = (0,0,0)
- set method
- numpy dtype:
    - available as .dtype() class method
    - int for Integer, bool for Boolean, etc.
      SpyderType.dtype() for SpyderType; numpy supports nested dtypes!
- fromnumpy constructor:
    Does not work on Spyder objects that contain Arrays, Files, Resources, or optional attributes
    Strings are expanded to 255 char arrays (like old Pascal).
        If x is a String attribute, 'self.x = "spam"'' is changed to self.x[:] = "spam" +  ('\0' * 255)[len("spam"):]
    On a single object:
    - Stores the argument to .fromnumpy as the inner numpy object
    - all attributes become now accessors/properties into the numpy object
    On Arrays (also ArrayArrays, ArrayArrayArrays):
    - fromnumpy determines length of numpy array, fromnumpy is then forwarded to every element
    - __setitem__ becomes overridden, changing a[0] = spam to a[0].set(spam)
    - __setslice__, same (is this necessary?)
    - append, pop becomes forbidden

    Any Spyder object constructed with .fromnumpy has a .numpy method to retrieve the inner numpy object
    Calling .numpy on a Spyder object NOT constructed with .fromnumpy is not possible
      However, there is a .tonumpy method, with two different behaviors:
        For Spyder objects constructed with .fromnumpy, .tonumpy is an alias of .numpy
        For other Spyder objects, a numpy array is constructed according to
            If the Spyder object is an Array (or ArrayArray etc.), the shape is determined using max(len(X)) for dimension

    In the future: storage {} blocks :
    - to support non-255 string storage
    - support Arrays, Files, Resources, optionals
    - make the Spyder model numpy-only; i.e. after standard construction, return self.type.fromnumpy(self.tonumpy())

"""
from . import typeparse, transform
from .validate import is_valid_silktype, reserved_endings, reserved_membernames, reserved_types
from .registers import register, unregister
from .registers.typenames import _silk_types

class _SilkTypes:
    def __getattr__(self, silkclass):
        return _silk_types[silkclass]
    def __dir__(self):
        return [k for k in _silk_types.keys() \
         if not k.endswith("Array")
         and not k.endswith("mixin")]
Silk = _SilkTypes()
