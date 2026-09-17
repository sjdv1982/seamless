# Celltypes, Null, and Conversion (Contract)

This page defines what a celltype means, how the canonical null works, and how the checksum-level conversion engine converts a checksum from one celltype to another. The companion page `contracts/hashtype.md` defines the `HashType` classification that the engine and the parser use to reject impossible work without touching buffers.

Code locations (all in `seamless-core`):

| Concern | Module / symbol |
|---|---|
| Celltype list | `seamless.checksum.celltypes.celltypes` |
| Reference parser | `seamless.checksum.parse_buffer._parse_buffer` (used by `parse_buffer`, `parse_buffer_sync`, `Buffer.get_value`, `Checksum.resolve(celltype)`) |
| Serializer | `seamless.checksum.serialize._serialize` (used by `serialize`, `serialize_sync`, `Buffer(value, celltype)`) |
| Canonical null | `seamless.checksum.null` (`NULL_BUFFER`, `NULL_CHECKSUM`, `is_null`, `is_null_value`, `canonicalize_checksum`) |
| Virtual values | `seamless.checksum.virtual` (`NULL_CHECKSUMS`, `TRUE_CHECKSUMS`, `FALSE_CHECKSUMS`, `virtual_value`, `NOT_VIRTUAL`) |
| Rule table | `seamless.checksum.conversion` (`conversion_*` sets/dicts, `SeamlessConversionError`) |
| Executor | `seamless.checksum.convert` (`convert_checksum`, `conversion_needs_buffer`) |

Out of scope here: Expressions, Cells, pins, mounts, and the workflow Context. The engine's only caller is empty-path Expression evaluation (`seamless.checksum.expression`), which has its own docs.

## Celltypes

`seamless.checksum.celltypes.celltypes` has exactly 13 entries:

`binary`, `mixed`, `text`, `python`, `ipython`, `plain`, `yaml`, `str`, `bytes`, `int`, `float`, `bool`, `checksum`

These are the only celltypes that the parser, serializer and conversion engine accept. `convert_checksum` raises `TypeError` for anything else.

- **Storage celltypes**: `bytes` (raw), `binary` (NumPy `.npy` buffer), `mixed` (Seamless-mixed format, or pure JSON, or `.npy`), `plain` (JSON).
- **Text celltypes**: `text` (UTF-8), with the code/markup subtypes `python`, `ipython` and `yaml`.
- **Scalar celltypes**: `str`, `int`, `float` and `bool` are *readings* of JSON-compatible buffers, not separate storage formats.
- **`checksum`**: the value is a `Checksum`. The buffer is the bare 64-character lowercase hex digest, with no trailing newline.
- **Deep and structural celltypes** (`deepcell`, `deepfolder`, `folder`, `module`) are not in this list. They are distinct celltypes whose buffers are plain JSON: `Buffer._map_celltype` serializes and parses them as `plain`. Conversion between them and the 13 celltypes is not part of the rule table.

## The celltype hierarchy is a checksum hierarchy

A subtype→supertype edge means: **every checksum that is valid as the subtype is valid, unchanged, as the supertype.** The hierarchy is about sets of valid checksums, not about values. The edges are exactly the pairs in `conversion_trivial`:

| Subtype | Supertype(s) |
|---|---|
| `python` | `ipython`, `text` |
| `ipython`, `yaml` | `text` |
| `text` | `bytes` |
| `plain` | `yaml`, `mixed`, `bytes` |
| `binary` | `mixed` |
| `str`, `int`, `float`, `bool` | `plain` |
| `int`, `float`, `bool` | `str` |
| `int` ↔ `float` | each other (both directions are trivial) |

Consequences:

- `bytes` is not a universal supertype. `mixed → bytes` and `binary → bytes` are *reformat* rules: a zero-dimensional dtype-`S` NumPy array becomes its raw bytes.
- `yaml → plain` is not trivial. It runs the YAML parser and writes a new canonical `plain` buffer.
- `int` and `float` accept the same checksums. Which one you use decides only the reading.
- `checksum` is outside the hierarchy. It has no trivial edges, and every conversion to or from it is value-level.
- **The canonical null is valid for every celltype** (see below).

## Checksum identity vs values

- **Identity stays with the checksum.** One value can have several checksums. Examples: `b"true"` and `b"true\n"`; compact and indented JSON for the same object; `b"4.5\n"` read as `int` (value `4`) and the canonical `int` buffer `b"4\n"`.
- A checksum-preserving conversion (trivial or reinterpret) keeps the source checksum, even when the target celltype's serializer would write different bytes for the resulting value. Seamless never replaces a checksum with the checksum of the re-serialized value. The one exception is empty bytes → null (below).
- **"Deserializable as X"** means the reference parser (`_parse_buffer`) accepts the buffer as X. It does **not** mean that re-serializing the value as X gives back the same checksum.

## Canonical null

- `NULL_BUFFER = b"null\n"`. `NULL_CHECKSUM` is its SHA-256: `38e0b9de817f645c4bec37c0d4a3e58baecccb040f5718dc069a72c7385a0bed`.
- **Serialization.** `_serialize(None, celltype)` returns `NULL_BUFFER` for every celltype. Serializing `b""` as `bytes` also returns `NULL_BUFFER`, so `Buffer(b"", "bytes")` has `NULL_CHECKSUM`.
- **Canonicalization of empty bytes.** `canonicalize_checksum(checksum, celltype)` maps `sha256(b"")` to `NULL_CHECKSUM` **only when `celltype == "bytes"`**. Expression keys apply it to their input checksum and input celltype. A raw `Buffer(b"")` made without a celltype still has checksum `sha256(b"")`: canonicalization is not applied to raw buffers.
- **Reading.** A null checksum reads as `b""` for `bytes` and as `None` for every other celltype, including `str` and `checksum`. `virtual_value` treats both `sha256(b"null")` and `sha256(b"null\n")` as null. Only `b"null\n"` is canonical, and the two remain distinct identities.
- **Predicates.** `is_null(cs)` is true only for `NULL_CHECKSUM`. `is_null_value(cs)` is true for either null checksum.
- **Display.** `str(Checksum(NULL_CHECKSUM))` is `"NULL"`, and nothing else is displayed that way. `repr()` and `.hex()` give the hex digest. Machine-readable output (JSON, wire, database, filenames) must use `.hex()`, never `str()`.

## Virtual values (null, true, false)

Some checksums fully determine their value, so `virtual_value(checksum, celltype)` resolves them without a buffer cache or remote lookup. It returns `NOT_VIRTUAL` when the checksum does not determine the value.

| Checksum set | Reading |
|---|---|
| `NULL_CHECKSUMS` (`b"null"`, `b"null\n"`) | `b""` for `bytes`; `None` for all other celltypes |
| `TRUE_CHECKSUMS` / `FALSE_CHECKSUMS` (with and without `\n`) | `True`/`False` for `bool`, `plain`, `mixed`; `"True"`/`"False"` for `str`; `ValueError` for `int`/`float`; `NOT_VIRTUAL` (parsed from the buffer) for other celltypes, e.g. `text` gives `"true"` |
| any other checksum, celltype `bool` | `ValueError` ("checksum does not encode a boolean value"), without fetching |

Therefore **`bool` accepts only the four canonical boolean checksums plus null.** The parser performs no content-based bool coercion.

In addition, `seamless.checksum.calculate_checksum.TRIVIAL_CHECKSUMS` maps the checksums of `null`, `true`, `false`, `""`, `{}` and `[]` (each with and without a trailing newline, except `""`) to their buffers. `Checksum.resolve()` and local Expression evaluation materialize these without cache residency.

## Reference parser (`_parse_buffer`)

Order of operations: (1) `virtual_value`; (2) `validate_deserializable_as(checksum, celltype, buffer=buffer)`, which raises `HashTypeValidationError` when HashType proves the reading impossible (see `contracts/hashtype.md`); (3) the per-celltype rule:

| Celltype | Accepts / returns |
|---|---|
| `text`, `python`, `ipython`, `yaml` | UTF-8 decode, then strip all trailing `\n`; returns the text. `python` must pass `ast.parse`, `ipython` must pass `ipython2python`, `yaml` must pass `yaml.safe_load` (the value is still the text). Failure raises `HashTypeValidationError`. |
| `plain` | Decode, strip trailing `\n`, then `orjson.loads` |
| `binary` | Seamless-mixed deserializer; storage must be `pure-binary` (an `.npy` buffer) |
| `mixed` | Seamless-mixed deserializer (`.npy`, Seamless-mixed format, or JSON) |
| `bytes` | Returns the `Buffer` object itself (the null reading is `b""`) |
| `str` | `orjson` parse; a JSON string, number or boolean gives `str(value)` (so `4.5` → `"4.5"`, `1e3` → `"1000.0"`); objects and arrays are rejected |
| `int`, `float` | Buffers over 1000 bytes are rejected. `orjson` parse; accepts a finite JSON number, or a JSON string that parses as a finite float. `float` → `float(v)`. `int` → `int(v)`, falling back to `int(float(v))`. |
| `bool` | Only virtual values (above); anything else raises |
| `checksum` | Decode; must construct a `Checksum` (64 hex characters) |

**`int` truncates.** Reading `b"4.5\n"` as `int` succeeds and returns `4`. The JSON string `"4.5"` also gives `4`, and `-4.5` gives `-4`. Serializing a value as `int` truncates the same way (`Buffer(-4.5, "int")` → `b"-4\n"`).

**Large integers.** Numbers are parsed by `orjson`, which returns a float for an integer outside the unsigned 64-bit range. `int` and `plain` readings of such integers therefore lose precision.

## Canonical serialization (`_serialize`)

| Celltype | Buffer |
|---|---|
| any, value `None` | `b"null\n"` |
| `plain` | `orjson` with 2-space indent and sorted keys, plus `\n` |
| `str` | JSON of `str(value)` plus `\n`, except that a `bool` stays a JSON boolean (`True` → `b"true\n"`) |
| `int`, `float`, `bool` | JSON of `int(v)` / `float(v)` / `bool(v)`, plus `\n` |
| `text`, `python`, `ipython`, `yaml` | `str(value)` with trailing `\n` stripped, plus exactly one `\n` (no syntax check) |
| `bytes` | Raw bytes (or `.tobytes()`, or the encoded `str()`); `b""` becomes `b"null\n"` |
| `mixed` | Seamless-mixed serializer (pure JSON values serialize the same way as `plain`; NumPy arrays, zero-dimensional ones included, serialize the same way as `binary`; finite NumPy integer and floating-point scalars serialize as JSON numbers, see below) |
| `binary` | `.npy` of `np.array(value)` |
| `checksum` | Bare hex digest, no newline; the value must be a `Checksum` or a hex `str` |

**NumPy scalars.** Under `mixed`, a finite NumPy integer or floating-point scalar is written as a JSON number, so its dtype is not kept: `np.float32(1.5)` reads back as the Python float `1.5`. Under `binary`, a NumPy scalar is written as a `.npy` of its own dtype. That buffer reads back as the same NumPy scalar under both `binary` and `mixed`, and `binary → mixed` keeps its checksum.

Known defects in the current code (a planned fix is described in `compiled-transformer-celltypes-design-plan.md`, section "Prerequisites In seamless-core"):

- NaN and infinity under `mixed` are written as `NaN` / `Infinity`, which cannot be read back as `mixed`.
- NaN and infinity under `plain` and `float` are written as `b"null\n"` and read back as None.
- `np.bool_` under `mixed` raises `TypeError`.
- Complex scalars and arrays raise `TypeError` under both `mixed` and `binary`.

## Conversion engine

### Principle

Conversion avoids value-level work unless it is necessary. Preference order: **checksum** (answer from the checksum alone: trivial rule, virtual value, or a HashType disproof) → **buffer** (read or classify bytes) → **value** (deserialize, convert and re-serialize).

### Rule table (`seamless.checksum.conversion`)

Every ordered pair of distinct celltypes is in exactly one category. `check_conversions()` runs at import and raises `SeamlessConversionError` on a missing pair, a duplicate, or a circular mapping.

| Category | Checksum | Guaranteed for valid input? | Pairs |
|---|---|---|---|
| `conversion_trivial` | same | yes, no validation and no buffer | the hierarchy edges above (18 pairs) |
| `conversion_reinterpret` | same | no; the target reading is validated | reverse of each trivial edge whose reverse is not itself trivial, minus `ipython→python` and `yaml→plain`: `bytes→text`, `bytes→plain`, `text→python`, `text→ipython`, `text→yaml`, `mixed→binary`, `mixed→plain`, `plain→str`, `plain→int`, `plain→float`, `plain→bool`, `str→int`, `str→float`, `str→bool` |
| `conversion_reformat` | may change | yes | `bytes→binary`, `bytes→mixed`, `binary→bytes`, `mixed→bytes`, `plain→text`, `text→plain`, `text→str`, `str→text`, `yaml→plain`, `ipython→python` |
| `conversion_possible` | new buffer | no | `binary→int/float/bool`, `mixed→str/int/float/bool` |
| `conversion_values` | new buffer (or dereference) | no | `binary↔plain`; `bool↔int`, `bool↔float`; every `X→checksum` and `checksum→X` |
| `conversion_equivalent` | — | mapped to another pair | e.g. `text/python/ipython/yaml→mixed` and `python/ipython/yaml→str` → `text→str` (not via `plain`); `python/ipython→plain` → `text→str`; `str/int/float/bool→mixed` → `…→plain`; `int/float/bool→text` → `plain→text` |
| `conversion_chain` | — | `A→B→C` | e.g. `mixed→text` via `plain`; `binary→str` via `bytes`; `bytes→str/int/float/bool` via `plain`; `text→binary` via `mixed`; `text/yaml→int/float/bool` via `plain` |
| `conversion_forbidden` | — | always fails | `python/ipython↔yaml`, `python/ipython→int/float/bool`, `int/float/bool→python/ipython` |

### Reformat rules (as executed)

| Pair | Behaviour |
|---|---|
| `bytes→binary` | Always fetches the buffer. `.npy` magic: validate as `binary` and keep the checksum. Otherwise: new `.npy` of a 0-d dtype-`S` array holding the bytes. |
| `bytes→mixed` | Null/boolean checksum, or cached HashType says `mixed`: keep. Otherwise fetch and classify; if it is `mixed`-deserializable, validate and keep. Otherwise, if UTF-8: new `str` buffer of the text (trailing `\n` stripped). Otherwise: new dtype-`S` `.npy`. |
| `binary→bytes` | Parse as `binary`; a 0-d dtype-`S` array becomes `value.tobytes()`; anything else keeps the checksum |
| `mixed→bytes` | `.npy` magic: as `binary→bytes`. Otherwise validate as `mixed` and keep. |
| `plain→text` | Value is a JSON string: new `text` buffer of that string. Otherwise keep. |
| `text→plain` | Null/boolean checksum, or text that `orjson` accepts: keep. Otherwise: new `plain` buffer holding the text as a JSON string. |
| `text→str`, `str→text` | Re-serialize the same value under the target celltype |
| `yaml→plain` | `yaml.safe_load`, then canonical `plain` |
| `ipython→python` | `ipython2python` |

`conversion_possible` parses the source value, rejects `dict`/`list`/non-scalar arrays, and serializes `builtins.<target>(value)`. A `float` target must produce a finite result; a non-finite result raises `SeamlessConversionError` instead of being serialized as JSON `null`. Value rules: `binary→plain` goes through `orjson` numpy encoding and then canonical `plain`; `plain→binary` requires an int, float, bool or list whose `np.array` is not dtype `object`; `bool↔int/float` apply the builtin.

**Conversions involving `checksum`** (current behaviour):

- `X→checksum` produces a `checksum`-celltype buffer whose value is **the source checksum itself** (its hex digest). It does not parse the source as a hex string.
- `checksum→X` **dereferences**: it reads the stored checksum and returns it as the result, with no new buffer. The referenced checksum is not validated as `X` at this point.

### Executor (`seamless.checksum.convert`)

`convert_checksum(checksum, source, target, get_buffer) -> (Checksum, Buffer | None)`

- `source` and `target` must be in `celltypes`, otherwise `TypeError`. `get_buffer` must be a zero-argument callable that returns a `Buffer` or `bytes`-like object.
- `get_buffer` is called **only** when a rule needs content, and **at most once** per call (memoized). The engine knows nothing about buffer caches or remotes.
- `source == target`: returns `(checksum, None)` without validation.
- Return value: `(checksum, None)` when the checksum is kept; `(new_checksum, new_buffer)` when new content is serialized.
- Resolving a source value (`_value_of`) tries `virtual_value` first, then `validate_deserializable_as(checksum, celltype)` without a buffer (fails early on a HashType disproof from the local cache, or from the database when no event loop is running), and only then calls `get_buffer()` and `_parse_buffer`.
- Errors: `CacheMissError` from `get_buffer` propagates unchanged, because a missing buffer is not a failed conversion. `SeamlessConversionError` (a `ValueError` subclass) propagates. Any other exception, including `HashTypeValidationError`, is wrapped in `SeamlessConversionError("<hex> cannot be converted from <source> to <target>", …)`.
- The executor does not special-case null for `checksum`: `convert_checksum(NULL_CHECKSUM, "plain", "checksum", …)` produces a checksum buffer. Empty-path Expression evaluation short-circuits a null input to a null result for every celltype pair before it calls the executor.

`conversion_needs_buffer(checksum, source, target) -> bool` is a dry run. It returns `True` only if the conversion would call `get_buffer`. A conversion that succeeds or fails from the checksum alone (trivial rule, virtual value, or cached HashType disproof) returns `False`. Expression evaluation uses it to decide whether an empty-path expression can be evaluated locally or must run where the data is.

## Agent guidance

- Compare identities by checksum, never by deserialized value.
- For values of the same celltype, you can normally assume that one value has one checksum *if the buffer was serialized by Seamless*. For arbitrary files/buffers, you can never assume this.
- Prefer conversions along hierarchy edges (trivial) when you want to avoid buffer I/O; reinterpretations need a parse unless a virtual value or HashType settles them.
- Do not print `str(checksum)` into machine-readable output; use `.hex()`.
- Expect `int` readings to truncate, and `bool` readings to accept only canonical boolean checksums.
