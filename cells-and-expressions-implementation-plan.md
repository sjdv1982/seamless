# Implementing `Cell` And `Expression`

> A high-level, contract-oriented plan. It fixes the *what* and the *why* — the
> primitives, their identity, their guarantees, and how they compose with the
> existing transformation DAG. It deliberately does not prescribe a code recipe;
> the implementing agent owns the *how*.

## Summary

This plan adds two new primitives, `Expression` and `Cell`, as the
**structural-layer** counterparts of the existing **compute-layer** primitives
`Transformation` and `Transformer`. The four form a clean 2×2:

| layer | mutable builder | immutable definition |
|------------|-----------------|----------------------|
| compute | `Transformer` | `Transformation` |
| structural | `Cell` | `Expression` |

The mutable column (`Transformer`, `Cell`) is what a user configures and
navigates. The immutable column (`Transformation`, `Expression`) is the
content-addressed, referentially transparent record of a computation that the
cache, the database, and fingertipping key on. The relationship within each row
is identical: a mutable builder, when *built*, snapshots its current inputs into
an immutable definition. Building is functional and one-shot — a later mutation
of the builder never reaches back into a definition already built. Resolution is
a property of the immutable definitions and their checksum futures, **not** of the
builders: a `Cell` or `Transformer` is *built*, never *resolved*.

An `Expression` is best understood as **a transformation whose code is a fixed,
closed, pure codebook** — get-attribute, get-item, slice, and celltype conversion
— instead of arbitrary user code. Because the codebook is finite and pure, an
expression needs **no execution environment, no worker, and no orthogonal
execution envelope at all**. It resolves to a result checksum by structural
navigation, frequently *without materializing* the input buffer, at effectively
zero cost.

`Expression` and `Transformation` are nodes in **one lazy, content-addressed
DAG**, each producing a **checksum future**. The edges are symmetric:

- an expression's input may be a concrete checksum, a transformation future, or
  an expression future;
- a transformation pin may now take an expression future, in addition to the
  concrete checksums and transformation futures it already accepts.

Composition is by object reference (the future/edge), not by a nested expression
*object*: each `Expression` stays a flat `(input-ref, path, celltypes)` node, and
chaining is done by making one node's input be another node. The reactive graph
(legacy Seamless's `Context`) is intentionally **not** part of this layer; it is
reintroduced later, on top of this functional substrate, and is sketched in the
appendix. Keeping reactivity out of the immutable layer is the same
separation-of-concerns discipline the transformation-immutability hardening
established.

### Handoff-ready self-check

- The contract is explicit: immutable, content-addressed `Expression`; mutable,
  functional `Cell`; both unified with the existing transformation DAG via
  checksum futures.
- Expression identity is a **queryable composite key**, not a single derived
  checksum — because that composite key is the reverse-resolution index
  fingertipping walks.
- The load-bearing / orthogonal split from the transformation contract is reused:
  `path` and both celltypes are load-bearing; the `validator` is an orthogonal
  reject-not-coerce gate.
- The frontend is unified (one resolve/compute/await/cancel surface), but
  **dispatch branches by node kind**, because an expression is zero-cost and
  envelope-free.
- Validator behavior and result-identity (determinism) are settled contracts, with
  one residual question each, recorded explicitly.

## Why `Expression` Is A Transformation-Shaped Object

This section records the reasoning the rest of the plan rests on.

### The same shape, already

The persistence layer already carries an `Expression` table and a reverse-index
request, in stub form. That is evidence, not coincidence: the correspondence to
the transformation cache is literal, not loose.

| | `Transformation` | `Expression` |
|-------------------|------------------------------------------|------------------------------------------------------------|
| **identity** | `tf_checksum` (serialized code + inputs + load-bearing dunders) | composite `(input_checksum, path, celltype, target_celltype)` |
| **forward cache** | `tf_checksum → result` | composite key `→ result` |
| **reverse index** | `rev_transformations` | `rev_expression` |

Both are two-level, content-addressed `definition → result` caches with a reverse
index for provenance and fingertipping. At the cache level, an expression simply
**is** a transformation-shaped object.

### Everything heavy about transformations comes from the code being arbitrary

A transformation's code is arbitrary, and that single fact drags in the entire
orthogonal execution envelope: a language interpreter, an environment, a worker,
resource bounds — `__env__`, `__compilation__`, `__meta__`, `metavars`, and the
`process`/`spawn`/`jobserver`/`daskserver` dispatch machinery.

An expression's "code" is the opposite — a finite, pure, structural codebook.
Therefore:

- it has **no envelope**: nothing about *where/how* it runs is configurable,
  because there is nothing to configure;
- it can be evaluated **server-side**, inside the database/hashserver, by
  structural navigation — which is why the persistence stubs already live there;
- over a **deep checksum**, an attribute/item access is just selecting a
  sub-checksum out of the Merkle manifest — the parent buffer is **never
  materialized**. Expressions are the *projection/access* dual of transformations'
  *compute*: transformations make new values, expressions name sub-values without
  recomputing or materializing them ("precisely define without materializing").

### Expressions are the *easy* instance of the immutability model

The immutable-definition / mutable-result-promise decomposition just hardened for
`Transformation` applies to `Expression` directly — and `Expression` is its
limiting, simplest case, because removing the envelope and the work removes
exactly the parts that made transformations hard:

- **No envelope ⇒ the entire latch-on/`strict` concurrency problem dissolves.**
  Two concurrent evaluations of the same expression are envelope-identical by
  construction, so they idempotently agree. The situation that made transformation
  concurrency hard — two different envelopes contending for one `tf_checksum` —
  cannot arise.
- **Near-trivial result promise ⇒ effectively no cancellation surface of its
  own.** An expression is "almost all immutable definition, almost no promise." The
  only thing worth cancelling is an *upstream* dependency.
- **Zero compute cost ⇒ zero eviction cost**, consistent with the existing
  eviction-cost stub for structural conversions.

Expressions therefore *validate* the model imposed on transformations: they are
what a transformation looks like once you strip the envelope and the work.

### Identity at construction; result after dependencies

This is the property that lets the two kinds share one DAG. An expression's
*identity* (its composite key) is fully determined the moment you state
`(input-ref, path, celltypes)`. Its *result* is known only once the input
resolves. When the input is a transformation future or another expression future,
the expression is "constructed but not yet keyed": forming its cache key needs the
input's **result checksum**, so keying waits on the upstream — exactly as a
transformation parent checksum waits on its dependency results. Same lazy-edge
model, reused unchanged.

## Identity And Classification (`Expression`)

Expression identity is a **composite key**, not a single checksum:

```text
(input_checksum, path, celltype, target_celltype) -> result
```

### Why a composite key, not a single derived checksum

A single hashed `expr_checksum` would only "look neat" and would actively *lose* a
property the system needs. The composite key is the **reverse-resolution index
that fingertipping walks**: `rev_expression` maps `result → {input_checksum, path,
celltype, target_celltype}`, so a missing result can be rematerialized by finding
the expression that produces it, recursing to fingertip its input, and re-applying
the path. A single opaque checksum would force a separate decomposition table to
recover those four fields — i.e. you would rebuild the composite key anyway. The
composite key is not denormalization; it *is* the navigable structure that makes
reverse-resolution possible. **Decision: keep the 4-field composite key as the
canonical identity; do not introduce a single derived expression checksum.**

### Load-bearing (determines the result; part of identity)

- **input identity** — the input's **result checksum** (immediate for a concrete
  input; resolved-after-upstream for a future input).
- **`path`** — the ordered operations and their arguments (attribute name, item
  index/key, slice bounds).
- **`celltype`** — the source interpretation of the input bytes; not derivable
  from the bytes in general (the same bytes mean different things as `binary` vs
  `plain` vs `mixed`).
- **`target_celltype`** — the interpretation/serialization of the result; the
  structural-layer analog of a transformation's `__output__`/`__format__`.

### Orthogonal (carried, but excluded from identity)

- **`validator` / `validator_language`** — see the dedicated contract below.

### Derived/eliminable

- None.

## The Validator Contract (settled, with one residual question)

A validator is an **orthogonal gate**. It may cause an expression to **fail**, but
it must **never change the value the expression denotes**. Consequently it is
**excluded from identity**: two expressions that differ only in their validator
share one key and one result. This is the structural-layer instance of the
orthogonality keystone established for transformations — anything that can change a
*successful* result value is load-bearing, never orthogonal. A "validator" that
coerces or normalizes a value is a contract breach; that behavior must be expressed
as a load-bearing `path`/conversion instead, not smuggled into a validator.

**Residual question:** a validator carries a `validator_language`, so it is itself
code, yet expressions are meant to be envelope-free and zero-cost. *Where* a
non-trivial validator runs is open, and must not quietly reintroduce an execution
environment into the structural layer. Whatever the resolution (restrict
validators to cheap/structural checks; run them co-located with the result; or
model a validating expression as a tiny transformation that reuses the compute
layer), the invariant above — reject yes, coerce never — must survive it.

## The Result-Identity Contract (settled, with one residual question)

Expression evaluation is **deterministic**: the same `(input, path, celltypes)`
always denotes the same result. The forward cache is therefore an **idempotent
memo** — re-deriving overwrites with an identical checksum. Crucially, unlike a
transformation an expression has **no environment**, so it cannot be
"environment-sensitive": a differing result for the same key is not
irreproducibility, it is corruption.

**Residual question:** decide whether expressions deserve a forensic path
analogous to `IrreproducibleTransformation`, or whether the cheaper stance —
"structural ops cannot be irreproducible, so a mismatch is a hard error" — is
acceptable. This is a deliberate choice to make, not an oversight to leave
implicit.

## Operations Codebook

The codebook is closed, pure, and environment-free: **get-attribute**,
**get-item**, **slice**, and **celltype conversion**.

- An **empty `path`** is the pure cell-to-cell conversion (source → target
  celltype, no access).
- Over a **deep checksum**, attribute/item access is structural navigation of the
  manifest — the result sub-checksum is selected **without materializing** the
  parent buffer. This is the cheap, high-value path and the reason expressions can
  resolve server-side.
- For **non-deep** cells, a non-empty `path` requires materializing the input to
  apply the operation; the established constraint restricting a non-empty `path` to
  `mixed`/`plain`/`binary` sources holds.

## `Cell` (Mutable Builder, Functional)

A `Cell` is the mutable, reassignable, user-facing handle of the structural layer.
It is to `Expression` what `Transformer` is to `Transformation`.

### Navigation returns Cells; calling builds the Expression

This shape mirrors `Transformer` exactly:

- **Navigation stays in the mutable layer.** `cell.attr`, `cell[i]`, and
  `cell[a:b]` each return **another `Cell`** — a derived Cell that has accumulated
  one more step of access path over the same underlying input reference. Nothing
  is built, snapshotted, or evaluated. Chaining keeps accumulating: `cell.a.b[0]`
  is a Cell with `path = ["a", "b", 0]`. A Cell also carries a `celltype`;
  targeting a different celltype yields a derived Cell whose eventual build is a
  conversion.
- **Calling/running builds the `Expression`.** `cell()` or `cell.run()` is the
  moment the immutable `Expression` is constructed from the Cell's then-current
  `(input-ref, path, source celltype, target celltype)` and resolved. `cell()` /
  `cell.run()` return the value; a `cell.compute()` sibling returns the result
  checksum, mirroring the `Transformation` handle.

| | navigate / configure (mutable, returns builder) | build (immutable definition + resolve) |
|---------------|-------------------------------------------------|----------------------------------------|
| `Transformer` | set `.code`, `.schema`, pins, `.meta`, … | call the transformer → `Transformation` |
| `Cell` | `cell.attr`, `cell[i]`, `cell[a:b]`, celltype | `cell()` / `cell.run()` → `Expression` |

### "Build time" and the snapshot contract

**"Build time" is the build call** — the moment a mutable builder produces an
immutable definition. For `Cell` that is `cell()` / `cell.run()` (not `cell.attr`,
which only returns another Cell). For `Transformer` it is the transformer call.
Build time is distinct from **compute/resolve time** (when the definition's
checksum future is actually resolved — possibly later, possibly remotely). The
snapshot happens at build, not at compute.

Two precisions that make this load-bearing point unambiguous:

1. **What is frozen at build time is the Cell's current base reference — the thing
   it points at — not the Cell itself.** If the base is a concrete value, the build
   snapshots its concrete checksum; if the base is an `Expression`/`Transformation`
   future, the build wires a frozen dependency *edge* to that definition — never a
   live pointer to the mutable Cell. Either way, reassigning the Cell afterward
   cannot reach back into the already-built `Expression`. That is the whole
   functional guarantee, carried over verbatim from `Transformer → Transformation`.
   (The Cell is never itself "resolved"; only the definitions its base may point at
   resolve.)
2. **"Build-once" means one snapshot *per build*, not one build per Cell.** A
   single Cell can feed many builds; each produces its own independent immutable
   snapshot. Rebuilding the same Cell after a reassignment yields a new, separate
   node. (This is precisely the seam the reactive `Context` exploits: reactivity =
   re-build with fresh snapshots — see appendix.)

### Composition

In the functional layer, the edges of the DAG are **always** concrete checksums or
immutable-definition futures (`Expression`/`Transformation`) — never builders. A
`Cell` participates only by being **built** into an `Expression`; that `Expression`
future is then what flows along an edge, symmetrically with a `Transformation`
future (a transformation pin may take an expression future, and an expression's
base may be a transformation future).

Passing a **`Cell` (or `Transformer`) itself** as the input to another
`Cell`/`Transformer` is **strictly** a feature of the upcoming `Context`:
builder-to-builder wiring lives only there, where the `Context` resolves each such
binding into concrete `Expression`/`Transformation` evaluations on every tick. The
functional layer has no builder-valued edges.

## Frontend And Dispatch

The resolve surface is **unified** with `Transformation` — `.compute()` (→ result
checksum), `.run()` / `__call__` (→ value), `await`, `.cancel()` — and resolving a
mixed graph walks the DAG, dispatching **each node by its kind**.

- **Transformation nodes** dispatch to the configured backend as today.
- **Expression nodes** are zero-cost and envelope-free — there is no `__meta__`,
  so placement is fixed *policy*, not a per-node choice. On a cache miss,
  placement follows the **data**, never a compute resource:

  1. **Cache** — a hit on the composite key returns the result checksum with no
     work; the rest of the ladder runs only on a miss.
  2. **Deep + path** — navigate the manifest to the sub-checksum; no materialization.
  3. **Data local** — materialize-and-apply in the current process.
  4. **Data remote** — resolve *at the data*: the database/hashserver applies the
     path server-side and returns only the result checksum. Never pull a large
     buffer across the network just to slice it locally.
  5. **Never a spawn worker**, in *any* context (local, jobserver process, or Dask
     worker). An expression is evaluated **in-place where its data already is**;
     handing a zero-cost op to a process-pool slot is pure overhead and makes no
     sense.

  When an expression's input is an unresolved transformation, that transformation
  dispatches normally, and the expression then evaluates in whatever context the
  result landed in (rule 3) — e.g. inside the Dask worker that just produced the
  input, not by re-dispatching.

  This is the same **"placement follows data, not compute"** principle as
  scratch + input-fingertipping, with the compute cost set to zero — the existing
  placement philosophy at its limit, not a special case.

- **Cancellation.** An expression's own evaluation is effectively instantaneous
  and not separately cancellable; cancelling an expression handle detaches from
  and (with `recursive=True`) cancels its upstream transformation/expression
  dependencies, reusing the existing checksum-addressed cancellation surface.

## Immutability Carry-Over

The transformation immutability discipline applies to `Expression` unchanged, and
is what makes the structural layer safe to compose freely: an `Expression` freezes
its `(input-ref, path, source/target celltype)` at build time; the input-ref is a
concrete checksum or a frozen dependency edge, never a live pointer to a mutable
Cell; mutating the originating Cell afterward cannot change a built expression's
identity or result; and only result-promise state (the resolving future, the
result checksum, status) stays mutable on the handle.

## Scope And Sequencing

The work divides into three stages, ordered so each rests on a settled contract
rather than on the next stage's design. Each stage is described by the *capability
and contract* it delivers, not by a code recipe.

1. **The immutable structural primitive.** `Expression` as a content-addressed
   `(input, path, source/target celltype) → result` derivation, honoring the
   identity, validator, and result-identity contracts above, resolvable and
   cacheable through the existing persistence shape, and reverse-resolvable for
   fingertipping. Done when an expression over a concrete checksum resolves,
   caches, and is reverse-resolvable.

2. **The mutable builder.** `Cell` as the functional, build-once builder whose
   navigation returns Cells and whose call builds an `Expression`. Done when cells
   can be navigated and converted ergonomically and each build is an immutable
   snapshot.

3. **Unification with the compute DAG.** `Expression` and `Transformation` as
   interchangeable graph nodes — symmetric futures as edges, one resolve surface,
   per-node dispatch with the expression placement ladder, and fingertipping that
   recurses across both kinds. Done when mixed graphs of cells and transformers
   resolve as one DAG.

## What The Implementation Must Guarantee

These are the contract invariants the implementation must demonstrate (they double
as the test charter), stated as properties rather than test scaffolding:

- **Identity.** The result depends on input, `path`, and both celltypes, and
  **never** on the validator.
- **Validator.** A validator may reject an expression but never changes the value
  it denotes; a value-changing validator is rejected as a contract breach.
- **Determinism.** The same key always denotes the same result; the forward cache
  is an idempotent memo.
- **Deep navigation.** Attribute/item/slice access on a deep checksum (deep-celltype
  input) resolves to a sub-checksum without materializing the parent buffer.
- **Build-once.** Mutating or reassigning a Cell after a build never changes a
  built `Expression`; a single Cell feeding two builds yields two independent
  snapshots.
- **Composition.** Expressions over transformation futures, and transformations
  over expression futures, resolve correctly and reuse the cache on re-evaluation.
- **Dispatch.** Expressions resolve at the data and are **never** dispatched to a
  spawn worker, in any context.
- **Fingertipping.** A missing result is rematerializable via the reverse index
  (input + `path`), recursing through both transformation and expression producers.

## Assumptions

`path` payloads are small and may be copied freely.

Expression evaluation is deterministic and (near) zero-cost; re-deriving is usually
cheaper than transferring large buffers, which justifies data-local / at-the-data
placement and the never-spawn rule.

Validators are pure gates: reject, never coerce.

Expressions carry no execution envelope; placement is fixed policy, not per-node
configuration.

Forming an expression's cache key requires its input's result checksum, so keying
an expression over an unresolved input waits on the upstream — exactly like a
transformation parent checksum waiting on dependency results.

---

## Appendix: Reactive `Context` (Upcoming)

`Context` brings back reactive Seamless **on top of** the functional substrate
above, scoped so that reactivity never leaks into the immutable layer — the same
separation that keeps that layer cacheable and referentially transparent.

### Contract

- A `Context` contains **`Cell`s and `Transformer`s** — the mutable builders. It
  **never** contains `Expression`s or `Transformation`s (the immutable
  definitions). The immutable layer has no notion that a `Context` exists.
- A context-bound `Cell`/`Transformer` takes inputs that are **concrete
  checksums** or **other `Cell`s/`Transformer`s bound to the same `Context`**
  (intra-context edges).
- Whenever something changes, the `Context` **reactively fires** concrete
  `Expression`s and `Transformation`s — the immutable, functional layer — to
  recompute the affected results. Each change "ticks" the graph; each tick
  materializes a fresh set of immutable evaluations whose results flow to
  downstream cells.

### Why this is cheap and safe

Reactivity reduces to **re-build with fresh snapshots**. When a context-bound Cell
changes, the Context discards nothing in the immutable layer; it builds new
`Expression`s/`Transformation`s from the new snapshots, and the content-addressed
cache reuses every sub-result that did not actually change. The functional layer
never mutates; the Context only rebuilds on top of it. The Context is the single
place where "the same logical cell took a new value," and it expresses that purely
as a new build.

### Open design points (resolve when this phase starts)

- change propagation, scheduling, and equilibrium/quiescence detection;
- partial / incremental recomputation (the cache reuse falls out of
  content-addressing, but the scheduling around it does not);
- cycle handling and well-formedness of the intra-context graph;
- identity and binding semantics of intra-context edges;
- (de)serialization of a `Context` graph;
- cancellation/abort of in-flight reactive recomputation;
- which cells are observable / witness outputs and how the `Context` exposes them.
