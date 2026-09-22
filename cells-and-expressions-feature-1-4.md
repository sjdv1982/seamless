# Features 1–4: celltypes, HashType, conversion, Expressions

Two things in one page:

1. **The repo-footprint audit** this file was written for (2026-09-21), answering: *is the
   implementation of features 1–4 limited to seamless-core?*
2. **Everything the work register holds about features 1–4**, copied across so the page can be
   read without it.

The register — `cells-and-expressions-known-issues.md` — remains the live to-do list and the
source of record. This page is a **snapshot taken on 2026-09-21**; if the register moves, re-copy.
Blocks marked *(Register §…)* are verbatim; everything else is this page's own.

## How the copied cross-references read here

The copied text uses the register's numbering — "section 2, item 4", "section 4, feature 4,
bug 1", "Appendix B". Those resolve inside this page as:

| Register reference | Here |
|---|---|
| section 1, features 1–4 | §1 |
| section 4, features 1–3 and feature 4 | §3 |
| section 4, feature 5 bug 5; feature 7 bug 3 | §3, last block — the two neighbouring bugs the copied text points at |
| section 2, items 3, 4, 5, 7, 9 | §4 |
| section 3.1–3.6 | §5 |
| Appendix A, items 1, 3, 4, 5, 6, 7 | §6 |
| section 5 (documentation, chores) | §7 |
| Appendix B | §8 |
| Appendix C; Appendix D items 1, 6, 8, 12 | §9 |
| Appendix E | §10 |

**Not copied**, because they belong to features 5–11 and nothing in 1–4 depends on them:
section 2 items 1, 2, 6, 8; the rest of section 4's feature 5, 7 and 9 bugs; section 5's
API-surface list; Appendix A items 2, 8, 9; Appendix C's dead-passage list (mount and context
material) and its three false design-doc statements; Appendix D items 2–5, 7, 9–11. Sections
3.4 and 3.5 are copied **whole** even though two of their items are feature 5/7 material,
because splitting them would break their internal references.

---

## 1. The four features


1. **Type hierarchy (celltypes)** — a *checksum* hierarchy, not a value hierarchy: subtype →
   supertype means any checksum valid as the subtype is valid, unchanged, as the supertype.
   "Deserializable as X" means the reference parser accepts it, not that it round-trips to the same
   checksum; one value may have several checksums, and identity stays with the checksum. Canonical
   null `b"null\n"`; null/true/false are checksum-level virtual values. Defined by the rule table in
   `seamless-core/seamless/checksum/conversion.py`. `str(null checksum) == "NULL"`; machine formats
   use `.hex()`.
   **Delivered.** Contract: `contracts/celltypes-and-conversion.md`.
2. **HashType** — on top of 1: a total, packed classification of a checksum, replacing BufferInfo
   (removed everywhere). Two purposes: detect impossible deserialization at checksum level, and
   answer expression capability (which path steps SEQ/MAP and what rank the root structure admits).
   One-sided error: never rejects valid work, may answer "maybe" (`None`). Stored words only
   tighten; stored locally and in the seamless-database `hash_type` table. Query:
   `conversion_feasible` → True/False/None.
   **Delivered.** The false-rejection family (`X → checksum`, the `int`/`float` targets, the
   never-disproved chains, `deserializable_as("bool")`, the broken `SEMANTIC` flag) was fixed by
   seamless-core `0d3ccfb` "address HashType limitations" and `827bd5b`.
   Contract: `contracts/hashtype.md`.
3. **Conversion engine** — on top of 1, using 2: ported from legacy Seamless. Defining feature: no
   value-level work unless necessary, exploiting the type hierarchy and HashType entries
   (checksum → buffer → value). Scalars are readings of JSON-compatible buffers (int↔float and
   scalar→str keep the checksum; an int reading of `4.5` gives `4`). Buffer-level conversion results
   are cached as empty-path Expressions, so 3 and 4 are entangled.
   **Delivered.** Contract: `contracts/celltypes-and-conversion.md`.
4. **Expressions** — on top of 3, using 2: the structural, immutable counterpart of Transformation —
   a closed, pure codebook (get-attr, get-item, slice, celltype conversion) with no execution
   environment. Expressions and Transformations share one lazy, content-addressed DAG. Over a deep
   checksum, a path selects a sub-checksum without materializing the parent. Identity =
   `(input_checksum, path, input_celltype, celltype)`, plus the reverse index that fingertipping
   walks. Evaluated where the data is (`execution="auto"`). seamless-database protocol 2.2.
   **Delivered (gaps).** Cancellation gaps: section 4. Validators: deferred, reject-only semantics
   settled. Parts of the contract are ahead of the code; both pages say which.
   Contract: `contracts/expressions.md`, `contracts/deep-celltypes.md`.

Features 5 (Cells as deferred Expressions), 7 (transformer pins) and 10 (the reactive workflow
Context) build on these four; 8 (cancellation) and 9 (the checksum reference lifecycle) sit
beside them. Two of the non-feature scope items bear directly on 1–4:

*(Register §1, "Also in scope", verbatim.)*

**Also in scope** (not part of the dependency chain):

- **A. Transformation core** (RELEASE-NOTES v1.4): immutable definition vs mutable promise; dunders
  reclassified (`__meta__` / `__env__` out of identity, `__schema__` in for compiled — an intentional
  cache break); latch-on default vs `--strict` / `strict_dunder`; checksum-addressed cancellation
  API; `seamless-run-transformation` replay CLI; `.zst` / `.gz` checksumming fix. These sit below 4
  and 8.
- **B. Operational contract clarifications** (not features): remote execution requires a shared
  hashserver plus database; environment fingerprints come from manual probes (conda-cache refresh
  excepted);  caching masks nondeterminism; fingertipping is
  distinct from scratch (relevant to 4 and 5: the reverse index; `.value` never fingertips).

---

## 2. Repo footprint: which repos actually implement 1–4

Verdict per feature:

| Feature | Footprint |
|---|---|
| 1. Type hierarchy (celltypes) | seamless-core only |
| 2. HashType | seamless-core + seamless-database + seamless-remote |
| 3. Conversion engine | seamless-core only |
| 4. Expressions | seamless-core + seamless-database + seamless-remote + seamless-jobserver + seamless-transformer + seamless-dask |

### What is genuinely core-only

The semantics of all four live in `seamless-core/seamless/checksum/`: the celltype table and
hierarchy (`celltypes.py`, `conversion.py`, `convert.py`, `canonical.py`, `null.py`,
`virtual.py`), HashType classification and its queries (`hash_type.py`,
`hash_type_validation.py`), and the Expression class with local evaluation and the in-process
result cache (`expression.py`). Add `Buffer._map_celltype`
(`seamless-core/seamless/buffer_class.py:61-68`), which is where the deep celltypes are mapped
onto `plain`.

If the question means "the rule table and the algorithms", then yes: that is core.

### The non-core implementation sites

Not callers — implementation that features 2 and 4 are defined in terms of.

| Repo | What it implements | Feature |
|---|---|---|
| **seamless-database** | the `HashType` model **and the tighten-only conflict rule**, enforced server-side by importing core's `_hash_type_implies` / `unpack` (`database_models.py:61-85`); the `Expression` model (`database_models.py:115`); the `hash_type`, `expression` and `rev_expression` request types (`database.py:285-293`, `:525-527`, `:627-664`) — that is the Expression result cache **and the reverse index that fingertipping walks**, which feature 4's own description names as part of its identity; `_valid_hash_type_word` → core `HashType.is_valid_word` (`database.py:57-64`) | 2, 4 |
| **seamless-remote** | the wire half: `get/set_hash_type`, `get/set_expression_result`, `get_rev_expressions` (`database_client.py:157`, `:206`, `:245`, `:435`, `:469`; aggregated in `database_remote.py:178-301`), `jobserver_remote.run_expression` (`:148`), `daskserver_remote.has_daskserver` / `run_expression` (`:177-184`) | 2, 4 |
| **seamless-jobserver** | the `/run-expression` endpoint (`jobserver.py:251`, `:774-796`) and the expression-evaluation status counters (`:208-211`, `:330-348`) | 4 |
| **seamless-transformer** | `dispatch_expression` (`worker.py:2396-2438`), the backend dispatcher that core's remote path terminates at (`daskserver_remote` imports it); and `unpack_deep_structure` / `pack_deep_structure` (`transformation_utils.py:196`, `:219`), which the deep-celltype enforcement plan (§4, item 3) names as one of the **two layers that must change together** for the deep contract | 4 |
| **seamless-dask** | the actual remote evaluation: `_expression_task`, `_expression_checksum_task`, `get_expression_future` (`client.py:834`, `:884`, `:1357`) and `_expression_input_future` (`transformation_mixin.py:59-90`) | 4 |

### Core is not self-contained either

`seamless-core/seamless/checksum/expression.py` imports `seamless_remote` at lines 265, 296,
318, 394 and 401, and `hash_type.py` does the same at `:347`. "Evaluated where the data is" and
the database-backed HashType/Expression caches are cross-repo by construction. The feature list
in §1 already says as much: feature 2 is "stored locally and in the seamless-database
`hash_type` table", feature 4 is "evaluated where the data is (`execution="auto"`).
seamless-database protocol 2.2."

### What merely consumes 1–4

These are features 5, 7 and 10 standing on 1–4, not part of them:

- `seamless-workflow/seamless_workflow/context.py` builds Expressions (`:1416-1439`) and
  HashType-validates checksum writes (`:1357`); likewise `runtime_api.py:84-87` and
  `builder_state.py:343-351`;
- the transformer's `pin_class.py:68`, `:112` and `pretransformation.py` — pin celltype
  conversion, which is feature 7;
- the `validate_deserializable_as` calls in `seamless-dask/seamless_dask/client.py:983`,
  `transformation_mixin.py:736` and `seamless-transformer/.../transformation_class.py:1442`.

### Repos with no involvement at all

`hashserver`, `seamless-share`, `seamless-signature`, `seamless-config` and
`remote-http-launcher`. The launcher's only "expression" hit is f-string templating
(`remote_http_launcher.py:1421`), unrelated.

### Where the footprint is about to widen

Three items copied below add repos to features 2 and 4 the moment they are implemented:

- **§4, item 3** (deep-celltype enforcement) makes seamless-transformer's pin unpacking part of
  the Expression contract, under one shared validator;
- **§4, item 9** (the 2026-09-21 ruling set) spans seamless-core, seamless-workflow and
  seamless-database, and changes the graph format;
- **§6, item 7** (path storage) puts a `plain`-serialized path, a checksum indirection, a
  refholder claim and a protocol bump inside seamless-database.

### Consequences for the register

The split matches the open work already recorded there: Appendix A, item 7 closes path storage
as "a seamless-database matter" (§6 below), and section 2, item 3 requires the Expression layer
(core) and pin unpacking (seamless-transformer) to change together under one validator (§4
below).

If the register should state this itself, the candidates are: change section 4's headings from
"(seamless-core)" to name the repo per bug; add a repo-footprint line to each feature in section
1; or link this page from section 1 and leave the headings alone.

---

## 3. Known bugs in features 1–4

*(Register §4, verbatim. None of these is scheduled. All are documented as current behaviour in
the contract docs, which is why they are not blocking anything.)*

### Features 1–3 — celltypes, conversion, HashType (seamless-core)

The false-rejection family is **fixed** (`0d3ccfb`, `827bd5b`). What is left:

1. **`checksum → X` is not validated.** Converting *from* celltype `checksum` returns the referenced
   checksum without checking it against the target celltype X.
2. **`true` / `false` / `null` are classified as `JSON_STRING`.** Path validation therefore treats them
   as sequences. Too permissive, never rejects valid work. Deliberately not fixed: new `JSON_BOOL` /
   `JSON_NULL` kinds would only restore rejections on tiny buffers, and stored `JSON_STRING` words
   would contradict the new words (409 from the database), so they would need a migration.
3. **The `str` spelling of booleans is not symmetric.** Reading the `true` buffer as `str` gives
   `"True"`, but serializing `True` as `str` writes `true\n`.
4. **Large integers lose precision.** orjson turns integers beyond 64 bits into floats, so `int` and
   `plain` readings lose precision.
5. **`bytes` reading returns inconsistent types.** A non-null reading as `bytes` returns a `Buffer`
   object; the null reading returns `b""`.
6. **The HashType "untested" kinds have no producer.** Keep them: they have a natural future producer.
   `from_buffer` runs a full `orjson.loads` on every UTF-8 buffer each time a checksum is computed — a
   71 MB JSON array measured 0.40 s to classify against 0.02 s for sha256, with ~286 MB extra peak
   memory. A size cap that emits `UTF8_UNTESTED` for large buffers is what these kinds are for.
   (The `SEMANTIC` flag, the other half of this item, **was** retired: `from_buffer` no longer takes
   `semantic=` and `is_valid_word` now rejects the bit.)
7. **Stale docstring** in `seamless-core/seamless/checksum/conversion.py:6` — "Paths and deep hash
   patterns remain Expression-level work". Deep celltypes are distinct celltypes serialized and parsed
   as `plain` (`Buffer._map_celltype`), not legacy hash patterns.
8. **`seamless-core/type_bits_design.md` is out of date.** §13 describes HashType database tightening
   as pending; it is implemented and tested. §8.3 says "cheap peek, never `json.loads`"; `from_buffer`
   runs a full `orjson.loads`.

### Feature 4 — Expressions (seamless-core)

1. **`Expression.cancel()` is a no-op for local in-flight evaluations.** `evaluate_expression_async`
   registers members under a 7-tuple key
   `("local", checksum, path, input_celltype, celltype, validator, validator_language)`, while
   `cancel_expression` looks up the 4-tuple `_cache_key`
   `(checksum, path, input_celltype, celltype)`. Confirmed by test: `cancel()` returns `False` and the
   evaluation keeps running. The minimum fix is to align the two keys; section 2, item 4 removes the
   class of bug altogether.
2. **Dask-dispatched Expressions cannot be interrupted mid-flight.** `dispatch_expression`
   (`seamless-transformer/seamless_transformer/worker.py`) awaits `asyncio.to_thread(thin.result)` and
   never cancels the Dask future. Worse than the lost interrupt: cancelling the awaiting task does not
   free the thread, which stays blocked until the remote side finishes, so a burst of superseded
   Expressions could starve the default executor — the failure family of the jupyter-sync hang.
   Separate question worth asking: should Expressions go through Dask at all? A scheduler round trip
   costs far more than the evaluation, and queueing behind Transformations is worse.
3. **Fingertip chains run in the wrong place.** The reverse-index walk in
   `seamless-core/seamless/checksum/checksum_class.py` re-evaluates through
   `evaluate_expression_async` *locally, in the requesting process*, contradicting "evaluated where the
   data is" — and it does so precisely in the case whose cost is unbounded, since the chain may contain
   Transformations. This is listed here as a defect **and** in Appendix A, item 4, because the fix
   direction has never been ruled.
   **Ruled 2026-09-21 (Appendix A, item 4; Appendix E): local evaluation is correct**, so this is not a
   placement defect after all. What survives as a defect is the *publication*: the same branch writes the
   recovered buffer back to the hashserver (Appendix E, §E.4, item 1).

**Not a bug, listed to stop it being refiled as one:** there is no hard cancel for Expressions. That is
a ruled non-feature — the only leaf a hard cancel could kill is a shared fetch, so it would merely make
the other waiters fail and re-fetch. The *naming* fix is already contract
(`contracts/expressions.md`, "API": `Expression.softcancel()` is the only verb, `Expression.cancel` is
retired and raises, and the module-level `cancel_expression` alias is dropped). The code lags: today
`Expression.cancel()` exists and is soft, `softcancel()` does not exist, and `cancel_expression` is
still an alias.

Note on the two headings above: "(seamless-core)" is where these bugs sit, not where the
features live — and feature 4's bug 2 is itself in seamless-transformer. See §2.

### Added 2026-09-21, not in the register yet

*(Not part of the verbatim copies above; copy back into the register. This one belongs in the
**features 1–3** list, as its item 9 — it is a celltype-layer anomaly, not an Expression defect.)*

9. **A deep dummy read is unvalidated, and `.buffer` contradicts `.value`.** On a `Cell("deepcell")` /
   `"deepfolder"` / `"folder"` holding an index, with **no path and no retyping**, `.value` returns the
   `{key: hex}` index — `Buffer.get_value` calls `Buffer._map_celltype` first, which maps the deep
   celltypes to `plain`, and a flat index parses fine as `plain`. **That read is correct and is
   contract**: requesting the value of a deep checksum yields its index, at every layer (ruled
   2026-09-21). The defects are around it: the read succeeds only because the dummy-Expression fast path
   **skips validation altogether**, and `.buffer` on the same Cell **raises** `HashTypeValidationError`,
   because `CellBase.buffer` validates against the *un-mapped* celltype (§9, item 12, describes the same
   split). Meanwhile every typed route — a path step, a retype — raises, which is why indexing that dict
   by hand is currently also the **only** way to reach a deep child's checksum.
   **Ruled 2026-09-21: fix the anomaly in the code first, and remove the interim passages from the
   contract pages afterwards** — the order matters, because deleting them while the typed routes still
   raise would leave agents concluding that Seamless cannot reach a deep child at all. The code half
   belongs with §4, item 3 (deep-celltype enforcement), which makes the one-step path work and makes
   `.buffer` legal; the documentation half is a chore in §7. Note what is *not* stripped: `.value`
   returning the index stays, since it is the value rule.

10. **A direct-called `deepcell` result is materialized behind the caller's back.**
    `DirectCompiledTransformer.__call__` (`seamless-transformer/seamless_transformer/compiled_transformer.py:771-778`)
    returns `unpack_deep_structure(value, "deepcell")` for a `deepcell` result, and
    `unpack_deep_structure` resolves **every** child (`transformation_utils.py:194-214`). So a property
    read costs an *all children* fan-out, the opposite of the input side, where a `deepcell` pin hands
    over unresolved `Checksum` objects. A `folder` result already returns the raw index — correct, but
    by accident. **Ruled 2026-09-21: a deep result is an index**, reading it resolves nothing, and the
    transformer holds no claim on the leaves; `unpack_deep_structure` was wrongly ported from legacy
    Seamless and is to be replaced. The branch goes with §4, item 3, which replaces that function
    anyway — one change, not two. Stated in `contracts/deep-celltypes.md` §*The output side* and
    `contracts/compiled-transformers.md` §*Result types*.

### Two neighbouring bugs this page's copied text points at

*(Register §4, feature 5, bug 5 — referenced by §4, item 7; verbatim.)*

5. **Standalone projection writes are silently lost.** `cell.b` returns a *fresh derived* Cell
   (`Cell.item` → `_derive`), and `SubCell` (`cell_class.py:688-750`) overrides only
   `__eq__`/`__bool__`/`__len__`/`__iter__`, inheriting the setters unchanged. So standalone
   `cell.b.checksum = cs`, `cell.b.value = v` and `cell.b.buffer = buf` mutate a throwaway handle and
   the write is lost with no error. `cell.b = v` and `cell["b"] = v` are blocked
   (`cell_class.py:633` `__setattr__` / `:651` `__setitem__`); these three are not. **They should
   raise.** Note the tension to resolve when fixing it: `SubCell`'s own docstring declares assignment a
   *handle* operation, deliberately left untouched alongside `.value`, `.checksum` and `.state`. That
   is right for a **bound** projection, where assignment reaches the Context; standalone there is no
   controller to reach, which is exactly why `cell.b = v` and `cell["b"] = v` already raise.
   Related but *not* a bug: a standalone Cell constructed with `path=` has `.checksum = cs` set the
   pre-path input, so the round-trip genuinely fails. That one is coherent — the path is recipe, not
   value — and is documented as such.

*(Register §4, feature 7, bug 3 — the Pin side of the same dummy-Expression fast path;
verbatim.)*

3. **A Pin's `.checksum` getter has no dummy-Expression fast path.** Unlike `CellBase.checksum`
   (`cell_class.py:118-123`), `StandalonePinBackend.checksum` (`pin_class.py:86-123`) always calls
   `Expression(...).compute()`, so a `RunningLoopRefusal` is wrongly recorded as `.exception` on a Pin,
   where `contracts/cells.md` says it must not be.

---

## 4. Coordinated change plans that touch 1–4

*(Register §2, verbatim, items 3, 4, 5, 7 and 9. Each spans more than one repo or more than one
layer, so none of them is a local fix. Items 1, 2, 6 and 8 of that section are feature 7/10/11
work and are not copied.)*

### 3. Deep-celltype enforcement

**No plan document yet.**

`contracts/deep-celltypes.md` and `contracts/expressions.md` state the full deep contract — the
zero-path conversion table, the exactly-one-string-item path step, and what each deep celltype yields
— and both say, in as many words, that **none of it is enforced by the code yet**. Two layers must
change together, or they will disagree about what a deep value is:

- the **Expression layer** must reject the conversions and path shapes outside the table;
- **pin unpacking** (`unpack_deep_structure` / `pack_deep_structure`,
  `seamless-transformer/seamless_transformer/transformation_utils.py`) must become flat-dict-only.
  The nesting those functions recurse through is legacy Seamless generality that never had a producer
  or a consumer.

They must share **one validator**. Related: a `folder` value serialized as `mixed` must present each
child as a 1-D `S1` array, never as a 0-d `S<N>` scalar (NumPy's `S` dtype strips trailing NULs, so
the 0-d form does not round-trip `b""` or `b"ab\x00\x00"`).

### 4. Remote materialization: a waiting set with latch-on and delayed cancel

**Design sketch: Appendix B. No plan document, and nothing in it is verified against code.**

The conclusion of Appendix B is that the only cancellable work is remote *materialization* — which is
not Expression-specific. The machinery is a waiting set per in-flight materialization, keyed by
checksum, held in the buffer layer; latch-on for a second requester; softcancel = deregister, with the
fetch aborted only when the set empties and only after a linger of a few seconds; no hard cancel;
failure never sticky. `Expression.cancel()` becomes "leave the set", which removes the key-mismatch
bug (section 4, feature 4, bug 1) by removing the expression-level set altogether. The site must hold a
reference-lifecycle claim for the duration of the linger and release it when the timer fires — the one
place the waiting set meets feature 9. The questions that used to gate this (Appendix A, items 3–5) are
all decided — see §6 — so what remains before planning is **evidence, not a ruling**: whether an
abandoned Expression materialization keeps holding a jobserver worker slot (item 5's (a)) is the one
answer that has to be read out of the code first, because it decides how much the mechanism is worth.

Note the ordering constraint: landing the linger will break the third assertion of
`seamless-core/tests/test_expression_remote_evaluation.py` (section 3).

### 5. `.exception` as a string, everywhere

**No plan document. Spans seamless-core and seamless-workflow.**

Ruled: `Cell.exception`, `Pin.exception` and `Transformation.exception` all hold a **string**, because
the convention follows the *remote boundary* — Expressions and Transformations can execute remotely
and exception objects do not transfer well. Purely local error surfaces are exempt, which is why
`ctx.a.mount.error` and `status['sense_error']` hold `MountError` / `ConflictError` objects.

The contract docs already state the string convention. The code does not: `error_envelope.execution_error`
returns an exception *object* with its traceback stripped, `__cause__`/`__context__` cleared and a
`failure_id` attached, and both `CellBase.exception` and the bound `node.exception` hand that object
out. Two sites block the change — standalone `.value` and `run()` both do
`raise self._standalone_exception`, which needs an object. Consequence to keep: a `CacheMissError`'s
checksum then reaches the Cell as prose only, so there is no machine-readable arm on the Cell.

**The sweep lands in four contract pages at once.** `contracts/cells.md`, `contracts/pins.md` and
`contracts/node-state-lifecycle.md` each list the string convention as *contract ahead of code*, while
`contracts/compiled-pins.md` §9 decision D5 already states it as **settled contract** ("an `.exception`
attribute is a **string**, not an `Exception` instance") and builds on it. Whoever does the code change
must reconcile all four in the same commit, and fix the two tests of section 3.4, items 3 and 4, which
are written against the object convention.

### 7. `.set_checksum` and the dummy-Expression fast path

**Discussed in `seamless/compiled-transformer-celltypes-design-plan.md`.**

Cells and Pins are containers of Expressions. `Cell.set_checksum` / `Pin.set_checksum` do **not** set
the `.checksum` attribute: they are the Checksum variant of the three `.set*` methods, which set the
*input* checksum (from Checksum, Buffer or value). That is instantaneous, and `.checksum` is expected
to be `None` afterwards. Two exceptions: when the underlying Expression is a **dummy**
(`input_celltype` and `celltype` identical, no path component), `.checksum` must return the argument
of `.set_checksum` immediately; and when the Cell is **unbound**, `.checksum` is a computed property
that does a synchronous evaluation of the underlying Expression.

Verified present in `seamless-core/seamless/cell_class.py` (dummy fast path at lines 118–123, the
unbound sync `Expression(...).compute()` at 129–136) and stated in `contracts/cells.md` and
`contracts/compiled-pins.md` §2. **What remains is the Pin side and the projection case**: see
section 4, feature 5, bug 5.

### 9. Cells, Expressions and wiring: the 2026-09-21 ruling set

**No plan document. Spans seamless-core, seamless-workflow and seamless-database. Every item below is
already written into the contract pages and marked *contract ahead of code*; none of it is implemented,
and none of it has a test.**

The author ruled a connected set of changes on 2026-09-20/21. They lean on each other, so they are one
change, not nine:

| Rule | Page |
|---|---|
| **Project-then-convert**, and an Expression never converts its input (at most one conversion, always last) | `expressions.md` §Application order |
| **Syntax order = application order**: `Cell.as_celltype` mid-chain closes the Expression and re-bases the next step | `cells.md` §Projections |
| **The wiring rule**: an edge may carry a path *or* a conversion, never both; redefining an input needs a pathless source or a celltype match | `cells.md` §Connecting |
| **`miswired`**, a seventh node state, plus `blocked-by-miswiring`; precedence `miswired > unwired > blocked-by-miswiring > blocked-by-unwired > blocked-by-error > waiting` | `node-state-lifecycle.md`, `workflow-context.md` |
| `block_reason` becomes a **dict from input to reason** wherever a node has several inputs — keyed by edge for a cell (`"<root>"` for the root edge), by pin name for a transformer; every responsible input appears in every state, and the winning category is the maximum of the values, not a separate field. Retires `Node.block_pins` and `tf.result.block_reason`'s category role | `node-state-lifecycle.md`, `pins.md` |
| **Pins follow the cell rules**; a miswired pin makes the transformer `miswired`, not `blocked` | `pins.md` |
| **Fusion**, always, over four edge pairs; a deep step is a barrier | `expressions.md` §Fusion |
| **Elidable / elided** cells; anonymous nodes; the graph **symbol table** `symbol → (source, celltype, path)` | `cells.md` |
| `path` removed from `Cell.__init__`; projection and `as_celltype` return **children** edged to the parent | `cells.md` §Projections |
| **`SubCell` retired**; its four dunders move to `CellBase`, covering Pins too | `cells.md` |
| **Deep sources are carved out** — governed by `deep-celltypes.md`'s table, not by the wiring rule | `cells.md`, `expressions.md` |

Code touchpoints known so far:

- `seamless_workflow/graph.py`: `NodeState` and `BlockReason` are `Literal` aliases and need the two new
  members; `Node.block_reason` is typed as the scalar and becomes the dict form for a cell; `Edge` and the
  graph gain the symbol table. **This is a graph format change** — the format is at `0.4`.
- `seamless_workflow/ingress.py:37-50`: `_prepare_assignment` refuses an unbound Cell whose `_input_ref` is
  an `Expression`, and `PreparedCell` carries no path. Anonymous cells cannot be bound at all today.
- `seamless_workflow/builder_state.py`: `BoundCellBackend.derive` detaches by building the root as a source
  and overwriting only the output celltype, which is why `as_celltype` before a projection currently has no
  effect on what the path sees.
- `seamless-core/seamless/cell_class.py`: `_derive` copies the parent's own input rather than pointing at the
  parent (so `cell[3].source` reports the grandparent); `SubCell` at `:689`; `item`/`slice` at `:545`/`:551`;
  `SubCell` is in `seamless.__all__` and must be retired, not deleted.
- **Raising from `CellBase.__eq__` breaks membership tests** (`x in [cells]`, dict keys, sets). An internal
  identity helper has to land first; this is the likeliest thing to break during the change.

Ordering constraints: the symbol table and the `miswired` state are both graph-format changes and should land
together. Fusion must land **with** the ordering rule, not after it — fusion is what makes the anonymous and
named spellings agree, which is the whole justification for the ordering rule at the Cell level.

Two rulings landed after this item was first written, and belong to it:

- **Appendix A, item 6 is decided: (b).** `input_celltype` uses the *same resolution* as `.source` — the
  one-level edge targeting the path if there is one, otherwise the nearest enclosing source — and reports that
  endpoint's celltype. One lookup, two members, so they cannot drift apart again; read projections are
  unaffected, because both fall back to the root. `BoundCellBackend.input_celltype` still drops `local_path`
  (`builder_state.py:64-69`). Stated in `cells.md` §"The input", together with the fact that a projection's own
  `celltype` is its parent's — which the wiring rule compares a source against at a one-level target, and which
  the page had never stated (Appendix D.1, item 4).
- **Path storage is a seamless-database matter** (Appendix A, item 7, closed): the contract says only that
  there is no limit on path length. Nothing in this item depends on it, but the two land in the same area.

Nothing in this set is still open.

---

## 5. Test set gaps

*(Register §3, verbatim. The register's own preamble to this section:)*

> **Not done: the per-feature comparison of each contract doc against its tests.** That pass — read
> each contract doc's rules, find the test that pins each one, and report the rules with no test and
> the tests that assert something the contract does not say — was planned for 2026-09-20 and did not
> run (the subagents that were to do it hit an account spend limit). Everything below is what is
> known without it. **This section is the place for that pass's output when it runs.**

### 3.1 The harness: one pytest process per test file

Combining Seamless test files into one pytest run produces spurious failures — process-global cache
and refholder state carries between files, worker processes and module-level caches in seamless-core
are per-process, and a genuine failure in one file manufactures audit failures in the next.
`conftest.py` resets per-test state, which is necessary but not sufficient.

`tests/run-tests.sh` implements the one-file-one-process loop in **seamless-workflow**,
**seamless-transformer**, **seamless-dask** and **seamless-config**. It does **not** exist in
**seamless-core**, **seamless-remote**, **seamless-database**, **seamless-share**, **hashserver** or
**seamless-signature**. seamless-core is the largest of those (41 test files) and the one whose tests
carry the most global state, so it is the gap that matters.

### 3.2 Test suite status

**Current status, measured 2026-09-20** — one pytest process per file, `seamless1` environment,
**no Seamless services running** (no hashserver, jobserver or daskserver):

| Repo | Files | Passed | Failed | Collection errors |
|---|---|---|---|---|
| `seamless-core` | 38 | 2442 | 2 | 0 |
| `seamless-workflow` | 52 | 572 | 2 | 0 |
| `seamless-transformer` | 69 | 358 | 2 | 0 |
| `seamless-database` | 3 | 28 | 0 | 0 |
| `seamless-remote` | 5 | 26 | 0 | 0 |
| **total** | **167** | **3426** | **6** | **0** |

**Additional suites, measured 2026-09-21** — one pytest process per file, `seamless1`
environment:

| Repo | Files | Passed | Failed | Collection errors |
|---|---:|---:|---:|---:|
| `hashserver` | 14 | 13 | 10 | 0 |
| `remote-http-launcher` | 5 | 82 | 0 | 0 |
| `seamless-config` | 6 | 46 | 0 | 0 |
| `seamless-signature` | 2 | 31 | 0 | 0 |
| `seamless-share` | 9 | 24 | 0 | 0 |
| `seamless-jobserver` | 2 | 16 | 0 | 0 |
| `seamless-dask` | 14 | 48 | 2 | 0 |

*(The per-repo failure lists for `hashserver`, `remote-http-launcher`, `seamless-config`,
`seamless-signature` and `seamless-share` are in the register. The two that bear on features
1–4:)*

`seamless-jobserver` failures: none.

`seamless-dask` failures:

- `tests/test_expression_cancellation.py::test_cancelled_expression_dispatch_retains_default_executor_thread`
- `tests/test_nested_transformations_multi.py::test_nested_transformations_multi`

*(The six remaining failures, in the register's two groups:)*

*Needs a service that was not running* (re-run these against a live hashserver before treating them as
defects):

- `seamless-core::tests/test_cell_input_ref.py::test_positional_celltype_with_keyword_reference` —
  `CacheMissError: 084c799c…`;
- `seamless-transformer::tests/test_fingertip.py::test_fingertip_recovers_expression_over_transformation_result`
  — `ClientConnectionError: Error 500`, plus a `RuntimeError: no running event loop` on the way out;
- `seamless-transformer::tests/test_run_transformation_cli.py::test_run_transformation_cli_replays_delayed_python_transformation_checksum`.

*Genuine, and each one is a finding in its own right:*

- `seamless-core::tests/test_expression_hashtype_cases.py::test_hashtype_witness_corpus_has_expected_shape`
  — `assert len(WITNESSES) >= 65` fails with 61. **This is a test-side error, not a code defect**: the
  witness corpus shrank when the HashType limitations were addressed (the false-rejection witnesses and
  the `SEMANTIC` ones stopped being witnesses), and the floor was never lowered. Either lower it or say
  in the test why 65 is the number.
- `seamless-workflow::tests/test_literal_retention.py::test_unavailable_literal_is_captured_as_transformer_exception`
  — asserts `isinstance(tf.exception, RuntimeError)` and gets a `CacheMissError`. **This test sits
  directly on the `.exception` convention** (section 2, item 5): it type-checks an exception *object*
  on a surface the contract says will hold a string. It must be rewritten in the same change that
  makes `.exception` a string, or it will have to be rewritten twice.
- `seamless-workflow::tests/correctness/test_correctness_compiled.py::test_original_compiled_alias_exposes_bound_pins`
  — `WorkflowExecutionError` out of `transformation_class.py:738`. Uncharacterized; it is in the
  compiled-pin area that section 2, item 1 rewrites.

TODO: add a `run-tests.sh` to the repos that lack one.


### 3.3 The characterization tests added on 2026-09-20, and what they cost

Eight test files were added or extended on 2026-09-20, closing almost every coverage gap this file
used to list. They are good tests and they should stay. But **five of them are red by construction and
carry no `xfail` marker**, so as things stand they turn a nearly-green suite red and nobody can tell a
new regression from a known gap:

| File | Status | What it pins |
|---|---|---|
| `seamless-core/tests/test_expression_local_cancellation.py` | 1 passed | the local `cancel()` no-op, as *current behaviour* |
| `seamless-core/tests/test_cell_running_loop_refusal.py` | 1 passed | a running-loop refusal reads as `None` with no exception recorded |
| `seamless-workflow/tests/test_late_expression_materialization.py` | 1 passed | Appendix B.6(c): a superseded Expression result does not reach its node |
| `seamless-core/tests/test_materialization_waiter_contract.py` | **2 failed**, 1 passed | Appendix B.6 (a), (b), (d) — the waiting set does not exist, so this is contract ahead of code |
| `seamless-transformer/tests/test_compiled_e2e.py` (extended) | **4 failed**, 19 passed | null into a required compiled input must name the pin and its declared celltype |
| `seamless-workflow/tests/test_cell_joins.py` | **5 failed**, 1 passed | the six join behaviours — but see 3.4, the five failures are test errors |
| `seamless-workflow/tests/test_cell_inspection_contracts.py` | **1 failed**, 1 passed | the join observation log, and a bound projection failure at derivation time |
| `seamless-dask/tests/test_expression_cancellation.py` | not run | the Dask thread-retention gap; needs a live cluster |

**Decided (Appendix A, item 1): a known-gap test is marked `xfail(strict=False)`, everywhere.** It
flips to `xpass` the moment the gap closes, so it cannot be forgotten, and the default run stays green
without hiding anything. Two of these files — `test_materialization_waiter_contract.py` and the
compiled-null parametrization — are *deliberately* ahead of the code and are exactly that category.
**Apply it retroactively to `seamless-transformer/tests/cancellation/`**, whose `README.md` already
claims the convention while the directory carries no markers at all (3.4, item 1) — the inconsistency
that caused a contract page to cite a suite proving nothing. The convention is written down here; it is
not yet applied anywhere.

Note that the sweep of 3.2 predates these files, so its totals do not include them.

### 3.4 Errors in the test set

Found on 2026-09-20 by comparing the contract docs against the tests. These are tests that are
*wrong*, not merely thin. **None has been fixed** — this section is a report.

1. **`seamless-transformer/tests/cancellation/` does not prove what `cancellation.md` cites it for.**
   Its `README.md` states that the two known cross-process gaps "are recorded as `xfail(strict=False)`
   (they flip to `xpass` once implemented — they are not silenced)". There is **no**
   `@pytest.mark.xfail` anywhere in that directory, and no dynamic marking. Worse, both tests assert
   the **fixed** behaviour outright:
   - `test_jobserver_both_softcancel_leaf_kill` asserts
     `count(markers, "finished") == 0, "leaf kill failed: run completed after all left"` — while the
     README's own findings say the jobserver runs the orphaned job to completion;
   - `test_dask_first_runner_softcancel_latcher_survives` asserts the latcher receives the value —
     while the README says the latcher gets `TransformationError("Transformation was canceled")`.

   Both files carry `pytestmark = pytest.mark.remote` and need a live cluster, so the two tests are
   presumably never run. Either the markers were dropped in an edit, or the 2026-06-15 run recorded in
   the README was done against a locally patched copy. Until this is resolved, **the suite is not
   evidence for anything it claims about softcancel across processes**, and `cancellation.md` has been
   reworded accordingly.

2. **Five of the six new join tests use a spelling the contract forbids.**
   `seamless-workflow/tests/test_cell_joins.py` lines 40, 61, 75, 103 and 120 all write
   `ctx.join.value = <handle>`. `value` is **Cell API**, so that is the `.value` setter, which takes a
   value and correctly raises
   `TypeError: A Cell is not a value: connect it by assignment, or with Cell(source=...)`. This is the
   exact API-name-collision hazard the docs describe — and the reason attribute projection is loud.
   The item form is the correct spelling and produces precisely what the tests assert: *verified*,
   `ctx.join["value"] = ctx.source` then `ctx.compute()` gives `{'value': 'first'}`. Only
   `test_join_assembles_root_and_subpath_values_at_its_declared_celltype`, which uses non-colliding
   keys (`left`, `right`), passes. Fix the spelling, and all six should go green; they are the six
   behaviours the uncommitted 2026-09-17 evidence tests established.

3. **`test_cell_inspection_contracts.py::test_bound_exception_reports_projection_failure_during_derivation`
   compares two exception objects with `==`.** It fails with
   `assert ExpressionEvaluationError("Cannot apply expression path step 'missing'") == ExpressionEvaluationError("Cannot apply expression path step 'missing'")`
   — identical messages, unequal objects, because Python exceptions do not implement `__eq__`. The
   test is written for the world in which `.exception` is a **string**, and it will pass unchanged once
   section 2, item 5 lands. Until then it is red for the right reason and the wrong one at once: leave
   it, but mark it, and fix it in that change.

4. **`seamless-workflow/tests/test_literal_retention.py::test_unavailable_literal_is_captured_as_transformer_exception`
   type-checks an exception object.** It asserts `isinstance(exception, RuntimeError)` and gets a
   `CacheMissError`. Same root cause as item 3: it pins a convention the contract has already replaced.
   It must be rewritten in the `.exception`-as-a-string change, or it gets rewritten twice.

5. **`seamless-core/tests/test_expression_hashtype_cases.py::test_hashtype_witness_corpus_has_expected_shape`
   has a floor with no stated reason.** `assert len(WITNESSES) >= 65` now fails with 61, because the
   corpus legitimately shrank when the HashType false-rejection family was fixed. A magic threshold
   that breaks when the code is *improved* is a defect in the test: either derive the number or drop
   the assertion.

6. **`seamless-core/tests/test_expression_remote_evaluation.py` pins a current absence as contract.**
   It asserts that the last member leaving aborts the jobserver request *synchronously*. True today
   only because no linger exists, and forbidden by the settled contract, under which a softcancel never
   means the work stopped and the abort follows the linger. The test's intent survives; it needs a
   tolerance for the linger, added in the same change that lands section 2, item 4.


### 3.5 Coverage still missing

Most of what this section used to list was closed on 2026-09-20 (see 3.3). What is left:

- **The optional-pin identity rule is verified for two celltypes, not "any".**
  `seamless-transformer/tests/test_transformation_checksum.py` asserts real checksum equality and
  inequality for all four cases of the rule — absent == connected-null, non-null participates,
  required-null differs, and the same for `binary` — which is the right shape. But the contract says
  the rule holds for **any** celltype, and the evidence covers `plain` and `binary`. Since absence is
  decided by comparing checksums and never by deserializing, the mechanism is celltype-independent and
  two is defensible; a parametrization over the celltype list would make the claim self-evident.
- **The 3×2 write matrix is not walked.** The contract says all six writes exist at a projection, and
  four of them raise `TypeError: _edit() got an unexpected keyword argument 'input_celltype'` today
  (section 4, feature 5, bug 1). A test that walked the matrix would have caught that, and no test
  does.
- **The 2026-09-21 ruling set has no tests at all.** Section 2, item 9 — the ordering rule, the wiring
  invariant, `miswired`, fusion, anonymous nodes and the symbol table. Every rule there is contract ahead of
  code, so the tests land with the implementation; until then the doc-vs-test pass of 3.6 will report the
  whole set as uncovered, which is correct and should not be “fixed” by writing tests against today's code.
- **`seamless-dask` is unswept.** Its 33 recorded failures need a live Dask cluster to interpret, as
  does the new `test_expression_cancellation.py`. Separate exercise.

### 3.6 Still to do: the systematic doc-vs-test pass

Sections 3.4 and 3.5 come from a targeted pass over the highest-risk rules, not an exhaustive one. The
full exercise — walk every rule in all thirteen contract pages, name the test that pins it, and report
every rule with no test — was attempted on 2026-09-20 and did not complete. Features **1–3, 4, 6–7, 10
and 11** have had no systematic doc-vs-test comparison. This section is where that output belongs.

---

## 6. Design decisions — all six are closed

*(Register Appendix A, verbatim, items 1, 3, 4, 5, 6 and 7. Items 2, 8 and 9 are feature 7/8/6 work
and are not copied.)*

**Every item below now carries a decision**, and each is marked with where it landed. The question text
is kept because the reasoning is the record of *why*, and because other sections of this page cite these
items by number. The section's old preamble — "nothing here is stated as contract anywhere, and nothing
here should be" — no longer holds: items 3, 5, 6 and 7 are in the contract pages, item 1 is a test-suite
convention recorded in §5, and item 4 is in §10.

### 1. How is a known-gap test marked?

**Superseded in part (2026-09-20):** the question used to be whether the throwaway evidence tests for
Expression cancellation and cell-level joins should be written properly. They have been — eight files
went in that day (section 3.3) — so what is left is the question they raise. Five of those files are
**red by construction**: they state contract the code does not implement yet, and they carry no
`xfail` marker, so the suite cannot go green and a new regression is indistinguishable from a known
gap. Options: (a) `xfail(strict=False)` on every known-gap test, which flips to `xpass` the moment the
gap closes and so cannot be forgotten; (b) a dedicated marker (`@pytest.mark.gap`) deselected by
default, which keeps the default run green but hides the tests; (c) leave them failing as a standing
reminder. **Recommendation: (a)**, and apply it retroactively to
`seamless-transformer/tests/cancellation/`, whose README already *claims* this convention while the
code carries no markers at all (section 3.4, item 1). Whatever is chosen, write it down once — the
inconsistency is what caused a contract page to cite a suite that proves nothing.
**Decision**: (a).
**Closed** — recorded in §5, 3.3. This is a test-suite convention, not contract-doc material, and it is
**not applied in any repo yet**: the retroactive pass over `seamless-transformer/tests/cancellation/`
still has to happen.

### 3. Does "where the data is" include a locally mounted read-buffer directory?

`choose_expression_evaluation_location` treats locality as "in this process's memory" only, so a buffer
sitting in a local read-buffer directory counts as remote and is dispatched to a jobserver/daskserver,
although the client could read it off local disk for free. Options: (a) keep locality = process memory
(current code) and pay an unnecessary round trip; (b) extend locality to include local read-buffer
directories, checked before dispatch — which adds a filesystem probe to a placement decision that is
currently side-effect-free and fast, and needs a definition of "local read buffer directory" that
generalizes across deployments. **Recommendation: (b), gated behind an explicitly configured
read-buffer-directory path** rather than a generic filesystem scan, so placement stays a cheap
deterministic check.
**Decision**: (b).
**Closed** — `contracts/expressions.md` §*Placement*: a buffer in an explicitly configured read-buffer
directory counts as local, those directories are consulted **before** any hashserver query, and a hit
means local placement. Two things the decision had left open are settled with it: placement may make a
**cheap, deterministic filesystem check** against a configured path (the earlier "side-effect-free"
phrasing is deliberately relaxed, and an index-only membership test is not required), and the rule is
about the **input** buffer only. Result resolution needs no change and already behaves correctly:
`Checksum.resolution()` goes through `buffer_remote.get_buffer`, which queries every configured read
*folder* before any read *server* (`seamless-remote/seamless_remote/buffer_remote.py:171-186`) —
verified in code, 2026-09-21.

### 4. Where does a fingertip chain run — client, or the server that took the dispatch?

Today it runs locally in the requesting process (section 4, feature 4, bug 3). Options: (a) keep local
evaluation — simplest, but it moves potentially large recomputation onto a thin client, and it is a real
violation of the placement contract; (b) dispatch the chain to the jobserver/daskserver, matching the
contract, which needs a new server-side code path because a fingertip chain is not a single Expression,
with its own error-envelope and cancellation implications. **Recommendation: rule this explicitly and
soon.** The unbounded cost of a fingertip chain is the whole reason the Appendix B machinery is worth
building, so this is not a wording fix; it deserves the same priority as that work.

**CLOSED (2026-09-21): (a), local — and the question was the wrong one.** Remote evaluation cannot
deliver a buffer to the client except through the hashserver (the jobserver returns a checksum only), so
dispatching a fingertip necessarily re-adds the entry that scratch or eviction had excluded. Local is
therefore not a placement compromise but the only placement that respects the decision which made the
fingertip necessary. **Appendix E** carries the ruling, the reasoning an agent needs in order not to
re-derive the wrong model, and nine defects found while checking it — chief among them that expression
evaluation publishes its result buffer at all, so a fingertip re-adds what it recovers, locally, with no
dispatch involved.

### 5. Do remote materializations hold bounded resources while a waiter is abandoned?

A jobserver worker slot, a Dask worker, a default-executor thread. Head-of-line blocking is the main
resource argument for building cancellation at all. The Dask half is confirmed — `dispatch_expression`
blocks a default-executor thread until the remote side finishes, regardless of client-side cancellation
— but the jobserver-slot question is unconfirmed for Expression materializations, and it is recorded for
Transformations that "a jobserver cancel does not free the slot". Options: (a) read the jobserver
dispatch/cancel path and settle it before building the waiting set; (b) build the waiting set first and
measure later. **Recommendation: (a)** — it is cheap, and it materially changes how much the whole
mechanism is worth.

Two sub-questions that only matter once the answer is in:

- ~~**Is buffer resolution already deduplicated by checksum across consumers?**~~ **Answered (checked
  in code, 2026-09-20): no.** `Checksum.resolution()` (`seamless-core/seamless/checksum_class.py:214`)
  goes cache → `buffer_remote.get_buffer` → `CacheMissError` with no waiting set and no shared future,
  and `contracts/expressions.md`'s implementation status says the same. So Appendix B.5's point 2 is
  **not a live bug** — there is no shared fetch for one waiter's cancellation to kill. It is instead a
  **design requirement** on the waiting set: shared work must be owned by a task belonging to the site,
  with each waiter awaiting a derived or shielded future. The throwaway evidence that "cancelling the
  awaiting task interrupts a blocked buffer resolution" was a single-waiter observation and says
  nothing about the shared case, because there is no shared case yet.
- **The linger default, and whether it is per-site configurable.** The *shape* is already ruled — one
  knob, one default, no per-source tuning until something measured asks for it. Only the number is
  open. **Recommendation:** reuse the few-seconds figure of the node-state-lifecycle self-edit-revert
  hold rather than inventing a second constant, pending measurement.

 **Decision: (a)**. Deduplicate fetches. Follow recommendation on the linger.

**Closed** — the deduplication requirement is `contracts/expressions.md` §*Cancellation*: the waiting set
lives at the materialization site, keyed by **checksum**, with latch-on, so shared work is owned by the
site and not by any one waiter. The linger recommendation is superseded in one respect by the later
ruling that the linger and the node-state self-edit revert hold are **two knobs, not one shared
constant** (§*The linger* there, and `contracts/node-state-lifecycle.md` §*Self-edit revert hold*, whose
figure is 30 s). What (a) still asks for is **evidence, not a ruling**: read the jobserver
dispatch/cancel path and settle whether an abandoned Expression materialization holds a worker slot,
before the waiting set is built.

### 6. Does a bound projection's `input_celltype` follow the path, or report the root's?

`BoundCellBackend.input_celltype` (`seamless-workflow/seamless_workflow/builder_state.py:64-69`) calls
`context._effective_input_celltype(self.node_path)` and **drops `self.local_path`**, while
`BoundCellBackend.source` passes `local_path` into `_public_cell_source` and so does follow the path.
For a join `ctx.join.left = ctx.left`, `ctx.join.left.source` correctly reports `ctx.left` while
`ctx.join.left.input_celltype` reports the **root's** input celltype. Options: (a) rule it intended —
`input_celltype` is a property of the node's input edge, not of a projection of it — and document that
the two members deliberately disagree; (b) rule it a bug, pass `local_path` through, and make the pair
consistent. **Recommendation: (b)**, because the page presents `.source` and `input_celltype` as two
readings of the same input, and a reader has no way to guess that one walks the path and the other does
not. Whichever is chosen, `contracts/cells.md` must say so explicitly.

**Unblocked, still open (2026-09-21).** The wiring rule of section 2, item 9 is defined in terms of the **input** path — the projection on the *source* side — so a one-level connection target never makes an edge projecting and the rule never consults a bound projection's `input_celltype`. Heterogeneous joins stay legal. Nothing now waits on this item; it remains a genuine inconsistency between two members the page presents as two readings of the same input.
**Decision**: (b), known bug.
**Closed** — `contracts/cells.md` §*The input* states the single resolution for `.source` and
`input_celltype`, and the page's implementation-status list records the divergence as a known bug
(`BoundCellBackend.input_celltype` drops `local_path`), with "do not rely on `input_celltype` at a bound
projection" until it is fixed.

### 7. The database `path` column is `CharField(max_length=100)`

`seamless-database/database_models.py:118`. Deepfolder keys are routinely full relative file paths, and
the contract makes exactly one string-item step legal over a deep checksum — so once deep Expressions
are enforced (section 2, item 3), a legitimate path can exceed the column. It is moot today, because
every deep Expression raises before reaching the database. Options: (a) widen the column, which is a
schema migration on a protocol that is otherwise stable at 2.2; (b) cap the path length at the
Expression layer and reject longer ones, which makes a legal deep key unusable; (c) store a hash of the
path and keep the text elsewhere. **Recommendation: (a)**, decided *before* item 3 is implemented rather
than after, since the alternative is discovering it as a runtime failure on somebody's real directory.
Note that neither `contracts/expressions.md` (which owns the identity tuple and its storage) nor
`contracts/deep-celltypes.md` (which owns the path rule producing long keys) cross-references the other
on this, so the collision is invisible from either page.

**Materially worse after 2026-09-21.** Unconditional Expression **fusion** (section 2, item 9) concatenates the paths of a whole run of projecting edges into one stored path, so long path strings stop being a deep-only concern and become ordinary: `ctx.data.results.samples.s1.measurements.values[3]` is one Expression with one ~55-character path where it used to be six Expressions with short ones. The column is therefore reachable by plain nested-dict work, not only by deepfolder keys.

**CLOSED (2026-09-21), and it is a seamless-database matter.** None of (a), (b) or (c) as written, and
nothing about it reaches the Expression contract: `contracts/expressions.md` now says only that there is **no
limit on path length** and that no Expression is refused for it. Everything below happens **internally, at the
database level**. The author's decision: serialize the path as
**Seamless-`plain`** rather than as bare JSON — canonical bytes, so one path has one stored form — and when
that serialization exceeds the column, store the **checksum** of the path buffer instead, JSON-encoded, with
the buffer itself in the hashserver. No column migration, no length limit, and it covers the case splitting
could not: a single deepfolder key longer than the column. The earlier ruling that fusion is *bounded by
storage* is withdrawn with it — fusion is unconditional again. Stated in `contracts/expressions.md`
§Identity.

Three things this needs, all inside seamless-database rather than in any contract page:

- **A discriminator.** The column may now hold either a serialized path or a checksum, and length does not
  separate them: a checksum JSON-encodes to 66 characters, well inside the column, and a path whose text is
  64 hex characters is a legal identifier step, so both forms can be a 66-character JSON string. Store the
  indirect form self-describingly — an object such as `{"checksum": "…"}`, which can never be the
  serialization of a path string — rather than inferring it.
- **A refholder claim from the database.** A stored Expression row is a *durable* claim on its path buffer.
  `contracts/internal/checksum-reference-lifecycle.md` lists only in-process refholders, so it has to gain
  this one, or a path buffer can be evicted out from under a row that fingertipping still needs.
- **A protocol bump and a decision on the existing rows.** `plain` serialization is JSON plus a trailing
  newline, so whether the stored text keeps that newline decides whether every existing key changes. Protocol
  is `("seamless", "database", "2.2")`.

---

## 7. Documentation and chores touching 1–4

*(Register §5, verbatim extracts.)*

- **`seamless/docs/main/`** has not been touched by this work. Known stale:
  `docs/main/api/seamless-database.md` still lists BufferInfo and shows protocol 2.1 (the code is 2.2).
- **`public-api.json` does not list `seamless.checksum.*`**, so the new contract pages have no
  generated API reference. The same holds for `seamless.cell_class` and `seamless.expression_class`:
  `cells.md` and `expressions.md` have no generated API companion either. Decide whether to add those
  modules.
- **~~There is no documented route to a deep folder child's *checksum* today.~~ Resolved
  (2026-09-21).** The interim route — read `.value` on an untouched deep Cell and index the raw dict —
  is now stated as such in `contracts/deep-celltypes.md` §*Reading a deep child today* and
  `contracts/cells.md` §*Deep celltypes on a Cell*, marked interim and not contract. The ruling that
  followed is that the route is to be **removed from the code first and from those pages afterwards**;
  see §3, the added bug 9, and the chore below.
- **~~`DirectCompiledTransformer.__call__` resolves a `deepcell` transformer *result* through
  `unpack_deep_structure`.~~ Documented and ruled (2026-09-21).** The output side is now written in
  `contracts/deep-celltypes.md` §*The output side: a deep result is an index* and cross-linked from
  `contracts/compiled-transformers.md` §*Result types*: a deep result is an index, reading it resolves
  nothing, and no claim is held on the leaves. What remains is the **code** change — §3, added bug 10.

Chores:

- **Orphaned `buffer_info` table.** The dead BufferInfo placeholder was removed from seamless-database
  (the model, its `_model_classes` entry, the import, the `SeamlessBufferInfo` helper, the
  `"buffer_info"` request type and its get/put branches, the README row). No client in any repo ever
  called the endpoint, so the protocol stays 2.2. Existing database files keep an empty, orphaned
  `buffer_info` table: decide whether to add a one-off `DROP TABLE IF EXISTS buffer_info` migration or
  leave it.
- **Historical design records in `seamless/` still mention BufferInfo.** Leave them as history.

Added 2026-09-21, not in the register yet:

- **Remove the interim deep-child passages from the contract docs — *after* the code.** When §4, item 3
  lands, the one-step path works and `.buffer` stops contradicting `.value`, delete
  `contracts/deep-celltypes.md` §*Reading a deep child before the rules are enforced* and the
  corresponding paragraph of `contracts/cells.md` §*Deep celltypes on a Cell*, together with the ruling
  notes that announce the removal. Not before: while every typed route still raises, those passages are
  what stop an agent from concluding there is no route at all (§3, bug 9). **Keep** the value rule
  itself — the value of a deep checksum is its index — which is contract and lives in
  `contracts/deep-celltypes.md` §*What a deep buffer is*.
- **Rename `_publish_expression_result` to `_tempref_expression_result`** (`seamless-core/seamless/checksum/expression.py`).
  The ruled vocabulary is *publishing* = the buffer write, *recording* = the result checksum; the
  function means neither — it registers a tempref. `contracts/expressions.md` and
  `contracts/internal/checksum-reference-lifecycle.md` both name the new spelling already. Do it in the
  same change that removes the publication (§10, §E.4 items 1–2).
- **The self-edit revert hold is ruled 30 seconds; the code default is 15.**
  `seamless-workflow/seamless_workflow/scheduler.py`, `self_edit_hold_seconds`. This is feature 10's
  constant, recorded here because the ruling came out of this pass;
  `contracts/node-state-lifecycle.md` states 30 and marks the code lag. One test pins the value
  explicitly (`seamless-workflow/tests/test_reference_lifecycle_forced_expiry.py`), so changing the
  default does not break it.

---

## 8. Appendix B — remote materialization: a waiting set with latch-on and delayed cancel

*(Register Appendix B, verbatim. This is the design behind §4, item 4.)*

Design discussion of 2026-09-17 (author + Opus). **No code was read and no tests were run: nothing below
is verified against the code.** The discussion settles what Expression cancellation is *for*, and
concludes that the mechanism does not belong to Expressions at all. It is used by any remote
materialization — Expressions, transformation input resolution, `.buffer` reads, mounts. It is the
design behind section 2, item 4.

### B.1 Premise: what can take time

Expression evaluation proper — deserialize, walk the path, convert, serialize, hash — is cheap, and it is
CPU-bound inside a single thread, so it could not usefully be interrupted anyway. (The worst case
measured is 0.4 s to classify 71 MB of JSON.) The only part that can take real time is resolving a
checksum to a buffer from a remote source: a read buffer server or a read buffer directory.

Three cases were raised against that premise; author's rulings:

- **Fingertipping (1a).** An Expression normally does not fingertip its input checksum, but it can, as a
  step in a fingertip chain. The cost of a materialization is therefore unbounded: the chain may contain
  Transformations. This is what makes the machinery below worth building.
- **Deep fan-out (1b).** Materializing a deep checksum into a value (`deepcell → plain`, N child buffers)
  is banned from Expressions, except for `folder`. So every Expression waits on exactly one buffer,
  `folder` excepted, and `folder` is the only case needing a multi-checksum waiter.
- **After the buffer arrives (1c).** Evaluation is near-instantaneous, so there is no cancel point once
  the data is present: the evaluation runs to completion and its result is recorded.

### B.2 What cancellation is for

Never for correctness. Results are content-addressed, so a late result is unwanted, never wrong; and
since cancellation is best-effort, the Context must ignore late results from superseded runs in any case.
The value of a cancel is therefore: remaining resource cost × the chance that nobody else wants the
output.

For materializations the second factor is low, lower than for a Transformation result: the same buffer is
wanted by sibling projections of one parent (`ctx.a.x`, `ctx.a.y`), by the Transformation that takes the
same checksum as an input, and by a revert. Hence latch-on plus a delay before the abort, rather than an
eager abort.

### B.3 The mechanism

- **A waiting set per in-flight materialization, keyed by checksum**, held at the materialization site in
  the buffer layer — not by `Expression`. `Expression.cancel()` becomes "leave the set".
- **Latch-on**: a second requester for the same checksum joins the in-flight materialization instead of
  starting a second one.
- **Softcancel = deregister.** The fetch is aborted only when the set is empty, and then only after a
  linger of a few seconds; a requester arriving during the linger simply re-registers. One knob, one
  default; no progress-awareness and no per-source tuning until something measured asks for it.
- **No hard cancel** (settled). The only leaf a hard cancel could kill is a shared fetch, so it would
  merely make the other waiters fail and re-fetch. A single waiter pressing Ctrl-C is already covered:
  with one member, softcancel aborts the fetch.
- **Failure must not be sticky** (settled). A Transformation caches its exception; a materialization that
  fails (unreachable server, buffer absent) must not poison the checksum for the next requester. "Not
  found anywhere" is a real terminal answer, but it is the trigger for fingertipping, not a cached
  failure.
- **Vocabulary: "waiting set", not "refcount".** Keep it separate from the checksum reference lifecycle
  (feature 9: refholder claims vs manual incref/decref). Different things, different lifetimes: one keeps
  a buffer alive once it exists, the other tracks who still wants a fetch that has not finished. The two
  meet in exactly one place: the site must hold a lifecycle claim for the duration of the linger and
  release it when the timer fires. That is what the balance audit at `seamless.close()` should catch.

### B.4 Fingertip chains

With 1a, the chain is the real unit: a requester asks for one buffer, and the machinery may start a tree
of Expressions and Transformations that nobody named.

- Abandoning the root must cascade soft deregistration down every step, or an abandoned chain runs to
  completion. Each step keeps its own waiting set, so a step shared with a live chain survives — the
  membership model of feature 8, applied one layer down.
- Convergence is normal: two chains often need the same intermediate, and one may arrive seconds after the
  other gives up. A second, independent argument for the linger.
- Abandoning mid-chain discards every intermediate; where intermediates are scratch, no trace of the work
  remains. A third argument for the linger.
- The leaf Transformation needs no special case: the linger keeps its member registered for those few
  seconds, and it is killed only when its own set empties (softness cascades, feature 8).

### B.5 What asyncio task cancellation does and does not give

Task cancellation is the right propagation mechanism for *abandonment* — cancelling the requester's task
unwinds its awaits down the chain and runs each step's cleanup — but it is not the mechanism for
deregistration. Four things it does not do:

1. **Deregister.** It knows nothing about the waiting set; each site must leave the set in its own cleanup
   path, synchronously or under a shield (an `await` inside a cancelled task raises at once).
2. **Protect shared work.** If the requester's task *owns* the fetch, cancelling that task kills the fetch
   for every latched waiter — a hard cancel in disguise. Shared work must be owned by a task belonging to
   the site, with each waiter awaiting a derived or shielded future. This is the worry recorded in
   Appendix A, item 5.
3. **Stop what is not an await**: a thread (`asyncio.to_thread`), a subprocess, a jobserver request, a Dask
   future. There, cancellation abandons the waiter while the work continues and keeps holding its resource.
4. **Delay.** A linger is by definition not "cancel the child when the parent is cancelled": the site's task
   must outlive every waiter.

### B.6 The four tests this design needs

Test the contract rather than "it stopped": (a) softcancel by the only waiter aborts a slow materialization,
after the linger; (b) with two waiters on the same *checksum* — not the same Expression — softcancel of one
keeps it alive; (c) a result arriving after supersession does not reach the node; (d) the reference-balance
audit at `seamless.close()` stays clean when a fetch completes after its last waiter left. (d) is a likelier
bug than a fetch that will not stop.

---

## 9. Ambiguities in the contract docs that bear on 1–4

*(Register Appendix D, items 1, 6, 8 and 12, verbatim; the register's numbering is kept. Appendix C's
dead-passage list is mount and context material and is not copied. The heading was missing from this
page and was restored on 2026-09-21.)*

1. **`expressions.md` calls one code object by two names.** §Deduplication presents
   `_active_expressions` as the membership set (contractual, present); §"Implementation status" says
   "the waiting set lives at the **Expression** layer (`_active_expressions`), not at the
   materialization site". Both sentences are true — today one object serves both roles — but a reader
   can conclude the two sets are one thing *by design*, which is exactly what section 2, item 4 exists
   to undo.
6. **`celltypes-and-conversion.md` never names the false-negative property.** By design — `hashtype.md`
   owns it — but a reader of that page alone could take a `False` answer to be as trustworthy as a
   `True` or `None` one, which is precisely backwards.
8. **Which page owns the *output* side of deep celltypes is undecided.** `deep-celltypes.md`'s
   "How deep values reach a transformer" is explicitly input-side and correct;
   `compiled-transformers.md` §"Result types" says a `deepcell` result is "individually
   checksum-addressed" without saying what the *caller* receives. That is a structural call, not a
   wording one — see the `DirectCompiledTransformer` item in section 5.

12. **A deep *dummy* read splits `.buffer` and `.value`.** On a `Cell("deepcell")` holding an index with
    no path, `.value` **succeeds** and returns the raw index dict — `Buffer.get_value` calls
    `Buffer._map_celltype` first, which maps the deep celltypes to `plain`, and a flat index parses
    fine as `plain`. `.buffer` instead **raises** `HashTypeValidationError`, because `CellBase.buffer`
    validates against the *un-mapped* celltype (`validate_deserializable_as(checksum, "deepcell")`),
    and `deserializable_as` returns `False` for anything outside the 13 celltypes. This is a second,
    distinct split from the one in section 4, feature 5, bug 4 (which is `None` versus a re-raised
    stored failure, after a recorded evaluation failure; this one is silent success versus a fresh
    raise, on an untouched read). It is documented in `contracts/cells.md` as current behaviour, and it
    is currently the **only** working route to a deep folder's child checksum — see section 5.
    **Ruled 2026-09-21:** the route is to be stripped from the code and only then from the contract
    pages — §3's added bug 9, with the documentation half as a chore in §7. The `.buffer`/`.value`
    split itself stays listed here, because it is what makes the route work.
    *(Item 8 above is closed with §11.7: a deep result is an index, so there is no separate
    "output side" to own — `deep-celltypes.md` keeps the deep semantics and
    `compiled-transformers.md` points at it.)*

---

## 10. Appendix E — fingertipping: placement, scratch and persistence

*(Register Appendix E, verbatim and complete. It carries the ruling that closed Appendix A item
4 — §6 above — and nine defects found while checking it. It is also the densest cross-repo
evidence on this page: seamless-core, seamless-jobserver, seamless-remote, seamless-dask and
seamless-transformer all appear in its line references.)*

Design discussion of 2026-09-21 (author + Opus), prompted by Appendix A, item 4. **Unlike Appendix B,
every code statement below was checked against the code**, and the line references are from that check.

Two readers — one agent, one author — reached the same wrong conclusion about where a fingertip chain
runs, starting from the contract pages as they stand. §E.1–E.3 are therefore written to be *moved into
the agentic contract docs* (§E.5 says where), not merely recorded here. §E.4 is what makes them untrue
today.

### E.1 The misunderstanding to prevent

The wrong model, stated so that it can be recognized: *"a fingertip chain is only orchestrated locally;
each Expression in it is dispatched to where the data is, and each Transformation runs on the server.
Only cell-level joins are forced local."*

Every clause of it is false, and the naming actively encourages it:

- **`evaluate_expression_async` is local-only**, despite having no "local" in its name. It registers its
  dedup members under a key that literally begins with `"local"`
  (`seamless-core/seamless/checksum/expression.py:144-161`) and calls `_evaluate_expression_async`
  directly; the sync `evaluate_expression` (`:104`) is local-only too. **The dispatching entry point is
  `evaluate_expression_remote` (`:271`)** — the one function whose name says "remote" is the only one
  that can decide *local*, because it is the one that takes `execution="auto"` and consults
  `choose_expression_evaluation_location`. Anyone reasoning from the names will get this backwards.
- **`Checksum.fingertip` calls the local evaluator** (`seamless-core/seamless/checksum_class.py:398`),
  so no placement decision is taken anywhere in a fingertip chain.
- **The decision would come out "local" regardless.** The loop materializes the input into this process
  first (`checksum_class.py:388`), and `choose_expression_evaluation_location` defines locality as "in
  this process's memory" (`expression.py:75-100`).
- **Transformations are forced local.** `recompute_from_transformation_checksum` passes
  `force_local=True` (`seamless-transformer/seamless_transformer/transformation_cache.py:1160`), which
  `_run_uncached` turns into `execution = "process"` (`:630`); the jobserver (`:654`), worker-pool
  (`:713`) and forward-to-parent (`:733`) branches are each guarded by `not force_local`, as is the
  remote result lookup (`:235`).

So: **a fingertip chain executes entirely in the requesting process.** "Evaluated where the data is"
(`expression-where-the-data-is.md`, `contracts/expressions.md`) governs ordinary Expression evaluation
and does **not** govern fingertipping. Cell-level joins (section 2, item 6) are a separate local-only
case, not the only one.

What *is* remote-aware is candidate discovery: the reverse index is read from the local caches and from
the database (`get_rev_transformations`, `get_rev_expressions`), so a client needs no local cache to find
the chain. And a fingertip that happens *inside* a job runs on that job's host —
`transformation_namespace.py:226-228` fingertips a missing input where the transformation executes, gated
on `allow_input_fingertip`, and seamless-dask submits `_fat_finger_checksum_task` to a worker for the same
purpose (`seamless-dask/seamless_dask/client.py:817-829`). Those are not counter-examples to the rule
below; they are the same rule applied at the site that wants the buffer.

### E.2 Why local evaluation is correct, and not merely current

1. **There is no buffer-return channel.** The jobserver's `run-expression` handler returns
   `{"result_checksum": …}` and nothing else (`seamless-jobserver/jobserver.py:809-812`). A remotely
   evaluated result reaches the client only through the hashserver. Remote evaluation of a fingertip is
   therefore not a placement choice with a transfer cost — it is a placement choice that **must write to
   the hashserver**.
2. **That would undo the decision that made the fingertip necessary.** Every Expression result could have
   been stored in the hashserver; a seamless-database deployment implies one. When a buffer is missing it
   is missing because of a scratch decision or an eviction decision. Remote evaluation re-adds exactly the
   entry that was deliberately kept out or removed. Local evaluation materializes it in process memory
   only. (The exception proves the rule: a manual Expression whose result is never increfed signals
   ephemeral interest, which contradicts wanting it back later.)
3. **The cost is bounded by the frontier, not by the ancestry.** `fingertip` resolves first at every level
   — `checksum_class.py:299-302`, and the nested call at `:388` is itself a `fingertip()` — so the walk
   stops at the first checksum `resolution()` can serve: local buffer cache, then hashserver (see also
   Appendix A, item 3 for the read-buffer-directory case). What travels to the client is the frontier of
   the absent region. For a direct request the target reaches the client either way, so local recompute
   transfers the frontier *instead of* the target — normally less, because the archetypal scratch shape is
   a large output derived from smaller stored inputs.
4. **Capability is the requester's own business.** The client holds the graph. Under this ruling that is a
   restriction the contract must **state**, not an argument against it: fingertipping assumes the
   requester can execute its own transformations. Today it cannot even find out that it could not — see
   §E.4, items 5 and 6.

**The projection counter-case, and why it does not overturn the rule.** Fingertipping a large parent in
order to keep one small item is real, and there local evaluation is the expensive choice. It is a
modelling error, and two rules keep a graph out of it:

- **Do not scratch a small derived cell.** If it is stored, `resolution()` serves it and no chain is built
  at all.
- **Make an item-addressed large parent deep.** A path step over a deep checksum selects a sub-checksum
  without materializing the parent.

That shape is reachable only by opting into it. Neither rule is stated in the scratch guidance today.

**The optimization that stays available and is not recommended:** remote evaluation followed by immediate
hashserver eviction. It buys the projection case at the price of a write that scratch or eviction had
excluded, and anything expensive enough to justify it should not have been scratched in the first place.

### E.3 Publication is an act of interest, not a side effect of evaluation

Three things are easy to conflate, and the code's own naming conflates two of them:

- **Evaluating** an Expression, or recovering a buffer by fingertipping, produces a buffer in the
  evaluating process's memory. That is all it does.
- **Recording identity** — `_expression_cache` and `database_remote.set_expression_result` — stores the
  mapping from an Expression to its result checksum. It is what the reverse index that fingertipping
  walks is made of, it must keep happening, and it says nothing about where the buffer is.
- **Publishing** — writing the buffer to the hashserver — is an assertion that somebody holds the result
  and will want it later.

The rule: **neither evaluation nor fingertipping publishes.** An Expression that publishes its result is
a bug, whether or not a fingertip drove it. Publication is the act of increfing the buffer — indicating
non-ephemeral interest, for example through a non-scratch Cell — and that single act both writes the
buffer to the hashserver and overturns any scratch status, because `incref` and `incref_refholder`
`discard` the checksum from `_scratch_refs` and queue its buffer
(`seamless-core/seamless/caching/buffer_cache.py:260-270`, `:295-308`).

So a bare `Checksum.fingertip()` leaves nothing behind but a buffer in local memory. `Cell.fingertip()`
on a non-scratch Cell persists the result, because the Cell increfs it; on a scratch Cell it does not.
The fingertip site itself never decides: it holds a bare checksum, with no owner and no scratch intent.
Nor is any promotion machinery needed — the buffer is already in the local cache, so the later
non-scratch incref finds `entry.buffer` and writes it (`_ensure_entry_locked`,
`buffer_cache.py:215-218`). The one caveat is `purge_scratch()` running in between.

**Terminology warning.** `_publish_expression_result` (`expression.py:537`) does not mean "publish" in
the sense above. Its docstring is "Publish bounded cache interest" — it registers a tempref, and the
hashserver write is a *side effect* of that tempref being non-scratch. The name will mislead whoever
fixes §E.4, item 1.

**Remote evaluation therefore needs the interest to travel with the dispatch — which is exactly how
transformations already work.** If the evaluating side never publishes, a remotely evaluated result stays
in the worker's memory and the client receives a checksum it cannot resolve; the client's own later
incref cannot repair that, because a non-scratch incref on a checksum with no local buffer marks the
entry `remote_registered` and writes nothing (`buffer_cache.py:195-218`) — there is no buffer in that
process to write. The transformation path solves this by making `scratch` a parameter of the request:
`run_transformation` carries it (`seamless-remote/seamless_remote/jobserver_remote.py:115`, `:130`;
`seamless-jobserver/jobserver.py:536`, `:565`, `:613`, `:647`), the executing side's non-scratch tempref
writes the result buffer to the hashserver, and the jobserver asserts it can resolve the result before
answering (`jobserver.py:698-700`). So the executing side publishes **on the requester's behalf, under
the requester's scratch decision** — the rule above is preserved across the process boundary rather than
broken by it. The expression dispatch simply lacks that parameter today (§E.4, item 3).

### E.4 Why none of this is true today

Bugs and missing features found while checking §E.1–E.3 against the code on 2026-09-21. None is recorded
elsewhere in this file, and none is scheduled.

1. **Expression evaluation publishes its result buffer.** Every terminal branch of
   `_evaluate_expression_after_validation` calls `_publish_expression_result(…, buffer=…)`
   (`expression.py:492`, `:498`, `:512`, `:533`), which temprefs non-scratch — it has no scratch
   parameter — so `_ensure_entry_locked` sets `write_remote` and `tempref` ends in
   `buffer_writer.register(write_buffer)` (`buffer_cache.py:405`), a background write to the hashserver
   whenever one is configured (`buffer_writer.py:59-68`). By §E.3 this is a bug for **every** expression
   evaluation, not only a fingertip-driven one: it makes persistence a property of who evaluated rather
   than of who holds. Its sharpest form is the fingertip case — recovering a scratch or evicted buffer
   *re-adds it to the hashserver*, locally, with no dispatch involved, silently repopulating the store
   with exactly the buffers someone decided to keep out. That is the more consequential half of
   Appendix A, item 4. **The transformation branch of a fingertip does not have this defect**:
   `scratch=True` gives `result_checksum.tempref(scratch=True)` (`transformation_cache.py:819`),
   documented as "no remote registration" (`buffer_cache.py:375`). The two branches of the same function
   disagree, and the expression branch is the wrong one.
2. **The fix is not a scratch flag on Expressions.** Recorded because the obvious-looking fix — give
   `_publish_expression_result` a scratch parameter and pass it from the fingertip call site — would
   leave ordinary expression evaluation publishing, which §E.3 says is equally wrong. The fix is to
   remove the publication and let the refholder be the only publisher, which means the identity
   recording (`_expression_cache`, `set_expression_result`) and the HashType registration must be kept
   while the buffer write goes. It pairs with item 3, which is what lets the rule survive a dispatch.
3. **The expression dispatch carries no `scratch` flag.** The client sends only the four identity fields
   (`seamless-remote/seamless_remote/jobserver_remote.py:148-153`, `daskserver_remote.py:181`); the
   handler accepts those plus an optional validator pair
   (`seamless-jobserver/jobserver.py:774-812`), and answers `{"result_checksum": …}` alone. So the
   executing side has no way to learn whether the requester will hold the result, and no way to be told
   to publish on its behalf — the gap that §E.2,
   item 1 sees as a missing return channel and §E.3 sees as interest that cannot travel. The remedy is
   the parameter the transformation path already has, not new machinery: `scratch` on the request,
   publication on the executing side when it is false, and the same resolvability assertion the
   jobserver already makes for transformations.
4. **`Cell.fingertip()` does not exist.** There is no `fingertip` anywhere in
   `seamless-core/seamless/cell_class.py` or `expression_class.py`; the only entry point is
   `Checksum.fingertip()`. A bare checksum has no owner and no scratch intent, which is plausibly why the
   publication of item 1 defaults to non-scratch. A Cell-level entry point is what makes §E.3's rule
   expressible at all.
5. **A fingertip discards every failure reason.** Both candidate loops are `except Exception: continue`
   (`checksum_class.py:419`, `:437`), so a missing binary, an unavailable conda environment, a resource
   error and a genuine absence all collapse into a bare `CacheMissError(self)`. Under a local-evaluation
   ruling this is the difference between a livable restriction and an undiagnosable one.
6. **A local recompute can silently produce nothing.** `__env__` is not enforced for Python; only declared
   binaries are checked (`run.py:131-142`, `shutil.which` → `RuntimeError`), and bash activates the
   declared conda environment. A mismatched client environment therefore yields a *different* result,
   fails `if Checksum(result) != self`, and the candidate is skipped — which item 4 then reports as a
   cache miss.
7. **There is no "materialize" mode, only a cache-popping workaround.** `evaluate_expression_remote`
   short-circuits on `_expression_cache` (`expression.py:290-293`) and on
   `database_remote.get_expression_result` (`:299-309`), both returning the result *checksum* without
   producing its buffer — the wrong answer for a fingertip, whose target checksum is already known and
   whose database mapping is how the candidate was found. Today's code works around this by evicting the
   memo first (`checksum_class.py:397`), a global side effect standing in for a missing flag. Any change
   to that call site must preserve the distinction between "tell me the checksum" and "produce the
   buffer".

### E.5 Where this has to land in the contract docs

(The list below is not necessarily exhaustive, and treat it as suggestions)

- **`contracts/expressions.md`** — fingertipping is exempt from "evaluated where the data is", with the
  no-buffer-return-channel reason (§E.2, item 1), and the naming hazard of §E.1 stated where the API is
  listed.
- **The scratch pages** (`scratch-witness-audit.md`, `identity-and-caching.md`) — the two modelling rules
  of §E.2, and §E.3's separation of evaluating, recording identity and publishing.
- **`contracts/internal/checksum-reference-lifecycle.md`** — that a non-scratch incref is the *only*
  publisher: it writes the buffer to the hashserver and overturns any scratch status. It is the
  load-bearing mechanism of §E.3 and is currently stated nowhere.
- **`contracts/cells.md`** — `Cell.fingertip()`, once it exists (§E.4, item 4).

Until §E.4 is addressed, each of those passages is contract ahead of code, and should say so.

---

## Method of the footprint audit (§2)

Case-insensitive sweep for `expression` over the non-test sources of every repo in the
workspace, plus targeted greps for `HashType` / `hash_type` / `checksum.conversion` /
`conversion_feasible` / `deserializable_as`, then reading each hit to separate implementation
from consumption. Test files were excluded from the footprint; §5 covers those.

---

## 11. Ambiguities found while making the contract docs crystal clear (2026-09-21)

*(Raised by the documentation pass over `docs/agent/contracts/` on 2026-09-21 — the pass that landed
the cross-reference spine, the deep-celltype coverage, the prominence of project-then-convert, and
Appendix E's §E.5 list. Each item was a question the pass could **not** answer from the existing
rulings.)*

**All ten were answered by the author on 2026-09-21, and all ten are closed.** Each decision has been
adopted into the contract pages and its question deleted; the table records what was decided and where
it landed, so a ruling stays findable without its question. **11.8 was not a contract question** — its
answer is to remove something from the code first — and it has moved to §3 (added bug 9) and §7 (a
chore). **Nothing in this section is open.**

| Question | Decision | Adopted in |
|---|---|---|
| **11.1** "publish" meant three different things in three pages | *publishing* is the **buffer write**; *recording* is what happens to a result **checksum** (the lifecycle page's old sense of "publication"); `_publish_expression_result` → `_tempref_expression_result` | `internal/checksum-reference-lifecycle.md` §1 and §8 (term renamed, callout replaced by the ruled vocabulary); `expressions.md`; `identity-and-caching.md`; `scratch-witness-audit.md`. The code rename is a chore in §7 |
| **11.2** does reading `Expression.checksum` publish the result buffer? | **(a)**, strengthened: an Expression's `"result"` claim is **scratch-neutral** — eviction protection only, no write, no scratch override — and, because a result checksum may equally come from the process cache, the database or a checksum-preserving conversion, **fingertipping is the only guaranteed way to obtain a result buffer** | `expressions.md` §*Results and caching*; `internal/checksum-reference-lifecycle.md` §6 and §8 (only an owner with a scratch policy publishes); `cells.md` |
| **11.3** `Cell.fingertip()` — four unspecified details | it is `Cell.checksum.fingertip()` **without** the forcing of `.checksum`: no result checksum → **no-op returning `None`** (so it is safe bound as well as standalone); it returns the recovered **buffer**; it never sets `.exception`; and **`Pin.fingertip()` exists** with the same meaning | `cells.md` §*`.buffer` and `.value`* and the work table; `pins.md` (surface, read section, status) |
| **11.4** does "never publishes" bind a fingertip *inside* a job? | yes, uniformly: **a fingertip chain writes no regenerated buffer to the hashserver at any site**. The one exception is a fingertip performed on somebody else's behalf — a **remote fingertip request** — which writes the buffer of the fingertipped checksum, and **only the end result**, never an intermediate | `expressions.md` §*Fingertipping is exempt…*; `scratch-witness-audit.md`; `identity-and-caching.md`; `internal/checksum-reference-lifecycle.md` §8 |
| **11.5** the read-buffer-directory decision versus placement's stated properties | **cheap and deterministic filesystem checks** are allowed (the "side-effect-free" phrasing is relaxed; no index-only membership test is required); read-buffer directories count as local for placement and are consulted **before** the hashserver. Resolution needs no change — verified in code that `buffer_remote.get_buffer` queries read folders before read servers | `expressions.md` §*Placement* and *Current limitations*; §6, item 3 |
| **11.6** deep celltypes and the false-negative property | **neither** offered option: `deserializable_as` accepts only the 13 and **raises `ValueError`** on anything else. Deep shapes are vetted **structurally, at Expression construction** — the conversion engine for pathless (it gains the deep-to-deep conversions), the deep table for pathed, common-sense path rules for the 13 — and HashType vets only what the input checksum's word proves, at evaluation | `hashtype.md` (queries, capabilities, false-negative property, non-goals); `deep-celltypes.md` §*Where deep validation happens*; `expressions.md` §*When an Expression is vetted* |
| **11.7** the deep output side | there was no real question. The answer is general: **whenever the value of a deep checksum is requested, it is the index** — at every layer, for results exactly as for inputs. A transformation returns a checksum as always; reading a deep result resolves no children, and `folder` is not a special case (a caller that wants the bytes pays for `folder → mixed` explicitly). The transformer holds **no refcount on the leaves**. `unpack_deep_structure`'s output-side fan-out is the mis-port and goes | `deep-celltypes.md` §*What a deep buffer is* (the value rule) and §*The output side: a deep result is an index*; `compiled-transformers.md` §*Result types*; `cells.md`; `internal/checksum-reference-lifecycle.md` §8 (no-leaf-ownership now names the result side); §3, added bug 10 |
| **11.8** the interim route to a deep child's checksum | strip it **from the code first, and only then from the contract**. Narrowed by the value rule of 11.7: what is stripped is the **anomaly** — the unvalidated dummy read and the `.buffer`/`.value` split — not `.value` returning the index, which is contract | §3, added bug 9; §7, chore. The two contract passages carry the ruling and stay until the code changes |
| **11.9** cost-*class* vocabulary | the three classes — **free**, **one child**, **all children** — are named once, in `deep-celltypes.md` | `deep-celltypes.md` §*The organising principle*; `expressions.md` §*Cost class* uses those names |
| **11.10** the linger constant versus the self-edit hold | **two knobs**, because they answer different events; the self-edit revert hold is **30 seconds** for now (the code default is 15) | `expressions.md` §*The linger*; `node-state-lifecycle.md` §*(b) Self-edit revert hold* and its status list; the code lag is a chore in §7 |
