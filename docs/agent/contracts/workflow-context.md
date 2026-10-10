# The workflow Context (Contract)

The canonical authoring namespace is `seamless.workflow`, which exports `Context`, `Cell`, and the `Transformer` factory together.

**A `Context` is a DAG of nodes plus a runtime that keeps it in equilibrium.** Its essence fits in one sentence: **reactivity is re-building with fresh snapshots.** When a node takes a new value, the Context builds new immutable `Expression` / `Transformation` definitions from the new snapshot and fires them; the content-addressed cache reuses every sub-result that did not actually change. **The functional layer never mutates, and nothing below the Context knows a Context exists** — a Transformation the Context submits is indistinguishable from one submitted by hand, and its identity and caching are exactly those of `contracts/identity-and-caching.md`. The Transformer-side builder and snapshot contract is `contracts/transformers.md`.

Four consequences are contract in their own right:

- **The Context stores only nodes.** It holds no `Cell`, no `Expression` and no `Transformation`. Expressions and Transformations are *private to the Context*: materialized per tick from the edge path plus the current upstream checksum, fired, and discarded. `Cell` and `Transformer` are **views over a node**, as `contracts/cells.md` and `contracts/transformers.md` state from the handle's side.
- **Binding is a move, not a copy.** Assigning a standalone builder into a Context migrates its private state into the node and abandons the private shadow; the node is then the single source of truth. There is no dual-write window, and two handles for one node are deliberate aliases.
- **Handle identity carries no meaning.** `ctx.a is not ctx.a`. Dependencies are captured by content — a node path or symbol on an edge — never by view identity, so `id()`-keyed caches over handles must not be used. A handle whose node is gone, or that was invalidated when another handle to the same anonymous node was assigned a name (*What an assignment means*), raises `StaleWorkflowHandleError` on its next use.
- **Re-building is cheap.** The per-tick materialization cost is bounded to the invalidated cone, and is a small hash over checksum-sized inputs — never a re-hash of buffers.

This page is the Context as a **runtime and an API**. The **node state lifecycle** — the seven node states (`unwired`, `miswired`, `blocked`, `waiting`, `computing`, `complete`, `failed`), the glitch-free cascade, block reasons, speculative supersession and grace holds — is `contracts/node-state-lifecycle.md` and is deliberately not specified here; this page names states only where a rule depends on them. Cells — including anonymous cells, symbols, fusion and elision — are `contracts/cells.md`; pins are `contracts/pins.md`; the attachment framework — sensing external state into a node, actuating a node's value out of it — is `contracts/attachments.md`; and the file driver is `contracts/mounts.md`.

Code locations:

| Concern | Module / symbol |
|---|---|
| The Context itself | `seamless_workflow.context.Context` (a composition of `RuntimeAPI`, `Reactive` and `AttachmentRuntime`) |
| Durable graph | `seamless_workflow.graph` (`ContextGraph`, `Node`, `NodeState`, `CellConfig`, `TransformerConfig`) |
| Controller thread and sequenced ingress | `seamless_workflow.controller.Controller`; `seamless_workflow.ingress` (`controller_method`, `_wait`, `_wait_async`, `_edit`, `_prepare_assignment`) |
| Reactive derivation and execution | `seamless_workflow.reactive.Reactive` |
| Barriers, FrozenTransformers, leases | `seamless_workflow.runtime_api.RuntimeAPI` (`_install_wait`, `_check_barriers`, `_freeze_transformer`) |
| Transient run records and speculation | `seamless_workflow.scheduler` (`ContextRuntime`, `RunRecord`, `Scheduler`) |
| Bound handles | `seamless_workflow.builder_state` (`BoundCellBackend`, `BoundPinBackend`, `BoundTransformerBackend`) |
| Namespaces | `seamless_workflow.views` (`MissingView`, `SubContextView`) |
| Cell join formation and evaluation | `seamless.celljoin_class.CellJoin`; `seamless.checksum.celljoin` (`evaluate_celljoin_local_async`, `evaluate_celljoin_placed`) |
| Local projection workers and leases | `seamless_workflow.sidework` (`evaluate_projection`, `Lease`, `SideLoop`) |
| Errors | `seamless_workflow.errors`; `ValueUnavailableError` is defined in seamless-core (`seamless.cell_errors`, exported as `seamless.ValueUnavailableError`) and re-exported here |
| Process-level registry and shutdown | `seamless_workflow.lifecycle` |

## Constructing and closing

```python
ctx = Context(expression_execution="auto")   # "auto" | "local" | "remote"

with Context() as ctx:
    ...
```

- `expression_execution` is **keyword-only** and fixes the placement policy for every Expression job this Context fires; any other value raises `ValueError`. What the three values mean, and the fact that only `"auto"` may downgrade, is `contracts/expressions.md`.
- A Context can only be constructed while Seamless is open.
- **`Context.close()` is idempotent**, and is also the context-manager exit. It closes admission first, then runs one ordered shutdown turn: registered barriers fail, outstanding Expression and Transformation memberships are **softcancelled**, the side loop drains, graph and runtime roles are released, and both Context threads are joined. Late notifications arriving after that turn are discarded and their payload ownership released. Close is no exception to the soft-only rule (*Speculation control*): a run shared with another caller survives the Context's departure.
- After close, a bound handle raises `ClosedContextError` on use. A Context-level call (`ctx.a = …`, `ctx.compute()`, `ctx.prune()`, `ctx.get_graph()`, …) is refused because admission is closed; **its exception type is unspecified** — today it is also `ClosedContextError`, but do not depend on it.
- Every Context is kept in a weak process-level registry, so `seamless.close()` closes the Contexts too.

## Nodes, names and namespaces

- **A named node is created by assignment to a name that does not exist yet.** `ctx.a` afterwards returns a fresh handle for that node.
- **A name that is not a node is a namespace placeholder, not an error.** `ctx.foo` for an unknown path returns a *view* whose attribute and item access extend the path, so `ctx.foo.bar = 1` creates the node at path `("foo", "bar")`. Item access stringifies its key: `ctx["a"]` and `ctx.a` are the same node.
- **An anonymous node exists while an edge refers to its recipe.** `ctx.a[3]`, `ctx.a.b` and `ctx.b.as_celltype("plain")` each return a handle to the recipe of an **anonymous** cell node: it has a symbol and no name, never appears in the Context's attribute namespace, and is reached only through a handle or as the source of an edge. A handle neither creates nor holds it: it is created, and its symbol assigned, when an edge or another entry first refers to the recipe, and it is held by those references only. References to the same recipe share one node. Symbols, fusion and elision are `contracts/cells.md`, *Connecting*.
- **`ctx.sub = Context()` declares a namespace**, not a nested runtime: it marks the path as a namespace of *this* Context. Assigning a namespace view copies that subtree. A genuine sub-Context — one with its own controller and its own equilibrium — is out of scope (see *Non-goals*).
- **`mounts` and `shares` are reserved.** `ctx.mounts` is the Context's mount API — the external synchronization barrier and the per-mount error map — and assigning to it raises `AttributeError("mounts is reserved for the Context mount API")`. `ctx.shares` is the share API; assigning to it raises `AttributeError("shares is reserved for the Context share API")`. A graph node at either path is refused with `PathError`. See `contracts/mounts.md` and `contracts/shares.md`.
- `del ctx.a` deletes the node, and deleting a namespace path deletes its whole subtree. Deleting a node softcancels its remaining run memberships (*Speculation control*).

## What an assignment means

`ctx.a = X` is dispatched by the type of `X` and by what `a` currently is:

| `X` | `a` does not exist | `a` is a cell | `a` is a transformer |
|---|---|---|---|
| a handle to a **named** node | creates a cell with the source's `celltype` and an edge from the source | replaces the incoming edge (detaching); `a` keeps its own `celltype` and converts into it | **converts `a` to a cell** with an edge from the source, softcancelling its runs and releasing its producers |
| an **anonymous** handle — a bound projection (`ctx.b[3]`, `ctx.b.x`) or `as_celltype` | creates a cell with the handle's `celltype`, fed by a **dummy edge** (an identity) from the handle's anonymous node; nothing is renamed, and the handle and every other handle stay valid. On save, the dummy edge of a single link is written as `a`'s own incoming link (`contracts/cells.md`, *Assigning an anonymous handle*) | adds an edge **from the symbol**, as in the row above; the handle stays anonymous | as in the row above, with an edge from the symbol |
| a standalone **`Cell`** builder | creates a cell from the builder | replaces the cell's configuration (below, for a mounted cell) | `NodeError` |
| a standalone **`Transformer`** builder | creates a transformer | `NodeError` | replaces the transformer's configuration |
| a **callable** or a transformer configuration | creates a transformer | `NodeError("Cannot replace a cell node with transformer code")` | sets the transformer's code |
| a **`str`** | creates a **cell** holding the string, like any other value | writes the value (detaching) | sets the transformer's code (pins: see below) |
| a **`Context`** | declares a namespace | — | — |
| a **namespace view** | copies that subtree | — | — |
| anything else — a value (a `Checksum` is read as a declared reference, `contracts/cells.md`, *Celltype `checksum`*) | creates a cell holding the value | writes the value, detaching any incoming edge | `NodeError` |

A dash means this page does not specify the combination. The rules the table relies on:

- **Connecting is always assignment.** There is no `connect()` and no source setter. `contracts/cells.md` and `contracts/pins.md` give the two write families — *declare the input* versus *write what you own* — the authority rule that decides when an assignment may detach an existing producer, and the **wiring rule** that refuses a converting edge behind a projection. The wiring rule looks through an anonymous handle's symbol to its entry, so an entry that carries a path counts as a source that carries one.
- **A code string is only code on a transformer.** Assigned to a new name or onto a cell, a `str` is a value; to create a transformer from code, assign a callable or a `Transformer` builder. *Unspecified — deferred:* whether `ctx.tf = "code"` on an existing transformer drops its pins (today it can, while `ctx.tf.code = …` keeps them).
- **An empty builder of the same celltype detaches a mount and clears the cell.** `ctx.a = Cell(celltype=<same>)` on a mounted cell detaches the attachment — spec, status and session removed, no `mount` entry in `get_graph()` — and leaves the cell with no checksum; a persistent file is left untouched. A builder of a *different* celltype is refused as a retype (`ValueError("Mounted celltype cannot change; unmount first")`). See `contracts/attachments.md`, *Detach*, and `contracts/mounts.md`, *Unmount, persistence and close*.
- **A handle belongs to its Context.** Assigning any handle — named, anonymous or projection — into a *different* Context raises `DependencyError`.
- **A transformer's result is read-only as a target.** Any producer operation aimed at it raises `ReadOnlyEndpointError`, and attribute assignment `ctx.tf.result = …` is one such operation (`contracts/transformers.md`, *Pins and result*).

**Cycles are rejected at declaration time.** Adding an edge checks reachability from the target back to the source and raises `DependencyError` if the new edge would close a cycle. Parallel edges into different pins of one transformer are not a cycle and are accepted.

**Connection targets are limited to the root or one level below it** — a mapping key, an attribute name, or an integer sequence index — and a slice is never a connection target. **A cell with sub-path edges may hold only a literal at its root, never a source**: `ctx.join = ctx.base; ctx.join["k"] = ctx.other` is refused, and so is the reverse order (the exception class is deferred). That rule, the read-modify-set model for sub-path writes, and cell-level joins belong to `contracts/cells.md` and are not repeated here.

## The controller: one thread, sequenced ingress

- **One controller thread per Context is the sole mutator of the graph.** Every public operation is routed through it and executed in a turn, and nothing interleaves with a turn. That is what makes invalidation atomic and what makes binding free of a dual-write window.
- **Removing an anonymous node is a controller operation too.** When neither an edge nor a live handle holds an anonymous node any more, its symbol entry's removal is **posted to the controller**, which performs it in a turn. A handle's finalizer only posts the removal; it never mutates the graph itself, whatever thread it runs on.
- **Ingress is sequenced.** Envelopes are immutable, acceptance order is monotonic, and operations are prioritized by class: barrier installation and withdrawal, ordinary reads, conditional commits, and the continuations that carry results back each have their own place in that order. A result arriving from execution is handled in a later turn, synchronously on the controller, exactly like an edit.
- **A controller turn never materializes.** A read taken in a turn returns a **lease** — a snapshot of a checksum plus its celltype, with its reference already claimed — and resolution to a buffer or a value happens on the caller's side, outside the turn. Projections, joins and other local value work run on a separate **side loop**, never on the controller thread.
- **Public re-entry is forbidden.** Calling a public Context operation, or a bound handle, from inside a controller turn raises `ReentrantContextError`.
- **An internal failure poisons ingress.** If a continuation fails unexpectedly, the Context raises `ControllerFailedError` for subsequent ingress, fails pending barrier predicates and cancels adapters. This is deliberate: an asynchronous error must never leave an invisible stalled barrier. `close()` still works on a poisoned Context; nothing else does.

## Reads

- **Reads on a named node never wait.** A bound `.checksum` reports the node's current result, or `None` when it has none; it never evaluates, dispatches or probes a cache (the dummy-Expression exception is `contracts/cells.md`, *Reads*). Waiting is the job of the explicit barriers below.
- **On a named node that is not `complete`, `.buffer` and `.value` return `None`.** They neither wait nor raise, and that includes a `failed` node: its failure is on `.exception`, and only `run()` raises it (`contracts/cells.md`, *Failures*, *How a failure is delivered*; ruled 2026-09-28). On a `complete` node they materialize the result checksum, and a materialization failure — `CacheMissError` for an unreachable buffer, a validation or deserialization error — is raised to the caller on every read and never recorded: the node stays `complete`. This is what `contracts/cells.md`'s *Work* table means by "buffer / value, or raise": the raise concerns a result that exists and cannot be materialized, never a result that does not exist yet.
- **Anonymous and projection handles pull over the parent's checksum.** A read or `compute()` through such a handle builds the handle's own Expression over the parent's current checksum and evaluates it through the standalone resolution order, so it **can** wait — for its own dispatched evaluation, never for the parent. If the parent has no checksum it returns `None` without raising. The handle's `.state` and `.exception` are its own, and the state the Context derives for the anonymous node is invisible (`contracts/cells.md`, *Reads*, *Anonymous and projection handles*).
- This is the one place where bound and standalone reads deliberately differ: a standalone Cell has nothing working in the background, so it pulls; a named node's Context is eager, so its reads only report.

## Barriers: `compute` and `computation`

| Call | Waits until |
|---|---|
| `ctx.compute(timeout=None)` / `await ctx.computation(timeout=None)` | **no node in the Context** is `waiting` or `computing` |
| `node.compute(timeout=None)` / `await node.computation(timeout=None)` on a **named** Cell, a Transformer, or a Pin | **that node and its upstream cone** are no longer `waiting` or `computing`. For a Pin, which has no node of its own, this is its **owning Transformer's** barrier (`contracts/pins.md`) |
| `ctx.mounts.sync(timeout=None)` / `await ctx.mounts.synchronization(timeout=None)` | the **external** cut is settled: every external change before the final cut has been sensed and propagated, the graph is quiescent, and every complete node value has been delivered to its resource or its attachment reports why not. Returns a `SyncReport`. The barrier is driver-generic (`contracts/attachments.md`); it is spelled `mounts` because the file driver is the only production one (`contracts/mounts.md`) |

- A barrier is a **predicate installed in a turn** and satisfied in the turn that makes it true; the caller is released then.
- **`compute()` on an anonymous or projection handle is not a barrier.** It evaluates the handle's Expression over the parent's current checksum (*Reads*) and never waits on the parent; with no parent checksum it returns `None` without raising. Its `timeout=` bounds only the handle's own dispatched evaluation, and expiry raises `TimeoutError`.
- **A barrier timeout raises `TimeoutError`.** Both a timeout and an async cancellation **withdraw the predicate without cancelling any graph work**: a barrier is a wait, never a control operation.
- A barrier on a path whose node has been deleted raises `StaleWorkflowHandleError`.
- A **reading** barrier — the form behind a bound `compute()` on a named node, which returns a checksum — **reports the outcome and never raises it** (ruled 2026-09-28). It returns the node's checksum when the node settles in `complete`, and `None` when it settles in `failed`, `unwired`, `miswired` or `blocked`; `.state`, `.exception` and `.block_reason` say which. **`run()` is the form that raises.** After the same wait it re-raises the node's own recorded exception on `failed`, and raises a `NodeError` naming the state and what to repair on `unwired`, `miswired` or `blocked`: the block reason, the miswired edge with its two celltypes, or the missing pin. Otherwise it materializes the result (`contracts/cells.md`, *Failures*, *How a failure is delivered*).
- **Quiescence is a property of node states only.** A `complete` node may still have a superseded run in flight; see *Speculation control* below, and `contracts/node-state-lifecycle.md` for what the states mean. **Elided anonymous nodes take no part in state derivation or in barriers**: they are never `waiting` and never hold a barrier open.
- **`compute()` stays graph-only and never waits for external state.** External settlement is a separate barrier, `ctx.mounts.sync()`, and it is stateful: it cuts, waits for quiescence, waits for deliveries, and starts another round if anything moved. `contracts/attachments.md` specifies it; there is deliberately no `settled()` predicate.

## Writes through the Context

The write families and the authority rule that separates them are in `contracts/cells.md`. What belongs here is what the Context does with them.

- **Serialization happens before ingress.** A value is serialized, and transformer code and builders are prepared, on the caller's side; the controller receives checksums.
- **A whole-checksum write is validated against the node celltype using HashType metadata, and then installed without resolving it.** The buffer need not be present. The consequences of an unresolvable checksum appear later, at a read (`contracts/hashtype.md`, `contracts/cells.md`).
- **A sub-path write is a pathed write to the root.** `ctx.a.b = v`, `ctx.a["b"] = v`, `ctx.a.b += 1`, and every write through a projection handle — all six verbs (`p.set`, `p.value =`, `p.set_buffer`, `p.buffer =`, `p.set_checksum`, `p.checksum =`) and `p += 1` on `p = ctx.a.b` — are the same transaction on `a`'s root value, never a write to the handle's own node. The parent's authority rule applies, and a sub-path write never detaches. Checksum and buffer forms are resolved at the handle's `celltype` first. A write through an `as_celltype` handle raises `AuthorityError`, and **clearing a sub-path** (`p.checksum = None`, `p.buffer = None`, `p.set_checksum(None)`) raises `ValueError` naming `ctx.a.b = None` and `del ctx.a["b"]` (`contracts/cells.md`, *Writes through a handle*).
- **That transaction is optimistic.** Lease the current root checksum in a turn, resolve and modify it off the controller, then commit conditionally against the base checksum and the node revision. A losing commit is retried; **after eight attempts in total, all lost**, the write raises `ConcurrentUpdateError`. If the root has no checksum and the node is `waiting`, the write waits on a barrier and retries; otherwise it raises `ValueUnavailableError` — except that a string/attribute path into an *unwired* cell starts from an empty mapping. The Context is what serializes this read-modify-set; a sub-path write always targets a cell node, which is never `computing` (`contracts/node-state-lifecycle.md`).
- **Assignment detaches edges covered by the write; an explicit `set` does not** — again `contracts/cells.md`, and again a root-level act only.

## Speculation control: `prune`

The Context **launches replacement work immediately and delays only the cancellation of the superseded run**. Obsolete runs may therefore still occupy backend slots after every node has reached equilibrium: **node-state quiescence does not by itself mean the cluster is idle.**

- **`ctx.prune()`** closes that gap. It **softcancels every superseded or grace-held run immediately**, leaving only the current wavefront, and returns `{"cancelled": <count>}`. It is lightweight and repeatable — not a freeze, and not a commit.
- **`ctx.a.prune()`** does the same for `ctx.a` and its **downstream cone** only. `ctx.prune()` is that same call at the graph root. This is the user's manual control over which superseded work to reclaim; the scheduler does not guess a tighter policy.
- **The Context only ever softcancels** — on supersession, `prune()`, node deletion, graph replacement and `close()` — because a running transformation may legitimately be shared with sibling nodes, with superseded runs, and with other processes. **Hard cancellation is never issued by the reactive layer.** What soft and hard mean is `contracts/cancellation.md`; `contracts/expressions.md` states the same soft-only rule for Expressions.
- The hold policy that decides *how long* a superseded run is kept before `prune()` or the scheduler reclaims it is part of the node state lifecycle; see that page.

## Execution

- **The workflow layer never invokes a raw callable.** It submits immutable, checksum-wired snapshots built through the ordinary Transformer builder path (`contracts/transformers.md`); the ordinary transformation cache executes them (`contracts/direct-delayed-and-transformation.md`, `contracts/execution-backends.md`). A cache hit is not a shortcut around the runtime: it still arrives through a later controller turn.
- A node is `computing` **from dispatch onwards, including the window in which its transformation identity is being constructed.** There is no separate "constructing" state, and `computing` is not delayed until the identity exists.
- **Expression jobs** — projections, and conversions on edges — use the ordinary asynchronous evaluator with the Context's placement policy (`expression_execution`), with member-scoped cancellation; their results re-enter through a controller turn like any other.
- **Determinism is assumed.** The Context's compare-and-reuse loop assumes that the same inputs give the same result checksum. Irreproducible transformations are out of scope for workflows. Accidental nondeterminism being masked by the content-addressed cache is a universal Seamless property, not a Context hazard (`contracts/identity-and-caching.md`, `contracts/scratch-witness-audit.md`).

## Graph serialization

- **`ctx.get_graph()` returns the durable graph, in format `0.6`**: nodes, configurations, edges and literal producers — never runtime state. Named nodes are stored under `nodes`; anonymous nodes are stored under the top-level key **`anonymous_nodes`**, the symbol table, and never duplicated in `nodes`. The entry schema and the `<ref>` form edges use to name a node or a symbol are `contracts/cells.md`, *Connecting*.
- **Only reachable entries are serialized.** `anonymous_nodes` holds every entry that an edge, or another serialized entry, names. An entry held only by a live handle is runtime state and is excluded: after a reload nothing could reach it.
- **Elision is not serialized.** An elided anonymous node stays in `anonymous_nodes`, unmarked; whether it is elided is re-derived at runtime.
- **`ctx.set_graph(graph)` replaces the graph wholesale.** It checks the wiring rule on `anonymous_nodes` entries exactly as on edges. It is ordered so that the new graph's claims are acquired **before** any live role is released. It softcancels every current and superseded run, detaches mount sessions, and resets the runtime.
- **`ctx.set_graph(graph, mounts=True, shares=True)` — the default — also attaches every mount and share spec in the new graph, so it blocks and can write files or open HTTP endpoints.** Reservations and initial reads are prepared in parallel on the caller's side, one message replaces the graph and all sessions atomically, and the call waits for every initial acknowledgement. `mounts=False` strips mount specs; `shares=False` strips share specs. **Graphs of unknown origin must be loaded with both disabled** (`contracts/mounts.md`, `contracts/shares.md`).
- **Run generations are never reused across a replacement**, and node revisions are bumped for the same reason: a late completion from the old graph can never be mistaken for a run at the same path in the new one.
- **Graph loading never executes code to reconstruct callables.**

## The Context surface: which calls wait, and which errors mean what

Only the operations this page specifies are listed; handle-level calls are in `contracts/cells.md` and `contracts/pins.md`.

| Call | Waits? | Returns |
|---|---|---|
| `ctx.a = X`, `del ctx.a`, and every root write | no — one controller turn, serialization done before ingress | `None` |
| a sub-path write | only when the node is `waiting` (it waits on a barrier and retries) | `None` |
| `ctx.a`, `ctx.foo.bar` (unknown path) | no | a fresh handle, or a namespace view |
| `ctx.a.checksum` / `.buffer` / `.value` on a named node | no | the current result, or `None` when the node is not `complete` |
| `ctx.compute()` / `await ctx.computation()` | **yes** — graph-wide barrier | `None`, or raises `TimeoutError` |
| `node.compute()` / `await node.computation()` on a named node | **yes** — that node's upstream cone | the node's checksum, or `None` when it settles in any other state; never raises for the node's state |
| `node.run()` on a named node | **yes** — as `node.compute()` | the materialized value; raises the recorded exception on `failed`, `NodeError` on `unwired`, `miswired` or `blocked`, and any materialization failure |
| `x.compute()` on an anonymous or projection handle | not a barrier — only for the handle's own dispatched evaluation | the handle's checksum, or `None` when the parent has none |
| `ctx.mounts.sync()` / `await ctx.mounts.synchronization()` | **yes** — the external cut barrier | a `SyncReport`; raises `TimeoutError` |
| `ctx.shares.namespace = name` | **yes** — the Context's share namespace | `None`, or raises `ValueError` if the name is taken |
| `ctx.mounts.errors` | no | `{node path: error}`, computed without a cut |
| `ctx.prune()`, `ctx.a.prune()` | no | `{"cancelled": <count>}` |
| `ctx.get_graph()` | no | the durable graph |
| `ctx.set_graph(graph, mounts=False, shares=False)` | no — but it softcancels every run | `None` |
| `ctx.set_graph(graph)` (i.e. `mounts=True, shares=True`) | **yes** — it blocks through every attachment's first delivery acknowledgement, **and it can write files or open HTTP endpoints** | `None` |
| `ctx.close()` | **yes** — one ordered shutdown turn, joining both threads | `None`; idempotent |

| Error | Raised when |
|---|---|
| `ValueError` | `expression_execution` is not `"auto"`, `"local"` or `"remote"`; a sub-path is cleared through a handle; a mounted cell is retyped, including by a builder of a different celltype |
| `ClosedContextError` | a bound handle is used after `close()`. A Context-level call after `close()` is refused with an unspecified exception type |
| `ControllerFailedError` | ingress is poisoned by an internal continuation failure; only `close()` still works |
| `ReentrantContextError` | a public Context operation or a bound handle is called from inside a controller turn |
| `StaleWorkflowHandleError` | a handle — or a barrier — names a node that has been deleted |
| `NodeError` | an assignment mismatches the node kind; or `run()` on a **named** node settles in `unwired`, `miswired` or `blocked` (never `compute()`) |
| `ReadOnlyEndpointError` | a producer operation targets a transformer's result, including `ctx.tf.result = …` |
| `DependencyError` | a new edge would close a cycle; or a handle — named, anonymous or projection — is assigned into a different Context |
| `ValueUnavailableError` | a sub-path write finds no root checksum and the node is not `waiting` (defined in seamless-core; `seamless.ValueUnavailableError`) |
| `ConcurrentUpdateError` | a sub-path commit loses eight attempts in total |
| `TimeoutError` | a barrier times out, or a handle's own evaluation outlasts its `timeout=`; no graph work is cancelled |
| `AuthorityError`, `PathError` | the handle-level rules of `contracts/cells.md`, including writes through an `as_celltype` handle; also the attachment topology rules (`contracts/attachments.md`) |
| `MountError` | never raised — *reported*, as an object on `ctx.a.mount.error` and as a string on `ctx.a.exception` (`contracts/attachments.md`) |
| `ConflictError` | a `MountError` subclass; also never raised, and latched on the mount when the oscillation detector trips |

## Implementation status and current limitations

The former named-barrier, node-replacement exception, checksum validation, result assignment, mount detach, shared-run close, wiring, handle-write, materialization and miswiring propagation gaps now satisfy the contract. Focused plain tests cover these in `seamless-workflow/tests/test_contract_workflow_context.py`, the Cell/Pin/node-state contracts, attachment tests and cancellation-policy tests.

Expression fusion satisfies the contract, and a cell bound from a direct Expression over a checksum is wired, and saved, as ordinary links; focused coverage is in `seamless-workflow/tests/test_contract_bound_fusion.py` and `seamless-workflow/tests/test_contract_direct_expression_binding.py`. One case remains: a cell bound from a direct Expression whose innermost input is not a checksum is not saved. It is tracked in [the carried-gap plan](../../../contract-ahead-of-code-plan.md).

**Deferred features and known limitations.** These are not contract gaps, and no test pins them:

- **Future-wiring is not implemented; the runtime is checksum-wired only.** A node leaves `waiting` for `computing` exactly when all of its inputs are concrete checksums. The design's future-wired Expressions and Transformations — a registered continuation keyed by its upstream's identity, which would let a `waiting` cone advance before the checksums exist — is deferred to the fire-and-forget milestone, together with the delayed cancellation that would let a checksum-wired submission latch onto it.
- **Fire-and-forget is deferred.** Detaching the Context process while a cluster advances the workflow headlessly needs future-wiring and is not available. `prune()` — the first half of it — is.
- **There is no dependency-declaration contract.** How a declared dependency edge is picked up, and how it transitions between the future-wired and checksum-wired regimes, is an open design question; nothing may depend on an answer.
- **Buffer arrival has no subscription primitive.** A missing *input* buffer becomes a visible `failed` node, and the retry is `clear_exception()` after the caller has made the buffer available. A missing *result* buffer never fails a node: the node stays `complete`, and the `CacheMissError` is raised to whoever reads (*Reads*). The Context deliberately does not invent a buffer-availability event, and deliberately does not treat cancellation as an authoritative result.
- **Individual graph construction reconciles the whole graph.** Building a large graph node by node is much slower than one `set_graph`.
- **Tests are run one process per file.** Process-global cache and refholder state carries between files, so combining Seamless test files in one pytest run produces spurious failures.

**Unspecified.** Do not depend on either answer:

- whether `ctx.tf = "code"` drops the transformer's pins (deferred);
- the exception class for a root edge combined with sub-path edges (deferred);
- the exception type of a Context-level call after `close()`.

## Non-goals

- **Sub-contexts.** A namespace is a path prefix inside one Context, with one controller and one equilibrium. A nested Context with its own runtime is not a feature.
- **Non-eager mode and activation leases.** Unratified; nothing may depend on them.
- **Cycles.** Out of scope, not merely rejected as an implementation limit: the cascade assumes a DAG, and a new edge that would close one is refused at declaration time (`DependencyError`).
- **A transient-failure state.** `failed` is one state, and the block-reason vocabulary has exactly three members (`blocked-by-unwired`, `blocked-by-error`, `blocked-by-miswiring`). Classifying a failure as transient and retrying it is a Transformation/backend concern, not Context logic.
- **Mandatory preemption.** Reclaiming a slot from a superseded run in favour of a current run elsewhere is, at most, an optional nicety; `prune()` is the supported control.
- **Epoch-stamping of the invalidation cone.** The cone is marked eagerly; a generation/epoch scheme was considered and rejected.
- **Storing Cells, Expressions or Transformations.** The Context holds nodes. Anything that looks like a stored Expression is a snapshot it fired and discarded.
- **Handle identity.** As for Cells and Pins: views are interchangeable, and nothing may be keyed on them; no operation depends on a particular handle object.
