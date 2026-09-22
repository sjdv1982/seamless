# Celltypes, Null, and Conversion (Contract)

This page defines what a celltype means, how the canonical null works, and how the checksum-level conversion engine converts a checksum from one celltype to another. The companion page `contracts/hashtype.md` defines the `HashType` classification that the engine and the parser use to reject impossible work without touching buffers. The deep celltypes (`deepcell`, `deepfolder`, `folder`), which are outside the rule table below, are defined in `contracts/deep-celltypes.md`.

## Where this page sits: the stack

Each layer is defined **on top of** the one before it, and no page re-derives the one below it. Read them in this order.

| Layer | Page | What it adds |
|---|---|---|
| 1. **Celltypes and the type hierarchy** | **this page**, *Celltypes* … *Canonical serialization* | which checksums are valid as which celltype, and the subtype→supertype edges |
| 2. **HashType** | `contracts/hashtype.md` | a checksum-level classification that **disproves** readings and conversions without fetching a buffer |
| 3. **Conversion** | **this page**, *Conversion engine* | the rule table, built **on top of the hierarchy** — `conversion_trivial` *is* the set of hierarchy edges — and using layer 2 to refuse or skip work before any buffer is fetched |
| 4. **Expressions** | `contracts/expressions.md` | path steps plus **at most one** conversion, in that order (**project, then convert**). Layer 3 is exactly the **empty-path** case of an Expression |
| 5. **Cells** | `contracts/cells.md` | a Cell is a *deferred* Expression: the mutable builder for the same recipe, standalone or bound to a workflow Context node |

Two things sit beside the stack rather than in it:

- the **deep celltypes** `deepcell`, `deepfolder` and `folder` — not in the 13 celltypes below, not in the rule table below, and governed by their own conversion and path table in `contracts/deep-celltypes.md`;
- **`module`**, which is not a deep celltype either (`contracts/deep-celltypes.md`, *`module` is not a deep celltype*).

Both are mapped to `plain` at the buffer layer by `Buffer._map_celltype`, which is the only thing this page's machinery knows about them.

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

Out of scope here: Expressions, Cells, pins, mounts, and the workflow Context. The engine's only caller is empty-path Expression evaluation (`seamless.checksum.expression`), which has its own docs. How a celltype is chosen, declared and converted on a handle — `celltype` as the output type, the read-only `input_celltype`, retyping, and where null and empty `bytes` show up in writes and reads — is in `contracts/cells.md`.

## Celltypes

`seamless.checksum.celltypes.celltypes` has exactly 13 entries:

`binary`, `mixed`, `text`, `python`, `ipython`, `plain`, `yaml`, `str`, `bytes`, `int`, `float`, `bool`, `checksum`

These are the only celltypes that the parser, serializer and conversion engine accept. `convert_checksum` raises `TypeError` for anything else.

- **Storage celltypes**: `bytes` (raw), `binary` (NumPy `.npy` buffer), `mixed` (Seamless-mixed format, or pure JSON, or `.npy`), `plain` (JSON).
- **Text celltypes**: `text` (UTF-8), with the code/markup subtypes `python`, `ipython` and `yaml`.
- **Scalar celltypes**: `str`, `int`, `float` and `bool` are *readings* of JSON-compatible buffers, not separate storage formats.
- **`checksum`**: the value is a `Checksum`. The buffer is the bare 64-character lowercase hex digest, with no trailing newline.
- **Deep and structural celltypes** (`deepcell`, `deepfolder`, `folder`, `module`) are not in this list. They are distinct celltypes whose buffers are plain JSON: `Buffer._map_celltype` serializes and parses them as `plain`. **Conversion between them and the 13 celltypes is not part of the rule table on this page**, and neither is conversion among themselves: their own conversion table, member-celltype rules and one-step path rule are in `contracts/deep-celltypes.md`. The deep celltypes are `deepcell`, `deepfolder` and `folder`; `module` is not one of them.

**The *engine* nevertheless gains the deep zero-path conversions, while the *table* stays on that page.** The handful of legal deep conversions (`deepcell → plain`, `folder ↔ deepfolder`, `deepcell → deepfolder`, `folder → mixed`) are conversions like any other, so a **pathless** Expression — deep or not — is vetted by the conversion engine, and a *pathed* deep Expression by the deep path table instead (`contracts/expressions.md`, *When an Expression is vetted*). This is a division of labour, not a second rule table: the rules are defined once, in `contracts/deep-celltypes.md`.

*Contract ahead of code:* today `convert_checksum` raises `TypeError` for all four names, and an Expression naming any of them on either side raises `HashTypeValidationError` before evaluation, because `deserializable_as` answers `False` outside the 13 — an answer the ruling replaces with a `ValueError`, since a deep celltype is never a question for HashType (`contracts/hashtype.md`, `deserializable_as`; `contracts/deep-celltypes.md`, *Where deep validation happens*).

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

**The conversion rule table is built on this table.** `conversion_trivial` is *exactly* the set of edges above — that is what "trivial" means: the checksum is kept, nothing is validated and no buffer is fetched. Every other category in the rule table below is defined by how far it departs from a hierarchy edge: `conversion_reinterpret` is a hierarchy edge walked *backwards* (same checksum, but the target reading must be validated), and `conversion_reformat`, `conversion_possible` and `conversion_values` are the pairs with no edge at all.

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
- **Collisions with real content.** Null is decided by checksum, so some non-null content is indistinguishable from null:
  - Under `bytes`, content that is exactly `b"null\n"` has `NULL_CHECKSUM`, the same checksum and buffer as empty bytes, and reads as `b""`. Content `b"null"` has the non-canonical null checksum and also reads as `b""`, although serializing empty bytes never produces it.
  - Under the text celltypes (`text`, `python`, `ipython`, `yaml`), the string `"null"` serializes to `b"null\n"` and reads back as `None`. The empty string is not affected: it is stored as `b"\n"` and reads as `""`.
  - `str` and `plain` are not affected: the string `"null"` is written as the JSON string `"null"`.
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
| `mixed` | Seamless-mixed deserializer (`.npy`, Seamless-mixed format, or JSON). A zero-dimensional NumPy leaf reads back as a NumPy scalar, at the top level and nested in a dict or list alike. |
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
| `plain` | `orjson` with 2-space indent and sorted keys, plus `\n`. NaN and infinity raise. |
| `str` | JSON of `str(value)` plus `\n`, except that a `bool` stays a JSON boolean (`True` → `b"true\n"`) |
| `int`, `float`, `bool` | JSON of `int(v)` / `float(v)` / `bool(v)`, plus `\n`. A `bytes` value is decoded first. Under `float`, NaN and infinity raise. |
| `text`, `python`, `ipython`, `yaml` | `str(value)` with trailing `\n` stripped, plus exactly one `\n` (no syntax check). A `bytes` value is decoded first. |
| `bytes` | A `bytes` value unchanged; otherwise `.tobytes()`; otherwise `str(value)` with trailing `\n` stripped, UTF-8 encoded. `b""` becomes `b"null\n"` |
| `mixed` | Seamless-mixed serializer (pure JSON values serialize the same way as `plain`; NumPy arrays, zero-dimensional ones included, serialize the same way as `binary`; NumPy scalars, complex values, NaN and infinity: see below) |
| `binary` | A `bytes` value is taken as an already-serialized buffer and stored unchanged (it is readable as `binary` only if it is an `.npy` buffer). Anything else: `.npy` of `np.array(value)`, complex dtypes included |
| `checksum` | Bare hex digest, no newline; the value must be a `Checksum` or a hex `str` |

**NumPy scalars and arrays.**

- Under `mixed`, a finite NumPy integer or floating-point scalar is written as a JSON number, and an `np.bool_` as a JSON boolean, so the dtype is not kept: `np.float32(1.5)` reads back as the Python float `1.5`.
- Under `binary`, a NumPy scalar is written as a `.npy` of its own dtype. That buffer reads back as the same NumPy scalar under both `binary` and `mixed`, and `binary → mixed` keeps its checksum.
- A NumPy array keeps its dtype under both `binary` and `mixed`, zero-dimensional arrays included.
- **Complex values** have no JSON form. A complex scalar or array is written as the `.npy` of its own dtype, under `binary` and under `mixed`.

**NaN and infinity are NumPy values.** JSON cannot hold them.

- Under `mixed`, a top-level NaN or ±infinity (a Python `float`, or a NumPy floating-point scalar of any precision) is written as a zero-dimensional `float64` `.npy`. Inside a dict or list, it is written as a NumPy value inside the Seamless-mixed format. In both positions it reads back as `np.float64(nan)` / `np.float64(inf)`.
- Under `plain` and `float`, serializing NaN or infinity raises; it is never written as `null`. A value containing NaN or infinity therefore has no `plain` or `float` checksum. `int` already raises through `int(v)`.
- Under `binary`, NaN and infinity are ordinary elements of a floating-point array or scalar of its own dtype.

## Conversion engine

### Principle

Conversion avoids value-level work unless it is necessary. Preference order: **checksum** (answer from the checksum alone: trivial rule, virtual value, or a HashType disproof) → **buffer** (read or classify bytes) → **value** (deserialize, convert and re-serialize).

**Only a HashType `False` is a proof.** The engine consults HashType at the checksum level, and that layer is deliberately one-sided: a `False` from `deserializable_as` or `conversion_feasible` is a proof of impossibility and is the *only* answer the engine acts on to refuse work. `True` and `None` are **not** guarantees — they mean "not disproved", and the parser or the value-level rule still decides. Reading this page alone, it would be easy to take the three answers as equally trustworthy; they are not, and the asymmetry is owned by `contracts/hashtype.md`, *The false-negative property*.

**This engine is only ever the empty-path case.** A conversion has nothing to order it against: there is no path step, so *project, then convert* (`contracts/expressions.md`, *Application order*) is vacuous here. The moment a path is involved, the ordering is load-bearing and is that page's rule — the conversion is applied to **what the path selected**, never to the whole input. A convert-then-project recipe is therefore not one call to this engine followed by a path; it is two Expressions, the first of which is an empty-path conversion whose new buffer is parent-sized.

### Rule table (`seamless.checksum.conversion`)

Every ordered pair of distinct celltypes is in exactly one category. `check_conversions()` runs at import and raises `SeamlessConversionError` on a missing pair, a duplicate, or a circular mapping — so the matrix below is **exhaustive by construction**: all 13 × 12 = **156** ordered pairs are classified.

Six categories are **terminal** — they say what happens. Two are **indirections** — they say which other pair to evaluate instead:

| Category | Code | Checksum | Guaranteed for valid input? | Members |
|---|---|---|---|---|
| `conversion_trivial` | **T** | same | **yes** — no validation, no buffer | 18 pairs: `binary→mixed`, `bool→plain`, `bool→str`, `float→int`, `float→plain`, `float→str`, `int→float`, `int→plain`, `int→str`, `ipython→text`, `plain→bytes`, `plain→mixed`, `plain→yaml`, `python→ipython`, `python→text`, `str→plain`, `text→bytes`, `yaml→text` |
| `conversion_reinterpret` | **RI** | same | no — the target reading is validated and may raise | 14 pairs: `bytes→plain`, `bytes→text`, `mixed→binary`, `mixed→plain`, `plain→bool`, `plain→float`, `plain→int`, `plain→str`, `str→bool`, `str→float`, `str→int`, `text→ipython`, `text→python`, `text→yaml` |
| `conversion_reformat` | **RF** | may change | **yes** | 10 pairs: `binary→bytes`, `bytes→binary`, `bytes→mixed`, `ipython→python`, `mixed→bytes`, `plain→text`, `str→text`, `text→plain`, `text→str`, `yaml→plain` |
| `conversion_possible` | **P** | new buffer | no | 7 pairs: `binary→bool`, `binary→float`, `binary→int`, `mixed→bool`, `mixed→float`, `mixed→int`, `mixed→str` |
| `conversion_values` | **V** | new buffer, or a dereference for `checksum` | no | 30 pairs: `binary→plain`, `plain→binary`; `bool→float`, `bool→int`, `float→bool`, `int→bool`; and every `X→checksum` and `checksum→X` (12 each) |
| `conversion_forbidden` | **X** | — | **never** — always raises | 16 pairs: `python/ipython↔yaml`, `python/ipython→int/float/bool`, `int/float/bool→python/ipython` |
| `conversion_equivalent` | **=a→b** | — | — | 32 pairs, each mapped to a different pair to evaluate instead |
| `conversion_chain` | **»m** | — | — | 29 pairs, each evaluated as `source→m` followed by `m→target` |

**Resolving an indirection.** `=a→b` means: discard this pair and evaluate `(a, b)`. `»m` means: convert `source→m`, then `m→target`. Either may resolve again — `binary→str` is `»bytes`, and `bytes→str` is in turn `»plain` — and `check_conversions()` proves that every chain of resolutions terminates in a terminal category without a cycle.

#### The complete matrix

Read a row as the **source** celltype and a column as the **target**. Generated from `seamless-core/seamless/checksum/conversion.py`; regenerate it from that module rather than editing cells by hand.

| source ↓ / target → | `binary` | `mixed` | `text` | `python` | `ipython` | `plain` | `yaml` | `str` | `bytes` | `int` | `float` | `bool` | `checksum` |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **`binary`** | id | T | »plain | »text | »text | V | »text | »bytes | RF | P | P | P | V |
| **`mixed`** | RI | id | »plain | »text | »text | RI | »text | P | RF | P | P | P | V |
| **`text`** | »mixed | =text→str | id | RI | RI | RF | RI | RF | T | »plain | »plain | »plain | V |
| **`python`** | =text→binary | =text→str | T | id | T | =text→str | X | =text→str | =python→text | X | X | X | V |
| **`ipython`** | =text→binary | =text→str | T | RF | id | =text→str | X | =text→str | =ipython→text | X | X | X | V |
| **`plain`** | V | T | RF | »text | »text | id | T | RI | T | RI | RI | RI | V |
| **`yaml`** | »plain | =text→str | T | X | X | RF | id | =text→str | =text→bytes | »plain | »plain | »plain | V |
| **`str`** | =plain→binary | =str→plain | RF | =str→text | =str→text | T | =str→text | id | =plain→bytes | RI | RI | RI | V |
| **`bytes`** | RF | RF | RI | »text | »text | RI | »text | »plain | id | »plain | »plain | »plain | V |
| **`int`** | =plain→binary | =int→plain | =plain→text | X | X | T | »plain | T | =plain→bytes | id | T | V | V |
| **`float`** | =plain→binary | =float→plain | =plain→text | X | X | T | »plain | T | =plain→bytes | T | id | V | V |
| **`bool`** | =plain→binary | =bool→plain | =plain→text | X | X | T | »plain | T | =plain→bytes | V | V | id | V |
| **`checksum`** | V | V | V | V | V | V | V | V | V | V | V | V | id |

**id** is the diagonal: `source == target` returns the checksum unchanged, without validation and without a buffer. It is not a member of any category, and it is the dummy Expression of `contracts/expressions.md`.

Three readings worth taking from the matrix, because each surprises people:

- **`checksum` is a wall.** Every pair with `checksum` on either side is **V**, in both directions, and no chain or equivalence routes through it. A `checksum` celltype is a reference, not a scalar that happens to look like hex.
- **Composition is not associative, so the matrix cannot be derived from a smaller one.** `text→mixed` is `=text→str`, explicitly *not* `text→plain`; `yaml→mixed` likewise. Converting in two steps by hand can therefore give a different result from asking for the pair directly — which is also why two consecutive conversions never fuse (`contracts/expressions.md`, *Fusion*).
- **The scalar block is not uniform.** `int→float`, `float→int` and `…→str` are **T** (the bytes are unchanged and only the reading differs), while `bool↔int` and `bool↔float` are **V** (the serialized form genuinely differs: `true` versus `1`).

**Deep celltypes are not in this matrix.** `deepcell`, `deepfolder`, `folder` and `module` are not among the 13, and `convert_checksum` raises `TypeError` for them. Their own (much smaller) conversion table is `contracts/deep-celltypes.md`, *Zero-path conversions*; the engine is what evaluates it for a pathless deep Expression (see above).

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

`conversion_possible` parses the source value, rejects `dict`/`list`/non-scalar arrays, and serializes `builtins.<target>(value)`. A `float` target must produce a finite result; a non-finite result raises `SeamlessConversionError` instead of being serialized as JSON `null`. Value rules: `binary→plain` goes through `orjson` numpy encoding and then canonical `plain` (it rejects non-finite floats first, so NaN and infinity raise here as they do in direct `plain` serialization, instead of being written as JSON `null` by `orjson`); `plain→binary` requires an int, float, bool or list whose `np.array` is not dtype `object`; `bool↔int/float` apply the builtin.

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
- **The engine's only caller is empty-path Expression evaluation** (which is why the ordering note above is vacuous here), and a new buffer it produces is not a private side effect: it is recorded as the result of that empty-path Expression — `(checksum, "", source, target)` — in the process-local Expression cache and, when configured, the database `expression` table. A later conversion between the same two celltypes for the same checksum is therefore an Expression-identity cache hit, not a second value-level conversion. See `contracts/expressions.md`.

`conversion_needs_buffer(checksum, source, target) -> bool` is a dry run. It returns `True` only if the conversion would call `get_buffer`. A conversion that succeeds or fails from the checksum alone (trivial rule, virtual value, or cached HashType disproof) returns `False`. Expression evaluation uses it to decide whether an empty-path expression can be evaluated locally or must run where the data is.

## Implementation status and current limitations

These are current behaviour, not scheduled fixes — each is described in full where it first comes up above; this section only collects them:

- **`checksum → X` is not validated against `X`.** See "Conversions involving `checksum`" above.
- **Large integers lose precision.** `orjson` turns an integer outside the unsigned 64-bit range into a float, so `int` and `plain` readings of it are imprecise. See "Large integers" above.
- **`bytes` reads return inconsistent types.** A non-null reading returns a `Buffer` object; the null reading returns `b""`. See the reference-parser table above.
- **The `str` spelling of a boolean is not symmetric.** Reading the `true` buffer as `str` gives `"True"` (the virtual-values table), while serializing `True` as `str` writes `b"true\n"` (the serialization table), so a `bool` does not round-trip through `str`.

The false-rejection family that HashType used to cause (`X → checksum`, the `int`/`float` targets, the never-disproved chains, `deserializable_as("bool")`, the broken `SEMANTIC` flag) is fixed; see `contracts/hashtype.md`, "Current limitations", for what is left there. Those were *false rejections* — breaches of the false-negative property, not conservatism — which is why they were bugs rather than accepted imprecision.

## Agent guidance

- Compare identities by checksum, never by deserialized value.
- For values of the same celltype, you can normally assume that one value has one checksum *if the buffer was serialized by Seamless*. For arbitrary files/buffers, you can never assume this.
- Prefer conversions along hierarchy edges (trivial) when you want to avoid buffer I/O; reinterpretations need a parse unless a virtual value or HashType settles them.
- Do not print `str(checksum)` into machine-readable output; use `.hex()`.
- Expect `int` readings to truncate, and `bool` readings to accept only canonical boolean checksums.
- Act on a HashType `False`, never on a `True` or a `None` (`contracts/hashtype.md`).
- A conversion you want applied *after* a path selection is the ordinary case and needs nothing special (`contracts/expressions.md`, *Application order*). A conversion you want applied *before* a path is a second Expression, and costs a parent-sized buffer unless the conversion is trivial or reinterpret.
- None of this page applies to `deepcell`, `deepfolder`, `folder` or `module`: use `contracts/deep-celltypes.md`.
