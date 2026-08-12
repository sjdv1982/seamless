# Audit: Implementation Plan vs. Design Pass 3

## Purpose and method

This document audits [`context-workflow-internals-implementation-plan.md`](context-workflow-internals-implementation-plan.md)
(the "PLAN") against [`context-internals-design-pass3.md`](context-internals-design-pass3.md)
(the "DESIGN"), which is the authoritative settled design: pass 3 states the resolved
position directly, with every pass-1/pass-2 criticism either resolved, retracted, or
carried as an explicit admission, plus the user's own point-by-point responses.

The audit asks three questions of every normative element:

1. **Deviation** — does the PLAN contradict a settled DESIGN position?
2. **Addition** — does the PLAN introduce a mechanism with no DESIGN basis?
3. **Omission** — does the PLAN drop a settled DESIGN position?

Chronology: DESIGN pass 1 is 14 June, pass 2 and pass 3 are 15 June, and the PLAN and its
handoff share one timestamp on 16 June. The handoff is a near-simultaneous elaboration of
the PLAN, not an independent document — auditing the handoff against the PLAN finds little,
so this audit targets the PLAN.

## Verdict

| category | count | severity |
| --- | --- | --- |
| Faithful | 21 elements | — |
| Deviations | 2 | 1 major, 1 consequential |
| Additions without DESIGN basis | 9 | 1 major, 3 needing ratification, 5 benign |
| Omissions | 8 | 2 consequential, 6 mild |

The PLAN is a **high-fidelity rendering of DESIGN Part I §I.3–§I.5 and §I.8** — the node
state machine, cascade, glitch-freedom invariant, three-case hold taxonomy, and concurrency
model are transcribed accurately, including nuances that are easy to lose. The divergence is
concentrated in one area: **the public handle and navigation surface (§I.2)**, where the PLAN
reverses a settled position and substitutes an invented mechanism.

---

## Part A — Faithful

Recorded so the audit is not read as uniformly negative. These DESIGN positions are
transcribed correctly, several with nuance intact:

| DESIGN | PLAN | note |
| --- | --- | --- |
| Six node states `unwired/blocked/waiting/computing/complete/failed` | §4 | exact |
| Upstream failure does not propagate as `failed`; dependents are `blocked` | §4 | exact |
| Block reason enum; `blocked-by-unwired` wins when both apply | §4 | exact, including priority |
| Connected-optional pins gate; a failed optional upstream blocks | handoff | omitted in PLAN, **restored** in handoff |
| Cascade: on leaving `complete`, downstream **re-derive**, don't force-set | §8 | exact, both refinements |
| Trigger is "leaves `complete`", broader than "input changed" | §8 | exact |
| Glitch-freedom: invalidate cone before launching wavefront | §8 | exact |
| O(cone) marking in v1; epoch stamping deferred | §8 | matches the V.1 resolution |
| Launch immediately, delay cancellation | §10 | exact |
| Three holds: upstream-confirmation ~5 min event-driven; self-edit ~15 s fixed; completed-downstream tempref | §10 | **all three, faithfully** |
| ≤3 cap on **in-flight** superseded runs; completed ones leave the cap | §10 | exact |
| `ctx.prune()` **and** `ctx.a.prune()` | §10 | exact |
| Preemption stays optional | §1, handoff deferrals | matches V.3 resolution |
| Checksum-wired first; future-wiring ships with fire-and-forget | §9 | matches §I.6 phasing |
| `waiting` nodes own no future-wired E/T in v1 | §9 | correct scoping |
| Fire-and-forget out of v1 | §1 | correct |
| `ctx.node.clear_exception()` forwarded to the private E/T | §11 | matches V.4 resolution |
| Substrate split: optional-pin rule + cancellation are **not** Context logic | §1 | explicit |
| **Awaiter sets** named as the substrate cancellation model | §1 | correctly tracks III.1 |
| Reactive scheduler uses `softcancel` exclusively, including deletion | §6 | exact |
| Concurrency: all transitions serialized; only `.compute()` concurrent, callbacks re-enter | §13 | matches the V.5 resolution |

---

## Part B — Deviations

### B1. `[MAJOR]` Navigation is reversed, and the edge model is left unreachable

DESIGN §I.2 states, as settled:

> - **Navigation** (`ctx.a.sub`, `ctx.a[i]`, `ctx.a[x:y]`) returns an **ephemeral `Cell`**: a
>   transient view that accumulates a path over a node. Navigation does **not** grow the DAG.
> - **Edges** are created by assignment: `ctx.b = ctx.a.sub` captures `(source-node, path,
>   celltypes)` **on the edge** — not as a stored `Expression`.

PLAN §5 states the opposite:

> `ctx.a.b` is never cell data navigation; it is ordinary `Cell` attribute access, preserving
> class-defined attributes such as `.run` and `.value`. `ctx.a["b"]` is sugar for
> `ctx.a.pins["b"]`.

The reversal is unmarked — the PLAN does not note that it is overturning a settled position,
and gives a namespace-collision rationale (`.run`/`.value` shadowing) for a change that is
structural.

**Consequence.** The PLAN *keeps* DESIGN's edge model — §4 defines `Edge` with `source: ViewPath`
and "for a source cell, the suffix addresses the cell value", and the handoff's `ViewPath`
example is literally `("a", "y")` for "subcell `y` of cell `a`". But with navigation banned there
is **no syntax that can produce a suffixed source**. The DESIGN's own worked example,
`ctx.b = ctx.a.sub`, is unexpressible in the PLAN's API. The feature is specified and unreachable
— and in the experimental implementation it is indeed unreachable (`ctx.b = ctx.a.pins.x` raises
`TypeError`, because the bound-source check enumerates view classes and `CellPinView` is not one).

**Status.** [`context-internals-followup-design.md`](context-internals-followup-design.md)
supersedes this ("`ctx.a.b` can never be cell data navigation" is listed under *Superseded
Experimental Rules*) and restores uniform projection. The follow-up is therefore a **restoration
of DESIGN §I.2**, not a new direction.

### B2. `[CONSEQUENTIAL]` "The private shadow is abandoned" is not carried over

DESIGN §I.2 is explicit:

> **Binding is a move, not a copy.** On attach, the builder's private state (path / celltype /
> value-or-edge) migrates *into* the DAG node and the private shadow is **abandoned**; the node
> is the sole source of truth. There is **no dual-write window**.

The PLAN carries "binding mutates the handle's state backend in place" (§3) and the handoff
carries "binding is a move of state, not a copy" — but **neither states that the private state
must never be read again**. That single omitted clause is the whole content of the invariant.

**Consequence.** The experimental implementation reads abandoned private state in at least two
places: `Cell.item()` derives from the private `_path` slot rather than the backend path, so
chained navigation on a bound cell silently drops a level (`c.a.b` yields path `b`); and
`Cell.path_python` returns the private slot while `Cell.path` returns the backend's. Both are
direct consequences of the un-transcribed clause.

---

## Part C — Additions without DESIGN basis

Presence counts are lines-with-match across the three design documents (des1/des2/des3) versus
the PLAN.

| addition | des1 | des2 | des3 | PLAN | classification |
| --- | --- | --- | --- | --- | --- |
| `Cell.pins` / cell subcells / join `Transformation` | 0 | 0 | 0 | 7 / 21 / 3 | **major — ratify or drop** |
| Subcontexts (`ctx.sub = Context()`, copy, `SubContextView`) | 0 | 0 | 0 | 16 | needs ratification |
| Non-eager mode + activation leases (`active`/`derived-active`) | 0 | 0 | 0 | 5 / 4 | needs ratification |
| Dependency-declaration contract (legality matrix, recursive binding, capture) | — | — | `[OPEN]` | §6 | needs ratification |
| Graph serialization (`get_graph`/`set_graph`, static DAG JSON) | — | — | out of scope | §12 | benign |
| `Transformer.pins` prebinding (`functools.partial`) | 0 | 0 | 0 | 9 | benign |
| `ctx.tf.inp` / `.result` / `.code` views | 0 | 0 | 0 | 2 / 4 | benign |
| Pseudo-anonymous names (`cell1`, `cell2`), `top_id` | 0 | 0 | 0 | 4 / 3 | benign |
| `translate()` compatibility no-op | 0 | 0 | 0 | 2 | benign |

Note that `Overlay`, `ConstantProducer`, `RunRecord`, `NodePath`/`ViewPath` are also
DESIGN-absent but are **not** listed: inventing internal data structures is what an
implementation plan is for. The concern is only where an addition encodes *semantics*.

### C1. `[MAJOR]` `Cell.pins` and the join `Transformation`

Zero occurrences in any design document. Every "pins" mention across all three DESIGN passes is
about *transformer* input pins (optional pins, connectivity, `tf_checksum` construction). There
is no cell-pins, cell-subcell, subvalue-composition, or StructuredCell discussion anywhere.

This is not merely an addition — it is the mechanism that **replaces** the position reversed in
B1. DESIGN composes cell values through edges carrying paths; the PLAN composes them through a
per-cell pin namespace plus a synthetic join transformation.

**The un-vetted consequence.** Under DESIGN, a cell is a pass-through: its value is its producer's
checksum, optionally via an `Expression` path. Under the PLAN, a cell with pins **owns a
computation** — PLAN §3: "it concretifies to a simple, deterministic join `Transformation` that
takes the pin inputs and returns a dictionary `{pin_name: pin_value}`." That silently gives cells
four properties DESIGN analysed only for transformers:

- a cell can be `computing` and `failed` on its own account;
- a cell can accumulate **superseded runs** and needs hold windows (§I.5 was written for
  transformer runs);
- cells enter the `softcancel` / awaiter-set layer (Part III);
- cell derivation forks into two paths — root-producer versus pieces-assembly.

None of this appears in any DESIGN document, because the concept postdates them.

**Recommendation.** Ratify or drop, explicitly. Ratifying means writing the §I.5/Part III
analysis for cell-owned computations that was never done. Dropping means returning to §I.2, which
is also where the follow-up design's uniform-projection rule already points.

### C2. Subcontexts

Zero DESIGN basis (0/0/0 vs 16 in the PLAN). DESIGN's graph model is flat and says nothing about
namespaces, path prefixes, or subtree copying. The PLAN's subcontext copy semantics — copy nodes
under the prefix, copy internal edges, **drop boundary-crossing edges** — is a nontrivial rule
invented without review. Dropping edges silently on copy is the kind of behavior that should have
had a design pass.

### C3. Non-eager mode and activation leases

The *axis* has a one-line basis: the user's response to V.11 says "Right that evaluation can be
eager or lazy". The **mechanism** — `active_count` / `derived_active_count`, lease acquisition
over the upstream cone, release on completion, softcancel of abandoned work — is entirely
plan-invented.

More importantly, the PLAN's non-eager mode inherits the exact objection DESIGN used to *reject*
pull-by-default:

> **Resolution (pass 3, per user).** Rebutted — … **a pull coroutine is still concurrent with
> input updates**, so a demanded computation can still be superseded mid-flight and the same
> hold/supersession questions recur.

The PLAN never addresses how leases interact with supersession, holds, or the three-case hold
taxonomy. A demand-gated node whose input changes mid-flight is in exactly the state DESIGN said
pull does not simplify.

### C4. The dependency-declaration contract

DESIGN Part IV is explicitly `[OPEN]` — "How a dependency on a `Context`-held node is declared,
captured, and resolved is deferred." The PLAN §6 closes it comprehensively: a legality matrix,
recursive binding of unbound closures, pseudo-anonymous naming, cross-top-level rejection, and
bound-to-unbound snapshot capture with per-state rules.

Closing an open item is a legitimate plan-level act. Flagged because it is the **largest**
plan-side invention by volume, it received no design pass, and DESIGN did leave a sketch (V.10
resolution: a declared edge is a future-wired `Expression` that becomes checksum-wired by
substitution) that the PLAN does not reference. The PLAN's per-tick materialization is consistent
with checksum-wired-first phasing, but the relationship should be stated rather than left implicit.

### C5. Benign additions

Serialization (DESIGN lists it as out of scope; a v1 needs it), `Transformer.pins` (grounded in
shipped code — `_args`/`ArgsWrapper` and `_bind_arguments` already implement prebinding, so the
PLAN documents an existing substrate feature under a new name), the transformer view surface,
pseudo-anonymous naming, and `translate()`.

One sub-item deserves a note: the PLAN invents the rule that **`.set(None)` stores the canonical
`null` checksum while `= None` is deletion sugar**. That is a subtle, easily-confused distinction
with no DESIGN basis. It is defensible but should be a stated decision, not an inherited one.

---

## Part D — Omissions

### D1. `[CONSEQUENTIAL]` Determinism assumption and irreproducibility scoping

DESIGN §I.8 opens: "**Determinism is assumed.** The retain-and-compare loop (§I.5) assumes *same
input ⇒ same result checksum*. **Irreproducible transformations are out of scope for workflows.**"

PLAN: zero occurrences of "irreproducib". The PLAN implements the entire retain-and-compare hold
machinery (§10) without ever stating the assumption it rests on. An implementer has no way to know
that the holds are unsound for irreproducible transformations, or that such transformations are
scoped out.

### D2. `[CONSEQUENTIAL]` "Reinstatement is not a special operation"

DESIGN §I.5 states it twice, and V.12.1 exists specifically to insist it be said plainly:

> "Reinstate `B`" (case (a)) is mechanically *nothing*: `B` re-derives the **same** `tf_checksum`
> and re-latches onto the still-running submission via the §III awaiter set. There is no surgical
> resurrection of a run — the hold merely keeps that submission alive long enough for the
> re-derivation to find it.

PLAN: absent. The predicted failure mode materialized — the experimental implementation carries a
`RunRecord` supersession/generation bookkeeping layer rather than relying on re-derivation plus
re-latching.

### D3. Equilibrium classification and quiescence

DESIGN §I.3 defines equilibrium vs. out-of-equilibrium states, "quiescence ⇔ no node is `waiting`
or `computing`", the guarantee that quiescence is reachable, "quiescence ≠ success", and the
relation "after `prune`, quiescence == cluster-idle". PLAN: zero occurrences of either term.

This is the vocabulary for test "settled" detection, and the PLAN's test strategy has no settled
-detection test as a result.

### D4. Detach

DESIGN §I.2 makes detach half of the single-source-of-truth contract: "On detach, the node's state
is snapshotted *out* into a fresh standalone builder." PLAN: absent (2 hits, both "fire-and-forget
detach"). The follow-up design reintroduces it conditionally.

### D5–D8. Mild

- **`id()`-keyed caches over views must not be used** (§I.2) — the PLAN keeps "view identity is not
  meaningful" but drops the operational prohibition.
- **Marking/launching decoupling** (§I.4) — the PLAN preserves the ordering but drops "running E/T
  launched with priority, bursts capped; pending E/T submitted lazily". Partly moot in a
  checksum-wired v1.
- **"Connected-optional pins lose laziness"** (§I.8) — the one admitted trade-off DESIGN insisted be
  "stated, not silently accepted"; absent from the PLAN.
- **Per-tick E/T materialization cost** (§I.2, V.12.2) — the note that cost is bounded to the
  invalidated cone and is a checksum-sized hash, not a buffer rehash. Added to DESIGN specifically
  so it would not be mistaken for a whole-graph rehash; dropped.

---

## Part E — Corrections to earlier claims

Two items I previously reported as "dropped by the plans" were wrong, and the PLAN is correct:

- **`refholding`** was not dropped by the PLAN — it was **superseded by DESIGN itself**. Pass 3
  §III.1: "The awaiter set replaces the hand-rolled refcount… There is **no** manually-maintained
  integer refcount and **no** `refholding` flag — the set's membership **is** the count." The PLAN
  §1 correctly names "awaiter sets".
- **The jobserver / daskserver cancellation asymmetry** was not silently re-accepted. Pass 3 Part
  III **fixes** it (III.7: "This fixes the jobserver multi-tenant footgun… rather than admitting
  it") and marks the whole area `[SUBSTRATE]`. PLAN §1 explicitly delegates cancellation to the
  substrate. Correct delegation, not an omission.

**witness/observable** is likewise correctly handled: DESIGN §I.8 lists it as open/out of scope,
and both plans carry it as a deferral.

---

## Recommendations

1. **Treat the PLAN, not the handoff, as the divergence point.** Auditing the handoff against the
   PLAN yields almost nothing; the handoff mostly elaborates (its own additions — the overlay
   assembly algorithm, "dependent path", `ExceptionInfo`, transformer pin-inference rules — are
   specification detail, and in one case it *restored* a DESIGN rule the PLAN omitted).
2. **Resolve `Cell.pins` explicitly** (C1). It is load-bearing in the current code, contradicts
   §I.2, and has never been analysed against §I.5 or Part III.
3. **Ratify or re-scope C2–C4** — subcontexts, activation leases, and the Part IV closure. Each is
   a real feature; none has a design pass. For C3 in particular, state how leases interact with
   supersession, given that DESIGN rejected pull-by-default on exactly that ground.
4. **Re-import D1–D4** into the follow-up plan: the determinism assumption, "reinstatement is not a
   special operation", the equilibrium/quiescence vocabulary, and detach. D1 and D2 are the two
   whose absence has already produced consequences.
5. **Add the abandoned-private-state clause** (B2) as a normative sentence, not an implication. The
   follow-up design already states it ("it must not be read by bound behavior") — confirm it
   survives into the follow-up plan, since it is the clause whose absence produced a shipped bug.

---

# Appendix — Coverage by the follow-up design and plan

This appendix checks each concern above against
[`context-internals-followup-design.md`](context-internals-followup-design.md) (FU-DESIGN) and
[`context-internals-followup-plan.md`](context-internals-followup-plan.md) (FU-PLAN, the
handoff-ready version). Status is assessed against what those documents *specify*, not against
implementation state.

## A.1 Summary

| # | concern | status | where |
| --- | --- | --- | --- |
| B1 | Navigation reversed; edge model unreachable | **addressed** | FU-PLAN Purpose, Cell projection, Phase 5 |
| B2 | "Private shadow abandoned" not carried over | **addressed** | FU-PLAN Package direction, Phase 1/2/3 acceptance |
| C1a | `Cell.pins` public API | **addressed (dropped)** | FU-PLAN Explicitly Removed, Phases 3/9 |
| C1b | Cells owning a join `Transformation` | **partial** | join survives at FU-PLAN Phase 6 |
| C2 | Subcontexts unratified | **not addressed** | explicitly out of scope |
| C3 | Non-eager mode + activation leases | **not addressed** | explicitly out of scope |
| C4 | Part IV closure unratified | **partial** | endpoint protocol added; ratification absent |
| C5a | `.set(None)` vs `= None` | **addressed (reversed)** | FU-PLAN Cell assignment |
| C5b | Serialization closes a DESIGN-open item | **partial** | extended, still unratified |
| C5c | `Transformer.pins` prebinding | **addressed** | sole pin namespace, parity required |
| C5d | `tf.inp` / `.result` / `.code` | **addressed** | `.inp` removed; other two specified |
| C5e | Pseudo-anonymous names, `top_id`, `translate()` | **not addressed** | carried forward |
| D1 | Determinism assumption / irreproducibility scoping | **not addressed** | 0 occurrences |
| D2 | "Reinstatement is not a special operation" | **not addressed** | 0 occurrences |
| D3 | Equilibrium / quiescence vocabulary | **not addressed** | 0 occurrences |
| D4 | Detach | **partial** | FU-DESIGN conditional; FU-PLAN absent |
| D5 | `id()`-keyed caches prohibited | **addressed** | "identity is never dependency identity" |
| D6 | Marking/launching decoupling | **not addressed** | out of scope |
| D7 | Connected-optional loses laziness | **not addressed** | tested, not admitted |
| D8 | Per-tick materialization cost | **partial** | mechanism kept, cost note absent |

**7 addressed, 5 partial, 8 not addressed.** Every concern in the *handle and navigation* cluster
— which is where the audit found the divergence concentrated — is resolved. Every concern in the
*scheduling and execution-semantics* cluster is carried forward untouched, which is consistent
with FU-PLAN's own scoping statement: it "assumes the existing Context graph, state machine,
eager/non-eager scheduler, pruning, and static serialization code remain the starting
implementation."

## A.2 Fully addressed

**B1 — navigation.** FU-PLAN restores DESIGN §I.2 exactly: "Attribute, item, and slice reads
return derived `Cell` projections in standalone and bound modes"; "Projection retains the complete
path and may be arbitrarily deep where Expression supports it"; "Cell dot-navigation prohibition"
is listed under *Explicitly Removed*. Critically, the **unreachable edge source** is fixed
explicitly — Phase 5: "Store full normalized projection paths on source edge endpoints. Permit
Cell source suffixes to every depth supported by Expression", with the test
`ctx.out = ctx.data.a.b[0]`. That is the DESIGN's own `ctx.b = ctx.a.sub` example made
expressible again.

**B2 — abandoned private state.** Better handled than in DESIGN, which stated it in one sentence.
FU-PLAN names the exact anchors (`Cell.path_python`, `Cell.item()`, `Cell.slice()`,
`_transformer_config_from_builder()`), states the contract ("Bound code never reads abandoned
standalone state"), and enforces it at three acceptance gates plus the completion checklist.

**C1a / C5a / C5c / C5d.** `Cell.pins` is removed with the audit's own rationale quoted as
grounds — "introduced by the alpha implementation plan, **not by the ancestor designs or legacy
Seamless**". `None`-as-deletion is reversed to the cleaner rule (`None` is a value, `del` deletes),
which also makes assignment/`.set()` equivalence exact. `.pins` becomes the sole Transformer pin
namespace with alias/lookup parity required; `.inp` is removed.

**D5.** "Lookups may return fresh objects. Python object identity is never dependency identity."

## A.3 Partially addressed

**C1b — the join `Transformation` survives, and its consequences are still un-analysed.**

This is the most important residue. FU-PLAN removes the *per-pin* join for transformers ("never
join descendant pieces", "contains no per-pin join/overlay path") but **retains a join for cells**:

> root set value combined with one-level incoming edges -> join Transformation snapshot;
> projection from an assembled result -> projection Expression depending on the join
> — FU-PLAN Phase 6

So a cell with a root value plus one-level edges still **owns a computation**. The audit's C1
concern had two halves; the API half is resolved, but the execution half is not. A cell can still
be `computing` and `failed` on its own account, still accumulate superseded runs, and still enter
the awaiter-set / `softcancel` layer — and DESIGN §I.5 and Part III were written for transformer
runs. Neither FU document analyses this.

This is now a *smaller* question than before (it applies only to multi-input cells, not to every
`.pins` use), but it is the same unreviewed question.

**C4 — Part IV.** The *mechanism* improves substantially: `BoundEndpoint` descriptors replace the
view-class registry, and — addressing a gap the audit flagged separately — "both Context edge
wiring and lower-package standalone snapshot capture consume this protocol; no second
capture-specific registry of workflow helper classes is permitted", which retires
`_capture_workflow_source`'s attribute-sniffing. The capture-state matrix
(complete/computing/failed/waiting/unwired/blocked) is required as a test.

What is still missing is *ratification*: FU-PLAN never references DESIGN Part IV or its V.10
contract sketch (a declared edge stored as a future-wired `Expression` that becomes checksum-wired
by substitution). Phase 5's per-tick materialization is consistent with checksum-wired-first
phasing, but the relationship is left implicit. Recursive binding and pseudo-anonymous naming are
preserved verbatim ("Preserve recursive binding only for genuinely standalone builders") without
review.

**C5b — serialization.** Extended rather than ratified: `call_mode`, canonical Expression path
encoding, and independent load-time validation of source vs. target paths are all added. Still
closes a DESIGN-open item without a design pass, but it is now considerably more defensible.

**D4 — detach.** FU-DESIGN mentions it conditionally ("Detaching, if implemented, snapshots node
state into a fresh standalone builder"). FU-PLAN does not implement it — all four "detach"
occurrences are "detached snapshot" (DirectTransformer) or "detached current value" (the RMW
transaction). DESIGN treats detach as half of the single-source-of-truth contract; it remains
unbuilt.

**D8 — per-tick cost.** The mechanism is preserved (Phase 5: "Materialize source Expressions per
tick"), but DESIGN's clarifying note — cost is bounded to the invalidated cone and is a
checksum-sized hash, never a buffer re-hash — is still absent. See A.5 for why this now matters
more, not less.

## A.4 Not addressed

**C2, C3, C5e** are carried forward by explicit scoping. Two notes:

- FU-PLAN Phase 8 *preserves* the subcontext boundary-edge drop ("while continuing to drop
  boundary-crossing edges"), so the unreviewed rule is now deliberately retained rather than merely
  inherited.
- FU-PLAN *consumes and tests* the activation-lease mechanism (Phase 6: "Non-eager root and
  projected demands increment/release exactly one activation lease set"; Phase 10 audits release)
  without ratifying it. The specific gap the audit raised — that DESIGN rejected pull-by-default
  because "a pull coroutine is still concurrent with input updates, so a demanded computation can
  still be superseded mid-flight" — is still unanswered.

**D1, D2, D3, D6, D7** have zero occurrences in either FU document. D1 (determinism assumption)
and D2 (reinstatement is not a special operation) remain the two whose absence has already
produced consequences, and neither is scoped out — they were simply never carried forward. D3's
practical need is partly met without the vocabulary: Phase 10 adds "a small reactive diamond using
a deep projected source to check glitch-free invalidation."

## A.5 New additions introduced by the follow-up itself

Applying the same standard the audit applies to the alpha plan, one FU-PLAN feature has no basis
in DESIGN or in the alpha plan:

**Writable bound projections at arbitrary depth.** `ctx.a.b.c = 12` becomes legal, implemented as
"a serialized read-modify-set transaction that replaces that same root set value". DESIGN's
navigation is read-side only; it never says projections are writable.

The specification is careful — authority interaction, `ValueUnavailableError`, container
bootstrap/`TypeError` rules, single-commit augmented assignment, and the guarantee that no non-root
producer or deep target is persisted are all defined. Two consequences are not discussed:

1. **Cost scales with cell size, not edit size.** Every deep value update re-serializes,
   re-checksums, and re-deposits the *entire* root value. For a large `mixed` cell — or any cell
   whose value is expensive to materialize — a small edit is a full re-hash. This is in direct
   tension with the DESIGN note dropped at D8 ("never a re-hash of buffers"); the two should be
   reconciled explicitly, and the interaction with `deepcell`/`folder` celltypes stated.
2. **A value/source asymmetry replaces the read/write asymmetry.** `ctx.a.b.c = 12` is legal while
   `ctx.a.b.c = source` raises `PathError`. This is a real improvement over the alpha rules and is
   defensible — value updates fold into one producer, connections need a persistent target — but it
   should be stated as the deliberate rule it is, since "same syntax, different depth limit
   depending on RHS type" is the kind of thing that reads as arbitrary.

Also new and welcome, with no predecessor in any document: the error contract
(`BoundStateError`, `ReadOnlyEndpointError`, `StaleWorkflowHandleError`, `ValueUnavailableError`)
and handle-lifetime semantics.

## A.6 Defects the follow-up plan identified independently

For completeness, FU-PLAN's *Current anchors* sections catch several defects this audit did not
raise, and several it raised only as implementation observations:

- `Cell.__getattr__` turning a bound-only property's `AttributeError` into a same-named projection;
- `Cell.pins` importing `seamless_workflow`, violating dependency direction;
- `ctx.out = already_bound_tf` rebinding instead of wiring;
- `DirectTransformer.__call__` broken by a backend that returns a raw value;
- `Path`/`ViewPath` typed as string tuples, blocking integer-index endpoints from round-tripping;
- the graph not recording delayed/direct call mode;
- deletion leaving handles to fail with raw `KeyError`.

## A.7 Recommendation

The follow-up documents resolve the audit's *structural* findings. What remains is a short,
well-defined residue that is largely orthogonal to their scope:

1. **C1b** — decide whether cells may own a join `Transformation`, and if so write the §I.5 / Part
   III analysis for cell-owned runs. This is the only residue that is inside FU-PLAN's own scope,
   since Phase 6 specifies the join.
2. **D1 and D2** — re-import the determinism assumption and "reinstatement is not a special
   operation" into whichever document owns scheduling. Neither was scoped out; both were dropped.
3. **A.5.1** — reconcile deep-value-update RMW cost with the per-tick no-re-hash property, and
   state the `deepcell`/`folder` interaction.
4. **C2, C3, C4-ratification, D3, D4, D6, D7** — schedule as a separate scheduling-and-execution
   review. They do not belong in a handle-specialization plan, and FU-PLAN is right to exclude
   them; they should not be lost by that exclusion.
