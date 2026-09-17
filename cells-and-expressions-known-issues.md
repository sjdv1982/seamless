# Known issues: cells-and-expressions

Code problems, documentation gaps, open decisions, and items still to verify, found on 2026-09-17
while updating the docs after the cells-and-expressions work. This file is the starting point for
continuing that work. Contents:

1. Where we are: goal, progress, uncommitted work, the feature list
2. Open decisions
3. Celltypes, conversion, HashType: bugs, inaccuracies, stale text (features 1–3)
4. Compiled-transformer pins bypass the required-pin null check (feature 7)
5. To verify against code: Expression placement (feature 4)
6. Expression cancellation (feature 4)
7. Cell-level joins (feature 10)
8. Documentation gap: checksum reference lifecycle (feature 9)
9. BufferInfo removal: follow-ups
10. Design-doc limitations not yet verified against code (features 4, 8, 10, 11)
11. Question log (Q1–Q12) and gap-analysis notes
12. Source list: design docs changed during the cells-and-expressions work

The celltype/conversion/HashType bugs (section 3) are not being worked on; the agentic docs
describe the current behaviour and list them as limitations. For the other sections, nothing has
been decided about fixing them yet (cell-level joins have a follow-up design by the author).

## 1. Where we are

### Goal and approach

- Seamless is alpha. The goal is to bring the docs up to date with the current code, not to
  attribute changes to branches or dates.
- Start with the agentic docs in `seamless/docs/agent/` (precision over didactics), then the main
  docs (`seamless/docs/main/`).
- Work feature by feature through the list below. Check claims against code or tests where
  in doubt.
- Implementation on the branch is finished (last work: mounts, Cell API, null values outside
  pins). Docs for features 4 onward must be written from the final code.

### Sources and their authority

- The feature list below is sufficient as the basis for the contract docs: it has the full
  feature inventory, the dependency structure, and the status of each feature. The ~58 KB
  summary of the changed design docs, which the list was partly derived from, was deliberately
  not kept. It is second-hand, and it was already wrong in several places (section 11); some
  design docs behind it describe superseded passes.
- Caveat: the list says *which* features exist, not every contract detail within them (for
  example the six `.state` values, barrier timeout semantics, the full old → new renames table).
  For those details:
  - the **code** is the primary source;
  - the **design docs** (section 12) are only a guide to intent and may be stale;
  - where design docs and code may disagree, see the unverified limitations in section 10.
    Where they disagree, ask the user.

### Progress

- Features 1–3: agentic docs written and checked against code:
  - new `docs/agent/contracts/celltypes-and-conversion.md`;
  - new `docs/agent/contracts/hashtype.md`;
  - short section added to `docs/agent/contracts/identity-and-caching.md`;
  - both pages linked from `docs/agent/README.md`, `docs/agent/index.md`,
    `docs/agent/config/mkdocs.yml`, and `seamless/mkdocs.yml`.
- The null section of `celltypes-and-conversion.md` was re-checked against the final code
  (after the last null-value implementation work) and still holds: `b"null\n"` canonical,
  `b"null"` read as null but a distinct identity, empty bytes → null only for celltype `bytes`,
  null reads as `b""` for `bytes` and `None` otherwise, `str()` = `"NULL"`, `convert_checksum`
  does not special-case null → `checksum` while empty-path Expression evaluation short-circuits
  null.
- Features 4–11: not started.

### Work status

After the first version of the current doc was built, all work was merged into main. 

### Feature list (current understanding)

Dependency-ordered: each item builds on earlier ones. This integrates the author's original
8-item list, the Opus gap analysis of the design-doc summary, and the later findings (Q1–Q12,
section 11). Details marked *(design docs)* come from the summary of the design docs and have
not been checked against the final code; check them when writing each feature's docs.
Status keys: **delivered**, **delivered (gaps)**, **deferred**, **open**, **rejected**.

1. **Type hierarchy (celltypes)** — a *checksum* hierarchy, not a value hierarchy:
   subtype → supertype means any checksum valid as the subtype is valid, unchanged, as the
   supertype. "Deserializable as X" means the reference parser accepts it, not that it
   round-trips to the same checksum; one value may have several checksums, and identity stays
   with the checksum. Canonical null `b"null\n"`; null/true/false are checksum-level virtual
   values. Defined by the rule table in `seamless-core/seamless/checksum/conversion.py`.
   Contract: `str(null checksum) == "NULL"`; machine formats use `.hex()`.
   Status: delivered. Docs done.
2. **HashType** — on top of 1: a total, packed classification of a checksum, replacing
   BufferInfo (now removed everywhere, section 9). Two purposes: (a) detect impossible
   deserialization at checksum level; (b) expression capability: which path steps
   (SEQ/MAP, rank) the root structure admits. One-sided error: never rejects valid work
   (but see bug 1), may answer "maybe" (`None`). Stored words only tighten; stored locally and in
   the seamless-database `hash_type` table. Query: `conversion_feasible` (True/False/None).
   Status: delivered (gaps: section 3). Docs done.
3. **Conversion engine** — on top of 1, using 2: ported from legacy Seamless. Defining
   feature: no value-level work unless necessary, exploiting the type hierarchy and HashType
   entries (checksum → buffer → value). Scalars are readings of JSON-compatible buffers
   (int↔float and scalar→str keep the checksum; an int reading of `4.5` gives `4`). Buffer-level
   conversion results are cached as empty-path Expressions, so 3 and 4 are entangled.
   Status: delivered. Docs done.
4. **Expressions** — on top of 3, using 2: the structural, immutable counterpart of
   Transformation: a closed, pure codebook (get-attr, get-item, slice, celltype conversion)
   with no execution environment *(design docs)*.
   - Expressions and Transformations share one lazy, content-addressed DAG; expression futures
     can feed transformation pins and vice versa *(design docs)*.
   - Over a deep checksum, a path selects a sub-checksum without materializing the parent
     *(design docs)*.
   - Identity = (input_checksum, path, input_celltype, celltype); also the reverse index that
     fingertipping walks *(design docs)*.
   - Evaluated where the data is (`execution="auto"`: local, or jobserver `run_expression`);
     claimed exceptions to verify in section 5.
   - Cancellation: implemented, with gaps (section 6).
   - Contract: seamless-database protocol 2.2 (column renames + migration) *(design docs)*.
   - Deferred: validators (reject-only semantics settled). Open: forensic
     "irreproducible expression" analogue *(design docs)*.
5. **Cells as delayed Expressions** — on top of 4: a Cell is the mutable builder; it holds an
   input (literal/checksum) or builds an Expression over a `.source`, as a Transformer builds a
   Transformation. Navigation returns projection Cells *(design docs)*.
   - Shared CellBase read API: `.source`, `.checksum`, `.buffer`, `.value`, `.state` (6 values)
     + `.block_reason`, `.exception` / `clear_exception()` *(design docs)*.
   - Standalone reads: a getter evaluates its own cheap expression but never runs a source;
     `.value` never fingertips; `.compute()` does the work.
   - Contract (renames): `celltype` = output type; read-only `input_celltype`;
     `target_celltype`, `input_ref` retired; `.status` → `.state`; `.set()` takes values only; a
     Checksum is a value only for celltype `checksum`; None is a value and `del` is the only
     deletion; retired names raise with a pointer to the replacement. The docs should contain
     one consolidated old → new table.
   - Deferred: Cell validators *(design docs)*.
   - Status: Cell API just finalized; document from the final code.
6. **Optional pins** — transformer-construction substrate, below the Context.
   `Transformer.optional_pins` is a settable set of pin names. Canonical null on an optional
   pin = absence, for any celltype: unconnected and connected-then-null give the same
   transformation checksum (the pin is dropped before the checksum is computed). Connected
   optional pins still compute, and a failing optional upstream still fails.
   Contract: transformation-checksum identity rule. Status: delivered. Settled.
7. **Transformer and pins sharpened** — mostly a consequence of 3, 5, 6; the pin-sugar removal
   was driven by the Context's name-collision problem.
   - Pin: sister class of Cell (shared CellBase); a Pin can't be a source.
   - `tf.pins.x` is the only pin path (`tf.x` / `tf["x"]` sugar removed); one producer per pin;
     out-of-signature names rejected for Python callables; `result` is never a valid pin name;
     `del` only for signatureless code *(design docs)*.
   - `pin.celltype` is the same setting as `tf.celltypes.x`; pin celltype conversion is shared
     by reactive and snapshot runs; a failed conversion gives blocked-by-error before a
     Transformation is built.
   - Null: on a required pin, null raises `TypeError`, except for celltypes `plain`, `mixed`,
     `bytes` (verified in code). Compiled transformers bypass this (section 4).
   - Status: delivered (gap: compiled pins recorded as `mixed`).
8. **Cancellation substrate** — base layer for 4, 7, 10 *(design docs)*.
   - One membership set per dedup site (in-process / jobserver / Dask).
   - `softcancel` = deregister; the run is cancelled only when the set is empty. `cancel` = hard
     kill of every member. Softness cascades; a real kill happens only at the leaf set.
   - Cross-process liveness deliberately not built. The reactive scheduler uses softcancel only;
     CLI/SIGINT stays hard.
   - Contract: replaces first-caller-owns-execution; jobserver multi-tenant footgun fixed.
   - Status: delivered (gaps to verify, section 10). Expression cancellation: section 6.
9. **Checksum reference lifecycle** — internal. Refholders (Cell, Expression,
   Transformer/Transformation, Context current/superseded runs) keep checksum buffers alive;
   refholder claims counted separately from manual incref/decref; public vs internal interest
   is a hard rule; scratch and deep checksums have own rules; balance audit at
   `seamless.close()` (user-visible only as `seamless.references` warnings). The Context's
   `current` / `superseded:<generation>` roles back feature 10's grace holds.
   Needs its own doc in seamless-workflow (section 8).
10. **Reactive workflow (seamless-workflow Context)** — rests on 4 and Transformations, with
    Cells (5) and Transformers/Pins (7) as its handles, using 2, 6, 8, 9. The Context holds a
    DAG of nodes and builds private Expression/Transformation snapshots each tick; `ctx.a` /
    `ctx.tf` are views (one canonical handle type); on binding, a Cell's builder state moves
    into the Context.
    - The **node state lifecycle** must be documented extensively (do not confuse with 9):
      six-state node machine with a glitch-free cascade; speculative supersession with grace
      holds (at most 3 superseded runs per node), `ctx.prune()`.
    - Controller: one thread per Context, sole mutator, sequenced ingress, poison on internal
      failure, `Context.close()`.
    - Barriers (compute/computation) with timeouts; contract: barrier timeout raises
      `TimeoutError`.
    - Contract: deep value assignment is legal; a connection may go at most one level below the
      root; legacy `ctx.tf.x` sugar gone.
    - Checksum writes are HashType-validated.
    - Cell-level joins: section 7.
    - Status: Part I (A0–A5) delivered. Deferred / open / unratified / rejected items: section 10
      *(design docs)*.
11. **Attachments and mounts** — on top of 10. Attachment framework: sense = authoritative
    write; actuate = delivery after a turn; durable spec plus ephemeral session; a manual test
    driver. File mounts are the only production driver: global watch broker + I/O pool; atomic,
    conditional writes; null files read as null and deliver as truncation; mounts never give up;
    oscillation detector; `ctx.mounts.sync()` *(design docs)*. Use "attachment" and "mount"
    precisely in the docs.
    Status: implemented and tested (confirmed by author); last implementation work was on
    mounts, so document from the final code. Open items / v1 exclusions: section 10.

**Also in scope** (if they reflect current code; not part of the dependency chain):

- A. Transformation core (RELEASE-NOTES v1.4): immutable definition vs mutable promise;
  dunders reclassified (`__meta__` / `__env__` out of identity, `__schema__` in for compiled — an
  intentional cache break); latch-on default vs `--strict` / `strict_dunder`; checksum-addressed
  cancellation API; `seamless-run-transformation` replay CLI; `.zst` / `.gz` checksumming fix.
  These sit below 4 and 8.
- B. Operational contract clarifications (not features): remote execution requires a shared
  hashserver + database; environment fingerprints come from manual probes (conda-cache refresh
  exception); remote-http-launcher debug logging; caching masks nondeterminism; fingertipping
  defined as distinct from scratch (relevant to 4/5: reverse index; `.value` never fingertips).

**Supporting work, not features** (the docs may point to them as executable contract):
seamless-workflow A0 contract suite (folded from `claude/` + `codex/`; `tests/claude/` retired);
black-box cancellation suite (`seamless-transformer/tests/cancellation`, xfail-tracked);
legacy-mining of ~296 characterization scripts.

## 2. Open decisions

1. **Compiled-transformer null gap** (section 4): fix in code (changes transformation checksums)
   or document as a limitation?
2. **Orphaned `buffer_info` table** (section 9): add a one-off `DROP TABLE IF EXISTS buffer_info`
   step for existing database files, or leave the empty table?
3. **`public-api.json`**: it does not list `seamless.checksum.*`, so the new contract pages have
   no generated API reference. Add those modules or not?
4. **Cell-level joins** (section 7): how to document them now — suggestion: document observable
   behaviour (node states, no transformation checksum) and not the implementation, since the
   follow-up design will change it.
5. **Section 10 limitations**: verify each against code now, or record them as limitations while
   writing the docs for each feature?
6. **Evidence tests**: the Q7/Q8 test scripts were not kept in any repo; decide whether
   repo tests should be written for Expression cancellation and cell-level joins.

## 3. Celltypes, conversion, HashType (features 1–3)

Repo: seamless-core.

### Bugs

#### 1. `X → checksum` violates the HashType no-false-rejection rule (reproduced)

- `convert_checksum` accepts any valid source for a conversion to celltype `checksum` and
  returns the source's own checksum.
- `conversion_feasible` (in `seamless.checksum.hash_type_validation`) returns `False` for
  `→ checksum` unless the source is 64 bytes of raw text.
- As a result, `evaluate_expression(cs, "", "plain", "checksum")` raises
  `HashTypeValidationError`, although the conversion engine itself would succeed.
- HashType is contracted to have only false negatives ("maybe"), never false rejections.

#### 2. `_parse_buffer` crashes inside a running event loop (reproduced)

- Inside a running event loop, `ensure_hash_type` returns `None` right after the local cache
  and skips both the database and any buffer it was given.
- If the local cache has no HashType for the checksum, `_parse_buffer` then fails with a
  bare `AssertionError`.

#### 3. `checksum → X` is not validated

Converting from celltype `checksum` returns the referenced checksum without checking it
against the target celltype X.

### Classification inaccuracies (HashType)

#### 4. `true` / `false` / `null` are classified as `JSON_STRING`

Path validation therefore treats them as sequences. This is too permissive, but it never
rejects valid work.

#### 5. `deserializable_as("bool")` without a checksum returns `False` for everything

#### 6. Chain conversions are never ruled out

`conversion_feasible` returns `None` for every pair in `conversion_chain`.

### Value-level inconsistencies

#### 7. `str` spelling of booleans is not symmetric

Reading the `true` buffer as `str` gives `"True"`, but serializing `True` as `str` writes
`true\n`.

#### 8. Large integers lose precision

orjson turns integers beyond 64 bits into floats, so `int` and `plain` readings lose
precision.

#### 9. `bytes` reading returns inconsistent types

Re-checked against the final code (2026-09-17): still present.

A non-null reading as `bytes` returns a `Buffer` object; the null reading returns `b""`.

### Unused features / stale text

#### 10. Features nothing uses

Nothing produces the HashType "untested" kinds or the `SEMANTIC` flag.

#### 11. Stale comment in `convert._value_of`

The comment says a missing cached HashType makes validation a no-op, but outside a running
event loop, validation can query the database.

#### 12. Stale "deep hash patterns" docstring in `seamless/checksum/conversion.py`

Deep celltypes (`deepcell`, `deepfolder`, `folder`, `module`) are distinct celltypes
serialized and parsed as `plain` (`Buffer._map_celltype`), not legacy hash patterns.

#### 13. `type_bits_design.md` is out of date

- §13 describes HashType database tightening as pending; it is implemented and tested.
- §8.3 says "cheap peek, never json.loads"; `from_buffer` runs a full `orjson.loads`.

## 4. Compiled-transformer pins bypass the required-pin null check (feature 7)

Repo: seamless-transformer. This is about transformer pins (feature 7), not the type/conversion
layer, but it rests on the same celltype rules.

- The pin null rule lives in `validate_pin_null` (`seamless_transformer/transformation_utils.py`):
  - on an optional pin, canonical null means absence, for any celltype
    (`normalize_optional_pins_for_construction` drops the pin before the checksum is computed);
  - on a required pin, null raises `TypeError`, except when the pin's celltype is `plain`, `mixed`,
    or `bytes`.
- Compiled transformers set every input pin to celltype `mixed`, whatever the schema declares
  (`compiled_transformer.py`, `self._celltypes = {parameter.name: "mixed" ...}`;
  `pretransformation.py`, `pretransformation_dict[pinname] = ("mixed", None, value)`).
- As a result, null on a required compiled input declared e.g. `float` in the schema gets past
  every pin-level check, becomes Python `None` (`compiled_transformer.py`, prepared-value
  resolution), and reaches C argument marshalling. The resulting failure is not traced; it is
  probably a late or unclear error instead of the pin-level `TypeError`.
- Known open item: "compiled transformers record every pin as mixed" was left open because fixing
  it changes transformation checksums.
- Test coverage: `seamless-workflow/tests/correctness/test_correctness_compiled.py` covers a null
  *result*, but no test sends null into a compiled *input*.

## 5. To verify against code: Expression placement (`execution="auto"`, feature 4)

Feature 4 (Expressions) is documented as "evaluated where the data is": with `execution="auto"`,
an Expression is evaluated locally or through the jobserver's `run_expression`. A doc summary
made the claims below. They are probably inaccuracies in that summary, but nobody has checked
them against the code yet.

- The sync and async evaluation paths mean different things by "local".
- With no jobserver configured, `"auto"` has no fallback (e.g. to the hashserver).
- Standalone `compute()` bypasses `"auto"`.
- Expression inputs to transformations bypass `"auto"`.
- Expression errors lose their exception type when they come back from the jobserver.

Note: seamless-core has recent commits that may already address some of these:
`108a1f1` "Keep expression error types, resolve run() results, test undone results" (2026-09-15)
and `8e00718` "Expressions execute where the data is" (2026-09-17).

## 6. Expression cancellation (feature 4): implemented, with gaps

Verified by code inspection (2026-09-17), plus evidence tests (4 passing) that were not kept
in any repo (see open decision 6).

The old `NotImplementedError` stub is gone. Remaining `NotImplementedError`s in
`seamless-core/seamless/checksum/expression.py` gate validators, not cancellation.

What works:
- Jobserver path: `Expression.cancel()` aborts the in-flight `run_expression` request (tested).
  With two members, softcancel of one keeps the run alive and the survivor gets the result (tested).
- Local path: cancelling the awaiting asyncio task interrupts a blocked buffer resolution (tested).
- Workflow: on node supersession, the Context cancels the job and softcancels the Expression
  (`seamless-workflow/seamless_workflow/context.py`, `_demand`). `Context` close cancels all
  outstanding jobs.

Gaps:
1. `Expression.cancel()` is a no-op for local in-flight evaluations. `evaluate_expression_async`
   registers members under a 7-tuple key `("local", checksum, path, input_celltype, celltype,
   validator, validator_language)`. `cancel_expression` looks up the 4-tuple `_cache_key`
   `(checksum, path, input_celltype, celltype)`. Confirmed by test: `cancel()` returns `False` and
   the evaluation keeps running.
2. No hard cancel for Expressions. `cancel_expression` is an alias of `softcancel_expression`;
   there is no counterpart of `TransformationCache.cancel_by_checksum`.
3. Dask-dispatched Expressions can't be interrupted mid-flight. `dispatch_expression`
   (`seamless-transformer/seamless_transformer/worker.py`) awaits
   `asyncio.to_thread(thin.result)` and never cancels the Dask future. Found by inspection only;
   testing it needs a live Dask cluster.
4. No repo test covers Expression cancellation.

## 7. Cell-level joins (feature 10): not (yet) ordinary transformations

Verified by testing only (2026-09-17): 6 evidence tests passing, stable over two runs, not kept
in any repo (see open decision 6).

A join is a Cell with several producers: a root value and/or one-level subpath connections, e.g.
`ctx.join = {}; ctx.join.left = ctx.left; ctx.join.right = ctx.right`. This pattern is also
used in `seamless-workflow/tests/correctness/test_correctness_fanin.py`.

Behaves as expected:
- the value is correct;
- it recomputes reactively when an upstream cell changes;
- reverting an upstream gives the same checksum again;
- a failed upstream leaves the join `blocked` / `blocked-by-error`, not `failed`.

Understood design (author): provisionally implemented as ordinary transformations, with a
follow-up design pending. Observed behaviour, compared with a control Transformer in the same
Context:
- 0 entries in the transformation observation log, vs. 1 for the Transformer;
- the transformation cache doesn't grow, vs. +1 for the Transformer;
- state goes straight from `waiting` to `complete`, never `computing`, while a slow control
  Transformer is observed in `computing`.

Open: the test can't distinguish "assembled directly in the Context, no Transformation" from
"an internally built Transformation that bypasses Transformer instrumentation and the
transformation cache". A short look at the join code path would settle it.

## 8. Documentation gap: checksum reference lifecycle (feature 9)

The checksum reference lifecycle (refholders that keep checksum buffers alive; refholder claims
vs. manual incref/decref; scratch and deep-checksum rules; balance audit at `seamless.close()`)
is internal and stays out of the public agentic contracts in `seamless/docs/agent/`. It still
needs its own doc, and that doc belongs in the seamless-workflow repo.

Do not confuse it with the workflow node state lifecycle (node state machine, cascade,
supersession, grace holds). That lifecycle is user-visible and must be documented extensively in
the agentic docs.

## 9. BufferInfo removal: follow-ups

The dead BufferInfo placeholder (never filled by any modern seamless-database) was removed from
seamless-database (branch `cells-and-expressions`, uncommitted): the `BufferInfo` model and its
`_model_classes` entry (`database_models.py`); the import, `SeamlessBufferInfo` helper,
`"buffer_info"` request type and its get/put branches (`database.py`); the README row. No client
in any repo called the endpoint. `hash_type` is untouched. Protocol stays `2.2` (no bump seems
needed, since no client ever used the request type). `docs/agent/contracts/hashtype.md` no longer
mentions the legacy table.

Follow-ups:
- Existing database files keep an empty, orphaned `buffer_info` table (open decision 2).
- `seamless/docs/main/api/seamless-database.md` is stale: it still lists BufferInfo and shows
  protocol 2.1 (code: 2.2). Fix during the main-docs update.
- `seamless-database/tests/test_hash_type_tightening.py::test_server_and_local_cache_agree[10-11-replace]`
  fails, before and after the removal, with `AttributeError: module
  'seamless_remote.database_remote' has no attribute 'set_hash_type'` (raised from
  `seamless-core/seamless/caching/buffer_writer.py`). `set_hash_type` exists in the
  seamless-remote source, so a stale installed copy or the then-ongoing implementation is the
  likely cause. Not confirmed; re-run in the `seamless1` conda env.
- Historical design records in `seamless/` still mention BufferInfo; leave as history.

## 10. Design-doc limitations not yet verified against code

These come from the design docs (via the doc summary). They were not discussed or checked. Each
must be verified before it goes into the docs as a limitation (open decision 5).

Cancellation substrate (feature 8):
- Two xfail-tracked gaps: the jobserver does not cascade a softcancel down to the leaf
  (considered harmless); on Dask, when the first runner leaves, jobs that joined it are killed
  (not harmless).
- A jobserver cancel does not free the worker slot.

Expressions (feature 4):
- Validators: reject-only contract settled, implementation deferred (the remaining
  `NotImplementedError`s in `expression.py` gate validators).
- A forensic "irreproducible expression" analogue: open.

Workflow Context (feature 10):
- Deferred: fire-and-forget; future-wiring (v1 is checksum-wired only).
- Open: Part IV dependency-declaration contract.
- Unratified / out of scope: subcontexts, non-eager mode, activation leases.
- Rejected (document as non-features if useful): transient-failure state, mandatory preemption,
  epoch-stamping.

Mounts (feature 11):
- Open: w-mode reassert timing, network-filesystem fingerprints, resource limits, directory leaf
  retention.
- Not in v1: standalone, sub-path, and pin mounts; `edit_policy="external-owned"`.

## 11. Question log and gap-analysis notes

### Questions raised on the original feature list

| Q | Question | Resolution |
|---|----------|------------|
| 1 | Null on pins | Code: optional pin → null = absence (any celltype); required pin → `TypeError` except `plain`/`mixed`/`bytes`. Compiled gap: section 4. |
| 2 | Source of the type hierarchy | The rule table in `seamless-core/seamless/checksum/conversion.py`, sharpened to make checksum-level hierarchies explicit. |
| 3 | "Ported from legacy" | Code port; defining feature is avoiding value-level conversion via hierarchy + HashType. |
| 4 | seamless-workflow provenance | Moot: goal is current docs, not attribution. |
| 5 | Mounts implemented? | Yes, implemented and tested (author). |
| 6 | Scope of adjacent v1.4 / backend changes | Moot: in scope if they reflect current code. |
| 7 | Expression cancellation | Implemented with gaps (section 6). |
| 8 | Cell-level joins | Author: provisionally ordinary transformations; testing suggests otherwise (section 7). |
| 9 | `int` parser vs "integrality" | `4.5` → `4` accepted; `float→int` is trivial; no integrality check. |
| 10 | Expression placement exceptions | Probably summary inaccuracies; to verify (section 5). |
| 11 | Optional-pin API | `Transformer.optional_pins` (settable set of names). Settled. |
| 12 | Checksum reference lifecycle | Internal; own doc in seamless-workflow; not to be confused with node state lifecycle. |

### Gap-analysis notes still relevant for writing docs

- **Ordering vs the author's original list:** HashType before conversion (conversion is a
  HashType query); Transformer/pins before the Context (its technical dependencies are all
  earlier; the Context only motivated the sugar removal); three substrates below the Context
  (optional pins, cancellation, reference lifecycle). Original order 1–8 became
  1, 3, 2, 4, 5, [6], 7, [8], [9], 6→10, 8→11.
- **Context vs Cells:** the Context runtime does not hold Cells or Expressions; Cells and
  Transformers are views onto nodes. Describe the Context as resting on Expressions and
  Transformations, with Cells/Transformers as handles.
- **Renames are API changes, not features:** document them in the feature they affect, plus one
  consolidated old → new table (earlier design docs cite it as "Superseded API names"). Any doc
  that says "celltype/target_celltype" uses superseded draft naming.
- **Dunder reclassification** is a cache-breaking identity change; better over-documented than
  missing.
- **Rejected alternatives** (transient-failure state, mandatory preemption, epoch-stamping) should
  not appear in the docs as planned features.
- **Summary inaccuracies found so far** (so the design docs, too, may be stale in places):
  `convertible_to` does not exist (it is `conversion_feasible`); expression-result HashType *is*
  stored; the database is skipped only inside a running event loop; optional-pin drop-on-null
  works for every celltype, not only plain/mixed/bytes; a required pin cannot hold null (except
  plain/mixed/bytes).

## 12. Source list: design docs changed during the cells-and-expressions work

All `.md` files added (A) or changed (M) since 2026-06-08 16:59 +0200, the earliest inception
date of the cells-and-expressions work (commit `4ad38fe0` in seamless, "Cells and expressions
plan"). Refs: seamless and seamless-workflow `main`; the other repos `cells-and-expressions`.
A summary can be regenerated from these (for changed files, read only the diff since that date).
Where they disagree with the code, the code wins.

- **seamless:**
  - M: `README.md`, `RELEASE-NOTES.md`, `docs/agent/contracts/execution-backends.md`,
    `docs/agent/contracts/execution-records.md`, `docs/agent/contracts/identity-and-caching.md`,
    `docs/agent/contracts/scratch-witness-audit.md`, `docs/main/api/remote-http-launcher.md`,
    `docs/main/api/seamless-jobserver.md`, `docs/main/api/seamless-transformer.md`,
    `docs/main/sharing.md`
  - A: `a1-computing-state-argument.md`, `attachments-and-mount-design.md`,
    `attachments-and-mount-partI-implementation.md`, `cancellation-improvement-plan.md`,
    `cells-and-expression-handoff-ready-implementation-plan.md`,
    `cells-and-expressions-implementation-plan.md`, `celltype-rename-review-decisions.md`,
    `checksum-reference-lifecycle-plan.md` (+ `-handoff-plan.md`,
    `-finalization-handoff-plan.md`, `-verification-handoff-plan.md`; the verification handoff is
    normative), `context-internals-design.md` (superseded by `-pass2.md`, in turn superseded by
    `-pass3.md`), `context-internals-followup-design.md`, `context-internals-followup-plan.md`
    (empty), `context-workflow-internals-implementation-plan.md` (+ `-handoff-plan.md`),
    `context-workflow-plan-vs-pass3-audit.md`, `mount-design.md`,
    `optional-pins-implementation-plan.md`
- **seamless-workflow** (new repo): `README.md`, `tests/README.md`, `tests/consensus-gemini.md`,
  `tests/consensus-gpt-5.5.md`, `tests/consensus-sonnet.md` (`tests/claude/README.md` no longer
  exists)
- **seamless-core:** M `README.md`; A `type_bits_design.md` (partly stale, bug 13)
- **seamless-transformer:** M `README.md`; A `tests/cancellation/README.md`
- **seamless-dask, seamless-database, seamless-jobserver:** M `README.md`

## 13. The jupyter-sync branch is to be merged.

## 14. Review of `hashtype.md` "Current limitations" (2026-09-17)

Each item in the "Current limitations" section of `docs/agent/contracts/hashtype.md` was checked
against the code (L1–L7 below, in that section's order). L2–L4 were first analysed by independent
agents; the key claims were then re-checked by experiment (conda env `seamless1`, run from outside
the workspace root; scripts not kept). Six of the seven items are already in section 3 under
other names:

| `hashtype.md` limitation | Section 3 | Verdict |
|---|---|---|
| L1. `X→checksum` breaks the false-negative property | bug 1 | Confirmed; a plain bug |
| L2. Sync lookup inside a running event loop | bug 2 (and item 11) | Accurate; low severity |
| L3. `deserializable_as("bool")` without `checksum=` | item 5 | Accurate but latent; also affects null |
| L4. JSON `true`/`false`/`null` classified `JSON_STRING` | item 4 | Understated; leads to new finding L4b |
| L5. Chains are never disproved | item 6 | Confirmed; worth fixing |
| L6. Untested kinds and `SEMANTIC` have no producer | item 10 (and item 13) | Keep untested kinds; `SEMANTIC` is broken |
| L7. Syntax and hex validity not encoded in the word | — | A non-goal, not a limitation |

New findings, not in section 3: **L4b**, a family of false rejections for `int`/`float` targets;
an engine bug that writes non-finite floats as `null` (under L4b); the `SEMANTIC` contradiction
(L6).

> **`docs/agent/contracts/hashtype.md` will have to be updated once these issues are settled**
> (fixed, or accepted as limitations). Today it presents L1 as the only break of the false-negative
> property and says the L4 classification never rejects valid work; L4b contradicts both. See
> "Documentation follow-up" at the end of this section.

### L1. `X → checksum` (= section 3, bug 1)

- Confirmed end to end: `Expression(cs, "", input_celltype="plain", celltype="checksum").compute()`
  raises `HashTypeValidationError`, while `convert_checksum` returns the source's own digest. Same
  for `str`, `int` and `mixed` sources.
- Cause: `_value_conversion_feasible` (`hash_type_validation.py`) returns `True` only for
  `RAW_TEXT` + `EQ64`, as if the source were parsed as a hex string. The engine
  (`convert._convert_values`) does not do that. The rule is wrong even on its own terms: an
  all-digit digest is classified `JSON_NUMBER`.
- Proposed fix: return `True` for a `checksum` target. `conversion_feasible` has already returned
  `False` for a source that is not deserializable as its celltype. The engine does not check
  that, but rejecting invalid input is allowed.

### L2. Sync lookup inside a running event loop (= section 3, bug 2)

- All claims reproduced, including the bare `AssertionError` from `_parse_buffer` and
  `parse_buffer_sync` inside `asyncio.run` when the local cache has no word.
- "Normally this does not happen" holds for the public API. `Buffer(..., checksum=...)`,
  `Buffer.get_checksum[_async]` and the remote buffer clients (which verify a fetched buffer by
  recomputing its checksum) all register the word, and the local cache is never evicted.
- Unregistered buffers do exist internally:
  - `convert._coerce_buffer` wraps raw bytes from `get_buffer` without `checksum=`; its only
    production caller passes registered `Buffer`s;
  - `expression._get_local_buffer` returns `Buffer(trivial)` for the 11 `TRIVIAL_CHECKSUMS`, none
    of which is registered at import. `_parse_buffer` on those (`{}`, `[]`, `""`, ...) inside a
    running loop raises the `AssertionError`. Through `Expression.compute_async()` it did not
    trigger, because expression validation registers the word first.
- Missing from `hashtype.md`: the async `parse_buffer` calls the sync `_parse_buffer`, so async
  code always takes the running-loop branch, and its parse-time validation never consults the
  database.
- Running-loop callers that pass no buffer (`transformation_class.py`, reached from
  `constructor_async`; `convert._value_of` via `conversion_needs_buffer`) only lose an early
  rejection. This never rejects valid work.
- Proposed fix: in `ensure_hash_type`, classify a supplied buffer before the running-loop check
  (pure CPU plus a non-blocking upload enqueue), and replace the assert in `_parse_buffer` with a
  real error. Rewrite the stale `_value_of` comment (item 11) at the same time.
- Not recommended: querying the database from a worker thread, as `Checksum.resolve` does.
  Without a buffer it only gains an earlier rejection that the parser makes anyway after the
  fetch, and it blocks the loop thread on network I/O.

### L3. `deserializable_as("bool")` without a checksum (= section 3, item 5)

- Confirmed: the `bool` rule runs before the untested-kinds rule, so every word gives `False`.
- Latent: every production caller passes the checksum. `validate_deserializable_as` takes it as a
  required argument, and `conversion_feasible` is only called from `validate_expression[_async]`,
  which pass it.
- The rule itself is sound. `bool` parsing accepts exactly the four canonical buffers (`true`,
  `true\n`, `false`, `false\n`) plus null, and rejects `1`, `True`, `" true "` and a NumPy bool.
- Understated: the null rule also needs `checksum=`. Without it, the `null\n` word
  (`JSON_STRING`, no flags) gives `False` for `int`, `float`, `binary`, `checksum` and `bool`
  (reproduced).
- Proposed fix: make `checksum` keyword-only with no default in `deserializable_as` and
  `conversion_feasible`. Returning `None` when it is missing would also be sound, but would hide
  caller mistakes. Encoding "is a boolean" in the word adds nothing over the exact checksum check.

### L4. `true` / `false` / `null` classified as `JSON_STRING` (= section 3, item 4)

- Classification confirmed, also for whitespace-padded variants. `capabilities("plain")` and
  `capabilities("mixed")` give `{"SEQ"}`, `has_string_items` gives `True`, `has_numeric_items`
  gives `False`. Only path validation consumes these, and there they are merely too permissive.
- But the classification (no `NUMERIC_SCALAR`) does cause false rejections: the first row of the
  L4b table.

#### L4b. `int` / `float` targets: false rejections (new)

`_possible_conversion_feasible` (`hash_type_validation.py`) assumes an `int`/`float` target needs
a numeric value: `NUMERIC_SCALAR`, or a numeric scalar NumPy word for a `binary` source, and never
a `LONG` buffer. The engine (`convert._convert_possible`) applies `builtins.int` /
`builtins.float` to any scalar value, as `celltypes-and-conversion.md` documents. Reproduced, with
`conversion_feasible` returning `False`, the engine succeeding, and `Expression.compute()` raising
`HashTypeValidationError`:

| Case | Engine result |
|---|---|
| `mixed→int` / `mixed→float` on JSON `true`, `false`, `" true "` | `1`, `0` / `1.0`, `0.0` |
| `mixed→float` on a 0-d NumPy `float64`, `int64` or `bool` | `5.0` etc. (`binary→float` on the same checksum passes) |
| `binary→float` / `mixed→float` on a 0-d NumPy `S` or `U` array holding `"5"` / `"5.5"` | `5.0` / `5.5` |
| `mixed→float` on a JSON number longer than 1000 bytes (`5.000…0`) | `5.0` |
| `mixed→float` on the JSON string `"inf"` | `null\n` |

- The last row is also an engine bug: a non-finite float is written as `null` instead of raising.
- Proposed fix, on the HashType side. Seamless already allows bool→int (`conversion_values`) and
  numeric-string→float (`NUMERIC_SCALAR` on `JSON_STRING`), so the engine behaviour is
  consistent. For an `int`/`float` target in `conversion_possible`:
  - NumPy word, whatever the source celltype: not scalar → `False`; `NUMERIC` → `True`;
    otherwise `None`;
  - `JSON_OBJECT`, `JSON_ARRAY`, `MIXED_OBJECT`, `MIXED_ARRAY` → `False`;
  - `JSON_NUMBER`, or `NUMERIC_SCALAR` set → `True`;
  - `JSON_STRING` without flags → `None`;
  - `LONG` no longer decides this category (keep it for reinterpretation, where the parser
    enforces it).
- Proposed engine fix: raise on a non-finite `float` result.
- Not recommended: new `JSON_BOOL` / `JSON_NULL` kinds (Kind values 12–15 are free). They would
  only restore rejections on tiny buffers, and stored `JSON_STRING` words would contradict the new
  words (409 from the database), so they would need a migration.

### L5. Chains are never disproved (= section 3, item 6)

- Confirmed, and it costs I/O. For `bytes→int` on `"hello"`: `conversion_feasible` gives `None`,
  `conversion_needs_buffer` gives `True` (so placement routes the Expression to the data), and the
  engine fetches the buffer and parses all of it as `plain` before the word rules out `int`. On a
  `RAW_BYTES` word the engine does reject from the cache, without a fetch.
- Proposed fix: compose the two steps.
  - First step `False` → `False`.
  - First step keeps the checksum (trivial or reinterpret, after `conversion_equivalent`) → also
    evaluate the second step on the same word.
  - Second step always succeeds on valid input (trivial or reformat) → the first step's answer.
  - Otherwise `None`.
- This can rule out `bytes→str/int/float/bool/yaml/python/ipython` and
  `mixed→text/yaml/python/ipython`. Don't predict through a first step that creates a new buffer
  (`text→plain→int`): inputs such as `"1_000"` (valid for Python `float()`, not JSON) make that
  unsafe.

### L6. Untested kinds and `SEMANTIC` have no producer (= section 3, item 10)

- Accurate, but the two cases differ.
- Untested kinds: keep them; they have a natural future producer. `from_buffer` runs a full
  `orjson.loads` on every UTF-8 buffer each time a checksum is computed (the point item 13 raises
  against `type_bits_design.md` §8.3). Measured: a 71 MB JSON array took 0.40 s to classify vs
  0.02 s for sha256, with about 286 MB extra peak memory; a 200 MB NumPy array took 0.03 s. A size
  cap that emits `UTF8_UNTESTED` for large buffers is what these kinds are for.
- `SEMANTIC`: broken, not just unused. It is not a property of the bytes, and
  `_hash_type_implies` requires concrete words to be identical. So `RAW_TEXT|SEMANTIC` contradicts
  the `RAW_TEXT` word that every checksum computation registers, in either order: `ValueError`
  locally, 409 from the database.
- Proposed: remove the `semantic=` parameter (and the ignored `checksum`, `value`, `celltype`
  parameters of `from_buffer`), and mark the bit reserved in `is_valid_word` (the database uses
  seamless-core's `is_valid_word`, so both change together).

### L7. Syntax and hex validity are not encoded in the word (no section 3 counterpart)

A non-goal rather than a limitation. `from_buffer` is independent of celltype and classifies from
the bytes alone; running Python or YAML parsers on every checksum computation would be expensive;
all three flag bits are in use. The only effect is over-permissive `True` answers, which the
contract allows. Proposed: move it to a "Non-goals" note in `hashtype.md`.

### Decisions needed

1. Section 3 says these bugs are not being worked on. L1 and L4b reject valid work today: fix them
   now?
2. L4b: fix on the HashType side (recommended), or narrow the engine's `int`/`float` coercion?
3. Engine: raise on non-finite `float` results (recommended)?
4. L3: required `checksum` parameter (recommended), or `None` when it is missing?
5. L6: retire `SEMANTIC` (recommended)?

### Documentation follow-up

**`docs/agent/contracts/hashtype.md` must be updated once these issues are settled.**

- "Current limitations": drop each fixed item; add L4b if it is not fixed; correct the L4 wording
  (the classification does cause false rejections); move L7 to non-goals; if L2 and L3 stay, add
  the async `parse_buffer` note to L2 and the null case to L3.
- "The false-negative property" sends readers to "Current limitations" for the exceptions, so
  that list must be complete.
- Rule sections that change with the fixes: `conversion_feasible` (L1, L4b, L5); the Lookup table
  (L2); the `deserializable_as` signature (L3); the word table, well-formedness and `from_buffer`
  (L6).
- An engine change for non-finite floats also needs `docs/agent/contracts/celltypes-and-conversion.md`
  (the `conversion_possible` rules).
- Section 1 (feature 2) says HashType never rejects valid work "(but see bug 1)"; it should also
  point to L4b.

## 15. Notes

### Section 14. has been implemented as "address HashType limitations"

### Compiled transformer overhaul
See home/agent/seamless1/seamless/compiled-transformer-celltypes-design-plan.md.

### The .set_checksum contract
(Also discussed in /home/agent/seamless1/seamless/compiled-transformer-celltypes-design-plan.md)
Cells (and Pins) are containers of Expressions. `Cell.set_checksum` (and `Pin.set_checksum`) do not set the `.checksum` attribute: they are merely the Checksum variant of the three `.setX` methods that set the *input* checksum (from Checksum, Buffer or value). This is instantaneous, and `.checksum` is expected to be None afterwards.
Two exceptions:
1. The Cell or Pin's underlying Expression is a dummy: input_celltype and celltype are identical and there is no path component. This should be special-cased in the implementation, and `.checksum` must return the arg of `.set_checksum`
(as a Checksum) immediately.
2. The Cell is unbound. This doesn't change the semantics, but `.checksum` is now no longer an attribute but a computed property that does a sync evaluation of the underlying expression.

### The jupyter-sync branch is to be merged. (repeat)

### The test set must go green

/home/agent/seamless1/FULL_TEST_REPORT.md

### seamless.workflow API

Needs to provide Context, Cell, and Transformer (which does not exist?)

### Features 4-11 need to be agent-documented
As of 17 sept

### All features require human documentation

We now have reactivity. Soon we will have interactivity, and collaborative webservers.