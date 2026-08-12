# Context-Bound Builder Specialization And Endpoint Semantics

## Status And Purpose

This document is a normative follow-up to the reactive `Context` design and its
implementation plans. It resolves a mismatch exposed by the experimental
implementation: binding an existing `Cell` or `Transformer` specializes that Python
builder in place through a workflow backend, while looking up the same node through
the `Context` returns an unrelated `CellView` or `TransformerView` wrapper. The two
public surfaces have already diverged.

The Context implementation is alpha. This design chooses a coherent API without
preserving the behavior of the experimental view classes.

This document changes the public-handle, navigation, endpoint, immutable-snapshot, and
Transformer-input contracts. In particular, it removes the experimental general
subpath-overlay mechanism for Transformer inputs: each Transformer pin has exactly one
producer. It does not otherwise change the Context graph state machine, scheduling,
cancellation, pruning, constant-as-checksum, or serialization principles except where
new durable metadata is explicitly required below.

## Decision Summary

1. `ctx.a` for a cell node returns an ephemeral, context-bound `Cell`.
2. `ctx.tf` for a transformer node returns an ephemeral, context-bound `Transformer`
   (or the canonical direct-transformer variant when the node records direct call
   mode).
3. Binding an existing builder and reconstructing a handle from Context lookup use
   the same backend contract and expose the same behavior.
4. `CellView`, `TransformerView`, and `TransformerResultView` cease to be public node
   handle types.
5. Builder handle identity remains meaningless: `ctx.a is ctx.a` may be false. Node
   identity is `(top_context_id, node_path)`; endpoint identity additionally includes
   endpoint kind and local path.
6. Cell navigation is projection in both standalone and bound modes. It never grows
   the Context DAG.
7. Cells have no `.pins` namespace. Direct Cell attribute/item paths are projections
   on read. Assignment or `.set()` of a value may update any supported depth by atomic
   root-value read-modify-set; assignment or `.set()` of a bound source may create a
   connection only at the Cell root or one level below it.
8. Public API names win over attribute navigation. Item syntax is the escape hatch for
   a data key that collides with an API name.
9. Calling a delayed bound `Transformer` builds an immutable `Transformation`
   snapshot. It does not execute the stored Python callable directly and does not mean
   "return the current reactive result."
10. Focused namespace wrappers remain only where no canonical builder counterpart
    exists; no Cell subvalue or Transformer-input target wrapper is public.
11. A Transformer pin is one producer slot, not a structured overlay. `.pins` is the
    sole public pin namespace; the reserved `.inp` namespace and Transformer
    pin-subpath targets are removed.
12. `.pins` is also the sole *access path*: `tf.x` and `tf["x"]` pin sugar is removed in
    standalone and bound modes, and pin declaration respects the code signature
    (Appendix A).

## Why The Experimental Dual Surface Is Rejected

The current implementation has two ways to obtain a handle for one node:

- assigning `ctx.tf = tf` mutates `tf._workflow_backend`, leaving `tf` an actual
  `Transformer`;
- evaluating `ctx.tf` constructs a separate `TransformerView`.

The same split exists for `Cell`. It causes differences in callability, metadata,
pin-read behavior, navigation, source recognition, snapshot construction, and runtime
helpers. It also forces Context dependency detection to enumerate every view class.
Missing one class makes a valid endpoint look like a literal value or causes an
incorrect rebind.

Binding-as-move already requires public builders to support Context-owned state.
Separate top-level wrappers therefore do not isolate workflow integration; they add a
second implementation of it. The specialization model completes the backend design
instead.

## Terminology

**Standalone builder**: A `Cell` or `Transformer` whose mutable builder state is
private to that Python object.

**Bound builder**: A `Cell` or `Transformer` whose authoritative state is owned by a
Context node and accessed through a workflow backend.

**Root handle**: A bound builder addressing the whole logical node result, with empty
local path.

**Projection**: A structural read/select operation over a cell value. A projection is
represented by a `Cell` carrying an accumulated path. It may be built into an
immutable `Expression`, resolved, or used as a Context edge source. Projection does
not create a Context node or a local producer.

**Cell value update**: Assignment of a non-source value through a writable bound Cell
handle. At the root it replaces the Cell's root set value. At every non-empty path it
is an atomic read-modify-set of that same root set value; it never creates a local
subvalue producer or a deep graph target.

**Connection target**: A graph location that may receive a bound source. Legal Cell
connection targets are the root and one-level subvalues. Legal Transformer connection
targets are whole pins and the whole code input. There are no deeper connection
targets.

A one-level Cell connection target is one point-selection path component: a mapping
key/attribute name or an integer sequence index supported by the Expression path
substrate. A slice may be read or value-updated but is not a connection target because
it denotes multiple positions. A mapping-key connection can bootstrap an unwired Cell
as a mapping. An integer-index connection requires an existing compatible sequence and
valid index; it never infers or grows a list.

**Bound endpoint descriptor**: The internal, normalized identity exposed by any bound
object that may participate in Context wiring. It contains at least:

```text
top_id
node_path
endpoint_kind
local_path
access_mode
```

`endpoint_kind` distinguishes cell result/projection, one-level Cell subvalue target,
Transformer result, whole Transformer input pin, and Transformer code where behavior
differs.
`access_mode` records whether the endpoint permits projection, value update, or
connection targeting. A normal bound Cell is writable at its root and projections;
a Transformer-result Cell is read-only at both.

**API name**: A name defined by the public class or one of its bases, including a
method, property, descriptor, or deliberately reserved public attribute.

## Public Type Contract

### Context lookup

Context lookup constructs fresh canonical builder handles:

```python
isinstance(ctx.a, Cell)                 # True
isinstance(ctx.tf, Transformer)         # True
isinstance(ctx.tf.result, Cell)         # True
callable(ctx.a)                         # True
callable(ctx.tf)                        # True
```

The construction mechanism must be supported by the lower-level package that owns the
public class. The workflow package supplies a duck-typed backend; `seamless-core` and
`seamless-transformer` must not import `seamless_workflow`.

The Context graph stores no builder objects. A weak handle cache is permissible for
allocation optimization but must not define identity or correctness.

### Binding an existing builder

Binding remains a move:

1. Validate and migrate the standalone builder's authoritative state into the Context
   node.
2. Replace the builder's standalone backend/state selection with the same bound backend
   contract used by lookup-created handles.
3. Abandon the private state as authoritative state; it must not be read by bound
   behavior.
4. Keep the original Python object usable as an alias of the node.

An original bound alias and a fresh lookup handle must agree on every public operation
that applies to both. They need not be the same Python object.

### Canonical classes and subclasses

The supported durable transformer flavors are ordinary delayed `Transformer` and
`DirectTransformer`. A transformer node records its call mode so a fresh handle has
the same call contract as the builder that was bound. Arbitrary user subclasses are
not reconstructed by graph deserialization in v1. Binding may preserve the original
subclass object as an alias, but fresh lookup promises only the canonical public class
for the stored flavor.

No `BoundCell(Cell)` or `BoundTransformer(Transformer)` public subclass is introduced.
Boundness is state/backend specialization, not nominal-type specialization.

## Cell Contract

### Uniform projection navigation

Attribute, item, and slice reads navigate uniformly in standalone and bound modes:

```python
cell.foo
cell["foo"]
cell[0]
cell[1:4]

ctx.a.foo
ctx.a["foo"]
ctx.a[0]
ctx.a[1:4]
```

Each returns a derived `Cell` with one additional normalized projection operation. A
derived bound `Cell` carries the same root node identity and an accumulated projection
path. Chaining must retain the entire path; no method may read a stale standalone
`_path` slot after binding.

Projection depth is not limited by the one-level connection-target rule. Deep
projection is legal wherever the underlying `Expression` path and source celltype
support it.

### API-name arbitration

Normal Python attribute lookup wins. `__getattr__` performs projection only for a name
that is not statically defined or reserved on `Cell` or its bases.

Examples:

```python
ctx.a.value       # bound Cell API: resolved value at ctx.a's current projection
ctx.a.run         # Cell.run
ctx.a.foo         # projection named "foo"
ctx.a["value"]    # projection of data field "value"
ctx.a["run"]      # projection of data field "run"
```

This rule applies equally to standalone cells. In particular, a bound-only property
such as `value`, `checksum`, or `buffer` must not raise `AttributeError` and then fall
through to `__getattr__` as a same-named data projection. `Cell.__getattr__` must detect
statically defined API names and preserve the property's original error.

### Projection, value update, and connection assignment

Cell reads always produce projection handles:

```python
ctx.out = ctx.a.b.c       # legal deep edge source
expr = ctx.a.b.c.build()  # legal snapshot when the source can be captured
ctx.a.b.c.set(3)          # legal value update through the bound projection
```

Cells have no `.pins` API. The name `pins` is not reserved on `Cell`; if the value has
a field named `pins`, `ctx.a.pins` is an ordinary projection of that field.

Assignment syntax classifies the right-hand side and target depth independently:

| Cell target | Value/checksum RHS | Cell/Transformer source RHS |
|---|---|---|
| root | replace root value | connect root |
| one component | atomic root-value read-modify-set | connect that component |
| deeper than one component | atomic value read-modify-set | `PathError` |

For the source-RHS column, a one-component slice is also a `PathError`; only the
point-selection components defined above are legal one-level connection targets.

Examples:

```python
ctx.a.b = 12             # root-value read-modify-set
ctx.a.b = ctx.source     # one-level connection
ctx.a.b.c = 12           # deep value update; no deep producer/edge
ctx.a.b.c = ctx.source   # PathError: deep connection target

ctx.a["b"]["c"] = 12
ctx.a.items[0].name = "x"
```

Attribute and item assignment have the same rules after API-name arbitration. Item
reads remain projections. On a writable bound Cell, `.set(rhs)` at a projection is
equivalent to assignment at that path, including RHS classification and connection
depth:

```python
ctx.a["b"].set(12)             # equivalent to ctx.a["b"] = 12
ctx.a["b"].set(ctx.source)     # legal one-level connection
ctx.a.b.c.set(ctx.source)      # PathError: deep connection target
```

`None` is an ordinary literal value in both forms. Deletion uses `del`; assignment of
`None` is never deletion sugar.

These assignment rules apply to writable bound Cells. Standalone Cells retain their
existing builder behavior: projection reads and projected `.set()` are legal, but
unknown attribute/item assignment is not a mutation of some other standalone Cell.

### Atomic non-root value update

A non-root value assignment or `.set(value)` is imperative convenience, not persistent
path-overlay state. The controller performs it as one serialized transaction:

1. Check that no incoming edge targets the Cell root or the first path component.
2. Read a detached copy of the current resolved value.
3. Apply ordinary Python container mutation along the path.
4. Commit the changed aggregate as the Cell's root set value, preserving every
   unrelated one-level incoming edge.

For string/attribute paths, a truly unwired Cell is treated as an empty mapping and
missing intermediate mapping keys are created as `{}`. An explicitly stored `null` is
not unwired and fails with `TypeError`, as does any existing non-mapping intermediate.
Numeric and slice updates require an existing compatible container and use ordinary
Python index/slice rules; the implementation does not infer or auto-grow a missing
list. Returned `.value` objects are non-live, so mutation occurs on a detached value.

Thus this is legal and yields `{"b": {"c": 12}}`:

```python
ctx.a = Cell()
ctx.a.b.c = 12
```

An incoming connection at `ctx.a` or `ctx.a.b` makes that update raise
`AuthorityError`. A connection at an unrelated one-level component does not block the
update by authority and must remain connected afterward. Its current result still has
to be materializable because the transaction reads `ctx.a.value`; otherwise the update
raises `ValueUnavailableError`. No local producer is stored at `("b",)` or
`("b", "c")`; non-root local value producers are not part of the graph model.

Deletion follows the same authority rule. If the exact one-level path has an incoming
edge, deletion removes that edge. Otherwise deletion at any non-empty path performs an
atomic root-value read-modify-set and never creates a local subvalue producer or deep
graph target. `del ctx.a` deletes the Cell node itself.

### `Cell.set()` and standalone builder reconfiguration

`.set(value)` uses the active Cell state model:

- standalone `Cell`, root or projected: preserve existing builder semantics by
  replacing that builder object's base input while retaining its structural path;
- writable bound root `Cell`: classify the RHS exactly as Context root assignment;
- writable bound projected `Cell`: classify the RHS and apply the same value-update or
  legal connection operation as assignment at its accumulated path;
- Transformer-result Cell, root or projected: reject with `ReadOnlyEndpointError`.

Thus standalone and bound Cells retain the same method surface, while their active
state model determines what is mutated. For example, a standalone derived Cell may
retain path `a` while its `input_ref` is changed by `.set()`, explicit assignment, or
`.with_input(...)`. A writable bound projection instead addresses its owning Context
Cell and cannot change `input_ref`: its base is the Context node by definition.

`.set_checksum(checksum)` follows the same capability and path rules. At the root it
can install the checksum directly. At a bound non-root path the controller resolves
the supplied subvalue checksum, performs the same atomic root-value update, and fails
with `ValueUnavailableError` if that checksum cannot be materialized.

### Other mutable Cell fields

The active backend must define the existing Cell builder fields without consulting an
abandoned private slot:

- `.path` and `.path_python` report the complete accumulated projection path;
- assigning `.path` is permitted for a standalone builder and rejected for a bound
  builder, whose path is derived by navigation;
- `.celltype`, `.target_celltype`, `.validator`, and `.validator_language` read and
  update the active standalone or Context-owned configuration as applicable;
- a bound root `.input_ref` represents its configured root producer when that producer
  can be represented unambiguously as a checksum or reconstructed bound source;
- a bound projection's `.input_ref` is its owning root endpoint and is read-only;
- a root combined with one-level incoming edges may report no single `.input_ref`.

The implementation may use a normalized producer descriptor internally instead of
returning private graph objects. Public reads must never expose `Edge`, `Overlay`, or
other workflow implementation records.

### Read-modify-set special methods

The existing Context requirement for `+=`, `-=`, `*=`, `/=`, and corresponding
supported augmented assignment applies to writable Cell value paths. A syntactic
operation such as `ctx.a.b.c += 1` reads the current resolved value and commits through
the same one-transaction deep value-update path. It may not create a deep edge or
producer.

Python writes an augmented attribute/item result back to its owner after `__iadd__`
and similar methods return. Returning the same already-updated bound handle must
therefore be treated as an inert same-endpoint reassignment by `Context`; it must not
create a self-edge. A separately retained writable bound projection is also a complete
mutation handle, so `p = ctx.a.b.c; p += 1` performs the same single transaction.

### Snapshot and demand operations

The canonical Cell meanings remain:

- `cell.build()` / `cell.expression()` return an immutable structural snapshot;
- `cell()` is equivalent to `build()`;
- `cell.compute()` resolves and returns the result checksum;
- `cell.run()` resolves and returns the value;
- bound `await cell.computation()` is the asynchronous demand equivalent when
  provided by the Context API.

For a bound root or projection, `build()` captures the current Context-owned immutable
work or current concrete checksum under the established bound-capture state rules. A
Cell assembled from its root set value and one-level incoming edges may require a join
`Transformation` followed by a projected `Expression`; the public snapshot must
preserve those immutable dependencies rather than materializing and copying the Python
value.

For non-eager Contexts, `compute()` and `run()` acquire a temporary activation lease
for the owning node, wait for the node result, then apply the projection if any and
release the lease.

### Bound-only observations and control

The following properties operate at the current projection for a bound Cell and raise
a deliberate bound-only error for a standalone Cell:

- `.checksum`
- `.buffer`
- `.value`

The following Context controls are available on bound Cells and projections where
meaningful:

- `.prune()` applies to the owning node and its downstream cone;
- `.clear_exception()` applies to the owning node;
- runtime status/exception helpers, if exposed, read the owning node/run.

These controls are explicit backend-aware APIs. They are not obtained through an
unrestricted `__getattr__` fallback to the backend.

## Transformer Contract

### Uniform public builder surface

A bound Transformer exposes the existing transformer builder surface through its
backend, including:

- code and language;
- args and pins;
- celltypes;
- modules and globals;
- meta and environment;
- optional pins;
- scratch, local, direct-print, driver, and input-fingertip flags;
- result metadata.

Bound code must not read stale `_args`, `_celltypes`, `_modules`, `_globals`, `_meta`,
or other abandoned standalone fields. Shared transformer construction consumes a
normalized snapshot of the active backend state.

### Call versus reactive demand

Calling a delayed Transformer always builds an immutable `Transformation`:

```python
snapshot = ctx.tf(x=1)
assert isinstance(snapshot, Transformation)
```

Explicit call arguments override prebound/current pin inputs for that snapshot only.
Calling does not mutate the Context graph. Calling does not directly invoke the stored
Python function. Modules, globals, environment, celltypes, optional pins, metadata,
scratch, and dependencies participate exactly as they do for a standalone transformer
snapshot.

Calling a bound `DirectTransformer` builds the same immutable snapshot internally and
then executes it according to the existing direct-transformer contract, returning the
resolved value. This is detached snapshot execution, not a demand on the reactive
Context node: it does not mutate the graph or current reactive result, acquire a
Context activation lease, or participate in Context current-run/prune bookkeeping.

Reactive execution is explicit:

- `ctx.tf.run()` demands the current reactive node and returns its value;
- `ctx.tf.compute()` demands it and returns its result checksum;
- `await ctx.tf.task()` is the asynchronous demand form;
- `.transformation()` / `.get_transformation()` capture the current immutable
  `Transformation` when legal.

The implementation must not make `Transformer.__call__` return the reactive value for
an ordinary delayed transformer.

### Pins

`Transformer.pins` is the sole public input-pin namespace **and the sole access path**.
It remains the prebinding/configuration wrapper analogous to `functools.partial`, with
the same public shape in standalone and bound modes. See Appendix A for the removal of
the direct attribute and item sugar this section originally specified.

Each pin has exactly one configured producer:

```text
pin name -> literal/checksum producer OR one incoming source edge
```

There is no pin-subpath producer tree and no join/overlay step within a Transformer
pin. When the reactive node is ready, its inputs reduce to a dictionary from pin name
to concrete checksum. A whole-pin assignment replaces the previous whole-pin producer.

Reading a pin through `.pins` returns its configured producer/value/dependency form,
not a target endpoint wrapper merely because the Transformer is bound. For a bound
Transformer, an incoming edge is reconstructed as a bound source handle or another
stable public producer representation; raw graph `Edge` objects are never returned.
`.args` remains the documented alias of `.pins`, not a second endpoint namespace, and
may not diverge merely because the Transformer is bound.

Assignment through `.pins` accepts a literal, checksum form, or legal bound source:

```python
ctx.tf.pins.x = 10
ctx.tf.pins.y = ctx.source
del ctx.tf.pins.y
```

A Transformer exposes no attribute or item pin sugar. `ctx.tf.x`, `ctx.tf.x = source`,
`del ctx.tf.x`, and `ctx.tf["x"]` are not pin operations in standalone or bound mode:
every Transformer attribute name is configuration API, and pins live only in `.pins`.
There is therefore no API-name arbitration to perform and no colliding pin: a pin named
`scratch` is `ctx.tf.pins.scratch` while `ctx.tf.scratch` is always the execution
setting.

`Transformer` defines no `__getattr__` fallback. An unknown attribute raises
`AttributeError`, and a bound-only property such as `.result` keeps its own deliberate
error instead of decaying into a pin read. Assigning or deleting an unknown public
attribute name also raises `AttributeError` rather than creating an instance attribute.

Pin declaration is constrained by the code signature in both modes: `.pins` and
`.celltypes` may assign an already declared pin, and may declare a new one only when
the code has no fixed signature (text, bash). When the code is a Python callable, a
name outside its parameters raises `AttributeError` instead of declaring a pin whose
every later run would fail with an unexpected-keyword `TypeError`. `result` is never an
input pin name.

The reserved `.inp` namespace is removed. A Transformer that declares an ordinary pin
named `inp` reaches it as `ctx.tf.pins.inp`; `ctx.tf.inp` raises `AttributeError`. A nested
expression such as `ctx.tf.pins.payload.left = source` does not create a graph target
below `payload`; Transformer pins are whole-pin targets only.

### Code

`.code` retains normal `Transformer` builder semantics: reading returns the configured
code representation and assignment updates code while preserving pins according to
the existing Context replacement rules.

Assigning a legal bound source to `.code` wires that source to the whole code input.
`.code` itself must not change type merely because the Transformer is reached through
a Context, and no `.inp.code` namespace exists.

### Result

`ctx.tf.result` is a read-only bound `Cell` over the transformer result endpoint. It:

- is a `Cell` for typing, callability, projection, snapshot, observation, and source
  wiring;
- uses transformer result celltype metadata;
- rejects `.set()`, attribute/item assignment, connection targeting, and other
  producer mutations;
- supports deep projection as `ctx.tf.result.foo[0]`;
- makes `ctx.cell = ctx.tf` and `ctx.cell = ctx.tf.result` equivalent source wiring.

A dedicated result-cell backend is required; an ordinary bound-cell backend that
assumes `node.cell_config` is not sufficient.

### Context controls

Bound transformers explicitly expose `.run()`, `.compute()`, `.task()`, `.prune()`,
`.clear_exception()`, snapshot helpers, and result through the public class/backend
contract. Do not use a catch-all backend `__getattr__` for these names. `Transformer`
defines no `__getattr__` at all, so no attribute lookup can silently reach the backend
or a pin.

## Endpoint Protocol And Dependency Wiring

Context dependency recognition must be protocol-based, not an `isinstance` registry
over public view classes.

Every legal bound source object exposes one normalized source endpoint descriptor.
Every target-capable assignment operation resolves a normalized target descriptor;
the target need not be exposed as a first-class public object. Context validates
`top_id`, endpoint kind, local path, direction, and authority before adding an edge.
The same source/capture protocol is consumed when lower-level standalone snapshot
construction captures a bound dependency; `_capture_workflow_source` must not inspect
workflow-private attributes or enumerate helper classes.

Required legal sources include:

- root bound Cell;
- projected bound Cell at arbitrary supported depth;
- bound Transformer, meaning its result;
- `ctx.tf.result` and projections from it.

Required legal targets include:

- root cell producer through Context assignment or bound `.set()`;
- one-level Cell subvalue through direct attribute/item assignment or bound `.set()`;
- one whole Transformer input pin through `.pins`, direct pin sugar, or item syntax;
- the whole Transformer code input through `.code`.

The endpoint protocol must make cross-top-level validation uniform and must preserve
the entire source projection path on the graph edge. Target validation permits only
the Cell root, a one-level Cell subvalue, a whole Transformer pin, or the whole
Transformer code input.

## Remaining Lightweight Views

The specialization decision removes wrappers that impersonate whole cell or
transformer nodes. It retains focused objects with no canonical standalone builder
counterpart:

- `MissingView` for unresolved Context namespace paths;
- `SubContextView` for namespace prefixes;
- metadata wrappers such as transformer celltypes, modules, globals, args, and pins,
  shared or behaviorally symmetric with their standalone counterparts.

Exact class names are internal. Public behavior and endpoint protocol matter; callers
must not depend on these helper identities.

## Backend And Package Boundary

`seamless-core` owns standalone `Cell` state, projection navigation, and value-update
dispatch. It declares or documents the minimal backend protocol used by bound cells,
but it never imports `seamless_workflow`.

`seamless-transformer` owns standalone Transformer state, wrappers, snapshot assembly,
and canonical bound-handle factories. It declares or documents its backend protocol
but never imports `seamless_workflow`.

`seamless-workflow` supplies bound backend implementations and endpoint objects. It
owns graph mutation, authority, source/target descriptors, runtime demand, and capture
of Context-private immutable work.

Lower packages may call duck-typed backend methods. Backend APIs should return
normalized builder-state snapshots rather than encouraging public classes to mix
backend data with stale private fields.

## Bound Handle Lifetime

An ephemeral handle remains valid while its node exists. Deleting the owning node
invalidates outstanding bound handles and endpoint objects. Subsequent operations raise
a workflow-specific stale-handle error rather than leaking `KeyError`.

Detaching, if implemented, snapshots node state into a fresh standalone builder; it
does not silently turn every outstanding alias into an independent mutable copy.
Precise multi-alias detach behavior remains governed by the Context lifecycle design.

## Graph And Serialization Consequences

The static graph format remains node-and-edge based and never serializes Python
handles. It must additionally retain any canonical builder flavor needed to recreate
public behavior, notably delayed versus direct transformer call mode.

Source endpoint paths remain serialized on edges. Cell source-projection depth may
exceed connection-target depth, while a deep value-update path is transient and is
never serialized as an endpoint. Validation must therefore distinguish:

- arbitrary supported cell source projection paths;
- empty cell root targets;
- one-level point-selection Cell subvalue targets, excluding slices;
- whole Transformer pin targets;
- the whole Transformer code target.

The graph stores at most one node-local producer for a Cell: its root set-value
checksum. Cell value assignment at any non-empty path updates that checksum by atomic
RMW and never emits a non-root local producer. One-level incoming edges remain legal
and are joined over the root set value when the Cell is derived.

The graph stores at most one producer per Transformer pin: either a node-local
constant/checksum producer or one incoming edge targeting that pin. It does not store
Transformer pin overlay entries or descendant target paths.

No compatibility reader for the experimental Context graph format is required unless
it is useful for tests during implementation.

## Superseded Experimental Rules

The following earlier rules are superseded:

- `ctx.a` returns a separate `CellView` type;
- `ctx.tf` returns a separate `TransformerView` type;
- `ctx.a.b` can never be cell data navigation;
- Cell source paths are restricted to one level merely because connection targets are
  restricted to one level;
- Cells expose the public `.pins` namespace invented by the alpha implementation plan;
- deep Cell value assignment must be represented as a persistent deep target;
- projected bound Cell `.set(value)` is rejected rather than applying the same value
  update as assignment at that path;
- assignment of `None` acts as deletion rather than storing a literal null;
- `ctx.tf.pins.x` has different read semantics depending on whether the same node was
  reached through an original bound alias or Context lookup;
- `.inp` is required as a second Transformer-input namespace;
- Transformer pins accept descendant target paths and require per-pin overlays;
- bound delayed `Transformer.__call__` may return a raw value;
- `.code` may return an endpoint wrapper instead of the normal Transformer code
  representation;
- Context wiring discovers bound sources by enumerating concrete view classes.

One rule of this document's own first version is superseded by Appendix A:

- `ctx.tf.x` and `ctx.tf["x"]` are read/write sugar for `ctx.tf.pins.x`, arbitrated
  against Transformer API names.

## Required Behavioral Examples

The following examples are normative:

```python
# Type and alias parity
c = Cell(value_checksum)
tf = delayed(add)
ctx.c = c
ctx.tf = tf

assert isinstance(ctx.c, Cell)
assert isinstance(ctx.tf, Transformer)
assert callable(ctx.c)
assert callable(ctx.tf)

c.celltype = "plain"
assert ctx.c.celltype == "plain"

tf.celltypes.result = "int"
assert ctx.tf.celltypes.result == "int"
```

```python
# Projection and API collision
source = ctx.data.payload.items[0]
ctx.out = source

whole_value = ctx.data.value
field_named_value = ctx.data["value"]
```

```python
# Cell value updates and connection depth
ctx.record.left = {"detail": 1}
ctx.record["right"] = ctx.source
ctx.record.left.detail.set(2)
assert ctx.record.left.detail.value == 2

with pytest.raises(PathError):
    ctx.record.left.detail = ctx.source
```

```python
# Transformer snapshots versus reactive demand
snapshot = ctx.add(x=1, y=2)
assert isinstance(snapshot, Transformation)

current_value = ctx.add.run()
current_checksum = ctx.add.compute()
```

```python
# Transformer pins have one producer each, and .pins is the only way in
ctx.add.pins.x = 10                 # local checksum producer
ctx.add.pins.y = ctx.source         # one incoming edge for pin y
ctx.add.pins.scratch = ctx.flag     # pin named like an API name: no collision
ctx.add.scratch = True              # Transformer execution setting

with pytest.raises(AttributeError):
    ctx.add.x = 10                  # no attribute pin sugar
with pytest.raises(TypeError):
    ctx.add["x"] = 10               # no item pin sugar
with pytest.raises(AttributeError):
    ctx.add.pins.typo = 10          # outside the code signature
```

## Design Acceptance Criteria

This follow-up design is satisfied when:

1. Fresh Context lookup and original bound aliases use canonical builder classes and
   agree on shared public behavior.
2. No top-level node wrapper reimplements the Cell or Transformer API.
3. Cell attribute/item navigation is uniform projection and retains complete paths.
4. API-name collision behavior is uniform and bound-only properties do not
   accidentally become projections.
5. Projection reads, value-update assignment, and connection assignment have the
   distinct authority and depth rules defined above.
6. Cell source projection supports every depth the Expression substrate supports,
   independently of one-level Cell connection targets.
7. Writable bound projections support `.set()` and augmented mutation through the
   same root-value transaction as assignment; Transformer-result projections remain
   read-only.
8. A Cell stores only one node-local root set-value producer; non-root values are
   never durable local producers, while one-level incoming edges remain legal.
9. Delayed Transformer calls return immutable `Transformation` snapshots before and
   after binding; direct-transformer behavior remains direct.
10. Transformer `.pins`, `.code`, and `.result` have the meanings defined above;
   no reserved `.inp` namespace, Transformer pin-subpath targets, or attribute/item
   pin sugar exist, and pin declaration respects the code signature.
11. `ctx.tf.result` is a read-only bound Cell.
12. Context dependency wiring uses normalized endpoint descriptors rather than a
    concrete view-class registry.
13. Bound behavior never reads abandoned standalone state.
14. Lower-level packages do not import `seamless_workflow`.

---

# Appendix A — Removal Of Direct Transformer Pin Sugar

Normative. Adopted 2026-08-12, after the body of this document was implemented. Where
this appendix and the body disagree, the appendix wins; the body has been amended to
match.

## A.1 Decision

`Transformer.pins` (and its `.args` alias) is the only way to read, write, or delete a
transformer input pin. The direct attribute and item sugar specified in the original
*Pins and attribute sugar* section is removed in **both** standalone and bound modes:

```python
ctx.tf.pins.x = source     # the only spelling
ctx.tf.x = source          # AttributeError
ctx.tf.x                   # AttributeError
del ctx.tf.x               # AttributeError
ctx.tf["x"] = source       # TypeError: not subscriptable
```

Item sugar goes with attribute sugar rather than surviving alone: its stated purpose was
to be the escape hatch for names colliding with Transformer API, and with no attribute
sugar there is nothing to escape from — `pins["x"]` already covers dynamic and awkward
names.

`Transformer` consequently defines **no** `__getattr__`. `__setattr__` and `__delattr__`
keep rejecting unknown public attribute names, so a typo is an error rather than a silent
instance attribute.

This holds for bound handles too. Context lookup returns a canonical handle as soon as a
path reaches a node, so `ctx.tf.whatever` is resolved by the `Transformer` class and
raises `AttributeError`; it never continues as Context namespace navigation and never
yields a `MissingView`. Only a path whose owning node does not exist — `ctx.nonode.whatever`
— remains an unresolved namespace view.

## A.2 Why

**1. Collision arbitration was silent and could not be made safe.** "API names win" is a
rule the writer must know in advance. For `def f(local, x)`:

```python
ctx.tf.local = "PIN?"      # sets the execution setting, unvalidated
                           # cfg.local == "PIN?", pins.local is still None
```

Nothing reports that the intended pin was not written. The colliding surface is large and
mostly ordinary parameter vocabulary: `local`, `code`, `result`, `meta`, `scratch`,
`driver`, `language`, `args`, `pins`, `run`, `compute`, `value`. Removing the sugar
deletes the collision class instead of arbitrating it, and makes the rule statable in one
line: **a Transformer's attributes are its configuration; its inputs are in `.pins`.**

**2. It restores bound-only error messages.** The sugar required a `__getattr__` that
first checked for a statically defined API name (the same defensive rule this document
states for `Cell`) and then raised a bare `AttributeError(name)` — discarding the original
error. `delayed(f).result` reported `AttributeError: result` instead of *"result is only
available for bound workflow transformers"*. With no `__getattr__`, the property's own
error propagates.

**3. It restores static checking.** `Transformer` is `Generic[P, R]`. An untyped
`__getattr__` makes every misspelled attribute type-check; without it, `tf.xx` is a type
error.

**4. Cell and Transformer become sharply distinguishable rather than confusingly
similar.** Cell attributes navigate data (a projection); Transformer attributes never
navigate anything. The previous surface made `ctx.a.b` and `ctx.tf.b` look like the same
gesture while one produced a projection handle and the other a producer read.

## A.3 What it costs

Legacy Seamless documented `ctx.tf.x = ctx.c` as *the* pin syntax, so this breaks 0.x
muscle memory. That break was already partial: legacy sugar **created** pins on
assignment, which the body of this document forbids. A half-compatible echo of the legacy
API is worse than a clean one, and `.pins` is five characters.

## A.4 Required companion rule: signature-checked pin declaration

With the sugar gone, `.pins` is the only door — so the guard the sugar happened to
provide must be moved into `.pins` itself. Before this change, the sugar checked declared
pin names while `.pins` did not, and on a bound transformer:

```python
ctx.add.pins.typo = 1      # accepted; pins become {typo, x, y}
ctx.add.run()              # TypeError: add() got an unexpected keyword argument 'typo'
```

The node was permanently unrunnable and nothing had objected. Normative rule, in both
modes and for both `.pins` and `.celltypes`:

- an already declared pin name is always assignable;
- a new pin name may be declared only when the code has no fixed signature (text, bash);
- when the code is a Python callable, a name outside its parameters raises
  `AttributeError`;
- `result` is never an input pin name.

This restores the standalone/bound parity the body requires of `.pins`, in the direction
that fails loudly.

## A.5 Residual parity notes

Two `.pins` divergences remain, both predating this change and neither resolved here:

- **Delete means different things.** Standalone `del tf.pins.x` removes the *declaration*
  and is refused outright when the signature is fixed; bound `del ctx.tf.pins.x` clears
  the *producer*, leaving the pin declared and the node `unwired`. The bound meaning is
  the one this document specifies; the standalone meaning predates it.
- **Reading an undeclared name.** Standalone returns `None`; bound raises
  `AttributeError`. The bound behavior is the better one.

## A.6 Implementation anchors

- `seamless_transformer/transformer_class.py`: `TransformerCore.__getattr__`,
  `__getitem__`, `__setitem__`, `__delitem__`, and `_declared_pin_names()` are deleted;
  `__setattr__`/`__delattr__` keep only the API-name/private-name branch.
- `seamless_workflow/graph.py`: `TransformerConfig.signature_parameters()` and
  `TransformerConfig.check_pin_name()` hold the A.4 rule.
- `seamless_workflow/context.py`: `_set_transformer_pin()` calls `check_pin_name()`.
- `seamless_workflow/builder_state.py`: `WorkflowCelltypes.__setitem__` calls
  `check_pin_name(allow_result=True)`; the now-unused `pin_names` backend property is
  deleted.
- Incidental fix in the same surface: `CompiledMixin.__init_compiled__` assigned the
  public attribute `self.compilation`, which the strict `__setattr__` introduced by this
  document already rejected — `CompiledTransformer(...)` could not be constructed at all.
  `compilation` is now a property backed by `_compilation`.
