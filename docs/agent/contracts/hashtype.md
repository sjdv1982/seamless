# HashType (Contract)

`HashType` classifies a **checksum** by the structure of its buffer. It lets Seamless make deserialization, conversion and path decisions at the checksum level, rejecting impossible work without fetching or parsing a buffer. It replaces the old `BufferInfo` decision layer: no seamless-core, seamless-transformer, seamless-remote or seamless-dask code reads or writes `BufferInfo`.

Celltypes, the reference parser and the conversion engine are defined in `contracts/celltypes-and-conversion.md`. HashType classifies only the 13 celltypes; the deep celltypes (`deepcell`, `deepfolder`, `folder`) are outside its vocabulary, and `contracts/deep-celltypes.md` records what that currently means for them.

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

The rules below preserve this property; current limitations are conservative (`None` or an
over-permissive capability), not false rejections.

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
- an Expression publishes a result that has a buffer. This covers both local evaluation and remote evaluation, where the worker's `evaluate_expression_async` publishes.

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

### `capabilities(source_celltype) -> set` (expression capability)

Records which path steps the **root** structure admits: `"SEQ"` (positional item/slice) and `"MAP"` (string key).

| Source celltype | Capabilities |
|---|---|
| `bytes`, `text`, `str`, `python`, `ipython`, `yaml` | `{"SEQ"}` |
| `binary` | `"SEQ"` if `Rank != SCALAR`; `"MAP"` if `STRUCTURED` |
| `plain`, `mixed` | `JSON_OBJECT`/`MIXED_OBJECT` → `{"MAP"}`; `JSON_ARRAY`/`MIXED_ARRAY`/`JSON_STRING` → `{"SEQ"}`; else empty |
| other | empty |

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
- **Expression validation** (`validate_expression[_async]`): checks the source celltype, then path capability, then `conversion_feasible` for an empty path, before evaluation.
- **Retrieval validation** of a declared checksum/celltype (`validate_deserializable_as`) in `seamless.cell_class`, `seamless_transformer` (`pin_class`, `pretransformation`, `transformation_class`), `seamless_dask` and `seamless_workflow.context`.

## Current limitations

- **Remote lookup from synchronous validation inside a running event loop**: when no buffer is supplied, `ensure_hash_type` skips the database and returns `None` if the checksum is not in the local cache. A supplied buffer is classified locally and its upload is queued. Although async `parse_buffer` calls the synchronous `_parse_buffer`, it passes the buffer, so parse-time validation can classify it without a database request. Use `ensure_hash_type_async` when remote-only metadata is needed before a buffer is available.
- **JSON `true`/`false`/`null` are classified `JSON_STRING`.** For `plain` and `mixed`, path validation sees `{"SEQ"}` and can allow positional access to a scalar; parsing/evaluation still decides whether that access is valid. The classification is therefore not a proof of a JSON string: `conversion_possible` answers `None` for an unflagged `JSON_STRING` word with an `int`/`float` target, because JSON `true`/`false` convert there.
- **Untested kinds remain supported** and can arrive through `set_hash_type` or from the database, although `from_buffer` does not currently produce them. The `SEMANTIC` bit is reserved and rejected by `is_valid_word`.

## Non-goals

- **Value-level syntax and hex validation.** HashType classifies buffer bytes without parsing them for the requested celltype. It does not check `python`/`ipython`/`yaml` syntax or whether `checksum` text contains valid hexadecimal characters. Those checks belong to the parser or conversion engine. A permissive HashType answer is allowed; only `False` is used to reject work.
