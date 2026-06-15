# Reactive `Context` Internals — Design (Pass 2)

> **What this document is.** A second-pass synthesis of
> [`context-internals-design.md`](context-internals-design.md). That document was a
> three-round argument: Part I a design, Part II/III a critique, with the author's
> resolutions interleaved across rounds 1–7. This pass folds every *resolved*,
> *conceded*, and *admitted* point into one coherent, standalone statement (Part I),
> then criticises **that** statement from first principles (Part II), and finally
> carries forward the criticisms from the original that were never rebutted
> (Part III).
>
> It is the concrete form of the appendix of
> [`cells-and-expressions-implementation-plan.md`](cells-and-expressions-implementation-plan.md):
> the reactive layer that sits **on top of** the immutable functional substrate
> (`Expression`/`Transformation` nodes, checksum futures).
>
> **Implementation status (verified against the tree, 2026-06-14).** The functional
> substrate is implemented: [`Cell`](../seamless-core/seamless/cell_class.py) and
> [`Expression`](../seamless-core/seamless/expression_class.py) exist, with
> composite-key identity and the build-once snapshot contract.
> [`Expression.cancel()`](../seamless-core/seamless/expression_class.py#L222) is a
> `NotImplementedError` stub. The reactive `Context` is **not implemented** —
> `seamless-workflow` is empty and no `Context` class exists. The
> running-transformation refcount is **net-new**: today
> [`_active_submissions`](../seamless-transformer/seamless_transformer/transformation_cache.py#L316)
> is a single-entry-per-`tf_checksum` latch, and
> [`cancel_by_checksum`](../seamless-transformer/seamless_transformer/transformation_cache.py#L348)
> pops it and fails the one shared future, killing *all* latchers. The **buffer**
> refcount + [`tempref`](../seamless-core/seamless/caching/buffer_cache.py#L230)
> machinery already exists and is reused; the **running-work** refcount does not.

---

# Part I — Synthesized Design

## 1. Scope and substrate

The functional layer is settled and shipped. `Expression` and `Transformation` are
immutable, content-addressed nodes in one lazy DAG, each producing a checksum
future. `Cell` and `Transformer` are mutable, build-once builders: navigation
returns a derived builder; the build call snapshots the current `(input-ref, path,
celltypes)` into an immutable definition. Nothing below the `Context` knows a
`Context` exists.

`Context` reintroduces **reactivity** on top, without leaking reactivity into the
immutable layer. Its one-sentence essence:

> **Reactivity = re-build with fresh snapshots.** When a logical cell takes a new
> value, the `Context` builds new immutable `Expression`/`Transformation` definitions
> from the new snapshot and fires them; the content-addressed cache reuses every
> sub-result that did not actually change. The functional layer never mutates.

Throughout, **E/T** abbreviates "`Expression` and/or `Transformation`" — the two
immutable node kinds the `Context` fires.

### Substrate vs. workflow scope — what is *preparatory*, not `Context` logic

Several capabilities this document specifies are **not** reactive-`Context` logic.
They live in the **functional substrate** (`seamless-core`, `seamless-transformer`,
the servers) and would exist there even without a `Context`; the `Context` only
*consumes* them. The workflow layer **forces them into existence and makes them
acute**, but they are implemented **below** it. They are tagged **`[SUBSTRATE]`** at
their section headers and constitute **preparatory work in the lower repos** — to be
built and tested beneath the `Context`, not inside it. The three are:

- the **connected-optional-pin semantics** and the **`null`-as-absence / drop-on-`null`**
  transformation-construction rule (§3) — a `seamless-transformer` tf-construction
  concern;
- the **cancellation substrate** — soft/hard cancel, the awaiter-set holder model, and
  server cancel semantics (§6) — which lives in `seamless-transformer`'s transformation
  cache and the servers; the `Context` only *calls* `softcancel`;
- **`Expression` cancellation** on the byte-moving paths (§9) — a `seamless-core`
  concern.

Everything else — `Context` = DAG, node states/equilibrium, the cascade and
glitch-freedom invariant, speculation *policy*, wiring, `prune`/detach — is genuine
workflow-level logic. (Note the split inside §5/§6: *deciding when to hold* a
superseded run is `Context` policy; the *holding/cancel mechanism* it calls is
`[SUBSTRATE]`.)

## 2. A `Context` is a DAG; builders are views over it

Internally a `Context` holds **only a DAG of nodes** (mirroring legacy Seamless, but
re-derived below from first principles in Part II, not accepted on precedent alone).
`Cell`s and `Transformer`s are **not** stored objects — they are **views over a
node**.

The graph ontology (the original's **F5**, resolved):

- **Nodes** are the context-key-bound builders: `ctx.a`, `ctx.b` — one node per key.
- **Navigation** (`ctx.a.sub`, `ctx.a[i]`, `ctx.a[x:y]`) returns an **ephemeral
  `Cell`**: a transient view that accumulates a path over a node. Navigation does
  **not** grow the DAG.
- **Edges** are created by assignment: `ctx.b = ctx.a.sub` captures `(source-node,
  path, celltypes)` **on the edge** — not as a stored `Expression` object.
- **E/T are private to the `Context`.** On each tick they are *materialized* from
  `(edge path + current upstream checksum)`, fired, and discarded. A `Context`
  **contains** only builders (as node state); it **fires** E/T but never stores them.

### Single source of truth (the original's §11, resolved by F5)

A builder is backed by **exactly one** store, never two:

- An **unbound** builder owns its private state (the functional, standalone
  behavior).
- **Binding is a move, not a copy.** On attach, the builder's private state
  (path / celltype / value-or-edge) migrates *into* the DAG node and the private
  shadow is abandoned; the node is the sole source of truth. On detach, the node's
  state is snapshotted *out* into a fresh standalone builder. There is **no
  dual-write window**, and two handles to the same node key are deliberate aliases.

The functional "build-once" guarantee is a property of the **unbound** builder only;
a bound view is, by design, a live mutable alias of shared node state.

## 3. Node states, connectivity, and equilibrium

### Connectivity (looser than legacy Seamless)  `[SUBSTRATE]`

This subsection is a **transformation-construction** concern, not `Context` logic: it
defines how a `tf_checksum` is built from pins, and lives in `seamless-transformer`.
The `Context` only *relies on* it. It is preparatory substrate work.

- An **unconnected optional** pin is **accepted** and is simply **not part of** the
  transformation — it does not gate the node.
- A **connected optional** pin is treated as **required** (it gates), with one
  escape valve: a transformer may now **return no result**, provided its result
  celltype can encode JSON `null` (`plain` or `mixed`). An optional pin that
  receives that "no result" value is **dropped from the transformation**.
  - **The "no result" value is the canonical checksum of JSON `null`** — a real
    content-addressed value — **not** `result_checksum is None`, which already means
    "not computed." (Conflating the two breaks completion detection.)
  - **By definition, JSON `null` on a connected optional pin *means that pin's
    absence*.** So "pin absent" and "pin present-but-`null`" canonicalize to the
    **same** `tf_checksum` — intended semantics, not an accident. The accepted
    tradeoff: a connected optional pin therefore cannot also carry an *intentional*
    `null` value (see Part II C4 — retracted as a "wart"; recorded as an admitted
    restriction).

So **"sufficiently connected"** = every required pin wired + every connected-optional
pin wired; unconnected optional pins are absent.

### The six node states

The original overloaded "pending"/"running" to name *both* node states *and* E/T run
phases. This pass **renames the node-state axis** so the two never collide (resolving
the original's open §2 bullet 3). E/T runs keep the words **running / superseded /
cancelled / completed**; nodes use:

| state (pass-2 name) | original name | meaning |
|---------------------|---------------|---------|
| `unwired` | `unconnected` | not yet sufficiently connected |
| `blocked` | `upstream` | sufficiently connected, but some upstream is `unwired` or `failed` — blocked, **not itself errored** |
| `waiting` | `pending` | upstream is progressing but not all complete |
| `computing` | `running` | every required + connected-optional upstream is `complete`; this node's own E/T is executing |
| `complete` | `complete` | result checksum available |
| `failed` | `error` | this node's **own** evaluation failed |

Rules:

- A node reaches `computing` iff **all required upstream are `complete`, and every
  connected-optional upstream is either `complete` or definitively empty/`failed`'s
  drop case** — *not* the naive "all upstream complete" (which would wedge a node
  forever behind one errored optional pin).
- **Upstream failure does not propagate as `failed`.** A dependent of a failed node
  is `blocked`, not `failed`. `failed` is reserved for a node's **own** evaluation.
- **The block reason is a first-class, queryable field**, an enum
  `{blocked-by-unwired, blocked-by-error}` (resolving the original's §2 "UX cliff").
  Both block conditions need an *external* change, so they are one *state*; but they
  imply different user actions (wire something vs. fix code), so the *reason* must be
  inspectable by UI and tests.

### Equilibrium vs. out-of-equilibrium (the dynamical picture)

| kind | states | leaves only via |
|------|--------|-----------------|
| **equilibrium** | `complete`, `failed`, `blocked`, `unwired` | an **external change** |
| **out-of-equilibrium** | `waiting`, `computing` | **autonomously** |

This is the **autonomy split**: a `waiting`/`computing` node relaxes toward
equilibrium on its own as upstream computation finishes; an equilibrium node moves
only when the user (or a fix) perturbs it. An external change perturbs; the `Context`
relaxes.

Two consequences used later:

- **Quiescence ⇔ no node is `waiting` or `computing`** (every node in an equilibrium
  state). Within scope (a DAG of reproducible transformations) it is **guaranteed
  reachable** in finite steps after a finite burst of edits. Quiescence is a property
  of node **states** (current results); a `complete` node may still have a
  **superseded** run in flight — obsolete by construction — which does **not** count
  against quiescence. So quiescent ≠ cluster-idle; **`ctx.prune()`** (§5) drops those
  obsolete runs to make the two coincide (Part II C10).
- **Quiescence ≠ success.** Equilibrium includes `failed`/`blocked`/`unwired`.
  *Success* is the stronger condition that all **witness/observable** nodes are
  `complete`.

## 4. Reactive propagation and glitch-freedom

A "change" is an update to a node's value/config/identity or to connectivity. The
cascade rule (the original's **F4**, resolved):

> On any change to a node's **identity or connectivity**, the node re-derives its own
> state. If it **leaves `complete`** (its output checksum changes or becomes
> unavailable), every downstream node **re-derives its own state** — landing in
> `waiting` *or* `blocked` per its full upstream set — **synchronously, before** the
> wavefront recompute is launched.

Two points the blunt "all downstream → pending" rule got wrong:

- **Re-derive, don't force-set.** A multi-input downstream may belong in `blocked`,
  not `waiting` (e.g. it also depends on a `failed` node). Each downstream computes
  its own state against its full upstream set.
- **The trigger is "leaves `complete`," broader than "an input checksum changed."**
  It includes **self-edits** (editing a node's code/load-bearing `meta` changes its
  own `tf_checksum` with no input change) and **disconnection** (a required pin
  removed moves a node `complete → unwired`, and its downstream to `blocked`).

### The glitch-freedom invariant (the original's §12)

> **Invalidation dominates recomputation.** On any change, mark the whole downstream
> cone non-current (revoke it from `complete`) *before* launching the wavefront
> recompute. **Never fire a node on a stale-completed input.**

This is what makes the textbook diamond glitch-free. With `a=1; b=a+1; c=a+b`, when
`a→10` the danger is `c` firing on `a=10` (new) with `b=2` (`b`'s stale-completed
result) → a transient `c=12` corresponding to no consistent state. The invariant
forbids it: the instant `a` changes, `b` and `c` are synchronously revoked to
`waiting`, so `c` cannot fire until `b` recompletes to `11`; then `c` fires `21`. The
only visible effect is an honest `waiting` on `c` during the recompute. Equivalently:
*an input edge always resolves to the upstream's **current** checksum, and a node
with a changed ancestor has **no** current checksum until it recompletes.*

The invariant is load-bearing precisely **because** the launch-immediately /
per-node-async model (§5) is where it is easy to violate. The strict order is **mark
the cone non-current → then build/launch.** The two halves have very different costs:

- **Marking** the downstream cone non-current (flip `complete`/`computing` → `waiting`)
  is **cheap in-process bookkeeping** — state flips, no I/O, no computation. It must
  complete, in one non-yielding pass, *before any descendant is evaluated for firing*
  (otherwise a descendant could be built from a stale-complete input). That ordering is
  the whole requirement.
- **Building/launching** the refreshed E/T is **decoupled and need not be synchronous
  or atomic**: a node only becomes checksum-wired (and thus eligible to fire) once all
  its inputs are current, so glitch-freedom holds for free. Running (checksum-wired) E/T
  are launched **with priority** (latency), bursts capped; pending (future-wired) E/T
  are submitted **lazily**. (See Part II C8 — an earlier "expensive synchronous sweep"
  framing, retracted.)

When a recompute yields the **same** checksum (an inert edit), downstream
re-complete instantly via a content-addressed cache hit — the §5 hold is the
optimization that avoids even the transient `waiting`.

## 5. Speculation: launch immediately, delay cancellation

On a change, for the changed node and everything downstream:

1. **Future-wired E/T are cancelled immediately** — they hold no completed work
   (see §8).
2. **Checksum-wired ("running") E/T are *not* cancelled immediately.** The change may
   be inconsequential (a cosmetic source edit that does not alter the result), so
   cancelling running work — and the downstream work feeding on its already-completed
   checksum — would be wasteful.

The rule for running work is **"relaunch the new run immediately, *and also* retain
the superseded run for a grace period."** Launch is never debounced; only
*cancellation of the old run* is delayed.

The grace period's **goal** is to **prevent running work from being cancelled while
there is still a plausible chance it will be needed after all** — an inconsequential
upstream edit, a reverted edit, or an oscillation.

The driver that organizes the holds is a single content-addressing fact:

> A downstream's `tf_checksum = hash(its own code, its upstream inputs' **output
> checksums**, …)`. So a node's running work survives an upstream edit **iff the
> upstream's *output* is unchanged** — even though the upstream's *code* changed.
> Editing a node's **own** code, by contrast, always changes that node's
> `tf_checksum`, so its own running work is reusable only on a literal revert.

This splits the holds into **three** cases (correcting an earlier two-case
taxonomy):

- **(a) Upstream-confirmation hold — event-driven, the high-value case.** A node `B`
  is `computing` (possibly nearly finished); a changed upstream `A` is recomputing.
  Because `A`'s edit may be inconsequential (a comment / refactor / defensive clause
  that does not change `A`'s output), `B`'s `tf_checksum` may be **unchanged** — in
  which case `B`'s in-flight run is *still the current run*, not a superseded one, and
  killing it would throw away a nearly-finished expensive computation for nothing.
  **Hold `B`'s run until the changed upstream `A` resolves, then compare `A`'s output
  checksum:** if unchanged, **reinstate** `B`'s run (it was never really interrupted);
  if changed, cancel `B` and relaunch. The window is therefore **the time until `A`
  resolves** (an *event*), with a timer only as a backstop for an upstream that never
  resolves. Because the canonical instance is *short `A` → expensive `B`*, the wait is
  short *because `A` is short*; a fixed timer would be wrong precisely when `A` is slow
  (it would expire before `A` confirms, killing `B` at exactly the case the hold
  exists to protect).
- **(b) Self-edit revert hold — fixed window, behavioral.** A node is `computing` and
  its **own** identity (code / load-bearing `meta`) is edited. Its `tf_checksum`
  changes, so the new run is from scratch and the old run is reusable **only if the
  user reverts** to the old identity. This is a behavioral bet on a revert, so a
  **fixed human-timescale window** (seconds) is correct, *independent of the run's own
  runtime*: holding a superseded 2-hour run for ~15 s is worthwhile because a revert
  within those 15 s saves the whole restart. Realized as a **fixed-lifetime** hold —
  hold until a deadline, then release; **no decay curve** (decay is the buffer cache's
  general memory-pressure mechanism; this hold only needs a lifetime). For a very
  expensive run (e.g. GPU) the lifetime shrinks toward zero.
- **(c) Completed-downstream retention — buffer retention, lifetime bounded by the
  same event.** A node `Y` is already `complete` on result `R` when an upstream
  changes. There is no running work to protect — reinstating a *completed* `Y` is a
  **pure cache hit** — so what is held is `Y`'s **output buffer** (and the upstream's
  old output), via a
  [`tempref`](../seamless-core/seamless/caching/buffer_cache.py#L230), so the cache
  hit lands if the upstream re-resolves to the same output. Like (a), the right
  lifetime is **bounded by the upstream event** rather than a blind fixed timer; a
  fixed lifetime is an acceptable approximation only when the upstream is fast.
  Memory pressure may evict the buffer early regardless — the correct compute-vs-memory
  trade-off.

Cases (a) and (c) are the same event-driven downstream hold (hold until the changed
upstream resolves, then compare), distinguished only by whether the downstream is
still `computing` (protect live compute) or already `complete` (retain a buffer).
This is the original's **F1**, now endorsed; see Part II C2/C3.

### Nodes do not "hang on" to completed work

A node need not specially retain *completed* work. Correctness and most of the
performance benefit come from the **content-addressed cache**: if new work turns out
to match previously completed work, the cache yields an instant hit. Retention of
*running* work is different: it is not mere churn-smoothing — by §5 case (a) it is
**load-bearing**, because a single inconsequential edit to a fast upstream must not
abort a nearly-finished expensive downstream whose `tf_checksum` is in fact unchanged.
The cache cannot recover that — once cancelled, an in-flight run's partial progress is
gone.

### Holder policy and bounds

- A node holds **≤1 current** run plus **a small bounded set of superseded
  *in-flight* runs** (cap **≤3**). The cap is on **in-flight** runs only (the
  original's **F3**): when a superseded run **completes**, it **leaves the cap**, and
  its result is retained, if at all, by the normal buffer `tempref` — never by a
  running-work slot. This keeps the §6 membership set strictly about running work.
- When a superseded in-flight run is **evicted** from the set, it is `softcancel`'d
  (§6).
- **Aggregate bound (the original's F2, conceded).** No global budget is needed.
  Only `computing` nodes have running work to supersede, and the *wavefront* of
  actually-running work is bounded by **backend concurrency** (the rest are
  `waiting`/queued). So superseded in-flight runs ≤ **3 × backend-concurrency**,
  independent of DAG size. The residual contention (a node's superseded holds
  occupying a slot another node's *current* run needs) is a corner case of *non-local
  rapid editing of a wide wavefront*; an **optional** preemption nicety (*current
  everywhere preempts superseded anywhere* under saturation) covers it.

### `ctx.prune()` — drop obsolete work on demand

Speculation (the grace-held superseded runs above) means that even when no node is
`pending`/`computing`, **obsolete runs may still be burning cluster slots** until their
hold windows fire — so node-state quiescence (§3) does not by itself imply the cluster
is idle. **`ctx.prune()`** closes that gap: it **`softcancel`s (§6) every obsolete
(superseded / grace-held) running E/T immediately**, leaving only the **current**
wavefront. It is lightweight and **repeatable** — *not* a freeze, *not* a commit. After
`prune`, all running work is current work, so once the wavefront finishes the cluster is
genuinely idle (i.e. *quiescence == idle*). The same call is what fire-and-forget issues
before detaching (§8). (Resolves Part II C10; replaces the rejected "seal.")

## 6. Cancellation substrate: one membership set per dedup site  `[SUBSTRATE]`

Multiple node-bound `Transformer`s (across nodes, or across superseded/current runs,
or across *processes*) may share **one** running `Transformation` (same
`tf_checksum`). A `Context`-initiated cancel must therefore be a **soft** signal, not
an unconditional kill.

The whole substrate is **one uniform pattern**: *a membership set lives wherever
deduplication happens*, and two operations act on it everywhere. There is **no
manually-maintained integer refcount and no `refholding` flag** — the set's
membership **is** the count (this is C1: the awaiter set replaces the hand-rolled
refcount, dissolving the generation-aliasing, incref-on-cache-hit, completion-decref,
and `__del__` hazards by construction).

### Two bookkeeping mechanisms (where the set lives, and what a "member" is)

- **In-process & jobserver — an awaiter set.** A `tf_checksum` maps to the set of
  participants currently awaiting its one running submission.
  - *In-process* (`seamless-transformer`): members are the coroutines suspended on the
    shared submission future
    ([the latch](../seamless-transformer/seamless_transformer/transformation_cache.py#L319));
    a member deregisters in `finally`, so completion, error, and cancellation all
    clean up automatically. A pure cache hit returns immediately and is never a member
    — refcount-neutral for free.
  - *Jobserver*: the **same pattern, an independent instance inside the jobserver** —
    members are the latched *clients/processes*. This is the change that makes the
    **jobserver no longer delete siblings**: a client's cancel removes only that client
    from the server-side set.
- **Dask — a first-runner → latch-on-runner set.** Dask has *obligate* latch-on onto
  a **first-runner**, so instead of a flat awaiter set the daskserver maps the
  first-runner to its **set of latch-on-runners**, and **the first-runner itself is
  registered as a (quasi-)member of that set**. "Quasi" = counted like a member for
  cancellation *and* result delivery, but **not** the lifecycle owner: the **cache/set
  owns the future reference**, so softcancelling the first-runner cannot let Dask
  release the future out from under the surviving latchers.

### Two cancel operations (uniform across all three sites)

- **`softcancel`** = *remove this member from the set; if the set is now empty, cancel
  the underlying run.* Above zero, the run continues for the remaining members; on a
  completed/forgotten checksum it is a no-op.
  - **It is pure deregistration — no signal reaches the member being removed.** The
    member's own coroutine (the awaitable / latch-on-runner) needs *no* cancellation
    signal: soft-cancel is a member *voluntarily leaving* (its owner has stopped wanting
    the result), so the substrate's entire job is to drop the bookkeeping reference. A
    real cancellation signal is delivered **only** when the set empties, and **only to
    the underlying run/executor** — never to the (already-departing) members. So a
    server's whole job on a soft-cancel is `set.discard(member)` + the empty check;
    in-process, an awaiter's `finally` does the same discard (C1).
- **`cancel`** (hard) = *cancel the underlying run/first-runner outright; every member
  (awaiter / latch-on-runner) is signalled and cancelled too* — matching today's
  kill-all
  [`cancel_by_checksum`](../seamless-transformer/seamless_transformer/transformation_cache.py#L348).
  Unlike `softcancel`, this **does** deliver a cancellation signal to the members,
  because they are not leaving voluntarily — the *run* is being declared wrong (see
  Policy).

### Constraints — one load-bearing (the C5 fix), two cheap-or-optional

1. **`[LOAD-BEARING — the C5 fix]` Softness composes across layers — softcancel
   cascades *soft*, never hard.** The "cancel the underlying" in `softcancel` is itself
   a **`softcancel` of the next layer down** when the underlying is a shared remote
   submission: an empty *in-process* set ⇒ *leave the jobserver/dask set* (not kill it).
   A real termination happens **only at the leaf set** — the one co-located with the
   actual executor — when *that* set empties. So a single logical softcancel is
   soft→soft→…→(leaf empty)→kill. If empty-set instead hard-cancelled the remote, the
   local set would merely relocate the unconditional kill one process hop downstream —
   i.e. C5 unfixed. **This alone fixes C5** (it concerns *over*-cancellation; the next
   two do not).
2. **`[OPTIONAL — slot reclamation, not correctness]` Cross-process membership liveness.**
   The in-process set self-cleans via `finally`; a server-side set does not. **But a
   leaked member is benign**: it causes *under*-cancellation, never a peer kill. A
   crashed/disconnected client that never sends `softcancel` does **not** pin the job
   indefinitely — the job simply **runs to completion** (bounded by its own runtime =
   the no-early-cancel baseline), after which the set is forgotten. So liveness is a
   slot-reclamation *optimization*, not a condition for correctness or for C5. Take it
   **for free** where membership is naturally **connection-scoped** (a dropped
   connection auto-removes the member — the cross-process analog of `finally`); do
   **not** build TTL heartbeats merely for this — accept that a crashed holder's job
   completes uncancelled. At most one such job per crashed holder, each bounded by its
   own runtime.
3. **`[HYGIENE]` Per-set atomicity.** "remove last member → empty → cancel" races "a new
   submitter wants to latch." Keep membership-change and empty-check-and-cancel under
   one lock **per set** (in-process
   [`_active_lock`](../seamless-transformer/seamless_transformer/transformation_cache.py#L172);
   the analogous server-side lock). A lost race merely re-submits a fresh run, so it is
   never corrupting — results come from the content-addressed cache, never from the
   set.

### Policy

- **The reactive scheduler uses `softcancel` exclusively** — including for **node
  deletion** — because sibling nodes (in-process) *and* cross-process peers may
  legitimately share a running `tf_checksum`. The reactive loop only ever *loses
  interest*, which is precisely `softcancel`.
- **Hard `cancel` means "this run is *wrong* and must be killed and resubmitted" — and
  its cross-tenant reach is therefore *correct*, not a footgun.** It is not "I lost
  interest" (that is `softcancel`); it is the response to a run computed the wrong way:
  a **wrong dunder envelope** or **wrong hardware**. Because the execution envelope is
  **orthogonal to the `tf_checksum`** (the identity is load-bearing; the envelope is
  not), the *same* `tf_checksum` can be running under the wrong envelope **for every
  latcher at once** — so all of them need it killed and resubmitted under the right
  envelope. Killing every member is exactly right. (This is the deliberate escape hatch
  for the existing `strict_dunder` envelope-contention check in
  [`_active_submissions`](../seamless-transformer/seamless_transformer/transformation_cache.py#L304):
  "already running with a different dunder envelope — cancel before strict
  re-submission.") A wrong *input*, by contrast, is usually a **different**
  `tf_checksum`, unlikely to be shared cross-tenant, so `softcancel` (just leave — and,
  being the only holder, cancel) usually suffices there; hard `cancel` is mainly for the
  orthogonal-envelope/hardware case.
- The caller never manages server-side membership directly; it only `softcancel`s its
  own participation. **Each site decides when to actually kill, by its own set.**

Expressions participate in the **same** substrate — see §9.

> **Scope reversal (settles the original's §10a).** This **fixes** the jobserver
> multi-tenant footgun rather than admitting it — at the cost of giving the jobserver a
> server-side membership set, reversing the "intentionally simple jobserver, no
> server-side refcount" decision. The daskserver's previously-"aspirational" latch-aware
> cancel (§8/§10b) is now simply **one instance of this one pattern**, not a separate
> asymmetry. The cost is modest — the set itself, *not* a liveness mechanism (constraint
> 2: a leaked member is benign, the job just completes) — and it removes a cross-tenant
> data-loss hazard, which is worth it.

## 7. Future-wired vs. checksum-wired E/T

- A **`waiting`** node owns a **future-wired** E/T: its inputs are upstream futures,
  not yet resolved checksums. It is keyed by its *upstream's* identity, so it can
  **never** produce a cache entry under its own identity. It is really a **registered
  continuation**, not a cacheable definition (the original's **F7**) — which both
  reassures (it cannot pollute the cache) and confirms it carries no caching value.
- A **`computing`** node owns a **checksum-wired** ("running") E/T: a concrete E/T
  whose inputs are resolved checksums and which therefore has a constructed
  `tf_checksum`. At `waiting → computing` the checksum-wired E/T **replaces** the
  future-wired one (which is cancelled).

**Phasing (the original's §10, confirmed as sequencing only).** Future-wired E/T's
sole present benefit (a few seconds of latency) is not worth its complexity on its
own. It is **necessary** for headless frontier advance (§8) — it is the Dask-future
encoding of the `waiting` cone. So: **ship the reactive `Context` checksum-wired
first** (a node leaves `waiting` for `computing` exactly when its inputs are concrete
checksums), and introduce future-wiring **with** the fire-and-forget milestone, where
it earns its keep. This shrinks the v1 state machine and removes a whole cancellation
path from v1.

### `[OPEN — to be discussed later]` Dependency declaration into `Context`-held nodes

How a dependency on a `Context`-held node is **declared, captured, and resolved** is
flagged here and **deferred**. The capture shape below is the likely-settled part; the
**contract** at the end is what must be worked out later.

**Capture — does not depend on view identity.** Declaring a dependency on a node (e.g.
`ctx.b = ctx.a.sub`) does **not** rely on the identity of the transient navigation view.
`ctx.a is ctx.a` may be `False` (ephemeral views, see C9) and **that is harmless** — a
`Context` weak-value cache of active `Cell` views *could* stabilize it, but is most
likely **unnecessary**, because the dependency is captured by *content*, not by object
identity:

- **`Context`-bound** `Transformer`/`Cell`: the dependency is written **immediately into
  the `Context`-held DAG as a nodepath edge** `(source-node-ref, path, celltypes)`, which
  **becomes an `Expression` as soon as the consuming node goes `pending`/`computing`**
  (the F5 / §7 per-tick materialization).
- **Non-`Context`-bound** `Transformer`/`Cell`: the dependency can be **stored verbatim**
  (the reference as given) and **resolves to an `Expression` as soon as the
  `Transformer` becomes a `Transformation`** (at build time).

**Contract — to settle later.** When the edge's `Expression` materializes, its **input
checksum** is in one of two regimes, and each needs a defined contract:

- **input checksum already known → checksum-wired** `Expression`;
- **input checksum not yet known → future-wired** `Expression` (the upstream is still
  pending).

The precise contract for each — resolution, identity/caching, and the
**checksum-wired ↔ future-wired** transition — is the open item. It is the §7
future-wired/checksum-wired split applied specifically to *declared dependency edges*,
and it governs how navigation-derived dependencies cache, fire, and reattach.

## 8. Fire-and-forget: `prune` then detach (no "seal")

Fire-and-forget tears down the `Context` process while Dask keeps advancing the
workflow headlessly. The original design gated this behind a heavy **seal/commit** step
that collapsed speculation, compiled the forward cone, **and froze the graph** (the
original's **F6**). **That "seal" feature is rejected** — too heavy-handed, and no
freeze is wanted. Fire-and-forget is instead just two lightweight, already-available
actions:

1. **`ctx.prune()`** — softcancel all obsolete (superseded / grace-held) running work,
   leaving exactly the **current wavefront** running plus the **future-wired forward
   cone** (the `waiting` nodes' E/T, already submitted to Dask as futures during normal
   lazy operation — §4/§7). This is the **same** `prune` that makes quiescent ==
   cluster-idle (C10); fire-and-forget just calls it before letting go, so there is no
   "messy state to collapse" and no adjudicator needed.
2. **Detach** — the `Context` process lets go. The current wavefront and the
   future-wired cone are **already** running on Dask (remote-by-checksum, against the
   shared hashserver — C7), so they advance `waiting → computing → complete`
   headlessly by Dask dataflow.

**No freeze.** "No external edits during fire-and-forget" is a **consequence of
detaching** (the reactive process is simply gone), **not an imposed mechanic**. The
**entire reactive apparatus** (the §4 cascade, the §5 holds, supersession, invalidation)
is **online-only** and ceases to exist on detach — which is exactly why headless advance
needs only the **autonomous** transitions Dask provides natively.

Bounds (the in-scope headless-advance analysis, now without a seal):

- **Forward-only.** Only autonomous `waiting → computing → complete` transitions occur
  headlessly; nothing reactive.
- **Blocked branches stay blocked.** `failed`/`blocked` nodes never resolve headlessly
  (their input futures never arrive) — correct, since they need intervention that
  cannot happen headless. On reattach they are still blocked.
- **No special case in tf-construction timing.** It follows the wiring: **eager at
  submission** for a checksum-wired node (the wavefront, all input checksums in hand),
  **deferred to runtime** for a future-wired node (the pending cone, some input still
  a future). The connected-optional drop-if-`null` rule (§3) is **one rule within
  tf-construction**, applied whenever construction happens. The cone advances
  **uniformly**.

## 9. Expressions are cancelable — but only on the byte-moving paths  `[SUBSTRATE]`

The functional-substrate plan said an expression is "not separately cancellable." That
is **half right and must be amended**:

- The **codebook application** (get-attr / get-item / slice / convert) is zero-cost
  and uncancelable.
- The **buffer I/O envelope** around it — fingertip/materialize a large input,
  serialize/write a large output — is neither instantaneous nor uninterruptible.

So **an `Expression` exposes a cancellation surface iff it must move bytes.** The
deep-checksum fast path (navigate the Merkle manifest, never materialize the parent)
genuinely has nothing to interrupt and stays uncancelable. On the materialize-and-apply
and write paths, `Expression.cancel()`/`softcancel()` interrupts the **I/O**, not the
op, and participates in the **same** §6 refcount layer (input materialization and
output writing share the one running-checksum refcount; I/O is not a separate layer).

> **Implementation note.** This requires replacing the
> [`NotImplementedError`](../seamless-core/seamless/expression_class.py#L222) stub and
> amending the plan's "not separately cancellable" sentence.

## 10. Scope, assumptions, and admitted trade-offs

**Determinism is assumed.** The retain-and-compare loop (§5) assumes *same input ⇒
same result checksum*. **Irreproducible transformations are out of scope for
workflows.** Irreproducibility is not a declared property but an imperative post-hoc
"undo": the `"irreproducible"` request
([database.py:947](../seamless-database/database.py#L947)) records an
`IrreproducibleTransformation` marker and **deletes** the forward, reverse, and
metadata rows — dropping the cache *mapping* but not the result *buffer*. The correct
response is **to pin that buffer** (do not evict it, so the result stays
materializable). *Accidental* nondeterminism is equally out of scope and, crucially,
**masked by the content-addressed cache by default** — it surfaces only in consumers of
a nondeterministic result that is `scratch` (forcing recomputation). See Part II C6
(retracted) for why this is a universal Seamless property, not a `Context` hazard.

**Expressions are deterministic by construction**, so the retain-and-compare is
**unconditionally safe on expression edges** — the hazard above cannot arise there.

**Resolved (was an admitted footgun):**

- **§10a — jobserver multi-tenant cancel — now FIXED, not admitted.** The §6 uniform
  membership-set model gives the **jobserver its own server-side client-latch set**, so
  evicting a superseded run no longer kills a cross-process peer: a client's
  `softcancel` only deregisters that client, and the job is killed only when the
  server-side set empties. This **reverses** the "intentionally simple jobserver"
  decision — but the cost is just the set; **no liveness mechanism is required** (§6
  constraint 2: a leaked member from a crashed client is benign — the job runs to
  completion, never killing a peer). The previous *grace-on-cancel* idea is moot.
- **§10b — daskserver latch-aware cancel — now one instance of the §6 pattern.** It is
  still net-new work (a scheduler-side latch set + a client-side
  [`_transformation_cache`](../seamless-dask/seamless_dask/client.py#L1212) that maps
  many in-process holders to one submission), but it is no longer a *separate*
  asymmetry — it is the same membership-set + `softcancel`/`cancel` as everywhere else.

**Admitted trade-offs** (stated, not silently accepted):

- **§10c — connected-optional pins lose laziness** (F7). Because a connected optional
  pin is treated as required and the upstream may legitimately return `null`, the
  upstream **always runs**, even when its `null` is then dropped. "Optional" means
  "may be absent **or** `null`, but if connected, always computed" — the opposite of
  the intuitive reading.

**Open at this layer** (the plan lists them; out of scope until the relevant phase):
intra-context **cycles** (the §4 cascade assumes a DAG; cycles need
termination/cycle handling), (de)serialization of a `Context` graph, the precise
witness/observable-output surface, and the **dependency-declaration contract**
(checksum-wired vs future-wired `Expression` for a declared edge — see the §7 open
point `[OPEN — to be discussed later]`).

---

# Part II — Fresh first-principles critique

The synthesized design above is internally coherent and the in-process-only refcount
is the right backbone. The points below are **new** — they were not raised (or not
resolved this way) in the original. Ordered by leverage.

> **Revision note.** C1 (awaiter-set) is accepted. C2 originally proposed *deferring*
> the grace-hold out of v1; that is **retracted** — a short-upstream / long-downstream
> inconsequential edit makes the hold load-bearing — and C2 now keeps the hold while
> showing it composes with C1 as a "speculative awaiter." C3 originally called F1's
> event-driven downstream hold over-engineered; that is **conceded** — F1 is endorsed.
> C4 originally called the null-as-absence rule a "wart"; that is **retracted** — it is
> the intended encoding and an admitted restriction. C5 is **resolved** (the §6
> membership-set model makes softcancel transitive). C6 is **retracted** (accidental
> nondeterminism is a universal Seamless property masked by the cache, not a `Context`
> hazard). C7 is **retracted** (shared persistent storage is intrinsic to
> remote-by-checksum execution, not a missing fire-and-forget precondition). C8 is **retracted**
> (glitch-freedom needs only cheap cone-marking + mark-before-fire ordering, not an
> expensive synchronous *submission*; submission is decoupled, lazy, and prioritized).
> C9 is **retracted** (its
> "functional value vs. mutable alias" premise is wrong — `Cell`/`Transformer` are
> uniformly mutable; bound = view, unbound = private state). C10 is **valid and
> resolved** by an API (`ctx.prune()`, Part I §5) — the heavy "seal" is rejected in
> favor of it. So of the ten, only **C1** stands as an adopted improvement; the rest are
> resolved, retracted, or conceded. Items that live **below** the
> `Context` are tagged `[SUBSTRATE]`
> (see §1): the null rule (C4 / §3) and the cancellation substrate (§6, behind C1).

## C1 — Replace the manual running-work refcount with the latch's *awaiter set*  `[SUBSTRATE]`

> This is a proposal about the **cancellation substrate** (§6), which lives in
> `seamless-transformer`, not in the `Context`. It is preparatory work the workflow
> layer makes acute (reactive supersession needs *soft* cancel), but it is built and
> tested below the `Context`. See §1.

**The single highest-leverage change.** Sections §3/§4/§6 spend enormous effort on a
manually-maintained integer refcount keyed by `tf_checksum`: the `refholding` flag, the
"completion decrefs too" special case, the "no incref on cache hit" rule, the
single-choke-point requirement, the cross-generation aliasing hazard, the single-lock
atomicity patch, and the `__del__` backstop. **Every one of these is a symptom of
maintaining a count that is already derivable.**

Look at the existing code. The latch is one `_ActiveSubmission` per `tf_checksum`
holding one `concurrent.futures.Future`; the owner runs the work, and non-owners do
`await asyncio.wrap_future(active.future)`
([transformation_cache.py:319](../seamless-transformer/seamless_transformer/transformation_cache.py#L319)).
**The set of coroutines currently suspended on that future *is* the holder set.** The
refcount is exactly `len(awaiters)`. There is no need to track it by hand.

The structured-concurrency form:

- The actual execution is a **detached background task** owned by the cache, not by
  the first caller. **Every** participant — including the first — is a mere awaiter.
- A participant registers an awaiter on entry and deregisters in `finally` (covering
  normal completion, exception, *and* task cancellation — which is what makes the
  `Context`'s `softcancel` "just cancel my await").
- When the awaiter set **empties**, the cache cancels the background task. That **is**
  `softcancel`-at-zero, for free.

What this dissolves, by construction rather than by patch:

- **The aliasing hazard (§4) vanishes.** Each generation is a *different future
  object* (the cache already pops the old `_ActiveSubmission` and installs a new one
  when the old future is done — see
  [transformation_cache.py:300](../seamless-transformer/seamless_transformer/transformation_cache.py#L300)).
  Awaiters of generation N await a different object than generation N+1; there is no
  shared integer to mis-target. The author's §4 "downgrade to bounded re-work" is then
  unnecessary — the re-work cannot happen.
- **"No incref on cache hit" (§3 residual a) is automatic.** A cache hit returns
  immediately and never registers an awaiter on a *running* future. Refcount-neutral
  by definition.
- **"Completion decrefs too" (§3) is automatic.** The owner-task's awaiters wake on
  completion and deregister in `finally`.
- **The `__del__` backstop (§3 residual) is automatic.** A GC'd/cancelled holder's
  coroutine is cancelled by the event loop, hits `finally`, deregisters. No explicit
  `__del__` needed.

The one real change required is **decoupling execution from the first caller**: today
the owner *is* the executor, so cancelling the first caller kills the work for
everyone. That coupling is exactly wrong for soft-cancel and should be fixed
regardless. I recommend Part I §6 be re-specified in these terms; the `refholding`
flag and generation key become unnecessary.

## C2 — Keep the grace-hold (retracted: deferring it is wrong), but express it as a C1 speculative awaiter

> **Retracted.** I originally proposed shipping v1 with *cancel-on-supersede
> immediately* and deferring the grace-hold as a profile-it-later optimization. That
> is **wrong**, because it discards the hold's highest-value case (Part I §5 case (a),
> now corrected): a short upstream `A` feeding a long, nearly-finished downstream `B`,
> where an **inconsequential edit to `A`** (a comment / refactor / defensive clause)
> leaves `A`'s *output* unchanged and therefore `B`'s `tf_checksum` **unchanged** —
> so `B`'s in-flight run is *still the current run*. Cancel-on-supersede kills `B` and
> restarts an expensive nearly-finished computation for nothing. Inconsequential
> upstream edits are routine and the protected work can be arbitrarily expensive, so
> this is neither narrow nor a revert bet. The grace-hold is **load-bearing, not a
> deferrable optimization.**

What survives is the *decomposition*, which C1 makes clean rather than something to
defer. There are two genuinely different concerns:

1. **Sibling-sharing cancellation** (don't kill a running `tf_checksum` while another
   *current* node still wants it). Correctness; it is exactly the C1 awaiter set —
   instantaneous, not a timed hold.
2. **The grace-hold** (keep a run alive while it might still be current/needed). This
   is naturally expressed *in the same C1 model*: the `Context` registers a
   **speculative awaiter** on the run for the hold's duration, and deregisters it when
   the hold ends. When *all* awaiters drop — the real consumers *and* the speculative
   one — the run cancels. There is no separate refcount, holder flag, or generation
   key: the holder cap (≤3) is just "the `Context` keeps at most 3 speculative
   awaiters per node," and `softcancel` is "drop my (speculative) await."

So C1 and the grace-hold compose: accepting C1 does **not** require deferring the
hold; it makes the hold *cheaper to implement*. The §3/§4 machinery I wanted to defer
(the `refholding` flag, the generation key, the manual integer) is removed by C1 — but
the **behavior** (hold superseded/uncertain runs) stays, because §5 case (a) demands
it.

## C3 — Conceded: the downstream hold must be event-driven (F1 was right); I over-rotated on buffer retention

> **Conceded.** I argued F1's *event-driven, dependency-aware* downstream hold was
> over-engineered and that a fixed-lifetime buffer `tempref` suffices. The §5 case (a)
> correction shows that is wrong in the case that matters.

The flaw in my original reasoning was treating the downstream as **already
`complete`** (a pure buffer-retention question). When the downstream `B` is still
**`computing`**, there is *live, possibly-nearly-finished compute* at stake, and the
decision to keep or kill it depends on an **event** — whether the changed upstream
`A` re-resolves to the same output — not on a clock. A fixed timer fails exactly when
`A` is slow: it expires before `A` confirms, killing `B` at the worst moment. So the
hold must be **event-driven**: hold `B` until `A` resolves, then compare `A`'s output
and reinstate-or-cancel.

What survives of the original C3 is **only the completed-downstream sub-case** (Part I
§5 case (c)): when `B` is already `complete`, reinstatement is a pure cache hit, so
what is held is the *buffer*, and (i) the lifetime is still best **bounded by the same
upstream event** (a fixed timer is merely an acceptable approximation when `A` is
fast), and (ii) **memory pressure may override** and evict early — the correct
compute-vs-memory trade-off. The bookkeeping I dismissed ("which upstream is `B`
waiting on") is **not** extra cost: the `Context` already holds that DAG edge, so the
event trigger is free.

Net: **endorse F1.** Cases (a) and (c) in §5 are one event-driven downstream hold,
split by whether the downstream is `computing` (protect compute) or `complete` (retain
a buffer). Case (b), the self-edit revert, keeps its fixed window because no upstream
event governs it.

## C4 — `[SUBSTRATE]` `[RETRACTED → admitted restriction]` null-as-absence on connected optional pins

> **Retracted as a criticism.** I framed "pin absent ≡ pin present-but-`null`" as a
> *wart* — a conflation of a real value with absence. That misreads the contract: on a
> connected optional pin, **JSON `null` *is* the defined encoding of that pin's
> absence**. There is nothing to conflate; the convergence to one `tf_checksum` is the
> *intended* meaning, not an accident.

What remains is the **accepted restriction** (already acknowledged in §3 / the
original's F7): a connected optional pin cannot *also* carry an intentional `null`
*value* distinct from "absent," because `null` is spoken-for. That is a real tradeoff,
recorded — but it is a deliberate one, not a defect, and there is no fix to propose
because the alternative (pass `null` through as a value) would simply contradict the
chosen semantics.

This is also **`[SUBSTRATE]`, not a `Context` concern**: the rule lives in
`seamless-transformer`'s transformation construction (§3 connectivity), surfaced and
made acute by the workflow layer (reactive re-firing across changing connectivity) but
implemented and tested **below** the `Context`. It is preparatory work, listed as such
in §1.

## C5 — `[RESOLVED → §6]` `softcancel` is now transitive across the jobserver boundary

> **Resolved.** I originally framed this as an *admitted* footgun: softcancel composes
> within a process but not across a shared jobserver, which kills peers
> unconditionally — so "softness is not transitive across the jobserver boundary." The
> §6 **uniform membership-set model** (a set wherever dedup happens; softcancel =
> deregister, real kill only on empty) makes softness **transitive**. The fix rests on
> **one** load-bearing condition (§6 constraint 1):
>
> - **Softness must cascade *soft* down the layers.** An empty in-process set must
>   *deregister from* the jobserver/dask set, never hard-cancel it; a real kill happens
>   only at the **leaf** set (co-located with the executor) when it empties. Otherwise
>   the local set merely relocates the unconditional kill one hop downstream — C5
>   unfixed.
>
> I originally also billed **cross-process liveness** as a second load-bearing
> condition — wrong. A leaked member (crashed client) causes only *under*-cancellation:
> the job **runs to completion** (the no-early-cancel baseline) and is then forgotten;
> no peer is ever killed. So liveness is an **optional** slot-reclamation nicety (free
> where membership is connection-scoped), not part of the C5 fix (§6 constraint 2).
>
> The price is reversing "intentionally simple jobserver": the jobserver gains a
> server-side membership set (no liveness needed). Worth it — it removes a cross-tenant
> **data-loss** hazard. Hard `cancel` (kill-all) stays deliberately cross-tenant — and
> that is *correct*: it means "this run is wrong (wrong envelope/hardware)," which,
> since the envelope is orthogonal to the `tf_checksum`, is wrong for every latcher at
> once (see §6 Policy). The reactive loop never issues it (it only loses interest →
> `softcancel`).

## C6 — `[RETRACTED]` Accidental nondeterminism is a universal Seamless property, not a `Context` hazard

> **Retracted.** I claimed the `Context`'s retain-and-compare is specially *endangered*
> by accidental nondeterminism (wall-clock reads, unordered-set hashing, non-associative
> float reductions, races) and should "degrade gracefully." That over-attributes the
> problem to the `Context`. The correct picture (author):

**By default Seamless does not even *notice* accidental nondeterminism — it is masked
by the content-addressed cache.** A transformation is computed once under its
`tf_checksum` and the result is cached by that key; a second request is a **cache hit**,
so the code never re-runs and the divergence is never observed. The only place it
surfaces is in **consumers of a nondeterministic result that is `scratch`**: a scratch
result is not durably stored, so a consumer must **recompute** the producer (via input
fingertipping), and *that* recomputation can yield a different checksum — breaking the
consumer's input identity. This is **universal in Seamless**, independent of the
`Context`.

Why this defuses the original C6: the `Context`'s grace-hold does **not** do "recompute
the same `tf_checksum` and compare." Its event-driven upstream-confirmation hold (§5
case (a)) compares the outputs of **two different** upstream identities (the old code
`X` vs. the inconsequentially-edited code `X'`), which is well-defined per key — no
same-key recomputation, no determinism assumption beyond what content-addressing already
requires. So there is no `Context`-specific resource-waste to "degrade gracefully"
against; the universal scratch-producer caveat already covers it, and §10's
determinism scoping stands.

> **Verification of the author's "well-documented in the agentic docs" claim — partial.**
> The *constituent facts* are well-documented, but the *combined property* is **not
> stated explicitly** and must be assembled:
> - cache reuse means no re-execution —
>   [`identity-and-caching.md`](docs/agent/contracts/identity-and-caching.md) ("reused
>   without re-executing code"); auditing requires *deliberately forcing* a recompute
>   ([`scratch-witness-audit.md` §Auditing](docs/agent/contracts/scratch-witness-audit.md)),
>   which *implies* the cache otherwise masks divergence;
> - scratch results are recomputed at the consumer —
>   [`scratch-witness-audit.md`](docs/agent/contracts/scratch-witness-audit.md),
>   [`cache-storage-and-limits.md`](docs/agent/contracts/cache-storage-and-limits.md),
>   [`seamless-run-and-argtyping.md`](docs/agent/contracts/seamless-run-and-argtyping.md);
> - a `result_checksum` mismatch for one `tf_checksum` is the referential-transparency
>   violation / `IrreproducibleTransformation`
>   ([`execution-records.md`](docs/agent/contracts/execution-records.md)).
>
> The masking property is stated outright only for a *different* cause —
> [`compiled-transformers.md`](docs/agent/contracts/compiled-transformers.md) ("the
> runtime will not detect violations … silently incorrect caching") — and the scratch
> docs actually *assume the producer is deterministic*. So the exact framing — *the
> cache hides accidental nondeterminism; `scratch`-consumption is its sole surfacing
> channel* — is **derivable but not written down as a named property**. Minor doc gap:
> one sentence in `scratch-witness-audit.md` or `identity-and-caching.md` would make it
> explicit.

## C7 — `[RETRACTED]` Shared persistent storage is intrinsic to remote-by-checksum, not a missing precondition

> **Retracted.** I claimed §8 *omits* a precondition — that headless results must land
> in shared storage rather than the torn-down process's memory. That precondition is not
> missing; it is **structural to how Seamless does remote execution at all** (author):

**All remote job submission in Seamless is *by checksum*.** A remote backend (jobserver
or daskserver) is handed input *checksums* and materializes the input buffers
**server-side from the shared hashserver**; it writes produced (non-`scratch`) results
**back to that shared hashserver**. So a fire-and-forget hand-off to Dask **already**
runs against shared persistent storage — there is no mode in which a remote job's
results live only in the detached `Context` process's memory. Tearing the process down
therefore loses nothing durable:

- The §5 temprefs and in-process buffers that die with the process held only
  **speculative/superseded** work, which **`ctx.prune()` cancels anyway** before detach
  (§8).
- The headless cone's results are pushed to the hashserver as each task completes, by
  the normal remote-execution path.
- Inputs need not even be uploaded at submission: they may be **pre-present** — from a
  prior upload, or **by design**, when the client holds the checksum of a large
  server-side dataset.

The only non-persisted values are `scratch` intermediates — but those are *recomputable*
by construction, and the meaning-bearing/witness outputs the user actually wants from a
headless run **must be non-`scratch`** anyway (the existing witness-output discipline).
So even the residual reduces to an existing Seamless rule, not a new fire-and-forget
precondition.

> **Verification of doc coverage — partial, and a more significant gap than C6.** The
> *constituent facts* are documented: a cluster "specifies where buffers are stored
> (hashserver), where results are recorded (database)…" and remote execution "expects a
> jobserver or daskserver" while "using the cluster's hashserver and database for
> persistent storage"
> ([`cluster.md`](docs/main/cluster.md)); remote setups store bytes "in dedicated
> services (hashserver/database), and the local process may push buffers it produces
> (unless scratch) / fetch buffers it needs"
> ([`cache-storage-and-limits.md`](docs/agent/contracts/cache-storage-and-limits.md));
> HPC uploads inputs automatically and `--write-remote-job` "must stage the input
> buffers on the remote hashserver"
> ([`hpc.md`](docs/main/hpc.md),
> [`seamless-run-and-argtyping.md`](docs/agent/contracts/seamless-run-and-argtyping.md));
> materialization config is fine "as long as the checksum of each artifact is passed as
> explicit argument"
> ([`content-addressed-files-and-dirs.md`](docs/agent/contracts/content-addressed-files-and-dirs.md),
> the pre-present-input case). **But** the crisp invariant — *remote submission is
> by-checksum, therefore a shared hashserver is a hard prerequisite for server-side
> input materialization, for **both** backends* — is stated only piecemeal and hedged
> ("typically"), and is **absent from
> [`execution-backends.md`](docs/agent/contracts/execution-backends.md)**, the contract
> page that defines the remote-execution operational model and is exactly where it
> belongs. The author's "less certain of doc coverage" instinct is right: this is a
> real gap — `execution-backends.md` should state the shared-hashserver prerequisite and
> the by-checksum input/result flow outright.

## C8 — `[RETRACTED]` Glitch-freedom needs cheap marking + ordering, not an expensive synchronous *submission*

> **Retracted.** I claimed glitch-freedom imposes an "O(cone) synchronous sweep per
> edit" as "the real cost," conflating two operations that should be separated (author):

The `Context` holds, per node, a running (checksum-wired) E/T and at most one pending
(future-wired) E/T; a reactive change **refreshes** this E/T set. There is **no
requirement that the refresh/submission be atomic or synchronous.** The two operations:

- **Invalidation (mark the cone non-current).** Cheap **in-process bookkeeping** —
  flipping node states, no I/O, no compute. O(cone), but each step is a pointer/enum
  flip; for a scrub over a huge cone it is negligible (and amortizes, since most of the
  cone is already `waiting` from the previous tick). The *only* real rule is **ordering**:
  this pass must precede any descendant being evaluated for firing, in one non-yielding
  pass — which is automatic, since there is nothing to `await` while flipping states.
  This is also the answer to my old "cannot touch remote state" caution: marking is
  *inherently* local, so the caution is trivially met.
- **Submission (build + launch the E/T).** **Decoupled, lazy, prioritized — not
  synchronous:**
  - **Running (checksum-wired) E/T** (all inputs are current concrete checksums) launch
    **with priority** to cut latency; edit **bursts can be capped/rate-limited** without
    harming correctness.
  - **Pending (future-wired) E/T** (some input still non-current) are submitted **at
    leisure** — they will not fire within seconds unless a dependency is very fast.

Glitch-freedom falls out **for free**, with no synchronous submission: a node becomes
checksum-wired (eligible to fire) **only once all its inputs are current concrete
checksums**, so while `b` is pending, `c` stays pending too and **never** builds the
`c = 12` glitch — regardless of *when* `c`'s E/T is (lazily) rebuilt. The marking is
what makes `b` visible as pending to `c`; the submission timing is then irrelevant to
correctness. So there is no "cost of glitch-freedom" beyond the cheap mark-before-fire
ordering already in §4 — the substantive claim of the old C8 is withdrawn.

## C9 — `[RETRACTED]` "dual-mode `Cell`/`Transformer`" — wrong premise; they are uniformly mutable

> **Retracted.** I claimed a single class is a "functional build-once **value**" when
> standalone and a "live mutable shared alias" when bound — a dual-semantics tension.
> That premise is **wrong**, as the shipped code shows:
> [`Cell`](../seamless-core/seamless/cell_class.py#L55) is **fully mutable standalone**
> — it has setters for `input_ref`, `path`, `celltype`, `target_celltype`, `validator`.
> The "build-once / functional" guarantee belongs to the **`Expression`** that `build()`
> snapshots out (a later `Cell` mutation cannot reach into an already-built
> `Expression`), **not** to the `Cell`. So there is no value-vs-alias seam:

`Cell`/`Transformer` are **uniformly mutable in both modes** (the author's framing).
The only difference is **where the mutable state lives**:

- **Bound** → the builder is a **view** over the DAG node; mutations go to the node.
- **Unbound** → the builder holds its **own private state**.

This is one coherent thing (a mutable builder with a relocatable backing store), not
two semantics bolted together. My two "bugs at the seam" dissolve: a `ctx.a` reference
outliving a detach is the ordinary **view-lifetime** question of *any* view-over-store
API (handled by the §2 attach/detach migration), and `ctx.a is ctx.a` is the ordinary
property-accessor identity question (a free choice — return a stable handle or
materialize on demand), not an incoherence. The `ctx.a is ctx.a == False` case is in
fact harmless and likely needs no fix, because dependency declaration is captured by
*content* (a nodepath edge / verbatim ref → `Expression`), not by view identity — see
the marked open point **"Dependency declaration into `Context`-held nodes"** (§7), whose
**contract** (checksum-wired vs future-wired) is deferred.

The one substantive requirement — **single source of truth across attach/detach (no
dual-write window)** — is real, but it is the original's **§11**, already stated in
Part I §2 ("binding is a move, not a copy"). C9 added only a mistaken "code smell"
framing on top of it; withdrawn. (A distinct `ContextCell` type remains an *option* for
implementation taste, but it is not *needed* to resolve a non-existent tension.)

## C10 — `[RESOLVED → `ctx.prune()`]` "Quiescent" (node states) ≠ "cluster idle"; an API closes the gap

§3 defines quiescence purely on node states, deliberately ignoring superseded runs
still in flight. That is the right definition for *settledness of results*, but it
means a `Context` can report "quiescent" while superseded (obsolete) runs still burn
cluster slots until their grace windows fire. Because the grace-hold is **kept** (C2),
this gap is **real and permanent** — superseded runs can outlive node-state quiescence
by their hold window. So the critique stands, and it needs an **API**, not a redefinition
of quiescence.

> **Resolution — `ctx.prune()`.** A `Context` method that **softcancels all obsolete
> (superseded / grace-held) running work right now**, leaving only the current
> wavefront. It is **lightweight and repeatable** — *not* a freeze, *not* a commit,
> *not* the rejected "seal." After `prune`, all running work is *current* work, so
> **node-state quiescence coincides with cluster-idle** (when the current wavefront also
> finishes, the cluster is genuinely idle). It is the same operation fire-and-forget
> calls before detaching (§8).

Consequence for tests/tools: a caller that wants "settled **and** idle" calls
`ctx.prune()` (then waits for quiescence); a caller measuring resource use must
otherwise not assume node-state quiescence means the cluster is idle. The distinction is
**surfaced as an API affordance**, not papered over.

## Minor

- **Per-tick E/T materialization cost.** §2 materializes E/T per tick. The cost is
  bounded to the *invalidated cone* (only there do inputs change), and is a small
  `tf_checksum` hash over checksum-sized inputs, not buffers — cheap. Worth a sentence
  so it is not mistaken for a whole-graph rehash.
- **View identity.** Ephemeral builders mean `ctx.a is ctx.a` is `False` and
  `id()`-based caches over views break. Document that node identity is the *key*, not
  the view object.

---

# Part III — Unrebutted criticisms carried forward from the original

These are the items the original document left **open** (its "Still to fix" set and
the residuals under otherwise-resolved points). They are recorded here so nothing is
lost; where Part I or Part II takes a position, it is noted.

**Resolved in this pass (position taken):**

- **§2 bullet 3 — overloaded "running"/"pending" terminology.** Resolved in Part I §3
  by renaming the node-state axis (`unwired / blocked / waiting / computing / complete
  / failed`) and reserving running/superseded/cancelled/completed for E/T runs. A
  mapping table to the original names is included.
- **§11 — single-source-of-truth attach/detach.** Resolved in Part I §2 ("binding is a
  move, no dual-write"), gated on F5. (Part II C9, which added a "dual-mode incoherence"
  framing, is **retracted** — `Cell`/`Transformer` are uniformly mutable; the only
  difference bound vs unbound is *where the state lives*, not its semantics.)

**Carried forward as still-to-fix (the original never closed these; Part II proposes
how):**

- **F1 — split the holds.** Resolved into the **three-case** taxonomy of Part I §5
  (event-driven upstream-confirmation; fixed-window self-edit revert; completed-
  downstream buffer retention). Part II C3 **endorses** F1's event-driven downstream
  hold (an earlier C3 that called it over-engineered is retracted).
- **F3 — the ≤3 cap applies to in-flight runs only.** Folded into Part I §5; kept (the
  grace-hold is kept, per C2).
- **F6 — fire-and-forget.** The original's heavy **"seal"/commit/freeze** is
  **rejected**. Fire-and-forget is now **`ctx.prune()` + detach** (Part I §8): `prune`
  drops obsolete speculation, the already-future-wired forward cone continues on Dask, no
  freeze. Part II C7 (retracted) confirms no extra out-of-process-persistence
  precondition (remote-by-checksum is already shared-hashserver-backed).

**Carried forward as residual sub-points (under otherwise-resolved items):**

- **§2 — `null`-checksum representation for "no result"** (must be the canonical
  checksum of JSON `null`, never `result_checksum is None`). Folded into Part I §3
  (a `[SUBSTRATE]` rule). Part II C4 (retracted as a "wart") records the accepted
  restriction: a connected optional pin cannot carry an intentional `null` value.
- **§2 — queryable block-reason** (`blocked-by-unwired` vs `blocked-by-error`). Folded
  into Part I §3 as a first-class enum field.
- **§3 — no incref on a pure cache hit; incref at the single submission choke point;
  `__del__ → softcancel` backstop.** Folded into Part I §6; Part II C1 makes all three
  automatic by switching to the awaiter-set model.
- **§4 — single-lock atomicity for incref+latch / decref-to-zero+cancel+pop.** Folded
  into Part I §6; rendered unnecessary by Part II C1 (distinct future objects per
  generation).
- **§13 — reactive *node deletion* must use `softcancel`, never hard `cancel`.** Folded
  into Part I §6.

**Resolved this round (were admitted, now fixed):**

- **§7/§10a / Part II C5 — jobserver multi-tenant cancel footgun → FIXED.** The §6
  uniform membership-set model makes `softcancel` transitive across the jobserver
  boundary (soft-cascade, constraint 1); the jobserver gains a server-side set, no
  liveness mechanism needed (a leaked member just lets its job complete). Reverses the
  "intentionally simple jobserver" decision.
- **§8/§10b — daskserver latch-aware cancel → one instance of the §6 pattern** (still
  net-new work — scheduler-side set + client-side multi-holder mapping — but no longer a
  separate asymmetry).

**Admitted trade-offs (rebutted by acceptance, recorded for completeness):**

- **§10/§7 (F7) — connected-optional pins lose laziness; future-wired identity is
  provisional.**
- **§10 phasing — future-wired E/T deferred to the fire-and-forget milestone** (Part I
  §7).
- **F2 — speculation-vs-current contention is a corner case; preemption optional**
  (bounded by the wavefront argument; the grace-hold is kept, so this remains a
  corner-case nicety rather than being eliminated).
- **§9 — irreproducible transformations are out of scope for workflows.** Part II C6
  (retracted) confirms *accidental* nondeterminism is equally out of scope — masked by
  the cache, surfacing only via `scratch` recomputation in consumers; a universal
  Seamless property, not a `Context` hazard.
