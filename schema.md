!!! SOMEWHAT OUTDATED !!!

the schema is accessible as cell.self.schema
all dicts inside schemas are wrapped in dot notation. At any level, .self gains access to the underlying dict methods

"object" and "array" have their JS meaning, i.e. they are "dict" and "list".
However, array may have a single schema that applies to all of its items (making it more like a Numpy array).
Note that all schema dicts are unordered, an "order" parameter may indicate order.
properties not in "order" are keyword-only in classes.

"number" means "float", "integer" means "int", "string" means "str", "boolean" means "bool"
The Python versions (texts, raw types) are also accepted in the .self.schema API. (test for equality also)

## JSON schema extensions
representation: "plain", "binary" (Numpy), "mixed".
shape: for array. shape is itself an array, each item being an integer or None.
dtype: for array. Any basic Numpy scalar.
gpu: replaces set_store
validators: list of Python texts.


!!! VERY OUTDATED !!!

Everything is a (sub)cell or a pin! (these are rather isomorphic)
Every subcell/outputpin can be assigned to a variable (which is copied, except for numpy arrays)
or to a cell (which creates automatically a listener: no macros needed!)
In BOTH cases, the schema is updated! This is not automatically undone!
Assign the subcell to seamless.nocell to update the schema as well.
By default, created subcells are added as required properties, but this can be changed to non-required.
Similarly, "array"

cell.value is an alias for cell.self.value. Similar for "get()" and .silk.
.silk provides a Silk wrapper around a cell's value.


Three worker classes, similar in form: transformer, reactor, macro.
Transformer and reactor are no longer macros.
Instead, worker.a automatically creates an outputpin (weakref),
which can be assigned to with cell = worker.a (which causes outputpin to be
  hard-referenced by the worker, because the worker's schema gets modified).
assignment, which is "worker.a = cell", creates an inputpin.
worker.a.self.mode = "edit" changes it into an edit pin.

Macros now always build a context.

```
ctx.value = 5
```

expands to:
```
ctx.value = cell()         #  ctx.value.self.schema = None;
                           #  None is shorthand for {"type": None}
ctx.value.schema = "int"   #  isinstance(5, int)
ctx.value.set(5)           #  ctx.value.self.schema.type = "int"
```

print(ctx.value) will still print out .value:
 use print(ctx.value.get()) or print(ctx.value.value)

subsequent "ctx.value = 'bla' " or ctx.value.set('bla') will give an error,
unless ctx.self.schema.type is set to "str" or "text"


```
ctx.composite = cell()
ctx.composite.a = ctx.value
```

expands to:
```
ctx.composite = cell()   # ctx.composite.schema = None
ctx.composite.a = subcell()
ctx.composite.a.rconnect(ctx.value) # (1)
ctx.composite.a.schema.type = "int"
ctx.composite.self.mode = "slave"    # (2)
```

where (1) expands to:
```
ctx.composite.a = subcell(ctx.value)
ctx.composite.a.schema = None
ctx.composite.schema = """{
  "type": "object",
  "properties": {
    a": {"type": None, "required": True}
  }
}"""
```

(2)
If an object/array cell is in "slave" mode, then its property subcells are derived from
cells (rconnect). The cells hold the authoritative representations for property values
and property schemas. The object cell's schema does hold
a full copy of the schema state (assignments to the property schemas are forwarded to the
cells, which may then become invalid), and it is authoritative for the schema
above the property level.

A cell in "slave" mode can only be connected to an input pin, not an output pin or edit pin.
Array cells can only be in "master" mode if their length is fixed (or can become fixed).

If an object cell or array cell is in "master" mode, itself holds the authoritative representations,
and cell.a is merely a subcell.
A object/array cell in "master" mode can only be connected to an output pin, not to an input pin or edit pin

```
ctx.bla = {"var": 20 }   #  ctx.bla.self.schema = {"type": "dict"}
ctx.var = ctx.bla.var      #  only now, an entry "var" in ctx.bla.self.schema is created, based on its current value
#  Alternatively, you can modify ctx.bla.self.schema.var yourself (which causes a re-validation)
ctx.tf = transformer()
ctx.tf.code = "print('Hello world!')"
ctx.bla = ctx.tf
# Connects them. If ctx.bla does not exist => ValueError
# If you want to rename ctx.tf instead, you need to do:
# del ctx.bla
# tf = ctx.tf
# ctx.tf.self.rename("bla")
# ctx.tf #AttributeError
# ctx.bla is tf # True
#
# ctx.tf is now in error, because the code must return something
ctx.tf.code = "return None" # ctx.tf is now in TypeError
ctx.tf.code = "return {}" # ctx.tf is now in ValidationError (missing "var")
ctx.tf.code = "return {'var': 30}" # Correct
print(ctx.var) # 30
ctx.var0 = 5
ctx.tf.var0 = ctx.var0
ctx.tf.code = "return {'var': 20 * var0}"
print(ctx.var0) # 100
ctx.var0 = ctx.var0.value * 2 # No syntactic sugar around this
print(ctx.var0) # 200

```

## Registers
Only one central register: the schema registrar. Source code (python/IPython/C)
is injected directly:

```
ctx.func = cell(("text", "code", "python"))
ctx.func = "def myfunc(): return 42"
ctx.tf.register.func = ctx.func
ctx.tf.code = "return {'var': 20 * var0 + func.myfunc()}"
```
