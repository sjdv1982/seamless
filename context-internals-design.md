# Reactive `Context` Internals — Design + Critique

> This document has two parts. **Part I** synthesizes a design from a working
> discussion into a single coherent statement, resolving the internal
> contradictions in that discussion (later corrections win over earlier text).
> **Part II** is a critical review of Part I: flaws that must be *fixed* or
> *explicitly admitted*, with proposed alternatives.
>
> It is the appendix of [`cells-and-expressions-implementation-plan.md`](cells-and-expressions-implementation-plan.md)
> made concrete — the reactive layer that sits **on top of** the immutable
> functional substrate (`Expression`/`Transformation` nodes, checksum futures).
> Part I is the author's position, cleaned up; Part II is the reviewer's.

---

# Part I — Design

## 1. Scope and substrate

The functional layer is settled: `Expression` and `Transformation` are immutable,
content-addressed nodes in one lazy DAG, each producing a checksum future; `Cell`
and `Transformer` are mutable, build-once builders. `Context` reintroduces
*reactivity* on top, without leaking reactivity into the immutable layer. Nothing
below the `Context` knows a `Context` exists.

Throughout, **E/T** abbreviates "`Expression` and/or `Transformation`" — the two
immutable node kinds the `Context` fires.

## 2. Internal representation: a `Context` holds only a DAG

Internally a `Context` holds **only a DAG** of nodes (this mirrors legacy
Seamless). `Cell`s and `Transformer`s are **not** stored objects; they are
**materialized ephemerally on demand** as views over a node.

This requires a design change to `Cell` and `Transformer`:

- Their public surface is implemented as **accessors** (already true for
  `Transformer`, whose `.code`, `.meta`, `.scratch`, … are `@property`).
- Each carries a `.context` attribute. **If set**, the accessors redirect into
  the `Context`'s DAG under a **node key**. **If unset**, they redirect to the
  builder's **private internal state** (the standalone, functional behavior).

So a context-bound builder is a thin, reconstructable handle; the single source of
truth is the DAG node.

## 3. Connectivity and node lifecycle states

The `Context` tracks, per node, whether its input pins are **"sufficiently
connected."** Pin handling (looser than legacy Seamless):

- An **unconnected optional** pin is **accepted** and is simply **not part of the
  transformation** — it does not gate the node.
- A **connected optional** pin is treated as a **required** pin (it gates), with
  one new escape valve: unlike legacy Seamless, a transformer may now **return no
  result** provided its result celltype can encode JSON `None` (i.e. `plain` or
  `mixed`). An optional pin that receives a JSON `None` is **dropped from the
  transformation**. (Consequence: "pin absent" and "pin present-but-`None`"
  canonicalize to the **same** `tf_checksum` — a free cache convergence. The
  "no result" value must be the canonical checksum of JSON `null`, a real
  content-addressed value — *not* `result_checksum is None`, which already means
  "not computed".)

So "sufficiently connected" = every **required** pin wired, plus every **connected
optional** pin wired; unconnected optional pins are absent.

Node states and transitions:

| state | meaning |
|---------------|------------------------------------------------------------------|
| `unconnected` | not yet sufficiently connected |
| `upstream` | sufficiently connected, but some upstream node is `unconnected` or `error` (the node is *blocked*, not itself errored) |
| `pending` | upstream nodes are progressing but **not all complete** |
| `running` | every **required** and **connected-optional** upstream node is `complete` (where `complete` may mean *completed with `None`*) |
| `complete` | result checksum available |
| `error` | this node's own evaluation failed |

- A **`pending`** node owns a **future-wired** E/T (its inputs are upstream
  futures, not yet resolved checksums).
- A **`running`** node owns a **checksum-wired** ("running") E/T: a concrete E/T
  whose inputs are resolved checksums and which therefore has, by default, a
  constructed transformation checksum. The running E/T **replaces** the
  future-wired one (the future-wired one is cancelled).
- An **upstream error does not propagate as `error`**; the dependent stays
  `upstream` (blocked). `error` is reserved for a node's own failure.
- The `upstream`/`pending` split is by **autonomy**: a `pending` node unblocks
  **on its own** as upstream computation finishes; an `upstream` node unblocks
  **only via an external change** (connect the missing input, or fix the upstream
  error). A connected-optional pin whose upstream *errors* therefore blocks the
  node (it is treated as required).

**Equilibrium vs out-of-equilibrium.** The six states split cleanly:

| kind | states | leaves only via |
|----------------------|--------------------------------------------------|------------------------|
| **equilibrium** | `complete`, `error`, `upstream`, `unconnected` | an **external change** |
| **out-of-equilibrium** | `pending`, `running` | **autonomously** |

This is the autonomy split generalized to all six states. It gives the dynamical
picture: an **external change perturbs**, then the Context **relaxes** — every
out-of-equilibrium node flows toward equilibrium (`pending → running →
complete`/`error`; `pending → upstream` if an ancestor errors), and only an external
change can push back out. Two consequences used later:

- **Quiescence** ⇔ **no node is `pending` or `running`** (every node sits in an
  equilibrium state). Within scope (a DAG of reproducible transformations) it is
  **guaranteed reachable** in finite steps after a finite burst of edits — the basis
  for test "settled" detection and the fire-and-forget seal (F6). Equilibrium is a
  property of node **states** (current results); a `complete` node may still have a
  **superseded** run in flight, but that run is obsolete by construction and does
  **not** count against quiescence.
- **Quiescence ≠ success.** Equilibrium includes `error`, `upstream`, and
  `unconnected`, so "settled" is not "all `complete`." *Success* is the stronger
  condition that all **witness/observable** nodes are `complete`.

## 4. Future-wired vs checksum-wired E/T

Both wirings are supported. The future-wired E/T's only *current* payoff is a few
seconds of latency (start constructing before inputs resolve), which on its own is
**not worth the complexity**. It is retained because the planned **fire-and-forget**
feature — tearing down the `Context` process while Dask keeps executing the
workflow — meshes naturally with future-wired E/T. (See Part II §10 for the
proposal to defer it until then.)

## 5. Reactive change propagation

A "change" is an update to a node's value/config or to connectivity. On a change,
for the changed node and everything downstream:

1. **Future-wired E/T are cancelled immediately.** They hold no completed work.
2. **Checksum-wired ("running") E/T are *not* cancelled immediately.** A change
   may be inconsequential (e.g. a cosmetic edit to a `Transformer`'s source that
   does not alter its result), so prematurely cancelling running work — and the
   downstream work feeding on its already-completed checksum — would be wasteful.

The reactive rule for running work is **"always relaunch immediately, and *also*
retain the superseded run for a while"**:

- The newly-updated running E/T is launched **as soon as possible**. There is no
  debounce delay on launching.
- The **superseded** running E/T (and, downstream, the *previously completed*
  checksum being consumed) is **retained for a grace period** — on the order of
  **1 minute** for a downstream consumer of a now-stale checksum, and **~15
  seconds** for an in-flight transformation whose own input just changed (in case
  the change is reverted). The grace is how long the *old* work is kept, **not**
  a delay before starting the *new* work.
- The `Context` always tracks which run is **current** and which are
  **superseded**.

**The goal of the grace period** is to **prevent running work from being cancelled
while there is still a plausible chance it will be needed after all** — a reverted
edit, an oscillation, or another node requesting the same checksum. The window is
therefore sized to the **human edit-settling timescale** (seconds), *independent*
of the transformation's own runtime: holding a superseded 2-hour run for 15 s after
an edit is worthwhile precisely because a revert within those 15 s saves the entire
restart. The hold is naturally realized as a **temporary (decaying) reference**
(consistent with "all timers are temporary references"), which also yields
memory-pressure release for free. The two horizons (≈1 min vs ≈15 s) are best read
as a **function of holding cost** — a completed *result* is cheap to keep, so it is
held longer; a *live running* transformation burns compute, so it is held more
briefly (and very expensive runs, e.g. GPU, shorter still).

### Nodes do not "hang on" to completed work

A node need not specially retain completed work. It may **let go on any change**.
If new work later turns out to correspond to previously completed work, the
**content-addressed cache yields an instant hit** — so correctness and most of the
performance benefit come from the cache, not from holding references. Retention of
superseded *running* work (above) is purely a transient optimization to avoid
cancel/relaunch churn during rapid edits.

## 6. Refcounting and soft-cancellation of running work

Multiple node-bound `Transformer`s (across nodes, or across superseded/current
runs) may share **one** running `Transformation` (same `tf_checksum`). Therefore a
`Context`-initiated cancel must be a **soft** signal, not an unconditional kill.

**The refcount lives in-process, in `seamless-transformer`'s transformation
cache** — *not* in singleton E/T objects, and *not* in any server. (An earlier
idea to make `.construct()` resolve each E/T to a content-keyed *singleton*, à la
`Buffer`, and to drive cancellation via `__del__`, was **dropped**: `Buffer` does
not actually do this today, and the singleton route mishandles non-`Context`-held
work. A separate `ContextHeldTransformationCache` was then proposed and in turn
**converged onto simply augmenting the existing in-process cache**.)

Mechanism:

- A **running-`tf_checksum` refcount** is kept in the in-process cache, guarded by
  a per-`Transformation` **`refholding`** flag. `Transformation.compute()`
  **increfs** and sets `refholding = True` (exactly once per object, and only when
  it launches/joins a *running* submission — a pure cache hit does not incref).
  Any **completion** *or* **`softcancel()`** **decrefs** iff `refholding` and
  clears it. Because *completion* decrefs too, the common compute→finish path is
  balanced without any softcancel. The same applies to `Expression` (see §7).
- **`softcancel()` cancels only when the refcount reaches zero.** Above zero, the
  run continues for the remaining holder(s).
- A **hard `cancel()`** is the escape hatch: it raises `CancelledError` in **all**
  running `.compute` coroutines for that checksum (not just the caller's), draining
  the refcount via their terminal decrefs. The reactive scheduler uses **only
  `softcancel()`** — including node deletion — because in-process **sibling nodes**
  may legitimately share a running `tf_checksum`; hard `cancel()` is reserved for
  explicit user-level "stop everything on this checksum now".
- The refcount is **only about currently-running work.** On **completion**, the
  entry is forgotten outright; `softcancel()` on a completed/forgotten checksum is
  a **no-op** ("softcancel is pointless" for completed work).

Holder policy per node:

- A `Context`-bound `Transformer` holds **at most one current** `Transformation`
  (which may be running) plus **a small bounded set of superseded ones** (say up
  to **three**, to bound resource use).
- When a superseded `Transformation` is **evicted** from that set, `softcancel()`
  is called on it (decref; cancel iff it was the last holder).

### Server boundaries (deliberately asymmetric)

- **In-process (`seamless-transformer`):** the latch-on described above, with the
  new refcount. This is the *only* layer the `Context` reasons about.
- **`jobserver`:** intentionally **simple**. It honors cancel requests
  **unconditionally**. If another client was latched onto the same transformation,
  that peer's job dies — **explicitly accepted as induced failure of a live peer.**
  No server-side refcount.
- **`daskserver`:** different, because it **already records latch-on**. It must be
  **smart enough to cancel a submitted future only if nothing is latched onto it.**

The caller never manages server-side latch-on; **the server decides, and the
caller never knows.** (There is *also* the strictly in-process latch within
`seamless-transformer`; that is a separate, lower layer.)

## 7. Expressions are cancelable too

The earlier claim that "expressions do no work" was **wrong**. Although the
*structural op* (the codebook: get-attr / get-item / slice / convert) is zero-cost,
an expression's resolution can take real time: **materializing a large input
buffer** and **writing a large output**. Expressions are therefore **cancelable on
par with `Transformation`s**, and participate in the **same** refcount layer.

I/O is **not** placed on a separate refcount layer — input materialization and
output writing share the one running-checksum refcount, not their own.

---

# Part II — Critique

The design is coherent and the in-process-only refcount is the right backbone. The
problems below are ordered roughly by severity. Each is tagged **[FIX]** (a defect
that should be corrected) or **[ADMIT]** (a defensible trade-off that must be stated
out loud rather than left implicit).

## 1. [FIX] §7 contradicts the just-implemented plan and the shipped code

The implementation plan states the opposite of §7: *"An expression's own
evaluation is effectively instantaneous and not separately cancellable"* and
*"effectively no cancellation surface of its own."* The shipped
[`Expression.cancel()`](../seamless-core/seamless/expression_class.py#L222) raises
`NotImplementedError`. So §7 is not a refinement — it **reverses** a settled
contract and contradicts running code.

The reconciliation is real and worth writing down precisely, because both sides are
half-right: the **codebook application** is zero-cost and uncancelable, but the
**buffer I/O envelope** around it (fingertip/materialize the input; serialize/write
the output) is neither instantaneous nor uninterruptible. The plan conflated "the
op is free" with "resolution is uninterruptible."

- **Action:** amend the plan's "not separately cancellable" sentence; implement
  `Expression.cancel()`/`softcancel()` so it interrupts the *I/O*, not the op.
- **Watch out:** the deep-checksum fast path (navigate the Merkle manifest, never
  materialize the parent) genuinely *is* near-instantaneous and uncancelable —
  there is nothing to interrupt. So "expressions are cancelable" is true **only on
  the materialize-and-apply and write paths**, not on the deep-navigation path.
  The contract should be: *an expression exposes a cancellation surface iff it must
  move bytes.*

> **Resolved (author, round 1):** expressions will be cancelable; the plan's "not
> separately cancellable" line is amended. **Residual:** keep the surface scoped to
> the byte-moving paths — deep navigation has nothing to interrupt.

## 2. [FIX] The node state machine is underspecified at exactly the load-bearing points

Three concrete gaps:

- **"all upstream complete" ⇒ `running` is wrong for optional/None pins.** §3 also
  says optional and `None` pins are "sufficiently connected." These collide: an
  optional upstream stuck in `upstream`/`error` must **not** block the dependent
  from reaching `running`. The real predicate is *"all **required** upstream
  `complete`, and every optional upstream is either `complete` or **definitively
  empty/errored**."* As written, one errored optional pin wedges the whole node in
  `pending` forever.
- **`error` non-propagation is a UX cliff.** Reserving `error` for a node's own
  failure and leaving dependents in `upstream` means a user sees a node that is
  *"waiting for input"* when it is really *"will never run because an ancestor
  failed."* Those are different conditions and need different surfacing (legacy
  Seamless distinguished "upstream error" / "pending" / "void"). Either add a
  distinct `blocked-by-upstream-error` substate, or make `status` report the
  reason.
- **Terminology overload.** "running" names *both* a node state *and* the
  checksum-wired E/T *and* the refcount key ("running-`tf_checksum`"). "pending"
  names a node state *and* the future-wired phase. This will produce confusing
  code and logs. Rename one axis (e.g. node states `blocked / partial / ready /
  done / failed`; keep "running"/"superseded" strictly for E/T runs).

> **Resolved (author, round 1):** bullet 1 settled — see the corrected predicate in
> Part I §3 (connected-optional pins gate; a `None` result is dropped). The
> `upstream`/`pending` split is by **autonomy** (`pending` self-clears, `upstream`
> needs an external change). **Residuals:** (i) represent "returns no result" as the
> canonical checksum of JSON `null`, *not* `result_checksum is None` (which already
> means "not computed"), or completion detection breaks; (ii) make the *reason*
> queryable on `upstream` (ancestor-unconnected vs ancestor-errored imply different
> user actions). Bullet 3 (terminology overload) is **still open**.

## 3. [FIX] "incref on compute / decref on softcancel" is unbalanced — the common path leaks

Stated literally, the refcount goes **up** on `compute()` and **down** only on
`softcancel()`. But the overwhelmingly common path is *compute → completes
normally → nobody ever softcancels*. That path never decrefs. §6 patches this
implicitly ("on completion the entry is forgotten outright"), but that patch is
load-bearing and must be promoted to a rule, not a footnote:

> The refcount entry is **created on first `compute()` of a running checksum**,
> incremented per holder, and **destroyed on completion** (or terminal error) —
> regardless of how many holders remain. `softcancel()` decrements iff the entry
> still exists; on a completed/destroyed entry it is a no-op.

Two consequences that need explicit handling:

- **Non-`Context` `compute()` must not incref into a cache nobody will clean up.**
  A bare, one-shot `tf.compute()` outside any `Context` should either not
  participate, or be balanced by an automatic decref on its own completion. Tying
  the *incref to the holder* (the `Context` node) rather than to `compute()` itself
  is cleaner: the `Context` increfs when it adopts a run and decrefs when it evicts
  it; `compute()` stays refcount-neutral. Recommend this.
- **Reinstate the *good half* of the discarded `__del__` idea.** The singleton
  scheme was rightly dropped, but "**auto-decref/softcancel on `__del__`**" was the
  sound part: it is the only backstop if a holder is GC'd (or the `Context` process
  dies mid-edit) without an explicit evict. Without it, a crashed/abandoned holder
  pins a running job until completion. Add `__del__ → softcancel` as a safety net
  (idempotent with explicit eviction).

> **Resolved (author, round 1):** the per-`Transformation` **`refholding`** flag
> balances incref/decref on *every* terminal path (completion decrefs too), so the
> leak is closed and "move the incref to the holder" is **withdrawn**. **Residuals:**
> (a) **do not incref on a pure cache hit** — only when a *running* submission is
> launched/joined, else you refhold completed work; (b) put the incref at the single
> submission-join **choke point**, not in each public API; (c) §4 still stands — a
> per-object flag does **not** fix the cross-generation aliasing of the shared,
> bare-`tf_checksum`-keyed counter. The `__del__ → softcancel` backstop is still
> wanted for GC'd/abandoned holders.

## 4. [FIX] A re-running `tf_checksum` aliases its own refcount entry across generations

The refcount is keyed by `tf_checksum`. But a deterministic checksum can oscillate
`running → complete → (input reverted, then re-changed) → running` and land on the
**same** `tf_checksum`. If entry destruction-on-completion races a new holder's
incref for the *next* run, two distinct runs share one entry, and a `softcancel`
meant for generation N can cancel generation N+1 (or be a spurious no-op). Key the
entry by **`(tf_checksum, run-generation)`** (or guard with a monotonic epoch), so
softcancel targets the run a holder actually adopted. The existing
[`_active_submissions`](../seamless-transformer/seamless_transformer/transformation_cache.py#L296)
map has the same single-key-per-checksum shape and the same latent hazard.

> **Resolved (author, round 2) — downgraded from `[FIX]` to minor:** moot for
> correctness, conceded. The refcount governs **cancellation only**; results are
> delivered by the content-addressed cache, never by the refcount, so aliasing
> cannot mis-deliver a result. Worst case is bounded re-work — a wrongly-cancelled
> run is re-submitted, or an orphaned run completes into a cache hit. **Residual
> (implementation):** keep *incref+latch* and *decref-to-zero+cancel+pop* atomic
> under the single `_active_lock`, so the wrong-generation interleaving cannot even
> transiently occur. Generation/epoch keying then becomes optional sugar (free if
> §12 adopts epochs).

## 5. [WITHDRAWN] Fixed grace timers — I misidentified what the timer measures

**Withdrawn (author, round 2).** My original objection assumed the window's goal was
*"keep the old result until the new run resolves, then compare"* — runtime-coupled —
and concluded the constants were mis-scaled (1 min "meaningless" for a 2-hour run,
"1200× too long" for a 50 ms run). That misreads the goal.

The real goal is to **prevent running work from being cancelled while there is still
a plausible chance it will be needed after all** (revert, oscillation, another node
requesting the same checksum). That horizon is a property of the **human
edit-settling timescale** (seconds), *not* of the transformation's runtime — so
holding a superseded 2-hour run for 15 s is exactly right: a revert within those 15 s
saves the whole restart. The "2-hour vs 50 ms" objection is therefore **void**.

What survives as **refinements** (not objections), now folded into Part I §5:

- Realize the hold as a **temporary (decaying)
  [`tempref`](../seamless-core/seamless/caching/buffer_cache.py#L230)** — matches the
  "all timers are temporary references" instinct and gives memory-pressure release
  for free.
- Treat the two horizons (≈1 min vs ≈15 s) as a **function of holding cost** (cheap
  completed result → held longer; live compute → held briefly; GPU/very-expensive →
  shorter still or not at all), rather than two hardcoded constants.
- Launch of the *new* work stays immediate; this hold only delays *cancellation* of
  the *old* work (see §6). Their interaction — transient concurrent runs during an
  edit burst — is bounded per-node by the holder cap and, in aggregate, by the
  running *wavefront* (≤ backend concurrency); no global budget is needed (§6, F2).

## 6. [WITHDRAWN] No launch-debounce — there was never a tension

**Withdrawn (author, round 2).** I read fragment 5's "wait 15 s in case reverted"
as a *debounce before relaunching*. It was misformulated: **launch of the new work
is always immediate; only the *cancellation* of the superseded run is delayed.** So
there is no competing policy — §6 collapses into §5 (the speculative hold). My
"cost-aware launch-debounce" proposal is dropped.

The confirmation does surface one **residual [FIX]** worth keeping, because
*launch-immediately* + *delay-cancellation* interact: during a rapid edit burst, a
node transiently accumulates **concurrent running transformations** (each launched
at once, none yet cancelled). This is bounded **per node** by the "≤1 current + ≤3
superseded" holder cap — under a fast burst the **count** cap evicts (and
`softcancel`s) older runs *before* their ≈15 s timer elapses, so per-node concurrency
tops out at ~4 regardless of typing speed. What is missing is a **global** bound:
≤3-superseded × thousands of nodes is still unbounded in aggregate. The decaying
[`tempref`](../seamless-core/seamless/caching/buffer_cache.py#L230) already budgets
held *result buffers* under memory pressure, but nothing budgets held *running
compute slots*. For expensive transformations on a large graph, add a **global
concurrency/holding budget** for superseded runs (a Context-wide LRU over running
holders), so launch-immediately cannot swamp the backend.

## 7. [ADMIT] The cross-backend cancellation asymmetry is a real, user-visible footgun

§6 makes the *same logical workflow* cancel-safe or cancel-unsafe depending on where
a transformation happened to run: in-process and Dask protect latched peers; the
jobserver does not. The in-process refcount shields a *single* process's own holders,
so within one `Context` this is invisible. The exposure is **cross-process peers on
a shared jobserver** — e.g. two users on one HPC `jobserver`, both running the same
deterministic transformation; user A reverts an edit, the `Context` evicts a
superseded run and the cancel reaches the jobserver, killing user B's live job.

This is a legitimate design choice (jobserver simplicity), but it must be **admitted
in writing**, with the failure scenario named, not buried under "too bad." Note also
that it is *partially mitigated for free*: the in-process refcount means a cancel is
only emitted to the jobserver when the **local** refcount hits zero, so single-user
workflows never trip it. The residual risk is strictly multi-tenant. If that
scenario is in scope later, the cheapest non-refcount mitigation is a jobserver
*grace-on-cancel* (defer the kill a few seconds; if a re-submit/latch arrives,
abort the kill) — which keeps the server "simple" without a full refcount.

> **Admitted (author, round 3).** Accepted as a footgun for the **specific** case
> *jobserver (not daskserver) + multiple clients + duplicate jobs + cancel*, and
> judged a corner case. Stated, not silently accepted — which is all this `[ADMIT]`
> asked for.

## 8. [ADMIT] "daskserver cancels only if nothing latches" is aspirational — it is net-new work in two places, and the doc implies one

The current [`dask client cancel_by_checksum`](../seamless-dask/seamless_dask/client.py#L1753)
marks the submission cancelled on the scheduler and releases futures; there is **no
latch refcount** gating the kill. Delivering §6 requires:

1. a **scheduler-side latch count** per `tf_checksum` (cancel the future only at
   zero), and
2. the **client-side** `_transformation_cache` (today one entry per `tf_checksum`,
   not refcounted) to become refcount-aware for multiple in-process holders mapping
   to one Dask submission.

These are two distinct refcounts at two layers (in-process holder count → whether a
cancel is even sent to Dask; Dask-scheduler latch count → whether the future is
actually killed). The design should name both levels; as written it reads as a
single property the daskserver "already" almost has. It does not.

> **Admitted (author, round 3).** Accepted as aspirational; the daskserver needs work
> to make it so. The point is the scope acknowledgement, now on record.

## 9. [FIX] The optimization assumes reproducibility, but the system supports irreproducible transformations

The entire "retain superseded, recompute, compare checksums, cancel downstream only
if changed" loop assumes *same input ⇒ same result checksum*. The codebase has an
explicit [`IrreproducibleTransformation`](../seamless-database/database.py) path. For
an irreproducible transformation, an unchanged input can still yield a **new** result
checksum, so the comparison **always** reports "changed," and the grace-hold becomes
pure cost (you pay to retain, then cancel anyway, every time). At minimum:

- skip the retain-and-compare optimization for transformations known/flagged
  irreproducible (run them eagerly, release downstream eagerly), and
- note that for *expressions* this hazard cannot arise (expressions are
  deterministic by construction — consistent with the plan's result-identity
  contract), so the optimization is unconditionally safe on the expression edges.

> **Resolved by scoping (author, round 3).** Irreproducible transformations are
> **out-of-scope for workflows**; the Context's retain-and-compare may assume
> determinism. Irreproducibility is not a declared property but an **imperative
> post-hoc "undo"**: the `"irreproducible"` request
> ([database.py:947](../seamless-database/database.py#L947)) records an
> `IrreproducibleTransformation` marker and **deletes** the forward
> (`Transformation`), reverse (`rev_transformation`), and metadata rows. The undo
> drops the cache mapping but not the result *buffer*; the correct response is **to
> not evict that buffer** (pin it, so the irreproducible result stays
> materializable). Out-of-scope for workflows regardless.

## 10. [ADMIT / propose phasing] Future-wired E/T is admitted-spurious; carry full reactive cancellation for it later, not now

§4 concedes the future-wired E/T's only present benefit (a few seconds) is "not
worth the complexity," and justifies it solely by an unbuilt feature
(fire-and-forget). Yet §5 already specifies immediate cancellation machinery for it.
That is complexity paid now for value deferred. **Propose:** ship the reactive
`Context` **checksum-wired only** (a node leaves `pending` for `running` exactly when
its inputs are concrete checksums), and introduce future-wiring **with**
fire-and-forget, where it earns its keep. This shrinks the first cut of the state
machine to `blocked / ready / running / done / failed` and removes a whole
cancellation path from v1.

> **Confirmed as phasing, not dropping (author, round 5).** Headless frontier advance
> is in scope (F6), so future-wired E/T are **necessary** — they are the Dask-future
> encoding of the `pending` cone that lets Dask advance the frontier after detach.
> They are not droppable; the recommendation stands only as **sequencing**: ship
> checksum-wired first, add future-wired **with** the fire-and-forget milestone.

## 11. [FIX] The `.context` accessor redirection needs explicit attach/detach (single-source-of-truth) semantics

§2 keeps **two** backing stores per builder — DAG node (when `.context` is set) and
private state (when not) — with a switch. That invites incoherence: which one is
authoritative across attach/detach, and what does a detached handle read? It also
quietly breaks the "functional, build-once" mental model the implementation plan
established for the standalone builders, because a context-bound builder is now a
*mutable aliased view* (two handles to one node key mutate each other).

**Propose:** on **attach**, *migrate* private state into the DAG node and abandon the
private shadow (single source of truth = the node); on **detach**, snapshot the node
back into private state. No dual-write window. Define explicitly whether two handles
to the same node key are intended aliases (probably yes) and document that the
standalone "build-once" guarantee is a property of the *unbound* builder only.

## 12. [STATE THE INVARIANT] Glitch-freedom holds *by construction* — but only given synchronous cone-invalidation; quiescence remains open

> **Reframed (author, round 3) — the glitch half is largely conceded.** The author
> objected: *"old work, even if not canceled, is obsolete: if it completes, it will
> not provide the current result checksum."* Correct — and that disposes of the
> **superseded-running-work** class of glitch. But that is not the glitch I meant.
> Here is the concrete one, and why the design already prevents it.

**Concrete scenario (the textbook diamond).** A direct edge and an indirect edge from
the same source, with different latencies:

```
a = 1
b = a + 1          # b = 2          (cheap: completes fast)
c = a + b          # c = 3          (consistent: a=1, b=2)
```

Now `a → 10`. `c` depends on `a` **directly** *and* **through `b`**. The danger is `c`
firing on `a = 10` (new) together with `b = 2` (`b`'s *previous, completed* result,
not yet recomputed) → a transient `c = 12`, which corresponds to **no** consistent
state of the system; then `b → 11`, then `c → 21`. The flashed `12` is the glitch.

Note this is **not** about `b`'s *old running work* — `b` is not even recomputing yet
at the moment of the glitch. It is about `c` reading `b`'s **stale-but-completed**
result as if it were current. The author's "obsolete work isn't used" principle is
about *running* work; the glitch is about a *completed* upstream that just became
stale. Different mechanism.

**Why the design already prevents it — the invariant.** The state machine fires a
node's current (result-providing) E/T **only when all upstream are `complete`**. So
the glitch is avoided **iff**, the instant `a` changes, the **entire downstream cone
(`b`, `c`) is synchronously marked non-current** (revoked from `complete`/`running`)
**before** any of them is evaluated for readiness. Then `c`, when re-evaluated, sees
`b` as `pending`, not as `2`, and does **not** fire until `b` recompletes to `11`;
`c` then fires `21`. No glitch — only an honest `pending` on `c` during the
recompute. Equivalently: *an input edge always resolves to the upstream's **current**
checksum, and a node with a changed ancestor has **no** current checksum (it is
`pending`) until it recompletes.*

So this is **not a flaw to fix** but **an invariant to state explicitly**:

> **Invalidation dominates recomputation.** On any change, mark the whole downstream
> cone non-current *before* launching the wavefront recompute. Never fire a node on a
> stale-completed input.

It is worth stating precisely **because the launch-immediately / per-node-async model
is exactly where it is easy to violate** — an eager scheduler that re-evaluates `c`
"because input `a` changed" before it has marked `b` stale would glitch. Order:
*invalidate cone → then launch wavefront.* (Legacy Seamless does this via a
void/pending sweep of the downstream cone.)

**Quiescence — now also resolved (author, round 4).** The equilibrium classification
(Part I §3) gives the definition directly: **quiescent ⇔ no node is `pending` or
`running`** (all in equilibrium), and within scope (DAG + reproducible) it is
guaranteed reachable. So both halves of §12 are settled: glitch-freedom by the
invalidation invariant, quiescence by the equilibrium definition. What remains is not
in §12 but in **F6**: the *seal* must additionally cancel lingering **superseded**
runs (obsolete, but still holding cluster slots) before detaching.

## 13. [FIX] Which API does the reactive loop call — `cancel()` or `softcancel()` — and is `cancel()` ever safe here?

`Transformation` today has a hard
[`cancel()`](../seamless-transformer/seamless_transformer/transformation_class.py#L416)
that pops `_active_submissions` and **fails every latcher**. Introducing
`softcancel()` alongside it means the reactive loop must **never** call the hard
`cancel()` on shared running work, or it defeats the whole refcount. Specify: the
`Context` uses `softcancel()` exclusively for superseded/evicted runs; hard `cancel()`
is reserved for explicit user destruction of a node and should itself be made
refcount-aware (or documented as "force-kills latched peers"). Without this rule
written down, the two APIs will be mixed up at exactly the points where it matters.

> **Resolved (author, round 1):** `cancel()` raises `CancelledError` in **all**
> running `.compute` coroutines (kill-all, matching today's `cancel_by_checksum`);
> the reactive loop uses `softcancel()` only. **Residual:** reactive **node deletion**
> must *also* use `softcancel()`, never hard `cancel()` — in-process **sibling
> nodes** can legitimately share a running `tf_checksum`, and a hard cancel would
> collaterally kill them. Hard `cancel()` = user-level "stop everything on this
> checksum". (Each kill-all'd coroutine decrefs via its terminal `CancelledError`,
> which counts as a completion under the `refholding` rule.)

---

# Part III — Fresh-pass critique (design now understood)

Rounds 1–2 corrected my misreadings. This pass assumes the design as clarified:
`Context = DAG`; ephemeral builders; launch the new run **immediately** and **delay
cancellation** of the superseded run; the hold is a **speculative bet against
re-need** realized as a decaying reference; **≤3 superseded runs per node**;
in-process `refholding` refcount; jobserver kills peers, daskserver cancels only if
unlatched. The points below only become visible *given* that design.

## F1. "The grace period" is actually two different mechanisms with two different correct triggers

The original text describes the hold twice, and they are **not the same**:

- **In-flight self-revert (≈15 s):** X is running, X's own source is edited; launch
  the new run, keep the old one "*in case the change to X is reverted*." The bet is
  **behavioral** (will the user revert?), so a **fixed, human-timescale** window is
  exactly right. Round-2 reframing holds. ✓
- **Downstream-of-recompute (≈1 min):** X already *completed* with result `R`; X's
  source changes; X recomputes; a downstream node Y is running/complete on `R`. The
  original words are *"wait… to see if the result is unchanged (and if not,
  canceled)."* That is **not** a behavioral bet — it is an **event**: hold Y's
  `R`-work **until X's recompute resolves to `R'`, then compare**. If `R' == R`
  (inert edit) Y needs nothing; if `R' != R` Y must recompute.

So the single round-2 reframing ("keep alive in case needed") flattens a distinction
present in your own original text. A **fixed 1-minute timer is a lossy proxy** for
the downstream case and is mis-scaled **both** ways: if X recomputes in 5 s the hold
wastes ~55 s; if X takes 2 min the hold **expires before** `R'` arrives, so Y's
`R`-work is cancelled at 1 min and must recompute from scratch at 2 min — the hold
**fails at exactly the expensive case it was meant to protect**.

- **Fix:** the downstream hold should be **dependency-aware and event-driven** —
  hold Y until *the specific upstream that changed* resolves, then compare; the timer
  is only a backstop for an upstream that never resolves (or is itself cancelled).
  This is more work than a blind timer (Y must remember which upstream it is waiting
  on), but it is the only version that is correct for slow upstreams. The in-flight
  case (F1 bullet 1) keeps its simple fixed timer.

## F2. Speculation must yield to current work under contention — delayed cancellation can starve *current* work elsewhere

> **Mostly conceded (author, round 3) — "global budget" was wrong.** The aggregate
> is **not** unbounded. Only **running** nodes (the *wavefront*) have running work to
> supersede; pending nodes have nothing to supersede, and completed nodes hold
> *results* (cheap buffer `tempref`s, F3), not slots. The wavefront of
> *actually-running* work is itself bounded by **backend concurrency** (the rest are
> pending/queued), so superseded running work is bounded by **3 × |wavefront| ≤
> 3 × backend concurrency**, independent of DAG size. My "3 × thousands of nodes" was
> wrong because running-ness is backend-gated. **No global-budget mechanism is
> needed.** What narrowly survives — superseded holds inflating slot demand up to
> ~4× and delaying a current run elsewhere — is reduced to a **corner case** by the
> same wavefront argument (it needs *non-local rapid editing of a wide wavefront*),
> and is left as an **optional** preemption nicety, below, not a requirement.

Per node, the current run is safe (it evicts the oldest superseded to stay within the
≤3 cap, so it always gets a slot). The residual (corner-case) exposure is **across
nodes on a shared backend**: a node's ≤3 superseded holds occupy Dask/jobserver slots
that *another node's **current** run* needs.

- **Continuous forward editing is the (local, bounded) worst case.** Scrubbing a
  slider feeding an expensive transformation launches a run per value; the held
  superseded runs are *doomed* (a forward scrub rarely revisits a value) yet sit in
  slots until their timer or the ≤3 cap evicts them. This is an **admitted local
  cost** of launch-immediately (bounded at ~4 runs for that node's subtree) — the
  price paid for low latency; the hold is calibrated for **revert/oscillation**, not
  forward exploration.
- **Optional nicety (not required):** make speculation **preemptible by current
  work** — under backend saturation, cancel superseded runs **eagerly** so a
  *current* run anywhere can take the slot (*current everywhere preempts superseded
  anywhere*); give remote-expensive runs a **shorter/zero** horizon; optionally
  **adapt** the horizon to the observed re-need hit-rate. All corner-case polish.

## F3. The ≤3 set conflates *in-flight* and *completed* superseded runs

A held superseded **running** run can **complete** while held. It is then a *result
holder*, not running work — but if it still occupies one of the 3 slots, completed
results **crowd out** the speculative protection meant for genuinely in-flight runs,
and the "running-tf refcount" is now counting a non-running thing. **Fix:** the ≤3
cap is on **in-flight** superseded runs only; on completion a superseded run **leaves
the cap** and its result is retained (if at all) by the normal decaying buffer
`tempref`, not by a running-work slot. This keeps the running-refcount strictly about
running work (consistent with "completed work is forgotten").

## F4. The *reactive* (change-triggered) transitions — mostly the author's one-line rule, plus two refinements

> **Mostly conceded (author, round 4).** The author supplied the core rule:
> *"Whenever an input checksum changes, the node status changes. If it has become
> `pending`/`running` where it was `completed`/`error`, all downstream nodes change
> to `pending`."* That **is** the synchronous cone-invalidation that makes §12
> glitch-free, so it disposes of most of F4. Two refinements remain.

**(1) "all downstream → `pending`" is too blunt — downstream must *re-derive*, not be
force-set to `pending`.** A multi-input downstream may belong in `upstream`, not
`pending`. Concrete: `Y` depends on `X` **and** `W`; `W` is in `error`, so `Y` is
`upstream` (blocked, needs intervention). `X` changes (`complete → running`); the
blunt rule sets `Y → pending`, but `Y` is still blocked by `W` and its correct state
is `upstream`. The distinction is the **autonomy** one from §3/2b (`pending`
self-clears; `upstream` needs an external fix), so this mislabels a needs-intervention
node as self-clearing. Not a correctness bug (`Y` still won't fire until all upstream
are `complete`), but a status-accuracy one. Symmetrically, if `X` recomputes and lands
in `error`, its downstream must flip `pending → upstream`. So: **each downstream
re-derives its own status against its full upstream set.**

**(2) The cascade trigger is broader than "input checksum changes":**
- **Self-edits.** Editing a node's code or load-bearing `meta` changes its own
  `tf_checksum` with **no input change**; it must de-complete and cascade.
- **Connectivity → `unconnected`.** Disconnecting a required pin moves a node
  `complete → unconnected` — neither `pending` nor `running`, so a literal reading of
  the rule **doesn't fire the cascade**, leaving stale downstream; and those downstream
  should become `upstream`, not `pending`. So the trigger is "**a node leaves
  `complete`** (its output checksum changes or becomes unavailable)," broader than
  "became `pending`/`running`."

Both refinements **confirmed by the author (round 4).** With them, F4 is one
paragraph, not an open question:

> On any change to a node's **identity or connectivity**, the node re-derives its
> status. If it **leaves `complete`**, every downstream node **re-derives its own
> status** (landing in `pending` *or* `upstream` per its full upstream set),
> synchronously, before the wavefront recompute (the §12 invariant). When a recompute
> yields the **same** checksum, downstream re-complete instantly via cache hit; **F1's
> hold is the optimization that avoids even the transient `pending`.** (This is also
> where §9's *undo → reactive invalidation* would slot in, if undo is ever allowed on
> a live node.)

(Open only if the intra-context graph may contain **cycles** — then the cascade needs
termination/cycle handling; the plan lists this separately. Assuming a DAG, the
above suffices.)

## F5. The graph ontology is undefined: what is a node, an edge, a navigation?

Is `ctx.a.sub` a **DAG node** or an **ephemeral expression** over node `a`? Does
navigation **grow** the DAG? Where does an intra-context edge `b ← a.sub` keep its
path — **on the edge**, re-materialized into an `Expression` each tick (consistent
with "the Context *fires* Expressions, never *contains* them"), or as a persistent
expression-node (which would violate "a Context contains only Cells/Transformers")?
The plan lists "intra-context edge identity" as open; the concrete fork is: **edges
carry paths and the Context builds ephemeral Expressions per tick** (keeps the
immutable layer node-free, costs a rebuild per tick — cheap, content-addressed) vs.
**navigation creates persistent nodes** (DAG grows with `.sub`, but no rebuild). Pick
one; the reactive cost model and the §11 attach/detach semantics both depend on it.

> **Resolved (author, round 5).** The first fork:
>
> - **Nodes** = the context-key-bound `Cell`s/`Transformer`s (`ctx.a`, `ctx.b`).
> - **Navigation** (`.sub`, `[i]`, `[a:b]`) returns an **ephemeral `Cell`** — a
>   transient view accumulating a path over a node; it does **not** grow the DAG.
> - **Edges**: assignment `ctx.b = ctx.a.sub` captures `(source-node-ref, path,
>   celltypes)` on the edge — **not** an `Expression` object.
> - **`Expression`/`Transformation` are private to the Context**, materialized
>   per-tick from `(edge path + current upstream checksum)`, fired, discarded.
>
> This gates §11: attach/detach is just migrating a node's **private `Cell` state**
> (path/celltype/value-or-edge) in and out of the DAG — single source of truth = the
> node, per §11.

## F6. Fire-and-forget (the sole justification for future-wired E/T) is in direct tension with delayed cancellation

Future-wired E/T is kept *only* because fire-and-forget — tearing down the Context
while Dask keeps running — "meshes nicely" with it. But at hand-off the Context holds,
per node, one current run **plus up to 3 superseded speculative runs**. Tear the
Context down in that state and you have **forked the workflow into multiple live
branches on the cluster with no adjudicator** to decide which is current or to cancel
the rest. Fire-and-forget therefore requires an explicit **seal/commit** step:
**cancel all superseded speculation**, pin exactly one current run per node, *then*
detach.

> **Refined (round 4).** Quiescence is now defined (Part I §3 / §12: no node `pending`
> or `running`), so it is no longer a blocker — but note the seal does **not** require
> full quiescence: fire-and-forget exists precisely to detach while the current
> wavefront is still `running`. The seal's job is to collapse the messy state (≤3
> superseded + 1 current per node) into the **clean current wavefront** (one run per
> running node, superseded cancelled), which is a hand-off-safe out-of-equilibrium
> state. So the remaining prerequisite is just the **commit operation** itself, not a
> wait-for-quiescence.
>
> **Resolved + scoped (author, round 5): headless frontier advance is in scope.**
> So the seal does more than pin the current wavefront — it **compiles the unblocked
> forward cone** (the `pending`/`upstream`-clearing nodes ahead of the wavefront) into
> **future-wired E/T as Dask futures**, so Dask advances `pending → running → complete`
> headlessly. Two clean bounds and one wrinkle:
>
> - **Forward-only.** The seal *freezes* the graph (no external edits during
>   fire-and-forget), so headless needs only the **autonomous** transitions — which
>   Dask's dataflow provides natively. The entire **reactive** apparatus (F4 cascade,
>   F1 holds, supersession, invalidation) is **Context-online-only and discarded at
>   seal**. This is what bounds the seal: compile the *unblocked forward cone*, nothing
>   reactive.
> - **Blocked branches stay blocked.** `error`/`upstream` nodes simply never resolve
>   headlessly (their input futures never arrive) — correct, since they need
>   intervention that can't happen headless. On reattach they are still blocked.
> - **No special case — tf-construction timing follows the wiring (corrected, rounds
>   6–7).** I first claimed connected-optional pins force a "dynamic task" (wrong), then
>   over-corrected to "tf is *always* computed at runtime for every node" (also wrong).
>   The precise statement is the §4 split: tf-construction is **eager at submission**
>   for a **checksum-wired** node (all input checksums already in hand — the current
>   wavefront) and **deferred to runtime** only for a **future-wired** node (some input
>   still a future — the pending cone). The connected-optional drop-if-`null` rule is
>   **one rule within tf-construction**, applied *whenever* that happens (eager or
>   deferred) — so it is no special case either way. The cone therefore compiles
>   **uniformly**: the wavefront submits with known `tf_checksum`s; the pending cone
>   submits as future-wired tasks that build their tf when inputs resolve (which is
>   exactly what a future-wired E/T *is*, per §4 and F7). Zero special cases.

## F7. Two smaller consequences of the clarified semantics

- **Connected-optional pins lose laziness.** Because a *connected* optional pin is
  "treated as required" and the upstream may legitimately return `None`, the upstream
  **always runs** — even when its `None` result is then dropped from the
  transformation. "Optional" no longer means "cheap when unused"; it means "may be
  absent **or** `None`, but if connected, always computed." Worth stating, because the
  intuitive reading of "optional" is the opposite.
- **Future-wired E/T have *provisional* identity.** A future-wired E/T is keyed by its
  *upstream's* identity, not by a concrete checksum, so it can **never** produce a
  cache entry under its own identity and is replaced wholesale by a *different*
  immutable object (concrete-checksum-keyed) at `pending → running`. It is really a
  **registered continuation**, not a cacheable definition — which both reassures
  (it cannot pollute the cache) and reinforces deferring it (§10): it carries no
  caching value of its own.

---

## Summary of required actions

**Resolved / conceded / admitted with the author (rounds 1–4):** §1 (expressions
cancelable; surface scoped to byte-moving paths), §2 bullets 1–2 (optional-pin
predicate; autonomy split — residuals: `null`-checksum representation, queryable
block-reason), §3 balance (`refholding`; residuals: no incref on cache hit, single
choke-point, `__del__` backstop), §4 (**downgraded** — moot for correctness; residual:
one-lock atomicity), §5 (**withdrawn** — misframed the goal), §6 (**withdrawn** — no
launch-debounce; F2 global budget **conceded** via the wavefront bound), §7
(**admitted** — jobserver corner case), §8 (**admitted** — daskserver aspirational),
§9 (**resolved by scoping** — irreproducible is out-of-workflow; pin the buffer, don't
evict), §12 (**resolved** — glitch-free by the cone-invalidation invariant; quiescence
defined via the equilibrium classification), §13 (kill-all `cancel()` vs
`softcancel()`; residual: reactive deletes use `softcancel`), **F4** (**resolved** —
the author's cascade rule + two confirmed refinements; re-derive don't blanket-pending,
broaden the trigger).

**Still to fix:** §2 bullet 3 (rename the overloaded "running"/"pending"), §11
(single-source-of-truth attach/detach — now *gated and mostly determined* by F5).
**From Part III:** **F1** (split the two holds; downstream hold is event-driven),
**F3** (≤3 cap on in-flight runs only), **F6-commit** (the seal/commit operation:
compile the unblocked forward cone to Dask futures — **uniformly**, no special cases;
each node is a task that builds its tf from resolved upstream checksums).

**Resolved (round 5):** **F5** (graph ontology — nodes = context-key builders;
navigation = ephemeral `Cell`s; edges carry `(node-ref, path)`; E/T private,
per-tick), **F6-scope** (headless frontier advance is in scope; seal is forward-only,
reactive machinery discarded at detach).

**Admitted / phasing:** §10 (future-wired E/T **necessary** for headless; defer to the
fire-and-forget milestone — sequencing only), F2 (speculation-vs-current contention is
a corner case; preemption optional), F7 (connected-optional loses laziness;
future-wired identity is provisional).
