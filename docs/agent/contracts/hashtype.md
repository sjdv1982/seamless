# HashType (Contract)

`HashType` classifies a **checksum** by the structure of its buffer. Seamless uses it to make deserialization, conversion and path decisions at the checksum level, so that it can reject impossible work, and skip a check it has already settled, without fetching or parsing a buffer.

HashType classifies the **13 celltypes** defined in `contracts/celltypes-and-conversion.md`, and only those. Four other celltype names exist in Seamless: the three **deep celltypes** `deepcell`, `deepfolder` and `folder`, and **`module`**, which is not a deep celltype (`contracts/deep-celltypes.md`, *`module` is not a deep celltype*). This page calls them **the four structural names**. They are outside HashType's vocabulary by ruling, not by omission: a HashType query about one of them is a caller error and raises (*Queries*).

## Where this page sits: the stack

Each layer is defined **on top of** the one before it, and no page re-derives the one below it.

| Layer | Page | What it adds |
|---|---|---|
| 1. **Celltypes and the type hierarchy** | `contracts/celltypes-and-conversion.md` | which checksums are valid as which celltype, and the subtype→supertype edges |
| 2. **HashType** | **this page** | a checksum-level classification that **disproves** readings and conversions, and **proves** readings where the word settles them, without fetching a buffer |
| 3. **Conversion** | `contracts/celltypes-and-conversion.md`, *Conversion engine* | the rule table, built on the hierarchy, using layer 2 to refuse or skip work before any buffer is fetched |
| 4. **Expressions** | `contracts/expressions.md` | path steps plus at most one conversion, in that order (**project, then convert**); layer 3 is exactly the empty-path case |
| 5. **Cells** | `contracts/cells.md` | a Cell is a *deferred* Expression |

The reference parser (layer 1), the conversion engine (layer 3) and Expression validation (layer 4) all consult HashType before touching bytes. A `False` refuses work (*The false-negative property*). A `True` from `deserializable_as` proves a reading, and the conversion engine uses it to skip a fetch whose only purpose would be that check (*The positive property*). Nothing else in HashType decides that work is possible.

Code locations:

| Concern | Module / symbol |
|---|---|
| Word, producer, queries, local cache | `seamless.checksum.hash_type` (`HashType`, `Kind`, `Length`, `DType`, `Rank`, `Flag`, `pack`, `unpack`, `is_valid_word`, `from_buffer`, `deserializable_as`, `capabilities`, `has_numeric_items`, `has_string_items`, `get_hash_type`, `get_hash_type_remote`, `set_hash_type`, `register_hash_type_for_buffer`) |
| Validation and conversion feasibility | `seamless.checksum.hash_type_validation` (`HashTypeValidationError`, `ensure_hash_type[_async]`, `validate_deserializable_as[_async]`, `validate_expression[_async]`, `conversion_feasible`) |
| Upload queue | `seamless.caching.buffer_writer.register_hash_type` |
| Remote client | `seamless_remote.database_remote.get_hash_type` / `set_hash_type` |
| Database | seamless-database `HashType` model → table `hash_type` (`checksum` primary key, `hash_type` integer); request type `hash_type` |

## The false-negative property

**HashType may answer "unknown", but it must never reject a valid deserialization or conversion.**

- A `False` from any query is a **proof of impossibility**. Callers act on it by raising `HashTypeValidationError`, a `ValueError` subclass (see *Errors*).
- `None` means "unknown". Whether a `True` proves anything depends on the query: see *The positive property*.

The property is kept by **narrowing the domain rather than widening the vocabulary**: a query is asked only about the 13 celltypes, and anything else raises. Deep feasibility is decided before HashType is consulted (`contracts/deep-celltypes.md`, *Where deep validation happens*).

Where HashType is imprecise, it is imprecise conservatively: it answers `None` or reports an over-permissive capability. It never falsely rejects, and `deserializable_as` never falsely proves. A *false rejection* or a *false proof* is therefore a bug of a different class from imprecision: a defect to fix, never a conservatism to accept.

## The positive property

**A `True` from `deserializable_as(celltype, checksum=…)` is a proof that the reference parser accepts the checksum as that celltype.**

- **Only `deserializable_as` makes this promise.** A `True` from `conversion_feasible` still means only "not disproved": whether a conversion succeeds also depends on the source value, which the word does not settle. No caller acts on it. `capabilities` and the item hints are over-permissive by design (*Current limitations*).
- **Where the word cannot settle a reading, the answer is `None`, never `True`.** The word cannot settle three things:
  - `python`, `ipython` and `yaml` syntax;
  - whether 64 characters are hexadecimal, for `checksum`;
  - the payload of a Seamless-mixed buffer, of which the producer reads only the header;

  A concrete JSON scalar has no ambiguity for a `str` reading: `JSON_NULL` records parsed null, and `JSON_STRING` records strings or booleans, all of which `str` accepts. The two virtual null checksums are handled before the word is examined.

  The tables in *`deserializable_as`* follow this rule.
- **Who acts on a `True`.** Only the conversion engine, and only to skip a fetch whose sole purpose would be that same check. That means a **reinterpretation**, which keeps the checksum and whose only work is validating the target reading, and the keep branch of `bytes→mixed` (`contracts/celltypes-and-conversion.md`, *Principle*). Everywhere else, the parser needs the value and not just the verdict, so it still parses. Retrieval validation still raises only on `False`.
- **A word is a claim about the whole buffer.** Both properties rest on this.
  - `from_buffer` meets it by construction: a `NUMPY` word means that `np.load` succeeded, and a JSON word means that `orjson` parsed the whole text. The one exception is the header-only Seamless-mixed classification, which is why a `MIXED_*` word answers `None` for `mixed`.
  - An untested kind is a claim too. `UTF8_UNTESTED` says that the whole buffer decodes as UTF-8. `JSON_UNTESTED` says that the whole buffer parses as JSON (`orjson`). A producer that has not checked the whole buffer must write `UNTESTED`.
- **What a wrong word costs.** The database checks that a word is well-formed, not that it is true (*Storage and tightening*). A word that falsely proves a reading makes a reinterpretation succeed, and the empty-path Expression records that success. The failure then surfaces later, when the checksum is read. This is the same trust that the database already gets for Expression and transformation results.

The positive property is monotone under tightening. A tighter word implies the stored one, so it never withdraws a proof. A conversion that the engine's dry run (`conversion_needs_buffer`) settled without a buffer therefore stays settled when it runs.

## The word

A HashType is a 13-bit integer (`pack`/`unpack`; `HashType.word`). `HashType` is a frozen dataclass with these fields:

| Bits | Field | Values |
|---|---|---|
| 0–3 | `Kind` | `RAW_BYTES`=0, `NUMPY`=1, `MIXED_OBJECT`=2, `MIXED_ARRAY`=3, `RAW_TEXT`=4, `JSON_OBJECT`=5, `JSON_ARRAY`=6, `JSON_STRING`=7, `JSON_NUMBER`=8, `UNTESTED`=9, `UTF8_UNTESTED`=10, `JSON_UNTESTED`=11, `JSON_NULL`=12 |
| 4–5 | `Length` | `SHORT` (<64 bytes), `EQ64` (=64), `MEDIUM` (65–1000), `LONG` (>1000) |
| 6–7 | `DType` | `NA`, `NUMERIC` (NumPy kinds `biufc`), `NONNUMERIC`, `STRUCTURED` (has fields) |
| 8–9 | `Rank` | `SCALAR`, `D1`, `D2`, `D3PLUS` |
| 10–12 | `Flag` | `NUMERIC_SCALAR`=1, `NUMPY_BYTES`=2, `SEMANTIC`=4 (reserved) |

**Well-formedness** (`is_valid_word`). A valid word is an `int` in `[0, 2**13)` that satisfies:

- `DType != NA` if and only if `Kind == NUMPY`. `Rank != SCALAR` only for `NUMPY`.
- `NUMPY_BYTES` only with `NUMPY` + `NONNUMERIC` + `SCALAR` (a 0-d dtype-`S` array).
- `JSON_NUMBER` requires `NUMERIC_SCALAR`. `NUMERIC_SCALAR` is allowed only on `JSON_NUMBER` or `JSON_STRING`.
- The `SEMANTIC` bit is reserved; a word with it set is invalid.

`is_valid_word` returns `False`, and never raises, for anything else, including non-integers. Well-formedness is enforced by local `set_hash_type`, by the remote client and by the database (*Storage and tightening*).

**`unpack` does not validate.** `unpack(word)` raises for a non-integer and for an integer outside `[0, 2**13)`; the exception classes are **unspecified** (today `TypeError` and `ValueError` respectively). What `unpack` does with an in-range word that is not well-formed is also **unspecified**: today it decodes most such words without complaint. A caller holding an untrusted word checks it with `is_valid_word` first.

**Derived properties:**

| Property | True for |
|---|---|
| `is_utf8` | `RAW_TEXT`, the JSON kinds, `UTF8_UNTESTED`, `JSON_UNTESTED` |
| `is_json` | the JSON kinds, `JSON_UNTESTED` |
| `is_untested` | `UNTESTED`, `UTF8_UNTESTED`, `JSON_UNTESTED` |
| `is_numpy` | `NUMPY` |
| `is_mixed` | `MIXED_OBJECT`, `MIXED_ARRAY` |

`mic` is the most-informative celltype: `RAW_BYTES`/`UNTESTED` → `bytes`; `RAW_TEXT`/`UTF8_UNTESTED` → `text`; `NUMPY` → `binary`; `MIXED_*` → `mixed`; `JSON_OBJECT`/`JSON_ARRAY`/`JSON_NULL`/`JSON_UNTESTED` → `plain`; `JSON_STRING` → `str`; `JSON_NUMBER` → `float`.

**The untested kinds** are placeholders that record less knowledge. `from_buffer`, the only producer, never emits them; they arrive only through `set_hash_type` or from the database, and every rule on this page supports them. Whoever writes one owes the claim that it makes about the whole buffer (*The positive property*).

## Producer: `from_buffer`

`HashType.from_buffer(buffer)` classifies by the **bytes only**:

1. Starts with `b"\x93NUMPY"`: `NUMPY`. The whole file is loaded with `np.load(allow_pickle=False)` to read `DType`, `Rank` and `NUMPY_BYTES`. If `np.load` refuses it, the result is `RAW_BYTES`.
2. Starts with `b"\x94SEAMLESS-MIXED"`: `MIXED_OBJECT` or `MIXED_ARRAY`, from the root type in the form header. **Only the header is read**, not the payload. A header that cannot be read, or whose root type is neither object nor array, gives `RAW_BYTES`.
3. Not UTF-8: `RAW_BYTES`.
4. Otherwise the whole text is parsed with `orjson.loads`:
   - object → `JSON_OBJECT`; array → `JSON_ARRAY`;
   - string → `JSON_STRING`, plus `NUMERIC_SCALAR` if it parses as a finite float;
   - number → `JSON_NUMBER` + `NUMERIC_SCALAR`;
   - `true`/`false` → `JSON_STRING` with no flags (see *Current limitations*);
   - `null` → `JSON_NULL` with no flags, including non-canonical whitespace spellings;
   - not JSON → `RAW_TEXT`.

`Length` is always the byte-length bucket.

A magic prefix alone therefore never makes `from_buffer` raise. Every buffer gets a word, and so a checksum.

**When it runs.** A HashType is computed and registered (`register_hash_type_for_buffer` → `set_hash_type`) whenever:

- a checksum is calculated from a buffer (`Buffer.get_checksum`, `cached_calculate_checksum[_sync]`);
- a `Buffer` is constructed with an explicit `checksum=`;
- `ensure_hash_type[_async]` is given a buffer for an unclassified checksum;
- an Expression evaluation produces a result buffer, locally or remotely. Remotely, the worker that holds the buffer classifies it.

Registering a HashType is neither *recording* a result checksum nor *publishing* a buffer. It is metadata about a checksum, and it travels through the database (`contracts/expressions.md`, *Evaluating, recording identity and publishing are three different things*).

## Storage and tightening

- **Local**: a process-wide dict `checksum → word` (`get_hash_type_cache()`), guarded by an `RLock`. A word is never evicted; it can only be tightened.
- **Remote**: the seamless-database table `hash_type`. A `GET` of type `hash_type` returns the word, or `null` for an unknown checksum. A `PUT` of type `hash_type` validates the word with seamless-core's `is_valid_word` (the database imports seamless-core).
- **Tightening only.** Local `set_hash_type` and the database (`HashType.create`, inside an `IMMEDIATE` transaction) apply the same rule, `_hash_type_implies(tighter, looser)`:
  - `Length` must be equal.
  - A looser `UNTESTED` is implied by any word, `UTF8_UNTESTED` by any `is_utf8` word, and `JSON_UNTESTED` by any `is_json` word.
  - A concrete word is implied only by an identical word.

| Incoming vs stored | Outcome |
|---|---|
| equal, or looser (implied by stored) | ignored; the stored word is kept; a local write queues no upload |
| tighter (implies stored) | replaces the stored word |
| contradictory | logged as an error; local `set_hash_type` raises `ValueError`; the database answers 409, which the remote client (`database_client.set_hash_type`) raises as `ValueError` |

- **Invalid words.** Local `set_hash_type` raises `ValueError` for a word that is not well-formed. The database refuses a malformed `hash_type` `PUT` (missing `value`, a non-integer, or a word that is not well-formed) and stores nothing. How it refuses is **unspecified**: today the handler raises `DatabaseError("Malformed PUT hash_type request")`, which the server answers as HTTP 400 with the body `ERROR: Malformed PUT hash_type request`.
- **Upload.** A local change is queued on the buffer writer (`buffer_writer.register_hash_type`, deduplicated per `(checksum, word)`) and sent with `database_remote.set_hash_type` when `seamless_remote` is importable. A word loaded from the database (`get_hash_type_remote`) enters the local cache without being uploaded again.

## Lookup

| Function | Order |
|---|---|
| `get_hash_type(cs)` | local cache only |
| `await get_hash_type_remote(cs)` | local cache → database |
| `ensure_hash_type(cs, buffer=None)` (sync) | local cache → if `buffer` is supplied, classify and register it and queue its upload; otherwise, **if no event loop is running**, query the database (via `asyncio.run`). **Inside a running event loop with no buffer, it returns `None` after the local cache.** |
| `await ensure_hash_type_async(cs, buffer=None)` | local cache → database → classify `buffer` if given |

## Queries

### The domain of every query

Every query below takes its celltypes from **the 13, and only the 13**. A name outside them, whether one of the four structural names or an unknown name, is a **caller error and raises `ValueError`**. It is never answered `False`, `None` or the empty set, because none of those classifies anything: the question was not HashType's to ask (`contracts/deep-celltypes.md`, *Where deep validation happens*).

| Query | Domain | Outside it |
|---|---|---|
| `deserializable_as(celltype, *, checksum)` | `celltype` ∈ the 13 | `ValueError` |
| `capabilities(source_celltype)` | `source_celltype` ∈ the 13 | `ValueError` |
| `has_numeric_items` / `has_string_items` | as `capabilities` | `ValueError` |
| `conversion_feasible(hash_type, source, target, *, checksum)` | `source` **and** `target` ∈ the 13 | `ValueError` |

**Inside the domain, an empty answer is a real answer.** `capabilities` returns the empty set for `int`, `float`, `bool` and `checksum` because those admit no path step at all; that is a classification, not a shrug. Likewise a `False` and a `True` from `deserializable_as` are both proofs, and `None` means "unknown".

**Why raise rather than widen.** Teaching the queries the four structural names would make HashType the owner of their feasibility. The legal deep set is *smaller* than "anything goes", so a widened `deserializable_as` would have to carry the whole deep table, and its `False` answers would be structural refusals dressed up as classification. Raising keeps one rule per layer, and keeps the false-negative property a property of the 13.

Where the four structural names are decided instead:

- **Deep celltypes.** Deep feasibility never depends on the data behind the checksum, so it is structural and settled at Expression construction: a pathless deep Expression by the conversion engine's deep table, a pathed one by the deep path table, both defined in `contracts/deep-celltypes.md` (`contracts/expressions.md`, *When an Expression is vetted, and by what*).
- **`module`.** None of the deep rules apply to it, and it is not in the conversion rule table either. Its conversion legality is not defined on this page.

### `deserializable_as(celltype, *, checksum) -> True | False | None`

`checksum` is a required keyword, because the null and boolean answers depend on the exact checksum. Omitting it raises `TypeError` at the call site.

Every `False` below disproves the reading and every `True` proves it (*The false-negative property*, *The positive property*). A reading that the word cannot settle is `None`.

Evaluated in order:

1. `checksum` is either null checksum: `True`. A null checksum deserializes as every one of the 13 celltypes: it reads as `b""` for `bytes` and as `None` for the others (`contracts/celltypes-and-conversion.md`, *Canonical null*). **This is deserializability, not convertibility.** It does not make a conversion legal: a null checksum on a forbidden pair is still refused by `conversion_feasible` (below).
2. `bytes`: `True`.
3. `bool`: `True` only if `checksum` is one of the four canonical boolean checksums; otherwise `False`.
4. Untested kinds:

   | Celltype | Result |
   |---|---|
   | `text` | `True` if `is_utf8`, else `None` |
   | `yaml`, `python`, `ipython` | `None` (syntax is never proved) |
   | `plain`, `mixed` | `True` if `is_json`, else `None` |
   | `str` | `True` for a boolean checksum, else `None` |
   | `int`, `float` | `False` if `LONG`, else `None` |
   | `binary` | `None` for `UNTESTED`, else `False` |
   | `checksum` | `None` if `EQ64`, else `False` |

5. Concrete kinds:

   | Celltype | Result |
   |---|---|
   | `text` | `is_utf8` |
   | `yaml`, `python`, `ipython` | `False` if not `is_utf8`; otherwise `None` (the syntax is the parser's to check) |
   | `plain` | `is_json` |
   | `str` | `True` for `JSON_NUMBER`, `JSON_STRING`, or a boolean checksum; otherwise `False`. The two virtual null checksums were already answered `True` in step 1; other `JSON_NULL` checksums are refused. |
   | `int`, `float` | `False` if `LONG`; otherwise whether `NUMERIC_SCALAR` is set |
   | `binary` | kind `NUMPY` |
   | `mixed` | `False` for `RAW_BYTES`/`RAW_TEXT`; `None` for `MIXED_OBJECT`/`MIXED_ARRAY`, whose payload the producer never read; otherwise `True` |
   | `checksum` | `None` if the kind is `RAW_TEXT` or `JSON_NUMBER` (an all-digit digest is a JSON number) and the length is `EQ64`, because hex validity is the parser's to check; otherwise `False` |

### `capabilities(source_celltype) -> set`

Records which path steps the **root** structure admits: `"SEQ"` (a positional item or a slice) and `"MAP"` (a string key).

| Source celltype | Capabilities |
|---|---|
| `bytes`, `text`, `str`, `python`, `ipython`, `yaml` | `{"SEQ"}` |
| `binary` | `"SEQ"` if `Rank != SCALAR`; `"MAP"` if `STRUCTURED` |
| `plain` | `JSON_OBJECT` → `{"MAP"}`; `JSON_ARRAY`/`JSON_STRING` → `{"SEQ"}`; otherwise empty |
| `mixed` | `NUMPY` follows the `binary` row; `JSON_OBJECT`/`MIXED_OBJECT` → `{"MAP"}`; `JSON_ARRAY`/`MIXED_ARRAY`/`JSON_STRING` → `{"SEQ"}`; otherwise empty |
| `int`, `float`, `bool`, `checksum` | empty: **no path step is ever admitted** over a scalar or a reference |

A deep path (exactly one string-item step below a deep parent) is a structural rule settled at construction (`contracts/deep-celltypes.md`, *Paths*), so `capabilities` never admits or refuses it. A deep index is an ordinary `JSON_OBJECT` buffer; queried under celltype `plain` or `mixed`, it classifies as a map like any other JSON object.

`has_numeric_items` and `has_string_items` return `True`/`False`/`None` hints about the item type, over the same domain.

**Path validation** (`_validate_path_capability`) applies `capabilities` step by step:

- An untested word is not checked at all.
- Each step must find the capability it needs (`"MAP"` for a string item, `"SEQ"` otherwise) in the current capabilities, or the path is refused with `HashTypeValidationError`.
- A slice keeps the current capabilities for the next step.
- After an item step, the root word no longer types the value, so checking stops, with two exceptions where it still does:
  - under `bytes`, an item is an integer, so any further step is refused;
  - under `binary`, **and under `mixed` over a word of kind `NUMPY`**, a `NUMERIC` array with rank below `D3PLUS` admits as many integer item steps as its rank. Each integer item step lowers the rank by one; at rank `SCALAR` no further step is admitted.

### `conversion_feasible(hash_type, source, target, *, checksum) -> True | False | None`

The checksum-level conversion query, asked before any conversion work. A pair of the 13 is **forbidden** if it is in `conversion_forbidden`: exactly the 16 pairs `python/ipython ↔ yaml`, `python/ipython → int/float/bool` and `int/float/bool → python/ipython` (`contracts/celltypes-and-conversion.md`, *Rule table*). No equivalence or chain resolves to a forbidden pair, so every other pair of distinct celltypes is **legal**.

Rules, in order:

1. `source == target`: `True`.
2. **A forbidden pair: `False`, for every checksum, including a null checksum.** The null checksum short-circuits only on a **legal** pair; an illegal conversion stays illegal for null (ruling, `contract-clarity-rulings.md`). The ruling covers forbidden ordinary pairs such as `python → int` as well as illegal deep pairs.
3. A null checksum on a legal pair: `True`.
4. `deserializable_as(source, checksum=checksum)` is `False`: `False`.
5. `target == "checksum"`: `True`.
6. The pair is mapped once through `conversion_equivalent`, and then evaluated by category:
   - `conversion_chain`: evaluate the first step. `False` disproves the chain. If the first step preserves the checksum (`conversion_trivial` or `conversion_reinterpret`), evaluate the second step on the same word; its `False` also disproves the chain. If the second step always succeeds on valid input (`conversion_trivial` or `conversion_reformat`), return the first step's answer. Otherwise return `None`. In particular, never predict through a first step that creates a new buffer.
   - `conversion_trivial` or `conversion_reformat`: `True`.
   - `conversion_reinterpret`: `deserializable_as(target, checksum=checksum)`.
   - `conversion_possible`: an untested word gives `None`. For a concrete word:
     - `int`/`float` target:
       - a NumPy word, whatever the source celltype: non-scalar → `False`; `NUMERIC` → `True`; otherwise `None`;
       - `JSON_OBJECT`, `JSON_ARRAY`, `MIXED_OBJECT`, `MIXED_ARRAY` → `False`;
       - `JSON_NUMBER`, or `NUMERIC_SCALAR` set → `True`;
       - an unflagged `JSON_STRING` → `None`, because JSON booleans can convert to numbers;
       - `JSON_NULL` → `False`, because `int(None)` and `float(None)` fail;
       - `LONG` does not decide this category; the length limit belongs to the deserialization and reinterpretation checks.
     - `mixed→str`: `False` for `JSON_OBJECT`/`JSON_ARRAY`, otherwise `True`.
     - everything else, including `bool` targets: `None`.
   - `conversion_values`: an untested word gives `None` (the `checksum` target was settled in rule 5). For a concrete word:
     - `checksum→X`: `None`;
     - `plain→binary`: `False` for `JSON_OBJECT`;
     - `binary→plain`: `True` for `NUMERIC`/`STRUCTURED`;
     - everything else: `None`.

**Only a `False` from this query is acted on.** Its `True` means "not disproved", and nothing more:

- for a trivial or reformat pair, the answer is given without proving that the source is valid (rule 4 refuses only a *disproved* source);
- in the possible and value categories, the conversion's outcome depends on the value, which the word does not see.

For a reinterpretation the answer *is* `deserializable_as(target)`, which is a proof. Even so, the engine asks `deserializable_as` directly (*The positive property*).

## Where HashType is consulted

- **Reference parser** (`_parse_buffer`): after virtual values, `validate_deserializable_as(checksum, celltype, buffer=buffer)` runs before any parsing.
- **Conversion engine** (`seamless.checksum.convert`): before a source buffer is fetched, it looks up the word (`validate_deserializable_as` without a buffer), and a `False` refuses the conversion. For a reinterpretation, and for the keep branch of `bytes→mixed`, a `True` from `deserializable_as(target)` settles the conversion without fetching (*The positive property*; `contracts/celltypes-and-conversion.md`, *Principle*). The dry run `conversion_needs_buffer` sees the same word, so it answers `False` there.
- **Expression validation** (`validate_expression[_async]`), before evaluation:
  - If either celltype is one of the four structural names, HashType is not asked anything: the checksum is only classified (`ensure_hash_type[_async]`), and the structural half of vetting, which ran at construction, stands. An unknown celltype name raises `ValueError`.
  - Otherwise, it checks the source celltype (`validate_deserializable_as`), then path capability, then `conversion_feasible` for an empty path only.

  Before an empty-path Expression decides whether its conversion needs the input buffer, evaluation loads the input's word with `ensure_hash_type_async`. A word that is known only to the database therefore counts too, and the synchronous dry run then finds it in the local cache (*Current limitations*, first item).

  This is the **evaluation-time** half of Expression vetting; the structural half runs at construction and never consults HashType (`contracts/expressions.md`, *When an Expression is vetted, and by what*). The order is **project, then convert** read at the checksum level (`contracts/expressions.md`, *Application order: project, then convert*): capability is asked of the **input** celltype, because the path walks the input's structure, and `conversion_feasible` is asked only where there is no path. No query on this page classifies "the value a path would select": that is data behind the checksum, and HashType never looks there.
- **Retrieval validation** of a declared checksum and celltype (`validate_deserializable_as`) in `seamless.cell_class`, `seamless_transformer` (`pin_class`, `pretransformation`, `transformation_class`), `seamless_dask` and `seamless_workflow.context`.

## Errors

| Situation | Raised |
|---|---|
| A celltype outside the 13 passed to a query | `ValueError` |
| `deserializable_as` called without `checksum=` | `TypeError` |
| A validation entry point finds a HashType `False` | `HashTypeValidationError` (a `ValueError` subclass) |
| Local `set_hash_type` with a malformed word, or a word that contradicts the stored one | `ValueError` |
| Remote `set_hash_type` contradicting the database (HTTP 409) | `ValueError` |
| `unpack` of a non-integer or out-of-range word | raises; class unspecified (*The word*) |
| Malformed `hash_type` `PUT` at the database | refused, nothing stored; form unspecified (*Storage and tightening*) |

**Across process boundaries**, `HashTypeValidationError` travels in the error envelope (`seamless.error_envelope`) with kind **`"hash_type_validation"`**, and `decode_error` turns that kind back into an instance of `HashTypeValidationError`. The kind string and the fact that the decoded error is a `HashTypeValidationError` are contract. The decoded error's exact class (as opposed to any subclass) and its message text are **unspecified**; today it is exactly `HashTypeValidationError`, carrying the original `str(exc)`.

## Current limitations

These are contract. They are conservative (a `None` or an over-permissive answer): never false rejections, and never false proofs.

- **No remote lookup from synchronous validation inside a running event loop.** With no buffer supplied, `ensure_hash_type` skips the database and returns `None` for a checksum missing from the local cache (*Lookup*). Async `parse_buffer` calls the synchronous `_parse_buffer`, but it passes the buffer, so parse-time validation classifies it locally without a database request. Use `ensure_hash_type_async` when remote-only metadata is needed before a buffer is available.
- **JSON `true`/`false` are classified `JSON_STRING`.** For `plain` and `mixed`, path validation can therefore still admit positional access to a boolean; parsing and evaluation decide whether that access is valid. The word does not prove an actual JSON string, and `conversion_possible` answers `None` for an unflagged `JSON_STRING` with an `int`/`float` target because booleans convert there. But every `JSON_STRING` proves a `str` reading: strings and booleans both pass. `JSON_NULL` has no sequence capability. A non-canonical spelling of null (`b" null \n"`, `b"null\n\n"`) receives `JSON_NULL`; its `str` reading is disproved, while the two virtual null checksums still read as `None` without a buffer. With a cached concrete word, `plain→str` over either kind is settled without fetching the buffer.
- **A Seamless-mixed word proves nothing about a `mixed` reading.** The producer reads only the form header, so `deserializable_as("mixed")` answers `None` for `MIXED_OBJECT`/`MIXED_ARRAY`. As a result, `bytes→mixed` over a Seamless-mixed buffer always fetches and parses it (`contracts/celltypes-and-conversion.md`, *Reformat rules*).

## Non-goals

- **The four structural names.** HashType classifies buffers. A deep buffer is an ordinary `plain` buffer, so a deep index *does* get a `JSON_OBJECT` word like any other. What HashType does not do is know the names `deepcell`, `deepfolder`, `folder` and `module`: every query raises for them (*The domain of every query*). `contracts/deep-celltypes.md` owns deep feasibility and decides it structurally, before any query on this page is reached.
- **Value-level syntax and hex validation.** HashType classifies buffer bytes without parsing them for the requested celltype. It does not check `python`/`ipython`/`yaml` syntax, or whether `checksum` text is valid hexadecimal. Those checks belong to the parser and the conversion engine. Wherever a reading turns on them, `deserializable_as` answers `None`, never `True` (*The positive property*).
