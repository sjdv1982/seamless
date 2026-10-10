# Expressions (Contract)

An **Expression** is the structural, immutable counterpart of a Transformation: a closed, pure codebook over one input checksum (get-attribute, get-item, slice, celltype conversion) with **no execution environment**. It has no code, no pins, no dunders and no `__env__`. It cannot run user code, and it cannot fail nondeterministically.

Expressions and Transformations share one lazy, content-addressed DAG. An Expression's input may be a Checksum, a Cell or another Expression, and an Expression result may feed a transformation pin, just as a transformation result may feed an Expression.

A **Cell is a deferred Expression**: the mutable builder for the same recipe, either standalone or bound to a workflow Context node. Everything on the Cell side is in `contracts/cells.md`: `celltype` versus the read-only `input_celltype`, `.source` / `.checksum`, the write families, null, standalone reads, failures on the handle, projections and cell-level joins.

Expressions and the conversion engine are entangled. Buffer-level conversion results are cached as **empty-path Expressions**, so every conversion that produces a new buffer is recorded under an Expression identity (`contracts/celltypes-and-conversion.md`).

**Read this rule before anything else on this page: an Expression projects, and only then converts.** The path is applied to the input read at `input_celltype`. `celltype` converts *what the path selected*, never the input as a whole. An Expression never pre-converts its input, so it performs at most one conversion, and that conversion is always last. Get this backwards and a path silently means something else (*Application order*).

## Where this page sits: the stack

Each layer is defined **on top of** the one before it, and no page re-derives the layer below it.

| Layer | Page | What it adds |
|---|---|---|
| 1. **Celltypes and the type hierarchy** | `contracts/celltypes-and-conversion.md` | which checksums are valid as which celltype, and the subtype→supertype edges |
| 2. **HashType** | `contracts/hashtype.md` | a checksum-level classification that **disproves** readings and conversions, and **proves** readings where the word settles them, without fetching a buffer. Every `False` is a proof, and so is a `True` from `deserializable_as`. A `True` from `conversion_feasible` is not |
| 3. **Conversion** | `contracts/celltypes-and-conversion.md`, *Conversion engine* | the rule table, built on the hierarchy, which uses layer 2 to refuse or skip work before any buffer is fetched |
| 4. **Expressions** | **this page** | path steps plus at most one conversion, in that order. Layer 3 is exactly the **empty-path** case of an Expression, and its results are stored under empty-path Expression identities |
| 5. **Cells** | `contracts/cells.md` | a Cell is a *deferred* Expression: the mutable builder for the same recipe, standalone or bound |

**Deep checksums are a carve-out at layer 4, not a layer of their own.** An Expression over `deepcell`, `deepfolder` or `folder` obeys a separate, much smaller conversion and path table, owned by `contracts/deep-celltypes.md`. *Deep checksums*, below, says how the two tables meet.

Code locations:

| Concern | Module / symbol |
|---|---|
| Definition container | `seamless.expression_class` (`Expression`, `normalize_path`, `append_item_path`, `append_slice_path`); re-exported as `seamless.Expression` |
| Evaluation, cache, placement, deduplication, cancellation | `seamless.checksum.expression` (`ExpressionKey`, `ExpressionEvaluationError`, `evaluate_expression_local`, `evaluate_expression_local_async`, `evaluate_expression_placed`, `choose_expression_evaluation_location`, `get_expression_cache`, `parse_path`, `resolve_expression_value`, `softcancel_expression`, `wait_for_active_expression`) |
| Checksum-level pre-validation | `seamless.checksum.hash_type_validation.validate_expression[_async]` |
| Error envelope | `seamless.error_envelope` (`encode_error`, `decode_error`, `error_kind`, `WorkflowExecutionError`, `RunningLoopRefusal`) |
| Remote dispatch | `seamless_remote.jobserver_remote.run_expression` / `has_jobserver`, `seamless_remote.daskserver_remote.run_expression` / `has_daskserver`, `seamless_transformer.worker.dispatch_expression` |
| Server endpoint | seamless-jobserver `GET /run-expression` |
| Database | seamless-database `Expression` model → table `expression`; request types `expression` (GET/PUT) and `rev_expression` (GET only); protocol `("seamless", "database", "2.3")`. Client: `seamless_remote.database_client.DatabaseClient.set_expression_result`, via `seamless_remote.database_remote.set_expression_result` |

## The definition

`Expression` is a frozen, slotted dataclass:

```python
Expression(input_ref, path="", *, input_celltype=None, celltype=None,
           validator=None, validator_language=None)
```

- `input_ref` is a `Checksum`, a `Cell` (built at construction into its builder state), another `Expression`, or anything a `Checksum` accepts.
- `input_celltype` defaults to the typed source's celltype, else to `celltype`, else to `"mixed"`. It must agree with a typed source, or construction raises `ValueError`.
- `celltype` defaults to `input_celltype`. It is the **output** celltype (the `celltype` / `input_celltype` naming rule of `contracts/cells.md`).
- Builders return new Expressions and never mutate: `.item(key)`, `.slice(start, stop, step)`, `.as_celltype(ct)`, `expr[key]`, `expr[a:b]`, `expr.name`. Attribute access is projection, so retired API names are rejected before projection, and names starting with `_` raise `AttributeError`.

### Path syntax

The path is stored as a string and parsed at evaluation time (`parse_path`):

| Form | Step |
|---|---|
| `.name`, or a leading bare `name` | `("item", "name")` |
| `[token]`, where `token` contains `:` | `("slice", slice(...))` |
| `[token]`, otherwise | `("item", ast.literal_eval(token))` |

`append_item_path` writes a string key in dotted form when it is a Python identifier, and otherwise in bracket form with `repr()`. Any non-identifier key, including one containing `/`, must therefore be written in bracket form.

Applying a step (`_apply_step`): a string item key indexes a `dict` or a structured NumPy array (or one of its records), and **nothing else**. Over any other value it fails. A path never reads an attribute of a value: `.name` is item syntax, not `getattr`. Any other key indexes. A step that raises becomes an `ExpressionEvaluationError`.

A step is one of three kinds: a **string item** (`.name`, `["name"]`), a **positional item** (`[3]`, or any non-string literal) or a **slice** (`[1:4]`).

## Application order: project, then convert

**Evaluation reads the input buffer as `input_celltype`, applies every path step to that value in order, and only then serializes whatever the path selected as `celltype`.** `celltype` is never applied to the unprojected input. This is a property of evaluation, not of the identity tuple (*Identity*).

**An Expression never converts its input.** `input_celltype` is the celltype the input buffer is *read* at, not a conversion applied to it. The source must already be legally readable at `input_celltype`, and a typed source that disagrees is refused at construction (`ValueError`). So an Expression performs **at most one conversion, and it is always the last step**.

Get the order backwards and a path means something else. Take `input_celltype="plain"`, `celltype="str"` and path `[3]` over the JSON list `[10, 20, 30, 40]`:

- project-then-convert reads the list as `plain`, selects element `3` (the integer `40`) and renders that as `str`: `"40"`;
- convert-then-project would render the whole list as `str` (`"[10, 20, 30, 40]"`) and take character `3` of that string: `"0"`.

The two conventions agree only when the path is empty or the celltypes coincide. Everywhere else, a path written for one convention gives a silently different, and differently typed, answer under the other.

The order is not arbitrary:

- Under convert-then-project, the **output** celltype would decide the structure the path walks. A downstream declaration (a consumer pin's celltype, a cell's celltype) would silently redefine what an upstream path selects, and the path would have to be written against an intermediate value that exists nowhere and has no name. Project-then-convert keeps a path's meaning on the input side alone: `input_celltype` decides what the path sees, and `celltype` decides only how the selected value is rendered.
- It is the only order under which a path over a deep checksum selects a child without materializing the parent (`contracts/deep-celltypes.md`).
- It is the only order that converts the selected value rather than the whole parent.

The order is vacuous in exactly two cases, because there is nothing to sequence: an **empty path**, where there is no projection step (the conversion is then the empty-path engine of `contracts/celltypes-and-conversion.md`), and the **dummy Expression** (*The dummy Expression*), where neither step runs.

**Convert-then-project is spellable; it is just not one Expression.** It is the composition of `(input_checksum, "", X, Y)` with `(that result, path, Y, Y)`. The converted parent is a distinct Expression, with its own identity and its own cache entry. Unless `X → Y` is in the checksum-preserving trivial or reinterpret classes of `contracts/celltypes-and-conversion.md`, it also produces its own **new, parent-sized buffer**, which the path then walks. That cost is the point, and it is also why such a pair does not fuse (*Fusion*). The composition is what a Cell builds when `as_celltype` is spelled before a projection.

*Verified:* `_evaluate_expression_after_validation` (`seamless-core/seamless/checksum/expression.py`) deserializes the input buffer at `key.input_celltype` (`_deserialize_for_expression`), applies every parsed step (`_apply_step`), and only then serializes the projected value at `key.celltype` (`_serialize_expression_result`). Nothing on the remote path reorders this: `evaluate_expression_placed`, the jobserver `GET /run-expression` endpoint and `dispatch_expression` all pass `path`, `input_celltype` and `celltype` as three separate fields to the same evaluator, wherever it runs.

**Where the rule shows up on other pages.** It is one rule with four consequences, each owned elsewhere:

| Consequence | Page |
|---|---|
| Checksum-level validation asks `capabilities` of the **input** celltype, and asks `conversion_feasible` only where the path is empty | `contracts/hashtype.md`, *Where HashType is consulted* |
| The conversion engine is only ever the **empty-path** case, so the order is vacuous there | `contracts/celltypes-and-conversion.md`, *Conversion engine* |
| A one-step path over a deep checksum selects a **child checksum** without materializing the parent, which the opposite order could not do | `contracts/deep-celltypes.md`, *Paths* |
| On a Cell, `cell[3].as_celltype("plain")` and `cell.as_celltype("plain")[3]` are **different recipes**, and `as_celltype` mid-chain closes the Expression | `contracts/cells.md`, *Projections* |

## Identity

**The identity of an Expression is the 4-tuple `(input_checksum, path, input_celltype, celltype)`.** The one exception is a cell join, whose identity is the pair `(celljoin checksum, celltype)` (*Cell joins*). The tuple names a recipe's ingredients, not the order in which they are combined. That order (project, then convert) is fixed by evaluation and cannot be recovered from the tuple alone.

- **In process.** `Expression.identity_key` is the in-process form, and `__eq__` and `__hash__` use it. Its first element is `("checksum", hex)` for a concrete input, `("expression", …)` for an Expression input and `("object", id(...))` for an unresolved source. An unresolved dummy Expression stays an Expression input, so separate unresolved sources never collapse onto a shared identity of `None`.
- **Wire form.** `Expression.database_key` is `(input_checksum.hex(), path, input_celltype, celltype)`. It raises `ValueError` while the input is not yet a concrete checksum.
- **Canonical null.** `ExpressionKey` canonicalizes the input checksum against the input celltype on construction, so `sha256(b"")` as `bytes` and the canonical null are one identity (`contracts/celltypes-and-conversion.md`).
- **Database row.** The seamless-database `Expression` row has exactly this 4-tuple as its **composite primary key**, with `result` as the payload. A second write of the same key with the same `result` is accepted. A second write with a **different** `result` is refused: the stored row is kept, and the server answers HTTP **409** (`"Expression already exists with different result"`).
- **A conflicting result is returned unrecorded.** The process cache is insert-only: a second result for the same identity leaves the recorded result in place and logs an error naming both results. It is not queued for database recording, so this route cannot make the process cache and database disagree. A concurrent writer can still receive a background 409, which is logged without turning the evaluation into a failure. Failure to queue a record is a programming error and can still raise.
- **Reverse index.** The same 4-tuple is the **reverse index** that fingertipping walks: `rev_expression` in the database plus the process-local Expression cache. Given a wanted result checksum, Seamless finds the Expressions that produce it, fingertips their inputs and re-evaluates them (`contracts/scratch-witness-audit.md`).
- **Wire and storage form of the path.** `path` is serialized as **Seamless-`plain`**: canonical bytes, so one path has exactly one stored form. **There is no limit on path length, and no Expression is ever refused for it.** How seamless-database stores a path is internal to that service. Each celltype is stored in a 20-character column. **Identity is over the path itself**, never over an encoding of it.

### Validators are deferred

**Validator semantics are deliberately unspecified.** What is settled is small, and is listed here in full. Everything else about validators is **not contract yet and must not be tested against**.

| Settled | |
|---|---|
| **Refused at entry** | every evaluation entry point raises `NotImplementedError` when `validator` or `validator_language` is supplied, **before any cache lookup, any placement decision and any dispatch**. The refusal is *total*: an identity tuple whose result is already in the process cache or the database raises exactly as a fresh one does, and a validator-carrying Expression never reaches a cache, a server or the evaluator. A Cell records the refusal as `.exception` (`contracts/cells.md`) |
| **Reject-only** | a validator may refuse a result; it can never transform one. A validator is not a conversion |
| **Excluded from identity** | `validator` / `validator_language` are fields of the container and columns of the database row, but **not** part of the primary key. `evaluate_expression_local`, `evaluate_expression_local_async` and `evaluate_expression_placed` carry an explicit TODO recording the exclusion |
| **Columns unwritten** | nothing currently writes the two database columns |
| **Type** | a validator must be a `Checksum` (or hex); source text is not accepted |

**Open, and known to be open, for when validators run:**

- whether a validator runs on a **cache hit** (process cache or database), or only on a fresh evaluation;
- how two Expressions with the same identity tuple but **different validators** share one cache entry and one database row;
- what the database does when a second write carries a different validator for a key whose `result` agrees.

Exclusion from identity creates all three questions. Answering them is part of implementing validators, not a wording fix.

**These open questions do not contradict the total refusal; the refusal pre-empts them.** Because `NotImplementedError` is raised before any lookup, the cache-hit case cannot arise today. There is no behaviour to observe, which is why the question is open rather than settled by the code. Until validators exist, the only behaviour a test may pin is the `NotImplementedError`, **including on an identity tuple whose result is already cached**. That test is worth writing, because it is the one that distinguishes "refused at entry" from "refused only on a fresh evaluation".

### The dummy Expression

An Expression with an **empty path and `input_celltype == celltype`** is the identity (dummy) Expression. It resolves to its input checksum without any work: no buffer is fetched, no conversion runs, and the input checksum is recorded as the result. Checksum-level validation still applies (a known structural incompatibility is rejected without source content), but nothing else happens.

**Null does not make an illegal pair legal.** On a forbidden ordinary pair or an illegal deep pair, construction raises `ValueError` exactly as it would for any other input, and the engine raises `SeamlessConversionError` without fetching. This holds for the forbidden ordinary pairs, such as `python → int`, as well as for the illegal deep pairs.

The dummy case is load-bearing for the `.set_checksum` contract. `Cell.set_checksum` and `Pin.set_checksum` are the checksum variant of the three setters: they set the **input** checksum, not `.checksum`. So `.checksum` is normally `None` immediately afterwards, with two exceptions:

1. the underlying Expression is a dummy: `.checksum` returns the argument (as a `Checksum`) immediately, without evaluation;
2. the Cell is unbound: `.checksum` is then a computed property that evaluates the underlying Expression synchronously. This does not change the semantics of `set_checksum`.

The dummy case is a required special case, not an optimization: `.set_checksum` is instantaneous, so `.checksum` must answer immediately, without entering the evaluator.

*Verified:* the standalone `CellBase.checksum` getter implements exactly this fast path, including the empty-`bytes` → null canonicalization.

## Cost class

**An Expression's cost class is decided from checksum-level facts alone, never from the buffer content behind the checksum.** There are three classes: **free**, **one child** (for an ordinary celltype, which has no members, simply *one buffer*) and **all children**. They are named once, in `contracts/deep-celltypes.md`, *The organising principle*.

- **A non-empty path always costs one buffer, the input buffer**, whatever checksum is at the root: shape alone decides. Over a deep checksum this still holds for evaluation. The one buffer is the *index*, and no member buffer is fetched to produce the result checksum (`contracts/deep-celltypes.md`, *Paths*, says what each one-step target yields).
- **An empty path is not always free.** Whether it needs a buffer also turns on the specific checksum's nullity and on what its cached `HashType` already proves. So two Expressions of the same shape `(input_celltype, path shape, celltype)` do not necessarily have the same cost. Contrast the deep celltypes, where no conversion branches on anything but the declared celltypes, so shape alone does decide.

An agent can always decide the cost class without touching a buffer. That is why deep fan-out is restricted (*Deep checksums*), and why placement can be decided before any buffer is touched.

An Expression needs a buffer if and only if:

- the path is non-empty; or
- the path is empty, the celltypes differ, the input is not null (on a legal pair: *The dummy Expression*), and `conversion_needs_buffer(checksum, input_celltype, celltype)` is `True`. That is, the conversion cannot be decided from the checksum, the rule table and the cached HashType alone.

## When an Expression is vetted, and by what

Validation happens **twice**, and the two phases ask different oracles.

**At construction** nothing is known about the content behind the input checksum, so only structural facts can be checked. That is enough to refuse a shape that could never be legal:

| Shape at construction | Vetted by |
|---|---|
| **pathless** (a conversion, deep or not) | the **conversion engine**'s rule table, which also owns the few legal deep-to-deep conversions (`contracts/celltypes-and-conversion.md`, `contracts/deep-celltypes.md`) |
| **pathed**, with a deep celltype on either side | the **deep table** of `contracts/deep-celltypes.md`: exactly one string-item step, plus the member-celltype rules |
| **pathed**, over the 13 ordinary celltypes only | the **structural path rules** below: a path cannot be applied to an `int`, a string key cannot index a string, and so on |

**At evaluation** the input checksum's `HashType` is available, and a sharper pass runs. For a **pathed** Expression, the same path / `input_celltype` rules are re-applied against what the word now proves (`capabilities`). For a **pathless** Expression over the 13, `deserializable_as` and `conversion_feasible` do the vetting instead. Either rejection is a `HashTypeValidationError` at checksum level, before any buffer is fetched (`contracts/hashtype.md`).

### The structural path rules

These are decidable from `input_celltype` and the path **shape** alone, so they are checked at construction. The three step kinds are defined in *Path syntax*.

| `input_celltype` | string item | positional item | slice | after a step |
|---|---|---|---|---|
| `plain`, `mixed` | allowed | allowed | allowed | **unknown**: the element's type is data, and checking passes to evaluation |
| `binary` | allowed (a structured array's field) | allowed | allowed | **unknown**, as above |
| `text`, `str`, `python`, `ipython`, `yaml` | **refused** | allowed | allowed | still a string, so **the same row applies** to every further step |
| `bytes` | **refused** | allowed | allowed | a positional item yields an `int`, so **the path must end there**; a slice is still `bytes`, and the row continues |
| `int`, `float`, `bool` | **refused** | **refused** | **refused** | none: a scalar has no members |
| `checksum` | **refused** | **refused** | **refused** | none: a `checksum` is a reference, not a container (`contracts/celltypes-and-conversion.md`: every pair with `checksum` on either side is value-level) |
| `deepcell`, `deepfolder`, `folder` | **exactly one, as the whole path** | **refused** | **refused** | none: the deep table owns this row (`contracts/deep-celltypes.md`, *Paths*) |

A string item over a text-like celltype is refused at construction rather than left to evaluation: a string has no string-keyed members, so the step could only ever fail.

### Which refusal happens where

The line is exact, and it is what a test should assert against:

| The refusal follows from | When | Raised as |
|---|---|---|
| the declared celltypes and the path shape alone | **construction** | `ValueError`, the constructor's class for a statically ill-formed Expression, naming the offending step. No checksum is involved, so no `HashType` is consulted |
| the input checksum's `HashType` word | **evaluation**, before any buffer is fetched | `HashTypeValidationError` (a `ValueError` subclass; error-envelope kind `hash_type_validation`) |
| the value behind the checksum | **evaluation**, after the buffer is deserialized | `ExpressionEvaluationError`, naming the failing path step |

A **Cell** builds its Expression lazily, so a construction refusal surfaces at the first `build()`, read or `compute()`. A standalone Cell **records** it as `.exception` rather than raising, exactly as it does an evaluation failure (`contracts/cells.md`, *Failures*). It is the same refusal; only its delivery differs.

**HashType is never asked about a deep celltype.** Deep feasibility is structural: it turns on the declared celltypes and the path shape, never on the data, so the deep table settles it at construction. `deserializable_as` accepts only the 13 ordinary celltypes and **raises `ValueError`** on anything else. That is a caller error, not an answer (`contracts/hashtype.md`), and it keeps HashType's false-negative property intact instead of widening it to cover deep names.

## Results and caching

- Successful results are recorded in a process-global dict, `get_expression_cache()`, keyed by the 4-tuple, with the result checksum as the value. When `seamless_remote` is importable they are also recorded in the database `expression` table.
- A newly produced result buffer is kept in a weak-valued map, given a buffer-cache tempref, and **classified**: `register_hash_type_for_buffer` runs in the process that produced the buffer.
- `Expression.checksum` is an alias of `Expression.result`: the recorded result checksum, or `None`. Reading it also expresses public result interest, which is a refholder claim on the result. **That claim is scratch-neutral.** It protects the result from eviction for as long as it is held, and it neither writes the buffer to the hashserver nor overturns any scratch status. A claim publishes only for an owner with a scratch policy (a Cell, a Transformation, a Context node), and an Expression is not one (`contracts/internal/checksum-reference-lifecycle.md`). So reading a property can never defeat a scratch decision.
- `Expression.compute(execution="auto")` and `compute_async(execution="auto")` return the result checksum. `Expression.run()` (also `expr()`) computes and then materializes the value: local buffers first, then `Checksum.resolve()`, which asks the hashserver and raises `CacheMissError` when no buffer is found. `run()` does not fingertip.
- **Both raise on failure.** An Expression has no `.exception` and no state, so it has nowhere to record a failure and nothing to report it through: `compute()` and `run()` raise the evaluation failure itself. This is the one exception to "`compute()` reports a failure, `run()` raises it", which holds for the owners that record failures — Cell, Pin, Transformer and Transformation (`contracts/cells.md`, *Failures*, *How a failure is delivered*; ruled 2026-09-28). A Cell over an Expression records the Expression's failure and delivers it by that rule.
- **The two entry points differ in more than their return type.** Asking for a value asserts that this requester wants the bytes. That fixes the `scratch` decision a dispatch carries, and so decides whether a remotely evaluated result is reachable at all. It is the one thing on this page that can cause a hashserver write (*The requester's scratch decision, and what a bare Expression carries*).

**A result checksum does not imply a result buffer.** Evaluation temprefs the buffer it produced, but evaluation is only one way to obtain a result checksum. The checksum may also come from the process cache, from the database `expression` table, or from a checksum-preserving conversion that produced no new buffer. And a tempref is bounded and decays. So `.checksum` answering does not mean that `.run()` or `.value` will find bytes: both resolve, and both may raise `CacheMissError`. **Given that its input buffer is available, the only guaranteed way to obtain an Expression's result buffer is to fingertip the result checksum**: `Checksum.fingertip()`, or `Cell.fingertip()` / `Pin.fingertip()` where the result has an owner.

### Evaluating, recording identity and publishing are three different things

These acts are easy to conflate, and the code's naming used to conflate two of them. They are separate, with separate rules:

| Act | What it does | Who does it |
|---|---|---|
| **Evaluating** | produces a buffer in the evaluating process's memory. That is *all* it does | whichever process ran the Expression |
| **Recording identity** | stores the mapping Expression → result checksum, in `get_expression_cache()` and in the database `expression` table. The reverse index that fingertipping walks is made of these records, so recording must keep happening. It says nothing about where any buffer is | the evaluating process |
| **Publishing** | writes the result *buffer* to the hashserver, and nothing more: it takes no claim and asserts nothing about who holds the result (ruled 2026-09-29). A scratch result is never published | an owner's **non-scratch incref**, or the **executing side of a non-scratch dispatch**, on the requester's behalf. Never the evaluator's own decision |

**The vocabulary is the same on every page.** *Publishing* is the buffer write; *recording* is what happens to a result **checksum**. `contracts/internal/checksum-reference-lifecycle.md` uses "recording" in that second sense throughout and reserves "publishing" for the write.

**The rule: neither evaluation nor fingertipping publishes of its own accord.** An evaluation that writes its result buffer to the hashserver unasked is a bug, whether or not a fingertip drove it, because it makes persistence a property of *who evaluated* rather than of *who holds* or *who asked*. A result is published in exactly two ways. Either an owner increfs it non-scratch, for example a non-scratch Cell; that incref also overturns any scratch status (`contracts/internal/checksum-reference-lifecycle.md`). Or a non-scratch dispatch asks the executing side to write it (*Across a dispatch*, below). So a bare `Checksum.fingertip()` leaves nothing behind except a buffer in local memory, while `Cell.fingertip()` on a non-scratch Cell persists the result, because the Cell increfs it (`Pin.fingertip()` is the same verb on a pin). The fingertip site itself never decides: it holds a bare checksum, with no owner and no scratch intent.

**No site is exempt.** A fingertip chain writes nothing to the hashserver: not on a client, not in a jobserver, not on a Dask worker. A worker that fingertips a missing `scratch` input wants the buffer *for itself*, so it is the ordinary case, not an exception. Making persistence depend on *where* a recovery happened is exactly what this rule prevents. Fingertipping always runs locally: no process fingertips on another's behalf, and there is no such thing as a remote fingertip request.

**Across a dispatch, the interest travels with the request.** If the evaluating side never publishes, a remotely evaluated result stays in the worker's memory, and the client receives a checksum it cannot resolve. The client's own later incref cannot repair that, because there is no buffer in *its* process to write. The transformation path solves this by making `scratch` a parameter of the request: when the request is non-scratch, the executing side writes the result buffer, and the jobserver checks that it can resolve the result before answering. Expressions follow the same contract: the executing side publishes **on the requester's behalf, under the requester's scratch decision**. The rule above is thereby kept across the process boundary, not broken by it.

#### The requester's scratch decision, and what a bare Expression carries

**An Expression has no scratch policy of its own; a dispatch carries the *requester's*.** The request is parameterized, but the Expression is never the thing that decides. The value is **derived, never invented by the evaluator**:

| The requester | `scratch` on the dispatch |
|---|---|
| an **owner with a scratch policy**: a Cell (`Cell.scratch`, standalone or bound; default `False`), a workflow Context node | The owner's **own last link** carries its policy as a checksum request. Every intermediate link and anonymous node carries `scratch=True, materialize=False`, whatever the owner's policy. A source Transformation keeps its own policy unless a non-scratch holder receives its result through checksum-preserving links only |
| a **transformation's input**: input resolution, pin conversion, and Context edges into a pin | The request producing the pin's **own input** carries the pin's scratch (`contracts/pins.md`, *Scratch at the pin*). A non-scratch pin makes that request a value request. Earlier links carry `scratch=True, materialize=False`; a Transformation behind a link keeps its own policy |
| a **bare `Expression`** asked for a **checksum**: `compute()`, `compute_async()` (`.checksum` never evaluates; it only reports the recorded result) | **`True`.** The requester asked for a checksum, not bytes, so nothing is published. A value wanted later is obtained by recomputation: `run()` asks again, non-scratch, and a fingertip recomputes locally |
| a **bare `Expression`** asked for a **value**: `run()`, `expr()` | **`False`.** Asking for the value *is* the assertion that this requester wants the bytes, and across a dispatch the hashserver is the only channel by which they can arrive |

**A value request is answered only by bytes the requester can reach.** A value request (`run()`, `expr()`, and the input of a non-scratch pin) carries `scratch=False` and means "produce the bytes and make them reachable by me". A result checksum answers it only when its buffer is in this process or on the hashserver. A cached checksum (process cache or database `expression` row) without a reachable buffer is not an answer, and the Expression is **materialized** instead (*The materialize mode*):

- Placed locally, that is a local re-evaluation, which writes nothing.
- Dispatched without a scratch ban, the executing side materializes and writes the end result. Placement is optimistic when this client cannot reach the input: the hashserver or a private read folder on the executing side may still have it.
- A scratch intermediate whose recorded checksum is unreachable is evaluated again here only when the next link misses its caches and needs the bytes. This is not a fingertip: the owner has the recipe. Nothing is written. The first link may run remotely and fail before any download; later links run here once the intermediate is materialized. A thin client cannot materialize a scratch Transformation if its execution environment exists only remotely.

A checksum request keeps the short-circuit: any recorded checksum answers it. That covers `compute()`, a Cell's getters and `compute()` whether the Cell is scratch or not, a Context cell node (ruled 2026-09-30), and the input of a scratch pin. For a non-scratch owner, `scratch=False` still makes a dispatch it causes write the end result, but a recorded checksum whose buffer is unreachable is accepted as is.

**This is how `run()` obtains a remotely produced buffer without breaking the publication rule.** The executing side writes the end result because the *request* told it to, on the requester's behalf, and, as on the transformation path, the jobserver checks that it can resolve the result before answering. The evaluator still decides nothing. **This is an evaluation, not a fingertip**: a write made on somebody else's behalf, of the end result only, never of an intermediate. Fingertipping never makes such a write.

**That write is publishing, and it asserts nothing.** Publishing is only the buffer write (*Evaluating, recording identity and publishing*). After a bare `run()` nobody holds the result, and no claim is taken with the write: the entry is written, the requester resolves it, and with nothing increfing it, the buffer is as evictable as any other unheld buffer. Durability still requires an owner, on the requester's side. What matters is that **the write is not the evaluator's decision.** A bare `run()` on a locally placed Expression writes nothing; the same call on a dispatched one writes, because that is the only way the bytes can arrive. A caller that wants no write even then (against a hashserver that is deliberately kept thin, say) uses `execution="local"`, and pays the input transfer instead.

Three consequences, all contract:

- **Locally placed, nothing is written either way.** The buffer is in this process's memory, which is all `run()` needs, so `scratch` has no publication effect on a local evaluation. **The flag is observable only across a dispatch.** The result of an Expression still does not depend on where it ran (*Placement*); only its *persistence side effect* does, and that is the requester's to choose.
- **`compute()` never causes a write, anywhere.** A client that asks for a checksum and gets one may be unable to resolve it. That is not a defect: it is *A result checksum does not imply a result buffer*, one layer down.
- **A scratch owner's `.value` may miss, and that is the scratch contract, not a defect.** A scratch Cell whose Expression was dispatched receives a checksum and no buffer. `.buffer` and `.value` resolve and never fingertip (`contracts/cells.md`), so they raise `CacheMissError`, and the explicit route to the bytes is `Cell.fingertip()` / `Pin.fingertip()`. A scratch *transformation* result behaves the same way. An agent that wants a dispatched value with no hashserver write at all has two other options: evaluate locally (`execution="local"`, paying the input transfer that placement avoided), or fingertip.
- **`scratch` is not part of identity, so it is not part of the deduplication key** (*Deduplication*). A dispatch is made under the **strongest request among the members at the moment it is made**: non-scratch wins. A member that joins afterwards and needs more does not change the dispatch retroactively. It resolves the result checksum as usual and, finding no buffer, asks again: non-scratch if it was placed remote, or by evaluating here if it is a local or materializing caller (*The materialize mode*). Asking again is always safe, because results are content-addressed and failures are not cached (*Expression failures are not cached*).

A non-scratch Cell is not immune either. Under specific circumstances, usually an external eviction or cleanup of the hashserver's directory contents, its buffer and value may be unavailable. `Cell.fingertip()` then restores them, and the Cell, being non-scratch, persists what it recovers.

## Fusion

An Expression's input may be another Expression, so a recipe is in general a **chain**. **Chains are fused as far as the codebook allows, always, and the fused form is the definition.** What a recipe computes must not depend on how its intermediates happened to be split or named. This is the *Application order* principle applied one level up.

**Four adjacent pairs are possible.** An Expression is *read, project, convert*, in that order, and there are two kinds of step to pair:

| adjacent pair | fuses to | when |
|---|---|---|
| **path + path** | one Expression, paths concatenated | always |
| **conversion + path** | one Expression over the *source's* checksum, with `input_celltype` set to the converted celltype | only when the conversion is **pathless** (its own Expression has an empty path, so what it converts is a checksum) **and checksum-preserving**: the trivial and reinterpret classes of `contracts/celltypes-and-conversion.md`. A conversion that follows a path inside its own Expression converts a value that has no checksum, so it closes the run like any other conversion, whatever its class |
| **path + conversion** | already one Expression | — |
| **conversion + conversion** | **never fuses; it stays two Expressions** | — |

**A conversion that produces a new buffer cannot fuse into a following path.** The path has to be applied to the converted bytes, so that conversion's result is a genuine input: the chain keeps two members, and the outer one takes the inner's result checksum. This is the practical edge of the rule that conversion is not reinterpretation.

**Why two conversions never collapse into one.** There are two reasons, and the first alone settles it:

- **An Expression has exactly one `input_celltype` and one `celltype`**, so it can express **at most one conversion**. `A→B` followed by `B→C` has no single-Expression spelling. The question is not whether to fuse it; it is two Expressions.
- **Composition is not associative in the conversion table.** `A→C` may be a *different rule* from `A→B→C`, sometimes deliberately: `text→mixed` is defined as `text→str`, explicitly not as `text→plain`, and `yaml→mixed` likewise (`contracts/celltypes-and-conversion.md`, *The complete matrix*). Collapsing the chain would silently change what it computes. Fusing conversions would also mean fusing **across** a `conversion_chain` entry, whose intermediate is chosen by the table, not by the user.

So each conversion keeps its own identity 4-tuple and its own cache entry, and the outer one takes the inner's **result checksum** as its input: the ordinary two-member chain. Consecutive conversions arise readily. `cell.as_celltype("text").as_celltype("str")` is two, because `as_celltype` mid-chain closes the Expression (`contracts/cells.md`, *Projections*). Nothing is lost by not fusing them: the intermediate is a real, nameable result, and if it is checksum-preserving it costs no buffer anyway.

**A deep step is a barrier and forms no pair.** A one-step path over a deep checksum yields a **child checksum**, so a following path would project into the checksum rather than into what it names. The run ends at the deep step, and anything after it (a further path, or the child's own conversion) is a separate Expression over the child checksum. This is not only a correctness point. `contracts/deep-celltypes.md` restricts the one-step result precisely so that the child's conversion is keyed at the **child's** checksum, and is therefore shared by every parent index that references that child. Fusing it into the parent's Expression would re-key that shared work under each parent.

**What an Expression corresponds to.** Not a cell, and not an edge: a **maximal fusible run** of edges. Building a bound Cell's recipe walks its incoming edge backwards, accumulating projecting edges, and closes the run at the first of:

- a **conversion**. A checksum-preserving one is absorbed into the run's `input_celltype`; any other is left outside the run. At most one can ever be absorbed, because an Expression has exactly one `input_celltype`;
- a **deep step** (the barrier above);
- a **join**: a cell join has several inputs and no path, so it forms no pair (*Cell joins*);
- the end of the chain: a concrete checksum.

The run becomes one Expression, `(the run's root checksum, the concatenated path, input_celltype, the cell's own celltype)`, and is evaluated where the root's data is. Intermediates **inside** a run get no Expression, no identity and no cache entry. A *named* intermediate still gets its own Expression, because its checksum is demanded on its own account; that is a second, separate recipe, not a member of this run.

A fused Expression's failure belongs to the node whose recipe it is: the downstream end of the run. Anonymous intermediates inside the run have no node to carry the failure, which is why the error names the failing path step; that is what locates it.

**Identity.** A collapsed chain has a genuinely different identity. `(root, "[3][1]", X, X)` is not the 4-tuple `(intermediate, "[1]", X, X)`, so it is a different database row and a different cache entry that arrives at the same result checksum. That is not a conflict: the reverse index simply gains a second route to that result (`contracts/scratch-witness-audit.md`). Where a chain does *not* collapse, the outer member's input resolves to the intermediate's checksum, and the key is exactly the one an unfused evaluation would have used.

## Placement: an Expression is evaluated where the data is

**Placement is contract.** A jobserver or daskserver counts as closer to the hashserver than the client, so an input the client does not hold is evaluated there rather than downloaded. What is contract is the *rule for choosing* where to evaluate. Placement is no more part of an Expression's identity than of a Transformation's: the identity is the 4-tuple, and the result must not depend on where the Expression ran.

`execution` takes `"auto"`, `"local"` or `"remote"`. **These three values are an argument of an Expression evaluation, not the `execution:` configuration key that selects a transformation backend** (`contracts/execution-backends.md`), and `local` and `remote` mean something narrower here. `"auto"` is the default on every path that evaluates an Expression: `Expression.compute` / `compute_async` / `run`, transformation dependencies, pin preparation, and workflow Context projections (`Context(expression_execution=...)` overrides it for one Context).

**`"local"` means *the input buffer is already here***: in this process's memory, or in an explicitly configured read-buffer directory (below). **`"remote"` means *it is not here*, whether or not a backend is available.** `choose_expression_evaluation_location` answers only that question: local if no buffer is needed or if the input buffer is already in process memory, remote otherwise.

Resolution order (`evaluate_expression_placed`):

1. the process-local Expression cache;
2. the database Expression result;
3. local evaluation, when no buffer is needed or the input is local;
4. jobserver/daskserver dispatch, when it is not local and a server is configured;
5. local materialization from the hashserver, when no server is configured (the local evaluator resolves the input through `Checksum.resolution()`, and `CacheMissError` propagates if it cannot);
6. resolution of the result checksum, through the hashserver if necessary, when a value is wanted.

For a value request, steps 1 and 2 answer only when the result buffer is reachable (*A value request is answered only by bytes the requester can reach*).

Rules:

- **No silent fallback once a *configured* server fails.** Availability is queried without side effects (`has_jobserver()` / `has_daskserver()`). A missing backend downgrades `"auto"` to local *before* dispatch, but connection, restart and evaluation errors from a configured server propagate.
- **Explicit `"local"` and `"remote"` never fall back.** `"remote"` raises `ExpressionEvaluationError` when `seamless_remote` is unavailable, and `RuntimeError` when no client is configured. `"local"` never dispatches. Only `"auto"` may downgrade.
- **Dispatch target.** A configured jobserver is used first. A client with no jobserver but a configured daskserver submits the Expression to the Dask scheduler itself. A jobserver with a Dask client forwards the Expression to a Dask worker, passing only the identity fields: it never downloads the input in order to forward it. Only `ClientRestartRequiredError` is retried (once, then the next client); a decoded job failure is never retried.
- **Synchronous evaluation inside a running event loop is refused, not failed.** `Expression.compute()` in a running loop evaluates only when the location is local; otherwise it raises `RunningLoopRefusal`. A standalone Cell getter turns that refusal into `None`, with the Cell left `waiting`, no exception recorded and nothing dispatched. Outside a loop, the synchronous path drives the full asynchronous path through `asyncio.run`.
- **A dispatched `run()` resolves its result from the hashserver, and step 6 is not an accident of deployment.** It succeeds only because the step-4 request carried the requester's scratch decision and the executing side wrote the end result on its behalf. A dispatched `compute()` carries no such decision and leaves nothing for step 6 to find (*The requester's scratch decision, and what a bare Expression carries*).

Two derived rules:

- **The result, including the exception type, must not depend on where the Expression ran.** That is what the structured error envelope buys (*Errors*).
- **HashType classification is owned by whichever process holds the buffer**: the client for local evaluation, the jobserver for direct evaluation, the Dask worker for daskserver evaluation. A process that receives only a checksum classifies nothing and uploads nothing. Jobserver and daskserver responses are checksum-only; HashTypes travel through the database.

**Locality includes an explicitly configured read-buffer directory.** A buffer in a configured local read-buffer directory counts as **local**, and the Expression is evaluated here rather than dispatched: the client can read those bytes for free, and a server round trip for them is waste. Read-buffer directories are consulted **before** any hashserver query, and a hit means local placement. The gate is deliberately narrow, an *explicitly configured* read-buffer-directory path and never a generic filesystem scan, so that placement stays a **cheap and deterministic** check. A filesystem check against a configured path is allowed; this relaxes the earlier "side-effect-free" wording, and an index-only alternative is not required.

**This definition of *local* deliberately deviates from the convention.** Elsewhere in Seamless, *local* means this process's memory, and a buffer in storage is not local (`contracts/execution-backends.md`). Placement treats the two stores asymmetrically because it asks where the bytes are *closest*. The hashserver is assumed to be local to the jobserver's or daskserver's file system, so a buffer that is only on the hashserver is closer to the server than to the client, and the Expression goes there. A read-buffer directory is assumed to be local to this process (a remotely mounted read-buffer directory is assumed not to occur), so a buffer there is closest to this process, and the Expression stays here.

The rule concerns the **input** buffer, which is what placement is about. **Resolution already behaves correctly**: `Checksum.resolution()` goes through `buffer_remote.get_buffer`, which queries every configured read *folder* before any read *server* (`seamless-remote/seamless_remote/buffer_remote.py`), so steps 5 and 6 already prefer a local directory. The check is split over two functions: `choose_expression_evaluation_location()` checks process memory, and when it answers remote, `evaluate_expression_placed()` checks the configured read-folder clients before dispatching. A directory hit materializes the input locally and changes the final placement to local.

### Fingertipping is exempt from "where the data is"

**Fingertipping always runs locally and never writes to the hashserver.** There is no exception: not for a manual fingertip, not inside a job, not at any site, and not for the end result of a chain.

**A fingertip chain runs in the process that wants the buffer. That is contract, not a placement compromise.** Nothing in the chain is dispatched: neither its Expressions nor its Transformations. With a job server active there are two cases. The canonical statement is `contracts/scratch-witness-audit.md`, *Where a fingertip chain runs, and what it leaves behind*, summarized in `contracts/identity-and-caching.md`, *Fingertipping under remote execution*.

- **Case 1: an input fingertip inside a job.** This is the common case. A transformation, dispatched to the job server like any other, fingertips a missing scratch input when it runs. The chain runs **locally to that job**, and nothing in it is dispatched again. (On a daskserver the work may land on another Dask worker; Dask moves that data between workers itself, outside Seamless.)
- **Case 2: a manual fingertip.** An explicit request for the bytes: `Checksum.fingertip()`, `Cell.fingertip()`, `Pin.fingertip()`, `Transformation.run()` (which fingertips its result) or `seamless-fingertip`. **Local evaluation is the norm, even while a job server is active**: the chain runs in the requesting process.

**Neither case writes anything to the hashserver, because there is no buffer-return channel.** A remote evaluation answers with a *checksum* and nothing else (the jobserver's `run-expression` handler returns `{"result_checksum": …}`), so a remotely evaluated result can reach the requester only by being written to the hashserver. Dispatching a fingertip is therefore not a placement choice with a transfer cost: it is a placement choice that **must publish**. And a fingertip exists precisely because a buffer is absent, which is always the consequence of a decision: a `scratch` policy or an eviction. Remote evaluation would re-add exactly the entry that decision kept out or removed. Evaluating where the buffer is wanted materializes it in process memory only, and so is the only placement that respects that decision.

Three things follow, and they are contract:

- **The cost is bounded by the frontier, not by the ancestry.** `fingertip` resolves at every level before recursing, so the walk stops at the first checksum that ordinary resolution can serve (local buffer cache, then hashserver). What is recomputed locally is the frontier of the absent region, not the whole history. For a manual fingertip the target reaches the client either way, so local recomputation transfers the frontier *instead of* the target. That is normally less, since the archetypal scratch shape is a large output derived from smaller stored inputs. **This bounds how far back the walk goes, not the work.** The frontier may itself be a Transformation that costs hours, which is why a materialization's cost is unbounded, and why it is worth being able to abandon one (*Cancellation*).
- **Fingertipping assumes that the process that wants the buffer can execute the chain's transformations.** In case 1 that is the job's worker; in case 2 it is the requester. A thin client with no conda environment, compiler or declared binaries cannot execute such a candidate. A failed search reports a `CacheMissError` with a category, not the candidate's environment traceback (*What a failed fingertip reports*).
- **Two modelling rules keep a graph out of the expensive shape.** Fingertipping a large parent in order to keep one small item is real, and there local evaluation is the costly choice. It is reachable only by opting into it. **Do not scratch a small derived cell**: if it is stored, resolution serves it and no chain is built. **Make an item-addressed large parent deep**: a path step over a deep checksum selects a sub-checksum without materializing the parent (`contracts/deep-celltypes.md`). Both rules are in `contracts/scratch-witness-audit.md`.

An optimization remains available and is **not** recommended: remote evaluation followed by immediate hashserver eviction. It buys the projection case at the price of a write that scratch or eviction had excluded, and anything expensive enough to justify it should not have been scratched.

**The wrong model.** *"A fingertip chain is only orchestrated locally; each Expression in it is dispatched to where the data is, and each Transformation runs on the server."* Every clause of that is false: the whole chain runs where the buffer is wanted, in the job (case 1) or in the requester (case 2). `Checksum.fingertip` calls the local evaluator, `evaluate_expression_local_async`, and never `evaluate_expression_placed`, so no placement decision is taken anywhere in a fingertip chain.

What *is* remote-aware in a fingertip is **candidate discovery**. The reverse index is read from the local caches *and* from the database (`get_rev_transformations`, `get_rev_expressions`), so a client with no local cache can still find the chain. And a fingertip *inside* a job (case 1) runs on that job's host. Neither is a counter-example: both are the same rule, that the work happens at the site that wants the buffer.

### When a fingertip fails, and the materialize mode it needs

A fingertip is a **search**, not a single evaluation. It reads the reverse index, finds candidate producers of the wanted checksum and tries them (`contracts/scratch-witness-audit.md`). So two things must be pinned that an ordinary evaluation never raises: **what it reports when the candidates fail**, and **how it asks the evaluator for a buffer** rather than for a result checksum it already holds.

#### What a failed fingertip reports

**A fingertip that cannot produce the buffer raises `CacheMissError(checksum)` with a `fingertip_category`.** Its first argument remains the wanted checksum. The category is the highest-ranked outcome across every candidate tried, including categories carried up from nested fingertips:

| Rank | `FingertipCategory` wire name | Outcome |
|---|---|---|
| 1 | `materialization` | No candidate exists; a definition or input is unavailable; or a matching result buffer remains unreachable. |
| 2 | `failed_transformation` | A Transformation candidate raises during execution. |
| 3 | `irreproducible_transformation` | A Transformation candidate runs and returns a different checksum. |
| 4 | `irreproducible_expression` | An Expression candidate returns a different checksum or raises after previously recording a result. |

**The maximum is independent of candidate trial order.** Local caches and the database may supply candidates in different orders; choosing the highest category gives the same answer. A category describes the search, not the exception class of a particular candidate. Cancellation (`asyncio.CancelledError`, `ExecutionCanceledError`) and infrastructure failures (`ClientConnectionError`, `ClientPayloadError`, timeouts) propagate as themselves and have no category.

**The investigation route remains the records and indexes.** The database's forward, reverse, and automatic irreproducible rows identify producers and divergent results; the hashserver index shows which buffers are stored. Execution records retain the original Transformation context (`contracts/execution-records.md`). A forensic caller queries these records and re-runs a candidate it chooses. The error envelope carries the category across process boundaries (*Errors*), without exposing a candidate traceback as the wanted checksum's failure.

Two consequences:

- **A mismatched environment is reported.** `__env__` is not enforced for Python; only declared binaries are checked. If a recomputed Transformation returns a different checksum, the fingertip reports `irreproducible_transformation` and an automatic irreproducible row records that observation. The original forward result remains in place.
- **A failed fingertip is not sticky.** The next request searches again. An automatic irreproducible row is evidence, not a block: the Transformation remains available as a fingertip candidate until explicitly quarantined in manual mode (`contracts/execution-records.md`).

#### The materialize mode

**`materialize=True` is the evaluator-level flag that means: produce the buffer in this process; a recorded result checksum is not an answer unless its buffer is already here.** It has two callers:

- A fingertip. Its target checksum is already known (the reverse-index mapping is *how the candidate was found*), so every short-circuit that answers with a checksum answers the wrong question.
- A value request (*A value request is answered only by bytes the requester can reach*). It needs the buffer, either locally or, when dispatched, on the executing side before that side writes it. At the dispatching entry point (`evaluate_expression_placed`), `materialize` takes the looser client-level form: a cached checksum answers if its buffer is reachable here *or on the hashserver*. Otherwise the local evaluator is called with `materialize=True`, or the dispatch goes out non-scratch.

Its rules:

- **Under it, the first two steps of the resolution order do not satisfy the call.** The process Expression cache and the database `expression` result (*Placement*, steps 1–2) may still be **read**, to find and confirm a candidate, but may not be **returned** as the answer. The call ends only with the buffer present here, or with a failure.
- **Joining an in-flight evaluation is not an answer either, unless it leaves the buffer here.** A materializing caller joins an evaluation of the same identity that is already in flight, like any other caller (*Deduplication*). A local evaluation leaves its buffer in this process, which answers the call. A dispatched one, scratch or not, leaves it elsewhere. When the joined result's buffer is not here, the caller evaluates the Expression **here**, without joining again, as its own work outside any member set. It never re-dispatches: this is what a local `run()` and every fingertip do. At the dispatching entry point a value request placed remote follows the looser client-level form instead, and asks once more, non-scratch (*The requester's scratch decision*).
- **It is a parameter, not a side effect.** It must not be spelled as evicting the memo first. That would be a global side effect standing in for a flag: it perturbs an unrelated cache for every other caller, and it does not generalize to the database hit at all.
- **It is orthogonal to `scratch`, and the two must not be merged.** `scratch` says *who will hold the result*; `materialize` says *what counts as an answer*. A fingertip chain is local by ruling and never writes, so it carries no `scratch` at all, and the two never meet.
- **It is not a user-facing argument.** `Expression.compute()` and `run()` do not take it. The entry points that mean it say so by name: `Checksum.fingertip()` passes `materialize=True` (and `Cell.fingertip()` / `Pin.fingertip()` delegate to it), while `run()` means it through `scratch=False`, whose default implies it. An owner's checksum request passes `scratch` and `materialize=False` separately (`Expression._compute_for_owner`, `_available_input_checksum`, the Context's projection), so a non-scratch Cell does not mean it.

## Errors

Expression errors cross process boundaries as a structured envelope (`seamless.error_envelope`):

```json
{"error": {"kind": "cache_miss", "message": "...", "checksum": "64-hex-digest", "fingertip_category": "materialization"}}
```

- **Kinds with a reconstructable class:** `cache_miss` (`CacheMissError`), `hash_type_validation` (`HashTypeValidationError`), `expression_evaluation` (`ExpressionEvaluationError`), `conversion` (`SeamlessConversionError`) and `canceled` (`ExecutionCanceledError`, also produced by `asyncio.CancelledError`). Any other exception encodes as kind `execution`. A well-formed envelope with an unrecognized kind decodes to `WorkflowExecutionError`, carrying the message and the kind: a deterministic execution failure, never a connection error.
- **`CacheMissError` keeps its checksum in `args[0]`.** The encoder takes the digest from the first argument, and the decoder reconstructs `CacheMissError(Checksum(hex))`. The optional `fingertip_category` field carries one of the four wire names above; an unknown value makes the envelope malformed. An ordinary cache miss may omit the field. Agents may rely on `exc.args[0]` being the `Checksum`, not its display string.
- **HTTP status.** A job that answered (success, failure or cancellation) is an **HTTP 200** response carrying either the result checksum or the envelope. A 4xx/5xx means *no job answered* and surfaces as `ClientConnectionError`, as do transport failures and malformed 200 bodies. So a decoded job failure never triggers a client retry or restart.

### Expression failures are not cached

**Nothing about an Expression is sticky.** Only successful results are recorded, in the process cache and in the database. A failed Expression records nothing, and the next request simply tries again.

This is deliberately unlike a Transformation, which caches its exception. An Expression is cheap to redo, so caching a failure would only risk poisoning a checksum. Materialization failure is not sticky either: "not found anywhere" is a real terminal answer, but it is the trigger for fingertipping, not a cached failure.

Two things not to confuse with it:

- **Deduplication is not caching.** Concurrent callers for one Expression identity share a single in-flight evaluation and all receive the same result *or the same error*. The shared entry is removed after success, failure **or** cancellation, so the next caller starts fresh (*Deduplication*).
- **`Cell._standalone_exception`** is the *Cell* holding a failure (exposed as `.exception`, cleared by `clear_exception()`). That is Cell state, not the Expression layer caching anything.

## Deduplication

**There is one in-flight evaluation per Expression identity, with one member set: the member set keyed by Expression identity.** Its key is the full identity 4-tuple `(input_checksum, path, input_celltype, celltype)`, the same key used for evaluation and caching. Its members are the callers that still want that evaluation's result. This one keyed entry both deduplicates equal Expressions and tracks who still wants the shared work, and it is the set that *Cancellation* acts on. `contracts/cancellation.md` and `contracts/internal/checksum-reference-lifecycle.md` refer to it; this page is its definition. (Some code comments and test names still call it the *waiting set*. It is the same set, and it is a member set, never a refcount.)

- **It is keyed by the Expression, not by a checksum.** Two different Expressions that need the same input buffer are members of two different evaluations, and softcancelling one never touches the other. They may still share the *fetch* of that buffer, which the buffer layer deduplicates by checksum on its own (*Buffer fetches are shared by checksum*). That is a separate mechanism, and nobody is a member of it.
- **It is shared by local and dispatched evaluation.** A caller that arrives while an evaluation of the same identity is in flight **joins** it rather than starting a second one, whether that evaluation is local or dispatched. It then awaits a shielded view of the shared result. A caller that needs the buffer in this process and finds it absent from the shared result evaluates once more, here, outside the member set (*The materialize mode*).
- **Only callers that would do work become members.** A cache hit that answers the call, and a **free** Expression (one that needs no buffer: *Cost class*), return before the member set is consulted, and never become members.
- **Members.** A caller identifies itself by a member id. A standalone `Expression` uses `id(self)`, so two `Expression` objects with the same identity are two members of one evaluation. The workflow Context uses its demand key, which it deregisters when its own job is cancelled (node supersession, `Context.close()`). Any other caller (transformation dependency resolution, pin preparation, a fingertip) joins as an anonymous member that only its own unwinding removes.
- **Server side.** A direct jobserver inherits this set, because it calls the core evaluator in its own process; the jobserver endpoint keeps no active-expression map of its own. In daskserver mode the same ownership is kept by giving equivalent submissions a deterministic Dask task identity (which includes `scratch`), so duplicate requests resolve to one Dask evaluation.
- **Active work is process-local or scheduler-local**, and is never recorded in the database.

**Three mechanisms around Expression evaluation are easy to confuse, and they are distinct:**

| Mechanism | Keyed by | What it deduplicates | Section |
|---|---|---|---|
| the **member set** | Expression identity | the **evaluation** of one Expression | this section |
| the **shared fetch** | checksum | the **fetch** of one buffer, for any caller | *Buffer fetches are shared by checksum*, below |
| the **multi-checksum waiter** (deferred) | — | nothing; it would fetch all children of a `folder → mixed` in parallel | `contracts/deep-celltypes.md`, *`folder → mixed`* |

### Buffer fetches are shared by checksum

Below the Expression layer, and independent of it, **concurrent fetches of one checksum share one in-flight fetch.** This is the shared fetch. It is not a member set, and it has nothing to do with Expression identity:

- **Keyed by the checksum.** Every asynchronous `Checksum.resolution()` that misses the local cache takes part, not only Expressions: an Expression's shared evaluation, a transformation, a fingertip, the mount service. A free Expression fetches nothing and never takes part.
- **Participants are anonymous.** A participant is an awaiting call, counted, not named. It leaves only by unwinding (result, error or task cancellation). There is no member id and no softcancel verb.
- **The fetch is aborted as soon as its last participant leaves.** There is no linger at this layer. An Expression's linger still protects its input fetch, because the lingering evaluation stays a participant until the linger expires (*The linger*).
- **Failure is not sticky.** The entry is dropped when the fetch ends, and the next request fetches again.
- **It holds no reference claim** (`contracts/internal/checksum-reference-lifecycle.md`).
- **One Expression waits on at most one shared fetch at a time.** Every Expression except `folder → mixed` needs at most one buffer (*Cost class*). `folder → mixed` needs the index plus every child, and today it fetches them one after another, so it too waits on one fetch at a time. A **multi-checksum waiter**, which would fetch all children in parallel and leave all their fetches when the evaluation is cancelled, is deferred (`contracts/deep-celltypes.md`, *`folder → mixed`*).

## Cancellation

Expression cancellation acts on the member set keyed by Expression identity (*Deduplication*). Equal Expressions share one evaluation, and each caller is a member of it. This is the membership model of `contracts/cancellation.md`, applied at the Expression layer, with three differences that this page owns: a **linger**, **no hard cancel**, and — unresolved, see below — **a signal to the leaving member itself**.

**Open inconsistency with `contracts/cancellation.md`, not yet reconciled.** That page's softcancel definition says "pure deregistration: no signal reaches the member being removed" (its introduction scopes the page to transformations, but the same introduction and its section *The Expression layer is the same pattern* call the Expression layer "the same pattern"). The code disagrees for Expressions: `softcancel_expression` explicitly cancels the leaving member's own pending call (`waiter.get_loop().call_soon_threadsafe(waiter.cancel)`) — see the `asyncio.CancelledError` bullet below. That is a real signal to the departing member, not to a peer, but it is still a signal the transformation-layer rule says shouldn't exist. Whether this is a deliberate, documented Expression-layer exception (like the linger and no-hard-cancel) or a gap in either page is not yet ruled. Do not resolve this by editing around it; it is pinned as current behaviour by `seamless-core/tests/test_contract_expressions.py::test_softcancel_leaves_the_member_set_and_the_peer_keeps_the_evaluation`.

**`softcancel()` means that this Expression instance leaves its evaluation's member set.**

- It returns `True` only when the instance was a registered member and has now left.
- If another member remains, the shared evaluation continues for it.
- The instance's own pending evaluation call, if any, ends with `asyncio.CancelledError`: it asked to leave.
- When the last member leaves, the evaluation enters the linger (*The linger*).

**Cancelling a caller's `asyncio` task unwinds that caller's wait.** The evaluator's cleanup path softcancels its membership, so cancelling one caller does not cancel work while another member remains.

**There is no hard-cancel operation on an Expression.** A hard cancel exists to kill a run that is *wrong*, because of a wrong dunder envelope or wrong hardware (`contracts/cancellation.md`). An Expression has no execution envelope that could be wrong, so a hard kill would have nothing to fix (*API*).

### The linger

**When the last member leaves, the evaluation lingers under the same Expression identity for a short, fixed interval** (currently 3 seconds):

- A requester for the same identity that arrives during the linger **rejoins** the existing evaluation, and the pending expiry is cleared.
- If the result completes during the linger, it is recorded and stays usable.
- If the linger expires with no member, the shared evaluation task is cancelled. Anything that task was awaiting unwinds like any cancelled caller: a shared fetch loses one participant and is aborted if that was the last (*Buffer fetches are shared by checksum*); at a transformation site it is a softcancel of its membership there (`contracts/cancellation.md`). Failures are not cached, so a later request starts fresh work.

The linger exists because an Expression's cost is unbounded (a fingertip chain may contain Transformations), while the chance that **nobody else wants the result** is low. Sibling projections, a Transformation over the same checksum and a revert all tend to want the same result soon after it was abandoned.

**The shared evaluation holds one lifecycle claim on its input** until its task finishes, including while it lingers. The claim is **neutral**: it protects the input from eviction and does not publish it or change its scratch status (`contracts/internal/checksum-reference-lifecycle.md`). Completion or expiry releases it, so a `seamless.close()` during that period can observe the outstanding claim.

**Two knobs, different events.** The linger is **independent** of the node-state **self-edit revert hold** (`contracts/node-state-lifecycle.md`, *(b) Self-edit revert hold*). They are separate mechanisms with separate triggers, and neither is defined in terms of the other:

| | The linger | The self-edit revert hold |
|---|---|---|
| Layer | the Expression member set | the workflow Context scheduler |
| Keyed by | Expression identity | a node's superseded run |
| Triggered when | the last member leaves a shared Expression evaluation | a `computing` node's own code or load-bearing metadata is edited |
| Bets on | a second requester arriving for the same Expression | a person reverting the edit |
| Window | currently 3 s (an internal constant) | 30 s (ruled, pending measurement; `contracts/node-state-lifecycle.md` lists the code's 15 s) |

The two windows may be measured and moved independently, and changing one says nothing about the other. The earlier recommendation to reuse the revert-hold figure for the linger (register Appendix A, item 5) is superseded by this ruling.

The linger has one default and no per-site tuning; nothing measured asks for more. Its value is an internal constant, not a contract value: a test may rely on the linger existing and on rejoin and expiry behaving as above, but must not pin the exact number of seconds.

### API

**The substrate vocabulary is the same everywhere in Seamless: `softcancel` means *deregister*, and `cancel` means *hard kill*.** This rule governs the checksum-addressed substrate verbs. A verb on a *handle* means something narrower, "this handle gives up": terminal for the handle, soft at the substrate. That is why `Transformation.cancel()` keeps its name (`contracts/cancellation.md`). An Expression handle has nothing terminal to mark and no hard operation to offer, so it carries only `softcancel()`.

| Name | Status |
|---|---|
| `Expression.softcancel()` | the only cancellation verb on an Expression |
| `Expression.cancel` | retired. It raises `NotImplementedError`, pointing at `softcancel()` and stating that Expressions have no hard cancel |
| `seamless.checksum.expression.softcancel_expression(key, member_id)` | the module-level entry point. With `member_id=None` it is a no-op returning `False` |
| `seamless.checksum.expression.cancel_expression` | dropped (it was an alias of `softcancel_expression`) |

`softcancel()` returns a `bool` that means **"I was a registered member and have now left"**:

- `False` when the Expression is not a member: its evaluation is already complete, was never started, was answered from a cache, or is **free**, since an Expression that needs no buffer never becomes a member;
- `False` again on a second call (idempotent);
- **it never means that the work stopped.** With other members, or during the linger, the shared evaluation continues, and a result that arrives anyway is recorded and usable.

There is no "cancelled" state to clear. Results are content-addressed and failures are not cached, so a caller that changes its mind simply asks again.

### Implementation details

The local and dispatched evaluators both register in `_active_expressions` and move an emptied entry to `_lingering_expressions`, both in `seamless.checksum.expression` and keyed by the Expression 4-tuple. The linger constant is `_EXPRESSION_LINGER = 3.0`. Each active evaluation takes its neutral input claim (`incref_refholder(scratch=None)`) when it is created (`_ActiveExpression.hold_input`) and releases it when its shared task completes or is cancelled after expiry.

The shared fetch is separate: `seamless_remote.buffer_remote._pending_buffer_fetches`, keyed by `(running event loop, checksum)`, holds the shared fetch task plus a count of its waiters. `get_buffer` awaits the task shielded, and cancels it when the count reaches zero before the task finishes. A synchronous `Checksum.resolve()` fetches on a loop of its own, so it never shares a fetch. `folder → mixed` fetches the index and then each child in turn (`_evaluate_expression_async`); no multi-checksum waiter exists yet. The shared fetch is pinned by the shared-fetch tests in `seamless-remote/tests/test_materialization_waiter_contract.py`.

## Deep checksums

An Expression whose `input_celltype` or `celltype` is `deepcell`, `deepfolder` or `folder` leaves the rule table of `contracts/celltypes-and-conversion.md` entirely. It is governed by the much smaller table of **`contracts/deep-celltypes.md`**, which owns it: the conversion table, the member-celltype rules, the flatness requirement and the reasons. Do not re-derive them here. This page states only how the carve-out meets the Expression machinery:

| Expression concept | How a deep checksum behaves |
|---|---|
| **Path** | **exactly one step, a string item**: an index lookup that selects one member. A longer path is rejected, because a further step would continue into the **child**, which is a different checksum and therefore a different Expression |
| **Result of that one step** | one of exactly two targets. The **member celltype** (`mixed` for `deepcell`, `bytes` for `deepfolder`/`folder`) yields the child's own checksum and makes no new buffer. **`checksum`**, the reference form, makes a new 64-byte buffer holding the child's digest. Which to use, and why the member celltype keys the child's own conversion at the *child's* checksum, is in `contracts/deep-celltypes.md`, *What the one step yields* |
| **Zero-path conversions** | index-level and free (checksum-preserving), with exactly one exception: **`folder → mixed`**, the only conversion in the system that materializes children. Null short-circuits only on legal deep pairs (*The dummy Expression*) |
| **Application order** | this is the shape *project-then-convert* exists for: the step selects a child without materializing the parent, which the opposite order could not express |
| **Cost class** | decided by the identity tuple alone, as everywhere, and *strictly* so here: no deep conversion branches on nullity or on a cached `HashType`, so shape alone decides (*Cost class*) |
| **Fusion** | a deep step is a **barrier and forms no pair**. The run ends at it, and anything after it is a separate Expression over the child checksum (*Fusion*) |
| **Connecting a deep source on a Cell** | the path-and-conversion wiring rule does **not** apply: a deep step necessarily changes the celltype, so a path and a conversion always travel together there (`contracts/cells.md`, *Connecting*) |

**Enforced.** `validate_expression_shape` applies the deep conversion and path rules at construction. Deep buffers are checked for flatness when they are read, and `deserializable_as` raises `ValueError` if it is given a deep celltype (`contracts/hashtype.md`).

## Cell joins

**A cell join is an Expression of its own kind: many inputs, no path, and an identity of its own.** A cell-level join (`contracts/cells.md`, *Cell-level joins*) is evaluated as a **cell join**, a subclass of `Expression`. Its input is not one checksum but a dict of input checksums with string keys: one entry per member, the special key `"<root>"` for the join's literal root when it has one, and the special key `"<numeric>"`, with value null, when all member keys are integer indices. A member key is a string or a non-negative integer, and the two special names cannot be member keys (`contracts/cells.md`, *Projections*). That dict, serialized as Seamless `plain` like a deep index, is the **celljoin JSON**, and its checksum is the **celljoin checksum**. A cell join also has a **celltype**: `mixed`, `plain`, `deepcell` or `deepfolder`. A join into a `folder` cell is a `deepfolder` cell join; the two give byte-identical results. **The identity is the pair `(celljoin checksum, celltype)`**: there is no path and no `input_celltype`, and the celltype is not in the celljoin JSON. The pair stands wherever this page speaks of the 4-tuple, so a cell join is tracked exactly as any other Expression is: the process cache, the member set (*Deduplication*), the linger and soft cancellation (*Cancellation*), result recording, and failures that are never cached (*Expression failures are not cached*). Like any Expression it has no scratch policy of its own.

**What it computes depends on the celltype.** For `mixed` and `plain`, the root and each member are first converted to that celltype by an ordinary Expression, so the inputs are the converted checksums. The root has the same status as a member here. The result is the root value with every member's value inserted under its key, serialized at the celltype. For `deepcell` and `deepfolder`, the deep joins, members keep their checksum: the result is the root index with each member's checksum inserted, and no member is ever resolved. Integer keys need a sequence root. A cell join that carries `"<numeric>"` over a mapping root fails, for `mixed` exactly as for `plain`.

**Recording.** Whenever a celljoin JSON is computed it is checksummed, and it is written to the hashserver when a hashserver and a database are both configured. The database stores a forward row, `(celljoin checksum, celltype)` → result checksum, with that pair as its composite key, and a reverse row from the result back to the pair, as it does for Transformations. The database never receives the celljoin JSON: it holds checksums only, as it does for a Transformation, and the JSON is stored on the hashserver alone.

**Placement follows its own rule, deliberately different from *Placement*.** A deep join is always evaluated in this process. It needs no member buffer, only its root index when it has one, and that buffer must be reachable from here. A `mixed` or `plain` cell join takes the first of these that applies, with *local* as defined in *Placement*:

1. every input is local: evaluate here;
2. every input is on the hashserver: dispatch. The dispatch carries only the identity, and the executing side reads the celljoin JSON from the hashserver, where it always is because remote execution requires a database;
3. every input is local or on the hashserver: evaluate here, fetching the ones that are not local;
4. otherwise, `CacheMissError`.

Explicit `execution="remote"` takes case 2 or nothing: the cell join is dispatched only when every input is on the hashserver, and otherwise raises `CacheMissError`, with no local fallback. It raises `RuntimeError` when no writable hashserver and database are configured.

The asymmetry is intended. An Expression has one input that may be huge, so it goes to the data. A cell join has inputs that may be numerous but are expected to be small, never scratch and never behind a remote read folder, so fetching them is cheap.

**A conversion that produces an input is never dispatched.** The conversion of the root or of a member to the join's celltype is a scratch value request (`scratch=True`, `materialize=True`): its own input is fetched when it is only on the hashserver, and the conversion is evaluated in this process, so a buffer it produces is here. A cell join with such an input is therefore normally evaluated here, under case 1 or 3. A checksum-preserving conversion produces no buffer: its result is its input, which stays where it was, so case 2 remains available.

**A projection that produces an input is a value request.** The last link of a member edge that carries a path (`ctx.j["a"] = ctx.big[3]`) is requested non-scratch, whatever the join Cell's scratch policy, like the input of a non-scratch pin (`contracts/pins.md`, *Scratch at the pin*): the projection is evaluated where the data is, and a dispatched one writes its result to the hashserver.

**In an ordinary evaluation a cache miss on an input is final**: a cell join does not fingertip its inputs. **In a fingertip chain a cell join is an ordinary link**: a wanted result is traced to its cell join through the reverse row, the celljoin JSON is read from this process or from the hashserver, the inputs are fingertipped like those of any other link, and the cell join is re-evaluated in the process that wants the buffer (*Fingertipping is exempt from "where the data is"*). A cell join whose JSON is no longer on the hashserver cannot serve as a candidate, as a Transformation without its definition cannot. A cell join candidate that raises, or that returns a different checksum, is reported as `irreproducible_expression` (*What a failed fingertip reports*). A `CacheMissError` is exempt: it keeps its own category, `materialization` unless a nested fingertip reported a higher one.

## Implementation status and current limitations

This section lists where the code does not yet implement the contract above, where it implements it differently, and what is still open. **The contract wins**: the rules above are the test oracle.

**Current limitations** (not contract violations):

- **Validators are not implemented.** See *Validators are deferred*: supplying `validator` or `validator_language` raises `NotImplementedError` from every evaluation entry point, before any cache lookup.
- **Cell joins are partially implemented.** `seamless-core` provides canonical celljoin formation and parsing, the pure evaluator, the `CellJoin` Expression subclass and local evaluation through the shared process cache and active/lingering member sets. Input reference holding and local materialization use the Expression machinery; cell joins are refused as inputs to Cells and ordinary Expressions. The workflow Context now forms and memoizes cell joins, tracks their jobs and facts, leases required inputs and definitions, and softcancels superseded demands. Root and value-member conversions are local materializing requests; projected value members request non-scratch materialization, and forbidden target keys are rejected or diagnosed as loaded-graph miswiring. Definitions are queued to the hashserver when both write services are configured. Database forward/reverse recording uses the composite identity, rejects conflicting results atomically, and never receives the definition JSON. Evaluation checks the process cache and database before resolving inputs. Remote placement/dispatch and a fingertip route through a join are not implemented yet (*Cell joins*).
- **Irreproducible Expressions normally do not exist.** An Expression runs no user code, so for a given implementation its result is a function of its identity tuple. But the celltype contract under it relies on reference implementations: `orjson` (`plain`, the JSON part of `mixed`), NumPy's `.npy` format (`binary`, the arrays in `mixed`), PyYAML (`yaml`), IPython's input transformer (`ipython`) and CPython's parser (`python`). Drift across versions or hosts can give one identity two results. There is no Expression counterpart of `IrreproducibleTransformation` (`contracts/execution-records.md`): the second result is returned unrecorded and logged, and a fingertip that encounters it reports `irreproducible_expression`.
- **The process-local Expression cache is unbounded** and result-only. It is cleared only at process exit or by an explicit `get_expression_cache().clear()`.
- **A reachability check costs a hashserver query.** Under `scratch=False`, a cached result checksum without a local buffer is confirmed with `buffer_remote.get_buffer_lengths` before it is returned.
- **Cancellation does not reach the executing side of a dispatch.** Linger expiry cancels the client's shared task, but the jobserver's `run-expression` handler joins its own member set as an anonymous member and is not told, so the remote evaluation runs to completion. For Dask, the register (Appendix A, item 5) records that `dispatch_expression` blocks a default-executor thread until the remote side finishes. This is under-cancellation, which `contracts/cancellation.md` (constraint 2) makes benign; it is reported, not re-verified here.

### Status: publication and fingertipping

*Verified against code (2026-09-24), and implemented:*

- **Expression evaluation does not publish its result buffer.** Every terminal branch of `_evaluate_expression_after_validation` calls `_tempref_expression_result`, which temprefs (a tempref never writes) and marks a buffer it produced as scratch; the input tempref leaves the input's scratch status alone. So a fingertip that recovers a scratch or evicted buffer through an Expression leaves it in local memory only, and the Expression and transformation branches of the walk agree. Identity recording (`_record_expression_result`: the process cache and the database) and HashType registration are kept. Pinned by `seamless-core/tests/test_expression_contract.py::test_expression_evaluation_does_not_publish_without_a_refholder`.
- **The Expression dispatch carries `scratch`.** `jobserver_remote.run_expression` sends it, the jobserver `run-expression` handler passes it to `worker.dispatch_expression`, and a non-scratch request writes the end result (the Dask path carries it as `expression.scratch`). `run()` / `expr()` request a value; `compute()` requests a checksum. For a Cell or pin chain, intermediate links are scratch checksum requests and only the last link carries the owner's policy. A non-scratch pin's last link is a value request. A source Transformation keeps its own policy unless its result is itself held by a non-scratch owner through checksum-preserving links. `evaluate_expression_placed` and `Expression._evaluate_internal` carry `materialize` separately from `scratch`; a local materializing caller that joined a dispatch with no reachable buffer evaluates here (`seamless-core/tests/test_contract_expressions.py::test_materializing_local_caller_that_joins_a_dispatch_evaluates_here`).
- **The materialize mode exists.** `evaluate_expression_local`, `evaluate_expression_local_async` and `_evaluate_expression_async` take `materialize`. `Checksum.fingertip()` passes it (the old memo-evicting workaround is gone), `worker.dispatch_expression` passes `materialize=not scratch`, and `evaluate_expression_placed` applies the client-level rule for `scratch=False`.
- **A failed fingertip reports the highest failure category.** Candidate failures contribute to `CacheMissError.fingertip_category`; cancellation and infrastructure errors propagate (*What a failed fingertip reports*).
- **`Cell.fingertip()` and `Pin.fingertip()` exist, and persistence follows the owner.** Both resolve the owner's current result checksum and delegate to `Checksum.fingertip_sync()`. A non-scratch Cell persists the recovered buffer through its own incref, and a scratch Cell does not (`seamless-core/tests/test_contract_reference_lifecycle_late_buffer.py::test_cell_fingertipping_a_held_result_persists_it_only_if_non_scratch`).

## Non-goals

- **An execution environment.** An Expression has no code, environment, meta or scratch policy **of its own**. Anything that needs one is a Transformation. A *dispatch* does carry a `scratch` parameter, because interest could not otherwise cross a process boundary, but its value is the requester's, never the Expression's (*The requester's scratch decision, and what a bare Expression carries*).
- **Hard cancellation.** A deliberate non-feature (*Cancellation*).
- **Failure caching.** Deliberate, not a missing optimization (*Expression failures are not cached*).
- **Value-level canonicalization.** An Expression produces whatever checksum its steps and target celltype produce. It does not re-serialize a result to normalize it (`contracts/identity-and-caching.md`). Canonical `plain` is obtained by asking for the conversions that produce it (`contracts/celltypes-and-conversion.md`, *Canonicalizing a `plain` checksum*).
- **Publication of its own accord.** A local evaluation never writes its result, and a dispatched one writes it only when a non-scratch request asks it to. Whether a result persists is decided by whoever holds or requested it, never by the evaluator (*Evaluating, recording identity and publishing are three different things*).
- **Deep-celltype semantics.** Owned by `contracts/deep-celltypes.md`. This page states only how the carve-out meets Expression identity, cost, fusion and placement.
