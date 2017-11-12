# Silk objects

A Silk object doesn't hold state itself. It is only a *wrapper* around:  
- an *data instance* (data object)
- an associated Silk schema
- a form dict that describes the form:
   The data instance is plain (list/dict), binary (Numpy), or a mix of the two.
   For more details, (see *form* below)

A Silk object provides protected access to the instance:
- Accessing a Silk object returns either a scalar or a Silk sub-object. This
sub-object is constructed on-the-fly, wrapping a sub-instance and a Silk sub-schema and a form sub-dict.
- Silk object provides and API that supports both .property and ["property"].
- Silk object provides an identical API no matter the form of the instance. For example, if the
Silk schema indicates an array of ints, and the instance is either [5,2,1] or np.array([5,2,1])
then silkobject[0] will return 5 (int).
- Assigning to a Silk object attribute will check that the modified instance validates against
  the Silk schema. Typically, the first attribute assignment will modify the Silk schema too (type inference).
- Note that a data instance may only ever contain plain and binary data.
  Assigning an arbitrary Python object to a under-defined schema (i.e. an object schema without any properties)
  will do a recursive isinstance(obj, (np.ndarray, dict, list, tuple, <scalar>) ) check, building the form dict
  in the process. Moreover, dicts, lists and unhashable tuples will be deep-copied (after recursion).
  Numpy arrays and hashable tuples (after recursion) will simply be assigned to the data (sub-)instance.
  Numpy arrays will be recursed if their dtype contains Python objects.
- In a data instance, hashable tuples will be converted to lists upon (i.e. right before) modification.
- You can always get access to the raw data (plain, binary or mixed). Obviously, this allows you to create invalid
  (non-schema-validating) data instances, so you may want to backup (deep-copy) your data instance first.
  However, it is guaranteed that raw data access is the *only* way to create invalid instances (assuming the schema
    remains constant).
- Numpy form and raw binary form may not exactly be the same. For example, for a vararray in binary form
  of length 2 and space 5, the raw binary form would be binary-encoded {"data": np.array([1,2,0,0,0]) "length": 2}
  whereas the numpy form would be np.array([1,2]), with the same underlying memory pointer as "data" but a different shape.

In very advanced future versions of Silk, it will be possible to bootstrap the Silk object API itself using Silk.
i.e. the entire Silk object method API is just another Python text cell that is live-interpreted.

# Silk schemas

Silk schemas are a superset of JSON schema. A schema that validates against
a Silk schema will always validate against JSON schema too, if in plain form,
and if converted as below.

NO SUPPORT FOR "default", THIS IS NOT PART OF SILK SCHEMA!

Seamless will implement its own $ref resolver for $refs that start with
SEAMLESS. These are provided by the central schema register
These can be used for both full-blown schemas AND new basic types
(still refer to them using $ref instead of using {"type": ...} )

Conversion to JSON schema:
- SEAMLESS $refs are re-written
- Silk schema "constructs" are replaced with their plain-form-generated schema
- Python validators are preserved, although JSON schema implementations won't know what to do with them.

# extra schema fields
On top of JSON schema
(1) indicates object-only, (2) indicates array-only

## not_required (2)
It is possible to explicitly annotate properties as not_required.
In a later version of Silk, there will be an annoying Microsoft-Office-paperclip
assistant who will ask all kind of annoying questions

## order (2)
Tells the order of properties, which helps in building \*args constructors.

## storage
Note: in addition to being normative (schema) values,
these are also descriptive (actual) values that are carried by Silk
for each instance. As a simple value, the schema describes the
required value.
Full-blown schematics (e.g. anyOf) should also be supported.

### form
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

### /(note on *form*)

### dtype (only for scalars)
If form is binary, defines binary data type: float32, int32, uint8, etc.
Must match with "type": float32 for number, uint8 for integer, etc.

### gpu
Dict of storage parameters on the GPU.
Examples:
- OpenGL vertex buffer
- N-dimensional OpenGL texture
- OpenCL, CUDA
- Pointer to the GPU data (carried by Silk)

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
What to do with extra properties/items when plain is converted to binary
- Error
- Silently discard them
- Incorporate them in the dtype.
  For object: as additional Python object fields.
  For array: change the dtype to "object" (if not already) and add them as extra Python object counts
  In any case, this invalidates Cython/C headers generated from the schema)
Default: Error

### infer_property (2)
If a new property is accessed via Silk, an (empty) schema for that property is inserted under "properties"
If False, the returned Silk object will be schema-less (and policy-less)
For arrays, this has no meaning by itself, but still can be provided to govern the behavior of items
Default: True

### infer_item (1)
What happens if a new item is assigned:
"uniform": all items have the same schema. For the first item, an empty schema is created when it is first accessed via Silk.
"pluriform": all items have their own schema.  For each item, an empty schema is created when it is first accessed via Silk.
False: If a new item is accessed via Silk, the returned Silk object will be schema-less (and policy-less)
Default: uniform

### infer_type
Silk will replace a "any" or absent "type" value with the type of the first assigned value
Default: True

### infer_dtype
Whenever an instance enters binary form (but not mixed-binary form),
the dtype is assigned based on the current value.
Instance must be a standalone scalar (parent is an object) or an array's scalar base instance
(item [0] in a single-schema items list)
Default: False

### infer_dtype_mixed
Same as above, but also for mixed-binary
Default: False

### force_valid_schema
Disallow manipulations of the schema that create an invalid schema, or that invalidate the data. If this happens,
the schema is error-buffered, if schema error buffering is enabled.
If force_valid_schema is disabled:
   If the schema is invalid, raise an exception.
   Else, the data is set to invalid, and schema violations are stored in the error log.
If there is neither an error log nor error buffering, force_valid_schema has no effect:
  an exception is raised, no matter what.
Default: True

### error_buffer (2)
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
Error-buffer all manipulations of the schema properties (see above).

## error_log
Errors (data-schema mismatches) are logged, rather than raising exceptions immediately.
Stack traces, exceptions and whatnot are stored in the error log.
In Silk, error logs are observable, both for appends and for clear events.
(error log can be cleared by API)
Default: True

### infer_contents
New properties/items can be auto-created via Silk access
Default: True

### walk_tree
Arrays and objects are always tree structures. If a value is assigned to the array or object, walk the entire tree
of the assigned value and add a schema for each item.
Default: False

### binary_validation
If False:
  all schema validation is skipped, also for the children, if the instance is in binary form.
Default: True ( => not skipped)

### schema_undo_buffer
Allows you to undo schema manipulations (automatic and manual) that you didn't want to happen.
Works similar to the schema error buffer.
To-be-determined on what level the undo buffer will be stored (globally?), and the atomicity.

# Validators
Array of strings containing Python code. Each of them will be executed as an
eval'ed function.

Alternative (seamless world):
Array of "SEAMLESS:text.code.pythoncode". Each of them will be executed in a
transformer.

In any case, in its local namespace, the validator gets access to the object
in Silk form as "self", and to all properties as variables (same as for Spyder).
(Special case for construct validators: they get access to the construct instance descriptor instead)


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

## extra fields:

### dtype
computed from/to base_item.dtype

### shape
A list of items that are one of the following:
- None
- A single positive integer value
- A pair of (inclusive) lower-bound - upper-bound positive integer values
The length of the list must match with "ndim", if defined

### ndim
The array must have ndim dimensions. Must match with "shape", if defined.

### base
Schema of the scalar base item.
Base may be undefined, in which case the scalar base item is simply a Python
object.

### c_contiguous
If form is binary, array must be c_contiguous
Default: False

### f_contiguous
If form is binary, array must be f_contiguous
Default: False

### validators
Construct validators for the shapedarray construct.
The shapedarray construct instance descriptor contains:
   .shape, .ndim, .dtype, .type (mapped from .dtype)
    .c_contiguous, .f_contiguous;
    in case of a Numpy array / Python buffer: .strides and some flags.

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
ndims, but not shape, is known in advance (and the base item is fixed-binary).
They will then be exposed to C as a pointer + *shape object* (similar to memoryview)

However, this complicates the use of C code in a transformer.
No problem if such a non-fixed shapearray is just an input (or editpin).
But if it is an *output*, then the memory must be pre-allocated by Python, which
is not trivial for non-fixed-binary schemas. In that case, the schema must contain
a *shape computer* (or multiple ones). A shape computer receives the data and the
shape objects of the inputs, and the partial shape objects of the output. After all shape
computers have run, the output shape objects must be complete.
(Alternatively, in Seamless, since schemas are themselves cells,
you can directly connect them using a transformer. This will make the output fixed-binary
(no shape object, just fixed-size C arrays), and will re-generate the C header every time
the shape changes.
