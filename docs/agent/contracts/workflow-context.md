# The workflow Context (Contract)

**A `Context` is a DAG of nodes plus a runtime that keeps it in equilibrium.** Its essence fits in one sentence: **reactivity is re-building with fresh snapshots.** When a node takes a new value, the Context builds new immutable `Expression` / `Transformation` definitions from the new snapshot and fires them; the content-addressed cache reuses every sub-result that did not actually change. **The functional layer never mutates, and nothing below the Context knows a Context exists** — a Transformation the Context submits is indistinguishable from one submitted by hand, and its identity and caching are exactly those of `contracts/identity-and-caching.md`.

Four consequences are contract in their own right:

- **The Context stores only nodes.** It holds no `Cell`, no `Expression` and no `Transformation`. Expressions and Transformations are *private to the Context*: materialized per tick from the edge path plus the current upstream checksum, fired, and discarded. `Cell` and `Transformer` are **views over a node**, as `contracts/cells.md` and `contracts/pins.md` state from the handle's side.
- **Binding is a move, not a copy.** Assigning a standalone builder into a Context migrates its private state into the node and abandons the private shadow; the node is then the single source of truth. There is no dual-write window, and two handles for one node are deliberate aliases.
- **Handle identity carries no meaning.** `ctx.a is not ctx.a`. Dependencies are captured by content — a node path on an edge — never by view identity, so `id()`-keyed caches over handles must not be used. A handle whose node is gone raises `StaleWorkflowHandleError` on its next use.
- **Re-building is cheap.** The per-tick materialization cost is bounded to the invalidated cone, and is a small hash over checksum-sized inputs — never a re-hash of buffers.

This page is the Context as a **runtime and an API**. The **node state lifecycle** — the seven node states (`unwired`, `miswired`, `blocked`, `waiting`, `computing`, `complete`, `failed`), the glitch-free cascade, block reasons, speculative supersession and grace holds — is `contracts/node-state-lifecycle.md` and is deliberately not specified here; this page names states only where a rule depends on them. Cells are `contracts/cells.md`, pins are `contracts/pins.md`, the attachment framework — sensing external state into a node, actuating a node's value out of it — is `contracts/attachments.md`, and the file driver is `contracts/mounts.md`.

Code locations:

| Concern | Module / symbol |
|---|---|
| The Context itself | `seamless_workflow.context.Context` (a composition of `RuntimeAPI`, `Reactive` and `AttachmentRuntime`) |
| Durable graph | `seamless_workflow.graph` (`ContextGraph`, `Node`, `NodeState`, `CellConfig`, `TransformerConfig`) |
| Controller thread and sequenced ingress | `seamless_workflow.controller.Controller`; `seamless_workflow.ingress` (`controller_method`, `_wait`, `_wait_async`, `_edit`, `_prepare_assignment`) |
| Reactive derivation and execution | `seamless_workflow.reactive.Reactive` |
| Barriers, snapshots, leases | `seamless_workflow.runtime_api.RuntimeAPI` (`_install_wait`, `_check_barriers`, `_snapshot_transformer`) |
| Transient run records and speculation | `seamless_workflow.scheduler` (`ContextRuntime`, `RunRecord`, `Scheduler`) |
| Bound handles | `seamless_workflow.builder_state` (`BoundCellBackend`, `BoundPinBackend`, `BoundTransformerBackend`) |
| Namespaces | `seamless_workflow.views` (`MissingView`, `SubContextView`) |
| Local projection and join workers | `seamless_workflow.sidework` (`evaluate_cell`, `evaluate_projection`, `Lease`, `SideLoop`) |
| Errors | `seamless_workflow.errors` |
| Process-level registry and shutdown | `seamless_workflow.lifecycle` |

## Constructing and closing

```python
ctx = Context(expression_execution="auto")   # "auto" | "local" | "remote"

with Context() as ctx:
    ...
```

- `expression_execution` is **keyword-only** and fixes the placement policy for every Expression job this Context fires; any other value raises `ValueError`. What the three values mean, and the fact that only `"auto"` may downgrade, is `contracts/expressions.md`.
- A Context can only be constructed while Seamless is open.
- **`Context.close()` is idempotent**, and is also the context-manager exit. It closes admission first, then runs one ordered shutdown turn: registered barriers fail, outstanding Expression and Transformation memberships are cancelled, the side loop drains, graph and runtime roles are released, and both Context threads are joined. Late notifications arriving after that turn are discarded and their payload ownership released.
- A bound handle used after close raises `ClosedContextError`.
- Every Context is kept in a weak process-level registry, so `seamless.close()` closes the Contexts too.

## Nodes, names and namespaces

- **A node is created by assignment to a name that does not exist yet.** `ctx.a` afterwards returns a fresh handle for that node.
- **A name that is not a node is a namespace placeholder, not an error.** `ctx.foo` for an unknown path returns a *view* whose attribute and item access extend the path, so `ctx.foo.bar = 1` creates the node at path `("foo", "bar")`. Item access stringifies its key: `ctx["a"]` and `ctx.a` are the same node.
- **`ctx.sub = Context()` declares a namespace**, not a nested runtime: it marks the path as a namespace of *this* Context. Assigning a namespace view copies that subtree. A genuine sub-Context — one with its own controller and its own equilibrium — is out of scope (see *Non-goals*).
- **`mounts` is reserved.** `ctx.mounts` is the Context's mount API — the external synchronization barrier and the per-mount error map — and assigning to it raises `AttributeError("mounts is reserved for the Context mount API")`. A graph node at that path is refused with `PathError`. See `contracts/mounts.md`.
- `del ctx.a` deletes the node, and deleting a namespace path deletes its whole subtree. Deleting a node cancels its remaining run memberships (softly — see *Speculation control*).

## What an assignment means

`ctx.a = X` is dispatched by the type of `X` and by whether `a` already exists:

| `X` | On a new name | On an existing node |
|---|---|---|
| a **bound source** (another node's handle, or a projection of one) | creates a cell node with the source's celltype and an edge from it | on a cell: replaces the incoming edge (detaching). On a transformer: **converts the node to a cell**, cancelling its runs and releasing its producers |
| a standalone **`Cell`** builder | creates a cell node from the builder | replaces the cell's configuration; on a transformer node it is a `NodeError` |
| a standalone **`Transformer`** builder | creates a transformer node | replaces the transformer's configuration; on a cell node it is a `NodeError` |
| a **callable**, a code string, or a transformer configuration | creates a transformer node | sets the transformer's code; on a cell node it raises `NodeError("Cannot replace a cell node with transformer code")` |
| a **`Context`** | declares a namespace | — |
| a **namespace view** | copies that subtree | — |
| anything else (a value) | creates a cell node holding that value | writes the value, detaching any incoming edge |

Two rules are worth stating separately:

- **Connecting is always assignment.** There is no `connect()` and no source setter. `contracts/cells.md` and `contracts/pins.md` give the two write families — *declare the input* versus *write what you own* — and the authority rule that decides when an assignment may detach an existing producer.
- **A transformer's result is read-only as a target.** A producer operation aimed at it raises `ReadOnlyEndpointError`.

**Cycles are rejected at declaration time.** Adding an edge checks reachability from the target back to the source and raises `DependencyError` if the new edge would close a cycle. Parallel edges into different pins of one transformer are not a cycle and are accepted.

**Connection targets are limited to the root or one level below it** — a mapping key, an attribute name, or an integer sequence index — and a slice is never a connection target. That rule, the read-modify-set model for sub-path writes, and cell-level joins belong to `contracts/cells.md` and are not repeated here.

## The controller: one thread, sequenced ingress

- **One controller thread per Context is the sole mutator of the graph.** Every public operation is routed through it and executed in a turn, and nothing interleaves with a turn. That is what makes invalidation atomic and what makes binding free of a dual-write window.
- **Ingress is sequenced.** Envelopes are immutable, acceptance order is monotonic, and operations are prioritized by class: barrier installation and withdrawal, ordinary reads, conditional commits, and the continuations that carry results back each have their own place in that order. A result arriving from execution is handled in a later turn, synchronously on the controller, exactly like an edit.
- **A controller turn never materializes.** A read taken in a turn returns a **lease** — a snapshot of a checksum plus its celltype, with its reference already claimed — and resolution to a buffer or a value happens on the caller's side, outside the turn. Projections, joins and other local value work run on a separate **side loop**, never on the controller thread.
- **Public re-entry is forbidden.** Calling a public Context operation, or a bound handle, from inside a controller turn raises `ReentrantContextError`.
- **An internal failure poisons ingress.** If a continuation fails unexpectedly, the Context raises `ControllerFailedError` for subsequent ingress, fails pending barrier predicates and cancels adapters. This is deliberate: an asynchronous error must never leave an invisible stalled barrier. `close()` still works on a poisoned Context; nothing else does.
- **Ordinary reads never wait.** A bound `.checksum` / `.buffer` / `.value` reports current availability and returns `None` when nothing is published; waiting is the job of the explicit barriers below. `contracts/cells.md` states the same rule from the handle's side, and marks it as the one place where bound and standalone reads deliberately differ.

## Barriers: `compute` and `computation`

| Call | Waits until |
|---|---|
| `ctx.compute(timeout=None)` / `await ctx.computation(timeout=None)` | **no node in the Context** is `waiting` or `computing` |
| `node.compute(timeout=None)` / `await node.computation(timeout=None)` (a Cell, Pin or Transformer handle) | **that node and its upstream cone** are no longer `waiting` or `computing` — for a Pin, which has no node of its own, this is its **owning Transformer's** barrier (`contracts/pins.md`) |
| `ctx.mounts.sync(timeout=None)` / `await ctx.mounts.synchronization(timeout=None)` | the **external** cut is settled: every external change before the final cut has been sensed and propagated, the graph is quiescent, and every complete node value has been delivered to its resource or its attachment reports why not. Returns a `SyncReport`. The barrier is driver-generic (`contracts/attachments.md`); it is spelled `mounts` because the file driver is the only production one (`contracts/mounts.md`) |

- A barrier is a **predicate installed in a turn** and satisfied in the turn that makes it true; the caller is released then.
- **A barrier timeout raises `TimeoutError`.** Both a timeout and an async cancellation **withdraw the predicate without cancelling any graph work**: a barrier is a wait, never a control operation.
- A barrier on a path whose node has been deleted raises `StaleWorkflowHandleError`.
- A **reading** barrier — the form behind a bound `compute()` that returns a checksum — additionally reports the outcome. If the node settles in `unwired` or `blocked` it raises a `NodeError` naming the state and the block reason; if it settles in `failed` it raises the node's own recorded exception.
- **Quiescence is a property of node states only.** A `complete` node may still have a superseded run in flight; see *Speculation control* below, and `contracts/node-state-lifecycle.md` for what the states mean.
- **`compute()` stays graph-only and never waits for external state.** External settlement is a separate barrier, `ctx.mounts.sync()`, and it is stateful: it cuts, waits for quiescence, waits for deliveries, and starts another round if anything moved. `contracts/attachments.md` specifies it; there is deliberately no `settled()` predicate.

## Writes through the Context

The write families and the authority rule that separates them are in `contracts/cells.md`. What belongs here is what the Context does with them.

- **Serialization happens before ingress.** A value is serialized, and transformer code and builders are prepared, on the caller's side; the controller receives checksums.
- **A whole-checksum write is validated against the node celltype using HashType metadata, and then installed without resolving it.** The buffer need not be present. The consequences of an unresolvable checksum appear later, at a read (`contracts/hashtype.md`, `contracts/cells.md`).
- **A sub-path write is one optimistic transaction.** Lease the current root checksum in a turn, resolve and modify it off the controller, then commit conditionally against the base checksum and the node revision. A losing commit retries, **at most eight times**, and then raises `ConcurrentUpdateError`. If the root has no checksum and the node is `waiting`, the write waits on a barrier and retries; otherwise it raises `ValueUnavailableError` — except that a string/attribute path into an *unwired* cell starts from an empty mapping. This is the read-modify-set model of `contracts/cells.md`, and the Context is what serializes it. (A sub-path write always targets a cell node, which is never `computing` — `contracts/node-state-lifecycle.md`.)
- **Assignment detaches edges covered by the write; an explicit `set` does not** — again `contracts/cells.md`, and again a root-level act only.

## Speculation control: `prune`

The Context **launches replacement work immediately and delays only the cancellation of the superseded run**. Obsolete runs may therefore still occupy backend slots after every node has reached equilibrium: **node-state quiescence does not by itself mean the cluster is idle.**

- **`ctx.prune()`** closes that gap. It **softcancels every superseded or grace-held run immediately**, leaving only the current wavefront, and returns `{"cancelled": <count>}`. It is lightweight and repeatable — not a freeze, and not a commit.
- **`ctx.a.prune()`** does the same for `ctx.a` and its **downstream cone** only. `ctx.prune()` is that same call at the graph root. This is the user's manual control over which superseded work to reclaim; the scheduler does not guess a tighter policy.
- **The Context only ever softcancels**, including on node deletion, because a running transformation may legitimately be shared with sibling nodes, with superseded runs, and with other processes. **Hard cancellation is never issued by the reactive layer.** What soft and hard mean is `contracts/cancellation.md`; `contracts/expressions.md` states the same soft-only rule for Expressions.
- The hold policy that decides *how long* a superseded run is kept before `prune()` or the scheduler reclaims it is part of the node state lifecycle; see that page.

## Execution

- **The workflow layer never invokes a raw callable.** It submits immutable, checksum-wired snapshots built through the ordinary Transformer/Transformation path, and the ordinary transformation cache executes them (`contracts/direct-delayed-and-transformation.md`, `contracts/execution-backends.md`). A cache hit is not a shortcut around the runtime: it still arrives through a later controller turn.
- A node is `computing` **from dispatch onwards, including the window in which its transformation identity is being constructed.** There is no separate "constructing" state, and `computing` is not delayed until the identity exists.
- **Expression jobs** — projections, and conversions on edges — use the ordinary asynchronous evaluator with the Context's placement policy (`expression_execution`), with member-scoped cancellation; their results re-enter through a controller turn like any other.
- **Determinism is assumed.** The Context's compare-and-reuse loop assumes that the same inputs give the same result checksum. Irreproducible transformations are out of scope for workflows. Accidental nondeterminism being masked by the content-addressed cache is a universal Seamless property, not a Context hazard (`contracts/identity-and-caching.md`, `contracts/scratch-witness-audit.md`).

## Graph serialization

- **`ctx.get_graph()` returns the durable graph**: nodes, configurations, edges and literal producers — never runtime state.
- **`ctx.set_graph(graph)` replaces it wholesale.** It is ordered so that the new graph's claims are acquired **before** any live role is released. It cancels every current and superseded run, detaches mount sessions, and resets the runtime.
- **`ctx.set_graph(graph, mounts=True)` — the default — also attaches every mount spec in the new graph, and therefore blocks and can write files.** Reservations and initial reads are prepared in parallel on the caller's side, one message replaces the graph and all sessions atomically, and the call waits for every initial acknowledgement. `mounts=False` strips the specs; **graphs of unknown origin must be loaded that way** (`contracts/mounts.md`).
- **Run generations are never reused across a replacement**, and node revisions are bumped for the same reason: a late completion from the old graph can never be mistaken for a run at the same path in the new one.
- **Graph loading never executes code to reconstruct callables.**

## The Context surface: which calls wait, and which errors mean what

Only the operations this page specifies are listed; handle-level calls are in `contracts/cells.md` and `contracts/pins.md`.

| Call | Waits? | Returns |
|---|---|---|
| `ctx.a = X`, `del ctx.a`, and every write | no — one controller turn, serialization done before ingress | `None` |
| `ctx.a`, `ctx.foo.bar` (unknown path) | no | a fresh handle, or a namespace view |
| `ctx.compute()` / `await ctx.computation()` | **yes** — graph-wide barrier | `None`, or raises `TimeoutError` |
| `node.compute()` / `await node.computation()` | **yes** — that node's upstream cone | the node's checksum for a reading barrier; raises on `unwired`, `blocked` or `failed` |
| `ctx.mounts.sync()` / `await ctx.mounts.synchronization()` | **yes** — the external cut barrier | a `SyncReport`; raises `TimeoutError` |
| `ctx.mounts.errors` | no | `{node path: error}`, computed without a cut |
| `ctx.prune()`, `ctx.a.prune()` | no | `{"cancelled": <count>}` |
| `ctx.get_graph()` | no | the durable graph |
| `ctx.set_graph(graph, mounts=False)` | no — but it cancels every run | `None` |
| `ctx.set_graph(graph)` (i.e. `mounts=True`) | **yes** — it blocks through every mount's initial read and first delivery acknowledgement, **and it can write files** | `None` |
| `ctx.close()` | **yes** — one ordered shutdown turn, joining both threads | `None`; idempotent |

| Error | Raised when |
|---|---|
| `ValueError` | `expression_execution` is not `"auto"`, `"local"` or `"remote"` |
| `ClosedContextError` | a bound handle is used after `close()` |
| `ControllerFailedError` | ingress is poisoned by an internal continuation failure; only `close()` still works |
| `ReentrantContextError` | a public Context operation or a bound handle is called from inside a controller turn |
| `StaleWorkflowHandleError` | a handle — or a barrier — names a node that has been deleted |
| `NodeError` | an assignment mismatches the node kind, or a reading barrier settles in `unwired` or `blocked` |
| `ReadOnlyEndpointError` | a producer operation targets a transformer's result |
| `DependencyError` | a new edge would close a cycle |
| `ValueUnavailableError` | a sub-path write finds no root checksum and the node is not `waiting` |
| `ConcurrentUpdateError` | a sub-path commit loses eight times |
| `TimeoutError` | a barrier times out; the predicate is withdrawn and no graph work is cancelled |
| `AuthorityError`, `PathError` | the handle-level rules of `contracts/cells.md`; also the attachment topology rules (`contracts/attachments.md`) |
| `MountError` | never raised — *reported*, as an object on `ctx.a.mount.error` and as a string on `ctx.a.exception` (`contracts/attachments.md`) |
| `ConflictError` | a `MountError` subclass; also never raised, and latched on the mount when the oscillation detector trips |

## Implementation status and current limitations

Settled contract that the code does not yet implement, or implements differently. Where a design document and the code disagree, **the code wins**, and the disagreement is listed here.

- **Future-wiring is not implemented; the runtime is checksum-wired only.** A node leaves `waiting` for `computing` exactly when all of its inputs are concrete checksums. The design's future-wired Expressions and Transformations — a registered continuation keyed by its upstream's identity, which would let a `waiting` cone advance before the checksums exist — is deferred to the fire-and-forget milestone, together with the delayed cancellation that would let a checksum-wired submission latch onto it.
- **Fire-and-forget is deferred.** Detaching the Context process while a cluster advances the workflow headlessly needs future-wiring and is not available. `prune()` — the first half of it — is.
- **There is no dependency-declaration contract.** How a declared dependency edge is picked up, and how it transitions between the future-wired and checksum-wired regimes, is an open design question; nothing may depend on an answer.
- **A bound public read does not validate and does not record**, and a bound read of a non-existent projection raises rather than reporting. `contracts/cells.md` states both; in each case the standalone behaviour is the intended contract.
- **Buffer arrival has no subscription primitive.** A missing buffer becomes a visible `failed` node, and the retry is `clear_exception()` after the caller has made the buffer available. The Context deliberately does not invent a buffer-availability event, and deliberately does not treat cancellation as an authoritative result.
- **Individual graph construction reconciles the whole graph.** Building a large graph node by node is much slower than one `set_graph`.
- **Tests are run one process per file.** Process-global cache and refholder state carries between files, so combining Seamless test files in one pytest run produces spurious failures.

## Non-goals

- **Sub-contexts.** A namespace is a path prefix inside one Context, with one controller and one equilibrium. A nested Context with its own runtime is not a feature.
- **Non-eager mode and activation leases.** Unratified; nothing may depend on them.
- **Cycles.** Out of scope, not merely rejected as an implementation limit: the cascade assumes a DAG, and a new edge that would close one is refused at declaration time (`DependencyError`).
- **A transient-failure state.** `failed` is one state, and the block-reason vocabulary has exactly two members. Classifying a failure as transient and retrying it is a Transformation/backend concern, not Context logic.
- **Mandatory preemption.** Reclaiming a slot from a superseded run in favour of a current run elsewhere is, at most, an optional nicety; `prune()` is the supported control.
- **Epoch-stamping of the invalidation cone.** The cone is marked eagerly; a generation/epoch scheme was considered and rejected.
- **Storing Cells, Expressions or Transformations.** The Context holds nodes. Anything that looks like a stored Expression is a snapshot it fired and discarded.
- **Handle identity.** As for Cells and Pins: views are interchangeable, and nothing may be keyed on them.
