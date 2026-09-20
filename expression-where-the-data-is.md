# Expressions are evaluated where the data is

## Handoff-ready implementation plan

Line numbers below are one-based and refer to the current working tree. Existing uncommitted test changes must be preserved.

## 1. Expose jobserver availability

- Modify [`jobserver_remote.py`](/home/agent/seamless1/seamless-remote/seamless_remote/jobserver_remote.py:18), near `activate` at lines 50–102.
- Add a side-effect-free `has_jobserver() -> bool` returning whether `_jobserver_clients` contains a configured client.
- Do not initialize, launch, or health-check clients from this query.
- Keep `run_expression` at lines 143–165 unchanged: explicit remote execution with no client should continue to raise.

Add coverage to [`test_client_recovery.py`](/home/agent/seamless1/seamless-remote/tests/test_client_recovery.py:125), inside `JobserverRemoteRecoveryTests` at lines 125–192:

- Empty client list returns `False`.
- A fake configured client returns `True`.
- Preserve the existing setup/teardown restoration of `_jobserver_clients`.

## 2. Implement the no-jobserver fallback centrally

Modify `evaluate_expression_remote` in [`expression.py`](/home/agent/seamless1/seamless-core/seamless/checksum/expression.py:174), lines 174–247.

After cache and database lookup:

1. Let `choose_expression_evaluation_location` select local versus remote based solely on buffer locality.
2. If `execution="auto"` selected remote, query `jobserver_remote.has_jobserver()`.
3. If `seamless_remote` is unavailable or no jobserver is configured, switch to the local asynchronous branch.
4. That branch already calls `evaluate_expression_async` at lines 120–171, which uses `Checksum.resolution()`—the asynchronous equivalent of normal `Checksum.resolve()`—and therefore may materialize the input from the hashserver.
5. Allow `CacheMissError` to propagate if normal resolution cannot find the buffer.

Important boundaries:

- Do not change explicit `execution="local"` semantics.
- Do not silently fall back after a configured jobserver fails. Connection, restart, and evaluation errors must propagate.
- Do not put jobserver availability into `choose_expression_evaluation_location` at lines 55–77. That function should continue to answer only “where is the data?”
- Update its docstring to clarify that `"remote"` means “not in this process’s memory,” independently of backend availability.

## 3. Make standalone Expression evaluation default to `"auto"`

Modify [`expression_class.py`](/home/agent/seamless1/seamless-core/seamless/expression_class.py:135):

- `Expression._evaluate_internal`, lines 135–174: change the default to `"auto"`.
- `Expression._evaluate_internal_async`, lines 176–216: change the default to `"auto"`.
- `Expression.compute_async`, lines 357–359: change the public default to `"auto"`.
- `Expression.compute`, lines 361–363: change the public default to `"auto"`.
- `Expression.run`, lines 365–371, then inherits `"auto"` through `compute()`.

Also adjust the synchronous bridge in `_evaluate_internal`:

- Preflight an `"auto"` request with `choose_expression_evaluation_location`.
- If the expression needs no buffer or its buffer is already in memory, evaluate synchronously. This preserves local evaluation inside a running event loop.
- Otherwise, use the existing asynchronous evaluator bridge, which performs jobserver dispatch or the no-jobserver resolution fallback.
- Retain the existing error for synchronous remote evaluation attempted from a running event loop.

Explicit `"local"` and `"remote"` arguments remain supported.

Serena found no `Cell.compute()` method in the current source. Standalone cells construct Expressions; bound cells use the Context path. The decision document’s reference to `Cell.compute()` should therefore be corrected rather than implemented.

## 4. Make transformation Expression dependencies explicit

Although changing the internal defaults covers omitted arguments, encode the policy explicitly at transformation boundaries.

Modify [`transformation_class.py`](/home/agent/seamless1/seamless-transformer/seamless_transformer/transformation_class.py:122):

- `_dependency_result_checksum`, lines 122–133: call `_evaluate_internal(execution="auto")`.
- `_dependency_computation`, lines 136–146: call `_evaluate_internal_async(execution="auto")`.

Modify [`pretransformation.py`](/home/agent/seamless1/seamless-transformer/seamless_transformer/pretransformation.py:163):

- `PreTransformation._prepare_pin_value`, lines 163–193: use `"auto"`.
- `PreparedPreTransformation._prepare_pin_value`, lines 291–317: use `"auto"`.

This covers synchronous preparation, asynchronous dependencies, and prepared-transformation reconstruction.

## 5. Preserve already-correct paths

No product-code changes are needed in these paths:

- Bound projections already default to auto in [`Context.__init__`](/home/agent/seamless1/seamless-workflow/seamless_workflow/context.py:45), lines 45–83, and pass that setting through [`Context._demand`](/home/agent/seamless1/seamless-workflow/seamless_workflow/context.py:1199), lines 1199–1249.
- Dask’s `_expression_task` already passes `execution="auto"` in [`client.py`](/home/agent/seamless1/seamless-dask/seamless_dask/client.py:829), lines 829–863.

These paths need regression tests, not routing changes.

## 6. Complete the test matrix

Build on the existing uncommitted tests.

- [`seamless-core/tests/test_expression_remote_evaluation.py`](/home/agent/seamless1/seamless-core/tests/test_expression_remote_evaluation.py:26), lines 26–262:
  - Update `_install_fake_remotes` to provide `has_jobserver()`.
  - Retain the explicit in-memory buffer reference in the local-branch test.
  - Retain tests for hashserver-only dispatch, no-jobserver fallback, and standalone default-auto behavior.
  - Add assertions that:
    - missing input with no jobserver raises `CacheMissError`;
    - explicit `"remote"` does not fall back;
    - a memory-local standalone `compute()` still works inside a running event loop;
    - `compute_async()` also defaults to auto.

- [`seamless-transformer/tests/test_expression_inputs.py`](/home/agent/seamless1/seamless-transformer/tests/test_expression_inputs.py:25), lines 25–54:
  - Retain `test_transformation_expression_dependency_uses_auto`.
  - Add asynchronous dependency coverage if the asynchronous transformation path is not exercised by that test.

- [`seamless-transformer/tests/test_expression_remote_schema.py`](/home/agent/seamless1/seamless-transformer/tests/test_expression_remote_schema.py:55), lines 55–110:
  - Retain the real hashserver-only input test and verify exactly one jobserver dispatch.

- Add `seamless-workflow/tests/test_expression_execution.py`:
  - Configure a real jobserver/hashserver using the existing subprocess pattern.
  - Upload a source buffer to the hashserver, then evict it from all process-local caches.
  - Bind its checksum to a Context cell and create a projection using the default Context configuration.
  - Run `ctx.compute()`.
  - Assert the projected value and exactly one jobserver dispatch.

- [`seamless-dask/tests/test_expression_inputs.py`](/home/agent/seamless1/seamless-dask/tests/test_expression_inputs.py:28), lines 28–62:
  - Retain `test_expression_task_requests_auto_location`; it already passes.

## 7. Update the decision record

Modify [`celltype-rename-review-decisions.md`](/home/agent/seamless1/seamless/celltype-rename-review-decisions.md:1097), lines 1097–1146:

- Mark §10.3 as decided.
- Record the three-branch `"auto"` algorithm verbatim.
- State that “local” means available in process memory.
- State that all Expression evaluation paths use auto.
- Correct the nonexistent `Cell.compute()` reference.
- After implementation, update §10.2’s current-code findings and §10.7’s test inventory.

## Verification commands

Run all tests in the required `seamless1` conda environment:

```bash
cd /home/agent/seamless1/seamless-remote
conda run -n seamless1 pytest -q tests/test_client_recovery.py
```

```bash
cd /home/agent/seamless1/seamless-core
conda run -n seamless1 pytest -q tests/test_expression_remote_evaluation.py tests/test_expression_errors.py
```

```bash
cd /home/agent/seamless1/seamless-transformer
conda run -n seamless1 pytest -q tests/test_expression_inputs.py tests/test_expression_remote_schema.py
```

```bash
cd /home/agent/seamless1/seamless-workflow
conda run -n seamless1 pytest -q tests/test_expression_execution.py tests/test_execution_error_types.py
```

```bash
cd /home/agent/seamless1/seamless-dask
conda run -n seamless1 pytest -q tests/test_expression_inputs.py
```

## Current baseline

- The no-jobserver and standalone-default tests fail in `seamless-core`.
- The transformation-auto test fails.
- The Dask auto test passes.

## Appendix: implementation plan for §§10.4–10.6

This appendix records the subsequently accepted decisions. Where an appendix clause conflicts with the earlier plan, the appendix is authoritative; the earlier text is retained as historical handoff context.

**Standalone-plan guarantee:** this file contains the complete implementation contract. An implementer does not need to read `celltype-rename-review-decisions.md` or any other decision document. References such as “§10.4,” “§10.5,” “§10.6,” and “§8.3” are traceability labels only; they do not import unstated requirements. If an external document differs from this plan, the behavior written here controls. Source-code links are navigation aids, while the required behavior is stated directly in the surrounding text.

### Accepted cross-cutting decisions

- A standalone Cell getter may refuse remote work from a running event loop. That refusal is not an evaluation failure: it returns `None`, leaves the Cell `waiting`, records no exception, and dispatches no job. Memory-local getter evaluation remains available.
- A synchronous HashType lookup made from a running event loop likewise skips the database lookup and returns `None`; it must neither block nor raise.
- Dask must preserve typed `CacheMissError` failures instead of reducing them to traceback strings.
- Jobserver Expression and transformation endpoints use one shared structured error envelope. A completed job, including a job that failed, is an HTTP 200 response; 4xx/5xx are reserved for cases where no job answered.
- A reconstructed `CacheMissError` must preserve its checksum argument when the original exception has one. In that case, `exc.args[0]` on the receiving side is the corresponding `Checksum`, not merely its display string.
- The local HashType cache is write-through. Whichever process classifies a buffer creates or tightens the local word and queues its database upload; a process that receives only a checksum uploads nothing.
- In this plan, “jobserver” includes a daskserver-backed jobserver. A direct jobserver evaluates an Expression in its own execution environment; a daskserver delegates the Expression to a Dask worker. Both modes expose the same checksum, error, caching, and HashType contracts.
- The earlier pre-appendix statement that the source has no `Cell.compute()` is obsolete in the current working tree. `CellBase.compute`, `run`, and `compute_async` now exist in `cell_class.py`; this appendix covers the standalone `Cell.checksum` getter that calls them.

## 8. §10.4 — Complete standalone remote reads

### 8.1 Route standalone Cell reads through the Expression contract

Modify the standalone [`CellBase.checksum`](/home/agent/seamless1/seamless-core/seamless/cell_class.py:104) getter, currently lines 104–130, together with `CellBase.compute`, `run`, and `compute_async` around lines 254–270.

- A normal synchronous getter waits for the same cache/database/jobserver result as `Expression.compute()` and returns the result checksum.
- The getter records genuine evaluation exceptions in `_standalone_exception`. On such a failure, the Cell becomes `failed`, exposes that typed object through `.exception`, and has no result checksum. A decoded jobserver `CacheMissError` is stored with no worker traceback and preserves its checksum argument. After the missing buffer becomes available, `clear_exception()` clears the failure and permits a fresh read to succeed.
- A refusal to wait because the caller already has a running event loop is handled separately from evaluation exceptions: return `None`, keep `_standalone_exception` clear, leave the Cell in `waiting`, and do not dispatch.
- A memory-local getter inside that same loop still completes normally.
- Preserve the asynchronous `compute_async` path for callers that want to await remote work explicitly.

### 8.2 Preserve the standalone-read resolution order

Keep the ordering in [`evaluate_expression_remote`](/home/agent/seamless1/seamless-core/seamless/checksum/expression.py:174):

1. process-local Expression cache;
2. database Expression result;
3. local evaluation when no buffer is required or the input is in memory;
4. jobserver/daskserver dispatch when the input is not in memory and a server is configured;
5. normal local materialization when no server is configured; and
6. resolution of the returned result checksum through the hashserver when a value is requested.

Database hits and remote results must be published through the same result-holding path as local evaluation. The standalone Cell getter must observe this order too, and `Expression.run()` must resolve a jobserver/daskserver result buffer from the hashserver.

### 8.3 Coalesce duplicate requests in the evaluator layer

Do not add request state to `JobServer`. Extend the active-expression mechanism in [`expression.py`](/home/agent/seamless1/seamless-core/seamless/checksum/expression.py:261) so concurrent `evaluate_expression_async` calls for one complete Expression identity share one evaluation task, just as client-side remote requests already share `_active_expressions`.

- A direct jobserver inherits this behavior because `_run_expression` calls the core evaluator in one process.
- The jobserver endpoint may expose an evaluation counter for integration assertions, but owns no active-expression map.
- In daskserver mode, preserve the same evaluator-layer ownership by giving equivalent Expression submissions a deterministic Dask task identity/future rather than keeping an HTTP-layer map. Duplicate requests must resolve to one Dask evaluation.
- Active work remains process-local/scheduler-local and is not recorded in the database.
- Remove active entries after success, failure, or cancellation.

Add same-process coverage for concurrent `evaluate_expression_async` calls and cross-client integration coverage for one direct evaluation or one Dask task, with all callers receiving the same checksum or structured error.

### 8.4 Delegate daskserver Expressions to Dask workers

`JobServer._run_expression` currently evaluates inline. Split its execution step behind a backend-neutral Expression dispatcher:

- direct jobserver mode calls `evaluate_expression_async` in the jobserver execution environment;
- daskserver mode submits the Expression to a Dask worker, passing only the input checksum, path, input celltype, target celltype, and validator fields;
- the worker obtains the input through the hashserver, evaluates it, publishes the result buffer and HashType, and returns the result checksum or structured error envelope;
- the jobserver process must not download the Expression input merely to forward a daskserver request.

Extend the worker dispatch boundary near [`dispatch_to_workers`](/home/agent/seamless1/seamless-transformer/seamless_transformer/worker.py:2359), lines 2359–2378, with a corresponding Expression dispatch operation. Route the Dask implementation through [`SeamlessDaskClient.get_fat_checksum_future`](/home/agent/seamless1/seamless-dask/seamless_dask/client.py:1274), lines 1274–1295, and [`SeamlessDaskClient.get_expression_future`](/home/agent/seamless1/seamless-dask/seamless_dask/client.py:1320), lines 1320–1347. Reuse `_expression_task`; do not implement a second Dask Expression evaluator.

Add a daskserver integration test with an input present only on the hashserver. Assert that execution occurs on a Dask worker, the jobserver returns only the checksum-level response, and the client resolves the result through the hashserver.

## 9. §10.5 — Preserve errors across jobserver and Dask boundaries

### 9.1 Define one structured error envelope

Add one dependency-neutral exception-mapping/codec module in `seamless-core`, shared by `seamless-jobserver`, `seamless-remote`, `seamless-dask`, and workflow `execution_error`. It owns the keep-list and the wire names:

- `cache_miss`;
- `hash_type_validation`;
- `expression_evaluation`;
- `conversion`;
- `execution`; and
- `canceled`.

The envelope contains at least:

```json
{
  "error": {
    "kind": "cache_miss",
    "message": "...",
    "checksum": "64-hex-digest"
  }
}
```

For substrate errors on the keep-list, `message` is `str(exc)` without a traceback. For other worker failures, `message` is the existing frame-filtered `_format_exception` diagnostic. Use the same mapping from [`execution_error`](/home/agent/seamless1/seamless-workflow/seamless_workflow/errors.py:74), lines 74–97, rather than maintaining a second class list.

Make `WorkflowExecutionError` available from the dependency-neutral layer and re-export/alias it from `seamless_workflow.errors` so all packages reconstruct the same class without adding a core-to-workflow dependency. Extend it with the remote `kind` for forward-compatible unknown envelopes while retaining the existing message and `failure_id` behavior. Change `execution_error` to delegate kind selection and substrate preservation to the shared codec.

For `CacheMissError`:

- inspect the first argument without replacing it with `str(exc)`;
- when it is a `Checksum` or a valid checksum representation, encode its canonical hex digest in `checksum`;
- reconstruct it as `CacheMissError(Checksum(checksum_hex))`, ensuring the checksum survives in `args[0]`;
- support an argument-less `CacheMissError` by omitting `checksum`; and
- retain the exact checksum field through every jobserver and Dask hop.

The `checksum` field is also present for any other recognized kind whose exception names a checksum; it is omitted when the source exception has no checksum argument.

When decoding a well-formed envelope with a future/unknown `kind`, construct `WorkflowExecutionError` carrying both the message and the unrecognized kind. It is a deterministic execution failure, not a `ClientConnectionError`. Malformed envelopes remain protocol failures.

Add focused round-trip tests for `CacheMissError(Checksum(...))`, argument-less `CacheMissError`, malformed envelopes, and an unknown exception kind.

### 9.2 Use the envelope in both jobserver endpoints

Modify [`JobServer._run_expression`](/home/agent/seamless1/seamless-jobserver/jobserver.py:729), lines 729–766, to return HTTP 200 with either a result payload or the structured error envelope. Remove the catch-and-discard input-resolution block: let normal evaluation raise the original `CacheMissError` once.

Modify [`JobServer._run_transformation`](/home/agent/seamless1/seamless-jobserver/jobserver.py:486), lines 486–560, and [`JobServer._run_transformation_task`](/home/agent/seamless1/seamless-jobserver/jobserver.py:562), lines 562–727, so execution failures remain structured until the HTTP response is built. Do not convert an exception to a string inside `_run_transformation_task` and then attempt to infer its type later.

Apply the same rule to transformations: once a job has answered, success, cancellation, and evaluation failure are HTTP 200 job payloads. Invalid JSON, invalid payloads, record-mode mismatches, server crashes, and other cases where no job answered remain 4xx/5xx protocol responses.

### 9.3 Reconstruct typed client errors without changing retry behavior

Modify [`JobserverClient.run_expression`](/home/agent/seamless1/seamless-remote/seamless_remote/jobserver_client.py:93), lines 93–126, and [`JobserverClient.run_transformation`](/home/agent/seamless1/seamless-remote/seamless_remote/jobserver_client.py:33), lines 33–91:

- treat every 4xx/5xx as `ClientConnectionError`, because those statuses mean no job answered;
- parse result/error payloads only from HTTP 200 responses;
- raise the decoded `CacheMissError` directly, preserving its checksum argument;
- reconstruct all recognized keep-list kinds; map an unknown well-formed kind to `WorkflowExecutionError`, preserving its kind and message;
- reserve `ClientConnectionError` for transport failures, non-200 protocol responses, and malformed 200 bodies; and
- keep `jobserver_remote.run_expression` retrying only `ClientRestartRequiredError` in [`jobserver_remote.py`](/home/agent/seamless1/seamless-remote/seamless_remote/jobserver_remote.py:148), lines 148–170. A decoded cache miss must never restart or retry a client.

The client-level `_retry_operation` continues to handle retryable transport/protocol failures represented by `ClientConnectionError`; the outer `jobserver_remote` client-rotation loop remains limited to `ClientRestartRequiredError`. Decoded HTTP-200 job failures bypass both retry paths.

### 9.4 Carry the same envelope through Dask

Modify [`_expression_task`](/home/agent/seamless1/seamless-dask/seamless_dask/client.py:829), lines 829–863, to return the shared serializable error envelope instead of `traceback.format_exc()`.

Update the fat/thin tuple error field and its consumers in:

- `_fat_checksum_task`, lines 799–810;
- `_run_base`, lines 866–1178;
- `_run_fat`, lines 1181–1192;
- `_run_thin`, lines 1212–1217; and
- [`TransformationDaskMixin._compute_with_dask`](/home/agent/seamless1/seamless-dask/seamless_dask/transformation_mixin.py:251) and `_compute_with_dask_async`, current lines 251–534.

Decode the envelope only at the API boundary that must raise or record the failure. A standalone Expression delegated by a daskserver re-raises the typed `CacheMissError`. A transformation preserves the structured cause until `execution_error` applies the shared mapping; substrate failures are then recorded/exposed as their typed exception objects, including the checksum argument, while presentation code may render `str(exception)`.

Test direct `_expression_task`, Expression-as-transformation-input, and standalone daskserver Expression failures. In each case assert the missing checksum survives exactly; do not merely assert that it appears in formatted text.

## 10. §10.6 — Make database HashTypes monotonic and complete

### 10.1 Share the tightening rule between memory and database

Use the existing `_hash_type_implies` rule around [`set_hash_type`](/home/agent/seamless1/seamless-core/seamless/checksum/hash_type.py:281), lines 281–324, to classify an incoming word as:

- equal;
- looser than the stored word, so the stored word remains;
- tighter than the stored word, so the incoming word replaces it; or
- contradictory, which raises a conflict.

Import that core implication rule in the database rather than copying it, so the in-memory cache and database cannot diverge.

Modify [`HashType.create`](/home/agent/seamless1/seamless-database/database_models.py:71), lines 71–79, and the `hash_type` branch of [`DatabaseServer._put`](/home/agent/seamless1/seamless-database/database.py:770), currently lines 786–804:

- perform read/compare/update atomically;
- retain an equal or tighter stored word;
- replace the row only when the incoming word is tighter; and
- return `"OK"` for equal, looser, and tighter writes; and
- log and return HTTP 409 only for a contradictory word, without changing the stored row.

Update [`DatabaseClient.set_hash_type`](/home/agent/seamless1/seamless-remote/seamless_remote/database_client.py:468), lines 468–491: equal, looser, and tighter writes all report success, while the now-unambiguous 409 contradiction raises `ValueError`, matching local `set_hash_type`. Do not return `False` for a contradiction.

### 10.2 Make the local HashType cache write-through

Move upload triggering to the point where [`set_hash_type`](/home/agent/seamless1/seamless-core/seamless/checksum/hash_type.py:281) actually creates or tightens the cached word. `register_hash_type_for_buffer` and its asynchronous counterpart classify buffers and call that single write-through operation; they are not separate ownership rules.

- A synchronous cache change queues `(checksum, word)` on the existing [`buffer_writer`](/home/agent/seamless1/seamless-core/seamless/caching/buffer_writer.py:57) worker and returns immediately. Extend the writer with a HashType entry/operation rather than starting another thread.
- The caller never waits for the database write. Tests and shutdown use `buffer_writer.flush()` when durability must be observed.
- An equal or looser incoming word returns before queueing anything.
- A contradiction raises synchronously in the caller before anything is queued.
- Writes may arrive out of order. The database tightening transaction guarantees convergence on the tightest compatible word.
- Remove any direct asynchronous upload that would duplicate the write-through queue operation.

### 10.3 Make synchronous validation consult the database

Modify [`ensure_hash_type`](/home/agent/seamless1/seamless-core/seamless/checksum/hash_type_validation.py:50), lines 50–63:

1. consult the local HashType cache;
2. if absent and no event loop is running, query the database through `get_hash_type_remote` using the normal synchronous adapter;
3. if still absent and a buffer is available, derive and register the HashType; and
4. if called from a running event loop with no local word, skip the database lookup and return `None` as “unknown,” without blocking or raising.

Keep `ensure_hash_type_async`, lines 66–79, as the native asynchronous form. Both paths must enforce the same tightening/conflict rules.

### 10.4 Classify result buffers in the process that holds them

Modify the result-producing branches in [`_evaluate_expression_after_validation`](/home/agent/seamless1/seamless-core/seamless/checksum/expression.py:372), current lines 372–427, plus the synchronous and asynchronous evaluator wrappers:

- when a new result buffer is produced, derive its HashType and register it through the normal write-through local cache;
- do not add a result-specific direct database writer or block the evaluation response on the background upload;
- for an identity Expression, retain/use the input checksum’s existing HashType rather than inventing a second type;
- apply the same logic to null, conversion, and path-projection results; and
- do not infer result HashType merely from the declared target celltype when the actual buffer is available.

The ownership rule follows the buffer, not the role named “evaluator”:

- local evaluation classifies in the client process that holds the result buffer;
- direct jobserver evaluation classifies in the jobserver process;
- daskserver evaluation classifies in the Dask worker;
- a client or jobserver that receives only the result checksum does not classify or upload anything.

The jobserver/daskserver response remains checksum-only; HashTypes are read from the database, not supplied by the response. Where integration tests immediately inspect the database, flush the writer in the buffer-holding process first.

### 10.5 Extend HashType tests

Update or add coverage in:

- [`seamless-core/tests/test_hash_type_tightening.py`](/home/agent/seamless1/seamless-core/tests/test_hash_type_tightening.py:117) for local equal, looser, tighter, contradictory, and upload-on-tightening behavior;
- `seamless-core/tests/test_hash_type_remote_cache.py` for fire-and-forget write-through, flush behavior, and synchronous database lookup outside a running event loop;
- `seamless-core/tests/test_hash_type_validation.py` for the running-loop lookup refusal returning `None` without blocking or raising;
- [`seamless-database/tests/test_execution_records.py`](/home/agent/seamless1/seamless-database/tests/test_execution_records.py:250), replacing the current “all differing words conflict” expectation with the four-way tightening matrix;
- the local and remote Expression evaluation tests for result HashType persistence; and
- daskserver integration tests proving the Dask worker stores the result HashType and a fresh client can validate the result using only the database entry, with neither a local HashType cache entry nor the result buffer.

## 11. Additional verification commands for §§10.4–10.6

```bash
cd /home/agent/seamless1/seamless-core
conda run -n seamless1 pytest -q tests/test_standalone_read_remote_steps.py
conda run -n seamless1 pytest -q tests/test_expression_remote_evaluation.py
conda run -n seamless1 pytest -q tests/test_hash_type_remote_cache.py
conda run -n seamless1 pytest -q tests/test_hash_type_validation.py
```

```bash
cd /home/agent/seamless1/seamless-database
conda run -n seamless1 pytest -q tests/test_hash_type_tightening.py
```

```bash
cd /home/agent/seamless1/seamless-remote
conda run -n seamless1 pytest -q tests/test_jobserver_client.py
conda run -n seamless1 pytest -q tests/test_client_recovery.py
```

```bash
cd /home/agent/seamless1/seamless-jobserver
conda run -n seamless1 pytest -q tests/test_run_expression_errors.py
```

```bash
cd /home/agent/seamless1/seamless-transformer
conda run -n seamless1 pytest -q tests/test_expression_remote_schema.py
```

```bash
cd /home/agent/seamless1/seamless-dask
conda run -n seamless1 pytest -q tests/test_expression_inputs.py
```

Run each core test file in its own pytest process because their process-global caches are intentionally isolated by process. Run the direct-jobserver and daskserver integration scenarios separately. Both must satisfy the same assertions for result checksums, result HashTypes, duplicate-request coalescing, and typed `CacheMissError` reconstruction with its checksum argument intact.
