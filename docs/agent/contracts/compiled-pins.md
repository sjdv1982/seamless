# Compiled Pins (Contract)

This page defines the contract for the **input pins of compiled transformers**: which pin celltypes may be declared for a schema parameter, which values each declaration admits, where validation runs, and what a failure does. It is stricter than the general pin contract because a compiled pin feeds a native C ABI call.

**Scope.** Compiled **result** pins and multi-output packaging are out of scope (see "Result types" in `contracts/compiled-transformers.md`). The general pin layer — reaching pins, which pins exist, the two write families, conversion at the pin boundary, and pin and transformer state reporting — is `contracts/pins.md` and is not repeated; typed inputs are converted into a compiled pin exactly as into a Python or bash pin. What this page adds is the restricted set of pin celltype declarations, the schema-bound validation, and how a compiled validation failure is reported.

**Terminology.** `char` always means the **seamless-signature schema dtype**, never a C type. The C type generated for a schema `char` is `unsigned char`; where a C type is meant it is named as such ("the C type `unsigned char`", "plain C `char`").

## 1. Foundation: the C ABI contract

1. **The schema is the only source of the ABI.** `seamless-signature` generates the C header (`tf.header`) from the schema alone; CFFI builds the extension module from that header; the Python call signature and all marshalling rules derive from the same schema. `__schema__` is part of transformation identity; `__header__` is derived from it and excluded from identity (`contracts/compiled-transformers.md`, "Transformation identity and caching"). A rule that changes how an input is marshalled therefore belongs in the schema, not in builder state.
2. **No header, no transformer.** Until a C header can be generated, the transformer cannot run, whatever its input data: this is a Stage 1 failure, and so is every other check that needs no input data (section 5).
3. **Every schema input is a positional C argument.** `transform()` has fixed arity: scalars by value, arrays and character buffers as `const T *`, and input wildcard dimensions as leading `unsigned int` arguments. C has no absent argument, so **compiled transformers have no optional pins.** No API route declares one (optional pins come only from Python signature defaults, `contracts/pins.md`), and graph import rejects a compiled transformer node that carries one. An optional-pin declaration is never translated into "drop the pin".
4. **C has no None.** A compiled input whose value reads as None under its declared pin celltype is rejected, whatever that celltype is, `mixed` included. Detection is by *reading*, not by checksum equality: the canonical null `null\n`, the non-canonical buffer `null`, and (under `mixed`) whitespace-padded JSON null all read as None.
   - **`bytes` is not an exception.** Under `bytes` the canonical null checksum reads as `b""`, which is how Seamless stores empty bytes. An empty `bytes` value is passed as **length 0 with a valid, non-NULL pointer**, never as a NULL pointer (Rust's `slice::from_raw_parts` requires a non-null pointer even at length 0; `memcpy(dst, NULL, 0)` is undefined behaviour in C before C2y; an empty array through the `binary` path already arrives non-NULL). Length 0 is valid only where the header takes a pointer and a wildcard length; for a scalar `char` or a fixed-size character array it is a schema refinement error.
   - **Two collisions no check can resolve:**
     - Under `bytes`, content that is exactly `null\n` has the canonical null checksum. Its checksum and buffer are identical to those of empty bytes, so nothing — the executor included — can tell them apart, and it reaches the kernel as length 0.
     - Under `text`, the string `null` serializes to `null\n`, the canonical null, which `text` reads as None; a `text` pin therefore rejects it, and no check can distinguish it from a real null. The empty string is unaffected: it is stored as `\n`, reads as `""`, and is passed as length 0 where the schema admits it.
   - **The non-canonical null on a `bytes` pin is rejected.** The non-canonical null checksum (content `null`, no trailing newline) is never produced by empty bytes: the serializer writes `null\n`, and canonicalization maps `sha256(b"")` to the canonical null. Its origin is ambiguous — real 4-byte content, or a non-canonical JSON null that crossed a trivial `plain → bytes` conversion — and no reading is right for both, so a `bytes` pin rejects it with a targeted error naming both possible origins. The test is checksum-level and needs no buffer.
   - A `binary` character array (NumPy `S1`) has neither problem and is the choice when the content is arbitrary.
5. **NaN and infinity are NumPy values.** JSON cannot hold them, and `float` is a checksum-level subtype of `plain`, so serializing NaN or infinity under `plain` or `float` raises. Under `mixed` they are serialized as NumPy data (a zero-dimensional `.npy` at the top level; a NumPy value inside JSON when nested) and read back as `np.float64(nan)` / `np.float64(inf)`. They therefore reach a compiled transformer only as a zero-dimensional `binary` scalar, which a floating-point parameter admits whatever its precision.
6. **A schema `char` is an unsigned byte, passed without a terminator.** The generated header declares every schema `char` — scalar, array element, struct field — as the C type `unsigned char`, because plain C `char` has implementation-defined signedness while the transformation checksum stays the same. Kernels declare `unsigned char` (Rust `u8`). A character array is passed as a pointer to its bytes plus its length (the input wildcard, or the fixed size). **No NUL terminator is added**, so no copy is needed and the pointer may point directly into the input buffer. The length is authoritative: bytes at and beyond it are not part of the input, and reading them is undefined behaviour (under `text`, the next byte is usually the newline that serialization appends). NUL bytes inside the data are ordinary data.

## 2. The conservative baseline is scoped to the pin

The conservative compatibility baseline governs exactly one pair: **(schema parameter, declared compiled-pin celltype)**. It does **not** constrain the celltype of an upstream Cell and does not prohibit liberally typed workflow data. Conversion into the pin's celltype is normal and expected, and it happens *before* the pin:

```
liberally typed upstream Cell
   → explicit workflow edge / Seamless Expression conversion
   → conservatively typed compiled pin (checksum already has the pin celltype)
   → compiled transformation construction and schema validation
```

A `mixed` Cell may feed an `int` pin through an empty-path `mixed → int` Expression; a `plain` list may feed a `binary` array pin where that conversion is valid; a Seamless-mixed structure may be navigated or transformed by an explicit Expression whose scalar or binary result then feeds the pin. The Seamless-mixed structure itself is not a valid direct value of a compiled `mixed` pin (section 3a).

Once the pin checksum is known, **neither transformation construction nor the executor performs a second round of broad conversion**. Between them they may only:

- canonicalize checksums, and reject values that read as None;
- validate readability as the declared pin celltype;
- classify and reject disallowed representations on a `mixed` pin;
- resolve or materialize a value or buffer when a schema check actually needs it;
- validate schema refinements;
- prepare an already-valid value for the native call, without semantic coercion.

### Worked example

A C function that parses a JSON document receives UTF-8 text. The dict is `plain` data, but the compiled pin is declared `text`: **a pin celltype describes what the C function receives, not what the upstream data is.** `plain` is not a compiled declaration at all, and a `mixed` compiled pin rejects JSON containers. The schema parameter is a one-dimensional character array (`doc`, dtype `char`, shape `[N]`); the kernel gets the UTF-8 bytes and their length, without a terminator.

- **Bound, in a workflow:** put the dict in a `plain` Cell and connect it to the `text` pin; the edge converts `plain → text`.
- **Unbound, typed input:** pass a `plain` Cell, Expression or Transformation as the argument, or assign it as the pin's source; it is converted exactly as an edge would convert it. A failed conversion raises an error naming the pin, the input celltype and the pin celltype.
- **Unbound, raw Python dict:** a raw value has no celltype. A literal passed or assigned to a pin means exactly `Buffer(value, pin_celltype).get_checksum()`, so passing the dict itself gives the `text` checksum of `str(d)` — Python's repr, which is not JSON. Make it JSON text first: `Expression(checksum, input_celltype="plain", celltype="text")`, or `json.dumps(d)` in Python. The two routes format the JSON differently and give different input checksums; both are valid.
- **A checksum works the same way.** A Pin has an underlying Expression: `set_checksum` sets that Expression's *input* checksum, and `.checksum` is its result, so `set_checksum(cs, input_celltype="plain")` converts to the pin celltype like any other input. The conversion is not performed during the `set_checksum` call. Only when the input celltype equals the pin celltype is no conversion involved.

Three points that are easy to misread:

- "Conservative" restricts the pin **declaration**, not conversion.
- An input celltype equal to the pin celltype is the **special case**, not the rule.
- Pins hold **checksums, not values**: a literal is serialized under the pin celltype when it is passed or assigned. That is the celltype's contract, not a conversion.

## 3. Three sources of authority

### 3a. Natural mixed-value admission

What a declared `mixed` pin accepts, by the actual representation behind the checksum:

| Actual `mixed` representation | Direct compiled `mixed` pin policy |
|---|---|
| Pure binary / NumPy `.npy` | Accept when the schema can consume the scalar, array or structure |
| Pure JSON integer/float/Boolean | Accept for a compatible native scalar schema |
| Pure JSON string | Reject; declare the pin `text` when textual input is intended |
| Pure JSON list/dict | Reject |
| Proper Seamless-mixed list/dict containing NumPy values | Reject |
| Null (any buffer reading as None) | Reject before ordinary value validation (rule 4) |

"Proper mixed" means Seamless-specific mixed serialization that is neither pure `.npy` nor pure JSON; it has no natural C ABI. JSON containers have no general native ABI either: for a JSON document, declare a `text` pin and parse explicitly; for list data meant as an array, put an explicit conversion to `binary` on a workflow Expression before the pin. A JSON string is not native text at the boundary — it is JSON-quoted; a `text` target lets the `mixed → plain → text` chain produce unquoted UTF-8.

### 3b. Schema-derived celltypes

| Schema parameter | Schema celltype |
|---|---|
| Signed or unsigned integer scalar | `int` |
| Floating-point scalar | `float` |
| Boolean scalar | `bool` |
| Complex or structured scalar | `binary` |
| Scalar `char`, or one-dimensional `char` array | none: an explicit declaration is required |
| Every other array, of any dtype and number of dimensions | `binary` |

Integer width and signedness, float precision, NumPy dtype, shape, byte order, alignment and struct layout are **schema refinements**, not celltypes. The schema celltype never replaces the declared pin celltype, and a `mixed` pin is never resolved to it. Its one job is to generate the whitelist of compatible declarations (3c), plus diagnostics and inspection (section 4).

**Auto consistency** — the property that makes `mixed` safe wherever a schema celltype exists: *a value of the schema celltype that satisfies the schema, serialized under that celltype, is accepted by a `mixed` pin and makes the same native call as on a pin declared with the schema celltype.* It holds because `int`, `float` and `bool` convert to `mixed` without changing the checksum (through `plain`) and read under `mixed` as the same JSON scalar, and because `binary` converts to `mixed` without changing the checksum and both celltypes use the same parser. The property concerns values serialized under the schema celltype. A checksum that is not canonical for it can behave differently — an `int` pin reads JSON `5.7` as 5, while a `mixed` pin on an integer parameter rejects it. That is the documented `int` reading, not an auto inconsistency.

**No auto for a scalar `char` or a one-dimensional `char` array.** There the natural celltype is ambiguous: `bytes`, `binary` and (for the array) `text` all fit, and they accept different inputs. `mixed` cannot stand in. Converting `bytes` to `mixed` keeps a JSON-parsable buffer as that JSON value (`b"1"` becomes integer 1), turns other UTF-8 content into a JSON string (`b"ACGT"` becomes `"ACGT"`), and turns only non-UTF-8 content into a zero-dimensional `S{len}` array — all rejected on `char [N]`. `text` converts to `mixed` as a JSON string and fails the same way. Only `binary` agrees with `mixed`, and making it the schema celltype would turn auto into a silent choice of the narrowest option. A `char` array with two or more dimensions keeps auto, because `binary` is its only other declaration and it agrees with `mixed`.

### 3c. User-declared pin celltypes: the whitelist

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

One formula generates the table: where a parameter has a schema celltype, the compatible declarations are the schema celltype, `binary` and `mixed`; where it has none, they are listed explicitly. Every compatible declaration is therefore one of `int`, `float`, `bool`, `bytes`, `text`, `binary`, `mixed`. `bytes` and `text` carry only a length, so they cannot fill a multidimensional array (`[N, M]` has no single split; `[N, 4]` would need a reshape rule). `plain`, `str`, the other code and text celltypes, `checksum`, and the deep and structural celltypes are **not** compatible with any native parameter.

This is a **whitelist, not a test of whether some generic conversion path happens to exist**. It grows only when a specific native representation and validation rule are documented — never because the native-call library happens to coerce a value successfully.

### `mixed` is "auto"

`mixed` is the default declaration, and it lets the schema decide which values pass. There is no separate auto state: declaring `mixed` explicitly is the same as the default, and resets a pin to auto. On a compiled input pin, `mixed` has one meaning: *accept only natural mixed values compatible with the schema (3a), reject every other mixed representation, and apply the schema refinements without general value coercion.* **There is no unrestricted, non-schema-bound `mixed` mode for compiled input pins.** Auto exists for every parameter except a scalar `char` or a one-dimensional `char` array, which need an explicit declaration.

## 4. Declaration state, schema changes and reporting

Assigning a schema is an **atomic builder-state update**:

1. parse and validate the prospective schema (a schema that does not parse raises and changes nothing);
2. derive the prospective schema-celltype map;
3. **preserve the declared celltypes of surviving pin names**, compatible or not;
4. give newly introduced pins the declaration `mixed` (auto);
5. remove the declarations of pins that disappeared;
6. rebuild the call signature and the schema-derived metadata;
7. recompute Stage 1 and report every incompatible declaration.

A schema change never resets declared pins to `mixed`, and never replaces a `mixed` declaration with an explicit one. A `mixed` pin stays auto; it becomes incompatible only when its parameter becomes a scalar `char` or a one-dimensional `char` array, where it is reported as a *missing declaration*. Any other declaration can become incompatible too. Either way it is kept and reported, never silently changed.

Pins are identified by name:

- **A pin exists only once the schema defines it.** Its celltype cannot be declared before that: the compiled celltypes wrapper raises `AttributeError` for an unknown pin.
- **"Either order" applies to existing pins.** A user may change a declaration first and then the schema, or the other way round; temporary builder inconsistency is allowed. A new pin needs the schema first.
- **Renaming a pin in the schema removes one pin and adds another**: the old name's declaration is dropped and the new name starts as auto. This is intended.

**Absent or unparsable schema.** The API prevents it, but graph import can produce it. Declarations are then kept as imported, without validation, and the transformer has a Stage 1 failure on its schema. Declarations are removed and compatibility-checked only against a schema that parses.

### Reporting incompatible declarations

A declared celltype that the schema does not allow is always reported, never silently accepted, reset or replaced.

- A celltype that **no** schema allows (anything outside `int`, `float`, `bool`, `bytes`, `text`, `binary`, `mixed` — e.g. `plain`, `str`, `deepcell`) raises immediately when declared, because no schema edit can make it valid. Graph import can still bring one in: it is imported as declared and reported like the case below.
- A celltype that **some** schema allows but the current one does not is accepted, so that schema and declaration can be edited in either order, and it is reported:
  - **when it arises**, from a declaration change or a schema change, as a `CompiledPinCelltypeWarning` carrying the diagnostic;
  - **whenever the transformer is used**, as a Stage 1 failure with `CompiledPinCelltypeError` (section 5);
  - **on inspection**: the repr and the `schema_celltypes` view mark the pin incompatible;
  - **after graph import or snapshot restore**, the same way, as if it had just arisen.
- Every report lists **all** incompatible pins, not only the first.
- While the schema is absent or unparsable, compatibility cannot be checked: the schema failure is reported instead, and declarations are checked as soon as a schema parses.

The diagnostic names the pin, the declared pin celltype, the schema dtype and shape, the schema celltype (or that there is none), and the allowed declarations:

```text
Compiled pin 'x' declares celltype 'int', which is incompatible with
schema dtype 'float64', shape [N] (schema celltype 'binary'). Allowed pin
celltypes are 'binary' and 'mixed'.
```

```text
Compiled pin 'seq' (schema dtype 'char', shape [N]) needs an explicit
celltype: 'bytes', 'text', or 'binary'. 'mixed' (auto) is not available
for this parameter.
```

### Inspecting the two celltypes

The declared and the schema celltype are both exposed, on standalone and bound compiled transformers alike:

- `tf.celltypes.x` is the **declared** pin celltype (`contracts/pins.md`, *Celltypes*).
- **`tf.schema_celltypes`** is a **read-only mapping** from each schema input name to its schema celltype (3b), with `None` where the parameter has none. It is derived from the schema alone and never from the declarations; it is empty while the schema is absent or unparsable. Its repr carries the incompatibility diagnostic when a declaration is incompatible. The transformer's repr shows both the declared and the schema celltypes.

## 5. Two validation stages, and what a failure does

### Stage 1: data-independent

Stage 1 is decided from builder state alone:

- the schema is set and parses, so that a C header can be generated;
- the metavars are complete;
- every declared pin celltype is compatible with its schema parameter (3c).

(An optional compiled input cannot reach Stage 1: no API route declares one, and graph import rejects it — rule 3.)

**A Stage 1 failure is the transformer's own failure**, whatever its inputs, and **no input is resolved, converted or validated**:

- a standalone call or snapshot build raises the diagnostic before binding its call arguments;
- a bound workflow transformer is **`failed`**: `tf.block_reason` is `None`, and `tf.exception` holds the Stage 1 diagnostic (with its class name, section 9). No pin is resolved and no transformation is built.

Graph import brings in a Stage 1 failure as declared — an incompatible or unknown declared celltype, an absent or unparsable schema, a legacy `char` input without a declaration (section 10) — and the imported transformer is `failed` until builder state is made consistent. (Builder state may be temporarily inconsistent; a node with optional compiled inputs is the one case graph import rejects, because it can never become valid.)

### Stage 2: data-dependent

Stage 2 runs per transformation. It needs input checksums, and for some checks buffers or values. Its steps, in order, are in section 6: null (rule 4); readability of each checksum as its declared pin celltype; `mixed` representation classification (3a); schema refinements — dtype, width and range, shape and wildcard consistency, byte order, alignment, layout — including the scalar and character rules of sections 7 and 8.

### What a Stage 2 failure does to a bound transformer

There are two kinds of failure, and they differ in whether the pin **has a valid checksum for its declared celltype**:

| Failure | Transformer state | `tf.block_reason` | `tf.exception` |
|---|---|---|---|
| A pin has **no valid checksum** for its celltype: its upstream failed, the Expression conversion into the pin celltype failed (section 9), or its checksum is not deserializable as the pin celltype | `blocked` | a `blocked-by-error` entry for that pin | `None`; the pin's own failure is recorded on the pin (`pin.state == "failed"`, `pin.exception`) |
| Every pin has a valid checksum, but **compiled validation rejects one**: `mixed` admission (3a), the scalar rules (section 7), the character rules (section 8) or another schema refinement | `failed` | `None` | the diagnostic, naming the pin, with its class name (section 9) |

The first row is the general rule of `contracts/pins.md` and `contracts/node-state-lifecycle.md`: no transformation is built from a pin without a valid checksum, so nothing of the transformer's own has failed. In the second row the pin is fine and the compiled transformer cannot use its value, so the failure is the transformer's.

**The state follows this rule, not where the check runs.** The same rejection detected before hashing and detected in the executor gives the same state, the same exception class and the same message.

**Null is not yet classified.** Whether a null checksum on a compiled pin counts as "valid for its celltype" is deferred. So is the state of a transformer whose compiled pin is rejected for null: rule 4, the non-canonical null on a `bytes` pin, and a `bytes` canonical null (`b""`) that fails a length refinement. Either row may apply; do not rely on one.

### Validation placement: identity without input data

Computing a transformation checksum must not require input buffers. Python transformations already have this property (identity comes from input checksums, and HashType checks never fetch a buffer), and compiled transformations keep it. Otherwise a cache hit would still download every input, and a large remote array would be fetched to the client only to compute identity. Stage 2 therefore runs in two places.

**Before hashing, at construction: only checks that need no input buffer fetch.**

- Inputs supplied as **literal values** (standalone call arguments, pin assignments): the value is serialized under the declared pin celltype, and every Stage 2 check applies to the value *as read back from that local buffer*. The Python object before serialization plays no part, so a literal and its checksum `Buffer(value, pin_celltype).get_checksum()` get the same verdict. For example, `np.float32(1.5)` given to a `mixed` pin is serialized as JSON `1.5` and validated as that JSON number, not as a `float32`.
- **Every** input: checksum-level facts — the null checksums (under `bytes`, the non-canonical one too), the Boolean virtual values, and the other trivial checksums (`{}`, `[]`, `""`).
- **Every** input: HashType facts available without fetching the buffer — readability disproofs for the declared celltype, `mixed` storage classes that are always rejected (JSON and Seamless-mixed objects and arrays), and NumPy dtype class and rank.

**In the executor, before compilation: every Stage 2 check on every input**, whatever construction already checked. This is the guarantee; the pre-hash checks are an early-fail optimization.

Rules:

- A pre-hash check may reject only what the executor would also reject, with the same exception class and message, and it never changes what is accepted.
- Pre-hash checks use only sound facts. A `JSON_STRING` HashType word does not prove a JSON string, because JSON `true`, `false` and `null` are classified `JSON_STRING` (`contracts/hashtype.md`). HashType does not record exact dtype, shape, byte order or wildcard sizes, so those checks run in the executor unless the input was a literal.
- **The invariant: an invalid input never reaches native compilation or the native call, and never produces a cached result.** An invalid input *may* acquire a transformation checksum when its invalidity cannot be decided without its data.
- Whether a failure surfaces before hashing or in the executor may depend on local state, such as whether a HashType word is cached. Its class, its message and the resulting node state do not.

## 6. The concrete compiled transformation

Every concrete compiled transformation's input tuple carries its **actual declared pin celltype**:

```python
{
    "a": ("int", None, checksum_hex),
    "array": ("binary", None, checksum_hex),
    "auto_pin": ("mixed", None, checksum_hex),
}
```

The schema remains part of the transformation definition and checksum. A declared `mixed` pin stays `mixed` in the concrete tuple — its restricted meaning comes from the schema plus the compiled mixed-value validator — and is never rewritten to the schema celltype after the workflow has targeted the pin.

**Stage 2 validation order**, once Stage 1 has passed and every input has a concrete checksum. Construction applies each step only as far as it can be decided without fetching an input buffer; the executor applies every step in full, before compilation.

1. Canonicalize checksums according to their declared pin celltypes.
2. Reject every input that reads as None (rule 4). **No pin is dropped**: compiled transformers have no optional pins. Under `bytes` the canonical null reads as `b""` and is left to schema refinement, while the non-canonical `null` checksum is rejected.
3. Validate that every checksum is deserializable as its declared pin celltype.
4. For a declared `mixed` pin, classify the actual mixed representation and apply the admission table (3a).
5. Apply schema refinement validation (sections 7 and 8).

Construction computes the transformation checksum only after its pre-hash checks pass. Synchronous and asynchronous (deferred) construction share this order.

Validation follows the conversion engine's economy: checksum-only facts first, then cached HashType and storage classification, then buffer inspection, and full value deserialization only for schema checks that require it. Classification is **reject-only**: it never rewrites or canonicalizes a successful non-null value.

## 7. Native scalar rules

A scalar parameter is passed to C **by value**, so its value is always converted to the C type, and the rules below decide only which values are *admitted*. An array is passed as a **pointer to its buffer**, so its dtype is its memory layout: a mismatch would need a copy and a cast, which is exactly the hidden conversion this contract rules out. Numeric scalars are therefore admitted **by kind and range**, arrays by **exact dtype**.

For pins declared `mixed` or `binary`, one admission table covers JSON scalars and zero-dimensional numeric `binary` scalars alike; an admitted value is passed on without further semantic coercion:

| Schema scalar | JSON scalar | Zero-dimensional `binary` scalar |
|---|---|---|
| Signed/unsigned integer | Python `int`, excluding `bool` | any signed or unsigned integer dtype |
| Floating point | Python `float`; a Python `int` only when the target type represents it exactly (D1) | any floating-point dtype; an integer dtype only when the target represents it exactly (D1) |
| Boolean | Python `bool` only | `bool` dtype only |
| Complex | no JSON representation | any complex dtype |
| `char` | no JSON representation; a JSON string is rejected. A scalar `char` does not allow `mixed` | exact dtype `S1` |

After admission, the range of the schema type is enforced:

- integers must lie within the native range;
- for floating-point values, and for each part of a complex value, NaN and ±infinity pass through (rule 5) and rounding within the finite range is accepted, but **a finite value outside the target's finite range is rejected** under every declared celltype (**D2** — converting such a value to C `float` is undefined behaviour, C11 6.3.1.5). JSON `1e300` or `np.float64(1e300)` on a `float32` parameter is rejected; JSON `0.1` on `float32` is accepted with ordinary rounding.

The decisions behind the table:

- **D1:** an integer — JSON or `binary` — is accepted on a floating-point parameter **only when the target type represents it exactly**, and rejected otherwise. Integers beyond 2^53 for `float64` or 2^24 for `float32` are not all exactly representable. JSON has a single number type, so `5` versus `5.0` is a serialization accident; silent precision loss is not.
- **D3:** a numeric scalar parameter admits a zero-dimensional `binary` value **by kind, not by exact dtype**, under the same range rules as a JSON scalar, on `mixed` and `binary` pins alike, NaN and infinity included. Structured scalars, character scalars, and **all** arrays — including shape-`(1,)` arrays on a scalar parameter — keep exact dtype and native byte order.

The dtype of an admitted zero-dimensional value is not compared with the schema dtype, and its byte order plays no part. The rule is the same for `mixed` and `binary` pins: converting `binary` to `mixed` does not change the checksum, so both give the same checksum the same verdict. A JSON scalar carries no dtype, and neither does a finite NumPy scalar serialized under `mixed`, which is written as a JSON number. `np.float32(1.5)` as a zero-dimensional `.npy`, `np.float64(1.5)` as one, and JSON `1.5` have **different checksums but make the same native call**; they are cached separately, which duplicates a result but never returns a wrong one.

There is **no float-to-int truncation** in the schema-bound validator, for JSON or `binary` scalars. A user who wants Seamless `float → int` semantics puts that conversion on a workflow edge feeding an `int` pin. For a pin declared `int`, `float` or `bool`, ordinary celltype serialization and Expression conversion semantics remain authoritative, including the documented Seamless scalar conversion behaviour; those celltypes cannot hold NaN or infinity. The table above exists because `mixed` and `binary` values have no Seamless scalar conversion semantics of their own.

## 8. Character rules

A schema `char` parameter receives bytes (rule 6). The declared pin celltype decides how the input is read into bytes; once read, the bytes are passed the same way whatever the celltype, so the kernel cannot tell which celltype delivered them.

| Declared pin celltype | Schema shapes | Bytes the kernel receives |
|---|---|---|
| `bytes` | scalar `char`; one-dimensional array | the `bytes` value, unchanged |
| `text` | one-dimensional array | the `text` value encoded as UTF-8, without the newline that serialization appends |
| `binary` | every `char` shape | the data of a NumPy array of exact dtype `S1` and the schema's shape |
| `mixed` | `char` arrays with two or more dimensions | the same as `binary` |

- **Length.** For a wildcard dimension the length is the **byte** count — for `text`, UTF-8 bytes, not characters. A fixed size `[k]` requires exactly k bytes, and a scalar `char` exactly one; any other length is a schema refinement error. Nothing is padded (with NUL or otherwise) or truncated; padding is an explicit upstream conversion.
- **`text` delivers its value, not its buffer.** The value `ACGT` is stored as `ACGT\n`, and reading strips trailing newlines, so the kernel receives `ACGT` with length 4. The value is a prefix of the stored buffer, so it can be passed without a copy. A `text` pin and a `bytes` pin fed from the same `text` Cell therefore differ: the trivial `text → bytes` conversion keeps the buffer unchanged, so the `bytes` pin receives `ACGT\n` with length 5.
- **A `bytes` pin fed NumPy byte strings receives their raw bytes.** Conversion into a `bytes` pin from `binary` — and from `mixed` when the buffer is `.npy` — calls `tobytes()` (C order) on **every** dtype-`S` array, whatever its shape and width: a zero-dimensional `S{len}`, a one-dimensional `S1`, an `S4` array. An empty one becomes the canonical null, which a `bytes` pin reads as `b""`. Any other array keeps its `.npy` checksum, so a `bytes` pin receives the whole `.npy` buffer, header included (`contracts/celltypes-and-conversion.md`, *Reformat rules*).
- **`binary` and `mixed` take exact `S1`.** A NumPy fixed-width byte string `S{k}` with k > 1 is rejected even where its bytes would fit — a zero-dimensional `S4` on `char [4]`, or an `S4` array of shape `(N,)` on `char [N, 4]`. This includes the zero-dimensional `S{len}` array that converting `bytes` to `binary` produces, and the one `mixed` produces when it reads a raw byte buffer that is neither JSON nor NumPy. Such a byte string belongs on a `bytes` pin. A JSON string is rejected.
- **Null.** Under `bytes` the canonical null is `b""`; under `text` the string `null` is rejected and `""` has length 0 (rule 4).
- **Declarations outside the table.** A declared celltype that the table does not list for the parameter's shape is a **Stage 1** failure. This includes `mixed` on a scalar `char` or a one-dimensional `char` array.

**Choosing a declaration** for a scalar `char` or a one-dimensional `char` array — the three choices accept different inputs:

| Declaration | Typical inputs | Rejected or surprising |
|---|---|---|
| `bytes` | `bytes` literals and Cells; `str` literals, encoded as UTF-8; NumPy dtype-`S` arrays of any shape from a `binary` or `mixed` Cell, converted with `tobytes()` | a `text` Cell keeps its trailing newline (`text → bytes` is trivial); a `plain` Cell delivers its JSON text, quotes included; a non-`S` array delivers its whole `.npy` buffer |
| `text` (one-dimensional only) | `str` literals; `text` and `str` Cells; `bytes` Cells whose content is UTF-8 | NumPy arrays; content that is not UTF-8 |
| `binary` | NumPy `S1` arrays: `ndarray` literals, and `binary` or `mixed` Cells holding an `S1` `.npy` | a `bytes` literal — the `binary` serializer takes a `bytes` object as an already-serialized buffer, so its checksum is unreadable as `binary`; a `bytes` Cell on `char [N]`, which converts to a zero-dimensional `S{len}` array and is then rejected (exact `S1` only, below); a `text` Cell, which does not convert at all: `text → binary` raises `SeamlessConversionError`, so the pin itself fails, and bound, the transformer is `blocked`, not `failed` (`contracts/pins.md`, *Pin failures*). Routing the text through a `bytes` Cell does not help, because that is the `bytes` case; declare the pin `bytes` or `text` instead |

`bytes` is the broadest choice, `text` is for text, and `binary` is for data that already is a NumPy `S1` array.

**Declaring the pin `bytes` is the standard way to pass a text buffer to a compiled transformer.** Feed it from a `text` Cell, directly or through a `bytes` Cell: `text → bytes` is trivial, so the kernel receives the stored buffer unchanged, including the trailing newline that `text` serialization appends (`ACGT` arrives as `ACGT\n`, N = 5). Declare the pin `text` instead only when the kernel should receive the value without that newline. Never declare it `binary` for text: a `text` Cell cannot convert to `binary`, and a `bytes` Cell becomes a rejected zero-dimensional `S{len}` array.

## 9. Errors

Stable, targeted failures:

| Failure | Raised as | Stage and state |
|---|---|---|
| A declared pin celltype incompatible with the schema | `CompiledPinCelltypeError`; `CompiledPinCelltypeWarning` carries the same diagnostic when the incompatibility arises. A celltype that no schema allows raises when declared | Stage 1: the transformer is `failed` |
| An optional input pin on a compiled transformer | no API route declares one; graph import rejects the node | — |
| **Null on a compiled pin** (rule 4), for every declared celltype | a targeted pin-level error naming the pin, the declared celltype and the schema dtype and shape — never a CFFI error or a `KeyError` | Stage 2; state deferred (section 5) |
| **Non-canonical `null` checksum on a `bytes` pin** | a targeted pin-level error stating that the checksum is ambiguous and naming both possible origins (4-byte content `null`, or a non-canonical JSON null) | Stage 2; state deferred (section 5) |
| A declared `mixed` pin given a JSON string or container, or proper Seamless-mixed data (3a) | `CompiledMixedValueError`. The message lists the other declarations the whitelist allows for the parameter, so the user of an auto pin sees which explicit declaration would convert the input (for example `binary` for a JSON list on a numeric array) | Stage 2: the transformer is `failed` |
| A value with the right pin celltype that violates dtype, range, shape, length, byte-order, alignment or layout requirements (sections 7 and 8) | `CompiledPinSchemaError` | Stage 2: the transformer is `failed` |

**Existing error kinds are unchanged.** Dependency errors remain dependency errors. Conversion errors remain **Expression conversion** errors, raised *before* compiled transformation construction by an edge or by the conversion of a typed standalone input; they name the pin, the input celltype and the pin celltype. In a workflow they are recorded on the pin, and the transformer is `blocked` with a `blocked-by-error` entry for that pin in `tf.block_reason` and `tf.exception` `None` (section 5; `contracts/node-state-lifecycle.md`).

**D5: the error classes and the `.exception` string.**

- `CompiledPinCelltypeError`, `CompiledMixedValueError` and `CompiledPinSchemaError` are **public exception classes subclassing `TypeError`**, exported from `seamless_transformer`, so existing `except TypeError` code keeps working and tests assert on classes rather than on message wording.
- Across the executor boundary a failure raised in the executor arrives as a `TransformationError` whose **message contains the same class name and message**. Propagating the real class out of the executor stays possible later without changing the classes.
- An `.exception` attribute is a **string**, not an `Exception` instance, and for these failures it **carries the class name**, as in `CompiledPinCelltypeError: Compiled pin 'x' declares celltype 'int', …`. This holds wherever the failure was detected: in Stage 1, before hashing, or in the executor.

## 10. Graphs, snapshots and checksums

- **Round-trips.** Graph export and import, and compiled-transformer snapshots, preserve the schema text, the declared pin celltypes, and the distinction between builder state and concrete transformation inputs. Compiled transformer nodes never carry optional input pins; graph import rejects a node that does.
- **D4: no separate legacy rule.** A compiled input with no declared celltype imports as `mixed`, the same rule as a pin newly introduced by a schema change. Declared celltypes import as declared, and the resulting checksum change is accepted. Consequence: a scalar `char` or one-dimensional `char` input in a legacy graph imports as a **Stage 1 failure** — the transformer is `failed`, reported as a missing declaration — until the user declares `bytes`, `text` or `binary`. Every other imported declaration goes through Stage 1 in the ordinary way.
- **Checksum consequences.** Recording the real pin celltype intentionally changes transformation checksums wherever the stored pin celltype changes. This is correct, because an `int` pin and a `mixed` pin have different acceptance and conversion semantics. Old cached compiled results may be reused only when the full corrected transformation definition — schema and pin celltypes included — has the same checksum. Declared `mixed` inputs that remain encoded as `mixed` may keep their old checksum for valid values.
- **`unsigned char` changes no checksum.** Generating `unsigned char` for schema `char` changes no transformation checksum, because `__header__` is excluded from identity. Kernel source that declares the parameter as plain C `char` must still be updated to `unsigned char` (Rust `u8`), and the updated source has a new **code** checksum.

## 11. Non-goals

- **Compiled result pins and the current multi-output aggregate:** see `contracts/compiled-transformers.md`. Whether single outputs acquire schema-derived result celltypes, and how multiple typed outputs avoid conflating native output structure with unrestricted `mixed`, is a separate decision.
- **Optional compiled inputs:** the C ABI has no absent argument (rule 3).
- **Redesigning the global Seamless conversion table**, adding unrestricted recursive Python-object marshalling, treating proper Seamless-mixed serialization as a native ABI, or defining a new scalar `complex` celltype.
- **Changing ordinary Python and bash transformer pin semantics** (`contracts/pins.md`).

## 12. Implementation status and current limitations

Settled contract that the code does not yet implement, or implements differently. The rules above define the test oracle; each gap below is pinned by an `xfail(strict=False)` test whose reason reads "contract ahead of code" (`seamless-workflow/tests/test_contract_compiled_pins_workflow.py`, and the rule-3 and ruling-6 cases in `seamless-workflow/tests/test_contract_node_state_lifecycle.py`).

- **A Stage 1 failure reports `blocked`, with `tf.block_reason == {}`.** The contract is `failed` with `block_reason` `None` (section 5). The diagnostic is already stored as `tf.exception`, and no pin is resolved.
- **A valid value that compiled validation rejects before hashing reports `blocked`.** For example, a JSON list on a `mixed` pin records the pin as `failed` and reports the transformer `blocked` with `blocked-by-error`. The contract is `failed`, with the diagnostic in `tf.exception` (section 5). The same kind of rejection found in the executor — such as an out-of-range integer on a `mixed` pin — already reports `failed`.
- **A conversion failure sets `tf.exception`.** The pin's conversion error is copied into the transformer's `.exception`. The contract is that a pin with no valid checksum leaves `tf.exception` `None` (section 5); the pin side — `pin.state == "failed"`, `pin.exception`, and the `blocked-by-error` entry — is implemented.
- **An `.exception` string can lack the class name.** A compiled-pin failure found before hashing on a bound pin, and a Stage 1 diagnostic, are stored as the bare message, without `CompiledMixedValueError`, `CompiledPinCelltypeError`, etc. (D5, section 9). Failures that arrive from the executor already carry it.

**Implemented.** The declaration whitelist, Stage 1 and Stage 2 live in `seamless_transformer.compiled_validation`, and the public error classes are exported from `seamless_transformer`. The declared pin celltype is preserved in concrete transformation tuples and across schema edits, snapshots and graph round-trips, and `schema_celltypes` exposes the independently derived schema celltypes. Construction validates literals as serialized values and validates deferred inputs by checksum and locally available HashType facts, without fetching input buffers. The executor validates every input before native compilation, including replayed transformation dictionaries. Workflow Stage 1 checks run before pin resolution. Ordinary Expression conversions run before the pin boundary. Character buffers are passed with byte lengths and without terminators, and empty buffers receive a non-NULL pointer. The core serializer supports the non-finite, Boolean and complex representations specified above, and `binary → bytes` calls `tobytes()` on every dtype-`S` array.

---

## Reference Map (load only as needed)

- `contracts/pins.md` — the general pin layer: reaching pins, the pin set, writes, conversion at the pin boundary, pin and transformer state reporting, and the Python/bash null and optional-pin rules this page overrides
- `contracts/compiled-transformers.md` — compiled transformers as a whole: schema, calling convention, struct marshalling, result types, identity and caching
- `contracts/seamless-signature-schema.md` — schema YAML format, dtype tables, shapes and wildcards
- `contracts/celltypes-and-conversion.md` — celltype semantics, serialization, the conversion table and the reformat rules (including `binary → bytes`)
- `contracts/hashtype.md` — what HashType words do and do not prove, for pre-hash checks
- `contracts/expressions.md` — Expression construction and conversion semantics at and before the pin
- `contracts/node-state-lifecycle.md` — transformer node states, block reasons, and the pin-versus-transformer failure split behind section 5
