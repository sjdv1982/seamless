# Compiled Transformer And Transformation Celltypes - Design And Implementation Plan

## Purpose

Give compiled transformers a typed Seamless boundary that is jointly defined by:

1. the compiled signature schema;
2. the celltype declared for each transformer pin;
3. for a pin declared `mixed`, a deliberately restricted set of natural mixed values.

The present implementation records every compiled input in the concrete transformation as
`mixed`, even when the transformer has a schema and the user declared a more conservative
pin celltype. That erases the pin boundary, bypasses ordinary conversion and null checks, and
allows invalid values to fail only during native argument marshalling.

This plan changes both layers:

- **Compiled transformers**: the mutable builder/API, schema mutation, declared pin
  celltypes, workflow snapshots and standalone calls.
- **Compiled transformations**: the immutable pin tuples and checksums, dependency
  resolution, pre-hash validation, and native execution.

The plan concerns compiled **input** pins. Result celltypes and the packaging of multiple
compiled outputs are related but separate; see [Out Of Scope](#out-of-scope).

Normative background:

- [Foundation: The C ABI Contract](#foundation-the-c-abi-contract), below, is the contract
  this plan builds on. Where the current code disagrees with it, the code is fixed.
- [`docs/agent/contracts/compiled-transformers.md`](docs/agent/contracts/compiled-transformers.md)
  and [`docs/agent/contracts/seamless-signature-schema.md`](docs/agent/contracts/seamless-signature-schema.md)
  define the schema, the generated C header, and transformation identity for compiled
  transformers.
- [`docs/agent/contracts/celltypes-and-conversion.md`](docs/agent/contracts/celltypes-and-conversion.md)
  defines celltype serialization, readings, null, checksum identity, and Expression
  conversion.
- [`cells-and-expressions-known-issues.md`](cells-and-expressions-known-issues.md), section
  4, records the current compiled-input `mixed` behavior and late-null failure. Traced on the
  current code: a required scalar input given null fails inside the CFFI call
  (`TypeError: an integer is required`) after compilation, also when the pin is declared
  `int`, because the declaration is discarded. A connected optional input that resolves to
  null is dropped, and the call then fails with `KeyError` after compilation.

## Foundation: The C ABI Contract

Compiled transformers are defined by a C API/ABI. The rules below are the contract this plan
builds on. Where the code disagrees (see [Current Code Anchors](#current-code-anchors)), the
code is fixed.

**Terminology.** Throughout this plan, `char` is the seamless-signature schema dtype, never
a C type. The C type generated for it is `unsigned char` (rule 6). Where a C type is meant,
the plan says so explicitly: "the C type `unsigned char`", or "plain C `char`".

1. **The schema is the only source of the ABI.** `seamless-signature` generates the C header
   (`tf.header`) from the schema alone. CFFI builds the extension module from that header, and
   the Python call signature and all marshalling rules derive from the same schema.
   `__schema__` is part of transformation identity; `__header__` is derived from it and
   excluded. A rule that changes how an input is marshalled therefore belongs in the schema,
   not in builder state.
2. **No header, no transformer.** Until a C header can be generated, the transformer is
   blocked, whatever the input data. Every other check that needs no input data blocks it in
   the same way; see [Two Validation Stages](#two-validation-stages).
3. **Every schema input is a positional C argument.** `transform()` has a fixed arity:
   scalars are passed by value; arrays and character buffers are passed as `const T *`, with
   the input wildcard dimensions as leading `unsigned int` arguments. C has no absent
   argument, so **optional pins are not supported** on compiled transformers. An optional-pin
   declaration on a compiled input is rejected; it is never translated into "drop the pin".
4. **C has no None.** A compiled input whose value reads as None under its declared pin
   celltype is rejected, whatever that celltype is, `mixed` included. Detection is by
   reading, not by checksum equality: the canonical null `null\n`, the non-canonical buffer
   `null`, and, under `mixed`, whitespace-padded JSON null all read as None.

   `bytes` is not an exception to this rule. Under `bytes` the null checksum reads as `b""`,
   which is how Seamless stores empty bytes. An empty `bytes` value is passed as length 0 with
   a valid, non-NULL pointer, never as a NULL pointer: Rust's `slice::from_raw_parts` requires
   a non-null pointer even for length 0, `memcpy(dst, NULL, 0)` is undefined behaviour in C
   before C2y, and an empty array passed through the `binary` path already arrives as a
   non-NULL pointer. Length 0 is only valid where the header takes a pointer and a wildcard
   length. For a scalar `char` or a fixed-size character array it is a schema refinement
   error.

   The flip side is that, under `bytes`, real content can read as empty:

   - Content exactly `null\n` has the null checksum. Its checksum and buffer are identical
     to those of empty bytes, so no check anywhere, the executor included, can tell them
     apart, and it reaches the kernel as length 0. This is inherent to the canonical null
     and is documented for `bytes` pins.
   - The non-canonical null checksum (content `null`, no trailing newline) is never produced
     by empty bytes: the serializer writes `null\n`, and canonicalization maps `sha256(b"")`
     to the canonical null. The current parser nevertheless reads it as `b""` under `bytes`.
     Its origin is ambiguous: real 4-byte content, or a non-canonical JSON null that crossed
     a trivial `plain → bytes` conversion unchanged (the Expression null short-circuit tests
     only `is_null`). No reading is right for both origins, so a `bytes` pin **rejects** it
     with a targeted error. The test is checksum-level (`is_null_value` and not `is_null`)
     and needs no buffer. How seamless-core reads this checksum is out of scope here.

   Under `text`, the string `null` collides in the same way. It serializes to `null\n`, the
   canonical null, which `text` reads as None, so a `text` pin rejects it and no check can
   tell it apart from a real null. This is documented for `text` pins. The empty string is
   not affected: it is stored as `\n`, reads as `""`, and is passed as length 0 with a
   non-NULL pointer where the schema admits length 0.

   A `binary` character array (NumPy `S1`) has neither problem and is the choice when the
   content is arbitrary.
5. **NaN and infinity are NumPy values.** JSON cannot hold them. `float` is a checksum-level
   subtype of `plain`, which is handled by orjson, so serializing NaN or infinity under
   `plain` or `float` raises. Under `mixed`, NaN or infinity is serialized as NumPy data: a
   zero-dimensional `.npy` at the top level, or a NumPy value inside JSON when it sits in a
   dict or list. In every case it reads back as `np.float64(nan)` (or `np.float64(inf)`).
   It therefore reaches a compiled transformer only as a zero-dimensional `binary` scalar,
   which a floating-point parameter admits whatever its precision (see
   [Native Scalar Rules](#native-scalar-rules)). This requires changes in seamless-core; see
   [Prerequisites In seamless-core](#prerequisites-in-seamless-core).
6. **A schema `char` is an unsigned byte, passed without a terminator.**
   - The generated header declares every schema `char` as the C type `unsigned char`:
     scalars, array element types, and struct fields. Whether plain C `char` is signed is
     implementation-defined: it is signed on x86-64 and unsigned on AArch64 Linux. With plain
     C `char`, a byte of 0x80 or above would compare and widen differently per platform,
     while the transformation checksum stays the same. Kernels declare the C type
     `unsigned char` (Rust `u8`) to match.
   - A character array is passed as a pointer to its bytes and its length: the input
     wildcard, or the fixed size. No NUL terminator is added, so no copy is needed, and the
     pointer may point directly into the input buffer. The length is authoritative. Bytes at
     and beyond it are not part of the input, and reading them is undefined behaviour; under
     `text`, for example, the next byte is usually the newline that serialization appends.
     NUL bytes inside the data are ordinary data.
   - Which bytes each declared pin celltype delivers is set by
     [Character Rules](#character-rules). The schema and the declared pin celltype determine
     them completely; no other declaration is involved.

## Two Validation Stages

Compiled-pin checks are split by whether they need input data.

**Stage 1: data-independent; a failure blocks the transformer.** Decided from builder state
alone:

- the schema is set and parses, so that a C header can be generated;
- metavars are complete;
- every declared pin celltype is compatible with its schema parameter (see
  [User-declared pin celltypes](#3-user-declared-pin-celltypes));
- no compiled input pin is declared optional.

A Stage 1 failure blocks the transformer whatever its inputs, exactly as a missing header
does. No input is resolved, converted, or validated for it:

- a standalone call or snapshot build raises before binding its call arguments;
- a bound workflow transformer is blocked with the Stage 1 diagnostic before its pins are
  resolved;
- graph import rejects a compiled transformer node with optional input pins, because that
  state can never become valid. It imports other Stage 1 failures as a blocked transformer,
  because builder state may be temporarily inconsistent.

**Stage 2: data-dependent; runs per transformation.** Needs input checksums, and for some
checks their buffers or values:

- null (C ABI rule 4);
- readability of each checksum as its declared pin celltype;
- `mixed` representation classification;
- schema refinements: dtype, width and range, shape and wildcard consistency, byte order,
  alignment, and layout.

Where each Stage 2 check runs is set by
[Validation Placement](#validation-placement-identity-without-input-data).

## Validation Placement: Identity Without Input Data

Computing a transformation checksum must not require input buffers. Python transformations
already have this property: their identity is computed from input checksums, and their
HashType checks never fetch a buffer. Compiled transformations must keep it. Otherwise a
cache hit would still download every input, and a large remote array would be fetched to
the client only to compute identity. The current compiled code breaks this property: its
deferred validation hooks resolve every deferred input before hashing.

Stage 2 therefore runs in two places:

- **Before hashing, at construction: only checks that need no input buffer fetch.**
  - Inputs supplied as literal values (standalone call arguments, pin assignments): the
    value is serialized under the declared pin celltype, and every Stage 2 check applies to
    the value as read back from that local buffer. The Python object before serialization
    plays no part, so a literal and its checksum `Buffer(value, pin_celltype).get_checksum()`
    get the same verdict. For example, `np.float32(1.5)` given to a `mixed` pin is
    serialized as JSON `1.5` and validated as that JSON number, not as a `float32`.
  - Every input: checksum-level facts, namely the null checksums (`is_null_value`; under
    `bytes`, the non-canonical one), the boolean virtual values, and the other trivial
    checksums (`{}`, `[]`, `""`).
  - Every input: HashType facts, when the word is available without fetching the buffer:
    readability disproofs for the declared celltype, `mixed` storage classes that are
    always rejected (JSON and Seamless-mixed objects and arrays), and NumPy dtype class and
    rank.
- **In the executor, before compilation: every Stage 2 check on every input**, whatever
  construction already checked. This is the guarantee. The pre-hash checks are an
  early-fail optimization.

Rules:

- A pre-hash check may reject only what the executor would also reject, with the same error
  type and message. It never changes what is accepted.
- Pre-hash checks use only sound facts. A `JSON_STRING` HashType word does not prove a JSON
  string: JSON `true`, `false`, and `null` are classified `JSON_STRING` (see
  [`docs/agent/contracts/hashtype.md`](docs/agent/contracts/hashtype.md)). HashType does not
  record exact dtype, shape, byte order, or wildcard sizes; those checks run in the executor
  unless the input is a literal value.
- The invariant is: **an invalid input never reaches native compilation or the native call,
  and never produces a cached result.** An invalid input may acquire a transformation
  checksum when its invalidity cannot be decided without its data.
- Whether an error surfaces before hashing or in the executor may depend on local state,
  such as whether a HashType word is cached. Its type and message do not; how the type
  crosses the executor boundary is open decision D5. In a bound
  workflow, the transformer's exception names the offending pin in either case.

## Contract Summary

A Seamless celltype is a function-boundary contract. It determines accepted checksums,
serialization of direct values, the value read from a checksum, and the conversion required
on a workflow edge. A compiled schema refines that boundary with native facts that celltypes
do not express, such as integer width, signedness, array shape, native byte order, and struct
layout.

For a compiled pin, keep these concepts distinct:

- **Source celltype**: the celltype of an upstream Cell or Expression.
- **Declared pin celltype**: the public celltype configured on the compiled transformer.
- **Schema celltype**: the one celltype derived from a schema parameter, or none where the
  natural celltype is ambiguous (see [Schema-derived celltypes](#2-schema-derived-celltypes)).
- **Schema refinement**: dtype, width, signedness, shape, alignment, and layout checks.

The declared pin celltype is what the workflow graph targets and what the concrete
transformation records. The schema celltype never replaces it, and a pin declared `mixed`
is never resolved to it. The schema celltype has one job: it generates the whitelist of
compatible declarations (see [User-declared pin celltypes](#3-user-declared-pin-celltypes)).
Where there is none, the whitelist lists the declarations explicitly. It also appears in
diagnostics and inspection.

For a declared `mixed` pin, `mixed` has one compiled-specific meaning:

> Accept only natural mixed values compatible with the schema, reject the other mixed
> representations, and apply the schema refinements without general value coercion.

There is no unrestricted, non-schema-bound `mixed` mode for compiled input pins.

**`mixed` is "auto".** It is the default declaration, and it lets the schema decide which
values pass. There is no separate auto state: declaring `mixed` explicitly is the same as the
default, and resets a pin to auto. Graph export already writes `mixed` for an undeclared pin,
and D4 imports a missing celltype as `mixed`.

Auto exists only where the schema can decide. A scalar `char` or a one-dimensional `char`
array has no schema celltype, and does not allow `mixed`: its pin needs an explicit
declaration. Everywhere else `mixed` is allowed, and the two meanings of `mixed`, an actual
`mixed` value and auto, are kept consistent by the auto-consistency property in
[Schema-derived celltypes](#2-schema-derived-celltypes). A pin declared `mixed` therefore
becomes incompatible only when the schema turns its parameter into a scalar `char` or a
one-dimensional `char` array.

## Non-Negotiable Decision: The Conservative Baseline Is Scoped To The Pin

The conservative compatibility baseline governs this pair:

```text
(schema parameter, declared compiled-pin celltype)
```

It does **not** constrain the celltype of an upstream Cell and it does not globally prohibit
liberally typed workflow data.

The usual conversion path is the workflow graph:

```text
liberally typed upstream Cell
        |
        | explicit workflow edge / Seamless Expression conversion
        v
conservatively typed compiled pin
        |
        | checksum already has the pin celltype
        v
compiled transformation construction and schema validation
```

Examples:

- A `mixed` Cell may feed an `int` compiled pin through an empty-path
  `mixed -> int` Expression.
- A `plain` list may feed a `binary` array pin through the conversion engine where that
  conversion is valid.
- A proper Seamless-mixed structure may be navigated or transformed by an explicit
  Expression; the resulting scalar or binary checksum may then feed the compiled pin.
- The proper Seamless-mixed structure itself is not a valid direct value of a compiled
  `mixed` pin.

Once the pin checksum is known, neither compiled transformation construction nor the
executor may perform a second round of broad or convenient conversion. Between them, they
may only:

- canonicalize, and reject values that read as None (C ABI rule 4);
- validate that the checksum is readable as the declared pin celltype;
- classify and reject disallowed representations for a declared `mixed` pin;
- resolve/materialize when schema validation actually needs the value or buffer (in the
  executor, unless the value was supplied as a literal; see
  [Validation Placement](#validation-placement-identity-without-input-data));
- validate schema refinements;
- prepare the already-valid value for native calling without semantic coercion.

This scope distinction must be stated in API documentation and protected by tests. It is
the central design decision of this plan.

### Worked example: a Python dict passed to C as JSON text

A C function that parses a JSON document receives UTF-8 text. The dict is `plain` data, but
the compiled pin is declared `text`: a pin celltype describes what the C function receives,
not what the upstream data is. Declaring the pin `plain` or `mixed` is not possible, because
a JSON object has no C ABI and a `mixed` compiled pin rejects JSON containers. The schema
parameter is a one-dimensional character array, such as `doc` with dtype `char` and shape
`[N]`; the C function receives the JSON text as UTF-8 bytes and their length N, without a
terminator (see [Character Rules](#character-rules)).

The `plain → text` conversion therefore happens before the pin:

- **Bound, in a workflow.** Put the dict in a Cell with celltype `plain`, and connect that
  Cell to the `text` pin. The edge converts `plain → text`.
- **Unbound, with a typed input.** Pass a `plain` Cell, Expression, or Transformation that
  holds the dict as the `doc` argument, or assign it as the pin's source. It is converted to
  `text` exactly as an edge would convert it. A failed conversion raises an error that names
  the pin (for example, `ValueError` in pin `'doc'`).
- **Unbound, with a raw Python dict.** A raw value has no celltype of its own. A literal
  passed to or assigned to a pin means exactly `Buffer(value, pin_celltype).get_checksum()`,
  so passing `d` itself gives the `text` checksum of `str(d)`, Python's repr, which is not
  JSON. Make the dict into JSON text first:
  - with an Expression from its `plain` checksum,
    `Expression(checksum, input_celltype="plain", celltype="text")`;
  - or in Python, with `json.dumps(d)`, whose string becomes the `text` checksum of that
    JSON.

  The two routes format the JSON differently, so they give different input checksums. Both
  are valid.

A checksum works the same way. Like a Cell, a Pin has an underlying Expression:
`set_checksum` sets the *input* checksum of that Expression, and `.checksum` is its result.
`set_checksum(checksum, input_celltype="plain")` with the dict's `plain` checksum therefore
converts to `text` like any other input. The conversion is not performed during the
`set_checksum` call. Only when the input celltype equals the pin celltype, as with
`set_checksum(checksum)` on the `text` pin, is no conversion involved.

Three points that are easy to misread:

- **"Conservative" restricts the pin declaration, not conversion.** Converting data into the
  pin's celltype is fine.
- **A Pin has an underlying Expression.** Its input (an edge, a Cell, Expression, or
  Transformation, a literal, or a checksum given to `set_checksum`) is converted from its
  input celltype to the pin celltype. An input celltype equal to the pin celltype is the
  special case, not the rule.
- **Pins hold checksums, not values.** A literal is serialized under the pin celltype when it
  is passed or assigned. That serialization is the celltype's contract, not a conversion.

Typed inputs are converted as for Python and bash transformers. What is specific to
compiled transformers is the restricted set of pin celltype declarations.

## Three Sources Of Authority

### 1. Natural mixed-value admission and rejection

`mixed` is a union of several storage/value families. Compiled pins must not treat the
whole union as a native ABI.

| Actual `mixed` representation | Direct compiled `mixed` pin policy |
|---|---|
| Pure binary / NumPy `.npy` | Accept when the schema can consume the scalar, array, or structure |
| Pure JSON integer/float/Boolean | Accept for a compatible native scalar schema |
| Pure JSON string | Reject; declare the pin `text` when textual input is intended |
| Pure JSON list/dict | Reject as a direct `mixed` pin value |
| Proper Seamless-mixed list/dict containing NumPy values | Reject |
| Null (any buffer that reads as None) | Reject before ordinary value validation (C ABI rule 4) |

“Proper mixed” means Seamless-specific mixed serialization that is neither pure `.npy` nor
pure JSON. It has no natural C ABI and must be rejected. The compiled layer must not invent
recursive marshalling for it.

JSON containers also have no general native ABI. If a compiled function wants a JSON
document, declare a `text` pin and parse the text explicitly. If a list is intended as
numeric array data, let a workflow Expression perform the explicit source-to-`binary`
conversion before the compiled pin.

A JSON string is not native text at the boundary: it is JSON-quoted. A `text` target gives
the existing `mixed -> plain -> text` conversion chain the opportunity to produce unquoted
UTF-8 text.

### 2. Schema-derived celltypes

Every input parameter has one schema celltype, or none:

| Schema parameter | Schema celltype |
|---|---|
| Signed or unsigned integer scalar | `int` |
| Floating-point scalar | `float` |
| Boolean scalar | `bool` |
| Complex or structured scalar | `binary` |
| Scalar `char`, or one-dimensional `char` array | none: an explicit declaration is required |
| Every other array, of any dtype and number of dimensions | `binary` |

Integer width/signedness, float precision, NumPy dtype, shape, byte order, alignment, and
structure layout remain schema validations. They are not new Seamless celltypes. Numeric
scalars are checked by kind and range, everything else by exact dtype; see
[Native Scalar Rules](#native-scalar-rules).

A schema `char` is a byte, not Unicode. For `char` parameters, the declared pin celltype
alone decides how the input becomes bytes; see [Character Rules](#character-rules).

**Auto consistency.** Where a parameter has a schema celltype, the two meanings of `mixed`
agree:

> A value of the schema celltype that satisfies the schema, serialized under that celltype,
> is accepted by a `mixed` pin, and makes the same native call as on a pin declared with the
> schema celltype.

It holds for every row that has a schema celltype:

- `int`, `float`, and `bool` convert to `mixed` without changing the checksum (through
  `plain`), and read under `mixed` as the same JSON scalar.
- `binary` converts to `mixed` without changing the checksum, and both celltypes read a
  checksum with the same parser, so a `mixed` pin and a `binary` pin give every `binary`
  checksum the same verdict.

Apart from the deliberate exclusion below, no schema is incompatible with `mixed`: every
schema parameter has a `.npy` representation, which is a valid `mixed` value. Two limits
apply to `binary` and `mixed` alike: a complex value cannot be serialized until the
[seamless-core prerequisite](#prerequisites-in-seamless-core) lands, and a structured value
must have an aligned, native dtype to be serialized at all.

The property concerns values serialized under the schema celltype. A checksum that is not
canonical for that celltype can behave differently: an `int` pin reads JSON `5.7` as 5, while
a `mixed` pin on an integer parameter rejects it. That is the documented `int` reading, not
an auto inconsistency.

**No auto for a scalar `char` or a one-dimensional `char` array.** Here the natural
celltype is ambiguous. `bytes`, `binary`, and, for a one-dimensional array, `text` all fit,
and they accept different inputs (see [Character Rules](#character-rules)). `mixed` cannot
stand in for any of them consistently:

- Converting `bytes` to `mixed` keeps a buffer that parses as JSON as that JSON value
  (`b"1"` becomes the integer 1), turns other UTF-8 content into a JSON string (`b"ACGT"`
  becomes `"ACGT"`), and turns only non-UTF-8 content into a zero-dimensional `S{len}`
  array. All of these are rejected on `char [N]`. On a scalar `char`, only a non-UTF-8 byte
  such as `b"\xe9"` would pass, and `b"x"` would not.
- `text` converts to `mixed` as a JSON string and fails the same way.
- Only `binary` agrees with `mixed`, and `binary` accepts nothing but NumPy `S1` data.
  Making it the schema celltype would turn auto into a silent choice of the narrowest option.

These parameters therefore have no schema celltype and do not allow `mixed`. The user
declares `bytes`, `binary`, or `text` explicitly. A pin left at `mixed`, including the
default of a new pin, is an incompatible declaration: it blocks the transformer and is
reported as a missing declaration (see
[Reporting incompatible declarations](#reporting-incompatible-declarations)). A `char` array
with two or more dimensions keeps auto: `binary` is its only other declaration, and it agrees
with `mixed`.

### 3. User-declared pin celltypes

The transformer stores the declared pin celltype independently from the derived schema
celltype. New schema pins default to declared `mixed` (auto), whose meaning is the
restricted, schema-bound policy above. On a scalar `char` or a one-dimensional `char` array
that default is not allowed, and must be replaced by an explicit declaration.

The initial conservative compatibility matrix is:

| Schema kind | Compatible declared pin celltypes |
|---|---|
| Integer scalar | `int`, zero-dimensional `binary`, schema-bound `mixed` |
| Floating scalar | `float`, zero-dimensional `binary`, schema-bound `mixed` |
| Boolean scalar | `bool`, zero-dimensional `binary`, schema-bound `mixed` |
| Complex scalar | zero-dimensional `binary`, schema-bound `mixed` |
| Numeric/Boolean/complex array | `binary`, schema-bound `mixed` |
| Structured scalar or array | `binary`, schema-bound `mixed` |
| Scalar `char` | `bytes`, zero-dimensional `S1` `binary` (no `mixed`) |
| One-dimensional `char` array (`[N]` or `[k]`) | `bytes`, `text`, `S1` `binary` (no `mixed`) |
| `char` array with two or more dimensions | `S1` `binary`, schema-bound `mixed` |

The matrix follows one formula. Where a parameter has a schema celltype, the compatible
declarations are the schema celltype, `binary`, and `mixed`: for numeric scalars the schema
celltype adds `int`, `float`, or `bool`, and for every other such parameter it is `binary`
itself. Where it has none, the declarations are listed explicitly: `bytes` and `binary` on a
scalar `char`, and `bytes`, `text`, and `binary` on a one-dimensional `char` array. The
compatible declarations are therefore always drawn from `int`, `float`, `bool`, `bytes`,
`text`, `binary`, and `mixed`.

This is a whitelist, not a test of whether some generic conversion path happens to exist.
Which zero-dimensional `binary` values a numeric scalar parameter admits is set by
[Native Scalar Rules](#native-scalar-rules) (decision D3). Character parameters take exact
dtype `S1`; see [Character Rules](#character-rules). `bytes` and `text` carry only a length,
so they cannot fill a multidimensional array: `[N, M]` has no single split, and `[N, 4]`
would need a reshape rule.
In particular, `plain`, `str`, general code/text celltypes, `checksum`, and deep/structural
celltypes are not automatically compatible with a native numeric parameter.

The matrix can grow only when a specific native representation and validation rule are
documented. Do not broaden it because the current native-call library happens to coerce a
value successfully.

## Schema Mutation And Celltype State

Compiled transformer schema assignment must become an atomic builder-state update:

1. Parse and validate the prospective schema. A schema that does not parse raises, and
   nothing changes.
2. Derive the prospective schema-celltype map.
3. Preserve declared celltypes for surviving pin names, whether or not they are still
   compatible.
4. Give newly introduced pins the declared celltype `mixed` (auto). On a scalar `char` or a
   one-dimensional `char` array this is reported as a missing declaration in step 7.
5. Remove declarations for pins that disappeared.
6. Rebuild the call signature and schema-derived metadata.
7. Recompute the Stage 1 state (see [Two Validation Stages](#two-validation-stages)), and
   report every incompatible declaration (see
   [Reporting incompatible declarations](#reporting-incompatible-declarations)).

Do not reset every declared pin to `mixed` whenever the schema changes, and never replace a
`mixed` declaration with an explicit one. A pin declared `mixed` stays auto; it becomes
incompatible only when its parameter becomes a scalar `char` or a one-dimensional `char`
array, and is then reported as a missing declaration. Any other declaration can become
incompatible too. Either way it is kept and reported, never silently changed.

Pins are identified by name:

- **A pin exists only once the schema defines it.** Its celltype cannot be declared before
  that: the compiled celltypes wrapper raises `AttributeError` for an unknown pin.
- **"Either order" applies to existing pins.** Temporary builder inconsistency is allowed so
  that users can change a pin's declaration first and then the schema, or the other way
  round. A new pin needs the schema first.
- **Renaming a pin in the schema removes one pin and adds another.** The declaration of the
  old name is dropped, and the new name starts as auto. This is intended.

**Absent or unparsable schema.** Step 1 keeps the API from producing this state, but graph
import can: it imports Stage 1 failures as a blocked transformer (see
[Two Validation Stages](#two-validation-stages)). Declarations are then kept as imported,
without validation, and the transformer is blocked on its schema. Declarations are removed
(step 5) and checked for compatibility only against a schema that parses.

An incompatible declaration is a Stage 1 failure: it blocks the transformer until corrected,
whatever the input data.

### Reporting incompatible declarations

A declared celltype that the schema does not allow is always reported. It is never silently
accepted, reset, or replaced.

- **A celltype that no schema allows** is anything other than `int`, `float`, `bool`,
  `bytes`, `text`, `binary`, and `mixed` (for example `plain`, `str`, or `deepcell`).
  Declaring it raises immediately, because no schema edit can make it valid. Graph import
  can still bring one in, for example from a graph saved by code that ignored compiled pin
  declarations (D4): it is imported as declared, blocks the transformer, and is reported
  like the case below.
- **A celltype that some schema allows but the current one does not** is accepted, so that
  schema and declaration can be edited in either order, and reported:
  - **when it arises**, from either a declaration change or a schema change: a
    `CompiledPinCelltypeWarning` carrying the diagnostic below;
  - **whenever the transformer is used**: a standalone call or snapshot build raises
    `CompiledPinCelltypeError`, and a bound workflow transformer is blocked with it as its
    exception;
  - **on inspection**: repr output and the schema-celltype view mark the pin as
    incompatible;
  - **after graph import or snapshot restore**: the same way, as if it had just arisen.
- Every report lists all incompatible pins, not only the first.
- While the schema is absent or does not parse, compatibility cannot be checked. The schema
  failure is reported instead, and the declarations are checked as soon as a schema parses.

The diagnostic names:

- the pin;
- the declared pin celltype;
- the schema dtype and shape;
- the derived schema celltype, or that there is none;
- the allowed declarations.

Example, after a schema change from `int32` to `float64` with shape `[N]`:

```text
Compiled pin 'x' declares celltype 'int', which is incompatible with
schema dtype 'float64', shape [N] (schema celltype 'binary'). Allowed pin
celltypes are 'binary' and 'mixed'.
```

A `mixed` pin on a scalar `char` or a one-dimensional `char` array is reported as a missing
declaration, whether `mixed` is the default or was declared:

```text
Compiled pin 'seq' (schema dtype 'char', shape [N]) needs an explicit
celltype: 'bytes', 'text', or 'binary'. 'mixed' (auto) is not available
for this parameter.
```

Expose the distinction for inspection. At minimum, debugging/repr output shows both the
declared and schema celltypes. A read-only `schema_celltypes` or equivalent view is
preferable to hiding the derived state.

## Direct Calls, Workflow Calls, And Expressions

### Workflow-bound transformers

The workflow graph must expose the declared compiled-pin celltype. A connection from a
differently typed upstream Cell is represented by the normal Expression conversion edge.
The compiled transformer does not duplicate this conversion after dependency resolution.

Graph export/import and compiled-transformer snapshots must preserve:

- schema text;
- declared pin celltypes;
- the distinction between builder state and concrete transformation inputs.

Compiled transformer nodes never carry optional input pins; graph import rejects them
(C ABI rule 3).

### Standalone compiled transformers

For direct Python literals, serialize under the declared pin celltype and then apply schema
validation to the serialized value, never to the original Python object (see
[Validation Placement](#validation-placement-identity-without-input-data)). This is ordinary
celltype serialization, not a compiled-specific coercion layer.

An already typed Cell, Transformation, or Expression input whose celltype differs from the
declared pin celltype is converted to the pin celltype, as for Python and bash transformers
(`_convert_pin_arguments`, `_bind_snapshot_arguments`, `Pin.build`). The conversion is part
of dependency resolution and happens before compiled transformation construction. A failed
conversion raises an error that names the pin, the input celltype, and the pin celltype
(for example, `ValueError` in pin `'doc'`). Today it surfaces as
`RuntimeError: Dependency 'doc' has an exception: Cannot convert expression source to
target celltype ...`, which names the pin but not the celltypes. How the error class
crosses the executor boundary is open decision D5.

`set_checksum(checksum, input_celltype=...)` sets the input checksum of the pin's
underlying Expression, and converts the same way (see the worked example above).

## Concrete Compiled Transformation Contract

Every concrete compiled transformation input tuple must contain its actual declared pin
celltype:

```python
{
    "a": ("int", None, checksum_hex),
    "array": ("binary", None, checksum_hex),
    "auto_pin": ("mixed", None, checksum_hex),
}
```

The pretransformation builder must stop replacing all input celltypes with `mixed`.

The schema remains part of the transformation definition and checksum. A declared `mixed`
pin remains `mixed` in the concrete tuple; its restricted meaning comes from the compiled
schema plus the compiled mixed-value validator. It is not silently rewritten to the schema
celltype after the workflow has targeted the pin.

Stage 2 validation order, once Stage 1 has passed and all dependencies have concrete
checksums. Construction applies each step only as far as it can be decided without fetching
an input buffer; the executor applies every step in full, before compilation (see
[Validation Placement](#validation-placement-identity-without-input-data)).

1. Canonicalize checksums according to their declared pin celltypes.
2. Reject every input that reads as None (C ABI rule 4). No pin is dropped: compiled
   transformers have no optional pins. The generic `validate_pin_null` is not sufficient: it
   exempts `plain`, `mixed`, and `bytes`, and it tests `is_null`, which matches only the
   canonical `null\n`. `is_null_value` rejects both null checksums without a buffer. Other
   buffers that read as None, such as whitespace-padded JSON null under `mixed`, are caught
   by the classification in step 4. Under `bytes`, the canonical null reads as `b""` and is
   left to schema refinement; the non-canonical `null` checksum is rejected (C ABI rule 4).
3. Validate that every checksum is deserializable as its declared pin celltype.
4. For declared `mixed`, classify the actual mixed representation and apply natural
   admission/rejection.
5. Apply schema refinement validation.

Construction computes the transformation checksum only after its pre-hash checks pass. Sync
and async/deferred construction share this order and one validation helper; the executor
runs the same helper in full mode. An invalid input never reaches native compilation or
calling and never produces a cached result. It may acquire a transformation checksum when
its invalidity cannot be decided without its data.

## Native Scalar Rules

The compiled layer must not use native marshalling as a general conversion engine.

A scalar parameter is passed to C by value (C ABI rule 3), so its value is always converted
to the C type; the rules below decide only which values are admitted. An array is passed as
a pointer to its buffer, so its dtype is its memory layout: a mismatch would need a copy and
a cast, which is the hidden conversion this plan rules out. Numeric scalars are therefore
admitted by kind and range, and arrays by exact dtype.

For pins declared `mixed` or `binary`, one admission table covers JSON scalars and
zero-dimensional numeric `binary` scalars alike. The admitted value is passed on without
further semantic coercion:

| Schema scalar | JSON scalar | Zero-dimensional `binary` scalar |
|---|---|---|
| Signed/unsigned integer | Python `int`, excluding `bool` | any signed or unsigned integer dtype |
| Floating point | Python `float`; Python `int` is open decision D1 | any floating-point dtype; integer dtypes are open decision D1 |
| Boolean | Python `bool` only | `bool` dtype only |
| Complex | No JSON representation | any complex dtype |
| `char` | No JSON representation; a JSON string is rejected. A scalar `char` does not allow `mixed` (see [Character Rules](#character-rules)) | exact dtype `S1` |

After admission, the range of the schema type is enforced:

- integers must lie within the native range;
- for floating-point values, and for each part of a complex value, NaN and ±infinity pass
  through (C ABI rule 5), rounding within the finite range is accepted, and a finite value
  outside that range is open decision D2.

The dtype of an admitted zero-dimensional value is not compared with the schema dtype, and
its byte order plays no part. Exact dtype and native byte order still apply to structured
scalars and character scalars, whose dtype is their layout, and to every array, including
shape-`(1,)` arrays on a scalar parameter.

The rule is the same for `mixed` and `binary` pins. Converting `binary` to `mixed` does not
change the checksum, so both pins give the same checksum the same verdict.

A JSON scalar carries no dtype. Neither does a finite NumPy scalar serialized under `mixed`,
which is written as a JSON number (see
[Prerequisites In seamless-core](#prerequisites-in-seamless-core)). `np.float32(1.5)` as a
zero-dimensional `.npy`, `np.float64(1.5)` as one, and JSON `1.5` have different checksums
but make the same native call. They are cached separately, which duplicates a result but
never returns a wrong one.

Any widening retained in this table must be tested as part of the stable compiled ABI, not
accepted accidentally because of one CFFI version. There is no float-to-int truncation in
the schema-bound validator, for JSON or `binary` scalars. A user who wants Seamless
`float -> int` semantics should put that conversion on a workflow edge feeding an `int` pin.

For a pin explicitly declared `int`, `float`, or `bool`, ordinary celltype serialization
and Expression conversion semantics remain authoritative, including the documented
Seamless scalar conversion behavior. These celltypes cannot hold NaN or infinity. The table
above exists because `mixed` and `binary` values have no Seamless scalar conversion
semantics of their own.

## Character Rules

A schema `char` parameter receives bytes (C ABI rule 6). The declared pin celltype decides
how the input is read into bytes. Once read, the bytes are passed the same way whatever the
celltype, so the kernel cannot tell which celltype delivered them.

| Declared pin celltype | Schema shapes (see the [compatibility matrix](#3-user-declared-pin-celltypes)) | Bytes the kernel receives |
|---|---|---|
| `bytes` | scalar `char`; one-dimensional array | the `bytes` value, unchanged |
| `text` | one-dimensional array | the `text` value encoded as UTF-8, without the newline that serialization appends |
| `binary` | every `char` shape | the data of a NumPy array of exact dtype `S1` and the schema's shape |
| `mixed` | `char` arrays with two or more dimensions | the same as `binary` |

Rules:

- **Length.** For a wildcard dimension, the length is the byte count: for `text`, UTF-8
  bytes, not characters. A fixed size `[k]` requires exactly k bytes, and a scalar `char`
  exactly one. Any other length is a schema refinement error. Nothing is padded (with NUL or
  otherwise) or truncated; padding is an explicit conversion upstream.
- **`text` delivers its value, not its buffer.** The value `ACGT` is stored as `ACGT\n`, and
  reading strips trailing newlines. The kernel receives `ACGT` with length 4. The value is a
  prefix of the stored buffer, so it can be passed without a copy. A `text` pin and a
  `bytes` pin fed from the same text Cell therefore differ: the trivial `text → bytes`
  conversion keeps the buffer unchanged, so the `bytes` pin receives `ACGT\n` with length 5.
- **`binary` and `mixed` take exact `S1`.** A NumPy fixed-width byte string `S{k}` with
  k > 1 is rejected, even where its bytes would fit: a zero-dimensional `S4` on `char [4]`,
  or an `S4` array of shape `(N,)` on `char [N, 4]`. This includes the zero-dimensional
  `S{len}` array that converting `bytes` to `binary` produces, and the one that `mixed`
  produces when it reads a raw byte buffer that is neither JSON nor NumPy. Such a byte string
  belongs on a `bytes` pin. A JSON string is rejected.
- **Null.** Under `bytes`, the canonical null is `b""`; under `text`, the string `null` is
  rejected and `""` has length 0 (C ABI rule 4).
- A declared celltype that the table does not list for the parameter's shape is a Stage 1
  failure. This includes `mixed` on a scalar `char` or a one-dimensional `char` array.

### Choosing a declaration

A scalar `char` or a one-dimensional `char` array needs an explicit declaration. The three
choices accept different inputs. The table follows the core serializer and conversion table;
the [character tests](#character-tests) confirm it.

| Declaration | Typical inputs | Rejected or surprising |
|---|---|---|
| `bytes` | `bytes` literals and Cells; `str` literals, encoded as UTF-8; NumPy `S1` arrays from a `binary` or `mixed` Cell, converted with `tobytes` | a `text` Cell keeps its trailing newline (`text → bytes` is trivial); a `plain` Cell delivers its JSON text, quotes included |
| `text` (one-dimensional only) | `str` literals; `text` and `str` Cells; `bytes` Cells whose content is UTF-8 | NumPy arrays; content that is not UTF-8 |
| `binary` | NumPy `S1` arrays: `ndarray` literals, and `binary` or `mixed` Cells holding an `S1` `.npy` | a `bytes` literal: the `binary` serializer takes a `bytes` object as an already-serialized buffer, so its checksum is unreadable as `binary`; a `bytes` or `text` Cell on `char [N]`, which converts to a zero-dimensional `S{len}` array |

`bytes` is the broadest choice, `text` is for text, and `binary` is for data that already is a
NumPy `S1` array.

## Efficient Validation

Validation should follow the same economy principle as the conversion engine:

1. checksum-only facts first;
2. cached HashType/storage classification next;
3. buffer inspection only when classification cannot be decided otherwise;
4. full value deserialization only for schema checks that require it.

Before hashing, only steps 1 and 2 apply to inputs that were not supplied as literal values.
Steps 3 and 4 run in the executor (see
[Validation Placement](#validation-placement-identity-without-input-data)).

Add or reuse one mixed-representation classifier with outcomes such as:

```text
null
pure-binary
json-int
json-float
json-bool
json-string
json-container
proper-mixed
```

Do not infer this taxonomy merely from the final Python value: storage representation and
checksum identity matter. Prefer an existing core parser/HashType fact; if core exposes no
stable classifier, add the smallest reusable API there rather than duplicating the mixed
format parser in `seamless-transformer`.

Classification is reject-only. It must not rewrite or canonicalize a successful non-null
value.

## Current Code Anchors

Primary changes in `seamless-transformer`:

- `seamless_transformer/compiled_transformer.py`
  - `CompiledMixin.schema` currently recreates all input celltypes as `mixed`.
  - `CompiledCelltypesWrapper` needs schema-aware declaration handling.
  - Compiled transformers currently accept `optional_pins` declarations; they must reject
    them (C ABI rule 3).
  - `_bind_compiled_arguments` already raises for a missing schema or incomplete metavars.
    These checks, plus declared-celltype compatibility and the optional-pin check, become
    the shared Stage 1 check. It must not become a conversion engine.
  - `_bind_compiled_arguments` also calls `_validate_native_numpy_value` on each raw literal
    before serialization, comparing a NumPy scalar's dtype with the schema dtype. On a
    `float64` schema, `tf(b=np.float32(1.5))` is therefore rejected, while
    `tf.pins.b = np.float32(1.5)`, which stores the checksum of JSON `1.5`, is accepted. The
    Stage 2 validator replaces this check and runs on the serialized value.
  - `_deferred_validation_hooks` resolves every deferred input (`fingertip_sync("mixed")`)
    before hashing, and `TransformerCore._build_from_snapshot` applies these hooks to every
    input. Replace them with the shared Stage 2 validator in pre-hash mode, which fetches no
    input buffer.
  - `CompiledTransformer.__call__` keeps converting typed inputs through
    `_convert_pin_arguments`; a failed conversion must name the pin.
- `seamless_transformer/pretransformation.py`
  - `compiled_transformer_to_pretransformation` currently hardcodes every input tuple to
    `("mixed", None, value)`.
  - It must receive and preserve the declared celltype for every pin.
- `seamless_transformer/transformation_class.py`
  - `_prepared_dict_with_dependencies` is the post-dependency, pre-hash construction point.
    It runs the pre-hash checks, which fetch no input buffer. It currently calls
    `normalize_optional_pins_for_construction`, whose generic null check would raise before
    the compiled validator can produce its targeted error.
- `seamless_transformer/transformation_utils.py`
  - `validate_pin_null` tests `is_null`, which matches only the canonical `null\n`, and
    exempts `plain`, `mixed`, and `bytes`. The compiled null rule (C ABI rule 4) is stricter
    and reading-based, and does not reuse this exemption.
- `seamless_transformer/transformer_class.py`
  - Pin inputs are wrapped in conversion Expressions at several sites, not only in
    `_convert_pin_arguments`. All of them keep converting typed inputs to the pin
    celltype, and Phase 4 requires a pin-naming error at each of them:
    - `TransformerCore._convert_pin_arguments`: typed call arguments (Transformation,
      Expression) whose celltype differs from the pin's;
    - `TransformerCore._bind_snapshot_arguments`: every input stored on a pin, from its
      input celltype to the pin's current celltype;
    - `Pin.build` (`seamless_transformer/pin_class.py`), which `_bind_compiled_arguments`
      uses: the same, on the direct compiled call path;
    - bound transformers: `seamless_workflow/runtime_api.py` (edges from Cells, and
      checksums set directly on pins) and `Reactive._derive_transformer`
      (`seamless_workflow/reactive.py`).
- `seamless_transformer/builder_snapshot.py`
  - Preserve schema-derived state and declared celltypes without conflation.
- `seamless_transformer/run.py`
  - `call_compiled_transform` builds the compiled module before it reads any input, then
    reads `namespace[parameter.name]`, so a missing input raises `KeyError`. The full Stage 2
    validator must run first, before `build_compiled_module`.
  - `_numpy_dtype` maps the schema dtype `char` to `S1`, and `_coerce_array_input` requires exactly that
    dtype. A `bytes` or `text` value is not an `S1` array (`np.asarray(b"ACGT")` is a
    zero-dimensional `S4`), so today only `binary` reaches a character array. Marshalling
    must pass `bytes` and `text` values as a pointer and a byte length (see
    [Character Rules](#character-rules)).
  - `_array_ctype` and `_output_scalar_pointer` take their C type names from
    `SCALAR_C_TYPES` in seamless-signature. Under `unsigned char`, CFFI takes a scalar as an
    integer and rejects a one-byte `bytes` object, so a scalar `char` input is passed as its
    byte value, and a scalar `char` output is read back as a byte.
- `seamless_transformer/transformation_namespace.py`
  - `build_transformation_namespace_sync` reads each pin under the celltype in its input
    tuple. Once tuples keep declared celltypes, a non-empty `bytes` pin arrives as a
    `Buffer` object and an empty one as `b""`; marshalling must accept both.
- `seamless_transformer/api/run_transformation.py` (`seamless-run-transformation`) and the
  remote workers
  - Submit transformation dicts that never passed through construction, and rely on
    executor validation.

Changes in `seamless-core`: see
[Prerequisites In seamless-core](#prerequisites-in-seamless-core).

Changes in `seamless-signature` (C ABI rule 6):

- `seamless_signature/c_header.py`: `SCALAR_C_TYPES` maps the schema dtype `char` to the C
  type `char`. It must map it to the C type `unsigned char`. The same mapping names the
  element types of `char` arrays and struct fields, and the CFFI types in `run.py`.
- [`docs/agent/contracts/seamless-signature-schema.md`](docs/agent/contracts/seamless-signature-schema.md):
  for the schema dtype `char`, the dtype table gives the C type `char` and Rust `c_char`;
  they become `unsigned char` and `u8`. The page must state that the schema dtype `char` is
  not the C type `char`.

Workflow changes:

- preserve compiled schema and declared pin celltypes in graph serialization;
- make compiled pin endpoints advertise the declared celltype;
- ensure ordinary edge construction owns source-to-pin Expression conversion;
- `seamless_workflow/reactive.py` (`Reactive._derive_transformer`) runs its own pin-level
  null check with the generic `validate_pin_null`, and treats null on an optional pin as
  absence. For compiled transformer nodes it must apply C ABI rule 4, treat no pin as
  optional, and block on Stage 1 failures before resolving pins;
- graph export currently writes `optional_pins` for every transformer
  (`seamless_workflow/context.py`); graph import must reject compiled transformer nodes with
  optional input pins.

## Prerequisites In seamless-core

The scalar rules rely on the following properties of the core serializer and parser. For a
NumPy scalar `value`, with S meaning serialization and D meaning reading:

- `S(mixed)` may write JSON: a finite NumPy integer or floating-point scalar is written as a
  JSON number, and reads back as a Python `int` or `float`.
- `S(binary)` writes a `.npy` buffer of the value's own dtype.
- `D(mixed)` of that `.npy` buffer returns the same NumPy scalar as `D(binary)`.
- Converting that buffer from `binary` to `mixed` is a no-op: the checksum does not change.

On the current code these hold for integer, floating-point (NaN and infinity included), and
Boolean scalars, and for zero-dimensional arrays. The following changes must land before
[Phase 3](#phase-3-add-pre-hash-compiled-pin-validation):

1. **NaN and infinity are NumPy values** (C ABI rule 5).
   - Under `mixed`, a top-level NaN or infinity, whether a Python `float` or a NumPy
     floating-point scalar of any precision, is serialized as a zero-dimensional `float64`
     `.npy`. Today it is written as `NaN\n` or `Infinity\n`, which cannot be read as `mixed`.
   - Inside a dict or list, it is serialized as a NumPy value inside JSON (mixed-plain
     storage). Today it is written as JSON `NaN`, which cannot be read back either.
   - In both positions it reads back as `np.float64(nan)` or `np.float64(inf)`. A nested
     zero-dimensional leaf therefore reads back as a NumPy scalar, as a top-level one already
     does; today it reads back as a zero-dimensional array (`array(nan)`).
   - Under `plain` and `float`, serializing NaN or infinity raises. Today both write
     `null\n`, which reads back as None.
   - A NumPy array keeps its dtype, including a zero-dimensional array.
2. **`np.bool_` under `mixed`.** Serialization raises `TypeError` today, because `np.bool_`
   is missing from the scalar types in `seamless/util/mixed`; a Python `bool` works. It is
   written as a JSON Boolean, like the other finite NumPy scalars.
3. **Complex values.** Serializing a complex scalar or array raises `TypeError` today, under
   `binary` and `mixed` alike (`get_tform_numpy_builtin` has no complex dtype). A hand-made
   complex `.npy` already reads correctly under both. Under `binary` a complex value is
   written as the `.npy` of its own dtype. Under `mixed` a complex scalar, which has no JSON
   form, is written the same way. Until this lands, a complex schema parameter can only be
   fed a hand-made `.npy`.
4. **Documentation. (Done, 2026-09-17.)**
   [`docs/agent/contracts/celltypes-and-conversion.md`](docs/agent/contracts/celltypes-and-conversion.md)
   states the four properties above and the NaN rule once they hold. Written ahead of the
   code, assuming items 1–3 land as specified; the "Known defects" list was removed.
5. **Classifier, if needed.** Expose a stable, checksum-aware classifier for the mixed
   storage taxonomy if existing HashType and parser APIs cannot distinguish pure JSON, pure
   binary, and proper mixed without duplicating format knowledge.

## Open Decisions Before Implementation

These rules are still undecided in the plan text, except D3, which is decided and keeps its
number because other sections refer to it. Each open decision must be decided, and the plan
text at the listed places updated, before Phase 0 starts. Each comes with a recommendation.

### D1. Integers on floating-point schemas

- **Where:** [Native Scalar Rules](#native-scalar-rules), floating-point row.
- **Question:** does a `mixed` or `binary` pin on a `float32` or `float64` parameter accept
  a JSON integer or a zero-dimensional integer `binary` scalar, and under what condition? C
  does not settle it: a prototyped C call converts implicitly in both directions.
- **Constraint:** integers beyond 2^53 (`float64`) or 2^24 (`float32`) are not all exactly
  representable.
- **Recommendation:** accept an integer, JSON or `binary`, only when the target type
  represents it exactly, and reject it otherwise. JSON has a single number type, so `5`
  versus `5.0` is a serialization accident; silent precision loss is not.

### D2. Finite floating-point values outside the target range

- **Where:** [Native Scalar Rules](#native-scalar-rules), range rules.
- **Question:** what happens to a finite value outside the finite range of `float32`, such
  as JSON `1e300` or `np.float64(1e300)` on a `float32` parameter?
- **Constraint:** converting such a value to C `float` is undefined behaviour (C11 6.3.1.5).
  NaN and ±infinity are not affected: both floating-point types represent them, and they
  pass through (C ABI rule 5).
- **Recommendation:** reject a finite value outside the finite range of the target type,
  for every declared celltype. Accept ordinary rounding within that range, such as JSON
  `0.1` on a `float32` parameter.

### D3. Zero-dimensional `binary` scalars (decided)

- **Where:** the compatibility matrix in
  [User-declared pin celltypes](#3-user-declared-pin-celltypes), and the mixed taxonomy
  tests.
- **Decision:** a numeric scalar parameter admits a zero-dimensional `binary` value by kind,
  not by exact dtype, under the same range rules as a JSON scalar, on `mixed` and `binary`
  pins alike. NaN and infinity are included. Structured and character scalars and all
  arrays, shape `(1,)` included, keep exact dtype and native byte order. See
  [Native Scalar Rules](#native-scalar-rules).

### D4. Legacy graphs

- **Where:** [Phase 6](#phase-6-workflow-persistence-and-migration): "reject legacy graphs
  ... or apply one documented compatibility default".
- **Constraint:** graph export already writes a celltype for every pin, defaulting to
  `mixed`. Compiled transformer nodes with optional input pins are rejected on import
  regardless of this decision.
- **Recommendation:** no separate legacy rule. A compiled input without a declared celltype
  imports as `mixed`, the same rule as for a pin newly introduced by a schema change.
  A consequence: old code recorded every compiled input as `mixed`, so a scalar `char` or
  one-dimensional `char` input in a legacy graph imports blocked, reported as a missing
  declaration, until the user declares `bytes`, `text`, or `binary`.
  Declared celltypes import as declared, although the old code ignored them; the resulting
  checksum change is accepted (see
  [Checksum And Compatibility Consequences](#checksum-and-compatibility-consequences)).
  Everything else goes through Stage 1.

### D5. Error classes, and errors raised in the executor

- **Where:** [Error Taxonomy](#error-taxonomy), and the rule in
  [Validation Placement](#validation-placement-identity-without-input-data) that an error's
  type and message do not depend on where it surfaces.
- **Constraint:** an exception raised during execution does not reach the caller as its own
  class. It arrives as a `TransformationError` carrying the formatted traceback, also for
  local execution. A pre-hash failure raises its class directly. As things stand, the same
  invalid input therefore produces different exception types depending on where it fails.
- **Question:** which exception classes, and what does "same type" mean across the executor
  boundary?
- **Options:** (a) propagate the exception class out of the executor, locally and from
  remote workers, which is transport work outside this plan; (b) define public classes, and
  require that an executor failure arrive as a `TransformationError` whose message contains
  the same class name and message.
- **Recommendation:** public classes that subclass `TypeError`, so existing
  `except TypeError` code keeps working and tests assert on classes rather than message
  wording. Use (b) as the rule across the executor boundary; (a) can replace it later
  without changing the classes.

## Implementation Phases

### Phase 0: Freeze the compatibility and mixed-admission tables

- Resolve the [open decisions](#open-decisions-before-implementation) first.
- Schedule the [seamless-core prerequisites](#prerequisites-in-seamless-core); they must
  land before Phase 3.
- Encode the schema-kind-to-celltype whitelist as data, not scattered conditionals.
- Encode the scalar admission table (JSON and zero-dimensional `binary` scalars) and its
  range rules.
- Encode the [character rules](#character-rules) (declared celltype and shape to the bytes
  received) as data, next to the whitelist.
- Add table-driven tests before changing construction.

Acceptance:

- Every supported schema dtype/shape has one schema celltype, or explicitly none, and a
  finite declared-celltype whitelist.
- Every unsupported pair has an expected diagnostic.

### Phase 1: Separate schema-derived and declared transformer state

- Add a derived schema-celltype map to `CompiledMixin`.
- Preserve user declarations across schema mutation by pin name.
- Default new pins to declared `mixed` (auto).
- Add inspection/repr support for both maps.
- Implement Stage 1 as one data-independent check, shared by standalone calls, snapshot
  builds, the workflow, and graph import.
- Reject optional-pin declarations on compiled inputs.
- Raise on a declared celltype that no schema allows, and report every incompatible
  declaration as set out in
  [Reporting incompatible declarations](#reporting-incompatible-declarations).
- On graph import with a schema that does not parse, keep declarations as imported and
  block the transformer.

Acceptance:

- Changing `int32` to `int64` retains a declared `int` pin.
- Changing scalar `int32` to array `int32[N]` leaves a retained `int` declaration visibly
  incompatible until corrected. The change emits `CompiledPinCelltypeWarning`, and
  meanwhile the transformer is blocked: a standalone call raises `CompiledPinCelltypeError`
  before binding its arguments, and a bound transformer is blocked without resolving its
  pins.
- Declaring `int` on an array pin emits the same warning; declaring `plain` on any compiled
  input raises.
- Newly added pins appear as declared `mixed` with a derived schema celltype. A pin declared
  `mixed` stays compatible through any schema change except one to a scalar `char` or a
  one-dimensional `char` array.
- A new `char [N]` pin, and an auto pin whose schema changes from `int32` to `char [N]`,
  block the transformer and are reported as a missing declaration until `bytes`, `text`, or
  `binary` is declared.
- Renaming a pin in the schema drops the old declaration; the new name is `mixed`.
- `tf.optional_pins.add(name)` on a compiled transformer raises, and a graph with a compiled
  transformer node that has optional input pins is rejected on import.

### Phase 2: Preserve celltypes in concrete transformations

- Pass the declared celltype map into compiled pretransformation construction.
- Write each input tuple with its declared celltype.
- Cover direct, deferred, snapshot, workflow-backend, and Dask construction paths.
- Remove any compiled-only assumption that all input pins are `mixed`.

Acceptance:

- An `int` compiled pin is recorded as `int`.
- A `binary` compiled pin is recorded as `binary`.
- A declared `mixed` compiled pin remains `mixed` and carries the schema needed for its
  restricted validator.

### Phase 3: Add pre-hash compiled-pin validation

- Implement one sync/async-capable Stage 2 validator over prepared pin tuples and schema
  parameters, with a pre-hash mode that fetches no input buffer and a full mode. It must not
  depend on a Transformation object, so that the executor can call it.
- Run it in pre-hash mode after dependency resolution, before `tf_get_buffer()`.
- Reject values that read as None first, then validate declared celltype readability.
- Apply mixed taxonomy classification only to pins declared `mixed`.
- Apply dtype/shape/range/layout refinements without coercion.

Acceptance:

- Invalid values that can be decided without input data (literal values, null and other
  trivial checksums, HashType disproofs) fail before transformation checksum calculation.
- Computing the transformation checksum fetches no input buffer.
- Direct and deferred inputs produce the same exception type and message, whichever stage
  raises it.
- A literal and its checksum get the same verdict. On a `float64` schema with a `mixed` pin,
  `tf(b=np.float32(1.5))`, `tf.pins.b = np.float32(1.5)`, and
  `tf(b=Buffer(np.float32(1.5), "mixed").get_checksum())` are all accepted.
- Null on any compiled input pin, whatever its declared celltype, reports the pin, declared
  celltype, and schema type rather than a late CFFI error. Both null checksums (`null\n` and
  `null`) are rejected before hashing. Whitespace-padded JSON null on a `mixed` pin, which
  can only come from a raw buffer, is rejected in the executor.
- The canonical null under `bytes` is `b""`: accepted where the schema admits length 0,
  otherwise a schema refinement error. The non-canonical `null` checksum under `bytes` is
  rejected before hashing.

### Phase 4: Put conversions at the correct boundary

- Ensure workflow edges create ordinary Expression conversions to declared compiled pin
  celltypes.
- Keep converting typed standalone inputs (Cell, Transformation, Expression) to the
  declared pin celltype, at every site that wraps a pin input in a conversion Expression
  (see [Current Code Anchors](#current-code-anchors)), not only in `_convert_pin_arguments`.
- Make a failed conversion raise an error that names the pin, the input celltype, and the
  pin celltype.
- Continue serializing direct Python literals under the declared pin celltype.
- Document the explicit routes for a raw Python value that must be converted first (an
  Expression, or conversion in Python), using the dict-as-JSON example.

Acceptance:

- A typed standalone input of another celltype converts and succeeds when the normal
  conversion table permits it, and otherwise fails with an error that names the pin.
- The same source connected through a workflow edge behaves the same way.
- `set_checksum(checksum, input_celltype=...)` with a celltype other than the pin's
  converts like any other input, and a failed conversion names the pin.

### Phase 5: Executor validation and minimal marshalling

Transformation dicts reach the executor without passing through construction: the
`seamless-run-transformation` replay CLI, remote workers, and any other client that submits
a dict. Construction also leaves data-dependent checks to the executor by design (see
[Validation Placement](#validation-placement-identity-without-input-data)). The executor
therefore never assumes its inputs were validated.

- In `call_compiled_transform`, run the Stage 2 validator in full mode on every input, using
  `__schema__` and the declared pin celltypes in the dict, before building the compiled
  module. A schema input missing from the dict is an invalid transformation, reported by pin
  name, not a `KeyError`.
- Remove native-call coercions that duplicate celltype or Expression conversion.
- Retain only ABI preparation: pointer creation, contiguous/aligned views, output
  allocation, and unboxing of already validated scalar representations. An empty `bytes`
  input is passed as length 0 with a valid non-NULL pointer.
- Generate `unsigned char` for schema `char` in seamless-signature, and pass character
  inputs as the [character rules](#character-rules) define: a pointer and a byte length, no
  terminator, and no copy needed; a scalar `char` as its byte value.
- A marshalling or CFFI type error after executor validation passed is an internal contract
  failure (a validator gap), reported with diagnostic context.

Acceptance:

- A deferred input whose invalidity needs its data fails in the executor, before
  compilation, with the same error as the equivalent literal value at construction.
- A replayed or hand-built transformation dict with a null, missing, or invalid input fails
  in the executor with the same pin-level error, before compilation.
- User type errors are reported by pin/schema validation.
- CFFI/native errors represent ABI/compiler failures or validator gaps, not ordinary input
  classification.
- A kernel receiving an empty `bytes` input sees length 0 and a non-NULL pointer.
- The generated header declares every schema `char` as `unsigned char`, and a byte 0xE9
  reaches the kernel as 233, in a scalar and in an array.

### Phase 6: Workflow persistence and migration

- Round-trip schema and declared celltypes through snapshots and workflow graphs. Together
  they determine validation and marshalling; there is no separate ABI metadata.
- Reject compiled transformer nodes with optional input pins on graph import.
- Reconstruct the derived schema-celltype map rather than serializing it as independent
  authority.
- Reject legacy graphs whose compiled builder state cannot be reconstructed safely, or
  apply one documented compatibility default (`mixed` for undeclared legacy inputs). This
  is open decision D4.

Acceptance:

- A compiled transformer survives graph round-trip with identical declared pin types and
  build behavior.
- Schema mutation after round-trip recomputes the same derived state.

## Test Plan

### Schema and declaration tests

- Every scalar dtype maps to the expected schema celltype.
- Complex and structured scalars, and all arrays other than one-dimensional `char` arrays,
  map to `binary`; a scalar `char` and a one-dimensional `char` array have no schema
  celltype.
- Every compatibility-table entry succeeds.
- Every non-entry fails at build time with the full targeted diagnostic.
- Schema mutation preserves surviving declarations and defaults new pins to `mixed`.
- Auto consistency: for every schema kind that has a schema celltype, a Cell of the schema
  celltype holding a valid value makes the same native call through a `mixed` pin as through
  a pin declared with the schema celltype.
- `mixed` on a scalar `char` or a one-dimensional `char` array, as the default or declared,
  blocks the transformer and is reported as a missing declaration that lists `bytes`,
  `binary`, and (one-dimensional only) `text`. On a `char` array with two or more dimensions
  `mixed` is allowed.
- Reporting: an incompatible declaration is reported when it arises (from a declaration
  change and from a schema change), on every use, on inspection, and after graph import;
  every report lists all incompatible pins; a celltype that no schema allows raises when
  declared, and is imported as a blocked, reported transformer.
- Declaring a celltype for a pin that the schema does not define raises `AttributeError`.
- A graph whose compiled transformer has a schema that does not parse imports as blocked,
  with its declarations unchanged.
- A Stage 1 failure blocks the transformer: a standalone call raises before binding its
  arguments, and a bound transformer is blocked without resolving, converting, or
  validating its pins.
- Declaring a compiled input optional raises; importing a compiled transformer node with
  optional input pins is rejected.

### Null tests

For every declared celltype compatible with a compiled pin, other than `bytes`:

- the canonical null checksum is rejected before hashing, naming the pin, declared celltype,
  and schema type;
- the non-canonical `null` buffer is rejected the same way;
- neither reaches native compilation.

Under `text`, this includes the string `null`, which has the canonical null checksum.

For a `mixed` pin, whitespace-padded JSON null from a raw buffer is rejected in the executor,
before compilation.

For `bytes`:

- null on a wildcard-length character buffer reaches the kernel as length 0 with a non-NULL
  pointer;
- null on a scalar `char` or a fixed-size character array is a schema refinement error;
- a character buffer whose content is exactly `null\n` reaches the kernel as length 0
  (documented collision);
- the non-canonical `null` checksum is rejected before hashing with the targeted error,
  whether it comes from 4-byte content `null` or from a non-canonical JSON null crossing a
  `plain → bytes` edge;
- the executor rejects it the same way in a replayed transformation dict.

### Mixed taxonomy tests

For a pin declared `mixed`, cover all representations explicitly:

- JSON integer, float, and Boolean in compatible and incompatible scalar schemas;
- zero-dimensional binary scalar with the schema dtype, with another dtype of the same kind
  (accepted, subject to range), and with a dtype of another kind (rejected);
- binary arrays with matching and mismatching shape/dtype;
- JSON string rejection, including numeric-looking strings;
- JSON list rejection;
- JSON dict rejection;
- proper Seamless-mixed list containing an ndarray rejection;
- proper Seamless-mixed dict containing an ndarray rejection.

Assert that failures occur before native compilation/calling. Assert that they occur before
the transformation receives a checksum when the input was a literal value, or when the
failure is decidable from its checksum or its HashType word (when available); otherwise,
assert that they occur in the executor.

### Scalar admission tests

- The same zero-dimensional checksum gets the same verdict on a `binary` pin and on a
  `mixed` pin.
- NaN and ±infinity reach the kernel on `float32` and `float64` parameters: from a Python
  `float` literal on a `mixed` pin, and from a zero-dimensional `.npy` of either precision
  on a `binary` or `mixed` pin.
- NaN or infinity given as a literal to a `float` pin fails at serialization with an error
  that names the pin; it is never passed on as null.
- `np.int64(2**40)` on an `int32` parameter is rejected by range.
- `np.float64(5.0)` on an `int32` parameter is rejected: a floating-point kind is not an
  integer kind.
- A finite `np.float64` outside the `float32` range on a `float32` parameter follows D2.
- A structured zero-dimensional value with a different dtype, a character scalar with a
  different dtype, and a shape-`(1,)` array on a scalar parameter are rejected.
- A literal and its checksum get the same verdict, for NumPy scalars of every dtype.

### Character tests

- `bytes` on a scalar `char`: a one-byte value reaches the kernel as its byte value; zero or
  two bytes are a schema refinement error.
- `bytes` and `text` on `char [N]`: N is the byte count, also for non-ASCII text; NUL bytes
  inside the data arrive unchanged.
- `text` `ACGT` on `char [N]` arrives with N=4; the same Cell over a `text → bytes` edge on a
  `bytes` pin arrives with N=5.
- `bytes` and `text` with 3 or 5 bytes on `char [4]` are a schema refinement error; nothing
  is padded or truncated.
- `text` on a scalar `char`, and `bytes` or `text` on `char [N, 4]` or `char [N, M]`, are
  Stage 1 failures.
- On `binary` pins, and on `mixed` pins of multidimensional `char` arrays, exact `S1` of
  the schema's shape passes. A zero-dimensional `S4` on `char [4]`, an `S4` array of shape
  `(N,)` on `char [N, 4]`, a raw byte buffer read under `mixed`, and a JSON string are
  rejected.
- Every row of [Choosing a declaration](#choosing-a-declaration) holds, both as literals and
  as Cells over workflow edges: accepted inputs reach the kernel as described, and the listed
  rejections are reported at the pin.
- `text` `""` on `char [N]` arrives as N=0 with a non-NULL pointer.
- No test relies on a byte after the data.

### Conservative-scope tests

These tests must mention the scope explicitly in their names/docstrings:

- A liberal upstream `mixed` Cell converts over a workflow edge to an `int` pin.
- A liberal upstream `plain` list converts over an allowed workflow edge to `binary`.
- A proper mixed structure is rejected when connected directly to a compiled `mixed` pin.
- An Expression extracting a binary/scalar member from that same proper mixed structure
  can feed the conservative pin.
- A typed standalone input of another celltype converts to the pin celltype; a failed
  conversion raises an error that names the pin, the input celltype, and the pin celltype.
- `set_checksum` with an `input_celltype` other than the pin's celltype converts, bound and
  unbound; a failed conversion names the pin.
- The dict-as-JSON example works through a workflow edge, a typed standalone input, an
  explicit Expression, `json.dumps`, and `set_checksum` on the `text` pin.

The purpose is to prevent a future implementation from misreading “conservative pins” as
“conservative workflows.”

### Checksum and cache tests

- Changing a declared pin from `mixed` to `int` changes the concrete transformation
  checksum.
- Changing the schema changes transformation identity even where the declared celltype is
  unchanged.
- Two equivalent workflow conversions that yield the same declared pin celltype and input
  checksum may share the compiled transformation cache.
- Rejected inputs never populate the transformation cache.
- Computing the checksum of a compiled transformation whose inputs are remote fetches no
  input buffer, and a cache hit returns the result without fetching any input.

### Execution tests

- C/C++/Fortran/Rust/Go paths, where supported, receive already validated native scalars
  and buffers.
- Sync, async, direct, delayed, workflow, and Dask paths agree.
- Native width/range overflow, a scalar of the wrong kind, an array or structured dtype
  mismatch, non-native byte order of an array or structured value, bad shape, and bad
  structure layout are reported before compilation.
- A replayed or hand-built transformation dict with a null, missing, or invalid input fails
  in the executor with the same pin-level error as construction, before compilation.

## Checksum And Compatibility Consequences

Fixing the pin boundary intentionally changes transformation checksums whenever the stored
pin celltype changes. This is correct: an `int` pin and a `mixed` pin have different
acceptance and conversion semantics.

Do not preserve old checksums by continuing to encode every input as `mixed`. Old cached
compiled results may only be reused when the full corrected transformation definition,
including schema and pin celltypes, has the same checksum.

Declared `mixed` inputs that remain encoded as `mixed` may retain their old checksum for
valid values, depending on the rest of the payload. Newly enforced rejection does not
require rewriting successful values merely to force a cache miss; the schema is already
part of the definition. Add an explicit implementation-version field only if execution
semantics for an otherwise identical definition change in a way that can make an old cached
result observably invalid.

Generating `unsigned char` for schema `char` changes no checksum: `__header__` is excluded
from identity. Kernel source that declares the parameter as plain C `char` must be updated to
the C type `unsigned char` (Rust
`u8`); the updated source has a new code checksum.

The NaN change in [Prerequisites In seamless-core](#prerequisites-in-seamless-core) changes
checksums and behaviour beyond compiled transformers:

- Under `mixed`, a value containing NaN or infinity gets a new checksum. The old buffers
  (`NaN\n`, JSON with `NaN`) could not be read back, so no readable value loses its checksum.
- Under `plain` and `float`, serializing NaN or infinity now raises instead of writing
  `null\n`. A Python transformer whose `plain` or `float` result contains NaN now fails
  instead of silently producing null.

## Error Taxonomy

Use stable, targeted failures:

- `CompiledPinCelltypeError`: declared pin celltype is incompatible with schema. This is a
  Stage 1 failure: it blocks the transformer. `CompiledPinCelltypeWarning` carries the same
  diagnostic when the incompatibility arises. A celltype that no schema allows raises when
  declared. See
  [Reporting incompatible declarations](#reporting-incompatible-declarations).
- Optional-pin declaration on a compiled input: rejected when declared and on graph import.
- Null on a compiled pin (C ABI rule 4), for every declared celltype: a targeted pin-level
  error naming the pin, declared celltype, and schema dtype/shape. It is never reported as a
  CFFI error or a `KeyError`.
- Non-canonical `null` checksum on a `bytes` pin: a targeted pin-level error stating that
  the checksum is ambiguous and naming both possible origins (4-byte content `null`, or a
  non-canonical JSON null).
- `CompiledMixedValueError`: a declared `mixed` pin contains JSON text/container or proper
  Seamless-mixed data. The message lists the other declarations the whitelist allows for the
  parameter, so that a user of an auto pin sees which explicit declaration converts the
  input (for example `binary` for a JSON list on a numeric array).
- `CompiledPinSchemaError`: value has the right pin celltype but violates dtype, range,
  shape, length, byte-order, alignment, or layout requirements.
- Existing dependency errors remain dependency errors.
- Existing conversion errors remain Expression conversion errors, raised before compiled
  transformation construction by an edge or by the conversion of a typed standalone input.
  They name the pin, the input celltype, and the pin celltype. In a workflow they are
  recorded on the pin and block the transformer (`blocked-by-error`; see
  `seamless_workflow/reactive.py`, `Reactive._derive_transformer`).

Whether these are public exception classes or targeted `TypeError` messages, and how the
category survives an error raised in the executor, is open decision D5. Preserve the
category distinction in messages and tests either way.

## Out Of Scope

- Redesigning the global Seamless conversion table.
- Adding unrestricted recursive Python-object marshalling to compiled functions.
- Treating proper Seamless-mixed serialization as a native ABI.
- Defining a new scalar `complex` celltype.
- Redesigning compiled result pins or the current multi-output aggregate. A follow-up must
  decide whether single outputs acquire schema-derived result celltypes and how multiple
  typed outputs avoid conflating native output structure with unrestricted `mixed`.
- Optional compiled inputs: the C ABI has no absent argument (C ABI rule 3).
- Changing ordinary Python/bash transformer pin semantics. The generic `validate_pin_null`
  also misses the non-canonical `null` buffer on ordinary pins; fixing that there is a
  separate change.
- Changing how seamless-core reads the non-canonical `null` buffer under `bytes`.

## Definition Of Done

The work is complete when:

- compiled transformer schemas derive one inspectable schema celltype per input, or none for
  a scalar `char` or a one-dimensional `char` array; it generates the declaration whitelist,
  and auto consistency holds wherever it exists;
- `mixed` is auto; it is compatible with every schema parameter except a scalar `char` or a
  one-dimensional `char` array, which require an explicit `bytes`, `text`, or `binary`
  declaration; every incompatible or missing declaration is reported when it arises, on use,
  on inspection, and after import;
- declared pin celltypes survive schema edits and graph/snapshot round-trips;
- Stage 1 failures (no header, incomplete metavars, incompatible schema/pin declarations)
  block the transformer before any input is considered;
- optional pins are rejected on compiled transformers, when declared and on graph import;
- concrete compiled transformations preserve every declared input celltype;
- declared `mixed` pins accept only compatible pure binary or JSON scalar values and reject
  JSON strings, JSON containers, and proper Seamless-mixed values;
- numeric scalar parameters admit JSON and zero-dimensional `binary` scalars by kind and
  range under one table, on `mixed` and `binary` pins alike, while arrays, structured
  values, and characters keep exact dtype;
- NaN and infinity reach native code only as NumPy values, and the seamless-core
  prerequisites are in place;
- a literal is validated as its serialized value, so it gets the same verdict as its
  checksum;
- no value that reads as None reaches native compilation or calling, on any compiled pin;
  empty `bytes` values reach the kernel as length 0 with a non-NULL pointer; the `null\n`
  content collision under `bytes` is documented, and the non-canonical `null` checksum under
  `bytes` is rejected; the `null` string collision under `text` is documented;
- character inputs follow the [character rules](#character-rules): a pointer and a byte
  length, without a terminator; `text` delivers its UTF-8 value without the serialization
  newline; `bytes` and `text` only on the shapes the whitelist lists; `binary` and `mixed`
  only exact `S1`; the generated header declares `unsigned char`;
- differently typed inputs are converted before the pin (workflow edges, typed standalone
  inputs), never inside compiled transformation construction, and a failed conversion
  names the pin;
- computing a compiled transformation checksum fetches no input buffer;
- the executor runs the full Stage 2 validator before compiling, so invalid values never
  reach native compilation or calling and never produce a cached result, including in
  transformation dicts that bypassed construction;
- checksum changes caused by corrected pin metadata are accepted and covered by tests;
- documentation states plainly that the conservative baseline is scoped to the compiled
  pin, not to upstream workflow data.
