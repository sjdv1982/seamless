# Cells (Contract)

**A Cell is a deferred Expression.** An `Expression` is a frozen recipe that has already been closed over its input. A `Cell` is the mutable builder for the same recipe — `(input, input_celltype, celltype)`, plus a path and an optional validator — that can be re-aimed, retyped and re-read, and that snapshots into an immutable `Expression` on demand. Everything an Expression means (identity, cost class, placement, the error envelope, uncached failures) is in `contracts/expressions.md` and is not repeated here.

**A deferred recipe is not necessarily one Expression.** A standalone Cell is a **chain**: every projection and every `as_celltype` returns a **child** Cell linked to its parent, so a standalone builder has the same shape as the graph — each link carries *either* a path *or* a conversion, never both. (A *link* is not an edge: edges exist only in a workflow; standalone, the link is simply the input reference the child holds to its parent — *Connecting*.) A **bound** Cell wraps its incoming edge — several edges, for a join — whose source may be a concrete checksum, a named node or an anonymous one. **One edge is not one Expression**: at build time a run of edges is walked and fused, so an Expression corresponds to a *maximal fusible run*, bounded by conversions and joins (`contracts/expressions.md`, *Fusion*). Bound, a projection (`ctx.a[3]`, `ctx.a.b`) or an `as_celltype` returns an **anonymous** cell handle: a handle to the recipe of a Context node that has a symbol and no name, and that exists once an edge refers to it. The handle reads like an unbound Cell over its parent's checksum (*Connecting*; *Reads*, *Anonymous and projection handles*).

**Where this page sits.** Cells are layer 5 of the stack: celltypes and the type hierarchy (`contracts/celltypes-and-conversion.md`) → HashType (`contracts/hashtype.md`) → conversion (`contracts/celltypes-and-conversion.md`) → Expressions (`contracts/expressions.md`) → **Cells**. Nothing below layer 5 is re-derived here. Two rules from below are used throughout: **project, then convert** (`contracts/expressions.md`, *Application order*), and the deep-celltype carve-out (`contracts/deep-celltypes.md`).

A Cell exists in one of two modes:

- **standalone** — the builder state is private to the Python object;
- **bound** — the builder state is owned by a workflow `Context` node, and the Cell is a *view* onto that node.

The two modes share one class, one read API and one write API. They differ in exactly three places: who owns the state, whether a read waits or evaluates, and which operations exist at all (mounts, `prune()` and `block_reason` are bound-only). These differences are marked throughout. A handle to an anonymous bound cell — a bound projection or `as_celltype` — is bound in ownership and unbound in how it reads (*Reads*, *Anonymous and projection handles*).

Pins are the **sister class**, not a subclass: `Pin` and `Cell` share `CellBase`, which carries the value, type, evaluation and ownership API. Everything Pin-specific — routing to a Transformer, the pin null rules, the absence of projection, validators and mounts — is in `contracts/pins.md`. A Pin is never a valid Cell input; passing one raises `TypeError` pointing at `pin.source`.

Code locations:

| Concern | Module / symbol |
|---|---|
| Shared value/type/evaluation/ownership API | `seamless.cell_class.CellBase` |
| Builder, navigation, snapshots | `seamless.cell_class.Cell`; re-exported as `seamless.Cell` |
| Module helpers | `seamless.cell_class` (`_is_input_ref`, `_check_input_ref`, `_serialize_value`, `_checksum_for_buffer`, `_available_input_checksum`, `_typed_input_celltype`, `_capture_workflow_source`, `_class_attribute`) |
| Errors | `seamless.cell_errors` (`WorkflowError`, `AuthorityError`, `ValueUnavailableError`, `ProjectionError`, `BoundStateError`; `ValueUnavailableError` is also exported as `seamless.ValueUnavailableError`); `seamless.CacheMissError`; `seamless.error_envelope` (`RunningLoopRefusal`, `execution_error`, `WorkflowExecutionError`); `seamless_workflow.errors`, which re-exports `WorkflowError`, `AuthorityError` and `ValueUnavailableError` and adds `DependencyError`, `PathError`, `NodeError`, `StaleWorkflowHandleError`, `ConcurrentUpdateError` |
| Retired names | `seamless.retired_names` (`RETIRED_NAMES`, `check_retired_name`) |
| Snapshot container | `seamless.expression_class.Expression` (`contracts/expressions.md`) |
| Bound backend | `seamless_workflow.builder_state.BoundCellBackend` |
| Bound writes, reads, barriers | `seamless_workflow.ingress` (`controller_method`, `_edit`, `_wait`, `_wait_async`, `_prepare_assignment`) |
| Bound graph operations | `seamless_workflow.context.Context` (`_assign`, `_cell_operation`, `_validate_write`, `_cell_delete_path`, `_derive_cell`, `_apply_pending`, `_projection`, `_demand`, `_build_cell_expression`, `_effective_input_celltype`, `_public_cell_source`, `_get_checksum`/`_get_buffer`/`_get_value`, `_clear_exception`) |
| Local join and projection workers | `seamless_workflow.sidework` (`evaluate_cell`, `evaluate_projection`, `Lease`, `SideLoop`) |
| Value-form classification | `seamless_workflow.adapters.checksum_for_value` |

## The definition

```python
Cell(celltype=None, *, checksum=None, source=None, input_celltype=None,
     validator=None, validator_language=None)
```

- The positional argument is the **produced** celltype.
- `checksum=` and `source=` are **mutually exclusive** (`TypeError` otherwise). `source=` takes a typed reference — a `Cell`, an `Expression`, or any object exposing the duck-typed `_workflow_endpoint` / `_compute_dependency` protocol (a `Transformation`, a bound endpoint of a named node). A bare `Checksum` passed as `source=` raises `TypeError` naming `checksum=`; a `Pin` raises `TypeError` naming `pin.source`; a handle to an anonymous cell raises `DependencyError` (*Binding*).
- **A source is a dependency, not an owned input.** A Cell claims an explicit `checksum=` input from construction. It does not claim the input behind a `source=`: that input stays with its own owner (for a bound node, the Context) until the Cell evaluates and claims its result (`contracts/internal/checksum-reference-lifecycle.md`, §7). To keep a bound node's value past its Context, capture the checksum: `Cell(ctx.a.celltype, checksum=ctx.a.checksum)`.
- `celltype` defaults to a typed source's `celltype`, else `"mixed"`. An unsupported name raises `TypeError` listing the supported celltypes (`contracts/celltypes-and-conversion.md`).
- `input_celltype=` is a **declaration**, legal only alongside a bare checksum. With a typed source it must match, or construction raises `ValueError`.
- `path=` is not a constructor parameter; passing it raises `TypeError`. Paths come only from projecting, and `.path` is read-only (*Work*).
- `validator` / `validator_language` are accepted and stored, but validators are **not implemented** (*Implementation status*).

`build()` — also spelled `cell.expression()` and `cell()` — freezes the current builder state into an `Expression`. That Expression is the contract object; the Cell is the handle that produced it.

### Binding

Assigning a Cell into a Context binds it: `ctx.a = Cell("int")` moves the builder state into a Context node, and every later `ctx.a` returns a **fresh** `Cell` whose state lives entirely in `BoundCellBackend` (`Cell._from_backend`). Consequences:

- **Handle identity carries no meaning.** `ctx.a is not ctx.a`; two handles for one node are interchangeable, and a handle for a deleted node raises `StaleWorkflowHandleError` on its next use.
- **A bound Cell is a view, not a copy.** The Context runtime holds nodes, Expressions and Transformations, never Cells.
- **A standalone Cell is never implicitly bound.** `Cell(source=ctx.a)` captures the bound endpoint of a **named** node as its input (`_capture_workflow_source`): a reference to the node, not a binding of the new Cell.
- **Every handle belongs to its Context.** Assigning a handle — named, anonymous or projection — into a *different* Context raises **`DependencyError`**. A handle to an **anonymous** cell additionally cannot be captured as a standalone source: `Cell(source=ctx.a[3])` and `Cell(source=ctx.b.as_celltype("plain"))` raise `DependencyError`. Assign the handle into its own Context instead (*Connecting*, *Assigning an anonymous handle*).

### Retired names

`target_celltype` and `input_ref` are retired and raise `AttributeError` naming the replacement (`celltype`; `source` or `checksum`). Because attribute access on a Cell falls through to *projection*, `check_retired_name` runs first in `__getattr__`, `__setattr__` and `__delattr__`, so a retired name can never silently become a sub-path. Item navigation is unaffected: `ctx.a["input_ref"]` is an ordinary projection of a data field with that name.

**There is no `SubCell`.** Use `Cell` for projections. The class is removed, not kept as a retirement shim: there is no `seamless.SubCell` and no `__all__` entry for it. The handle guards it used to carry live on `CellBase` (*Projections*).

**There is no old → new migration.** Cells reach `main` unreleased; the contract below is the contract, not a translation of an earlier one.

## Celltypes: `celltype` is the output

**`celltype` is the type of what the Cell produces** — its checksum, its `.buffer`, its `.value`, its `run()`. **`input_celltype` says how the input is read, and is read-only**: assigning it raises `AttributeError`, and there is no setter in either mode.

On a Cell that carries a path — a projection — `contracts/expressions.md`'s **project, then convert** rule applies unchanged: `input_celltype` describes how the value at the Cell's *root* is read, the path is walked against that reading, and `celltype` converts only the value the path selected. Conversion never runs before the path; *Projections* has the worked example.

`input_celltype` comes from the input, and from nowhere else:

| The input is | `input_celltype` is |
|---|---|
| a typed reference (Cell, Expression, Transformation, bound upstream node) | that reference's `celltype`, followed **live** on a Cell; an `Expression` resolves it once, at construction |
| a value written with `.set()` / `.value =` / assignment | the celltype it was serialized in, which is the Cell's `celltype` at that moment |
| a bare `Checksum` | the celltype declared with it (`Cell(ct, checksum=cs, input_celltype=…)`, `set_checksum(cs, input_celltype=…)`), defaulting to `celltype` at that moment |
| absent | `None` |

*Verified:* standalone in `CellBase.input_celltype` / `_replace_input_ref` (`_typed_input_celltype(input_ref) or input_celltype or self.celltype`); bound in `Context._effective_input_celltype` (the root edge's source celltype, else `cell_root_producer.celltype`, else `None`).

Three rules follow:

- **Retyping converts; it does not reinterpret the stored input.** `cell.celltype = ct` changes only the output side. A `str` cell holding `"hello"` (`b'"hello"\n'`) retyped to `text` keeps `input_celltype == "str"` and produces the `text` checksum of `b"hello\n"`: a different checksum, the same value. Where the conversion is checksum-preserving (the trivial and reinterpret classes of `contracts/celltypes-and-conversion.md`, such as `int → float`), the checksum does not move and only `.value` differs. A reformat may keep the checksum too, but only for some values: `int → text` is `=plain→text`, which keeps any buffer that is not a JSON string. It is still a reformat, and the class, not the observed checksum, is what the fusion rule goes by (`contracts/expressions.md`, *Fusion*).
- **Copy once, at creation.** A *new* cell built from a typed source copies that source's `celltype` once: `ctx.a = ctx.b` creates `a` with `b.celltype`. An *existing* cell keeps its own output type when rewired: `ctx.existing = ctx.typed` leaves `existing.celltype` alone and converts into it. The same holds for an anonymous handle: assigned to a new name it feeds the new node through a dummy edge, and the new node keeps the handle's `celltype`; assigned to an existing name it feeds an edge that converts into the existing cell's `celltype` (*Connecting*, *Assigning an anonymous handle*).
- **To correct a wrong declaration, declare the input again.** There is no setter; `set_checksum(cs, input_celltype=…)` is the spelling.

**Retyping is refused on a mounted cell**, whatever the mount mode: `ValueError("Mounted celltype cannot change; unmount first")`. The celltype decides how the attached file's bytes are read and written, so it is frozen for as long as the attachment lives (`contracts/attachments.md`). Assigning a builder of a *different* celltype (`ctx.a = Cell(celltype=other)`) is a retype and is refused the same way; an empty builder of the *same* celltype is not a retype — it detaches the mount and clears the cell (*Authority*).

## The input: `.source` versus `.checksum`

The configured input is public under two names:

| Public | Meaning |
|---|---|
| `.source` | the **derivation** arm, read-only: the upstream handle (bound) or the Cell / Expression / Transformation a standalone builder is built on; `None` when the node holds its own value |
| `.checksum` | the **value** arm: the current produced checksum. As a *write* it declares a literal input, and `None` clears it (at the root only; clearing a sub-path is refused, *Null and `None`*) |

Connecting is always assignment (`ctx.a = ctx.b`, `Cell(source=…)`, `with_input(…)`), so `.source` needs no setter and there is exactly one spelling. `_input_ref` is private and is the Expression recipe, in both modes.

`.checksum` reports the node's **current value**, so it is populated for a connected node too, and is `None` whenever the node is not complete:

| State | `.source` | `.checksum` |
|---|---|---|
| unwired | `None` | `None` |
| literal, complete | `None` | the literal, converted if its `input_celltype` differs from `celltype` |
| connected, complete, no conversion | the handle | `== source.checksum` |
| connected, complete, checksum-preserving conversion | the handle | equal to the source's (trivial / reinterpret: `plain → mixed`, `int → float`, `str → int`) |
| connected, complete, reformatting or value conversion | the handle | in general a different checksum (reformat: `str → text`; value: `int → bool`) |
| connected, upstream waiting / blocked / failed | the handle | `None` |
| own conversion or validator failed | the handle | `None` |

So **`.source is None` means "nothing upstream feeds this"**, and **`.checksum is None` means "not complete"** — the blocker rule, read off the handle.

**On a projection, `.source` answers for that path.** It is the one-level edge targeting that path if there is one, otherwise the nearest enclosing source, otherwise `None`. Deeper paths, which can never carry an edge, walk up the same way. A join with a literal root and a connection at `b` therefore reports `ctx.a.source is None` and `ctx.a.b.source` as the upstream; otherwise sub-path edges would be visible only through `get_graph()`. *Verified:* `Context._public_cell_source` walks `local[:length]` downwards from the full path to the root.

**Bound and standalone projections answer `.source` differently, deliberately.** A **standalone** projection is a child link, and its `.source` is its **parent** Cell (*Projections*). A **bound** projection handle answers with the **resolved edge** above — the edge targeting that path, else the nearest enclosing source, else `None` — never with the parent handle, even though the handle's own recipe is evaluated over the parent's checksum (*Reads*, *Anonymous and projection handles*). The bound reading is what makes sub-path edges and join members visible from a handle.

**`input_celltype` uses the same resolution.** It reports the celltype of whatever `.source` resolves to at that path. The two members are **one lookup**: `.source` returns the endpoint, `input_celltype` returns its celltype. So on a `plain` join fed at `left` by a `text` cell, `ctx.join.left.source` is `ctx.left` and `ctx.join.left.input_celltype` is `text`. **A dummy edge from a single link is looked through**: a cell fed that way (*Assigning an anonymous handle*) reports the link's own source, so after `ctx.a = ctx.b.as_celltype("plain")`, with `b` a `text` cell, `ctx.a.source` is `ctx.b` and `ctx.a.input_celltype` is `text`. That is what `a` reports after a save and reload too, since `get_graph()` saves exactly that link as `a`'s own edge. On a read projection with no edge of its own, both fall back to the enclosing source, and `input_celltype` is the root's — which is what that projection needs, since its path is applied to the root's value at the root's celltype. Standalone, the child link's source is the parent, so `input_celltype` is the parent's `celltype`.

**A projection's own `celltype` is its parent's** — except one step below a deep parent, where it is the member celltype (`mixed` for `deepcell`, `bytes` for `deepfolder` and `folder`; `contracts/deep-celltypes.md`, *Handles and writes one step below a deep parent*). A child carries the parent's `celltype` forward unless `as_celltype` changes it, so `ctx.join.left.celltype` is the join's. This is what the wiring rule compares a source against at a one-level target: `ctx.j["left"] = ctx.t[3]`, with a `text` source and a `plain` join, is `text` against `plain`, hence refused. **A bound handle's `celltype` follows its parent.** Retyping the parent retypes every live handle over it, so a retype never leaves a bound handle `miswired`; the celltype is fixed only when an edge creates the handle's anonymous cell (*The handle and the node*). A standalone child instead copies its parent's celltype at creation, which is why it can become `miswired` (*Connecting*).

## Connecting: a path and a conversion may not share one link

**An edge exists only in a workflow.** Bound, a cell's input is an **edge** in the durable graph, which the Context can see, check, mark and save. Standalone there is no graph and there are no edges: a cell's input is a **link** — the input reference the Cell holds to the Cell, Expression or checksum above it. The invariant below is a property of the link and holds in both modes; what differs is the spelling that creates one, and what a bad one does. Where this section says *edge*, it means the bound case.

**A cell whose input arrives through a path has `celltype == input_celltype`.** A link may not both project into its source *and* convert. The wiring rule that keeps the invariant:

> Defining or redefining a cell's input is legal iff the new source carries **no path**, or the new source's celltype equals the cell's **`celltype`**.

Bound, that is `ctx.a = …` and `ctx.j["k"] = …`; standalone, it is `Cell(source=…)` and `with_input()`, since a standalone Cell cannot be rewired in place (*`.set()` and `.value =` take values only*). It is also the rule behind the builder's shape: `cell[3]` and `cell.as_celltype(ct)` each produce a **separate** link rather than one link carrying both (*Projections*).

**The Expression convention does not lift to a chain.** Inside one Expression the order is fixed — read, project, convert — so `contracts/expressions.md`'s **project, then convert** settles what a single Expression means. Seamless deliberately declines to impose that order on a builder. **Each link is project *or* convert, never both**, and a chain applies its links in the order they were written (*Projections*: syntax order is application order). A Cell can do both as two links, which is why `cell[3].as_celltype("plain")` and `cell.as_celltype("plain")[3]` are two different recipes rather than two spellings of one. A link carrying both would have to pick an order silently, which is exactly what the refusal below prevents. *Fusion* (below) collapses a run of links into a single Expression wherever the codebook allows — **always, not as an optimization** — and where it does not, the recipe stays several Expressions.

- **"Path" means the *input* path** — the projection on the source side. A one-level **connection target** (`ctx.j["left"] = …`), which exists only in a workflow, is where the value lands, not how it is read, so it never makes an edge projecting. A heterogeneous join is therefore legal: `ctx.j["left"] = ctx.t` connects a `text` source into a `plain` join. `ctx.j["left"] = ctx.t[3]` is not, for exactly the reason `ctx.a = ctx.t[3]` is not.
- **The comparison is against `celltype`, never `input_celltype`.** A rewire discards the old `input_celltype`, so it has no standing, and wherever a path is involved the invariant makes the two coincide anyway. `S == celltype` is what lets a divergence *end*; nothing lets one *start* behind a projection.
- **A raw checksum / buffer / value write sets `input_celltype := celltype`**, so it carries neither a path nor a conversion and always satisfies the rule.
- **A symbol whose `anonymous_nodes` entry carries a path counts as a source that carries a path.** An edge from an anonymous cell names only its symbol, but the rule looks through the symbol to its entry: `ctx.a = ctx.b[3]` into an *existing* `plain` cell `a`, with `b` of celltype `text`, is refused exactly as if the edge carried the path itself. The same holds at a pin (`contracts/pins.md`).
- **Retyping obeys the same invariant.** `ctx.a.celltype = …`, and `cell.celltype = …` on a standalone child that carries a path, are refused on a cell fed through a path; put the conversion on the source instead.

**Writing such a link raises; having one imposed on you does not.** The refusal is a `TypeError`, and **its message text is contract**. It points at both readings, because the whole problem is that the spelling does not choose between them:

```
ctx.a = ctx.b[3]
TypeError: would convert text -> plain behind a projection.
  ctx.a = ctx.b[3].as_celltype("plain")   # item 3 of the text (a character), as plain
  ctx.a = ctx.b.as_celltype("plain")[3]   # item 3 of the parsed list
```

The format:

- the header line is `would convert <in> -> <out> behind a projection.`, with the source's celltype as `<in>` and the target's as `<out>`;
- it is followed by the two spellings, projection first: `…[k].as_celltype("<out>")` and then `….as_celltype("<out>")[k]`, where `k` is the step that was written;
- each spelling carries a `# item k of …` gloss saying which reading it means.

**Unknown names are omitted.** Where the refusing code does not know how the target or the source is spelled — a standalone Cell has no name, and the same applies at a join target and at a pin wherever a name is not known — that part is left out, and the spelling starts at the step: `…[3].as_celltype("plain")` and `….as_celltype("plain")[3]`. The pin-side rendering of the same format is in `contracts/pins.md`. **Whether the text of the *retype* refusal (`Cannot convert behind a projection; use as_celltype()`) is also contract is deferred**; for that refusal, rely only on the `TypeError`.

Retyping a **source** that has projecting consumers is a valid request and is *not* refused. Each affected consumer becomes **`miswired`**. In a Context, its own dependents are `blocked` with reason `blocked-by-miswiring` (`contracts/node-state-lifecycle.md`); `blocked` and `block_reason` remain bound-only. Only invalid requests raise; a valid request that invalidates someone else's wiring leaves a node condition.

**Standalone consumers can also be `miswired`.** After `c = b[3]`, retyping `b` so that the link would project and convert leaves `c` in state `miswired`, rather than rejecting the valid change to `b`. Its `.checksum` is `None`. The standalone state vocabulary therefore includes `miswired` (*Non-goals*).

*Verified:* standalone, `Cell(source=…)`, `with_input()` and a retype refuse a converting link behind a projection (`_check_projected_source`, `CellBase.celltype`'s setter), and a consumer whose parent is retyped reports `miswired` (`Cell._miswired`). Bound cell targets and transformer pins are checked when wired; a source retype derives affected consumers as `miswired`.

**A deep source is governed by the deep celltype's own rules, not by these.** Where the link's source celltype is deep — `deepcell`, `deepfolder` or `folder` — the path-and-conversion rule above does not apply. A deep step is an **index lookup, not a structural projection**, and it necessarily changes the celltype, so a path and a conversion always travel together there. What is legal is the table in `contracts/deep-celltypes.md`: the zero-path conversions, and the exactly-one-string-item step whose result is `checksum` or the member's own celltype, and nothing else. The **outcome is the same** — a link outside that table is statically ill-formed, and bound that leaves the node `miswired`; only the criterion differs. The carve-out is scoped to the link whose *source* is deep: everything downstream of the resulting child checksum is ordinary wiring again.

### Anonymous cells, symbols and elision (bound only)

Anonymity, symbols, the symbol table and elision all describe cells that live in a Context; none of them is a standalone concept.

**Anonymous cells.** An **anonymous** cell is a Context cell node that has a **symbol** and no name. Its recipe is a single link — `(source, celltype, path)`, carrying *either* a path *or* a conversion — whose source is its parent: a named node or another anonymous cell. **It exists while an edge, or another anonymous cell's entry, refers to its recipe.** Two things create such a reference:

- **assigning a bound projection or `as_celltype` handle.** `ctx.a[3]`, `ctx.a.b`, `ctx.a[1:4]` and `ctx.b.as_celltype("plain")` each return a handle to an anonymous cell's recipe, and chaining them (`ctx.b.as_celltype("plain")[3]`) gives one recipe per link. Assigning the handle, to a new name or an existing one, creates one anonymous cell per link (*Assigning an anonymous handle*);
- **binding a standalone chain.** Binding is a move (*Projections*): every intermediate link goes into the graph as an anonymous cell, named by the edge that uses it.

There is no such thing as an anonymous *standalone* cell. A standalone chain's intermediates — the temporary `b[3]` in `a = b[3].as_celltype("plain")` — are ordinary Python objects that survive only as the **input reference** held by the next link: no node, no symbol, no name, and nothing that would ever evaluate them on their own. That is the other half of why an unbound chain is lazy: nothing but a read will ever drive those links (*Reads*, *Laziness*).

**The handle and the node.**

- **A handle neither creates nor holds the node.** Evaluating `ctx.b.as_celltype("plain")` creates a handle to a recipe, and nothing in the graph. The anonymous cell is created, and its symbol assigned, when an edge or another entry first refers to that recipe; it is held by every edge that names its symbol and by every entry whose source is that symbol, never by a handle. When none remains, its removal is posted to the controller; the controller removes it, never a finalizer or any other thread. **Its symbol outlives it**: within a living Context a symbol stays reserved for its recipe, so the recipe gets the same symbol back if an edge refers to it again. `get_graph()` writes only the symbols of the entries it saves, so a reloaded Context starts without the released ones.
- **An anonymous cell's `celltype` is fixed when it is created**, like a named cell's (*Copy once, at creation*), and its entry records it. Retyping its source never retypes it, unlike a live handle, which follows its parent until an edge creates the anonymous cell (*The input*). After `ctx.a = ctx.b["x"].as_celltype("plain")`, with `b` a `mixed` cell, retyping `b` to `plain` leaves the anonymous cell for `ctx.b["x"]` reading `b` at `mixed`. A link that carries a path then both projects and converts, so the anonymous cell becomes `miswired` (*Connecting*), and the cells it feeds are `blocked` with reason `blocked-by-miswiring`. This holds while running and after a reload alike.
- **References to the same recipe share one node.** A second edge from `ctx.b.as_celltype("plain")`, from the same handle or another one, attaches to the existing entry. The handles themselves are fresh, as every handle is: `ctx.a[3] is ctx.a[3]` is `False` (*Binding*).
- **An anonymous cell never appears in the Context's attribute namespace.** It is reached only through a handle, or named as the source of an edge.
- **Reads through the handle are unbound reads over the parent's checksum** (*Reads*, *Anonymous and projection handles*). The Context-derived state of an anonymous cell is never visible through the API.
- **Writes through a projection handle are pathed writes to the parent; writes through an `as_celltype` handle are refused** (*Writes through a handle*).
- **The handle belongs to its Context.** Capturing it with `Cell(source=…)` or assigning it into another Context raises `DependencyError` (*Binding*).

**Assigning an anonymous handle** into its own Context depends on whether the target name exists:

- **A new name is fed through a dummy edge.** `x = ctx.b.as_celltype("plain"); ctx.a = x`, where `ctx.a` did not exist, creates the named node `a` with the handle's `celltype` — copy once, at creation (*Celltypes*) — and an identity edge to it from `x`'s anonymous cell: no path, and no conversion, since the two celltypes are equal. **Nothing is renamed and no handle is invalidated**: `x` stays a handle to its anonymous cell, every other handle to the same recipe stays valid, and a later `ctx.d = x` feeds `d` the same way. The same holds for a handle at the end of a chain of two or more links, such as `ctx.b[3].as_celltype("plain")` or `ctx.b.as_celltype("plain")[3]`: every link of the chain is an anonymous cell, and the dummy edge comes from the outermost one. **On save, the dummy edge of a single link is collapsed.** For a handle whose link reads directly from a named node, such as `ctx.b[3]` or `ctx.b.as_celltype("plain")`, `get_graph()` writes that link as `a`'s own incoming edge (*Which entries are serialized*), so after a reload `a` holds the link itself. A chain's dummy edge is saved as it is.
- **An existing name gains an edge from the symbol.** `ctx.a = x`, where `ctx.a` already exists, adds an edge from `x`'s symbol to `a`. `a` keeps its own `celltype` and converts into it, subject to the wiring rule, which looks through the symbol to its entry. `x` stays exactly what it was: an anonymous handle. A later `ctx.d = x` therefore adds another edge from the same symbol.

**Symbols.** An anonymous cell's symbol is **five hex characters derived from `(source, celltype, path)`**, assigned when the anonymous cell is created (*The handle and the node*). Two *different* recipes whose five characters collide are suffixed `-1`, `-2`, … in the order they were added, which is why the scheme is *mostly*, not purely, content-addressed; a second reference to the *same* recipe attaches to the existing entry and takes no suffix. Three consequences, all load-bearing:

- **The hash is over the recipe's shape, never over data.** `source` is the source *endpoint* — a node symbol or name plus a local path — not its checksum. A value change must never rename a node.
- **A symbol never changes once assigned.** Symbols are stored, not recomputed — not on load, and not when an entry's source is renamed (the entry's `source` is re-pointed; its symbol stays). The suffix depends on which contender arrived first, so recomputing symbols could hand `abcde` to a different node and silently re-point every edge that names it. After a rename, an entry whose definition equals an older one's may therefore carry a different symbol, so a symbol is not a deduplication key across renames.
- **Only the suffix is order-dependent, and that is the right trade.** Suffixing by arrival keeps existing symbols stable when a node is added; ordering the contenders by their full hash instead would be construction-order-independent but would renumber live nodes on insertion. The price is that two isomorphic graphs built in different orders can differ in their symbols, so graph equality is not canonical.

Five hex characters is twenty bits, so a graph on the order of a thousand anonymous nodes is more likely than not to contain a collision. The suffixed form is an ordinary case that needs a test, not a defensive branch.

**Elidable and elided are properties of bound cells only.** They exist because a Context is **eager**: it evaluates every cell node's expression as its tick runs, whether or not anybody reads it (*Reads*, *Laziness*). Elision is what stops that eagerness from computing intermediates no named node needs. Standalone there is nothing to elide: an unbound chain evaluates nothing until it is read, and its intermediates are input references rather than nodes.

A bound cell is **elidable** when the Context never has to produce its checksum for anyone — it is in the graph only as a step in a recipe. **Every anonymous cell is elidable.** A read through its handle does not demand the Context's result: it evaluates privately, as an unbound Cell does, and never makes the Context evaluate the node. A **named** cell is never elidable: `ctx.mid.checksum` and `ctx.mid.value` read what the Context produced, so the node produces it and reaches `complete` like any other.

**An anonymous cell is elided iff every edge and every table entry naming it lies inside a maximal fusible run** (`contracts/expressions.md`, *Fusion*). An anonymous cell behind a fusion barrier is never elided. An elided cell's expression is never built and its checksum is never produced; eliding one may in turn make other anonymous cells elided. **Elision is runtime state and is not serialized**: an elided cell stays in `anonymous_nodes`, unmarked. **Elided cells take no part in state derivation or in barriers**: they are never `waiting`, and never hold a barrier open (`contracts/node-state-lifecycle.md`).

An anonymous cell that is **not** elided is the ordinary consequence of a **fusion barrier** — a conversion that produces a new buffer, or a deep step (`contracts/expressions.md`, *Fusion*). It is then a real member of the chain: the Context evaluates it like any other node, so its Expression is built and its result checksum is produced and cached, although no named node reads it. That state and result stay invisible through the API; a read through the handle evaluates the same Expression over the same parent checksum, and so is a cache hit. So *elidable* says who needs the checksum, not that none is computed; only *elided* means no Expression and no checksum.

**The graph carries anonymous nodes separately.** `get_graph()` stores named nodes under `nodes` and anonymous nodes under the top-level key **`anonymous_nodes`**, never duplicated in `nodes`. `anonymous_nodes` is the symbol table:

```
"anonymous_nodes": {
    "<symbol>": {"source": <ref>, "celltype": "<celltype>", "path": "<path string>"}
}
<ref> = {"node": [<path component>, ...]}  |  {"symbol": "<symbol>"}
```

An edge spells its source with the same `<ref>` form, and an entry carries `scratch` only when it is not the default. An entry **is** the anonymous cell's definition — *take `source`, apply `path`, at `celltype`* — and an edge referring to a symbol resolves through it:

```
ctx.a = ctx.b[3].as_celltype("plain")     s1 → (b, text, "[3]")   s2 → (s1, plain, "")      edge (s2) → a(plain)
ctx.a = ctx.b.as_celltype("plain")[3]     s1 → (b, plain, "")     s2 → (s1, plain, "[3]")   edge (s2) → a(plain)
```

Both handles are chains of two links, so both links are saved as entries, and `a`'s dummy edge from the outer one is saved as it is (*Assigning an anonymous handle*). The two spellings keep their different application orders after fusion, which is the whole reason the table is durable: without it, the first spelling would reload indistinguishable from `ctx.a = ctx.b[3]` and come back **`miswired`**.

- **The wiring invariant holds on table entries too**, and `set_graph` checks them exactly as it checks edges: an entry carrying both a path and a conversion is ill-formed. Chains alternate by construction, so a legal builder never writes one.
- **Which entries are serialized.** `get_graph()` includes every entry that an edge, or another serialized entry, names. An entry held only by a live handle is runtime state and is excluded: after a reload nothing could reach it.
- **A dummy edge from a single link is saved as its target's own incoming link.** When an edge comes from an anonymous cell whose link reads directly from a named node, and the edge is an identity (the celltype at the target — a cell's, a join slot's or a pin's — equals the anonymous cell's), `get_graph()` writes that link as the target's incoming edge, and writes the entry only if something else names it. A dummy edge from the outermost link of a chain is saved as it is: collapsing it could leave a conversion behind a path, which reloads `miswired`.
- **The table resolves the namespace question.** An edge's source is *either* a node `<ref>` *or* a symbol `<ref>`, and the `<ref>` says which, so a user cell named `abcde` and the symbol `abcde` never collide, and no sigil has to leak into anything user-visible.

This is a **graph format change to `0.5`**, from `0.4` (register `cells-and-expressions-known-issues.md`, Appendix F.2a, item 7). A graph written with `anonymous_nodes` cannot be read by a loader that does not know about it.

**Fusion is independent of elision, and is always done.** Chains of Expressions collapse as far as the codebook allows — path into path, and a checksum-preserving conversion into a following path — under the rules in `contracts/expressions.md`, *Fusion*. It applies to named and anonymous intermediates alike, so these two build the same fused recipe:

```python
ctx.a = ctx.b.as_celltype("plain")[3]                                    # anonymous, elided
ctx.mid = Cell("plain"); ctx.mid = ctx.b; ctx.a = ctx.mid[3]             # named, not elided
```

Here `b` is a `mixed` cell, so `mixed → plain` is a checksum-preserving reinterpretation and fuses into the following path. Were `b` a `text` cell, as in the symbol-table example above, `text → plain` would produce a new buffer: a fusion barrier, so the anonymous cell would be evaluated and not elided, and the two lines would build the same two-member chain instead. Either way, where the conversion is written and whether the intermediate was given a name must not change what the recipe computes.

What fusion does **not** do is remove a named intermediate's own work: `ctx.mid` still produces its checksum, because something may read it. What it removes is the *consumer's* dependency on that intermediate's **buffer** — the fused chain is evaluated where the root's data is and yields only what the path selected, and where the intermediate is `scratch` its buffer need never exist at all.

**Elidability and miswiring are re-detected together**, whenever a celltype changes or an edge is added or removed — exactly the events that can create or destroy a conversion. Same trigger set, same local comparison of a source's `celltype` against the cell's, so one pass over the affected cone.

## Writes: two verb families

Every write either **defines** the node's input or **writes under** an existing one, and the two families differ in whether authority is checked.

| Family | Spellings | On a connected target |
|---|---|---|
| **Declare the input** | `ctx.a = X`, `.value =`, `.buffer =`, `.checksum =` (including `= None`) | **make it so**: replaces whatever input exists, edge or producer |
| **Write what you own** | `.set()`, `.set_buffer()`, `.set_checksum()`, sub-path assignment, `+=` and friends | **check**: `AuthorityError`, since an upstream edge would overwrite the write on the next recompute |

The two answer different questions. `ctx.a = 7` over a connected cell is a statement about what `a` *is*; `ctx.a.set(7)` is a statement about a value the caller believes it owns, and an upstream edge falsifies that belief.

"Make it so" has one exception: a root **source** is never combined with sub-path edges. Assigning a source at the root of a cell that has sub-path edges is refused, not resolved by detaching them (*Cell-level joins*).

### The 3×2 matrix at the root

Three forms — value, buffer, checksum — each in both families. All three are readable and all three are writable.

| Form | Declare the input (detaches) | Write what you own (checks) |
|---|---|---|
| value | `ctx.a.value = v`; `ctx.a = v` and `tf.pins.x = v` are the idiomatic sugar | `ctx.a.set(v)` |
| buffer | `ctx.a.buffer = buf` | `ctx.a.set_buffer(buf)` |
| checksum | `ctx.a.checksum = cs` | `ctx.a.set_checksum(cs, input_celltype=…)` |

Everything reduces to setting a checksum; the rows differ in what they do first and in what they can guarantee:

- **value** — serialize with the node's `celltype`, which **validates**: `Cell("int").set("abc")` raises `ValueError`. This is where an invalid literal is rejected. The buffer is deposited (with a tempref until the Cell's refhold adopts it), and `input_celltype = celltype` is recorded.
- **buffer** — the bytes are in hand, so nothing is serialized, but they are still checked against the celltype: `_checksum_for_buffer` runs `validate_deserializable_as(checksum, celltype, buffer=buffer)` *and* `buffer.get_value(celltype)`, so a buffer that does not parse as the celltype is rejected at write time. A `Buffer` carries no celltype of its own, so `input_celltype = celltype`.
- **checksum** — an id only. Nothing is deposited, so the buffer must already be resolvable or a later read fails with `CacheMissError`; validation is limited to the hash-type bits; `input_celltype` defaults to `celltype` and is declarable.

**Both sides of a property write speak `celltype`.** Every spelling in the declare family is expressed in the Cell's `celltype` *and records `input_celltype = celltype`*: `.value =` serializes with it, `.buffer =` is validated against it, `.checksum =` declares it. None of the three can name a different input celltype; there is no argument to pass one. So at the root a property write is its own inverse at the moment it happens: `ctx.a.checksum = cs` leaves `ctx.a.checksum == cs`, exactly as `ctx.a.value = v` leaves `ctx.a.value == v`. *Verified:* the `CellBase.checksum` setter calls `_write_checksum(value, detach=True)` with `input_celltype=None`, and `_replace_input_ref` resolves that through `_typed_input_celltype(input_ref) or input_celltype or self.celltype` to `self.celltype`.

Exactly three acts make `input_celltype` differ from `celltype`, and each names the other celltype **explicitly**:

- the method form, `set_checksum(cs, input_celltype=…)`;
- the constructor, `Cell(ct, checksum=cs, input_celltype=…)`;
- a later `cell.celltype = …`, which retypes and therefore converts.

Reading `.checksum` after one of those reports the converted output rather than the checksum that was declared. That is retyping doing what it is specified to do, not an asymmetry between getter and setter. On a `bytes` cell, the empty-buffer checksum canonicalizes to null on the way out (*Null and `None`*). There is no constructor `path=`, so no path-carrying Cell exists without a parent link whose round trip could fail; projection writes are pathed writes to the parent (*Writes through a handle*).

**`set_checksum` sets the input, not `.checksum`.** It is the Checksum variant of the three setters. On a bound named node, `.checksum` reports what the Context has produced, which may not include the write yet. Two cases answer at once: a **dummy Expression** (no path, no conversion, no validator), whose result is its input checksum and needs no evaluation; and a **standalone** Cell, whose `.checksum` getter evaluates the recipe synchronously (*Reads*, *`.checksum`*; `contracts/expressions.md`, *The dummy Expression*). *Verified:* standalone, the `CellBase.checksum` getter returns a bare-checksum input with no path, no validator and `input_celltype == celltype` without building an Expression; bound, `Context._derive_cell` installs such a literal as the node's checksum without evaluation (it does not yet canonicalize empty `bytes`, *Implementation status*).

### `.set()` and `.value =` take values only

A reference is never a value:

- a `Checksum` raises `TypeError: A Checksum is not a value: use .set_checksum() (a Checksum is a value only for celltype 'checksum')`;
- a `Cell`, `Expression`, `Transformation` or bound endpoint raises `TypeError: A <T> is not a value: connect it by assignment, or with Cell(source=...)`;
- a `Pin` raises `TypeError` naming `pin.source`.

The check runs before the bound/standalone split, so it applies identically in both modes and to `.value =` as well as `.set()`. Assignment (`ctx.a = X`) and call-time transformer arguments are the *other* family, and do read a `Checksum` as a declared reference.

A consequence: a standalone Cell cannot be rewired to a source in place. Only `Cell(source=…)` and `with_input()` do that, and both create a new Cell.

### Authority

`AuthorityError` (a `WorkflowError`) is raised by the checking family when a source controls the target:

- **standalone:** a write refuses when the written Cell has a source (`CellBase._check_write_authority`). A write through a projection child is a write to its parent (*Writes through a handle*), so the check applies to the **root** of the projection chain: `c.b.set(2)` refuses when `c` has a source. A write through a child produced by `as_celltype` always refuses;
- **bound:** `Context._validate_write` refuses when an incoming edge is an **ancestor** of the write path, or when an edge is **covered** by the write path and the write is not detaching.

So with an edge at `ctx.a.b`: `ctx.a.b.c.set(2)` raises, `ctx.a.set({...})` raises (the edge is covered by the root write), and `ctx.a.other.set(2)` succeeds — an edge at an unrelated first-level key does not block a sibling.

**Sub-path writes never detach.** `BoundCellBackend.write_value` / `write_checksum` pass `detach=detach and not self.local_path`, so the declare family collapses into the checking family below the root: `ctx.a.b.value = 3` checks authority exactly as `ctx.a.b.set(3)` does. Detaching is a root-level act.

**Mounted cells.** A mounted cell refuses to be cleared: `AuthorityError("Cannot clear a mounted cell; unmount first")`. A sensing mount refuses an incoming edge, at the root or at any sub-path (`AuthorityError("Sensing mount is the producer; unmount first")`), because a sensing attachment *is* the node's producer. Retyping is refused (*Celltypes*). **One assignment is exempt: `ctx.a = Cell(celltype=<same>)`**, an empty builder of the cell's own celltype, is not refused. It **clears the mounting and clears the cell** in one operation, so the cell it clears is no longer mounted. These refusals, the exemption and the sense that writes through this same path are specified in `contracts/attachments.md` (*Detach*) and `contracts/mounts.md`.

### Writes through a handle

**A write through a projection handle is a pathed write to the parent, never a write to the handle's own node** — bound and standalone alike. With `p = ctx.a.b`, all six writes — `p.set(v)`, `p.value = v`, `p.set_buffer(buf)`, `p.buffer = buf`, `p.set_checksum(cs)`, `p.checksum = cs` — and augmented assignment (`p += 1`) perform the same transaction as `ctx.a.b = v`: an atomic read-modify-set of `a`'s root value (*Projections*), checked by the parent's authority rule and never detaching. Retained and non-retained handles are the same thing: `ctx.a.b.set(10)` and `p.set(10)` are one operation, as are `ctx.a.b += 1` and `p += 1`.

- **The checksum and buffer forms are resolved at the handle's `celltype`**, and the resulting value is inserted. `p.checksum = cs` and `p.set_checksum(cs)` resolve `cs` at that celltype; `p.set_checksum(cs, input_celltype=X)` converts from `X` to it first; `p.buffer = buf` and `p.set_buffer(buf)` validate and parse `buf` at it. A buffer that cannot be resolved raises `CacheMissError` to the caller, and nothing is recorded anywhere.
- **Clearing a sub-path is refused.** `p.checksum = None`, `p.buffer = None` and `p.set_checksum(None)` raise `ValueError`, naming the two unambiguous spellings: `ctx.a.b = None` stores null in the key, and `del ctx.a["b"]` removes it. A sub-path has no input of its own to clear, so neither reading is chosen silently. The root distinction of *Null and `None`* is unaffected.
- **A write through an `as_celltype` handle is refused.** On `x = ctx.b.as_celltype("plain")`, all six writes and `+=` raise `AuthorityError`, naming the source to write to instead: a conversion has no general inverse, so there is no pathed write to the parent. Assigning the handle itself (`ctx.a = x`, `ctx.a["k"] = x`) is unaffected.
- **The handle does not keep a stale result.** Its memo is keyed by the parent's checksum, so the next read through `p` after a write re-evaluates (*Reads*, *Anonymous and projection handles*).

**One step below a deep parent, what is inserted is a member checksum.** The parent's value is a flat index `{key: checksum}` (`contracts/deep-celltypes.md`), and the handle `p = d["k"]` carries the member celltype (`mixed` below a `deepcell`, `bytes` below a `deepfolder` or `folder`). A write at `k` is still a pathed read-modify-set of the index, with authority checked on the root, but it replaces `index[k]` with a checksum, so the index stays flat:

- a checksum write (`p.checksum = cs`, `p.set_checksum(cs)`) puts the member checksum `cs`, resolved at the member celltype, into `index[k]`;
- a buffer write (`p.buffer = buf`, `p.set_buffer(buf)`) validates `buf` at the member celltype and puts its checksum into `index[k]`;
- a value write (`p.set(v)`, `p.value = v`) serializes `v` at the member celltype and puts that checksum into `index[k]`.

**Writes below `k` are illegal**: `d["k"]["x"] = v` and `d["k"]["x"].set(v)` raise. A member is behind a checksum, and a write into it would be a write into a different checksum. **The exception class is deferred**; rely only on the write raising.

**Standalone, the same rules hold.** On a standalone Cell `c` with `p = c.b`, the six writes and `p += 1` are a read-modify-set of `c`'s root value, performed synchronously in the caller's thread: the checksum and buffer forms are resolved at `p`'s `celltype`, the clearing forms raise `ValueError`, a write through a standalone `as_celltype` child raises `AuthorityError`, and the authority check applies to the root of the chain (*Authority*). A projection of a projection writes through each parent in turn, down to that root. The parent-side spellings are the same write: `c.b = v` and `c["b"] = v` are pathed writes to `c`; `del c["b"]` removes the key `b` from `c`'s root value (a standalone Cell has no edges, so there is none to remove with it); and `c += 1` is a read-modify-set of `c`'s own root value. Each is checked on the root of the chain. There is no controller, and so no concurrent writer to serialize against; the write is visible to the next read of `c` and of any handle over it. *Implemented* (ruling B).

## Null and `None`

**`None` is a value for every Cell celltype.** Every cell is in effect `T | None`. There is **one celltype-independent representation**: the canonical JSON-null buffer `b"null\n"`, checksum `38e0b9de…`, which is trivial and resolves without cache residency, and `str(checksum)` prints `NULL`.

**Null converts to itself on every legal conversion pair, and only there.** Retyping a null cell along a legal pair is a no-op. A forbidden pair or an illegal deep pair stays illegal for null too: retyping a null `python`, `ipython`, `deepcell`, `deepfolder` or `folder` cell to `int` fails exactly as it would for any other value, because null being deserializable as every celltype is a statement about readings, not a licence to convert. This covers the forbidden ordinary pairs, such as `python → int`, as well as the illegal deep pairs. The pair tables are in `contracts/celltypes-and-conversion.md` (*Null and conversion legality*) and `contracts/deep-celltypes.md`.

The spellings stay apart:

| Spelling | Meaning |
|---|---|
| `.value = None`, `.set(None)` | store the **null value** — a real checksum; state `complete` |
| `.checksum = None`, `.buffer = None`, `.set_checksum(None)` | **clear the input** — the node stays, state `unwired`, `input_celltype` becomes `None` |
| `del ctx.a` | **delete the node** |
| `del ctx.a["b"]`, standalone `del c["b"]` | delete a key from the value (bound: and any edge targeting that exact path) |
| `ctx.a.b = None`, `ctx.a.b.set(None)`, `ctx.a.b.value = None` | store null **in the key** — a pathed write to the parent |
| `ctx.a.b.checksum = None`, `ctx.a.b.buffer = None`, `ctx.a.b.set_checksum(None)` | **refused** with `ValueError` naming `ctx.a.b = None` and `del ctx.a["b"]` — a sub-path has no input to clear (*Writes through a handle*) |

`del` means the named thing is gone, never "empty it". `ctx.a = None` does **not** delete; it stores null. This is required, not incidental: merging "no value" with "the value `None`" would destroy the distinction that optional pins and the "no result" checksum are built on, and the absence of a checksum is the blocker that gates every dependent.

**`bytes` is the one celltype where empty *is* null**, in both directions. `bytes` is the only celltype whose canonical serialization of a legitimate value is empty (`b""`, checksum `e3b0c442…`, which is also the empty file), so an empty buffer under celltype `bytes` canonicalizes to the null checksum, and resolving the null checksum as `bytes` gives `b""`. Hence `ctx.a = b""` on a `bytes` cell stores null and reads back `b""`. The rule is blanket — serialization, Expression evaluation with output celltype `bytes`, transformation results, mount reads — and it is enforced in three places on the Cell path: `Buffer(b"", "bytes")`, `_checksum_for_buffer`, and the `.checksum` dummy fast path. One-directional aliasing would be worse: `b""` would silently become "no value", and every downstream required `bytes` pin would reject it. No other celltype is affected, because none serializes to zero bytes (`text ""` is `b"\n"`, `str ""` is `b'""\n'`, `plain {}` is `b"{}\n"`).

## Celltype `checksum`

**A `Checksum` is a value exactly when the target celltype is `checksum`.** One rule, covering `.set()`, `.value =`, `ctx.a =`, `tf.pins.x =` and `tf(x=…)`. For a `checksum` cell:

- the buffer is the bare 64-character hex digest, which the cell does **not** hold — the cell points at a checksum; it does not contain the buffer behind it;
- `.value` is a `Checksum` object, and `.value == .run() == .build().run()`;
- `.set(cs)` and `.set(cs.hex())` give the same checksum.

For every other celltype, assignment and call-time arguments read a `Checksum` as a declared reference, while `.set()` and `.value =` raise `TypeError`. A 64-character `str` is always a value, never a checksum. Note that `Checksum == hex_str` is true, but the two hash differently.

## Reads

Two concerns stay separate: **retrieving** `.checksum`, and **materializing** it into `.buffer` or `.value`.

### Laziness: a standalone Cell pulls, a Context pushes

**A standalone Cell computes nothing until it is read.** It holds a recipe, not a running computation: there is no thread, no scheduler and no background work behind it, so every evaluation it performs is pulled out of it by a read. The reads that pull are `.checksum`, `.buffer` and `.value` (which need the result checksum first), and the explicit `compute()` / `run()`. Configuration and inspection — `.source`, `.celltype`, `.input_celltype`, `.path`, `build()`, `.state` and `.exception` — pull nothing (*Work*).

**A pull walks the whole cheap chain, and stops at a Transformation.** A standalone Cell is a chain (*Projections*), and every link above it — an upstream Cell, an upstream Expression — is part of the same recipe and cheap by construction, so one read evaluates as much of that run as it needs. What a pull never does is start **execution**: a source Transformation that has not run is left alone, and the read answers `None`. That is what "a property getter never runs a source" means — never start a Transformation, not never evaluate the recipe.

**A bound named Cell is the opposite: its Context is eager.** A Context evaluates its cell nodes' expressions as its own tick runs, without being read, which is why a bound `.checksum` on a named node never waits: it reports what the node has reached so far. The only bound cells whose expressions a Context does not evaluate are the **elided** ones (*Connecting*). A handle to an anonymous cell is read the standalone way instead (*Anonymous and projection handles*).

### `.checksum`

**A property getter never runs a source *Transformation*.** For a Cell fed by a Transformation, `.checksum` reports a result only if that Transformation already has one; the call that starts it is `.compute()`, exactly as `Buffer.get_checksum()` is the working counterpart of `Buffer.checksum`. An upstream **Cell or Expression** is different: standalone, it is a link of this Cell's own recipe, and a read evaluates it. Cell, Pin and Expression get no `get_checksum()`, because `.compute()` already fills that role.

**A standalone Cell's own expression is cheap, so its getter evaluates it** whenever the input checksum is at hand. Standalone resolution order:

1. nothing to apply (no path, no conversion, no validator) — the input checksum;
2. a hit in the process-local Expression cache;
3. a hit in the database;
4. the same evaluation already running in this process — wait for it;
5. the input buffer is local — evaluate now;
6. the input buffer is elsewhere — dispatch the evaluation and wait.

Otherwise `.checksum` is `None`: nothing is known, no remote is configured, or evaluation failed. Steps 2–6 are Expression placement (`contracts/expressions.md`). Step 1 is the **dummy Expression** fast path. On a standalone Cell it is implemented in the getter itself, without entering the evaluator, and it applies the empty-`bytes` → null canonicalization. *Verified:* `CellBase.checksum` returns `canonicalize_checksum(input, celltype)` for a bare-checksum input with no path, no validator and `input_celltype == celltype`, before building any Expression.

**Standalone: wait on expressions, never on transformations.** A source Transformation that is still running gives `None`. A source Expression is evaluated, or its in-flight evaluation waited on, unless it depends on a Transformation that has no result yet. *Verified:* `_available_input_checksum` returns a bare `Checksum` unchanged, evaluates an `Expression` over its own available input (recursively) and answers `None` when that input is an unfinished compute dependency, recurses into a source `Cell`'s own getter, and otherwise reads only the already-recorded `_result_checksum_internal()`.

**Bound and standalone deliberately differ.** A bound `.checksum` on a **named** node is a simple attribute read: it never waits, evaluates, dispatches, or probes the Expression caches or the database. It reports the already-produced checksum, or `None` with state `waiting` while evaluation is pending. The dummy Expression is the only case that needs no evaluation: the Context installs a literal whose `input_celltype` equals `celltype` directly (`Context._derive_cell`). Steps 2–6 belong to standalone getters and to anonymous and projection handles; the Context does named-node evaluation in the background. A standalone Cell has nothing working in the background, so it waits.

### Anonymous and projection handles

**A handle to an anonymous cell reads like an unbound Cell over its parent's checksum.** This covers every bound projection handle (`ctx.a[3]`, `ctx.a.b`) and every bound `as_celltype` handle (*Connecting*). On such a handle `x`:

- **`x.checksum`, `x.buffer`, `x.value`, `x.compute()` and `x.run()` build the handle's Expression and evaluate it** through the standalone resolution order above. The Expression's input is the parent's **checksum**, not the parent: for a named parent, that node's `.checksum`, read as a bound read; for an anonymous parent, the parent handle's own pulled checksum, recursively.
- **They never wait on the parent.** If the parent — any link of the chain — has no checksum, they return `None` without raising: no `NodeError`, no recorded exception. They wait only for the handle's **own** evaluation when it is dispatched; `x.compute(timeout=…)` bounds that wait, and expiry raises `TimeoutError`. A `None` from `x.run()` is therefore ambiguous with the null value: `x.checksum` tells them apart (`None` — no parent checksum; `NULL` — the null value).
- **Failures live on the handle**, exactly as for a standalone Cell (*Failures*): recorded in `x.exception` as a string, cleared by `x.clear_exception()`, and never seen by another handle. Handles are fresh (`ctx.a[3] is ctx.a[3]` is `False`), and a new handle starts clean.
- **`x.state` is passive and local to the handle.** It never builds or runs the Expression: a fresh handle is `waiting` until a pulling read or `compute()` on *that handle* succeeds (`complete`) or fails (`failed`), and it reports `miswired` for an ill-formed link. The Context-derived state of the anonymous node is never visible, and a parent that is `blocked` or `failed` shows on the handle only as `waiting` with `.checksum` `None`. **When a handle reports `unwired` is unspecified**: the handle vocabulary includes it, but no ruling says whether a handle over an unwired parent reports `unwired` or `waiting`.
- **A result the Context already has is a cache hit.** Where the Context evaluates the anonymous node itself (a non-elided one, *Connecting*), the handle's Expression has the same identity over the same concrete parent checksum, so the handle reuses that result.
- **The handle's memo is keyed by the parent's checksum.** When the parent changes — including through a write via the handle (*Writes through a handle*) — the next read re-evaluates; a stale result is never returned.
- **Assignment does not change the handle.** After `ctx.a = x`, `x` is still a handle to its anonymous cell and keeps reading this way; `ctx.a` is the handle with named-node semantics (*Connecting*, *Assigning an anonymous handle*).

The `.checksum` of a bound **named** node — including `ctx.a.checksum`, the parent's checksum these reads consume — stays a simple attribute read.

**A running-loop refusal is not a failure.** Inside a running event loop, a synchronous evaluation that would need the async bridge is refused (`RunningLoopRefusal`, `contracts/expressions.md`). The standalone getter turns that into `None`, leaves `.exception` as `None` and the state as `waiting`, and dispatches nothing. It is a condition that resolves itself outside the loop, not an error to be cleared.

Reading `.checksum` expresses **user result interest**: `Expression.compute()` enables result holding, so the result checksum acquires a refholder claim for the lifetime of the reading handle. That is the checksum reference lifecycle, an internal contract (`contracts/internal/checksum-reference-lifecycle.md`). **The Expression-level claim is scratch-neutral**: it protects the result from eviction and does not write the buffer anywhere, so reading a property can never defeat a scratch decision. A Cell is one of the owners that *can* publish, when it is non-scratch and holds a buffer (`contracts/expressions.md`, *Results and caching*).

### `.buffer` and `.value`

**Neither ever fingertips.** Both resolve through `Checksum.resolve()`: local cache, then hashserver, otherwise `CacheMissError`. `Transformation.run()` does fingertip, but it is an explicit method, not a property.

**When there is no result checksum, there is nothing to materialize.** `.buffer` and `.value` return `None` in both modes, whatever the reason: nothing computed yet, a source still running, an unwired input, a bound node that is `blocked`, or a recorded failure. **A failed Cell does not re-raise its failure from a read**; `run()` does (*Failures*, *How a failure is delivered*; ruled 2026-09-28). On a bound named node this means every state but `complete` (`contracts/workflow-context.md`, *Reads*).

**A result checksum does not imply a result buffer.** The checksum may have been recorded without any buffer being produced in this process, and a buffer that did exist may have been evicted or never stored at all (`scratch`). So a `.checksum` that answers guarantees nothing about `.buffer` or `.value`; `fingertip()` is the only guaranteed route to the bytes (`contracts/expressions.md`, *Results and caching*).

**`Cell.fingertip()` is the Cell-level explicit entry point**, and the only place where a fingertip acquires an owner. A fingertip site otherwise holds a bare checksum, with no owner and no scratch intent, so it cannot decide whether the recovered buffer should persist. Through a Cell it can: **on a non-scratch Cell the recovered result is persisted, because the Cell holds it under a non-scratch claim; on a scratch Cell it is not** (`contracts/internal/checksum-reference-lifecycle.md`). *Verified:* `test_cell_fingertipping_a_held_result_persists_it_only_if_non_scratch` in `seamless-core/tests/test_contract_reference_lifecycle_late_buffer.py`.

**`fingertip()` is `Cell.checksum.fingertip()`, with one deliberate difference: it never forces `.checksum`.** The standalone getter's synchronous evaluation is not triggered; `fingertip()` works from the result checksum already in hand. Four consequences:

- **No result checksum, no work.** If `.checksum` is `None` — nothing computed yet, a source still running, a recorded failure — `fingertip()` is a **no-op returning `None`**. Because it never starts the Cell's own evaluation, it is equally safe on a bound Cell whose node is still `waiting`.
- **It returns what `Checksum.fingertip()` returns**: the recovered **buffer**, not a checksum.
- **It never sets `.exception`.** A fingertip is a materialization, and a materialization failure on a *result* checksum is raised to the caller and not recorded (below). That holds even though the chain may execute transformations on the way: their failures belong to their own nodes, not to this handle.
- **`Pin.fingertip()` exists and means the same thing** (`contracts/pins.md`).

Both `Cell.fingertip()` and `Pin.fingertip()` delegate to `Checksum.fingertip_sync()`. The recovery runs **entirely in this process** (`contracts/scratch-witness-audit.md`, *Where a fingertip chain runs*), so it assumes this process can execute the chain's transformations, and **the chain itself writes nothing to the hashserver**. What persists a non-scratch Cell's recovered result is the Cell's own claim, never the walk.

**A `CacheMissError` on the *result* checksum is raised to the caller and never becomes `.exception`.** The computation succeeded; whether its buffer can be reached depends on storage and on who is reading. The state stays `complete`, and `.checksum` keeps its value. No materialization failure is recorded (below); contrast a `CacheMissError` on an *input* buffer, which is an evaluation failure and does become `.exception`.

The deserialization pipeline is:

1. retrieve the result checksum, without questioning its validity;
2. validate it against the celltype using the result's HashType (`validate_deserializable_as`, checksum-level first, then again with the buffer in hand);
3. obtain the buffer, and for `.value` deserialize it.

Step 3 can still fail after step 2 passes, because HashType does not cover every future deserialization: `python`, `ipython` and `yaml` need text validation at parse time, which no classification of the bytes provides (`contracts/hashtype.md`). **A validation or deserialization failure is raised to the caller on every read, and is never recorded** (ruled 2026-09-28). Like a `CacheMissError` on the result, it concerns a result that exists: the state stays `complete`, `.checksum` keeps its value, and `.exception` stays `None`. It is **deterministic**, so every read reproduces it, with no `clear_exception()` in between. A HashType disproof at step 2 fails `.buffer` and `.value` alike; a parse failure at step 3 fails only `.value`, and `.buffer` still returns the bytes. `run()` raises it too; `.checksum` and `compute()` do not, because they do not materialize. This holds for bound and standalone Cells alike, and it is why an Expression result that cannot be deserialized as its celltype is never undone: the Expression succeeded, and only reading its value fails.

`.value` returns `Buffer.content` (raw `bytes`) for celltype `bytes`, and the parsed value otherwise.

**Writing does not run step 3's text validation.** `ctx.a.set("def (:\n")` (or any equivalent assignment) on a `python`/`ipython`/`yaml` Cell does not parse the text and does not raise: `canon_T` deliberately skips the parser for the code celltypes, so the write succeeds and the cell is `complete`. The syntax error surfaces only downstream: a `.value` read raises it on every read without failing the Cell (as above), and a transformer that runs the code fails with the `SyntaxError` as its own failure. A mounted or sensed value follows exactly the same rule, and so a mounted file with a syntax error stays `complete` (ruled 2026-09-28; `contracts/mounts.md`, *Canonical bytes*; `contracts/attachments.md`, *Sense*).

## Scratch policy: `Cell.scratch`

**Every Cell has a scratch policy, `scratch`, default `False`.** It is configuration, like `validator`: it never changes the Cell's checksum or identity (`contracts/identity-and-caching.md`), only who keeps its result buffer.

- **A non-scratch Cell (the default) owns its result for keeps.** Its hold on the result is a non-scratch claim, which publishes: the buffer is written to the hashserver. Its own last Expression link carries `scratch=False`; earlier links and anonymous nodes are scratch checksum requests. A dispatched last link writes its result on the executing side. Its reads and `compute()` still ask for a checksum only, so a recorded checksum answers them even when its buffer is reachable nowhere; `.value` then raises `CacheMissError`, and `fingertip()` recovers the bytes and persists them (`contracts/expressions.md`, *A value request is answered only by bytes the requester can reach*; ruled 2026-09-30).
- **In a Context, a non-scratch cell overrules a scratch transformer when it holds the transformer's result as its own buffer.** The result may pass through other cells and checksum-preserving conversions. A path or buffer-producing conversion stops the overrule, because the cell then holds a different buffer. The transformer node's own claim stays scratch (`contracts/pins.md`, *Scratch at the pin*).
- **A scratch Cell keeps its result in memory only.** Its hold is a scratch claim, and its last Expression link also requests `scratch=True`: nothing is written. After a remote evaluation `.value` may raise `CacheMissError`; `fingertip()` recovers the bytes locally.
- **Standalone and bound alike.** A standalone Cell stores the flag itself; a bound Cell stores it on its Context node (`ctx.a.scratch = True`), where it is saved with the graph. A standalone Cell assigned into a Context brings its flag along.
- **Per Cell, not inherited.** A projection (`cell["a"]`, `cell.a`) or a retyping (`as_celltype()`) is a new Cell that owns its own result, so it starts non-scratch. `with_input()` and `with_validator()` return a new Cell that copies the flag. A transformer result's `scratch` is its transformer's setting, and is read-only on the result handle.
- **Leases do not decide.** The leases a Context holds, on reads, on FrozenTransformers and on in-flight work, are neutral: they keep a buffer alive but neither publish it nor change its scratch status (`contracts/internal/checksum-reference-lifecycle.md`). Only the owning node's claim follows the policy.



## Failures

**What sets `.exception`:** an evaluation failure of the Cell's own expression — an impossible path, a forbidden or failing conversion, a `CacheMissError` on an *input* buffer, a HashType rejection. `NotImplementedError` from an unimplemented validator arrives the same way. **What does not:** a running-loop refusal, and any failure to materialize a result that exists — a `CacheMissError` on the result checksum, or a validation or deserialization failure while reading it (*`.buffer` and `.value`*).

**A failure sticks.** The state is `failed`, `.checksum` reports `None` even where the result checksum is well-defined, and it stays that way until `clear_exception()`. There is **no automatic retry on a read**. Calling `compute()` on a handle is an explicit request for work and may evaluate again; its reads keep reporting the recorded failure until `clear_exception()`. A deterministic failure simply reproduces; a transient one may succeed after an explicit retry.

**How a failure is delivered: reads and `compute()` report it, `run()` raises it** (ruled 2026-09-28). This is one rule for every owner that records failures — Cell, Pin, Transformer and Transformation, bound and standalone (`contracts/pins.md`, `contracts/transformers.md`, `contracts/direct-delayed-and-transformation.md`). A standalone Transformer records nothing on itself: its `compute()` and `run()` delegate to the Transformation it builds, which records the failure, so the rule holds through that Transformation (`contracts/transformers.md`, *Live-node members*):

- **`.checksum`, `.buffer`, `.value` and `compute()` / `compute_async()` never raise for a recorded failure.** On a failed Cell all four answer `None`, and the failure is on `.state` and `.exception`. The same holds for every other outcome that leaves no result — `waiting`, `unwired`, `miswired` and, bound, `blocked`. So on a bound named node `compute()` is a barrier that waits and then reports, as `ctx.compute()` does: it never re-raises the node's failure and never raises `NodeError` (`contracts/node-state-lifecycle.md`, *States as seen through barriers and handles*).
- **`run()` is the call that raises.** It does the work of `compute()` and then re-raises the recorded failure; on a bound named node that settled in `unwired`, `miswired` or `blocked`, it raises `NodeError` naming the state and what to repair; otherwise it materializes the result. On an anonymous or projection handle whose parent has no checksum it returns `None` (*Anonymous and projection handles*).
- **A failure to materialize a result that exists is raised, and never recorded** (*`.buffer` and `.value`*). It is not an outcome of the computation, so it reaches whoever reads, on every read.
- **What `compute()` still raises is about the call, not the work:** a barrier timeout or a handle's evaluation timeout (`TimeoutError`), a deleted node (`StaleWorkflowHandleError`), a closed or poisoned Context, re-entry from a controller turn, and an invalid one-shot input override.
- **`None` from `.value` is ambiguous; `.checksum` is not.** The null value also reads as `.value is None`, but it has the `NULL` checksum, so `.checksum` or `compute()` tells a null result from no result, and `.state` says why there is none (*Null and `None`*). Use `run()` where a failure must stop the caller.
- **An `Expression` has no failure record, so it cannot report.** `Expression.compute()` and `Expression.run()` raise (`contracts/expressions.md`). A Cell records its Expression's failure and delivers it by the rule above.

**A failure is remembered on the handle, never in the substrate.** This is the Cell-side counterpart of "Expression failures are not cached" (`contracts/expressions.md`):

- **standalone** — on the Cell (`_standalone_exception`), reset whenever the recipe changes: a new input (`_replace_input_ref`), a new `celltype`, a new `validator` or `validator_language`;
- **bound** — on the Context node, where `clear_exception()` also drops the stored demand result, releases its lease and re-derives.

So **a new Cell built on the same recipe never inherits an old failure.** Keying a failure by expression identity in the substrate would have exactly the opposite effect, and would poison a checksum for every later reader.

The checksum shown by a `CacheMissError` is the one whose buffer was missing. In a chain of expressions, that can be an inner input rather than the Cell's own.

**`Cell.exception` holds a string**, as `Transformation.exception` does — one convention across Cell, Pin and Transformation. *Verified:* the standalone getter returns `str(...)` of the stored failure, and `BoundCellBackend.exception` does the same for the node's. One consequence: `CacheMissError`'s checksum reaches the Cell as **prose only**. The jobserver error envelope's split between `message` (for a person) and `checksum` (for code) therefore has no machine-readable arm on the Cell: `exc.args[0]` is a `Checksum` on the `CacheMissError` that `.value` *raises*, but not on the string that `.exception` *holds*. **Whether every `.exception` string carries the exception class name (`<Class>: <message>`)**, as ruled for compiled pins, **is deferred**; today a `CacheMissError` becomes the bare checksum string.

**`.state` and `.exception` are passive inspection in both modes.** They never evaluate a recipe, wait for work, or fetch a buffer. Standalone, an unevaluated recipe is `waiting` with `.exception is None`; a literal dummy result can be `complete` without evaluation. After a recipe change, inspection discards any stale result or failure but does not compute the new recipe. `clear_exception()` makes `.exception` return `None`; a deterministic failure reappears only after a pulling read or explicit computation. The same holds for a handle to an anonymous cell, whose state and failure are its own (*Reads*, *Anonymous and projection handles*).

## State and `block_reason` (bound)

The state machine is `contracts/node-state-lifecycle.md`; this section states only what a Cell handle reports. `.state` is one of the seven node states on a named bound Cell (a cell node is never observed `computing`), and one of `unwired`, `miswired`, `waiting`, `complete` and `failed` on a standalone Cell or on a handle to an anonymous cell. `block_reason` is **bound-only**; on a standalone Cell it raises `AttributeError`.

**`block_reason` is shaped by the cell's inputs, never by its state**, so the form to expect is known from the graph alone (`contracts/node-state-lifecycle.md`, *Where each form is visible*, is the canonical statement):

- **A cell whose only input is at the root reports a single value** from the five-member domain below when it is `unwired`, `miswired` or `blocked`. The `block_reason` of a cell with **no input at all** (no producer, no edge) is unspecified (`contracts/node-state-lifecycle.md`, *Unspecified*); today it is `None`.
- **A cell with one-level inputs — a join — reports a dict** keyed by edge path, a detached copy:
  - **Entries:** one per input that is neither `complete` nor `waiting`.
  - **Values:** exactly one of `miswired`, `unwired`, `blocked-by-miswiring`, `blocked-by-unwired` and `blocked-by-error`.
  - **Label:** the cell's category is the maximum of the values under the precedence `miswired > unwired > blocked-by-miswiring > blocked-by-unwired > blocked-by-error` — topology before values. There is no separate "winning category" field.
  - **There is no `"<root>"` key.** A cell with sub-path edges has a literal root, never a root edge (*Cell-level joins*).
- **A cell that is itself `waiting` reports `None`**, as does one that is `complete` or `failed`.

`tf.result.block_reason` is the ordinary cell reading of a transformer's result endpoint; the transformer's own dict is `tf.block_reason` (`contracts/pins.md`).



## Work: which calls compute and which never do

| Call | Does work? | Returns |
|---|---|---|
| `.source`, `.celltype`, `.input_celltype`, `.path`, `.path_python` | no | configuration |
| `.checksum` | standalone, and on an anonymous or projection handle: evaluates its recipe and upstream Cell/Expression links (a handle over its parent's checksum), never starts a Transformation, never waits on a bound parent; bound named node: reads the current result only | `Checksum` or `None` |
| `.buffer`, `.value` | resolve the result checksum; never fingertip | the buffer / value; `None` when there is no result checksum, a recorded failure included (bound named node: whenever it is not `complete`); raises a failure to materialize an existing result, which is never recorded |
| `.state` | no evaluation; reports the current state | lifecycle state |
| `.exception` | no evaluation; reports the stored failure | the failure string, or `None` |
| `.block_reason` (bound only) | no evaluation | `None`, a reason, or a dict (*State and `block_reason`*) |
| `build()` / `expression()` / `cell()` | no | an immutable `Expression` |
| `compute()` | **yes** — standalone, starts missing upstream work; bound named node, waits on the Context barrier; anonymous or projection handle, evaluates over the parent's current checksum without waiting on the parent | the result `Checksum`, or `None`; never raises for a failure or a node state (*Failures*) |
| `await compute_async()` / `await computation()` | **yes** | the result `Checksum`, or `None`, as `compute()` |
| `run()` | **yes** — compute, then materialize | the value (`None` on a handle whose parent has no checksum); raises the recorded failure, `NodeError` on a bound named node that settled `unwired`, `miswired` or `blocked`, and any materialization failure |
| `with_input()`, `as_celltype()`, `item()`, `slice()`, `with_validator()` | no (bound `item()`, `slice()`, `as_celltype()` create an anonymous node, *Connecting*) | a new Cell |
| `fingertip()` | **yes** — resolve, else recompute from provenance, locally, even while a job server is active (`contracts/scratch-witness-audit.md`, case 2); never starts the Cell's **own** evaluation | the recovered buffer, or `None` when there is no result checksum |
| `clear_exception()`, `prune()` | no evaluation | `None` |

Notes:

- **Reading is the only thing that makes a *standalone* Cell compute**; it has no scheduler of its own (*Reads*, *Laziness*). A **bound** Cell computes without being read, because its Context does it.
- `compute()` is the explicit operation that starts missing upstream work; `.checksum` is not. `computation()` is `compute_async()` under its Context-facing name.
- **`compute()` / `compute_async()` never raise for a failure, in either mode.** They return `None`, and the failure is on `.exception` — recorded by that call standalone, by the Context bound; `run()` re-raises it (*Failures*, *How a failure is delivered*). A **bound** `compute()` / `compute_async()` on a named node waits on a Context barrier, and `timeout=` is meaningful there (a barrier timeout raises `TimeoutError`; `contracts/workflow-context.md`); a node that settles in any state but `complete` gives `None`. On an anonymous or projection handle it never waits on the parent: with no parent checksum it returns `None` without raising, and `timeout=` bounds only the wait for the handle's own dispatched evaluation. Work performed in place on a running loop cannot be interrupted by that timeout (*Reads*, *Anonymous and projection handles*).
- `compute(input_ref)` / `run(input_ref)` / `build(input_ref)` accept a one-shot input override, type-checked like a constructor input, that does not mutate the Cell. The **parameter** is still spelled `input_ref` (as on `Expression`); only the retired *attribute* of that name raises.
- All of these default to `execution="auto"`; placement is in `contracts/expressions.md`.
- **`.path` and `.path_python` are the same string.** `.path` is the path as stored — `""` at the root, dotted for identifier keys and bracketed otherwise (`contracts/expressions.md`, *Path syntax*) — and `.path_python` is an **exact alias** in both modes, kept because the bound backend protocol requires the name (`BoundCellBackend.path_python = path`; `Expression.path_python` returns `self.path`).
- **`.path` is read-only in both modes.** Assigning it raises `AttributeError`; add a path by projecting, which returns a child Cell.
- **The builder methods return new Cells and never mutate.** On a **bound** Cell, `item()`, `slice()` and `as_celltype()` return handles to **anonymous** bound cells linked to the parent (*Connecting*), while `with_validator()` and `with_input()` return a *standalone* Cell built on the bound cell's current Expression snapshot (`BoundCellBackend.derive`). Re-aiming a bound cell in place is a Context write, not a derivation.

## Projections

Attribute, item and slice reads navigate uniformly in both modes, and each returns a derived Cell carrying one more normalized path step:

```python
cell.foo   cell["foo"]   cell[0]   cell[1:4]
ctx.a.foo  ctx.a["foo"]  ctx.a[0]  ctx.a[1:4]
```

**A projection selects within the value read at `input_celltype`; `celltype` then converts only what the projection selected — never the whole value before the path is walked.** This is the Cell-side statement of Expression evaluation order; `contracts/expressions.md`, *Application order*, owns the rule, with the reason the order is not cosmetic and a worked example in Expression terms.

For example, take a `Cell("text")` holding `[10, 20, 30, 40]` as text. `cell[3].as_celltype("plain")` selects item `3` of the **text** — the character `','` — and renders that as `plain`. `cell.as_celltype("plain")[3]` converts the text to `plain` **first**, closing that Expression, and then selects item `3` of the resulting **list** — the integer `40`. The two spellings are different recipes, and each means what it reads as: `as_celltype` fixes the celltype from that point in the chain onward, so a path written after it walks the converted value, and a Cell is a *chain* of Expressions wherever a conversion is followed by a projection.

*Verified, standalone:* `Cell.item`, `Cell.slice` and `Cell.as_celltype` each build a child `Cell(source=self)` carrying one path step or one conversion, so the two spellings are two different chains.

**Projection and `as_celltype` both return a child Cell linked to the parent.** `cell[3]` is a child Cell whose *source* is `cell`, carrying the path; `cell.as_celltype(ct)` is a child Cell whose source is `cell`, carrying the conversion. Bound, the child is an anonymous cell whose link names the parent (*Connecting*). Three things follow:

- **Paths come only from projecting**, so the builder stays a chain. There is no path-carrying Cell without a parent link.
- **The wiring invariant holds standalone too.** `cell[3].as_celltype("plain")` is two cells and two links, not one cell carrying both; so **binding is a move, not a decomposition** — the chain that goes into the Context already has the shape the graph requires, one symbol-table entry per anonymous link.
- **`.source` on a standalone projection answers the parent Cell.** Bound, `.source` answers the resolved edge instead (*The input*).

This costs nothing at evaluation time: a run of path links fuses back into one Expression (`contracts/expressions.md`, *Fusion*), which is why fusion has to be unconditional rather than an optimization.

**API-name arbitration: normal Python lookup wins.** `__getattr__` projects only for a name that is not statically defined on `Cell` or its bases. A bound-only member whose getter raises `AttributeError` on a standalone Cell (`mount`, `share`, `block_reason`) must *not* fall through to a same-named projection, so `Cell.__getattr__` consults `_class_attribute` and re-raises rather than projecting. Names starting with `_` never project. Item access is the escape hatch: `ctx.a["value"]`, `ctx.a["run"]` and `ctx.a["share"]` are ordinary projections of data fields with those names. Cells have no `.pins` API, and `pins` is not reserved, so `ctx.a.pins` is an ordinary projection.

**A Cell is a handle, and says so.** `==`, ordering, `bool()`, `len()` and iteration raise `ProjectionError` — which subclasses both `TypeError` and `AttributeError` — on **every** Cell, and on every Pin, which shares `CellBase`. Handle identity carries no meaning, so comparing a Cell to a value, or to another Cell, is always a mistake, whether or not a path is involved. **There is no separate projection class**: the guard lives on `CellBase`, and the message adapts to the object — on a Cell carrying a path it names the path and suggests the misspelling that attribute projection makes silent (`ctx.a.vlaue`), and on one without a path it says to read `.value`. One gap has no fix: `is None` compiles to a pointer comparison with no protocol to intercept, so `assert ctx.a.vlaue is not None` still passes.

*Verified:* the guards are defined on `CellBase` (`_not_a_value`), which `Cell` and `Pin` share. `CellBase.__hash__` stays identity-based, so handles can be dict keys and set members. **Membership in a list is not safe**, however: `x in [cells]` compares by identity first and then with `==`, so it raises `ProjectionError` as soon as it compares `x` against a member that is not the identical object. Set and dict membership use the hash and identity, and do not raise for a present member.

**Projection depth is unlimited; connection targets are not.** A projection path may be arbitrarily deep wherever the underlying Expression path and source celltype support it. A **connection target** — a graph location that may receive a bound source — is the **root or one level below it, and nothing deeper**. A one-level target is a single point selection: a mapping key, an attribute name, or an integer sequence index. A slice may be read or value-updated but is never a connection target, because it denotes several positions. `ctx.a.b.c = ctx.x` raises `PathError: Cell connection targets are limited to one point component`.

A mapping-key connection can bootstrap an unwired cell as a mapping. An integer-index connection requires an existing compatible sequence; it never infers or grows a list, and the check happens when the join is evaluated, which fails with `TypeError("Integer Cell connection targets require an existing sequence")`. This holds for a `mixed` join exactly as for a `plain` one: an integer target over a mapping root is refused, never stored under a string key (*Cell-level joins*).

**A connection target key is a string or a non-negative integer.** A negative integer, a `bool`, a key of any other kind, and the reserved names `"<root>"` and `"<numeric>"` are refused at assignment, before the graph changes. An edge with such a target that arrives through a loaded graph makes the cell `miswired` (`contracts/node-state-lifecycle.md`). The two names are reserved because a join's inputs are recorded under them (*Cell-level joins*). **The exception classes are deferred**; rely only on the assignment raising. A join whose targets mix integer and string keys is not refused at assignment: no cell join is formed, and the join is `failed`. Value writes are not connection targets and keep Python's rules: `ctx.a[-1] = 5` updates the last item of the root value.

**A sub-path write is an atomic read-modify-set of the root value**, not persistent path-overlay state and not a sub-value producer. One serialized transaction:

1. check that no incoming edge targets the root or an ancestor of the path;
2. read a **detached** copy of the current resolved root value;
3. apply ordinary Python container mutation along the path;
4. re-serialize and commit the changed aggregate as the root, preserving every unrelated one-level incoming edge.

**It needs the current value to be materializable.** When the bound node is `waiting`, the write waits on a barrier and retries (a sub-path write only ever targets a cell node, and a cell node is never `computing`). Otherwise a root with no checksum raises **`ValueUnavailableError`** (`seamless.cell_errors`, importable as `seamless.ValueUnavailableError`), in both modes — except that for a string/attribute path an *unwired* cell is treated as an empty mapping and missing intermediate keys are created as `{}`, so `ctx.a = Cell(); ctx.a.b.c = 12` yields `{"b": {"c": 12}}`. An integer path has nothing to bootstrap from. An explicitly stored `null` is not unwired, and a write under it fails; **the exception class for a write under a stored null is deferred**, bound and standalone. Bound, the commit is optimistically concurrent (base checksum plus node revision): a losing commit is retried, and after eight attempts in total, all lost, the write raises `ConcurrentUpdateError` (`contracts/workflow-context.md`, *Writes through the Context*).

**Augmented assignment** (`+=`, `-=`, `*=`, `/=`) reads the current resolved value and commits through the same single transaction. Because Python writes the result of `__iadd__` back to its owner, the returned handle must be treated as an inert same-endpoint reassignment and must not create a self-edge; a separately retained projection (`p = ctx.a.b.c; p += 1`) performs the same single transaction. So does every write through a projection handle (*Writes through a handle*). `del ctx.a["b"]` deletes the key and, being a detaching delete, also removes any edge targeting that exact path.

**Standalone, the same transaction runs without the controller**: `cell.b = v`, `cell["b"] = v`, `del cell["b"]`, `cell += 1`, and every write through a projection child update `cell`'s root value (steps 2–4 above, synchronously, with no retry since there is no concurrent writer). Authority is checked on the root of the chain, and the materializability rule above applies unchanged (*Writes through a handle*). Whether the attribute spelling `del cell.b` is the same as `del cell["b"]` is deferred.

## Cell-level joins

A **join** is a Cell with one-level sub-path connections, optionally over a **literal** root value:

```python
ctx.join = {}
ctx.join.left = ctx.left
ctx.join.right = ctx.right
```

**A cell with sub-path edges may hold only a checksum at its root — a literal — never a source.** A root edge and sub-path edges on one cell are refused, in either order: `ctx.join = ctx.base; ctx.join["k"] = ctx.other` is refused at the sub-path assignment, and `ctx.join["k"] = ctx.other; ctx.join = ctx.base` is refused at the root assignment, rather than silently detaching the sub-path edge. A literal root with sub-path edges, as above, stays a legal join. **The exception class is deferred**; rely only on the assignment raising.

**Members of a `mixed` or `plain` join convert to the join's celltype before insertion.** For an assignable member, `ctx.j["left"] = ctx.t; a = ctx.j.value` and the root connection `ctx.j = ctx.t; b = ctx.j.value` must give the same value for `a["left"]` and `b` after computation. For example, a `text` source containing `"[1,2]"` contributes the list `[1, 2]` to a `plain` join, not the source string. A heterogeneous member source must be pathless: the conversion cannot share its link with a source projection (*Connecting*). A conversion failure is an evaluation failure, as for a root conversion.

**Deep joins insert member checksums.** For `ctx.d["k"] = ctx.x`, a `deepcell` target requires a `mixed` source; a `deepfolder` or `folder` target requires a `bytes` source. The key must be a string. Other source celltypes are refused at assignment, even if an ordinary conversion would be possible, and the graph is unchanged. An explicitly converted source is legal if its resulting celltype is the required member celltype; this conversion is preserved rather than collapsed into a root conversion. The join inserts the source's checksum as `index[k]`, preserving its identity without resolving or reserializing the member. It does not convert the member to the deep root celltype. For example:

```python
ctx.d = Cell("deepcell")
ctx.x = Cell("mixed")
ctx.x.set({"a": 1})
ctx.d["k"] = ctx.x
ctx.compute()
assert ctx.d.value == {"k": ctx.x.checksum}
assert ctx.d["k"].value == {"a": 1}
```

A literal deep root supplies the base index; unrelated entries remain unchanged. Root-source and sub-path-source edges remain mutually exclusive. Compatibility is checked again when either celltype changes: an incompatible member edge makes the join `miswired`, with no execution exception. Changing the target to an ordinary celltype also invalidates a deep member edge; changing both cells back to a compatible deep/member combination repairs it. Graph serialization preserves this member-insertion intent with `deep_member: true` on the connection, so reloads retain the same miswiring behavior. A compatible but failed member blocks the join with `blocked-by-error`, as for ordinary joins.

**A join is evaluated as a cell join.** Once every member is complete, the Context forms one **cell join**: an Expression of its own kind, whose input is the dict of the join's input checksums. The root is entered under `"<root>"` and each member under its key, and `"<numeric>"` marks a join whose keys are integer indices. `contracts/expressions.md`, *Cell joins*, owns the definition. Its identity is the pair `(celljoin checksum, celltype)`, so a join is content-addressed: the same root and members at the same celltype are one cell join in every Context and every process, and it is recorded, cached and deduplicated like any other Expression. **There is no Transformation behind it.** (The design text in `context-internals-followup-design.md` that a join "may require a join `Transformation` followed by a projected `Expression`" is superseded.)

**The root has the same status as a member.** A literal root whose `input_celltype` differs from the join's `celltype` (*The 3×2 matrix at the root* lists the three acts that make them differ) is converted to the join's celltype before it enters the cell join, exactly as the same literal is converted on a cell without sub-path edges. The conversions of the root and of the members are evaluated in this process and are never dispatched (`contracts/expressions.md`, *Cell joins*).

**Where a join is evaluated.** A `mixed` or `plain` join is evaluated in this process when all its inputs are local, dispatched when all of them are on the hashserver, and evaluated in this process again when each input is in one of those two places, fetching the ones that are not local. A deep join is a `deepcell` or `deepfolder` cell join, a `folder` join being a `deepfolder` one with byte-identical results. It is always evaluated in this process and needs no member buffer, however large the members are: only the root index, when there is one, must be reachable from here.

**Inputs are expected to be small and reachable.** An input that is neither in this process nor on the hashserver fails the join with `CacheMissError`, and an ordinary evaluation does not fingertip it. So a scratch cell or a scratch transformer that feeds a join directly, and whose result was computed elsewhere, fails the join: **do not scratch what feeds a join.** A member edge that carries a path is protected from the join Cell's own policy: the last link of `ctx.j["a"] = ctx.big[3]` is a non-scratch value request whatever the join Cell's `scratch`, so the projection is evaluated where the data is and a dispatched one writes its result to the hashserver. A fingertip is the exception to the cache miss. `fingertip()` on a join's result walks through the cell join and fingertips its inputs like those of any other link (`contracts/scratch-witness-audit.md`).

Observable behaviour:

- the value is correct, and it is the value of the assembled aggregate at the Cell's own `celltype`;
- it recomputes reactively when an upstream changes;
- reverting an upstream reproduces the checksum;
- a failure of the join's own work makes it **`failed`**, and is not cached: a conversion of the root or of a member, an integer key over a root that is not a sequence, or an input that is in neither store;
- like any Cell's, the join's result checksum does not imply a result buffer (*`.buffer` and `.value`*). A recorded result completes the join without evaluating it, and a dispatched join under a scratch Cell leaves its buffer on the executing side;
- an upstream that is stuck leaves the join **`blocked`**, never `failed`, with a `block_reason` dict naming each stuck edge (*State and `block_reason`*): a failed or error-blocked upstream gives `blocked-by-error`, an unwired or unwired-blocked one `blocked-by-unwired`, and a miswired or miswiring-blocked one `blocked-by-miswiring`. An upstream that is still progressing contributes no entry, so a join whose other members are all complete stays `waiting`. A member edge that is itself missing or ill-formed makes the join `unwired` or `miswired`, not `blocked`;
- **no transformation is observed** — not in the observation log, not in the transformation cache;
- the node goes straight from `waiting` to `complete` and is **never seen `computing`**, wherever the cell join is evaluated, because `computing` belongs to the transformer path alone;
- `build()` on a join does **not** return a recipe: with no root edge to follow, it snapshots the join's *current* checksum as a dummy Expression.

## Deep celltypes on a Cell

A Cell whose `celltype` or `input_celltype` is `deepcell`, `deepfolder` or `folder` is restricted, because an Expression's cost class must be a function of its identity tuple and never of the data behind the checksum: exactly **one string-item step**, and a short list of index-level conversions. The table, the member-celltype rules, the flatness requirement and the reasons are in `contracts/deep-celltypes.md`; `module` is not a deep celltype. Keys are opaque strings that routinely contain `/`, so the step usually has to be written in bracket form.

*Verified:* `validate_expression_shape` admits the deep zero-path conversions and the one string-item step and refuses every other shape at construction; the conversion engine evaluates the free deep conversions and `folder → mixed`; and `validate_deep_structure` is the shared flatness validator. On a **standalone** Cell, a one-step projection of a deep parent carries the member celltype (`mixed` for `deepcell`, `bytes` for `deepfolder` and `folder`), and `as_celltype` to a legal deep target works like any other conversion. Bound, a one-step projection carries the member celltype too, as a handle and as a named cell. Writes at and below `k` are in *Writes through a handle*.

**`.value` on a deep Cell is the index.** Requesting the value of a deep checksum yields its index at every layer, with each member presented as a `Checksum` object — `{key: Checksum}` (`contracts/deep-celltypes.md`, *What a deep buffer is*). `.value` resolves through `Checksum.resolve(celltype)` → `Buffer.get_value(celltype)`, which maps `deepcell`/`deepfolder`/`folder` to `plain` (`Buffer._map_celltype`) before parsing, and then validates and wraps the flat index (`validate_deep_structure`). Nothing is resolved and no member buffer is touched: wrapping a hex in a `Checksum` is typing, not resolution. `.buffer` agrees: `CellBase.buffer` validates against the same mapped celltype, so it returns the index buffer.

**The typed route to a single child is the one-step path** (`cell["path/to/file"]`, `contracts/deep-celltypes.md`, *Paths*); indexing the `.value` dict yourself gives the same child `Checksum`.

## Implementation status and current limitations

The rules above are the test oracle; where the code or an older design text disagrees with them, the rules win.

### Contract alignment

The former gaps in bound scratch policy, wiring, join conversion, null writes, reads and named barriers now satisfy the contract. Focused coverage is in the Cell alignment tests in `seamless-core` and `seamless-workflow`, the bound Cell and wiring contracts, and the expression-result read tests. These are plain tests; no contract-gap xfail marks remain in those files.

Expression fusion and elision across named and anonymous intermediates satisfy the contract. Focused coverage is in `seamless-workflow/tests/test_contract_bound_fusion.py` and `seamless-workflow/tests/test_contract_cells_handles.py`.

### Gaps

- **Cell joins are not yet integrated into the Context** (*Cell-level joins*; `contracts/expressions.md`, *Cell joins*). Canonical celljoin formation, parsing and the pure evaluator are implemented in `seamless-core`, but a workflow join is still assembled in-process: `Context._derive_cell` hands `sidework.evaluate_cell` to `_demand`, which runs it in a worker thread under a per-Context memo key, and `evaluate_cell` calls `Checksum.resolve`, `_assign_path` and `checksum_for_value`. There is no cell join identity, no database row, no placement and no fingertip route through a join. The following behaviours differ from the contract in the meantime:
  - a literal root whose `input_celltype` differs from the join's `celltype` is not converted, so a `text` root under a `plain` join fails with `'str' object does not support item assignment`;
  - a member connected through an explicit `as_celltype` is not converted to the join's celltype: `ctx.j["k"] = ctx.p.as_celltype("text")` into a `plain` join inserts the string;
  - a member conversion is requested under the join Cell's own scratch flag and may be dispatched;
  - a member edge's own link carries the join Cell's scratch flag as a checksum request, so a projected member under a scratch join Cell may be dispatched as scratch and end up unreachable;
  - forbidden connection target keys are accepted: a reserved name is an ordinary key, `-1` sets the last item of a sequence root, `True` sets item 1, and a `float` or `None` key is stored under its string form.

### Current limitations (not gaps)

- **Validators are deferred.** `validator` and `validator_language` are accepted by the constructor, by `with_validator()` and by `CellConfig`, and are excluded from Expression identity, but every evaluation entry point raises `NotImplementedError("Expression validators are not implemented yet")`, which a Cell records as `.exception` (wrapped as `WorkflowExecutionError`). The reject-only semantics are settled; nothing writes the database's validator columns. A validator must be a `Checksum` (or hex); a validator given as source text fails with a `fromhex` error, not a useful message.
- **Standalone `clear_exception()` does not clear a memoized result.** It clears only `_standalone_exception`, and inspection stays passive: `.exception` remains `None` until a pulling read or explicit computation meets the failure again.
- **`context-internals-followup-design.md` is stale on two points.** It makes `.checksum`, `.buffer` and `.value` bound-only (superseded by the standalone-read contract above), and it makes a projection's `input_ref` its owning root endpoint (that meaning belongs to the private `_input_ref`; the public split is `.source` / `.checksum`).

## Open questions

The author has deferred these. Do not rely on either answer; where a test exists, it asserts only that the operation raises.

- **Exception classes** for: a root edge combined with sub-path edges (*Cell-level joins*); a write under a stored null, bound and standalone (*Projections*); a write below `k` under a deep parent (*Writes through a handle*).
- **Retype-refusal text.** Whether `Cannot convert behind a projection; use as_celltype()` is contract (*Connecting*).
- **Handle state over an unwired parent.** When a handle reports `unwired` rather than `waiting` (*Anonymous and projection handles*).
- **`block_reason` of a cell with no input at all.** Owned by `contracts/node-state-lifecycle.md` (*Unspecified*) (*State and `block_reason`*).
- **`.exception` string format.** Whether every `.exception` string carries the class name (*Failures*).
- **Standalone `del c.b`**, the attribute spelling of `del c["b"]` (*Projections*).
- **Connection target keys** (*Projections*): the exception classes for a forbidden key.

*Resolved 2026-09-28:* bound `.buffer` / `.value` on a `failed` named node. Reads and `compute()` answer `None` for a recorded failure in both modes, and `run()` raises it (*Failures*, *How a failure is delivered*).

## Non-goals

- **Execution.** A Cell has no code, no environment, no pins and no dunders. Anything that needs one is a Transformer (`contracts/transformers.md`).
- **Handle identity.** Handles are views. Two handles for one node are equal in effect and identical in nothing; nothing may be keyed on a handle's identity, and no operation depends on a particular handle object (*Connecting*, *Assigning an anonymous handle*).
- **Deep connection targets.** One level below the root, by design: a deeper target would be a producer of a sub-value, which the read-modify-set model exists to avoid.
- **Persistent sub-path overlays.** A sub-path write is a transaction on the root value, not a stored per-path input.
- **Fingertipping from a property.** `.buffer` and `.value` never recompute a missing buffer. `fingertip()` is the explicit method; `contracts/scratch-witness-audit.md` defines fingertipping and where it happens.
- **Value identity.** A Cell names a checksum, not a value. One value may have several checksums, and identity stays with the checksum (`contracts/identity-and-caching.md`); a Cell never re-serializes a result to normalize it, and `==` between two Cells is not a value comparison.
- **Failure caching.** A Cell failure lives on the handle for as long as the recipe does, and nowhere else.
- **The node state machine.** Derivation, the cascade and the block-reason precedence belong to `contracts/node-state-lifecycle.md`. This page states only what a Cell handle reports (*State and `block_reason`*): standalone — and on a handle to an anonymous cell, whose state is its own — `.state` is one of `unwired`, `waiting`, `complete`, `failed` and `miswired`, and `.block_reason` is bound-only.
