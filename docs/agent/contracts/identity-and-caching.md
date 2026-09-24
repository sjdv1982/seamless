# Identity and Caching (Contract)

Seamless is a checksum-driven system. It treats a computation step as “defined” when it has:

- code identity
- explicit inputs (values and/or checksum identifiers)
- relevant metadata that affects execution/meaning

The core contract is referential transparency with respect to the declared inputs:
“same step definition ⇒ same result”.

## Transformation identity

At minimum, assume transformation identity is determined by:

- the executed code (or code checksum), including embedded module definitions
- the set of input pins and their content identities (checksums)
- the **load-bearing** metadata that changes the computation's meaning: code
  language (`__language__`), output type (`__output__`), pin namespace mapping
  (`__as__`), pin materialization format (`__format__`), and compiled function
  schema/ABI (`__schema__`)

Identity is *not* affected by the orthogonal execution envelope — where/how the
computation runs (`__meta__` including local-vs-remote placement, `__env__`,
`__compilation__`, scratch policy, …). Those change execution, not the denoted
result. If the platform allows environment-dependent semantics, it should record
an **environment signature** as provenance (see `contracts/scratch-witness-audit.md`).

## Checksums, values, and celltypes

- The checksum is the identity; a deserialized value is not. One value may have several checksums (e.g. `b"true"` vs `b"true\n"`, compact vs indented JSON), and Seamless does not re-canonicalize a checksum by re-serializing its value — the only canonicalization is empty `bytes` → the canonical null `b"null\n"`.
- A celltype is an interpretation of a checksum. The celltype hierarchy is a hierarchy of valid checksums: a checksum valid as a subtype is valid, unchanged, as its supertype, so such a conversion keeps the checksum (and hence cache identity).
- See `contracts/celltypes-and-conversion.md` (celltypes, null, parser, conversion engine) and `contracts/hashtype.md` (checksum-level classification used to reject impossible deserializations/conversions without buffers).

## Caching

Caching is valid only to the extent that the step is referentially transparent under the identity definition above.

Practical rules:

- The cache may store “transformation checksum → result checksum” mappings.
- A result checksum can be reused without re-executing code only when it is resolvable/materializable (or recomputable, if scratch).
- Content-addressed reads are not semantic side effects: resolving a pre-declared checksum is materialization, not “reading whatever is on disk”.
- Compression (`.zst`, `.gz`) is a materialization detail — it does not affect identity or caching. A compressed and uncompressed form of the same buffer have the same checksum and are cache-equivalent. See `contracts/compression.md`.

### Transformations are not the only thing cached

This page defines the *Transformation* identity and its cache. Three other kinds of entry are keyed and stored by their own identity, and none of them is a transformation-cache entry:

- **Expression results.** An Expression's identity is the 4-tuple `(input_checksum, path, input_celltype, celltype)`, and a successful result is recorded under it — in a process-global cache and in the database `expression` table, with `rev_expression` as its reverse index. Failures are **not** cached, deliberately, unlike a Transformation's exception. See `contracts/expressions.md`.
- **Conversion results.** A buffer-level celltype conversion that produces a new buffer is recorded as an **empty-path Expression**, so a later conversion between the same two celltypes for the same checksum is an Expression cache hit, not a second conversion. See `contracts/celltypes-and-conversion.md`.
- **HashType words.** The checksum-level classification of a buffer is cached per checksum, locally and in the database `hash_type` table, and only ever tightens. It is metadata about a checksum, never a result. See `contracts/hashtype.md`.

The local buffer cache, its strong/weak strategy and its eviction pressure are `contracts/cache-storage-and-limits.md`; which buffers may not be evicted at all is the checksum reference lifecycle (`contracts/internal/checksum-reference-lifecycle.md`).

### Recording identity is not publishing

The caches above record **identity**: producer → result checksum. That is a separate act from **publishing** — writing the result *buffer* to the hashserver — and the two must not be conflated. The two words are ruled to mean exactly that, everywhere, including `contracts/internal/checksum-reference-lifecycle.md`, which owns the reference side:

- **Evaluating** a transformation or an Expression, or recovering a buffer by fingertipping, produces a buffer in the evaluating process's memory. That is all it does.
- **Recording identity** stores the mapping. It must keep happening — it is what the reverse index that fingertipping walks is made of — and it says nothing about where any buffer is.
- **Publishing** is an assertion that somebody holds the result and will want it later. It is the act of **increfing** the buffer for non-ephemeral interest, and that single act both writes the buffer to the hashserver and overturns any scratch status.

**Neither evaluation nor fingertipping publishes**, at any site, so an evaluated result's persistence is a property of *who holds it*, never of *who computed it* or *where*. Fingertipping has no exception to this: it always runs locally and never writes to the hashserver (*Fingertipping under remote execution*, below). A corollary worth keeping in mind when reading a cache: a recorded result checksum does not imply that its buffer exists anywhere. Across a dispatch the interest travels with the request (`scratch` is a request parameter, and the executing side publishes on the requester's behalf under the requester's decision), which preserves the rule across a process boundary rather than breaking it. Where the requester is a bare `Expression` and there is no owner to supply that decision, the entry point supplies it — asking for a checksum carries `scratch=True` and writes nothing, asking for a value carries `scratch=False` because the hashserver is the only channel by which the bytes can arrive (`contracts/expressions.md`, *The requester's scratch decision, and what a bare Expression carries*). See `contracts/scratch-witness-audit.md` and `contracts/internal/checksum-reference-lifecycle.md`, and, for where the code stands, `contracts/expressions.md`, *Status: publication and fingertipping*.

### Fingertipping under remote execution: two cases

**Fingertipping always runs locally and never writes to the hashserver.** There is no exception: not for a manual fingertip, not inside a job, not at any site, and not for the end result of a chain.

Fingertipping recovers an absent buffer (scratch, or evicted) by recomputing its producer chain. "Locally" means in the process that wants the buffer: nothing in a fingertip chain is ever dispatched. When a job server (jobserver or daskserver) is active, a fingertip happens in one of two cases. They differ in who asks and therefore in which process runs the chain. **Neither writes anything to the hashserver.**

| | **Case 1: input fingertip inside a job** | **Case 2: manual fingertip** |
|---|---|---|
| **Typical use** | The common case: a big scratch intermediate that exists only to feed a transformation | Someone wants the bytes of a result marked scratch (or evicted) |
| **Trigger** | A dispatched transformation whose input buffer is absent, with input fingertipping enabled (`allow_input_fingertip = True`, `--fingertip`) | An explicit request: `Checksum.fingertip()`, `Cell.fingertip()`, `Pin.fingertip()` or the fingertip of an Expression's result in Python, or the `seamless-fingertip` CLI |
| **Where the chain runs** | Where the job runs. The transformation is dispatched like any other, and its input fingertip is **local to that job**: nothing in the chain is dispatched again. On a daskserver the recomputation may land on another Dask worker, but Dask moves that data between workers itself, outside Seamless | **In the requesting process, as the norm, even while a job server is active.** Nothing in the chain is dispatched: the chain is not sent to the job server, and neither are its individual links |
| **Hashserver writes** | **None.** Neither the recovered input nor any intermediate is written | **None** from the fingertip itself. A bare `Checksum.fingertip()` leaves the buffer in local memory only. A fingertip through a non-scratch owner (Cell, Pin) persists the result, but through that owner's own incref, not because of the fingertip |
| **Scratch status afterwards** | Unchanged: the input stays unstored | Unchanged, unless a non-scratch owner increfs the result |

In both cases the chain runs where the buffer is wanted, so the buffer is already in memory there and nothing has to travel through the hashserver. This is why the manual case stays local. A remote evaluation answers with a checksum only, so dispatching the chain would force a hashserver write of exactly the buffer that the scratch decision or eviction had kept out. The cost of staying local: the requester must be able to execute the chain's transformations itself (`contracts/expressions.md`, *Fingertipping is exempt from "where the data is"*).

`contracts/scratch-witness-audit.md` (*Where a fingertip chain runs, and what it leaves behind*) is the full statement; `contracts/expressions.md` covers the Expression side.

### Caching masks accidental nondeterminism

A direct consequence of “same `tf_checksum` ⇒ reuse the cached result”: Seamless **does not, by default, observe** accidental nondeterminism (wall-clock reads, unordered-set iteration, non-associative parallel reductions, data races). A transformation is computed **once**, its result is cached under its `tf_checksum`, and every later request is a **cache hit** — the code is never re-run, so a divergent result is never seen.

Accidental nondeterminism therefore surfaces **only when a result is recomputed**:

- **deliberately**, by forcing a recomputation for an audit (see “Forcing recomputation / auditing” below), or
- **incidentally**, by **fingertipping** — when a requested buffer is *absent* (evicted from the store, **or** `scratch` and so never stored), Seamless regenerates it by recomputing its producer (recomputation-using-provenance). A non-reproducible producer then yields a *different* checksum on regeneration, breaking the consuming step's input identity. Note this is a property of fingertipping (the recompute), not of scratch as such — an evicted non-`scratch` buffer is exposed the same way (see `contracts/scratch-witness-audit.md`). A fingertip chain is never dispatched, so the recomputation, and any divergence it exposes, happens in the environment of the process that wants the buffer: the job's for an input fingertip, the client's for a manual fingertip (see *Fingertipping under remote execution*).

A `result_checksum` that differs for the same `tf_checksum` is a **referential-transparency violation**, not a Seamless feature; that is what `IrreproducibleTransformation` records (see `contracts/execution-records.md`). Determinism is a contract the user must uphold; Seamless's silence on a cache hit is not evidence of it.

### Concurrent submissions of the same checksum

Because orthogonal-only differences are cache-equivalent, a second submission of an already-running `tf_checksum` under a different orthogonal envelope does not start a second execution. By default it **latches on**: it attaches to the running submission, adopts that submission's envelope, and returns its result *value* (not the latcher's envelope side-effects, e.g. its own direct-print, placement, or record request). A caller that requires its own envelope to execute can opt into `strict` mode (`strict_dunder=True` in Python; `--strict` on `seamless-run-transformation`, which is the only CLI that offers it), which instead fails while a differently-dundered submission is active — the prior submission must finish or be canceled (`seamless-cancel <tf_checksum>`) first. This reflects a backend limitation — the same `tf_checksum` cannot execute concurrently under two different envelopes — not a property of the identity model.

## Load-bearing vs orthogonal keys in a transformation dict

Internally, a transformation is represented as a dict. A dunder (double-underscore) key is **not** automatically excluded from the checksum — each key is classified as one of three kinds:

**Load-bearing** (determinant) — included in the transformation checksum (the cache key). Changing the value produces a different transformation identity and bypasses the cache. This is every plain pin (`code`, `arg1`, `objects`, …) **and** the load-bearing dunders: `__language__` (code interpretation/execution semantics), `__output__` (output name/celltype), `__as__` (pin namespace mapping, observable by code), `__format__` (pin materialization), and `__schema__` (compiled function ABI/signature; not derivable from `code`).

**Orthogonal** — frozen and carried with the transformation, but excluded from the checksum. Changing the value changes the execution envelope, not identity, and must not change the denoted result value. These include `__meta__` (incl. local-vs-remote placement and compiled `metavars`), `__env__`, `__compilation__`, `__record_probe__`, `__code_checksum__`, `__code_text__`, scratch policy, the legacy `__compilers__`/`__languages__`, and any `META__*` key.

**Derived/eliminable** — not independent identity state; regenerated from load-bearing data, and only validated then discarded if a caller supplies them. These include `__header__` (generated from `__schema__` via `seamless-signature`), `__compiled__` (derived from the presence of compiled definition state), and `__deps__` (derived from the dependency graph).

Practical consequence: two transformations that differ only in orthogonal values are cache-equivalent. For example:

- Compiler flags live in `__compilation__` (orthogonal) → switching from `-O3` to `-g` does not invalidate the cache.
- The conda environment name lives in `__env__` (orthogonal) → activating a different environment reuses a cached result if the code and inputs are unchanged.
- Source code lives in the plain key `code`, and the code language lives in `__language__` (load-bearing) → changing either is a cache miss. The same `code` bytes interpreted as Python versus bash are *different computations* and must not alias to one cache key.

This split is the heart of the identity model: load-bearing keys capture the "what to run" identity, orthogonal keys capture the "how to run" envelope. An agent must not move load-bearing data into the orthogonal set to avoid cache misses — doing so corrupts the identity model by aliasing distinct computations to one key.

## Forcing recomputation / auditing

An agent should assume there is (or should be) a way to:

- bypass transformation-result caches for a specific computation
- recompute the step
- compare results bitwise (checksum equality), and if not equal, compare a user-provided witness output (see `contracts/scratch-witness-audit.md`)

If docs do not specify audit/recompute controls, ask the user; don’t guess.
