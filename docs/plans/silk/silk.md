# Silk objects

A Silk object doesn't hold state itself. It is only a *wrapper* around:  
- an *data instance* (data object)
- an associated Silk schema
- Optionally, a form dict that describes the form:
   The data instance is plain (list/dict), binary (Numpy), or a mix of the two.
   For more details, (see *form* below)

A Silk object provides protected access to the instance:
- Accessing a Silk object returns either a scalar or a Silk sub-object. This
sub-object is constructed on-the-fly, wrapping a sub-instance and a Silk sub-schema and a form sub-dict.
- Silk object provides and API that supports both .property and ["property"].
- Silk object provides an identical API no matter the form of the instance. For example, if the
Silk schema indicates an array of ints, and the instance is either [5,2,1] or np.array([5,2,1])
then silkobject[0] will return 5 (int). (UPDATE: Now 5 will always be wrapped in Silk...)
- Assigning to a Silk object attribute will check that the modified instance validates against
  the Silk schema. Typically, the first attribute assignment will modify the Silk schema too (type inference).
- Note that a data instance may only ever contain plain and binary data.
  Assigning an arbitrary Python object to a under-defined schema (i.e. an object schema without any properties)
  will do a recursive isinstance(obj, (np.ndarray, dict, list, tuple, <scalar>) ) check, building the form dict
  in the process. Moreover, dicts, lists and unhashable tuples will be deep-copied (after recursion).
  Numpy arrays and hashable tuples (after recursion) will simply be assigned to the data (sub-)instance.
  Numpy arrays will be recursed if their dtype contains Python objects.
  UPDATE: scrap the form dict
- In a data instance, hashable tuples will be converted to lists upon (i.e. right before) modification.
- You can always get access to the raw data (plain, binary or mixed). Obviously, this allows you to create invalid
  (non-schema-validating) data instances, so you may want to backup (deep-copy) your data instance first.
  UPDATE: use forks
  However, it is guaranteed that raw data access is the *only* way to create invalid instances (assuming the schema
    remains constant).
- Numpy form and raw binary form may not exactly be the same. For example, for a vararray in binary form
  of length 2 and space 5, the raw binary form would be binary-encoded {"data": np.array([1,2,0,0,0]) "length": 2}
  whereas the numpy form would be np.array([1,2]), with the same underlying memory pointer as "data" but a different shape.
  UPDATE: now they *are* the same. Use constructs to manage vararrays etc.

In very advanced future versions of Silk, it will be possible to bootstrap the Silk object API itself using Silk.
i.e. the entire Silk object method API is just another Python text cell that is live-interpreted.
UPDATE: This is already possible, except for __get/setitem__ , __get/setattr__. This can be tackled with construct registration.

# Silk schemas

Silk schemas are a superset of JSON schema. A schema that validates against
a Silk schema will always validate against JSON schema too, if in plain form,
and if converted as below.

NO SUPPORT FOR "default", THIS IS NOT PART OF SILK SCHEMA!
UPDATE: Silk.constructor (TODO) will generate a constructor based on a schema, including
"default" and "order"

Seamless will implement its own $ref resolver for $refs that start with
SEAMLESS. These are provided by the central schema registry
These can be used for both full-blown schemas AND new basic types
(still refer to them using $ref instead of using {"type": ...} )
UPDATE: Every Silk class has its own schema registry.
For Seamless StructuredCells, add a facility where schema cells can be injected

Conversion to JSON schema:
- SEAMLESS $refs are re-written
- Silk schema "constructs" are replaced with their plain-form-generated schema
- Python validators are preserved, although JSON schema implementations won't know what to do with them.

UPDATE:
- Now include methods as well as validators (each with "language" annotation)
- No formal "conversion" at all. Tools are of course free to convert/compile/transpile
  from one Silk schema into another. Also, a "purify" method to rip all Silk-specific entries
- Generic mechanism to resolve $ref (jsonschema library already has this?)

# extra schema fields
On top of JSON schema
(1) indicates array-only, (2) indicates object-only
For other schemas, (1) or (2) have no meaning by itself, but still can be provided to govern the behavior of children (by policy inheritance).
In a later version of Silk, there will be an annoying Microsoft-Office-paperclip
assistant who will ask all kind of annoying questions

## order (2)
Tells the order of properties, which helps in building \*args constructors (as does "default").
Necessary for binary storage (the order of fields)

## storage
Note: in addition to being normative (schema) values,
these are also descriptive (actual) values that are carried by Silk
for each instance. As a simple value, the schema describes the
required value.
Full-blown schematics (e.g. anyOf) should also be supported.
UPDATE: for now, descriptive values are not carried but re-computed on demand
(possibly with some kind of caching)

### form
Forms are only used if the data is an instance of SilkHasForm.
In that case, data.\_get_silk_form() is invoked on the data,
 and the Silk form_validator is invoked on the form, validated against the schema
The only known subclass of SilkHasForm is the Seamless Mixed class.

"plain": instance must be stored as a list, dictionary or plain scalar
"binary": instance is in binary form. This is a Numpy structured scalar for
objects, an Numpy array for arrays.
"any": no constraints on the form
Default: "any"

### (note on *form*)
The *actual* (carried) form of an instance is one of *four* values:
"pure-plain": plain, and does not contain binary (grand)children
"pure-binary": binary, and does not contain plain (grand)children
"mixed-plain": plain, but contains binary (grand)children
"mixed-binary":binary, but contains plain (grand)children
  (encoded as Python objects: see np.dtype.hasobject)

These *actual* forms exist only in the context of Silk wrapper instances,
not Silk-based schema validation.
Every Silk wrapper instance carries a descriptor of its own actual form
(serialized)
and a tuple of four counts, counting the number of forms for the children
(regenerated).

Pure plain instances can be serialized as JSON, pure binary instances as Numpy arrays
(or, in the case of objects, as singleton structured-array scalars).
Mixed instances need special serialization.
Only for fixed-binary schemas, C struct headers can be generated.
For all schemas, Cython classes/structs can be generated. For any schema that is
not fixed-binary (see below), a Python object is filled in.
  (NOTE: Nested arrays (not shapedarrays/vararrays) simply become 1D np.object arrays.
  Other fixed-length arrays of non-fixed-binary schemas are represented
  as (np.object, <length>) fields in the dtype;
  in Cython, this becomes a memoryview, for which size information
  is not as of yet supported)

UPDATE: do not store this on the instance, compute this at runtime, possibly cached
(same as methods)
UPDATE2: "mixed" classes take care of this now
FINAL UPDATE: "form" will contain constraints on the form!!


### /(note on *form*)

### dtype (only for scalars)
If form is binary, defines binary data type: float32, int32, uint8, etc.
Must match with "type": float32 for number, uint8 for integer, etc.
UPDATE: use "bytes" and "unsigned" instead!!

### gpu
Dict of storage parameters on the GPU.
Examples:
- OpenGL vertex buffer
- N-dimensional OpenGL texture
- OpenCL, CUDA
- Pointer to the GPU data (carried by Silk)
UPDATE:
Abandon. Make separate system for Numpy->OpenGL, Numpy->CUDA/OpenCL sync
The pointer should be enough to retrieve a GPU representation


## /storage


## validators
See below.

## policy

For each policy field that is absent, the parent schema is queried.
If there is no parent schema, it is looked up in the global Silk config.
(optimization: every Silk instance holds a ref to the nearest parent policy dict)
Default values are indicated for the Silk global config.

Every infer_XXX property has a corresponding set_XXX function in the Silk API,
 which does the inference retroactively based on the current value(s).
Every set_XXX has a "recursive" parameter.

### surplus_to_binary
UPDATE: ELIMINATE. Conversion to binary is out of scope of Silk
What to do with extra properties/items when plain is converted to binary
- Error
- Silently discard them
- Incorporate them in the dtype.
  For object: as additional Python object fields.
  For array: change the dtype to "object" (if not already) and add them as extra Python object counts
  In any case, this invalidates Cython/C headers generated from the schema)
Default: Error


### accept_missing_binary_optional
What to do with binary-form instances that lack one or more columns of optional properties
- True: accept them. This can be practical for backwards compatibility with an earlier schema where
  the optional property was lacking.
  However, this invalidates Cython/C headers generated from the schema.
  But note that most header generators cannot deal with optional properties anyway.
- False: raise an error.
Default: True

##infer_default
Every first assignment is assigned to "default".
Can be handy in class statements (class variables are faked by default variables )
Default: False
UPDATE: in the future, maybe lookup scope for default dict to save memory.

### infer_new_property (2)
If a new property is accessed via Silk, an schema for that property is inserted under "properties".
If False, the returned Silk object will be schema-less (and policy-less)
If True, a new schema may be created.
Created schemas have all other policies applied (infer_type etc.), except
 infer_array  and infer_object.
Default: True

### infer_object (2)
What happens if a non-empty dict or a Numpy struct is assigned to a new object schema.
If True, a schema will be created for each property.
Created schemas have all other policies applied (infer_type etc.), except
 infer_array  and infer_object.
Default: False

### infer_new_item (1)
What happens if a new item is assigned (e.g. via .append):
If False, the returned Silk object will be schema-less (and policy-less)
If True, a new schema may be created.
This depends if the existing array schema is uniform ("items" holds a single schema) or pluriform ("items" is empty or holds an array of schemas).
A new schema is only created for pluriform arrays.
Created schemas have all other policies applied (infer_type etc.), except
 infer_array and infer_object.
Default: True


### infer_array (1)
What happens if a non-empty list or a Numpy array is assigned to a new array schema.
The result will be an array schema that is empty, uniform ("items" holds a single schema) or pluriform ("items" holds an array of schemas).
"pluriform": A schema will be created for each item.
"auto": A schema will be created for the first item. If any item does
 not validate against that schema, the schema becomes pluriform,
 else uniform.
False: No "items" schema will be created at all.
Created schemas have all other policies applied (infer_type etc.), except
 infer_array and infer_object.
For Numpy arrays, the bytesize may also be inferred, if infer_storage is defined.
Default: "auto"

### infer_type
Silk will replace a "any" or absent "type" value with the type of the first assigned value
Lists and dicts are not recursively inferred, but simply set to "object" / "array"
When assigned to a Silk type, the schema is copied.
Default: True

### infer_storage
For any instance, infer its storage as a form constraint.
Storage is inferred as "plain" or "binary"; "pure-" and "mixed-" must be
 added manually.
If the instance is binary, infer its bytesize as well.
Default: True
UPDATE: this is stored in a "storage" attribute.
For children, it can also be stored in schema["form"]["storage"][child]

### infer_ndim
Whenever a binary array is assigned, the instance is inferred to be a shapedarray, fixing ndim.
Default: True

### infer_strides
Whenever a binary array is assigned, the strides/contiguous property is fixed.
Default: False

### infer_required (2)
A new inferred property is automatically added to the required properties
Default: False

### force_valid_schema
UPDATE: this is too complicated. Instead, use "with fork: ..." . /UPDATE
When a fork is created, the data (and schema?) are copied
While a Silk object is forked, validation is off
When the fork ends, the fork is validated.
If successful, the fork state becomes the main state
A Silk object can be forked multiple times
/UPDATE
Disallow manipulations of the schema that create an invalid schema, or that invalidate the data. If this happens,
the schema is error-buffered, if schema error buffering is enabled.
If force_valid_schema is disabled:
   If the schema is invalid, raise an exception.
   Else, the data is set to invalid, and schema violations are stored in the error log.
If there is neither an error log nor error buffering, force_valid_schema has no effect:
  an exception is raised, no matter what.
Default: True

### error_buffer (2)
UPDATE: this is too complicated. Use a fork instead. /UPDATE
Error-buffer the data.
Only works in plain form, disabled in binary form. Conversion to binary form will raise an exception if there is anything
in the error buffer.
Only works for "object" schemas. For other schemas, has no effect but can be used to control child behavior.
(error buffer can be cleared by API)
Any manipulation that is valid for the individual properties, but not for the instance as a whole,
is stored in a "diff" dict. What actually happens is as follows:
- After the individual property schemas have been successfully validated, a shallow copy of the old instance value is made
- The shallow copy is updated with the old "diff" dict (if any)
- The shallow copy is updated with the value of the newly manipulated property
- The shallow copy is validated.
  On success: the shallow copy replaces the instance value, and the "diff" dict (if any) is deleted.
  On failure: the old instance value is kept, and the newly manipulated property is added to the "diff" dict
In Silk, the (wrapper of the) manipulated property has access to its "raw value" from the "diff" dict.
If not enabled, an exception will be raised for illegal data manipulations
Default: True

### error_buffer_schema
UPDATE: this is too complicated. Use a fork instead. /UPDATE
Error-buffer all manipulations of the schema properties (see above).

## error_log
UPDATE: no longer needed
Errors (data-schema mismatches) are logged, rather than raising exceptions immediately.
Stack traces, exceptions and whatnot are stored in the error log.
Error logs are observable, both for appends and for clear events.
(error log can be cleared by API)
Default: False

### infer_recursive
Arrays and objects are tree structures. If a value is assigned to the array or object, walk the entire tree of the assigned value and add a schema for each item. This is done for arrays if "infer_array" is true, and for objects if
"infer_object" is true.
Default: False

### binary_validation
If False:
  all schema validation is skipped, also for the children, if the instance is in binary form.
Default: True ( => not skipped)

### schema_undo_buffer
UPDATE: this is too complicated. Use a fork instead. /UPDATE
Allows you to undo schema manipulations (automatic and manual) that you didn't want to happen.
Works similar to the schema error buffer.
To-be-determined on what level the undo buffer will be stored (globally?), and the atomicity.

### wrap_scalar
If False:
  If a property or item is a scalar, Silk returns the naked scalar, not the Silk-wrapped scalar
Default: False (scalars are not wrapped)

# Validators
Array of strings containing Python code. Each of them will be executed as an
eval'ed function.

Alternative (seamless world):
Array of "SEAMLESS:text.code.pythoncode". Each of them will be executed in a
transformer.

In any case, in its local namespace, the validator gets access to the object
in Silk form as "self", and to all properties as variables (same as for Spyder).
(Special case for construct validators: they get access to the construct instance descriptor instead)
UPDATE: just access to self.

# Fixed-binary schemas

Any instance can be converted to mixed-binary form. Many instances can be converted
to a pure-binary form as well: it is just that typically, the dtype/size in memory will depend
on the contents of the data.
A fixed-binary schema is a schema for which it is guaranteed that a pure-binary
form exists (no Python objects) and always has the same dtype/size in memory.
Only for fixed-binary schemas,
C struct headers can be generated. It is guaranteed
that the pure-binary form matches these struct headers.
(For binary conversion, Silk will generate Numpy dtypes with align=True).

Fixed-binary schemas are:
- non-string scalar schemas
- string schemas that have an upper length.
- object schemas whose properties are all fixed-binary
- array schemas with a fixed length and containing a single schema, which is
  itself a non-array fixed-binary schema.
- construct schemas that declare themselves fixed-binary  
This means that nested array schemas (not shapedarrays/vararrays)
are *never* fixed-binary schemas.
shapedarrays and vararrays can easily be fixed-binary, though.


# Constructs

Constructs are schemas where:
  "type" : "construct"
  "construct": <one of the registered constructs>

For Silk schema validation, every construct must register four functions:
1. From the "construct" schema dict, generate a schema for plain instances,
and another for binary/mixed-binary instances. If the construct schema is overall
invalid, this must be reported here (return None / exceptions).
2. From the instance, generate a construct instance descriptor.
This construct instance descriptor is validated using construct validators.
3. A function that returns if the binary schema is a pure-binary schema or not.
4. A function to do type inference. Returns if the received value is suitable.
(some priority must be established here)

Note that a construct defines *extra* fields: the functions have access to all
other schema fields.

For Silk wrapping, a construct must also define the following:
1. A construct API is defined to manipulate instances of the construct.
For example, the shape construct API contains .append(), which does very different things
for plain or binary form instances.
2. A top-level converter between plain and binary form.
UPDATE: the API is defined in the usual way (method section). Drop the converter.

Normally, constructs also have a specialized generation routines for C struct headers
and Cython class headers generation.

# shapedarray construct
The shape construct is a straightforward construct around an N-dimensional Numpy array
or an equivalent nested-list plain representation. The Numpy array is space-efficient,
but not easy to grow or shrink.

The shapedarray type inferencer accepts Numpy arrays and suitable nested-lists.
(=> {"type":  "construct", "construct": "shapedarray"})
It has a lower priority than the generic "array" type inferencer => {"type": "array"},
which accepts one-dimensional Numpy arrays and normal lists.
UPDATE: or a higher priority? policy option...



### validators
Construct validators for the shapedarray construct.
The shapedarray construct instance descriptor contains:
   .shape, .ndim, .dtype, .type (mapped from .dtype)
    .c_contiguous, .f_contiguous;
    in case of a Numpy array / Python buffer: .strides and some flags.
UPDATE: if the construct API is just added on top of the normal API, then there is no
need for a special validator category.

## /extra items

## policies

### infer_shape (1)
Whenever a Numpy array is assigned to an array, its shape parameters are imprinted on the array schema.
The imprinting is done *after* the array is validated against the existing schema: so if there was already a shape,
re-imprinting is likely to fail.
For non-shapedarrays, this has no meaning by itself, but still can be provided to govern the behavior of children.
Default: False

### re_infer_shape (1)
Same as above, but existing shape-constraint schema parameters are first removed. This is useful if e.g. OpenCL/CUDA code needs to
be regenerated whenever the array shape changes.
Shape validators are not removed, so constraints on the shape can be encoded there.
Default: False

## /policies

shaped array schemas are pure-binary schemas if they are both *fully-shaped* (fixed-length in all dimensions)
and whose base item is a pure-binary schema

# /shapedarray construct


# vararray construct
Construct that simulates a N-dimensional variable-length numpy array
using a fixed-length 1D "store" array. Offsets and sizes of each subarray
(or, in case of a 1D array, just the size of array itself) are stored. In case
of a simulated shape=(10,20,X) array, there are 200 subarray lengths,
and  the number of offsets is 201: the first offset
is 0, the last one is the length of the 1D store. Available space for each [x,y]
subarray can be computed as offset[(x,y) + 1] - offset[(x,y)] - length[(x,y)]
Accessing a subarray returns a wrapper around a Numpy array between the offsets.
Data access is restricted to :length[(x,y)], and asking for the raw Numpy array
also returns a Numpy array around store[offset[(x,y)]: offset[(x,y)] + length[(x,y)]]
API supports .append() etc. which is rather efficient as long as there is there is space.
Policy options to define the initial amount of space upon initialization/to-binary conversion,
 and what happens if there is an append() and no space.

Multiple variable-length dimensions are also possible: shape(10, X, Y), but lengths
must be stored independently per dimension (the X'es and the Y's).
.append() to the second dimension (increasing one of the 10 X'es) is again rather
efficient, but it must be policy'ed how much space a newly created Y receives.

vararray schemas are pure-binary schemas as long as the base scalar item is a
pure-binary schema.

# tree construct
The tree consists of nodes and leaves. Nodes contain other nodes, and leaves.
Nodes are stored as a vararray of indices, where every index stands for a node or for a leaf,
depending on its value (i.e. negative is node, positive is leaf).
Leaves are stored as a 1D array, into which the nodes index.
Policy: store the parent node index for every node (or 0 for the top node).

tree schemas are pure-binary schemas as long as the node schema is a
pure-binary schema.

# other possible constructs
(typed) sets, (typed) maps/hash tables, linked lists, ...
"Internal" lookup-accelerating structures etc. can be stored as well, by policy,
 as long as they use indices and not raw pointers.


# C headers, revisited

Written above is that C-headers can only be generated for fixed-binary schemas.
This is not actually true. C headers can also be generated for shapedarrays if
ndim, but not shape, is known in advance (and the base item is fixed-binary).
They will then be exposed to C as a pointer + *shape object* (similar to memoryview)

However, this complicates the use of C code in a transformer.
No problem if such a non-fixed shapearray is just an input (or editpin).
But if it is an *output*, then the memory must be pre-allocated by Python, which
is not trivial for non-fixed-binary schemas. In that case, the schema must contain
a *shape computer* (or multiple ones). A shape computer receives the data and the
shape objects of the inputs, and the partial shape objects of the output. After all shape
computers have run, the output shape objects must be complete.
Alternatively, in Seamless, since schemas are themselves cells,
you can directly connect them using a transformer. This will make the output fixed-binary
(no shape object, just fixed-size C arrays), and will re-generate the C header every time
the shape changes.
UPDATE: after some deliberation: cancel the shape computers, use transformers! However,
because of timing effects, the computing of the output schema must be well-integrated
in the transformer, because it must be complete before the computation starts
=> transformer under macro control by the schema (which it already should be, so no problem!)

# UPDATE: object-oriented programming

Silk structures are perfectly usable for traditional object-oriented programming.
Everything is stored in the .data struct, and you have to use fork() and/or
 program by example, but the end result is pretty much the same. You can even use
 class-statement syntax if using a Silk-based metaclass (see test-meta.py)

What is obviously missing is a constructor. What can be built is a universal
constructor factory, that takes a Silk schema and returns a constructor. The
constructor will be usable in the same way as the old Spyder constructors, i.e.
they accept keyword/value, list, and copy (both naked dict and Silk-wrapped).
Specialized versions are available as constructor attributes:

Example:
schema = {"properties": "a": {"type": "integer"}, "b": {"type": "integer"}, "order" : ["a", "b"]}
constructor = constructor_factory(schema)
instance = constructor(1,b=2)
instance = constructor([1,2]) #requires "order" in schema
data = {"a": 1, "b": 2}
s = Silk(data=data, schema=schema)
instance = constructor(data)
instance = constructor(s)
instance = constructor.fromvalues(1,b=2)
instance = constructor.fromlist([1,2])
instance = constructor.fromdict(data)
instance = constructor.fromcopy(s)

*NOTE*: "default" entries in the schema will be honored by the constructor.

As before (in Spyder), schemas can be degenerate, therefore it is recommended to use the
specialized .fromXXX sub-constructors.

In all cases, the constructor returns a naked dict that conforms to the schema.
However, no kind of validation is performed by the constructor!
The dict can be wrapped trivially in a Silk instance, which will perform validation.

UPDATE: Silk instances are now callable. If data is None, this invokes the __init__
method, else the __call__ method.

UPDATE: traditional class syntax is supported via metaclass. The metaclass builds
the Silk schema after the class statement has finished, not during (would be too clever).
Silk class decorators are probably not a good idea (inheritance would never work!).
