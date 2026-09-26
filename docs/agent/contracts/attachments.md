# Attachments (Contract)

An **attachment** connects one Context cell node to an external resource, in one or both directions:

- **sense** — external state becomes an **authoritative value write** on the node: an ordinary user assignment that happens to arrive from somewhere else;
- **actuate** — after a turn in which the node's value changed, and once the node is **`complete`**, that value is **delivered** to the resource.

This page is the framework: scope, the durable spec and the ephemeral session, the topology rules, the sense and actuate disciplines, the error model, the oscillation detector, the cut barrier, the lifecycle and leaf retention. The **file driver** — bytes, paths, celltype canonicalization, fingerprints, atomic writes, directories, limits — is `contracts/mounts.md`. The seam is **direction and discipline versus bytes and filesystem**: `contracts/mounts.md` never restates a rule from this page; it only says where the file driver specializes one.

**This page specifies the guaranteed behaviour of the attachments that exist; it is not a supported plugin API.** The file driver is the only production driver. `ManualDriver` is a test instrument, `WidgetDriver` is experimental, and third-party drivers are not supported. There is a real transport boundary and it is worth understanding, but nothing below is a stable extension point, and the "generic" layer is still file-shaped in four named places (*Current limitations*, below).

**"Authority" has two unrelated meanings**, both inherited from the code's own naming. Keep them apart:

- **Write authority** — the topology check that every write passes, and that refuses with **`AuthorityError`** when a source controls the target (`contracts/cells.md`, *Authority*). An **authoritative write** is one that passes this check and installs a value. **Unqualified, "authority" and "authoritative" on this page always mean this.**
- **The `authority` spec field** — `"file"`, `"cell"` or `"file-strict"`, an argument of `mount()`. It **only resolves the initial file-versus-cell conflict at attach time** (`contracts/mounts.md`, *The initial decision table*). It confers no write authority, is not a continuous ownership rule, and has nothing to do with `AuthorityError`. This page always names it as "the `authority` field" or writes it as `authority=…`.

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
| a sub-path projection (`ctx.a.b`) | `AttributeError("Only whole Context cell nodes can be mounted")` |
| a read-only handle, **including a transformer's result, `ctx.tf.result`** | `AttributeError("Only whole Context cell nodes can be mounted")` |
| a bound `as_celltype` handle (`ctx.a.as_celltype("text")`) | **unspecified — deferred.** Whether mounting one is refused, and with which error, is an open question; do not depend on either outcome |
| a transformer pin | no `mount` member exists at all (`AttributeError`); see `contracts/pins.md` |
| transformer code | not a cell handle; there is no `mount` on it |
| a missing node, or a transformer node | `NodeError("Mounts require an existing whole cell node")` |
| a node that already has an attachment | `ValueError("Cell is already mounted; unmount first")` |

The messages `"Only whole Context cell nodes can be mounted"` and `"Cell is already mounted; unmount first"` are contract, and so is the `NodeError` message.

**The remedy for every exclusion is the same: attach a cell and connect it**, in whichever direction the value flows. `ctx.code = Cell(celltype="python"); ctx.code.mount("code.py"); ctx.tf.code = ctx.code` is the supported way to edit transformer code externally; `ctx.out = ctx.tf.result; ctx.out.mount("outdir", mode="w")` is the supported way to write a transformer's result out. This is not a temporary limitation: only nodes carry checksums, only a Context has a controller and an update stream, and an attachment's whole discipline is built on the node being the unit of change.

**Only the whole node value is attached.** There are no sub-path attachments: a sub-path write is a read-modify-set transaction on the root (`contracts/cells.md`), and an attachment that owned part of a root value would have no checksum of its own to compare against.

**Every public call is an ordinary public Context operation.** Attaching, detaching, `clear_error()` and the barrier raise `ReentrantContextError` when called from the controller thread, and `ClosedContextError` after `close()`.

## The durable spec and the ephemeral session

An attachment is two objects with two different lifetimes.

**The spec is durable node state.** It is a frozen dataclass stored in a dedicated `Node.mount` field — deliberately *not* in `CellConfig`, so that the parameterized configuration path cannot reach it. Only attaching and detaching change it. It is what `get_graph()` serializes and what `set_graph()` restores.

- The spec **survives value writes and every configuration edit that leaves the node a cell** — with one exception: replacing the cell with an **empty builder of the same celltype** detaches it (*Detach*).
- It is removed, and the session closed, when the attachment is **unmounted**, when the node is **deleted**, and when the graph is **replaced** by `set_graph()`. Every one of those paths is a detach (*Detach*).
- **The post-turn pass is the backstop:** it detaches any session whose node has disappeared or is no longer a cell, so no removal path depends on the caller's cooperation. Through the public API a cell node never turns into a transformer in place — assigning transformer code or a `Transformer` builder onto a cell node is refused with `NodeError` (`contracts/workflow-context.md`, *What an assignment means*) — so the "no longer a cell" branch guards internal paths only.

**The session is runtime state, and is never copied, serialized or restored.** It holds the transport registration, the one belief about the resource, the processed watch sequence, the actuation baseline, the pending and in-flight deliveries, the reassert timestamps, the two error slots and the session state (`active`, `tripped`, `closing`).

- **A fresh `session_id` per session, never reused**, plays the role of a generation. Detaching and re-attaching, or reloading the graph, closes the old session and opens a new one.
- **Every late message from an old session is discarded**, and the payload claims it carries are released. Every handler matches the session id first.
- Therefore a `get_graph()` / `set_graph()` round trip carries the spec and nothing else: after a reload, sensing starts from a fresh initial read, not from a remembered state.

## The topology rules an attachment imposes

**A sensing attachment is the node's producer.** While a node has an attachment whose mode contains `r`:

- any operation that would add an **incoming edge** to it — at the root **or at any sub-path** — raises `AuthorityError("Sensing mount is the producer; unmount first")`. That includes assignment syntax, which would otherwise detach and connect;
- attaching a sensing mode to a node that already has an incoming edge raises `AuthorityError("Sensing mount cannot have incoming edges; unmount first")`. A `w`-only attachment on a connected node is legal: that is how a computed value is written out;
- a graph carrying such a connection is refused at load with `PathError("Sensing mounts cannot have incoming connections")`.

This is the ordinary "a target has at most one producer" rule, and it is what makes a sensed write's write-authority check unable to fail (*Sense*).

Two further refusals apply to **any** attached node, whatever the mode:

- **The celltype is frozen.** Retyping, or replacing the cell with a builder of a **different** celltype, raises `ValueError("Mounted celltype cannot change; unmount first")`. The celltype decides how the resource's bytes are read and written, and re-initializing in place would need a multi-turn protocol that a configuration edit does not have.
- **Clearing is refused.** `ctx.a.checksum = None` and the other clearing spellings raise `AuthorityError("Cannot clear a mounted cell; unmount first")`. Clearing a value is an explicit graph operation, and there is no defined external state for "no value".

**One assignment is exempt from both refusals: `ctx.a = Cell(celltype=<same>)`**, an empty builder of the cell's own celltype. It is not refused, and it is not a clearing spelling of an attached cell: it **detaches the attachment and clears the cell** in one operation (*Detach*), so the cell it clears is no longer attached.

`contracts/cells.md` states the celltype freeze and the clearing refusal from the handle's side.

## Sense: a non-detaching authoritative write

A sensed value is installed exactly as a user assignment is, with two qualifications:

- **The same write-authority check, never detaching.** The write is validated against topology as a non-detaching root write and installed without clearing edges, followed by the ordinary cascade. The newest authoritative input wins, by acceptance order: a sense has no privilege over a user write, and no user write has privilege over a sense.
- **The check cannot fail** while the edge rule above holds. If it fails anyway, the failure is **recorded in the session, not raised** — a sense arrives on the controller as a message from a background producer, and raising would poison ingress.

Two consequences:

- **A sensed value supersedes an *undispatched* pending delivery.** The pending delivery is dropped and its claim released: there is no point writing back a value the resource has just told us is stale. An **in-flight** delivery is never cancelled (*Actuate*).
- **Any value write clears the sense error.** Every value write passes through the one installation point, which clears `session.sense_error`, so a valid observation *and* a user assignment both clear it.

Sensing deliberately does **not** do three things:

- **Invalid external state does not stop sensing.** It fails the cell and monitoring continues; the next valid observation recovers it with no user action.
- **Only what the celltype's parser checks is rejected; nothing more.** A mount checks exactly what a user assignment of the same value would check (`contracts/celltypes-and-conversion.md`, the parser table) — no more leniently, no more strictly. For `python`, that parser check includes syntax, so the contract wants a syntax error in a sensed `python` value rejected the same way `ctx.a.set("def (:\n")` would be, as a sense error (see `contracts/mounts.md`, *there is no mount-local parsing*). **Contract ahead of code:** `canon_T` deliberately skips the parser for all four code celltypes, so neither a direct assignment nor a sensed value is actually rejected for a syntax error today — both are sensed as `complete`, and the error surfaces only later, when `.value` is read or when a transformer runs the code. Content that parses but is merely wrong for the program (e.g. a `python` file that parses but raises at runtime) is never rejected here, syntax check or not; that failure surfaces where it would for a user write, in the transformer that runs it.
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

- **Only `complete` actuates.** A node in **any other state** — `waiting`, `blocked`, `failed`, `unwired`, `miswired` — delivers nothing: **a node that is not complete never deletes or rewrites the resource.** A cell mid-recompute does not blank its file, and a failed or blocked cell does not propagate its failure into external state.
- **Actuation is triggered by node changes**, never by a node/resource mismatch on its own. The one exception is the `w`-mode **reassert** (*The oscillation detector*), where a foreign change to an output the Context owns re-requests the current value.
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
| **sense error** | the **cell**: `failed`, with the error's text as the string `.exception` | the resource cannot supply the cell's value | the next valid observation, **any** value write, or detaching |
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

**`ctx.a.mount.error` and `status["sense_error"]` are `MountError` objects** (a `ConflictError`, which subclasses `MountError`, for a tripped detector). **`ctx.a.exception` is a string**, as it is for every Cell failure (`contracts/cells.md`, *Failures*).

The rule that separates the two is the **remote boundary**: the string convention exists because Expressions and Transformations can execute remotely, and exception objects do not transfer well. Attachments are fundamentally local — the transport lives in this process — so the attachment's own error surface is exempt and keeps objects. The cell surface is not exempt, because a cell's failure is read like any other.

Two consequences:

- **`isinstance(ctx.a.mount.error, ConflictError)` is the machine-readable way to tell a tripped detector from a failed write.** There is no other flag for it on the error; `status["state"] == "tripped"` says the same about the session.
- **The same sense error appears as a `MountError` object in `status["sense_error"]` and as a string in `ctx.a.exception`.** Its `"<path>: <reason>"` prefix is **contract** on both surfaces, and it is what identifies a sense error among ordinary cell failures: check the string for that prefix, never `isinstance(ctx.a.exception, MountError)`.

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

### Attach

**Attaching** (`ctx.a.mount(...)`) does all the slow work on the caller's thread, then decides in one turn:

1. validate the request and the node (the table in *Scope*, plus spec validation);
2. reserve the resource with the transport;
3. run the **initial observation** and wait for it. The observation fixes the watch **baseline**, so a change made after it is not lost: it is detected as an ordinary later event once the session is active (observation begins as a post-turn effect of step 4, not at reservation);
4. submit one message. In its turn the controller re-validates, evaluates the **initial decision table** — where the `authority` field decides a file-versus-cell conflict (`contracts/mounts.md`) — against the node's value *at that turn*, installs spec and session, applies a resource → node write or sets a sense error if the table says so, and queues an initial delivery if the table says node → resource;
5. if an initial delivery was queued, **wait for its acknowledgement**, so that attach-then-read from outside the process works. A failed initial write does not make attaching raise; it becomes the attachment's error and is retried.

**Attach blocks, and raises only for an invalid request.** It never raises for the *state* of the resource — missing, unreadable, invalid for the celltype, or not writable. In all of those the attachment is installed and monitoring, each problem is logged once, and when the resource is fixed the attachment recovers with no user action. If it does raise, nothing is installed and the reservation is released.

### Detach

**Unmounting** (`del ctx.a.mount`) is a single turn that:

- marks the session `closing` and removes it, so every later message from it fails the id match;
- drops the pending delivery and releases its claim, and releases the controller's claim on an in-flight one — the transport keeps its own claim until that operation finishes;
- **clears the cell's sense error, unmasking the stored value**;
- releases the registration.

The call then **waits for the transport's cleanup**, bounded by the delivery timeout. Cleanup includes the driver's conditional deletes, so for the file driver a `persistent=False` file has already been deleted — where the conditional-delete rule allows it — by the time `del ctx.a.mount` returns (`contracts/mounts.md`, *Unmount, persistence and close*).

**Node deletion detaches in exactly the same way, including the wait.** `del ctx.a`, or deleting a subcontext that contains attached cells, detaches each attachment as above and **returns only after the transport's cleanup has run**: the conditional delete of a `persistent=False` file has happened when `del` returns, exactly as for unmounting. The leaf-retention claims of a deleted node are released (*Leaf retention*).

**An empty builder of the same celltype detaches and clears.** `ctx.a = Cell(celltype=<same>)` on an attached cell:

- **detaches the attachment**: the spec, the session and the status are removed — `ctx.a.mount.spec` and `ctx.a.mount.status` read `None`, `get_graph()` writes no `mount` entry for the node, the node is no longer actuated, and the registration is released, so the resource can be attached again;
- **clears the cell**: it no longer has a checksum;
- **leaves a persistent resource untouched**: the file is neither rewritten nor deleted.

**Unspecified — deferred:** whether a `persistent=False` file is deleted on this path. Do not depend on either outcome.

An empty builder of a **different** celltype is still refused (*The topology rules an attachment imposes*), and every other clearing spelling is still refused with `AuthorityError`.

**Graph replacement** by `set_graph()` detaches every session **with deletion disabled**, so no conditional delete runs on that path (`contracts/mounts.md`).

### Close

**Closing the Context** (`ctx.close()`, or leaving its `with` block) flushes once, and does not retry:

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

Settled contract that the code does not yet implement, or implements differently. The rules above are the test oracle; each gap below is pinned by an `xfail(strict=False)` test whose reason reads "contract ahead of code". Where the code or an older design text disagrees with a rule above, the rule above wins.

- **A standalone `Cell().mount` loses its message.** It raises a bare `AttributeError('mount')` instead of `AttributeError("mount is only available for bound workflow cells")`: the property's own `AttributeError` is swallowed, and `Cell.__getattr__` raises a new one (*Scope*).
- **The `NodeError` row of *Scope* is unreachable through the public API.** Mounting a **transformer node** raises `AttributeError`, because the transformer handle has no `mount` member; mounting a **missing node** raises `TypeError`, because `ctx.missing.mount` is a `MissingView` and calling it fails. Neither raises `NodeError("Mounts require an existing whole cell node")`.
- **Node deletion returns before the transport's cleanup.** `_delete_subtree` does not wait for the unregister future, so when `del ctx.a` returns, the conditional delete of a `persistent=False` file usually has not run yet (*Detach*). Unmounting with `del ctx.a.mount` does wait.
- **An empty same-celltype builder keeps the attachment.** `ctx.a = Cell(celltype=<same>)` on an attached cell clears the cell but leaves it attached — spec, session and status survive, and `get_graph()` still writes the `mount` entry — instead of detaching it (*Detach*). The cell is left cleared and `unwired` while still attached. The rest already matches the contract: nothing is refused, and the resource is not rewritten.
- **A cell below a miswired transformer stays `waiting` forever.** `Context._apply_upstream_state` has no branch for `miswired` or `blocked-by-miswiring`, so the transformer's result cell never becomes `blocked` (`contracts/node-state-lifecycle.md`). The actuate rule still holds — the cell is not `complete`, so nothing is delivered — but the cut barrier's graph-quiescence step never completes, so `ctx.mounts.sync()` times out instead of resolving with a report (*The cut barrier*). `ctx.compute()` times out for the same reason.
- **"No longer a cell" cannot be reached by assigning a transformer.** `ctx.a = f` or `ctx.a = delayed(f)` onto a cell node raises `TypeError` from `_retain_producer`, mounted or not, instead of the `NodeError` of `contracts/workflow-context.md`. The spec stays, which is the contractual outcome of a refused assignment; only the exception type is wrong. Node deletion is the only public path to the post-turn backstop detach (*The durable spec and the ephemeral session*).
- **A `python`/`yaml` syntax error is not rejected at sense time.** `canon_T` deliberately skips the parser for all four code celltypes, so neither a direct assignment nor a sensed value is rejected for a syntax error — both are sensed as `complete`. This holds identically for a mount (`contracts/mounts.md` carries the same gap); the error surfaces only later, when `.value` is read or a transformer runs the code.

### Current limitations

These are properties of the code that the rules above permit, plus one divergence that cannot be reached. None of them is test-pinned as a gap.

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

Smaller rough edges:

- **On an *unattached* cell the surface answers `None` — except `clear_error()`.** `.mount.spec`, `.mount.status` and `.mount.error` all return `None`, and `del ctx.a.mount` is a silent no-op, but `ctx.a.mount.clear_error()` raises a bare `KeyError(<node path>)`. **Whether that `KeyError` is contract is deferred**; until it is decided, do not depend on the exception type.
- **Delivery retries are dispatched by the post-turn pass, and `_mount_tick` is an explicit no-op.** The attachment layer owns no timer. In practice the file driver's broker enqueues one `_mount_tick` message per registration per poll interval, and since the post-turn pass runs after **every** turn, a due backoff fires within about one poll interval even on an otherwise idle Context (measured: ~1.5 s for the first, 1 s retry). A driver that sends no tick — `ManualDriver` — fires a due retry only when something else causes a turn; `ctx.mounts.sync()` is one.
- **A failure inside the observation handler becomes `session.error` as a bare `MountError(str(exc))`**, without the `"<path>: "` prefix that every other `MountError` carries. Strictly this breaks the prefix contract, but the path cannot be reached while the edge rule holds (the write-authority check of a sense cannot fail, *Sense*), so no test pins it.
- **Malformed internal messages are dropped silently.** `_mount_delivered` and `_mount_cut` validate their payload shape and return without effect on anything unexpected, because they run as class-5 messages and raising would poison ingress.

## Non-goals

- **A plugin API.** See the top of this page. The contract describes the attachments that exist.
- **Standalone, sub-path, pin and code mounts.** Only a bound whole cell node can be mounted (*Scope*) — this is architectural, not a version gap: a standalone `Cell` has no controller, a sub-path write is a read-modify-set transaction on the root with nothing of its own to compare against, and a pin or code handle is not a cell. The remedy is always the same: attach a cell and connect it. (Bound `as_celltype` handles are the one undecided target; see *Scope*.)
- **Continuous external ownership** (an `edit_policy="external-owned"` that would forbid later user assignment). Deferred with a named condition: if it is added it gets its own name and specification. It must **not** be expressed by redefining the `authority` field's `"file"` value, which only resolves the initial conflict (`contracts/mounts.md`).
- **Cross-process locking or exclusivity.** The registry is a safety net within one process (`contracts/mounts.md`); two processes sharing a resource are handled by conditional writes and the detector, not prevented.
- **A settledness predicate without a cut.** `settled()` was considered and rejected.
- **Hard cancellation of an in-flight delivery.** It is never cancelled, by design: the write is either done or not, and cancelling it would leave the belief about the resource undefined.
- **Attachment-driven computation.** A delivery resolves and never fingertips; attaching is not a way to make Seamless do work.
