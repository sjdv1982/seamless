# Context-Bound Builder Specialization: Handoff-Ready Implementation Plan

## Purpose

Implement one canonical public handle model for the experimental reactive `Context`:
Context cell nodes are exposed as bound `Cell` objects and transformer nodes as bound
`Transformer` objects. Remove the parallel top-level `CellView`/`TransformerView`
surface, make cell navigation uniformly mean projection, make normal bound projections
writable through assignment and `.set()`, restore immutable snapshot semantics for
bound builders, and use a normalized endpoint protocol for Context wiring. Remove the
alpha-only public `Cell.pins` namespace: direct Cell paths accept value updates at
arbitrary supported depth but connections only at root/one level. Simplify Transformer
inputs to one producer per whole pin, use `.pins` as the only Transformer pin namespace, and
remove the reserved `.inp` namespace, Transformer pin-subpath targets, and per-pin
overlays.

This plan is self-contained for the follow-up. It assumes the existing Context graph,
state machine, eager/non-eager scheduler, pruning, and static serialization code remain
the starting implementation. Those components may be corrected where this follow-up
touches them, but redesigning their unrelated behavior is out of scope.

The current Context implementation is alpha. Do not preserve compatibility with its
wrapper types, wrapper return values, or serialized graph omissions.

## Handoff-Ready Criteria

This plan is ready for handoff only if:

1. It defines every new public and internal term used by the follow-up.
2. It states the non-negotiable API contracts and the experimental behaviors being
   removed.
3. It identifies affected repositories, files, classes, and current failure anchors.
4. It separates `seamless-core`, `seamless-transformer`, and `seamless-workflow`
   ownership without introducing reverse imports.
5. It resolves navigation, collision, value update, connection depth, call, result,
   pin, and endpoint behavior rather than leaving those decisions to the implementer.
6. It orders work so lower-level builder contracts exist before Context consumes them.
7. Every phase has concrete implementation work, tests, and an acceptance gate.
8. It includes removal/migration work for the experimental dual surface.
9. It covers error behavior, stale handles, cross-Context wiring, direct versus delayed
   transformers, graph round-tripping, and non-eager demand.
10. It ends with an executable test strategy and compliance audit.

## Terms

**Canonical builder handle**: A public `Cell`, `Transformer`, or
`DirectTransformer`, regardless of whether its state is standalone or Context-owned.

**Standalone backend/state**: Mutable state private to one builder object.

**Bound backend**: A duck-typed backend supplied by `seamless-workflow` that maps a
canonical builder handle onto Context-owned state.

**Root handle**: A bound Cell or Transformer addressing one whole Context node.

**Projection Cell**: A derived `Cell` that structurally selects a path from a root
cell or transformer result. A normal bound-Cell projection is a writable mutation
handle as well as a read/build/source handle. A Transformer-result projection is
read-only. A standalone projection retains existing standalone builder semantics.

**Cell value update**: Assignment or `.set()` of a non-source value through a writable
bound Cell. A root update replaces the root set value. Every non-root update is a
serialized read-modify-set transaction that replaces that same root set value and
never becomes a local subvalue producer or deep graph target.

**Connection target**: A graph location that may receive a workflow source. These are
the Cell root, a one-level Cell subvalue, a whole Transformer pin, and the whole code
input. No deeper target is legal.

A one-level Cell target component is a point selector supported by the canonical
Expression path format: a mapping key/attribute name or integer sequence index. Slice
components are legal for reads and value updates but never for connection targets. A
mapping-key target may bootstrap an unwired mapping; an integer target requires an
existing compatible sequence and valid index and never infers or grows a list.

**Transformer pin producer**: The single producer configured for one whole input pin:
either a node-local literal/checksum producer or one incoming graph edge. Once ready,
it contributes exactly one concrete checksum to Transformation construction. It is
never a collection of descendant producers.

**Endpoint descriptor**: An immutable normalized internal record identifying a bound
source or target:

```text
BoundEndpoint
  top_id: str
  node_path: tuple[str, ...]
  endpoint_kind:
    "cell-result"
    | "transformer-result"
    | "cell-subvalue"
    | "transformer-input"
    | "transformer-code"
  local_path: tuple[path-component, ...]
  can_source: bool
  can_target: bool
  can_set: bool
```

Use the existing canonical Expression path-component representation for projection
paths. Do not reduce arbitrary item/slice operations to `tuple[str, ...]` if the
Expression substrate supports richer path operations.

For targets, `local_path` is deliberately restricted: empty for a Cell root, one
point-selection component for a Cell subvalue, one pin-name component for a whole
Transformer pin, and empty for `endpoint_kind == "transformer-code"`. The endpoint
kind distinguishes the two empty-path cases. Deep Cell value-update paths are transient
operation inputs, not endpoint descriptors or serialized edge targets. Transformer
target descriptors never contain a pin descendant path.

**API name**: A statically defined or reserved public member on `Cell` or
`Transformer`. API names win over attribute projection/pin sugar.

**Builder-state snapshot**: A normalized copy of the active builder configuration used
to construct one immutable `Expression` or `Transformation`. A snapshot never reads a
bound object's abandoned private fields.

**Call mode**: Durable transformer flavor: `"delayed"` or `"direct"`.

## Repositories And Current Anchors

### `seamless-core`

Primary files:

- `seamless/cell_class.py`
- `seamless/__init__.py`
- a new local helper/protocol module if useful, such as
  `seamless/cell_backend.py` or `seamless/cell_errors.py`
- `tests/test_cell_expression_builder.py`
- new focused Cell API tests

Current anchors to replace or correct:

- `Cell` dispatches many properties through `_workflow_backend`, but several methods
  still read `_path` or other private slots directly.
- `Cell.path_python` reads the standalone slot even when bound.
- `Cell.item()` and `Cell.slice()` derive from the standalone path slot.
- `Cell.__getattr__` always navigates after a property raises `AttributeError`, so
  standalone `.value`, `.checksum`, and `.buffer` accidentally become same-named data
  projections.
- `Cell.pins` imports `seamless_workflow.builder_state.StandaloneCellPins`, violating
  the dependency direction.
- `_capture_workflow_source` reaches into workflow implementation attributes instead
  of consuming a narrow capture/endpoint protocol.

### `seamless-transformer`

Primary files:

- `seamless_transformer/transformer_class.py`
- `seamless_transformer/__init__.py` or the package's public export module
- a new internal snapshot/protocol module if useful
- `tests/test_transformer.py`
- new bound-backend contract tests that use a fake backend and do not import workflow

Current anchors to replace or correct:

- public properties partially delegate through `_workflow_backend`, but construction
  still reads `_args`, `_modules`, `_globals`, `_celltypes`, `_environment`, `_meta`,
  and related private state directly.
- `allow_input_fingertip`, `driver`, and similar helpers have direct `_meta` paths that
  bypass bound state.
- `TransformerCore.__call__` delegates wholesale to backend `.call()` instead of using
  one shared immutable-Transformation assembly path.
- `DirectTransformer.__call__` requires the superclass call to return a
  `Transformation`; the current workflow backend instead returns a raw value, causing
  bound direct calls to fail.
- Context-only result and demand helpers are absent from canonical builder handles.

### `seamless-workflow`

Primary files:

- `seamless_workflow/context.py`
- `seamless_workflow/builder_state.py`
- `seamless_workflow/views.py`
- `seamless_workflow/graph.py`
- `seamless_workflow/errors.py`
- `seamless_workflow/__init__.py`
- all files under `tests/`

Current anchors to replace or correct:

- `Context._view()` returns `CellView`/`TransformerView` instead of canonical builders.
- binding mutates original builders to use bound backends, creating a second public
  surface over the same node.
- `_is_bound_source()` and `_source_path()` enumerate concrete view classes and omit
  valid endpoints.
- assigning an already-bound Transformer to a new Context key is treated as binding a
  builder again instead of wiring from its result.
- `BoundTransformerBackend.call()` executes the Python callable or reactive node and
  returns a value instead of constructing a `Transformation`.
- `WorkflowTransformerPins` and `TransformerPinsView` have incompatible read
  semantics.
- `TransformerPinView` recursively creates arbitrary descendant target paths, while
  `Context._assembled_pin_checksum()` implements a per-pin join/overlay subsystem that
  is not required by the simplified whole-pin producer model.
- `Node.cell_overlay` and `Context._store_cell_producer()` retain non-root local Cell
  producers introduced for the alpha `Cell.pins` API; the follow-up permits only one
  node-local root set-value producer.
- graph `Path`/`ViewPath` are currently typed as string tuples and must adopt the
  canonical Expression component encoding before integer-index endpoints can round-trip.
- the graph does not record transformer delayed/direct call mode.
- deletion can leave outstanding handles failing with raw `KeyError`.

## Non-Negotiable Contracts

### Public types and identity

- `ctx.cell` is a `Cell`.
- `ctx.tf` is a `Transformer`; a recorded direct node is exposed as
  `DirectTransformer`.
- `ctx.tf.result` is a read-only `Cell`.
- Lookups may return fresh objects. Python object identity is never dependency
  identity.
- Binding an existing builder mutates it into a usable alias. A fresh lookup and the
  original alias agree on shared public behavior.
- The graph never stores public builder objects.

### Cell projection

- Attribute, item, and slice reads return derived `Cell` projections in standalone
  and bound modes.
- Class/API names win. Colliding data fields use item syntax.
- Projection retains the complete path and may be arbitrarily deep where Expression
  supports it.
- Projection never creates a Context node or producer.
- A projected Cell may be built/resolved or used as an edge source.
- `.set()` and `.set_checksum()` on a writable bound-Cell projection apply the same
  operation as assignment at that accumulated path.
- A standalone projected builder retains existing semantics: `.set()`, `.input_ref`,
  and `.with_input()` retarget that derived builder without mutating its source Cell.
- A Transformer-result projection raises `ReadOnlyEndpointError` for every mutation.

### Cell assignment

- The path-assignment rules in this section apply to writable bound Cells. Standalone
  Cells retain existing builder behavior and do not gain source-Cell mutation through
  unknown attribute/item assignment.
- Cells do not expose `.pins`; `cell.pins` is an ordinary data projection when such a
  field exists.
- Attribute and item reads return projections. Attribute/item assignment and bound
  `.set()` are classified by RHS and complete path in the same dispatch operation.
- A value/checksum RHS is legal at the root or any non-root path supported by the
  current containers. Every non-root update is atomic read-modify-set of the root set
  value and stores no local subvalue producer or deep edge.
- A Cell/Transformer source RHS may connect only at the Cell root or one level below
  it. A deeper source assignment raises `PathError` before mutation.
- `ctx.a["x"].set(rhs)` is equivalent to `ctx.a["x"] = rhs`, including source
  classification and connection-depth validation.
- `None` is an ordinary literal RHS for assignment and `.set()` at every writable
  value path; deletion is expressed only with `del`. This supersedes alpha
  null-as-deletion sugar and makes assignment/`.set()` equivalence exact.
- An incoming edge at the root or first path component blocks a non-root value update;
  unrelated one-level connections retain authority and remain intact, but their current
  results must be materializable for the aggregate RMW.
- A truly unwired Cell may bootstrap a missing string-key path from `{}`. Explicit
  null and incompatible intermediate containers raise `TypeError`. Numeric/slice
  updates require an existing compatible container and do not auto-grow missing lists.
- If an exact one-level incoming edge exists, one-level deletion removes it. Otherwise
  every non-root deletion is an atomic root-value read-modify-set.

### Cell snapshots and demand

- `build()` / `expression()` / `__call__()` construct an immutable snapshot.
- `compute()` returns a checksum; `run()` returns the resolved value.
- Bound demand uses temporary activation leases in non-eager Contexts.
- Bound projection applies its structural path after the owner node is current.
- Cells assembled from a root set value and one-level incoming edges preserve
  immutable join dependencies and do not copy a materialized Python aggregate merely
  to build a projection.

### Transformer surface and calls

- The canonical Transformer metadata/configuration surface is available before and
  after binding.
- `.args` is an alias of the `.pins` prebinding wrapper, not a second endpoint
  namespace; reads and writes are behaviorally identical through original aliases and
  Context lookup.
- Every Transformer pin has exactly one producer: one local literal/checksum producer
  or one incoming edge targeting the whole pin.
- `.pins` is the sole Transformer pin namespace. The reserved `.inp` namespace and
  Transformer pin-subpath targets do not exist; a declared pin named `inp` remains an
  ordinary pin.
- Declared non-colliding direct pin attributes are `.pins` sugar. API names win.
- Transformer item syntax is `.pins` sugar, including for colliding names.
- `.code` retains normal Transformer code semantics. Assigning a bound source to
  `.code` wires the whole code input.
- Calling a delayed bound Transformer returns a `Transformation` snapshot and never
  directly executes its Python callable.
- Explicit call arguments override prebound/current inputs for that snapshot only and
  do not mutate the graph.
- Calling a bound DirectTransformer executes a detached snapshot and returns its
  value; it does not demand or mutate the reactive Context node or participate in
  Context activation/current-run bookkeeping.
- `.run()`, `.compute()`, and `.task()` demand the reactive node; they are distinct
  from `__call__`.

### Result and endpoints

- `ctx.tf.result` uses a dedicated read-only result-cell backend.
- Wiring from a bound Transformer is equivalent to wiring from `.result`.
- Context wiring obtains endpoint descriptors through a protocol, not a concrete
  view-class registry.
- Source projection paths are preserved in full. Target paths are restricted to the
  Cell root, a one-level Cell subvalue, a whole Transformer pin, or the whole code
  input. Deep Cell value-update paths are not serialized targets.
- Cross-top-level descriptors are rejected before graph mutation.
- Assignment of a same-top-level bound builder at a new key is dependency wiring, not
  rebinding of the Python object.

### Package direction and state authority

- `seamless-core` and `seamless-transformer` never import `seamless_workflow`.
- Bound code never reads abandoned standalone state.
- Lower packages own standalone helpers and canonical handle factories.
- Workflow owns Context mutation, endpoint descriptors, authority, capture, and
  runtime demand.

## Explicitly Removed Experimental Behavior

- Public top-level `CellView`, `TransformerView`, and `TransformerResultView` node
  handles.
- Non-callable `ctx.cell` and `ctx.tf` wrappers.
- Public `Cell.pins`, `CellPinsView`, and `CellPinView` APIs introduced by the alpha
  implementation plan, not by the ancestor designs or legacy Seamless.
- Different `.pins` read results for an original bound Transformer and `ctx.tf`.
- `.inp` as a second, bound-only Transformer input namespace.
- General Transformer pin-subpath targets, descendant overlays, and aggregate pin
  assembly.
- Bound delayed calls returning raw Python values.
- `.code` changing from normal code representation to an endpoint view on lookup.
- Cell dot-navigation prohibition.
- Rejection of `.set()` merely because a normal bound Cell has a non-empty projection
  path.
- Assignment of `None` as deletion sugar; `None` is a value and `del` is deletion.
- Source detection through a hard-coded list of view types.
- Compatibility with Context graph JSON that lacks newly required call-mode metadata.

## Error Contract

Add or standardize these errors:

- `BoundStateError`: owned/exported by `seamless-core`; raised for standalone-only Cell
  state mutation such as assigning `.path` or `.input_ref` on a bound projection.
- `ReadOnlyEndpointError`: owned/exported by `seamless-workflow`; raised by `.set()`,
  `.set_checksum()`, attribute/item assignment or deletion, and augmented mutation on
  a Transformer-result Cell or projection.
- `StaleWorkflowHandleError`: owned by `seamless-workflow`; raised when a bound handle
  or endpoint outlives its deleted node.
- Existing `AuthorityError`: retained when the root set value is controlled by a root
  incoming edge, or when a root/first-component incoming edge is an ancestor of a
  requested non-root value update.
- Existing `DependencyError`: retained for cross-top-level, cyclic, or illegal
  endpoint wiring.
- Existing `PathError`: retained for a source connection below one Cell component, a
  one-level Cell slice connection target, a Transformer target below a whole pin, or
  another unsupported path component.
- `ValueUnavailableError`: owned/exported by `seamless-workflow`; raised for a non-root
  value update whose existing Cell or supplied subvalue checksum is waiting, blocked,
  failed, missing from available buffers, or otherwise cannot be materialized. A truly
  producer-free unwired Cell is the documented empty-mapping bootstrap case, not this
  error.
- `TypeError` identifies the first incompatible container in a non-root value update;
  explicit null is incompatible rather than an unwired bootstrap signal. It also
  rejects an integer-index connection target without an existing compatible sequence;
  ordinary `IndexError` is retained for an out-of-range integer.

Error messages must identify the public endpoint and operation. Raw `KeyError`,
`TypeError` from checksum serialization of a missed view, and `AttributeError` caused
by stale private slots are not acceptable public outcomes.

## Implementation Sequence

### Phase 0: Lock The Follow-Up Contract In Tests

Goal: encode the new public contract before deleting either current surface.

Implementation:

- Add focused tests in each owning repository rather than one workflow-only test file.
- Mark tests that expose current failures as expected-to-fail only if required to keep
  intermediate commits green; remove every marker by the phase that implements it.
- Add a shared workflow test helper that creates:
  - one root constant Cell;
  - one nested dictionary Cell;
  - one delayed Python Transformer;
  - one DirectTransformer;
  - one Cell assembled from a root set value and independent one-level incoming edges;
  - one Transformer with several whole pins and a pin named `scratch`.
- Add an API parity helper that runs the same getter/setter/call operation through an
  original bound alias and a fresh Context lookup.

Tests:

- `isinstance` and `callable` assertions for all canonical bound handles.
- alias-versus-lookup parity for Cell configuration and Transformer metadata.
- standalone `cell.value`, `.checksum`, and `.buffer` raise their intended bound-only
  error; `cell["value"]` remains a projection.
- delayed bound call returns `Transformation`; direct bound call returns a value.
- writable projected `.set()` parity with assignment, read-only result rejection,
  absence of public `Cell.pins`, and direct one-level Cell value/source assignment.
- deep projected Cell used as an edge source.
- deep Cell value assignment performs RMW and stores no deep target; the same path with
  a workflow-source RHS raises `PathError`.
- whole Transformer pin wiring works through `.pins`, direct sugar, and item sugar;
  no reserved `.inp` namespace exists, a declared `inp` pin remains usable, and nested
  Transformer target paths are rejected.

Acceptance:

- Every non-negotiable contract has at least one named test location.
- Expected failures correspond to enumerated implementation phases; none are vague
  catch-all failures.

### Phase 1: Make `Cell` Backend-Complete In `seamless-core`

Goal: canonical `Cell` behavior can be supplied entirely by standalone or bound state
without importing workflow.

Implementation:

- Remove the workflow-owned `StandaloneCellPins` import and the public `Cell.pins`
  property. Do not replace it with another public Cell namespace.
- Define the minimal Cell backend protocol locally. Required backend operations:
  - read configuration and complete projection path;
  - derive a backend with an appended normalized path;
  - return a normalized endpoint/capture token where available;
  - build an immutable snapshot;
  - demand checksum/value synchronously and asynchronously;
  - expose bound observations and Context controls;
  - perform root and projected `.set()`/`.set_checksum()` when backend capability
    permits them;
  - perform value/source assignment and deletion at a normalized path;
  - hand a potential workflow-source RHS to the bound backend without importing or
    interpreting workflow classes in `seamless-core`.
- Refactor `_capture_workflow_source` to consume the normalized source/capture token
  from that protocol. It must not inspect workflow-private fields or enumerate public
  workflow helper classes.
- Add an internal constructor such as `Cell._from_backend(backend)` that initializes
  every slot safely without making standalone state authoritative.
- Make `path`, `path_python`, navigation, representation, build, compute, and run use
  the active state/backend consistently.
- Implement API-name arbitration using static class lookup. If a defined property
  raises its deliberate bound-only `AttributeError`, `__getattr__` must re-raise rather
  than create a projection of the same name.
- Keep attribute/item/slice navigation uniform and preserve the complete path.
- Preserve existing standalone projection retargeting through `.set()`, `input_ref`,
  and `.with_input()`. For a bound backend, route `.set()` and `.set_checksum()` using
  the complete path and backend write capability.
- Add explicit bound-only methods/properties needed by Context (`prune`,
  `clear_exception`, async computation) rather than a catch-all backend fallback.
- Implement `__setattr__`, `__setitem__`, `__delattr__`, and `__delitem__` so normal
  API descriptors/initialization win. When a writable bound backend is active, other
  paths delegate a normalized value/source operation to it; standalone unknown-path
  assignment retains its existing rejection behavior. Assignment through a bound
  projected handle and `.set()` on that handle pass the same complete path.
- Implement augmented assignment so both `ctx.a.b.c += 1` and
  `p = ctx.a.b.c; p += 1` become one value-update transaction. Return/assignment
  handling for the first form must avoid a second mutation or self-edge.

Tests:

- Existing standalone Cell/Expression tests, including projected `.set()` retargeting,
  remain green.
- Standalone unknown attribute/item assignment remains rejected and cannot mutate the
  Cell from which a projection was derived.
- `Cell(...).a.b[0]` preserves the entire path through clone, mutation, build, and repr.
- `.value`, `.checksum`, `.buffer`, `.run`, and every other class-defined name win over
  attribute navigation; bracket access reaches colliding fields.
- `cell.pins` is an ordinary projection and no public Cell pins namespace is exported.
- projected bound `.set()` and attribute/item assignment reach the same backend
  operation with the complete path; result projections raise `ReadOnlyEndpointError`.
- `ctx.a.b.c += 1` and `p = ctx.a.b.c; p += 1` each commit once.
- explicit `derived.input_ref = new_checksum` retains the derived path and builds a new
  independent Expression.
- import tests prove `seamless-core` functions with `seamless_workflow` unavailable.
- a fake bound backend proves the canonical factory and every delegated field without
  importing workflow.

Acceptance:

- `rg "seamless_workflow" seamless-core/seamless` returns no integration import.
- No bound-capable Cell method reads `_path`, `_input_ref`, or configuration slots
  after selecting a bound backend.
- Standalone and fake-bound navigation pass the same path test corpus.

### Phase 2: Centralize Transformer State And Snapshot Assembly

Goal: standalone and bound Transformer calls use one immutable-Transformation builder.

Implementation:

- Define a normalized `TransformerBuilderSnapshot` containing code buffer/checksum,
  language, signature/pins, configured arguments, celltypes, optional pins, modules,
  globals, meta, environment, scratch, local/direct flags, and call mode.
- Make the standalone state and workflow backend each produce that snapshot.
- Refactor `TransformerCore.__call__`:
  1. request the active state snapshot;
  2. merge explicit arguments over prebound arguments without mutating either source;
  3. validate missing/optional pins;
  4. call the existing pretransformation/transformation construction path;
  5. return the immutable `Transformation`.
- Remove backend `.call()` as an execution escape hatch. A backend may provide
  `snapshot_for_call()` and immutable dependency captures but may not return a raw
  computed value for delayed calls.
- Keep `DirectTransformer.__call__` as build-then-execute over the returned
  Transformation. For a bound DirectTransformer this is detached snapshot execution:
  it must not demand or mutate the current reactive node, acquire Context activation,
  or enter Context current-run/prune bookkeeping.
- Route `allow_input_fingertip`, `driver`, meta, modules, globals, environment,
  celltypes, args/pins, and every other mutable surface through active state.
- Add supported canonical factories for a delayed or direct handle from a backend.
- Add explicit backend-aware properties/methods for `.result`, `.run()`,
  `.compute()`, `.task()`, `.prune()`, `.clear_exception()`, `.transformation()`, and
  `.get_transformation()`.
- Add API-name-aware pin sugar. After static API lookup fails, `__getattr__` reads the
  declared pin exactly as `.pins`; `__setattr__` writes the whole pin exactly as
  `.pins`. Preserve initialization and normal descriptors before considering pin
  sugar.
- Define Transformer `__getitem__`, `__setitem__`, and deletion as `.pins` sugar in
  standalone and bound modes. Item syntax is the collision escape hatch and must not
  return a bound-only endpoint wrapper.
- Do not add a reserved `.inp` property/namespace to the canonical class. A declared
  pin named `inp` follows normal direct-pin sugar. No public operation accumulates a
  target path below a Transformer pin.

Tests:

- Existing delayed/direct standalone tests remain green.
- A fake bound backend yields the same transformation identity as an equivalent
  standalone Transformer snapshot.
- Explicit arguments override prebound pins for one call without mutating the backend.
- Bound delayed calls return `Transformation` and never call the stored Python function
  during construction.
- Bound direct calls execute successfully.
- Bound direct calls leave graph state, current reactive result, activation counts,
  and Context run bookkeeping unchanged.
- All snapshot-bearing metadata affects construction exactly as in standalone mode.
- Static API names win over pin sugar; a declared `scratch` pin requires `.pins` or
  item syntax.
- Direct and item pin sugar has the same read/write behavior before and after binding.

Acceptance:

- There is one transformation assembly implementation for standalone and bound calls.
- No bound call path returns a raw delayed-transformer value.
- No bound-capable public method reads abandoned `_args`, `_celltypes`, `_modules`,
  `_globals`, `_environment`, or `_meta` state.

### Phase 3: Introduce The Workflow Endpoint Model And Bound Backends

Goal: all Context sources and target-capable operations have one normalized identity
independent of public helper class, while each Transformer pin remains one producer
slot.

Implementation:

- Add immutable `BoundEndpoint` and access-mode definitions in a workflow-owned module
  such as `seamless_workflow/endpoints.py`.
- Implement one source protocol entry point, for example `_workflow_endpoint()`, on
  bound backends and source-capable endpoint helpers. Target-capable namespace/setter
  operations synthesize the same normalized descriptor internally; a target does not
  need a first-class public object. Do not expose graph `Node`, `Edge`, or `Overlay`.
- Make both Context edge wiring and lower-package standalone snapshot capture consume
  this protocol; no second capture-specific registry of workflow helper classes is
  permitted.
- Extend `BoundCellBackend` with:
  - root node identity;
  - complete projection path;
  - access mode (`cell-writable` or `result-readonly`), independent of path depth;
  - correct derive/navigation;
  - root/projection observations;
  - `.set()`/`.set_checksum()` dispatch using the complete path;
  - snapshot capture and runtime demand;
  - stale-node validation.
- Add `BoundTransformerResultCellBackend` using transformer result celltype metadata.
  It supports projection, observation, capture, and demand but rejects all producer
  mutation and path assignment.
- Replace the alpha Cell local-producer overlay with one root set-value producer plus
  zero or more one-level incoming edges used for deterministic assembly. There are no
  non-root local value producers. Replace `Node.cell_overlay` with a scalar field such
  as `cell_root_producer: ConstantProducer | None`. Expose no
  `CellPinsView`/`CellPinView`.
  Target-capable Cell assignment or `.set()` synthesizes a root/one-level descriptor
  directly from the bound Cell backend and requested path.
- Enforce that Cell edge storage never contains target paths deeper than one component
  and Cell local producer storage never contains a non-empty path. Literal update
  paths exist only for the duration of an RMW transaction.
- Replace Transformer pin overlays with a whole-pin producer representation. Use one
  node-local map such as `transformer_pin_producers: dict[str, ConstantProducer]` for
  literal/checksum producers; dependency producers remain graph edges targeting
  exactly `(pin_name,)`. Enforce at most one producer per pin.
- Delete recursive Transformer input endpoint construction. The canonical `.pins`
  wrapper performs whole-pin read/set/delete, validates declared pins, reconstructs
  dependency sources on reads, synthesizes target descriptors for writes, and checks
  stale-node state.
- Replace `_assembled_pin_checksum()` with exact-pin resolution: select the local
  producer or incoming edge, require its resolved checksum, and never join descendant
  pieces.
- Rework `BoundTransformerBackend` to expose:
  - normalized builder snapshot;
  - behaviorally symmetric `.pins`/`.args` and metadata wrappers;
  - `.result`, whole-code semantics, runtime controls, and result/source descriptors;
  - call mode.
- Replace `_transformer_config_from_builder()` and replacement/binding paths that read
  `_args`, `_celltypes`, `_modules`, `_globals`, or `_meta` directly. They must consume
  the normalized active builder snapshot, so an already-bound alias cannot contribute
  stale standalone configuration.
- Reconstruct configured incoming-edge producers returned through `.pins` as public
  bound source handles or stable producer descriptors; never return raw graph records.
- Add `StaleWorkflowHandleError`; make every backend/endpoint operation validate node
  existence before access.

Tests:

- Endpoint descriptor equality depends on top id, node path, kind, local path, and
  access flags—not Python object identity.
- Root Cell, deep projection, one-level Cell target resolution, Transformer result,
  deep result projection, whole Transformer pin target resolution, and whole code
  target resolution yield correct descriptors.
- Result Cell rejects root/projected `.set()` and `.set_checksum()`, attribute/item
  assignment or deletion, connection assignment, and augmented mutation with
  `ReadOnlyEndpointError`.
- Deleted-node operations consistently raise `StaleWorkflowHandleError`.
- `.pins` and `.args` reads match through original alias and fresh lookup, including a
  configured incoming edge.
- Local whole-pin assignment replaces the previous incoming edge; whole-pin edge
  assignment replaces the local producer; neither operation leaves descendants.
- Graph loading rejects a Transformer target path below `(pin_name,)`.
- Graph loading rejects a Cell edge below one component and every non-root Cell local
  producer; literal assignment tests prove no such producer is emitted at any depth.

Acceptance:

- Every legal source/target named in the contract has an endpoint test.
- No wiring decision requires importing or enumerating a concrete public view class.
- `ctx.tf.result` can be constructed as an actual `Cell` using its dedicated backend.
- Workflow Transformer evaluation consumes a direct dictionary of resolved pin
  checksums and contains no per-pin join/overlay path.

### Phase 4: Replace Context Node Wrappers With Canonical Handles

Goal: Context lookup, assignment dispatch, and binding use canonical builder handles.

Implementation:

- Change `Context._view()`:
  - cell node -> `Cell._from_backend(BoundCellBackend(...))`;
  - delayed transformer node -> canonical bound `Transformer`;
  - direct transformer node -> canonical bound `DirectTransformer`;
  - namespace/missing path -> retain `SubContextView`/`MissingView`.
- Order assignment classification so a same-top-level bound endpoint is recognized as
  a dependency source before generic `isinstance(Cell/Transformer)` builder binding.
- Replace `_is_bound_source()`/`_source_path()` with endpoint-protocol resolution.
- Make assigning a bound Transformer source mean its result endpoint. Ensure
  `ctx.out = tf` never rebinds `tf` away from its original node.
- Preserve recursive binding only for genuinely standalone builders.
- Remove `None`-as-deletion dispatch: classify `None` as a literal value for existing
  or new Cell assignments; only `del` enters deletion dispatch.
- Make same-endpoint assignment inert. This handles Python's write-back after
  successful bound `__iadd__` without adding a self-edge.
- Preserve cross-top-level errors, cycle checks, and longest-prefix node resolution.
- Route Context root item/attribute assignments through writable backend/endpoint
  operations where appropriate.
- Remove imports and runtime dependencies on `CellView`, `TransformerView`, and
  `TransformerResultView`.

Tests:

- `ctx.a`/`ctx.tf` canonical type and callability.
- original alias and repeated lookup parity; `ctx.a is ctx.a` need not hold.
- `ctx.out = already_bound_tf` creates a cell/result edge and leaves the original alias
  attached to its original node.
- `ctx.out = ctx.tf.result` produces the same static graph edge.
- same-endpoint augmented write updates once and creates no self-edge.
- cross-top-level assignment errors before mutation.
- `ctx.a = None` and `ctx.a.set(None)` store the same null value; `del ctx.a` deletes
  the node.
- recursive standalone builder binding still creates pseudo-anonymous nodes and mutates
  absorbed original handles to aliases.

Acceptance:

- Context lookup never returns a top-level node wrapper.
- Bound-source classification cannot fall through to literal checksum serialization
  or builder rebinding.
- Existing graph/state-machine tests pass after adapting assertions to canonical
  handles.

### Phase 5: Implement Cell Projection, Value Update, And Connection Depth

Goal: deep Cell reads and literal updates coexist with root/one-level-only connection
targets, without public Cell pins or persistent deep overlays.

Implementation:

- Store full normalized projection paths on source edge endpoints. Permit Cell source
  suffixes to every depth supported by Expression.
- Materialize source Expressions per tick from the source node's current immutable
  result plus complete projection path and celltype metadata.
- Make `ctx.a.foo`, `ctx.a["foo"]`, numeric item access, and slice access derive bound
  projection Cells. With `Cell.pins` removed, `ctx.a.pins` follows the same projection
  rule.
- Implement one serialized mutation entry point receiving owner node, complete logical
  path, operation (`set-rhs`, `set-checksum`, or `delete`), and RHS/capture token.
  Attribute/item assignment and bound `.set()` call the same entry point. Classify a
  workflow source before checksum serialization.
- For a source RHS, allow only path `()` or one point-selection component. Add/replace
  the exact edge and reject deeper paths or a slice target with `PathError` before
  changing the root producer or edges.
- For a root value/checksum RHS, serialize or normalize it immediately and replace the
  root set-value producer under existing authority rules.
- For every non-root value/checksum update:
  1. reject an incoming edge at the root or first component with `AuthorityError`;
  2. obtain a detached current value in the same controller transaction;
  3. materialize a supplied subvalue checksum when using `.set_checksum()`;
  4. distinguish truly producer-free unwired state from explicit null;
  5. bootstrap unwired string-key paths with `{}` and create missing mapping
     intermediates;
  6. require existing compatible containers for numeric/slice components and apply
     ordinary Python indexing/mutation errors;
  7. commit the updated aggregate as the one root set-value checksum while preserving
     every unrelated one-level incoming edge.
- For non-root deletion, remove an exact one-level incoming edge if present; otherwise
  perform the same atomic root-value RMW deletion. `del ctx.a` deletes the Cell node;
  it is not an operation on the root set-value producer alone.
- Never store a Cell local value producer at a non-empty path or an edge target deeper
  than one component. A non-root value-update path must be absent from graph JSON,
  dependency indexes, and reactive authority tables after the transaction.
- Make `.set(rhs)` on a writable bound projection exactly equivalent to assignment at
  the same path. Augmented mutation through an owning expression or a separately held
  bound projection uses the same mutation entry point and commits once.
- Apply API-name arbitration uniformly to standalone and bound Cells.

Tests:

- `ctx.out = ctx.data.a.b[0]` stores the complete source path and updates reactively.
- Deep projection over plain/mixed data resolves correctly; deep projection over deep
  checksums preserves checksum-level structural selection where supported.
- `ctx.data.value` is API; `ctx.data["value"]` is field projection; `ctx.data.pins` is
  an ordinary field projection.
- `ctx.a = Cell(); ctx.a.b.c = 12` produces `{"b": {"c": 12}}` and serializes exactly
  one root set-value checksum producer.
- Existing mapping intermediates are copied and updated; missing mapping
  intermediates are created; explicit null and scalar intermediates raise `TypeError`.
- Assignment and `.set(None)` store a null leaf at root/one-level/deep paths; `del`
  remains the only deletion syntax.
- Existing list index, negative-index, and slice updates follow Python behavior;
  missing lists are not inferred or grown.
- `ctx.a.b = source` creates a one-level edge; `ctx.a.b.c = source` raises `PathError`
  without graph mutation.
- A one-level integer-index source target works against an existing compatible list;
  an unwired/missing list raises `TypeError`, an out-of-range index raises `IndexError`,
  and a one-level slice source target raises `PathError`, all without graph mutation.
- `ctx.a.b.set(12)` equals `ctx.a.b = 12`; `ctx.a.b.set(source)` equals
  `ctx.a.b = source`; `ctx.a.b.c.set(source)` raises `PathError` without mutation.
- An incoming root or `b` edge blocks `ctx.a.b.c = 12`; an unrelated `d` edge remains
  connected and reactive after the update.
- A waiting/failed unrelated `d` edge does not cause `AuthorityError`, but it causes
  `ValueUnavailableError` when the aggregate cannot be materialized.
- `ctx.a.b.c.set(1)`, `ctx.a.b.c += 1`, and
  `p = ctx.a.b.c; p += 1` are legal and each commits once.
- One-level edge deletion and non-root value deletion follow their separate edge/RMW
  behavior.
- If root auth contains `b` and an edge overlays `b`, the first `del ctx.a.b` removes
  the edge and reveals auth `b`; a subsequent deletion removes auth `b` by root RMW.
- Waiting/blocked/failed non-root updates raise `ValueUnavailableError` and
  do not mutate the graph.

Acceptance:

- Source projection, value-update, and connection-target depth use separate
  validators/dispatch paths.
- Every cell in the assignment matrix has a direct value-RHS and source-RHS test.
- The graph represents deep Cell source paths but contains no non-root Cell local value
  producer and no deep Cell target after a value update.
- No public Cell pins namespace or helper survives.

### Phase 6: Restore Bound Snapshot And Reactive Demand Semantics

Goal: canonical bound builders correctly separate immutable snapshots from reactive
node demand.

Implementation:

- Implement bound Cell `build()`/`expression()`/`__call__()` capture:
  - complete independent cell -> checksum-wired Expression;
  - current Context-private Expression/Transformation -> immutable captured dependency;
  - root set value combined with one-level incoming edges -> join Transformation
    snapshot;
  - projection from an assembled result -> projection Expression depending on the
    join;
  - waiting -> `NotImplementedError` until future-wired snapshots exist;
  - unwired/blocked -> typed node/capture error;
  - failed -> capture the failed current immutable work where the existing capture
    contract permits it.
- Implement bound Cell `compute()`/`run()`/async computation using activation leases
  and projection application.
- Implement `BoundTransformerBackend.snapshot_for_call()` using current configured
  pins/edges and established capture rules.
- Implement `.transformation()`/`.get_transformation()` as no-override snapshots of
  current transformer configuration.
- Implement Transformer `.compute()`/`.run()`/`.task()` as reactive demand with
  checksum/value/async return types respectively.
- Ensure explicit `ctx.tf(...)` overrides affect only the returned snapshot.
- Preserve failure, cancellation membership, and clear-exception propagation of
  captured E/T handles.

Tests:

- Bound Cell call/build returns immutable E/T and remains unaffected by later graph
  edits.
- Bound delayed Transformer call returns a frozen Transformation whose identity and
  result match an equivalent standalone snapshot.
- Explicit overrides do not alter `ctx.tf.pins`, configured pin producers, edges, or
  current reactive result.
- Bound DirectTransformer works before and after lookup reconstruction.
- A bound DirectTransformer call executes only its detached snapshot and leaves the
  Context's reactive result, activation leases, and run/prune records unchanged.
- `run()` returns value; `compute()` returns checksum; `task()` awaits value.
- Non-eager root and projected demands increment/release exactly one activation lease
  set, including cancellation/error paths.
- capture-state matrix covers complete, computing, failed, waiting, unwired, and
  blocked.

Acceptance:

- `__call__` and reactive demand are observably distinct and correctly typed.
- Snapshot identity includes all load-bearing Transformer state and immutable
  dependencies.
- No snapshot construction directly calls user transformer code.

### Phase 7: Transformer Pins, Metadata, And Collision Completion

Goal: finish the Transformer public surface without recreating a parallel wrapper API.

Implementation:

- Complete behaviorally symmetric wrappers for `.args`, `.pins`, `.celltypes`,
  `.modules`, `.globals`, `.meta`, and `.environment`.
- Define `.pins` reads for constants, checksums, and reconstructed same-Context bound
  dependencies. Mutating returned materialized containers does not mutate the graph;
  reassignment is required.
- Complete whole-pin set/delete/wiring through `.pins` and `.args`; each operation
  replaces the pin's one previous producer atomically.
- Lift direct and item pin sugar into canonical Transformer lookup/assignment with the
  declared-pin and API-collision rules. Reads return the same configured
  producer/value form as `.pins`, never a target wrapper.
- Preserve `.code` read type across standalone, original bound alias, and lookup;
  make `.code = bound_source` target the whole code input without introducing
  `.inp.code`.
- Complete `.result` projection, observations, snapshots, and wiring.
- Verify driver, fingertip, local, scratch, direct-print, optional-pin, result celltype,
  modules/globals, and environment changes rederive or invalidate exactly as required
  by existing Context identity rules.

Tests:

- Table-driven parity over every Transformer public metadata surface.
- `.pins.x` has the same kind/value through original and lookup handles.
- `.pins.x = source`, `tf.x = source`, and `tf["x"] = source` produce the same
  whole-pin edge; corresponding reads agree.
- Nested Transformer target construction is unavailable, and a serialized nested
  target is rejected with `PathError`.
- `scratch` setting and pin collision remain separately reachable.
- `.code` type/value parity and whole-code source-assignment behavior.
- `.result` is a Cell, is read-only, supports deep projection, and wires as source.
- optional pins and metadata survive snapshot, graph round-trip, and reactive rerun.

Acceptance:

- No required Transformer API is implemented only on a workflow top-level wrapper.
- `.pins` is the only Transformer pin namespace and has one behavior before and after
  binding.
- No Transformer evaluation, mutation, or serialization path contains descendant pin
  targets or per-pin assembly.
- Metadata parity helper passes for original aliases and fresh lookups.

### Phase 8: Graph Schema, Serialization, And Stale Handles

Goal: persist enough static state to reconstruct canonical handle behavior and make
handle invalidation deliberate.

Implementation:

- Add transformer `call_mode` to `TransformerConfig`, `get_graph()`, and `set_graph()`.
- Serialize a Cell's node-local value as one optional root producer, not an overlay
  entry list. One-level Cell inputs are represented only by graph edges.
- Serialize complete source projection paths with the canonical Expression path
  encoding. Serialize target paths only in their restricted root/one-component forms.
- Validate source projection and connection-target paths independently on graph load;
  reject every Cell target below one component, every Cell slice target, every
  non-root Cell local producer, and every Transformer target with components below the
  whole pin. Deep Cell value-update paths are never serialized.
- Do not add compatibility fallback for missing alpha `call_mode`; tests may update
  fixtures directly. If a default is operationally convenient during development,
  remove it or document it as deliberate `"delayed"` normalization before release.
- On node/subcontext deletion, invalidate bound backend access through existence checks;
  outstanding handles raise `StaleWorkflowHandleError`.
- Ensure copied subcontexts reconstruct correct canonical handles and preserve direct
  call mode while continuing to drop boundary-crossing edges.
- Keep runtime E/T and public handles out of static graph JSON.

Tests:

- delayed/direct graph round-trip recreates the right canonical class and call
  behavior.
- graph round-trip preserves deep source paths and whole Transformer pin targets.
- graph loading rejects former alpha `transformer_pin_overlays` data and descendant
  Transformer targets rather than silently changing their meaning.
- graph loading rejects deep Cell targets, non-root Cell local producers, and former
  public Cell-pins artifacts; completed non-root literal updates round-trip only as
  their committed root set-value checksum producer.
- invalid endpoint-kind/path combinations are rejected deterministically.
- stale root, projection, result, and retained Transformer `.pins`/metadata
  wrappers all raise the same typed error after deletion.
- subcontext copy retains internal paths/flavor and drops external edges.

Acceptance:

- Static graph JSON is sufficient to reconstruct every durable public behavior added
  by this follow-up.
- No serialized object is a Python builder, backend, helper view, or private E/T.

### Phase 9: Remove The Experimental Dual Surface

Goal: delete obsolete code only after canonical handles cover all required behavior.

Implementation:

- Remove `CellView`, `TransformerView`, and `TransformerResultView`.
- Remove `CellPinsView`, `CellPinView`, `StandaloneCellPins`, the public `Cell.pins`
  property, and their exports. Replace the alpha Cell local-producer overlay with one
  root set-value producer; retain only one-level incoming edges for subvalue
  connections.
- Remove `TransformerInputView` and `TransformerPinView`; no replacement public
  endpoint type is needed. Consolidate `TransformerPinsView`,
  `WorkflowTransformerPins`, and the standalone pins wrapper behind the canonical
  backend-aware `.pins` implementation.
- Remove `transformer_pin_overlays`, descendant-target assembly, and their graph JSON
  fields. Retain only whole-pin local producers and exact-pin incoming edges.
- Keep `MissingView` and `SubContextView`.
- Remove dead `isinstance` branches, duplicate metadata forwarding, duplicate pin
  wrappers, and obsolete exports.
- Update workflow README and the earlier Context implementation/handoff documents with
  a prominent superseded-by link to the follow-up design/plan or directly correct their
  conflicting public-view sections.
- Remove all temporary expected-failure markers.

Tests:

- `rg`/AST check finds no construction of removed top-level wrapper classes.
- `rg`/AST check finds no `CellPinsView`, `CellPinView`, `StandaloneCellPins`, or
  class-defined public `Cell.pins`.
- Public workflow exports do not expose obsolete node wrapper types.
- Full tests pass without compatibility shims.
- Import-cycle smoke tests pass in separate processes for core, transformer, and
  workflow.

Acceptance:

- There is one public Cell implementation and one public Transformer implementation
  over either standalone or bound state.
- Remaining helper views represent only namespaces/endpoints with no canonical builder
  counterpart.

### Phase 10: Full Contract And Regression Audit

Goal: prove the refactor did not preserve the alpha API at the expense of settled
functional and reactive contracts.

Implementation:

- Run standalone core and transformer suites first.
- Run workflow tests with local repository packages selected explicitly in
  `PYTHONPATH` or an equivalent editable environment; do not accidentally test
  unrelated installed releases.
- Add a public-surface parity table test covering original alias versus lookup.
- Add a small reactive diamond using a deep projected source to check glitch-free
  invalidation under the new endpoint model.
- Add repeated graph edits and calls to prove snapshots remain immutable while the
  Context remains reactive.
- Audit all source/target paths for constants-as-checksums, no materialized Python
  values retained in graph state after a transaction, and no persisted non-root Cell
  value-update paths. Transient materialization inside atomic RMW is expected.
- Audit non-eager lease release, prune, and clear-exception through canonical handles.
- Run static searches for reverse imports and stale private-state reads.

Tests:

- `seamless-core` full test suite.
- `seamless-transformer` full local/non-remote unit suite; remote suites only when their
  configured services are available.
- `seamless-workflow` full suite.
- Targeted integration matrix below.

Acceptance:

- All mandatory local suites pass.
- Service-dependent tests are either passing or reported separately with their exact
  missing service; they are not silently skipped as proof of correctness.
- Compliance audit at the end of this document passes.

## Required Test Matrix

### Canonical handle parity

- bound Cell original alias versus `ctx.cell`;
- bound delayed Transformer original alias versus `ctx.tf`;
- bound DirectTransformer original alias versus `ctx.tf`;
- repeated Context lookups with different Python identities;
- configuration mutations visible through every alias.

### Cell navigation and collision

- attribute, string item, integer item, and slice projections;
- paths at depths 1, 2, and 4;
- API collision names: `value`, `checksum`, `buffer`, `run`, and `clear_exception`;
- `pins` specifically remains available as an ordinary Cell data projection;
- standalone bound-only-property errors do not fall through;
- full path retained across derive/build/repr;
- explicit standalone projection `input_ref` retargeting;
- standalone projected `.set()` retargeting versus writable bound projected `.set()`;
- read-only Transformer-result projection mutation rejection.

### Cell value update, connection depth, and authority

- absence of public `Cell.pins` in standalone and bound modes;
- root and one-level value assignment;
- root and one-level source connection;
- one-level and deep attribute/item value assignment, `.set()`, `.set_checksum()`, and
  deletion as one root-value RMW transaction;
- deep source assignment rejection before mutation;
- empty mapping bootstrap versus explicit null;
- literal `None` assignment/`.set()` versus explicit `del`;
- missing/existing mapping intermediates;
- list integer, negative-index, and slice behavior without inferred list growth;
- root/first-component authority conflicts;
- preservation of unrelated one-level connections;
- item-read projection versus item write/`.set()` parity;
- augmented assignment through owner syntax and a separately held bound projection,
  plus same-endpoint write-back no-op;
- graph proof that no non-root literal producer is stored.

### Transformer construction and demand

- delayed call returns Transformation before/after binding;
- direct call returns value before/after binding and graph round-trip;
- explicit call override is snapshot-local;
- missing, default, required, optional, connected-optional, and null optional pins;
- modules, globals, environment, metadata, celltypes, scratch/local/direct/fingertip
  state in snapshot identity/envelope as appropriate;
- reactive `run`, `compute`, and `task` return types;
- non-eager activation acquire/release.

### Transformer pins and result

- `.pins`/`.args` parity and non-live materialized container reads;
- one local or edge producer per whole pin;
- whole-pin wiring through `.pins`, direct attribute sugar, and item sugar;
- direct attribute sugar for declared non-colliding pins;
- typo rejection;
- `scratch` and other API collisions;
- absence of a reserved `.inp` namespace, ordinary behavior for a declared pin named
  `inp`, and nested Transformer target rejection;
- `.code` normal semantics and whole-code source assignment;
- `.result` type, read-only behavior, projection, snapshot, and source wiring.

### Dependency and lifecycle

- every legal source/target endpoint combination;
- bound Transformer assigned at a new key creates result wiring, not rebind;
- cross-top-level rejection;
- self-edge and cycle rejection;
- recursive binding of standalone closures;
- complete/computing/failed/waiting/unwired/blocked capture matrix;
- stale handles after node and subcontext deletion;
- subcontext copy and graph round-trip.

## Suggested Commit Boundaries

Keep commits independently reviewable and, where practical, test-green:

1. Contract tests and local error types.
2. `seamless-core` Cell backend/path/collision cleanup.
3. `seamless-transformer` normalized snapshots and shared call construction.
4. Workflow endpoint descriptors and complete bound backends.
5. Context canonical lookup and assignment dispatch.
6. Projection/value-update/connection depth and deep source paths.
7. Snapshot/demand completion.
8. Transformer pin/result completion.
9. Graph schema and stale-handle behavior.
10. Obsolete wrapper removal, docs, and final audit.

Do not combine lower-package semantic changes with wrapper deletion in one commit; the
intermediate API parity tests should show which side provides each behavior.

## Completion Checklist

- [ ] `ctx.cell` is an actual `Cell` and `ctx.tf` an actual canonical Transformer.
- [ ] Original aliases and fresh lookups pass the public parity matrix.
- [ ] No top-level node wrapper duplicates Cell/Transformer behavior.
- [ ] Cell projection is uniform across boundness and complete paths are retained.
- [ ] API names win and colliding fields remain available by item syntax.
- [ ] Writable bound projections support `.set()`/`.set_checksum()` and augmented
      mutation; Transformer-result projections raise `ReadOnlyEndpointError`.
- [ ] Cells expose no `.pins`; `cell.pins` is an ordinary projection.
- [ ] Cell connections are root/one-level-only and authority-checked.
- [ ] One-level mapping-key/integer connection targets and slice rejection follow the
      declared component rules.
- [ ] Every non-root Cell value assignment/deletion is atomic root-value RMW and
      persists no non-root local producer or deep target.
- [ ] `None` is stored as a value by assignment/`.set()`; only `del` deletes.
- [ ] Item read projection and item write/`.set()` parity are tested distinctly.
- [ ] Delayed bound calls return immutable `Transformation` objects.
- [ ] Direct bound calls preserve direct behavior.
- [ ] Reactive run/compute/task are distinct from builder calls.
- [ ] `.pins` is the sole Transformer pin namespace; no reserved `.inp` namespace
      exists, and a declared pin named `inp` remains ordinary.
- [ ] Every Transformer pin has exactly one whole-pin producer and no descendant
      overlay.
- [ ] `.code` and `.result` obey their separate contracts.
- [ ] `ctx.tf.result` is a read-only bound Cell.
- [ ] Endpoint-protocol wiring replaces view-class enumeration.
- [ ] Same-top-level bound Transformer assignment wires instead of rebinding.
- [ ] Deep Cell source-projection paths, transient deep value-update paths, and
      one-level connection paths validate separately.
- [ ] Call mode and endpoint paths round-trip statically.
- [ ] Stale handles raise a typed workflow error.
- [ ] Bound paths never read abandoned private slots.
- [ ] `seamless-core` and `seamless-transformer` contain no workflow imports.
- [ ] Core, transformer, workflow, and targeted integration tests pass.
- [ ] Experimental compatibility shims and expected-failure markers are gone.

## Compliance Audit

The handoff is complete only when an implementer can answer yes to all of these without
consulting an ancestor design document:

1. Are the desired public types and identity rules explicit?
2. Are projection, value update, and connection assignment defined independently,
   including depth and authority?
3. Are attribute collisions and bracket escape behavior explicit?
4. Are standalone projection reconfiguration and projected `.set()` distinguished?
5. Are Cell call/build/compute/run return types explicit?
6. Are Transformer call and reactive demand distinct and correctly typed?
7. Are `.pins`, `.code`, and `.result` independently defined, with the reserved `.inp`
   namespace and Transformer pin-subpath targets explicitly absent?
8. Is every legal endpoint represented by one normalized protocol?
9. Are repository ownership and import directions explicit?
10. Are direct/delayed flavor, graph schema, deletion, and stale handles covered?
11. Does every phase have implementation, tests, and acceptance criteria?
12. Does the test matrix cover both standalone contracts and Context integration?

Compliance evaluation at authoring time: **pass**. All twelve questions are answered in
this document. Implementation completion remains subject to the phase acceptance gates
and completion checklist.
