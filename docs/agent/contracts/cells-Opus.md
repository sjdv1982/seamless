# Cells (Contract)

**A Cell is a deferred Expression.** Where an `Expression` is a frozen recipe that has already been closed over its input, a `Cell` is the mutable builder for the same recipe — `(input, input_celltype, celltype)` plus a path and an optional validator — that can be re-aimed, retyped and re-read, and that snapshots into an immutable `Expression` on demand. Everything an Expression means (identity, cost class, placement, the error envelope, uncached failures) is in `contracts/expressions.md` and is not repeated here.

**A Cell is a deferred recipe; a recipe is not necessarily one Expression.** A standalone Cell is itself a **chain**: every projection and every `as_celltype` returns a **child** Cell linked to its parent, so a standalone builder has the same shape as the graph — each link carries *either* a path *or* a conversion, never both. (A *link* is not an edge: edges exist only in a workflow, and standalone the link is simply the input reference the child holds to its parent — *Connecting*.) A **bound** Cell wraps its incoming edge — several edges, for a join — whose source may be a concrete checksum, a named node or an anonymous one, and **one edge is no longer one Expression**: at build time a run of edges is walked and fused, so an Expression corresponds to a *maximal fusible run*, bounded by conversions and joins. The rules, and what falls inside a run, are in `contracts/expressions.md`, *Fusion*. Bound, a projection (`ctx.a[3]`, `ctx.a.b`) or an `as_celltype` returns an **anonymous** cell handle: a handle to a Context node that has a symbol and no name, and that reads like an unbound Cell over its parent's checksum (*Connecting*; *Reads*, *Anonymous and projection handles*).

**Where this page sits.** Cells are layer 5 of the stack — celltypes and the type hierarchy (`contracts/celltypes-and-conversion.md`) → HashType (`contracts/hashtype.md`) → conversion (`contracts/celltypes-and-conversion.md`) → Expressions (`contracts/expressions.md`) → **Cells**. Nothing below layer 5 is re-derived here. Two rules from below are used constantly and are worth carrying in mind while reading this page: **project, then convert** (`contracts/expressions.md`, *Application order*), and the deep-celltype carve-out (`contracts/deep-celltypes.md`).

A Cell exists in one of two modes:

- **standalone** — the builder state is private to the Python object;
- **bound** — the builder state is owned by a workflow `Context` node, and the Cell is a *view* onto that node.

The two modes share one class, one read API and one write API. They differ in exactly three places: who owns the state, whether a read waits or evaluates, and which operations exist at all (projection writes, mounts, `prune()` and `block_reason` are bound-only). Those differences are marked throughout. A handle to an anonymous bound cell — a bound projection or `as_celltype` — is bound in ownership and unbound in how it reads (*Reads*, *Anonymous and projection handles*).

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
     validator=None, validator_language=None)
```

- The positional argument is the **produced** celltype.
- `checksum=` and `source=` are **mutually exclusive** (`TypeError` otherwise). `source=` takes a typed reference — a `Cell`, an `Expression`, or any object exposing the duck-typed `_workflow_endpoint` / `_compute_dependency` protocol (a `Transformation`, a bound endpoint). A bare `Checksum` passed as `source=` raises `TypeError` naming `checksum=`; a `Pin` raises `TypeError` naming `pin.source`.
- `celltype` defaults to a typed source's `celltype`, else `"mixed"`. An unsupported name raises `TypeError` listing the supported celltypes (see `contracts/celltypes-and-conversion.md`).
- `input_celltype=` is a **declaration**, legal only alongside a bare checksum. With a typed source it must match, or construction raises `ValueError`.
- `path=` is not a constructor parameter; passing it raises `TypeError`. Add paths by projecting. The `.path` property is read-only (see *Work*).
- `validator` / `validator_language` are accepted and stored, but validators are **not implemented** (below).

`build()` — also spelled `cell.expression()` and `cell()` — freezes the current builder state into an `Expression`. That Expression is the contract object; the Cell is the handle that produced it.

### Binding

Assigning a Cell into a Context binds it: `ctx.a = Cell("int")` moves the builder state into a Context node, and every later `ctx.a` returns a **fresh** `Cell` whose state lives entirely in `BoundCellBackend` (`Cell._from_backend`). Consequences:

- **Handle identity carries no meaning.** `ctx.a is not ctx.a`; two handles for one node are interchangeable, and a handle for a deleted node raises `StaleWorkflowHandleError` on its next use.
- A bound Cell is a view, not a copy: the Context runtime holds nodes, Expressions and Transformations, never Cells.
- A standalone Cell is never implicitly bound. `Cell(source=ctx.a)` captures the bound endpoint of a **named** node as its input (`_capture_workflow_source`), which is a reference to the node, not a binding of the new Cell.
- **A handle to an anonymous cell belongs to its Context.** Passing one as `Cell(source=…)` — `Cell(source=ctx.a[3])`, `Cell(source=ctx.b.as_celltype("plain"))` — or assigning one into a *different* Context raises `TypeError` naming the reason. Assign it into its own Context instead (*Connecting*, *Assigning an anonymous handle*). *Contract ahead of code:* today a bound projection handle is captured like any endpoint, and a cross-Context assignment raises `DependencyError("Cross-top-level dependencies are not supported")`.

### Retired names

`target_celltype` and `input_ref` are retired and raise `AttributeError` naming the replacement (`celltype`; `source` or `checksum`). Because attribute access on a Cell falls through to *projection*, `check_retired_name` runs first in `__getattr__`, `__setattr__` and `__delattr__`, so a retired name can never silently become a sub-path. Item navigation is unaffected: `ctx.a["input_ref"]` is an ordinary projection of a data field with that name.

**There is no `SubCell`.** Use `Cell` for projections. The class is removed, not kept as a retirement shim: there is no `seamless.SubCell` and no `__all__` entry for it. The handle guards it used to carry live on `CellBase` (see *Projections*).

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
- **Copy once, at creation.** A *new* cell built from a typed source copies that source's `celltype` once: `ctx.a = ctx.b` creates `a` with `b.celltype`. An *existing* cell keeps its own output type when rewired — `ctx.existing = ctx.typed` leaves `existing.celltype` alone and converts into it. The same holds for an anonymous handle: assigned to a new name it becomes that node and keeps its own `celltype`; assigned to an existing name it feeds an edge that converts into the existing cell's `celltype` (*Connecting*, *Assigning an anonymous handle*).
- **To correct a wrong declaration, declare the input again.** There is no setter; `set_checksum(cs, input_celltype=…)` is the spelling.

Retyping is refused on a mounted cell, whatever the mount mode: `ValueError("Mounted celltype cannot change; unmount first")`. The celltype decides how the attached file's bytes are read and written, so it is frozen for as long as the attachment lives (`contracts/attachments.md`).

## The input: `.source` versus `.checksum`

The configured input is public as two read-only-in-meaning names that used to be one union:

| Public | Meaning |
|---|---|
| `.source` | the **derivation** arm, read-only: the upstream handle (bound) or the Cell / Expression / Transformation a standalone builder is built on; `None` when the node holds its own value |
| `.checksum` | the **value** arm: the current produced checksum. As a *write* it declares a literal input, and `None` clears (at the root; clearing a sub-path is refused, *Null and `None`*) |

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

**On a projection, `.source` answers for that path.** It is the one-level edge targeting that path if there is one, otherwise the nearest enclosing source, otherwise `None`; deeper paths, which can never carry an edge, walk up the same way. A cell with a literal root and a connection at `b` therefore reports `ctx.a.source is None` and `ctx.a.b.source` as the upstream — otherwise sub-path edges would be visible only through `get_graph()`. *Verified:* `Context._public_cell_source` walks `local[:length]` downwards from the full path to the root.

**Bound and standalone projections answer `.source` differently, deliberately.** A **standalone** projection is a child link, and its `.source` is its **parent** Cell (*Projections*). A **bound** projection handle answers with the **resolved edge** above — the edge targeting that path, else the nearest enclosing source, else `None` — never with the parent handle, even though the handle's own recipe is evaluated over the parent's checksum (*Reads*, *Anonymous and projection handles*). The bound reading is the one that makes sub-path edges and join members visible from a handle; `input_celltype` follows it (below).

### Connecting: a path and a conversion may not share one link

**An edge exists only in a workflow.** Bound, a cell's input is an **edge** in the durable graph, which the Context can see, check, mark and save. Standalone there is no graph and there are no edges: a cell's input is a **link** — the input reference the Cell holds to the Cell, Expression or checksum above it. The invariant below is a property of the link and holds in both modes; what differs is the spelling that creates one, and what a bad one does. Where this section says *edge*, it is speaking about the bound case specifically.

**A cell whose input arrives through a path has `celltype == input_celltype`.** A link may not both project into its source *and* convert. The wiring rule that keeps the invariant:

> Defining or redefining a cell's input is legal iff the new source carries **no path**, or the new source's celltype equals the cell's **`celltype`**.

Bound, that is `ctx.a = …`; standalone, it is `Cell(source=…)` and `with_input()`, since a standalone Cell cannot be rewired in place (*`.set()` and `.value =` take values only*). It is also the rule behind the builder's shape: `cell[3]` and `cell.as_celltype(ct)` each produce a **separate** link rather than one link carrying both (*Projections*).

**The Expression convention does not lift to a chain.** Inside one Expression the order is fixed — read, project, convert — so `contracts/expressions.md`'s **project, then convert** settles what a single Expression means. Seamless deliberately declines to impose that order on a builder. **Each link is project *or* convert, never both**, and a chain applies its links in the order they were written (*Projections*: syntax order is application order). A Cell can of course do both — as two links — which is why `cell[3].as_celltype("plain")` and `cell.as_celltype("plain")[3]` are two different recipes rather than two spellings of one; a link carrying both would have to pick an order silently, which is exactly what the refusal below prevents. And the Cell you hold is a deferred **recipe**, not one deferred Expression: *fusion* (below) collapses a run of links into a single Expression wherever the codebook allows — **always, not as an optimization** — and where the codebook does not allow it, the recipe stays several Expressions.

- **"Path" means the *input* path** — the projection on the source side. A one-level **connection target** (`ctx.j["left"] = …`), which exists only in a workflow, is where the value lands, not how it is read, so it never makes an edge projecting. A heterogeneous join is therefore legal: `ctx.j["left"] = ctx.t` connects a `text` source into a `plain` join. `ctx.j["left"] = ctx.t[3]` is not, for exactly the reason `ctx.a = ctx.t[3]` is not.
- **The comparison is against `celltype`, never `input_celltype`.** A rewire discards the old `input_celltype`, so it has no standing — and wherever a path is involved the invariant makes the two coincide anyway. `S == celltype` is what lets a divergence *end*; nothing lets one *start* behind a projection.
- **A raw checksum / buffer / value write sets `input_celltype := celltype`**, so it carries neither a path nor a conversion and always satisfies the rule.
- **A symbol whose `anonymous_nodes` entry carries a path counts as a source that carries a path.** An edge from an anonymous cell names only its symbol, but the rule looks through the symbol to its entry: `ctx.a = ctx.b[3]` into an *existing* `plain` cell `a`, with `b` of celltype `text`, is refused exactly as if the edge carried the path itself. The same holds at a pin (`contracts/pins.md`).
- **Retyping obeys the same invariant.** `ctx.a.celltype = …`, and `cell.celltype = …` on a standalone child that carries a path, are refused on a cell fed through a path; put the conversion on the source instead.

**Writing such a link raises; having one imposed on you does not.** The refusal is a `TypeError`, and its message points at both readings, because the whole problem is that the spelling does not choose between them. **The exception class is contract; the wording is not.** The intended message spells both alternatives out:

```
ctx.a = ctx.b[3]
TypeError: would convert text -> plain behind a projection.
  ctx.a = ctx.b[3].as_celltype("plain")   # item 3 of the text (a character), as plain
  ctx.a = ctx.b.as_celltype("plain")[3]   # item 3 of the parsed list
```

Today's message is the shorter `Cannot implicitly convert behind a projection; use as_celltype() before or after projecting`; assert on `TypeError`, not on the text.

Retyping a **source** that has projecting consumers is a valid request and is *not* refused. Each affected consumer becomes **`miswired`**. In a Context, its own dependents are `blocked` with reason `blocked-by-miswiring` (`contracts/node-state-lifecycle.md`); `blocked` and `block_reason` remain bound-only. Only invalid requests raise; a valid request that invalidates someone else's wiring leaves a node condition.

**Standalone consumers can also be `miswired`.** After `c = b[3]`, retyping `b` so that the link would project and convert leaves `c` in state `miswired`, rather than rejecting the valid change to `b`. Its `.checksum` is `None`. The standalone state vocabulary therefore includes `miswired` (*Non-goals*).

*Verified:* standalone, the rule is enforced — `Cell(source=…)`, `with_input()` and a retype refuse a converting link behind a projection (`_check_projected_source`, `CellBase.celltype`'s setter), projection and `as_celltype` build separate child links, and a consumer whose parent is retyped reports `miswired` (`Cell._miswired`). Bound, it is enforced for **transformer pins** (the edge check in `Context._add_endpoint_edge`, the pin-retype check, and `miswired` derivation in `Context._source_state`). *Contract ahead of code:* bound **cell** targets are not checked — `ctx.a = Cell("plain"); ctx.a = ctx.b[3]` with `b` of celltype `text` is accepted and answers `','`, and a cell consumer is never derived `miswired`; the symbol-with-path clause above waits on anonymous nodes.

**A deep source is governed by the deep celltype's own rules, not by these.** Where the link's source celltype is deep — `deepcell`, `deepfolder` or `folder` — the path-and-conversion rule above does not apply. A deep step is an **index lookup, not a structural projection**, and it necessarily changes the celltype, so a path and a conversion always travel together there. What is legal is the table in `contracts/deep-celltypes.md`: the zero-path conversions, and the exactly-one-string-item step whose result is `checksum` or the member's own celltype, and nothing else.

The **outcome is the same** — a link outside that table is statically ill-formed, and bound that leaves the node `miswired`; only the criterion differs. And the carve-out is scoped to the link whose *source* is deep: everything downstream of the resulting child checksum is ordinary wiring again.

**The rest of this section is about binding.** Anonymity, symbols, the symbol table and elision all describe cells that live in a Context; none of them is a standalone concept.

**Anonymous cells.** An **anonymous** cell is a Context cell node that has a **symbol** and no name. Its recipe is a single link — `(source, celltype, path)`, carrying *either* a path *or* a conversion — whose source is its parent: a named node or another anonymous cell. Two things create one:

- **a bound projection or a bound `as_celltype`.** `ctx.a[3]`, `ctx.a.b`, `ctx.a[1:4]` and `ctx.b.as_celltype("plain")` each return a handle to an anonymous cell, and chaining them (`ctx.b.as_celltype("plain")[3]`) creates one anonymous cell per link;
- **binding a standalone chain.** Binding is a move (*Projections*): every intermediate link goes into the graph as an anonymous cell, named by the edge that uses it.

There is no such thing as an anonymous *standalone* cell. A standalone chain's intermediates — the temporary `b[3]` in `a = b[3].as_celltype("plain")` — are ordinary Python objects that survive only as the **input reference** held by the next link: no node, no symbol, no name, and nothing that would ever evaluate them on its own. That is the other half of why an unbound chain is lazy: nothing but a read will ever drive those links (*Reads*, *Laziness*).

**The handle and the node.**

- **The handle creates the node.** Evaluating `ctx.b.as_celltype("plain")` creates the anonymous cell at once, before anything is assigned. The Context holds it **weakly**, through its symbol entry; every edge that names its symbol, and every live handle to it, holds it **strongly**. When neither an edge nor a handle remains, its removal is posted to the controller — it is never performed from a finalizer or any other thread.
- **Handles to the same recipe share one node.** A second `ctx.b.as_celltype("plain")` attaches to the existing entry. The handles themselves are fresh, as every handle is: `ctx.a[3] is ctx.a[3]` is `False` (*Binding*).
- **An anonymous cell never appears in the Context's attribute namespace.** It is reached only through a handle, or named as the source of an edge.
- **Reads through the handle are unbound reads over the parent's checksum** (*Reads*, *Anonymous and projection handles*). The Context-derived state of an anonymous cell is never visible through the API.
- **Writes through a projection handle are pathed writes to the parent; writes through an `as_celltype` handle are refused** (*Writes*, *Writes through a handle*).
- **The handle belongs to its Context.** It cannot be captured by `Cell(source=…)` or assigned into another Context (*Binding*).

**Assigning an anonymous handle** into its own Context depends on whether the target name exists:

- **A new name takes the anonymous cell over.** `x = ctx.b.as_celltype("plain"); ctx.a = x`, where `ctx.a` did not exist, turns the anonymous cell into the named node `a`: its entry leaves `anonymous_nodes`, the node is stored under `nodes` at `("a",)`, and every edge and every entry that named its symbol now names `("a",)` instead. The old symbol is retired. `x` becomes a handle to `a`, with named-node read semantics from then on (*Reads*). **Every other handle to the old symbol is invalid**, and raises `StaleWorkflowHandleError` on its next use. A handle to a *different* anonymous cell whose entry named the old symbol stays valid: only that entry's `source` is re-pointed. The new node keeps the anonymous cell's `celltype` — copy once, at creation (*Celltypes*).
- **An existing name gains an edge from the symbol.** `ctx.a = x`, where `ctx.a` already exists, adds an edge from `x`'s symbol to `a`. `a` keeps its own `celltype` and converts into it, subject to the wiring rule, which looks through the symbol to its entry (above). `x` stays exactly what it was: an anonymous handle. A later `ctx.d = x` therefore adds another edge from the same symbol — whereas, had `ctx.a = x` created `a`, `ctx.d = x` would be `ctx.d = ctx.a`.

**Symbols.** An anonymous cell's symbol is **five hex characters derived from `(source, celltype, path)`**. Two *different* recipes whose five characters collide are suffixed `-1`, `-2`, … in the order they were added, which is why the scheme is *mostly*, not purely, content-addressed; a second handle to the *same* recipe attaches to the existing entry and takes no suffix.

Three consequences, all load-bearing:

- **The hash is over the recipe's shape, never over data.** `source` is the source *endpoint* — a node symbol or name plus a local path — not its checksum. A value change must never rename a node.
- **A symbol never changes once assigned.** Symbols are stored, not recomputed — not on load, and not when an entry's source is renamed (the entry's `source` is re-pointed; its symbol stays). The suffix depends on which contender arrived first, so recomputing symbols could hand `abcde` to a different node and silently re-point every edge that names it. A consequence: after a rename, an entry whose definition equals an older one's may carry a different symbol, so a symbol is not a deduplication key across renames.
- **Only the suffix is order-dependent, and that is the right trade.** Suffixing by arrival keeps existing symbols stable when a node is added; ordering the contenders by their full hash instead would be construction-order-independent but would renumber live nodes on insertion. The price is that two isomorphic graphs built in different orders can differ in their symbols, so graph equality is not canonical.

Five hex characters is twenty bits, so a graph on the order of a thousand anonymous nodes is more likely than not to contain a collision. The suffixed form is an ordinary case that needs a test, not a defensive branch.

**Elidable and elided are properties of *bound* cells only.** They exist because a Context is **eager**: it evaluates every cell node's expression as its tick runs, whether or not anybody reads it (*Reads*, *Laziness*). Elision is what stops that eagerness from computing intermediates no named node needs. Standalone there is nothing to elide and nothing to be eager about — an unbound chain evaluates nothing until it is read, and its intermediates are input references rather than nodes.

A bound cell is **elidable** when the Context never has to produce its checksum for anyone — it is in the graph only as a step in a recipe. **Every anonymous cell is elidable.** A read through its handle does not demand the Context's result: it evaluates privately, as an unbound Cell does, and never makes the Context evaluate the node (*Reads*, *Anonymous and projection handles*). A **named** cell is never elidable — `ctx.mid.checksum` and `ctx.mid.value` read what the Context produced, so the node produces it and reaches `complete` like any other.

**An anonymous cell is elided iff every edge and every table entry naming it lies inside a maximal fusible run** (`contracts/expressions.md`, *Fusion*). An anonymous cell behind a fusion barrier is never elided. An elided cell's expression is never built and its checksum is never produced; eliding one may in turn make other anonymous cells elided. **Elision is runtime state and is not serialized**: an elided cell stays in `anonymous_nodes`, unmarked. **Elided cells take no part in state derivation or in barriers** — they are never `waiting`, and never hold a barrier open (`contracts/node-state-lifecycle.md`).

An anonymous cell that is **not** elided is the ordinary consequence of a **fusion barrier** — a conversion that produces a new buffer, or a deep step (`contracts/expressions.md`, *Fusion*). It is then a real member of the chain: the Context evaluates it like any other node, so its Expression is built and its result checksum is produced and cached, although no named node reads it — which is exactly the work elision exists to avoid. That state and result stay invisible through the API; a read through the handle evaluates the same Expression over the same parent checksum, and so is a cache hit. So *elidable* says who needs the checksum, not that none is computed; only *elided* means no Expression and no checksum.

**The graph carries anonymous nodes separately.** `get_graph()` stores named nodes under `nodes` and anonymous nodes under the top-level key **`anonymous_nodes`**, never duplicated in `nodes`. `anonymous_nodes` is the symbol table:

```
"anonymous_nodes": {
    "<symbol>": {"source": <ref>, "celltype": "<celltype>", "path": "<path string>"}
}
<ref> = {"node": [<path component>, ...]}  |  {"symbol": "<symbol>"}
```

An edge spells its source with the same `<ref>` form, and an entry carries `scratch` only when it is not the default. An entry **is** the anonymous cell's definition — *take `source`, apply `path`, at `celltype`* — and an edge referring to a symbol resolves through it:

```
ctx.a = ctx.b[3].as_celltype("plain")     sym → (b, text, "[3]")   edge (sym, no path) → a(plain)
ctx.a = ctx.b.as_celltype("plain")[3]     sym → (b, plain, "")    edge (sym, path [3]) → a(plain)
```

(In both lines the outermost link is the handle assigned to the new name `a`, so it becomes `a`; only the inner link stays anonymous.) The two spellings preserve their different application orders after fusion, which is the whole reason the table is durable: without it, the first spelling would reload indistinguishable from `ctx.a = ctx.b[3]` and come back **`miswired`**.

- **The wiring invariant holds on table entries too**, and `set_graph` checks them exactly as it checks edges — an entry carrying both a path and a conversion is ill-formed. Chains alternate by construction, so a legal builder never writes one.
- **Which entries are serialized.** `get_graph()` includes every entry that an edge, or another serialized entry, names. An entry held only by a live handle is runtime state and is excluded: after a reload nothing could reach it.
- **The table resolves the namespace question.** An edge's source is *either* a node `<ref>` *or* a symbol `<ref>`, and the `<ref>` says which, so a user cell named `abcde` and the symbol `abcde` never collide and no sigil has to leak into anything user-visible.

This is a **graph format change to `0.5`**, from `0.4` (register `cells-and-expressions-known-issues.md`, Appendix F.2a, item 7). A graph written with `anonymous_nodes` cannot be read by a loader that does not know about it. *Contract ahead of code* (below).

**Fusion is independent of elision, and is always done.** Chains of Expressions collapse as far as the codebook allows — path into path, and a checksum-preserving conversion into a following path — under the rules in `contracts/expressions.md`, *Fusion*. It applies to named and anonymous intermediates alike, so these two build the same fused recipe:

```python
ctx.a = ctx.b.as_celltype("plain")[3]                                    # anonymous, elided
ctx.mid = Cell("plain"); ctx.mid = ctx.b; ctx.a = ctx.mid[3]             # named, not elided
```

(Here `b` is a `mixed` cell, so `mixed → plain` is a checksum-preserving reinterpretation and fuses into the following path. Were `b` a `text` cell, as in the symbol-table example above, `text → plain` would produce a new buffer: a fusion barrier, so the anonymous cell would be evaluated and not elided, and the two lines would build the same two-member chain instead.)

— which is the point of the ordering rule one level up: where the conversion is written, and whether the intermediate was given a name, must not change what the recipe computes.

What fusion does **not** do is remove a named intermediate's own work: `ctx.mid` still produces its checksum, because something may read it. What it removes is the *consumer's* dependency on that intermediate's **buffer** — the fused chain is evaluated where the root's data is and yields only what the path selected, and where the intermediate is `scratch` its buffer need never exist at all.

**Elidability and miswiring are re-detected together**, whenever a celltype changes or an edge is added or removed — exactly the events that can create or destroy a conversion. Same trigger set, same local comparison of a source's `celltype` against the cell's, so one pass over the affected cone.

*Contract ahead of code — bound Cells only.* Fusion exists below the Context: constructing an Expression over another Expression fuses the pair (`Expression.__post_init__`), so a standalone chain fuses as described here and in `contracts/expressions.md`, *Fusion*. A Context does not fuse: it builds each bound cell's Expression over its source node's current **checksum** (`Context._build_source_expression`), never over that node's own Expression, so no run spans more than one edge and nothing collapses across nodes. Elision does not exist. None of the anonymous-cell model exists yet either:

- a bound projection is a view onto the parent node (`BoundCellBackend` with a `local_path`), not a node with a symbol;
- a bound `as_celltype` returns a standalone Cell over a snapshot of the parent's Expression (`BoundCellBackend.derive`), which is not reactive;
- binding a chain raises `TypeError: Cannot bind a Cell whose input_ref is Expression`;
- there is no `anonymous_nodes` table, no renaming and no weak/strong holding, and `get_graph()` writes format `0.4`.

**`input_celltype` uses the same resolution.** It reports the celltype of whatever `.source` resolves to at that path — the one-level edge targeting the path if there is one, otherwise the nearest enclosing source. The two members are **one lookup**: `.source` returns the endpoint, `input_celltype` returns its celltype. So on a `plain` join fed at `left` by a `text` cell, `ctx.join.left.source` is `ctx.left` and `ctx.join.left.input_celltype` is `text`; on a read projection with no edge of its own, both fall back to the enclosing source, and `input_celltype` is the root's — which is what that projection needs, since its path is applied to the root's value at the root's celltype.

Standalone, the child link's source is the parent, so `input_celltype` is the parent's `celltype` — the same asymmetry as for `.source` (*The input*).

*Contract ahead of code.* `BoundCellBackend.input_celltype` drops `local_path` today (`builder_state.py:64-69`), so a connection target reports the root's celltype where it should report its producer's. Read projections are unaffected.

**A projection's own `celltype` is its parent's** — except one step over a deep parent, which carries the member celltype (`mixed` for `deepcell`, `bytes` for `deepfolder` and `folder`; `contracts/deep-celltypes.md`, *Paths*). A child carries the parent's `celltype` forward unless `as_celltype` changes it, so `ctx.join.left.celltype` is the join's. This is what the wiring rule above compares a source against at a one-level target: `ctx.j["left"] = ctx.t[3]` with a `text` source and a `plain` join is `text` against `plain`, hence refused.

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

Reading `.checksum` after one of those reports the converted output rather than the checksum that was declared. That is retyping doing what retyping is specified to do, not an asymmetry between the getter and the setter. On a `bytes` cell the empty-buffer checksum canonicalizes to null on the way out (*Null and `None`*). There is no constructor `path=`, so there is no path-carrying Cell without a parent link whose round trip could fail. Standalone projection writes raise (*Projections*); bound projection writes are pathed writes to the parent (*Writes through a handle*, below).

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

### Writes through a handle

**A write through a bound projection handle is a pathed write to the parent, never a write to the handle's own node.** With `p = ctx.a.b`, all six writes — `p.set(v)`, `p.value = v`, `p.set_buffer(buf)`, `p.buffer = buf`, `p.set_checksum(cs)`, `p.checksum = cs` — and augmented assignment (`p += 1`) perform the same transaction as `ctx.a.b = v`: an atomic read-modify-set of `a`'s root value (*Projections*), checked by the parent's authority rule above and never detaching. Retained and non-retained handles are the same thing: `ctx.a.b.set(10)` and `p.set(10)` are one operation, as are `ctx.a.b += 1` and `p += 1`.

- **The checksum and buffer forms are resolved at the handle's `celltype`** — the parent's (*Connecting*), or the member celltype one step below a deep parent — and the resulting value is inserted. `p.checksum = cs` and `p.set_checksum(cs)` resolve `cs` at that celltype; `p.set_checksum(cs, input_celltype=X)` converts from `X` to it first; `p.buffer = buf` and `p.set_buffer(buf)` validate and parse `buf` at it. A buffer that cannot be resolved raises `CacheMissError` to the caller, and nothing is recorded anywhere.
- **Clearing a sub-path is refused.** `p.checksum = None`, `p.buffer = None` and `p.set_checksum(None)` raise `ValueError`, naming the two unambiguous spellings: `ctx.a.b = None` stores null in the key, and `del ctx.a["b"]` removes it. A sub-path has no input of its own to clear, so neither reading is chosen silently. The root distinction of *Null and `None`* is unaffected.
- **A write through an `as_celltype` handle is refused.** On `x = ctx.b.as_celltype("plain")`, all six writes and `+=` raise `AuthorityError`, naming the source to write to instead: a conversion has no general inverse, so there is no pathed write to the parent. Assigning the handle itself (`ctx.a = x`, `ctx.a["k"] = x`) is unaffected.
- **The handle does not keep a stale result.** Its memo is keyed by the parent's checksum, so the next read through `p` after a write re-evaluates (*Reads*, *Anonymous and projection handles*).

Standalone, a projection has no controller to serialize the transaction, and its writes raise (*Projections*).

*Contract ahead of code:* the four checksum and buffer forms fail at a sub-path today (*Implementation status*); `p.checksum = None` and its siblings are not refused but fail the same way; and a bound `as_celltype` returns a standalone snapshot rather than a handle (*Connecting*), so the `as_celltype`-handle refusal has nothing to apply to yet.

## Null and `None`

**`None` is a value for every Cell celltype.** Every cell is in effect `T | None`. There is **one celltype-independent representation**: the canonical JSON-null buffer `b"null\n"`, checksum `38e0b9de…`, which is trivial and resolves without cache residency. Null converts to itself for every celltype pair, so retyping a null cell is a no-op, and `str(checksum)` prints `NULL`. The details are in `contracts/celltypes-and-conversion.md`.

Three behaviours stay apart, and each has its own spelling:

| Spelling | Meaning |
|---|---|
| `.value = None`, `.set(None)` | store the **null value** — a real checksum; state `complete` |
| `.checksum = None`, `.buffer = None`, `.set_checksum(None)` | **clear the input** — node stays, state `unwired`, `input_celltype` becomes `None` |
| `del ctx.a` | **delete the node** |
| `del ctx.a["b"]` | delete a key from the value (and any edge targeting that exact path) |
| `ctx.a.b = None`, `ctx.a.b.set(None)`, `ctx.a.b.value = None` | store null **in the key** — a pathed write to the parent |
| `ctx.a.b.checksum = None`, `ctx.a.b.buffer = None`, `ctx.a.b.set_checksum(None)` | **refused** with `ValueError` naming `ctx.a.b = None` and `del ctx.a["b"]` — a sub-path has no input to clear (*Writes through a handle*) |

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

### Laziness: a standalone Cell pulls, a Context pushes

**A standalone Cell computes nothing until it is read.** It holds a recipe, not a running computation: there is no thread, no scheduler and no background work behind it, so every evaluation it ever performs is pulled out of it by a read. The reads that pull are `.checksum`, `.buffer` and `.value` (which need the result checksum first), and the explicit `compute()` / `run()`. Configuration and inspection — `.source`, `.celltype`, `.input_celltype`, `.path`, `build()`, `.state` and `.exception` — pull nothing (*Work*).

**A pull walks the whole cheap chain, and stops at a Transformation.** A standalone Cell is a chain (*Projections*), and every link above it — an upstream Cell, an upstream Expression — is part of the same recipe and is cheap by construction, so one read evaluates as much of that run as it needs. What a pull never does is start **execution**: a source Transformation that has not run is left alone and the read answers `None`. That is what "a property getter never runs a source" means — never start a Transformation, not never evaluate the recipe.

*Verified:* `_available_input_checksum` recurses into a source **Cell**'s getter, and for a source **Expression** it first obtains that Expression's own input the same way, then freezes it into a concrete Expression over the available checksum and computes it — so an intermediate that nothing else will ever run is evaluated by the read, and a source Transformation is never started.

**A bound named Cell is the opposite: its Context is eager.** A Context evaluates its cell nodes' expressions as its own tick runs, without being read by anyone, which is why a bound `.checksum` on a named node never waits — it reports what the node has reached so far. The only bound cells whose expressions a Context does not evaluate are the **elided** ones (*Connecting*). A handle to an anonymous cell is read the standalone way instead (*Anonymous and projection handles*, below).

### `.checksum`

**A property getter never runs a source *Transformation*.** For a Cell fed by a Transformation, `.checksum` reports a result only if that Transformation already has one; the call that starts it is `.compute()`, exactly as `Buffer.get_checksum()` is the working counterpart of `Buffer.checksum`. For a standalone Cell, an upstream **Cell or Expression** is a different matter: it is a link of this Cell's own recipe, and a read evaluates it (*Laziness*). Cell, Pin and Expression get no `get_checksum()`, because `.compute()` already fills that role.

**A standalone Cell's own expression is cheap, so its getter evaluates it** whenever the input checksum is at hand. Standalone resolution order:

1. nothing to apply (no path, no conversion, no validator) — the input checksum;
2. a hit in the process-local Expression cache;
3. a hit in the database;
4. the same evaluation already running in this process — wait for it;
5. the input buffer is local — evaluate now;
6. the input buffer is elsewhere — dispatch the evaluation and wait.

Otherwise `.checksum` is `None`: nothing is known, no remote is configured, or evaluation failed. Steps 2–6 are `Expression` placement and are specified in `contracts/expressions.md`; step 1 is the **dummy Expression** fast path, and on a standalone Cell it is implemented in the getter itself rather than being delegated, because `set_checksum` is instantaneous and `.checksum` must answer without entering the evaluator. That fast path also applies the empty-`bytes` → null canonicalization.

The second `.set_checksum` exception is that **on an unbound Cell `.checksum` is a computed property**, performing a synchronous evaluation of the underlying Expression. This does not change what `set_checksum` means.

**Standalone: wait on expressions, never on transformations.** A source Transformation that is still running gives `None`. A source Expression is evaluated, or its in-flight evaluation waited on, unless it depends on a Transformation that has no result yet. *Verified:* `_available_input_checksum` returns a bare `Checksum` unchanged, evaluates an `Expression` over its own available input (recursively) and answers `None` when that input is an unfinished compute dependency, recurses into a source `Cell`'s own getter, and otherwise reads only the already-recorded `_result_checksum_internal()`.

**Bound and standalone deliberately differ.** A bound `.checksum` on a **named** node is a simple attribute read: it never waits, evaluates, dispatches, or probes the Expression caches/database. It reports the already-produced checksum, or `None` with state `waiting` when evaluation is pending. The dummy Expression is the sole exception: its input checksum is available without evaluation (step 1 above). Steps 2–6 belong to standalone getters and to anonymous and projection handles; the Context does named-node evaluation in the background. A standalone Cell has nothing working in the background, so it waits.

### Anonymous and projection handles

**A handle to an anonymous cell reads like an unbound Cell over its parent's checksum.** This covers every bound projection handle (`ctx.a[3]`, `ctx.a.b`) and every bound `as_celltype` handle (*Connecting*). On such a handle `x`:

- **`x.checksum`, `x.buffer`, `x.value`, `x.compute()` and `x.run()` build the handle's Expression and evaluate it** through the standalone resolution order above. The Expression's input is the parent's **checksum**, not the parent: for a named parent, that node's `.checksum`, read as a bound read; for an anonymous parent, the parent handle's own pulled checksum, recursively.
- **They never wait on the parent.** If the parent — any link of the chain — has no checksum, they return `None` without raising: no `NodeError`, no recorded exception, and the handle stays `waiting`. They wait only for the handle's **own** evaluation when it is dispatched; `x.compute(timeout=…)` bounds that wait, and expiry raises `TimeoutError`. A `None` from `x.run()` is therefore ambiguous with the null value: `x.checksum` tells them apart (`None` — no parent checksum; `NULL` — the null value).
- **Failures live on the handle**, exactly as for a standalone Cell (*Failures*): recorded in `x.exception` as a string, cleared by `x.clear_exception()`, and never seen by another handle — handles are fresh (`ctx.a[3] is ctx.a[3]` is `False`), and a new handle starts clean.
- **`x.state` is passive and local to the handle.** It never builds or runs the Expression: a fresh handle is `waiting` until a pulling read or `compute()` on *that handle* succeeds (`complete`) or fails (`failed`), and it reports `miswired` for an ill-formed link. The Context-derived state of the anonymous node is never visible, and a parent that is `blocked` or `failed` shows on the handle only as `waiting` with `.checksum` `None`.
- **A result the Context already has is a cache hit.** Where the Context evaluates the anonymous node itself (a non-elided one, *Connecting*), the handle's Expression has the same identity over the same concrete parent checksum, so the handle reuses that result rather than recomputing it.
- **The handle's memo is keyed by the parent's checksum.** When the parent changes — including through a write via the handle (*Writes through a handle*) — the next read re-evaluates; a stale result is never returned.
- **After a rename, the handle is a named-node handle.** When `ctx.a = x` creates `a`, `x` becomes a handle to `a` and from then on reads with named-node semantics (*Connecting*, *Assigning an anonymous handle*).

The `.checksum` of a bound **named** node — including `ctx.a.checksum`, the parent's checksum these reads consume — stays a simple attribute read.

*Contract ahead of code:* a bound projection read today resolves the projection over the parent's current checksum (`ingress.controller_method` → `sidework.evaluate_projection`), which matches the rule above, but it records no failure on the handle and raises for a missing path (*Implementation status*); `.state` on a bound projection reports the parent node's state; `compute()` on a bound projection waits on the parent's barrier; and a bound `as_celltype` is a standalone snapshot rather than a handle.

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

The recovery runs **entirely in this process** either way (`contracts/scratch-witness-audit.md`, *Where a fingertip chain runs*), so it assumes this process can execute the chain's transformations — and **the chain itself writes nothing to the hashserver**. What persists a non-scratch Cell's recovered result is the Cell's own incref, never the walk. Both `Cell.fingertip()` and `Pin.fingertip()` exist and delegate to `Checksum.fingertip_sync()`.

**A `CacheMissError` on the *result* checksum is raised to the caller and never becomes `.exception`.** The computation succeeded; whether its buffer can be reached depends on storage and on who is reading. The state stays `complete` and `.checksum` keeps its value. This is the one materialization failure that is deliberately not recorded — contrast a `CacheMissError` on an *input* buffer, which is an evaluation failure and does become `.exception`.

The deserialization pipeline is:

1. retrieve the result checksum, without questioning its validity;
2. validate it against the celltype using the result's HashType (`validate_deserializable_as`, checksum-level first, then again with the buffer in hand);
3. obtain the buffer, and for `.value` deserialize it.

Step 3 can still fail after step 2 passes, because HashType does not cover every future deserialization: `python`, `ipython` and `yaml` need text validation at parse time, which no classification of the bytes provides (`contracts/hashtype.md`). **A validation or deserialization failure is raised to the caller and also sets `.exception`**, and it is **deterministic**: the expression result stays stored, so `clear_exception()` followed by the same read produces the same failure again. *Verified:* a `RAW_TEXT` buffer that is not valid Python, under celltype `python`, gives a readable `.buffer` and a `.value` that raises `HashTypeValidationError`; after `clear_exception()` the checksum and the state return, and the next `.value` fails identically.

`.value` returns `Buffer.content` (raw `bytes`) for celltype `bytes`, and the parsed value otherwise.

## Scratch policy: `Cell.scratch`

**Every Cell has a scratch policy, `scratch`, default `False`.** It is configuration, like `validator`: it never changes the Cell's checksum or identity (`contracts/identity-and-caching.md`), only who keeps its result buffer.

- **A non-scratch Cell (the default) owns its result for keeps.** Its hold on the result is a non-scratch claim, which publishes: the buffer is written to the hashserver. Its requests carry `scratch=False`, so a dispatched Expression is materialized and written by the executing side, and `.value` works after a remote evaluation (`contracts/expressions.md`, *A non-scratch request is answered only by bytes the requester can reach*).
- **A scratch Cell keeps its result in memory only.** Its hold is a scratch claim and its requests carry `scratch=True`: nothing is written. After a remote evaluation `.value` may raise `CacheMissError`; `fingertip()` recovers the bytes locally.
- **Standalone and bound alike.** A standalone Cell stores the flag itself; a bound Cell stores it on its Context node (`ctx.a.scratch = True`), where it is saved with the graph. A standalone Cell assigned into a Context brings its flag along.
- **Per Cell, not inherited.** A projection (`cell["a"]`, `cell.a`) or a retyping (`as_celltype()`) is a new Cell that owns its own result, so it starts non-scratch. `with_input()` and `with_validator()` return a new Cell that copies the flag. A transformer result's `scratch` is its transformer's setting, and is read-only on the result handle.
- **Snapshots do not decide.** In-flight and snapshot claims held by a Context (leases) are neutral: they keep a buffer alive but neither publish it nor change its scratch status (`contracts/internal/checksum-reference-lifecycle.md`). Only the owning node's claim follows the policy.

## Failures

**What sets `.exception`:** an evaluation failure of the Cell's own expression — an impossible path, a forbidden or failing conversion, a `CacheMissError` on an *input* buffer, a HashType rejection — and a validation or deserialization failure while materializing. `NotImplementedError` from an unimplemented validator arrives the same way. **What does not:** a running-loop refusal, and a `CacheMissError` on the result checksum.

**A failure sticks.** The state is `failed`, `.checksum` reports `None` even where the result checksum is well-defined, and it stays that way until `clear_exception()`. There is **no automatic retry**: `clear_exception()` is the explicit retry, for when more caches are configured or the network is better. A deterministic failure simply reproduces; a transient one succeeds.

**A failure is remembered on the handle, never in the substrate.** This is the Cell-side counterpart of "Expression failures are not cached" (`contracts/expressions.md`):

- **standalone** — on the Cell (`_standalone_exception`), and reset whenever the recipe changes: a new input (`_replace_input_ref`), a new `celltype`, a new `validator` or `validator_language`;
- **bound** — on the Context node, where `clear_exception()` also drops the stored demand result, releases its lease and re-derives.

So **a new Cell built on the same recipe never inherits an old failure.** Keying a failure by expression identity in the substrate would have exactly the opposite effect, and would poison a checksum for every later reader.

The checksum shown by a `CacheMissError` is the one whose buffer was missing. In a chain of expressions, that can be an inner input rather than the Cell's own.

**`Cell.exception` holds a string**, as `Transformation.exception` does — one convention across Cell, Pin and Transformation. *Verified:* the standalone getter returns `str(...)` of the stored failure, and `BoundCellBackend.exception` does the same for the node's. One consequence: `CacheMissError`'s checksum then reaches the Cell as **prose only**, inside the message. The jobserver error envelope's split between `message` (for a person) and `checksum` (for code) therefore has no machine-readable arm on the Cell; `exc.args[0]` is a `Checksum` on the `CacheMissError` that `.value` *raises*, but not on the string that `.exception` *holds*.

**`.state` and `.exception` are passive inspection in both modes.** They never evaluate a recipe, wait for work, or fetch a buffer. Standalone, an unevaluated recipe is `waiting` with `.exception is None`; a literal dummy result can be `complete` without evaluation. After a recipe change, inspection discards any stale result or failure but does not compute the new recipe. `clear_exception()` makes `.exception` return `None`; a deterministic failure reappears only after a pulling read or explicit computation. The same holds for a handle to an anonymous cell, whose state and failure are its own (*Reads*, *Anonymous and projection handles*).

## Work: which calls compute and which never do

| Call | Does work? | Returns |
|---|---|---|
| `.source`, `.celltype`, `.input_celltype`, `.path`, `.path_python` | no | configuration |
| `.checksum` | standalone, and on an anonymous or projection handle: evaluates its recipe and upstream Cell/Expression links (a handle over its parent's checksum), never starts a Transformation, never waits on a bound parent; bound named node: reads the current result only, with the dummy exception above | `Checksum` or `None` |
| `.buffer`, `.value` | resolve the result checksum; never fingertip | buffer / value, or raise |
| `.state` | no evaluation; reports current state | lifecycle state |
| `.exception` | no evaluation; reports the stored failure | the stored failure string or `None` |
| `build()` / `expression()` / `cell()` | no | an immutable `Expression` |
| `compute()` | **yes** — standalone, starts missing upstream work; bound named node, waits on the Context barrier; anonymous or projection handle, evaluates over the parent's current checksum without waiting on the parent | the result `Checksum`, or `None` |
| `await compute_async()` / `await computation()` | **yes** | the result `Checksum`, or `None` |
| `run()` | **yes** — compute, then materialize | the value (`None` on a handle whose parent has no checksum) |
| `with_input()`, `as_celltype()`, `item()`, `slice()`, `with_validator()` | no (bound `item()`, `slice()`, `as_celltype()` create an anonymous node, *Connecting*) | a new Cell |
| `fingertip()` | **yes** — resolve, else recompute from provenance, locally, even while a job server is active (`contracts/scratch-witness-audit.md`, case 2); but never starts the Cell's **own** evaluation | the recovered buffer, or `None` when there is no result checksum |
| `clear_exception()`, `prune()` | no evaluation | `None` |

Notes:

- **Reading is the only thing that makes a *standalone* Cell compute**; it has no scheduler of its own (*Reads*, *Laziness*). A **bound** Cell computes without being read, because its Context does it.
- `compute()` is the explicit operation that starts missing upstream work; `.checksum` is not. `computation()` is `compute_async()` under its Context-facing name, and `await cell.computation()` is the asynchronous demand equivalent.
- A **standalone** `compute()` / `compute_async()` records a failure in `.exception` and returns `None` rather than raising; `run()` re-raises the stored failure. A **bound** `compute()` / `compute_async()` on a named node waits on a Context barrier, and `timeout=` is meaningful there (a barrier timeout raises `TimeoutError`; that is feature 10). On an anonymous or projection handle it never waits on the parent: with no parent checksum it returns `None` without raising, and `timeout=` bounds only the wait for the handle's own dispatched evaluation (*Reads*, *Anonymous and projection handles*).
- `compute(input_ref)` / `run(input_ref)` / `build(input_ref)` accept a one-shot input override, type-checked like a constructor input, that does not mutate the Cell. The **parameter** is still spelled `input_ref` (as it is on `Expression`); only the retired *attribute* of that name raises.
- All of these default to `execution="auto"`; placement is in `contracts/expressions.md`.
- **`.path` and `.path_python` are the same string.** `.path` is the path as stored — `""` at the root, dotted for identifier keys and bracketed otherwise (`contracts/expressions.md`, *Path syntax*) — and `.path_python` is an **exact alias** in both modes, kept because the bound backend protocol requires the name (`BoundCellBackend.path_python = path`; `Expression.path_python` returns `self.path`). Neither is a second spelling of the path, and nothing distinguishes them.
- **`.path` is read-only in both modes.** Assigning it raises `AttributeError`; add a path by projecting, which returns a child Cell. `.path_python` is the same read-only alias.
- The builder methods return **new** Cells and never mutate. On a **bound** Cell, `item()`, `slice()` and `as_celltype()` return handles to **anonymous** bound cells linked to the parent (*Connecting*), while `with_validator()` and `with_input()` return a *standalone* Cell built on the bound cell's current Expression snapshot (`BoundCellBackend.derive`). Re-aiming a bound cell in place is a Context write, not a derivation. *Contract ahead of code:* a bound `as_celltype()` still returns a standalone snapshot, like `with_validator()`, and `item()` / `slice()` return views onto the parent node rather than anonymous nodes.

## Projections

Attribute, item and slice reads navigate uniformly in both modes and each return a derived Cell carrying one more normalized path step:

```python
cell.foo   cell["foo"]   cell[0]   cell[1:4]
ctx.a.foo  ctx.a["foo"]  ctx.a[0]  ctx.a[1:4]
```

**A projection selects within the value read at `input_celltype`; `celltype` then converts only what the projection selected — never the whole value before the path is walked.** This is the Cell-side statement of Expression evaluation order; `contracts/expressions.md`'s *Application order* is the rule's owner, together with the reason the order is not cosmetic and a worked example in Expression terms.

For example, a `Cell("text")` holding `[10, 20, 30, 40]` as text. `cell[3].as_celltype("plain")` selects item `3` of the **text** — the character `','` — and renders that as `plain`. `cell.as_celltype("plain")[3]` converts the text to `plain` **first**, closing that Expression, and then selects item `3` of the resulting **list** — the integer `40`. The two spellings are different recipes, and each means what it reads as: `as_celltype` fixes the celltype from that point in the chain onward, so a path written after it walks the converted value, and a Cell is therefore a *chain* of Expressions wherever a conversion is followed by a projection.

*Verified, standalone:* `Cell.item`, `Cell.slice` and `Cell.as_celltype` each build a child `Cell(source=self)` carrying one path step or one conversion, so the two spellings are two different chains. *Contract ahead of code, bound:* `BoundCellBackend.derive` still builds a standalone snapshot over the root and overwrites only the output celltype, so `ctx.b.as_celltype("plain")[3]` walks the text rather than the list.

**Projection and `as_celltype` both return a child cell linked to the parent.** `cell[3]` is a child Cell whose *source* is `cell`, carrying the path; `cell.as_celltype(ct)` is a child Cell whose source is `cell`, carrying the conversion. `Cell.__init__` takes **no `path` argument** — constructor paths are replaced by projection — and `.path` is read-only. Bound, the child is an anonymous cell whose link names the parent (*Connecting*). Three things follow:

- **Paths come only from projecting**, so the builder stays a chain. There is no path-carrying Cell without a parent link.
- **The wiring invariant holds standalone too.** `cell[3].as_celltype("plain")` is two cells and two links, not one cell carrying both; so **binding is a move, not a decomposition** — the chain that goes into the Context already has the shape the graph requires, one symbol-table entry per anonymous link.
- **`.source` on a standalone projection answers the parent Cell** — the reading the name promises. Bound, `.source` answers the resolved edge instead (*The input*).

This costs nothing at evaluation time: a run of path links fuses back into one Expression (`contracts/expressions.md`, *Fusion*), which is why fusion has to be unconditional rather than an optimization.

**API-name arbitration: normal Python lookup wins.** `__getattr__` projects only for a name that is not statically defined on `Cell` or its bases. A bound-only member whose getter raises `AttributeError` on a standalone Cell (`mount`, `block_reason`) must *not* fall through to a same-named projection, so `Cell.__getattr__` consults `_class_attribute` and re-raises rather than projecting. Names starting with `_` never project. Item access is the escape hatch: `ctx.a["value"]` and `ctx.a["run"]` are ordinary projections of data fields with those names. Cells have no `.pins` API, and `pins` is not reserved, so `ctx.a.pins` is an ordinary projection.

**A Cell is a handle, and says so.** `==`, ordering, `bool()`, `len()` and iteration raise `ProjectionError` — which subclasses both `TypeError` and `AttributeError` — on **every** Cell, and on every Pin, which shares `CellBase`. Handle identity carries no meaning, so comparing a Cell to a value, or to another Cell, is always a mistake whether or not a path is involved. **There is no separate projection class**: the guard lives on `CellBase`, and the message adapts to the object — on a Cell carrying a path it names the path and suggests the misspelling that attribute projection makes silent (`ctx.a.vlaue`), and on one without a path it says to read `.value`. One gap has no fix: `is None` compiles to a pointer comparison with no protocol to intercept, so `assert ctx.a.vlaue is not None` still passes.

*Verified:* the guards are defined on `CellBase` (`_not_a_value`), which `Cell` and `Pin` share; `CellBase.__hash__` stays identity-based, so handles can still be dict keys and set members.

**Projection depth is unlimited; connection targets are not.** A projection path may be arbitrarily deep wherever the underlying Expression path and source celltype support it. A **connection target** — a graph location that may receive a bound source — is the **root or one level below it, and nothing deeper**. A one-level target is a single point selection: a mapping key, an attribute name, or an integer sequence index. A slice may be read or value-updated but is never a connection target, because it denotes several positions. `ctx.a.b.c = ctx.x` raises `PathError: Cell connection targets are limited to one point component`.

A mapping-key connection can bootstrap an unwired cell as a mapping. An integer-index connection requires an existing compatible sequence; it never infers or grows a list, and the check happens when the value is assembled (`evaluate_cell` raises `TypeError("Integer Cell connection targets require an existing sequence")`).

**A sub-path write is an atomic read-modify-set of the root value**, not persistent path-overlay state and not a sub-value producer. One serialized transaction:

1. check that no incoming edge targets the root or an ancestor of the path;
2. read a **detached** copy of the current resolved root value;
3. apply ordinary Python container mutation along the path;
4. re-serialize and commit the changed aggregate as the root, preserving every unrelated one-level incoming edge.

It therefore **needs the current value to be materializable**. When the node is `waiting` the write waits on a barrier and retries (a sub-path write only ever targets a cell node, and a cell node is never `computing`); otherwise a root with no checksum raises `ValueUnavailableError` — except that for a string/attribute path an *unwired* cell is treated as an empty mapping and missing intermediate keys are created as `{}`, so `ctx.a = Cell(); ctx.a.b.c = 12` yields `{"b": {"c": 12}}`. An explicitly stored `null` is not unwired and fails. The commit is optimistically concurrent (base checksum plus node revision) and retries up to 8 times before raising `ConcurrentUpdateError`.

Augmented assignment (`+=`, `-=`, `*=`, `/=`) reads the current resolved value and commits through the same single transaction. Because Python writes the result of `__iadd__` back to its owner, the returned handle must be treated as an inert same-endpoint reassignment and must not create a self-edge; a separately retained projection (`p = ctx.a.b.c; p += 1`) performs the same single transaction. So does every write through a projection handle — `ctx.a.b.set(10)`, `p.value = 3`, `p.checksum = cs` — which is a pathed write to the parent, never a write to the handle's own anonymous node (*Writes through a handle*). `del ctx.a["b"]` deletes the key and, being a detaching delete, also removes any edge targeting that exact path.

Sub-path writes and augmented assignment are **bound-only**. Standalone, `cell["b"] = v` and `cell += 1` raise `TypeError`, and `cell.b = v` raises `AttributeError`: a standalone Cell has no controller to serialize the transaction.

The same absence of a controller means a standalone projection's *property* writes — `cell.b.checksum = cs`, `cell.b.set_checksum(cs)`, `cell.b.value = v`, `cell.b.buffer = buf` — are contractually errors for the identical reason, but today they do not raise; see *Implementation status*.

## Cell-level joins

A **join** is a Cell with several producers — a root value and/or one-level sub-path connections:

```python
ctx.join = {}
ctx.join.left = ctx.left
ctx.join.right = ctx.right
```

**Join members convert to the join's celltype before insertion.** For an assignable member of a `mixed` or `plain` join, `ctx.j["left"] = ctx.t; a = ctx.j.value` and the root connection `ctx.j = ctx.t; b = ctx.j.value` must give the same value for `a["left"]` and `b` after computation. For example, a `text` source containing `"[1,2]"` contributes the list `[1, 2]` to a `plain` join, not the source string. A heterogeneous member source must be pathless: conversion cannot share its link with a source projection. Conversion failure is an evaluation failure, as for a root conversion. **Contract ahead of code:** current assembly embeds the value resolved at the source's own celltype without this conversion.

**Current implementation: a join is plain local Python.** It is assembled directly in the Context, in-process: the root value is resolved, each connected sub-path source's value is resolved and assigned into a detached copy, and the aggregate is re-serialized. **There is no Transformation and no Expression behind it.** *Verified:* `Context._derive_cell` takes this branch when there are sub-path edges and no root edge, and hands `sidework.evaluate_cell` to `_demand`, which runs it in a worker thread; `evaluate_cell` calls `Checksum.resolve`, `_assign_path` and `checksum_for_value`, and nothing else.

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

*Verified:* the rules are enforced. `validate_expression_shape` admits the deep zero-path conversions and the one string-item step and refuses every other shape at construction, the conversion engine evaluates the free deep conversions and `folder → mixed`, and `validate_deep_structure` is the shared flatness validator. On a Cell, a one-step projection of a deep parent carries the member celltype (`mixed` for `deepcell`, `bytes` for `deepfolder` and `folder`), and `as_celltype` to a legal deep target works like any other conversion.

**`.value` on a deep Cell is the index.** Requesting the value of a deep checksum yields its index at every layer, with each member presented as a `Checksum` object — `{key: Checksum}` (`contracts/deep-celltypes.md`, *What a deep buffer is*). `.value` resolves through `Checksum.resolve(celltype)` → `Buffer.get_value(celltype)`, which maps `deepcell`/`deepfolder`/`folder` to `plain` (`Buffer._map_celltype`) before parsing and then validates and wraps the flat index (`validate_deep_structure`). Nothing is resolved and no member buffer is touched: wrapping a hex in a `Checksum` is typing, not resolution. `.buffer` agrees with it: `CellBase.buffer` validates against the same mapped celltype, so it returns the index buffer.

**The typed route to a single child is the one-step path** (`cell["path/to/file"]`, `contracts/deep-celltypes.md`, *Paths*); indexing the `.value` dict yourself gives the same child `Checksum`.

## Implementation status and current limitations

Settled contract that the code does not yet implement, or implements differently. The settled rules above define the test oracle, including explicitly marked contract-ahead-of-code rules; current implementation differences are listed here. Where an older design text disagrees with a rule above, the rule above wins.

- **The bound anonymous-cell model is not implemented.** Bound projections are views onto the parent node, a bound `as_celltype` is a standalone snapshot, there are no symbols, no `anonymous_nodes`, no renaming, no elision and no bound fusion, and `get_graph()` writes format `0.4` (*Connecting*). Handle reads, `.state` and `compute()` on bound projections follow the parent node rather than the handle rules (*Reads*, *Anonymous and projection handles*), and the handle-capture and cross-Context refusals are not in place (*Binding*).
- **Bound cell targets do not enforce the wiring rule.** Only transformer pins are checked and derived `miswired` (*Connecting*).
- **Validators are deferred.** `validator` and `validator_language` are accepted by the constructor, by `with_validator()` and by `CellConfig`, and are excluded from Expression identity, but every evaluation entry point raises `NotImplementedError("Expression validators are not implemented yet")`, which a Cell records as `.exception` (wrapped as `WorkflowExecutionError`). The reject-only semantics are settled; nothing writes the database's validator columns. A validator must be a `Checksum` (or hex) — a validator given as source text fails with a `fromhex` error, not a useful message.
- **The join implementation is provisional** — see above. Caching and placement are to change; only the observable behaviour is contract.
- **A bound sub-path checksum or buffer write fails.** `ctx.a.b.checksum = cs`, `ctx.a.b.set_checksum(cs)`, `ctx.a.b.buffer = buf` and `ctx.a.b.set_buffer(buf)` all raise `TypeError: _edit() got an unexpected keyword argument 'input_celltype'`: `BoundCellBackend.write_checksum` always passes `input_celltype=` on, and `ingress.controller_method` forwards it into `_edit`, which has no such parameter. Root writes are unaffected, and the standalone path is unaffected. The contract is that all six writes through a projection handle are pathed writes to the parent, with a checksum or buffer resolved to a value at the handle's `celltype` before the read-modify-set (`checksum_rhs`), and that clearing a sub-path is refused with `ValueError` (*Writes through a handle*); today the clearing spellings fail with the same `TypeError`.
- **A bound public read does not validate, and does not record.** `Context._get_buffer` and `_get_value` validate against the celltype and record a failure on the node, but `ingress.controller_method` intercepts `_get_checksum` / `_get_buffer` / `_get_value` for every caller outside the controller and resolves the checksum directly. So a bound `.buffer` returns unvalidated bytes, and a bound `.value` whose deserialization fails raises without setting `.exception` — where the standalone path does both. The settled rule ("the same applies to bound and standalone Cells") is the standalone behaviour.
- **A bound read of a non-existent projection raises instead of reporting.** `ctx.p.nope.checksum`, `.value` and `.compute()` raise `ExpressionEvaluationError`, because the ingress read path catches only `KeyError` and `IndexError` while `_apply_step` wraps those in `ExpressionEvaluationError`. The contract is the handle rule of *Reads*, *Anonymous and projection handles*: the read answers `None` and the failure is recorded on that handle, as standalone.
- **Standalone `clear_exception()` does not clear the memoized result.** It clears only `_standalone_exception`. Inspection is passive: `.exception` stays `None` until a pulling read or explicit computation encounters a failure again. If a result was already produced and only materialization failed, its checksum remains available; the next materializing read may reproduce that failure.
- **`context-internals-followup-design.md` is stale on two points**: it makes `.checksum`, `.buffer` and `.value` bound-only (superseded by the standalone-read contract above), and it makes a projection's `input_ref` its owning root endpoint (that meaning belongs to the private `_input_ref`; the public split is `.source` / `.checksum`).
- **On a bound projection, `input_celltype` does not follow the path while `.source` does.** `BoundCellBackend.input_celltype` (`seamless-workflow/seamless_workflow/builder_state.py:64-69`) calls `Context._effective_input_celltype(self.node_path)` and drops `self.local_path`, whereas `BoundCellBackend.source` passes `local_path` into `_public_cell_source`. So for a join `ctx.join.left = ctx.left`, `ctx.join.left.source` reports `ctx.left` but `ctx.join.left.input_celltype` reports the **root's** input celltype. **This is a known bug, not an intended divergence**: the two members are one lookup, as stated in *The input* above, and `local_path` is to be passed through. Until it is, do not rely on `input_celltype` at a bound projection.
- **`Cell.fingertip()` and `Pin.fingertip()` exist but only delegate.** Both resolve the current result checksum and call `Checksum.fingertip_sync()`. It has not been verified that a non-scratch owner's fingertip persists the recovered buffer, as the ownership rule above requires. The earlier defect is fixed: Expression evaluation no longer writes its result buffer to the hashserver, so a fingertip no longer re-adds a buffer that scratch or eviction excluded (`contracts/expressions.md`, *Status: publication and fingertipping*).
- **A standalone projection's property writes are silently lost.** `cell.b.checksum = cs`, `cell.b.set_checksum(cs)`, `cell.b.value = v` and `cell.b.buffer = buf` do not raise, unlike `cell.b = v` (`AttributeError`) and `cell["b"] = v` (`TypeError`). `cell.b` returns a fresh child Cell (`Cell.item` builds `Cell(source=cell)`) whose setters are `CellBase`'s ordinary ones, so the write re-aims that child's own input and the child is then discarded. *Verified:* `CellBase.checksum`'s setter (`_write_checksum` → `_replace_input_ref`) runs against the child instance. The contract is that these four spellings raise the same way item/attribute assignment already does.

### Additional test-confirmed gaps (2026-09-22)

The feature 5 alignment pass exercised the public APIs without inspecting the workflow implementation:

- **Bound empty-`bytes` checksum canonicalization:** writing the empty-buffer checksum to a bound `bytes` Cell leaves that checksum visible instead of the canonical null. Value and buffer writes, and the standalone checksum write, pass the same test.
- **Unwired bound builders:** `as_celltype()` / `build()` on an unwired bound Cell raise `ValueError("Cannot build unwired Cell ...")`, whereas the standalone builder can return an unevaluated recipe. This contradicts the shared builder API in *Work*.
- **Bound deferred-validator failure reporting:** `compute()` raises `WorkflowExecutionError("Expression validators are not implemented yet")` instead of returning `None` and exposing the failure through the Cell. The corresponding standalone case passes, including when the unvalidated recipe was already computed. This test pins only the settled refusal, not future validator semantics.
- **Standalone null retyping:** a null Cell retyped to `int` from `python`, `ipython`, `deepcell`, `deepfolder`, `folder` or `module` fails instead of preserving null. For example, the Python case records `Illegal expression conversion: python -> int`. The corresponding bound cases pass. The null shortcut must precede the ordinary conversion refusal.

These have paired regression cases in `tests/test_cells_contract_alignment.py` in both repositories. See [the alignment report](../../../cells-feature-5-test-alignment.md) for coverage and validation.

## Non-goals

- **Execution.** A Cell has no code, no environment, no pins and no dunders. Anything that needs one is a Transformer; see `contracts/transformers.md`.
- **Handle identity.** Handles are views. Two handles for one node are equal in effect and identical in nothing; nothing may be keyed on a handle's identity. The one place where a particular handle object matters is renaming: the handle assigned to a new name becomes that node's handle, and other handles to the old symbol become invalid (*Connecting*).
- **Deep connection targets.** One level below the root, by design: a deeper target would be a producer of a sub-value, which the read-modify-set model exists to avoid.
- **Persistent sub-path overlays.** A sub-path write is a transaction on the root value, not a stored per-path input.
- **Fingertipping from a property.** `.buffer` and `.value` never recompute a missing buffer. `fingertip()` is the explicit method; `contracts/scratch-witness-audit.md` defines fingertipping and where it happens.
- **Value identity.** A Cell names a checksum, not a value. One value may have several checksums, and identity stays with the checksum (`contracts/identity-and-caching.md`); a Cell never re-serializes a result to normalize it, and `==` between two Cells is not a value comparison.
- **Failure caching.** A Cell failure lives on the handle for as long as the recipe does, and nowhere else.
- **Node state.** `.state` and `.block_reason` are node-lifecycle members shared with bound Transformers, and belong to feature 10's node state lifecycle; standalone — and on a handle to an anonymous cell, whose state is its own — `.state` reports `unwired`, `waiting`, `complete`, `failed` and `miswired`, and `.block_reason` is bound-only.
