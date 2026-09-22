# Expressions (Contract)

An **Expression** is the structural, immutable counterpart of a Transformation: a closed, pure codebook over one input checksum — get-attribute, get-item, slice, celltype conversion — with **no execution environment**. It has no code, no pins, no dunders, no `__env__`; it cannot run user code and cannot fail nondeterministically.

Expressions and Transformations share one lazy, content-addressed DAG: an Expression's input may be a Checksum, a Cell, or another Expression, and an Expression result may feed a transformation pin, exactly as a transformation result may feed an Expression.

A **Cell is a deferred Expression**: the mutable builder for the same recipe, either standalone or bound to a workflow Context node. Everything Cell-side — `celltype` versus read-only `input_celltype`, `.source` / `.checksum`, the write families, null, standalone reads, failures on the handle, projections and cell-level joins — is in `contracts/cells.md`.

Expressions and the conversion engine are entangled: buffer-level conversion results are cached as **empty-path Expressions**, so every conversion that produces a new buffer is recorded under an Expression identity (see `contracts/celltypes-and-conversion.md`).

**The one rule to read before anything else on this page: an Expression projects, and only then converts.** The path is applied to the input read at `input_celltype`; `celltype` converts *what the path selected*, never the input as a whole. An Expression never converts its input, so it performs at most one conversion and it is always last. Get this backwards and a path silently means something else — see *Application order*.

## Where this page sits: the stack

Each layer is defined **on top of** the one before it, and no page re-derives the one below it.

| Layer | Page | What it adds |
|---|---|---|
| 1. **Celltypes and the type hierarchy** | `contracts/celltypes-and-conversion.md` | which checksums are valid as which celltype, and the subtype→supertype edges |
| 2. **HashType** | `contracts/hashtype.md` | a checksum-level classification that **disproves** readings and conversions without fetching a buffer. Only a `False` is a proof |
| 3. **Conversion** | `contracts/celltypes-and-conversion.md`, *Conversion engine* | the rule table, built on top of the hierarchy, using layer 2 to refuse or skip work before any buffer is fetched |
| 4. **Expressions** | **this page** | path steps plus at most one conversion, in that order. Layer 3 is exactly the **empty-path** case of an Expression, and its results are stored under empty-path Expression identities |
| 5. **Cells** | `contracts/cells.md` | a Cell is a *deferred* Expression: the mutable builder for the same recipe, standalone or bound |

**Deep checksums are a carve-out at layer 4, not a layer of their own.** An Expression over `deepcell`, `deepfolder` or `folder` obeys a separate, much smaller conversion and path table, owned by `contracts/deep-celltypes.md`; see *Deep checksums* below for how the two tables meet.

Code locations:

| Concern | Module / symbol |
|---|---|
| Definition container | `seamless.expression_class` (`Expression`, `normalize_path`, `append_item_path`, `append_slice_path`); re-exported as `seamless.Expression` |
| Evaluation, cache, placement, dedup, cancellation | `seamless.checksum.expression` (`ExpressionKey`, `ExpressionEvaluationError`, `evaluate_expression`, `evaluate_expression_async`, `evaluate_expression_remote`, `choose_expression_evaluation_location`, `get_expression_cache`, `parse_path`, `resolve_expression_value`, `softcancel_expression`, `cancel_expression`, `wait_for_active_expression`) |
| Checksum-level pre-validation | `seamless.checksum.hash_type_validation.validate_expression[_async]` |
| Error envelope | `seamless.error_envelope` (`encode_error`, `decode_error`, `error_kind`, `WorkflowExecutionError`, `RunningLoopRefusal`) |
| Remote dispatch | `seamless_remote.jobserver_remote.run_expression` / `has_jobserver`, `seamless_remote.daskserver_remote.run_expression` / `has_daskserver`, `seamless_transformer.worker.dispatch_expression` |
| Server endpoint | seamless-jobserver `GET /run-expression` |
| Database | seamless-database `Expression` model → table `expression`; request types `expression` (GET/PUT) and `rev_expression` (GET only); protocol `("seamless", "database", "2.2")` |

> **Read the names in that second row with care.** `evaluate_expression` and `evaluate_expression_async` are **local-only** despite not saying so, and `evaluate_expression_remote` is the **dispatching** entry point — the only one that can decide *local*. `_publish_expression_result` does not mean "publish" in the sense used on this page, and is to be renamed `_tempref_expression_result`. The full table, and the wrong model these names produce, is in *Fingertipping is exempt from "where the data is"*.

## The definition

`Expression` is a frozen, slotted dataclass:

```python
Expression(input_ref, path="", *, input_celltype=None, celltype=None,
           validator=None, validator_language=None)
```

- `input_ref` is a `Checksum`, a `Cell` (built at construction into its builder state), another `Expression`, or anything a `Checksum` accepts.
- `input_celltype` defaults to the typed source's celltype, else `celltype`, else `"mixed"`; it must agree with a typed source or construction raises `ValueError`.
- `celltype` defaults to `input_celltype`. It is the **output** celltype (see the `celltype` / `input_celltype` naming rule for Cells).
- Builders return new Expressions and never mutate: `.item(key)`, `.slice(start, stop, step)`, `.as_celltype(ct)`, `expr[key]`, `expr[a:b]`, `expr.name`. Attribute access is projection, so retired API names are rejected before projection, and names starting with `_` raise `AttributeError`.

### Path syntax

The path is stored as a string and parsed at evaluation time (`parse_path`):

| Form | Step |
|---|---|
| `.name` or a leading bare `name` | `("item", "name")` |
| `[token]`, `token` containing `:` | `("slice", slice(...))` |
| `[token]`, otherwise | `("item", ast.literal_eval(token))` |

`append_item_path` writes a string key in dotted form when it is a Python identifier, otherwise in bracket form with `repr()`; any non-identifier key (including one containing `/`) therefore has to be written in bracket form.

Applying a step (`_apply_step`): a string item key indexes a `dict` or a structured NumPy array, and otherwise falls back to `getattr`; any other key indexes. A step that raises becomes `ExpressionEvaluationError`.

## Application order: project, then convert

**Project, then convert.** Evaluation reads the input buffer *as `input_celltype`*, applies every path step (`_apply_step`) to that value in order, and only afterwards serializes whatever the path selected *as `celltype`*. `celltype` is therefore never applied to the unprojected input; it applies only to what the path already picked out. This is a property of evaluation, not of the identity tuple below — see *Identity*.

**An Expression never converts its input.** `input_celltype` is the celltype the input buffer is *read* at, not a conversion applied to it: the source must already be legally readable at `input_celltype`, and a typed source that disagrees is refused at construction (`ValueError`). An Expression therefore performs **at most one conversion, and it is always the last step**. Convert-then-project is not unavailable — it is simply not one Expression. It is the composition of `(input_checksum, "", X, Y)` with `(result, path, Y, Y)`, in which the converted parent is a distinct Expression with its own identity and its own cache entry, and — for every conversion outside the checksum-preserving trivial and reinterpret classes of `contracts/celltypes-and-conversion.md` — its own new buffer, parent-sized.

Get the order backwards and a path means something else entirely. With `input_celltype="plain"`, `celltype="str"` and path `[3]` over the JSON list `[10, 20, 30, 40]`: project-then-convert reads the list as `plain`, selects element `3` (the integer `40`), and renders *that* as `str` (`"40"`). Convert-then-project would instead render the whole list as its `str` form (`"[10, 20, 30, 40]"`) and take character `3` of that string (`"0"`). The two conventions agree only when the path is empty or the celltypes coincide; everywhere else a path written for one gives a silently different — and differently typed — answer under the other.

The order is not arbitrary. Under convert-then-project the **output** celltype would decide the structure the path walks, so a downstream declaration — a consumer pin's celltype, a cell's celltype — would silently redefine what an upstream path selects, and the path would have to be written against an intermediate value that exists nowhere and is named nothing. Project-then-convert keeps a path's meaning a property of the input side alone: `input_celltype` decides what the path sees, `celltype` decides only how the selected value is rendered. It is also the only order under which a path over a deep checksum selects a child without materializing the parent (`contracts/deep-celltypes.md`), and the only one that converts the selected value rather than the whole parent.

The order has nothing to sequence, and is therefore vacuous, in exactly two cases: an **empty path**, where there is no projection step to order against the conversion (the conversion itself is the empty-path engine of `contracts/celltypes-and-conversion.md`), and the **dummy Expression** (empty path, `input_celltype == celltype`, below), where neither step runs at all.

*Verified:* `_evaluate_expression_after_validation` (`seamless-core/seamless/checksum/expression.py:478-533`) deserializes the input buffer at `key.input_celltype` (`_deserialize_for_expression`), applies every parsed step in `steps` (`_apply_step`), and only then serializes the projected value at `key.celltype` (`_serialize_expression_result`). Nothing on the remote path reorders this: `evaluate_expression_remote`, the jobserver `GET /run-expression` endpoint and `dispatch_expression` all pass `path`, `input_celltype` and `celltype` as three separate fields to the same evaluator, wherever it runs.

**Where the rule shows up on the other pages.** It is one rule with four consequences, each owned elsewhere:

| Consequence | Page |
|---|---|
| Checksum-level validation asks `capabilities` of the **input** celltype, and `conversion_feasible` only where the path is empty | `contracts/hashtype.md`, *Where HashType is consulted* |
| The conversion engine is only ever the **empty-path** case, so the ordering is vacuous there | `contracts/celltypes-and-conversion.md`, *Conversion engine* |
| A one-step path over a deep checksum selects a **child checksum** without materializing the parent — impossible under the opposite order | `contracts/deep-celltypes.md`, *Paths* |
| On a Cell, `cell[3].as_celltype("plain")` and `cell.as_celltype("plain")[3]` are **different recipes**, and `as_celltype` mid-chain closes the Expression | `contracts/cells.md`, *Projections* |

**Convert-then-project is spellable; it is just not one Expression.** `(input, "", X, Y)` composed with `(that result, path, Y, Y)` is the convert-first recipe, and the composition is what a Cell writes when you spell `as_celltype` before a projection. Its cost is the point: unless `X → Y` is trivial or reinterpret (`contracts/celltypes-and-conversion.md`), the inner Expression produces a **new, parent-sized buffer** that the path then walks — which is also why that pair does not fuse (*Fusion*, below).

## Identity

**The identity of an Expression is the 4-tuple `(input_checksum, path, input_celltype, celltype)`.** The tuple names a recipe's ingredients, not the order they are combined in: that order — project, then convert — is fixed by evaluation (above) and is not recoverable from the tuple alone.

- `Expression.identity_key` is the in-process form; `__eq__` and `__hash__` use it. Its first element is `("checksum", hex)` for a concrete input, `("expression", …)` for an Expression input, and `("object", id(...))` for an unresolved source, so an Expression over an uncomputed source is identical only to itself.
- `Expression.database_key` is the wire form `(input_checksum.hex(), path, input_celltype, celltype)`. It raises `ValueError` when the input is not yet a concrete checksum.
- `ExpressionKey` canonicalizes the input checksum against the input celltype on construction, so `sha256(b"")` as `bytes` and the canonical null are one identity (see `contracts/celltypes-and-conversion.md`).
- The seamless-database `Expression` row has exactly this 4-tuple as its **composite primary key**, with `result` as the payload. A second write of the same key is accepted only when the stored `result` agrees; otherwise the row is kept and the request answered with a conflict.
- The same 4-tuple is the **reverse index** that fingertipping walks: `rev_expression` (database) plus the process-local expression cache. Given a wanted result checksum, Seamless finds Expressions that produce it, fingertips their inputs and re-evaluates them (see `contracts/scratch-witness-audit.md`).
- **Wire and storage form.** `path` is serialized as **Seamless-`plain`** — canonical bytes, so one path has exactly one stored form. **There is no limit on path length, and no Expression is ever refused for it**; how seamless-database stores a path too long for its key column is internal to that service. Each celltype is stored in a 20-character column. **Identity is over the path itself**, never over any encoding of it.

**Validators are deferred, and their semantics are deliberately unspecified.** What is settled is small and is listed here in full; everything else about them is **not contract yet and must not be tested against**:

| Settled | |
|---|---|
| **Deferred** | every evaluation entry point raises `NotImplementedError` when `validator` or `validator_language` is supplied — **at entry, before any cache lookup, any placement decision and any dispatch**. The refusal is therefore *total*: an identity tuple whose result is already in the process cache or in the database raises exactly as a fresh one does, and a validator-carrying Expression never reaches a cache, a server or the evaluator. A Cell records the refusal as `.exception` (`contracts/cells.md`) |
| **Reject-only** | a validator may refuse a result; it can never transform one. A validator is not a conversion |
| **Excluded from identity** | `validator` / `validator_language` are fields of the container and columns of the database row, but **not** part of the primary key, and `evaluate_expression*` carries an explicit TODO recording that exclusion |
| **Columns unwritten** | nothing currently writes the two database columns |
| **Type** | a validator must be a `Checksum` (or hex); source text is not accepted |

**Open in the world where validators run, and known to be open:** whether a validator runs on a **cache hit** (process cache or database) or only on a fresh evaluation; how two Expressions with the same identity tuple but **different validators** coexist in one cache entry and one database row; and what the database does when a second write carries a different validator for a key whose `result` agrees. Exclusion-from-identity is what creates all three questions, and answering them is part of implementing validators, not a wording fix.

**The three open questions do not contradict the total refusal above; they are pre-empted by it.** Because the `NotImplementedError` is raised before any lookup, the cache-hit case cannot arise today: there is no behaviour to observe, which is precisely why the question is still open rather than settled by the code. Until validators exist, the only behaviour a test may pin is the `NotImplementedError` — **including on an identity tuple whose result is already cached**, which is the one test that distinguishes "refused at entry" from "refused only on a fresh evaluation" and is therefore worth writing.

### The dummy Expression

An Expression with an **empty path and `input_celltype == celltype`** is the identity (dummy) expression. It resolves to its input checksum without any work: no buffer is fetched, no conversion runs, and the input checksum is recorded as the result. Checksum-level validation still applies — a known structural incompatibility is rejected without source content — but nothing else happens. (A null input short-circuits earlier still: an empty-path Expression whose canonicalized input is null yields the canonical null result for every celltype pair.)

This is load-bearing for the `.set_checksum` contract. `Cell.set_checksum` and `Pin.set_checksum` are the Checksum variant of the three setters; they set the **input** checksum, not `.checksum`. `.checksum` is therefore normally `None` immediately afterwards, with two exceptions:

1. the underlying Expression is a dummy — `.checksum` returns the argument (as a `Checksum`) immediately, without evaluation;
2. the Cell is unbound — `.checksum` is then a computed property performing a synchronous evaluation of the underlying Expression. This does not change the semantics of `set_checksum`.

The dummy case is a required special case, not an optimization: `.set_checksum` is instantaneous, so `.checksum` must answer immediately, without entering the evaluator.

*Verified:* the standalone `CellBase.checksum` getter implements exactly this fast path, including the empty-`bytes` → null canonicalization.

## Cost class

**An Expression's cost class is decided from checksum-level facts alone, never from the buffer content behind the checksum.** There are three classes — **free**, **one child** (here simply *one buffer*: an Expression over an ordinary celltype has no members) and **all children** — and they are named once, in `contracts/deep-celltypes.md`, *The organising principle*. A non-empty path always costs **one buffer — the input buffer** — regardless of which checksum is at the root; shape alone decides. (Over a deep checksum this still holds for evaluation: the one buffer is the *index*, and no member buffer is fetched to produce the result checksum. See `contracts/deep-celltypes.md`, *Paths*, for what each one-step target yields.) An empty path is not always free, though: whether it needs a buffer also turns on the specific checksum's nullity and on what its cached `HashType` already proves, so two Expressions with the same `(input_celltype, path shape, celltype)` shape are not guaranteed the same cost (contrast the deep celltypes, `contracts/deep-celltypes.md`, where no conversion branches on anything but the declared celltypes, so shape alone does decide). An agent can always decide cost class without touching a buffer; that is why deep fan-out is restricted (below) and why placement can be decided before any buffer is touched.

Concretely, an Expression needs a buffer if and only if:

- the path is non-empty; or
- the path is empty, the celltypes differ, the input is not null, and `conversion_needs_buffer(checksum, input_celltype, celltype)` is `True` — that is, the conversion is not decidable from the checksum, the rule table and the cached HashType alone.

## When an Expression is vetted, and by what

Validation happens **twice**, and the two phases ask different oracles.

**At construction** nothing about the input checksum's content is known, so only structural facts can be checked — which is enough to refuse a shape that could never be legal:

| Shape at construction | Vetted by |
|---|---|
| **pathless** (a conversion, deep or not) | the **conversion engine**'s rule table, which owns the few legal deep-to-deep conversions as well (`contracts/celltypes-and-conversion.md`, `contracts/deep-celltypes.md`) |
| **pathed**, with a deep celltype on either side | the **deep table** of `contracts/deep-celltypes.md` — exactly one string-item step, and the member-celltype rules |
| **pathed**, over the 13 ordinary celltypes only | the **structural path rules** below: a path cannot be applied to an `int`, a string key cannot index a string, and so on |

#### The structural path rules

These are decidable from `input_celltype` and the path **shape** alone, so they are checked at construction. A step is one of three kinds (`contracts/expressions.md`, *Path syntax*): a **string item** (`.name`, `["name"]`), a **positional item** (`[3]`, or any non-string literal), or a **slice** (`[1:4]`).

| `input_celltype` | string item | positional item | slice | after a step |
|---|---|---|---|---|
| `plain`, `mixed` | allowed | allowed | allowed | **unknown** — the element's type is data; checking passes to evaluation |
| `binary` | allowed (a structured array's field) | allowed | allowed | **unknown** — as above |
| `text`, `str`, `python`, `ipython`, `yaml` | **refused** | allowed | allowed | still a string, so **the same row applies** to every further step |
| `bytes` | **refused** | allowed | allowed | a positional item yields an `int`, so **the path must end there**; a slice is still `bytes` and the row continues |
| `int`, `float`, `bool` | **refused** | **refused** | **refused** | — a scalar has no members |
| `checksum` | **refused** | **refused** | **refused** | — a `checksum` is a reference, not a container (`contracts/celltypes-and-conversion.md`: every pair with `checksum` on either side is value-level) |
| `deepcell`, `deepfolder`, `folder` | **exactly one, as the whole path** | **refused** | **refused** | — the deep table owns this row (`contracts/deep-celltypes.md`, *Paths*) |

A string item over a text-like celltype is refused rather than left to evaluation because `_apply_step` would fall back to `getattr` on a `str` object, which is not addressing a value at all.

#### Which refusal happens where

The line is exact, and it is what a test should assert against:

| The refusal follows from | When | Raised as |
|---|---|---|
| the declared celltypes and the path shape alone | **construction** | `ValueError` — the Expression constructor's class for a statically ill-formed Expression, naming the offending step. No checksum is involved, so no `HashType` is consulted |
| the input checksum's `HashType` word | **evaluation**, before any buffer is fetched | `HashTypeValidationError` (a `ValueError` subclass; error-envelope kind `hash_type_validation`) |
| the value behind the checksum | **evaluation**, after the buffer is deserialized | `ExpressionEvaluationError`, naming the failing path step |

A **Cell** builds its Expression lazily, so a construction refusal surfaces at the first `build()`, read or `compute()` — and a standalone Cell **records** it as `.exception` rather than raising, exactly as it does for an evaluation failure (`contracts/cells.md`, *Failures*). The refusal is the same refusal; only its delivery differs.

**At evaluation** the input checksum's `HashType` is available and a sharper pass runs: for a **pathed** Expression the same path / `input_celltype` rules are re-applied against what the word now proves (`capabilities`); for a **pathless** Expression over the 13, `deserializable_as` and `conversion_feasible` do that vetting instead. Either rejection is a `HashTypeValidationError` at checksum level, before any buffer is fetched (`contracts/hashtype.md`).

**HashType is never asked about a deep celltype.** Deep feasibility is structural — it turns on the declared celltypes and the path shape, never on the data — so it is settled at construction by the deep table. `deserializable_as` accepts only the 13 and **raises `ValueError`** on anything else: that is a caller error, not an answer (`contracts/hashtype.md`). This is what keeps HashType's false-negative property intact, rather than widening it to cover deep names.

*Contract ahead of code:* today there is one pass, not two. `validate_expression[_async]` runs before evaluation — source celltype, then path capability, then (for an empty path) `conversion_feasible` — and nothing is checked at construction. Deep celltypes have no rules anywhere: they reach `deserializable_as`, which answers `False`, which is why every deep Expression currently raises.

## Results and caching

- Successful results are recorded in a process-global dict `get_expression_cache()`, keyed by the 4-tuple, value = result checksum; and, when `seamless_remote` is importable, in the database `expression` table.
- A newly produced result buffer is kept in a weak-valued map, given a buffer-cache tempref, and **classified**: `register_hash_type_for_buffer` runs in the process that produced the buffer.
- `Expression.checksum` is an alias of `Expression.result`: the recorded result checksum or `None`. Reading it also expresses user result interest — a refholder claim on the result. **That claim is scratch-neutral**: it protects the result from eviction for as long as it is held, and it neither writes the buffer to the hashserver nor overturns any scratch status. Publishing needs an owner with a scratch policy — a Cell, a Transformation, a Context node — and an Expression is not one (`contracts/internal/checksum-reference-lifecycle.md`). Reading a property can therefore never defeat a scratch decision. **Asking for a value is not a property read**, and it is the one thing on this page that can cause a write: `run()` over a *dispatch* carries a scratch decision with its request, because the bytes have no other way back (*The requester's scratch decision, and what a bare Expression carries*).
- `Expression.compute(execution="auto")` / `compute_async(execution="auto")` return the result checksum. `Expression.run()` (also `expr()`) computes and then materializes the value: local buffers first, then `Checksum.resolve()`, which asks the hashserver and raises `CacheMissError` when no buffer is found. `run()` does not fingertip. **The two entry points differ in more than their return type**: asking for a value is an assertion that this requester wants the bytes, which is what fixes the `scratch` decision a dispatch carries and hence whether a remotely evaluated result is reachable at all — see *The requester's scratch decision, and what a bare Expression carries*.

**A result checksum does not imply a result buffer.** Evaluation temprefs the buffer it produced, but producing a buffer here is only one of the ways a result checksum is obtained: it may come from the process cache, from the database `expression` table, or from a checksum-preserving conversion that produced no new buffer at all — and a tempref is bounded and decays. So `.checksum` answering does not mean `.run()` or `.value` will find bytes; both resolve, and both may raise `CacheMissError`. **Assuming its input buffer is available, the only guaranteed way to obtain an Expression's result buffer is to fingertip the result checksum** — `Checksum.fingertip()`, or `Cell.fingertip()` / `Pin.fingertip()` where the result has an owner.

### Evaluating, recording identity and publishing are three different things

These are easy to conflate, and the code's own naming conflates two of them. They are separate acts with separate rules:

| Act | What it does | Who does it |
|---|---|---|
| **Evaluating** | produces a buffer in the evaluating process's memory. That is *all* it does | whichever process ran the Expression |
| **Recording identity** | stores the mapping Expression → result checksum, in `get_expression_cache()` and the database `expression` table. It is what the reverse index that fingertipping walks is made of, it must keep happening, and it says nothing about where any buffer is | the evaluating process |
| **Publishing** | writes the *buffer* to the hashserver. It is an assertion that somebody holds the result and will want it later | the **refholder**, never the evaluator |

**The vocabulary is ruled, and it is the same on every page.** *Publishing* is the buffer write; *recording* is what happens to a result **checksum**. `contracts/internal/checksum-reference-lifecycle.md` uses "recording" in that second sense throughout, and reserves "publishing" for the write. The code's `_publish_expression_result` means neither — it registers a tempref — and is to be renamed `_tempref_expression_result`.

**The rule: neither evaluation nor fingertipping publishes.** An Expression that writes its result buffer to the hashserver is a bug, whether or not a fingertip drove it — it makes persistence a property of *who evaluated* rather than of *who holds*. Publication is the act of increfing the buffer for non-ephemeral interest (for example through a non-scratch Cell), and that single act both writes the buffer and overturns any scratch status; see `contracts/internal/checksum-reference-lifecycle.md`. So a bare `Checksum.fingertip()` leaves nothing behind but a buffer in local memory, while a `Cell.fingertip()` on a non-scratch Cell persists the result because the Cell increfs it (`Pin.fingertip()` is the same verb on a pin). The fingertip site itself never decides: it holds a bare checksum, with no owner and no scratch intent.

**No site is exempt, and no intermediate is ever written.** A fingertip chain writes nothing to the hashserver — not on a client, not in a jobserver, not on a Dask worker. A worker that fingertips a missing `scratch` input wants the buffer *for itself*, so it is the ordinary case, not an exception: persistence stays the holder's act, and making it depend on *where* a recovery happened is exactly what this rule exists to prevent. The one genuine exception is a fingertip performed **on somebody else's behalf** — a remote fingertip *request* — which must write the buffer of the fingertipped checksum, because there is no other channel by which the requester can receive it. Even then it writes **only the end result of the chain**, never an intermediate.

**Across a dispatch, the interest travels with the request.** If the evaluating side never publishes, a remotely evaluated result stays in the worker's memory and the client receives a checksum it cannot resolve — and the client's own later incref cannot repair that, because there is no buffer in *that* process to write. The transformation path already solves this by making `scratch` a parameter of the request: the executing side's non-scratch tempref writes the result buffer, and the jobserver asserts it can resolve the result before answering. The same shape is the contract for Expressions — the executing side publishes **on the requester's behalf, under the requester's scratch decision**, so the rule above is preserved across the process boundary rather than broken by it.

*Contract ahead of code, on both halves.* Today every terminal branch of local evaluation calls `_publish_expression_result(…, buffer=…)`, which temprefs **non-scratch** and therefore queues a background hashserver write whenever one is configured — for every evaluation, fingertip-driven or not. And the expression dispatch carries no `scratch` flag at all, so the table below has no implementation either. See *Status: publication and fingertipping*.

#### The requester's scratch decision, and what a bare Expression carries

**An Expression has no scratch policy of its own; a dispatch carries the *requester's*.** That is what *Non-goals* means by an Expression having no scratch policy: not that the request is unparameterized, but that the Expression is never the thing that decides. The value is **derived, never invented by the evaluator**:

| The requester | `scratch` on the dispatch |
|---|---|
| an **owner with a scratch policy** — a Cell, a workflow Context node, a transformation input resolution | **that owner's policy, unchanged.** Carrying it across the boundary is the whole point of the parameter: a scratch owner's decision must survive a dispatch |
| a **bare `Expression`** asked for a **checksum** — `compute()`, `compute_async()`, `.checksum` | **`True`.** The requester asked for a checksum, not for bytes. Nothing asserts that anybody holds the result, so nothing is written anywhere |
| a **bare `Expression`** asked for a **value** — `run()`, `expr()` | **`False`.** Asking for the value *is* the assertion that this requester wants the bytes, and across a dispatch the hashserver is the only channel by which it can receive them |

**This is how `run()` obtains a remotely produced buffer without anybody breaking the rule above.** The executing side writes the end result because the *request* told it to, on the requester's behalf, and — as on the transformation path — the jobserver asserts it can resolve the result before answering. The evaluator still decides nothing. It is the general form of the exception already ruled for a remote fingertip *request*: **a write performed on somebody else's behalf, of the end result only, never of an intermediate.**

**What that write does and does not assert.** For a bare `run()` nobody holds the result afterwards, so calling the write "an assertion that somebody holds it" would be a fiction. It is the executing side's **non-scratch tempref** — bounded, exactly as on the transformation path — and it is the transfer channel, nothing more: the entry is written, the requester resolves it, and with nothing increfing it the buffer is as evictable as any other unheld buffer. Durability still requires an owner, and the owner is still on the requester's side. The distinction that matters is the one this page keeps everywhere: **the write is not the evaluator's decision.** A bare `run()` on a locally placed Expression writes nothing; the same call on a dispatched one writes, because that is the only way the bytes can arrive. If even that write is unwanted — against a hashserver that is deliberately kept thin, say — the answer is `execution="local"`, which pays the input transfer instead.

Four consequences, all contract:

- **Locally placed, nothing is written either way.** The buffer is in this process's memory, which is all `run()` needs, so `scratch` has no publication effect at all on a local evaluation. **The flag is observable only across a dispatch** — which is the same thing as saying that the result of an Expression still does not depend on where it ran (*Placement*), while its *persistence side effect* does, and is the requester's to choose.
- **`compute()` never causes a write, anywhere.** A client that asks for a checksum and gets one may well be unable to resolve it. That is not a defect: it is *A result checksum does not imply a result buffer*, stated one layer down.
- **A scratch owner's `.value` may miss, and that is the scratch contract rather than a defect.** A scratch Cell whose Expression was dispatched receives a checksum and no buffer; `.buffer` and `.value` resolve and never fingertip (`contracts/cells.md`), so they raise `CacheMissError`, and the explicit route to the bytes is `Cell.fingertip()` / `Pin.fingertip()`. This is exactly how a scratch *transformation* result already behaves. An agent that wants a dispatched value with no hashserver write at all has two other options: evaluate locally (`execution="local"`, paying the input transfer that placement avoided), or fingertip.
- **`scratch` is not part of identity, so it is not part of the dedup key** (*Deduplication*). A dispatch is made under the **strongest request among its members at the moment it is made** — non-scratch wins — and a member that joins afterwards and needs more does not retroactively change it: it resolves the result checksum as usual and, finding no buffer, asks again. Asking again is always safe, because results are content-addressed and failures are not cached (*Expression failures are not cached*).

## Fusion

An Expression's input may be another Expression, so a recipe is in general a **chain**. **Chains are fused as far as the codebook allows, always, and the fused form is the definition** — what a recipe computes must not depend on how its intermediates happened to be split or named. That is the *Application order* principle applied one level up.

**Four adjacent pairs are possible**, because an Expression is *read, project, convert* in that order and there are two kinds of step to pair up:

| adjacent pair | fuses to | when |
|---|---|---|
| **path + path** | one Expression, paths concatenated | always |
| **conversion + path** | one Expression over the *source's* checksum, `input_celltype` set to the converted celltype | only when the conversion is **checksum-preserving** — the trivial and reinterpret classes of `contracts/celltypes-and-conversion.md` |
| **path + conversion** | already one Expression | — |
| **conversion + conversion** | **never fuses — it stays two Expressions** | — |

A conversion that produces a **new buffer** cannot be fused into a following path: the path has to be applied to the converted bytes, so that conversion's result is a genuine input and the chain keeps two members, the outer one taking the inner's result checksum. This is the practical edge of the rule that conversion is not the same thing as reinterpretation.

**Why two conversions never collapse into one.** Two reasons, and the first alone settles it:

- **An Expression has exactly one `input_celltype` and one `celltype`**, so it can express **at most one conversion**. `A→B` followed by `B→C` has no single-Expression spelling; the question is not whether to fuse it but what it is, and it is two Expressions.
- **Composition is not associative in the conversion table.** `A→C` may be a *different rule* from `A→B→C`, and sometimes deliberately so: `text→mixed` is defined as `text→str`, explicitly not as `text→plain`, and `yaml→mixed` likewise (`contracts/celltypes-and-conversion.md`, *The complete matrix*). Collapsing a chain would silently change what it computes. Fusing conversions would also mean fusing **across** a `conversion_chain` entry, whose own intermediate is chosen by the table rather than by the user.

So each conversion keeps its own identity 4-tuple and its own cache entry, and the outer one takes the inner's **result checksum** as its input — the ordinary two-member chain. Consecutive conversions arise readily: `cell.as_celltype("text").as_celltype("str")` is two, because `as_celltype` mid-chain closes the Expression (`contracts/cells.md`, *Projections*). Nothing is lost by not fusing them: the intermediate is a real, nameable result, and if it is checksum-preserving it costs no buffer anyway.

**Fusion can widen what is defined.** A chain additionally requires each intermediate to be *serializable at its own celltype*; the fused form never serializes it. So a fused Expression succeeds wherever the chain does, and sometimes where the chain does not, and where both succeed they agree. Fusing **always** is what makes that difference unobservable — which is the reason to do it unconditionally rather than as an optimization.

**A deep step is a fusion barrier.** A one-step path over a deep checksum yields a **child checksum**, so a following path would project into the checksum rather than into what it names. The run ends there, and the child's own conversion is a separate Expression. That is not only a correctness point: `contracts/deep-celltypes.md` restricts the one-step result precisely so that the child's conversion is keyed at the **child's** checksum and is therefore shared by every parent index that references that child. Fusing it into the parent's Expression would re-key that shared work under each parent. A deep edge is thus a third edge kind, outside the four pairs above.

**What an Expression corresponds to.** Not a cell, and not an edge: a **maximal fusible run** of edges. Building a bound Cell's recipe walks its incoming edge backwards, accumulating projecting edges, and closes the run at the first of

- a **conversion** — absorbed into the run's `input_celltype` when it is checksum-preserving, left outside the run otherwise. At most one can ever be absorbed, because an Expression has exactly one `input_celltype`;
- a **join**, which is not an Expression at all but plain local Python (`contracts/cells.md`);
- the end of the chain — a concrete checksum.

The run becomes one Expression — `(the run's root checksum, the concatenated path, input_celltype, the cell's own celltype)` — and is evaluated where that root's data is. Intermediates **inside** a run get no Expression, no identity and no cache entry. A *named* intermediate still gets its own Expression, because its checksum is demanded on its own account; that is a second, separate recipe, not a member of this run.

A fused Expression's failure belongs to the node whose recipe it is — the downstream end of the run. Anonymous intermediates inside the run have no node to carry it, which is why the error names the failing path step: that is what locates it.

**Identity.** A collapsed chain has a genuinely different identity: `(root, "[3][1]", X, X)` is not the 4-tuple `(intermediate, "[1]", X, X)`, so it is a different database row and a different cache entry, arriving at the same result checksum. That is not a conflict — the reverse index simply gains a second route to that result (`contracts/scratch-witness-audit.md`). Where a chain does *not* collapse, the outer member's input resolves to the intermediate's checksum, and the key is exactly the one an unfused evaluation would have used.

## Placement: an Expression is evaluated where the data is

Placement **is** contract. A jobserver/daskserver counts as closer to the hashserver than the client, so an input the client does not hold is evaluated there rather than downloaded. What is contract is the *rule for choosing* where to evaluate; placement is no more part of an Expression's identity than it is part of a Transformation's — the identity is the 4-tuple above, and the result must not depend on where the Expression ran (below).

`execution` takes `"auto"`, `"local"` or `"remote"`. **These three values are an argument on an Expression, not the `execution:` configuration key that selects a transformation backend** (`contracts/execution-backends.md`); the words `local` and `remote` mean something narrower here. `"auto"` is the default on every path that evaluates an Expression: `Expression.compute` / `compute_async` / `run`, transformation dependencies, pin preparation, and workflow Context projections (`Context(expression_execution=...)` overrides it for one Context).

- **`"local"` means *the input buffer is already here*** — in this process's memory, or in an explicitly configured read-buffer directory (below). **`"remote"` means *it is not here*, independently of backend availability.** `choose_expression_evaluation_location` answers only that question: local if no buffer is needed, or if the input buffer is already resolvable without a server; remote otherwise.

Resolution order (`evaluate_expression_remote`):

1. process-local Expression cache;
2. database Expression result;
3. local evaluation, when no buffer is needed or the input is in process memory;
4. jobserver/daskserver dispatch, when it is not and a server is configured;
5. local materialization from the hashserver, when none is configured (the local async evaluator resolves the input through `Checksum.resolution()`, and `CacheMissError` propagates if it cannot);
6. resolution of the result checksum — through the hashserver if necessary — when a value is wanted.

Rules:

- **No silent fallback once a *configured* server fails.** Availability is queried side-effect-free (`has_jobserver()` / `has_daskserver()`); a missing backend downgrades `"auto"` to local *before* dispatch, but connection, restart and evaluation errors from a configured server propagate.
- **Explicit `"local"` and `"remote"` never fall back.** `"remote"` raises when `seamless_remote` is unavailable (`ExpressionEvaluationError`) or when no client is configured (`RuntimeError`); `"local"` never dispatches. Only `"auto"` may downgrade.
- **Client-side dispatch target.** A configured jobserver is used first; a client with no jobserver but a configured daskserver submits the Expression to the Dask scheduler itself. Only `ClientRestartRequiredError` is retried (once, then the next client); a decoded job failure is never retried.
- **Synchronous evaluation inside a running event loop is refused, not failed.** `Expression.compute()` in a running loop evaluates only when the location is local; otherwise it raises `RunningLoopRefusal`. A standalone Cell getter turns that refusal into `None` with the Cell left `waiting`, no exception recorded and nothing dispatched. Outside a loop, the synchronous path drives the full asynchronous path through `asyncio.run`.
- **A dispatched `run()` resolves its result from the hashserver, and step 6 is not an accident of deployment.** It can succeed only because the step-4 request carried the requester's scratch decision and the executing side wrote the end result on its behalf; a dispatched `compute()` carries no such decision and leaves nothing for step 6 to find (*The requester's scratch decision, and what a bare Expression carries*).
- **A daskserver is a jobserver *mode*, not a competing backend.** Both modes expose the same checksum, error, caching and HashType contracts. In a jobserver, `dispatch_expression` evaluates in-process when no Dask client is configured, and otherwise submits the Expression to a Dask worker, passing only the identity fields; the jobserver does not download the input in order to forward it.

Two derived rules:

- **The result, including the exception type, must not depend on where the Expression ran.** That is what the structured error envelope buys (below).
- **HashType classification is owned by whichever process holds the buffer**: the client for local evaluation, the jobserver for direct evaluation, the Dask worker for daskserver evaluation. A process that receives only a checksum classifies nothing and uploads nothing. Jobserver/daskserver responses are checksum-only; HashTypes travel through the database.

**Locality includes an explicitly configured read-buffer directory.** A buffer sitting in a configured local read-buffer directory counts as **local**, and the Expression is evaluated here rather than dispatched: the client could read those bytes for free, and paying a server round trip for them is waste. Read-buffer directories are consulted **before** any hashserver query, and a hit means local placement. The gate is deliberately narrow — an *explicitly configured* read-buffer-directory path, never a generic filesystem scan — so that placement stays a **cheap and deterministic** check: a filesystem check against a configured path is allowed, which is a deliberate relaxation of the earlier "side-effect-free" phrasing, and the index-only alternative is not required.

The rule is about the **input** buffer, which is what placement is about. **Resolution already behaves correctly and needs no change**: `Checksum.resolution()` goes through `buffer_remote.get_buffer`, which queries every configured read *folder* before any read *server* (`seamless-remote/seamless_remote/buffer_remote.py:171-186`), so steps 5 and 6 of the resolution order above already prefer a local directory. *Contract ahead of code:* only the placement half is missing — `choose_expression_evaluation_location` today defines locality as this process's **memory** alone, so a buffer on local disk is currently treated as remote and dispatched.

### Fingertipping is exempt from "where the data is"

**A fingertip chain runs entirely in the requesting process, and that is contract, not a placement compromise.** Nothing in the chain is dispatched: not the Expressions in it, and not the Transformations in it.

The reason is that **there is no buffer-return channel.** A remote evaluation answers with a *checksum* and nothing else — the jobserver's `run-expression` handler returns `{"result_checksum": …}` — so a remotely evaluated result can reach the client only by being written to the hashserver. Dispatching a fingertip is therefore not a placement choice with a transfer cost; it is a placement choice that **must publish**. And a fingertip exists precisely because a buffer is absent, which is always the consequence of a decision — a `scratch` policy or an eviction. Remote evaluation would re-add exactly the entry that decision kept out or removed. Local evaluation materializes the buffer in process memory only, and so is the only placement that respects the decision which made the fingertip necessary.

Three things follow, and they are contract:

- **The cost is bounded by the frontier, not by the ancestry.** `fingertip` resolves at every level before recursing, so the walk stops at the first checksum that ordinary resolution can serve (local buffer cache, then hashserver). What is recomputed locally is the frontier of the absent region, not the whole history. For a direct request the target reaches the client either way, so local recompute transfers the frontier *instead of* the target — normally less, since the archetypal scratch shape is a large output derived from smaller stored inputs. **This bounds how far back the walk goes; it does not bound the work.** The frontier may itself be a Transformation costing hours, which is why a materialization's cost is unbounded and why the cancellation machinery of *Cancellation* is worth building.
- **Fingertipping assumes the requester can execute the chain's transformations.** This is a restriction the contract states rather than hides: a thin client with no conda environment, no compiler and no declared binaries cannot fingertip through a Transformation. *Contract ahead of code:* today it cannot even find out that it could not — see *Implementation status*.
- **Two modelling rules keep a graph out of the expensive shape.** Fingertipping a large parent in order to keep one small item is real, and there local evaluation is the costly choice. It is reachable only by opting into it: **do not scratch a small derived cell** (if it is stored, resolution serves it and no chain is built at all), and **make an item-addressed large parent deep** (a path step over a deep checksum selects a sub-checksum without materializing the parent — `contracts/deep-celltypes.md`). Both are in `contracts/scratch-witness-audit.md`.

The optimization that remains available and is **not** recommended: remote evaluation followed by immediate hashserver eviction. It buys the projection case at the price of a write that scratch or eviction had excluded, and anything expensive enough to justify it should not have been scratched.

**A naming hazard, stated because two readers have already got it backwards.** The wrong model is: *"a fingertip chain is only orchestrated locally; each Expression in it is dispatched to where the data is, and each Transformation runs on the server."* Every clause of that is false, and the function names encourage it:

| Name | What it actually does |
|---|---|
| `evaluate_expression_async` | **local only**, despite having no "local" in its name. It registers its dedup members under a key beginning with `"local"` and calls the local evaluator directly |
| `evaluate_expression` | local only too (the synchronous form) |
| `evaluate_expression_remote` | **the dispatching entry point** — the one function whose name says "remote" is the only one that can decide *local*, because it is the one that takes `execution="auto"` and consults `choose_expression_evaluation_location` |
| `Checksum.fingertip` | calls the **local** evaluator, so no placement decision is taken anywhere in a fingertip chain |
| `_publish_expression_result` | does **not** mean "publish" in the sense of *Evaluating, recording identity and publishing*, above; its docstring is "Publish bounded cache interest" and it registers a tempref. It is to be renamed **`_tempref_expression_result`** |

What *is* remote-aware in a fingertip is **candidate discovery**: the reverse index is read from the local caches *and* from the database (`get_rev_transformations`, `get_rev_expressions`), so a client with no local cache can still find the chain. And a fingertip that happens *inside* a job runs on that job's host. Those are not counter-examples: they are the same rule — the work happens at the site that wants the buffer — applied at a different site.

### When a fingertip fails, and the materialize mode it needs

A fingertip is a **search**, not a single evaluation: it reads the reverse index, finds candidate producers of the wanted checksum and tries them (`contracts/scratch-witness-audit.md`). Two things therefore have to be pinned that an ordinary evaluation never raises — **what it reports when candidates fail**, and **how it asks the evaluator for a buffer** rather than for a result checksum it already holds.

#### What a failed fingertip reports: the cache miss, and nothing else

**A fingertip that does not produce the buffer raises `CacheMissError(checksum)`, on the checksum that was wanted, and that is the whole of what it reports.** No candidate's reason reaches the caller — not the sharpest one, not an aggregate, not a list. Whether the walk found no candidate at all or tried ten and lost all ten is not in the answer.

Three reasons, and the first alone settles it:

- **The order in which candidates are tried is not contract.** It follows whatever the local caches and the database happened to answer, so a client with a cold cache may try them in a different order from one with a warm cache. Any reason lifted out of that sequence would be an arbitrary choice presented as an explanation, and the same request could explain itself differently on two machines.
- **A candidate's failure is a fact about the candidate, not about the request.** The request asked for bytes; the honest answer is that they could not be produced here. Re-raising a candidate's exception in its place would attribute to the wanted checksum a failure that belongs to one producer of it — and "this process cannot execute that producer" is in particular a fact about *this process*, true of nothing else.
- **The error envelope carries `kind`, `message` and `checksum`** (*Errors*), so anything richer would either not survive a process boundary or force the envelope to grow a diagnostic protocol for one case.

**The investigation route is the reverse index, not the exception.** Seamless already records what an investigation needs: the `rev_transformation` and `rev_expression` records in seamless-database name the producers that claim the wanted checksum, and `contracts/execution-records.md` holds the execution metadata for the transformations among them — that page already names this as one of the two reasons execution records exist ("when fingertipping fails … the record is the breadcrumb back to the original execution context"). A caller that wants to know *why* queries those records and re-runs the candidate it cares about itself — for a transformation, `seamless-run-transformation` replays one from its checksum. **Tools that automate that walk may be developed later; they are not part of this contract, and a fingertip will not grow into one.**

Two consequences to keep in view:

- **A mismatched environment is silent, by design.** `__env__` is not enforced for Python — only declared binaries are checked — so a client whose environment differs from the one that produced the original recomputes a candidate, gets a *different* checksum, fails the `result == wanted` check and moves on. The caller sees a cache miss. That is the ruled behaviour and not a defect; it is also the shape in which accidental nondeterminism shows up at all (`contracts/scratch-witness-audit.md`, *Fingertipping is where accidental nondeterminism surfaces*), which is another thing the records are there to establish and the exception is not.
- **A fingertip failure is not sticky**, like every other materialization failure (*Expression failures are not cached*). Nothing is remembered, and the next request starts the search again — which is what makes a bare answer livable: retrying costs a search, not a poisoned checksum.

#### The materialize mode

**`materialize=True` is the evaluator-level flag that means: produce the buffer in this process; a recorded result checksum is not an answer.** It exists because a fingertip's target checksum is already known — the reverse-index mapping is *how the candidate was found* — so every short-circuit that answers with a checksum answers the wrong question.

- **Under it the resolution order's first two steps do not satisfy the call.** The process Expression cache and the database `expression` result (*Placement*, steps 1–2) may still be **read**, to find and confirm a candidate; they may not be **returned** as its answer. The call ends only with the buffer present here, or with a failure.
- **It is a parameter, not a side effect.** It must not be spelled as evicting the memo first: that is a global side effect standing in for a flag, it perturbs an unrelated cache for every other caller, and it does not generalize to the database hit at all. See *Status: publication and fingertipping*.
- **It is orthogonal to `scratch`, and the two must not be merged.** `scratch` says *who will hold the result*; `materialize` says *what counts as an answer*. A fingertip chain is local by ruling, so it carries no `scratch` at all; the one place the two meet is a **remote fingertip request**, which is a `materialize` call on the server side and a non-scratch write on the requester's behalf (*The requester's scratch decision*).
- **It is not a user-facing argument.** `Expression.compute()` and `run()` do not take it. The entry points that mean it already exist and say so by name — `Checksum.fingertip()`, and `Cell.fingertip()` / `Pin.fingertip()` once they do (`contracts/cells.md`) — and `materialize=True` is what they pass down.

*Where the code stands:* the failure half is **already how the code behaves** — both candidate loops are `except Exception: continue` and the walk ends in a bare `CacheMissError` — so what was previously listed as a defect is now the ruled behaviour, and nothing is to be changed there. The materialize half does not exist: there is no parameter, and the buffer is forced out of the evaluator by evicting a global memo. See the next section.

### Status: publication and fingertipping

The rules of *Evaluating, recording identity and publishing*, of *Fingertipping is exempt from "where the data is"* and of *When a fingertip fails, and the materialize mode it needs* are contract ahead of code on every point below.

- **Expression evaluation publishes its result buffer.** Every terminal branch of `_evaluate_expression_after_validation` calls `_publish_expression_result(…, buffer=…)`, which has no scratch parameter and so temprefs non-scratch; that sets `write_remote` and ends in a background hashserver write. Its sharpest form is the fingertip case: recovering a scratch or evicted buffer **re-adds it to the hashserver**, locally, with no dispatch involved, silently repopulating the store with exactly the buffers someone decided to keep out. The transformation branch of a fingertip does *not* have this defect (it temprefs `scratch=True`); the two branches of the same walk disagree, and the Expression branch is the wrong one.
- **The fix is not a scratch flag on `_publish_expression_result`.** Passing scratch down from the fingertip call site would leave *ordinary* evaluation publishing, which is equally wrong. The fix is to remove the publication and leave the refholder as the only publisher — while **keeping** the identity recording (`_expression_cache`, `set_expression_result`) and the HashType registration, which are a different act.
- **The expression dispatch carries no `scratch` flag.** The client sends only the four identity fields; the handler accepts those plus an optional validator pair and answers `{"result_checksum": …}` alone. So the executing side cannot learn whether the requester will hold the result, and cannot be told to publish on its behalf. The remedy is the parameter the transformation path already has, not new machinery.
- **`Cell.fingertip()` does not exist.** The only entry point is `Checksum.fingertip()`. A bare checksum has no owner and no scratch intent, which is plausibly why the publication above defaults to non-scratch; a Cell-level entry point is what makes the ownership rule expressible at all (`contracts/cells.md`).
- **Not on this list any more: a fingertip reporting no reason.** Both candidate loops are `except Exception: continue` and the walk ends in a bare `CacheMissError`. That was recorded here as a defect; it is **ruled to be the contract** (*What a failed fingertip reports*, above), so the code is right and the investigation route is the reverse-index records rather than the exception. The same ruling covers a candidate silently skipped because a mismatched environment recomputed it to a different checksum.
- **There is no "materialize" mode, only a cache-popping workaround.** `evaluate_expression_remote` short-circuits on the process cache and on the database result, both returning the result *checksum* without producing its buffer — the wrong answer for a fingertip, whose target checksum is already known and whose database mapping is how the candidate was found. Today's code works around this by evicting the memo first, a global side effect standing in for a missing flag. The flag, and the rule that a cache may be read but not returned under it, are in *The materialize mode*, above; any change here must preserve the distinction between "tell me the checksum" and "produce the buffer".

## Errors

Expression errors cross process boundaries as a structured envelope (`seamless.error_envelope`):

```json
{"error": {"kind": "cache_miss", "message": "...", "checksum": "64-hex-digest"}}
```

- Kinds with a reconstructable class: `cache_miss` (`CacheMissError`), `hash_type_validation` (`HashTypeValidationError`), `expression_evaluation` (`ExpressionEvaluationError`), `conversion` (`SeamlessConversionError`), `canceled` (`ExecutionCanceledError`, also produced by `asyncio.CancelledError`). Any other exception encodes as kind `execution`; a well-formed envelope with an unrecognized kind decodes to `WorkflowExecutionError` carrying the message and the kind — a deterministic execution failure, never a connection error.
- `CacheMissError` **keeps its checksum in `args[0]`**: the encoder takes the digest from the first argument, and the decoder reconstructs `CacheMissError(Checksum(hex))`. Agents may rely on `exc.args[0]` being the `Checksum`, not its display string.
- A job that answered — success, failure, or cancellation — is an **HTTP 200** response carrying either the result checksum or the envelope. 4xx/5xx mean *no job answered* and surface as `ClientConnectionError`, as do transport failures and malformed 200 bodies. A decoded job failure therefore never triggers a client retry or restart.

### Expression failures are not cached

**Nothing about an Expression is sticky.** Only successful results are recorded — in the process cache and in the database. A failed Expression records nothing and is simply retried on the next request.

This is deliberately unlike a Transformation, which caches its exception: an Expression is cheap to redo, so caching a failure would only risk poisoning a checksum. Materialization failure must not be sticky either: "not found anywhere" is a real terminal answer, but it is the trigger for fingertipping, not a cached failure.

Two things not to conflate with it:

- **Deduplication** is not caching. Concurrent callers for one Expression identity share a single in-flight evaluation and all receive the same result *or the same error*; the shared entry is removed after success, failure **or** cancellation, so the next caller starts fresh.
- **`Cell._standalone_exception`** is the *Cell* holding a failure (exposed as `.exception`, cleared by `clear_exception()`). That is Cell state, not the Expression layer caching anything.

## Deduplication

One in-flight evaluation per Expression identity, with a membership set of interested callers:

- a caller that arrives while an evaluation is in flight **joins** it rather than starting a second one, and awaits a shielded view of the shared future;
- a direct jobserver inherits this because it calls the core evaluator in its own process; the jobserver endpoint owns no active-expression map of its own;
- in daskserver mode the same ownership is preserved by giving equivalent submissions a deterministic Dask task identity, so duplicate requests resolve to one Dask evaluation;
- active work is process-local/scheduler-local and is never recorded in the database.

**This membership set is not the waiting set of *Cancellation*, below.** Today one code object (`_active_expressions`) serves both roles, which is exactly the conflation the settled model exists to undo: deduplication belongs to the **Expression identity**, while the waiting set belongs to the **checksum being materialized**, one layer down and shared with transformation input resolution, `.buffer` reads and mounts. They are keyed differently and they will be two objects.

A caller identifies itself to the set by a member id: a standalone `Expression` uses `id(self)`, and the workflow Context uses its demand key, which it deregisters when its own job is cancelled (node supersession, `Context.close()`). Two `Expression` objects with the same identity are therefore two members of one evaluation.

## Cancellation

**The cancellation mechanism does not belong to Expressions.** The only cancellable work is remote materialization of a buffer, which Expressions share with transformation input resolution, `.buffer` reads and mounts. Expression evaluation proper — deserialize, walk the path, convert, serialize, hash — is cheap and CPU-bound inside a single thread, so it could not usefully be interrupted even if there were a way to.

Three premises decide the shape of the mechanism, and each is a consequence of a rule stated elsewhere on this page:

- **A materialization's cost is unbounded**, which is what makes the machinery worth building at all. An Expression does not normally fingertip its input checksum, but it can, as a step in a fingertip chain — and **a chain may contain Transformations**. Do not read *Fingertipping is exempt from "where the data is"* as saying otherwise: the **frontier** bound there is about how much of the *ancestry* is walked, not about how much work the frontier itself is. Recomputing one frontier Transformation can cost hours.
- **Every Expression waits on *at most* one buffer — `folder → mixed` excepted.** The number of buffers an Expression waits on is exactly its **cost class** (*Cost class*, above), read as a waiting-set requirement:

  | Cost class | Buffers waited on | What that means for cancellation |
  |---|---|---|
  | **free** | **none** | there is nothing to materialize, so there is **no cancellable window at all**: the Expression never registers in a waiting set, and `softcancel()` answers `False` from the start. This class is not a corner case — it holds the **dummy Expression** (the most common Expression in the system), a null short-circuit, any conversion decidable from the checksum, the rule table and the cached `HashType`, and **every deep index conversion** |
  | **one buffer** (*one child*) | **exactly one** | the ordinary case, and the one the waiting set is designed for: it is keyed by that single checksum. Over a deep checksum the one buffer is the **index**, never a member |
  | **all children** | the index **plus every member** | `folder → mixed`, and nothing else |

  Materializing a deep checksum into a value is banned from Expressions except for `folder → mixed` (`contracts/deep-celltypes.md`), so **the waiting set is keyed by a single checksum in every case but that one**. `folder → mixed` is the only shape in the system that needs a **multi-checksum waiter**, and it is the only reason that case has to exist. (This premise used to read *exactly* one buffer. That was wrong at the free end, and wrong about something ordinary rather than exotic; what the mechanism actually needs is an upper bound of one, which is what the table gives.)
- **There is no cancel point once the data is present.** Evaluation is then near-instantaneous, so the buffer's arrival is the end of the cancellable window.

**Why latch-on and a delay rather than an eager abort.** The value of a cancel is *remaining resource cost × the chance that nobody else wants the output* (`contracts/cancellation.md`, *What cancellation is not for*). For a materialization the second factor is **low — lower than for a Transformation result** — because the same buffer is routinely wanted by somebody else: by **sibling projections of one parent** (`ctx.a.x` and `ctx.a.y` resolve the same root), by the **Transformation that takes the same checksum as an input**, and by a **revert**. An eager abort would therefore throw away work that another requester is about to ask for, which is exactly what latch-on and the linger exist to prevent.

The settled model:

- **A waiting set per in-flight materialization, keyed by checksum**, held at the materialization site in the buffer layer.
- **Latch-on**: a second requester for the same checksum joins the in-flight fetch instead of starting a second one.
- **Softcancel = deregister.** The fetch is aborted only when the set is empty, and then only after a **linger**; a requester arriving during the linger re-registers and the fetch continues.
- **No hard cancel at all** — a documented non-feature. The only leaf a hard cancel could kill is a shared fetch, which would merely make the other waiters fail and re-fetch. A single waiter pressing Ctrl-C is already covered: with one member, softcancel aborts the fetch.
- **No cancel point once the buffer is present.** Evaluation then runs to completion and its result is recorded.
- **Failure is not sticky** (above).
- **Soft deregistration cascades down fingertip chains**; a step shared with a live chain survives, because it still has a member of its own. **The leaf Transformation needs no special case**: the linger keeps its member registered for those few seconds, and it is killed only when its own set empties — softness cascading to the leaf, exactly as in `contracts/cancellation.md`.
- Vocabulary: **waiting set**, not refcount. It tracks who still wants a fetch that has not finished, which is a different thing with a different lifetime from the checksum reference lifecycle. The two meet in one place: the site holds a lifecycle claim for the duration of the linger.

### The linger

**Three independent arguments produce the linger**, which is why it is not an optimization to be tuned away:

1. **Somebody else usually wants the same buffer** — sibling projections, a Transformation over the same checksum, a revert (above).
2. **Convergence is normal in a fingertip chain.** Two chains often need the same intermediate, and one may arrive seconds after the other gave up.
3. **Abandoning mid-chain discards every intermediate**, and where those intermediates are `scratch` no trace of the work remains — so the next requester starts from nothing.

The linger is an internal constant — "a few seconds, not contractual" — at most a test hook, and is **not user-visible**. **It is a knob of its own.** The node-state-lifecycle self-edit revert hold (`contracts/node-state-lifecycle.md`, *Self-edit revert hold*) is a human-timescale window of the same order, but the two are **two knobs, not one shared constant**: they answer different events — a person reverting an edit, versus a second requester arriving for the same buffer — so tuning one must never retune the other, and each may be measured and moved alone. The linger is a few seconds, pending measurement; the revert hold's own figure is on that page. Its observable consequences are contract:

- after the last waiter leaves, a fetch may run on for a few seconds;
- it may still complete, and its result is then recorded and usable;
- the site holds a lifecycle claim meanwhile, so a `seamless.close()` landing in that window can block briefly or report an outstanding claim.

### Why deregistration, not task cancellation

Cancelling the caller's `asyncio` task is the right way to make it abandon an Expression — it unwinds the caller's own awaits — but task cancellation is not itself the deregistration mechanism, for four reasons:

- **it does not deregister**: cancellation knows nothing about the waiting set, so each site must leave the set in its own cleanup path, synchronously or under a shield, since an `await` inside an already-cancelled task raises at once;
- **it does not protect shared work**: if the caller's task *owns* the fetch rather than merely awaiting it, cancelling that task kills the fetch for every latched waiter too — a hard cancel in disguise. Shared work must instead be owned by a task belonging to the materialization site, with each waiter awaiting a derived or shielded future;
- **it does not stop what is not an `await`**: a thread (`asyncio.to_thread`), a subprocess, a jobserver request or a Dask future all keep running and keep holding their resource once the awaiting task is abandoned — the Dask case in *Implementation status* below is one instance of this;
- **it gives no delay**: a linger is by definition not "cancel the child the moment the parent is cancelled", so the site's task must outlive every individual waiter.

### API

**The rule is about the checksum-addressed substrate verbs**: `softcancel` means **deregister** everywhere in Seamless, and `cancel` means **hard kill** everywhere. A verb on a *handle* means something narrower — "this handle gives up": terminal for the handle, soft at the substrate, which is why `Transformation.cancel()` keeps its name (`contracts/cancellation.md`). An Expression handle has nothing terminal to mark and no hard operation to offer, so it carries only `softcancel()`.

| Name | Status |
|---|---|
| `Expression.softcancel()` | the only cancellation verb on an Expression |
| `Expression.cancel` | retired; raises, pointing at `softcancel()` and stating that Expressions have no hard cancel |
| `seamless.checksum.expression.softcancel_expression` | the module-level entry point |
| `seamless.checksum.expression.cancel_expression` | dropped (it was an alias of `softcancel_expression`) |

`softcancel()` returns `bool`, meaning **"I was a registered waiter and have now left"**:

- `False` when the Expression was not waiting — already complete, never started, past the buffer into the CPU phase, or **free**, since an Expression that needs no buffer never enters a waiting set at all (*Cancellation*, first premises);
- `False` again on a second call (idempotent);
- **it never means the work stopped.** With other waiters, or during the linger, the fetch continues, and a result that arrives anyway is recorded and usable.

There is no "cancelled" state to clear. Results are content-addressed and failures are not cached, so a caller that changes its mind simply asks again.

### Implementation status: cancellation

The settled cancellation model above is **ahead of the code**. What exists today:

- The waiting set lives at the **Expression** layer (`_active_expressions` in `seamless.checksum.expression`), not at the materialization site in the buffer layer, and buffer resolution itself is **not** deduplicated by checksum.
- There is **no linger**: when the last member deregisters, the in-flight remote request is aborted at once and the awaiting task receives `CancelledError`.
- `Expression.cancel()` exists and is soft; `Expression.softcancel()` does not exist yet, `cancel` is not retired, and `cancel_expression` is still an alias of `softcancel_expression`.
- `Expression.cancel()` is a **silent no-op for local in-flight evaluations**: `evaluate_expression_async` registers members under a 7-tuple key `("local", hex, path, input_celltype, celltype, str(validator), validator_language)`, while `cancel_expression` looks up the 4-tuple identity key. The call returns `False` while the evaluation keeps running. Only the remote path (`evaluate_expression_remote`, which registers under the 4-tuple with `member_id=id(self)`) can be deregistered.
- **Dask-dispatched Expressions cannot be interrupted mid-flight**: `dispatch_expression` awaits `asyncio.to_thread(thin.result)`, so cancelling the awaiting task neither cancels the Dask future nor frees the thread, which stays blocked until the remote side finishes. This is the confirmed half of "an abandoned waiter keeps holding a bounded resource", and it is the head-of-line blocking that justifies the mechanism.
- **The jobserver half of that is unconfirmed.** Whether an abandoned Expression materialization keeps holding a jobserver worker slot has not been read out of the dispatch/cancel path; it is recorded for *Transformations* that a jobserver cancel does not free the slot. It should be settled before the waiting set is built, because it materially changes how much the mechanism is worth.
- No soft-deregistration cascade down fingertip chains exists.
- Repo tests cover the remote path only: one member leaving keeps a shared request alive and both callers get the result; the last member leaving aborts the request; `cancel()` on an idle Expression returns `False`. There is no test for local in-flight cancellation.

## Deep checksums

An Expression whose `input_celltype` or `celltype` is `deepcell`, `deepfolder` or `folder` leaves the rule table of `contracts/celltypes-and-conversion.md` entirely and is governed by the much smaller table in **`contracts/deep-celltypes.md`**, which owns it. That page has the conversion table, the member-celltype rules, the flatness requirement and the reasons; do not re-derive them here. What belongs on *this* page is how the carve-out meets the Expression machinery:

| Expression concept | How a deep checksum behaves |
|---|---|
| **Path** | **exactly one step, and it is a string item** — an index lookup, selecting one member. A longer path is rejected, because a further step would continue into the **child**, which is a different checksum and therefore a different Expression |
| **Result of that one step** | one of exactly two targets, and nothing else: the **member celltype** (`mixed` for `deepcell`, `bytes` for `deepfolder`/`folder`), whose result checksum **is** the child's and which makes no new buffer; or **`checksum`**, the reference form, which makes a new 64-byte buffer holding the child's digest. Which of the two to use, and why the member celltype keys the child's own conversion at the *child's* checksum, is `contracts/deep-celltypes.md`, *What the one step yields* |
| **Zero-path conversions** | index-level and free (checksum-preserving), with exactly one exception: **`folder → mixed`**, the only conversion in the system that materializes children |
| **Application order** | this is the shape *project-then-convert* exists for: the step selects a child without materializing the parent, which the opposite order could not express |
| **Cost class** | decided by the identity tuple alone, as everywhere — but *strictly* so here: no deep conversion branches on nullity or on a cached `HashType`, so shape alone decides (*Cost class*, above) |
| **Fusion** | a deep step is a **barrier**. The run ends at it, and the child's own conversion is a separate Expression (*Fusion*, above) |
| **Connecting a deep source on a Cell** | the path-and-conversion wiring rule does **not** apply; a deep step necessarily changes the celltype, so path and conversion always travel together (`contracts/cells.md`, *Connecting*) |

**Status: settled contract, not yet enforced.** The Expression path contains no deep-celltype rules at all — no deep conversion table, no deep path rule, no flatness validator — and a deep celltype on either side of an Expression currently raises `HashTypeValidationError` before evaluation, because `deserializable_as` returns `False` for any celltype outside the 13 (`contracts/hashtype.md`). That `False` is retired by the ruling: under the contract `deserializable_as` raises `ValueError` when asked about a deep celltype, and the shape is admitted or refused at construction by the deep table instead (*When an Expression is vetted*). Enforcing it requires the Expression layer and pin unpacking (`unpack_deep_structure` / `pack_deep_structure`) to change **together, under one shared validator**, or the two layers will disagree about what a deep value is.

## Current limitations

- **Validators are not implemented, and their interaction with the caches is not specified.** Supplying `validator` or `validator_language` raises `NotImplementedError` from every evaluation entry point, before any cache lookup — so the refusal is total and the cache-hit case cannot arise. Reject-only semantics and the identity exclusion are settled; cache-hit behaviour *once validators run*, two validators under one identity, and the database column conflict rule are open. See *Identity*, "Validators are deferred".
- **No forensic "irreproducible expression" analogue exists.** There is no Expression counterpart of `IrreproducibleTransformation` (see `contracts/execution-records.md`); an Expression that yields a different result for the same identity tuple is not recorded anywhere.
- **Cancellation** — see *Implementation status: cancellation*.
- **Deep-checksum restrictions are unenforced** — see above.
- **The process-local Expression cache is unbounded** and result-only; it is cleared only by process exit or an explicit `get_expression_cache().clear()`.
- **Locality is process memory only** — *placement* does not yet consult a configured read-buffer directory (resolution already does); see *Placement*.
- **Evaluation publishes its result buffer**, and the dispatch carries no `scratch` flag; `Cell.fingertip()` does not exist. See *Status: publication and fingertipping*. Until the flag exists, a dispatched `run()` works only because evaluation publishes unconditionally — the right behaviour reached by a wrong mechanism, and a scratch owner's decision is silently overridden along with it.
- **A fingertip has no materialize mode.** The buffer is forced out of the evaluator by evicting a global memo, in place of a parameter. (That it reports no reason for a failed candidate is *not* a limitation — it is the contract: see *When a fingertip fails, and the materialize mode it needs*.)

## Non-goals

- **Execution environment.** An Expression has no code, environment, meta or scratch policy **of its own**. Anything that needs one is a Transformation. A *dispatch* does carry a `scratch` parameter — it has to, or interest could not cross a process boundary — but its value is the requester's and never the Expression's (*The requester's scratch decision, and what a bare Expression carries*).
- **Hard cancellation.** See above; it is a deliberate non-feature.
- **Failure caching.** See above; it is deliberate, not a missing optimization.
- **Value-level canonicalization.** An Expression produces whatever checksum its steps and target celltype produce; it does not re-serialize a result to normalize it (see `contracts/identity-and-caching.md`).
- **Publication.** Evaluating an Expression is not an assertion that anyone wants its buffer kept. Persistence is the refholder's act, never the evaluator's (*Evaluating, recording identity and publishing*).
- **Deep-celltype semantics.** Owned by `contracts/deep-celltypes.md`; this page states only how the carve-out meets Expression identity, cost, fusion and placement.
