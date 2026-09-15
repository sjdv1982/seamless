# Celltype rename: decisions from the test review

**Status.** Decisions from the 2026-09-14 review of the tests Codex wrote for the
celltype-rename and Pin plan ([plan](../seamless-workflow/validation/celltype-rename/plan.md)),
made after Phases 0–8 were committed. Final commits: seamless-core `639dcc4`,
seamless-workflow `055adec`, seamless-transformer `5406f68`, seamless `c84ce320`.
All code references are to those commits. Where this document and the plan disagree,
this document wins. None of it is implemented yet, except §1–§7.

Labels:

- **Decided**: agreed in the review.
- **Recommended**: proposed in the review and not contested, but not explicitly
  confirmed. Confirm before implementing.
- **Open**: still needs a decision.
- **Not yet discussed**: a review finding that hasn't been discussed.

**Order.** The document is ordered for implementation, in four parts. Each part states
what it depends on. Each section carries its own tests and the documents it changes,
so that a step lands complete.

Contents:

- **Part I. Baseline tests**
  1. [Tests of the committed contract](#1-tests-of-the-committed-contract)
- **Part II. Serialization semantics**
  2. [Printing the null checksum](#2-printing-the-null-checksum)
  3. [HashType, `parse_buffer` and conversions](#3-hashtype-parse_buffer-and-conversions)
  4. [Celltype `checksum`: serialization](#4-celltype-checksum-serialization)
  5. [Expression errors and materialization](#5-expression-errors-and-materialization)
- **Part III. Simple workflow API changes**
  6. [`.set()` takes values only](#6-set-takes-values-only)
  7. [Celltype `checksum`: value-form writes](#7-celltype-checksum-value-form-writes)
- **Part IV. Workflow and serialization together**
  8. [Standalone Cell reads](#8-standalone-cell-reads)
  9. [Mounts and null](#9-mounts-and-null)
- **Part V. Evaluation location**
  10. [Expressions are evaluated where the data is](#10-expressions-are-evaluated-where-the-data-is)

---

## Part I. Baseline tests

These tests cover the contract committed in Phases 0–8, as amended by §3.3 (nested
celltypes keep the checksum), which is implemented. The later parts don't change this
contract. Fixing the tests first gives the later parts a safety net. Depends on §3.3.

### 1. Tests of the committed contract

**Decided, implemented** (2026-09-15). Two more findings belong with later sections: a
bare Checksum passed at call time (§7), and a mount on a cell that is still being
computed (§9).

**Baseline repairs.** At the final commits plus §3.3, the baseline was red:

- `test_pin_celltype_changes.py` (16 of 40 cases) and `test_celltype_changes.py` (4 of
  20) expected a new checksum for int → float and str → int. Both now carry an explicit
  `keeps_checksum` column. A literal written after a retype is serialized as the new
  celltype, so it doesn't keep the source's checksum; the uncommitted §3.3 update of
  `test_celltype_changes.py` had missed that.
- `celltype_probes.py` failed on the same int → float case.
- seamless-dask `test_pin_conversion.py` expected int 42's checksum for an int pin fed
  by a str Transformation. It now expects the str's checksum, as the uncommitted §3.3
  update of the transformer's `test_pin_conversion.py` does.

**Still failing, not yet discussed:** workflow
`correctness/test_correctness_compiled.py::test_original_compiled_alias_exposes_bound_pins`.
This is a code gap, not a stale test:

- A compiled transformation records every pin as `mixed`, whatever its celltype
  ([pretransformation.py:457](../seamless-transformer/seamless_transformer/pretransformation.py#L457)).
  The transformation namespace parses a pin with the celltype that is recorded.
- An `int` pin fed by the str `'2'` now keeps the str's checksum (§3.3). So the C
  function receives the string `"2"` and raises `TypeError: an integer is required`,
  in both the reactive and the snapshot run. Before §3.3, the conversion rewrote the
  bytes to `2`.
- Recording the pin's celltype, as the Python path does, would change the checksum of
  every compiled transformation that has a non-`mixed` pin.

**Also failing at the committed heads**, outside this section (checked against clean
worktrees of seamless-core `3701453` and seamless-transformer `5406f68`):

- transformer
  `test_expression_inputs.py::test_transformation_consumes_expression_result`: the
  Expression's input buffer, `{"value": 41}`, raises `CacheMissError`. The test helper
  `_checksum` returns only the checksum and doesn't hold the buffer. Whether holding
  it is enough wasn't established.
- transformer `test_fingertip.py` (3 tests): the launcher can't reach the hashserver it
  starts (`rhl-verify-port failed: Connection refused`), which looks environmental.

In the shared working tree, uncommitted §2 changes (seamless-core, seamless-transformer,
seamless-dask, seamless-remote) made 11 more transformer test files fail during this
check. They pass at the committed heads.
- `test_pin_handles.py::test_declared_checksum_roundtrip_preserves_pin_input_type`
  declared a checksum without holding its buffer, and raised `CacheMissError`. It now
  holds the buffer.

**Tests that asserted nothing, or too little**

- The assertion-free `test_pin_probe.py` and `test_pin_probe2.py` are deleted, and so
  is `celltype_probes.py`, which ran in no suite. Their unported scenarios became
  assertions:
  - which checksum enters the transformation: the identity assertion below;
  - a standalone retype followed by `tf()`: transformer `test_retype_converts_at_call`;
  - text → int and int → str: new rows of the pin retype matrix (now 56 cases);
  - standalone and bound retypes agree, and so do typed source constructions: workflow
    `test_standalone_and_bound_retype_agree` and `test_typed_source_constructions_agree`;
  - an Expression over a typed Expression takes both celltypes from it: core
    `test_typed_expression_input_supplies_both_types`.

  The declared-checksum probe duplicated
  `test_declared_checksum_recipe_survives_binding_and_graph`.
- The pin retype matrix asserts the transformation's pin entry,
  `[celltype, None, pin.checksum]`, and that the reactive run's identity in the runtime
  graph equals the snapshot's transformation checksum.
- A transformer's `block_reason` is its list of culprit pins; the kind of block is on
  its result. A failed pin conversion and a rejected required null both assert
  `ctx.tf.block_reason == ['value']` and `ctx.tf.result.block_reason == 'blocked-by-error'`.
- `test_retype_converts_at_call`: a stored int pin retyped to str keeps its checksum
  through `tf()` and returns `'42'`. An unconvertible retype gives the pin a
  `HashTypeValidationError`; `construct()` returns `None`, and `run()` raises
  `TransformationError` naming the dependency.
- `test_expression_type_defaults_are_symmetric` restores the Expression half of the
  removed test. The Cell half stays replaced by `test_unwired_cell_has_no_input_type`.
- The actual `RETIRED_NAMES` are tested, matching the full message
  `'<name>' has been retired; use <replacement> instead`: get, set and delete on
  standalone and bound Cells and projections, get and set on a bound Pin, and get on an
  Expression.

**Missing tests, now present.** The behaviour already matched the contract.

1. `ctx.tf.pins.value = v` detaches a connected pin (`test_writes_check_or_detach`,
   form `pins`); a standalone `tf.pins.value = v` replaces a source.
2. Buffer writes deposit the buffer, for Cells and Pins in both modes, each against an
   undeposited control buffer that raises `CacheMissError`. An invalid buffer raises
   `HashTypeValidationError`, through `.buffer =` and `set_buffer`.
3. `test_source_and_checksum_of_connected_cells`: an upstream that is unwired
   (`blocked-by-unwired`) or failed (`blocked-by-error`); a failed own conversion, with
   its downstream `blocked-by-error`; int → float reporting the source's checksum.
4. `test_connected_none_result_drops_optional_pin`.
5. `ctx["a"] = None` stores null.
6. `test_value_assignment_keeps_celltype_and_validates`,
   `test_builder_assignment_replaces_cell_config` and
   `test_new_cell_from_transformer_copies_result_celltype_once`.
7. seamless-database `test_expression_records_differing_only_in_celltypes_coexist`.
8. `test_celltype_changes.py` asserts the downstream cell's checksum.
9. Deleting a bound pin drops it from `celltypes` and `optional_pins`.

Dropped as not worth testing: setting an invalid `pin.celltype`, and accepting a
matching explicit `input_celltype=`.

**Not yet discussed** (found while implementing):

- Setting or deleting any non-field attribute of an `Expression`, retired names
  included, raises `TypeError: super(type, obj): obj … is not an instance or subtype of
  type (Expression)` instead of `AttributeError`. Setting a field correctly raises
  `FrozenInstanceError`. The likely cause is the `__setattr__` that
  `dataclass(frozen=True, slots=True)` generates: it refers to the class from before
  `slots` recreated it.
- Deleting a retired name on a Pin raises `AttributeError` without the retirement
  message.

**Decided:** an invalid literal (`ctx.a = 'abc'` on an `int` cell) raises a bare
`ValueError` from `int()`, while an invalid buffer raises `HashTypeValidationError`, a
`ValueError` subclass. The two don't need to match. The test asserts `ValueError`.

---

## Part II. Serialization semantics

Substrate work, mostly in seamless-core. It changes how checksums, HashTypes, `checksum`
values and errors are represented, not the workflow API. The parts that cross the
database and the jobserver are in §10. Depends on nothing outside this part.

### 2. Printing the null checksum

**Status: implemented**, including the audit run. New machine formats that carry
checksums, such as §10's result HashTypes in the database and structured jobserver
errors, must use `.hex()`; rerun the audit once they exist.

**Decided:**

- `str(checksum)` prints the canonical null checksum as `NULL` instead of its hex
  digest. This is a display form only.
- `repr()` stays the hex digest, and `Checksum("NULL")` stays invalid. The printed form
  deliberately doesn't round-trip.

**Required changes.** Several places use `str()`, or f-string formatting, of a
Checksum as a machine format. They must switch to `.hex()` before `__str__` changes:

- `is_null` compares `str(checksum)` with the null digest
  ([null.py:11](../seamless-core/seamless/checksum/null.py#L11)), so it would stop
  recognizing null;
- hashserver buffer URLs are built as `"/" + str(checksum)`
  ([buffer_client.py:162](../seamless-remote/seamless_remote/buffer_client.py#L162),
  [:198](../seamless-remote/seamless_remote/buffer_client.py#L198),
  [:216](../seamless-remote/seamless_remote/buffer_client.py#L216));
- execution-record fields
  ([record_assembly.py:311-318](../seamless-transformer/seamless_transformer/record_assembly.py#L311-L318),
  [:1180](../seamless-transformer/seamless_transformer/record_assembly.py#L1180)), and
  compiled-module identifiers
  ([run.py:191-193](../seamless-transformer/seamless_transformer/run.py#L191-L193));
- Dask client keys
  ([client.py:145-244](../seamless-dask/seamless_dask/client.py#L145-L244)), CLI
  result file names
  ([get_results.py:22](../seamless-transformer/seamless_transformer/cmd/get_results.py#L22))
  and the CLI's JSON output
  ([main.py:1213](../seamless-transformer/seamless_transformer/cmd/api/main.py#L1213)).

The first two are affected by null directly. The others normally carry checksums of
transformations, code or environments, but should switch too, so that `str()` is only
ever used for display. The list comes from a pattern search and may be incomplete;
the audit test below finds the rest.

**Tests:**

- `str()` of the null checksum is `NULL`, its `repr()` is the hex digest, and
  `Checksum("NULL")` raises.
- `is_null` recognizes the null checksum, and a null buffer uploads to and downloads
  from the hashserver.
- An audit run: the test suites pass with `Checksum.__str__` patched to return a
  non-hex string for *every* checksum. That catches any remaining use of `str()` as a
  machine format.

**Documents:** seamless-core README: how the null checksum prints.

### 3. HashType, `parse_buffer` and conversions

**Decided: HashType needs work, but its mechanism is adopted.** Type-bits design §5
([type_bits_design.md:316](../seamless-core/type_bits_design.md#L316)) defines
`deserializable_as` as strict: "`parse_buffer` would succeed". What succeeds is
defined by a reference parser (§3.1). §8.4 relies on it: a Cell validates its result
checksum against its celltype, using the result's HashType.

**Status: implemented** (seamless-core `c77d688`, seamless-transformer `773cf1f`): the
reference parser (§3.1), items 1–5 of §3.2 (item 5 for the local cache), the
conversions of §3.3, and the tests and documents of §3.4. Item 7 changes no code here;
its substrate tests pass, and its Cell tests are strict xfails until §8.3/§8.4. Item 6, and the database part of item 5, moved to
§10.6.

#### 3.1 The reference parser — Decided, implemented

*Question*: does "strict" mean "parses", or "parses **and** re-serializes to the same
checksum"? The type-bits §5 table accepts `"42"` as an int and `42` as a str.
Alternative: the canonical reading, leaving coercion to Expression conversions.

*Decision*: "strict" means "parses". Round-trip re-serialization is not assumed. What
parses is defined by a reference parser: `parse_buffer` implements it, and
`deserializable_as` predicts it.

- **null**: the checksums of `null` and `null\n` are `None` for every celltype (`b""`
  for `bytes`). Only `null\n` is the canonical null (`is_null`); `is_null_value`
  recognizes both.
- **bool**: the checksums of `true` and `false`, with or without a trailing newline.
  Any other checksum is rejected.
- **plain**: `orjson`.
- **str**: parsed as `plain`. An object, an array or null is rejected. A string, a
  number or a boolean becomes `str(value)`, so `42` is `"42"` and `true` is `"True"`.
- **int, float**: the buffer is at most 1000 bytes, and the decoded value is numeric:
  a number that isn't a boolean, or a string whose `float()` is finite. A `float` is
  `float(value)`. An `int` is `int(value)`, or else `int(float(value))`; if both fail,
  the error of `int(value)` is raised. So `"42"` is 42, and `4.5` and `"4.5"` are 4.

The null and bool parsers are virtual: they work on the checksum, and never fetch or
parse a buffer ([virtual.py](../seamless-core/seamless/checksum/virtual.py)).
`Checksum.resolve()`, `Checksum.resolution()` and `parse_buffer` consult them first.
The buffers of `null`, `true` and `false`, with and without a newline, are trivial
checksums, so the celltypes that need their content never fetch them remotely.

The numeric check is made on the value, never on a stored HashType flag. So the
outcome doesn't depend on whether a HashType is known.

Because nothing is re-serialized, one value can have several checksums: `42` and
`"42"` are both the int 42. Identity stays with the checksum
([identity-and-caching](docs/agent/contracts/identity-and-caching.md)). Two
transformations that differ only in that pin have different checksums and the same
result. That costs cache reuse, but doesn't break referential transparency. It does
require the reference parser to be a fixed function of the buffer: if what it accepts
changes, for example with an `orjson` upgrade, the classification rules have changed
(§3.2, item 5).

Outcomes, compared with the code before:

| buffer | celltype | before: HashType | before: `parse_buffer` | now |
|---|---|---|---|---|
| `"4.5"` | int | allowed | raises `ValueError` | 4 |
| `4.5` | int | allowed | returns 4 | 4 |
| `12345678901234567890123` | int | allowed | returns 12345678901234567741440 | the same |
| `"42"` (JSON string) | int / float | allowed | 42 / 42.0 | 42 / 42.0 |
| `"nan"`, `"inf"` | int / float | allowed | raises / returns `nan`, `inf` | rejected |
| `1e999`, `NaN` | float | allowed | raises | rejected |
| `NaN` | plain | allowed | raises | rejected |
| `true` | int | rejected | would return 1 | rejected |
| `42` | str | allowed | `"42"` | `"42"` |
| `true` | str | allowed | `"True"` | `"True"` |
| `[1]` | str | rejected | would return `"[1]"` | rejected |
| ` null ` | str | allowed | returns `"None"` | rejected |
| `42` | bool | rejected | would coerce to `True` | rejected |
| 64×`z` | checksum | allowed | raises `TypeError` | unchanged (item 4) |
| invalid Python / YAML | python / yaml | allowed | raises `ValueError` | unchanged (item 3) |

#### 3.2 HashType

**Recommended changes**, in implementation order: align the classifier with the
reference parser (1–4), then the stored word (5), then item 7. Item 6 (result
HashTypes in the database) and the database part of item 5 are in §10.6.

1. **Decided, implemented: HashType classifies JSON with the reference parser.**
   `_json_kind_and_flags` used `json.loads`, which accepts `NaN`, `Infinity` and exact
   big integers. It now uses `orjson`, which rejects `NaN` and `Infinity` and returns
   integers beyond 64 bits as floats. A buffer is JSON exactly when `orjson` accepts
   it: `NaN` is `RAW_TEXT`, and `12345678901234567890123` is a `JSON_NUMBER`. `orjson`
   also rejects numbers beyond the float range, such as `1e999` or a 400-digit integer,
   so every JSON number is finite.
2. **Decided, implemented: no integer bit.** The word decides `int` and `float`:
   `Length` isn't `LONG`, and `NUMERIC_SCALAR` is set. `NUMERIC_SCALAR` now means a
   finite number: a JSON number, or a JSON string whose `float()` is finite, so
   `"nan"`, `"inf"` and `"1e999"` don't get it. With the `int(float(value))` fallback,
   `int` and `float` accept exactly the same checksums.
   - `str` is decided by the word too: `JSON_STRING` or `JSON_NUMBER`. `true` and
     `false` are classified as `JSON_STRING`. A non-canonical null such as ` null `
     has the same word as a string, so HashType allows it as `str` and `parse_buffer`
     rejects it.
   - `bool` and null are decided by the checksum (§3.1). `deserializable_as`
     recognizes both null checksums.
3. **Implemented:** a failed `text_validation_celltype_cache` check (python, ipython,
   yaml) raises `HashTypeValidationError`, exactly like a HashType validation failure.
   These celltypes are outside HashType by design (type-bits §5 †, §13).
4. **Implemented:** `parse_buffer` raises `HashTypeValidationError` for a non-hex
   `checksum` value, instead of `TypeError`.
5. **Decided, implemented for the local cache: a stored HashType can only be tightened.** A word is tighter when it
   implies the stored word. For example, testing may replace `JSON_UNTESTED` with
   `JSON_OBJECT`. A producer may also store an untested level without testing further,
   such as "UTF-8" without testing for JSON.

   The rule applies to local HashType caches and to the database. The database side
   (accepting a tighter word, and uploading a changed local word) is in §10.6.

   This changes the type-bits design. Type-bits §8.1 requires every word to be
   complete, and `RAW_TEXT` asserts a negative: "UTF-8 and *not* JSON" (type-bits §4.1).

   **Decided: the untested levels.** From loosest to tightest:
   - **Nothing tested:** any Kind is possible.
   - **UTF-8:** Kind 4–8 (`RAW_TEXT` or a JSON Kind).
   - **JSON:** Kind 5–8.
   - **Numeric scalar:** tested or not.

   Whether a value can be an `int` or a `float` then follows from `deserializable_as`
   (item 2); `bool` follows from the checksum.

   The Kinds form a tree, and testing moves a word down it:
   - "Nothing tested" narrows to "UTF-8", to `RAW_BYTES`, to `NUMPY` or to a `MIXED_*`
     Kind. The binary Kinds need no intermediate level, because their magic bytes are
     recognized in constant time.
   - "UTF-8" narrows to "JSON" or to `RAW_TEXT`.
   - "JSON" narrows to a concrete JSON Kind.

   **Implemented** (proposed as Recommended; the implementation follows it):
   - **Three new Kind values**, taken from the unused values 9–15. The full enum:

     | value | Kind | meaning | narrows |
     |---|---|---|---|
     | 0 | `RAW_BYTES` | not UTF-8, no magic bytes | `UNTESTED` |
     | 1 | `NUMPY` | `.npy` magic bytes | `UNTESTED` |
     | 2 | `MIXED_OBJECT` | mixed magic bytes, dict root | `UNTESTED` |
     | 3 | `MIXED_ARRAY` | mixed magic bytes, list root | `UNTESTED` |
     | 4 | `RAW_TEXT` | UTF-8, not JSON | `UTF8_UNTESTED` |
     | 5 | `JSON_OBJECT` | JSON object | `JSON_UNTESTED` |
     | 6 | `JSON_ARRAY` | JSON array | `JSON_UNTESTED` |
     | 7 | `JSON_STRING` | JSON string | `JSON_UNTESTED` |
     | 8 | `JSON_NUMBER` | JSON number | `JSON_UNTESTED` |
     | 9 | `UNTESTED` (new) | nothing tested: any of 0–8 | — |
     | 10 | `UTF8_UNTESTED` (new) | UTF-8, JSON not tested: one of 4–8 | `UNTESTED` |
     | 11 | `JSON_UNTESTED` (new) | JSON, which JSON type not tested: one of 5–8 | `UTF8_UNTESTED` |

     - `Length` is always known.
     - For the new Kinds, `DType` is `NA`, `Rank` is `SCALAR`, and every flag is 0.
     - Their most-informative celltypes (type-bits §8.2) are `bytes`, `text` and
       `plain`.
     - `is_utf8` and `is_json` can no longer be `≥` thresholds (type-bits §4.1). They
       become set membership, because renumbering the existing Kinds would change every
       stored word.
   - **"Numeric scalar tested" needs no bit.** Confirming a concrete JSON Kind requires
     its value, and the `float(value)` probe then costs nothing (type-bits §8.2). So
     `NUMERIC_SCALAR` is always tested for a concrete JSON Kind, and untested (stored
     as 0) at the three new levels. A disagreement about `NUMERIC_SCALAR` is a
     conflict (below).
   - **`deserializable_as` gets three outcomes.** It rejects only when a negative is
     proven. An untested level never causes a rejection; `parse_buffer` decides at
     materialization. `conversion_feasible` already works this way. For the new Kinds
     ("?" means untested, so no rejection):

     | celltype | `UNTESTED` | `UTF8_UNTESTED` | `JSON_UNTESTED` |
     |---|---|---|---|
     | `bytes` | yes | yes | yes |
     | `text` | ? | yes | yes |
     | `python`, `ipython`, `yaml` | ? | yes (validity checked at parse, as today) | yes (same) |
     | `plain`, `mixed` | ? | ? | yes |
     | `str` | ? | ? | ? |
     | `int`, `float` | ? (no if `Length` is `LONG`) | ? (no if `LONG`) | ? (no if `LONG`) |
     | `binary` | ? | no | no |
     | `checksum` | ? (no unless `Length` is `EQ64`) | ? (no unless `EQ64`) | ? (no unless `EQ64`) ¹ |

     ¹ **Decided, implemented** (2026-09-15): a digest of only decimal digits is a
     `JSON_NUMBER`, and a concrete `JSON_NUMBER` with `EQ64` is accepted as
     `checksum`. So `JSON_UNTESTED` with `EQ64` gives "?". It used to give "no".

     - `bool` and null stay decided by the checksum.
     - A path step on these Kinds is never rejected, because their capabilities
       (type-bits §7) are not yet known.
   - **Writes that aren't tighter.**
     - An equal or looser write changes nothing.
     - **Decided** (2026-09-15): a contradictory write is a conflict. It is logged,
       raises `ValueError`, and keeps the stored word. This includes a
       disagreement about `Length` or `NUMERIC_SCALAR`. A HashType is a function of the
       buffer, so correct producers never contradict each other; only a bug or a change
       in the classification rules can.
   - **The local cache.** `set_hash_type` only tightens; it used to overwrite
     unconditionally. Uploading a changed word to the database is in §10.6.

   Consequences:
   - Information only grows. Item 7's "can't be deserialized" marker is never erased,
     so that failure stays visible at retrieval.
   - A wrong stored word can't be repaired by writing a correct one, because that write
     conflicts. So when the classification rules change (item 1, or any change in what
     the reference parser accepts), development databases must clear their `hash_type`
     table, which is a cache. Phase 3 did the same for the `expression` table. Items 1
     and 2 are such a change.
6. **Moved to §10.6:** HashTypes are stored in the database, including those of
   results.
7. **Decided: expression results are never undone.** An expression whose result can't
   be deserialized as its celltype is not invalid: it deterministically returns that
   checksum. The result is stored in the `expression` table as usual. Whether it can
   be deserialized as that celltype is not stored separately: the result's HashType
   (§10.6) proves the failure where it can, and otherwise retrieval re-validates. A Cell built on it stays `failed`, and `clear_exception()`
   produces the same failure again, as it should (§8.4).

   **Tests** (2026-09-15): the substrate part holds; the Cell part waits for §8.3/§8.4.
   Only the text celltypes reach this case. A path over plain or text whose result is
   invalid python or yaml returns a checksum. For the other celltypes, serializing the
   result fails, so no result exists.
   - [test_expression_result_never_undone.py](../seamless-core/tests/test_expression_result_never_undone.py):
     a failed `.run()` keeps the result in the expression cache and fails identically
     when repeated; re-evaluation returns the same checksum, which reads fine as
     `text`. A standalone Cell failing, with `clear_exception()` reproducing it, is a
     strict xfail: the Cell stays `complete` with no exception, and standalone
     `clear_exception()` raises.
   - [test_undeserializable_expression_result.py](../seamless-workflow/tests/test_undeserializable_expression_result.py):
     the bound variant, a strict xfail: the cell ends `blocked` with no exception.

   **Decided** (2026-09-15): HashType doesn't cover deserializability in every case, and
   expression deserializability isn't stored separately in the database. For python,
   ipython and yaml, validity is outside HashType (item 3): the result is `RAW_TEXT`,
   which allows the celltype, and each read re-validates through
   `text_validation_celltype_cache`. These are the only celltypes that reach this case.

#### 3.3 Conversions — Decided, implemented

**Subtypes are subtypes of checksums.** A celltype is a subtype of another when every
checksum it accepts is also accepted by the other. It says nothing about values:
`"42"` is the string `"42"` as `plain` and 42 as `int`. Under the reference parser,
the scalar celltypes nest:

- `bool`, `int` and `float` are subtypes of `str`, which is a subtype of `plain`;
- `int` and `float` accept exactly the same checksums;
- `bool` shares no checksum with `int` or `float`.

**A conversion between nested celltypes keeps the checksum.** The value comes from the
target's parser. In [conversion.py](../seamless-core/seamless/checksum/conversion.py):

- `plain` → `str`/`int`/`float`/`bool` and `str` → `int`/`float`/`bool` are
  `reinterpret`: the checksum is kept if the target's parser accepts it. They used to
  be value conversions (`possible`).
- `int` ↔ `float` and `int`/`float`/`bool` → `str` are `trivial`. They used to be value
  conversions (`reformat`).
- `int`/`float` ↔ `bool` stay value conversions.
- `str` → `mixed` is equivalent to `str` → `plain` (trivial), no longer to `str` →
  `binary`.
- YAML subtyping is out of scope. `plain` → `yaml` stays `trivial`, although PyYAML
  rejects some valid JSON (`[1,\t2]`) and reads `1e3` as a string.

**Expression executes the conversion table.** It used not to: an empty-path conversion
parsed the buffer as the source celltype and serialized the value as the target,
whatever the table said, and the table was only a HashType feasibility gate. Plain
`{"a": 1}` → bytes gave `b"{'a': 1}"`, and text `{"a": 1}` → plain gave a JSON
string. The conversion engine
([convert.py](../seamless-core/seamless/checksum/convert.py)) now follows the table:

- `trivial` keeps the checksum.
- `reinterpret` keeps it once the target's parser accepts it.
- `reformat` follows the rules written in the table:
  - bytes → binary: an `.npy` buffer is kept; other bytes become a dtype-S array.
  - bytes → mixed: a valid mixed buffer (`.npy`, mixed format or JSON) is kept; other
    UTF-8 becomes a str; other bytes become a dtype-S array.
  - binary → bytes: a 0-d dtype-S array becomes its bytes; anything else is kept.
    mixed → bytes does the same for an `.npy` buffer, and keeps anything else.
  - plain → text: a string value becomes that text; anything else is kept.
  - text → plain: text that `orjson` accepts is kept; other text becomes a JSON string.
  - text ↔ str keep the value.
  - yaml → plain runs the YAML parser; ipython → python converts the code.
  - `bool` ↔ `int`/`float` convert the value.
- `equivalent` and `chain` entries are followed hop by hop.
- `possible` and `values` convert the value, as before. `mixed` →
  `str`/`int`/`float`/`bool` stay there. Conversions from and to `checksum` are §4.

Path expressions still work on values.

**The engine works on checksums.** It fetches the input buffer only when a rule needs
its content, or a value that isn't virtual. Trivial conversions, and conversions of a
null or bool checksum, need no buffer, so they are evaluated locally even when the
buffer is elsewhere.

**The "42" case.** `Cell('int', checksum=<checksum of the JSON string "42">)` takes the
identity shortcut and keeps the string's checksum; its value is 42. Converting a `str`
cell holding `"42"` to `int` gives the same checksum.

**This replaces the plan's Phase 5 expectation**
([plan.md:330](../seamless-workflow/validation/celltype-rename/plan.md#L330)) that "an
int pin fed by a str dependency holds int 42's checksum". The pin holds the str's
checksum, and its value is 42.

**BufferInfo is removed.** HashType superseded it, and nothing used it. The database's
legacy BufferInfo endpoint is unaffected.

#### 3.4 Tests and documents — Implemented

**Tests** (all green; seamless-core files run one pytest process each):

- [test_reference_parser.py](../seamless-core/tests/test_reference_parser.py): each
  row of the outcomes table (§3.1), with HashType and `parse_buffer` agreeing; the
  numeric check with and without a known HashType; null and bool values with every
  buffer fetch patched to fail. Items 3 and 4 of §3.2: invalid python and yaml, a
  rejected ipython conversion, and a non-hex `checksum` value all raise
  `HashTypeValidationError`.
- [test_hash_type_tightening.py](../seamless-core/tests/test_hash_type_tightening.py),
  for item 5 of §3.2:
  - the three new Kinds: their values, `is_utf8`/`is_json` membership, their
    most-informative celltypes, and that they are valid only with `DType` `NA`,
    `Rank` `SCALAR` and no flags;
  - the three outcomes of `deserializable_as`, per celltype and untested level, with
    `LONG` rejecting `int`, `float` and `checksum`, and `bool` and null decided by
    the checksum;
  - every Kind tightens from each of its ancestors, and a looser write afterwards
    keeps the tighter word;
  - contradictory writes (`Length`, sibling Kinds, `NUMERIC_SCALAR`, `SEMANTIC`,
    `DType`, `Rank`) are logged, raise, and keep the stored word, in both orders;
  - registering a buffer tightens `JSON_UNTESTED` to `JSON_STRING` with
    `NUMERIC_SCALAR`;
  - a word at an untested level never causes a rejection in synchronous and
    asynchronous validation, path validation or `conversion_feasible`; only a proven
    negative (`binary` on a UTF-8 level, a `LONG` numeric target) rejects.
- [test_conversion_engine.py](../seamless-core/tests/test_conversion_engine.py): one
  case per engine rule, including failures and a forbidden pair; conversions that need
  no buffer are evaluated locally with buffer access patched to fail.
- The witness corpus: the `LONG` JSON-number and numeric-string witnesses are finite
  decimals, because `orjson` rejects a 1001-digit number and `float()` of 1000 digits
  is infinite.
- seamless-workflow `test_celltype_changes.py`: int → float and str → int keep the
  source checksum.
- seamless-transformer `test_pin_conversion.py`: an int pin fed by a str keeps the
  str's checksum, and its value is 42.

Item 7's tests are listed under that item. The database tests are in §10.7.

**Documents, updated:**

- [type_bits_design.md](../seamless-core/type_bits_design.md):
  - §1 and §8.1: completeness gives way to untested levels, and a stored word can
    only be tightened, in the local cache and (pending §10.6) in the database;
  - §2: subtypes of checksums, with `bool`, `int` and `float` below `str`;
  - §4.1: the three new Kind values, and set membership for `is_utf8`/`is_json`;
  - §5: the three outcomes of `deserializable_as`; "strict" as "the reference parser
    accepts it", with no round trip; the JSON rules (`orjson`); the finite
    `NUMERIC_SCALAR`; null and bool by checksum;
  - §6 and §6.1: Expression executes the conversion table; the scalar rows follow
    §3.3, and the untested levels give `?`;
  - §8.2, §8.6, §9–§13: the most-informative celltypes of the new Kinds, what a
    producer may store unconfirmed, the `checksum` screen (`RAW_TEXT` or
    `JSON_NUMBER`), the migration table, the sketch, the invariants and witness
    counts.
- The `.source`/`.checksum` table of the
  [plan](../seamless-workflow/validation/celltype-rename/plan.md#L203) (:203): int →
  float and str → int keep the checksum.

### 4. Celltype `checksum`: serialization

**Status: implemented** (seamless-core `c77d688`, seamless-transformer `773cf1f`),
verified 2026-09-15, with the tests and documents below.

**Decided:** the value of a `checksum` cell is a `Checksum` object (`None` stays
`None`). `.set(Checksum)` on a `checksum` cell stores that checksum as the value; that
part is in §7.

**Code before: the round trip was broken.**

- `Buffer("ab"*32, "checksum")` writes a quoted JSON string
  ([serialize.py:57-58](../seamless-core/seamless/checksum/serialize.py#L57-L58)).
  HashType and `parse_buffer` expect a bare 64-byte digest, so reading the value back
  raises `HashTypeValidationError`.
- `Buffer(Checksum(...), "checksum")` raises `TypeError`
  ([buffer_class.py:28-29](../seamless-core/seamless/buffer_class.py#L28-L29)).
- No test uses this celltype.

**Implemented** (proposed as Recommended):

- Wrap and unwrap during serialization. `serialize` accepts a `Checksum` or a hex
  string and writes the bare digest; `parse_buffer` returns a `Checksum`. Then
  `.value`, `.run()`, `Expression.run()`, `Checksum.resolve("checksum")` and
  transformation pins all agree. Transformation code with a `checksum` pin then
  receives a `Checksum`.
- Wrapping only affects typing: a `checksum` cell doesn't hold the buffer it points
  to. Note that `Checksum == hex_str` is true, but the two hash differently.

**Tests:**

- A `checksum` pin receives a `Checksum`. A function that returns a `Checksum` with
  result celltype `checksum` serializes it to the bare digest.

### 5. Expression errors and materialization

§8.3 makes `CacheMissError(checksum)` a Cell's `.exception`, and §8.4 makes `.run()`
agree with `.value`. Both need these substrate changes first.

**Status: implemented** (2026-09-15).

- A missing buffer in local evaluation raises `CacheMissError(checksum)`, including
  through a conversion: the conversion engine no longer wraps it in
  `SeamlessConversionError`. `"auto"` still reads it as "not local". An invalid path
  still raises `ExpressionEvaluationError`.
- The bound runners (the transformer runner in `reactive.py` and projection jobs in
  `context.py`) record substrate errors with their own class and arguments:
  `CacheMissError`, `ExpressionEvaluationError`, `HashTypeValidationError` and
  `SeamlessConversionError`. Each gets a `failure_id` and loses its traceback, whose
  frames would keep the worker's leases alive. Any other exception is still reduced to
  `WorkflowExecutionError` text (`execution_error` in `errors.py`). A transformation's
  own failure still arrives as text, because `Transformation.exception` is a string
  (§8.3).
- `Expression.run()`, and so `Cell.run()`, looks for a local buffer first, and
  otherwise materializes through `Checksum.resolve()`.

Tests: seamless-core
[test_expression_errors.py](../seamless-core/tests/test_expression_errors.py) (a missing
input buffer for an item, a slice and a conversion; an invalid path; `"auto"`;
`Expression.run()` and `Cell.run()` through a fake hashserver, and `CacheMissError` when
no buffer exists anywhere), and seamless-workflow
[test_execution_error_types.py](../seamless-workflow/tests/test_execution_error_types.py)
(the kept types survive `deepcopy` with their `failure_id`; other errors stay text; a
bound projection over a missing buffer records `CacheMissError`, read from the
Context's facts until §8.3 surfaces it).

**Not yet discussed** (found while implementing):

- **Deadlock.** An `Expression` finalized by garbage collection in the buffer-writer
  thread releases its refholds under the buffer-cache lock
  (`Expression.__del__` → `decref_refholder`). If the main thread holds that lock
  inside `buffer_writer.register`, which imports `seamless_remote.buffer_remote`, while
  the writer thread is importing the same module, the two threads deadlock. It was
  observed in `test_expression_errors.py`, whose failed computes leave Expressions in
  traceback cycles; the test now collects garbage on the main thread. The cause
  predates §5: finalizers take the cache lock on whatever thread runs them.
- **Stale install.** Run from seamless-workflow, `seamless_remote` resolves to an old
  copy in site-packages, without `database_remote.get_expression_result`. Every
  bound projection that asks the database then fails, for example in
  `test_celltype_changes.py`. This is environmental, not a code change.

**Required changes: errors keep their type.**

- A missing buffer in local evaluation raises `ExpressionEvaluationError("… is not
  available locally")` ([expression.py:453](../seamless-core/seamless/checksum/expression.py#L453)),
  the same class as an invalid path. It must raise `CacheMissError`.
- The bound transformer runner reduces errors to `WorkflowExecutionError(str(exc))`
  ([reactive.py:167](../seamless-workflow/seamless_workflow/reactive.py#L167)), which
  loses the exception type.

Errors that cross the jobserver are in §10.5.

**Decided: `Expression.run()`, and so `Cell.run()`, materializes through
`Checksum.resolve()`.** Today it uses the local-only lookup
([expression_class.py:365-371](../seamless-core/seamless/expression_class.py#L365-L371)),
so a result computed on the jobserver fails in `.run()` while `.value` works.

**Tests:**

- `Expression.run()` of a result whose buffer is on the hashserver, but not local,
  resolves through the hashserver. The variant with a result evaluated on the jobserver
  is in §10.7.
- The missing-input-buffer tests of §8 cover the error changes end to end.

---

## Part III. Simple workflow API changes

How value-form writes classify their argument. The authority checks already exist.
§7 depends on §4.

### 6. `.set()` takes values only

**Status: implemented** (seamless-core `c77d688`, seamless-transformer `773cf1f`,
seamless-workflow `69fd2b0`), verified 2026-09-15, including the recommendation, the
four call-site rewrites and the documents below.

**Decided:**

- `.set()` accepts values only. A checksum goes through `.set_checksum()`. A source
  is connected by assignment (bound) or with `Cell(source=...)` (standalone).
- `.set()` on a cell that is wired to a source raises `AuthorityError`, bound or
  standalone. `.set_checksum()` and `.set_buffer()` check authority the same way
  ([plan.md:147](../seamless-workflow/validation/celltype-rename/plan.md#L147)).
- For a projection, "wired" follows
  [followup:277-293](context-internals-followup-design.md#L277-L293).
  `ctx.a.b.c.set(v)` raises if an edge targets `ctx.a` or `ctx.a.b`. An edge at an
  unrelated first-level key doesn't block it.

**Recommended:** passing a Checksum, Cell, Expression, Transformation or Pin to
`.set()` raises `TypeError` that names the right spelling: `.set_checksum()`,
assignment, `Cell(source=...)` or `pin.source`. Celltype `checksum` is the exception (§7).

**Consequences:**

- This retires three things:
  - the `.set(Checksum)` pass-through (seamless-core `a41c3bd`);
  - the bound rule "classify the RHS exactly as root assignment"
    ([followup:320](context-internals-followup-design.md#L320));
  - connecting a projection through `.set()`
    ([followup:265-267](context-internals-followup-design.md#L265-L267)).
    `ctx.a["b"] = ctx.source` stays.
- A standalone Cell can no longer be rewired to a source in place. Only
  `Cell(source=...)` and `with_input()` remain, and both create a new Cell.

**Code before:** a standalone `.set()` stored a Checksum, Expression or Cell as the
input ([cell_class.py:184-185](../seamless-core/seamless/cell_class.py#L184-L185)). A
bound `.set()` classifies its argument the way assignment does
([builder_state.py:169-172](../seamless-workflow/seamless_workflow/builder_state.py#L169-L172)).
The authority checks already exist.

**Tests:**

- `.set()` with a reference raises `TypeError`, for a standalone Cell, a bound Cell, a
  SubCell and a Pin.
- A projection's `.set()` raises under an edge at the root or at its first-level key,
  and succeeds under an edge at an unrelated key.
- Rewrite four call sites:
  - `seamless-core/tests/test_cell_input_ref.py:91`: use `set_checksum`;
  - `seamless-workflow/tests/test_assignment_semantics.py:51` and `:62`: use
    `Cell(source=ctx.a)`;
  - `seamless-workflow/tests/test_controller_lifecycle.py:122`: use
    `Cell(source=ctx.a.build())`.

**Documents:**

- [Plan](../seamless-workflow/validation/celltype-rename/plan.md) :64: "same as
  `.set(v)`" becomes "serialized like `.set(v)`".
- [context-internals-followup-design.md](context-internals-followup-design.md):
  - :259-268, `.set()` at a projection being equivalent to assignment;
  - :314-334, §`Cell.set()`.
- seamless-core README: `.set()`.

### 7. Celltype `checksum`: value-form writes

With §4 in place, a `Checksum` can be a value.

**Status: implemented** (seamless-core `c77d688`, seamless-transformer `773cf1f`,
seamless-workflow `69fd2b0`), verified 2026-09-15, for all five write forms, with the
tests and documents below.

**Not yet discussed** (found while verifying): `_prepare_transformer` in
`seamless_workflow/ingress.py`, used when an uncalled transformer is bound to a
Context, calls `checksum_for_value` without `checksum_is_value=True`, unlike
`_prepare_assignment` and `_set_transformer_pin`. It would matter only if a bare
`Checksum` reached a `checksum` pin there. That path wasn't exercised, so whether this
is a bug or dead code is unconfirmed.

**Implemented** (proposed as Recommended):

- One rule for every value-form write: **a `Checksum` is a value exactly when the
  target celltype is `checksum`.** That covers `.set()`, `.value =`, `ctx.a =`,
  `tf.pins.x =` and `tf(x=...)`. For every other celltype:
  - assignment and call-time arguments keep reading a `Checksum` as a declared
    reference ([adapters.py:16](../seamless-workflow/seamless_workflow/adapters.py#L16));
  - `.set()` and `.value =` raise `TypeError`.
- Remove the call-time rule that reads any 64-character `str` as a checksum
  ([pretransformation.py:240](../seamless-transformer/seamless_transformer/pretransformation.py#L240)).
  A hex string is a value, as it already is for Cells.

**Tests:**

- `Cell('checksum').set(cs)`:
  - the buffer is the bare 64-byte digest;
  - `.value` is a `Checksum` equal to `cs`, and `.value == .run() == .build().run()`;
  - `.set(cs.hex())` gives the same checksum.
- Assigning to a bound `checksum` cell stores the value. `.set(cs)` on an `int` cell
  raises `TypeError`.
- `tf(x=hex_str)` on a `str` pin is a value.
- **Not yet discussed** (review finding): a bare Checksum passed at call time is read
  in the pin's celltype.

**Documents:** seamless-core README: the `checksum` celltype.

---

## Part IV. Workflow and serialization together

These change user-visible contracts and span several repositories. Standalone reads
depend on §3 and §5; their remote steps are in §10. Mounts and null depend on nothing
above, and can be done in parallel with any part.

### 8. Standalone Cell reads

This replaces [plan.md:168](../seamless-workflow/validation/celltype-rename/plan.md#L168)
("`.value` and `.buffer` … stay bound-only") for standalone reads.

Before the plan, a standalone Cell's `.checksum`, `.value`, `.buffer`, `.state` and
`.exception` raised "only available for bound workflow cells"; no document gave a
reason. Codex made the standalone `.checksum` getter call `self.compute()`, and turn
every exception into state `failed` with checksum `None`
([cell_class.py:101-122](../seamless-core/seamless/cell_class.py#L101-L122)). Both
parts of that are replaced below.

Two concerns stay separate throughout: **retrieving** `.checksum`, and
**materializing** it into `.buffer` or `.value`.

#### 8.1 Retrieving `.checksum` — Decided

- **A property getter never runs a source.** For a Cell fed by an Expression or a
  Transformation, `.checksum` reports a result only if the source already has one.
  The call that does work is `.compute()`, as `Buffer.get_checksum()` is for
  `Buffer.checksum`. Cell, Pin and Expression get no `get_checksum()`, because
  `.compute()` already fills that role. `Expression.checksum` already behaves this way.
- **A Cell's own expression is cheap, so the getter evaluates it** whenever the input
  checksum is at hand: a bare checksum, or a source that already has its result. In
  the rare case where the input isn't available yet, it waits.
- **Resolution order** for the Cell's own expression:
  1. nothing to apply (no path, no conversion, no validator): the input checksum;
  2. a hit in the expression cache;
  3. a hit in the database (§10.4);
  4. the same evaluation already running in this process: wait for it;
  5. the input buffer is local: evaluate now;
  6. the input buffer is elsewhere: send the evaluation to the jobserver and wait
     (§10.4).

  Otherwise `.checksum` is `None`: nothing is known, no remote is configured, or
  evaluation failed (§8.3). What "local" means, and steps 3 and 6, are in §10.
- **Wait on expressions, never on transformations.** A source Transformation that is
  still running gives `None`. A running source Expression may be waited on, unless
  it depends on a running Transformation.
- **Bound and standalone deliberately differ.** A bound `.checksum` never waits: a
  node that is still computing reports `None` with state `waiting`, because the
  Context works in the background. A standalone Cell has nothing working in the
  background, so it waits.

#### 8.2 Expressions and fingertipping — Decided (existing design confirmed)

- Expressions fingertip their input only as part of a `Checksum.fingertip()` chain,
  never during ordinary evaluation. The code complies.
- Where expressions are evaluated is in §10.

#### 8.3 Evaluation failures

**Decided:**

- If evaluation fails with `CacheMissError(checksum)`, that error becomes the Cell's
  `.exception`, showing the missing checksum without a traceback. The state is
  `failed`, and it stays `failed`.
- `clear_exception()` retries, for example once more caches are configured or the
  network is better. There is no automatic retry, following the pass3 ruling on
  transient failures ([pass3:835-840](context-internals-design-pass3.md#L835-L840)).
- An expression that is itself invalid (an impossible path or conversion) also sets
  `.exception`, with state `failed`.
- The same applies to bound and standalone Cells.

The checksum shown is the one whose buffer was missing. In a chain of expressions,
that can be an inner input rather than the Cell's own.

**Recommended:**

- Remember the failure on the handle that `clear_exception()` is called on, not in
  the substrate keyed by expression identity. Otherwise a new Cell with the same
  recipe inherits an old cache-miss failure.
  - Standalone: on the Cell, reset when its input, path or celltype changes.
  - Bound: on the Context node, as the stored results of `_demand` already work
    ([context.py:1199](../seamless-workflow/seamless_workflow/context.py#L1199)).
    `clear_exception()` must drop that stored result.
- Use one convention for `.exception` across Cell, Pin and Transformation. Today a
  bound Cell stores an exception object, while `Transformation.exception` is a string.

**Required changes to the current code.** The substrate changes, which make
`CacheMissError` reach the Cell, are in §5. Here:

- Standalone `Cell.clear_exception()` raises
  ([cell_class.py:507-512](../seamless-core/seamless/cell_class.py#L507-L512)).
  `Expression.clear_exception()` ([pass3 III.6](context-internals-design-pass3.md#L649-L656))
  doesn't exist yet. Pin needs it too.

**Decided: what standalone `.state` should report for a Cell whose source has no
result yet** . The current getter falls through to `"blocked"`
([cell_class.py:156-166](../seamless-core/seamless/cell_class.py#L156-L166)). That is
misleading for a Cell that simply hasn't been computed. This is to be changed to "waiting".

#### 8.4 Materializing into `.buffer` and `.value` — Decided

- **`.value` and `.buffer` never fingertip.** Both modes resolve through
  `Checksum.resolve()`: local cache, then hashserver, otherwise `CacheMissError`. The
  code complies. `Transformation.run()` does fingertip, but it is an explicit method.
- **A `CacheMissError` on the result checksum is raised to the caller and never
  becomes `.exception`.** The computation succeeded; whether its buffer can be
  reached depends on storage and on who is reading. The state stays `complete`.
- **`Expression.run()`, and so `Cell.run()`, materializes through `Checksum.resolve()`**
  (§5).
- **Deserialization errors don't invalidate expressions.** The steps are:
  1. retrieve the result checksum, without questioning its validity;
  2. validate it against the celltype using the result's HashType, and for python,
     ipython and yaml also the text validation at parse time, which HashType doesn't
     cover (§3.2 items 3 and 7). Where HashTypes are stored, and validation with a
     HashType that only the database knows, are in §10.6.

  A validation failure is raised to the caller and sets the Cell's `.exception`. That
  failure is deterministic: the expression result stays stored, and `clear_exception()`
  produces the same failure again (§3.2 item 7).
- The HashType work this relies on is in §3.2 and §10.6, and the "42" case in §3.3.

**Tests:**

- A standalone `.checksum` doesn't start a source Transformation: it returns `None`,
  and the source stays unstarted. `.compute()` does start it.
- A Cell over a bare checksum with a conversion evaluates when `.checksum` is read.
- A read waits for an expression that is already running.
- A missing input buffer:
  - `.exception` shows the checksum and no traceback;
  - the state is `failed` and `.checksum is None`;
  - once the buffer is available, `clear_exception()` followed by a read succeeds.

  Test this standalone and bound. The variant through the jobserver is in §10.7.
- An unavailable result buffer, in both modes: `.value` raises `CacheMissError`, the
  state stays `complete`, and `.exception is None`.
- `.value` never fingertips: an evicted but recomputable result raises
  `CacheMissError`, with fingertipping patched to fail.
- A Cell built on an expression whose result can't be deserialized as its celltype
  fails. The expression record stays, and `clear_exception()` gives the same failure.

**Documents:**

- [Plan](../seamless-workflow/validation/celltype-rename/plan.md):
  - :61, the base-class member list, for standalone reads;
  - :168, standalone reads.
- seamless-core README: standalone reads.

### 9. Mounts and null

**Decided.** This replaces plan rules 3 and 5, and the missing-file parts of :129 and
:137 ([plan.md:117-139](../seamless-workflow/validation/celltype-rename/plan.md#L117-L139)).
Plan rule 2 is narrowed to: **a sensing mount (`r`, `rw`) never leaves its cell
without a checksum.** Clearing a mounted cell stays refused in every mode.

#### 9.1 Principles

1. A missing file holds no value. An empty file, or a file containing `null\n`, holds
   the null value.
2. Authority only decides between two values, and only at mount time. At mount time,
   a missing file, a zero-byte file or an empty directory never wins.
3. A cell without a value gets null only under a sensing mount, and only when the file
   supplies no value. That null is the outcome of table 9.2, never set before it.
4. When deciding whether to write, "missing" counts as equal to null. A null cell
   never creates a file.
5. `file-strict` means the file must exist. A missing file is a sense error, both at
   mount time and later. A zero-byte file does exist.
6. A value change never deletes a file or directory.

A *sense error* means: the cell becomes `failed` with a `MountError`, its stored value
is kept but hidden, and it recovers when the file becomes valid
([mount-design §8.2](mount-design.md#L498)).

#### 9.2 Initial state, at `mount()` and `set_graph(..., mounts=True)`

| mode, authority | cell | file missing | zero-byte file or empty directory | `null\n` | valid *F* | invalid file |
|---|---|---|---|---|---|---|
| `r`/`rw`, any | no value | cell ← null; `file-strict`: sense error | cell ← null | cell ← null | cell ← *F* | sense error |
| `r`/`rw`, `file` | value *N* | `r`: nothing; `rw`: write *N* ¹ | `r`: nothing; `rw`: write *N* ¹ | cell ← null ² | cell ← *F* if different ² | sense error |
| `r`/`rw`, `file-strict` | value *N* | sense error | `r`: nothing; `rw`: write *N* ¹ | cell ← null ² | cell ← *F* if different ² | sense error |
| `r`, `cell` | value *N* | nothing | nothing | nothing | nothing; *F* is the baseline | nothing |
| `rw`, `cell` | value *N* | write *N* ¹ | write *N* ¹ | write *N* ¹ | write *N* if different ² | write *N* |
| `w` | not complete (connected, or unconnected with no value) | nothing now; write when complete | same | same | same | same |
| `w` | value *N* | write *N* ¹ | write *N* ¹ | write *N* ¹ | write *N* if different | write *N* |

¹ Nothing if *N* is null. ² Logged once.

A zero-byte file or an empty directory counts as "no value" only at mount time.
`null\n` remains an explicit null value, because Seamless never writes it: it comes
from a person or a tool on purpose. Consequence: a file truncated while no Context is
running doesn't win when the graph is reloaded, and under `rw` the value from the
graph is written back.

#### 9.3 File changes, after mounting

| the file becomes | modes `r`, `rw` | mode `w` (cell complete) |
|---|---|---|
| deleted (file or directory) | cell unchanged; a sense error caused by an invalid file is cleared, revealing the stored value; under `rw` the next cell change recreates the file; `file-strict`: sense error until the file reappears | rewrite *N*, unless *N* is null |
| empty (zero bytes) or `null\n` | cell ← null; the file is not rewritten | rewrite *N*, unless *N* is null |
| valid *F* (an emptied directory reads as `{}`) | cell ← *F*; clears any sense error | rewrite *N* |
| invalid | sense error; the stored value is hidden | rewrite *N* |

Under `w`, nothing happens while the cell is incomplete, and the oscillation detector
limits rewrites. After mounting, authority plays no role, except that `file-strict`
requires the file to exist.

#### 9.4 Cell changes, after mounting

| cell event | modes with `w` | mode `r` |
|---|---|---|
| new value *N* that differs from the file | write *N* (atomic, and only if the file hasn't changed since last seen) | nothing |
| becomes null | write an empty file, also for `.gz`/`.zst`; nothing if the file is missing | nothing |
| value equals the file (null equals a zero-byte file, `null\n` and a missing file) | nothing | nothing |
| not complete (waiting, computing, blocked, failed) | nothing; the file keeps its last content | nothing |
| a directory cell becomes null | nothing; the tree stays and is reported out of sync | nothing |
| `.checksum = None` or `.buffer = None` | refused: unmount first | refused |
| retype | refused | refused |
| new incoming edge | `w`: allowed; `rw`: refused | refused (the mount is the cell's producer) |
| cell deleted, or replaced by a transformer | unmount; with `persistent=False`, delete the file only if it is unchanged | same |

#### 9.5 Differences from the current code

Checked against real files, except where marked:

| case | current behaviour |
|---|---|
| cell `'old'` mounted on a missing path with `rw`/`file`, `r`/`file` or `file-strict` | **the value becomes null** |
| `file-strict`, file missing at mount or deleted later | no error; the cell becomes null |
| cell without a value mounted on an existing file with `rw`+`cell`, or with `w` | **the file is truncated to empty** |
| cell without a value mounted on an invalid file with `rw`+`cell` | **the file is truncated**, and there is no sense error |
| cell without a value mounted on *F* with `r`+`cell` | the cell becomes null instead of *F* |
| file deleted under `rw` or `file-strict` | the cell becomes null |
| cell with a value mounted on a zero-byte file with `file` authority (not run; same code path as a missing file) | the value becomes null |
| directory cell becomes null (not run) | the tree is deleted with `rmtree` |

Causes:

- The file driver reports a missing file as the null checksum
  ([service.py:194](../seamless-workflow/seamless_workflow/attachments/fs/service.py#L194)).
- Mounting sets a cell without a value to null *before* the decision is made
  ([runtime.py:67-71](../seamless-workflow/seamless_workflow/attachments/runtime.py#L67-L71)).
- Delivering null to a directory calls `rmtree`
  ([service.py:325](../seamless-workflow/seamless_workflow/attachments/fs/service.py#L325)).

`test_initial_policy` still passes because it calls `decide_initial` with `ABSENT`,
which the file driver no longer produces.

Test edits to revert:

- [test_mounts.py:76-82](../seamless-workflow/tests/test_mounts.py#L76-L82) now
  expects null under `file-strict`;
- `authority='cell'` was added at lines 153, 213, 333 and 343 to keep values from
  being lost.

#### 9.6 Contradictions in `mount-design.md` (Phase 8)

- A missing file is null in the header (:15-21), §5.2 (:309), §7.2 (:418-449), the
  `absent` row of its §8.2 and the null-files paragraph of its §10 (:708-712).
- A deleted file doesn't clear the cell, and `file-strict` raises an error, in §3
  item 11 (:151-154), §8.3 (:568-570) and §20 item 2 (:1286-1288).
- §13 (:878-879) says empty directories can't be represented; the header says they
  read as `{}`.

Rewrite these along the lines of §9.1–9.4.

#### 9.7 Tests and documents

**Tests:**

- One integration test with real files per row of tables 9.2–9.4, including
  `.gz`/`.zst` files and directories.
- Revert the test edits listed in §9.5, and turn the cases in that table into
  regression tests.
- **Not yet discussed** (review finding): a mount on a cell whose checksum is still
  being computed doesn't write (plan rule 2). This is the "not complete" row of
  table 9.4.

**Documents:**

- [Plan](../seamless-workflow/validation/celltype-rename/plan.md) :117-139, the mount
  rules.
- [mount-design.md](mount-design.md): the sections listed in §9.6.
- seamless-workflow README: mounts.

---

## Part V. Evaluation location

Where expressions are evaluated, and what can be known without the buffer. This part
gathers pieces formerly in §3.2 (items 5 and 6), §5, §8.1 and §8.2, together with the
findings of a 2026-09-15 review. The code references of those findings (§10.2, and the
review finding in §10.5) are to the working tree of that date.

Depends on §3.2 items 1–5 (local), and on the local error changes of §5. Steps 3 and 6
of §8.1, and the jobserver tests of §5, §8.3 and §8.4, wait for this part.

### 10. Expressions are evaluated where the data is

#### 10.1 The rule — Decided (formerly §8.2)

Expressions are evaluated where the data is. With `execution="auto"`, evaluation goes to
the jobserver when the input buffer isn't local. The bound Context defaults to `"auto"`
([context.py:45](../seamless-workflow/seamless_workflow/context.py#L45)).

#### 10.2 Current code — Not yet discussed

[`evaluate_expression_remote`](../seamless-core/seamless/checksum/expression.py#L171)
checks the expression cache, then the database, then picks a location. With `"auto"`,
[`choose_expression_evaluation_location`](../seamless-core/seamless/checksum/expression.py#L54)
evaluates locally when no buffer is needed or the input buffer is local, and on the
jobserver otherwise. The jobserver fetches the input from the hashserver and evaluates
it inline. Only bound projections and dask workers use `"auto"`.

Findings, from probes without a jobserver configured:

1. **"Local" means "in this process's memory".** `_get_local_buffer` never asks the
   hashserver. It also finds buffers in `checksum_cache`, the last 10 buffers whose
   checksum was computed
   ([cached_calculate_checksum.py:17](../seamless-core/seamless/checksum/cached_calculate_checksum.py#L17)),
   which `Checksum.resolve()` doesn't consult. So a dropped buffer that `resolve()`
   can't find may still be evaluated locally.
2. **No fallback.** `"auto"` with an input buffer that isn't in memory, and no
   jobserver, raises `RuntimeError: No jobserver clients are available`, even if the
   hashserver has the buffer.
3. **"Local" differs by path.** The asynchronous local path fetches the input from the
   hashserver; the synchronous one raises "not available locally".
4. **Paths that ignore the rule.** Standalone `Expression.compute()` and `Cell.compute()`
   default to `"local"`, on the synchronous path. The Expression inputs of a
   transformation are evaluated locally (`dep._evaluate_internal()` in
   `transformation_class.py`, and `PreTransformation._prepare_pin_value`): they
   download the input or fail, and are never dispatched.
5. **A bound failure is silent.** A projection over a buffer that exists nowhere ends
   `blocked`, with `exception None`. §8.3 decides `failed` with `CacheMissError`.

Test coverage: `"auto"` is tested only on its local branch, with fake remotes, and that
test's input buffer is found through the 10-entry cache of finding 1. `"auto"`
dispatching to the jobserver, and `"auto"` without a jobserver, are untested. No
workflow test configures a jobserver or sets `expression_execution`, and no dask test
uses Expressions.

#### 10.3 Decisions needed — Open

- **What counts as local:** in memory, or resolvable through `Checksum.resolve()`,
  which includes the hashserver.
- **The fallback without a jobserver:** evaluate locally and fetch the input, or fail
  with `CacheMissError`.
- **Who follows the rule:** whether standalone `compute()` and the Expression inputs of
  transformations use `"auto"`, as bound projections and dask workers do.

#### 10.4 Remote steps of standalone reads — Decided (formerly §8.1)

- Steps 3 and 6 of the §8.1 resolution order: a hit in the database; and, when the
  input buffer is elsewhere, sending the evaluation to the jobserver and waiting.
- **"Running" is visible only inside this process**: `_active_expressions` for remote
  requests, and a bound Context's jobs. The jobserver merges a duplicate request from
  another process.
- **Inside a running event loop** (Jupyter, async code) the getter can't wait on a
  remote evaluation ([expression_class.py:164](../seamless-core/seamless/expression_class.py#L164)).
  Without the jupyter-sync driver-loop fix, it returns `None` there. Local evaluation
  is unaffected.

#### 10.5 Errors across the jobserver (formerly §5)

**Required changes: errors keep their type.**

- The jobserver returns every expression error as plain HTTP 500 text
  ([jobserver.py:729-761](../seamless-jobserver/jobserver.py#L729-L761)). The client
  turns every 4xx/5xx response into `ClientConnectionError`
  ([jobserver_client.py:113](../seamless-remote/seamless_remote/jobserver_client.py#L113)).
  Errors need a structured response (kind plus checksum) that the client turns back
  into `CacheMissError`.
- `jobserver_remote.run_expression` retries only on `ClientRestartRequiredError`, so a
  cache miss must not be mistaken for a connection problem.

**Not yet discussed** (review finding): the dask worker's expression path
([client.py:835-860](../seamless-dask/seamless_dask/client.py#L835-L860)) passes errors
back as strings, so a `CacheMissError` on a worker probably loses its type too. The
transformation endpoints of the jobserver also return plain 500 text; a shared error
format would keep the two paths aligned.

#### 10.6 HashTypes in the database (formerly §3.2, items 5 and 6)

**Decided: a stored HashType can only be tightened, in the database too.** Today the
database rejects every differing word as a conflict
([database_models.py:67-79](../seamless-database/database_models.py#L67-L79),
[database.py:797-800](../seamless-database/database.py#L797-L800)). It must accept a
tighter word, under the rules of §3.2 item 5. A local HashType cache uploads to the
database whenever its word changes; today only the asynchronous path uploads
(`register_hash_type_for_buffer_async`).

**Decided: HashTypes are stored in the database** (the `hash_type` table), not
provided by the jobserver. Validation at retrieval time reads the result's HashType
from there
([database_remote.py:198](../seamless-remote/seamless_remote/database_remote.py#L198)).
Two gaps in the current code:

- Nothing stores the HashType of a *result*. Only asynchronous validation writes a
  HashType to the database, and only for the expression's *input*
  (`ensure_hash_type_async` in `hash_type_validation.py`).
  Recommended: whoever evaluates the expression, including the jobserver, stores the
  result's HashType too, since it holds the result buffer.
- The synchronous `ensure_hash_type` only checks the local cache and a buffer that
  is already present. Otherwise it silently skips validation. It must also check the
  database. Called from a getter inside a running event loop, that lookup has the
  same constraint as §10.4.

#### 10.7 Tests

Moved here:

- A HashType write to the database replaces the stored word only when it is tighter;
  an equal or looser write keeps it, and a contradictory write is a conflict. A local
  word that gets tightened is uploaded to the database. (From §3.4.)
- Evaluating an expression, locally and on the jobserver, stores the result's HashType
  in the database. (From §3.4.)
- Retrieval validation works with a HashType that only the database knows: no local
  cache entry and no buffer. (From §3.4 and §8.4.)
- `Expression.run()` of a result evaluated on the jobserver resolves through the
  hashserver. (From §5.)
- A missing input buffer through the jobserver: `.exception` shows the checksum, the
  state is `failed`, and `clear_exception()` recovers once the buffer is available.
  (From §8.3.)

New, for the gaps of §10.2:

- `"auto"` dispatches to the jobserver when the input buffer isn't local, and
  evaluates locally when it is, with buffers held explicitly rather than found in
  `checksum_cache`.
- `"auto"` without a jobserver behaves as decided in §10.3.
- A bound Context with a jobserver: a projection over a buffer that is only on the
  hashserver.
- The Expression input of a transformation, and an Expression through dask, follow the
  decision on who follows the rule.
