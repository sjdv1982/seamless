# Cells (Contract)

**A Cell is a deferred Expression.** Where an `Expression` is a frozen recipe that has already been closed over its input, a `Cell` is the mutable builder for the same recipe — `(input, input_celltype, celltype)` plus a path and an optional validator — that can be re-aimed, retyped and re-read, and that snapshots into an immutable `Expression` on demand. Everything an Expression means (identity, cost class, placement, the error envelope, uncached failures) is in `contracts/expressions.md` and is not repeated here.

A Cell exists in one of two modes:

- **standalone** — the builder state is private to the Python object;
- **bound** — the builder state is owned by a workflow `Context` node, and the Cell is a *view* onto that node.

The two modes share one class, one read API and one write API. They differ in exactly three places: who owns the state, whether a read waits, and which operations exist at all (projection writes, mounts, `prune()` and `block_reason` are bound-only). Those differences are marked throughout.

Pins are the **sister class**, not a subclass: `Pin` and `Cell` share `CellBase`, which carries the value, type, evaluation and ownership API. Everything Pin-specific — routing to a Transformer, the pin null rules, the absence of projection, validators and mounts — belongs to features 6 and 7 and is documented with them. A Pin is never a valid Cell input; passing one raises `TypeError` pointing at `pin.source`.

Code locations:

| Concern | Module / symbol |
|---|---|
| Shared value/type/evaluation/ownership API | `seamless.cell_class.CellBase` |
| Builder, navigation, snapshots | `seamless.cell_class.Cell`; re-exported as `seamless.Cell` |
| Sub-path projection handle | `seamless.cell_class.SubCell` |
| Module helpers | `seamless.cell_class` (`_is_input_ref`, `_check_input_ref`, `_serialize_value`, `_checksum_for_buffer`, `_available_input_checksum`, `_typed_input_celltype`, `_capture_workflow_source`, `_class_attribute`) |
| Errors | `seamless.cell_errors` (`AuthorityError`, `ProjectionError`, `BoundStateError`, `WorkflowError`); `seamless.CacheMissError`; `seamless.error_envelope` (`RunningLoopRefusal`, `execution_error`, `WorkflowExecutionError`); `seamless_workflow.errors`, which re-exports `WorkflowError` / `AuthorityError` and adds `PathError`, `ValueUnavailableError`, `StaleWorkflowHandleError`, `ConcurrentUpdateError` |
| Retired names | `seamless.retired_names` (`RETIRED_NAMES`, `check_retired_name`) |
| Snapshot container | `seamless.expression_class.Expression` (see `contracts/expressions.md`) |
| Bound backend | `seamless_workflow.builder_state.BoundCellBackend` |
| Bound writes, reads, barriers | `seamless_workflow.ingress` (`controller_method`, `_edit`, `_wait`, `_wait_async`, `_prepare_assignment`) |
| Bound graph operations | `seamless_workflow.context.Context` (`_assign`, `_cell_operation`, `_validate_write`, `_cell_delete_path`, `_derive_cell`, `_projection`, `_demand`, `_build_cell_expression`, `_effective_input_celltype`, `_public_cell_source`, `_get_checksum`/`_get_buffer`/`_get_value`, `_clear_exception`) |
| Local join and projection workers | `seamless_workflow.sidework` (`evaluate_cell`, `evaluate_projection`, `Lease`, `SideLoop`) |
| Value-form classification | `seamless_workflow.adapters.checksum_for_value` |

## The definition

```python
Cell(celltype=None, *, checksum=None, source=None, input_celltype=None,
     path=None, validator=None, validator_language=None)
```

- The positional argument is the **produced** celltype.
- `checksum=` and `source=` are **mutually exclusive** (`TypeError` otherwise). `source=` takes a typed reference — a `Cell`, an `Expression`, or any object exposing the duck-typed `_workflow_endpoint` / `_compute_dependency` protocol (a `Transformation`, a bound endpoint). A bare `Checksum` passed as `source=` raises `TypeError` naming `checksum=`; a `Pin` raises `TypeError` naming `pin.source`.
- `celltype` defaults to a typed source's `celltype`, else `"mixed"`. An unsupported name raises `TypeError` listing the supported celltypes (see `contracts/celltypes-and-conversion.md`).
- `input_celltype=` is a **declaration**, legal only alongside a bare checksum. With a typed source it must match, or construction raises `ValueError`.
- `path=` starts the builder at a projection; it is normalized by `normalize_path` and uses the Expression path syntax.
- `validator` / `validator_language` are accepted and stored, but validators are **not implemented** (below).

`build()` — also spelled `cell.expression()` and `cell()` — freezes the current builder state into an `Expression`. That Expression is the contract object; the Cell is the handle that produced it.

### Binding

Assigning a Cell into a Context binds it: `ctx.a = Cell("int")` moves the builder state into a Context node, and every later `ctx.a` returns a **fresh** `Cell` whose state lives entirely in `BoundCellBackend` (`Cell._from_backend`). Consequences:

- **Handle identity carries no meaning.** `ctx.a is not ctx.a`; two handles for one node are interchangeable, and a handle for a deleted node raises `StaleWorkflowHandleError` on its next use.
- A bound Cell is a view, not a copy: the Context runtime holds nodes, Expressions and Transformations, never Cells.
- A standalone Cell is never implicitly bound. `Cell(source=ctx.a)` captures the bound endpoint as its input (`_capture_workflow_source`), which is a reference to the node, not a binding of the new Cell.

### Retired names

`target_celltype` and `input_ref` are retired and raise `AttributeError` naming the replacement (`celltype`, and `source` or `checksum`). Because attribute access on a Cell falls through to *projection*, `check_retired_name` runs first in `__getattr__`, `__setattr__` and `__delattr__`, so a retired name can never silently become a sub-path. Item navigation is unaffected: `ctx.a["input_ref"]` is an ordinary projection of a data field with that name.

**There is no old → new migration.** Cells reach `main` unreleased; the contract below is the contract, not a translation of an earlier one.

## Celltypes: `celltype` is the output

**`celltype` is the type of what the Cell produces** — its checksum, its `.buffer`, its `.value`, its `run()`. **`input_celltype` says how the input is read, and is read-only** (assigning it raises `AttributeError`; there is no setter in either mode).

`input_celltype` comes from the input, and from nowhere else:

| The input is | `input_celltype` is |
|---|---|
| a typed reference (Cell, Expression, Transformation, bound upstream node) | that reference's `celltype`, followed **live** on a Cell; an `Expression` resolves it once, at construction |
| a value written with `.set()` / `.value =` / assignment | the celltype it was serialized in, which is the Cell's `celltype` at that moment |
| a bare `Checksum` | the celltype declared with it (`Cell(ct, checksum=cs, input_celltype=…)`, `set_checksum(cs, input_celltype=…)`), defaulting to `celltype` at that moment |
| absent | `None` |

*Verified:* standalone in `CellBase.input_celltype` / `_replace_input_ref` (`_typed_input_celltype(input_ref) or input_celltype or self.celltype`); bound in `Context._effective_input_celltype` (the root edge's source celltype, else `cell_root_producer.celltype`, else `None`).

Three rules follow:

- **Retyping converts; it does not reinterpret the stored input.** `cell.celltype = ct` changes only the output side. A `str` cell holding `"hello"` (`b'"hello"\n'`) retyped to `text` keeps `input_celltype == "str"` and produces the `text` checksum of `b"hello\n"` — a different checksum, the same value. Where the conversion is checksum-preserving (`int → float`, `int → text`, the trivial and reinterpret classes of `contracts/celltypes-and-conversion.md`) the checksum does not move and only `.value` differs.
- **Copy once, at creation.** A *new* cell built from a typed source copies that source's `celltype` once: `ctx.a = ctx.b` creates `a` with `b.celltype`. An *existing* cell keeps its own output type when rewired — `ctx.existing = ctx.typed` leaves `existing.celltype` alone and converts into it.
- **To correct a wrong declaration, declare the input again.** There is no setter; `set_checksum(cs, input_celltype=…)` is the spelling.

Retyping is refused on a mounted cell: `ValueError("Mounted celltype cannot change; unmount first")` (feature 11; see the mounts doc when it exists).

## The input: `.source` versus `.checksum`

The configured input is public as two read-only-in-meaning names that used to be one union:

| Public | Meaning |
|---|---|
| `.source` | the **derivation** arm, read-only: the upstream handle (bound) or the Cell / Expression / Transformation a standalone builder is built on; `None` when the node holds its own value |
| `.checksum` | the **value** arm: the current produced checksum. As a *write* it declares a literal input, and `None` clears |

Connecting is always assignment (`ctx.a = ctx.b`, `Cell(source=…)`, `with_input(…)`), so `.source` needs no setter and there is exactly one spelling. `_input_ref` is private and is the Expression recipe, in both modes.

`.checksum` reports the node's **current value**, so it is populated for a connected node too, and is `None` whenever the node is not complete:

| State | `.source` | `.checksum` |
|---|---|---|
| unwired | `None` | `None` |
| literal, complete | `None` | the literal, converted if its `input_celltype` differs from `celltype` |
| connected, complete, no conversion | the handle | `== source.checksum` |
| connected, complete, checksum-preserving conversion | the handle | equal to the source's (trivial / reinterpret: `plain → mixed`, `int → float`, `str → int`) |
| connected, complete, reformatting conversion | the handle | a different checksum (`str → text`, `int → bool`) |
| connected, upstream waiting / blocked / failed | the handle | `None` |
| own conversion or validator failed | the handle | `None` |

So **`.source is None` means "nothing upstream feeds this"** and **`.checksum is None` means "not complete"** — the blocker rule, read off the handle.

**On a projection, `.source` answers for that path.** It is the one-level edge targeting that path if there is one, otherwise the nearest enclosing source, otherwise `None`; deeper paths, which can never carry an edge, walk up the same way. A cell with a literal root and a connection at `b` therefore reports `ctx.a.source is None` and `ctx.a.b.source` as the upstream — otherwise sub-path edges would be visible only through `get_graph()`. *Verified:* `Context._public_cell_source` walks `local[:length]` downwards from the full path to the root; the standalone equivalent falls back to the root builder's own input.

## Writes: two verb families

Every write either **defines** the node's input or **writes under** an existing one, and they differ in whether authority is checked.

| Family | Spellings | On a connected target |
|---|---|---|
| **Declare the input** | `ctx.a = X`, `.value =`, `.buffer =`, `.checksum =` (including `= None`) | **make it so**: replaces whatever input exists, edge or producer |
| **Write what you own** | `.set()`, `.set_buffer()`, `.set_checksum()`, sub-path assignment, `+=` and friends | **check**: `AuthorityError`, since an upstream edge would overwrite the write on the next recompute |

The reason for the split is that the two answer different questions. `ctx.a = 7` over a connected cell is a statement about what `a` *is*; `ctx.a.set(7)` is a statement about a value the caller believes it owns, and an upstream edge falsifies that belief.

### The 3×2 matrix at the root

Three forms — value, buffer, checksum — each in both families. All three are readable and all three are writable.

| Form | Declare the input (detaches) | Write what you own (checks) |
|---|---|---|
| value | `ctx.a.value = v`; `ctx.a = v` and `tf.pins.x = v` are the idiomatic sugar | `ctx.a.set(v)` |
| buffer | `ctx.a.buffer = buf` | `ctx.a.set_buffer(buf)` |
| checksum | `ctx.a.checksum = cs` | `ctx.a.set_checksum(cs, input_celltype=…)` |

Everything reduces to setting a checksum; the rows differ in what they do first and in what they can guarantee:

- **value** — serialize with the node's `celltype`, which **validates**: `Cell("int").set("abc")` raises `ValueError`. This is where an invalid literal is rejected. The buffer is deposited (with a tempref until the Cell's refhold adopts it) and `input_celltype = celltype` is recorded.
- **buffer** — the bytes are in hand, so nothing is serialized, but they are still checked against the celltype: `_checksum_for_buffer` runs `validate_deserializable_as(checksum, celltype, buffer=buffer)` *and* `buffer.get_value(celltype)`, so a buffer that does not parse as the celltype is rejected at write time. A `Buffer` carries no celltype of its own, so `input_celltype = celltype`.
- **checksum** — an id only. Nothing is deposited, so the buffer must already be resolvable or the read fails later with `CacheMissError`; validation is limited to the hash-type bits; `input_celltype` defaults to `celltype` and is declarable.

**`set_checksum` does not set `.checksum`.** It is the Checksum variant of the three setters and sets the *input*. It is instantaneous, so `.checksum` is normally `None` immediately afterwards — except in the two cases the `.set_checksum` contract carves out (the dummy Expression and the unbound computed property), which are stated under *Reads* below and derived in `contracts/expressions.md`.

### `.set()` and `.value =` take values only

A reference is never a value:

- a `Checksum` raises `TypeError: A Checksum is not a value: use .set_checksum() (a Checksum is a value only for celltype 'checksum')`;
- a `Cell`, `Expression`, `Transformation` or bound endpoint raises `TypeError: A <T> is not a value: connect it by assignment, or with Cell(source=...)`;
- a `Pin` raises `TypeError` naming `pin.source`.

The check runs before the bound/standalone split, so it applies identically in both modes and to `.value =` as well as `.set()`. Assignment (`ctx.a = X`) and call-time transformer arguments are the *other* family and do keep reading a `Checksum` as a declared reference.

Consequences worth stating: a standalone Cell can no longer be rewired to a source in place — only `Cell(source=…)` and `with_input()`, and both create a new Cell.

### Authority

`AuthorityError` (a `WorkflowError`) is raised by the checking family when a source controls the target:

- standalone: `CellBase._check_write_authority` refuses when `.source is not None`;
- bound: `Context._validate_write` refuses when an incoming edge is an **ancestor** of the write path, or when an edge is **covered** by the write path and the write is not detaching.

So with an edge at `ctx.a.b`: `ctx.a.b.c.set(2)` raises, `ctx.a.set({...})` raises (the edge is covered by the root write), and `ctx.a.other.set(2)` succeeds — an edge at an unrelated first-level key does not block a sibling.

**Sub-path writes never detach.** `BoundCellBackend.write_value` / `write_checksum` pass `detach=detach and not self.local_path`, so the declare family collapses into the checking family below the root: `ctx.a.b.value = 3` checks authority exactly as `ctx.a.b.set(3)` does. Detaching is a root-level act.

A mounted cell refuses to be cleared: `AuthorityError("Cannot clear a mounted cell; unmount first")`, and a sensing mount refuses an incoming edge (`"Sensing mount is the producer; unmount first"`). Mounts are feature 11.

## Null and `None`

**`None` is a value for every Cell celltype.** Every cell is in effect `T | None`. There is **one celltype-independent representation**: the canonical JSON-null buffer `b"null\n"`, checksum `38e0b9de…`, which is trivial and resolves without cache residency. Null converts to itself for every celltype pair, so retyping a null cell is a no-op, and `str(checksum)` prints `NULL`. The details are in `contracts/celltypes-and-conversion.md`.

Three behaviours stay apart, and each has its own spelling:

| Spelling | Meaning |
|---|---|
| `.value = None`, `.set(None)` | store the **null value** — a real checksum; state `complete` |
| `.checksum = None`, `.buffer = None`, `.set_checksum(None)` | **clear the input** — node stays, state `unwired`, `input_celltype` becomes `None` |
| `del ctx.a` | **delete the node** |
| `del ctx.a["b"]` | delete a key from the value (and any edge targeting that exact path) |

`del` means the named thing is gone, and never "empty it". `ctx.a = None` does **not** delete; it stores null. This is required, not incidental: merging "no value" with "the value `None`" would destroy the distinction that optional pins and the "no result" checksum are built on, and the absence of a checksum is the blocker that gates every dependent.

**`bytes` is the one celltype where empty *is* null**, in both directions. `bytes` is the only celltype whose canonical serialization of a legitimate value is empty (`b""`, checksum `e3b0c442…`, which is also the empty file), so an empty buffer under celltype `bytes` canonicalizes to the null checksum, and resolving the null checksum as `bytes` gives `b""`. Hence `ctx.a = b""` on a `bytes` cell stores null and reads back `b""`. The rule is blanket — serialization, expression evaluation with output celltype `bytes`, transformation results, mount reads — and it is enforced in three places on the Cell path: `Buffer(b"", "bytes")`, `_checksum_for_buffer`, and the `.checksum` dummy fast path. One-directional aliasing would be worse: `b""` would silently become "no value" and every downstream required `bytes` pin would reject it.

No other celltype is affected, because none serializes to zero bytes (`text ""` is `b"\n"`, `str ""` is `b'""\n'`, `plain {}` is `b"{}\n"`).

## Celltype `checksum`

**A `Checksum` is a value exactly when the target celltype is `checksum`.** One rule, covering `.set()`, `.value =`, `ctx.a =`, `tf.pins.x =` and `tf(x=…)`. For a `checksum` cell:

- the buffer is the bare 64-character hex digest, which the cell does **not** hold — the cell points at a checksum, it does not contain the buffer behind it;
- `.value` is a `Checksum` object, and `.value == .run() == .build().run()`;
- `.set(cs)` and `.set(cs.hex())` give the same checksum.

For every other celltype, assignment and call-time arguments read a `Checksum` as a declared reference, while `.set()` and `.value =` raise `TypeError`. A 64-character `str` is always a value, never a checksum. Note that `Checksum == hex_str` is true but the two hash differently.

## Reads

Two concerns stay separate: **retrieving** `.checksum`, and **materializing** it into `.buffer` or `.value`.

### `.checksum`

**A property getter never runs a source.** For a Cell fed by an Expression or a Transformation, `.checksum` reports a result only if the source already has one. The call that does work is `.compute()`, exactly as `Buffer.get_checksum()` is the working counterpart of `Buffer.checksum`. Cell, Pin and Expression get no `get_checksum()`, because `.compute()` already fills that role.

**A Cell's own expression is cheap, so the getter evaluates it** whenever the input checksum is at hand. Resolution order:

1. nothing to apply (no path, no conversion, no validator) — the input checksum;
2. a hit in the process-local Expression cache;
3. a hit in the database;
4. the same evaluation already running in this process — wait for it;
5. the input buffer is local — evaluate now;
6. the input buffer is elsewhere — dispatch the evaluation and wait.

Otherwise `.checksum` is `None`: nothing is known, no remote is configured, or evaluation failed. Steps 2–6 are `Expression` placement and are specified in `contracts/expressions.md`; step 1 is the **dummy Expression** fast path, and on a standalone Cell it is implemented in the getter itself rather than being delegated, because `set_checksum` is instantaneous and `.checksum` must answer without entering the evaluator. That fast path also applies the empty-`bytes` → null canonicalization.

The second `.set_checksum` exception is that **on an unbound Cell `.checksum` is a computed property**, performing a synchronous evaluation of the underlying Expression. This does not change what `set_checksum` means.

**Wait on expressions, never on transformations.** A source Transformation that is still running gives `None`. A running source Expression may be waited on, unless it depends on a running Transformation. *Verified:* `_available_input_checksum` returns a bare `Checksum` unchanged, asks an `Expression` for `_available_result()` (which joins matching in-flight work but returns `None` when the ultimate input is an unfinished compute dependency), recurses into a source `Cell`'s own getter, and otherwise reads only the already-published `_result_checksum_internal()`.

**Bound and standalone deliberately differ.** A bound `.checksum` never waits: a node that is still computing reports `None` with state `waiting`, because the Context works in the background. A standalone Cell has nothing working in the background, so it waits.

**A running-loop refusal is not a failure.** Inside a running event loop a synchronous evaluation that would need the async bridge is refused (`RunningLoopRefusal`, see `contracts/expressions.md`). The standalone getter turns that into `None`, leaves `.exception` as `None` and the state as `waiting`, and dispatches nothing. It is a condition that resolves itself outside the loop, not an error to be cleared.

Reading `.checksum` expresses **user result interest** — `Expression.compute()` enables result holding, so the result checksum acquires a refholder claim for the lifetime of the reading handle. That is the checksum reference lifecycle (internal; see feature 9's own document, not these contracts).

### `.buffer` and `.value`

**Neither ever fingertips.** Both resolve through `Checksum.resolve()`: local cache, then hashserver, otherwise `CacheMissError`. `Transformation.run()` does fingertip, but it is an explicit method, not a property.

**A `CacheMissError` on the *result* checksum is raised to the caller and never becomes `.exception`.** The computation succeeded; whether its buffer can be reached depends on storage and on who is reading. The state stays `complete` and `.checksum` keeps its value. This is the one materialization failure that is deliberately not recorded — contrast a `CacheMissError` on an *input* buffer, which is an evaluation failure and does become `.exception`.

The deserialization pipeline is:

1. retrieve the result checksum, without questioning its validity;
2. validate it against the celltype using the result's HashType (`validate_deserializable_as`, checksum-level first, then again with the buffer in hand);
3. obtain the buffer, and for `.value` deserialize it.

Step 3 can still fail after step 2 passes, because HashType does not cover every future deserialization: `python`, `ipython` and `yaml` need text validation at parse time, which no classification of the bytes provides (`contracts/hashtype.md`). **A validation or deserialization failure is raised to the caller and also sets `.exception`**, and it is **deterministic**: the expression result stays stored, so `clear_exception()` followed by the same read produces the same failure again. *Verified:* a `RAW_TEXT` buffer that is not valid Python, under celltype `python`, gives a readable `.buffer` and a `.value` that raises `HashTypeValidationError`; after `clear_exception()` the checksum and the state return, and the next `.value` fails identically.

`.value` returns `Buffer.content` (raw `bytes`) for celltype `bytes`, and the parsed value otherwise.

## Failures

**What sets `.exception`:** an evaluation failure of the Cell's own expression — an impossible path, a forbidden or failing conversion, a `CacheMissError` on an *input* buffer, a HashType rejection — and a validation or deserialization failure while materializing. `NotImplementedError` from an unimplemented validator arrives the same way. **What does not:** a running-loop refusal, and a `CacheMissError` on the result checksum.

**A failure sticks.** The state is `failed`, `.checksum` reports `None` even where the result checksum is well-defined, and it stays that way until `clear_exception()`. There is **no automatic retry**: `clear_exception()` is the explicit retry, for when more caches are configured or the network is better. A deterministic failure simply reproduces; a transient one succeeds.

**A failure is remembered on the handle, never in the substrate.** This is the Cell-side counterpart of "Expression failures are not cached" (`contracts/expressions.md`):

- **standalone** — on the Cell (`_standalone_exception`), and reset whenever the recipe changes: a new input (`_replace_input_ref`), a new `celltype`, a new `path`, a new `validator` or `validator_language`;
- **bound** — on the Context node, where `clear_exception()` also drops the stored demand result, releases its lease and re-derives.

So **a new Cell built on the same recipe never inherits an old failure.** Keying a failure by expression identity in the substrate would have exactly the opposite effect, and would poison a checksum for every later reader.

The checksum shown by a `CacheMissError` is the one whose buffer was missing. In a chain of expressions, that can be an inner input rather than the Cell's own.

**`Cell.exception` holds a string**, as `Transformation.exception` does — one convention across Cell, Pin and Transformation. **This is contract ahead of code** (see *Implementation status*). Its consequence is worth stating now: a `CacheMissError`'s checksum then reaches the Cell as **prose only**, inside the message. The jobserver error envelope's split between `message` (for a person) and `checksum` (for code) therefore has no machine-readable arm on the Cell; `exc.args[0]` is a `Checksum` on the `CacheMissError` that `.value` *raises*, but not on the string that `.exception` *holds*.

Reading `.exception` on a standalone Cell evaluates the Cell's expression first (the getter calls `self.checksum`), so `.exception` is a read that can do cheap work — and, for a deterministic failure, re-derives the same failure after `clear_exception()`.

## Work: which calls compute and which never do

| Call | Does work? | Returns |
|---|---|---|
| `.source`, `.celltype`, `.input_celltype`, `.path` | no | configuration |
| `.checksum` | evaluates the Cell's **own** expression only; never starts a source | `Checksum` or `None` |
| `.buffer`, `.value` | resolve the result checksum; never fingertip | buffer / value, or raise |
| `.exception` | reads `.checksum` first | the stored failure or `None` |
| `build()` / `expression()` / `cell()` | no | an immutable `Expression` |
| `compute()` | **yes** — starts missing upstream work | the result `Checksum`, or `None` |
| `await compute_async()` / `await computation()` | **yes** | the result `Checksum`, or `None` |
| `run()` | **yes** — compute, then materialize | the value |
| `with_input()`, `as_celltype()`, `item()`, `slice()`, `with_validator()` | no | a new Cell |
| `clear_exception()`, `prune()` | no evaluation | `None` |

Notes:

- `compute()` is the explicit operation that starts missing upstream work; `.checksum` is not. `computation()` is `compute_async()` under its Context-facing name, and `await cell.computation()` is the asynchronous demand equivalent.
- A **standalone** `compute()` / `compute_async()` records a failure in `.exception` and returns `None` rather than raising; `run()` re-raises the stored failure. A **bound** `compute()` / `compute_async()` waits on a Context barrier, and `timeout=` is meaningful there (a barrier timeout raises `TimeoutError`; that is feature 10).
- `compute(input_ref)` / `run(input_ref)` / `build(input_ref)` accept a one-shot input override, type-checked like a constructor input, that does not mutate the Cell.
- All of these default to `execution="auto"`; placement is in `contracts/expressions.md`.
- The builder methods return **new** Cells and never mutate. On a **bound** Cell, `as_celltype()`, `with_validator()` and `with_input()` return a *standalone* Cell built on the bound cell's current Expression snapshot (`BoundCellBackend.derive`), whereas `item()` and `slice()` stay bound. Re-aiming a bound cell in place is a Context write, not a derivation.

## Projections

Attribute, item and slice reads navigate uniformly in both modes and each return a derived Cell carrying one more normalized path step:

```python
cell.foo   cell["foo"]   cell[0]   cell[1:4]
ctx.a.foo  ctx.a["foo"]  ctx.a[0]  ctx.a[1:4]
```

**API-name arbitration: normal Python lookup wins.** `__getattr__` projects only for a name that is not statically defined on `Cell` or its bases. A bound-only member whose getter raises `AttributeError` on a standalone Cell (`mount`, `block_reason`) must *not* fall through to a same-named projection, so `Cell.__getattr__` consults `_class_attribute` and re-raises rather than projecting. Names starting with `_` never project. Item access is the escape hatch: `ctx.a["value"]` and `ctx.a["run"]` are ordinary projections of data fields with those names. Cells have no `.pins` API, and `pins` is not reserved, so `ctx.a.pins` is an ordinary projection.

A projection of a plain `Cell` is a **`SubCell`**, a handle that is deliberately loud about being used as a value: `==`, ordering, `bool()`, `len()` and iteration all raise `ProjectionError` (which subclasses both `TypeError` and `AttributeError`). This catches the two mistakes that projection makes silent — a typo (`ctx.a.vlaue`) and a name that used to be API. One gap has no fix: `is None` compiles to a pointer comparison with no protocol to intercept, so `assert ctx.a.vlaue is not None` still passes.

**Projection depth is unlimited; connection targets are not.** A projection path may be arbitrarily deep wherever the underlying Expression path and source celltype support it. A **connection target** — a graph location that may receive a bound source — is the **root or one level below it, and nothing deeper**. A one-level target is a single point selection: a mapping key, an attribute name, or an integer sequence index. A slice may be read or value-updated but is never a connection target, because it denotes several positions. `ctx.a.b.c = ctx.x` raises `PathError: Cell connection targets are limited to one point component`.

A mapping-key connection can bootstrap an unwired cell as a mapping. An integer-index connection requires an existing compatible sequence; it never infers or grows a list, and the check happens when the value is assembled (`evaluate_cell` raises `TypeError("Integer Cell connection targets require an existing sequence")`).

**A sub-path write is an atomic read-modify-set of the root value**, not persistent path-overlay state and not a sub-value producer. One serialized transaction:

1. check that no incoming edge targets the root or an ancestor of the path;
2. read a **detached** copy of the current resolved root value;
3. apply ordinary Python container mutation along the path;
4. re-serialize and commit the changed aggregate as the root, preserving every unrelated one-level incoming edge.

It therefore **needs the current value to be materializable**. When the node is `waiting` or `computing` the write waits on a barrier and retries; otherwise a root with no checksum raises `ValueUnavailableError` — except that for a string/attribute path an *unwired* cell is treated as an empty mapping and missing intermediate keys are created as `{}`, so `ctx.a = Cell(); ctx.a.b.c = 12` yields `{"b": {"c": 12}}`. An explicitly stored `null` is not unwired and fails. The commit is optimistically concurrent (base checksum plus node revision) and retries up to 8 times before raising `ConcurrentUpdateError`.

Augmented assignment (`+=`, `-=`, `*=`, `/=`) reads the current resolved value and commits through the same single transaction. Because Python writes the result of `__iadd__` back to its owner, the returned handle must be treated as an inert same-endpoint reassignment and must not create a self-edge; a separately retained projection (`p = ctx.a.b.c; p += 1`) performs the same single transaction. `del ctx.a["b"]` deletes the key and, being a detaching delete, also removes any edge targeting that exact path.

Sub-path writes and augmented assignment are **bound-only**. Standalone, `cell["b"] = v` and `cell += 1` raise `TypeError`, and `cell.b = v` raises `AttributeError`: a standalone Cell has no controller to serialize the transaction.

## Cell-level joins

A **join** is a Cell with several producers — a root value and/or one-level sub-path connections:

```python
ctx.join = {}
ctx.join.left = ctx.left
ctx.join.right = ctx.right
```

**A join is plain local Python.** It is assembled directly in the Context, in-process: the root value is resolved, each connected sub-path source's value is resolved and assigned into a detached copy, and the aggregate is re-serialized. **There is no Transformation and no Expression behind it.** *Verified:* `Context._derive_cell` takes this branch when there are sub-path edges and no root edge, and hands `sidework.evaluate_cell` to `_demand`, which runs it in a worker thread; `evaluate_cell` calls `Checksum.resolve`, `_assign_path` and `checksum_for_value`, and nothing else.

Observable behaviour — stable, and the only thing promised:

- the value is correct, and it is the value of the assembled aggregate at the Cell's own `celltype`;
- it recomputes reactively when an upstream changes;
- reverting an upstream reproduces the checksum;
- a failed upstream leaves the join **blocked-by-error**, not failed; an unwired or blocked upstream leaves it blocked-by-unwired;
- **no transformation is observed** — not in the observation log, not in the transformation cache;
- the node goes straight from `waiting` to `complete` and is **never seen `computing`**, because `computing` belongs to the transformer path alone;
- `build()` on a join does **not** return a recipe: with no root edge to follow, it snapshots the join's *current* checksum as a dummy Expression.

**This is provisional.** A future re-implementation is to cache joins and evaluate them where the data is. Describe and depend on the observable behaviour above; **no join identity is promised** — the in-process memoization key is internal and per-Context, and nothing about a join is content-addressed beyond its result. (The design text in `context-internals-followup-design.md` that a join "may require a join `Transformation` followed by a projected `Expression`" is superseded.)

## Deep celltypes on a Cell

A Cell whose `celltype` or `input_celltype` is `deepcell`, `deepfolder` or `folder` is restricted, because an Expression's cost class must be a function of its identity tuple and never of the data behind the checksum: exactly **one string-item step**, and a short list of index-level conversions. The table, the member-celltype rules, the flatness requirement and the reasons are in `contracts/deep-celltypes.md`; `module` is not a deep celltype. Keys are opaque strings that routinely contain `/`, so the step usually has to be written in bracket form.

**Status: settled contract, not yet enforced.** Today a deep celltype on either side of an Expression is rejected by `HashTypeValidationError` before evaluation, so on a Cell only the dummy case works: `Cell("deepcell")` holding an index reads back its own checksum (the fast path does no evaluation), while `as_celltype("plain")` or any path step records a `HashTypeValidationError` in `.exception`.

## Implementation status and current limitations

Settled contract that the code does not yet implement, or implements differently. Where a design document and the code disagree, **the code wins** and the disagreement is listed here.

- **`.exception` is an exception object, not a string.** `execution_error` returns the exception with its traceback stripped, its `__cause__`/`__context__` cleared and a `failure_id` attached, and both `CellBase.exception` (standalone) and `node.exception` (bound) hand that object out. The string convention is settled and the code is to be changed. Two code sites depend on the object form and must change with it: standalone `.value` and `run()` `raise self._standalone_exception`.
- **Validators are deferred.** `validator` and `validator_language` are accepted by the constructor, by `with_validator()` and by `CellConfig`, and are excluded from Expression identity, but every evaluation entry point raises `NotImplementedError("Expression validators are not implemented yet")`, which a Cell records as `.exception` (wrapped as `WorkflowExecutionError`). The reject-only semantics are settled; nothing writes the database's validator columns. A validator must be a `Checksum` (or hex) — a validator given as source text fails with a `fromhex` error, not a useful message.
- **The join implementation is provisional** — see above. Caching and placement are to change; only the observable behaviour is contract.
- **Deep-celltype rules are unenforced** — see above.
- **A bound sub-path checksum or buffer write fails.** `ctx.a.b.checksum = cs`, `ctx.a.b.set_checksum(cs)`, `ctx.a.b.buffer = buf` and `ctx.a.b.set_buffer(buf)` all raise `TypeError: _edit() got an unexpected keyword argument 'input_celltype'`: `BoundCellBackend.write_checksum` always passes `input_celltype=` on, and `ingress.controller_method` forwards it into `_edit`, which has no such parameter. Root writes are unaffected, and the standalone path is unaffected. The contract is that all six writes work at a sub-path, with the checksum resolved to a value before the read-modify-set (`checksum_rhs`).
- **`.buffer` returns `None` where `.value` raises.** After a recorded evaluation failure the standalone `.checksum` getter short-circuits to `None`, so `.buffer` answers `None` while `.value` re-raises the stored exception. The contract is that both report the same failure the same way.
- **A bound public read does not validate, and does not record.** `Context._get_buffer` and `_get_value` validate against the celltype and record a failure on the node, but `ingress.controller_method` intercepts `_get_checksum` / `_get_buffer` / `_get_value` for every caller outside the controller and resolves the checksum directly. So a bound `.buffer` returns unvalidated bytes, and a bound `.value` whose deserialization fails raises without setting `.exception` — where the standalone path does both. The settled rule ("the same applies to bound and standalone Cells") is the standalone behaviour.
- **A bound read of a non-existent projection raises instead of reporting.** `ctx.p.nope.checksum`, `.value` and `.compute()` raise `ExpressionEvaluationError`, because the ingress read path catches only `KeyError` and `IndexError` while `_apply_step` wraps those in `ExpressionEvaluationError`. Standalone, the same projection returns `None` and records the failure in `.exception`. The standalone behaviour is the intended one.
- **Standalone `clear_exception()` does not clear the memoized result.** It clears only `_standalone_exception`; the next read re-evaluates. This is correct for a deterministic failure (it reproduces) and is why `.exception` appears unchanged immediately after `clear_exception()` — the getter has already re-derived it.
- **`context-internals-followup-design.md` is stale on two points**: it makes `.checksum`, `.buffer` and `.value` bound-only (superseded by the standalone-read contract above), and it makes a projection's `input_ref` its owning root endpoint (that meaning belongs to the private `_input_ref`; the public split is `.source` / `.checksum`).

## Non-goals

- **Execution.** A Cell has no code, no environment, no pins and no dunders. Anything that needs one is a Transformer; see `contracts/direct-delayed-and-transformation.md`.
- **Handle identity.** Handles are views. Two handles for one node are equal in effect and identical in nothing; nothing may be keyed on a handle's identity.
- **Deep connection targets.** One level below the root, by design: a deeper target would be a producer of a sub-value, which the read-modify-set model exists to avoid.
- **Persistent sub-path overlays.** A sub-path write is a transaction on the root value, not a stored per-path input.
- **Fingertipping from a property.** `.buffer` and `.value` never recompute a missing buffer; `contracts/scratch-witness-audit.md` defines fingertipping and where it does happen.
- **Value identity.** A Cell names a checksum, not a value. One value may have several checksums, and identity stays with the checksum (`contracts/identity-and-caching.md`); a Cell never re-serializes a result to normalize it, and `==` between two Cells is not a value comparison.
- **Failure caching.** A Cell failure lives on the handle for as long as the recipe does, and nowhere else.
- **Node state.** `.state` and `.block_reason` are node-lifecycle members shared with bound Transformers, and belong to feature 10's node state lifecycle; standalone, `.state` reports only `unwired`, `waiting`, `complete` and `failed`, and `.block_reason` is bound-only.
