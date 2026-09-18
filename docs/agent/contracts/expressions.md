# Expressions (Contract)

An **Expression** is the structural, immutable counterpart of a Transformation: a closed, pure codebook over one input checksum — get-attribute, get-item, slice, celltype conversion — with **no execution environment**. It has no code, no pins, no dunders, no `__env__`; it cannot run user code and cannot fail nondeterministically.

Expressions and Transformations share one lazy, content-addressed DAG: an Expression's input may be a Checksum, a Cell, or another Expression, and an Expression result may feed a transformation pin, exactly as a transformation result may feed an Expression.

A **Cell is a deferred Expression**: the mutable builder for the same recipe, either standalone or bound to a workflow Context node. Everything Cell-side — `celltype` versus read-only `input_celltype`, `.source` / `.checksum`, the write families, null, standalone reads, failures on the handle, projections and cell-level joins — is in `contracts/cells.md`.

Expressions and the conversion engine are entangled: buffer-level conversion results are cached as **empty-path Expressions**, so every conversion that produces a new buffer is recorded under an Expression identity (see `contracts/celltypes-and-conversion.md`).

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

## Identity

**The identity of an Expression is the 4-tuple `(input_checksum, path, input_celltype, celltype)`.**

- `Expression.identity_key` is the in-process form; `__eq__` and `__hash__` use it. Its first element is `("checksum", hex)` for a concrete input, `("expression", …)` for an Expression input, and `("object", id(...))` for an unresolved source, so an Expression over an uncomputed source is identical only to itself.
- `Expression.database_key` is the wire form `(input_checksum.hex(), path, input_celltype, celltype)`. It raises `ValueError` when the input is not yet a concrete checksum.
- `ExpressionKey` canonicalizes the input checksum against the input celltype on construction, so `sha256(b"")` as `bytes` and the canonical null are one identity (see `contracts/celltypes-and-conversion.md`).
- The seamless-database `Expression` row has exactly this 4-tuple as its **composite primary key**, with `result` as the payload. A second write of the same key is accepted only when the stored `result` agrees; otherwise the row is kept and the request answered with a conflict.
- The same 4-tuple is the **reverse index** that fingertipping walks: `rev_expression` (database) plus the process-local expression cache. Given a wanted result checksum, Seamless finds Expressions that produce it, fingertips their inputs and re-evaluates them (see `contracts/scratch-witness-audit.md`).
- Wire/storage limits: the database stores `path` JSON-encoded in a 100-character column and each celltype in a 20-character column; longer values are refused as a malformed expression request.

**Validators are excluded from identity.** `validator` / `validator_language` are fields of the container and columns of the database row, but they are **not** part of the primary key, and `evaluate_expression*` carries an explicit TODO recording that exclusion. Validators are **deferred**: the reject-only contract is settled, and every evaluation entry point raises `NotImplementedError` when a validator is supplied. Nothing currently writes the two columns.

### The dummy Expression

An Expression with an **empty path and `input_celltype == celltype`** is the identity (dummy) expression. It resolves to its input checksum without any work: no buffer is fetched, no conversion runs, and the input checksum is recorded as the result. Checksum-level validation still applies — a known structural incompatibility is rejected without source content — but nothing else happens. (A null input short-circuits earlier still: an empty-path Expression whose canonicalized input is null yields the canonical null result for every celltype pair.)

This is load-bearing for the `.set_checksum` contract. `Cell.set_checksum` and `Pin.set_checksum` are the Checksum variant of the three setters; they set the **input** checksum, not `.checksum`. `.checksum` is therefore normally `None` immediately afterwards, with two exceptions:

1. the underlying Expression is a dummy — `.checksum` returns the argument (as a `Checksum`) immediately, without evaluation;
2. the Cell is unbound — `.checksum` is then a computed property performing a synchronous evaluation of the underlying Expression. This does not change the semantics of `set_checksum`.

The dummy case is a required special case, not an optimization: `.set_checksum` is instantaneous, so `.checksum` must answer immediately, without entering the evaluator.

*Verified:* the standalone `CellBase.checksum` getter implements exactly this fast path, including the empty-`bytes` → null canonicalization.

## Cost class

**An Expression's cost class is a function of its identity tuple `(input_celltype, path shape, celltype)`, and never of the data behind the checksum.** An agent can decide from the definition alone whether an Expression is free, one-buffer, or a fan-out; that is why deep fan-out is restricted (below) and why placement can be decided before any buffer is touched.

Concretely, an Expression needs a buffer if and only if:

- the path is non-empty; or
- the path is empty, the celltypes differ, the input is not null, and `conversion_needs_buffer(checksum, input_celltype, celltype)` is `True` — that is, the conversion is not decidable from the checksum, the rule table and the cached HashType alone.

Before evaluation, `validate_expression[_async]` checks the source celltype, then the path capability, then (for an empty path) `conversion_feasible`, rejecting impossible work at checksum level with `HashTypeValidationError` (see `contracts/hashtype.md`).

## Results and caching

- Successful results are recorded in a process-global dict `get_expression_cache()`, keyed by the 4-tuple, value = result checksum; and, when `seamless_remote` is importable, in the database `expression` table.
- A newly produced result buffer is kept in a weak-valued map, given a buffer-cache tempref, and **classified**: `register_hash_type_for_buffer` runs in the process that produced the buffer.
- `Expression.checksum` is an alias of `Expression.result`: the published result checksum or `None`. Reading it also expresses user result interest (a refholder claim on the result; see the checksum reference lifecycle).
- `Expression.compute(execution="auto")` / `compute_async(execution="auto")` return the result checksum. `Expression.run()` (also `expr()`) computes and then materializes the value: local buffers first, then `Checksum.resolve()`, which asks the hashserver and raises `CacheMissError` when no buffer is found. `run()` does not fingertip.

## Placement: an Expression is evaluated where the data is

Placement **is** contract. A jobserver/daskserver counts as closer to the hashserver than the client, so an input the client does not hold is evaluated there rather than downloaded.

`execution` takes `"auto"`, `"local"` or `"remote"`. `"auto"` is the default on every path that evaluates an Expression: `Expression.compute` / `compute_async` / `run`, transformation dependencies, pin preparation, and workflow Context projections (`Context(expression_execution=...)` overrides it for one Context).

- **`"local"` means *in this process's memory*.** **`"remote"` means *not in this process's memory*, independently of backend availability.** `choose_expression_evaluation_location` answers only that question: local if no buffer is needed, or if the input buffer is already resolvable from process-local caches; remote otherwise.

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
- **A daskserver is a jobserver *mode*, not a competing backend.** Both modes expose the same checksum, error, caching and HashType contracts. In a jobserver, `dispatch_expression` evaluates in-process when no Dask client is configured, and otherwise submits the Expression to a Dask worker, passing only the identity fields; the jobserver does not download the input in order to forward it.

Two derived rules:

- **The result, including the exception type, must not depend on where the Expression ran.** That is what the structured error envelope buys (below).
- **HashType classification is owned by whichever process holds the buffer**: the client for local evaluation, the jobserver for direct evaluation, the Dask worker for daskserver evaluation. A process that receives only a checksum classifies nothing and uploads nothing. Jobserver/daskserver responses are checksum-only; HashTypes travel through the database.

**Open placement questions** (documented as open; do not assume an answer):

1. Whether "where the data is" includes a locally mounted read buffer directory. Today locality is decided by process memory alone, so a buffer available on local disk still counts as remote and is dispatched.
2. Where a fingertip chain triggered by an Expression runs. It is the case whose cost is unbounded, because the chain may contain Transformations. Today the reverse-index walk re-evaluates the chain locally in the requesting process, but this is code behaviour, not a ratified contract.

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

A caller identifies itself to the set by a member id: a standalone `Expression` uses `id(self)`, and the workflow Context uses its demand key, which it deregisters when its own job is cancelled (node supersession, `Context.close()`). Two `Expression` objects with the same identity are therefore two members of one evaluation.

## Cancellation

**The cancellation mechanism does not belong to Expressions.** The only cancellable work is remote materialization of a buffer, which Expressions share with transformation input resolution, `.buffer` reads and mounts. Expression evaluation proper — deserialize, walk the path, convert, serialize, hash — is cheap and CPU-bound.

The settled model:

- **A waiting set per in-flight materialization, keyed by checksum**, held at the materialization site in the buffer layer.
- **Latch-on**: a second requester for the same checksum joins the in-flight fetch instead of starting a second one.
- **Softcancel = deregister.** The fetch is aborted only when the set is empty, and then only after a **linger**; a requester arriving during the linger re-registers and the fetch continues.
- **No hard cancel at all** — a documented non-feature. The only leaf a hard cancel could kill is a shared fetch, which would merely make the other waiters fail and re-fetch. A single waiter pressing Ctrl-C is already covered: with one member, softcancel aborts the fetch.
- **No cancel point once the buffer is present.** Evaluation then runs to completion and its result is recorded.
- **Failure is not sticky** (above).
- **Soft deregistration cascades down fingertip chains**; a step shared with a live chain survives, because it still has a member of its own.
- Vocabulary: **waiting set**, not refcount. It tracks who still wants a fetch that has not finished, which is a different thing with a different lifetime from the checksum reference lifecycle. The two meet in one place: the site holds a lifecycle claim for the duration of the linger.

### The linger

The linger is an internal constant — "a few seconds, not contractual" — at most a test hook, and is **not user-visible**. Its observable consequences are contract:

- after the last waiter leaves, a fetch may run on for a few seconds;
- it may still complete, and its result is then recorded and usable;
- the site holds a lifecycle claim meanwhile, so a `seamless.close()` landing in that window can block briefly or report an outstanding claim.

### API

**The rule is about the checksum-addressed substrate verbs**: `softcancel` means **deregister** everywhere in Seamless, and `cancel` means **hard kill** everywhere. A verb on a *handle* means something narrower — "this handle gives up": terminal for the handle, soft at the substrate, which is why `Transformation.cancel()` keeps its name (`contracts/cancellation.md`). An Expression handle has nothing terminal to mark and no hard operation to offer, so it carries only `softcancel()`.

| Name | Status |
|---|---|
| `Expression.softcancel()` | the only cancellation verb on an Expression |
| `Expression.cancel` | retired; raises, pointing at `softcancel()` and stating that Expressions have no hard cancel |
| `seamless.checksum.expression.softcancel_expression` | the module-level entry point |
| `seamless.checksum.expression.cancel_expression` | dropped (it was an alias of `softcancel_expression`) |

`softcancel()` returns `bool`, meaning **"I was a registered waiter and have now left"**:

- `False` when the Expression was not waiting — already complete, never started, or past the buffer into the CPU phase;
- `False` again on a second call (idempotent);
- **it never means the work stopped.** With other waiters, or during the linger, the fetch continues, and a result that arrives anyway is recorded and usable.

There is no "cancelled" state to clear. Results are content-addressed and failures are not cached, so a caller that changes its mind simply asks again.

### Implementation status

The settled model above is **ahead of the code**. What exists today:

- The waiting set lives at the **Expression** layer (`_active_expressions` in `seamless.checksum.expression`), not at the materialization site in the buffer layer, and buffer resolution itself is **not** deduplicated by checksum.
- There is **no linger**: when the last member deregisters, the in-flight remote request is aborted at once and the awaiting task receives `CancelledError`.
- `Expression.cancel()` exists and is soft; `Expression.softcancel()` does not exist yet, `cancel` is not retired, and `cancel_expression` is still an alias of `softcancel_expression`.
- `Expression.cancel()` is a **silent no-op for local in-flight evaluations**: `evaluate_expression_async` registers members under a 7-tuple key `("local", hex, path, input_celltype, celltype, str(validator), validator_language)`, while `cancel_expression` looks up the 4-tuple identity key. The call returns `False` while the evaluation keeps running. Only the remote path (`evaluate_expression_remote`, which registers under the 4-tuple with `member_id=id(self)`) can be deregistered.
- **Dask-dispatched Expressions cannot be interrupted mid-flight**: `dispatch_expression` awaits `asyncio.to_thread(thin.result)`, so cancelling the awaiting task neither cancels the Dask future nor frees the thread, which stays blocked until the remote side finishes.
- No soft-deregistration cascade down fingertip chains exists.
- Repo tests cover the remote path only: one member leaving keeps a shared request alive and both callers get the result; the last member leaving aborts the request; `cancel()` on an idle Expression returns `False`. There is no test for local in-flight cancellation.

## Deep checksums

An Expression over a deep checksum (`deepcell`, `deepfolder`, `folder`) is **restricted**, by the cost-class rule above: exactly **one string-item step** is allowed, yielding either the child's checksum or the child's value at its member celltype, and longer paths are rejected (a further step continues into the child, which is a different checksum and therefore a different Expression). The zero-path conversions are index-level and free, with **`folder → mixed` the only conversion that materializes children**. The conversion table, the member-celltype rules, the flatness requirement and the reasons are in `contracts/deep-celltypes.md`; do not re-derive them here. **Status: settled contract, not yet enforced** — the Expression path contains no deep-celltype rules at all, and a deep celltype on either side of an Expression currently raises `HashTypeValidationError` before evaluation.

## Current limitations

- **Validators are not implemented.** Supplying `validator` or `validator_language` raises `NotImplementedError` from every evaluation entry point. The reject-only semantics are settled; the identity exclusion is already decided and marked in the code.
- **No forensic "irreproducible expression" analogue exists.** There is no Expression counterpart of `IrreproducibleTransformation` (see `contracts/execution-records.md`); an Expression that yields a different result for the same identity tuple is not recorded anywhere.
- **Cancellation** — see the implementation-status list above.
- **Deep-checksum restrictions are unenforced** — see above.
- **The process-local Expression cache is unbounded** and result-only; it is cleared only by process exit or an explicit `get_expression_cache().clear()`.

## Non-goals

- **Execution environment.** An Expression has no code, environment, meta or scratch policy. Anything that needs one is a Transformation.
- **Hard cancellation.** See above; it is a deliberate non-feature.
- **Failure caching.** See above; it is deliberate, not a missing optimization.
- **Value-level canonicalization.** An Expression produces whatever checksum its steps and target celltype produce; it does not re-serialize a result to normalize it (see `contracts/identity-and-caching.md`).
