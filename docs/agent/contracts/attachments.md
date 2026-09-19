# Attachments (Contract)

An **attachment** connects one Context cell node to an external resource, in one or both directions:

- **sense** — external state becomes an **authoritative value write** on the node: an ordinary user assignment that happens to arrive from somewhere else;
- **actuate** — after a turn in which the node's value changed, that **complete** value is **delivered** to the resource.

This page is the framework: direction, scope, ownership, delivery discipline, error state and lifecycle. The **file driver** — bytes, paths, celltype canonicalization, fingerprints, atomic writes, directories, limits — is `contracts/mounts.md`. The seam is **direction and discipline versus bytes and filesystem**: `contracts/mounts.md` never restates a rule from this page, it only says where the file driver specializes one.

**This page specifies the guaranteed behaviour of the attachments that exist; it is not a supported plugin API.** The file driver is the only production driver. `ManualDriver` is a test instrument, `WidgetDriver` is experimental, and third-party drivers are not supported. There is a real transport boundary and it is worth understanding, but nothing below is a stable extension point, and the "generic" layer is still file-shaped in four named places (see *Implementation status*).

Code locations:

| Concern | Module / symbol |
|---|---|
| Durable spec, celltype admission | `seamless_workflow.attachments.spec` (`AttachmentSpec`, `validate_celltype`) |
| Pure policy | `seamless_workflow.attachments.policy` (`decide_initial`, `classify_observation`, `reassert`, `detector`, `ABSENT`, `INVALID`) |
| Session and messages | `seamless_workflow.attachments.session` (`MountSession`, `Observation`, `Delivery`, `DeliveryAck`, `MountLease`, `SyncReport`, `MountError`, `ConflictError`) |
| Controller mixin | `seamless_workflow.attachments.runtime` (`AttachmentRuntime`, `SyncPredicate`) |
| Public handles | `seamless_workflow.attachments.api` (`MountHandle`, `ContextMounts`, `make_sink`, `load_graph`) |
| Transport implementations | `seamless_workflow.attachments.fs.service` (`FileSystemService`, `Registration`), `…attachments.widget.WidgetDriver`, `…attachments.manual.ManualDriver` |
| Node field and graph entry | `seamless_workflow.graph.Node.mount`; `seamless_workflow.context.Context.get_graph` / `set_graph`; `seamless_workflow.serialization.prepare_graph` |
| Cell handle | `seamless.cell_class.Cell.mount` (property plus deleter, seamless-core) |
| Diagnostics | `seamless_workflow.diagnostics.record_attachments` |

## Scope: Context-bound whole cell nodes, one attachment each

An attachment attaches to a **whole cell node of a workflow Context**, and to nothing else.

| Target | Result |
|---|---|
| a bound whole cell node | the only legal target |
| a standalone `Cell` | `AttributeError("mount is only available for bound workflow cells")` — the bound-only error `Cell` already uses for Context-only members |
| a sub-path projection (`ctx.a.b`), or a read-only handle | `AttributeError("Only whole Context cell nodes can be mounted")` |
| a transformer pin | no `mount` member exists at all (`AttributeError`); see `contracts/pins.md` |
| transformer code | not a cell handle; there is no `mount` on it |
| a missing node, or a transformer node | `NodeError("Mounts require an existing whole cell node")` |
| a node that already has one | `ValueError("Cell is already mounted; unmount first")` |

**The remedy for every exclusion is the same: attach a cell and connect it.** `ctx.code = Cell(celltype="python"); ctx.code.mount("code.py"); ctx.tf.code = ctx.code` is the supported way to edit transformer code externally. This is not a temporary limitation: only nodes carry checksums, only a Context has a controller and an update stream, and an attachment's whole discipline is built on the node being the unit of change.

**Only the whole node value is attached.** There are no sub-path attachments: a sub-path write is a read-modify-set transaction on the root (`contracts/cells.md`), and an attachment that owned part of a root value would have no checksum of its own to compare against.

**Every public call is an ordinary public Context operation.** Attaching, detaching, `clear_error()` and the barrier raise `ReentrantContextError` when called from the controller thread, and `ClosedContextError` after `close()`.

## The durable spec and the ephemeral session

An attachment is two objects with two different lifetimes.

**The spec is durable node state.** It is a frozen dataclass stored in a dedicated `Node.mount` field — deliberately *not* in `CellConfig`, so that the parameterized configuration path cannot reach it. Only attach and detach change it. It is what `get_graph()` serializes and what `set_graph()` restores.

- The spec **survives value writes and every configuration edit that leaves the node a cell.**
- It is removed, and the session closed, when the node is **deleted** or **replaced by a transformer**. The post-turn pass detaches any session whose node has disappeared or is no longer a cell, so this needs no cooperation from the caller.

**The session is runtime state, and is never copied, serialized or restored.** It holds the transport registration, the one belief about the resource, the processed watch sequence, the actuation baseline, the pending and in-flight deliveries, the reassert timestamps, the two error slots and the session state (`active`, `tripped`, `closing`).

- **A fresh `session_id` per session, never reused**, plays the role of a generation. Replacing a spec, re-attaching, or reloading the graph closes the old session and opens a new one.
- **Every late message from an old session is discarded**, and the payload claims it carries are released. Every handler matches the session id first.
- Therefore `get_graph()` / `set_graph()` round-trips carry the spec and nothing else: after a reload, sensing starts from a fresh initial read, not from a remembered state.

## The topology rules an attachment imposes

**A sensing attachment is the node's producer.** While a node has an attachment whose mode contains `r`:

- any operation that would add an **incoming edge** to it — at the root **or at any sub-path** — raises `AuthorityError("Sensing mount is the producer; unmount first")`. That includes assignment syntax, which would otherwise detach and connect;
- attaching to a node that already has an incoming edge raises `AuthorityError("Sensing mount cannot have incoming edges; unmount first")`;
- a graph carrying such a connection is refused at load with `PathError("Sensing mounts cannot have incoming connections")`.

This is the ordinary "a target has at most one producer" rule, and it is what makes a sensed write's authority check unable to fail.

Two further refusals apply to **any** attached node, sensing or not:

- **The celltype is frozen.** Retyping, or replacing the cell with a builder of a different celltype, raises `ValueError("Mounted celltype cannot change; unmount first")`. The celltype decides how the resource's bytes are read and written, and re-initializing in place would need a multi-turn protocol that a configuration edit does not have.
- **Clearing is refused.** `ctx.a.checksum = None` and the other clearing spellings raise `AuthorityError("Cannot clear a mounted cell; unmount first")`. Clearing is an explicit graph operation, and there is no defined external state for "no value".

`contracts/cells.md` states the last two from the handle's side.

## Sense: a non-detaching authoritative write

A sensed value is installed exactly as a user assignment is, with two qualifications:

- **The same authority check, never detaching.** The write is validated against topology as a non-detaching root write and installed without clearing edges, followed by the ordinary cascade. The newest authoritative input wins, by acceptance order; a sense has no privilege over a user write and no user write has privilege over a sense.
- **The authority check cannot fail** while the edge rule above holds. If it fails anyway, the failure is **recorded in the session, not raised** — a sense arrives on the controller as a message from a background producer, and raising would poison ingress.

Two consequences:

- **A sensed value supersedes an *undispatched* pending delivery.** The pending delivery is dropped and its claim released: there is no point writing back a value the resource has just told us is stale. An **in-flight** delivery is never cancelled (below).
- **A sense clears the sense error.** Every value write passes through the one installation point, which clears `session.sense_error`, so a valid observation *and* a user assignment both clear it.

Sensing deliberately does **not** do three things:

- **Invalid external state does not stop sensing.** It fails the cell and monitoring continues; the next valid observation recovers it with no user action.
- **Content that is merely wrong for the program is not rejected.** A syntax error in a `python` cell passes, because a user assignment of the same text passes. The failure surfaces where it would for a user write: in the transformer that runs it.
- **Disappearance does not clear the node.** Removing a value is an explicit graph operation.

## Actuate: delivery after a turn

One pass runs at the end of **every** turn, before barrier predicates are re-evaluated, over the sessions whose mode contains `w`:

```text
N = node checksum if node.state == "complete" else None
if N is not None and N != session.last_synced:
    session.last_synced = N
    if N != session.disk:
        request a delivery of N
```

- **Only `complete` actuates.** A node that is `waiting`, `computing`, `blocked`, `failed` or `unwired` delivers nothing: **transient states never delete or rewrite the resource.** A cell mid-recompute does not blank its file, and a failed cell does not propagate its failure into external state.
- **Actuation is triggered by node changes**, never by a node/resource mismatch on its own. The one exception is the `w`-mode **reassert** (below), where a foreign change to an output the Context owns re-requests the current value.
- The pass is O(number of attachments) per turn and needs no changed-set from the cascade.

**Latest discipline.** A session has **at most one pending and at most one in-flight delivery**.

- A new request **replaces** the pending one and releases its claim: intermediate values are not queued, and a rapid series of edits produces one write of the last value.
- **An in-flight delivery is never cancelled.** When it is acknowledged, the pending one is dispatched — unless it has meanwhile become equivalent to the believed state of the resource, in which case it is dropped.
- A delivery carries a **claim on its payload checksum**, acquired in the requesting turn and owned by the controller, which releases it on supersession, acknowledgement or session close. The transport takes a **separate** claim of its own for the duration of the operation, so a detach during an in-flight write cannot pull the buffer out from under it.

### A delivery resolves; it never computes

**The payload is resolved through `Checksum.resolution()`: the local buffer cache, then the remote buffer server, then `CacheMissError`. It never fingertips.** A delivery therefore has exactly the powers of `.buffer` — **nothing in the attachment layer does work behind your back except an explicit `compute()`.**

Consequences worth stating, because the tempting reading is the wrong one:

- **Attaching is not a materialization mechanism for a scratch result.** It does not force a scratch transformation to be re-run, and it does not make a scratch result durable.
- A scratch-fed actuating attachment usually **works anyway**, because the delivery follows the completing turn while the result buffer is still cached. It **fails** when the checksum arrived without its bytes: remote execution, a cache hit, or eviction.
- That failure is an **ordinary delivery error** — retried cheaply, reported on the attachment, never on the cell — so the resource is still updated if the buffer ever becomes resolvable again.

`contracts/scratch-witness-audit.md` defines scratch and fingertipping; `contracts/cells.md` states the same "nothing computes without `compute()`" rule for reads.

## The three-way error model

| Error | Lives on | Meaning | Cleared by |
|---|---|---|---|
| **sense error** | the **cell**: `failed`, with the error as `.exception` | the resource cannot supply the cell's value | the next valid observation, **any** value write, or detaching |
| **delivery error** | the **attachment**: `.error` | the value is valid; only the resource is behind | the next successful delivery |
| **conflict error** | the **attachment**: `.error`, **latched** | the oscillation detector tripped | `clear_error()` only |

**None of them stops monitoring.** An attachment never gives up because of the resource: only an invalid *request* raises, and every resource-state problem becomes one of the three errors above with the transport still active.

### Sense errors fail the cell

A cell whose session holds a sense error derives as **`failed`** with that error, and its published checksum is dropped, so downstream nodes become **`blocked-by-error`** exactly as for any other failure. A cell never presents a stale value as valid while its source is broken.

- **The stored value is kept, but masked.** `get_graph()` still records the last good value, and detaching unmasks it.
- **`clear_exception()` on such a cell requests an immediate re-observation** instead of re-deriving: the cell's exception is owned by the resource, so the only way to clear it is to look again. `contracts/node-state-lifecycle.md` states this from the state machine's side.
- A brief sense error is cheap. If the resource returns to its previous content, the downstream transformations get their old identities back and can re-latch onto their held runs within the supersession grace window instead of recomputing.

### Write failures stay on the attachment, never on the cell

**A read problem is the cell's exception, because the resource *is* the cell's value source. A write problem stays on the attachment, because the value is valid and only the resource is behind.** Failing the cell would block every downstream consumer of a correct result merely because a copy could not be made.

The cost is visibility, and it is accepted: a failed write shows in `.error`, in one log line, and in the `sync()` report — **not** in `ctx.a.exception`.

A failed delivery is **retried with capped exponential backoff — 1 s, doubling, capped at 60 s** — and **immediately** whenever the node's value changes, until it succeeds or is superseded. The retrying delivery keeps its claim while it waits. The next success clears the error and resets the backoff. A missing target directory, a full disk or a permission problem therefore recovers by itself.

### Error typing: objects here, strings on the cell

**`ctx.a.mount.error` and `status["sense_error"]` are `Exception` objects** (`MountError`, or its subclass `ConflictError`). **`Cell.exception` is a string** (the ruling of `contracts/cells.md`).

The rule that makes this extensible is the **remote boundary**: the string convention exists because Expressions and Transformations can execute remotely, and exception objects do not transfer well. Attachments are fundamentally local — the transport lives in this process — so a local-only error surface is exempt.

Two consequences:

- **`isinstance(ctx.a.mount.error, ConflictError)` remains the machine-readable way to tell a tripped detector from a failed write.** There is no other flag for it; `status["state"] == "tripped"` says the same thing about the session.
- **The same `MountError` appears as an object on the attachment surface and as a string on the cell.** Its `"<path>: <reason>"` prefix is **contract**, and it is what identifies a sense error among ordinary cell failures.

## The oscillation detector

Conditional writes stop an attachment overwriting a change it has not seen. They do not stop two writers taking turns. A foreign write is not itself the signal — under a sensing attachment it is the whole point. The signal is narrower:

**our actuation restoring a value that a foreign writer had just replaced.**

```text
we deliver C1  →  a foreign C2 ≠ C1 is observed  →  we deliver C1 again
```

Each such **reassert** is counted per session over a rolling window. On trip:

- a **`ConflictError` is latched** in the session, naming the resource and the alternating checksums, and logged once;
- **actuation stops**: the session state becomes `tripped`, the pending delivery is dropped, and no further delivery is requested;
- **the registration is kept.** The attachment keeps sensing (modes with `r`) or watching (`w`), so its status stays current. **A tripped attachment is paused, never dead** — tracking the other writer beats diverging silently.

**Recovery is manual: `clear_error()`.** It clears the error, returns the session to `active`, forgets the reassert timestamps, and — for an actuating mode on a `complete` node — immediately requests a delivery of the current value, so the Context's value wins the moment you say so. The **thresholds, the window and the two-editors rationale** are file-driver policy: see `contracts/mounts.md`.

## The cut barrier

**"Every queue is empty" is not a settledness criterion**: a transport can always be between detecting a change and finishing the read of it. Settlement is established by a **cut** instead.

One round is:

1. request a cut from every registration of this Context;
2. wait for each cut result. A transport sends it only after enqueueing every observation that resolves what it had seen at or below the cut. Ingress is FIFO, so by the time the controller processes the cut result, those observations have been processed too;
3. wait for **graph quiescence** — no node `waiting` or `computing`;
4. wait until no session has a pending or in-flight delivery. **A delivery that failed and is waiting for its retry counts as settled**, with its error reported;
5. **if anything moved during the round** — any sensed value, any delivery requested — **start another round**; otherwise resolve.

A delivery is itself an external event after the cut, so our own writes are normally consumed as an echo in the final round; a genuinely concurrent foreign write starts another one.

**Guarantee — *settled through the final cut*:** every external change before the final cut has been sensed and propagated, and every node value that was complete at the end is delivered, or its session reports why not. **A change after the cut is outside the promise**, and continuous external mutation can prevent convergence — which is what the timeout is for.

- The barrier **resolves rather than raises** when a cell has a sense error, an attachment is in error, or an actuating node is not complete, exactly as `compute()` returns with failed nodes. The report says which.
- Barrier discipline is that of `contracts/workflow-context.md`: `timeout=None` waits; expiry raises `TimeoutError`, **withdraws the predicate and cancels nothing**. `close()` fails it like any other barrier.
- **`ctx.compute()` stays graph-only.** It never waits for external state. Reading an actuated resource from outside the process after `compute()` requires the cut barrier as well.
- There is **no `settled()` predicate.** "Is everything settled?" cannot be answered without a cut.

The spelling — `ctx.mounts.sync()`, `await ctx.mounts.synchronization()` — and the `SyncReport` fields are in `contracts/mounts.md`, because the only external barrier that exists is the file one.

## Attach, detach, close

**Attach** does all the slow work on the caller's thread, then decides in one turn:

1. validate the request and the node (the table in *Scope*, plus spec validation);
2. reserve the resource with the transport;
3. run the **initial observation** and wait for it. The observation fixes the watch **baseline**, so a change made after it is not lost: it is detected as an ordinary later event once the session is active (observation begins as a post-turn effect of step 4, not at reservation);
4. submit one message. In its turn the controller re-validates, evaluates the **initial decision table** against the node's value *at that turn*, installs spec and session, applies a resource → node write or sets a sense error if the table says so, and queues an initial delivery if the table says node → resource;
5. if an initial delivery was queued, **wait for its acknowledgement**, so that attach-then-read from outside the process works. A failed initial write does not make attaching raise; it becomes the attachment's error and is retried.

**Attach blocks, and raises only for an invalid request.** It never raises for the *state* of the resource — missing, unreadable, invalid for the celltype, or not writable. In all of those the attachment is installed and monitoring, each problem is logged once, and when the resource is fixed the attachment recovers with no user action. If it does raise, nothing is installed and the reservation is released.

**Detach** (`del ctx.a.mount`) is a single turn that:

- marks the session `closing` and removes it, so every later message from it fails the id match;
- drops the pending delivery and releases its claim, and releases the controller's claim on an in-flight one — the transport keeps its own claim until that operation finishes;
- **clears the cell's sense error, unmasking the stored value**;
- releases the registration, and waits for the transport's cleanup, bounded by the delivery timeout.

Node deletion and replacement by a transformer detach in exactly the same way.

**Close** flushes, once, and does not retry:

1. admission closes and sensing stops;
2. each **persistent** session with a pending delivery and no error dispatches it;
3. in-flight acknowledgements are awaited, bounded by `close(timeout=60)`; a timeout is logged and the close proceeds;
4. non-persistent cleanup runs (file-driver policy; see `contracts/mounts.md`);
5. registrations are released.

The flush completes only deliveries that **ordinary actuation has already requested**; it never compares node and resource afresh, so external state that someone is mid-way through editing is not overwritten at close. It does not retry a delivery that fails during the flush; the failure is logged. Acknowledgements and cut results are **internal** messages, so they keep being accepted after ordinary admission has closed — otherwise the flush could not observe its own completion.

**A close triggered by garbage collection on the controller thread cannot flush.** It releases roles in place and joins in a finalizer thread, so an already-requested delivery may be dispatched but is never awaited, and its acknowledgement arrives after the session is gone. Finalization *off* the controller thread performs an ordinary, flushing close. Do not rely on garbage collection to make external state current — use `close()`, the context manager, or the cut barrier.

`seamless.close()` closes the Contexts, each flushing, and then the transport service.

## Leaf retention, on the sense path only

**Leaves that an attachment *sensed* stay resolvable while the node holds that index, including after detaching.**

That is the whole promise, and it is narrow on purpose. The general rule is the opposite and is already settled: **only the top-level checksum of a deep value is owned, with no recursive deep ownership** (`contracts/internal/checksum-reference-lifecycle.md`). Sensing is a permanent exception to it, because the attachment is the only thing that ever held those leaf buffers: it read them, and nothing else in the process has a reason to keep them.

- The claims are attached to the **node and its index**, not to the session, which is why they outlive detaching; they are released when the node takes a different value, when the node is deleted, and at Context close.
- **A *computed* directory value gets no such claims.** Nothing sensed its leaves, so a leaf that cannot be resolved at delivery time surfaces as an ordinary delivery error — see *A delivery resolves; it never computes* — and is retried.

Directory celltypes and index shape are `contracts/deep-celltypes.md`; the file driver's directory rules are `contracts/mounts.md`.

## The driver roster

| Driver | Status |
|---|---|
| **file** (`fs.service.FileSystemService`) | the **only production driver**; `contracts/mounts.md` |
| `manual.ManualDriver` | **test-only.** It keeps the file driver's policy half and replaces its transport with a queue the test controls, so every interleaving of user edits, results, observations, acknowledgements, detaching and close can be forced deterministically. Never serialized |
| `widget.WidgetDriver` | **experimental.** A traitlets-style callback widget attached through the same session protocol, built to show that the boundary is real. Never serialized |
| anything else | **not supported.** There is no registration mechanism, no versioned protocol and no compatibility promise |

Only `driver == "file"` is serializable; `AttachmentSpec.to_graph()` raises `ValueError("Only file mounts are serializable")` for anything else, and a manual or widget session leaves no `"mount"` entry in `get_graph()`.

`seamless_workflow.diagnostics.record_attachments(ctx)` records the immutable event stream — each observation's classification, each delivery request, dispatch and acknowledgement, each reassert and the detector's verdict. It exists because an echo misclassified as foreign usually re-installs the checksum the node already has, which no state or value assertion can see.

## Implementation status and current limitations

Settled contract that the code does not yet implement, or implements differently. Where a design document and the code disagree, **the code wins**, and the disagreement is listed here.

**The generic layer is file-shaped in four places.** They are why this page is not a plugin API:

1. **`AttachmentSpec`'s fields are file fields.** `path`, `mode`, `authority`, `persistent` — plus `driver` — live on the supposedly generic spec class, and `to_graph()` raises unless the driver is `file`. A non-file driver gets a synthetic `path` (`"widget-<uuid>"`, `"manual-<uuid>"`) purely to satisfy validation.
2. **Every controller handler and the node field are `_mount_*` / `node.mount`.** `_mount_attach`, `_mount_observed`, `_mount_delivered`, `_mount_cut`, `_mount_sync`, `_mount_after_turn`, `Node.mount`. The vocabulary of this page ("attachment") is not the vocabulary of the code.
3. **`WidgetDriver` borrows the file service.** It constructs an `fs.service.Registration`, and it uses `get_service()` for its thread pool and for payload resolution — so the "second driver" is not independent of the first.
4. **The only external barrier is spelled `ctx.mounts`.** There is no driver-neutral name for it, and manual and widget sessions are cut through it all the same.

**The boundary is nonetheless real**, and that is the evidence for it: three implementations satisfy one transport protocol —

| Transport call | Meaning |
|---|---|
| `activate(reg)` | begin observing; called as a post-turn effect of attaching |
| `poll(reg, *, force=False)` | observe now |
| `request_cut(reg, cut_id)` | observe now, then report the cut |
| `deliver(reg, delivery)` | write the payload, then acknowledge `written`, `conflict` or `error` |
| `unregister(reg, **kwargs)` | close the registration, and run cleanup |
| `delivery_timeout` | the bound a detach wait and the close flush use |

— and `SyncPredicate` cuts every session regardless of driver.

Smaller divergences and rough edges:

- **`Cell.exception` is still an exception object in code, not a string.** A sense error is installed on the node as the `MountError` itself. `contracts/cells.md` carries the same note for cell failures generally; the string contract is what agents should code against, and the `"<path>: <reason>"` prefix holds either way.
- **On an *unattached* cell the surface answers `None` — except `clear_error()`.** `.mount.spec`, `.mount.status` and `.mount.error` all return `None`, and `del ctx.a.mount` is a silent no-op, but `ctx.a.mount.clear_error()` raises a bare `KeyError(<node path>)`. That is an inconsistency, not a designed refusal; do not depend on the exception type.
- **Delivery retries are dispatched by the post-turn pass, and `_mount_tick` is an explicit no-op.** The attachment layer owns no timer. In practice the file driver's broker enqueues one `_mount_tick` message per registration per poll interval, and since the post-turn pass runs after **every** turn, a due backoff fires within about one poll interval even on an otherwise idle Context (measured: ~1.5 s for the first, 1 s retry). A driver that sends no tick — `ManualDriver` — fires a due retry only when something else causes a turn; `ctx.mounts.sync()` is one.
- **A failure inside the observation handler becomes `session.error` as a bare `MountError(str(exc))`**, without the `"<path>: "` prefix that every other `MountError` carries. It is a can't-happen path (the authority check cannot fail while the edge rule holds), but the prefix contract does not hold for it.
- **Malformed internal messages are dropped silently.** `_mount_delivered` and `_mount_cut` validate their payload shape and return without effect on anything unexpected, because they run as class-5 messages and raising would poison ingress.
- **Deferred, and not in this version:** attaching a standalone `Cell`, sub-path attachments, attaching a transformer pin or code handle, attaching a whole sub-Context to a directory with automatic child paths, and continuous external ownership (an `edit_policy="external-owned"` that would forbid later user assignment). The last is deferred with a named condition: if it is added it gets its own name and specification, and must **not** be expressed by redefining `authority="file"`.

## Non-goals

- **A plugin API.** See the top of this page. The contract describes the attachments that exist.
- **Cross-process locking or exclusivity.** The registry is a safety net within one process (`contracts/mounts.md`); two processes sharing a resource are handled by conditional writes and the detector, not prevented.
- **A settledness predicate without a cut.** `settled()` was considered and rejected.
- **Hard cancellation of an in-flight delivery.** It is never cancelled, by design: the write is either done or not, and cancelling it would leave the belief about the resource undefined.
- **Attachment-driven computation.** A delivery resolves and never fingertips; attaching is not a way to make Seamless do work.
