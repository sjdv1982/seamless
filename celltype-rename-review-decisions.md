# Celltype rename: decisions from the test review

**Status.** Decisions from the 2026-09-14 review of the tests Codex wrote for the
celltype-rename and Pin plan ([plan](../seamless-workflow/validation/celltype-rename/plan.md)),
made after Phases 0–8 were committed. Final commits: seamless-core `639dcc4`,
seamless-workflow `055adec`, seamless-transformer `5406f68`, seamless `c84ce320`.
All code references are to those commits. Where this document and the plan disagree,
this document wins. None of it is implemented yet.

Labels:

- **Decided**: agreed in the review.
- **Recommended**: proposed in the review and not contested, but not explicitly
  confirmed. Confirm before implementing.
- **Open**: still needs a decision.

Contents:

1. [Standalone Cell reads](#1-standalone-cell-reads)
2. [`.set()` takes values only](#2-set-takes-values-only)
3. [Celltype `checksum`](#3-celltype-checksum)
4. [Mounts and null](#4-mounts-and-null)
5. [Printing the null checksum](#5-printing-the-null-checksum)
6. [Documents to update](#6-documents-to-update)
7. [Tests](#7-tests)
8. [Not yet discussed](#8-not-yet-discussed)

---

## 1. Standalone Cell reads

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

### 1.1 Retrieving `.checksum` — Decided

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
  3. a hit in the database;
  4. the same evaluation already running in this process: wait for it;
  5. the input buffer is local: evaluate now;
  6. the input buffer is elsewhere: send the evaluation to the jobserver and wait.

  Otherwise `.checksum` is `None`: nothing is known, no remote is configured, or
  evaluation failed (§1.3).
- **Wait on expressions, never on transformations.** A source Transformation that is
  still running gives `None`. A running source Expression may be waited on, unless
  it depends on a running Transformation.
- **"Running" is visible only inside this process**: `_active_expressions` for remote
  requests, and a bound Context's jobs. The jobserver merges a duplicate request
  from another process.
- **Inside a running event loop** (Jupyter, async code) the getter can't wait on a
  remote evaluation ([expression_class.py:164](../seamless-core/seamless/expression_class.py#L164)).
  Without the jupyter-sync driver-loop fix, it returns `None` there. Local
  evaluation is unaffected.
- **Bound and standalone deliberately differ.** A bound `.checksum` never waits: a
  node that is still computing reports `None` with state `waiting`, because the
  Context works in the background. A standalone Cell has nothing working in the
  background, so it waits.

### 1.2 Expressions and fingertipping — Decided (existing design confirmed)

- Expressions fingertip their input only as part of a `Checksum.fingertip()` chain,
  never during ordinary evaluation. The code complies.
- Expressions are evaluated where the data is. With `execution="auto"`, evaluation
  goes to the jobserver when the input buffer isn't local. The bound Context
  defaults to `"auto"` ([context.py:45](../seamless-workflow/seamless_workflow/context.py#L45)).

### 1.3 Evaluation failures

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

**Required changes to the current code:**

- A missing buffer in local evaluation raises `ExpressionEvaluationError("… is not
  available locally")` ([expression.py:453](../seamless-core/seamless/checksum/expression.py#L453)),
  the same class as an invalid path. It must raise `CacheMissError`.
- The jobserver returns every expression error as plain HTTP 500 text
  ([jobserver.py:729-761](../seamless-jobserver/jobserver.py#L729-L761)). The client
  turns every 4xx/5xx response into `ClientConnectionError`
  ([jobserver_client.py:113](../seamless-remote/seamless_remote/jobserver_client.py#L113)).
  Errors need a structured response (kind plus checksum) that the client turns back
  into `CacheMissError`.
- The bound transformer runner reduces errors to `WorkflowExecutionError(str(exc))`
  ([reactive.py:167](../seamless-workflow/seamless_workflow/reactive.py#L167)), which
  loses the exception type.
- Standalone `Cell.clear_exception()` raises
  ([cell_class.py:507-512](../seamless-core/seamless/cell_class.py#L507-L512)).
  `Expression.clear_exception()` ([pass3 III.6](context-internals-design-pass3.md#L649-L656))
  doesn't exist yet. Pin needs it too.

**Open:** what standalone `.state` should report for a Cell whose source has no
result yet. The current getter falls through to `"blocked"`
([cell_class.py:156-166](../seamless-core/seamless/cell_class.py#L156-L166)). That is
misleading for a Cell that simply hasn't been computed.

### 1.4 Materializing into `.buffer` and `.value` — Decided

- **`.value` and `.buffer` never fingertip.** Both modes resolve through
  `Checksum.resolve()`: local cache, then hashserver, otherwise `CacheMissError`. The
  code complies. `Transformation.run()` does fingertip, but it is an explicit method.
- **A `CacheMissError` on the result checksum is raised to the caller and never
  becomes `.exception`.** The computation succeeded; whether its buffer can be
  reached depends on storage and on who is reading. The state stays `complete`.
- **`Expression.run()`, and so `Cell.run()`, materializes through `Checksum.resolve()`.**
  Today it uses the local-only lookup
  ([expression_class.py:365-371](../seamless-core/seamless/expression_class.py#L365-L371)),
  so a result computed on the jobserver fails in `.run()` while `.value` works.
- **Deserialization errors don't invalidate expressions.** The steps are:
  1. retrieve the result checksum, without questioning its validity;
  2. validate it against the celltype using the result's HashType, which is stored in
     the database.

  A validation failure is raised to the caller and sets the Cell's `.exception`. That
  failure is deterministic: the expression result stays stored, and `clear_exception()`
  produces the same failure again (§1.5, items 5–6).
- **HashType needs work, but its mechanism is adopted.** Type-bits design §5
  ([type_bits_design.md:316](../seamless-core/type_bits_design.md#L316)) already
  defines `deserializable_as` as strict: "`parse_buffer` would succeed". The
  implementation doesn't meet that yet (§1.5).
- **Evaluation needs work too, for the "42" case.**
  `Cell('int', checksum=<checksum of the JSON string "42">)` gets
  `input_celltype='int'` and takes the identity shortcut
  ([expression.py:336](../seamless-core/seamless/checksum/expression.py#L336)). It
  then returns the string's checksum as the int result.

### 1.5 HashType

Probe comparing `deserializable_as` with `parse_buffer`:

| buffer | celltype | HashType | parse |
|---|---|---|---|
| `"4.5"` | int | allowed | raises `ValueError` |
| `1e999`, `NaN` | float | allowed | raises |
| `NaN` | plain | allowed | raises |
| `4.5` | int | allowed | **silently returns 4** |
| `12345678901234567890123` | int | allowed | **silently returns 12345678901234567741440** |
| `true` | str | allowed | **returns `"True"`** |
| `"42"` (JSON string) | int / float | allowed | coerced to 42 / 42.0 |
| `42` | str | allowed | coerced to `"42"` |
| 64×`z` | checksum | allowed | raises `TypeError` |
| invalid Python / YAML | python / yaml | allowed | raises `ValueError` |
| `42` | bool | rejected | would coerce to `True` (rejecting is fine) |

**Recommended changes:**

1. Classify JSON the way the parser does. HashType uses `json.loads`
   ([hash_type.py:556](../seamless-core/seamless/checksum/hash_type.py#L556)), which
   accepts `NaN`, `Infinity` and exact big integers. The parser uses `orjson`, which
   rejects `NaN` and returns integers beyond 64 bits as floats.
2. **Decided: no integer bit.** Whether a value can be an `int`, a `float` or a `bool`
   follows from the levels of item 7, except for rounding: `4.5`, or an integer beyond
   64 bits, is a numeric scalar that still doesn't fit an `int`. Recommended:
   `parse_buffer` raises instead of rounding silently.
3. Treat a failed `text_validation_celltype_cache` check (python, ipython, yaml)
   exactly like a HashType validation failure. These celltypes are outside HashType
   by design (§5 †, §13).
4. `parse_buffer` raises `TypeError` for a non-hex `checksum` value
   ([parse_buffer.py:127](../seamless-core/seamless/checksum/parse_buffer.py#L127)).
   It should raise a validation error.
5. **Decided: HashTypes are stored in the database** (the `hash_type` table), not
   provided by the jobserver. Validation at retrieval time reads the result's HashType
   from there
   ([database_remote.py:198](../seamless-remote/seamless_remote/database_remote.py#L198)).
   Two gaps in the current code:
   - Nothing stores the HashType of a *result*. Only asynchronous validation writes a
     HashType to the database, and only for the expression's *input*
     ([hash_type_validation.py:59-64](../seamless-core/seamless/checksum/hash_type_validation.py#L59-L64)).
     Recommended: whoever evaluates the expression, including the jobserver, stores the
     result's HashType too, since it holds the result buffer.
   - The synchronous `ensure_hash_type` only checks the local cache and a buffer that
     is already present. Otherwise it silently skips validation
     ([hash_type_validation.py:43-48](../seamless-core/seamless/checksum/hash_type_validation.py#L43-L48)).
     It must also check the database.
6. **Decided: expression results are never undone.** An expression whose result can't
   be deserialized as its celltype is not invalid: it deterministically returns that
   checksum. The result is stored in the `expression` table as usual. The result's
   HashType, in the separate `hash_type` table, records that it can't be deserialized
   as that celltype. A Cell built on it stays `failed`, and `clear_exception()`
   produces the same failure again, as it should.
7. **Decided: a stored HashType can only be tightened.** A word is tighter when it
   implies the stored word. For example, testing may replace `JSON_UNTESTED` with
   `JSON_OBJECT`. A producer may also store an untested level without testing further,
   such as "UTF-8" without testing for JSON.

   The rule applies to the database and to local HashType caches, which upload to the
   database whenever their word changes. Today the database rejects every differing
   word as a conflict
   ([database_models.py:67-79](../seamless-database/database_models.py#L67-L79),
   [database.py:797-800](../seamless-database/database.py#L797-L800)). It must accept a
   tighter word.

   This changes the type-bits design. §8.1 requires every word to be complete, and
   `RAW_TEXT` asserts a negative: "UTF-8 and *not* JSON" (§4.1).

   **Decided: the untested levels.** From loosest to tightest:
   - **Nothing tested:** any Kind is possible.
   - **UTF-8:** Kind 4–8 (`RAW_TEXT` or a JSON Kind).
   - **JSON:** Kind 5–8.
   - **Numeric scalar:** tested or not.

   Whether a value can be an `int`, a `float` or a `bool` then follows from
   `deserializable_as`, apart from rounding (item 2).

   The Kinds form a tree, and testing moves a word down it:
   - "Nothing tested" narrows to "UTF-8", to `RAW_BYTES`, to `NUMPY` or to a `MIXED_*`
     Kind. The binary Kinds need no intermediate level, because their magic bytes are
     recognized in constant time.
   - "UTF-8" narrows to "JSON" or to `RAW_TEXT`.
   - "JSON" narrows to a concrete JSON Kind.

   **Recommended:**
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
     - Their most-informative celltypes (§8.2) are `bytes`, `text` and `plain`.
     - `is_utf8` and `is_json` can no longer be `≥` thresholds (§4.1). They become set
       membership, because renumbering the existing Kinds would change every stored
       word.
   - **"Numeric scalar tested" needs no bit.** Confirming a concrete JSON Kind requires
     its value, and the `float(value)` probe then costs nothing (§8.2). So
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
     | `checksum` | ? (no unless `Length` is `EQ64`) | ? (no unless `EQ64`) | no |

     - `bool` and null stay decided by the checksum, as today.
     - A path step on these Kinds is never rejected, because their capabilities (§7)
       are not yet known.
   - **Writes that aren't tighter.**
     - An equal or looser write changes nothing.
     - A contradictory write is a conflict, and is logged. This includes a
       disagreement about `Length` or `NUMERIC_SCALAR`. A HashType is a function of the
       buffer, so correct producers never contradict each other; only a bug or a change
       in the classification rules can.
   - **The local cache.** Today it overwrites unconditionally
     ([hash_type.py:261-268](../seamless-core/seamless/checksum/hash_type.py#L261-L268)),
     and only the asynchronous path uploads to the database
     ([hash_type.py:334-351](../seamless-core/seamless/checksum/hash_type.py#L334-L351)).
     It must only tighten, and upload whenever its word changes.

   Consequences:
   - Information only grows. Item 6's "can't be deserialized" marker is never erased,
     so that failure stays visible at retrieval.
   - A wrong stored word can't be repaired by writing a correct one, because that write
     conflicts. So when the classification rules change (item 1, the parser's JSON
     rules), development databases must clear their `hash_type` table, which is a
     cache. Phase 3 did the same for the `expression` table.

**Open:** does "strict" mean "parses", or "parses **and** re-serializes to the same
checksum"? The §5 table accepts `"42"` as an int and `42` as a str. Recommended: the
canonical reading, leaving coercion to Expression conversions. `true` → `"True"` is
wrong under both readings.

---

## 2. `.set()` takes values only

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
assignment, `Cell(source=...)` or `pin.source`. Celltype `checksum` is the exception (§3).

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

**Current code:** a standalone `.set()` stores a Checksum, Expression or Cell as the
input ([cell_class.py:184-185](../seamless-core/seamless/cell_class.py#L184-L185)). A
bound `.set()` classifies its argument the way assignment does
([builder_state.py:169-172](../seamless-workflow/seamless_workflow/builder_state.py#L169-L172)).
The authority checks already exist.

---

## 3. Celltype `checksum`

**Decided:** the value of a `checksum` cell is a `Checksum` object (`None` stays
`None`). `.set(Checksum)` on a `checksum` cell stores that checksum as the value.

**Current code: the round trip is broken.**

- `Buffer("ab"*32, "checksum")` writes a quoted JSON string
  ([serialize.py:57-58](../seamless-core/seamless/checksum/serialize.py#L57-L58)).
  HashType and `parse_buffer` expect a bare 64-byte digest, so reading the value back
  raises `HashTypeValidationError`.
- `Buffer(Checksum(...), "checksum")` raises `TypeError`
  ([buffer_class.py:28-29](../seamless-core/seamless/buffer_class.py#L28-L29)).
- No test uses this celltype.

**Recommended:**

- Wrap and unwrap during serialization. `serialize` accepts a `Checksum` or a hex
  string and writes the bare digest; `parse_buffer` returns a `Checksum`. Then
  `.value`, `.run()`, `Expression.run()`, `Checksum.resolve("checksum")` and
  transformation pins all agree. Transformation code with a `checksum` pin then
  receives a `Checksum`.
- One rule for every value-form write: **a `Checksum` is a value exactly when the
  target celltype is `checksum`.** That covers `.set()`, `.value =`, `ctx.a =`,
  `tf.pins.x =` and `tf(x=...)`. For every other celltype:
  - assignment and call-time arguments keep reading a `Checksum` as a declared
    reference ([adapters.py:16](../seamless-workflow/seamless_workflow/adapters.py#L16));
  - `.set()` and `.value =` raise `TypeError`.
- Remove the call-time rule that reads any 64-character `str` as a checksum
  ([pretransformation.py:240](../seamless-transformer/seamless_transformer/pretransformation.py#L240)).
  A hex string is a value, as it already is for Cells.
- Wrapping only affects typing: a `checksum` cell doesn't hold the buffer it points
  to. Note that `Checksum == hex_str` is true, but the two hash differently.

---

## 4. Mounts and null

**Decided.** This replaces plan rules 3 and 5, and the missing-file parts of :129 and
:137 ([plan.md:117-139](../seamless-workflow/validation/celltype-rename/plan.md#L117-L139)).
Plan rule 2 is narrowed to: **a sensing mount (`r`, `rw`) never leaves its cell
without a checksum.** Clearing a mounted cell stays refused in every mode.

### 4.1 Principles

1. A missing file holds no value. An empty file, or a file containing `null\n`, holds
   the null value.
2. Authority only decides between two values, and only at mount time. At mount time,
   a missing file, a zero-byte file or an empty directory never wins.
3. A cell without a value gets null only under a sensing mount, and only when the file
   supplies no value. That null is the outcome of table 4.2, never set before it.
4. When deciding whether to write, "missing" counts as equal to null. A null cell
   never creates a file.
5. `file-strict` means the file must exist. A missing file is a sense error, both at
   mount time and later. A zero-byte file does exist.
6. A value change never deletes a file or directory.

A *sense error* means: the cell becomes `failed` with a `MountError`, its stored value
is kept but hidden, and it recovers when the file becomes valid
([mount-design §8.2](mount-design.md#L498)).

### 4.2 Initial state, at `mount()` and `set_graph(..., mounts=True)`

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

### 4.3 File changes, after mounting

| the file becomes | modes `r`, `rw` | mode `w` (cell complete) |
|---|---|---|
| deleted (file or directory) | cell unchanged; a sense error caused by an invalid file is cleared, revealing the stored value; under `rw` the next cell change recreates the file; `file-strict`: sense error until the file reappears | rewrite *N*, unless *N* is null |
| empty (zero bytes) or `null\n` | cell ← null; the file is not rewritten | rewrite *N*, unless *N* is null |
| valid *F* (an emptied directory reads as `{}`) | cell ← *F*; clears any sense error | rewrite *N* |
| invalid | sense error; the stored value is hidden | rewrite *N* |

Under `w`, nothing happens while the cell is incomplete, and the oscillation detector
limits rewrites. After mounting, authority plays no role, except that `file-strict`
requires the file to exist.

### 4.4 Cell changes, after mounting

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

### 4.5 Differences from the current code

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

### 4.6 Contradictions in `mount-design.md` (Phase 8)

- A missing file is null in the header (:15-21), §5.2 (:309), §7.2 (:418-449), the
  `absent` row of §8.2 and the null-files paragraph of §10 (:708-712).
- A deleted file doesn't clear the cell, and `file-strict` raises an error, in §3
  item 11 (:151-154), §8.3 (:568-570) and §20 item 2 (:1286-1288).
- §13 (:878-879) says empty directories can't be represented; the header says they
  read as `{}`.

Rewrite these along the lines of §4.1–4.4.

---

## 5. Printing the null checksum

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
§7 includes a test that finds the rest.

---

## 6. Documents to update

- **Plan** ([plan.md](../seamless-workflow/validation/celltype-rename/plan.md)):
  - :61, the base-class member list, for standalone reads;
  - :64, "same as `.set(v)`" becomes "serialized like `.set(v)`";
  - :117-139, the mount rules (§4);
  - :168, standalone reads (§1).
- **[context-internals-followup-design.md](context-internals-followup-design.md):**
  - :259-268, `.set()` at a projection being equivalent to assignment;
  - :314-334, §`Cell.set()`.
- **[mount-design.md](mount-design.md):** the sections listed in §4.6.
- **[type_bits_design.md](../seamless-core/type_bits_design.md):**
  - §1 and §8.1: completeness gives way to untested levels, and a stored word can only
    be tightened, both in the database and in the local cache;
  - §4.1: the three new Kind values, and set membership for `is_utf8`/`is_json`;
  - §5: the three outcomes of `deserializable_as`, the meaning of "strict", and the
    JSON rules.
- **READMEs:**
  - seamless-core: standalone reads, `.set()`, the `checksum` celltype, and how the
    null checksum prints;
  - seamless-workflow: mounts.

---

## 7. Tests

**§1, standalone reads and failures**

- A standalone `.checksum` doesn't start a source Transformation: it returns `None`,
  and the source stays unstarted. `.compute()` does start it.
- A Cell over a bare checksum with a conversion evaluates when `.checksum` is read.
- A read waits for an expression that is already running.
- A missing input buffer:
  - `.exception` shows the checksum and no traceback;
  - the state is `failed` and `.checksum is None`;
  - once the buffer is available, `clear_exception()` followed by a read succeeds.

  Test this standalone, bound, and through the jobserver.
- An unavailable result buffer, in both modes: `.value` raises `CacheMissError`, the
  state stays `complete`, and `.exception is None`.
- `.value` never fingertips: an evicted but recomputable result raises
  `CacheMissError`, with fingertipping patched to fail.
- `Expression.run()` of a result evaluated on the jobserver resolves through the hashserver.
- Each row of the §1.5 table becomes a parametrized case where HashType and the parser
  must agree.
- The "42" case is rejected or converted.
- Evaluating an expression, locally and on the jobserver, stores the result's HashType
  in the database.
- Retrieval validation works with a HashType that only the database knows: no local
  cache entry and no buffer.
- A Cell built on an expression whose result can't be deserialized as its celltype
  fails. The expression record stays, and `clear_exception()` gives the same failure.
- A HashType write replaces the stored word only when it is tighter, both in the
  database and in the local cache. An equal or looser write keeps the stored word, and
  a contradictory write is a conflict. A local word that gets tightened is uploaded to
  the database.
- A word at an untested level never causes a rejection.
- `parse_buffer` raises for `4.5` as `int` and for an integer beyond 64 bits.

**§2, `.set()`**

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

**§3, celltype `checksum`**

- `Cell('checksum').set(cs)`:
  - the buffer is the bare 64-byte digest;
  - `.value` is a `Checksum` equal to `cs`, and `.value == .run() == .build().run()`;
  - `.set(cs.hex())` gives the same checksum.
- Assigning to a bound `checksum` cell stores the value. `.set(cs)` on an `int` cell
  raises `TypeError`.
- A `checksum` pin receives a `Checksum`. A function that returns a `Checksum` with
  result celltype `checksum` serializes it to the bare digest.
- `tf(x=hex_str)` on a `str` pin is a value.

**§4, mounts**

- One integration test with real files per row of tables 4.2–4.4, including
  `.gz`/`.zst` files and directories.
- Revert the test edits listed in §4.5, and turn the cases in that table into
  regression tests.

**§5, printing the null checksum**

- `str()` of the null checksum is `NULL`, its `repr()` is the hex digest, and
  `Checksum("NULL")` raises.
- `is_null` recognizes the null checksum, and a null buffer uploads to and downloads
  from the hashserver.
- An audit run: the test suites pass with `Checksum.__str__` patched to return a
  non-hex string for *every* checksum. That catches any remaining use of `str()` as a
  machine format.

---

## 8. Not yet discussed

These review findings haven't been discussed yet. Their status was checked at the
final commits.

**Tests that assert nothing, or too little**

- `seamless-workflow/tests/test_pin_probe.py` and `test_pin_probe2.py` contain no
  assertions, yet count as passing files; the completion audit lists them as coverage.
  `validation/celltype-rename/celltype_probes.py` isn't part of any test suite.
- The bound Pin retype matrix has no checksum-level identity assertion
  ([plan.md:367](../seamless-workflow/validation/celltype-rename/plan.md#L367)). It
  checks the handle's checksum, not what enters the transformation.
- A failed pin conversion isn't asserted to be `blocked-by-error` (plan.md:369).
  `test_pin_handles.py:42` only checks that `'value'` appears in `block_reason`.
- Standalone "a retype converts at call time" (plan.md:347) is only checked on the Pin
  handle, never through `tf()`.
- The test of Expression's symmetric defaults was removed in Phase 4.
- Reading the retired `.input_ref` is never tested. The test for writing
  `target_celltype` on a bound cell only matches the message `'celltype'`.

**Missing tests where the contract is clear**

1. `ctx.tf.pins.x = v` over a connected pin detaches it, in both modes.
2. Buffer writes deposit the buffer: test without `tempref()`. Also validation in
   `set_buffer`, with a specific exception class instead of `pytest.raises(Exception)`.
3. The rows of the `.source`/`.checksum` table: an upstream that isn't complete; a
   connected cell whose own conversion fails, with its downstream `blocked-by-error`;
   a conversion that preserves bytes reporting the source's checksum.
4. Bound: a function returning `None` into a connected optional pin drops the pin
   (the bug that motivated the change).
5. `ctx["a"] = None` stores null.
6. Celltype stability:
   - assigning a value keeps the celltype, and an invalid literal raises;
   - assigning a builder over an existing cell replaces its config;
   - a new cell created from a transformer copies the result celltype.
7. Database composite key: records that differ only in `input_celltype`, or only in
   `celltype`, coexist.
8. Checksum assertions on the downstream cell in `test_celltype_changes.py`.
9. Deleting a bound pin removes it from `celltypes` and `optional_pins`.
10. A bare Checksum passed at call time is read in the pin's celltype.
11. A mount on a cell whose checksum is still being computed doesn't write (plan rule 2).

Dropped as not worth testing: setting an invalid `pin.celltype`, and accepting a
matching explicit `input_celltype=`.
