# HashType (Contract)

`HashType` classifies a **checksum** by the structure of its buffer. It lets Seamless make deserialization, conversion and path decisions at the checksum level, rejecting impossible work without fetching or parsing a buffer. It replaces the old `BufferInfo` decision layer: no seamless-core, seamless-transformer, seamless-remote or seamless-dask code reads or writes `BufferInfo`.

Celltypes, the reference parser and the conversion engine are defined in `contracts/celltypes-and-conversion.md`. HashType classifies only the 13 celltypes; the deep celltypes (`deepcell`, `deepfolder`, `folder`) are outside its vocabulary, and **asking it about one is a caller error, not a question with an answer** — see *Queries* below. `contracts/deep-celltypes.md` owns deep feasibility and records what the current code does instead.

## Where this page sits: the stack

Each layer is defined **on top of** the one before it, and no page re-derives the one below it.

| Layer | Page | What it adds |
|---|---|---|
| 1. **Celltypes and the type hierarchy** | `contracts/celltypes-and-conversion.md` | which checksums are valid as which celltype, and the subtype→supertype edges |
| 2. **HashType** | **this page** | a checksum-level classification that **disproves** readings and conversions without fetching a buffer |
| 3. **Conversion** | `contracts/celltypes-and-conversion.md`, *Conversion engine* | the rule table, built on top of the hierarchy, using layer 2 to refuse or skip work before any buffer is fetched |
| 4. **Expressions** | `contracts/expressions.md` | path steps plus at most one conversion, in that order (**project, then convert**); layer 3 is exactly the empty-path case |
| 5. **Cells** | `contracts/cells.md` | a Cell is a *deferred* Expression |

HashType is the only layer that both of its neighbours consult directly: the reference parser and the conversion engine of layer 1/3 call it before touching bytes, and layer 4 calls it (`validate_expression`) before evaluating anything. **HashType never decides that work is possible** — see the next section.

**The deep celltypes are outside HashType's vocabulary, by ruling and not by omission.** `deepcell`, `deepfolder`, `folder` and `module` classify nothing here, and a query about one **raises**; their feasibility is structural and is settled at Expression construction by `contracts/deep-celltypes.md`.

Code locations:

| Concern | Module / symbol |
|---|---|
| Word, producer, queries, local cache | `seamless.checksum.hash_type` (`HashType`, `Kind`, `Length`, `DType`, `Rank`, `Flag`, `pack`, `unpack`, `is_valid_word`, `from_buffer`, `deserializable_as`, `capabilities`, `has_numeric_items`, `has_string_items`, `get_hash_type`, `get_hash_type_remote`, `set_hash_type`, `register_hash_type_for_buffer`) |
| Validation and conversion feasibility | `seamless.checksum.hash_type_validation` (`HashTypeValidationError`, `ensure_hash_type[_async]`, `validate_deserializable_as[_async]`, `validate_expression[_async]`, `conversion_feasible`) |
| Upload queue | `seamless.caching.buffer_writer.register_hash_type` |
| Remote client | `seamless_remote.database_remote.get_hash_type` / `set_hash_type` |
| Database | seamless-database `HashType` model → table `hash_type` (`checksum` primary key, `hash_type` integer); request type `hash_type` |

## The false-negative property

**HashType may answer "unknown", but it must never reject a valid deserialization or conversion.** A `False` from a query is a proof of impossibility. `True` and `None` are not guarantees: the reference parser or the conversion engine still makes the final decision. Callers act only on `False`, by raising `HashTypeValidationError` (a `ValueError` subclass; error-envelope kind `"hash_type_validation"`).

The property is kept by **narrowing the domain rather than widening the vocabulary**: a query is asked only about the 13 celltypes it classifies, and anything else raises (*Queries*). Deep feasibility is decided before HashType is ever consulted (`contracts/deep-celltypes.md`).

The rules below preserve this property; current limitations are conservative (`None` or an
over-permissive capability), not false rejections. A *false rejection* is therefore a bug of a
different class from imprecision, which is why the false-rejection family fixed in `0d3ccfb` /
`827bd5b` was treated as a defect rather than as accepted conservatism
(`contracts/celltypes-and-conversion.md`, *Implementation status*).

**Consumers use `False` only to reject work.** A `True` or `None` does not guarantee that parsing or
conversion will succeed; the reference parser or conversion engine still makes the final decision.
The conversion engine has one identity shortcut: `bytes→mixed` keeps the checksum when the cached
word already identifies it as mixed.

## The word

A HashType is a 13-bit integer (`pack`/`unpack`; `HashType.word`). It is a frozen dataclass with these fields:

| Bits | Field | Values |
|---|---|---|
| 0–3 | `Kind` | `RAW_BYTES`=0, `NUMPY`=1, `MIXED_OBJECT`=2, `MIXED_ARRAY`=3, `RAW_TEXT`=4, `JSON_OBJECT`=5, `JSON_ARRAY`=6, `JSON_STRING`=7, `JSON_NUMBER`=8, `UNTESTED`=9, `UTF8_UNTESTED`=10, `JSON_UNTESTED`=11 |
| 4–5 | `Length` | `SHORT` (<64 bytes), `EQ64` (=64), `MEDIUM` (65–1000), `LONG` (>1000) |
| 6–7 | `DType` | `NA`, `NUMERIC` (NumPy kinds `biufc`), `NONNUMERIC`, `STRUCTURED` (has fields) |
| 8–9 | `Rank` | `SCALAR`, `D1`, `D2`, `D3PLUS` |
| 10–12 | `Flag` | `NUMERIC_SCALAR`=1, `NUMPY_BYTES`=2, `SEMANTIC`=4 (reserved) |

Well-formedness (`is_valid_word`; enforced locally, by the remote client, and by the database):

- `DType != NA` if and only if `Kind == NUMPY`. `Rank != SCALAR` only for `NUMPY`.
- `NUMPY_BYTES` only with `NUMPY` + `NONNUMERIC` + `SCALAR` (a 0-d dtype-`S` array).
- `JSON_NUMBER` requires `NUMERIC_SCALAR`. `NUMERIC_SCALAR` is allowed only on `JSON_NUMBER` or `JSON_STRING`.
- The `SEMANTIC` bit is reserved; words with it set are invalid.

Derived properties: `is_utf8` (`RAW_TEXT`, the JSON kinds, `UTF8_UNTESTED`, `JSON_UNTESTED`); `is_json` (the JSON kinds, `JSON_UNTESTED`); `is_untested`; `is_numpy`; `is_mixed`; `mic` (most-informative celltype: `RAW_BYTES`/`UNTESTED`→`bytes`, `RAW_TEXT`/`UTF8_UNTESTED`→`text`, `NUMPY`→`binary`, `MIXED_*`→`mixed`, `JSON_OBJECT`/`JSON_ARRAY`/`JSON_UNTESTED`→`plain`, `JSON_STRING`→`str`, `JSON_NUMBER`→`float`).

The untested kinds are placeholders that record less knowledge. The only producer in current code, `from_buffer`, never emits them. They can arrive only through `set_hash_type` or from the database.

## Producer: `from_buffer`

`HashType.from_buffer(buffer)` classifies by the **bytes only**.

1. Starts with `b"\x93NUMPY"`: `NUMPY`. The file is loaded with `np.load(allow_pickle=False)` to read `DType`, `Rank` and `NUMPY_BYTES`.
2. Starts with `b"\x94SEAMLESS-MIXED"`: `MIXED_OBJECT` or `MIXED_ARRAY`, from the root type in the form header. Any other root type raises `ValueError`.
3. Not UTF-8: `RAW_BYTES`.
4. Otherwise the whole text is parsed with `orjson.loads`: object → `JSON_OBJECT`; array → `JSON_ARRAY`; string → `JSON_STRING` (plus `NUMERIC_SCALAR` if it parses as a finite float); number → `JSON_NUMBER` + `NUMERIC_SCALAR`; `true`/`false`/`null` → `JSON_STRING` with no flags; not JSON → `RAW_TEXT`.

`Length` is always the byte-length bucket.

**When it runs.** A HashType is computed and registered (`register_hash_type_for_buffer` → `set_hash_type`) whenever:

- a checksum is calculated from a buffer (`Buffer.get_checksum`, `cached_calculate_checksum[_sync]`);
- a `Buffer` is constructed with an explicit `checksum=`;
- `ensure_hash_type[_async]` is given a buffer for an unclassified checksum;
- an Expression evaluation produces a result buffer. This covers both local evaluation and remote evaluation, where the classification is done by the worker that holds the buffer. (Registering a HashType is neither *recording* a result checksum nor *publishing* a buffer; it is metadata about a checksum, and it travels through the database — `contracts/expressions.md`, *Evaluating, recording identity and publishing*.)

## Storage and tightening

- **Local**: a process-wide dict `checksum → word` (`get_hash_type_cache()`), guarded by an `RLock`.
- **Remote**: seamless-database table `hash_type`. `GET` of type `hash_type` returns the word or `null`. `PUT` of type `hash_type` validates the word with seamless-core's `is_valid_word` (the database imports seamless-core).
- **Tightening only.** One rule is used locally (`set_hash_type`) and in the database (`HashType.create`, inside an `IMMEDIATE` transaction): `_hash_type_implies(tighter, looser)`.
  - `Length` must be equal.
  - A looser `UNTESTED` is implied by any word, `UTF8_UNTESTED` by any `is_utf8` word, and `JSON_UNTESTED` by any `is_json` word.
  - A concrete word is implied only by an identical word.

| Incoming vs stored | Outcome |
|---|---|
| equal, or looser (implied by stored) | ignored; stored word kept; local write queues no upload |
| tighter (implies stored) | replaces the stored word |
| contradictory | logged as an error; local `set_hash_type` raises `ValueError`; the database answers 409, which the remote client (`database_client.set_hash_type`) raises as `ValueError` |

- **Upload.** A local change is queued on the buffer writer (`buffer_writer.register_hash_type`, deduplicated per `(checksum, word)`). It is sent with `database_remote.set_hash_type` when `seamless_remote` is importable. A word loaded from the database (`get_hash_type_remote`) enters the local cache without being uploaded again.

## Lookup

| Function | Order |
|---|---|
| `get_hash_type(cs)` | local cache only |
| `await get_hash_type_remote(cs)` | local cache → database |
| `ensure_hash_type(cs, buffer=None)` (sync) | local cache → if `buffer` is supplied, classify/register it and queue its upload; otherwise, **if no event loop is running**, query the database (via `asyncio.run`). **Inside a running event loop with no buffer, it returns `None` after the local cache.** |
| `await ensure_hash_type_async(cs, buffer=None)` | local cache → database → classify `buffer` if given |

## Queries

### The domain of every query on this page

Each query below takes its celltypes from **the 13, and only the 13**. A name outside them — a deep celltype or `module` — is a **caller error and raises `ValueError`**. It is never answered `False`, never `None` and never the empty set, because none of those is a classification of anything: the question was not HashType's to answer (`contracts/deep-celltypes.md`, *Where deep validation happens*).

| Query | Domain | Outside it |
|---|---|---|
| `deserializable_as(celltype, *, checksum)` | `celltype` ∈ the 13 | `ValueError` |
| `capabilities(source_celltype)` | `source_celltype` ∈ the 13 | `ValueError` |
| `conversion_feasible(hash_type, source, target, *, checksum)` | `source` **and** `target` ∈ the 13 | `ValueError` |
| `has_numeric_items` / `has_string_items` | as `capabilities` | `ValueError` |

**Inside the domain, an empty answer is a real answer.** `capabilities` returns the empty set for `int`, `float`, `bool` and `checksum` because those admit no path step at all — that is a classification, not a shrug. Likewise a `False` from `deserializable_as` is a proof, while `None` is "not disproved".

### `deserializable_as(celltype, *, checksum) -> True | False | None`

`checksum` is a required keyword because null and boolean deserialization depend on the exact
checksum. Omitting it raises `TypeError` at the call site.

Evaluated in order:

1. `checksum` is either null checksum: `True` (null is valid for every celltype).
2. `bytes`: `True`.
3. `bool`: `True` only if `checksum` is one of the four canonical boolean checksums; otherwise `False`.
4. Untested kinds: `text/yaml/python/ipython` → `True` if `is_utf8` else `None`; `plain/mixed` → `True` if `is_json` else `None`; `str` → `True` for null/boolean checksums else `None`; `int/float` → `False` if `LONG` else `None`; `binary` → `None` for `UNTESTED`, else `False`; `checksum` → `None` if `EQ64` else `False`.
5. Concrete kinds:

| Celltype | Result |
|---|---|
| `text`, `yaml`, `python`, `ipython` | `is_utf8` (syntax is not checked; the parser checks it) |
| `plain` | `is_json` |
| `str` | kind `JSON_STRING` or `JSON_NUMBER`, or a null/boolean checksum |
| `int`, `float` | `False` if `LONG`; else `NUMERIC_SCALAR` is set |
| `binary` | kind `NUMPY` |
| `mixed` | kind not `RAW_BYTES`/`RAW_TEXT` |
| `checksum` | kind `RAW_TEXT` or `JSON_NUMBER` (an all-digit digest is a JSON number) and `EQ64` (hex validity is left to the parser) |

**A `celltype` outside the 13 above** — a deep celltype (`deepcell`, `deepfolder`, `folder`) or `module` — is **a caller error: `deserializable_as` raises `ValueError`.** It does not answer `False`, and it does not learn the deep names. Deep shapes are decided elsewhere, before any HashType query: a pathless deep Expression by the conversion engine's table, a pathed one by the deep table of `contracts/deep-celltypes.md` — both structural, both settled at Expression construction, because deep feasibility never turns on the data behind the checksum (`contracts/expressions.md`, *When an Expression is vetted*).

**Why raise rather than widen.** Teaching `deserializable_as` the four names would make HashType the owner of deep feasibility, and the legal deep set is *smaller* than "anything goes", not larger — so the widened function would have to carry the whole deep table, and its `False` answers would then be structural refusals dressed as classification. Raising keeps one rule per layer and keeps the false-negative property a property of the 13.

### `capabilities(source_celltype) -> set` (expression capability)

Records which path steps the **root** structure admits: `"SEQ"` (positional item/slice) and `"MAP"` (string key).

| Source celltype | Capabilities |
|---|---|
| `bytes`, `text`, `str`, `python`, `ipython`, `yaml` | `{"SEQ"}` |
| `binary` | `"SEQ"` if `Rank != SCALAR`; `"MAP"` if `STRUCTURED` |
| `plain` | `JSON_OBJECT` → `{"MAP"}`; `JSON_ARRAY`/`JSON_STRING` → `{"SEQ"}`; else empty |
| `mixed` | `NUMPY` follows the `binary` rule; `JSON_OBJECT`/`MIXED_OBJECT` → `{"MAP"}`; `JSON_ARRAY`/`MIXED_ARRAY`/`JSON_STRING` → `{"SEQ"}`; else empty |
| `int`, `float`, `bool`, `checksum` | empty — **no path step is ever admitted** over a scalar or a reference |

**A deep source celltype is never routed here.** A deep path — exactly one string-item step — is a
structural rule, settled by the deep table at construction time (`contracts/deep-celltypes.md`,
*Paths*), so `capabilities` is not the oracle that admits or refuses it. A flat index is a
`JSON_OBJECT`, and ordinary `plain`/`mixed` queries classify that buffer as a map; deep path
admission remains structural and is settled before this query.

`has_numeric_items` and `has_string_items` return `True`/`False`/`None` item-type hints for the same sources. Path validation (`_validate_path_capability`) skips untested words and checks a step only while the root word still types the value: a slice keeps the capabilities; an item step stops checking, except that any further step after a `bytes` item is rejected (the item is an int) and a `NUMERIC` NumPy array with rank below `D3PLUS` admits as many positional item steps as its rank.

### `conversion_feasible(hash_type, source, target, *, checksum) -> True | False | None`

This is the checksum-level conversion query used before any conversion work. Rules:

- A null checksum, or `source == target`: `True`.
- `deserializable_as(source, checksum=checksum)` is `False`: `False`.
- `target == "checksum"`: `True`.
- The pair is mapped once through `conversion_equivalent`. After that:
  - `conversion_chain`: evaluate the first step. `False` disproves the chain. If the first step
    preserves the checksum (`conversion_trivial` or `conversion_reinterpret`), evaluate the
    second step on the same word; its `False` also disproves the chain. If the second step always
    succeeds on valid input (`conversion_trivial` or `conversion_reformat`), return the first
    step's answer. Otherwise return `None`; in particular, do not predict through a first step
    that creates a new buffer.
  - `conversion_forbidden` → `False`;
  - `conversion_trivial` or `conversion_reformat` → `True`;
  - `conversion_reinterpret` → `deserializable_as(target, checksum=checksum)`.
- `conversion_possible`: untested → `None`. Concrete:
  - `int`/`float` target:
    - NumPy word, regardless of source celltype: non-scalar → `False`; `NUMERIC` → `True`; otherwise `None`.
    - `JSON_OBJECT`, `JSON_ARRAY`, `MIXED_OBJECT`, `MIXED_ARRAY` → `False`.
    - `JSON_NUMBER` or `NUMERIC_SCALAR` set → `True`.
    - Unflagged `JSON_STRING` → `None`.
    - `LONG` does not decide this category; the length limit remains in deserialization/reinterpretation checks.
  - `mixed→str`: `False` for `JSON_OBJECT`/`JSON_ARRAY`, otherwise `True`.
  - Everything else, including `bool` targets: `None`.
- `conversion_values`: untested → `None` (except for the earlier `checksum` target rule). Concrete:
  - `checksum→X`: `None`.
  - `plain→binary`: `False` for `JSON_OBJECT`.
  - `binary→plain`: `True` for `NUMERIC`/`STRUCTURED`.
  - Everything else: `None`.

## Where HashType is consulted

- **Reference parser** (`_parse_buffer`): after virtual values, `validate_deserializable_as(checksum, celltype, buffer=buffer)` runs before any parsing.
- **Conversion engine** (`seamless.checksum.convert`): before a source buffer is fetched, via `validate_deserializable_as` without a buffer. `bytes→mixed` also keeps the checksum when the cached word says `mixed`.
- **Expression validation** (`validate_expression[_async]`): checks the source celltype, then path capability, then `conversion_feasible` for an empty path, before evaluation. This is the **evaluation-time** half of Expression vetting, and it is asked only about the 13; the structural half runs at construction and never consults HashType (`contracts/expressions.md`, *When an Expression is vetted*). **That order is *project, then convert* read at the checksum level** (`contracts/expressions.md`, *Application order*): the capability check is asked of the **input** celltype, because the path walks the input's structure, and `conversion_feasible` is asked only where there is no path to walk. There is deliberately no query on this page that classifies "the value a path would select" — that is data behind the checksum, and HashType never looks there.
- **Retrieval validation** of a declared checksum/celltype (`validate_deserializable_as`) in `seamless.cell_class`, `seamless_transformer` (`pin_class`, `pretransformation`, `transformation_class`), `seamless_dask` and `seamless_workflow.context`.

## Current limitations

- **Remote lookup from synchronous validation inside a running event loop**: when no buffer is supplied, `ensure_hash_type` skips the database and returns `None` if the checksum is not in the local cache. A supplied buffer is classified locally and its upload is queued. Although async `parse_buffer` calls the synchronous `_parse_buffer`, it passes the buffer, so parse-time validation can classify it without a database request. Use `ensure_hash_type_async` when remote-only metadata is needed before a buffer is available.
- **JSON `true`/`false`/`null` are classified `JSON_STRING`.** For `plain` and `mixed`, path validation sees `{"SEQ"}` and can allow positional access to a scalar; parsing/evaluation still decides whether that access is valid. The classification is therefore not a proof of a JSON string: `conversion_possible` answers `None` for an unflagged `JSON_STRING` word with an `int`/`float` target, because JSON `true`/`false` convert there.
- **Untested kinds remain supported** and can arrive through `set_hash_type` or from the database, although `from_buffer` does not currently produce them. The `SEMANTIC` bit is reserved and rejected by `is_valid_word`.

## Non-goals

- **Deep celltypes.** HashType classifies buffers, and a deep buffer is an ordinary `plain` buffer, so a deep index *does* get a `JSON_OBJECT` word like any other. What HashType does not do is know the four names: they are outside `deserializable_as` (which raises for them), outside `capabilities` and outside `conversion_feasible`. `contracts/deep-celltypes.md` owns deep feasibility, and decides it structurally, before any query on this page is reached.
- **Value-level syntax and hex validation.** HashType classifies buffer bytes without parsing them for the requested celltype. It does not check `python`/`ipython`/`yaml` syntax or whether `checksum` text contains valid hexadecimal characters. Those checks belong to the parser or conversion engine. A permissive HashType answer is allowed; only `False` is used to reject work.
