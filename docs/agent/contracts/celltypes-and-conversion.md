# Celltypes, Null, and Conversion (Contract)

This page defines what a celltype means, how the canonical null works, and how the checksum-level conversion engine converts a checksum from one celltype to another. The companion page `contracts/hashtype.md` defines the `HashType` classification that the engine and the parser use to reject impossible work without touching buffers. The deep celltypes (`deepcell`, `deepfolder`, `folder`) have their own conversion and path table in `contracts/deep-celltypes.md`; this page says only how the engine admits them.

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

- the **deep celltypes** `deepcell`, `deepfolder` and `folder`. They are not among the 13 celltypes below and not in the 13 × 13 rule table. Their conversions are defined in `contracts/deep-celltypes.md`, *Zero-path conversions*; the engine on this page accepts the three names and evaluates that table for a pathless deep Expression (*Deep celltypes in the engine*, below);
- **`module`**, which is not a deep celltype (`contracts/deep-celltypes.md`, *`module` is not a deep celltype*) and is outside the engine altogether.

At the buffer layer, `Buffer._map_celltype` serializes and parses all four names as `plain`.

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

Out of scope here: Expressions, Cells, pins, mounts and the workflow Context. How a celltype is chosen, declared and converted on a handle — `celltype` as the output type, the read-only `input_celltype`, retyping, and where null and empty `bytes` show up in writes and reads — is in `contracts/cells.md`.

## Celltypes

`seamless.checksum.celltypes.celltypes` has exactly 13 entries:

`binary`, `mixed`, `text`, `python`, `ipython`, `plain`, `yaml`, `str`, `bytes`, `int`, `float`, `bool`, `checksum`

- **Storage celltypes**: `bytes` (raw), `binary` (NumPy `.npy` buffer), `mixed` (Seamless-mixed format, or pure JSON, or `.npy`), `plain` (JSON).
- **Text celltypes**: `text` (UTF-8), with the code/markup subtypes `python`, `ipython` and `yaml`.
- **Scalar celltypes**: `str`, `int`, `float` and `bool` are *readings* of JSON-compatible buffers, not separate storage formats.
- **`checksum`**: the value is a `Checksum`. The buffer is the bare 64-character lowercase hex digest, with no trailing newline.

**What each component accepts.**

| Component | Accepts | Anything else |
|---|---|---|
| reference parser, serializer | the 13 | `TypeError` |
| conversion engine (`convert_checksum`, `conversion_needs_buffer`) | the 13, plus `deepcell`, `deepfolder` and `folder` | `TypeError` — this is where `module` lands |

Within the engine's domain, a pair with a deep celltype on either side is either one of the legal deep conversions or an **illegal deep pair**. An illegal deep pair raises `SeamlessConversionError`, decided from the two celltypes alone: no buffer is fetched, and `conversion_needs_buffer` answers `False`. It never raises `TypeError`.

The deep celltypes are distinct celltypes whose buffers are plain JSON. Their conversion table, member-celltype rules and one-step path rule are defined once, in `contracts/deep-celltypes.md`; nothing on this page re-derives them. The division of labour is: a **pathless** Expression, deep or not, is vetted by the conversion engine, and a **pathed** deep Expression by the deep path table (`contracts/expressions.md`, *When an Expression is vetted*). HashType is never asked about a deep name (`contracts/hashtype.md`, *Queries*).

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

**The conversion rule table is built on this table.** `conversion_trivial` is *exactly* the set of edges above — that is what "trivial" means: the checksum is kept, nothing is validated and no buffer is fetched. Every other category is defined by how far it departs from a hierarchy edge: `conversion_reinterpret` is a hierarchy edge walked *backwards* (same checksum, but the target reading must be validated), and `conversion_reformat`, `conversion_possible` and `conversion_values` are pairs with no edge at all.

Consequences:

- `bytes` is not a universal supertype. `mixed → bytes` and `binary → bytes` are *reformat* rules (*Reformat rules*, below).
- `yaml → plain` is not trivial. It runs the YAML parser and writes a new canonical `plain` buffer.
- `int` and `float` accept the same checksums. Which one you use decides only the reading.
- `checksum` is outside the hierarchy. It has no trivial edges, and every conversion to or from it is value-level.
- The canonical null is valid (deserializable) as every celltype (*Canonical null*). That is a statement about readings, **not** about conversions: it does not make a forbidden pair legal (*Null and conversion legality*).

## Checksum identity vs values

- **Identity stays with the checksum.** One value can have several checksums. Examples: `b"true"` and `b"true\n"`; compact and indented JSON for the same object; `b"4.5\n"` read as `int` (value `4`) and the canonical `int` buffer `b"4\n"`.
- A checksum-preserving conversion (trivial or reinterpret) keeps the source checksum, even when the target celltype's serializer would write different bytes for the resulting value. Seamless never replaces a checksum with the checksum of the re-serialized value. The one exception is empty bytes → null (below).
- **"Deserializable as X"** means the reference parser (`_parse_buffer`) accepts the buffer as X. It does **not** mean that re-serializing the value as X gives back the same checksum.

## Canonical null

- `NULL_BUFFER = b"null\n"`. `NULL_CHECKSUM` is its SHA-256: `38e0b9de817f645c4bec37c0d4a3e58baecccb040f5718dc069a72c7385a0bed`.
- **Serialization.** `_serialize(None, celltype)` returns `NULL_BUFFER` for every celltype. Serializing `b""` as `bytes` also returns `NULL_BUFFER`, so `Buffer(b"", "bytes")` has `NULL_CHECKSUM`.
- **Canonicalization of empty bytes.** `canonicalize_checksum(checksum, celltype)` maps `sha256(b"")` to `NULL_CHECKSUM` **only when `celltype == "bytes"`**. An Expression key applies it to its input checksum and input celltype. A raw `Buffer(b"")` made without a celltype still has checksum `sha256(b"")`: canonicalization is not applied to raw buffers.
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

Order of operations:

1. `virtual_value`;
2. `validate_deserializable_as(checksum, celltype, buffer=buffer)`, which raises `HashTypeValidationError` when HashType proves the reading impossible (`contracts/hashtype.md`);
3. the per-celltype rule below.

| Celltype | Accepts / returns | A failure raises |
|---|---|---|
| `text`, `python`, `ipython`, `yaml` | UTF-8 decode, then strip all trailing `\n`; returns the text. `python` must pass `ast.parse`, `ipython` must pass `ipython2python`, `yaml` must pass `yaml.safe_load` (the value is still the text). | `HashTypeValidationError` |
| `plain` | Decode, strip trailing `\n`, then `orjson.loads` | `ValueError` |
| `binary` | Seamless-mixed deserializer; storage must be `pure-binary` (an `.npy` buffer) | `ValueError` |
| `mixed` | Seamless-mixed deserializer (`.npy`, Seamless-mixed format, or JSON). A zero-dimensional NumPy leaf reads back as a NumPy scalar, at the top level and nested in a dict or list alike. | `ValueError` |
| `bytes` | Returns the `Buffer` object itself; the null reading is `b""` | — (every buffer is valid `bytes`) |
| `str` | `orjson` parse; a JSON string, number or boolean gives `str(value)` (so `4.5` → `"4.5"`, `1e3` → `"1000.0"`); objects and arrays are rejected | `ValueError` |
| `int`, `float` | Buffers over 1000 bytes are rejected. `orjson` parse; accepts a finite JSON number, or a JSON string that parses as a finite float. `float` → `float(v)`. `int` → `int(v)`, falling back to `int(float(v))`. A boolean checksum is refused at step 1. | `ValueError` |
| `bool` | Only virtual values (above); anything else is refused at step 1 | `ValueError` |
| `checksum` | Decode; must construct a `Checksum` (64 hex characters) | `HashTypeValidationError` |

**Exception classes.** Every failure to read a buffer as one of the 13 raises a `ValueError`; a celltype outside the 13 raises `TypeError`. Within that:

- **`HashTypeValidationError` is contract** for three cases: a HashType disproof at step 2 (whatever the celltype), a failed syntax check in the text row, and a failure in the `checksum` row.
- **A plain `ValueError`, not `HashTypeValidationError`,** is contract for the step-1 refusals: `bool` over a non-boolean checksum, and `int`/`float` over a boolean checksum. Both are decided from the checksum without HashType.
- **The rows marked `ValueError`** (`plain`, `binary`, `mixed`, `str`, `int`, `float`) guarantee only the `ValueError` family, and a subclass is conformant. Because the parser always holds the buffer, step 2 classifies it and refuses most malformed buffers with `HashTypeValidationError` before the per-celltype rule runs, but a caller may not rely on that; assert `ValueError`.

**`int` truncates.** Reading `b"4.5\n"` as `int` succeeds and returns `4`. The JSON string `"4.5"` also gives `4`, and `-4.5` gives `-4`. Serializing a value as `int` truncates the same way (`Buffer(-4.5, "int")` → `b"-4\n"`).

**Large integers.** Numbers are parsed by `orjson`, which returns a float for an integer outside the unsigned 64-bit range. `int` and `plain` readings of such integers therefore lose precision. This is contract (*Deliberate imprecisions*).

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

**Only a HashType `False` is a proof.** A `False` from `deserializable_as` or `conversion_feasible` is a proof of impossibility, and it is the *only* HashType answer the engine acts on to refuse work. `True` and `None` mean "not disproved"; the parser or the value-level rule still decides. The asymmetry is owned by `contracts/hashtype.md`, *The false-negative property*.

**The engine is only ever the empty-path case.** Its only caller is empty-path Expression evaluation (`seamless.checksum.expression`). With no path step, *project, then convert* (`contracts/expressions.md`, *Application order*) is vacuous here. Once a path is involved, the ordering is that page's rule: the conversion is applied to **what the path selected**, never to the whole input. A convert-then-project recipe is therefore two Expressions, the first of which is an empty-path conversion whose new buffer is parent-sized.

### Rule table (`seamless.checksum.conversion`)

Every ordered pair of distinct celltypes among the 13 is in exactly one category. `check_conversions()` runs at import and raises `SeamlessConversionError` on a missing pair, a duplicate, or a circular mapping, so the matrix below is **exhaustive by construction**: all 13 × 12 = **156** ordered pairs are classified.

Six categories are **terminal** — they say what happens. Two are **indirections** — they say which other pair to evaluate instead:

| Category | Code | Checksum | Guaranteed for valid input? | Members |
|---|---|---|---|---|
| `conversion_trivial` | **T** | same | **yes** — no validation, no buffer | 18 pairs: `binary→mixed`, `bool→plain`, `bool→str`, `float→int`, `float→plain`, `float→str`, `int→float`, `int→plain`, `int→str`, `ipython→text`, `plain→bytes`, `plain→mixed`, `plain→yaml`, `python→ipython`, `python→text`, `str→plain`, `text→bytes`, `yaml→text` |
| `conversion_reinterpret` | **RI** | same | no — the target reading is validated and may raise | 14 pairs: `bytes→plain`, `bytes→text`, `mixed→binary`, `mixed→plain`, `plain→bool`, `plain→float`, `plain→int`, `plain→str`, `str→bool`, `str→float`, `str→int`, `text→ipython`, `text→python`, `text→yaml` |
| `conversion_reformat` | **RF** | may change | **yes** | 10 pairs: `binary→bytes`, `bytes→binary`, `bytes→mixed`, `ipython→python`, `mixed→bytes`, `plain→text`, `str→text`, `text→plain`, `text→str`, `yaml→plain` |
| `conversion_possible` | **P** | new buffer | no | 7 pairs: `binary→bool`, `binary→float`, `binary→int`, `mixed→bool`, `mixed→float`, `mixed→int`, `mixed→str` |
| `conversion_values` | **V** | new buffer, or a dereference for `checksum` | no | 30 pairs: `binary→plain`, `plain→binary`; `bool→float`, `bool→int`, `float→bool`, `int→bool`; and every `X→checksum` and `checksum→X` (12 each) |
| `conversion_forbidden` | **X** | — | **never** — always raises, null included | 16 pairs: `python/ipython↔yaml`, `python/ipython→int/float/bool`, `int/float/bool→python/ipython` |
| `conversion_equivalent` | **=a→b** | — | — | 32 pairs, each mapped to a different pair to evaluate instead |
| `conversion_chain` | **»m** | — | — | 29 pairs, each evaluated as `source→m` followed by `m→target` |

**Resolving an indirection.** `=a→b` means: discard this pair and evaluate `(a, b)`. `»m` means: convert `source→m`, then `m→target`. Either may resolve again — `binary→str` is `»bytes`, and `bytes→str` is in turn `»plain` — and `check_conversions()` proves that every chain of resolutions terminates in a terminal category without a cycle.

A **legal pair** is the diagonal, any of the 156 pairs that is not in `conversion_forbidden`, or a legal deep zero-path conversion. A **forbidden pair** is one of the 16 above; an **illegal deep pair** is any other pair with a deep celltype on either side.

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

### Deep celltypes in the engine

The matrix covers only the 13. The engine additionally accepts `deepcell`, `deepfolder` and `folder` on either side and applies the zero-path table of `contracts/deep-celltypes.md`, *Zero-path conversions*: the identity, the free index conversions (`deepcell → plain`, `deepfolder → plain`, `folder ↔ deepfolder`, `deepcell → deepfolder`), which keep the checksum without fetching, and `folder → mixed`, the one deep conversion that materializes children. Every other pair with a deep name on either side is an illegal deep pair and raises `SeamlessConversionError` without fetching (*Celltypes*). `module` is not accepted: `TypeError`.

### Reformat rules (as executed)

| Pair | Behaviour |
|---|---|
| `bytes→binary` | Always fetches the buffer. `.npy` magic: validate as `binary` and keep the checksum. Otherwise: new `.npy` of a 0-d dtype-`S` array holding the bytes. |
| `bytes→mixed` | Null/boolean checksum, or cached HashType says `mixed`: keep. Otherwise fetch and classify; if it is `mixed`-deserializable, validate and keep. Otherwise, if UTF-8: new `str` buffer of the text (trailing `\n` stripped). Otherwise: new dtype-`S` `.npy`. |
| `binary→bytes` | Parse as `binary`. **Every** dtype-`S` array, of any shape (a 0-d `S{len}`, a 1-D `S1`, …), becomes `value.tobytes()` in C order, serialized as `bytes`; an empty `S` array therefore gives empty bytes, which is the canonical null. Any array whose dtype is not `S` keeps its `.npy` checksum. |
| `mixed→bytes` | `.npy` magic: as `binary→bytes`. Otherwise validate as `mixed` and keep. |
| `plain→text` | Value is a JSON string: new `text` buffer of that string. Otherwise keep. |
| `text→plain` | Null/boolean checksum, or text that `orjson` accepts: keep. Otherwise: new `plain` buffer holding the text as a JSON string. |
| `text→str`, `str→text` | Re-serialize the same value under the target celltype |
| `yaml→plain` | `yaml.safe_load`, then canonical `plain` |
| `ipython→python` | `ipython2python` |

### Possible and value rules

`conversion_possible` parses the source value, rejects `dict`/`list`/non-scalar arrays, and serializes `builtins.<target>(value)`. A `float` target must produce a finite result; a non-finite result raises `SeamlessConversionError` instead of being serialized as JSON `null`.

Value rules:

- `binary→plain` goes through `orjson` NumPy encoding and then canonical `plain`. It rejects non-finite floats first, so NaN and infinity raise here as they do in direct `plain` serialization, instead of being written as JSON `null` by `orjson`.
- `plain→binary` requires an int, float, bool or list whose `np.array` is not dtype `object`.
- `bool↔int/float` apply the builtin.
- `X→checksum` produces a `checksum`-celltype buffer whose value is **the source checksum itself** (its hex digest). It does not parse the source as a hex string.
- `checksum→X` **dereferences**: it reads the stored checksum and returns it as the result, with no new buffer. The referenced checksum is **not** validated as `X` (*Deliberate imprecisions*).

### Null and conversion legality

**The null short-circuit applies only to legal pairs; a forbidden pair or an illegal deep pair stays illegal for null** (ruled). Null being deserializable as every celltype (*Canonical null*) is a statement about readings, not a licence to convert along a pair the rule table refuses. The same distinction is drawn for HashType in `contracts/hashtype.md`: `deserializable_as` answers `True` for null everywhere, while `conversion_feasible` answers `False` for a forbidden pair even when the checksum is null.

| Pair | Canonical-null input to an empty-path Expression |
|---|---|
| legal | construction succeeds; evaluation yields the canonical null result without calling the executor |
| forbidden, or illegal deep | construction raises `ValueError`, exactly as for any other checksum; the executor, if called directly, raises `SeamlessConversionError` |

- **Which inputs count as null here.** The Expression key canonicalizes empty `bytes` to the canonical null first (*Canonical null*); the short-circuit then applies to `NULL_CHECKSUM`. A non-canonical null (`sha256(b"null")`) takes the ordinary route through the executor.
- **The executor has no null short-circuit of its own for ordinary pairs.** A null checksum goes through the rule for its pair like any other checksum. So both null forms are refused on every forbidden pair (implemented), and a null that reaches a legal pair is converted by that pair's rule — for example, `convert_checksum(NULL_CHECKSUM, "plain", "checksum", …)` produces a `checksum` buffer holding the null checksum's digest, whereas the empty-path Expression for the same pair yields null.
- **Scope, unconfirmed.** The ruling is read as covering **both** the forbidden ordinary pairs (such as `python → int`) **and** the illegal deep pairs, and the tests assume that reading. The author's confirmation of that scope is deferred; until it is given, treat the scope as an open question, not as settled contract.

*Contract ahead of code* for the construction, evaluation and deep-executor rows; see *Implementation status*.

### Executor (`seamless.checksum.convert`)

`convert_checksum(checksum, source, target, get_buffer) -> (Checksum, Buffer | None)`

- `source` and `target` must each be one of the 13 or a deep celltype, otherwise `TypeError` (*Celltypes*). `get_buffer` must be a zero-argument callable that returns a `Buffer` or `bytes`-like object; otherwise `TypeError`.
- `get_buffer` is called **only** when a rule needs content, and **at most once** per call (memoized). The engine knows nothing about buffer caches or remotes.
- `source == target`: returns `(checksum, None)` without validation.
- Return value: `(checksum, None)` when the checksum is kept; `(new_checksum, new_buffer)` when new content is serialized.
- Resolving a source value (`_value_of`) tries `virtual_value` first, then `validate_deserializable_as(checksum, celltype)` without a buffer (fails early on a HashType disproof from the local cache, or from the database when no event loop is running), and only then calls `get_buffer()` and `_parse_buffer`.
- Errors: `CacheMissError` from `get_buffer` propagates unchanged, because a missing buffer is not a failed conversion. `SeamlessConversionError` (a `ValueError` subclass) propagates. Any other exception, including `HashTypeValidationError` and the parser's `ValueError`s, is wrapped in `SeamlessConversionError("<hex> cannot be converted from <source> to <target>", …)`.
- **A new buffer is recorded, not a private side effect.** It is the result of the empty-path Expression `(checksum, "", source, target)`, stored in the process-local Expression cache and, when configured, the database `expression` table. A later conversion between the same two celltypes for the same checksum is therefore an Expression-identity cache hit, not a second value-level conversion (`contracts/expressions.md`).

`conversion_needs_buffer(checksum, source, target) -> bool` is a dry run. It returns `True` only if the conversion would call `get_buffer`. A conversion that succeeds or fails from the checksum alone (trivial rule, virtual value, cached HashType disproof, forbidden pair or illegal deep pair) returns `False`. Expression evaluation uses it to decide whether an empty-path Expression can be evaluated locally or must run where the data is.

## Deliberate imprecisions (contract)

These are contract, not limitations awaiting a fix, and tests pin them. Each is described in full where it first comes up; this section collects them:

- **`checksum → X` is not validated against `X`.** The dereference returns the stored checksum without checking that it is deserializable as `X` (*Possible and value rules*).
- **A `bytes` reading returns a `Buffer`, or `b""` for null.** A non-null checksum read as `bytes` returns the `Buffer` object itself, not a Python `bytes`; the null reading is `b""` (*Reference parser*).
- **Large integers lose precision.** `orjson` turns an integer outside the unsigned 64-bit range into a float, so `int` and `plain` readings of it are imprecise (*Reference parser*).
- **The `str` spelling of a boolean is asymmetric.** Reading the `true` buffer as `str` gives `"True"` (*Virtual values*), while serializing `True` as `str` writes `b"true\n"` (*Canonical serialization*), so a `bool` does not round-trip through `str`.

## Implementation status

Settled contract that the code does not yet implement, or implements differently. The rules above are the test oracle; each gap below is pinned by an `xfail(strict=False)` test whose reason reads "contract ahead of code". Where the code disagrees with a rule above, the rule above wins.

- **`convert_checksum` passes null through illegal deep pairs.** For either null form, a pair with a deep celltype on either side returns `(checksum, None)` before the deep legality check runs, so `convert_checksum(NULL_CHECKSUM, "deepfolder", "deepcell", …)` succeeds instead of raising `SeamlessConversionError` (*Null and conversion legality*).
- **Empty-path Expressions accept the canonical null on forbidden and illegal deep pairs.** Construction skips the shape check for a canonical-null empty-path input, so `Expression(NULL_CHECKSUM, input_celltype="python", celltype="int")` and the same over an illegal deep pair are accepted instead of raising `ValueError` (a non-null or non-canonical-null input is refused), and evaluation then returns the canonical null instead of refusing.

**Fixed, for the record.** The false-rejection family that HashType used to cause (`X → checksum`, the `int`/`float` targets, the never-disproved chains, `deserializable_as("bool")`, the broken `SEMANTIC` flag) is fixed; `contracts/hashtype.md`, *Current limitations*, lists what remains there. Those were *false rejections* — breaches of the false-negative property, not conservatism — which is why they were bugs rather than accepted imprecision. The engine's former `TypeError` for the deep celltypes is also gone: it accepts them, and deep Expressions no longer consult HashType.

## Agent guidance

- Compare identities by checksum, never by deserialized value.
- For values of the same celltype, you can normally assume that one value has one checksum *if the buffer was serialized by Seamless*. For arbitrary files/buffers, you can never assume this.
- Prefer conversions along hierarchy edges (trivial) when you want to avoid buffer I/O; reinterpretations need a parse unless a virtual value or HashType settles them.
- Do not print `str(checksum)` into machine-readable output; use `.hex()`.
- Expect `int` readings to truncate, and `bool` readings to accept only canonical boolean checksums.
- Act on a HashType `False`, never on a `True` or a `None` (`contracts/hashtype.md`).
- Do not expect null to rescue an illegal conversion: a forbidden or illegal deep pair fails for null too.
- When asserting a parse failure, assert `ValueError`; assert `HashTypeValidationError` only in the cases *Reference parser* names.
- A conversion you want applied *after* a path selection is the ordinary case and needs nothing special (`contracts/expressions.md`, *Application order*). A conversion you want applied *before* a path is a second Expression, and costs a parent-sized buffer unless the conversion is trivial or reinterpret.
- For the deep celltypes, the conversion and path rules are in `contracts/deep-celltypes.md`; this page only says that the engine accepts them. `module` is outside every table on this page.
