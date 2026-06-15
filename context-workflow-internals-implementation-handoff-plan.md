# Context Workflow Internals - Handoff Implementation Plan

This document is the implementation handoff for the reactive workflow `Context`.
It is intended to be sufficient for an implementer without requiring any other
document for guidance.

The implementation lives primarily in the `seamless-workflow` repository. Small
integration hooks are required in `seamless-core` and `seamless-transformer`
because public `Cell` and `Transformer` objects must be able to change from
standalone builders into aliases of Context-owned node state.

## Handoff-Ready Criteria

This document is handoff-ready only if all of these criteria are met:

1. It is self-contained and defines the terms needed to implement the workflow layer.
2. It clearly separates workflow-layer work from substrate responsibilities.
3. It defines public API behavior for binding, assignment, dependency declaration,
   execution, cancellation, graph serialization, and subcontexts.
4. It defines internal data structures with enough precision to start implementation.
5. It defines the node state machine and propagation rules.
6. It defines eager and non-eager execution semantics.
7. It defines legality rules for bound and unbound dependencies.
8. It identifies v1 deferrals without mixing them with external subsystem ownership.
9. It contains an implementation sequence with testable milestones.
10. It contains a test strategy tied to the behavior described here.
11. It does not rely on another document for normative guidance.

## Terms

**Builder**: A mutable public object used to define work. In this plan, builders are
`Cell` and `Transformer`.

**Checksum**: A content address for a serialized buffer or immutable computation
definition. Constants in the workflow graph are stored as checksums, not as Python
objects.

**Celltype**: The serialization/deserialization interpretation for a checksum-backed
buffer. The workflow layer records celltypes and passes them to substrate APIs, but
does not implement serialization itself.

**Substrate**: The lower-level Seamless components that provide checksum storage,
buffer caching, expression evaluation, transformation construction/execution,
optional-pin normalization, and cancellation mechanics.

**Standalone builder**: A builder that owns its own private mutable state and is not
bound to any `Context`.

**Bound builder**: A builder whose mutable state has been moved into a Context node.
The Python object remains usable, but reads and writes go through the Context node.

**Binding**: The operation that mutates a standalone builder into a bound builder.
Binding is a move of state, not a copy.

**Node**: A Context-owned graph vertex. Nodes are either cell nodes or transformer
nodes. A public path such as `("a",)` or `("sub", "tf")` names a node.

**View**: A transient public object returned by navigation, such as `ctx.a`,
`ctx.a.pins.b`, `ctx.tf.x`, or `ctx.sub`. Views are not identity-bearing. Two calls to
`ctx.a` may return different Python objects that refer to the same node.

**Path**: A structural path within a node endpoint, represented internally as a
normalized tuple of path components.

For a cell node, path `()` addresses the whole cell value and path `(name,)` addresses
one named subcell. Cell subcells are intentionally limited to one level and are reached
only through `ctx.cell.pins.<name>` or `ctx.cell.pins[name]`, never through
`ctx.cell.<name>`. This keeps `Cell` class attributes such as `.run` and `.value`
unambiguous.

For a transformer source node, a path addresses the transformer's result. For a
transformer target node, a path addresses a transformer input pin: the first component
is the pin name and remaining components are subpath components within that pin. The
transformer code input is the pin named `"code"`.

**NodePath**: The public tuple path that identifies a node inside the private graph,
for example `("a",)` or `("sub", "tf")`. The graph is flat and keyed by
`NodePath`; subcontexts are represented by common path prefixes.

**ViewPath**: A tuple path that may address either a whole node or a legal endpoint
path within a node, for example `("b",)` for a whole node or `("a", "y")` for
subcell `y` of cell `a`. Edges are stored as source and target view paths.

**Top-level Context**: The root graph owner. Subcontexts are views into the same
top-level graph, not separate reactive graph owners.

**Context graph**: The private DAG owned by a top-level Context. It is internal
implementation state, not a public `Context.graph` property. Users inspect or
round-trip graph state through `get_graph()` and `set_graph()`.

**Edge**: A Context DAG dependency from one bound source view path to one bound target
view path. Edges live in the graph connection list. They are not stored as producers
inside the target node.

**Local producer**: A checksum assigned directly to a node path. Local producers are
stored on the node. Dependency producers are not stored on the node; they are graph
edges.

**Constant producer**: A producer made from a Python value or checksum. Python
values are serialized immediately, deposited in the buffer cache, and represented in
the DAG only by checksum.

**Overlay**: The set of local checksum producers assigned at the root of a cell value,
one-level subcells of a cell value, or paths within a transformer pin. Overlay assembly
combines node-local checksum producers with incoming graph edges.

**Set authority**: The right to replace a cell value, one-level cell subcell,
transformer pin value, or transformer pin subpath. A view path has set authority when
no incoming edge targets that exact path or any ancestor of that path within the same
cell value or transformer pin. Incoming edges below the path do not remove authority;
setting the path replaces that descendant subtree. Cell paths below one subcell level
are invalid.

**Dependent path**: A cell or pin path that is produced by an incoming edge at that
path or by an incoming edge at an ancestor path. `.set(value)` on a dependent path is
an error; dependency-changing assignment or deletion must be used instead.

**E/T**: Immutable `Expression` or `Transformation` object materialized privately by
the Context from current node and edge state.

**Current run**: The E/T run that corresponds to a node's current identity and
inputs.

**Superseded run**: A previously-current in-flight run retained temporarily because
it may still be useful if the new computation resolves to the same identity.

**Active**: A refcount label on a node explicitly demanded by a non-eager execution
request.

**Derived-active**: A refcount label on upstream dependencies of an active demand.
It keeps those upstream nodes eligible to execute while the demand is outstanding.

**CellConfig**: The mutable non-runtime configuration for a cell node, including
celltype, target celltype, validator checksum/language, scratch flag if supported,
and any metadata the substrate needs to build the cell's concrete computation. A cell
with connected `Cell.pins` concretifies as a join transformation, not as an
`Expression`.

**TransformerConfig**: The mutable non-runtime configuration for a transformer node,
including code checksum, language, pin metadata, prebound pin values from
`Transformer.pins`, result celltype, optional pins, modules, globals, meta,
environment metadata, scratch flag, and local/direct flags.

**Scheduler**: The workflow component that decides whether a checksum-ready node
should submit work, tracks transient node-to-E/T run mappings, and owns hold/prune
policy.

**ExceptionInfo**: A normalized transient failure record stored on a `RunRecord`.
Bound `.exception` convenience APIs read it from the relevant current or failed run.

**Controller**: The workflow component that serializes all Context state transitions
so edits, result callbacks, activation leases, pruning, and clear-exception actions
do not interleave.

## Ownership Boundaries

### Workflow layer

The workflow layer owns:

- Context graph storage;
- binding and bound view behavior;
- assignment semantics;
- edge legality and graph validation;
- state propagation;
- eager and non-eager scheduling policy;
- current/superseded run bookkeeping;
- `prune`;
- subcontext views and subcontext copying;
- static graph serialization.

### External substrate responsibilities

The workflow layer depends on, but does not implement:

- checksum calculation and buffer cache storage;
- value serialization and celltype conversion;
- immutable `Expression` evaluation;
- immutable `Transformation` construction and execution;
- optional-pin transformation construction semantics;
- soft cancellation and hard cancellation mechanics;
- execution backends, languages, environments, compiled support, and remote execution;
- database, fingertipping, and buffer retrieval policies.

The workflow layer should call these capabilities through narrow adapters so exact
API names can be adjusted without changing graph semantics.

## V1 Deferrals

These are design features intentionally deferred from v1:

- future-wired E/T;
- fire-and-forget detach;
- dependency cycles;
- epoch-stamped invalidation optimization;
- automatic prune/preemption policy under saturation;
- transient retry taxonomy and retry backoff;
- cross-top-level Context import/copy;
- complete witness/observable API beyond node demand helpers;
- full persistence packaging beyond static DAG JSON plus checksums.

## Package Scaffold

Create or keep this package structure in `seamless-workflow`:

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
    adapters.py
    errors.py
  tests/
```

Minimum package dependencies:

- `seamless-core`;
- `seamless-transformer`.

The package should export `Context` from `seamless_workflow`.

## Integration Hooks

### Cell state backend

`seamless-core` `Cell` must read and write through a state backend.

Standalone backend:

- owns private cell state;
- preserves existing standalone `Cell` behavior;
- builds concrete cell computations from the active state.

`Cell.pins` exists for standalone and bound cells. It is not a cosmetic view: once a
cell has connected or assigned pins, the cell's concrete computation is a simple
join transformation that takes the pin inputs and produces a dictionary value. The
join transformation is internal and deterministic; it does no user computation beyond
assembling `{pin_name: pin_value}`.

A cell with connected pins must have a celltype that can represent the assembled
dictionary: `plain`, `mixed`, `deepcell`, `deepfolder`, or `folder`. Connecting or
assigning `Cell.pins` on incompatible celltypes is an error. Root value assignment and
pin assignment remain mutually governed by set authority: an incoming/root producer for
the whole cell prevents setting individual pins, and an individual connected pin
prevents overwriting that pin.

Bound backend:

- references `(top_context, node_id, path)`;
- delegates reads and writes to the Context graph;
- navigation returns a new view/backend with appended path;
- `build()` snapshots current bound state when legal;
- binding mutates the existing Python `Cell` object's backend in place.

Required mutable fields:

- input reference;
- path;
- celltype;
- target celltype;
- validator;
- validator language.

Required methods:

- `set(value)`;
- `set_checksum(checksum)`;
- `build()` snapshots from the active state backend;
- `expression()` only when the cell has no connected or assigned `Cell.pins`;
- `compute()` / `run()` demand helpers.

### Transformer state backend

`seamless-transformer` `Transformer` must read and write through a state backend.

Standalone backend:

- owns private transformer state;
- preserves existing standalone `Transformer` behavior;
- builds immutable `Transformation` snapshots.

`Transformer.pins` exists for standalone and bound transformers. It stores prebound
input values or dependencies, analogous to `functools.partial`: `Transformer.__call__`
may omit arguments that are already provided by `Transformer.pins`. Calling a
transformer merges explicit call arguments with `Transformer.pins`; for named pins, an
explicit call argument overrides the prebound value for that call only, matching
`functools.partial` keyword semantics. Binding a transformer to a Context preserves the
same semantics and moves the prebound pins into the Context-owned transformer node.

Bound backend:

- references `(top_context, node_id)`;
- delegates code, pin, celltype, module, global, meta, optional-pin, environment,
  and result metadata operations to the Context graph;
- binding mutates the existing Python `Transformer` object's backend in place.

The existing public wrapper style should remain available for:

- `args`;
- `pins` as prebound inputs;
- `celltypes`;
- `modules`;
- `globals`;
- `meta`;
- `optional_pins`;
- environment metadata;
- scratch and local/direct flags.

## Internal Data Structures

### Context

```text
Context
  top_id: unique identity for same-top-level validation
  _graph: private ContextGraph
  _runtime: private ContextRuntime
  eager: bool = True
  controller: serialized state-transition controller
```

`Context(eager=True)` is the default. `Context(eager=False)` still propagates state
eagerly but gates execution by activation labels.

### ContextGraph

```text
ContextGraph
  nodes: dict[NodePath, Node]
  edges: list[Edge]
  incoming: dict[NodePath, set[int]]
  outgoing: dict[NodePath, set[int]]
```

The graph is flat, not hierarchical. `nodes` is keyed by public `NodePath`.
`incoming` and `outgoing` are derived/backmapping indexes from node paths to indexes in
the `edges` list. Public paths are deterministic and are used for serialization and
user navigation. `ContextGraph` contains durable graph state only. It does not contain
private E/T objects.

### ContextRuntime

```text
ContextRuntime
  scheduler: Scheduler
  current_runs: dict[NodePath, RunRecord]
  superseded_runs: dict[NodePath, deque[RunRecord]]
```

`ContextRuntime` is transient private state. It is not exposed as public API and is not
serialized by `get_graph()`.

### Node

```text
Node
  kind: "cell" | "transformer"
  state: NodeState
  block_reason: BlockReason | None
  cell_config: CellConfig | None
  transformer_config: TransformerConfig | None
  cell_overlay: Overlay | None
  transformer_pin_overlays: dict[str, Overlay]
  current_checksum: Checksum | None
  active_count: int
  derived_active_count: int
```

Cell nodes use `cell_overlay`. Transformer nodes use one overlay per pin in
`transformer_pin_overlays`; the code input is stored under pin name `"code"`.
The node path is not stored on the node because it is the key in `ContextGraph.nodes`.
Node-local exceptions are not stored; `.exception` convenience APIs inspect the current
or failed private run in `ContextRuntime`.
`current_checksum` is the node's current output/result checksum, not an expression
identity checksum or transformation checksum.

### NodeState

```text
unwired
blocked
waiting
computing
complete
failed
```

Meanings:

- `unwired`: the node is not sufficiently connected.
- `blocked`: the node is sufficiently connected, but cannot progress because an
  upstream is unwired or failed.
- `waiting`: the node is sufficiently connected and is waiting for upstream work to
  complete.
- `computing`: all inputs needed for the current concrete E/T are available and the
  node's current E/T is running.
- `complete`: a current output checksum is available.
- `failed`: the node's own current E/T failed.

Upstream failure does not propagate as `failed`. It makes dependents `blocked`.

### BlockReason

```text
blocked-by-unwired
blocked-by-error
```

If both apply, report `blocked-by-unwired`.

### Overlay and Local Producer

```text
Overlay
  entries: dict[Path, LocalProducer]

LocalProducer
  ConstantProducer(checksum: Checksum, celltype: str)
```

Root path assignment replaces the root producer and removes subordinate producers and
incoming edge targets below the root. Cell subcell assignment replaces one named
subcell; cell overlays must reject paths deeper than one component. Transformer pin
assignment may still use deeper paths within a pin when the pin celltype supports that
shape.

Constants are always folded into checksums before entering the graph.
Edges are not represented inside `Overlay`; they live only in `ContextGraph.edges`.

### Overlay assembly

Overlay assembly is deterministic:

1. If the root path `()` has a producer, resolve that producer to the base checksum for
   the value.
2. If there is no root producer, start from an empty mapping implied by the first local
   cell subcell assignment or incoming edge target. For transformer pins, the substrate
   celltype rules decide whether nested mappings or lists can be assembled.
3. Resolve local subpath producers and incoming edges in parent-before-child order and
   insert their checksums into the assembled structure.
4. A local producer or edge target at path `p` shadows all local producers and edge
   targets below `p` for assembly.
5. A path has set authority only if no incoming edge targets that path or an ancestor
   path. Descendant incoming edges affect the assembled value but may be removed by a
   set at the ancestor path.
6. If any incoming edge needed for assembly is unavailable, failed, or blocked, the
   owning node derives to `waiting` or `blocked` according to the node-state rules.
7. The assembled value is serialized and checksummed by substrate APIs. The workflow
   layer stores only the resulting checksum.

This rule applies to whole cell values, one-level cell subcells, and transformer input
pins. Only transformer pins may use nested paths deeper than one component.

### Edge

```text
Edge
  source: ViewPath
  target: ViewPath
  source_celltype: str
  target_celltype: str
```

Edges are declarations. They become private `Expression` instances only when the
consumer node is derived and the source checksum is known.

Endpoint interpretation:

- resolve `source` and `target` by the longest prefix that is present in
  `ContextGraph.nodes`;
- source cell node: the suffix addresses the source cell value;
- source transformer node: the suffix addresses the source transformer result;
- target cell node: the suffix addresses the target cell value;
- target transformer node: the first suffix component is the pin name and the remaining
  suffix is the subpath within that pin.

### RunRecord

```text
RunRecord
  node_path: NodePath
  et: Expression | Transformation
  identity_checksum: Checksum | None
  result_checksum: Checksum | None
  exception: ExceptionInfo | None
  phase: "running" | "superseded" | "cancelled" | "completed"
  generation: int
  hold_deadline: float | None
  hold_kind: "upstream-confirmation" | "self-edit" | None
```

## Public API Semantics

### Navigation

`ctx.a`, `ctx["a"]`, `ctx.a.pins.b`, `ctx.a.pins["b"]`, `ctx.tf.x`, and `ctx.tf["x"]`
return ephemeral views. View identity must never be used for dependency identity.
`ctx.a.b` is never cell subvalue navigation; normal `Cell` attributes and methods keep
their class-defined meaning.

`ctx.a.pins` returns a `CellPinsView`. It is a data namespace, not transformer pin
metadata. `ctx.a.pins.b` and `ctx.a.pins["b"]` both address owner-local path `("b",)`.
Names that collide with `CellPinsView` attributes must remain accessible by item syntax.
`ctx.a["b"]` is harmless sugar for `ctx.a.pins["b"]`; this item syntax addresses the
cell pin namespace, not the resolved Python value. Resolved-value indexing must happen
after reading `ctx.a.value`.

`CellPinsView.update(mapping)` applies several one-level pin assignments in one
controller transaction. `del ctx.a.pins.b`, `del ctx.a.pins["b"]`, and `del ctx.a["b"]`
delete one cell pin. Assigning to `ctx.a.pins` itself is not pin replacement syntax.

Bound cells expose read helpers:

- `cell.checksum`: the current checksum, or `None` if the cell has no current result;
- `cell.buffer`: the current checksum resolved to a buffer, or `None`;
- `cell.value`: short for `cell.checksum.resolve(cell.celltype)` when
  `cell.checksum is not None`, otherwise `None`.

The object returned by `cell.value` is an ordinary resolved Python object. Mutating it
outside graph syntax does not affect the cell or the Context graph. To update the cell,
call `cell.set(value)` or assign through legal graph syntax.

These helpers are bound-cell conveniences. Standalone cells keep their standalone API
surface; the workflow layer must not require standalone cells to expose Context runtime
state.

### New assignment

If a public path does not exist:

- assigning a constant creates a cell node with a checksum constant producer;
- assigning a Python function creates a transformer node with code set from the
  function;
- assigning a standalone `Cell` or `Transformer` binds it by move;
- assigning a same-top-level bound cell/transformer view creates a new cell node and
  an edge from the source;
- assigning `Context()` creates a subcontext namespace;
- assigning a same-top-level bound subcontext view copies that subcontext.

### Existing assignment

If a public path exists:

- assigning `None` is deletion sugar, equivalent to `del ctx.a` for a node path or
  `del ctx.a.pins.b` / `del ctx.a["b"]` for a cell subcell;
- assigning a constant is sugar for `.set(value)` on that existing node/path;
- assigning a Python function to an existing transformer edits its code and preserves
  existing pins;
- assigning a standalone builder of the same kind replaces the node's builder state
  while preserving the node id and existing bound aliases;
- assigning a builder of a different kind is an error unless the existing node is
  deleted first;
- assigning `ctx.cell = ctx.tf.result` is equivalent to `ctx.cell = ctx.tf`.

### `.set(value)`

`.set(value)` is legal on a cell value or one-level cell subcell when the owning cell
supports that target shape and the view path has set authority. Plain and mixed cells
must support subcell set operations such as `ctx.a.pins.b.set({"c": 3})`. Assignment to
an existing subcell, such as `ctx.a.pins.b = {"c": 3}`, is sugar for the same
operation. `ctx.a["b"] = {"c": 3}` is equivalent item-syntax sugar. `ctx.a.b.c.set(3)`
and `ctx.a.b.c = 3` are invalid; `ctx.a.b` is normal `Cell` attribute access, not data
navigation.

For a cell subcell set:

1. Resolve the owning cell node by longest-prefix lookup. In
   `ctx.a.pins.b.set({"c": 3})`, the owner is `ctx.a` and the owner-local path is
   `("b",)`.
2. Validate authority: no incoming edge may target `ctx.a` or `ctx.a.pins.b`.
3. Serialize the value, deposit the buffer, and store a `ConstantProducer` at the
   owner-local path.
4. Remove any prior local producer or incoming edge at that subcell path. Deeper cell
   paths are not legal in v1, so there is no descendant cell path to preserve.
5. Re-derive the owning node once, then push any resulting state or checksum changes
   downstream.

`.set(value)` on a path that lacks authority is an error. This includes any incoming
edge targeting the root or the exact subcell path being set.

The same authority rule applies to transformer pin subpath assignment, with the pin as
the owning value. For `ctx.tf.inp.x = value`, validate incoming edges targeting
`ctx.tf.inp` or `ctx.tf.inp.x` before replacing the pin-local subtree.

`.set(None)` stores the canonical checksum for the value `null` according to the
target celltype. It is not deletion. Context assignment with `None` is the deletion
syntax.

### Deletion

`del ctx.a` removes the public node or subcontext subtree and softcancels current and
superseded work owned only by the removed nodes.

`del ctx.a.pins.b`, `del ctx.a.pins["b"]`, and `del ctx.a["b"]` remove local producers
and incoming edges at subcell `b`.

`del ctx.a.b` is invalid for cell subvalue deletion; `ctx.a.b` is ordinary `Cell`
attribute access.

For transformer pin paths, deleting a pin subpath removes local producers and incoming
edges at that pin subpath and its
descendants.

`del ctx.tf.x` removes pin `x`.

`ctx.a = None`, `ctx.a.pins.b = None`, `ctx.a["b"] = None`, and `ctx.tf.x = None` are
equivalent deletion sugar for the cases above. To store a `null` value, use
`.set(None)` or assign a pre-built cell containing that checksum.

Deletion must collect every removed outgoing edge before it is discarded. After the
delete, re-derive the connectivity and state of each removed outgoing edge's target
node, then propagate any resulting downstream invalidation. This applies to node
deletion, cell subcell deletion, transformer pin/subpath deletion, and `None`
assignment deletion sugar.

### Transformer special views

Required special views:

- `ctx.tf.result`: transformer output as a bound cell-like view;
- `ctx.tf.code`: transformer code as the pin path `("code",)`;
- `ctx.tf.inp`: synthetic aggregate view over all transformer pins;
- `ctx.tf.pins`: prebound input wrapper, analogous to standalone `Transformer.pins`.

`ctx.tf.inp.x = value` must behave like assigning subpath `x` in the transformer's
input aggregate.

`ctx.tf.pins.x = value` prebinds input pin `x`. Binding does not change the meaning of
`Transformer.pins`; it only changes where that state is stored.

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

## Dependency Semantics

### Bound-to-bound dependencies

Bound builders can depend on bound builders only when both are bound to the same
top-level Context. The dependency becomes a Context DAG edge.

Bound builders cannot depend on immutable `Expression` or `Transformation` objects.

Bound builders in different top-level Contexts cannot be connected in v1.

### Unbound dependencies

Standalone builders can depend on:

- other standalone builders;
- immutable standalone E/T objects;
- a bound source's current immutable E/T snapshot.

Only standalone builder dependency closures that contain builders only can later bind to
a Context.

If a standalone builder closure contains immutable E/T objects, that closure may be
used functionally, but binding it into a Context is an error.

### Recursive binding

Binding a standalone builder to a Context recursively binds its upstream builder
dependencies:

1. Walk the upstream dependency closure.
2. Reject immutable E/T in the closure.
3. Reject cycles.
4. Reject builders bound to another top-level Context.
5. Reuse builders already bound to the same top-level Context.
6. Bind unbound upstream builders under pseudo-anonymous public names such as
   `cell1`, `cell2`, using the first free number.
7. Rewrite builder-to-builder dependencies into normal Context DAG edges.
8. Mutate all absorbed Python builder handles into bound aliases.

### Bound source captured by standalone target

Connecting a bound source to a standalone target captures the source node's current
immutable E/T or checksum.

Allowed source states:

- `computing`;
- `complete`;
- `failed`.

`waiting` requires future-wired E/T and raises `NotImplementedError` in v1.
`unwired` and `blocked` are errors.

If the captured E/T is later cancelled, the standalone dependent is cancelled too.
This is a dependency on one immutable run, not a reactive Context edge.

If the bound source is a complete constant cell and no E/T is needed, capture the
current checksum directly.

## Subcontexts

`ctx.sub = Context()` creates a namespace. From then on, `ctx.sub.a` is valid and
addresses public path `("sub", "a")` in the same top-level graph.

`x = ctx.sub` returns a `SubContextView` that references a path prefix.

### Same-top-level subcontext copy

`ctx.sub2 = ctx.sub1` copies a same-top-level subcontext:

1. Create namespace `sub2`.
2. Copy all nodes under `sub1` to corresponding paths under `sub2`.
3. Copy edges whose source and target are both inside the copied subtree.
4. Drop edges that cross the copied subtree boundary.
5. Preserve independent checksums and builder configuration.
6. The original subcontext remains unchanged.

Cross-top-level subcontext copy is deferred from v1.

## State Propagation

All state propagation is push-based.

On every external change:

1. Run the mutation synchronously through the Context controller.
2. Re-derive the changed node.
3. If the node leaves `complete`, changes identity, or loses current output,
   synchronously walk the downstream cone.
4. Each downstream node re-derives from its full upstream set.
5. Only after this marking and derivation pass may new work be submitted.

This prevents firing a node on a stale-complete input.

Use simple downstream cone marking in v1. More advanced invalidation schemes are
deferred.

## State Derivation Rules

A cell node is sufficiently connected if its overlay can produce its current value:

- a root constant producer is sufficient;
- an incoming edge targeting the root path is sufficient if its source is reachable;
- one-level local subcell overlays plus incoming edge targets are sufficient when the
  celltype is `plain`, `mixed`, `deepcell`, `deepfolder`, or `folder`;
- any connected or assigned subcell pin on another celltype is a validation error;
- no producer means `unwired`.

A cell node with connected or assigned `Cell.pins` is not concretified as an
`Expression`. Once all connected subcell inputs have current checksums, the scheduler
builds a private deterministic join `Transformation` whose inputs are the subcell pins
and whose result is the assembled dictionary. A root-only cell with no connected pins
may use the direct checksum/expression path.

A transformer node is sufficiently connected when:

- code is available;
- every required pin is wired;
- every connected optional pin is wired;
- unconnected optional pins are absent.

Required pins come from the transformer signature when one exists, plus explicit pin
metadata. Optional pins come from transformer configuration. Reassigning transformer
code updates the inferred signature but does not delete existing explicit pins or
their producers.

Connected optional pins gate like required pins. If a connected optional upstream fails,
the transformer is `blocked`, not silently skipped.

A node reaches `computing` only when every required input and every connected optional
input needed for the current construction has a current concrete checksum or a
substrate-recognized absence value.

## Execution Scheduling

### Checksum-wired v1

V1 is checksum-wired only. A node in `waiting` does not own future-wired work.
Future-wired work is deferred.

### Eager execution

Default behavior:

```text
should_submit(node) =
  node is checksum-ready
```

When a node becomes checksum-ready:

1. Materialize private immutable E/T from current node and edge state. For cells with
   connected `Cell.pins`, this is the deterministic join `Transformation`, not an
   `Expression`.
2. Submit or latch onto the E/T.
3. Store it in `ContextRuntime.current_runs[node_path]`.
4. Move node to `computing`.

### Non-eager execution

`Context(eager=False)` still propagates state transitions immediately, but gates
execution:

```text
should_submit(node) =
  node is checksum-ready
  and (node.active_count > 0 or node.derived_active_count > 0)
```

A demand creates an activation lease:

- increment `active_count` on the demanded node;
- increment `derived_active_count` on all upstream dependencies needed by the demand;
- schedule checksum-ready nodes covered by the lease;
- hold the lease until the demanded E/T completes, fails, or is cancelled;
- release the lease by decrementing the same nodes.

When a node loses both `active` and `derived-active`, softcancel current work that
exists only for the abandoned demand.

### Bound E/T run and await

Bound `.run()`, `.compute()`, and await helpers use the same rules as connecting a
bound source to a standalone target:

- in eager mode, latch onto current work or cache when available;
- in non-eager mode, create a temporary activation lease;
- fail immediately for `unwired` or `blocked`;
- raise `NotImplementedError` for `waiting` in v1;
- release temporary activation after completion, failure, or cancellation.

## Supersession, Holds, And Prune

When a checksum-wired current run is superseded:

1. If scheduling permits, launch the new current run immediately.
2. Keep the superseded in-flight run during its hold window.
3. Cap superseded in-flight runs at three per node.
4. Softcancel a superseded run when it is evicted from the cap or its hold expires.
5. When a superseded run completes, remove it from the in-flight cap.

Hold kinds:

- upstream-confirmation hold: event-driven, maximum about five minutes;
- self-edit/revert hold: fixed short window, default about fifteen seconds and
  configurable;
- completed downstream retention: buffer-cache/tempref retention, event-bounded, and
  subject to memory pressure.

`ctx.prune()` softcancels all obsolete superseded or grace-held runs in the Context.

`ctx.a.prune()` softcancels obsolete runs in `ctx.a` and its downstream cone only.

## Clear Exception

`ctx.node.clear_exception()` is an external change:

1. If the node is not `failed`, return no-op success or a documented no-op result.
2. Forward to the failed private E/T's `clear_exception()` substrate hook.
3. Clear the failed `RunRecord.exception`.
4. Re-derive the node from current inputs.
5. Schedule if eligible.

## Graph Serialization

`get_graph()` is the public graph inspection API. It returns static graph state plus checksums for independent/current
constant producers. It must be deterministic.

Recommended shape:

```json
{
  "__seamless_workflow__": "0.1",
  "nodes": [],
  "connections": [],
  "params": {}
}
```

Cell node:

```json
{
  "type": "cell",
  "path": ["a"],
  "celltype": "mixed",
  "checksum": {"value": "..."},
  "overlay": []
}
```

Transformer node:

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

Connection:

```json
{
  "type": "connection",
  "source": ["a"],
  "target": ["tf", "x"]
}
```

`get_graph(runtime=True)` may additionally include node states, block reasons,
exceptions, and current checksums. It must not serialize private E/T objects. If run
metadata is exposed for diagnostics, it must be reduced to stable strings/checksums and
must remain optional.

`set_graph()` reconstructs static graph state, validates the DAG, and then derives the
Context from the loaded state. It does not perform a separate translation step.

`translate()` is a compatibility no-op that returns successfully.

## Controller And Concurrency

All Context state transitions must be serialized:

- public edits;
- binding migrations;
- deletion;
- marking and downstream derivation;
- result callbacks;
- activation lease changes;
- prune;
- clear exception.

Actual E/T computation runs outside the controller in a dedicated event loop or
executor. Completion callbacks must re-enter the controller before touching graph state.

## Implementation Milestones

### Milestone 0: package scaffold

- Add package metadata.
- Export placeholder `Context`.
- Add test skeleton.

### Milestone 1: builder state delegation

- Add state backend support to `Cell`.
- Add state backend support to `Transformer`.
- Preserve standalone behavior.
- Test binding-as-move and alias mutation.

### Milestone 2: graph and views

- Implement `ContextGraph`, `Node`, `Edge`, `Overlay`, `LocalProducer`.
- Implement `Context` navigation and mutation entry points.
- Implement `CellView`, `CellPinsView`, `TransformerView`, and `SubContextView`.

### Milestone 3: assignment and constants

- Implement new/existing assignment rules.
- Implement constants folded into checksums.
- Implement `.set()` authority checks.
- Implement deletion.

### Milestone 4: dependency legality and recursive binding

- Implement same-top-level edge creation.
- Implement dependency legality matrix.
- Implement recursive binding and pseudo-anonymous naming.
- Implement cycle detection.
- Implement bound source capture for standalone targets.

### Milestone 5: cell subcells and transformer pin overlays

- Implement one-level `Cell.pins` subcell overlay assembly.
- Implement path-overlay assembly for transformer pins.
- Implement materialization of edge expressions from current source checksums.
- Implement `result`, `code`, `inp`, and `pins` transformer views.

### Milestone 6: state machine and eager execution

- Implement node derivation.
- Implement push downstream marking.
- Implement checksum-wired E/T materialization.
- Implement eager submission and result callbacks.
- Implement failed/blocked distinction.

### Milestone 7: supersession and prune

- Implement current and superseded run records.
- Implement hold windows and per-node caps.
- Implement `ctx.prune()` and node-level `prune()`.

### Milestone 8: non-eager activation leases

- Implement `Context(eager=False)`.
- Implement active and derived-active refcounts.
- Implement temporary demand leases.
- Softcancel abandoned non-eager work.

### Milestone 9: graph serialization and subcontext copy

- Implement static `get_graph()` and `set_graph()`.
- Implement `get_graph(runtime=True)`.
- Implement `translate()` no-op.
- Implement same-top-level subcontext copy.

### Milestone 10: hardening

- Improve diagnostics.
- Add deterministic serialization ordering.
- Add adapter shims for exact substrate API names.
- Add stress tests for invalidation, cancellation, and activation lease release.

## Test Strategy

Use pytest in `seamless-workflow/tests`.

Required behavior tests:

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
- cell subcell assignment builds values from constants and edges;
- cells with connected `Cell.pins` concretify as deterministic join transformations,
  not expressions;
- assigning or connecting `Cell.pins` rejects celltypes other than `plain`, `mixed`,
  `deepcell`, `deepfolder`, and `folder`;
- standalone `Transformer.pins` lets `Transformer.__call__` omit prebound arguments;
- binding a `Transformer` preserves `Transformer.pins` prebinding behavior;
- transformer pin subpath assignment builds values from constants and edges;
- transformer item syntax and direct attribute syntax are equivalent only for
  non-colliding existing/declared pins;
- transformer direct attribute pin sugar is used only for existing/declared pins that
  do not collide with transformer API attributes;
- a transformer pin named `scratch` remains accessible by item syntax and is not
  confused with the transformer scratch API;
- standalone builder closure binds recursively with pseudo-anonymous nodes;
- closure containing immutable E/T cannot bind;
- bound-to-standalone capture works for `complete`, `computing`, and `failed`;
- bound-to-standalone capture errors for `unwired` and `blocked`;
- waiting capture raises `NotImplementedError` in v1;
- cross-top-level bound dependency errors;
- same-top-level subcontext copy drops external edges;
- eager mode computes downstream automatically;
- non-eager mode computes only active and derived-active nodes;
- activation lease release decrements exactly the nodes it incremented;
- failed upstream blocks downstream with `blocked-by-error`;
- unwired block reason takes priority over error block reason;
- `clear_exception()` re-derives and reschedules;
- `prune()` softcancels obsolete runs.

Recommended integration tests:

- one diamond graph to prove glitch-free invalidation;
- one long-running downstream run retained across an upstream inert edit;
- one self-edit/revert hold case;
- one non-eager demand that completes and releases all activation labels;
- one subcontext copy with an external edge that is intentionally dropped;
- one deterministic `get_graph()` round trip.

## Compliance Audit

This handoff document is complete when the following audit passes:

- Terms used by the implementation are defined.
- Workflow ownership and substrate ownership are separated.
- V1 deferrals are listed separately from substrate responsibilities.
- Public API behavior is specified.
- Internal graph structures are specified.
- State propagation and execution scheduling are specified.
- Edge legality is specified.
- Milestones are ordered and testable.
- Test strategy covers the specified behavior.
- No other document is required for normative guidance.

## Compliance Evaluation Result

Final evaluation: full compliance achieved.

- Self-contained terminology: pass.
- Workflow/substrate boundary: pass.
- Public API behavior coverage: pass.
- Internal data-structure precision: pass.
- State-machine and propagation coverage: pass.
- Eager/non-eager execution coverage: pass.
- Dependency legality coverage: pass.
- V1 deferrals separated from external ownership: pass.
- Testable milestone sequence: pass.
- Behavior-linked test strategy: pass.
- No reliance on another document for normative guidance: pass.
