# Reactive `Context` Workflow Internals - Implementation Plan

This plan implements the reactive workflow `Context`. It assumes the two substrate
issues are implemented separately:

- optional-pin / connectivity semantics in `seamless-transformer`;
- soft cancellation, awaiter sets, and `Expression.clear_exception()` / I/O cancellation
  in the functional substrate.

The implementation should live primarily in the new `seamless-workflow` repository. A
small number of integration hooks are still needed in `seamless-core` and
`seamless-transformer`, because public `Cell` and `Transformer` handles must mutate from
standalone builders into bound Context aliases.

## 1. Scope

### In scope for v1

- Bound/unbound `Cell` and `Transformer` handles.
- A reactive `Context` that owns a DAG of nodes and edges.
- Assignment sugar, `.set()`, deletion, one-level cell subcells, and transformer pin
  subpath assignment.
- Constants folded into the graph as checksums, never stored as Python literals.
- Same-top-level bound-to-bound dependencies as Context DAG edges.
- Recursive binding of unbound builder dependency closures.
- Pseudo-anonymous upstream nodes such as `cell1`, `cell2`, etc.
- Lightweight subcontext views and bound-to-bound subcontext copying.
- Push propagation of node state transitions.
- Default eager execution.
- Non-eager execution using `active` / `derived-active` refcount leases.
- Bound E/T run/await/capture semantics.
- `ctx.prune()` and `ctx.a.prune()`.
- `ctx.node.clear_exception()`.
- `ctx.translate()` as a compatibility no-op.
- Static DAG JSON serialization via `ctx.get_graph()` / `ctx.set_graph()`.

### Out of scope for v1

- Future-wired E/T and fire-and-forget detach.
- Macro/reactor execution and synthesized low-level contexts.
- Libraries and stdlib graph-rewriting.
- DeepCell, DeepFolder, FolderCell, hash-pattern/elision machinery.
- Mounting, sharing, REST/websocket/status binding, HTML/web UI.
- Debug mode, sandbox/shell attach, debugger mounts.
- Legacy Silk/schema/example surface behavior beyond basic validator metadata if the
  substrate already supports it.
- Module/package cells and compiled-module debug workflows.
- Environment management beyond carrying transformer metadata through to
  `Transformation`.
- Vault/save_zip/load_vault/fingertipping/database-specific workflow APIs.
- Undo/history/traitlet/Jupyter integration.
- Legacy high-level/low-level translation mechanics.

## 2. Package scaffold

Create the workflow package in `seamless-workflow`.

Recommended initial files:

```text
seamless-workflow/
  pyproject.toml
  README.md
  seamless_workflow/
    __init__.py
    context.py
    builder_state.py
    graph.py
    views.py
    assignment.py
    scheduler.py
    serialization.py
    errors.py
  tests/
```

Suggested `pyproject.toml`:

```toml
[build-system]
requires = ["setuptools>=69", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "seamless-workflow"
version = "0.1.0"
description = "Reactive workflow Context layer for Seamless"
readme = "README.md"
requires-python = ">=3.10"
license = "MIT"
authors = [{name = "Sjoerd de Vries"}]
dependencies = [
    "seamless-core>=0.1.4",
    "seamless-transformer>=0.6.1",
]
keywords = ["seamless", "workflow", "reactive", "checksum", "reproducible"]
classifiers = [
    "Development Status :: 3 - Alpha",
    "Intended Audience :: Science/Research",
    "Intended Audience :: Developers",
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3 :: Only",
    "Operating System :: OS Independent",
    "Topic :: Scientific/Engineering",
    "Topic :: Software Development :: Libraries",
]

[project.optional-dependencies]
dev = ["pytest"]

[project.urls]
Homepage = "https://github.com/sjdv1982/seamless"
Repository = "https://github.com/sjdv1982/seamless-workflow"
Issues = "https://github.com/sjdv1982/seamless/issues"

[tool.setuptools.packages.find]
where = ["."]
include = ["seamless_workflow*"]
exclude = ["tests*"]
```

The umbrella `seamless-suite` package should later add `seamless-workflow` as a
dependency and may re-export `Context` from a compatibility namespace.

## 3. Integration hooks outside `seamless-workflow`

Most behavior belongs in `seamless-workflow`, but honest binding requires small hooks in
the existing public builders.

### `seamless-core`: `Cell`

Refactor `Cell` so all mutable fields go through a state backend:

- standalone state: owned by the `Cell`;
- bound state: supplied by `seamless-workflow`, references a Context node plus view path.

The core package must not import `seamless_workflow`; use duck-typed backend methods or a
minimal local protocol. Existing standalone behavior and current tests must remain
unchanged.

Required operations:

- read/write `input_ref`, `path`, `celltype`, `target_celltype`, `validator`,
  `validator_language`;
- `set(value)` and `set_checksum(checksum)` on paths with authority;
- `build()` snapshots from the active state backend;
- `pins` for one-level subcells on standalone and bound cells;
- navigation returns a derived view, not a mutated parent;
- binding mutates the handle's state backend in place.

`Cell.pins` is fundamental, not just a bound-Context convenience. A cell with connected
or assigned pins does not concretify to an `Expression`; it concretifies to a simple,
deterministic join `Transformation` that takes the pin inputs and returns a dictionary
`{pin_name: pin_value}`. A cell with connected pins must be `plain`, `mixed`,
`deepcell`, `deepfolder`, or `folder`; connecting or assigning pins on other celltypes
is an error.

### `seamless-transformer`: `Transformer`

Refactor `Transformer` mutable surfaces through a state backend:

- code/language;
- args;
- `pins` as prebound inputs, analogous to `functools.partial`;
- celltypes;
- modules/globals;
- meta/environment/scratch/direct flags;
- optional pins;
- result celltype metadata.

The existing wrapper APIs (`args`, `pins`, `celltypes`, `modules`, `globals`,
`optional_pins`, etc.) should keep their public shape while writing through the backend.
Standalone `Transformer.pins` lets `Transformer.__call__` omit arguments already
provided by `Transformer.pins`; binding a transformer to a Context preserves that
behavior and moves the prebound pins into Context-owned state.

### Substrate APIs expected by workflow

Workflow code should call substrate APIs through a narrow adapter so exact names can be
adjusted after the substrate branches land:

- `sufficiently_connected(required_pins, optional_pins, wired_pins)`;
- transformation construction with optional-pin null canonicalization;
- `Transformation.softcancel()` or cache-level `softcancel_by_checksum(...)`;
- `Transformation.clear_exception()` or equivalent;
- `Expression.softcancel()` / `Expression.cancel()` for byte-moving paths;
- `Expression.clear_exception()`.

## 4. Core data model

### Context identity

A top-level `Context` owns a single graph. Subcontexts are path-prefix views into the same
top-level graph.

```text
Context
  top_id
  _graph: private ContextGraph
  _runtime: private ContextRuntime
  eager: bool = True
```

Every bound view carries `(top_id, node_path, view_path)`.

### Graph

```text
ContextGraph
  nodes: dict[NodePath, Node]
  edges: list[Edge]
  outgoing: dict[NodePath, set[int]]
  incoming: dict[NodePath, set[int]]
```

The graph is flat, not hierarchical. `nodes` is keyed by public `NodePath`, for example
`("a",)` or `("sub", "tf")`. `incoming` and `outgoing` are derived indexes from node
paths to indexes in `edges`. The graph is private durable Context state and contains no
private E/T objects.

```text
ContextRuntime
  scheduler: Scheduler
  current_runs: dict[NodePath, RunRecord]
  superseded_runs: dict[NodePath, deque[RunRecord]]
```

`ContextRuntime` is private transient state and is not serialized by `get_graph()`.
Pseudo-anonymous dependencies receive public names such as `cell1`, `cell2`, using the
first free number.

### Nodes

```text
Node
  kind: "cell" | "transformer"
  state: NodeState
  block_reason: None | "blocked-by-unwired" | "blocked-by-error"
  cell_overlay: Overlay | None
  transformer_pin_overlays: dict[str, Overlay]
  cell_config: CellConfig | None
  transformer_config: TransformerConfig | None
  current_checksum: Checksum | None
  active_count: int
  derived_active_count: int
```

The node path is not stored on the node because it is the key in `ContextGraph.nodes`.
`current_checksum` is the node output/result checksum, not an expression identity or
transformation checksum. Node-local exceptions are not stored; `.exception` convenience
APIs inspect the current or failed private `RunRecord`.

Node states:

```text
unwired | blocked | waiting | computing | complete | failed
```

`blocked-by-unwired` has display priority over `blocked-by-error` when both apply.

### Local producers and overlays

Cells support whole-value assignment plus one-level subcell assignment through
`Cell.pins`. Transformer pins support path assignment. Store local constant assignment
as an overlay of checksum producers. Store dependencies only as graph-level edges.

```text
LocalProducer =
  ConstantProducer(checksum, celltype)

Overlay
  entries: dict[Path, LocalProducer]
```

Literal values are serialized immediately, deposited in the buffer cache, and stored as
`ConstantProducer(checksum, celltype)`. Python literal values never live in the DAG.

The root path `()` is the whole cell/pin. Assigning a root producer replaces the
previous root producer and removes subordinate producers and incoming edge targets under
that root. For cells, assigning a subcell path `(name,)` replaces that one named
subcell and cell paths deeper than one component are invalid. For transformer pins,
assigning a subpath replaces that subpath and its descendants.

A set operation has authority only when no incoming edge targets the exact path being
set or any ancestor of that path in the same cell value or transformer pin. For cell
subcells this means checking only the whole cell and the exact one-level subcell path,
because deeper cell paths are invalid. For transformer pins, descendant incoming edges
do not remove authority; setting an ancestor path replaces that descendant subtree and
removes those descendant incoming edges.

### Edges

```text
Edge
  source: ViewPath
  target: ViewPath
  source_celltype: str
  target_celltype: str
```

Edges are graph declarations. Resolve `source` and `target` by the longest prefix present
in `ContextGraph.nodes`. For a source cell, the suffix addresses the cell value. For a
source transformer, the suffix addresses the transformer result. For a target cell, the
suffix addresses the cell value. For a target transformer, the first suffix component is
the pin name and the remaining suffix is the subpath within that pin. The code input is
the transformer pin named `"code"`.

Per tick, edges materialize private `Expression` objects from the current source checksum
and source suffix.

## 5. Public views

### `CellView`

`ctx.a`, `ctx.a.pins.b`, `ctx.a.pins["b"]`, and `ctx.a["b"]` return ephemeral bound
`Cell` or cell-pin views. View identity is not meaningful. `ctx.a.b` is never cell data
navigation; it is ordinary `Cell` attribute access, preserving class-defined attributes
such as `.run` and `.value`. `ctx.a["b"]` is sugar for `ctx.a.pins["b"]`; resolved-value
indexing must happen after reading `ctx.a.value`.

Required operations:

- navigation through `.pins.<name>`, `.pins[name]`, and `[name]` for one-level
  subcells;
- `.pins.update(mapping)` as one controller transaction for several one-level subcell
  assignments;
- `.set(value)`;
- `.set_checksum(checksum)`;
- `.build()` / `.expression()` snapshots when legal;
- bound-only `.value`, `.checksum`, `.buffer` as read helpers;
- `.run()` / `await .computation()` as demand helpers;
- `.prune()`;
- `.clear_exception()`;
- special methods such as `+=`, `-=`, `*=`, `/=` as read-modify-set compatibility.

For a bound cell, `.checksum` returns the current checksum or `None`, `.buffer` resolves
the current checksum to a buffer or returns `None`, and `.value` is short for
`cell.checksum.resolve(cell.celltype)` when `cell.checksum is not None`, otherwise
`None`. The returned Python value is not a live graph view: mutating it does not affect
the cell unless the caller later invokes `cell.set(value)` or uses legal graph
assignment syntax.

`.set()` on a cell value or one-level subcell is legal when the owning cell supports
that target shape and the view path has authority. Plain and mixed cells must support
subcell sets: `ctx.a.pins.b.set({"c": 3})` and `ctx.a.pins.b = {"c": 3}` both resolve
owner node `ctx.a`, validate that no incoming edge targets `ctx.a` or `ctx.a.pins.b`,
then store a local checksum producer at owner-local path `("b",)`.
`ctx.a["b"] = {"c": 3}` is equivalent item-syntax sugar.

`ctx.a.b.c.set(3)` and `ctx.a.b.c = 3` are invalid for cell data. Setting a cell
subcell replaces any previous producer or incoming edge at that subcell path, then
re-derives the owning node and pushes any downstream state changes. The same authority
rule applies to transformer pin subpath assignment. Context assignment is sugar for
`.set()` only when that is legal, except that assignment of `None` is deletion sugar.

`.set(None)` stores the canonical checksum for the value `null` according to the target
celltype. It is not deletion. Context assignment with `None` is deletion syntax.

### `TransformerView`

`ctx.tf` returns an ephemeral bound transformer view.

Required operations:

- pin assignment by attribute or item syntax;
- `ctx.tf.result` as a bound result view;
- `ctx.tf.inp` as a synthetic aggregate pin view;
- `ctx.tf.code` as a special code view;
- `ctx.tf.pins` as prebound input wrapper, analogous to standalone
  `Transformer.pins`;
- `ctx.tf.celltypes` style metadata mutation;
- `.copy()` as graph-copy helper;
- `.get_transformation()` / `.transformation()` snapshot when legal;
- `.run()` / `await .task()` as demand helpers;
- `.prune()`;
- `.clear_exception()`.

Transformer pin attribute sugar is allowed when it cannot shadow transformer API:
`tf.a` resolves to `tf.pins.a`, and `tf.a = value` resolves to `tf.pins.a = value`,
only if `a` is not a method/property/descriptor on the transformer object and `a` is an
existing or declared pin. Direct attribute syntax must not silently create a new pin
from a typo; use `tf.pins.a`, `tf.pins["a"]`, or the explicit pin declaration API for
new pins. Item syntax remains unambiguous: `tf["a"]` is equivalent to `tf.pins["a"]`
for pin access. If a pin name collides with transformer API, the API name wins:
`tf.scratch` and `tf.scratch = value` address the transformer's scratch setting, never
a pin named `"scratch"`. A colliding pin must be accessed as `tf["scratch"]` or
`tf.pins["scratch"]`.

`ctx.cell = ctx.tf.result` remains sugar for `ctx.cell = ctx.tf`.

### `SubContextView`

`ctx.sub = Context()` creates a namespace under the same top-level graph. `ctx.sub.a`
addresses path `("sub", "a")`.

`x = ctx.sub` may return a lightweight `SubContextView` with only `(top_id, path_prefix)`.

## 6. Assignment and binding semantics

### Existing key assignment

If `ctx.a` exists:

- `ctx.a = None` is deletion sugar, equivalent to `del ctx.a` for a node path or
  `del ctx.a.pins.b` / `del ctx.a["b"]` for a cell subcell;
- `ctx.a = value` is sugar for `ctx.a.set(value)`;
- `ctx.tf = func` edits the existing transformer's code and preserves existing pins;
- assignment of a same-kind unbound builder replaces the node's builder/config state while
  preserving the node id and existing bound aliases;
- assignment of a different kind is an error unless the user deletes the node first.

Deletion removes local producers and incoming edges at the deleted node/path and its
descendants. Deleting a node or subcontext subtree also softcancels current and
superseded work owned only by the removed nodes.
Deletion must collect every removed outgoing edge before discarding it. After the delete,
re-derive the connectivity and state of each removed outgoing edge's target node, then
propagate any resulting downstream invalidation.

### New key assignment

If `ctx.a` does not exist:

- constant value: create a cell node and store the serialized checksum;
- Python function: create a transformer node;
- unbound `Cell`/`Transformer`: bind it by move;
- bound `Cell`/`Transformer` in same top-level Context: create a new cell node with an
  edge from the source, unless assigning a subcontext view;
- `Context()`: create a subcontext namespace;
- bound subcontext: copy the subcontext graph.

### Recursive binding of unbound builders

Unbound builders may depend on:

- other unbound builders;
- immutable unbound `Expression` / `Transformation` objects;
- bound builders, but only by capturing their current immutable bound E/T snapshot.

Only builder-only dependency closures are Context-bindable.

When binding an unbound builder:

1. Walk its upstream dependency closure.
2. Reject the bind if the closure contains immutable E/T snapshots.
3. Reject cycles.
4. Reject builders already bound to another top-level Context.
5. Reuse builders already bound to the same top-level Context.
6. Bind unbound upstream dependencies under pseudo-anonymous names such as `cell1`,
   `cell2`, etc.
7. Rewrite builder-to-builder dependencies into normal Context DAG edges.
8. Mutate all absorbed Python handles into bound aliases.

### Dependency legality matrix

| target | source | behavior |
| --- | --- | --- |
| bound builder | bound builder in same top-level Context | DAG edge |
| bound builder | bound builder in different top-level Context | error |
| bound builder | immutable E/T | error |
| bound builder | unbound builder | bind or replace, then edges |
| unbound builder | unbound builder | allowed builder dependency |
| unbound builder | immutable unbound E/T | allowed, but no longer Context-bindable |
| unbound builder | bound builder | capture source's current bound immutable E/T |

### Bound-to-unbound capture

Connecting bound source `X` to unbound target `Y`, or calling/awaiting a bound E/T
snapshot, captures the current bound immutable work for `X`.

Allowed source states:

- `computing`;
- `complete`;
- `failed`;
- `waiting` only after future-wired E/T exists.

In v1, `waiting` raises `NotImplementedError`. `unwired` and `blocked` are errors.

If the captured current bound E/T is cancelled later, the unbound dependent is cancelled
too. This is not a reactive dependency; it is a dependency on one immutable run/snapshot.

For a complete constant cell with no E/T run, capture its checksum directly.

## 7. Subcontext copy

`ctx.sub2 = ctx.sub1`, where both are bound views in the same top-level Context:

1. Create a new namespace at `sub2`.
2. Copy all nodes under `sub1` to corresponding paths under `sub2`.
3. Copy all edges whose source and target are both inside the copied subtree.
4. Drop edges that cross the subcontext boundary.
5. Preserve checksums/config on copied independent nodes.
6. Rebind copied views to their new node ids.

Cross-top-level subcontext assignment is out of v1 unless implemented explicitly as graph
import.

## 8. State propagation

State propagation is always push-based.

On every external change:

1. Apply the mutation synchronously on the Context controller thread.
2. Re-derive the changed node's state.
3. If the node leaves `complete`, changes identity, or loses current output, eagerly walk
   the downstream cone.
4. Each downstream node re-derives its own state from its full upstream set.
5. Only after marking/derivation completes may scheduling submit new work.

This preserves glitch freedom: no node fires on a stale-complete upstream.

Use simple O(cone) marking in v1. Epoch stamping is deferred until marking latency is
observed to matter.

## 9. Execution scheduling

### Checksum-wired v1

V1 is checksum-wired only. A node can enter `computing` only when all required and
connected-optional inputs have current concrete checksums, subject to substrate optional-pin
construction rules.

For cells with connected or assigned `Cell.pins`, all connected subcell inputs must have
current concrete checksums before the cell can compute. Such cells must have celltype
`plain`, `mixed`, `deepcell`, `deepfolder`, or `folder`, and their private E/T is a
deterministic join `Transformation` that assembles `{pin_name: pin_value}`. They do not
concretify to `Expression`.

Nodes whose inputs are unresolved remain `waiting` and have no future-wired E/T in v1.

### Eager mode

Default `Context(eager=True)`.

```text
should_submit(node) =
  node is checksum-ready
```

When a node becomes checksum-ready, build the private immutable `Expression` or
`Transformation`, latch/submit it immediately, and store it in
`ContextRuntime.current_runs[node_path]`.

Cells with connected `Cell.pins` use the join `Transformation` path described above.

### Non-eager mode

`Context(eager=False)` still pushes all state transitions, but gates execution:

```text
should_submit(node) =
  node is checksum-ready
  and (node.active_count > 0 or node.derived_active_count > 0)
```

Demand creates an activation lease:

- demanded node: increment `active_count`;
- every upstream dependency needed by that demand: increment `derived_active_count`;
- hold the lease until the demanded E/T completes, fails, or the demand is cancelled;
- release decrements the same nodes and removes labels when counts reach zero.

When a node loses both `active` and `derived-active`, softcancel any current work that
exists only for the abandoned demand.

This simulates pull semantics without introducing pull dependency mechanics.

## 10. Supersession, holds, and prune

When a current checksum-wired run is superseded:

- relaunch the new current run immediately if `should_submit` permits it;
- keep the superseded in-flight run under the hold policy described below;
- cap superseded in-flight runs per node at 3;
- evicting a superseded run calls substrate `softcancel`;
- completed superseded work leaves the in-flight cap and is retained only via normal buffer
  cache/tempref policy.

Hold windows:

- upstream-confirmation hold: event-driven, max about 5 minutes;
- self-edit/revert hold: fixed short window, default about 15 seconds and configurable;
- completed downstream retention: buffer tempref, event-bounded, memory pressure may evict.

`ctx.prune()` softcancels all obsolete grace-held/superseded runs. `ctx.a.prune()` applies
only to `ctx.a` and its downstream cone.

## 11. Clear exception

`ctx.node.clear_exception()` is an external change:

1. Require the node to be `failed`, or make the call a no-op when not failed.
2. Forward to the failed private E/T's `clear_exception()`.
3. Clear the node exception.
4. Re-derive and reschedule from current inputs.

Upstream failures still make dependents `blocked`, not `failed`.

## 12. Graph serialization

Use a static DAG JSON format for graph serialization:

```json
{
  "__seamless_workflow__": "0.1",
  "nodes": [],
  "connections": [],
  "params": {}
}
```

Cell node shape:

```json
{
  "type": "cell",
  "path": ["a"],
  "celltype": "mixed",
  "checksum": {"value": "..."}
}
```

Transformer node shape:

```json
{
  "type": "transformer",
  "path": ["tf"],
  "language": "python",
  "pins": {
    "x": {"celltype": "mixed"}
  },
  "optional_pins": ["optional_x"],
  "checksum": {
    "code": "...",
    "result": "..."
  }
}
```

Connection shape:

```json
{
  "type": "connection",
  "source": ["a", "field"],
  "target": ["tf", "x"]
}
```

The plain `get_graph()` should be static DAG plus independent/current checksums. It must
not expose private E/T objects. `get_graph(runtime=True)` may include current runtime
state, status, exceptions, and transient checksums reduced to stable strings/checksums.

`set_graph()` reconstructs the static DAG and deposits/references checksum producers, but
does not require a separate translation step.

## 13. Controller and concurrency

All Context state transitions are serialized:

- public edits;
- attach/detach/bind migrations;
- marking and downstream derivation;
- compute result callbacks;
- activation lease changes.

Actual E/T `.compute()` invocations run outside this state-transition path, in a dedicated
event loop or executor. Completion callbacks re-enter the Context controller before
touching node state.

## 14. Milestones

### Milestone 0: package scaffold

- Add `seamless-workflow` packaging.
- Export placeholder `Context`, `Cell`, `Transformer` compatibility imports or wrappers.
- Add pytest test skeleton.

### Milestone 1: builder state delegation

- Add state backend support to `Cell`.
- Add state backend support to `Transformer`.
- Preserve standalone tests.
- Add tests for binding-as-move and bound alias mutation.

### Milestone 2: graph, views, assignment

- Implement `ContextGraph`, `ContextRuntime`, `Node`, `Edge`, overlays.
- Implement `Context.__getattr__`, `__setattr__`, `__getitem__`, `__setitem__`,
  deletion.
- Implement `CellView`, `CellPinsView`, `TransformerView`, `SubContextView`.
- Implement constants-as-checksums.
- Implement `.set()` authority errors.

### Milestone 3: dependency rules and recursive binding

- Implement dependency legality matrix.
- Implement recursive binding of unbound builder closures.
- Implement pseudo-anonymous names.
- Implement same-top-level validation.
- Implement bound-to-unbound immutable snapshot capture for `complete` and `computing`;
  `waiting` raises `NotImplementedError`.

### Milestone 4: cell subcells and transformer pin subpaths

- Implement one-level `Cell.pins` overlays for cells.
- Implement path overlays for transformer pins.
- Implement expression materialization from source checksum + path.
- Implement aggregate pin/input construction.
- Implement `ctx.tf.inp`, `ctx.tf.code`, and `ctx.tf.result` views.

### Milestone 5: state derivation and eager scheduling

- Implement node state machine.
- Implement eager push invalidation and downstream cone marking.
- Implement checksum-wired E/T construction and submission.
- Implement result callback handling.
- Implement failed vs blocked distinction and block reasons.

### Milestone 6: supersession and prune

- Implement current/superseded run records.
- Implement hold windows.
- Implement per-node superseded cap.
- Implement `ctx.prune()` and node-level `.prune()`.

### Milestone 7: non-eager activation leases

- Implement `Context(eager=False)`.
- Implement activation lease creation/release.
- Gate submission on `active` / `derived-active`.
- Softcancel abandoned non-eager work.

### Milestone 8: bound E/T run/await

- Implement bound `.run()` / `.compute()` / await helpers as temporary activation leases.
- Match case-3 capture restrictions.
- Ensure cancellation of captured E/T cancels unbound dependents.

### Milestone 9: subcontexts and serialization

- Implement `ctx.sub = Context()`.
- Implement same-top-level subcontext copying.
- Implement `get_graph()` / `set_graph()` static format.
- Add compatibility no-op `translate()`.

### Milestone 10: hardening

- Add cycle detection.
- Add deterministic ordering for graph serialization.
- Add readable errors for cross-top-level dependencies and non-bindable closures.
- Add runtime introspection for state, block reason, exception, current checksum.

## 15. Test strategy

Use pytest in `seamless-workflow/tests`. Legacy workflow tests are not pytest, so port the
idioms rather than running them verbatim.

Core tests:

- literal assignment stores checksums, not values;
- assigning the same value is inert;
- bound alias survives `ctx.a = value`;
- `.set()` rejects incoming edges at the root or exact cell subcell path being set;
- `ctx.a.pins.b.set({"c": 3})` works on plain and mixed cells when the path has
  authority;
- `ctx.a.pins.b = {"c": 3}` is equivalent to `ctx.a.pins.b.set({"c": 3})` for
  existing cells;
- `ctx.a["b"] = {"c": 3}` is equivalent to `ctx.a.pins["b"] = {"c": 3}`;
- `ctx.a.pins.update({"b": 1, "c": 2})` applies both assignments in one controller
  transaction;
- `del ctx.a["b"]` is equivalent to `del ctx.a.pins["b"]`;
- `ctx.a.b.c.set(3)` and `ctx.a.b.c = 3` are invalid for cell subvalues;
- cell subcell paths deeper than one component are rejected;
- replacing a cell subcell removes the previous producer or incoming edge at that
  subcell;
- bound `cell.value`, `cell.buffer`, and `cell.checksum` report current state; the
  workflow layer requires these helpers only for bound cells;
- mutating the Python object returned by bound `cell.value` does not affect the graph
  until `cell.set(value)` or graph assignment is used;
- transformer reassignment preserves old pins;
- `ctx.cell = ctx.tf` and `ctx.cell = ctx.tf.result` are equivalent;
- cell subcell assignment builds mixed value from constants and edges;
- cells with connected `Cell.pins` concretify as deterministic join transformations,
  not expressions;
- assigning or connecting `Cell.pins` rejects celltypes other than `plain`, `mixed`,
  `deepcell`, `deepfolder`, and `folder`;
- standalone `Transformer.pins` lets `Transformer.__call__` omit prebound arguments;
- binding a `Transformer` preserves `Transformer.pins` prebinding behavior;
- transformer pin subpath assignment builds mixed value from constants and edges;
- `ctx.tf["x"]` equals `ctx.tf.x` only for non-colliding existing/declared pins;
- transformer direct attribute pin sugar is used only for existing/declared pins that
  do not collide with transformer API attributes;
- a transformer pin named `scratch` remains accessible by item syntax and is not
  confused with the transformer scratch API;
- unbound builder closure binds recursively with `cell1`, `cell2`;
- closure containing immutable E/T cannot bind;
- bound-to-unbound capture works for complete/computing and errors for unwired/blocked;
- waiting capture raises `NotImplementedError` in v1;
- cross-top-level bound dependency errors;
- same-top-level subcontext copy drops external edges;
- eager mode recomputes downstream automatically;
- non-eager mode only computes active/derived-active nodes;
- activation lease release decrefs upstreams;
- failed upstream blocks downstream with `blocked-by-error`;
- unwired takes block-reason priority over error;
- `clear_exception()` re-derives;
- `prune()` softcancels obsolete runs.

Compatibility idiom coverage to test:

- `simple.py`, `simple-missing.py`, `simple-unbound.py`;
- `context.py`, `context2.py`, `subcontext.py`;
- `subcell.py`, `subsubcell.py`, `build-structured-list.py` idioms, adjusted because
  structured cells are gone and cells support only one-level `.pins` subcells;
- `transformer-bracket.py`, `reassign-transformer.py`;
- `test-copy.py`, `test-copy-tf-assign.py`;
- `delay.py` for invalidation under in-flight work;
- `special-methods.py` for read-modify-set sugar;
- `expression-exceptions.py` for conversion failures and transformer input errors;
- bytes/conversion tests where already supported by `seamless-core`.

Do not add tests for deferred features until the corresponding feature is designed.
