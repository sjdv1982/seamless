# Known issues: cells-and-expressions

Code problems, documentation gaps, open decisions, and items still to verify, found on 2026-09-17
while updating the docs after the cells-and-expressions work. This file is the starting point for
continuing that work. Contents:

1. Where we are: goal, progress, uncommitted work, the feature list
2. Open decisions
3. Celltypes, conversion, HashType: bugs, inaccuracies, stale text (features 1–3)
4. Compiled-transformer pins bypass the required-pin null check (feature 7)
5. Expression placement (feature 4); settled by `expression-where-the-data-is.md`
6. Expression cancellation (feature 4); its conclusions are in Appendix A
7. Cell-level joins (feature 10)
8. Checksum reference lifecycle (feature 9): its doc, and what feature 11 takes from it
9. BufferInfo removal: follow-ups
10. Design-doc limitations: still open (features 4, 8, 10), closed for mounts (feature 11)
11. Question log (Q1–Q12) and gap-analysis notes
12. Source list: design docs changed during the cells-and-expressions work
13. The jupyter-sync branch is to be merged
14. Review of `hashtype.md` "Current limitations" (L1–L7, plus the new finding L4b); since implemented
15. Notes: loose ends (compiled-transformer overhaul, the `.set_checksum` contract, green test set,
    `seamless.workflow` API, documentation still to write)
16. Bound vs standalone Cell reads, and bound sub-path writes (feature 5): findings from writing the
    contract page
- Appendix A: remote materialization — a waiting set with latch-on and delayed cancel (the design
  discussion behind section 6; not verified against code)

Part of the celltype/conversion/HashType bugs (section 3) has since been fixed, as section 14
records; the rest is not being worked on, and the agentic docs describe the current behaviour
and list them as limitations. For the other sections, nothing has
been decided about fixing them yet (cell-level joins have a follow-up design by the author).

**Status, 2026-09-20: the agentic contract docs are complete.** All eleven features are documented in
`docs/agent/contracts/`; feature 11 was the last, settled by seven rulings (section 2, items 18–24)
and written as two pages. What remains from this file is the code work nobody has decided on
(sections 3, 4, 6, 14), the human documentation and the main docs, and the loose ends in section 15.

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
- Feature 4 (Expressions): agentic docs written and checked against code (2026-09-18):
  - new `docs/agent/contracts/expressions.md` — definition and path syntax, identity (with the dummy
    Expression and the `.set_checksum` contract), cost class, results and caching, placement, the
    error envelope, "failures are not cached", deduplication, cancellation, deep checksums, current
    limitations, non-goals;
  - new `docs/agent/contracts/deep-celltypes.md` — `deepcell`, `deepfolder`, `folder` (and why
    `module` is not one of them): the flat index, member typing, the conversion table and its cost
    semantics, the one-string-item path rule, the `folder` note, the pin layer, and the fact that
    none of it is enforced by the code yet;
  - both linked from `docs/agent/README.md`, `docs/agent/index.md`, `docs/agent/index.json`,
    `docs/agent/config/mkdocs.yml` and `seamless/mkdocs.yml`, with cross-links added in
    `celltypes-and-conversion.md`, `hashtype.md` and `content-addressed-files-and-dirs.md`.
  - Both pages mark what is contract but not yet implemented, in the style of `hashtype.md`'s
    "Current limitations". Open items: section 2, items 7–9.
- Feature 5 (Cells): agentic doc written and checked against code (2026-09-18):
  - new `docs/agent/contracts/cells.md` — a Cell as a deferred Expression, bound or standalone: the
    definition and binding, `celltype` versus read-only `input_celltype`, `.source` / `.checksum`,
    the two write families and the 3×2 matrix, authority, null and `None` (including `bytes`),
    celltype `checksum`, the reads (`.checksum` resolution order, `.buffer` / `.value`, never
    fingertipping), failures, which calls do work and which never do, projections, cell-level joins,
    deep celltypes, implementation status and non-goals;
  - linked from `docs/agent/README.md`, `docs/agent/index.md`, `docs/agent/config/mkdocs.yml` and
    `seamless/mkdocs.yml`, with cross-links added in `expressions.md`, `celltypes-and-conversion.md`
    and `deep-celltypes.md`. `docs/agent/index.json` is generated and git-ignored, so its new entry
    exists on disk only.
  - Out of scope by ruling (section 2, item 10): `.state` and `.block_reason` (feature 10's node
    state lifecycle), pins (features 6 and 7), mounts (feature 11), the reference lifecycle
    (feature 9).
  - Marked as contract ahead of code: `.exception` as a string, Cell validators, the provisional
    join implementation, the unenforced deep-celltype rules.
  - Committed as seamless `3c2a3f2`. Code findings from writing it: section 16. Open items:
    section 2, items 15–17.
- Features 6–10: agentic docs written (2026-09-18), with the author rulings recorded in
  `/home/agent/seamless1/answers.md` (Q1–Q10): `docs/agent/contracts/pins.md` (features 6+7),
  `contracts/compiled-pins.md` (feature 7, compiled input pins), `contracts/cancellation.md`
  (feature 8), `contracts/node-state-lifecycle.md` and `contracts/workflow-context.md` (feature 10),
  plus the internal `contracts/internal/checksum-reference-lifecycle.md` (feature 9). Governing
  rulings: document the **contract, not the implementation**, with divergences in one
  "implementation status" section; `.exception` is a string; grace holds follow pass3's three-case
  taxonomy; `block_reason` precedence is `unwired` → `blocked-by-unwired` → `blocked-by-error` →
  `waiting`.
- Feature 11: contract settled by seven rulings (section 2, items 18–24) and agentic docs written
  (2026-09-20), as **two** pages: `docs/agent/contracts/attachments.md` (the framework) and
  `contracts/mounts.md` (the file driver), committed in seamless as `3d0b0080`. One ruling required
  code: `deepfolder` is sense-only (seamless-workflow `4bb2fdb`, `f8575bd`). Three design-doc
  statements were found false against code while writing the pages; they are recorded in section 10.
  **All eleven features now have their agentic contract docs.**

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
   (SEQ/MAP, rank) the root structure admits. One-sided error: never rejects valid work,
   may answer "maybe" (`None`). The false-rejection bugs (section 3, bug 1; section 14, L4b)
   were fixed by "address HashType limitations". Stored words only tighten; stored locally and in
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
   - Status: contract settled; agent-contract docs done (`docs/agent/contracts/expressions.md`, and
     `docs/agent/contracts/deep-celltypes.md` for the deep celltypes). Parts of the contract are
     ahead of the code — both pages say which. Items still needing a ruling: section 2, items 7–9.
5. **Cells as delayed Expressions** — on top of 4: a Cell is the mutable builder; it holds an
   input (literal/checksum) or builds an Expression over a `.source`, as a Transformer builds a
   Transformation. Navigation returns projection Cells *(design docs)*.
   - Shared CellBase read API: `.source`, `.checksum`, `.buffer`, `.value`, `.exception` /
     `clear_exception()`, plus `.compute()` / `.computation()` and `.set()` / `.set_buffer()` /
     `.set_checksum()`. `.state` and `.block_reason` are node-lifecycle members shared with bound
     Transformers (feature 10), not part of this feature's page; standalone `.state` reports only
     `unwired`/`waiting`/`complete`/`failed`, and `.block_reason` is bound-only.
   - Standalone reads: a getter evaluates its own cheap expression but never runs a source;
     `.value` never fingertips; `.compute()` does the work.
   - Contract: `celltype` = output type; read-only `input_celltype`; `target_celltype` and
     `input_ref` retired (they raise with a pointer to the replacement); `.set()` takes values only;
     a Checksum is a value only for celltype `checksum`; None is a value and `del` is the only
     deletion. **No old → new table**: Cells reach main unreleased, so the contract is stated once,
     not as a migration (section 2, item 11).
   - Deferred: Cell validators *(design docs)*.
   - Status: contract settled (section 2, items 10–14); agent-contract doc done
     (`docs/agent/contracts/cells.md`), framing a Cell as a *deferred Expression* that is bound or
     standalone and describing what the two modes have in common. Code findings from writing it:
     section 16. Items still needing a ruling: section 2, items 15–17.
6. **Optional pins** — transformer-construction substrate, below the Context.
   `Transformer.optional_pins` is a settable set of pin names. Canonical null on an optional
   pin = absence, for any celltype: unconnected and connected-then-null give the same
   transformation checksum (the pin is dropped before the checksum is computed). Connected
   optional pins still compute, and a failing optional upstream still fails.
   Contract: transformation-checksum identity rule. Status: delivered. Settled. Docs done
   (`docs/agent/contracts/pins.md`).
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
   - Status: delivered (gap: compiled pins recorded as `mixed`). Docs done
     (`docs/agent/contracts/pins.md`, `docs/agent/contracts/compiled-pins.md`).
8. **Cancellation substrate** — base layer for 4, 7, 10 *(design docs)*.
   - One membership set per dedup site (in-process / jobserver / Dask).
   - `softcancel` = deregister; the run is cancelled only when the set is empty. `cancel` = hard
     kill of every member. Softness cascades; a real kill happens only at the leaf set.
   - Cross-process liveness deliberately not built. The reactive scheduler uses softcancel only;
     CLI/SIGINT stays hard.
   - Contract: replaces first-caller-owns-execution; jobserver multi-tenant footgun fixed.
   - Status: delivered (gaps to verify, section 10). Expression cancellation: section 6. Docs done
     (`docs/agent/contracts/cancellation.md`).
9. **Checksum reference lifecycle** — internal. Refholders (Cell, Expression,
   Transformer/Transformation, Context current/superseded runs) keep checksum buffers alive;
   refholder claims counted separately from manual incref/decref; public vs internal interest
   is a hard rule; scratch and deep checksums have own rules; balance audit at
   `seamless.close()` (user-visible only as `seamless.references` warnings). The Context's
   `current` / `superseded:<generation>` roles back feature 10's grace holds.
   Own doc written: `docs/agent/contracts/internal/checksum-reference-lifecycle.md` (section 8).
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
    - Status: Part I (A0–A5) delivered; agentic docs done
      (`docs/agent/contracts/node-state-lifecycle.md` for the node state lifecycle,
      `docs/agent/contracts/workflow-context.md` for the runtime and API). Deferred / open /
      unratified / rejected items: section 10 *(design docs)*.
11. **Attachments and mounts** — on top of 10. Attachment framework: sense = authoritative
    write; actuate = delivery after a turn; durable spec plus ephemeral session; a manual test
    driver. File mounts are the only production driver: global watch broker + I/O pool; atomic,
    conditional writes; null files read as null and deliver as truncation; mounts never give up;
    oscillation detector; `ctx.mounts.sync()` *(design docs)*. Use "attachment" and "mount"
    precisely in the docs.
    Status: implemented and tested; **contract settled** by the seven rulings of section 2,
    items 18–24, and documented (2026-09-20) as two pages — `docs/agent/contracts/attachments.md`
    (framework) and `docs/agent/contracts/mounts.md` (file driver), committed as seamless
    `3d0b0080`. The seam: *direction and discipline* on the attachments page, *bytes and filesystem*
    on the mounts page; the mounts page never restates a generic rule, only where the file driver
    specializes it. The attachments page specifies the behaviour of the attachments that exist, not
    a plugin API: file is the only production driver, `ManualDriver` is test-only, `WidgetDriver`
    experimental. Code change required by ruling 24: `deepfolder` is sense-only
    (seamless-workflow `4bb2fdb`, `f8575bd`). v1 exclusions and the now-closed open items:
    section 10.

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
   no generated API reference. Add those modules or not? The same holds for `seamless.cell_class`
   and `seamless.expression_class`: `cells.md` and `expressions.md` have no generated API companion
   either.
4. **Cell-level joins** (section 7): how to document them now — suggestion: document observable
   behaviour (node states, no transformation checksum) and not the implementation, since the
   follow-up design will change it.
   **Resolved (2026-09-18):** yes, observable behaviour only, marked provisional. See item 12 and
   section 7.
5. **Section 10 limitations**: verify each against code now, or record them as limitations while
   writing the docs for each feature?
6. **Evidence tests**: the Q7/Q8 test scripts were not kept in any repo; decide whether
   repo tests should be written for Expression cancellation and cell-level joins.

### The Expression contract (feature 4): three items needing a ruling

Raised while writing the agentic contract pages for feature 4 (2026-09-18) and verified against the
code. Everything else in the Expression contract is settled; these three are not.

7. **Fingertip chains run in the wrong place** (detail in section 5). An Expression that fingertips
   its input walks the reverse index in
   `seamless-core/seamless/checksum/checksum_class.py` and re-evaluates through
   `evaluate_expression_async` *locally, in the requesting process*. That contradicts the placement
   contract ("evaluated where the data is", with a jobserver/daskserver counted as closer to the
   hashserver than the client), and it does so precisely in the case whose cost is unbounded, since
   the chain may contain Transformations. Decide: does the chain follow the dispatch, or is local
   evaluation of a fingertip chain the intended exception?
8. **The linger will contradict a green test** (detail in section 6, gap 4).
   `seamless-core/tests/test_expression_remote_evaluation.py` asserts that the last member leaving
   aborts the jobserver request *synchronously* — true today, because no linger exists, and
   forbidden by the settled contract, under which a softcancel never means the work stopped and the
   abort follows the linger. The test's intent survives; it needs a tolerance for the linger rather
   than a new intent. Nothing to decide unless the abort should in fact stay immediate for the
   last-waiter case.
9. **A daskserver is a second client-side dispatch target**, not only a jobserver mode (detail in
   section 5). `_execute_remote_expression` falls through to `daskserver_remote.run_expression` when
   no jobserver is configured. The checksum, error, caching and HashType contracts are identical
   either way, so this is a wording question: `expression-where-the-data-is.md`'s "a daskserver is a
   jobserver mode" is true for the server side only, and the contract docs now say so.

### The Cell contract (feature 5): five rulings that settle it

Raised while assessing whether the agentic contract page for feature 5 can be written, and ruled by
the author on the same day (2026-09-18). With these, the Cell contract is settled. Write the page
from the final code, marking what is contract but not yet code, as `expressions.md` does.

10. **Framing and scope.** A Cell is a **deferred Expression**, bound or standalone; the page
    describes what the two modes have in common. **Out of scope:** `.state` and `.block_reason`,
    which are node-lifecycle members shared with bound Transformers and belong to feature 10's node
    state lifecycle. **Explicitly in scope:** `.compute()` / `.computation()`, `.checksum`, and
    `.set()` / `.set_buffer()` / `.set_checksum()`. Pins are documented with features 6 and 7, not
    here.
11. **No old → new table.** Cells reach main unreleased, so there is no "old": the contract is
    settled for the first (and hopefully last) time and the page states it as a contract, not as a
    migration. This retires the "one consolidated old → new table" requirement from the feature list.
12. **Cell-level joins are plain local Python.** A join is assembled directly in the Context,
    in-process: there is no Transformation and no Expression behind it, which is why no
    transformation is observed and the node never passes through `computing`. This settles the open
    question in section 7 and open decision 4. It is **provisional**: a future re-implementation is
    to cache joins and evaluate them where the data is. So document the observable behaviour only,
    marked as subject to change, and promise no join identity.
    `context-internals-followup-design.md`:392-396 ("may require a join `Transformation` followed by
    a projected `Expression`") is superseded.
13. **`Cell.exception` holds a string**, as `Transformation.exception` does; the code is to be
    changed to match. This settles the unconfirmed "one convention for `.exception` across Cell, Pin
    and Transformation" of `celltype-rename-review-decisions.md` §8.3. Consequence to record in the
    page: a `CacheMissError`'s checksum then reaches the Cell as prose only, so §10.5's split
    ("`message` is for a person, `checksum` is for code") has no machine-readable arm on the Cell.
14. **A failure is remembered on the handle, never in the substrate** (confirms the §8.3
    recommendation): standalone on the Cell, reset when its input, path or celltype changes; bound on
    the Context node, with `clear_exception()` dropping the stored result. A new Cell built on the
    same recipe never inherits an old failure. This agrees with "Expression failures are not cached".

### Feature 5 findings that need a ruling

Found while writing `docs/agent/contracts/cells.md` (2026-09-18), by code inspection plus probe
scripts. Detail in section 16. The page documents all of them as current behaviour; none is fixed.

15. **Bound sub-path checksum and buffer writes raise `TypeError`** (section 16, item 1). A one-line
    signature fix on either side would close it. Fix, or keep as a documented limitation?
16. **Bound and standalone reads diverge** (section 16, items 2–4): a bound public read neither
    validates nor records an exception, a bound read of a non-existent projection raises instead of
    reporting, and `.buffer` answers `None` where `.value` raises. The page states the *standalone*
    behaviour as the contract, following `celltype-rename-review-decisions.md` §8.4 ("the same
    applies to bound and standalone Cells"). Confirm that direction, rather than making standalone
    match bound.
17. **A refholder-balance warning at `seamless.close()`** (section 16), on a Cell/SubCell derivation
    path with shared input checksums. Feature 9, internal, so it is in no contract page — but it
    looks like a real imbalance.

### The attachment and mount contract (feature 11): seven rulings that settle it

Raised by an assessment of whether feature 11's contract was settled enough to document, and ruled by
the author on 2026-09-19/20. With these, the feature-11 contract is settled and both pages are
written. `mount-design.md` §1–§17 remains the normative design; where it and the code disagree, the
code wins, and the stale passages are listed at the end of section 12.

18. **Two pages, not one.** `docs/agent/contracts/attachments.md` (framework) and
    `contracts/mounts.md` (file driver). The seam is *direction and discipline* versus *bytes and
    filesystem*; `mounts.md` never restates a generic rule, only says where the file driver
    specializes one. `mode` / `authority` / `persistent` go on the mounts page although they live on
    the generic spec class. The oscillation detector is split deliberately: mechanism on attachments,
    thresholds and rationale on mounts; likewise `sync()` semantics on attachments, spelling and the
    `SyncReport` fields on mounts. The attachments page is **not** a plugin API: file is the only
    production driver, `ManualDriver` is test-only, `WidgetDriver` experimental.
19. **Error typing follows the remote boundary.** `Cell.exception` is a string (item 13), but
    `ctx.a.mount.error` and `status['sense_error']` are **Exception objects** (`MountError`,
    `ConflictError`). The reason, and the rule for any future error surface: Expressions and
    Transformations can execute remotely and exception objects do not transfer well, whereas mounts
    are fundamentally local. Consequences: `isinstance(err, ConflictError)` stays the machine-readable
    way to tell a tripped detector from a failed write, and on the cell the `"<path>: <reason>"`
    prefix is contract, being the only thing that identifies a mount sense error.
20. **Null on a `w`/`rw` directory mount is terminal.** The delivery is suppressed, the tree is left
    in place, and the mount reports `in_sync: False` permanently with **no error**, because nothing
    failed. Files always converge instead (null truncates to zero bytes; a null value with an absent
    file counts as in sync). The sharp edge is documented: the only signal is `in_sync: False` with an
    empty `ctx.mounts.errors`, so "sync until in_sync" never terminates.
21. **Limits are defaults, not contract.** Contract is the *shape* — a cap exists, exceeding it makes
    the observation `REJECTED`, and the checksum (never the fingerprint) is the correctness guard.
    The numbers (4 workers, 0.2 s poll, 2 s racy window, 60 s delivery, 1 GiB file, 100 000 files /
    10 GiB / 60 s scan, detector 3-in-20 s) are current defaults. Network filesystems are a
    documented limitation; the `rehash_interval` knob of `mount-design.md` §20.4 was never built and
    is not planned.
22. **Write failures stay on the mount, never on the cell** (confirms `mount-design.md` §20.11): a
    read problem is the cell's exception because the file *is* its value source, while a write problem
    leaves a valid value and only a stale file, so failing the cell would block every downstream
    consumer of a correct result.
23. **A delivery resolves; it never computes.** The payload goes through `Checksum.resolution()`
    (local cache → remote buffer server → `CacheMissError`) and never fingertips, so a delivery has
    exactly the powers of `.buffer`. Mounting is therefore **not** a materialisation mechanism for a
    scratch result: it usually works because the delivery follows the completing turn while the buffer
    is still cached, and fails visibly when the checksum arrived without bytes. This **supersedes**
    `mount-design.md` §20.3, which assumed the ordinary path recomputes.
24. **Leaf retention, narrowly; and `deepfolder` is sense-only.** Promise only that leaves a mount
    *sensed* stay resolvable while the node holds that index, including after unmount — the lease
    mechanism stays internal. The general rule is already ruled the other way
    (`contracts/internal/checksum-reference-lifecycle.md`: only the top-level checksum of a deep value
    is owned, no recursive deep ownership), so the mount's per-leaf claims are a permanent
    mount-specific exception on the sense path; a *computed* directory gets none, and a missing leaf
    is a delivery error. Separately: `folder` mounts in `r`/`w`/`rw`, `deepfolder` may only be
    sensed (`mode="r"`), `deepcell` / `module` / `checksum` stay unmountable. A write mount
    materialises every leaf, which is what `deepfolder` declares it does not do; `folder ↔ deepfolder`
    is free and checksum-preserving, and a transformer cannot produce a `deepfolder` at all, so
    `folder` is the only celltype a computed directory can arrive in. Since the default mode is `rw`,
    `ctx.a.mount(path)` on a deepfolder cell raises, deliberately. Implemented in seamless-workflow
    `4bb2fdb` + `f8575bd`: `validate_celltype(celltype, mode)` with `mode` required, enforced at all
    three call sites; an invalid **request** raises `TypeError`, an invalid mount spec in a **graph**
    raises `PathError` (including under `mounts=False`).

## 3. Celltypes, conversion, HashType (features 1–3)

Repo: seamless-core.

**Status after "address HashType limitations" (seamless-core `0d3ccfb`) and
`827bd5b`.** Fixed: bugs 1 and 2, items 5, 6 and 11, the `SEMANTIC` half of item 10, and
section 14's L4b, including the non-finite float results of `conversion_possible` and of
`binary → plain`. Still open, and documented as current behaviour: bug 3, items 4, 7, 8, 9,
the untested kinds of item 10, and items 12 and 13.

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

> **Settled by [`expression-where-the-data-is.md`](expression-where-the-data-is.md).** That plan is
> the normative source for placement, and placement *is* contract: an Expression is evaluated where
> the data is, with a jobserver/daskserver counted as closer to the hashserver than the client. It
> fixes the resolution order (§8.2: process-local Expression cache → database result → local when no
> buffer is needed or the input is in memory → jobserver/daskserver dispatch when it is not and a
> server is configured → local materialization when none is → result resolution when a value is
> wanted), defines `"local"` as *in this process's memory* and `"remote"` as *not in this process's
> memory, independently of backend availability*, forbids a silent fallback once a configured server
> fails, and records that a daskserver is a jobserver *mode* rather than a competing backend, with
> both modes exposing the same checksum, error, caching and HashType contracts. Two consequences
> belong in the contract docs as derived rules: the result *including the exception type* must not
> depend on where it ran (§9's structured error envelope, down to `CacheMissError` keeping its
> checksum in `args[0]`), and HashType classification is owned by whichever process holds the buffer
> (§10.4). This section is kept for the claim-by-claim history below.

Feature 4 (Expressions) is documented as "evaluated where the data is": with `execution="auto"`,
an Expression is evaluated locally or through the jobserver's `run_expression`. A doc summary
made the claims below.

- The sync and async evaluation paths mean different things by "local".
- With no jobserver configured, `"auto"` has no fallback (e.g. to the hashserver).
- Standalone `compute()` bypasses `"auto"`.
- Expression inputs to transformations bypass `"auto"`.
- Expression errors lose their exception type when they come back from the jobserver.

They were not summary inaccuracies. The placement plan addresses them: the no-jobserver fallback
(§2), standalone `compute()` / `compute_async()` / `run()` defaulting to `"auto"` (§3), transformation
dependencies and pin preparation using `"auto"` (§4), and the exception types (§9). What remains is
to confirm each against the code as implemented, not to decide anything.

Note: seamless-core has recent commits that may already address some of these:
`108a1f1` "Keep expression error types, resolve run() results, test undone results" (2026-09-15)
and `8e00718` "Expressions execute where the data is" (2026-09-17).

Two placement questions the plan does not answer:

- **Local read buffer directories.** Locality is decided by process memory alone, so a buffer in a
  locally mounted read buffer folder counts as remote and is dispatched to a jobserver, although the
  client could read it from local disk. Does "where the data is" include local buffer directories?
- **Fingertip chains.** An Expression can fingertip as a step in a chain (Appendix A, 1a). Where such
  a chain runs — on the client, or on the server that took the dispatch — is unstated, and it is the
  case whose cost is unbounded. **As implemented** (2026-09-18), the reverse-index walk in
  `seamless-core/seamless/checksum/checksum_class.py` re-evaluates through
  `evaluate_expression_async` *locally, in the requesting process*. That is the opposite of "where
  the data is", and it is exactly the case whose cost is unbounded, so it needs a ruling rather than
  a note.

The rest of the plan **is** implemented and was verified against the code (2026-09-18): the §8.2
resolution order and the `"auto"` downgrade in `evaluate_expression_remote`; `has_jobserver` /
`has_daskserver`; `"auto"` as the default on standalone `compute`/`compute_async`/`run`, on
transformation dependencies and pin preparation, and in the Context; the §9 error envelope
(`seamless/error_envelope.py`, HTTP 200 for answered jobs) ; §10.4 HashType ownership in the
buffer-holding process; §8.3 dedup with a shared future and a deterministic Dask key; and §8.4
daskserver delegation. One refinement to the plan's wording: client-side, a **daskserver is a second
dispatch target, not only a jobserver mode** — `_execute_remote_expression` falls through to
`daskserver_remote.run_expression` when no jobserver is configured. The contracts are the same
either way; the sentence "a daskserver is a jobserver mode" holds for the server side only.

## 6. Expression cancellation (feature 4): implemented, with gaps

**Read Appendix A first**: the 2026-09-17 discussion of this section concluded that the only
cancellable work is remote materialization, which is not Expression-specific, and it re-rates the
gaps listed below.

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
4. ~~No repo test covers Expression cancellation.~~ Stale (2026-09-18):
   `seamless-core/tests/test_expression_remote_evaluation.py` covers the remote path — an idle
   `cancel()` returns `False`; one of two members leaving keeps the shared request alive and both
   callers get the result; the last member leaving aborts the request. Local in-flight cancellation
   is still untested. Note that the third assertion encodes *today's* linger-free behaviour: under
   the settled contract the abort follows the linger, so that test needs a tolerance, not a new
   intent.
5. **Deep checksums — settled (2026-09-18); the code and docs must be adapted.** An Expression over
   a deep checksum is restricted, because its cost class must be a function of its identity tuple
   `(input_celltype, path shape, celltype)` and never of the data behind the checksum. A deep index
   is a **flat** dict: string keys, 64-hex values. The nesting that `unpack_deep_structure` /
   `pack_deep_structure` recurse through is legacy Seamless generality that never had producers or
   consumers; it must be rejected at the Expression layer *and* at pin unpacking, through one shared
   validator, or the two layers disagree about what a deep value is.

   Zero path:
   - identity (the dummy Expression): always legal;
   - `deepcell → plain`, `deepfolder → plain`, `folder → deepfolder`: the index, free and
     checksum-preserving;
   - `deepfolder → folder` and `deepcell → deepfolder`: free. `deepfolder → deepcell` is forbidden,
     because deepcell members are buffers deserializable as `mixed` while deepfolder members are
     arbitrary bytes (the feature-1 checksum hierarchy, applied one level down to members);
   - `folder → mixed`: the only conversion that materializes children. All-or-nothing; resolution
     order and concurrency are unspecified (an optimization, not contract);
   - everything else rejected, including `folder → plain`, which would put a free index read and an
     N-child fan-out under one identity tuple.

   Exactly one string-item step: the step yields either the child's checksum or the child's value at
   its member celltype — `→ checksum` for every deep celltype, `→ mixed` for `deepcell`, `→ bytes`
   for `deepfolder` and `folder`. Longer paths are rejected: a further step would continue into the
   child, which is a different checksum and therefore a different Expression. Keys are opaque strings
   with no path semantics, and deepfolder keys routinely contain `/`, so the step usually has to be
   written in bracket form.

   `module` is **not** a deep celltype (`DEEP_CELLTYPES = ("deepcell", "deepfolder", "folder")` in
   `seamless-transformer/seamless_transformer/transformation_utils.py`): a module buffer is a plain
   JSON module definition holding literal code strings, not checksums, and it travels as celltype
   `plain` with subcelltype `module`. None of the rules above apply to it.

   **Note on the `folder` celltype.** Conversion stops at `folder → mixed`: the children arrive as
   S1 NumPy arrays of raw bytes, and no conversion yields a dict of decoded strings. `mixed → plain`
   stays a pure reinterpretation — giving it a value-level route would make every S-array in every
   mixed buffer decode to text, and would make the pair only sometimes checksum-preserving; that is
   too much global semantics to buy one convenience. Consumers that want text decode it themselves:
   per file, through an ordinary `bytes → text` Expression on the child checksum, or for a whole
   folder in a transformer, which is the idiomatic route, since decoding N files is content
   transformation rather than celltype reinterpretation. One cosmetic consequence: an *empty* folder
   still converts to `plain` (its mixed buffer is literally `b"{}\n"`), so `{}` succeeds where every
   non-empty folder is rejected.

   Both open points for `folder` are now settled by evidence (2026-09-18):

   - A folder index buffer **is** byte-identical to a deepfolder index. The mount layer builds one
     index for both celltypes (`seamless-workflow/seamless_workflow/attachments/fs/service.py`,
     `{relative path: checksum hex}` serialized as `plain`), and `Buffer(idx, "folder")` and
     `Buffer(idx, "deepfolder")` give the same bytes and the same checksum. `folder → deepfolder` is
     checksum-preserving, unqualified.
   - `folder → mixed` must present each child as a **1-D `S1` array with one element per byte**
     (`np.frombuffer(content, dtype="S1")`), not as a 0-d `S<N>` scalar. Only the 1-D form is
     faithful: it round-trips `b""`, `b"\x00"` and content with trailing NULs exactly. Serializing a
     dict of Python `bytes` into `mixed` instead produces 0-d `S<N>` scalars, and neither extraction
     is faithful — `tobytes()` turns an empty child into `b"\x00"`, while `.item()` strips trailing
     NULs (`b"ab\x00\x00"` reads back as `b"ab"`), because NumPy's `S` dtype strips trailing NULs.
     The pin-level fan-out (`unpack_deep_structure`) hands the transformer Python `bytes`, which is
     fine as an in-process presentation, but a dict of `bytes` must never be the route by which a
     folder value is *serialized* as `mixed`.

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

Joins are currently assembled directly in the Context, but this is subject to future re-implementation (do caching of joins and evaluate them where the data is).
They are plain local Python: no Transformation and no Expression, which is why no transformation is
observed and the node never passes through `computing`. The docs describe the observable behaviour
only, marked provisional (section 2, item 12; open decision 4).

## 8. Checksum reference lifecycle (feature 9): its doc, and what feature 11 takes from it

The checksum reference lifecycle (refholders that keep checksum buffers alive; refholder claims
vs. manual incref/decref; scratch and deep-checksum rules; balance audit at `seamless.close()`)
is internal and stays out of the public agentic contracts in `seamless/docs/agent/`. **Its own doc is
written** (2026-09-18): `docs/agent/contracts/internal/checksum-reference-lifecycle.md`, kept separate
from the public contract pages rather than in the seamless-workflow repo as first planned. One rule
from it that feature 11 depends on: only the *top-level* checksum of a deep value is owned, with no
recursive deep ownership — hence the narrow leaf-retention promise of section 2, item 24. The rule now
names `folder` as well as `deepcell` / `deepfolder`.

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

## 10. Design-doc limitations: still open (features 4, 8, 10), closed for mounts (feature 11)

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

Mounts (feature 11) — **all closed** (section 2, items 18–24), and documented in
`contracts/attachments.md` / `contracts/mounts.md`:
- w-mode reassert timing: settled by the code — a `w` mount reasserts on a foreign, rejected or
  absent observation when the node is complete, capped by the detector (3 reasserts in 20 s).
- Network-filesystem fingerprints: documented as a limitation; no `rehash_interval` (item 21).
- Resource limits: shipped with the design's values, documented as defaults, not contract (item 21).
- Directory leaf retention: the narrow sensed-leaves promise (item 24).
- Not in v1, documented as non-goals: standalone, sub-path, pin and code mounts;
  `edit_policy="external-owned"`; cross-process locking; context mounts with automatic child paths.

**Three design-doc statements found false against the code** while writing the pages (2026-09-20);
the pages document the code, and these are the corrections:
- A failed delivery's backoff retry does **not** need an external turn. `_mount_tick` is a no-op
  handler, but `FileSystemService._broker` sends one tick per active registration per poll interval,
  and every turn runs the post-turn pass — measured recovery 1.5 s after the fault was fixed, with no
  Context call. Only a driver with no tick (`ManualDriver`) needs an external turn.
- The celltype freeze and the clearing refusal fire on `node.mount` **regardless of mode**; only "the
  sensing mount is the producer, so no incoming edge" is sensing-only.
- `Context.set_graph` detaches every session with `delete=False`, so it **never** deletes a
  `persistent=False` file — wider than `mount-design.md` §7.3, which promises this only when the new
  graph re-attaches the same path.

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
    `expression-where-the-data-is.md` (normative for Expression placement; see section 5),
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

### Stale passages in the feature-11 design docs (2026-09-20)

`mount-design.md` §1–§17 is the normative design and is decision-complete, but these passages are
dead and must not be copied into any later document:

- §17.3's row "clearing an `r`/`rw` cell's value stays cleared; the file is untouched". The code
  refuses: `AuthorityError("Cannot clear a mounted cell; unmount first")`, which is also what the
  doc's own preamble says. The refusal is the contract.
- §20.3 ("resolve it through the ordinary path, which may recompute it") — superseded by section 2,
  item 23: the ordinary path is `Checksum.resolution()`, which never fingertips.
- §16's "Naming is provisional" — the names are fixed by code.
- §20.4's proposed per-mount `rehash_interval` — never built (item 21).
- `mount-implementation.md` gives graph format `0.3`; the code and the seamless-workflow README say
  `0.4`.
- `attachments-and-mount-design.md` Part II is the earlier umbrella: its §21 still discusses a
  `settled()` predicate and spells the API `ctx.mount.sync()` (singular). Both are dead; where it and
  `mount-design.md` differ, `mount-design.md` plus the code wins.
- **Every "legacy Seamless" claim** in §7.2's legacy column and in §17.2. `mount-implementation.md`
  records that legacy could not be imported in either conda environment, so the M1 characterization
  never ran. The agentic pages therefore carry no legacy comparison at all.

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

### What .exception hold

Use one convention across Cell, Pin and Transformation . Today a Cell holds an exception object and Transformation.exception is a string. The code is to be changed.

**Ruled 2026-09-19 (section 2, item 19), with the reason that makes it extensible:** the string
convention follows the **remote boundary** — Expressions and Transformations can execute remotely and
exception objects do not transfer well. A purely local error surface is therefore exempt, which is why
`Cell.mount.error` and `status['sense_error']` hold `MountError` / `ConflictError` objects.

### Compiled transformer overhaul
See home/agent/seamless1/seamless/compiled-transformer-celltypes-design-plan.md.

### The .set_checksum contract
(Also discussed in /home/agent/seamless1/seamless/compiled-transformer-celltypes-design-plan.md)
Cells (and Pins) are containers of Expressions. `Cell.set_checksum` (and `Pin.set_checksum`) do not set the `.checksum` attribute: they are merely the Checksum variant of the three `.setX` methods that set the *input* checksum (from Checksum, Buffer or value). This is instantaneous, and `.checksum` is expected to be None afterwards.
Two exceptions:
1. The Cell or Pin's underlying Expression is a dummy: input_celltype and celltype are identical and there is no path component. This should be special-cased in the implementation, and `.checksum` must return the arg of `.set_checksum`
(as a Checksum) immediately.
2. The Cell is unbound. This doesn't change the semantics, but `.checksum` is now no longer an attribute but a computed property that does a sync evaluation of the underlying expression.

### Deepcell contract
The agentic contract now describe deepcells and their conversion rules, but these rules need to be implemented, and unpack_deep_structure is legacy code that needs to be flat-dict-only.

### The jupyter-sync branch is to be merged. (repeat)

### The test set must go green

/home/agent/seamless1/FULL_TEST_REPORT.md

### seamless.workflow API

Needs to provide Context, Cell, and Transformer (which does not exist?)

### Features 6-11 need to be agent-documented — DONE

All eleven features now have their agentic contract docs. Features 4–5 on 18 sept.
(`contracts/expressions.md`, `contracts/deep-celltypes.md`, `contracts/cells.md`), features 6–10 on
18 sept. (`contracts/pins.md`, `contracts/compiled-pins.md`, `contracts/cancellation.md`,
`contracts/node-state-lifecycle.md`, `contracts/workflow-context.md`, plus the internal
`contracts/internal/checksum-reference-lifecycle.md`), feature 11 on 20 sept.
(`contracts/attachments.md`, `contracts/mounts.md`). See the progress list in section 1. What remains
is the **human** documentation (next note but one) and the main docs in `docs/main/`.

### All features require human documentation

We now have reactivity. Soon we will have interactivity, and collaborative webservers.

### Cell bug (contract error)

Standalone projection writes go to a temporary. cell.b returns a fresh derived Cell, and SubCell inherits the setters unchanged — it overrides only __eq__/__bool__/__len__/__iter__ (cell_class.py:688-750). So standalone cell.b.checksum = cs mutates a throwaway handle and is silently lost. Line 309 blocks cell.b = v and cell["b"] = v, but not this. Same for cell.b.value = and cell.b.buffer =. That should raise. Related: a standalone Cell constructed with path= has .checksum = cs set the pre-path input, so the round-trip genuinely fails — that one is coherent (the path is recipe, not value) but deserves a sentence.

## 16. Bound vs standalone Cell reads, and bound sub-path writes (feature 5)

Found by code inspection plus ten probe scripts while writing `docs/agent/contracts/cells.md`
(2026-09-18; probes run in conda env `seamless1`, not kept in any repo). All of it is documented in
that page as current behaviour; nothing is fixed. Items 1–3 are divergences between the bound and
the standalone path, where `celltype-rename-review-decisions.md` §8.4 says "the same applies to
bound and standalone Cells". Rulings needed: section 2, items 15–17.

1. **Bound sub-path checksum and buffer writes raise `TypeError`.** `ctx.a.b.checksum = cs`,
   `ctx.a.b.set_checksum(cs)`, `ctx.a.b.buffer = buf` and `ctx.a.b.set_buffer(buf)` all fail with
   `TypeError: _edit() got an unexpected keyword argument 'input_celltype'`.
   `BoundCellBackend.write_checksum` (`seamless-workflow/seamless_workflow/builder_state.py`) always
   passes `input_celltype=`, and the `_cell_operation` branch of `ingress.controller_method`
   forwards `**kwargs` into `ingress._edit`, which has no such parameter. Root writes and the whole
   standalone path are unaffected. This contradicts the 3×2 matrix of the rename plan, under which
   all six writes exist at a projection and keep their ownership check.
2. **A bound public read neither validates nor records.** `Context._get_buffer` and `_get_value`
   validate the checksum against the celltype and set `node.state = "failed"` with
   `node.exception`, but `ingress.controller_method` intercepts `_get_checksum` / `_get_buffer` /
   `_get_value` for every non-controller caller and resolves the checksum directly, so those bodies
   are dead for public reads. Observed: a bound `.buffer` returns unvalidated bytes, and a bound
   `.value` whose deserialization fails raises without setting `.exception`. Standalone does both.
3. **A bound read of a non-existent projection raises instead of reporting.** `ctx.p.nope.checksum`,
   `.value` and `.compute()` raise `ExpressionEvaluationError`, because the ingress read path
   catches only `KeyError` / `IndexError` while `expression._apply_step` wraps those in
   `ExpressionEvaluationError`. Standalone, the same projection returns `None` and records
   `.exception`.
4. **`.buffer` returns `None` where `.value` raises.** After a recorded evaluation failure,
   `CellBase.checksum` short-circuits on `_standalone_exception` and returns `None`, so `.buffer`
   answers `None` while `.value` re-raises the failure.

### `.exception` as a string: the code sites that must change

Ruling 13 (section 2) makes `Cell.exception` a string. Today `error_envelope.execution_error`
returns an *exception object* with its traceback stripped, `__cause__` / `__context__` cleared and a
`failure_id` attached, and both `CellBase.exception` and the bound `node.exception` hand that object
out. The two sites that change with it: standalone `.value` and `run()` do
`raise self._standalone_exception`, which requires an exception object.

### Superseded design-doc statements, confirmed against code

Recorded so that a later reader does not trust them:

- `context-internals-followup-design.md`, "Bound-only observations and control": `.checksum`,
  `.buffer` and `.value` raise a deliberate bound-only error when standalone. Superseded by the
  standalone reads of `celltype-rename-review-decisions.md` §8; the code implements the new rule.
- `context-internals-followup-design.md`:348: a projection's `input_ref` is its owning root
  endpoint. Superseded — that meaning is the private `_input_ref`, and the public split is
  `.source` / `.checksum` (`Context._public_cell_source`).
- `context-internals-followup-design.md`:392-396: a join "may require a join `Transformation`
  followed by a projected `Expression`". Superseded by section 2, item 12, and confirmed from code:
  `Context._derive_cell` hands `sidework.evaluate_cell` to `_demand` under a `("merge", …)` fact
  key, and `evaluate_cell` is `Checksum.resolve` + `_assign_path` + `checksum_for_value`, nothing
  else. `_demand` reports `waiting` while in flight, so a join node can never be seen `computing`.

### Smaller findings

- A Cell validator must be a `Checksum` or a hex string; source text fails with an opaque `fromhex`
  error. Validators are deferred, so this only matters once they are implemented.
- Supplying a validator makes every evaluation entry point raise
  `NotImplementedError("Expression validators are not implemented yet")`, which a Cell records as
  `.exception`, wrapped in `WorkflowExecutionError`.
- `docs/agent/index.json` is generated by `docs/agent/scripts/gen_agent_docs.py` and git-ignored
  (`.gitignore:6`), so it is not part of any docs commit. Its `cells.md` entry was added on disk in
  the generator's sort position, which makes a regeneration a no-op.

### Not verified

- **The running-loop refusal path** (`CellBase.checksum` turning `RunningLoopRefusal` into `None`
  with no exception recorded) was established by code inspection only: provoking a genuine refusal
  needs a configured jobserver, which was not set up.
- **"No transformation is observed in the observation log"** for a join follows from there being no
  Transformation anywhere in the join code path; the log was not read through its API.
- **Bound `.exception` for a projection failure at derivation time** was not constructed separately;
  the node-level conversion failure (`text → int`) was, and records an object that reproduces after
  `clear_exception()`.

## Appendix A. Remote materialization: a waiting set with latch-on and delayed cancel

Design discussion of 2026-09-17 (author + Opus), starting from section 6. No code was read and no
tests were run: nothing below is verified against the code. The discussion settles what Expression
cancellation is *for*, and concludes that the mechanism does not belong to Expressions at all. It is
used by any remote materialization — Expressions, transformation input resolution, `.buffer` reads,
mounts.

### A.1 Premise: what can take time

Expression evaluation proper — deserialize, walk the path, convert, serialize, hash — is cheap, and
it is CPU-bound inside a single thread, so it could not usefully be interrupted anyway. (The worst
case measured in section 14 is 0.4 s to classify 71 MB of JSON.) The only part that can take real
time is resolving a checksum to a buffer from a remote source: a read buffer server or a read buffer
directory.

Three cases were raised against that premise; author's rulings:

- **Fingertipping (1a).** An Expression normally does not fingertip its input checksum, but it can,
  as a step in a fingertip chain. The cost of a materialization is therefore unbounded: the chain
  may contain Transformations. This is what makes the machinery below worth building.
- **Deep fan-out (1b).** Materializing a deep checksum into a value (`deepcell → plain`, N child
  buffers) is to be banned from Expressions, except for `folder`. Recorded separately by the author;
  the consequence here is that every Expression waits on exactly one buffer, `folder` excepted, and
  `folder` is the only case needing a multi-checksum waiter.
- **After the buffer arrives (1c).** Evaluation is near-instantaneous, so there is no cancel point
  once the data is present: the evaluation runs to completion and its result is recorded.

### A.2 What cancellation is for

Never for correctness. Results are content-addressed, so a late result is unwanted, never wrong; and
since cancellation is best-effort, the Context must ignore late results from superseded runs in any
case. The value of a cancel is therefore: remaining resource cost × the chance that nobody else
wants the output.

For materializations the second factor is low, lower than for a Transformation result: the same
buffer is wanted by sibling projections of one parent (`ctx.a.x`, `ctx.a.y`), by the Transformation
that takes the same checksum as an input, and by a revert. Hence latch-on plus a delay before the
abort, rather than an eager abort.

### A.3 The mechanism

- **A waiting set per in-flight materialization, keyed by checksum**, held at the materialization
  site in the buffer layer — not by `Expression`. `Expression.cancel()` becomes "leave the set".
- **Latch-on**: a second requester for the same checksum joins the in-flight materialization instead
  of starting a second one.
- **Softcancel = deregister.** The fetch is aborted only when the set is empty, and then only after
  a linger of a few seconds; a requester arriving during the linger simply re-registers. One knob,
  one default; no progress-awareness and no per-source tuning until something measured asks for it.
- **No hard cancel** (settled). The only leaf a hard cancel could kill is a shared fetch, so it would
  merely make the other waiters fail and re-fetch. A single waiter pressing Ctrl-C is already covered:
  with one member, softcancel aborts the fetch.
- **Failure must not be sticky** (settled). A Transformation caches its exception; a materialization
  that fails (unreachable server, buffer absent) must not poison the checksum for the next requester.
  "Not found anywhere" is a real terminal answer, but it is the trigger for fingertipping, not a
  cached failure.
- **Vocabulary: "waiting set", not "refcount".** Keep it separate from the checksum reference
  lifecycle (feature 9: refholder claims vs. manual incref/decref). Different things, different
  lifetimes: one keeps a buffer alive once it exists, the other tracks who still wants a fetch that
  has not finished. The two do meet in one place: the site itself must hold a lifecycle claim for the
  duration of the linger and release it when the timer fires. That is what the balance audit at
  `seamless.close()` should catch.

### A.4 Fingertip chains

With 1a, the chain is the real unit: a requester asks for one buffer, and the machinery may start a
tree of Expressions and Transformations that nobody named.

- Abandoning the root must cascade soft deregistration down every step, or an abandoned chain runs to
  completion. Each step keeps its own waiting set, so a step shared with a live chain survives — the
  membership model of feature 8, applied one layer down.
- Convergence is normal: two chains often need the same intermediate, and one may arrive seconds
  after the other gives up. A second, independent argument for the linger.
- Abandoning mid-chain discards every intermediate; where intermediates are scratch, no trace of the
  work remains. A third argument for the linger.
- The leaf Transformation needs no special case: the linger keeps its member registered for those few
  seconds, and it is killed only when its own set empties (softness cascades, feature 8).

### A.5 What asyncio task cancellation does and does not give

Task cancellation is the right propagation mechanism for *abandonment* — cancelling the requester's
task unwinds its awaits down the chain and runs each step's cleanup — but it is not the mechanism for
deregistration. Four things it does not do:

1. **Deregister.** It knows nothing about the waiting set; each site must leave the set in its own
   cleanup path, synchronously or under a shield (an `await` inside a cancelled task raises at once).
2. **Protect shared work.** If the requester's task *owns* the fetch, cancelling that task kills the
   fetch for every latched waiter — a hard cancel in disguise. Shared work must be owned by a task
   belonging to the site, with each waiter awaiting a derived or shielded future. See the worry in
   A.6 about the "local path works" evidence.
3. **Stop what is not an await**: a thread (`asyncio.to_thread`), a subprocess, a jobserver request, a
   Dask future. There, cancellation abandons the waiter while the work continues and keeps holding
   its resource (section 6, gap 3).
4. **Delay.** A linger is by definition not "cancel the child when the parent is cancelled": the
   site's task must outlive every waiter.

### A.6 Section 6's gaps, re-rated

1. **Key mismatch (local `cancel()` is a no-op).** Low resource impact, since task cancellation
   already interrupts local resolution; the real defect is that the API silently returns `False`.
   Moving membership to the materialization site removes the expression-level set altogether, and
   with it this class of bug. Minimum fix if the structure stays: align the two keys.
2. **No hard cancel.** Not a gap: a non-feature, to be documented. `Expression.cancel()` should be
   documented as soft, and the `cancel_expression` alias dropped or renamed, since "cancel" means
   hard for Transformations.
3. **Dask-dispatched Expressions.** The remote work is cheap, so failing to interrupt it hardly
   matters. What may matter, inferred from section 6's description of `asyncio.to_thread(thin.result)`
   and unverified: cancelling the awaiting task does not free the thread, which stays blocked until
   the remote side finishes, so a burst of superseded Expressions could starve the default executor
   (the failure family of the jupyter-sync hang). Separate question: should Expressions go through
   Dask at all? A scheduler round trip costs far more than the evaluation, and queueing behind
   Transformations is worse.
4. **No repo test.** Test the contract rather than "it stopped": (a) softcancel by the only waiter
   aborts a slow materialization, after the linger; (b) with two waiters on the same *checksum* (not
   the same Expression), softcancel of one keeps it alive; (c) a result arriving after supersession
   does not reach the node; (d) the reference-balance audit at `seamless.close()` stays clean when a
   fetch completes after its last waiter left. (d) is a likelier bug than a fetch that will not stop.

**Worry about the "local path works" evidence.** Section 6 records that cancelling the awaiting
asyncio task interrupts a blocked buffer resolution. That is only correct if the resolution is not
shared; if two waiters await one fetch and one waiter's cancellation propagates into it, the other
gets a `CancelledError` (A.5, point 2). The throwaway evidence test most likely had a single waiter.
First thing to check in code.

### A.7 Open questions

1. Is buffer resolution already deduplicated by checksum across consumers, and does one waiter's
   asyncio cancellation propagate into the shared fetch? Decides whether the worry above is a real
   bug.
2. Do materializations hold bounded resources — a jobserver worker slot (section 10 records that a
   jobserver cancel does not free the slot), a Dask worker, a default-executor thread? Head-of-line
   blocking is the main resource argument for cancelling at all.
3. Linger default, and whether it is per-site configurable.
4. Does the site's lifecycle claim during the linger show up cleanly in the `seamless.close()`
   balance audit?