# Cells (Contract)

**A Cell is a deferred Expression.** Where an `Expression` is a frozen recipe that has already been closed over its input, a `Cell` is the mutable builder for the same recipe — `(input, input_celltype, celltype)` plus a path and an optional validator — that can be re-aimed, retyped and re-read, and that snapshots into an immutable `Expression` on demand. Everything an Expression means (identity, cost class, placement, the error envelope, uncached failures) is in `contracts/expressions.md` and is not repeated here.

**A Cell is a deferred recipe; a recipe is not necessarily one Expression.** A standalone Cell is itself a **chain**: every projection and every `as_celltype` returns a **child** Cell edged to its parent, so a standalone builder has the same shape as the graph — each link carries *either* a path *or* a conversion, never both. A **bound** Cell wraps its incoming edge — several edges, for a join — whose source may be a concrete checksum, a named node or an anonymous one, and **one edge is no longer one Expression**: at build time a run of edges is walked and fused, so an Expression corresponds to a *maximal fusible run*, bounded by conversions and joins. The rules, and what falls inside a run, are in `contracts/expressions.md`, *Fusion*.

**Where this page sits.** Cells are layer 5 of the stack — celltypes and the type hierarchy (`contracts/celltypes-and-conversion.md`) → HashType (`contracts/hashtype.md`) → conversion (`contracts/celltypes-and-conversion.md`) → Expressions (`contracts/expressions.md`) → **Cells**. Nothing below layer 5 is re-derived here. Two rules from below are used constantly and are worth carrying in mind while reading this page: **project, then convert** (`contracts/expressions.md`, *Application order*), and the deep-celltype carve-out (`contracts/deep-celltypes.md`).

A Cell exists in one of two modes:

- **standalone** — the builder state is private to the Python object;
- **bound** — the builder state is owned by a workflow `Context` node, and the Cell is a *view* onto that node.

The two modes share one class, one read API and one write API. They differ in exactly three places: who owns the state, whether a read waits, and which operations exist at all (projection writes, mounts, `prune()` and `block_reason` are bound-only). Those differences are marked throughout.

Pins are the **sister class**, not a subclass: `Pin` and `Cell` share `CellBase`, which carries the value, type, evaluation and ownership API. Everything Pin-specific — routing to a Transformer, the pin null rules, the absence of projection, validators and mounts — is specified in `contracts/pins.md`. A Pin is never a valid Cell input; passing one raises `TypeError` pointing at `pin.source`.

Code locations:

| Concern | Module / symbol |
|---|---|
| Shared value/type/evaluation/ownership API | `seamless.cell_class.CellBase` |
| Builder, navigation, snapshots | `seamless.cell_class.Cell`; re-exported as `seamless.Cell` |
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

`target_celltype`, `input_ref` and `SubCell` are retired and raise `AttributeError` naming the replacement (`celltype`; `source` or `checksum`; and, for `SubCell`, `Cell` — there is no separate projection class, see *Projections*). Because attribute access on a Cell falls through to *projection*, `check_retired_name` runs first in `__getattr__`, `__setattr__` and `__delattr__`, so a retired name can never silently become a sub-path. Item navigation is unaffected: `ctx.a["input_ref"]` is an ordinary projection of a data field with that name.

**There is no old → new migration.** Cells reach `main` unreleased; the contract below is the contract, not a translation of an earlier one.

## Celltypes: `celltype` is the output

**`celltype` is the type of what the Cell produces** — its checksum, its `.buffer`, its `.value`, its `run()`. **`input_celltype` says how the input is read, and is read-only** (assigning it raises `AttributeError`; there is no setter in either mode).

On a Cell that carries a `path` — a projection — `contracts/expressions.md`'s **project, then convert** rule applies unchanged: `input_celltype` describes how the value at the Cell's *root* is read, the path is walked against that reading, and `celltype` converts only the value the path selected. Conversion never runs before the path; see *Projections*, below, for the worked example.

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

Retyping is refused on a mounted cell: `ValueError("Mounted celltype cannot change; unmount first")`. The celltype decides how the attached file's bytes are read and written, so it is frozen for as long as the attachment lives (`contracts/attachments.md`).

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

### Connecting: a path and a conversion may not share an edge

**A cell whose input arrives through a path has `celltype == input_celltype`.** An edge that both projects into its source *and* converts is statically ill-formed: a reader cannot tell which side of the path the conversion falls on, and the two readings differ (`contracts/expressions.md`, *Application order*). The wiring rule that keeps the invariant:

> Defining or redefining a cell's input with `=` is legal iff the new source carries **no path**, or the new source's celltype equals the cell's **`celltype`**.

- **"Path" means the *input* path** — the projection on the source side. A one-level **connection target** (`ctx.j["left"] = …`) is where the value lands, not how it is read, so it never makes an edge projecting. A heterogeneous join is therefore legal: `ctx.j["left"] = ctx.t` connects a `text` source into a `plain` join. `ctx.j["left"] = ctx.t[3]` is not, for exactly the reason `ctx.a = ctx.t[3]` is not.
- **The comparison is against `celltype`, never `input_celltype`.** A rewire discards the old `input_celltype`, so it has no standing — and wherever a path is involved the invariant makes the two coincide anyway. `S == celltype` is what lets a divergence *end*; nothing lets one *start* behind a projection.
- **A raw checksum / buffer / value write sets `input_celltype := celltype`**, so it carries neither a path nor a conversion and always satisfies the rule.
- **Retyping obeys the same invariant.** `ctx.a.celltype = …` is refused on a cell fed through a path; put the conversion on the source instead.

**Writing such an edge raises; having one imposed on you does not.** The refusal names both readings, because the whole problem is that the spelling does not choose between them:

```
ctx.a = ctx.b[3]
TypeError: would convert text -> plain behind a projection.
  ctx.a = ctx.b[3].as_celltype("plain")   # item 3 of the text (a character), as plain
  ctx.a = ctx.b.as_celltype("plain")[3]   # item 3 of the parsed list
```

Retyping a **source** that has projecting consumers is a valid request and is *not* refused. Each affected consumer becomes **`miswired`**, and its own dependents are `blocked` with reason `blocked-by-miswiring` (`contracts/node-state-lifecycle.md`). Only invalid requests raise; a valid request that invalidates someone else's wiring leaves a node condition.

*Contract ahead of code.* None of this is enforced today: `ctx.a = Cell("plain"); ctx.a = ctx.b[3]` with `b` of celltype `text` is accepted and answers `','`.

**A deep source is governed by the deep celltype's own rules, not by these.** Where the edge's source celltype is deep — `deepcell`, `deepfolder` or `folder` — the path-and-conversion rule above does not apply. A deep step is an **index lookup, not a structural projection**, and it necessarily changes the celltype, so a path and a conversion always travel together there. What is legal is the table in `contracts/deep-celltypes.md`: the zero-path conversions, and the exactly-one-string-item step whose result is `checksum` or the member's own celltype, and nothing else.

The **state is the same** — an edge outside that table is statically ill-formed and leaves the node `miswired`; only the criterion differs. And the carve-out is scoped to the edge whose *source* is deep: everything downstream of the resulting child checksum is ordinary wiring again.

**Elidable and elided.** A cell is **elidable** when its checksum is not needed — nothing wants it as a value, only as a step in a recipe. An **anonymous** cell, one produced mid-chain by `as_celltype` or by a projection and never bound to a name, is *always* elidable: there is no handle through which its checksum could ever be demanded. It is marked **elided**, and its checksum is never produced. A **named** cell is never elided — `ctx.mid.checksum` and `ctx.mid.value` can be asked for, so the node produces them and reaches `complete` like any other.

**Anonymous nodes are symbols.** An elided cell is a node in the durable graph — it must be, or the edges naming it would dangle and a saved graph would not round-trip — but it has no user-visible name: it is addressed only as the **source of an edge**, never as `ctx.<name>`, and it never appears in the Context's attribute namespace. Its symbol is **five hex characters derived from `(source, celltype, path)`**; on a collision the contenders are suffixed `-1`, `-2`, … in the order they were added, which is why the scheme is *mostly*, not purely, content-addressed.

Three consequences, all load-bearing:

- **The hash is over the recipe's shape, never over data.** `source` is the source *endpoint* — a node symbol or name plus a local path — not its checksum. A value change must never rename a node.
- **Symbols are stored, not recomputed on load.** The suffix depends on which contender arrived first, so recomputing symbols while reading a graph could hand `abcde` to a different node and silently re-point every edge that names it.
- **Only the suffix is order-dependent, and that is the right trade.** Suffixing by arrival keeps existing symbols stable when a node is added; ordering the contenders by their full hash instead would be construction-order-independent but would renumber live nodes on insertion. The price is that two isomorphic graphs built in different orders can differ in their symbols, so graph equality is not canonical.

Five hex characters is twenty bits, so a graph on the order of a thousand anonymous nodes is more likely than not to contain a collision. The suffixed form is an ordinary case that needs a test, not a defensive branch.

**The graph carries a symbol table.** Alongside its nodes and edges, a graph holds `symbol → (source, celltype, path)`, where `source` is a named node's name or another symbol. That table **is** the anonymous cell's definition — an entry says *take `source`, apply `path`, at `celltype`* — and an edge referring to a symbol resolves through it:

```
ctx.a = ctx.b[3].as_celltype("plain")     sym → (b, text, "[3]")   edge (sym, no path) → a(plain)
ctx.a = ctx.b.as_celltype("plain")[3]     sym → (b, plain, "")    edge (sym, path [3]) → a(plain)
```

The two spellings are the same recipe after fusion and differ only here, which is the whole reason the table is durable: without it, the first spelling would reload indistinguishable from `ctx.a = ctx.b[3]` and come back **`miswired`**.

- **The wiring invariant holds on table entries too**, and `set_graph` checks them exactly as it checks edges — an entry carrying both a path and a conversion is ill-formed. Chains alternate by construction, so a legal builder never writes one.
- **An entry is garbage when no edge and no other entry names its symbol**, and is removed then. Nothing else can reach it.
- **The table resolves the namespace question.** An edge's source is *either* a node path *or* a symbol, and which one is part of the reference, so a user cell named `abcde` and the symbol `abcde` never collide and no sigil has to leak into anything user-visible.

This is a **graph format change**: the format is at `0.4`, and a graph written with a symbol table cannot be read by a loader that does not know about one.

**Fusion is independent of elision, and is always done.** Chains of Expressions collapse as far as the codebook allows — path into path, and a checksum-preserving conversion into a following path — under the rules in `contracts/expressions.md`, *Fusion*. It applies to named and anonymous intermediates alike, so these two build the same fused recipe:

```python
ctx.a = ctx.b.as_celltype("plain")[3]                                    # anonymous, elided
ctx.mid = Cell("plain"); ctx.mid = ctx.b; ctx.a = ctx.mid[3]             # named, not elided
```

— which is the point of the ordering rule one level up: where the conversion is written, and whether the intermediate was given a name, must not change what the recipe computes.

What fusion does **not** do is remove a named intermediate's own work: `ctx.mid` still produces its checksum, because something may read it. What it removes is the *consumer's* dependency on that intermediate's **buffer** — the fused chain is evaluated where the root's data is and yields only what the path selected, and where the intermediate is `scratch` its buffer need never exist at all.

**Elidability and miswiring are re-detected together**, whenever a celltype changes or an edge is added or removed — exactly the events that can create or destroy a conversion. Same trigger set, same local comparison of a source's `celltype` against the cell's, so one pass over the affected cone.

*Contract ahead of code.* Neither elision nor fusion exists today: a bound projection is built as `Expression(expression, path=…)` and nothing collapses, and an anonymous cell has no representation at all — binding one raises `TypeError: Cannot bind a Cell whose input_ref is Expression`.

**`input_celltype` uses the same resolution.** It reports the celltype of whatever `.source` resolves to at that path — the one-level edge targeting the path if there is one, otherwise the nearest enclosing source. The two members are **one lookup**: `.source` returns the endpoint, `input_celltype` returns its celltype. So on a `plain` join fed at `left` by a `text` cell, `ctx.join.left.source` is `ctx.left` and `ctx.join.left.input_celltype` is `text`; on a read projection with no edge of its own, both fall back to the enclosing source, and `input_celltype` is the root's — which is what that projection needs, since its path is applied to the root's value at the root's celltype.

*Contract ahead of code.* `BoundCellBackend.input_celltype` drops `local_path` today (`builder_state.py:64-69`), so a connection target reports the root's celltype where it should report its producer's. Read projections are unaffected.

**A projection's own `celltype` is its parent's.** A child carries the parent's `celltype` forward unless `as_celltype` changes it, so `ctx.join.left.celltype` is the join's. This is what the wiring rule above compares a source against at a one-level target: `ctx.j["left"] = ctx.t[3]` with a `text` source and a `plain` join is `text` against `plain`, hence refused.

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

**Both sides of a property write speak `celltype`.** Every spelling in the declare family is expressed in the Cell's `celltype` *and records `input_celltype = celltype`*: `.value =` serializes with it, `.buffer =` is validated against it, `.checksum =` declares it. None of the three can name a different input celltype — there is no argument to pass one. So at the root a property write is its own inverse at the moment it happens: `ctx.a.checksum = cs` leaves `ctx.a.checksum == cs`, exactly as `ctx.a.value = v` leaves `ctx.a.value == v`. The conversion a Cell can perform is the identity right after the write; it becomes non-trivial only later. *Verified:* the `CellBase.checksum` setter calls `_write_checksum(value, detach=True)` with `input_celltype=None`, and `_replace_input_ref` resolves that through `_typed_input_celltype(input_ref) or input_celltype or self.celltype` to `self.celltype`.

Exactly three acts make `input_celltype` differ from `celltype`, and each of them names the other celltype **explicitly**:

- the method form, `set_checksum(cs, input_celltype=…)`;
- the constructor, `Cell(ct, checksum=cs, input_celltype=…)`;
- a later `cell.celltype = …`, which retypes and therefore converts (above).

Reading `.checksum` after one of those reports the converted output rather than the checksum that was declared. That is retyping doing what retyping is specified to do, not an asymmetry between the getter and the setter. Two further cases break the round-trip without any of the three, and both are stated elsewhere: a handle that carries a `path` declares the input *before* the path, so the read is the projection of what was written — coherent, not a bug, because the path is recipe, not value; and on a `bytes` cell the empty-buffer checksum canonicalizes to null on the way out (*Null and `None`*).

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

A mounted cell refuses to be cleared: `AuthorityError("Cannot clear a mounted cell; unmount first")`, and a sensing mount refuses an incoming edge, at the root or at any sub-path (`"Sensing mount is the producer; unmount first"`) — a sensing attachment *is* the node's producer. Both refusals, and the sense that writes through this same path, are in `contracts/attachments.md`.

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

**Wait on expressions, never on transformations.** A source Transformation that is still running gives `None`. A running source Expression may be waited on, unless it depends on a running Transformation. *Verified:* `_available_input_checksum` returns a bare `Checksum` unchanged, asks an `Expression` for `_available_result()` (which joins matching in-flight work but returns `None` when the ultimate input is an unfinished compute dependency), recurses into a source `Cell`'s own getter, and otherwise reads only the already-recorded `_result_checksum_internal()`.

**Bound and standalone deliberately differ.** A bound `.checksum` never waits: a node that is still computing reports `None` with state `waiting`, because the Context works in the background. A standalone Cell has nothing working in the background, so it waits.

**A running-loop refusal is not a failure.** Inside a running event loop a synchronous evaluation that would need the async bridge is refused (`RunningLoopRefusal`, see `contracts/expressions.md`). The standalone getter turns that into `None`, leaves `.exception` as `None` and the state as `waiting`, and dispatches nothing. It is a condition that resolves itself outside the loop, not an error to be cleared.

Reading `.checksum` expresses **user result interest** — `Expression.compute()` enables result holding, so the result checksum acquires a refholder claim for the lifetime of the reading handle. That is the checksum reference lifecycle, an internal contract: `contracts/internal/checksum-reference-lifecycle.md`. **The Expression-level claim is scratch-neutral**: it protects the result from eviction and does not write the buffer anywhere, so reading a property can never defeat a scratch decision. A Cell is one of the owners that *can* publish, when it is non-scratch and holds a buffer (`contracts/expressions.md`, *Results and caching*).

### `.buffer` and `.value`

**Neither ever fingertips.** Both resolve through `Checksum.resolve()`: local cache, then hashserver, otherwise `CacheMissError`. `Transformation.run()` does fingertip, but it is an explicit method, not a property.

**A result checksum does not imply a result buffer.** The checksum may have been recorded without any buffer being produced in this process, and a buffer that did exist may have been evicted or never stored at all (`scratch`). So a `.checksum` that answers guarantees nothing about `.buffer` or `.value`; `fingertip()` is the only guaranteed route to the bytes (`contracts/expressions.md`, *Results and caching*).

**`Cell.fingertip()` is the Cell-level explicit entry point**, and it is the only place where a fingertip acquires an owner. A fingertip site otherwise holds a bare checksum, with no owner and no scratch intent, so it cannot decide whether the recovered buffer should persist. Through a Cell it can: **on a non-scratch Cell the recovered result is persisted, because the Cell increfs it; on a scratch Cell it is not.**

**It is `Cell.checksum.fingertip()`, with one deliberate difference: it never forces `.checksum`.** The standalone getter's synchronous evaluation is not triggered; `fingertip()` works from the result checksum already in hand. Four consequences:

- **No result checksum, no work.** If `.checksum` is `None` — nothing computed yet, a source still running, a recorded failure — `fingertip()` is a **no-op returning `None`**. Because it never starts the Cell's own evaluation, it is equally safe on a bound Cell, where `.checksum` reports `None` while the node is still `waiting`.
- **It returns what `Checksum.fingertip()` returns**: the recovered **buffer**. Not a checksum — the checksum was the input to the call, not its answer.
- **It never sets `.exception`.** A fingertip is a materialization, and a materialization failure on a *result* checksum is raised to the caller and not recorded (above). That holds even though the chain may execute transformations on the way: their failures belong to their own nodes, not to this handle.
- **`Pin.fingertip()` exists and means the same thing** (`contracts/pins.md`).

The recovery runs **entirely in this process** either way (`contracts/scratch-witness-audit.md`, *Where a fingertip chain runs*), so it assumes this process can execute the chain's transformations — and **the chain itself writes nothing to the hashserver**. What persists a non-scratch Cell's recovered result is the Cell's own incref, never the walk. *Contract ahead of code:* neither `Cell.fingertip()` nor `Pin.fingertip()` exists; the only entry point today is `Checksum.fingertip()`.

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
| `fingertip()` | **yes** — resolve, else recompute from provenance, locally; but never starts the Cell's **own** evaluation | the recovered buffer, or `None` when there is no result checksum (contract ahead of code) |
| `clear_exception()`, `prune()` | no evaluation | `None` |

Notes:

- `compute()` is the explicit operation that starts missing upstream work; `.checksum` is not. `computation()` is `compute_async()` under its Context-facing name, and `await cell.computation()` is the asynchronous demand equivalent.
- A **standalone** `compute()` / `compute_async()` records a failure in `.exception` and returns `None` rather than raising; `run()` re-raises the stored failure. A **bound** `compute()` / `compute_async()` waits on a Context barrier, and `timeout=` is meaningful there (a barrier timeout raises `TimeoutError`; that is feature 10).
- `compute(input_ref)` / `run(input_ref)` / `build(input_ref)` accept a one-shot input override, type-checked like a constructor input, that does not mutate the Cell. The **parameter** is still spelled `input_ref` (as it is on `Expression`); only the retired *attribute* of that name raises.
- All of these default to `execution="auto"`; placement is in `contracts/expressions.md`.
- The builder methods return **new** Cells and never mutate. On a **bound** Cell, `as_celltype()`, `with_validator()` and `with_input()` return a *standalone* Cell built on the bound cell's current Expression snapshot (`BoundCellBackend.derive`), whereas `item()` and `slice()` stay bound. Re-aiming a bound cell in place is a Context write, not a derivation.

## Projections

Attribute, item and slice reads navigate uniformly in both modes and each return a derived Cell carrying one more normalized path step:

```python
cell.foo   cell["foo"]   cell[0]   cell[1:4]
ctx.a.foo  ctx.a["foo"]  ctx.a[0]  ctx.a[1:4]
```

**A projection selects within the value read at `input_celltype`; `celltype` then converts only what the projection selected — never the whole value before the path is walked.** This is the Cell-side statement of Expression evaluation order; `contracts/expressions.md`'s *Application order* is the rule's owner, together with the reason the order is not cosmetic and a worked example in Expression terms.

For example, a `Cell("text")` holding `[10, 20, 30, 40]` as text. `cell[3].as_celltype("plain")` selects item `3` of the **text** — the character `','` — and renders that as `plain`. `cell.as_celltype("plain")[3]` converts the text to `plain` **first**, closing that Expression, and then selects item `3` of the resulting **list** — the integer `40`. The two spellings are different recipes, and each means what it reads as: `as_celltype` fixes the celltype from that point in the chain onward, so a path written after it walks the converted value, and a Cell is therefore a *chain* of Expressions wherever a conversion is followed by a projection.

*Contract ahead of code.* Today both spellings build a single Expression at `input_celltype='text'`, so both answer `','`. Standalone, `Cell._derive` updates the independent `path` and `celltype` fields and never touches `input_celltype`; bound, `BoundCellBackend.derive` detaches by building the root as a source and overwriting only the output celltype. The rule above is the contract: appending a path step to a Cell whose `input_celltype` and `celltype` differ must **close** that Expression and re-base the step on its result; appending to a Cell with no pending conversion extends the path as it does today.

**Projection and `as_celltype` both return a child cell edged to the parent.** `cell[3]` is a child Cell whose *source* is `cell`, carrying the path; `cell.as_celltype(ct)` is a child Cell whose source is `cell`, carrying the conversion. `Cell.__init__` takes **no `path` argument** — a path is only ever added by projecting. Three things follow:

- **A path is only ever added by projecting**, so the builder stays a chain. The constructor was the one route that produced a path-carrying Cell without a parent link, and its `.checksum` round-trip could not work: `set_checksum` sets the *pre-path* input, so what went in never came back out.
- **The wiring invariant holds standalone too.** `cell[3].as_celltype("plain")` is two cells and two links, not one cell carrying both; so **binding is a move, not a decomposition** — the chain that goes into the Context already has the shape the graph requires, one symbol-table entry per anonymous link.
- **`.source` on a standalone projection answers the parent handle**, where today `Cell._derive` copies the parent's own input and so reports the *grand*parent. The new reading is the one the name promises.

This costs nothing at evaluation time: a run of path links fuses back into one Expression (`contracts/expressions.md`, *Fusion*), which is why fusion has to be unconditional rather than an optimization.

**API-name arbitration: normal Python lookup wins.** `__getattr__` projects only for a name that is not statically defined on `Cell` or its bases. A bound-only member whose getter raises `AttributeError` on a standalone Cell (`mount`, `block_reason`) must *not* fall through to a same-named projection, so `Cell.__getattr__` consults `_class_attribute` and re-raises rather than projecting. Names starting with `_` never project. Item access is the escape hatch: `ctx.a["value"]` and `ctx.a["run"]` are ordinary projections of data fields with those names. Cells have no `.pins` API, and `pins` is not reserved, so `ctx.a.pins` is an ordinary projection.

**A Cell is a handle, and says so.** `==`, ordering, `bool()`, `len()` and iteration raise `ProjectionError` — which subclasses both `TypeError` and `AttributeError` — on **every** Cell, and on every Pin, which shares `CellBase`. Handle identity carries no meaning, so comparing a Cell to a value, or to another Cell, is always a mistake whether or not a path is involved. **There is no separate projection class**: the guard lives on `CellBase`, and the message adapts to the object — on a Cell carrying a path it names the path and suggests the misspelling that attribute projection makes silent (`ctx.a.vlaue`), and on one without a path it says to read `.value`. One gap has no fix: `is None` compiles to a pointer comparison with no protocol to intercept, so `assert ctx.a.vlaue is not None` still passes.

**Projection depth is unlimited; connection targets are not.** A projection path may be arbitrarily deep wherever the underlying Expression path and source celltype support it. A **connection target** — a graph location that may receive a bound source — is the **root or one level below it, and nothing deeper**. A one-level target is a single point selection: a mapping key, an attribute name, or an integer sequence index. A slice may be read or value-updated but is never a connection target, because it denotes several positions. `ctx.a.b.c = ctx.x` raises `PathError: Cell connection targets are limited to one point component`.

A mapping-key connection can bootstrap an unwired cell as a mapping. An integer-index connection requires an existing compatible sequence; it never infers or grows a list, and the check happens when the value is assembled (`evaluate_cell` raises `TypeError("Integer Cell connection targets require an existing sequence")`).

**A sub-path write is an atomic read-modify-set of the root value**, not persistent path-overlay state and not a sub-value producer. One serialized transaction:

1. check that no incoming edge targets the root or an ancestor of the path;
2. read a **detached** copy of the current resolved root value;
3. apply ordinary Python container mutation along the path;
4. re-serialize and commit the changed aggregate as the root, preserving every unrelated one-level incoming edge.

It therefore **needs the current value to be materializable**. When the node is `waiting` the write waits on a barrier and retries (a sub-path write only ever targets a cell node, and a cell node is never `computing`); otherwise a root with no checksum raises `ValueUnavailableError` — except that for a string/attribute path an *unwired* cell is treated as an empty mapping and missing intermediate keys are created as `{}`, so `ctx.a = Cell(); ctx.a.b.c = 12` yields `{"b": {"c": 12}}`. An explicitly stored `null` is not unwired and fails. The commit is optimistically concurrent (base checksum plus node revision) and retries up to 8 times before raising `ConcurrentUpdateError`.

Augmented assignment (`+=`, `-=`, `*=`, `/=`) reads the current resolved value and commits through the same single transaction. Because Python writes the result of `__iadd__` back to its owner, the returned handle must be treated as an inert same-endpoint reassignment and must not create a self-edge; a separately retained projection (`p = ctx.a.b.c; p += 1`) performs the same single transaction. `del ctx.a["b"]` deletes the key and, being a detaching delete, also removes any edge targeting that exact path.

Sub-path writes and augmented assignment are **bound-only**. Standalone, `cell["b"] = v` and `cell += 1` raise `TypeError`, and `cell.b = v` raises `AttributeError`: a standalone Cell has no controller to serialize the transaction.

The same absence of a controller means a standalone projection's *property* writes — `cell.b.checksum = cs`, `cell.b.set_checksum(cs)`, `cell.b.value = v`, `cell.b.buffer = buf` — are contractually errors for the identical reason, but today they do not raise; see *Implementation status*.

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

**`.value` on a deep Cell is the index, and that part is contract.** Requesting the value of a deep checksum yields its index at every layer, with each member presented as a `Checksum` object — `{key: Checksum}` (`contracts/deep-celltypes.md`, *What a deep buffer is*). `.value` resolves through `Checksum.resolve(celltype)` → `Buffer.get_value(celltype)`, which maps `deepcell`/`deepfolder`/`folder` to `plain` (`Buffer._map_celltype`) before parsing, and a flat index is valid `plain` JSON. Nothing is resolved and no member buffer is touched: wrapping a hex in a `Checksum` is typing, not resolution. *Contract ahead of code:* today the hexes arrive unwrapped.

**`.buffer` disagreeing with it is the defect.** On the same Cell `.buffer` raises `HashTypeValidationError` (recorded in `.exception`), because `CellBase.buffer` validates the checksum against the **unmapped** celltype before resolving. This is a second, distinct `.buffer`/`.value` asymmetry from the one in *Implementation status* — that one is `None` versus a re-raised stored failure after an evaluation failure; this one is a raise versus a correct read.

Because every typed route raises today, indexing that dict yourself is also **the only way to reach a deep child's checksum** at the moment. The read is sound — it is the value rule — but the code hands back raw hex strings where the contract presents `Checksum` objects, so the member typing is left to you; the typed route to a single child is the one-step path in `contracts/deep-celltypes.md`, *Paths*, once the rules are enforced. **Ruled (2026-09-21): the anomaly is fixed in the code first — the unvalidated fast path and the `.buffer`/`.value` split — and the interim passages come out of these pages afterwards**, when the one-step path makes them unnecessary. Both halves are tracked in `cells-and-expressions-feature-1-4.md`.

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
- **On a bound projection, `input_celltype` does not follow the path while `.source` does.** `BoundCellBackend.input_celltype` (`seamless-workflow/seamless_workflow/builder_state.py:64-69`) calls `Context._effective_input_celltype(self.node_path)` and drops `self.local_path`, whereas `BoundCellBackend.source` passes `local_path` into `_public_cell_source`. So for a join `ctx.join.left = ctx.left`, `ctx.join.left.source` reports `ctx.left` but `ctx.join.left.input_celltype` reports the **root's** input celltype. **This is a known bug, not an intended divergence**: the two members are one lookup, as stated in *The input* above, and `local_path` is to be passed through. Until it is, do not rely on `input_celltype` at a bound projection.
- **`Cell.fingertip()` does not exist**, and neither does `Pin.fingertip()`. The only entry point is `Checksum.fingertip()`, which holds a bare checksum and therefore cannot express the ownership rule above. Related, and worse: Expression evaluation currently writes its result buffer to the hashserver on every evaluation, so a fingertip today re-adds exactly the buffer that scratch or eviction excluded (`contracts/expressions.md`, *Status: publication and fingertipping*).
- **A standalone projection's property writes are silently lost.** `cell.b.checksum = cs`, `cell.b.set_checksum(cs)`, `cell.b.value = v` and `cell.b.buffer = buf` do not raise, unlike `cell.b = v` (`AttributeError`) and `cell["b"] = v` (`TypeError`). `cell.b` returns a fresh, throwaway handle (`Cell.item`) whose setters are `CellBase`'s ordinary ones, so the write mutates that handle's own private state and the handle is then discarded. (In the code today that handle is a `SubCell`, which overrides only the comparison, truthiness and iteration dunders at `cell_class.py:688-750`; the contract retires the class and puts those dunders on `CellBase`, which does not by itself fix this.) *Verified against code (2026-09-20):* `Cell.item` builds the projection through `_derive`, which for a standalone Cell constructs a brand-new instance rather than returning a view; `CellBase.checksum`'s setter (`_write_checksum` → `_replace_input_ref`) runs against that instance. The contract is that these four spellings raise the same way item/attribute assignment already does.

## Non-goals

- **Execution.** A Cell has no code, no environment, no pins and no dunders. Anything that needs one is a Transformer; see `contracts/direct-delayed-and-transformation.md`.
- **Handle identity.** Handles are views. Two handles for one node are equal in effect and identical in nothing; nothing may be keyed on a handle's identity.
- **Deep connection targets.** One level below the root, by design: a deeper target would be a producer of a sub-value, which the read-modify-set model exists to avoid.
- **Persistent sub-path overlays.** A sub-path write is a transaction on the root value, not a stored per-path input.
- **Fingertipping from a property.** `.buffer` and `.value` never recompute a missing buffer. `fingertip()` is the explicit method; `contracts/scratch-witness-audit.md` defines fingertipping and where it happens.
- **Value identity.** A Cell names a checksum, not a value. One value may have several checksums, and identity stays with the checksum (`contracts/identity-and-caching.md`); a Cell never re-serializes a result to normalize it, and `==` between two Cells is not a value comparison.
- **Failure caching.** A Cell failure lives on the handle for as long as the recipe does, and nowhere else.
- **Node state.** `.state` and `.block_reason` are node-lifecycle members shared with bound Transformers, and belong to feature 10's node state lifecycle; standalone, `.state` reports only `unwired`, `waiting`, `complete` and `failed`, and `.block_reason` is bound-only.
