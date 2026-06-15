# Reactive `Context` Internals — Design (Pass 3)

> **What this document is.** A third-pass *synthesis* of
> [`context-internals-design-pass2.md`](context-internals-design-pass2.md). Pass 2 was
> itself a synthesis-plus-critique whose Part II had, by its own end, **retracted,
> resolved, or conceded nine of its ten new criticisms** and adopted the tenth (the
> awaiter-set refcount). The scaffolding of "I originally said X, now retracted" has
> done its job and is dropped here: Part I below states the **settled design directly**,
> as one standalone statement, with no archaeology.
>
> Pass 3 also **reorganises** at the reader's request. The two pieces of work that live
> in the lower repos rather than in the `Context` — the **optional-pin / connectivity
> rule** and the **cancellation substrate** — are pulled out of the workflow narrative
> into their own top-level parts (Parts II and III), and the one genuinely **open**
> item, **dependency declaration**, gets its own part (Part IV). Part V is a **fresh
> first-principles critique by this pass**, with alternatives — the criticisms are new,
> not recycled from pass 2.
>
> It remains the concrete form of the appendix of
> [`cells-and-expressions-implementation-plan.md`](cells-and-expressions-implementation-plan.md):
> the reactive layer that sits **on top of** the immutable functional substrate
> (`Expression`/`Transformation` nodes, checksum futures).

> **Implementation status (re-verified against the tree, 2026-06-15).** The functional
> substrate is shipped and the pass-2 status note still holds:
> [`Cell`](../seamless-core/seamless/cell_class.py) is fully mutable standalone —
> setters for `input_ref`, `path`, `celltype`, `target_celltype`, `validator` at
> [cell_class.py:52–102](../seamless-core/seamless/cell_class.py#L52), and
> [`build()`](../seamless-core/seamless/cell_class.py#L135) snapshots an immutable
> `Expression`. [`Expression.cancel()`](../seamless-core/seamless/expression_class.py#L222)
> is still a `NotImplementedError` stub. The reactive `Context` is **not implemented** —
> `seamless-workflow` is empty and no `Context` class exists. The running-work refcount
> is **net-new**: today
> [`_active_submissions`](../seamless-transformer/seamless_transformer/transformation_cache.py#L171)
> is one [`_ActiveSubmission`](../seamless-transformer/seamless_transformer/transformation_cache.py#L96)
> per `tf_checksum` holding a single shared future
> ([awaited at L320](../seamless-transformer/seamless_transformer/transformation_cache.py#L320)),
> guarded by a `threading.RLock`
> ([`_active_lock`, L172](../seamless-transformer/seamless_transformer/transformation_cache.py#L172));
> [`cancel_by_checksum`](../seamless-transformer/seamless_transformer/transformation_cache.py#L348)
> pops it and fails the one shared future — killing **all** latchers — and the
> `strict_dunder` envelope-contention check lives at
> [L304](../seamless-transformer/seamless_transformer/transformation_cache.py#L304). The
> **buffer** refcount + `tempref` machinery in
> [`buffer_cache.py`](../seamless-core/seamless/caching/buffer_cache.py) already exists
> and is reused; the **running-work** awaiter set does not.

---

# Part I — The Reactive `Context` (workflow layer)

## I.1 Essence and scope

The functional layer is settled and shipped. `Expression` and `Transformation` are
immutable, content-addressed nodes in one lazy DAG, each producing a checksum future.
`Cell` and `Transformer` are mutable, build-once builders: navigation returns a derived
builder; the build call snapshots the current `(input-ref, path, celltypes)` into an
immutable definition. Nothing below the `Context` knows a `Context` exists.

`Context` reintroduces **reactivity** on top, without leaking reactivity into the
immutable layer. Its one-sentence essence:

> **Reactivity = re-build with fresh snapshots.** When a logical cell takes a new value,
> the `Context` builds new immutable `Expression`/`Transformation` definitions from the
> new snapshot and fires them; the content-addressed cache reuses every sub-result that
> did not actually change. The functional layer never mutates.

Throughout, **E/T** abbreviates "`Expression` and/or `Transformation`" — the two
immutable node kinds the `Context` fires.

**What is and isn't `Context` logic.** Three capabilities this design depends on are
**not** reactive-`Context` logic; they live in the functional substrate and would exist
without a `Context`. They are split out into their own parts and tagged
**`[SUBSTRATE]`**:

- the **optional-pin / connectivity rule** (Part II) — a `seamless-transformer`
  transformation-construction concern;
- the **cancellation substrate** — soft/hard cancel and the membership-set model
  (Part III) — in `seamless-transformer` and the servers; the `Context` only *calls*
  `softcancel`. `Expression` cancellation (Part III.4) is its `seamless-core` tail.

Everything in this Part — the DAG, node states, the cascade and glitch-freedom
invariant, speculation *policy*, wiring, `prune`/detach — is genuine workflow-level
logic. (Note the split inside §I.5: *deciding when to hold* a superseded run is
`Context` policy; the *holding/cancel mechanism* it calls is `[SUBSTRATE]`.)

## I.2 A `Context` is a DAG; builders are views over it

Internally a `Context` holds **only a DAG of nodes**. `Cell`s and `Transformer`s are
**not** stored objects — they are **views over a node**.

- **Nodes** are the context-key-bound builders: `ctx.a`, `ctx.b` — one node per key.
- **Navigation** (`ctx.a.sub`, `ctx.a[i]`, `ctx.a[x:y]`) returns an **ephemeral `Cell`**:
  a transient view that accumulates a path over a node. Navigation does **not** grow the
  DAG.
- **Edges** are created by assignment: `ctx.b = ctx.a.sub` captures `(source-node, path,
  celltypes)` **on the edge** — not as a stored `Expression`.
- **E/T are private to the `Context`.** On each tick they are *materialized* from
  `(edge path + current upstream checksum)`, fired, and discarded. A `Context`
  **contains** only builders (as node state); it **fires** E/T but never stores them. The
  per-tick materialization cost is bounded to the **invalidated cone** (not the whole graph)
  and is a small `tf_checksum` hash over checksum-sized inputs — never a re-hash of buffers.

### Single source of truth

A builder is backed by **exactly one** store, never two:

- An **unbound** builder owns its private state (the functional, standalone behaviour).
- **Binding is a move, not a copy.** On attach, the builder's private state (path /
  celltype / value-or-edge) migrates *into* the DAG node and the private shadow is
  abandoned; the node is the sole source of truth. On detach, the node's state is
  snapshotted *out* into a fresh standalone builder. There is **no dual-write window**,
  and two handles to the same node key are deliberate aliases.

`Cell`/`Transformer` are **uniformly mutable in both modes**; the only difference is
**where the mutable state lives** (bound → in the node; unbound → private). The
functional "build-once" guarantee is a property of the **`Expression`** that `build()`
snapshots out — a later builder mutation cannot reach into an already-built `Expression`
— **not** of the builder. View identity is therefore not load-bearing: `ctx.a is ctx.a`
may be `False`, and that is harmless, because dependencies are captured **by content**
(a nodepath edge), not by view object identity. Node identity is the *key*, not the view
object; `id()`-keyed caches over views must not be used.

## I.3 Node states, connectivity, and equilibrium

Connectivity ("is this node sufficiently wired to compute?") is defined by the
**optional-pin rule in Part II** `[SUBSTRATE]`; the `Context` only *relies on* its
verdict. In brief: a node is **sufficiently connected** iff every required pin is wired
and every *connected-optional* pin is wired (unconnected optional pins are simply absent).

### The six node states

Pass 2 renamed the node-state axis so it never collides with E/T run phases (which keep
**running / superseded / cancelled / completed**). Nodes use:

| state | meaning |
|----------------|----------------------------------------------------------------------------------|
| `unwired` | not yet sufficiently connected |
| `blocked` | sufficiently connected, but some upstream is `unwired` or `failed` — blocked, **not itself errored** |
| `waiting` | upstream is progressing but not all complete |
| `computing` | every required + connected-optional upstream is resolved; this node's own E/T is executing |
| `complete` | result checksum available |
| `failed` | this node's **own** evaluation failed |

Rules:

- A node reaches `computing` iff **all required upstream are `complete`, and every
  connected-optional upstream is either `complete` or definitively in its empty/dropped
  (JSON-`null`) case** (Part II). The empty/dropped case is the upstream resolving to the
  `null`-absence value — **not** failure. A connected-optional pin gates exactly like a
  required pin; its *only* relaxation versus required is that resolving to `null`
  satisfies the gate (by dropping the pin). An **errored (failed)** connected-optional
  upstream therefore **blocks** the node (`blocked`), exactly like a failed required
  upstream — it is *not* skipped.
- **Upstream failure does not propagate as `failed`.** A dependent of a failed node is
  `blocked`, not `failed`. `failed` is reserved for a node's **own** evaluation.
- **The block reason is a first-class, queryable enum** `{blocked-by-unwired,
  blocked-by-error}`. Both are one *state* (both need an external change to leave), but
  they imply different user actions (wire something vs. fix code), so the *reason* must
  be inspectable by UI and tests. **When both apply** (a node has an unwired input *and*
  an errored input), **`blocked-by-unwired` is reported** — wiring is the more
  fundamental prerequisite, and an errored upstream is sometimes errored only because
  something below *it* is still unwired.
- **A `failed` node leaves `failed` only via an external change.**
  **`ctx.node.clear_exception()`** — forwarded to the failed `Context`-private E/T — is
  that change: it clears the node's recorded exception and re-derives it, recomputing
  from current inputs. (Auto-retry of *transient* infrastructure failures is a
  Transformation/backend concern, deliberately out of scope here — §I.8.)

### Equilibrium vs. out-of-equilibrium

| kind | states | leaves only via |
|------|--------|-----------------|
| **equilibrium** | `complete`, `failed`, `blocked`, `unwired` | an **external change** |
| **out-of-equilibrium** | `waiting`, `computing` | **autonomously** |

A `waiting`/`computing` node relaxes toward equilibrium on its own as upstream
computation finishes; an equilibrium node moves only when perturbed. **An external
change perturbs; the `Context` relaxes.**

- **Quiescence ⇔ no node is `waiting` or `computing`.** Within scope (a DAG of
  reproducible transformations) it is **guaranteed reachable** in finite steps after a
  finite burst of edits. Quiescence is a property of node **states**; a `complete` node
  may still have a **superseded** run in flight (obsolete by construction) that does
  **not** count against quiescence. So quiescent ≠ cluster-idle; **`ctx.prune()`** (§I.5)
  drops the obsolete runs so the two coincide.
- **Quiescence ≠ success.** Equilibrium includes `failed`/`blocked`/`unwired`. *Success*
  is the stronger condition that all **witness/observable** nodes are `complete`.

## I.4 Reactive propagation and glitch-freedom

A "change" is an update to a node's value/config/identity or to connectivity. The
cascade rule:

> On any change to a node's **identity or connectivity**, the node re-derives its own
> state. If it **leaves `complete`** (its output checksum changes or becomes
> unavailable), every downstream node **re-derives its own state** — landing in `waiting`
> *or* `blocked` per its full upstream set — **synchronously, before** the wavefront
> recompute is launched.

Two refinements over a blunt "all downstream → pending":

- **Re-derive, don't force-set.** A multi-input downstream may belong in `blocked`, not
  `waiting` (e.g. it also depends on a `failed` node). Each downstream computes its own
  state against its full upstream set.
- **The trigger is "leaves `complete`,"** which is broader than "an input checksum
  changed": it includes **self-edits** (editing a node's code/load-bearing `meta`
  changes its own `tf_checksum` with no input change) and **disconnection** (removing a
  required pin moves a node `complete → unwired`, its downstream to `blocked`).

### The glitch-freedom invariant

> **Invalidation dominates recomputation.** On any change, mark the whole downstream cone
> non-current (revoke it from `complete`) *before* launching the wavefront recompute.
> **Never fire a node on a stale-completed input.**

This is what makes the textbook diamond glitch-free. With `a=1; b=a+1; c=a+b`, when
`a→10` the danger is `c` firing on `a=10` (new) with `b=2` (`b`'s stale-completed
result) → a transient `c=12` corresponding to no consistent state. The invariant forbids
it: the instant `a` changes, `b` and `c` are synchronously revoked to `waiting`, so `c`
cannot fire until `b` recompletes to `11`; then `c` fires `21`. The only visible effect
is an honest `waiting` on `c` during the recompute.

The two halves have very different costs and are **decoupled**:

- **Marking** the downstream cone non-current (flip `complete`/`computing` → `waiting`)
  is **cheap in-process bookkeeping** — state flips, no I/O, no compute. It must complete,
  in **one non-yielding pass**, *before any descendant is evaluated for firing*. That
  ordering is the whole requirement (there is nothing to `await` while flipping states,
  so it is naturally atomic).
- **Building/launching** the refreshed E/T is **lazy, prioritised, and need not be
  synchronous or atomic**: a node becomes checksum-wired (eligible to fire) only once all
  its inputs are current, so glitch-freedom holds for free regardless of *when* the E/T
  is rebuilt. Running (checksum-wired) E/T are launched **with priority** (latency),
  bursts capped; pending (future-wired) E/T are submitted **lazily**.

When a recompute yields the **same** checksum (an inert edit), downstream re-complete
instantly via a content-addressed cache hit — and the §I.5 hold is the optimisation that
avoids even the transient `waiting`.

## I.5 Speculation: launch immediately, delay cancellation

On a change, for the changed node and everything downstream:

1. **Future-wired E/T are cancelled immediately** — they hold no completed work (§I.6).
2. **Checksum-wired ("running") E/T are *not* cancelled immediately.** The change may be
   inconsequential (a cosmetic source edit that does not alter the result), so cancelling
   running work — and the downstream feeding on its already-completed checksum — would be
   wasteful.

The rule for running work is **"relaunch the new run immediately, *and also* retain the
superseded run for a grace period."** Launch is never debounced; only *cancellation of
the old run* is delayed. Its **goal**: prevent running work from being cancelled while
there is still a plausible chance it will be needed (an inconsequential upstream edit, a
reverted edit, an oscillation).

The organising fact is content-addressing:

> A downstream's `tf_checksum = hash(its own code, its upstream inputs' **output
> checksums**, …)`. So a node's running work survives an upstream edit **iff the
> upstream's *output* is unchanged** — even though the upstream's *code* changed. Editing
> a node's **own** code always changes its own `tf_checksum`, so its own running work is
> reusable only on a literal revert.

This splits the holds into **three** cases:

- **(a) Upstream-confirmation hold — event-driven, the high-value case.** A node `B` is
  `computing` (possibly nearly finished); a changed upstream `A` is recomputing. Because
  `A`'s edit may be inconsequential, `B`'s `tf_checksum` may be **unchanged** — in which
  case `B`'s in-flight run is *still the current run*, and killing it throws away a
  nearly-finished expensive computation for nothing. **Hold `B`'s run until the changed
  upstream resolves, then compare its output checksum:** if unchanged, **reinstate** `B`
  (it was never really interrupted — mechanically, `B` re-derives the *same* `tf_checksum`
  and re-latches onto the still-running submission, Part III); if changed, cancel and
  relaunch. The window is **event-driven** — primarily the time until the upstream
  resolves — under a **fixed maximum of ~5 minutes**, which is a reasonable ceiling in its
  own right: if the upstream has not resolved within that bound, release `B`'s hold
  regardless. Event-driven release handles the common case (a fast upstream confirms
  quickly); the 5-minute maximum both keeps `B` held while a genuinely slow upstream is
  still resolving and bounds worst-case slot occupation, so a stuck upstream cannot pin a
  superseded run indefinitely.
- **(b) Self-edit revert hold — fixed window, behavioural.** A node is `computing` and
  its **own** identity (code / load-bearing `meta`) is edited; its `tf_checksum` changes,
  so the old run is reusable **only if the user reverts**. This is a behavioural bet on a
  revert, so a **fixed human-timescale window** (seconds) is correct, *independent of the
  run's runtime*: holding a superseded 2-hour run for ~15 s is worthwhile because a revert
  within those seconds saves the whole restart. Realised as a **fixed-lifetime** hold —
  hold until a deadline, then release; **no decay curve** (decay is the buffer cache's
  general memory-pressure mechanism; this hold needs only a lifetime). For a very
  expensive run (e.g. GPU) the lifetime shrinks toward zero.
- **(c) Completed-downstream retention — buffer retention, event-bounded.** A node `Y` is
  already `complete` on result `R` when an upstream changes. There is no running work to
  protect — reinstating a *completed* `Y` is a **pure cache hit** — so what is held is
  `Y`'s **output buffer** (and the upstream's old output) via a `tempref`, so the cache
  hit lands if the upstream re-resolves to the same output. As in (a), the right lifetime
  is **bounded by the upstream event** (with the same ~5-minute maximum backstop as case
  (a)); a fixed lifetime is an acceptable approximation only when the upstream is fast.
  Memory pressure may evict early regardless — the correct compute-vs-memory trade-off.

Cases (a) and (c) are the **same event-driven downstream hold** (hold until the changed
upstream resolves, then compare), split only by whether the downstream is still
`computing` (protect live compute) or already `complete` (retain a buffer). Case (b)
keeps a fixed window because no upstream event governs it.

**Reinstatement is not a special operation.** "Reinstate `B`" (case (a)) is mechanically
*nothing*: `B` re-derives the **same** `tf_checksum` and re-latches onto the
still-running submission via the §III awaiter set. There is no surgical resurrection of a
run — the hold merely keeps that submission alive long enough for the re-derivation to
find it.

### Nodes do not "hang on" to completed work

A node need not specially retain *completed* work: correctness and most of the
performance benefit come from the content-addressed cache (new work matching old work is
an instant hit). Retention of *running* work is different — by case (a) it is
**load-bearing**, because a single inconsequential edit to a fast upstream must not abort
a nearly-finished expensive downstream whose `tf_checksum` is in fact unchanged. The
cache cannot recover that: once cancelled, an in-flight run's partial progress is gone.

### Holder policy and bounds

- A node holds **≤1 current** run plus **a small bounded set of superseded *in-flight*
  runs** (cap **≤3**). The cap is on **in-flight** runs only: when a superseded run
  **completes**, it leaves the cap, and its result is retained, if at all, by the normal
  buffer `tempref` — never by a running-work slot.
- When a superseded in-flight run is **evicted** from the set, it is `softcancel`'d
  (Part III).
- **Aggregate bound.** No global budget is needed. Only `computing` nodes have running
  work to supersede, and the *wavefront* of actually-running work is bounded by
  **backend concurrency** (the rest are `waiting`/queued). So superseded in-flight runs
  ≤ **3 × backend-concurrency**, independent of DAG size. The residual contention (a
  node's superseded holds occupying a slot another node's *current* run needs) is a
  corner case of *non-local rapid editing of a wide wavefront*; an **optional** preemption
  nicety (*current everywhere preempts superseded anywhere* under saturation) covers it.
  *(Part V.3 argued this preemption should be mandatory; **resolved: kept optional** — the
  user reclaims slots explicitly via `ctx.a.prune()` (below), with automated prune policy
  deferred.)*

### `ctx.prune()` — drop obsolete work on demand

Speculation means that even when no node is `waiting`/`computing`, **obsolete runs may
still burn cluster slots** until their hold windows fire — so node-state quiescence does
not by itself imply the cluster is idle. **`ctx.prune()`** closes the gap: it
**`softcancel`s every obsolete (superseded / grace-held) running E/T immediately**,
leaving only the **current** wavefront. It is lightweight and **repeatable** — *not* a
freeze, *not* a commit. After `prune`, all running work is current work, so once the
wavefront finishes the cluster is genuinely idle (*quiescence == idle*). The same call is
what fire-and-forget issues before detaching (§I.7).

**`prune` is also a per-node operation: `ctx.a.prune()`.** It `softcancel`s only the obsolete
(superseded / grace-held) runs in `ctx.a`'s own subtree — `ctx.a` and its downstream cone —
leaving the rest of the `Context`'s speculation untouched. This is the **user's manual control**
over which superseded work to reclaim: rather than the scheduler guessing a tighter automatic
cancellation policy (the rejected Part V.2/V.3 alternatives), the user — who knows which held run
is still worth keeping and which is dead weight — prunes exactly the subtree they want.
`ctx.prune()` is then just `ctx.a.prune()` applied at the graph root. Configurable machinery to
call `ctx.a.prune()` automatically (edit-rate / saturation / cost driven) can be layered on later,
but is not part of v1.

## I.6 Future-wired vs. checksum-wired E/T

- A **`waiting`** node owns a **future-wired** E/T: its inputs are upstream futures, not
  yet resolved checksums. It is keyed by its *upstream's* identity, so it can **never**
  produce a cache entry under its own identity. It is really a **registered
  continuation**, not a cacheable definition — which both reassures (it cannot pollute the
  cache) and confirms it carries no caching value.
- A **`computing`** node owns a **checksum-wired** ("running") E/T: a concrete E/T whose
  inputs are resolved checksums and which therefore has a constructed `tf_checksum`. At
  `waiting → computing` the checksum-wired E/T **replaces** the future-wired one (which is
  cancelled — but **not instantly**: its cancellation is deferred until **~10 s after the
  checksum-wired E/T is submitted**, giving Dask time to **latch-on** (deduplicate) the new
  submission onto whatever run the future-wired E/T already started. Cancelling the
  future-wired E/T immediately would race the latch-on and could discard a run the
  checksum-wired submission would otherwise reuse). This delayed, *forward-transition*
  cancellation is distinct from §I.5's *immediate* cancellation of future-wired E/T on
  **supersession** — there the node is being invalidated, with no replacement to latch onto.

**Phasing (sequencing only).** Future-wired E/T's sole present benefit (a few seconds of
latency) is not worth its complexity on its own; it is **necessary** for headless frontier
advance (§I.7) — it is the Dask-future encoding of the `waiting` cone. So: **ship the
reactive `Context` checksum-wired first** (a node leaves `waiting` for `computing` exactly
when its inputs are concrete checksums), and introduce future-wiring **with** the
fire-and-forget milestone, where it earns its keep. This shrinks the v1 state machine and
removes a whole cancellation path from v1. *(How a declared dependency edge picks up and
transitions between these two regimes is the open item — Part IV.)*

## I.7 Fire-and-forget: `prune` then detach (no "seal")

Fire-and-forget tears down the `Context` process while Dask keeps advancing the workflow
headlessly. There is **no seal/commit/freeze** step. It is two lightweight, already-
available actions:

1. **`ctx.prune()`** — softcancel all obsolete (superseded / grace-held) running work,
   leaving exactly the **current wavefront** plus the **future-wired forward cone** (the
   `waiting` nodes' E/T, already submitted to Dask as futures during normal lazy operation
   — §I.4/§I.6). This is the same `prune` that makes quiescent == cluster-idle; fire-and-
   forget just calls it before letting go, so there is no "messy state to collapse."
2. **Detach** — the `Context` process lets go. The current wavefront and the future-wired
   cone are **already** running on Dask (remote-by-checksum, against the shared
   hashserver), so they advance `waiting → computing → complete` headlessly by Dask
   dataflow.

**No freeze.** "No external edits during fire-and-forget" is a **consequence of
detaching** (the reactive process is gone), not an imposed mechanic. The **entire
reactive apparatus** (the §I.4 cascade, the §I.5 holds, supersession, invalidation) is
**online-only** and ceases to exist on detach — which is why headless advance needs only
the **autonomous** transitions Dask provides natively.

Bounds:

- **Forward-only.** Only autonomous `waiting → computing → complete` transitions occur
  headlessly; nothing reactive.
- **Blocked branches stay blocked.** `failed`/`blocked` nodes never resolve headlessly
  (their input futures never arrive) — correct, since they need intervention that cannot
  happen headless. On reattach they are still blocked.
- **No special case in tf-construction timing.** It follows the wiring: **eager at
  submission** for a checksum-wired node (all input checksums in hand), **deferred to
  runtime** for a future-wired node (some input still a future). The optional-pin drop-if-
  `null` rule (Part II) is one rule within tf-construction, applied whenever construction
  happens. *(Part V.9 argued value-dependent tf-construction makes "deferred to runtime" a
  dynamic-task problem; **resolved: non-issue** — a future-wired E/T is already a
  runtime-constructed continuation, so value-dependent shape rides the ordinary future-wired
  mechanism, not a new one. See Part V.7/V.9.)*

## I.8 Scope, assumptions, and admitted trade-offs

**Determinism is assumed.** The retain-and-compare loop (§I.5) assumes *same input ⇒ same
result checksum*. **Irreproducible transformations are out of scope for workflows.**
Irreproducibility is handled post-hoc by the `"irreproducible"` request
([database.py:947](../seamless-database/database.py#L947)), which drops the cache *mapping*
but not the result *buffer* — the correct response is to **pin that buffer** so the result
stays materializable. *Accidental* nondeterminism is equally out of scope and is **masked
by the content-addressed cache by default** — it surfaces only in consumers of a
nondeterministic result that is `scratch` (forcing recomputation), a **universal** Seamless
property, not a `Context` hazard. Expressions are **deterministic by construction**, so the
retain-and-compare is unconditionally safe on expression edges.

**Concurrency model (made explicit, per the V.5 resolution).** Every `Context` state
transition — edits, the §I.4 marking pass and cascade, the §I.2 attach/detach migration, and
the handling of each arriving update or new result — runs **synchronously on a single thread,
the instant the update/result arrives**. The **only** concurrent activity is the actual E/T
`.compute()` invocations, which run in a **dedicated event loop**. This is what makes §I.4's
"one non-yielding pass" and §I.2's "no dual-write window" hold *by construction*: nothing
interleaves with a marking pass or a state migration, because state transitions are never
concurrent with one another — only with compute, and a compute result re-entering the
`Context` is itself handled synchronously on arrival.

**Admitted trade-offs (stated, not silently accepted):**

- **Connected-optional pins lose laziness.** Because a connected optional pin is treated as
  required and the upstream may legitimately return `null`, the upstream **always runs**,
  even when its `null` is then dropped (Part II). "Optional" means "may be absent **or**
  `null`, but if connected, always computed" — the opposite of the intuitive reading.

**Open at this layer** (out of scope until the relevant phase): intra-context **cycles**
(the §I.4 cascade assumes a DAG), (de)serialization of a `Context` graph, the precise
**witness/observable-output surface**, and the **dependency-declaration contract**
(Part IV).

---

# Part II — Substrate A: Optional pins and connectivity `[SUBSTRATE]`

> This is a **transformation-construction** concern, not `Context` logic. It defines how a
> `tf_checksum` is built from pins and lives in `seamless-transformer`. The `Context` only
> *relies on* it; it is preparatory substrate work, surfaced and made acute by the workflow
> layer (reactive re-firing across changing connectivity) but built and tested **below** the
> `Context`.

### Connectivity (looser than legacy Seamless)

- An **unconnected optional** pin is **accepted** and is simply **not part of** the
  transformation — it does not gate the node.
- A **connected optional** pin is treated as **required** (it gates), with one escape
  valve: a transformer may now **return no result**, provided its result celltype can
  encode JSON `null` (`plain` or `mixed`). An optional pin that receives that "no result"
  value is **dropped from the transformation**.
  - **The "no result" value is the canonical checksum of JSON `null`** — a real
    content-addressed value — **not** `result_checksum is None`, which already means "not
    computed." (Conflating the two breaks completion detection.)
  - **By definition, JSON `null` on a connected optional pin *means that pin's absence*.**
    So "pin absent" and "pin present-but-`null`" canonicalize to the **same** `tf_checksum`
    — intended semantics, not an accident.

So **"sufficiently connected"** = every required pin wired + every connected-optional pin
wired; unconnected optional pins are absent.

### Admitted restrictions — optional pins are genuinely awkward

Two deliberate restrictions, both stated plainly because together they make optional pins
**difficult to use**:

1. A connected optional pin cannot also carry an *intentional* `null` value distinct from
   "absent," because `null` is spoken-for as the absence encoding. The only alternative (pass
   `null` through as a value) would contradict the chosen semantics.
2. **The drop-on-`null` escape valve covers only `null`-encodable result celltypes
   (`plain`/`mixed`).** A connected optional pin whose result celltype is `binary`, a deep
   structure, or any other non-`null`-encodable type has **no in-band way to signal "no
   result"** — it can be absent only while *unconnected*, never conditionally dropped once
   computed. For such celltypes "connected optional" collapses back to plain "required." (An
   out-of-band absence sentinel — a distinguished "absent" checksum independent of celltype —
   would restore conditional absence for all celltypes, at the cost of a second magic value
   threaded through tf-construction; it is deliberately **not** adopted in v1.)

Net: optional pins can be difficult to use, and that difficulty is accepted, not hidden.
*(Part V.7's further consequence — the transformation's shape becoming input-value-dependent —
is real but not a defect; it is handled by the ordinary future-wired mechanism. See Part V.7.)*

---

# Part III — Substrate B: Cancellation `[SUBSTRATE]`

> This lives in `seamless-transformer`'s transformation cache and in the servers. The
> `Context` only ever *calls* `softcancel`. It is the substrate the reactive supersession
> (§I.5) and `ctx.prune()` (§I.5/§I.7) make acute, but it is built and tested below the
> `Context`.

Multiple node-bound `Transformer`s — across nodes, across superseded/current runs, or
across *processes* — may share **one** running `Transformation` (same `tf_checksum`). A
`Context`-initiated cancel must therefore be a **soft** signal, not an unconditional kill.

The whole substrate is **one uniform pattern**: *a membership set lives wherever
deduplication happens*, and two operations act on it everywhere. There is **no manually-
maintained integer refcount and no `refholding` flag** — the set's membership **is** the
count.

### III.1 The awaiter set replaces the hand-rolled refcount

The single highest-leverage substrate change. Today the latch is one `_ActiveSubmission`
per `tf_checksum` holding one `concurrent.futures.Future`; the owner runs the work and
non-owners `await asyncio.wrap_future(active.future)`
([transformation_cache.py:320](../seamless-transformer/seamless_transformer/transformation_cache.py#L320)).
**The set of coroutines currently suspended on that future *is* the holder set;** the
refcount is exactly `len(awaiters)`. The structured-concurrency form:

- The actual execution is a **detached background task owned by the cache**, not by the
  first caller. **Every** participant — including the first — is a mere awaiter.
- A participant registers on entry and deregisters in `finally` (covering normal
  completion, exception, *and* task cancellation — which is what makes the `Context`'s
  `softcancel` "just cancel my await").
- When the awaiter set **empties**, the cache cancels the background task. That **is**
  `softcancel`-at-zero, for free.

This dissolves, *by construction rather than by patch*: the cross-generation aliasing
hazard (each generation is a different future object — the cache already pops the old
`_ActiveSubmission` and installs a new one, see
[L301](../seamless-transformer/seamless_transformer/transformation_cache.py#L301)); "no
incref on a pure cache hit" (a hit returns immediately and never registers an awaiter);
"completion decrefs too" (awaiters wake and deregister in `finally`); and the `__del__`
backstop (a GC'd/cancelled holder's coroutine is cancelled by the loop, hits `finally`,
deregisters). The one real change required is **decoupling execution from the first
caller** — today the owner *is* the executor, so cancelling the first caller kills the
work for everyone; that coupling is exactly wrong for soft-cancel.

### III.2 Where the set lives, and what a "member" is

- **In-process & jobserver — an awaiter set.** A `tf_checksum` maps to the set of
  participants awaiting its one running submission.
  - *In-process* (`seamless-transformer`): members are the coroutines suspended on the
    shared submission future; a member deregisters in `finally`. A pure cache hit is never
    a member — refcount-neutral for free.
  - *Jobserver*: the **same pattern, an independent instance inside the jobserver** —
    members are the latched *clients/processes*. This is the change that makes the
    **jobserver no longer delete siblings**: a client's cancel removes only that client
    from the server-side set.
- **Dask — a first-runner → latch-on-runner set.** Dask has *obligate* latch-on onto a
  **first-runner**, so the daskserver maps the first-runner to its **set of
  latch-on-runners**, and **the first-runner itself is registered as a (quasi-)member**.
  "Quasi" = counted like a member for cancellation *and* result delivery, but **not** the
  lifecycle owner: the **cache/set owns the future reference**, so softcancelling the
  first-runner cannot let Dask release the future out from under surviving latchers.

### III.3 The two cancel operations

- **`softcancel`** = *remove this member from the set; if the set is now empty, cancel the
  underlying run.* Above zero, the run continues for the remaining members; on a
  completed/forgotten checksum it is a no-op.
  - **It is pure deregistration — no signal reaches the member being removed.** Soft-cancel
    is a member *voluntarily leaving* (its owner stopped wanting the result), so the
    substrate's whole job is `set.discard(member)` + the empty check. A real cancellation
    signal is delivered **only** when the set empties, and **only to the underlying
    run/executor**.
- **`cancel`** (hard) = *cancel the underlying run/first-runner outright; every member is
  signalled and cancelled too* — matching today's kill-all
  [`cancel_by_checksum`](../seamless-transformer/seamless_transformer/transformation_cache.py#L348).
  Unlike `softcancel`, this **does** signal members, because the *run* is being declared
  wrong, not abandoned.

### III.4 Constraints — one load-bearing, two cheap-or-optional

1. **`[LOAD-BEARING]` Softness composes across layers — softcancel cascades *soft*, never
   hard.** The "cancel the underlying" in `softcancel` is itself a **`softcancel` of the
   next layer down** when the underlying is a shared remote submission: an empty in-process
   set ⇒ *leave the jobserver/dask set* (not kill it). A real termination happens **only at
   the leaf set** — co-located with the actual executor — when *that* set empties. If
   empty-set hard-cancelled the remote instead, the local set would merely relocate the
   unconditional kill one process hop downstream — the footgun unfixed.
2. **`[OPTIONAL — slot reclamation, not correctness]` Cross-process membership liveness.**
   The in-process set self-cleans via `finally`; a server-side set does not. **But a leaked
   member is benign — and more than benign, often *correct*.** It causes *under*-cancellation,
   never a peer kill: a crashed/disconnected client that never sends `softcancel` does not pin
   a peer's job and corrupts nothing; the job simply **runs to completion** and the set is then
   forgotten. Critically, **a crashed holder usually still wants its result** — a crash is not
   a statement that the work has become uninteresting, more often the opposite — so the run
   completing and depositing its result in the content-addressed cache is exactly what the
   holder needs on reconnect. Building TTL heartbeats to *force* cancellation on disconnect
   would therefore destroy work that is still wanted. Connection-scoped auto-deregister may be
   taken **where it is free**, but it must **not** be relied on as a cancellation trigger, and
   dedicated liveness machinery is **not** built.
   *(This resolves Part V.8, which argued liveness should be required: it should not — the
   "unbounded cost" it cites is the result being computed once and cached, which the
   disconnected holder reclaims on reconnect, not waste.)*
3. **`[HYGIENE]` Per-set atomicity.** "remove last member → empty → cancel" races "a new
   submitter wants to latch." Keep membership-change and empty-check-and-cancel under one
   lock **per set** (in-process
   [`_active_lock`](../seamless-transformer/seamless_transformer/transformation_cache.py#L172);
   the analogous server-side lock). A lost race merely re-submits a fresh run — never
   corrupting, since results come from the content-addressed cache, never from the set.

### III.5 Policy

- **The reactive scheduler uses `softcancel` exclusively** — including for **node
  deletion** — because siblings and cross-process peers may legitimately share a running
  `tf_checksum`. The reactive loop only ever *loses interest*, which is precisely
  `softcancel`.
- **Hard `cancel` means "this run is *wrong* and must be killed and resubmitted" — and its
  cross-tenant reach is therefore *correct*.** It is the response to a run computed the
  wrong way: a **wrong dunder envelope** or **wrong hardware**. Because the execution
  envelope is **orthogonal to the `tf_checksum`**, the *same* `tf_checksum` can be running
  under the wrong envelope **for every latcher at once** — so all of them need it killed and
  resubmitted. This is the deliberate escape hatch for the existing `strict_dunder` check
  ([L304](../seamless-transformer/seamless_transformer/transformation_cache.py#L304)). A
  wrong *input* is usually a **different** `tf_checksum`, unlikely to be shared, so
  `softcancel` suffices there.
- The caller never manages server-side membership directly; it only `softcancel`s its own
  participation. **Each site decides when to actually kill, by its own set.**

### III.6 `Expression` cancellation — only on the byte-moving paths

The functional-substrate plan said an expression is "not separately cancellable." That is
**half right**:

- The **codebook application** (get-attr / get-item / slice / convert) is zero-cost and
  uncancelable. The deep-checksum fast path (navigate the Merkle manifest, never
  materialize the parent) genuinely has nothing to interrupt and stays uncancelable.
- The **buffer I/O envelope** around it — fingertip/materialize a large input,
  serialize/write a large output — is neither instantaneous nor uninterruptible.

So **an `Expression` exposes a cancellation surface iff it must move bytes.** On the
materialize-and-apply and write paths, `Expression.cancel()`/`softcancel()` interrupts the
**I/O**, not the op, and participates in the **same** §III refcount layer (input
materialization and output writing share the one running-checksum refcount; I/O is not a
separate layer). This requires replacing the
[`NotImplementedError`](../seamless-core/seamless/expression_class.py#L222) stub.

**`Expression.clear_exception()` (substrate, per the V.4 resolution).** Orthogonally to
cancellation, the failed-node recovery of §I.3 needs a substrate hook.
`ctx.node.clear_exception()` forwards to the failed `Context`-private E/T; for an
`Expression`-backed node that is **`Expression.clear_exception()`** — clear the recorded
exception and re-derive from current inputs, the `Expression` analog of a `Transformation`'s
clear-and-recompute. Like `Expression.cancel()`, it replaces a not-yet-existing stub.
(Automatic retry of *transient* failures stays a `Transformation`/backend concern, out of
scope — §I.8 / Part V.4.)

### III.7 What this buys

This **fixes** the jobserver multi-tenant footgun (rather than admitting it), at the cost
of giving the jobserver a server-side membership set — reversing the "intentionally simple
jobserver, no server-side refcount" decision. The daskserver's previously-aspirational
latch-aware cancel is now simply **one instance of this one pattern**, not a separate
asymmetry. The cost is modest — the set itself, *not* a liveness mechanism (constraint 2: a
leaked member is benign) — and it removes a cross-tenant data-loss hazard.

---

# Part IV — To discuss: dependency declaration into `Context`-held nodes `[OPEN]`

How a dependency on a `Context`-held node is **declared, captured, and resolved** is
deferred. The **capture** shape is the likely-settled part; the **contract** at the end is
what must be worked out.

**Capture — does not depend on view identity.** Declaring a dependency (e.g.
`ctx.b = ctx.a.sub`) does **not** rely on the identity of the transient navigation view
(`ctx.a is ctx.a` may be `False`, harmlessly). The dependency is captured by *content*:

- **`Context`-bound** `Transformer`/`Cell`: the dependency is written **immediately into the
  `Context`-held DAG as a nodepath edge** `(source-node-ref, path, celltypes)`, which
  **becomes an `Expression` as soon as the consuming node goes `waiting`/`computing`** (the
  §I.2/§I.6 per-tick materialization).
- **Non-`Context`-bound** `Transformer`/`Cell`: the dependency can be **stored verbatim**
  (the reference as given) and **resolves to an `Expression` as soon as the `Transformer`
  becomes a `Transformation`** (at build time).

**Contract — to settle later.** When the edge's `Expression` materializes, its **input
checksum** is in one of two regimes, each needing a defined contract:

- **input checksum already known → checksum-wired** `Expression`;
- **input checksum not yet known → future-wired** `Expression` (the upstream is still
  pending).

The precise contract for each — resolution, identity/caching, and the **checksum-wired ↔
future-wired** transition — is the open item. It is the §I.6 future-wired/checksum-wired
split applied specifically to *declared dependency edges*, and it governs how navigation-
derived dependencies cache, fire, and reattach.

*(Part V.10 sketches a concrete contract — a declared edge stored as a **future-wired
`Expression`** that transitions to checksum-wired by substitution when its input resolves.
Its "optional-pin landmine" — that such an edge cannot be *shaped* until the upstream resolves
— is **not** a special blocker: that is simply what a future-wired E/T is (a runtime-constructed
continuation), and pre-submission remains possible. See Part V.7/V.10.)*

---

# Part V — Fresh first-principles critique (this pass), with alternatives

The synthesized design above is internally coherent; the awaiter-set substrate is the right
backbone and the three-case hold taxonomy is correct as far as it goes. The points below are
**new** — not raised (or not raised this way) in pass 2 — and ordered by leverage. Two
(V.6/V.7 and V.8) attach to the substrates of Parts II and III; V.10 attaches to the open
item of Part IV.

## V.1 Eager cone-marking is O(cone) synchronous; prefer epoch-stamping

§I.4 makes one operation mandatorily **synchronous and non-yielding**: marking the entire
downstream cone non-current "in one non-yielding pass, before any descendant is evaluated
for firing." The design defends this as cheap-per-node (pointer/enum flips). It is cheap
*per node* but **O(cone) per edit**, on the event-loop thread, with no yield point. On a
large graph (10⁵–10⁶ nodes), a single edit near the root stalls the loop for the whole
cone scan — and edits near the root are exactly the common interactive case. "Most of the
cone is already `waiting`" softens the *steady-state* cost but not the worst case (a fresh
edit after quiescence), and it still requires *visiting* every node to check.

**Alternative — epoch / generation stamping** (the salsa / Adapton / Incremental
technique). Keep a monotonic `epoch` counter; bump it on each change and record only the
*changed node(s)*. Each node stores the epoch at which its result last completed. A node is
**current** iff every input's completed-epoch is consistent with the node's own — checked
**at firing time**, on the pull side, not eagerly pushed. Then:

- **Invalidation is O(1)**: bump `epoch`, record the changed node. No cone walk.
- **Glitch-freedom still holds**: a node refuses to fire if any input was completed under a
  superseded epoch — so `c` will not fire on a stale `b` regardless of *when* it is
  examined.
- **The cone walk survives only as the *lazy submission* pass** — which §I.4 already
  decoupled and made lazy/prioritised. The expensive part is the part already allowed to be
  slow; the part required to be synchronous becomes O(1).

The cost is a slightly more careful "is-current" predicate for multi-input nodes (current
iff *all* inputs current at-or-after the relevant epoch) and an epoch field per node. The
benefit is removing the design's **only** hard synchronous-latency obligation. I recommend
the design at least *justify* keeping eager marking over epoch-stamping; right now it adopts
the more expensive option without comparison.

> **Resolution (pass 3, per user).** Rejected — eager cone-marking is kept; epoch-stamping is
> **not** adopted until the O(cone) synchronous-marking latency is actually *observed* to bite.
> Simplicity first. Residual risk acknowledged: on very large graphs (10⁵–10⁶ nodes) a
> root-level edit's marking pass is O(cone) on the single `Context` thread; revisit
> epoch/generation stamping if and when that latency materializes.

## V.2 The hold window is bounded by the slowest *transitive* changed upstream, not the immediate one

§I.5 case (a) is framed throughout as "hold `B` until **`A`** resolves, then compare `A`'s
output," with the reassurance that "the wait is short *because `A` is short*." That
reasoning holds only for a **single, immediate** changed upstream. In general `B`'s
`tf_checksum` is a function of **all** its inputs, and a change may be several levels up or
fan in from several upstreams at once. `B` cannot decide reinstate-vs-cancel until its
**entire changed transitive upstream frontier** has re-resolved — so `B`'s hold window is
`max` over that frontier, i.e. potentially **the whole depth-wise recompute of the
invalidated cone**, not a short `A`. Worse, this is true for *every* `computing` node in the
cone simultaneously, so expensive superseded runs **stack down the depth of the cone** for
the cone's full recompute time — pressuring the ≤3×concurrency cap and memory at exactly the
moment (a large cascade) when the design's "bounded by backend concurrency" comfort is least
reassuring. The single-`A` narrative is the best case dressed as the general case.

**Alternative — cancel-on-first-divergence, per edge.** Do not wait for the whole frontier.
The instant *any* changed upstream of `B` re-resolves to a **different** output, `B`'s
`tf_checksum` is provably different → cancel `B`'s superseded run immediately (it can never
be reinstated). Keep holding only while *every* upstream resolved-so-far matched. This is
strictly tighter than "wait for the frontier, then compare," turns the worst case (deep
cone, one early divergence) into an early release, and needs no new bookkeeping (the
`Context` already holds the edges). Pair it with a **cost-weighted** slot budget rather than
a flat ≤3 — a node running an expensive GPU job should be allowed fewer or shorter holds than
one running a cheap op (the design already gestures at this for case (b); generalise it).

> **Resolution (pass 3, per user).** Rejected — no automatic cancel-on-first-divergence. The
> restored cache hit is **not always immediately downstream**: there are real cases where a
> superseded run/buffer pays off several levels down (e.g. a non-injective transformation
> collapses an upstream divergence back to an unchanged output), so eager per-edge cancellation
> would discard work that still has downstream value. Keep the event-driven grace-hold (≤5 min)
> and give the user **`ctx.a.prune()`** (§I.5) for explicit, surgical reclamation — the user
> knows which held run is worth keeping; the scheduler should not guess.

## V.3 Speculation harms the canonical reactive workload; "preemption is optional" is backwards

The reactive `Context` exists for **live, interactive** editing. The defining interactive
pattern is *rapid successive edits*: dragging a slider, scrubbing a parameter, an animation
loop, a sweep driver feeding the `Context`. Under that pattern the wavefront keeps moving and
superseded grace-holds keep occupying slots — so speculation (whose entire purpose is to
smooth churn) ends up **competing with the newest current work for the same backend slots**.
That is the opposite of help, and it happens in precisely the workload the feature targets.
§I.5 nonetheless relegates "current everywhere preempts superseded anywhere under saturation"
to an **optional nicety**. That is the priority inverted: under the canonical workload it is
load-bearing.

**Alternative — mandatory preemption under saturation, plus an adaptive hold window.** (1)
When the backend is saturated, *current* work must always preempt *superseded* work — make
it a guarantee, not an option. (2) Make the hold lifetime a **function of observed edit
rate**: at high edit frequency the probability that a held run is still wanted collapses
(the next edit is already here), so the hold should shrink toward zero — pure
cancel-on-supersede when edits are raining in, full hold when edits are sparse. This
generalises the design's own "GPU lifetime shrinks toward zero" instinct from *cost* to
*cost × contention × edit-rate*, and it makes speculation self-disabling exactly when it
would otherwise hurt.

> **Resolution (pass 3, per user).** Rejected — preemption stays **optional** and the hold
> window is not made adaptive. Same principle as V.2: the user reclaims slots explicitly via
> **`ctx.a.prune()`** rather than the scheduler guessing. Configurable machinery to call
> `ctx.a.prune()` automatically (edit-rate / saturation / cost driven) can be layered on later;
> it is out of v1.

## V.4 No transient/retryable-failure model — every `failed` is terminal-until-external-change

§I.3 makes `failed` an **equilibrium** state that leaves "only via an external change," and
§I.8 scopes out *irreproducibility*. But **transient infrastructure failure is neither an
equilibrium nor irreproducibility**: a Dask worker OOMs, a spot instance is preempted, a
network blip drops a connection. The transformation *would* yield its canonical result on a
re-run — it is fully reproducible — but the design parks its node in `failed`, where it sits
until a human intervenes. This silently defeats the headline features: a single preempted
worker permanently wedges a node, and **fire-and-forget** (§I.7) — running headless with no
reactive process to intervene — will simply **stall forever** on the first transient failure
in the forward cone. Real clusters fail transiently all the time; a workflow engine that
treats every failure as terminal is not deployable headless.

**Alternative — a substrate-level retry policy and a `failed` sub-distinction.** Distinguish
`failed-deterministic` (the transformation itself raised — true equilibrium, needs a code
fix) from `failed-transient` (infra-class failure — *out*-of-equilibrium, auto-retryable),
parallel to the existing `{blocked-by-unwired, blocked-by-error}` block-reason enum. Give the
backend a bounded retry-with-backoff policy for the transient class. This is mostly a
**substrate** concern (the transformation cache / backend classifies the failure), surfaced
by the `Context` as the sub-state — but the *design* must decide the taxonomy now, because
"all failures are terminal" is baked into the equilibrium definition and the headless bounds.

> **Resolution (pass 3, per user).** Mostly rejected as out of scope: the
> transient-vs-deterministic failure taxonomy and retry-with-backoff are a
> **`Transformation`/backend** concern, not `Context` logic, so `failed` stays one equilibrium
> state (V.12.3's `failed-transient` UX falls with it). **Adopted:** `ctx.node.clear_exception()`
> (forwarded to the failed `Context`-private E/T — §I.3) and, at the substrate,
> **`Expression.clear_exception()`** (Part III.6).

## V.5 The concurrency model is never stated — and the substrate evidence contradicts the implicit one

Several load-bearing claims are correct **only** under a single-threaded event loop that
serialises edits, cascades, and resolution callbacks: the "**one non-yielding pass**" of
§I.4, the "**no dual-write window**" of §I.2, and "an external change perturbs; the `Context`
relaxes" presuppose that nothing interleaves with the marking pass or the attach/detach
migration. The design never states this model — and the substrate it builds on suggests the
opposite: the transformation cache guards `_active_submissions` with a **`threading.RLock`**
([L172](../seamless-transformer/seamless_transformer/transformation_cache.py#L172)) and
bridges `concurrent.futures.Future` → asyncio via `wrap_future`, i.e. **results can arrive on
threads other than the loop thread**. If a resolution callback can fire mid-marking-pass from
a worker thread, the "non-yielding" guarantee is not automatic — it needs an explicit hop
onto the loop thread.

**Alternative / fix — state the concurrency contract explicitly.** Declare that all `Context`
state transitions (edits, the marking pass, cascade, attach/detach, and resolution handling)
execute on a single designated thread/event-loop, and that substrate callbacks arriving off-
thread are marshalled onto it (`loop.call_soon_threadsafe` or equivalent) before they touch
node state. This is probably what the author intends; it is currently load-bearing and
unwritten, and the `RLock` is concrete evidence the boundary is real.

> **Resolution (pass 3, per user).** Addressed by *stating the model*, not by the proposed
> off-thread marshalling. The concurrency contract (now in §I.8): every `Context` state
> transition runs **synchronously on a single thread the instant an update/result arrives**;
> the **only** concurrency is E/T `.compute()`, which runs in a **dedicated event loop**.
> §I.4's non-yielding pass and §I.2's no-dual-write window therefore hold by construction.

## V.6 Substrate A: drop-on-`null` only covers null-encodable result types

Part II's escape valve — "a transformer may return no result, provided its result celltype
can encode JSON `null` (`plain` or `mixed`)" — silently restricts conditional absence to
**null-encodable** pins. A connected optional pin whose result celltype is `binary`, a deep
structure, or any non-`null`-encodable type has **no in-band way** to signal "no result" at
all: it cannot be absent-when-computed, only absent-when-unconnected. So the cheerful reading
"optional means may-be-absent-or-`null`-if-computed" holds only for `plain`/`mixed` pins; for
every other celltype, "connected optional" collapses back to plain "required." This compounds
the already-admitted "can't carry an intentional `null`" restriction and should be stated
alongside it, because users will reach for an optional `binary` pin and find it can never be
conditionally dropped.

*Alternative:* an out-of-band absence sentinel (a distinguished "absent" checksum independent
of the pin's celltype) would restore conditional absence for all celltypes — at the cost of a
second magic value to thread through tf-construction. Whether that is worth it is a real
choice; the current design makes it by omission.

> **Resolution (pass 3, per user).** Accepted — documented. The drop-on-`null` escape valve
> covers only `null`-encodable (`plain`/`mixed`) result celltypes; for any other celltype
> "connected optional" collapses to "required." Now stated in Part II's *Admitted restrictions*,
> with the plain admission that **optional pins can be difficult to use**.

## V.7 Substrate A: the transformation's *shape* becomes input-value-dependent

A subtler consequence of the drop-on-`null` rule: whether a connected-optional pin is **part
of** the `tf_checksum` depends on the *runtime value* of its upstream (null → dropped,
non-null → present), not merely on that upstream's checksum treated opaquely. This is still
*consistent* — `tf_checksum` remains a pure function of input checksums (the null-checksum
maps to "drop") — but it means a downstream node's very **identity and arity are not known
until the optional upstream resolves to a concrete value**. That is stronger than the admitted
"loses laziness": it is "loses *identity-predictability*." Two concrete consequences the design
should own: (1) the `Context` cannot construct, key, or pre-submit such a node's E/T until the
optional upstream has *resolved* (not merely been *wired*); (2) this is the root cause of the
Part IV / V.10 problem and the V.9 Dask problem. Worth promoting from an implicit property to a
stated one, because it ripples into three other sections.

> **Resolution (pass 3, per user).** Rebutted. The property (a connected-optional consumer's
> shape is input-value-dependent) is real and admitted, but the claimed *consequence* — "cannot
> pre-submit until the upstream resolves" — is wrong. **Every** future-wired E/T has an input it
> cannot key until resolution; that *is* future-wiring (a runtime-constructed continuation), and
> **pre-submission remains possible**. No special blocker; V.9 and V.10's landmine fall with it.

## V.8 Substrate B: declining liveness strands exactly the expensive jobs cancellation exists to free

Part III constraint 2 calls cross-process liveness "optional — slot reclamation, not
correctness," on the grounds that a leaked member (crashed holder) is benign because "the job
runs to completion, bounded by its own runtime." That is right about **correctness** and wrong
about **the cost the feature exists to control**. Consider the case the cancellation substrate
is *for*: an expensive, long-running shared run where **all real consumers `softcancel`** but
**one crashed holder leaks** a membership entry. The leaf set never empties → the run is
**never** cancelled → it burns its full (long, expensive) runtime. The worst-case stranded cost
is therefore largest **precisely for the most expensive jobs** — the exact jobs whose slots you
most wanted to reclaim. "Bounded by its own runtime" is reassuring for cheap jobs and useless for
the ones that matter.

**Alternative — make connection-scoped membership *required*, not "free where available."** The
design already prefers connection-scoped auto-deregister "where membership is naturally
connection-scoped"; promote it from a nicety to a requirement at every server-side set. A dropped
connection removing its member is the cross-process analog of the in-process `finally` — it is the
crash-liveness mechanism, it needs **no** heartbeats/TTL, and it closes the unbounded-cost hole
without reintroducing the machinery constraint 2 rightly rejects. Reframe the constraint:
*liveness is optional for correctness, load-bearing for the cost goal that motivates cancellation
in the first place.*

> **Resolution (pass 3, per user).** Rebutted — liveness stays optional, on a *stronger* ground
> than "benign": a crashed/disconnected holder **usually still wants its result**, so forcing
> cancellation on disconnect would destroy work the holder will reclaim from the content-addressed
> cache on reconnect. The "unbounded cost on expensive jobs" is that result being computed once
> and cached — not wasted. (Part III constraint 2 updated.)

## V.9 Headless advance of a value-dependent cone needs dynamic task generation on Dask, not dataflow

§I.7 asserts the future-wired forward cone "advances `waiting → computing → complete` headlessly
by **Dask dataflow**," as if the whole cone were a static Dask graph of futures-of-futures.
Combine that with V.7: a future-wired node whose `tf_checksum`/arity depends on an optional
upstream's *runtime value* **cannot be encoded as a static Dask task** at prune/detach time — its
identity is not yet known. Such a node must instead be a Dask task that, **when its inputs
resolve, constructs and submits the real transformation** — i.e. *dynamic submission from within a
running task* (`client.submit`/`secede`-style), which is materially more complex and more failure-
prone than static dataflow, and interacts badly with V.4 (a transient failure mid-dynamic-
submission has no reactive process to recover it). The design should either (a) state that fire-
and-forget requires dynamic task generation for value-dependent nodes and accept the complexity,
or (b) **restrict the headless cone to nodes whose shape is already determined** (no unresolved
optional-pin dependence), making fire-and-forget's eligibility a checkable property rather than an
assumed one. Option (b) is the cleaner contract and worth preferring.

> **Resolution (pass 3, per user).** Rebutted (follows from V.7). No special "dynamic task
> generation" is required: a future-wired E/T is already a runtime-constructed continuation, so a
> value-dependent headless node advances as ordinary future-wired work. Fire-and-forget
> eligibility needs no extra shape-determinacy restriction.

## V.10 Part IV: a concrete dependency-declaration contract — and the optional-pin landmine in it

The open item (Part IV) can be given a concrete, defensible contract:

- **A declared edge is always stored as a future-wired `Expression`** (input = the upstream
  node's checksum-*future*), and **transitions to checksum-wired by substitution** when that future
  resolves. Identity/caching key **only ever on the resolved input checksum**; the future-wired
  form is a non-cacheable continuation (§I.6) and never produces a cache entry under its own
  identity. This makes the "transition" a non-event: the same edge yields the same `Expression`
  identity the moment its input is concrete, regardless of how long it was future-wired.

That contract is clean for ordinary edges. The **landmine** is the declared edge **into an
optional pin** (Parts II, V.7): by V.7 its consumer's `tf_checksum` is not even *shaped* until the
upstream resolves (null → pin dropped → different transformation than non-null). So such an edge is
**structurally provisional** — the `Context` cannot finalise the consumer's identity, cannot
pre-submit it, and cannot future-wire it as a fixed Dask task until the optional upstream has
*resolved to a value*. This is the precise mechanism behind the admitted "connected-optional pins
lose laziness," and it should be written into the Part IV contract as an explicit rule: *a declared
edge into a connected-optional pin defers the consumer's tf-construction past the upstream's
resolution, not merely past its wiring.* Settling Part IV without naming this case will reproduce
the V.9 problem inside the dependency model.

> **Resolution (pass 3, per user).** Contract sketch accepted as the working shape for Part IV
> (a declared edge is a **future-wired `Expression`** that becomes checksum-wired by substitution
> on resolution). The "optional-pin landmine" is rebutted (follows from V.7 — pre-submission
> works), so Part IV stays formally open but is no longer blocked by the optional-pin case.

## V.11 Architectural alternative: a pull/demand-driven `Context` instead of push/speculation

The largest observation. **Almost the entire complexity budget of Part I §I.5–§I.7 — supersession,
the three-case hold taxonomy, the ≤3×concurrency bound, `ctx.prune()`, the seal-that-isn't — exists
to manage *eagerly-launched speculative work* under a *push* model.** The design assumes push
(fire the wavefront proactively on every edit) without ever weighing it against the alternative.

A **pull / demand-driven** `Context` (the Adapton / salsa / Incremental lineage) computes a node
**only when a witness/observable output is demanded**. Under pull:

- **There are no superseded runs** — you do not fire until asked, so there is nothing to supersede,
  hold, cap, or `prune`. §I.5 largely **disappears**.
- **Glitch-freedom is trivial** — a demand pulls each input to its *current* value before computing,
  so a stale-input glitch cannot even be expressed (no eager wavefront to race).
- **Fire-and-forget becomes a one-shot** — "demand these outputs, then detach" is a single remote
  computation with no online reactive apparatus to tear down; §I.7's prune-then-detach and the
  future-wired/Dask-dataflow machinery (§I.6, V.9) reduce to ordinary remote-by-checksum execution.
- **Content-addressing already supplies the memo** that incremental pull needs, so re-demand after a
  small edit reuses every unchanged sub-result — the *same* benefit the push design gets from the
  cache, without the speculation.

The cost of pull is **latency-to-warm**: results are not ready until demanded, so a live UI that
wants every intermediate continuously updated feels less "instant." That cost is real for *live-
coding / interactive dashboards* — but it is small or irrelevant for Seamless's center of gravity,
**batch HPC pipelines**, where the natural API is exactly "compute these final outputs" and nobody
is watching intermediates tick. My recommendation is not necessarily "switch to pull," but: **the
design should make the push-vs-pull choice explicitly and justify push**, because push is what
drags in §I.5–§I.7's entire apparatus. A plausible synthesis is **pull by default, eager opt-in**:
demand-driven for batch/headless (most of Seamless), with an `eager=True` per-node or per-`Context`
flag that turns on the §I.5 speculation machinery only for the interactive subgraph that actually
benefits. That would let the speculation/hold/prune complexity be **paid for only where it earns its
keep**, instead of being the unconditional default.

> **Resolution (pass 3, per user).** Rebutted — push is retained; the `Context` is **not**
> switched to pull-by-default. Eager-vs-lazy is a real, available axis, but V.11's premise — that
> pull makes §I.5's supersession/holds **disappear** — is false: **a pull coroutine is still
> concurrent with input updates**, so a demanded computation can still be superseded mid-flight
> and the same hold/supersession questions recur. Pull does not buy the claimed simplification.

## V.12 Minor

- **Reinstatement is not a special operation — say so once, plainly.** §I.5 case (a) "reinstate
  `B`" reads like a mechanism, but per Part III it is *nothing*: `B` simply re-derives the same
  `tf_checksum` and re-latches onto a still-running submission via the awaiter set. Stating this kills
  the impression that the `Context` must surgically resurrect a run.
- **Per-tick E/T materialization cost.** §I.2 materializes E/T per tick; the cost is bounded to the
  invalidated cone and is a small `tf_checksum` hash over checksum-sized inputs, not buffers. Worth a
  sentence so it is not mistaken for a whole-graph rehash.
- **`failed` vs `blocked` UX, extended.** With V.4's `failed-transient`, a fourth user-facing
  situation appears ("nothing is wrong, it's retrying") that is neither an equilibrium error nor a
  wiring gap; the queryable-reason enum should cover it so a UI can show "retrying" rather than a
  spurious error badge.


> **Resolution (pass 3, per user).** 12.1 (reinstatement is not a special operation) — agreed;
> already stated plainly in §I.5. 12.2 (per-tick materialization cost) — agreed; sentence added
> to §I.2. 12.3 (`failed-transient` "retrying" UX) — rejected with V.4; no fourth user-facing
> state, the block-reason enum stays `{blocked-by-unwired, blocked-by-error}`.

## Response by the user


"A node reaches computing iff all required upstream are complete, and every connected-optional upstream is either complete or definitively in its empty/dropped case (Part II) — not the naive "all upstream complete," which would wedge a node forever behind one errored optional pin."

This is false. Errored optional pins *do* cause a node to be blocked.


"The block reason is a first-class, queryable enum {blocked-by-unwired, blocked-by-error}" In case of multiple reasons, blocked-by-unwired takes priority.

"A fixed timer would be wrong precisely when the upstream is slow — it would expire before confirmation, killing B at exactly the case the hold exists to protect." This is not quite right. I think five minutes is a reasonable maximum value to hold on to B.

ctx.prune() . This should also be implemented at the node level (ctx.a.prune())

"the checksum-wired E/T replaces the future-wired one (which is cancelled)" Cancelling should be ~10 seconds after the checksum-wired E/T was submitted, in order to allow Dask latch-on to happen.

V.1: reject proposal. Keep it simple until the outlined problem is proven to occur.
V.2: reject proposal. I know counterexamples where the restored cache hit is not immediately downstream. User knows best, `ctx.a.prune()` will help.
V.3: reject proposal. Same reason: user knows best, `ctx.a.prune()` will help. Configurable machinery for automated `ctx.a.prune()` calling can be added later.
V.4: mostly reject as out-of-scope. Retries and Transformation.clear_exception() are a Transformation feature. That being said. `ctx.node.clear_exception()` (call forwarded to failed Context-private E/T) is to be added. On a substrate level, `Expression.clear_exception()` is to be implemented.
V.5: No. Everything is synchronously as soon as an update/new result arrives, except the actual E/T .compute() invocations, these are in a dedicated event loop.
V.6: The tension is admitted, and it must be documented. Optional pins can be difficult to use.
V.7: The consequences are plain wrong. Any future-wired E/T has this problem, and it is dealt with: pre-submission remains possible.
V.8: Shrug. Holders may crash and leak, causing work to be not-cancelled. In any case, "crash" doesn't imply "my submitted work is no longer of interest and should be softcanceled", usually quite the opposite.
V.9/V.10: Wrong because V.7 is wrong.
V.10: Right that evaluation can be eager or lazy, wrong on all the specifics. A pull coroutine can still be concurrent with input updates!
V.12: 1., 2. agree. 3., reject.