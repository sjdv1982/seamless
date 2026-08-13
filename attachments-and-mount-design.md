# Context Actor, External Attachments, and File Mounts — Design and Plan

> **Status.** Design-level plan, not an implementation handoff. It deliberately separates
> two concerns that were previously folded together:
>
> 1. a `Context` actor that serializes all workflow state transitions; and
> 2. attachments, with file mounts as the first transport.
>
> The actor is useful without mounts: user edits, job results, cancellation, and future
> external inputs already need one mutation authority. Mounts depend on the actor, but the
> actor must not depend on mount concepts.

This document retains the useful conclusions of the earlier attachment design: one graph
mutator, turn-based propagation, post-cascade actuation, off-controller I/O, explicit
settledness, and a common sense/actuate vocabulary. It changes four important points:

- actor ordering is defined by immutable messages and a single ingress sequence;
- coalescing may not move a later external observation ahead of an intervening user edit;
- mount `authority` keeps its legacy initialisation meaning rather than becoming continuous
  file ownership; and
- file watching, file I/O, and graph mutation are separate roles with explicit protocols.

---

## 1. Why there are two designs

Legacy Seamless implemented mounts, traitlets, and shares with different schedulers, locks,
polling loops, and echo suppressors. The common architectural problem is real: an external
event can arrive while Python user code is idle or while a transformation is running, and it
must eventually become an ordinary workflow perturbation.

That observation does **not** make the Context controller part of an attachment abstraction.
It exposes a more general requirement:

> A current-Seamless `Context` needs one place where all state transitions are ordered and
> applied, regardless of whether mounts are implemented.

The work therefore has two layers:

```text
public calls ─┐
job results ──┼──> Context actor ──> graph state / job submissions
timers ───────┤
attachments ─┘
                         ▲
                         │ immutable attachment messages
                         ▼
              attachment runtime and transports
                         │
                         ▼
                filesystem / widget / network
```

The boundary matters for implementation and review. Actor correctness is about
linearizability, graph ownership, turns, parking, and shutdown. Mount correctness is about
filesystem observation, stable reads, canonical bytes, atomic writes, echo suppression, and
legacy policy. Neither test suite should need the other to explain a failure.

## 2. Decisions at a glance

The current proposed decisions are:

1. **One actor per `Context`, initially.** It owns a dedicated thread and asyncio loop and is
   the sole graph mutator. A global actor remains a possible measured optimisation, not an
   initial semantic choice.
2. **One sequenced ingress per Context.** All user operations, job results, timers, and
   attachment observations enter as immutable messages. The ingress assigns a monotonically
   increasing acceptance sequence.
3. **One message attempt is one turn.** It runs synchronously through validation, graph
   mutation, cascade, job submission, and the collection of outbound effects. No graph code
   awaits.
4. **Parking retries whole attempts.** A public operation that needs a temporarily unavailable
   value yields its place, waits, and is later re-enqueued and revalidated. It never suspends
   a half-applied mutation.
5. **A global filesystem service has two internal roles.** A cheap watch broker detects dirty
   paths; an I/O pool performs stable reads, hashing, directory scans, and writes. Neither
   knows about graph state.
6. **The semantic inbound boundary carries content.** The Context receives an immutable
   observation containing a checksum and `Buffer` (plus identity and version metadata), not
   merely “this file is dirty.” Dirty notifications remain internal to the filesystem
   service.
7. **Outbound delivery carries a usable payload.** It contains either a live `Buffer`, or a
   checksum backed by an explicit refholder lease. It is not a bare request to resolve an
   unowned checksum later.
8. **Durable attachment specifications and runtime sessions are separate.** The node stores
   configuration; the Context runtime owns queues, generation numbers, errors, pending
   deliveries, and transport registrations.
9. **`quiescent` remains graph-only.** `sync()`/`settled()` use a filesystem barrier and
   delivery acknowledgements to define a finite external cut.
10. **Legacy mount authority is not silently redefined.** It resolves the initial
    file-versus-cell conflict. Continuous external ownership, if wanted, is a new policy with
    a new name.

---

# Part I — The Context actor core

## 3. Scope and invariant

The actor project covers:

- ownership of mutable Context graph and runtime state;
- synchronous and asynchronous ingress;
- ordering and turn execution;
- job-result re-entry;
- parking and retry;
- public exception propagation;
- graph quiescence; and
- lifecycle, shutdown, and diagnostics.

It does not know about paths, mtimes, file modes, mount authority, filesystem errors, or echo
suppression.

Its load-bearing invariant is:

> Only the Context actor thread may read or mutate live graph runtime state. Code that touches
> that state is synchronous and non-yielding.

“Read” is included deliberately. Allowing arbitrary threads to inspect mutable graph objects
would replace mutation races with snapshot races and eventually require graph-wide locks.
Public reads initially round-trip through the actor. A published immutable snapshot can be
added later if profiling justifies the second read path.

## 4. Why an actor thread

A dedicated actor thread works in scripts, plain Python, terminal IPython, and Jupyter. It can
apply job results and mount observations while the user is idle; it does not depend on the
caller's event loop or on a later call to `compute()` to pump an inbox.

The main alternatives are weaker:

- **A graph mutex with mutation from arbitrary threads** serializes bytes of execution but
  gives no ownership model. It makes re-entry, lock-held callbacks, parking, and thread-affine
  code difficult to reason about.
- **A main-thread inbox** needs an event pump that plain Python does not provide while idle.
  Draining only on public calls changes the semantics of background completion.
- **One global actor for every Context** preserves the actor model, but introduces
  cross-Context head-of-line blocking and failure coupling. It may become worthwhile if large
  numbers of Context threads are measured to be a problem.

Asyncio is an implementation tool, not the essential idea. The essential idea is a single
owner and sequenced mailbox. A loop is useful for timers, reply futures, cancellation, and
parking, while all graph-touching code remains ordinary `def` code.

Job execution remains off-controller. The actor submits work and later accepts immutable job
result messages. It never awaits transformation execution, remote transfer, buffer resolution,
or user transformer code on its own loop.

## 5. Ingress and linearization

### 5.1 One gateway

Every source submits through one small thread-safe Context ingress gateway. Under a short
ingress lock, the gateway:

1. verifies that the Context is accepting messages;
2. assigns `context_sequence += 1`;
3. freezes an immutable message envelope; and
4. wakes the actor loop.

The lock protects only acceptance and queue insertion. It is never held while graph code,
callbacks, hashing, or I/O run.

A message envelope contains at least:

```text
ContextMessage(
    context_id,
    context_sequence,
    kind,
    payload,
    reply_future | None,
)
```

Source-specific payloads may carry their own sequence and generation fields, but those do not
replace `context_sequence`.

### 5.2 The ordering contract

An operation linearizes when the ingress accepts its immutable message, not when an OS event
occurred and not when some producer began preparing the payload.

- If message A is accepted before message B, A gets the first attempt.
- If two threads submit concurrently, either order is legal; the ingress lock chooses it.
- The actor provides ordering, not semantic precedence. Whether a later mount observation
  overrides a user edit is a mount-mode/policy question.
- A parked operation gives up its queue position. Its retry is a new attempt after whatever
  messages ran while it was parked, and it revalidates against their effects.

This is the answer to the “user update and mount message are both in the inbox” race. There is
no special winner: the accepted order is the order. Truly simultaneous events have no natural
cross-thread order for Seamless to discover.

### 5.3 Messages must not change after acceptance

The earlier mutable coalescing-slot proposal is invalid. Consider:

```text
accept mount observation M1 and schedule its callback
accept user edit U
transport overwrites M1's slot with later observation M2
run the scheduled callback, which now applies M2
run U
```

M2 was accepted after U in real submission order but is applied before it. The actor would no
longer be linearizable.

Therefore:

- an accepted message is immutable;
- a queued callback may not read a transport slot that later writers can overwrite;
- the transport may coalesce dirty events **before** producing a Context observation, because
  they have not yet entered Context ordering; and
- the actor may coalesce only a contiguous run of compatible messages, never across an
  intervening user operation, job result, barrier, or incompatible observation.

The simplest first implementation is no actor-side coalescing. Add bounded, adjacency-
preserving compaction only after realistic event-rate measurements.

## 6. Turns and effects

A turn is one non-yielding message attempt:

```text
validate message
apply its state transition
run the synchronous cascade as far as possible
collect job submissions, cancellations, and attachment deliveries
publish diagnostics/snapshot changes
return or record the outcome
```

The collected effects are dispatched only after graph mutation and cascade finish. Dispatch
must itself be non-blocking; executors and transports later return completion messages.

A turn need not make the Context quiescent. It may leave nodes `computing`; each job result is
a later turn. The important property is that no observer sees half of a graph transition.

Graph functions are divided mechanically:

- plain synchronous functions may touch graph state but may not block or call external code;
- coroutine wrappers may wait, schedule retries, or mirror an async API, but may not retain a
  partially applied graph mutation across an `await`.

Assertions should check actor-thread affinity at internal mutation entry points during the
migration.

## 7. Public API, parking, and failures

### 7.1 Synchronous public surface

Initially every public mutation and consistent read submits a message and waits on a future.
The controller exception is re-raised in the calling thread. This preserves normal Python
error handling for graph construction and assignments.

The round-trip cost is an engineering risk, not something to dismiss with “public calls are
never hot.” Programmatic graph construction, parameter sweeps, and repeated reads can be hot.
Before considering the actor complete, benchmark:

- large graph construction one operation at a time;
- bulk assignment;
- repeated `.value`/state reads; and
- notebook-scale interactive calls.

Likely remedies are an explicit transaction/batch API and, only if needed, controller-
published immutable read snapshots. Neither changes the single-writer rule.

Calling the synchronous public API from the actor thread raises `ReentrantContextError` rather
than deadlocking or creating a weaker inline path.

### 7.2 Parking

Some operations need a value that is temporarily `waiting` or `computing`, for example a
subcell update that must materialize its parent. They must not fail merely because a job is in
flight, and they cannot block the actor.

An attempt can return `RETRY(await_condition, deadline)` without mutating state. The actor
registers the request as parked. When the condition changes, the entire operation is submitted
again and validated from scratch. If the awaited node becomes `failed`/`blocked`, shutdown
starts, or the deadline expires, the reply future is failed promptly.

Parking is not a continuation and carries no mutable graph references across the wait.

### 7.3 Failure routing

- A public request completes its reply future with a value or exception.
- A job result that makes a node invalid records failure on the node and propagates blocking.
- An external edit rejected before changing the graph records an attachment/edit error; it
  does not falsely mark a previously valid node failed.
- Unexpected actor-internal exceptions poison or stop the Context in a visible way. They must
  not be reduced to a log line on a daemon thread.

Exact exception classes and reporting surfaces remain implementation details, but every
asynchronous failure needs a durable place a user can inspect.

## 8. Actor lifecycle and graph quiescence

`quiescent` keeps its workflow meaning: no node is `waiting` or `computing`. It says nothing
about whether an external source could change in the future.

Actor shutdown must be explicit and idempotent:

1. stop accepting new ordinary messages;
2. unregister attachment sessions through their normal runtime path;
3. cancel/fail parked public requests;
4. process or reject already accepted job-result messages according to a documented rule;
5. release Context-owned checksum references; and
6. stop and join the loop thread.

`Context.__del__` cannot be the primary shutdown mechanism: GC can run on any thread and at
interpreter teardown. It should at most request an idempotent best-effort close. The normal
path is `Context.close()` plus the process-level Seamless shutdown registry.

## 9. Actor implementation plan

This is a design sequence, not yet a file-by-file handoff.

### A1. Establish the ownership boundary

- Inventory every current Context graph mutation and read, including transitional inline
  transformer evaluation.
- Introduce actor identity/thread assertions and a direct test harness for turns.
- Define immutable message envelopes and the sequenced ingress gateway.
- Do not add mounts in this phase.

**Exit evidence:** tests prove that concurrent submitters receive one total acceptance order
and that graph mutations occur only on the actor thread.

### A2. Route the public API and jobs

- Move public mutations through synchronous request/reply messages.
- Route job submissions out as effects and job completions back as messages.
- Preserve current graph semantics before adding parking.
- Add clean exception propagation and re-entry detection.

**Exit evidence:** existing workflow tests pass; targeted tests cover a user edit racing a job
result in both accepted orders.

### A3. Add parking, reads, and performance escape hatches

- Implement retry-from-scratch parking with failure and deadline paths.
- Route consistent reads through the actor.
- Benchmark call overhead and add batching only if justified by results.

**Exit evidence:** a temporarily unavailable subcell edit succeeds after its dependency
completes, fails promptly on dependency failure, and cannot expose partial state.

### A4. Complete lifecycle and shutdown

- Integrate settled checksum ownership APIs from the lifecycle work.
- Define close, late result, cancellation, GC, and interpreter-shutdown behavior.
- Stress repeated Context construction/destruction and stalled jobs.

**Exit evidence:** no hanging futures, surviving actor threads, or leaked refholder roles after
close.

---

# Part II — Attachments and file mounts

## 10. Attachment boundary

An attachment connects one stable `NodePath` to an external producer, consumer, or both:

- **sense:** external state becomes a value perturbation of the node;
- **actuate:** a complete node value is delivered externally after a turn.

The common abstraction should stay narrow. It can define identity, direction, error state,
message ownership, and delivery discipline. It should not pretend that all transports share
filesystem stamps, traitlet callback recursion, web acknowledgements, or the same conflict
policy. Echo and conflict detection use a common place in the runtime session but are
driver-specific protocols.

Attachments are a Context feature. Standalone `Cell` mounting remains out of scope because it
has no actor, `NodePath`, or workflow update stream.

### 10.1 Specification versus runtime session

The node owns a durable, serializable attachment **specification**:

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

Separating them prevents transport handles, futures, buffers, locks, and refholder leases from
leaking into graph serialization or copying. Replacing, removing, or reloading a spec creates
a new monotonically increasing `generation`; messages from old sessions are harmlessly
discarded.

## 11. Filesystem service and protocols

The filesystem side is process-global so polling and I/O resources are shared and paths can be
checked for in-process conflicts. It has two distinct internal roles.

### 11.1 Watch broker

The broker registers `(attachment_id, generation, path, watch options)`, observes cheap
metadata/events, and emits internal dirty records:

```text
Dirty(attachment_id, generation, watch_sequence, fingerprint)
```

It does not read files, hash buffers, scan large directories synchronously, resolve Seamless
checksums, or call a Context. A polling implementation is sufficient first; inotify/watchdog
can be an optional producer of the same dirty records.

The broker is primarily a **read-side sensor**. Normal outbound writes go directly to the I/O
service. A write-only mount may still be watched to detect foreign modification and reassert
its value, but that is mount policy using the same sensor—not the ordinary write route.

### 11.2 I/O pool

The I/O pool performs stable reads, hashing, directory scans, and atomic writes. For a file
read, it should compare metadata before and after reading and retry/discard if the file changed
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

Thus the answer to “what crosses from global to per-workflow?” is: **an explicit immutable
buffer observation at the semantic boundary**. A mere dirty bit stays inside the global
filesystem service, where it can be coalesced before any Context ordering claim is made.

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

## 12. Sense semantics

An observation is submitted to the Context ingress as an immutable attachment message. The
actor then:

1. checks attachment id and generation;
2. rejects duplicate or stale watch sequences;
3. performs mount-specific echo suppression;
4. validates that the attachment may produce the node;
5. applies the buffer as an ordinary external value edit; and
6. runs a normal turn.

The `Buffer` is intentionally present. If only a dirty path were sent, each Context would
need to perform or schedule filesystem I/O, duplicate reads for shared observations, and
define what “the event” meant after the file changed again. If only a checksum were sent, its
resolvability and reference lifetime would become an implicit cross-system precondition.

### 12.1 Coalescing

The watch broker may collapse a burst of dirty notifications for one registration before or
during a stable read. It must retain enough `watch_sequence` information for barriers (§15).
Once an `Observation` is accepted by a Context, it is not mutable or replaceable.

Actor-side compaction, if added, may replace only adjacent pending observations for the same
attachment and generation. For example, `M1, M2, U` may become `M2, U`; `M1, U, M2` may not
become `M2, U` or `U, M2` by overwriting a slot.

## 13. Actuate semantics and checksum lifecycle

After a turn, an attachment runtime may produce a delivery only when its node is `complete`.
Transient `waiting`, `computing`, `blocked`, and `failed` states do not delete or rewrite the
external artifact. Deletion is an explicit node deletion or unmount policy.

Snapshot transports such as files use `latest` delivery discipline: a queued but not yet
started delivery may be superseded. An in-flight write is not silently cancelled; its ack is
processed, then the newer value is written if still needed. Log-like future drivers may need
`every`, but that is not required for mounts.

The payload has two legal forms:

- a live local `Buffer`, captured without blocking; or
- a checksum with an attachment-owned refholder lease acquired before control yields.

The lease role is derived from the pending/in-flight delivery record, for example
`attachment:<id>:delivery:<sequence>`. It is released on supersession, acknowledgement,
timeout, generation replacement, or shutdown. A bare checksum that may later be resolved is
not a legal delivery payload.

Comparison-only checksums such as `last_sensed_checksum` and `last_delivered_checksum` are
declared lifecycle exemptions and are never resolved.

Delivery errors belong to the attachment session. They do not make a valid node value failed.
Timeouts bound both external hangs and lease duration.

## 14. File-mount semantics

### 14.1 Port legacy policy as a decision table

The valuable legacy behavior is the initialisation table over:

```text
authority in {cell, file, file-strict}
mode in {r, w, rw}
path exists?
node has a value?
```

Port this table directly, with a test for every meaningful cell. `authority` chooses the
winner when attaching an existing node and existing file. It does not silently become a
permanent prohibition on later user assignment.

In particular, legacy `rw` plus cell-side assignment writes the new value to the file; the
next poll is normally an echo and does not revert it. If continuous external ownership is a
desired new feature, add a distinct option such as `edit_policy="external-owned"` and specify
it separately. Calling that behavior `authority="file"` would be an incompatible semantic
change hidden under a familiar option.

The ongoing behavior of each mode—including user edits in `r`, detection of foreign changes
in `w`, deletion, and `persistent`—should be captured from legacy with characterization tests
before choosing any intentional deviations.

### 14.2 Reads and writes

Use the legacy mtime/event plus checksum double guard: metadata decides whether a read is
worth doing; content checksum decides whether a semantic change occurred.

Writes use a uniquely named temporary file in the target directory followed by atomic
replace. The resulting fingerprint and checksum return in `DeliveryAck` and participate in
driver-specific echo suppression. Checksums, not mtimes alone, remain the correctness guard.

Canonical byte rules must be explicit per supported celltype. Text newline normalization and
structured text normalization cannot remain mount-local patches that make write bytes differ
from canonical buffer bytes. Non-canonical formats require an explicit serializer/disposition
or are not directly mountable.

Directory mounts reuse deep-folder representation and follow the lifecycle plan: hold the
top-level checksum, not recursive member references. Recursive scanning and materialization
run in the I/O pool and need limits/cancellation because they may be expensive.

### 14.3 Echoes and shared paths

The global registry rejects incompatible overlapping paths in-process after path
normalization. Any overlap involving actuation or directory cleanup is incompatible;
independent read-only registrations may be permitted or internally shared. File/directory
prefix overlap needs the same compatibility check, not merely exact path equality. This is a
safety check, not a complete exclusivity guarantee: other processes, hardlinks, bind mounts,
case folding, and some network filesystem aliases remain outside it.

Echo suppression is a mount-session protocol using observation fingerprints, delivery
acknowledgements, and checksums. It must tolerate atomic replace and identical-content
rewrites. A generic attachment layer should provide state storage and message correlation but
not prescribe filesystem causality for future traitlet/share drivers.

Cross-process write fights deserve detection, but a ping-pong breaker is a hardening feature,
not part of the minimal actor or mount contract. First establish deterministic single-writer
behavior, in-process overlap refusal, and observable errors. Then add and test an oscillation
detector if experience shows it useful; do not claim it can detect two `rw` workflows that
silently converge through a shared file.

Legacy remount garbage delays, translation-time graph scans, `must_run_mount`, and symlink
`LinkItem`s are not ported. Stable node identity and explicit sessions remove their original
reason to exist.

## 15. Quiescence, barriers, and `settled()`

The expression “every attachment inbox entry applied” is insufficient because a watcher can
always be between detecting a change and finishing its read. `settled()` needs a finite cut,
not a glance at several empty queues.

`ctx.mount.sync()` requests a barrier from the filesystem service. Conceptually, one barrier
round is:

1. the broker completes a scan/event cut and returns a per-registration watch sequence;
2. every dirty record at or below that cut is resolved to an observation or an explicit
   unchanged/error result;
3. those results are accepted and processed by the Context actor;
4. resulting workflow computation reaches graph quiescence;
5. all deliveries caused up to that point receive acknowledgements; and
6. the actor processes those acknowledgements.

A delivery in step 5 can itself create a watch event after the original cut. Therefore
`sync()` requests another broker cut after the deliveries and repeats the round. It returns
only after a round produces no new semantic observation, graph work, or delivery. Own-write
events should normally be consumed as echoes in this final round; a genuine concurrent foreign
write starts another round.

The returned condition is **settled through final barrier B**. A file change after B is
outside the promise and may immediately perturb the Context again. Continuous external
mutation can prevent the barrier rounds from converging and must be bounded by a timeout.

This protocol requires source `watch_sequence`, attachment `generation`, Context acceptance
sequence, and delivery sequence. They solve different problems and should not be collapsed
into one counter.

The public naming remains provisional:

```python
ctx.a.mount(path, mode="rw", authority="file", persistent=True)
del ctx.a.mount

ctx.a.mount.error
ctx.a.mount.clear_error()

ctx.mount.sync()       # establish and wait through an external barrier
ctx.quiescent()        # graph only
ctx.settled()          # if retained, defined as a barrier operation, not a timeless predicate
```

## 16. Mount implementation plan

### M1. Characterize and specify legacy mount behavior

- Turn the legacy initialisation state machine into a table and golden tests.
- Characterize user edits and external changes in each mode after initialisation.
- Decide and document intentional incompatibilities rather than deriving policy from the new
  concurrency architecture.
- Define mountable celltypes and canonical byte rules.

**Exit evidence:** mode/authority behavior can be reviewed without actor or watcher code.

### M2. Add attachment specs and sessions with a manual transport

- Add node-owned serializable specs and Context-owned runtime sessions.
- Implement generation invalidation, sense and actuate messages, error slots, and explicit
  unmount.
- Use a deterministic manual transport with caller-supplied buffers and captured deliveries.
- Integrate delivery leases with the completed checksum lifecycle implementation.

**Exit evidence:** actor tests can interleave user edits, job results, observations, unmount,
and stale-generation completions without touching the real filesystem.

### M3. Build the global filesystem service

- Add registration and normalized-path overlap checks.
- Implement polling broker and bounded I/O pool as separate components.
- Produce stable-read `Observation`s with buffers and checksums.
- Implement atomic file delivery and correlated acknowledgements.
- Ensure no global component stores node/Context objects or bare resolvable checksums.

**Exit evidence:** service-level tests cover rewrite-during-read, identical-content touch,
atomic replacement, write failure, timeout, unregister races, and stale generations.

### M4. Connect file mounts and echo suppression

- Apply the legacy policy table at attachment creation.
- Implement file-specific echo correlation and latest-delivery supersession.
- Test both orders of user edit versus observation and job result versus observation.
- Test foreign modification of `w` and `rw` modes according to the characterized contract.

**Exit evidence:** deterministic integration tests use barriers rather than polling sleeps.

### M5. Add sync barriers and directory mounts

- Implement the watch-cut/observation/delivery barrier protocol.
- Add directory stable reads and atomic-enough materialization policy.
- Exercise large trees, cancellation, partial failure, and cleanup behavior.

**Exit evidence:** `sync()` has a precise finite guarantee and tests never infer settledness
from temporarily empty queues.

### M6. Harden and generalize

- Measure watcher load, thread count, actor round-trip latency, and buffer retention.
- Add optional native filesystem notifications only behind the same broker contract.
- Consider cross-process oscillation detection.
- Validate the narrow attachment contract with one later driver (traitlet or share) before
  declaring it fully generic.

---

# Part III — Combined sequencing and open decisions

## 17. Dependency order

The two tracks are separate, but not independent in time:

```text
M1 legacy characterization ───────────────────────────────┐
                                                          ▼
checksum lifecycle reaches stable refholder API      M2 → M3 → M4 → M5 → M6
                    │                                  ▲
                    ▼                                  │
          A1 → A2 → A3 → A4                           │
                └──────────────────────────────────────┘
```

M1 is read-only/specification work and can proceed earlier. M2 requires a usable actor ingress
and turn boundary; M2's outbound delivery requires stable refholder APIs. Real filesystem work
should not be used to debug actor ordering.

The actor migration is the higher-risk architectural change. It deserves its own design
review, benchmarks, and merge boundary before mount mechanics are layered on top. Conversely,
mount-specific questions must not delay routing job results through the actor.

## 18. Open decisions before handoff plans

1. Which exact existing Context operations can park, and what are their default deadlines?
2. Is actor-thread ownership also required for all diagnostic reads, or can a first version
   publish a narrowly defined immutable status snapshot?
3. What is the shutdown policy for already accepted late job results?
4. Which existing API should expose explicit Context close and context-manager use?
5. What are the exact post-initialisation semantics of legacy `r`, `w`, and `rw`, especially
   deletion and user assignment, and which deviations are intentional?
6. Which celltypes have canonical file bytes and which require a disposition?
7. Does mounting a scratch result force durable materialization, reject the mount, or make the
   delivery best-effort?
8. What filesystem fingerprint is reliable enough on supported local and network filesystems,
   while retaining checksum as the final correctness guard?
9. Should `settled()` be a blocking barrier operation, or should only `mount.sync()` promise
   external settlement while `settled` remains an inspectable snapshot with weaker semantics?
10. What are the initial limits for I/O workers, directory scans, delivery timeouts, and
    per-Context actor threads?

These are genuine contract choices. Details such as concrete queue classes, executor
libraries, polling intervals, and exception names can wait for the handoff plans.
