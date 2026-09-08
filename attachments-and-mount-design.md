# Context Controller, External Attachments, and File Mounts — Design

> **Status.** Design-level plan, not an implementation handoff.
>
> It covers two separable concerns:
>
> 1. a **Context controller** that orders and applies all workflow state transitions; and
> 2. **attachments**, with file mounts as the first transport.
>
> The controller is useful without mounts: user edits, E/T results, cancellation, and
> future external inputs already need one mutation authority. Mounts depend on the
> controller; the controller must not depend on mount concepts.
>
> **Modifications marked `[MOD-n]`** are constraints imposed by the state of the current
> code (`seamless-workflow`, `seamless-transformer`, `seamless-core`). They are indexed in
> §25 and derived in `context-api-and-et-split-assessment.md`.
>
> **Scope.** Fire-and-forget is deferred, so **every dependency is checksum-wired**: a node
> becomes eligible to fire only once all its inputs are concrete checksums. Future-wired E/T —
> submissions carrying unresolved dependencies, which is what lets a cone advance headlessly
> after the Context detaches — is described in **[MOD-8]** only to record what must not be
> foreclosed. Nothing else in this document depends on it.
>
> **Starting point.** `Context` today is a **durable graph layer with no runtime layer**, and
> the split is clean: everything without a clock in it is largely sound, and everything with one
> is missing. Real and worth keeping: topology, path resolution, cycle detection,
> `get_graph`/`set_graph`, the refholder lifecycle (staged acquire-then-publish, named role
> claims, shutdown audit green on baseline), authority as a topology-only decision, the
> node-state derivation *rules*, and a **total facade/backend seam** — `Cell` and `Transformer`
> hold no state when bound, so every public call already funnels through
> `BoundCellBackend`/`BoundTransformerBackend`. Absent: `tf_checksum` occurs nowhere in the
> package, so there is no cache, no execution backend, no non-Python or compiled support, and no
> honoured execution envelope; `computing` is never assigned and `waiting` only appears under
> `eager=False`, where it means "not demanded"; there is no quiescence, no barrier, and the async
> surface is a synchronous stub. This document is therefore not a migration of a reactive layer
> but the **construction of the runtime half on top of a durable half worth keeping** — which is
> why A1 can break synchronicity without rewriting the derivation rules, and why A2 touches
> neither `seamless-core` nor `seamless-transformer`.
>
> *Note for whoever finishes A5:* this characterisation is recorded in agent memory at
> `~/.claude/projects/-home-agent-seamless1/memory/context-not-yet-reactive.md`. It becomes
> wrong on completion and should be amended then, not left to mislead a later session into
> assuming the runtime layer is still absent.

---

## 1. The requirement

An external event — a file changing, a widget edit, an HTTP write, an E/T finishing — can
arrive while Python user code is idle or while a transformation is running, and it must
eventually become an ordinary workflow perturbation. There must be exactly one place where
that happens.

Legacy Seamless (0.x) implemented mounts, traitlets and shares with three different
schedulers, locks, polling loops and echo suppressors. The divergence is the empirical case
for a single mutation authority:

| | inbound (external → cell) | outbound (cell → external) | echo suppression | scheduler coupling |
|---|---|---|---|---|
| **mount** | OS thread polling `stat` @ 0.2 s | `add_cell_update` deque, drained by that thread | `MountItem._renounce` | `must_run_mount`, `mm.last_run` |
| **traitlet** | `loop.call_later(0.1, …)` debounce | **synchronous** `cell._observer(cs)` fired inside checksum assignment | `_updating`, `Link.updating` | `livegraph._flush_observations()` |
| **share** | aiohttp handler → `cell_updates` dict | asyncio task loop @ 0.2 s | init/fallback logic | `sharemanager.busy` |

Legacy anchors: `seamless/workflow/core/mount.py` (`conditional_read` L445,
`conditional_write` L403, `_renounce` L80, `run` L751); `core/manager/manager.py:211` and
`:403-411`; `highlevel/SeamlessTraitlet.py:198`; `core/share.py:343`;
`core/manager/taskmanager.py:426-475`.

Two rows are load-bearing here.

The **traitlet outbound cell** fires an observer *inside* `_set_cell_checksum`,
mid-mutation. Legacy then needed `livegraph._hold_observations`, an `_observing` deferral
list and `_flush_observations()` at safe points, because re-entering user code mid-cascade
is not survivable. **Post-cascade actuation (§19) is that lesson promoted from exception
path to the only path.**

The **scheduler-coupling column** is the cost of having no single mutation authority:
because foreign threads could mutate cells at any time, "no pending tasks" stopped meaning
"settled", and `taskmanager.compute()` had to consult three subsystems before declaring
quiescence. **Keeping `quiescent` graph-only (§14, §21) is the direct response.**

The requirement generalises past attachments:

> A Context needs one place where all state transitions are ordered and applied,
> regardless of whether mounts are implemented.

The work therefore has two layers:

```text
public calls ─┐
E/T results ──┼──> Context controller ──> graph state / E/T submissions
timers ───────┤
attachments ──┘
                         ▲
                         │ immutable attachment messages
                         ▼
              attachment runtime and transports
                         │
                         ▼
                filesystem / widget / network
```

The boundary matters for review. Controller correctness is about linearizability, graph
ownership, turns, side work and shutdown. Mount correctness is about filesystem
observation, stable reads, canonical bytes, atomic writes, echo suppression and legacy
policy. Neither test suite should need the other to explain a failure.

---

## 2. Decisions at a glance

1. **One controller per Context.** It owns a dedicated thread and asyncio loop and is the
   sole graph mutator. A global controller stays a possible measured optimisation, not an
   initial semantic choice.
2. **One sequenced ingress per Context.** All user operations, E/T notifications, timers
   and attachment observations enter as immutable messages carrying a monotonically
   increasing acceptance sequence.
3. **The controller orders checksum transitions, nothing else.** Materialisation and
   dematerialisation happen *around* those transitions, as concurrent side work
   (§7).
4. **One message attempt is one turn**, run synchronously through validation, checksum
   transition, cascade, effect collection. No graph code awaits, and no graph code
   materialises (§8).
5. **There is no parking.** An operation that needs an unavailable value ends its turn and
   continues through side work, a subscription and a later immutable message (§9).
6. **A global filesystem service has two internal roles**: a cheap watch broker that
   detects dirty paths, and an I/O pool that performs stable reads, hashing, directory
   scans and writes. Neither knows about graph state.
7. **The semantic inbound boundary carries content.** The Context receives an immutable
   observation containing a checksum *and* `Buffer`, not merely "this file is dirty".
8. **Outbound delivery carries a usable payload**: a live `Buffer`, or a checksum backed
   by an explicit refholder lease. Never a bare checksum to be resolved later.
9. **Durable attachment specifications and runtime sessions are separate.** The node stores
   configuration; the Context runtime owns queues, generations, errors, pending deliveries
   and transport registrations.
10. **`quiescent` remains graph-only.** `sync()`/`settled()` use a filesystem barrier and
    delivery acknowledgements to define a finite external cut.
11. **Legacy mount `authority` is not silently redefined.** It resolves the initial
    file-versus-cell conflict. Continuous external ownership, if wanted, is a new policy
    with a new name.

---

# Part I — The Context controller

## 3. Scope and the ownership invariant

The controller project covers ownership of mutable Context graph and runtime state;
synchronous and asynchronous ingress; ordering and turn execution; E/T submission and
result re-entry; side work and conditional commits; public exception propagation; graph
quiescence; and lifecycle, shutdown and diagnostics.

It does not know about paths, mtimes, file modes, mount authority, filesystem errors or
echo suppression.

Its load-bearing invariant is:

> **Only the Context controller thread may read or mutate live graph runtime state, and
> code that touches that state is synchronous, non-yielding, and performs no
> materialisation.**

"Read" is included deliberately: allowing arbitrary threads to inspect mutable graph objects
would replace mutation races with snapshot races and eventually require graph-wide locks.
Public reads initially round-trip through the controller. A published immutable snapshot can
be added later if profiling justifies a second read path.

"Performs no materialisation" is the half that the current implementation does not satisfy,
and it is the substance of the first milestone rather than a detail of it:

> **[MOD-12] A1 is materialisation excision, not inventory.** The current cascade
> (`seamless-workflow/seamless_workflow/context.py:857` `_derive_all`) resolves buffers,
> deserialises values, executes user code and re-hashes results, on every public operation
> and for every node. Eighteen call sites route through four adapter functions in
> `seamless_workflow/adapters.py`. The first milestone must be stated as *removing those
> from the turn*, not as "inventory every mutation and read" — otherwise the plan
> understates its own largest task.

> **[MOD-14] Make materialisation observable before trying to remove it.** The waste is
> invisible to the test suite because materialisation has no trace: a test asserts the *value*,
> which is correct either way. Add a diagnostic recording mode in `seamless-core` — the level
> that catches every path, including ones that bypass `seamless_workflow/adapters.py`:
>
> ```python
> with seamless.diagnostics.record_materialisation() as log:
>     ctx.a = 42
> assert log.ops == []          # an unrelated assignment must materialise nothing
> ```
>
> Instrument buffer serialisation, `Checksum.resolve` / `resolution` / `fingertip`, and value
> deserialisation, recording `(op, checksum, celltype, nbytes)` plus an optional attributed
> node path. Then assert the **exact expected log** for each public operation.
>
> Three properties make this the right first task. It is **independent** — no concurrency, no
> inbox, nothing else has to move first. It is **executable now**, against current behaviour, so
> the expected logs start as a description of the defect and shrink as work lands; the test file
> is the specification. And it is the **exit-evidence instrument for [MOD-12] and §14.1**:
> "a turn performs no I/O and no hashing" stops being a claim in a document and becomes an
> assertion.
>
> Three qualifications. The log catches **materialisation, not redundant derivation** — those
> are different wastes, and since content-addressing absorbs the second once execution routes
> through the cache, that is the right scope; but it means the log will not catch an O(N²)
> re-derivation regression. **Checksum-level records suffice**: `assert log.ops == []` needs no
> node attribution, which removes a chunk of the instrumentation. And the expected logs are
> **not a write-once artifact** — they change wholesale at A1 and again at A3.

## 4. Why a controller thread, and why a loop

A dedicated controller thread works in scripts, plain Python, terminal IPython and Jupyter.
It can apply E/T results and mount observations while the user is idle; it does not depend
on the caller's event loop or on a later call to `compute()` to pump an inbox.

The alternatives are weaker. A **graph mutex with mutation from arbitrary threads**
serializes bytes of execution but gives no ownership model, making re-entry, lock-held
callbacks and thread-affine code hard to reason about. A **main-thread inbox** needs an
event pump that plain Python does not provide while idle; draining only on public calls
changes the semantics of background completion. **One global controller for every Context**
preserves the model but introduces cross-Context head-of-line blocking and failure
coupling; it may become worthwhile if large numbers of Context threads are measured to be a
problem.

Asyncio is an implementation tool, not the essential idea — the essential idea is a single
owner and a sequenced mailbox. The loop earns its place because **timer ownership is
required, not speculative**: the reactive layer commits to a bounded supersession grace hold
(≤ 5 minutes) and to delaying cancellation of a superseded submission by ~10 s after the
replacement is submitted, so that backend deduplication can latch on. Delivery timeouts and
barrier timeouts (§21) add more. A thread-based controller would need its own timer heap; a
loop has `call_later`, and `run_coroutine_threadsafe` supplies the reply channel §12 needs.

E/T execution remains off-controller. The controller submits work and later accepts
immutable notifications. It never awaits transformation execution, remote transfer, buffer
resolution or user transformer code on its own loop.

> **[MOD-10] The controller loop is not the E/T loop.** The submission substrate contains
> synchronous islands that must never run on the controller loop: `buffer_writer.flush()`
> inside `seamless-transformer/seamless_transformer/transformation_cache.py:656`,
> `Checksum.resolve()` inside `pretransformation._prepare_code`, and `Checksum.resolve()`
> itself, which may spin a fresh event loop or worker thread and perform a remote HTTP
> fetch (`seamless-core/seamless/checksum_class.py:162`). Additionally,
> `Transformation.start()` does not forward its `loop` argument to dependencies
> (`transformation_class.py:1116`), so anything scheduled from the controller thread leaks
> onto the controller loop. **The Context must own a second loop/thread for E/T and side
> work, and must never pass its own loop into the substrate.** This is enforceable by
> construction; it is not enforceable by review.

## 5. Ingress and linearisation

### 5.1 One gateway

Every source submits through one small thread-safe ingress gateway. Under a short ingress
lock, the gateway verifies that the Context is accepting messages, assigns
`context_sequence += 1`, freezes an immutable envelope, and wakes the controller loop.

The lock protects only acceptance and queue insertion. It is never held while graph code,
callbacks, hashing or I/O run.

```text
ContextMessage(
    context_id,
    context_sequence,
    klass,              # 1..5, see §6
    payload,
    reply_future | None,
)
```

Source-specific payloads may carry their own sequence and generation fields; those do not
replace `context_sequence`.

### 5.2 The ordering contract

An operation linearizes when the ingress accepts its immutable message — not when an OS
event occurred, and not when some producer began preparing the payload.

- If message A is accepted before message B, A is attempted first.
- If two threads submit concurrently, either order is legal; the ingress lock chooses it.
- The controller provides ordering, not semantic precedence. Whether a later mount
  observation overrides a user edit is a mount-mode/policy question.
- Acceptance order is the default processing order. The only departures are the *proven
  commuting* promotions of §10.

This answers the "user update and mount message are both in the inbox" race: there is no
special winner, the accepted order is the order. Truly simultaneous events have no natural
cross-thread order for Seamless to discover.

### 5.3 Accepted messages are immutable

A coalescing slot that a transport can overwrite after acceptance breaks linearizability:

```text
accept mount observation M1 and schedule its callback
accept user edit U
transport overwrites M1's slot with later observation M2
run the scheduled callback, which now applies M2
run U
```

M2 was submitted after U but applied before it. Therefore:

- an accepted message is immutable;
- a queued callback may not read a transport slot that later writers can overwrite;
- a transport may coalesce dirty events **before** producing a Context observation, because
  they have not yet entered Context ordering; and
- the controller may coalesce only a contiguous run of compatible messages, never across an
  intervening user operation, E/T notification, barrier or incompatible observation.

The first implementation performs no controller-side coalescing at all. Bounded,
adjacency-preserving compaction can be added after realistic event-rate measurements: `M1,
M2, U` may become `M2, U`; `M1, U, M2` may not become `M2, U` or `U, M2`.

## 6. The five inbox classes

The inbox has five semantic classes. This is not a priority queue that may reorder accepted
messages; it is a hierarchy of **permission and interpretation**. Higher classes establish
the state in which lower classes may be decided.

| class | direct meaning | what must already be stable |
|---|---|---|
| 1. procedure | change how the Context progresses | prior controller state and admission policy |
| 2. topology | change authority and dependency structure | any enclosing procedure |
| 3. value write | install an authoritative checksum | preceding topology |
| 4. value read | snapshot a checksum | preceding topology, and writes that may affect its target |
| 5. E/T notification | report a cache/checksum fact | current demand derived from classes 2–3 |

### Class 1 — procedural

Shutdown and any explicitly requested finite-cut procedure. A procedure may deliberately
stall normal progression while establishing a lifecycle or synchronisation boundary. That is
acceptable because procedures are infrequent and their purpose is precisely to create a
strong before/after boundary.

### Class 2 — topology and authority

Creating, removing or replacing graph structure and external attachment structure:
creating/deleting nodes and dependency edges; changing transformer or expression wiring;
attaching, removing or replacing an attachment; changing a producer direction, authority
rule or attachment generation.

**Node and pin configuration belongs here**, because it changes transformation identity and
therefore what is demanded: celltype, target celltype, validator, language, code, celltypes
map, optional pins, modules, globals, meta, scratch, local, direct_print, driver,
allow_input_fingertip.

> **[MOD-6] One parameterised configuration message, not fifteen setters.** The current code
> exposes ~15 config mutations as in-place attribute writes on shared mutable dataclasses
> reachable from a handle (`seamless-workflow/seamless_workflow/builder_state.py:399-447`,
> `WorkflowMapping`, `WorkflowCelltypes`), two of which (`driver`,
> `allow_input_fingertip`) do not even trigger re-derivation. Model these as a single
> `SetNodeConfig(node_path, field, value)` class-2 message with a per-field validator table.
> Fifteen message types is the shape that becomes copy-paste; one plus a table is not. Fix
> the two non-re-deriving setters as part of the same change.

A topology operation is applied atomically. Lower-class messages must not observe partially
installed topology.

> **[MOD-4] Value-dependent connection targets.** Connecting to an integer-indexed target
> currently bounds-checks against the target's materialised value
> (`context.py:691`), which makes a class-2 decision depend on materialisation. Choose one:
> **(a)** accept the edge on topology alone and let the derivation fail if the index is out
> of range; or **(b)** treat the bounds check as an optimistic precondition carried on the
> commit (§9), so it is evaluated as side work against a named base checksum. **(a)** is
> recommended: it keeps class 2 pure, and an out-of-range index is exactly the kind of thing
> the node-state machine already reports.

### Class 3 — authoritative value writes

A class-3 message proposes a checksum for a node that has direct-write authority — in the
ordinary graph case, a node with no incoming dependency edge. User assignment and an
attachment observation are both instances, differing in source policy and error routing.

**The permission rule:**

```text
class-3 message V at sequence S is authority-decidable
    iff there is no unresolved class-2 message T with T.sequence < S
```

Once that holds, let `Topology(S)` be the topology produced by the class-2 prefix before
*S*. Direct-write authority is a pure decision against that topology:

```text
no incoming dependency in Topology(S)  ->  V may install its checksum
incoming dependency in Topology(S)     ->  AuthorityError
```

So:

```text
10  remove incoming dependency from A        10  add incoming dependency to A
11  write checksum to A       -> allowed     11  write checksum to A       -> AuthorityError
```

A topology message *after* the write is irrelevant to that write's authority, even if it has
already been accepted into the tail of the inbox.

This rule is testable without materialising anything — a plain class-3 message neither creates
nor removes dependency edges. Assignment *syntax*, however, is deliberately not a plain class-3
message:

> **[MOD-1] Assignment detaches; `.set()` does not. Both are one message.**
>
> Seamless keeps legacy detach-and-write semantics, sharpened so that the rule is stateable
> without reference to path depth:
>
> - **Assignment syntax — `ctx.a.b = 3`, `ctx.a["b"] = 3`, `del ctx.a.b`, and the root form
>   `ctx.a = 3`** — is a **compound detach-and-write**. It removes every incoming edge landing
>   on the assigned path *or below it*, then installs the checksum. It raises `AuthorityError`
>   if an incoming edge lands on a **proper ancestor** of the assigned path, up to and including
>   the node root. So `ctx.a.b = 3` raises when `ctx.a` has a root-level incoming edge, and
>   detaches when `ctx.a.b` or `ctx.a.b.c` is connected.
> - **Explicit `.set()` / `.set_checksum()`** never detaches. It raises `AuthorityError` if an
>   incoming edge lands on the target path, on any proper ancestor, **or below it** — because a
>   non-detaching write cannot silently orphan a connection it would overwrite.
>
> A compound is **one inbox message**, not two. Its class-2 half is decided and applied before
> its class-3 half *within the same turn*, so no lower-class message can observe the detached-
> but-not-yet-written state, and the ordering contract is untouched. It does not weaken §12.2:
> a detach cannot fail on authority, and the write that follows it in the same turn sees the
> edge already gone.
>
> **Three objections to record, none of them fatal but all of them load-bearing for the spec.**
>
> *The `=` / `.set()` split is not discoverable and has no precedent in this codebase.* They are
> synonyms today, and `test_context_basics.py` uses both interchangeably within a single test
> (`ctx.a.b = {"c": 3}` beside `ctx.a.b.c.set(3)`). After the change, refactoring `x.set(v)` into
> `x = v` silently alters authority semantics with no diagnostic. An explicit opt-in —
> `set(v, detach=True)`, or a distinct verb — yields the same two behaviours and documents
> itself. The counter-argument is legacy compatibility, which is a real reason but should be
> named as one.
>
> *The rule as stated sweeps in transformer pins, where behaviour is strict today.*
> `ctx.tf.pins.x = 5` is assignment syntax, and `_set_transformer_pin` currently raises
> `AuthorityError` via `_check_authority` when the pin is connected. Under a blanket
> "assignment detaches", typing `=` would silently drop a first-class dependency edge. **Pins
> must be excluded** — after which the rule reads "assignment detaches *for cell sub-paths
> only*", a compatibility rule rather than a principle. A cell sub-path edge is no less real
> than a pin edge; nothing structural distinguishes them.
>
> *`del` is two different operations.* `del ctx.a.b` is a sub-path value edit (compound);
> `del ctx.a` is node deletion — pure class 2, and it must remain legal when the node has an
> incoming edge. The rule must not treat them alike.

> Current code matches neither rule. `.set()` and `=` are the same call path
> (`BoundCellBackend.set` and `.assign` both reach `_cell_operation`), so the distinction does
> not exist; and the ancestor check `_check_cell_update_authority` (`context.py:517`) inspects
> only `()` and `(local[0],)`, so for a path of depth ≥ 3 an intermediate ancestor edge is
> missed. Both need fixing together; the ancestor scan should walk every proper prefix.

> **[MOD-2] A checksum write installs a checksum.** `set_checksum` is the canonical class-3
> message, yet it is currently implemented as resolve → deserialise → re-serialise → re-hash
> (`context.py:469` → `context.py:486`), so it fails outright when the buffer is absent
> and risks identity drift for any celltype whose serialisation is not canonical. It must
> become: validate that the checksum is deserialisable as the target celltype
> (`seamless-core/seamless/checksum/hash_type_validation.py`), acquire the reference, install
> it. No resolution, no round trip. This is the single clearest instance of the controller
> not being checksum-based, and it should be a named fix rather than a side effect of a
> general refactor.

### Class 4 — value reads

A read asks for a checksum; it does not ask the controller to materialise a Python value. If
a current checksum exists, the controller snapshots it together with the reference lease
needed to keep it resolvable, and finishes the turn. Dematerialisation runs as side work.

If no checksum is available, the controller returns or installs a checksum-availability
subscription and finishes the turn. A synchronous wrapper may wait outside the controller and
re-read when notified. The inbox message itself is never parked. Such a retry normally
snapshots the then-current checksum and may therefore observe state later than the original
request; an API that promises a revision-pinned read must name and retain that checksum or
revision explicitly.

An ordinary class-4 read does **not** imply that its node must first become quiescent. If
some checksum is available, it is a valid read result even while newer derived work runs. A
separate quiescent-read construct is described in §10.

> **[MOD-3] Only nodes carry checksums; sub-path reads are E jobs.** The design of §10
> assumes "some checksum is currently available for *X*" for any readable endpoint. That is
> true only for whole nodes. A sub-path endpoint (`ctx.a.b.c`) has no stored checksum; the
> current code computes one on demand by resolving the parent, indexing the Python value and
> re-hashing it with the *parent's* celltype (`context.py:1034-1041`) — a private,
> uncached, uncancellable re-implementation of expression evaluation. **Sub-path reads must
> become class-5 E jobs** over `seamless-core/seamless/checksum/expression.py`, which already
> provides a content-addressed expression cache, an async evaluator, remote evaluation with
> member-scoped cancellation, and a `cancel_expression` entry point. Promotion (§10) is then
> stated over **nodes**, and the promoted, leased object is the *E result*. This is a net
> deletion of Context code, not an addition.

### Class 5 — E/T cache and checksum notifications

Expressions and transformations are content-addressed, cached work. Their callbacks never
touch graph state; they submit immutable notifications:

```text
InputChecksumAvailable(checksum)
CacheEntryAvailable(cache_key)
CacheEntryFailed(cache_key, error)
CachePollResult(cache_key, state)
CancellationResult(cache_key, state)
```

A class-5 message carries no independent authority to write a node. It wakes the controller,
which re-evaluates current checksum demand under the topology and authoritative values that
exist when the message is processed.

By construction, class-5 messages do not semantically change downstream checksums: they make
already-determined checksum/cache facts available, report failure or progress, or wake
reconciliation. They may change availability and runtime status, but they introduce no new
authoritative input and no new dependency relation. Semantic checksum changes come from
class 2 or class 3 and the deterministic propagation they induce.

Protocol-support events need no sixth level; they are classified by the transition they
enable. A shutdown timeout or procedure completion is class 1; a topology-generation
transition is class 2; an attachment observation proposing a node checksum is class 3; an E/T
grace timer or cache-poll result is class 5. A delivery acknowledgement that changes only
attachment diagnostics is runtime bookkeeping and cannot acquire graph authority by being
called a result message.

> **[MOD-9] Two of these five have no producer.** `CacheEntryAvailable`,
> `CacheEntryFailed` and `CachePollResult` map onto existing awaitables
> (`transformation_cache.run`, `is_cached`, `transformation_status`). **`InputChecksumAvailable`
> has no primitive at all** — there is no buffer-availability subscription in
> `seamless-core` (`buffer_writer.await_existing_task` is the nearest thing) — and
> `CancellationResult` has none either, since soft-cancel returns a synchronous `bool`
> (`transformation_cache.py:389`). Either build both, or drop them from the design and state
> what replaces them. They are new work, not adaptation.

## 7. The checksum data plane

Classes 3 through 5 are instantaneous at the controller boundary, because the controller
operates on checksums:

```text
write
    Python or external value
        -> side-work materialisation and hashing
        -> checksum plus Buffer/refholder lease
        -> instantaneous authoritative checksum transition

read
    instantaneous checksum snapshot plus lease
        -> side-work buffer resolution and dematerialisation
        -> Python or external value

E/T
    cache/checksum notification
        -> instantaneous demand reconciliation
        -> non-blocking launch, poll, subscription, or cancellation effects
```

"Instantaneous" means the controller attempt has no inherent wall-clock wait. It may do
bounded in-memory propagation over an affected graph region, but it performs no file or
network I/O, executes no user transformation, resolves no remote buffer, hashes no large
value and invokes no external callback.

A semantic inbound write is therefore **checksum-ready when it reaches the controller**. It
carries a live `Buffer`, or a checksum protected by an explicit reference lease when later
resolution may be required. Preparing that payload is producer-side work and does not occupy
the controller.

A read snapshots immutable content. Later messages cannot change the meaning of that
checksum, so its dematerialisation can overlap both later reads and later writes. Reference
ownership must keep the snapshot resolvable until dematerialisation finishes.

> **[MOD-16] `Expression` does not claim its `input_ref`, and the escape hatches rely on it
> doing so.** The Context's own refholder accounting is correct: every claim it makes is
> matched, staged before publication, and released on replacement. The gap is in the
> counterparty. `Cell.__init__` / `_replace_input_ref` incref a `Checksum` input and report it
> as the `"input"` role; `Expression.__post_init__` does neither, and
> `Expression._refheld_checksums()` reports only its *result*
> (`seamless-core/seamless/expression_class.py:87-99, 228-233`).
>
> Measured: after `expr = ctx.b.build()`, five reassignments of `ctx.b` and a `ctx.prune()`, the
> input checksum's refholder count is **0 with no eviction bridge**, while `expr.input_ref` still
> names it. It resolves only until the incidental `tempref` fades. `Cell(cs)` on the same
> checksum takes the count to 1 immediately.
>
> This is why cross-checking the Context found nothing: the defect is one class away, in the
> sibling that does *not* implement the lease. Fix `Expression` to claim its `input_ref` on the
> same terms as `Cell`, then audit the four escape hatches (`capture_source`,
> `_build_cell_expression`, `_build_source_expression`, `snapshot_for_call`) against the fixed
> contract. `capture_source` into a standalone `Cell` is already safe, because the receiver
> acquires.
>
> Note the timing dependency this exposes. Today the hand-off is safe *by temporal coincidence*:
> the read and the receiver's acquire happen in one synchronous frame while the Context still
> holds its own claim. Once a read completes through a reply future, that frame is gone and a
> class-3 write can drop the last claim between snapshot and acquire. **The controller must
> therefore acquire the lease inside the reading turn, atomically with the snapshot** — not
> leave it to the caller.

> **[MOD-13] State the write round trip explicitly.** For a whole-node write the caller
> materialises *first* and then makes **one** round trip; authority is decided against
> topology when the message is attempted. A consequence worth writing down: an
> `AuthorityError` can be raised *after* the caller has already paid for serialisation and
> hashing. That is correct and unavoidable — authority cannot be decided off-controller —
> but it should be documented rather than discovered.

## 8. A turn

A turn is one non-yielding message attempt:

```text
1. validate the message against current topology
2. apply its direct checksum-level meaning
3. propagate currently known checksum state synchronously
4. determine the E/T cache keys currently demanded by the graph
5. update derived node state and continue the in-memory cascade
7. collect non-blocking launch, poll, subscription and cancellation effects
8. return or record the outcome
```

Steps 4–6 are **autonomous controller reaction**, not additional inbox classes. Launching
E/T work and updating derived graph state are what the controller does *because of* a
message, not messages in their own right.

Collected effects are dispatched only after the cascade finishes. Dispatch must itself be
non-blocking; executors and transports later return completion messages. Effect callbacks
only submit new class-5 messages: `CacheEntryAvailable` may not inspect interested nodes,
install a checksum, complete a cell or initiate a cascade from its callback thread.

A turn need not make the Context quiescent. It may leave nodes `computing`; each E/T result
is a later turn. The important property is that no observer sees half of a graph transition.

**The two halves of a turn have very different precision requirements, and content-addressing
is what licenses the difference.** Steps 2–3 — revoking the downstream cone from `complete`
before anything downstream is evaluated for firing — must be **exact and complete in one
non-yielding pass**: an invalidation the cascade misses is a correctness bug, and it is the
only way a glitch can occur. Steps 4–6 — deciding what is demanded and launching it — may be
**blunt**. A node that is re-derived unnecessarily reconstructs the same `tf_checksum` and
resolves to a cache hit, so redundant reconciliation costs a small hash and a lookup, not a
recomputation. This asymmetry is why the cascade does not need to be clever, why cheap
whole-region reconciliation is an acceptable first implementation, and why demand can be
expressed as *interest in cache keys* rather than as a carefully maintained dependency
schedule.

Two costs are hidden by that licence and should be measured rather than assumed: a redundant
reconciliation still pays tf-dict construction and hashing per node, and a key that misses the
in-process cache pays a database round trip before it is memoised. Both are per-pass, not
per-node-lifetime — a cold wide graph under rapid editing is where they would first show up.

Graph functions are divided mechanically: plain synchronous functions may touch graph state
but may not block, materialise or call external code; coroutine wrappers may wait, schedule
retries or mirror an async API, but may not retain a partially applied graph mutation across
an `await`. Controller-thread affinity should be asserted at internal mutation entry points
during the migration.

## 9. Side work and optimistic commits

Side work belonging to several messages may execute concurrently. Completion order need not
match start order, because no side worker commits graph state directly.

Some side work is unconditional: dematerialising a captured checksum always yields the value
that checksum denotes. Other side work is **optimistic** — updating a sub-path requires
resolving and modifying a parent buffer, so its result must carry the base checksum it
depended on:

```text
MaterialisedUpdate(
    message,
    base_checksum,
    resulting_checksum
)
```

The controller commits the resulting checksum only if the precondition still holds;
otherwise the result is discarded or recomputed from a fresh checksum. This is optimistic
side work, not a parked or partially applied graph operation.

The full three-phase protocol for a sub-path write is:

```text
turn 1   validate authority; snapshot base checksum; acquire lease; end turn
side     resolve base -> value -> apply update -> serialize -> hash
turn 2   commit iff node checksum is still base_checksum; else retry (bounded)
```

> **This is the one genuinely new mechanism in Part I.** It affects exactly three current
> sites: the non-empty-path branch of `_cell_operation` (`context.py:495-501`),
> `_cell_delete_path` (`context.py:522`), and `augmented`
> (`builder_state.py:215`). Everything else in the public surface is a whole-value or
> whole-checksum operation and needs only §7's single round trip.

Side work started before a semantic message is accepted has no Context ordering of its own;
its checksum-ready result linearizes when ingress accepts it. If an accepted operation starts
side work for a later conditional commit, the returned result is a new immutable inbox
message carrying its preconditions. The controller never reserves a half-applied turn while
waiting for it.

**There is no parking.** An operation that needs materialisation or an unavailable checksum
ends its turn and continues through side work, a subscription and a later message. No mutable
graph reference and no partial mutation survives that wait. An `await` placed *inside* an
attempt would read as ordinary sequential code while quietly reintroducing
time-of-check/time-of-use inside the controller.

## 10. Safe promotion of reads and node-quiescence barriers

Acceptance order is the default, but it is stronger than necessary for messages that provably
commute with the pending prefix. A class-4 read of node *X* may be promoted ahead of preceding
lower-class messages when both hold:

1. a checksum is currently available for *X*; and
2. no preceding inbox message can change the checksum the read would return.

The purpose is latency, not semantics. Once the controller has exposed and leased the
checksum, slow buffer resolution and dematerialisation start immediately as side work,
overlapping the harmless preceding messages instead of waiting behind them. Promotion changes
neither the checksum returned nor the semantic history.

The conservative proof:

```text
no active or preceding class-1 gate
and no preceding class-2 message
and every preceding class-3 message is proven not to affect X
```

Class 2 is a blanket blocker because a topology change can alter both authority and the
dependency path used by the proof. With topology stable, the controller inspects each
preceding class-3 write: it cannot affect *X* when its target is neither *X* nor upstream of
*X*. A stronger implementation may also prove harmlessness from equal checksums; dependency
reachability is the safe initial rule.

Preceding class-4 messages do not change graph state. Preceding class-5 messages do not block
promotion, because they do not semantically change downstream checksums. So:

```text
W(Y), N(cache_key), R(X)
```

may process `R(X)` first when `Y` is not upstream of `X` and a checksum for `X` is available.

Per **[MOD-3]**, *X* here is always a **node**. A sub-path read is not itself promotable; it
is a class-5 E job whose *result* is a node-level checksum fact.

An API meaning "read *X* after *X* is quiescent" has different semantics and is represented
as a correlated pair:

```text
NodeQuiescenceBarrier(X)
ReadChecksum(X)
```

correlated so the read observes the state the barrier established — either an atomically
accepted pair, or a barrier completion that submits its linked read before unrelated work can
intervene. The barrier itself can be promoted when *X* is quiescent now, no class-1 gate or
class-2 message precedes it, and every preceding class-3 message is proven not to change *X*
or its quiescence. This node-local construct is distinct from a Context-wide or attachment
finite-cut barrier (§21).

The promotion test requires only current topology, pending message metadata, dependency
reachability, checksums and node status. It performs no materialisation and is itself an
instantaneous controller operation.

## 11. What a stall means

Classes 1 and 2 are naturally slow relative to a checksum transition. That is acceptable and
often desirable: later values and reads should not pass through a lifecycle boundary or
observe intermediate topology.

During such a stall:

```text
Context controller   holds its processed frontier
Context ingress      continues accepting and sequencing immutable messages
E/T workers          continue executing and populating content-addressed caches
side-work pools      continue materialising and dematerialising values
```

No worker, callback, cache notification or transport may read or mutate graph state. A
notification produced during the stall is accepted into the inbox and waits; when the atomic
operation finishes, queued messages are interpreted against the completed state.

Ingress, E/T execution and side work already belong to different threads or processes, so the
controller gains nothing by yielding mid-transition to keep them alive. Atomic synchronous
controller execution is the natural default; only the processed frontier stalls. The ingress
lock is therefore independent of the controller and is never held for the duration of a
procedural or topology operation. Shutdown is the exception only in admission policy: ingress
stays responsive but may reject new ordinary work.

## 12. Public API, failures, and what a user can encounter

### 12.1 Synchronous public surface

Every public mutation and consistent read submits a message and waits on a future; the
controller exception is re-raised in the calling thread. This preserves normal Python error
handling for graph construction and assignment.

The round-trip cost is an engineering risk, not something to dismiss with "public calls are
never hot": programmatic graph construction, parameter sweeps and repeated reads can be hot.
Before considering the controller complete, benchmark large graph construction one operation
at a time; bulk assignment; repeated `.value`/state reads; and notebook-scale interactive
calls. Likely remedies are an explicit transaction/batch API and, only if needed,
controller-published immutable read snapshots. Neither changes the single-writer rule.

Calling the synchronous public API from the controller thread raises `ReentrantContextError`
rather than deadlocking or creating a weaker inline path.

The public API needs no scheduling privilege and no separate mutation path. It is a producer
and consumer around the same checksum protocol: a synchronous write may wait for
materialisation and for the controller's authority decision while the controller stays free; a
synchronous read may wait for dematerialisation or checksum availability while the controller
stays free; exceptions are correlated back to the caller without changing message ordering.

> **[MOD-7] A view derivation must not mutate the node.** `BoundCellBackend.derive`
> (`builder_state.py:143`) applies `celltype` / `target_celltype` / `validator` updates by
> assigning to a *new backend object* whose setters write through to the **shared node**;
> measured, `ctx.a.as_celltype("str")` changes `ctx.a`'s own `target_celltype` in
> `get_graph()`. Standalone `Cell._derive` clones. Bound derivation must clone too, or be
> reclassified as class 2 — but a "read" message that mutates state invalidates the
> linearisation claim, so this must be settled before routing.

### 12.2 Two invariants, and the failures a user can meet

The ordering contract says which message wins. It does not say which *failures* a user can
encounter because something else was queued — which matters for interactive use, since "my
assignment raised, and it would not have a second earlier" is the least acceptable class of
error. Two invariants bound it, and both should be assertable in tests:

> **I1 — At most one public operation is in flight at any instant, and none is ever
> partially applied while another runs.** An attempt is a non-yielding synchronous function,
> and an operation that cannot complete ends its turn rather than suspending mid-mutation.
>
> **I2 — A single-threaded user has none of its own public messages pending when its call is
> attempted.** Every public call blocks its caller, so one user thread can have at most one
> outstanding; with *N* user threads the bound is *N*.

Consequences:

- **An inbox-induced `AuthorityError` is impossible for a single-threaded user.** Authority
  depends only on topology; topology changes only through class-2 messages and the class-2 half
  of a compound (**[MOD-1]**); by I2 none of the user's own are pending; attachment observations
  and E/T results carry values and checksums, never edges. The compound form does not weaken
  this: it is one message, so nothing interleaves between its detach and its write, and a detach
  cannot itself fail on authority. With concurrent user threads it becomes possible, and it is
  then a genuine race in user code — serializing it and failing the loser is correct.
- **Value-dependent checks are inbox-sensitive even single-threaded.** An integer-indexed
  connection target validated against a current value turns `ctx.a[3] = ctx.b` into an
  `IndexError` when a sensed observation shrinks a list — which is why **[MOD-4]** prefers
  removing that check from class 2 entirely.
- **A sub-path update on a node that is momentarily recomputing must not fail for no
  user-visible reason.** This is what §9's optimistic commit removes: the operation
  snapshots a base checksum, does its work off-controller, and either commits or retries.
  Without I1 that would be unsound, because a half-applied operation could be observed across
  the wait.

### 12.3 Failure routing

- A public request completes its reply future with a value or an exception.
- An E/T result that makes a node invalid records failure on the node and propagates blocking.
- An external edit rejected before changing the graph records an attachment/edit error; it
  does not falsely mark a previously valid node failed.
- Unexpected controller-internal exceptions poison or stop the Context visibly. They must not
  be reduced to a log line on a daemon thread.

Exact exception classes and reporting surfaces remain implementation details, but every
asynchronous failure needs a durable place a user can inspect.

## 13. E/T submission and the reactive continuation

The controller maintains **interest in cache keys** rather than ownership of results. E/T
execution has content-addressed identity, not Context-specific result authority. When graph
state changes and an E/T ceases to be demanded, the Context's interest becomes stale — the
cached computation does not become invalid. The work may still populate a valid cache entry,
may be useful to another Context, and may become useful again if the same demand returns.
Delayed cancellation after a grace period is therefore resource management, not a correctness
mechanism.

> **[MOD-8] One readiness regime per node — and the future-wired regime must not be bypassed.**
> A node's E/T lives in one of two regimes, distinguished exactly by whether the submitted
> transformation carries unresolved dependencies:
>
> - **Checksum-wired** — every input is a concrete checksum, so `upstream_dependencies` is
>   empty, `Transformation`'s dependency runner iterates nothing, and a `tf_checksum` is
>   constructed at submission. Here the controller may submit through
>   `transformation_cache.run(...)` directly (building the dict from checksums;
>   `pretransformation._to_checksum` accepts a `Checksum` verbatim) or through `Transformation`;
>   the two are equivalent, so the choice is ergonomic. Submitting directly saves the controller
>   nothing but a wrapper, and costs it result refholding (which it already does —
>   `context.py:803`) and the `__deps__` dunder (classified derived/eliminable, so omittable).
>
> - **Future-wired** — some input is still an upstream promise. The controller passes
>   `upstream_dependencies`, and `Transformation` together with the Dask mixin converts the cone
>   into a **resident task graph**: `_build_dask_submission` leaves `tf_checksum = None`,
>   declares each dependency as `kind="transformation", checksum=None`, recursively obtains its
>   futures via `_ensure_dask_futures`, and `fire_and_forget` keeps the scheduler holding the
>   task after the client releases it (`seamless-dask/seamless_dask/transformation_mixin.py:660-712`,
>   `seamless-dask/seamless_dask/client.py:1461`). **This is the only encoding of an
>   unresolved-input transformation in the codebase, and it is what makes headless advance after
>   detach possible.** It must not be bypassed or reimplemented.
>
> `Transformation`'s dependency machinery is therefore not duplicated scheduling; it is the
> submission-side encoding of the `waiting` cone, executed off-controller. What the controller
> must not do is hold *both* regimes for one node at once, or await a `Transformation`'s
> dependency resolution in order to decide its own node states. The transition is
> one-directional and already specified: at `waiting → computing` the checksum-wired E/T
> replaces the future-wired one, whose cancellation is delayed ~10 s so backend deduplication
> can latch on.
>
> Three consequences the controller must respect:
>
> - **A future-wired submission has no `tf_checksum` by construction.** Class-5 notifications
>   about a `waiting` node therefore cannot be keyed by cache key; they are keyed by node path
>   and run generation — equivalently, by the upstream identity. Member-scoped soft-cancel is
>   unavailable for the same reason: `release_transformation_futures` has no key to deregister
>   against and falls through to a plain release, so future-wired E/T are cancelled by
>   cancelling the future, not by deregistering a member.
> - **Headless advance is Dask-conditional.** The jobserver path submits a fully constructed
>   transformation dict and so requires concrete inputs; with no Dask client, dependency
>   resolution is a local `asyncio.wait` inside the Context process and does not survive detach.
>   Fire-and-forget is a Dask-backend guarantee, not a general one.
> - **The submitted transformation must carry the node's stored execution envelope.**
>   `language`, `modules`, `globals`, `environment`, `scratch`, `local` and `direct_print` are
>   serialized into `get_graph()` today and then dropped, so a Context transformer is
>   Python-only and module-less whatever its configuration says, and a non-Python transformer
>   silently reports `complete` with a null result (`context.py:971-974`). Relatedly, `ctx.tf()`
>   and the controller's own submission must construct **the same** `tf_checksum` for the same
>   node state; two identities for one node would silently split the cache — the one failure a
>   content-addressed model cannot detect for you.

> **[MOD-15] Non-Python transformers need correctness tests, and one of them fails on the first
> line.** A Context transformer today executes `cfg.callable(**kwargs)`, so bash and compiled
> transformers have no execution path at all — and rather than being rejected, a node whose
> `callable` is `None` is set to `complete` with a null result (`context.py:971-974`). Measured:
> a `delayed(…, language="bash")` transformer bound into a Context reports `Status: OK` and
> yields `None`. The suite is silent because it only smoke-tests state.
>
> Two separable actions:
>
> 1. **Immediately, independent of everything else:** stop reporting `complete` for a node with
>    no executable code. `unwired` (or `failed`, with a reason) turns a silently wrong answer
>    into a visible gap, and costs one branch.
> 2. **With the envelope work:** add correctness tests that assert *results*, not states — a
>    bash transformer writing `RESULT`, a compiled transformer with a `__schema__`, a
>    transformer using `modules`, and one carrying a non-default `environment`. These will fail
>    until the submitted transformation carries the node's stored envelope, which is the point:
>    they are the acceptance criteria for that work, not a regression suite for it.
>
> Sequence bash before compiled — and note that **compiled is a representation gap, not merely
> an execution gap**. `CompiledTransformer(CompiledMixin, TransformerCore)` inherits
> `_snapshot_for_call`, and `TransformerBuilderSnapshot` has no schema field; neither does
> `TransformerConfig`, nor `get_graph()`. So `ctx.tf = compiled_tf` silently discards the
> schema, and the durable graph format cannot express a compiled transformer at all. The format
> change must therefore **precede** its correctness tests, whereas bash needs only execution.

**The grace hold needs no new mechanism.** A submission stays alive while it has at least one
awaiter; the last awaiter leaving triggers soft-cancel
(`transformation_cache.py:369-406`). Therefore:

- *hold a superseded run* = do not end its adapter task;
- *reinstate a held run* = re-derive, obtain the same `tf_checksum`, submit again, and let
  `_run_active_or_execute` join the still-live submission — there is no resurrection path;
- *`ctx.prune()`* = end the held adapter tasks.

Each held run costs one live task on the E/T loop; the bound is the reactive layer's own
(≤ 3 superseded in-flight runs per node, and the running wavefront is bounded by backend
concurrency). Membership is scoped to the `await` inside `_run_active_or_execute`, so "join
as a member without awaiting" does not exist and the adapter task *is* the membership.

A superseded run whose adapter task is still awaiting will eventually deliver a class-5
completion for a node whose current identity has moved on. Every class-5 message must
therefore carry the identity it belongs to, and the controller must match before acting —
reinstating if that identity is current again, discarding otherwise. For checksum-wired work
the identity is the `tf_checksum` plus run generation. For future-wired work **there is no
`tf_checksum`** (**[MOD-8]**), so the identity is the node path plus run generation.

> **[MOD-11] `eager` and the activity counters have no place in this model.**
> `Context(eager=True)` (the default) evaluates the whole graph on every mutation;
> `eager=False` gates on `active_count` / `derived_active_count` refcounts incremented around
> `_compute_node` (`context.py:1056-1073`). Neither is demand-plus-speculation. Remove the
> flag and both counters; `compute()` becomes `NodeQuiescenceBarrier(X)` + `ReadChecksum(X)`
> (§10), and demand is expressed by interest in cache keys.

Node-state derivation rules and the run ledger are the two parts of the current
implementation worth keeping. The ledger — one current run per node, a bounded superseded
deque, monotonic generations, supersede-on-identity-change, `prune()`
(`seamless_workflow/scheduler.py`) — already has the right shape. Only the thing it points at
must become real: `RunRecord.et` is currently always `None`, and `hold_deadline` /
`hold_kind` / `self_edit_hold_seconds` are written but never read.

## 14. Node states, quiescence, barriers, and lifecycle

### 14.1 The synchronicity contract

This is the contract the current implementation breaks most visibly, and it is prior to every
other item in Part I: **a turn may not deliver a result that has not been computed yet.**

> **A message that makes a node newly eligible to compute leaves it `waiting` in that turn.
> Its result checksum — or its failure — is settled by a later turn, driven by a class-5
> notification. No public operation returns a freshly computed result.**

Measured, today the opposite holds: setting the last missing pin of a transformer returns with
that transformer *and its whole downstream cone* already `complete`, result checksums available,
because the cascade executes the Python callable inline. There is consequently **no observable
`waiting` state**, which has three consequences that compound:

- `quiescent` is vacuously true after every operation, so it means nothing;
- no test can distinguish "computed" from "will be computed", so the state machine is untested
  in the only dimension that matters;
- the public API silently promises synchronous execution, a promise it cannot keep the moment
  execution becomes real (remote, bash, compiled, or merely slow).

**There is no exception for cache hits.** It is tempting to let a turn install `complete`
immediately when the result is already in the in-process transformation cache. It should not:

- The cache check is **not** a local dictionary lookup in its general form. `run()` consults the
  in-process map, then the remote database, then executes; only the first step is instantaneous.
  A general cache check is a coroutine, so it belongs in side work regardless.
- Special-casing the local hit would make the controller reimplement a *partial* prefix of a
  lookup that `transformation_cache.run()` already performs, and the two would have to be kept
  in agreement forever.
- It would make node state **history-dependent**: re-setting a pin to a previously computed
  value would complete in-turn while the first setting did not. Every test asserting `waiting`
  after a write would silently depend on what the process had computed earlier.

So the cache check happens as side work and its outcome arrives as a class-5 notification, one
turn later, hit or miss. The cost is one in-memory turn on the local thread; the gain is that
the rule has no exception to state, test, or get wrong.

This yields a checkable invariant: **no class-2 or class-3 turn ever transitions a node to
`complete` if that node's checksum has to be computed rather than propagated.** Pure
propagation — installing a written checksum, or forwarding one across an alias edge — still
completes in-turn, because nothing is computed. Note the invariant only becomes fully true at
A4: until expression evaluation moves off the controller (§15), sub-value merges still settle
synchronously.

The invalidation half is unchanged and is the other half of the contract: when a node leaves
`complete`, its entire downstream cone leaves `complete` **in the same non-yielding pass**,
before anything is evaluated for firing (§8). A downstream node must never be observable as
`complete` on a stale input.

### 14.2 Quiescence and barriers

`quiescent` keeps its workflow meaning: no node is `waiting` or `computing`. It says nothing
about whether an external source could change in the future, and nothing about whether the
cluster is idle — obsolete runs may still hold slots until their hold windows fire, which is
what `prune()` exists to close.

Because results are no longer synchronous, the public API needs explicit barriers. Two, mirroring
legacy Seamless, where `ctx.compute()` waited for whole-Context quiescence:

```python
ctx.compute()                 # Context-wide: returns when no node is waiting or computing
await ctx.computation()       # the same barrier, without blocking the caller
ctx.a.compute()               # node-local: returns when a's cone is quiescent, then reads a
await ctx.a.computation()
```

The async form is not a convenience. A blocking barrier is unusable in Jupyter and in any
caller that already owns a running loop, which is where interactive workflow use actually
happens; and the mid-computation tests of §15 A0 need to observe state without occupying the
thread that would otherwise be inspecting it. ~~Neither form takes a timeout: a stuck E/T is a
hang to be caught by the caller's own timeout mechanism, not something a barrier should paper
over by returning as if quiescent.~~ **Superseded by §27:** all four forms take an optional
`timeout`, which defaults to `None`, bounds only the caller's wait, and **raises** on expiry —
so the second half of that sentence survives as the reason expiry raises rather than returns.

`ctx.a.compute()` is the correlated `NodeQuiescenceBarrier(a)` + `ReadChecksum(a)` pair of §10.
For a Transformer node it additionally implies that the node's submission has delivered — which
is not an extra condition but the same one, since the node stays `computing` until the class-5
notification arrives. Where the caller wants the underlying handle instead, `ctx.a()` still
yields a `Transformation` with its own `compute()`; the two must agree on identity
(**[MOD-15]**).

> **[MOD-17] A barrier must never hold the controller's processed frontier.** §11 permits a
> class-1 procedure to stall the frontier. A quiescence barrier is class-1 in *permission* — it
> establishes a before/after boundary — but stalling on one would **deadlock by construction**,
> because reaching quiescence requires the controller to keep processing exactly the class-5
> notifications a stall would defer. A barrier therefore installs a **completion predicate**,
> ends its turn immediately, and has its reply future resolved by whichever later turn first
> satisfies the predicate. The controller re-evaluates outstanding predicates at the end of every
> turn; only the *caller* blocks. Barriers need timeouts (§27), and a barrier installed when its
> predicate already holds resolves in its own turn. A barrier whose timeout expires must
> **withdraw** its predicate as it raises, or short-timeout polling accumulates predicates the
> controller re-evaluates forever (§27.1.5).

### 14.3 Lifecycle and shutdown

Controller shutdown must be explicit and idempotent:

1. stop accepting new ordinary messages;
2. unregister attachment sessions through their normal runtime path;
3. fail outstanding public reply futures;
4. process or reject already accepted E/T notifications according to a documented rule;
5. end adapter tasks and release Context-owned checksum references;
6. stop and join the loop thread.

`Context.__del__` cannot be the primary shutdown mechanism: GC can run on any thread and at
interpreter teardown. It should at most request an idempotent best-effort close. The normal
path is `Context.close()` plus the process-level Seamless shutdown registry
(`seamless.ensure_open` / `seamless.close`), which the workflow layer currently does not
participate in at all.

> **[MOD-5] Never snapshot runtime state to roll back a failed operation.** Transactional
> replacement currently rolls back by `copy.copy`-ing `ContextRuntime`, its `Scheduler` and
> every `RunRecord`, saving per-node state tuples, and reassigning `self._runtime`
> (`context.py:322-443`, ~120 lines). That is sound only while runtime state is inert data.
> Once a `RunRecord` holds an awaiter token or a task handle, restoring a copied runtime
> silently orphans live work — and this is precisely where the "complex continuation logic"
> failure mode would appear. **Stage-and-publish must apply to durable configuration only;
> runtime state gets forward-only repair (supersede/cancel), never restoration.** Decide this
> before A2.

## 15. Controller implementation plan

The plan is organised around a deliberate **limbo**: synchronicity (§14.1) is broken early, on
purpose, before the machinery that replaces it exists. Between A1 and A5 the Context cannot
compute transformer results at all. That is not a risk to be managed but the point — it makes
every subsequent phase's exit evidence a test transition rather than a judgement call, and it
prevents the synchronous evaluator from quietly satisfying tests that the real implementation
would have to satisfy differently.

### A0 — Instrument and specify (no behaviour change)

Everything here is independent of concurrency and can proceed immediately and in parallel.

- Build the materialisation recording mode and pin the **exact expected log** for each public
  operation, starting from current behaviour (**[MOD-14]**). Its sibling,
  `seamless_transformer.observation`, exists: off by default, one line per transformation
  reaching an execution decision — checksum, owner, `cache-hit`/`cache-miss` — recorded both in
  the transformation cache and at the workflow layer's direct callable call, which never reaches
  that cache (§26.5). It is the instrument behind the re-execution measurement below.
- Write the **node-transition tests** against §14.1: setting the last missing pin leaves the
  transformer and its downstream cone `waiting`, with no result checksum; leaving `complete`
  revokes the whole downstream cone in one pass; a failure yields `failed` + `blocked-by-error` downstream; a
  disconnected required pin yields `unwired` + `blocked-by-unwired`. These **fail now**.
- Write the **quiescence-barrier tests** for `ctx.compute()` and `ctx.a.compute()` (§14.2).
  These fail now, vacuously — every node is already `complete`, `Context.compute()` does not
  exist, and `ctx.a.compute()` is pinned by `test_canonical_handles.py:143` as a no-op read
  (`assert ctx.data.compute() == ctx.data.checksum`).

> **Two hazards in the existing state coverage, both of which make the gap look covered.**
>
> **`waiting` is overloaded.** All three assertions in the suite that observe
> `waiting` / `"Status: pending"` run under `Context(eager=False)`
> (`test_state_machine.py:102-103`, `test_canonical_handles.py:162`), where the state is
> produced by one branch — `if not self.eager and node.active_count == 0 and
> node.derived_active_count == 0` (`context.py:975`) — and means *"nobody has demanded this
> yet"*, not *"computation is in flight"*. Under the default `eager=True` no test observes
> `waiting` at all. **Consequence for ordering: [MOD-11] deletes `eager`, and with it the only
> producer of `waiting` and its only three consumers — so the new transition tests must be
> written and passing before `eager` is removed**, or coverage drops to zero with nothing
> turning red.
>
> **`computing` is never assigned.** It appears in the `NodeState` literal, is read by
> `_apply_pending` and `_update_runtime`, and maps to `"Status: pending"` — but no line writes
> it. The state that would mean "an E/T is in flight" does not exist yet, so A0's tests define
> it rather than assert it. Note also that `_PUBLIC_STATUS` maps both `waiting` and `computing`
> to `"Status: pending"`, so transition tests must assert on internal state, not public status.
>
> Glitch-freedom (§8) is the one property that cannot be tested in A0: synchronously it is
> trivially true and unobservable. It becomes an **A1** deliverable — the first phase in which a
> downstream node can be caught `complete` on a stale input.

- Write the **latency test**, which is the one that makes the whole defect self-evident and
  should be written first. A transformer whose body sleeps five seconds:

  ```text
  set the last pin        -> returns in well under a second
                          -> state is computing, no result checksum
  during the next ~5 s    -> state stays computing
  ctx.compute()           -> takes ~5 s, then state is complete
  connect a downstream    -> returns promptly; downstream is waiting, not computing
  ```

  Measured on the current implementation with a two-second body: setting the last pin blocks
  the caller **2.0 s** and returns `complete`; then connecting one downstream transformer blocks
  **6.0 s** and re-executes the body **four more times**. At five seconds those become 5 s and
  15 s. The absence of this test is why every other gap in this list stayed invisible.
  Counted rather than timed (§26.1), the same graph writes **eight `cache-miss` lines** to the
  observation log for one transformation checksum, under two node labels, so the convergence
  passes can be read off it directly.

> **Note: mine the legacy test suite first.** `/home/agent/legacy-seamless/tests` holds ~296
> integration tests, and they are **nearly all of the two shapes above**: **271 call
> `ctx.compute()` / `equilibrate`** and **47 use `time.sleep`** — a sleeping transformer observed
> across a barrier, or an edit-then-recompute sequence. Two details worth taking directly:
> legacy `ctx.compute()` accepted a **timeout** (`compute(0.5)`), which is what makes
> intermediate state observable — but only because in legacy the event loop ran in the caller's
> thread, so `compute()` *was the pump* and nothing progressed without it. A dedicated controller
> thread removes that role (§4), so a plain `sleep(X)` — or `await asyncio.sleep(X)` — observes
> mid-computation state just as well. **Do not port the timeout**; port the requirement it was
> standing in for, which is an async barrier (below). They are print-based characterization
> scripts, so porting means converting expected stdout into assertions.
>
> Legacy's **`preliminary`** result is deliberately *not* ported. It is not a stale value: legacy
> injects `return_preliminary()` into the transformer namespace
> (`seamless/workflow/core/execute.py:205`) so that running code can emit intermediate results —
> progress, best-so-far — each of which becomes the node's value until the final result arrives.
> The friction is with identity itself: `tf_checksum -> result_checksum` stops being a function,
> since one transformation identity emits a sequence; which value you observe depends on when
> you looked; and `return_preliminary` writes those buffers to the shared hashserver, where
> nothing distinguishes them from final results. A downstream consuming one acquires a
> `tf_checksum` built from an arbitrary mid-run snapshot.
>
> The need behind it is real for long computations. It belongs on the **runtime-status channel,
> not the value channel**: progress is a class-5 fact, and §6 already requires class-5 messages
> to change availability and runtime status while introducing no authoritative input. Emitting
> progress must therefore never install a node checksum. Legacy tests asserting `preliminary`
> are ported as progress assertions, not as value assertions.

- Write the **non-Python correctness tests**, and land the one-branch fix that stops reporting
  `complete` for a node with no executable code (**[MOD-15]**).
- Write **expression-correctness tests** over Cell-only Contexts with deep and wide dependency
  trees — sub-path sources, sub-path targets, chained projections, diamonds. These pass now and
  must keep passing; they are the regression net for **[MOD-3]**.
- Fix `Expression` to claim its `input_ref`, and add a lifetime test (**[MOD-16]**).
- Settle the semantic decisions: **[MOD-1]** (decided: assignment detaches, `.set()` does not),
  **[MOD-2]**, **[MOD-4]**, **[MOD-7]**.

**Exit evidence:** a red suite that describes the intended contract, and a green materialisation
log that describes the current one.

### A1 — Break synchronicity (enter limbo)

- Disable API-triggered evaluation of Python transformer code in the cascade.
- Node-transition tests now **pass**.
- Quiescence-barrier tests and all post-quiescence correctness tests now **fail**; mark them
  `xfail(strict=True)` so that accidentally passing one is itself an error.

> **Limbo is larger and dirtier than "disable one call" suggests.** Measured by monkeypatching
> `_derive_transformer` to stop at `waiting`: **34 of ~60 tests fail, across 10 of 13 files.**
> The patch itself is ~15 lines, so the breaking is indeed easy; the triage is the work.
>
> - **Eight failures are lifecycle/GC tests, not correctness tests** —
>   `test_garbage_collection.py` (3), `test_literal_retention.py` (2/2),
>   `test_reference_lifecycle_binding.py` (2), `test_reference_lifecycle_forced_expiry.py` (1).
>   They fail arithmetically, because a transformer that never computes holds no
>   `node:…:current` claim (`assert 3 == 4`, `assert 0 == 1`, `assert None is not None`). These
>   want **re-baselining, not `xfail`** — and re-baselining to limbo values means re-baselining
>   again at A4. The reference-lifecycle suite is the coverage least affordable to lose during a
>   restructure, and limbo removes it for the duration.
> - **Audit-based tests are order-coupled, and `xfail` does not fix it.**
>   `test_failed_transformer_replacement_restores_graph_and_roles` fails under limbo with
>   `Checksum … has refholder count 1 but only 0 live claims`, yet **passes in isolation**;
>   running it immediately after the preceding failing test reproduces the failure. One genuine
>   failure manufactures spurious audit failures downstream through process-global cache state,
>   and an `xfail`ed test still runs and still pollutes. **A0 must add a per-test cache and
>   refholder-registry reset fixture; it gates A1.**

**Exit evidence:** the state machine is correct and the Context computes nothing.

### A2 — Class-2 inbox

- Introduce immutable message envelopes, the sequenced ingress gateway, and the controller
  thread with identity assertions.
- Route topology and configuration through class-2 messages, collapsed into one parameterised
  message (**[MOD-6]**), including the compound detach half of **[MOD-1]**.
- Replace snapshot-rollback with stage-and-publish over durable configuration only
  (**[MOD-5]**).
- Remove `eager` and the activity counters (**[MOD-11]**).

**Exit evidence:** node-transition tests still pass, unchanged. Concurrent submitters receive
one total acceptance order; graph mutations occur only on the controller thread.

### A3 — Classes 1, 3, 4, and class-5 **E**

- Implement procedural messages, authoritative writes (**[MOD-2]**), reads with leases acquired
  inside the reading turn (**[MOD-16]**), and barriers as completion predicates (**[MOD-17]**).
- Excise materialisation from the cascade (**[MOD-12]**); the recorded log shrinks to its
  intended shape.
- Implement the three-phase optimistic sub-path update with bounded retry (§9).
- Replace the private sub-path evaluator with synchronous `evaluate_expression` (**[MOD-3]**).

> **Expression evaluation does not need class 5 yet.** `evaluate_expression` is local,
> synchronous and fast — a buffer index and a re-serialisation, no user code and no remote call.
> So **[MOD-3]** can land here as a *synchronous* replacement of the private sub-path evaluator:
> the Context gains the shared content-addressed expression cache and sheds its shadow
> implementation, while cell checksums still settle inside the turn. Only remote expression
> evaluation and expression cancellation need notifications, and they arrive with class 5 in A4.
>
> This is what keeps A1–A3 testable with plain reads. Public calls block their callers (I2), so
> for a single-threaded user with no attachments the **inbox is empty between calls** and the
> Context is fully settled when each one returns. `ReadChecksum` may therefore be a direct read
> of graph state until A4, when it becomes a real class-4 message.
>
> One branch does *not* get exercised for free as a result. With side work synchronous, the
> optimistic sub-path commit never sees an invalidated precondition, so its retry path would
> ship untested into A4. Force it here with a deliberately injected message between the two
> turns (a test hook, or a second thread), rather than waiting for concurrency to arrive and
> discover the branch was wrong.

**Exit evidence:** quiescence-barrier tests and the Cell-only expression-correctness tests pass,
and their `xfail` markers come off. Tests that alternate topology changes, barriers and value
reads in both orders pass. An injected interleave forces the optimistic-commit retry branch. A
turn performs no user-code execution and no buffer I/O. Contexts containing transformers still
cannot compute.

### A4 — Class 5 and the reactive engine (exit limbo)

**This is the phase in which a `Context` becomes a *Seamless* Context.** Everything before it
improves a Python graph that happens to store checksums; this one deletes the Python graph's
engine and connects the workflow layer to the ordinary Seamless transformer machinery.

Concretely, `result = cfg.callable(**kwargs)` in `_derive_transformer` — the raw in-process call
that is the whole reason none of the rest works — is **removed, not wrapped and not made
asynchronous**. With it go the `value_for_checksum` calls that materialise pin values purely to
build those `kwargs`; the transformation dict takes checksums, so the values are never needed
controller-side at all. `TransformerConfig.callable` survives only as *signature metadata* for
`check_pin_name`; it is never invoked again.

What replaces it is not new machinery. It is the same path a standalone `delayed(f)` already
takes: pretransformation → transformation dict → `tf_checksum` → `transformation_cache.run()` →
worker. From this point a Context transformer and a `delayed` transformer are **the same
computation**, keyed the same way, hitting the same cache entry. That single fact is what
delivers, all at once and not before:

- **non-Python execution** — bash and compiled transformers run, because execution happens in a
  worker rather than through Python `__call__`;
- **a live execution envelope** — `modules`, `globals`, `environment`, `scratch`, `local`,
  `direct_print` stop being inert graph decoration;
- **execution backends** — `process`, `spawn`, `remote: jobserver`, `remote: daskserver` become
  reachable from a Context at all;
- **reuse** — across Contexts, across processes, and with `direct`/`delayed`, because for the
  first time there is a key to reuse *by*;
- **execution records** in `seamless.db`, one per `tf_checksum`, which is also what makes the
  supersession tests below measurable.

One deletion worth taking deliberately: `set_graph` currently `exec()`s a node's code text to
recover a callable to invoke (`context.py:1211-1225`). Once execution goes through the worker
that reconstruction is dead weight, and removing it also removes arbitrary code execution on
graph load.

Nothing built in A0–A3 changes here — the derivation rules, the state machine, authority and
refholding are all preserved. Only the engine underneath them is swapped.

- Submit transformations through the transformation cache on a dedicated loop, and route
  completions back as class-5 messages (**[MOD-8]**, **[MOD-10]**).
- Turn reads into real class-4 messages, and expression evaluation into class-5 notifications
  (remote evaluation, cancellation).
- Add the transition test that §14.1 defers to here: a transformation whose result is already
  cached still leaves its node `waiting` for one turn and completes via class 5, never in-turn.
- Carry the node's stored execution envelope into the submission, and make `ctx.tf()` and the
  controller agree on `tf_checksum` (**[MOD-15]**).
- Implement supersession, grace holds and `prune()` against the existing run ledger.

- Write the **supersession tests**, which cannot exist before this phase. Using sleeping bodies
  and an **execution counter as the primary observable** — wall-clock is flaky under load and
  infers what you want rather than measuring it; the built-in instruments are the
  per-`tf_checksum` execution record in `seamless.db` and `seamless_transformer.observation`
  (§26.5), which by this phase sees every execution, because A4 is the phase in which they all
  go through the transformation cache:

  | scenario | construction | assertion |
  |---|---|---|
  | inconsequential upstream edit | `B: return 42` -> `return 6*7` — new code checksum, identical result checksum | `A`'s body runs **once**: `A`'s `tf_checksum` is unchanged, so its in-flight run is re-latched, not restarted |
  | consequential upstream edit | `B`'s result changes | `A`'s body runs **twice**: the first run is superseded and a new one launched |
  | self-edit revert | edit `B`'s own code, revert it inside the hold window | `B`'s body runs **once**; this is the only test that exercises `self_edit_hold_seconds`, currently written and never read |

  Keep timing as a loose upper bound, never as the assertion.

**Exit evidence:** the decisive test is one line — **the same computation expressed as `ctx.tf`
and as `delayed(f)(…)` produces the same `tf_checksum` and hits the same cache entry.** Nothing
short of the full swap can make it pass, and no amount of the preceding work can. Alongside it:
every remaining `xfail` comes off, including the non-Python correctness tests; `grep -c
tf_checksum seamless-workflow/` stops returning zero; a user edit racing an E/T result behaves
correctly in both accepted orders; and a superseded run completing after its node has moved on
is discarded or reinstated by identity, never misapplied.

### A5 — Lifecycle and shutdown

- Integrate the settled checksum-ownership API.
- Define close, late notification, cancellation, GC and interpreter-shutdown behaviour; join
  the process-level shutdown registry.
- Stress repeated Context construction/destruction and stalled E/T.

**Exit evidence:** no hanging futures, surviving controller threads, orphaned adapter tasks or
leaked refholder roles after close.

---

# Part II — Attachments and file mounts

## 16. Attachment boundary

An attachment connects one stable `NodePath` to an external producer, consumer, or both:

- **sense:** external state becomes a value perturbation of the node (class 3);
- **actuate:** a complete node value is delivered externally after a turn.

The common abstraction stays narrow. It defines identity, direction, error state, message
ownership and delivery discipline. It does not pretend that all transports share filesystem
stamps, traitlet callback recursion, web acknowledgements or one conflict policy. Echo and
conflict detection use a common place in the runtime session but are driver-specific
protocols.

Attachments are a Context feature. Standalone `Cell` mounting stays out of scope: it has no
controller, no `NodePath` and no workflow update stream.

### 16.1 Specification versus runtime session

The node owns a durable, serializable **specification**:

```text
AttachmentSpec(driver, direction, driver_config, policy)
```

The Context runtime owns an ephemeral **session**:

```text
AttachmentSession(
    attachment_id,
    generation,
    node_path,
    transport_registration,
    last_sensed,
    last_delivered,
    pending_delivery,
    in_flight_delivery,
    error,
)
```

Separating them keeps transport handles, futures, buffers, locks and refholder leases out of
graph serialization and copying. Replacing, removing or reloading a spec creates a new
monotonically increasing `generation`; messages from old sessions are harmlessly discarded.

Note that this is the same hazard **[MOD-5]** identifies for run records: a session is live
runtime state and must never be restored from a copy.

## 17. Filesystem service and protocols

The filesystem side is process-global, so polling and I/O resources are shared and paths can
be checked for in-process conflicts. It has two distinct internal roles.

### 17.1 Watch broker

The broker registers `(attachment_id, generation, path, watch options)`, observes cheap
metadata/events, and emits internal dirty records:

```text
Dirty(attachment_id, generation, watch_sequence, fingerprint)
```

It does not read files, hash buffers, scan large directories synchronously, resolve checksums
or call a Context. Polling is sufficient first; inotify/watchdog can be an optional producer of
the same records.

The broker is primarily a **read-side sensor**. Normal outbound writes go directly to the I/O
service. A write-only mount may still be watched to detect foreign modification and reassert
its value, but that is mount policy using the same sensor — not the ordinary write route.

### 17.2 I/O pool

The I/O pool performs stable reads, hashing, directory scans and atomic writes. For a file
read it compares metadata before and after reading and retries/discards if the file changed
during the read. It produces the semantic inbound message:

```text
Observation(
    attachment_id,
    generation,
    watch_sequence,
    fingerprint,
    checksum,
    buffer,
)
```

So what crosses from global to per-workflow is **an explicit immutable buffer observation at
the semantic boundary**. A mere dirty bit stays inside the global service, where it can be
coalesced before any Context ordering claim is made.

The reverse message is:

```text
Delivery(
    attachment_id,
    generation,
    delivery_sequence,
    payload,             # live Buffer, or checksum plus lease
    driver_options,
)
```

and completion is:

```text
DeliveryAck(
    attachment_id,
    generation,
    delivery_sequence,
    written_checksum,
    resulting_fingerprint,
    error | None,
)
```

Neither service holds node objects or accesses graph state. Routing back to a closed Context
is a failed/stale delivery, not a graph callback.

## 18. Sense semantics

An observation enters ingress as an immutable class-3 message. The controller then:

1. checks attachment id and generation;
2. rejects duplicate or stale watch sequences;
3. performs mount-specific echo suppression;
4. validates that the attachment may produce the node — the same topology-only authority
   decision as a user write (§6, class 3);
5. installs the buffer's checksum as an ordinary authoritative value edit; and
6. runs a normal turn.

The `Buffer` is intentionally present. If only a dirty path were sent, each Context would
have to perform or schedule filesystem I/O, duplicate reads for shared observations, and
define what "the event" meant after the file changed again. If only a checksum were sent, its
resolvability and reference lifetime would become an implicit cross-system precondition.

### 18.1 Coalescing

The watch broker may collapse a burst of dirty notifications for one registration before or
during a stable read, retaining enough `watch_sequence` information for barriers (§21). Once
an `Observation` is accepted by a Context it is neither mutable nor replaceable.
Controller-side compaction, if added, obeys §5.3.

## 19. Actuate semantics and checksum lifecycle

After a turn, an attachment runtime may produce a delivery only when its node is `complete`.
Transient `waiting`, `computing`, `blocked` and `failed` states do not delete or rewrite the
external artifact. Deletion is an explicit node deletion or unmount policy.

Snapshot transports such as files use `latest` delivery discipline: a queued but not yet
started delivery may be superseded. An in-flight write is not silently cancelled; its ack is
processed, then the newer value is written if still needed. Log-like future drivers may need
`every`, but mounts do not.

The payload has two legal forms: a live local `Buffer`, captured without blocking; or a
checksum with an attachment-owned refholder lease acquired before control yields. The lease
role is derived from the pending/in-flight delivery record, e.g.
`attachment:<id>:delivery:<sequence>`, and is released on supersession, acknowledgement,
timeout, generation replacement or shutdown. A bare checksum that may later be resolved is not
a legal delivery payload.

Comparison-only checksums such as `last_sensed_checksum` and `last_delivered_checksum` are
declared lifecycle exemptions and are never resolved.

Delivery errors belong to the attachment session. They do not make a valid node value failed.
Timeouts bound both external hangs and lease duration.

## 20. File-mount semantics

### 20.1 Port legacy policy as a decision table

The valuable legacy behaviour is the initialisation table over:

```text
authority in {cell, file, file-strict}
mode in {r, w, rw}
path exists?
node has a value?
```

Port this table directly, with a test for every meaningful cell. `authority` chooses the
winner when attaching an existing node to an existing file. It does not silently become a
permanent prohibition on later user assignment.

In particular, legacy `rw` plus cell-side assignment writes the new value to the file; the
next poll is normally an echo and does not revert it. If continuous external ownership is
wanted, add a distinct option such as `edit_policy="external-owned"` and specify it
separately. Calling that behaviour `authority="file"` would be an incompatible semantic change
hidden under a familiar option.

The ongoing behaviour of each mode — including user edits in `r`, detection of foreign changes
in `w`, deletion, and `persistent` — should be captured from legacy with characterization tests
before choosing any intentional deviation.

### 20.2 Reads and writes

Use the legacy mtime/event plus checksum double guard: metadata decides whether a read is
worth doing; content checksum decides whether a semantic change occurred.

Writes use a uniquely named temporary file in the target directory followed by atomic replace.
The resulting fingerprint and checksum return in `DeliveryAck` and participate in
driver-specific echo suppression. Checksums, not mtimes alone, remain the correctness guard.

Canonical byte rules must be explicit per supported celltype. Text newline normalization and
structured-text normalization cannot remain mount-local patches that make write bytes differ
from canonical buffer bytes. Non-canonical formats require an explicit serializer/disposition
or are not directly mountable. This is the same canonicality requirement that **[MOD-2]** makes
for checksum writes, seen from the transport side.

Directory mounts reuse deep-folder representation and hold the top-level checksum, not
recursive member references. Recursive scanning and materialization run in the I/O pool and
need limits and cancellation, because they may be expensive.

### 20.3 Echoes and shared paths

The global registry rejects incompatible overlapping paths in-process after path
normalization. Any overlap involving actuation or directory cleanup is incompatible;
independent read-only registrations may be permitted or internally shared. File/directory
prefix overlap needs the same compatibility check, not merely exact path equality. This is a
safety check, not a complete exclusivity guarantee: other processes, hardlinks, bind mounts,
case folding and some network filesystem aliases remain outside it.

Echo suppression is a mount-session protocol using observation fingerprints, delivery
acknowledgements and checksums. It must tolerate atomic replace and identical-content
rewrites. A generic attachment layer should provide state storage and message correlation but
not prescribe filesystem causality for future traitlet/share drivers.

**Cross-process write fights need a detector, because the in-process registry cannot see them
and legacy actively causes them.** `conditional_read` prints *"write-only file %s (%s) has
changed on disk, overruling"* and rewrites (`mount.py:492-499`), so two legacy contexts sharing
a path fight at the poll rate indefinitely. Two notebooks or two script runs on one file is the
*common* accident, not an exotic one.

A foreign write is not itself the signal — under a file-authority mount it is the entire point,
i.e. the user editing in vim. The signal is narrower: *our actuation restoring a value a foreign
writer had just replaced.*

```text
we deliver C1  →  we observe foreign C2 ≠ C1  →  we deliver C1 again
```

Count these alternations per session; **trip at three within a rolling 10–30 s window (default
20 s)**. The window matters: a human doing a slow edit-and-revert cycle over hours produces the
same signature with no conflict present, whereas a genuine two-writer fight runs at the poll
rate and crosses the threshold in under a second. On trip: stop actuating, record a
`ConflictError` in the session error slot, log once with the path and the alternating
checksums, and keep sensing if the mode contains `r` — tracking the other writer beats
diverging silently. A `w`-only attachment stops both directions, since an actuator that cannot
own its resource is useless and must be loud. Recovery is manual via `clear_error()`.

**Scope, stated so it is not overread.** The detector finds *oscillation*. It does not fire on
two `rw` mounts over independent nodes, which converge on last-writer with no error at all —
that regime silently couples two workflows through the filesystem, so that B's results depend on
whether A was running. It is refused in-process; across processes it is invisible to any
mechanism here and must be a documented warning, not a promise of detection.

The detector is a counter and a timestamp over state the session already keeps for echo
suppression, so it belongs in M4 with the rest of echo correlation rather than in hardening.

Legacy remount garbage delays, translation-time graph scans, `must_run_mount` and symlink
`LinkItem`s are not ported. Stable node identity and explicit sessions remove their original
reason to exist.

## 21. Quiescence, barriers, and `settled()`

"Every attachment inbox entry applied" is insufficient, because a watcher can always be between
detecting a change and finishing its read. `settled()` needs a finite cut, not a glance at
several empty queues.

`ctx.mount.sync()` requests a barrier from the filesystem service. One barrier round is:

1. the broker completes a scan/event cut and returns a per-registration watch sequence;
2. every dirty record at or below that cut resolves to an observation or an explicit
   unchanged/error result;
3. those results are accepted and processed by the controller;
4. resulting workflow computation reaches graph quiescence;
5. all deliveries caused up to that point receive acknowledgements; and
6. the controller processes those acknowledgements.

A delivery in step 5 can itself create a watch event after the original cut, so `sync()`
requests another broker cut after the deliveries and repeats the round. It returns only after a
round produces no new semantic observation, graph work or delivery. Own-write events should
normally be consumed as echoes in the final round; a genuine concurrent foreign write starts
another round.

The returned condition is **settled through final barrier B**. A file change after B is outside
the promise and may immediately perturb the Context again. Continuous external mutation can
prevent convergence and must be bounded by a timeout.

This protocol requires source `watch_sequence`, attachment `generation`, Context acceptance
sequence and delivery sequence. They solve different problems and must not be collapsed into
one counter.

An explicitly requested external barrier is application-visible synchronisation, not
infrastructure needed to stop ordinary controller races. Its waiting and external I/O use side
work and completion futures. Whether it deliberately gates later checksum messages is part of
that API's finite-cut contract, not a requirement imposed by reads, writes or E/T.

Public naming remains provisional:

```python
ctx.a.mount(path, mode="rw", authority="file", persistent=True)
del ctx.a.mount

ctx.a.mount.error
ctx.a.mount.clear_error()

ctx.mount.sync()       # establish and wait through an external barrier
ctx.quiescent()        # graph only
ctx.settled()          # if retained, a barrier operation, not a timeless predicate
```

## 22. Mount implementation plan

### M1 — Characterize and specify legacy mount behaviour

- Turn the legacy initialisation state machine into a table and golden tests.
- Characterize user edits and external changes in each mode after initialisation.
- Decide and document intentional incompatibilities rather than deriving policy from the new
  concurrency architecture.
- Define mountable celltypes and canonical byte rules.

**Exit evidence:** mode/authority behaviour can be reviewed without controller or watcher code.

### M2 — Attachment specs and sessions with a manual transport

- Add node-owned serializable specs and Context-owned runtime sessions.
- Implement generation invalidation, sense and actuate messages, error slots and explicit
  unmount.
- Use a deterministic manual transport with caller-supplied buffers and captured deliveries.
- Integrate delivery leases with the checksum lifecycle implementation.

**Exit evidence:** controller tests can interleave user edits, E/T results, observations,
unmount and stale-generation completions without touching the real filesystem.

### M3 — The global filesystem service

- Add registration and normalized-path overlap checks.
- Implement the polling broker and a bounded I/O pool as separate components.
- Produce stable-read `Observation`s with buffers and checksums.
- Implement atomic file delivery and correlated acknowledgements.
- Ensure no global component stores node/Context objects or bare resolvable checksums.

**Exit evidence:** service-level tests cover rewrite-during-read, identical-content touch,
atomic replacement, write failure, timeout, unregister races and stale generations.

### M4 — Connect file mounts and echo suppression

- Apply the legacy policy table at attachment creation.
- Implement file-specific echo correlation and latest-delivery supersession.
- Implement the oscillation detector (§20.3) on the same session state as echo correlation.
- Test both orders of user edit versus observation, and E/T result versus observation.
- Test foreign modification of `w` and `rw` modes against the characterized contract.

**Exit evidence:** deterministic integration tests use barriers rather than polling sleeps; a
simulated foreign writer trips the detector within its window, and a slow human edit-and-revert
across the window does not.

### M5 — Sync barriers and directory mounts

- Implement the watch-cut/observation/delivery barrier protocol.
- Add directory stable reads and an atomic-enough materialization policy.
- Exercise large trees, cancellation, partial failure and cleanup behaviour.

**Exit evidence:** `sync()` has a precise finite guarantee and tests never infer settledness
from temporarily empty queues.

### M6 — Harden and generalize

- Measure watcher load, thread count, controller round-trip latency and buffer retention.
- Add optional native filesystem notifications only behind the same broker contract.
- Tune the oscillation detector's threshold and window against observed behaviour; M4 ships
  with defaults, not with evidence.
- Validate the narrow attachment contract with one further driver (traitlet or share) before
  declaring it generic.

---

# Part III — Sequencing and open decisions

## 23. Dependency order

```text
M1 legacy characterization ───────────────────────────────┐
                                                          ▼
checksum lifecycle reaches stable refholder API      M2 → M3 → M4 → M5 → M6
                    │                                  ▲
                    ▼                                  │
     A0 → A1 → A2 → A3 → A4 → A5 ──────────────────────┘
```

M1 is read-only specification work and can proceed earliest, alongside A0, which is likewise
independent of every concurrency question. M2 requires a usable controller ingress and turn
boundary (A2); M2's outbound delivery requires stable refholder APIs. Real
filesystem work must not be used to debug controller ordering.

The controller migration is the higher-risk architectural change and deserves its own design
review, benchmarks and merge boundary before mount mechanics are layered on top. Conversely,
mount-specific questions must not delay routing E/T results through the controller.

## 24. Open decisions

**Semantics that the current code decides differently (settle in A0):**

1. ~~May a value write to a connected sub-path silently detach it?~~ **Decided
   (**[MOD-1]**):** assignment syntax detaches at and below the assigned path and raises on a
   proper ancestor; `.set()` / `.set_checksum()` never detach and raise on any overlapping
   edge. Open corner: whether `.set()` on a path whose *descendant* is connected should raise
   (recommended) or detach.
2. Do integer-indexed connection targets keep a value-dependent bounds check, and if so where
   is it evaluated? (**[MOD-4]**)
3. Does bound view derivation clone, or is it reclassified as configuration mutation?
   (**[MOD-7]**)
4. ~~Does a Context-wide `ctx.compute()` barrier fail, or wait, when part of the graph is
   `blocked` or `failed`?~~ **Decided:** it returns. `blocked` is terminal until a class-2 or
   class-3 message arrives, so waiting for it would hang by construction; quiescence is the
   least-surprising contract, and the caller inspects `.exception`. `compute()` keeps returning
   a checksum where the standalone form does — quiescence is an added guarantee, not a
   replacement.
5. **What exactly does `waiting` mean?** Two readings are in play and they need different
   mechanisms: *(a)* inputs not yet concrete, with `computing` covering submitted work whether
   queued or running; or *(b)* not yet executing, so that work queued behind backend concurrency
   is still `waiting`. **(a)** is recommended — it is knowable at dispatch, whereas (b) requires
   the backend to report start-of-execution, which jobserver and Dask may not surface. Under (a)
   a transformer with literal pins goes straight to `computing` and never shows `waiting`; only
   its downstream does. Whichever is chosen must be written down before the first transition
   test, which will otherwise encode its author's reading.

**Contract choices:**

6. What is the shutdown policy for already accepted late E/T notifications?
7. Which existing API exposes explicit Context close and context-manager use?
8. Is controller-thread ownership required for all diagnostic reads, or may a first version
   publish a narrowly defined immutable status snapshot?
9. What are the exact post-initialisation semantics of legacy `r`, `w` and `rw`, especially
   deletion and user assignment, and which deviations are intentional?
10. Which celltypes have canonical file bytes and which require a disposition?
11. Does mounting a scratch result force durable materialization, reject the mount, or make the
   delivery best-effort?
12. What filesystem fingerprint is reliable enough on supported local and network filesystems,
    while retaining checksum as the final correctness guard?
13. Should `settled()` be a blocking barrier operation, or should only `mount.sync()` promise
    external settlement while `settled` remains an inspectable snapshot with weaker semantics?
14. What are the initial limits for I/O workers, directory scans, delivery timeouts, and
    per-Context controller threads?

Concrete queue classes, executor libraries, polling intervals and exception names can wait for
the handoff plans.

## 25. Index of modifications

Each is a constraint imposed by the current implementation; derivation and evidence are in
`context-api-and-et-split-assessment.md`.

| id | subject | nature | where |
|---|---|---|---|
| **MOD-1** | assignment detaches, `.set()` does not; both are one message | **decided** | §6 class 3, §12.2, §24.1 |
| **MOD-2** | `set_checksum` installs, never resolves | named fix | §6 class 3 |
| **MOD-3** | only nodes carry checksums; sub-path reads are E jobs | design restatement + net code deletion | §6 class 4, §10 |
| **MOD-4** | value-dependent connection targets | semantic decision | §6 class 2, §12.2, §24.2 |
| **MOD-5** | never snapshot runtime state for rollback | structural constraint | §14, §16.1 |
| **MOD-6** | one parameterised config message, not fifteen setters | structural constraint | §6 class 2 |
| **MOD-7** | bound view derivation must not mutate the node | bug-shaped decision | §12.1, §24.3 |
| **MOD-8** | one readiness regime per node; future-wiring must not be bypassed | architectural constraint | §13 |
| **MOD-9** | two class-5 messages have no producer | new work or removal | §6 class 5 |
| **MOD-10** | E/T and side work own a separate loop | structural constraint | §4 |
| **MOD-11** | remove `eager` and the activity counters | simplification | §13 |
| **MOD-12** | A1 is materialisation excision, not inventory | plan restatement | §3, §15 |
| **MOD-13** | document that `AuthorityError` can follow paid-for serialisation | clarification | §7 |
| **MOD-14** | make materialisation observable before removing it | test instrument, do first | §3, §15 A0 |
| **MOD-15** | non-Python transformers need correctness tests; stop reporting `complete` | test gap + one-branch fix | §13, §15 A0/A4 |
| **MOD-16** | `Expression` must claim its `input_ref`; leases acquired in-turn | lifetime defect | §7, §15 A0/A3 |
| **MOD-17** | a barrier installs a predicate; it never stalls the frontier; all four forms take a `timeout` that raises | design correction | §14.2, §27 |

---

## 26. Appendix — what building the A0 suite found

The A0 test suite exists: `seamless-workflow/tests/`, 103 tests across
`node-transition/`, `quiescence-barrier/`, `latency/` and `correctness/`, with
29 green and 74 red against the current implementation. Nothing is `xfail`-marked
— that arrives at A1, per §15 — so every test instead carries the phase at which
it is expected to turn green, as a selectable marker (`now` 25, `a1` 24, `a2` 6,
`a3` 5, `a4` 43). Its `README.md` carries the file-by-file table, the legacy
mining record and the open questions.

It is a **fold of two independently written suites.** Two were produced against
this section, `tests/codex/` and `tests/claude/`, and three arbitrations compared
them (`tests/consensus-{gemini,gpt-5.5,sonnet}.md`, kept as the record). All
three converged on the same recommendation, on the merits rather than on this
appendix — one of them says so explicitly, and is right to: §26 was written by
the run that produced `tests/claude/`, so it is that suite documenting itself and
is not evidence about it. Take `claude/` as the base, because it reads node state
through one helper rather than through `ctx._graph` in every file, carries the
phase markers, and counts executions through a file rather than by wall clock;
take `codex/`'s [MOD-16] lifetime test, which `claude/` had recorded as owed
rather than written, and its Context-cleanup fixture; keep `claude/`'s in-place
cache reset rather than `codex/`'s singleton replacement. Both source
directories are retired: one contract, one suite.

The fold departed from the arbitrations in one place, on the project's
instruction, and §27 is the result — see §26.5.

This appendix records only what the body of this document does not already say:
two corrections to the plan, two decisions the tests could not be written without
settling, defects found on the way, and what the fold itself found.

### 26.1 Two corrections to §15

**The failure-propagation transition test cannot be green at A1.** §15 A0 groups
"a failure yields `failed` + `blocked-by-error` downstream" with the other
node-transition tests, and §15 A1 says those pass at A1. They cannot: A1 removes
in-cascade execution, and execution is the *only* producer of `failed` in a
Context. Cell validators are not applied, an alias edge does not enforce the
target celltype, and the two remaining cell-level failure paths
(deeper-than-one-component targets, merges that cannot serialise) raise out of the
public call rather than recording a node failure. During the A1–A3 limbo no node
reaches `failed` at all. The affected tests are therefore marked `a4`. The
`unwired` half of the same bullet is unaffected and is A1 work as written.

**Adding a node to a settled graph is quadratic in bodies run.** §15 A0 records
that connecting one downstream transformer blocks 6.0 s and re-executes a
two-second body "four more times". Measured by counting transformations rather
than wall-clock — through `seamless_transformer.observation`, which records
outside the transformation and therefore keeps working when execution moves to a
worker at A4 (§26.5) — a settled single-transformer graph runs its body **eight
times** where one is correct — seven re-executions across the three public calls that
attach a downstream transformer and its result cell. `_derive_all`
(`context.py:857`) makes up to one convergence pass per node and re-derives every
node in each pass, and derivation is execution, so the multiple grows with graph
size rather than being a fixed penalty per public call. This does not change the
plan; it changes how bad the A1 excision looks from the outside, and it is the
number worth quoting when justifying the phase.

### 26.2 Decisions the tests had to settle

**§24.5 — `waiting` is reading (a).** As §24.5 requires, this was settled before
the first transition test rather than encoded by accident: `waiting` means the
node's inputs are not all concrete checksums; `computing` means they are and the
work has been submitted, queued or running. The visible consequence, asserted
directly, is that a transformer whose pins are all literals goes straight to
`computing` and never shows `waiting` — only its downstream does. The §15 A0
latency script assumes the same thing ("set the last pin -> state is computing").
If the project later chooses reading (b), the assertions to flip are the
`computing` ones in `test_transition_eligibility.py` and
`test_latency_delay_port.py`; every other test is stated as "pending, and no
result checksum", which holds under both readings.

**§14.2 and [MOD-17] disagree about timeouts.** §14.2 said neither barrier form
takes a timeout; [MOD-17] said "barriers need timeouts". The first suite read
them as being about different objects — graph quiescence, versus the §21 external
finite cut and its delivery deadlines — and constrained only the first. Legacy
`ctx.compute(0.5)` conflated three roles: a pump (the loop ran in the caller's
thread, so the barrier was what advanced the graph), an observation window, and a
hang guard. A controller thread deletes the first and a plain `sleep` replaces the
second; the disagreement was only ever about the third.

Whichever way it resolved, one invariant had to hold, and the suite asserts it in
the form that survives either answer: **a barrier never returns a non-quiescent
graph.** A `timeout=` that raises on expiry passes that; one that returns early as
if settled is the pump, and makes "did my computation finish?" unanswerable from
the return value.

**It has since resolved, against §14.2: the parameter is in the API.** §27 has
the decision and the argument — in short, the hang guard turns out not to be
expressible outside the barrier, because the sync form has no caller-side
mechanism at all and `asyncio.wait_for` abandons the async form's [MOD-17]
predicate rather than withdrawing it. `quiescence-barrier/test_barrier_timeout.py`
pins §27.1's four rules; the invariant above is unchanged and is now one of them.

### 26.3 Defects the document does not list

Found while writing the tests, each with a test attached. They are defects in the
current implementation rather than constraints on the design, so they are recorded
here rather than as `[MOD-n]` entries — but the first two are on A0/A2's path.

1. **The cycle check is inverted.** `_add_edge` refuses an edge when
   `_would_cycle(source, target)` (`context.py:712`), and `_would_cycle`
   (`context.py:724`) walks forward *from the source*, returning true if it
   reaches the target. Adding `source -> target` closes a cycle exactly when the
   target already reaches the *source*. Both failure modes follow: a second edge
   from one node into another is refused as a "Dependency cycle" — which is what
   every diamond is, and what `tf.pins.x = ctx.a; tf.pins.y = ctx.a` is — and a
   genuine two-node cycle is accepted, since after `ctx.b = ctx.a` the write
   `ctx.a = ctx.b` installs the back edge without complaint. This is why the
   "diamonds" of §15 A0's expression-correctness bullet are **not** among the
   tests that pass now.
2. **The block reason degrades in both directions.** `_apply_pending`
   (`context.py:995-997`) folds every non-pending upstream state that is not
   `failed`/`blocked` into `blocked-by-error`, so a transformer under an `unwired`
   transformer reports an error that does not exist. `_apply_upstream_state`
   (`context.py:1014-1016`) folds `blocked` and `unwired` into
   `blocked-by-unwired`, so a cell under a *failing* node reports a missing
   connection. A failing transformer therefore reports *error* one hop down and
   *missing connection* two hops down; a disconnected pin reports the opposite.
3. **[MOD-15] is reachable without leaving Python.** The
   `if cfg.callable is None` branch (`context.py:971`) is not only a non-Python
   problem: `ctx.tf.code = None` on a fully wired Python transformer turns
   `Status: OK` with the value 3 into `Status: OK` with `None`, and nothing
   reports that the code is gone. The one-branch fix covers both.
4. **A compiled builder is captured as if it were a Python function.**
   `_assign` tests `isinstance(value, Transformer)` (`context.py:142`) — the
   *Python* subclass — and `CompiledTransformer` is a `TransformerCore` but not a
   `Transformer`, so it falls through to `elif callable(value)`
   (`context.py:144`) and is stored by `_transformer_config_from_code`
   (`context.py:278`) with `language="python"` and the builder object as
   `callable`. So a compiled transformer loses its **language** as well as its
   schema, and configuration fails before execution is ever reached:
   `ctx.tf.pins.a = 2` raises `AttributeError: Unknown transformer pin 'a'`,
   checked against the builder's `(*args, **kwargs)` signature. This strengthens
   [MOD-15]'s sequencing point — compiled is a representation gap first — and adds
   a dispatch fix to it.
5. **A missing key produces a node that is `complete` with no checksum.**
   *Corrected during the fold; the first statement of this finding was wrong.*
   The two cases are not indistinguishable: the projection of a key holding
   `null` carries the checksum of `null`, the projection of an absent key carries
   no checksum at all. What is identical is `state` and `.value` — both
   `complete` and `None` — so a reader who checks either sees a well-formed null.
   The original test appeared to prove indistinguishability, but was failing for
   its own reason (finding 7). The real defect is on the other side of the
   comparison: a node reporting `complete` while holding no checksum, reached
   here without any transformer at all, and its consequence one hop down is worse
   than its cause — a transformer whose pin is fed by the typo'd projection
   reports `unwired`, *a pin is not connected*, when the pin is connected and it
   is the key behind it that does not exist. [MOD-3] moves sub-path reads onto
   `evaluate_expression`, which is where the distinction can be made; the tests
   now pin the surviving distinction as a regression net and require only that a
   node with no checksum stop calling itself `complete`.
6. **`ctx.tf.celltypes` neither normalises nor validates.** The standalone
   `CelltypesWrapper` maps `int -> "int"` and rejects unknown celltypes;
   `WorkflowCelltypes.__setitem__` (`builder_state.py:359-363`) stores
   `str(value)`, so `celltypes.lines = int` records `"<class 'int'>"` and
   `celltypes.other = "not-a-celltype"` is accepted. This is one more entry for
   [MOD-6]'s per-field validator table.

7. **`Checksum.__eq__(None)` raises.** `Checksum(None)` is a `TypeError`, and
   `__eq__` constructs before comparing, so any assertion comparing a checksum
   against a possibly-absent one errors instead of answering. This is a
   test-writing hazard rather than an implementation defect, but a sharp one: it
   turns a *passing* contract into a red test that looks on-topic, which is how
   finding 5 came to be mis-stated. The suite now compares checksums as
   hex-or-`None` through one helper.

### 26.4 What A0 still owes

The suite is the test-writing half. Outstanding from §15 A0: the materialisation
recording mode of **[MOD-14]** and its pinned expected logs — the green half of
A0's exit evidence. Its sibling instrument now exists:
`seamless_transformer.observation` (§26.5) records transformations the same way
[MOD-14] is to record materialisations, off by default, with the same
justification — pin the behaviour before removing it.

Also outstanding: the one-branch fix of **[MOD-15]** (its acceptance test is
written and red); the **[MOD-16]** `Expression.input_ref` fix — its lifetime test
now exists, folded in from the second suite, and is red for the right reason (the
Expression claims nothing at all on its input); and the decisions **[MOD-2]**,
**[MOD-4]**, **[MOD-7]**. **[MOD-17]** versus §14.2 is no longer among them: §27
settles it.

The per-test cache and refholder-registry reset that §15 A1 requires is in place
and has been **lifted to `tests/conftest.py`**, so it covers the pre-existing
top-level suite as well as the contract directories; all 74 of those tests stay
green under it. The pollution it prevents is an A1 phenomenon — it needs a
failing derivation to leave unattributed refholder counts — so today it is
prophylactic.

### 26.5 What the fold found

Three things surfaced only when the two suites were merged and §27 was applied,
each of which changed the suite rather than the design.

**Finding 7 above is why finding 5 was wrong.** A red test that fails inside its
own assertion machinery looks exactly like a red test that fails on its subject.
This is the failure mode a red-by-design suite is most exposed to, since nobody
is surprised when one of its tests fails, and it argues for the same discipline
the arbitrations applied to `codex/`'s missing-barrier crashes: a red test earns
its place by failing for the reason it names.

**The suite's own waiting instrument contradicted §27.** `settle()` — a bounded
poll for quiescence — returned `False` on expiry, which is precisely what §27.1.2
forbids the barrier to do, and it was spelled `settle(ctx, timeout=30)`, which is
what `compute(timeout=30)` will be spelled. Six of its 43 call sites discarded
that `False` deliberately, because they are limbo preconditions that do not
expect quiescence, and nothing at the call site distinguished them from a typo.
It is now three named helpers: `compute_or_settle` (the ordinary wait, 17 tests),
`settle` (raises on expiry, 7 tests), `try_settle` (returns a bool, 6 tests).

**The execution counter was measuring from inside the transformation.** The
downstream re-execution finding of §26.1 was originally counted by having the
transformer body append to a file whose path travelled as an ordinary pin. That
works, and the file was chosen deliberately so the count would survive execution
moving to a worker — but it puts the instrument *inside* the transformation
identity, and its failure mode is asymmetric in the wrong direction. An identity
that accidentally **differs** produces a spurious re-execution: the count rises,
the test fails loudly, someone looks. An identity that accidentally **collides**
produces a spurious cache hit: the count stays low, which reads as "nothing
re-executed" — a *pass*. An instrument whose failure looks like success, sharing
a failure mode with the property under test, is the wrong instrument however
elegant, and it costs more than it saves: it also made the cache-hit tests
express themselves in wall-clock, which §15 A4 warns against.

It is replaced by **`seamless_transformer.observation`**, off-by-default product
machinery recording one line per transformation reaching an execution decision —
transformation checksum, whose it was, and whether a cache answered. This is
[MOD-14]'s category rather than a new one: observability added to the product so
that behaviour can be pinned before it is removed, in A0, alongside the
materialisation recorder that phase already owes. Two consequences worth
recording:

* **It needs two recording sites, and that is the finding.** The transformation
  cache is the obvious home, and a cache-side instrument alone reports *zero* for
  everything A0 measures — because `_derive_transformer` calls the Python
  callable directly (`context.py:979`) and never consults the cache. The second
  site is that call, in the workflow layer, and every line it writes is a
  `cache-miss` by construction. A1 deletes the call and the recording together,
  which is the correct lifetime for an instrument attached to a defect.
* **It makes the finding legible rather than scalar.** The eight executions are
  now eight lines carrying one transformation checksum under two node labels,
  `tf` and `tail` interleaving, so `_derive_all`'s convergence passes can be read
  off the log. The same instrument states the A4 contract as *one miss and zero
  hits* per settled node — separating "it re-ran", which is a correctness defect,
  from "it re-asked and the cache absorbed it", which is only waste.
* **It is the only instrument that can see over-invalidation.** §8's "its entire
  downstream cone" is two claims, and the suite originally tested one: that
  everything *in* the cone is revoked. The complement — that nothing *outside* it
  is — cannot be settled by states and checksums when bodies are deterministic,
  because an over-eagerly revoked node is recomputed and lands on exactly the
  checksum it had, so a before/after comparison passes while the work was thrown
  away. Counting separates "never invalidated" from "invalidated and rebuilt".
  Measured: editing one literal pin re-executes a node sharing *no ancestor* with
  anything in the graph **three more times**. The cheap before/after comparison
  is still worth keeping alongside it, as a phase-robust regression net — stated
  as *unchanged across the edit* rather than as *still complete*, it is
  discriminating today and vacuously true through the limbo — but on its own it
  would have declared the negative half of §8 satisfied.
* **The cache-hit test keeps its clock as well.** The two mechanisms answer
  different questions and can disagree, which is the point of running both: a hit
  that still costs a body duration to deliver — a defect in the delivery path
  rather than the cache — passes the count and fails the clock, while a second
  execution that happens to be cheap passes the clock and fails the count. The
  count is primary, for the reason §15 A4 gives against wall-clock; the clock
  corroborates. It also sharpens the current diagnosis: the two Contexts agree on
  the transformation checksum and record two `cache-miss` lines, so the defect is
  precisely that nothing consults the cache, not that identity is unstable.

**An instrument must not be the thing under test — but neither should it hide
it.** `settle()` is an oracle for exactly one of the barrier's postconditions,
not a reference implementation of it: it never enters the controller, so it
cannot stand in for [MOD-17]'s frontier property; it returns nothing, so it
cannot stand in for §10's correlated barrier-plus-read; and polling can report a
quiescence that was never a stable state. It is therefore kept for three reasons
only — the barrier does not exist yet (`now`/`a1`/`a2` preconditions), the
barrier is the subject, or the barrier would contaminate the measurement (the
execution-counting tests, where a derivation pass inside the barrier would add to
the number being reported). Everything else waits through `ctx.compute()`, which
makes 17 tests across three directories into barrier coverage by construction.
Until A3 that call falls back to polling, deliberately: barrier *existence* is a
separate contract, asserted once and legibly in `test_barrier_context.py`, and
re-asserting it in 17 result tests would replace 17 on-target failures with 17
copies of one missing-attribute message. Existence in one place, behaviour
everywhere.

---

## 27. Appendix — barrier timeouts are part of the API

**This appendix overrules §14.2's "Neither form takes a timeout" and closes the
§14.2 / [MOD-17] disagreement recorded in §26.2.** All four barrier forms take an
optional `timeout`:

```python
ctx.compute(timeout=None)               # Context-wide, blocking
await ctx.computation(timeout=None)     # Context-wide, async
ctx.a.compute(timeout=None)             # node-local, blocking; still returns a checksum
await ctx.a.computation(timeout=None)   # node-local, async
```

### 27.1 The contract

1. **`timeout=None` is the default and means "wait".** With no timeout the
   behaviour is exactly what §14.2 specifies, so nothing that already relied on
   the barrier changes.
2. **On expiry the barrier raises `TimeoutError`. It never returns.** This is
   the whole safety property, and it is what separates a deadline from the
   legacy pump: a barrier that returns early *as if quiescent* makes "did my
   computation finish?" unanswerable from the return value, and silently
   converts every downstream read into a possible stale read. Raising leaves the
   §26.2 invariant intact — **a barrier never returns a non-quiescent graph** —
   because on the timeout path it returns nothing at all.
3. **The timeout bounds the caller's wait and nothing else.** It does not
   cancel, pause, deprioritise or otherwise touch the computation. The graph
   keeps advancing across the expiry, and a second barrier on the same graph
   afterwards returns normally with the result the first one did not wait for.
   A timeout is an observation deadline, never a control operation — control
   operations on running work are `prune()` and cancellation, which are
   different messages with different consequences.
4. **Expiry is still not a pump.** Waiting on a barrier advances nothing, with
   or without a timeout, because the controller thread (§4) — not the caller —
   is what advances the graph. `ctx.compute(0.5)` in legacy *was* the pump; here
   the same call is a bounded look at something that is happening anyway.
   `compute(timeout=X)` and `sleep(X)` differ only in that the first stops early
   when the graph settles and raises when it does not.
5. **Expiry withdraws the predicate.** [MOD-17] has a barrier install a
   completion predicate, end its turn, and let a later turn resolve its reply
   future; the controller re-evaluates outstanding predicates at the end of
   every turn. A timed-out barrier must therefore *withdraw* its predicate as
   part of raising, or a caller that polls with a short timeout accumulates
   predicates the controller re-evaluates forever. This is the one place where
   the timeout is not purely caller-side machinery, and it is the reason the
   parameter belongs in the API at all — see §27.2.

### 27.2 Why the parameter has to exist, rather than being left to the caller

§14.2 argued that a stuck E/T is "a hang to be caught by the caller's own
timeout mechanism". Two things are wrong with leaving it there.

**The synchronous form has no caller-side mechanism.** `asyncio.wait_for` bounds
`await ctx.computation()`; nothing bounds a blocking `ctx.compute()` from
outside except a second thread built for the purpose. The sync form is the one
used from scripts and from Jupyter cells — precisely the callers least equipped
to build that thread, and most likely to meet a graph that never settles.
Offering the deadline only to the async caller makes the safe API the harder one
to reach.

**Even the async form needs the barrier's cooperation.** `asyncio.wait_for`
cancels the awaiting task; under [MOD-17] that cancellation is local to the
caller and says nothing to the controller, so the predicate installed by the
abandoned barrier stays installed and stays re-evaluated. Withdrawal (27.1.5) is
only expressible from inside the barrier. So the choice is not "timeout in the
API or timeout outside it" — it is "timeout in the API, or a predicate leak on
every abandoned wait".

The §26.2 reading of legacy `ctx.compute(0.5)` stands as written; only its
conclusion changes. Of the three roles legacy conflated, the controller thread
still deletes the **pump**, and a plain `sleep` still replaces the **observation
window**. The third — the **hang guard** — is the one this appendix keeps, and
keeps *in the API*, because it turns out not to be expressible outside it.

### 27.3 Consequences elsewhere in this document

* **§14.2** — the sentence "Neither form takes a timeout: a stuck E/T is a hang
  to be caught by the caller's own timeout mechanism, not something a barrier
  should paper over by returning as if quiescent" is superseded by this
  appendix. Its *second* clause survives and is 27.1.2: a barrier must not paper
  over a hang by returning as if quiescent. That is why expiry raises.
* **[MOD-17]** — "Barriers need timeouts" now means what it says, for the
  graph-quiescence barrier as well as for the §21 external finite cut. §26.2
  separated the two objects correctly, but the separation is no longer needed to
  keep the document consistent: both take deadlines, for different reasons — the
  finite cut because external I/O cannot be left unbounded, the quiescence
  barrier because the caller cannot bound it from outside.
* **§21** — unchanged. The external finite cut's delivery deadlines are a
  different mechanism with a different failure semantics (a cut *completes* with
  a recorded shortfall); nothing here merges them.
* **§24** — this is not an open decision any more; it is decided as above.
* **§15 A0** — "**Do not port the timeout**" still holds *as a statement about
  the legacy pump*: what is not ported is a barrier that advances the graph and
  returns early. The parameter name is reused; the semantics are not.
