# cells-and-expressions: what is left to do

This is the working register for the cells-and-expressions branch of work, reorganized on
2026-09-20 from the 2026-09-17 findings file. It is a **to-do register**, not a history: an item
is here because someone still has to act on it.

**Status.** All eleven features are implemented and merged to `main`, and all eleven have their
agentic contract docs in `seamless/docs/agent/contracts/`. What is left is the code work nobody
has scheduled (section 2 and section 4), the test debt (section 3), the human documentation and
`docs/main/` (section 5), and five genuinely open design questions (Appendix A).

How to read it:

| Section | Holds |
|---|---|
| 1. Feature list | The eleven features, their dependency order, status, and contract doc |
| 2. Coordinated implementation change plans | Multi-repo changes still to do, with their plan docs |
| 3. Test set gaps | Harness problems, missing coverage, tests that encode the wrong contract |
| 4. Known bugs | Defects with a known cause, in code or in a design doc, none of them scheduled |
| 5. Misc things to do | Everything else: merges, API surface, documentation, chores |
| Appendix A | The design decisions that are genuinely still open |
| Appendix B | The remote-materialization design discussion that Appendix A rests on |
| Appendix C | Provenance: the design docs of this work, and which of their passages are dead |

**What was removed on 2026-09-20.** Every design decision that had been ruled *and* is stated in
the contract docs was deleted from this file: the five Cell rulings, the seven attachment/mount
rulings, the deep-checksum ruling, the Expression placement history, the `hashtype.md` limitation
review (L1–L7, all since fixed by seamless-core `0d3ccfb` and `827bd5b`), the Q1–Q12 question log,
and the bound-vs-standalone finding list. Those are now contract, and the contract docs are the
place to read them. Three decisions turned out to be open after all and moved to Appendix A; one
turned out to be a previously unrecorded bug (section 4, feature 5, bug 5).

---

## 1. Feature list

Dependency-ordered: each item builds on the earlier ones. Status keys: **delivered**,
**delivered (gaps)**, **deferred**, **open**.

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
5. **Cells as deferred Expressions** — on top of 4: a Cell is the mutable builder, bound or
   standalone; it holds an input (literal/checksum) or builds an Expression over a `.source`, as a
   Transformer builds a Transformation. Shared CellBase read API; `celltype` is the output type and
   `input_celltype` is read-only; `.set()` takes values only; a Checksum is a value only for celltype
   `checksum`; `None` is a value and `del` is the only deletion. Standalone reads evaluate their own
   cheap expression but never run a source; `.value` never fingertips; `.compute()` does the work.
   **Delivered (gaps).** Bound/standalone divergences and the projection-write bug: section 4.
   Deferred: Cell validators. Contract: `contracts/cells.md`.
6. **Optional pins** — transformer-construction substrate, below the Context.
   `Transformer.optional_pins` is a settable set of pin names. Canonical null on an optional pin =
   absence, for any celltype: unconnected and connected-then-null give the same transformation
   checksum, because the pin is dropped before the checksum is computed. Connected optional pins
   still compute, and a failing optional upstream still fails.
   **Delivered.** Contract: `contracts/pins.md`.
7. **Transformer and pins sharpened** — mostly a consequence of 3, 5, 6; the pin-sugar removal was
   driven by the Context's name-collision problem. A Pin is a sister class of Cell (shared
   `CellBase`) and can never be a source. `tf.pins.x` is the only pin path; one producer per pin;
   out-of-signature names rejected for Python callables; `result` is never a valid pin name; `del`
   only for signatureless code. `pin.celltype` is the same setting as `tf.celltypes.x`; pin celltype
   conversion is shared by reactive and snapshot runs; a failed conversion gives `blocked-by-error`
   before a Transformation is built. Null on a required pin raises `TypeError`, except for celltypes
   `plain`, `mixed`, `bytes`.
   **Delivered (gap: compiled pins are recorded as `mixed`, section 4).**
   Contract: `contracts/pins.md`, `contracts/compiled-pins.md`.
8. **Cancellation substrate** — base layer for 4, 7, 10. One membership set per dedup site
   (in-process / jobserver / Dask). `softcancel` = deregister; the run is cancelled only when the set
   is empty. `cancel` = hard kill of every member. Softness cascades; a real kill happens only at the
   leaf set. Cross-process liveness deliberately not built; the reactive scheduler uses softcancel
   only, CLI/SIGINT stays hard. Replaces first-caller-owns-execution and fixes the jobserver
   multi-tenant footgun.
   **Delivered (gaps: section 4).** Contract: `contracts/cancellation.md`.
9. **Checksum reference lifecycle** — internal. Refholders (Cell, Expression,
   Transformer/Transformation, Context current/superseded runs) keep checksum buffers alive;
   refholder claims are counted separately from manual incref/decref; public vs internal interest is
   a hard rule; scratch and deep checksums have their own rules; only the *top-level* checksum of a
   deep value is owned, with no recursive deep ownership (`folder` included). Balance audit at
   `seamless.close()`, user-visible only as `seamless.references` warnings.
   **Delivered (gap: section 4).** Contract: `contracts/internal/checksum-reference-lifecycle.md`.
   Not to be confused with feature 10's node state lifecycle.
10. **Reactive workflow (seamless-workflow Context)** — rests on 4 and Transformations, with Cells
    (5) and Transformers/Pins (7) as its handles, using 2, 6, 8, 9. The Context holds a DAG of nodes
    and builds private Expression/Transformation snapshots each tick; `ctx.a` / `ctx.tf` are views
    onto nodes (one canonical handle type); on binding, a Cell's builder state moves into the
    Context. Six-state node machine with a glitch-free cascade; speculative supersession with grace
    holds (at most 3 superseded runs per node); `ctx.prune()`. One controller thread per Context,
    sole mutator, sequenced ingress, poison on internal failure, `Context.close()`. Barriers
    (compute/computation) with timeouts raising `TimeoutError`. Deep value assignment is legal; a
    connection may go at most one level below the root. Checksum writes are HashType-validated.
    Cell-level joins are plain local Python — no Transformation and no Expression — so a join node is
    never observed `computing`; this is **provisional** (section 2, item 6).
    **Delivered (Part I, A0–A5).** Contract: `contracts/node-state-lifecycle.md` (the node state
    lifecycle, documented extensively), `contracts/workflow-context.md` (runtime and API).
11. **Attachments and mounts** — on top of 10. Attachment framework: sense = authoritative write;
    actuate = delivery after a turn; a durable spec plus an ephemeral session. File mounts are the
    only production driver (`ManualDriver` is test-only, `WidgetDriver` experimental): global watch
    broker plus I/O pool; atomic conditional writes; null files read as null and deliver as
    truncation; mounts never give up; an oscillation detector; `ctx.mounts.sync()`. `folder` mounts
    in `r`/`w`/`rw`, `deepfolder` sense-only, `deepcell` / `module` / `checksum` unmountable.
    **Delivered.** Contract: `contracts/attachments.md` (framework),
    `contracts/mounts.md` (file driver).

**Also in scope** (not part of the dependency chain):

- **A. Transformation core** (RELEASE-NOTES v1.4): immutable definition vs mutable promise; dunders
  reclassified (`__meta__` / `__env__` out of identity, `__schema__` in for compiled — an intentional
  cache break); latch-on default vs `--strict` / `strict_dunder`; checksum-addressed cancellation
  API; `seamless-run-transformation` replay CLI; `.zst` / `.gz` checksumming fix. These sit below 4
  and 8.
- **B. Operational contract clarifications** (not features): remote execution requires a shared
  hashserver plus database; environment fingerprints come from manual probes (conda-cache refresh
  excepted); remote-http-launcher debug logging; caching masks nondeterminism; fingertipping is
  distinct from scratch (relevant to 4 and 5: the reverse index; `.value` never fingertips).

**Supporting work, not features:** the seamless-workflow A0 contract suite (folded from `claude/` +
`codex/`; `tests/claude/` retired); the black-box cancellation suite
(`seamless-transformer/tests/cancellation`); legacy-mining of ~296 characterization scripts.

---

## 2. Coordinated implementation change plans still to do

Each item spans more than one repo or more than one layer, so none of them is a local fix. Items 1
and 2 have written plans; the rest need one before they can be handed off.

### 1. Compiled transformer and transformation celltypes

**Plan: `seamless/compiled-transformer-celltypes-design-plan.md`** (1498 lines, handoff-ready).

Today every compiled input pin is recorded in the concrete transformation as `mixed`, whatever the
schema declares (`compiled_transformer.py:458`; `pretransformation.py:264`, `:459`). That erases the
pin boundary, bypasses ordinary conversion and the required-pin null check, and lets invalid values
fail only during native argument marshalling (section 4, feature 7, bug 1). The plan gives compiled
transformers a typed Seamless boundary defined jointly by the compiled signature schema, the declared
pin celltype, and — for a pin declared `mixed` — a restricted set of natural mixed values. It changes
both the mutable builder/API layer and the immutable transformation layer (pin tuples, checksums,
dependency resolution, pre-hash validation, native execution).

`contracts/compiled-pins.md` §10 already commits to this as the end state and accepts the
consequence: **transformation checksums change**, so cached compiled results are invalidated once.
Only scheduling is open.

### 2. Workflow authorizer (submit gate)

**Plan: `seamless/workflow-authorize.md`** (329 lines; design-level, explicitly *not* a handoff).

A per-boundary-edge gate holding the authorized checksums for a heavy stage, taken at
waiting → computing; unsubmit clears the authorization and immediately softcancels. Depends on the
reactive Context (delivered) **and on a shareserver** — an HTTP/websocket attachment driver that does
not exist yet. Blocked on that driver.

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
place the waiting set meets feature 9. Four open questions remain before this can be planned:
Appendix A, items 3–5.

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

### 6. Cell-level join re-implementation

**No plan document.** Superseded: `context-internals-followup-design.md`:392-396.

Joins are assembled directly in the Context, in-process, as plain local Python
(`Context._derive_cell` hands `sidework.evaluate_cell` to `_demand` under a `("merge", …)` fact key;
`evaluate_cell` is `Checksum.resolve` + `_assign_path` + `checksum_for_value`). The intended
re-implementation caches joins and evaluates them where the data is. The contract docs therefore
describe the observable behaviour only, marked provisional, and promise no join identity. Anyone
doing this work must keep that promise: the docs must not acquire a join identity claim before the
implementation has one.

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

### 8. Merge the `jupyter-sync` branch

The hang was executor starvation on a shared loop; the scoped driver-loop fix works on HEAD
(worktree `jupyter-final`). Do **not** add a `start()` wakeup — the construct would then compute
eagerly.

### 9. Cells, Expressions and wiring: the 2026-09-21 ruling set

**No plan document. Spans seamless-core, seamless-workflow and seamless-database. Every item below is
already written into the contract pages and marked *contract ahead of code*; none of it is implemented,
and none of it has a test.**

The author ruled a connected set of changes on 2026-09-20/21. They lean on each other, so they are one
change, not nine:

| Rule | Page |
|---|---|
| **Project-then-convert**, and an Expression never converts its input (at most one conversion, always last) | `expressions.md` §Application order |
| **Syntax order = application order**: `as_celltype` mid-chain closes the Expression and re-bases the next step | `cells.md` §Projections |
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

## 3. Test set gaps

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

### 3.2 `FULL_TEST_REPORT.md` is stale, and was produced the wrong way

`/home/agent/seamless1/FULL_TEST_REPORT.md` (2026-09-17) reports 804 passed / 40 failed and "23 test
modules with collection errors across 4 repositories". Both halves are artefacts:

- it ran `pytest -q -ra` **once per repository**, which is exactly the mode the harness rule above
  forbids. Every one of the 23 "collection errors" disappears when the module is collected on its own;
- it ran in an environment with a **stale installed `seamless_remote`**, which is what produced
  `AttributeError: module 'seamless_remote.database_remote' has no attribute 'set_hash_type'`. In the
  `seamless1` conda environment `seamless_remote` resolves to
  `/home/agent/seamless1/seamless-remote/seamless_remote/database_remote.py`, which has
  `set_hash_type`, and the affected tests pass. **This closes the open question left in the BufferInfo
  follow-ups** ("a stale installed copy or the then-ongoing implementation is the likely cause; not
  confirmed; re-run in the `seamless1` conda env") — it was the stale installed copy.

The report should be regenerated per-file in the `seamless1` environment, or deleted.

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

**Every collection error in the old report is gone** — they were the whole-directory artefact. The six
remaining failures are real and fall into two groups.

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

Both seamless-workflow failures are the same two the old report listed, so they have survived since
2026-09-17 and are not flakes. `seamless-dask` was not swept: its 33 recorded failures need a live Dask
cluster to interpret, which is a separate exercise.

So "the test set must go green", carried in this file since 2026-09-17, is **far closer to true than
the old report suggests** — 3426 passing, six failures, three of which are probably just missing
services. What remains is to re-run the service-dependent three properly, fix the three real ones, settle
`seamless-dask`, and add a `run-tests.sh` to the repos that lack one.

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

**Decide how a known-gap test is marked, once, and apply it everywhere.** The obvious choice is
`xfail(strict=False)`, which flips to `xpass` when the gap closes and so cannot be forgotten. Two of
these files — `test_materialization_waiter_contract.py` and the compiled-null parametrization — are
*deliberately* ahead of the code and belong in that category. The project already has a precedent for
getting this wrong: see 3.4, item 1.

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

## 4. Known bugs

None of these is scheduled. All are documented as current behaviour in the contract docs, which is why
they are not blocking anything.

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

**Not a bug, listed to stop it being refiled as one:** there is no hard cancel for Expressions. That is
a ruled non-feature — the only leaf a hard cancel could kill is a shared fetch, so it would merely make
the other waiters fail and re-fetch. The *naming* fix is already contract
(`contracts/expressions.md`, "API": `Expression.softcancel()` is the only verb, `Expression.cancel` is
retired and raises, and the module-level `cancel_expression` alias is dropped). The code lags: today
`Expression.cancel()` exists and is soft, `softcancel()` does not exist, and `cancel_expression` is
still an alias.

### Feature 5 — Cells

1. **Bound sub-path checksum and buffer writes raise `TypeError`.** `ctx.a.b.checksum = cs`,
   `ctx.a.b.set_checksum(cs)`, `ctx.a.b.buffer = buf` and `ctx.a.b.set_buffer(buf)` all fail with
   `TypeError: _edit() got an unexpected keyword argument 'input_celltype'`.
   `BoundCellBackend.write_checksum` (`seamless-workflow/seamless_workflow/builder_state.py`) always
   passes `input_celltype=`, and the `_cell_operation` branch of `ingress.controller_method` forwards
   `**kwargs` into `ingress._edit`, which has no such parameter. Root writes and the whole standalone
   path are unaffected. A one-line signature fix on either side would close it. This contradicts the
   3×2 write matrix, under which all six writes exist at a projection and keep their ownership check.
2. **A bound public read neither validates nor records.** `Context._get_buffer` and `_get_value`
   validate the checksum against the celltype and set `node.state = "failed"` with `node.exception`,
   but `ingress.controller_method` intercepts `_get_checksum` / `_get_buffer` / `_get_value` for every
   non-controller caller and resolves the checksum directly, so those bodies are dead for public reads.
   A bound `.buffer` returns unvalidated bytes, and a bound `.value` whose deserialization fails raises
   without setting `.exception`. Standalone does both.
3. **A bound read of a non-existent projection raises instead of reporting.** `ctx.p.nope.checksum`,
   `.value` and `.compute()` raise `ExpressionEvaluationError`, because the ingress read path catches
   only `KeyError` / `IndexError` while `expression._apply_step` wraps those in
   `ExpressionEvaluationError`. Standalone, the same projection returns `None` and records
   `.exception`.
4. **`.buffer` returns `None` where `.value` raises.** After a recorded evaluation failure,
   `CellBase.checksum` short-circuits on `_standalone_exception` and returns `None`, so `.buffer`
   answers `None` while `.value` re-raises the failure.
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

Items 1–4 are divergences between the bound and the standalone path, where
`celltype-rename-review-decisions.md` §8.4 rules that "the same applies to bound and standalone Cells".
The direction is settled: **the standalone behaviour is the contract**, and `contracts/cells.md` states
it that way with the bound behaviour listed as a divergence. Only the code fixes remain.

### Feature 7 — pins

1. **Compiled-transformer pins bypass the required-pin null check.** The pin null rule lives in
   `validate_pin_null` (`seamless_transformer/transformation_utils.py`): on an optional pin canonical
   null means absence for any celltype; on a required pin null raises `TypeError`, except for celltypes
   `plain`, `mixed` and `bytes`. Compiled transformers set every input pin to `mixed` whatever the
   schema declares, so null on a required compiled input declared e.g. `float` gets past every
   pin-level check, becomes Python `None`, and reaches C argument marshalling. The resulting failure is
   not traced: probably a late or unclear error instead of the pin-level `TypeError`. Fixed by section
   2, item 1. There is now a test — `seamless-transformer/tests/test_compiled_e2e.py::test_compiled_required_input_rejects_null_at_pin_boundary`
   — and it fails on all four parametrizations, which is the point (section 3.3).

2. **The compiled-pin gap is much wider than the null bypass.** Found on 2026-09-20 while checking
   `contracts/compiled-pins.md` against code, and now recorded in its §12:
   - **None of the compiled error types exist.** `CompiledPinCelltypeError`,
     `CompiledPinCelltypeWarning`, `CompiledMixedValueError` and `CompiledPinSchemaError` are specified
     in §9 and have **zero** occurrences in the code.
   - **The §3c celltype whitelist is never checked.** `CompiledCelltypesWrapper.__setitem__` delegates
     to the general, schema-unaware wrapper.
   - **`tf.schema = …` wipes every declared pin celltype back to `mixed`**, instead of preserving them
     as §4 step 3 requires.
   - **`tf.optional_pins` has no compiled guard**, so a compiled optional pin goes through the shared
     `normalize_optional_pins_for_construction` path and can be **silently dropped** — exactly the
     outcome rule 3 forbids. Whether graph import rejects a compiled node with a declared-optional pin
     is unverified; given the builder-level guard is absent, the import-time guard may be too.

3. **A Pin's `.checksum` getter has no dummy-Expression fast path.** Unlike `CellBase.checksum`
   (`cell_class.py:118-123`), `StandalonePinBackend.checksum` (`pin_class.py:86-123`) always calls
   `Expression(...).compute()`, so a `RunningLoopRefusal` is wrongly recorded as `.exception` on a Pin,
   where `contracts/cells.md` says it must not be.

4. **A call-time `Cell` argument is not converted to the pin's celltype.** `tf(x=some_cell)` falls
   through `_convert_pin_arguments` and `PreTransformation._prepare_pin_value`, neither of which has a
   `Cell` branch, reaching `_to_checksum` and being serialized as a literal — the Cell object itself.
   Pre-bound `tf.pins.x = cell` is unaffected, because `Pin.build()` already converts. No test covers
   this path.

### Feature 9 — checksum reference lifecycle

1. **A refholder-balance warning at `seamless.close()`** on a Cell/SubCell derivation path with shared
   input checksums. Internal, so it appears in no public contract page — but it looks like a real
   imbalance and nobody has traced it.

---

## 5. Misc things to do

### Documentation

- **Human documentation for all eleven features.** The agentic contract docs are complete; the
  didactic documentation is not written. We now have reactivity; interactivity and collaborative
  webservers are coming, and the human docs are what make them usable.
- **`seamless/docs/main/`** has not been touched by this work. Known stale:
  `docs/main/api/seamless-database.md` still lists BufferInfo and shows protocol 2.1 (the code is 2.2).
- **`public-api.json` does not list `seamless.checksum.*`**, so the new contract pages have no
  generated API reference. The same holds for `seamless.cell_class` and `seamless.expression_class`:
  `cells.md` and `expressions.md` have no generated API companion either. Decide whether to add those
  modules.
- **No example in any contract doc is ever executed.** The worked schema example in
  `contracts/seamless-signature-schema.md` did not parse: it carried a top-level `function_name` key,
  which `Signature.from_dict` rejects outright (`schema.py:120-122`, `TypeError: Unknown signature
  keys`), and a `/* Auto-generated from … */` comment the generator does not emit. It was wrong from
  the day it was written and nothing could have caught it. Either extract the doc examples into a
  doctest-style check, or accept that examples are illustrative and say so.
- **There is no documented route to a deep folder child's *checksum* today.** The `deep-celltypes.md`
  path rule gives `deepfolder[k] → checksum`, but every deep Expression raises
  `HashTypeValidationError` until section 2, item 3 lands; the pin route hands a transformer a dict of
  `Checksum` objects, where a checksum is not much use; and `cells.md` says any projection of a deep
  Cell raises. The one thing that *does* work — read `.value` on the deep Cell and index the raw index
  dict — is established only as an anomaly inside a status note. State it as the interim route, or say
  plainly that there is none.
- **`cache-storage-and-limits.md` never states the one hard eviction guarantee** — that referenced
  buffers are never deleted and memory pressure is reported instead. It lives only in the internal
  reference-lifecycle page, which is the one page nothing links to.
- **`compiled-pins.md` writes a fixed-size char array as `shape: [k]`.** In the signature-schema grammar
  a string entry in `shape` is a **wildcard**, so that spelling literally says the opposite of what is
  meant. Decide the right notation and correct every occurrence.
- **`DirectCompiledTransformer.__call__` resolves a `deepcell` transformer *result* through
  `unpack_deep_structure`** (`compiled_transformer.py:775-777`). That is an output-side deep path;
  `contracts/deep-celltypes.md`'s table covers the input side only, and is correct for it. Document the
  output side wherever direct-call sugar is specified.
- **`contracts/internal/checksum-reference-lifecycle.md` is linked from nothing.** It appears in
  neither `docs/agent/README.md`, `docs/agent/index.md`, `docs/agent/config/mkdocs.yml` nor
  `seamless/mkdocs.yml` — the only contract page in that state. It is deliberately internal, but an
  unreachable page is not discoverable even by the agents it is written for. Decide: link it in an
  "internal" group, or state somewhere that `contracts/internal/` is found by directory listing only.
- **`docs/agent/index.json` is generated** by `docs/agent/scripts/gen_agent_docs.py` and git-ignored
  (`.gitignore:6`), so it is in no docs commit. New entries exist on disk only, in the generator's sort
  position, which makes a regeneration a no-op. Nothing to fix; worth knowing before someone "fixes" it.

### API surface

- **`seamless.workflow` must provide `Context`, `Cell` and `Transformer`.** `Transformer` appears not
  to be exported at all. Confirmed and worse than recorded (2026-09-20): **neither `Transformer` nor
  `DirectTransformer` is in any `__all__`**, so `contracts/pins.md` specifies the behaviour of an object
  with no public import path, and **no contract page documents the Transformer builder itself**.
  `contracts/modules-and-closures.md` is in the same position: it gives the principle for embedding
  modules and no API, although `tf.modules` exists.
- **The `"code"` pseudo-pin has no inspectable handle.** Diagnosing a blocked transformer works —
  `tf.block_reason` → the named blocking pin → `tf.pins.x.source.state` — except when the blocker is
  `"code"`: `tf.pins.code` raises and `ctx.tf.code` returns the raw configured value, not a handle with
  a `.state`. The remedy (put the code in its own cell and connect it) exists but is documented nowhere
  near this symptom.

### Chores

- **Orphaned `buffer_info` table.** The dead BufferInfo placeholder was removed from seamless-database
  (the model, its `_model_classes` entry, the import, the `SeamlessBufferInfo` helper, the
  `"buffer_info"` request type and its get/put branches, the README row). No client in any repo ever
  called the endpoint, so the protocol stays 2.2. Existing database files keep an empty, orphaned
  `buffer_info` table: decide whether to add a one-off `DROP TABLE IF EXISTS buffer_info` migration or
  leave it.
- **Historical design records in `seamless/` still mention BufferInfo.** Leave them as history.

---

## Appendix A. Open design decisions

These are the decisions that are genuinely still open. Everything else that used to be in this file's
"open decisions" section was either already ruled and already in the contract docs, or turned out to be
a bug (section 4). Nothing here is stated as contract anywhere, and nothing here should be.

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

### 2. Compiled-pin celltype recording: when, not whether

Contract (`contracts/compiled-pins.md` §10) already requires compiled pins to carry their real declared
celltype instead of a blanket `mixed`, and accepts the resulting transformation-checksum churn as
correct. Options: (a) fix now — closes the rule-4 null bypass and the general "compiled pins do not
honour the declared celltype" lag in one change, at the cost of invalidating cached compiled results
whose stored pin celltype changes; (b) leave it a documented limitation indefinitely — cheap, but the
null bypass produces unclear failures in compiled pipelines until fixed. **Recommendation: (a)**, scoped
narrowly to recording the schema-derived celltype rather than a broader compiled-pin rework: the
checksum invalidation is one-time and the contract already treats it as the intended end state.

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

### 4. Where does a fingertip chain run — client, or the server that took the dispatch?

Today it runs locally in the requesting process (section 4, feature 4, bug 3). Options: (a) keep local
evaluation — simplest, but it moves potentially large recomputation onto a thin client, and it is a real
violation of the placement contract; (b) dispatch the chain to the jobserver/daskserver, matching the
contract, which needs a new server-side code path because a fingertip chain is not a single Expression,
with its own error-envelope and cancellation implications. **Recommendation: rule this explicitly and
soon.** The unbounded cost of a fingertip chain is the whole reason the Appendix B machinery is worth
building, so this is not a wording fix; it deserves the same priority as that work.

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

### 8. Is an execution record written for a run that was cancelled after it completed?

`contracts/execution-records.md` states "Canceled execution → No record" and that a cancelled run
"writes no `result_checksum` even if its dropped work later completes". The code disagrees, confirmed
2026-09-20: the record is written at `transformation_cache.py:927`, **before** the
`active_submission.canceled` check at `:934`, while `_register_transformation_result` sits after it. So
a run cancelled after completion leaves a MetaData row carrying a `result_checksum` with **no**
Transformation cache entry behind it — and a soft-cancelled jobserver job completes and records
worker-side regardless. Options: (a) the record is correct and the page is wrong — execution records are
forensic, and a run that really executed should leave a trace whatever the client later decided;
(b) the page is correct and the write must move after the cancel check. **Recommendation: (a)**, because
the record's purpose is forensic and suppressing it loses the evidence that the work happened; but then
the page must say that a record can name a `result_checksum` the Transformation cache does not hold, so
nobody treats a record as proof of a cached result. This is the one place where the cancellation and
execution-record contracts contradict each other.

### 9. Is a Python parameter default *intended* to declare an optional pin?

Confirmed in code (2026-09-20) and now documented in `contracts/pins.md`: `TransformerCore.code`
(`transformer_class.py:804-809`) seeds `self._optional_pins` from every signature parameter whose
`default is not inspect.Parameter.empty`. Two consequences follow, and neither has ever been ruled:
`def f(a, b=3)` makes `b` optional with no declaration; and because assigning `tf.optional_pins`
**replaces** the set rather than adding to it, an innocuous `tf.optional_pins = {"c"}` silently
*removes* `b`'s optionality. The companion half is that a dropped optional pin is simply not passed —
`cached_compile.exec_code:58-67` calls the function with one keyword argument per pin present in the
transformation — so Python's own default applies. Options: (a) rule it intended, and this item closes
with the documentation already written; (b) rule that optionality must be declared explicitly, and
`pins.md` changes with the code; (c) keep the signature-derived set but make `tf.optional_pins`
augment rather than replace. **Recommendation: (a) or (c)** — the signature-derived default is
genuinely convenient and matches Python's own reading, but replace-semantics on top of it is a trap.
This is the kind of rule that should be ruled rather than inherited from an implementation detail.

---

## Appendix B. Remote materialization: a waiting set with latch-on and delayed cancel

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

## Appendix C. Provenance: the design docs, and which passages are dead

The design docs of this work are listed here so a later reader can find the intent behind a contract.
**Where a design doc and the code disagree, the code wins**, and the contract docs in
`docs/agent/contracts/` are the normative statement of the code.

### Design docs added or changed during this work

- **seamless:** `a1-computing-state-argument.md`, `attachments-and-mount-design.md`,
  `attachments-and-mount-partI-implementation.md`, `cancellation-improvement-plan.md`,
  `cells-and-expression-handoff-ready-implementation-plan.md`,
  `cells-and-expressions-implementation-plan.md`, `celltype-rename-review-decisions.md`,
  `expression-where-the-data-is.md` (normative for Expression placement, and fully implemented),
  `checksum-reference-lifecycle-plan.md` (+ `-handoff-plan.md`, `-finalization-handoff-plan.md`,
  `-verification-handoff-plan.md`; the verification handoff is normative), `context-internals-design.md`
  (superseded by `-pass2.md`, in turn superseded by `-pass3.md`), `context-internals-followup-design.md`,
  `context-internals-followup-plan.md` (empty), `context-workflow-internals-implementation-plan.md`
  (+ `-handoff-plan.md`), `context-workflow-plan-vs-pass3-audit.md`, `mount-design.md`,
  `optional-pins-implementation-plan.md`. Changed: `README.md`, `RELEASE-NOTES.md`, four
  `docs/agent/contracts/` pages, four `docs/main/` pages.
- **seamless-workflow** (new repo): `README.md`, `tests/README.md`, `tests/consensus-gemini.md`,
  `tests/consensus-gpt-5.5.md`, `tests/consensus-sonnet.md`.
- **seamless-core:** `README.md` (M); `type_bits_design.md` (A, partly stale — section 4, feature 1–3,
  bug 8).
- **seamless-transformer:** `README.md` (M); `tests/cancellation/README.md` (A, and stale — section 3.3).
- **seamless-dask, seamless-database, seamless-jobserver:** `README.md` (M).

### Dead passages: do not copy these into any later document

In `mount-design.md`, whose §1–§17 is otherwise the normative design and is decision-complete:

- **§17.3's row** "clearing an `r`/`rw` cell's value stays cleared; the file is untouched". The code
  refuses with `AuthorityError("Cannot clear a mounted cell; unmount first")`, which is also what the
  doc's own preamble says. The refusal is the contract.
- **§20.3** ("resolve it through the ordinary path, which may recompute it"). The ordinary path is
  `Checksum.resolution()`, which never fingertips. A delivery resolves; it never computes.
- **§16's** "Naming is provisional" — the names are fixed by code.
- **§20.4's** proposed per-mount `rehash_interval` — never built, and not planned.

Elsewhere:

- `mount-implementation.md` gives graph format `0.3`; the code and the seamless-workflow README say `0.4`.
- `attachments-and-mount-design.md` Part II is the earlier umbrella: its §21 still discusses a `settled()`
  predicate and spells the API `ctx.mount.sync()` (singular). Both are dead; where it and `mount-design.md`
  differ, `mount-design.md` plus the code wins.
- **Every "legacy Seamless" claim** in `mount-design.md` §7.2's legacy column and in §17.2.
  `mount-implementation.md` records that legacy could not be imported in either conda environment, so the
  M1 characterization never ran. The agentic pages therefore carry no legacy comparison at all.
- `context-internals-followup-design.md`, "Bound-only observations and control": `.checksum`, `.buffer` and
  `.value` raise a deliberate bound-only error when standalone. Superseded by the standalone reads of
  `celltype-rename-review-decisions.md` §8; the code implements the new rule.
- `context-internals-followup-design.md`:348: a projection's `input_ref` is its owning root endpoint.
  Superseded — that meaning is the private `_input_ref`, and the public split is `.source` / `.checksum`
  (`Context._public_cell_source`).
- `context-internals-followup-design.md`:392-396: a join "may require a join `Transformation` followed by a
  projected `Expression`". Superseded: joins are plain local Python (section 2, item 6).

### Three design-doc statements found false against the code

Found while writing `contracts/attachments.md` and `contracts/mounts.md`; the pages document the code.

- A failed delivery's backoff retry does **not** need an external turn. `_mount_tick` is a no-op handler,
  but `FileSystemService._broker` sends one tick per active registration per poll interval, and every turn
  runs the post-turn pass — measured recovery 1.5 s after the fault was fixed, with no Context call. Only a
  driver with no tick (`ManualDriver`) needs an external turn.
- The celltype freeze and the clearing refusal fire on `node.mount` **regardless of mode**; only "the
  sensing mount is the producer, so no incoming edge" is sensing-only.
- `Context.set_graph` detaches every session with `delete=False` (`context.py:1543`), so it **never**
  deletes a `persistent=False` file — wider than `mount-design.md` §7.3, which promises this only when the
  new graph re-attaches the same path.

---

## Appendix D. Residue from the 2026-09-20 review passes

Everything below was found by the three review passes of 2026-09-20 (design decisions against the
contract docs; each feature's page for consistency and completeness, plus the pairs; and a final pass
over the whole corpus) and is **not** recorded anywhere else in this file. None of it is urgent. Each
item is here because it was deliberately *not* fixed — usually because the fix is a wording call that
belongs to the author, or because it needs a code check nobody has done.

**Fixed in flight, recorded here so the history is not lost.** These were real defects in the contract
docs and are already corrected: the cost class was described in `expressions.md` and
`deep-celltypes.md` as a function of `(input_celltype, path shape, celltype)` "never of the data behind
the checksum", while the next paragraph conditioned on checksum nullity and
`conversion_needs_buffer(checksum, …)` — it now reads "decided from checksum-level facts, not shape
alone"; `seamless-run-and-argtyping.md` documented `--strict` as a `seamless-run` flag when it exists
only on `seamless-run-transformation`; `identity-and-caching.md`, `scratch-witness-audit.md` and
`content-addressed-files-and-dirs.md` each gained the cross-reference they were missing; and
`workflow-context.md`'s cut-barrier entry was made driver-generic.

### D.1 Wording calls left to the author

1. **`expressions.md` calls one code object by two names.** §Deduplication presents
   `_active_expressions` as the membership set (contractual, present); §"Implementation status" says
   "the waiting set lives at the **Expression** layer (`_active_expressions`), not at the
   materialization site". Both sentences are true — today one object serves both roles — but a reader
   can conclude the two sets are one thing *by design*, which is exactly what section 2, item 4 exists
   to undo.
2. **`attachments.md` §Actuate lists `computing` among the non-delivering states.** An attachment only
   ever attaches to a **cell** node, and a cell node is never `computing`. A harmless superset, and the
   same shape as the defect corrected in `workflow-context.md` and `cells.md` — but whether the
   belt-and-braces is deliberate is the author's call.
3. **`attachments.md` uses "authority" in two unrelated senses**: the topology legitimacy check that
   raises `AuthorityError`, and the `AttachmentSpec.authority` field (`file` / `cell` / `file-strict`)
   that resolves the initial file-versus-cell conflict. Both faithfully mirror the code's own naming, so
   this is not a doc-invented ambiguity and was left alone; a one-line disambiguation where the second
   sense first appears would close it.
4. **`cells.md` never states what a projected Cell's `celltype` is.** `Cell._derive` carries the
   parent's `celltype` forward unchanged unless `.as_celltype()` is called. Inferable, never stated.
5. **`cells.md` states the celltype freeze on a mounted cell without saying it applies regardless of
   mode**, which `attachments.md` is explicit about.
6. **`celltypes-and-conversion.md` never names the false-negative property.** By design — `hashtype.md`
   owns it — but a reader of that page alone could take a `False` answer to be as trustworthy as a
   `True` or `None` one, which is precisely backwards.
7. **The sync/async naming convention is used across four pages and explained on none**:
   `compute`/`computation`, `resolve`/`resolution`, `sync`/`synchronization`. Both spellings of each
   pair really exist in code. One line somewhere central would pay for itself.
8. **Which page owns the *output* side of deep celltypes is undecided.** `deep-celltypes.md`'s
   "How deep values reach a transformer" is explicitly input-side and correct;
   `compiled-transformers.md` §"Result types" says a `deepcell` result is "individually
   checksum-addressed" without saying what the *caller* receives. That is a structural call, not a
   wording one — see the `DirectCompiledTransformer` item in section 5.
9. **Two residual frictions on the "optional input, mounted result directory" path.** Nothing states
   that `ctx.out = ctx.tf.result` makes `ctx.out` a `folder` cell — the reader must combine
   `workflow-context.md`'s assignment table with `cells.md`'s "copy once, at creation". And
   `mounts.md`'s "null on a directory mount is terminal" never mentions that a null `folder` result is
   impossible in the first place (`RuntimeError: Null result is not allowed for celltype 'folder'`),
   so the reader is left guarding against an unreachable trap.

### D.2 Code questions nobody has checked

10. **Does graph import reject a compiled node with a declared-optional input pin?** That is the second
    half of `compiled-pins.md` rule 3. The builder-level guard is confirmed **absent** (section 4,
    feature 7, bug 2), which makes it likely the import-time guard is absent too — but the
    seamless-workflow graph-import path was never read. Worth ten minutes.
11. **`session.leaf_leases` looks dead.** `attachments/session.py:89` is always empty in practice and is
    released in `runtime.py:293`'s `_mount_detach`, which makes that release a no-op. The real leaf
    retention lives in `Context._mount_node_leaves`, keyed by node path, and is correct. Either the
    field is vestigial and should go, or something was meant to populate it.

### D.3 One more `.buffer` / `.value` asymmetry

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
