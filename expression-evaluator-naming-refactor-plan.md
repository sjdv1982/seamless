# Expression evaluator naming refactor: implementation plan

The contract docs (`docs/agent/contracts/expressions.md`) already describe the landed state. This plan brings the code in line with them.

## Goals

1. Each evaluation entry point's name says where the evaluation runs.
2. Identity recording (the process cache plus the database `expression` table) happens in one place: the local evaluator core, in whichever process evaluates.
3. No helper whose name says "publish" is left in the Expression code unless it writes to the hashserver.

## 1. Renames

In `seamless-core/seamless/checksum/expression.py`:

| Old | New | What it does |
|---|---|---|
| `evaluate_expression` | `evaluate_expression_local` | synchronous; local only; never dispatches |
| `evaluate_expression_async` | `evaluate_expression_local_async` | asynchronous; local only; joins the member set keyed by Expression identity |
| `evaluate_expression_remote` | `evaluate_expression_placed` | asynchronous; checks the process cache, then the database, then decides placement (local, or a jobserver/daskserver dispatch); the only entry point that takes `execution` |

In `seamless-core/seamless/expression_class.py`: rename `Expression._publish_result` to `Expression._hold_result`. It keeps a tempref and an optional user hold, and writes nothing.

Not renamed: the private `_evaluate_expression_async` (`contracts/deep-celltypes.md` cites it) and `_tempref_expression_result`.

**No aliases.** Remove the old names from `__all__`. When the work is done, `grep -rnE "\bevaluate_expression(_async|_remote)?\b"` over the code repos and `seamless/docs/agent` must return no hits. Historical plan files (`seamless/*.md` and `seamless-workflow/validation/`) are left as they are.

Do not reuse `evaluate_expression` as the new name of the placing entry point. That would turn a synchronous function into an asynchronous one under the same name, and an old call site would then silently get a coroutine that is never awaited.

### Call sites outside the tests

| File | Old name → new name |
|---|---|
| `seamless-core/seamless/expression_class.py` (synchronous path, ~260/316) | `evaluate_expression` → `_local` |
| `seamless-core/seamless/expression_class.py` (asynchronous path, ~362–393) | `_async` → `_local_async`, `_remote` → `_placed` |
| `seamless-core/seamless/checksum/expression.py` (~471, inside the placing entry point) | `_async` → `_local_async` |
| `seamless-core/seamless/checksum_class.py` (~393–404, fingertip) | `_async` → `_local_async` |
| `seamless-transformer/seamless_transformer/worker.py` (~2452–2463, `dispatch_expression`) | `_async` → `_local_async` |
| `seamless-workflow/seamless_workflow/sidework.py` (~91, ~106–108) | `evaluate_expression` → `_local` |
| `seamless-workflow/seamless_workflow/context.py` (~1693–1699, `_demand`) | `_remote` → `_placed` |
| `seamless-dask/seamless_dask/client.py` (~855–858) | `_remote` → `_placed` |
| `seamless-workflow/tests/README.md` | check for any of the names |

### Test files to update

- `seamless-core/tests/`: `test_contract_expressions.py`, `test_standalone_read_remote_steps.py`, `test_expression_reference_lifecycle.py`, `test_expression_errors.py`, `test_conversion_engine.py`, `test_expression_contract.py`, `test_contract_celltypes_conversion.py`
- `seamless-remote/tests/`: `test_expression_remote_evaluation.py`, `test_core_remote_integration.py`
- `seamless-jobserver/tests/test_run_expression_errors.py`
- `seamless-workflow/tests/`: `test_late_expression_materialization.py`, `correctness/test_correctness_expressions.py`
- `seamless-dask/tests/test_expression_inputs.py`

Some of these name the functions in string literals: parametrize ids in `test_contract_expressions.py` (~189–197) and an `__import__(..., fromlist=["evaluate_expression"])` in `test_expression_reference_lifecycle.py` (~38). Rename those too.

## 2. Move identity recording into the evaluator

**Today.** Database writes are made by the callers, not by the evaluator:

| Site | When it writes |
|---|---|
| `checksum/expression.py` ~505 | the placing entry point, after it placed the evaluation locally |
| `checksum/expression.py` ~591 (`_execute_remote_expression`) | the client, after a dispatch |
| `expression_class.py` ~331–345 | synchronous `Expression.compute(execution="local")` |
| `checksum_class.py` ~414–424 | `Checksum.fingertip`, after a successful candidate |

Nothing records in the database for `compute_async(execution="local")`, for `sidework.py`, or for the executing side of a dispatch (the jobserver's in-process evaluation or a Dask worker). This contradicts the *Recording identity* row of `expressions.md`: "the evaluating process" records.

**Change.**

1. **A metadata writer that both sync and async code can use.** `seamless/caching/buffer_writer.py` already queues HashType writes to the database on its writer thread (`register_hash_type`). Generalize its metadata entry:
   - give `_QueueEntry` a `metadata_key` (the dedup key) and a `metadata_write` coroutine function in place of `hash_type` + `metadata_writer`;
   - key `_entries` by `metadata_key` for metadata entries;
   - rewrite `register_hash_type` on top of the generalized entry, with key `("hash_type", checksum, word)`;
   - add `register_expression_result(key, result)`, with key `("expression", input_hex, path, input_celltype, celltype)`, which calls `database_remote.set_expression_result(...)`.

   Writes are flushed by the existing `buffer_writer.flush()` and by `seamless.close()`.
2. **One recording helper.** Add `_record_expression_result(key, cache_key, result)` to `checksum/expression.py`. It sets `_expression_cache[cache_key] = result` and calls `buffer_writer.register_expression_result(key, result)`. It is a no-op for the database when `seamless_remote` is not importable.
3. **Call it at every terminal branch of `_evaluate_expression_after_validation`** that writes the process cache (~706, ~712, ~748, ~765, ~782). These are the only places where a result is produced, and every local path, synchronous or asynchronous, ends there.
4. **Delete the caller-side writes** in the placing entry point (~505), `expression_class.py` (~331–345) and `checksum_class.py` (~414–424).
5. **Keep the client-side write after a dispatch** (~591). It is idempotent with the executing side's own record (same key, same result is accepted), and it still records when the executing side has no database configured. Process-cache writes that only copy a database hit or a dispatched result (~416, ~495, ~588) stay plain cache writes.

**Consequences, all of which the contract already states:**

- Every evaluation records, wherever it was placed: the jobserver and Dask executing sides, `compute_async(execution="local")`, sidework and fingertip.
- For local evaluation the database write becomes queued instead of awaited inline. A test that reads the database right after `compute()` must call `buffer_writer.flush()` first. `test_explicit_local_evaluation_also_records_identity_in_the_database` needs that flush.
- Handling of the 409 conflict is unchanged here: the write still reports `False`. Whether to make the conflict loud is a separate decision (the irreproducibility item in `NEW REGISTER.md`).

## 3. Tests to add

- `compute_async(execution="local")` records the identity in the database: the asynchronous counterpart of the existing synchronous test.
- The executing side records: a `worker.dispatch_expression` evaluation writes the database row itself, with no client-side write involved.
- `buffer_writer`: a HashType write and an Expression-result write for the same checksum do not deduplicate against each other.

## 4. Order of work

1. Generalize the `buffer_writer` metadata entry and add `register_expression_result`, with its unit test. This step changes no behaviour.
2. Add `_record_expression_result`, switch the evaluator's terminal branches to it, delete the caller-side writes, and add the flush to the database test. Run the seamless-core expression tests.
3. Do the renames, call sites and tests: mechanical, one commit per repo, all repos in lockstep.
4. Run the grep check. Run the focused tests one pytest process per file: seamless-core, seamless-remote, seamless-jobserver, seamless-dask and seamless-workflow, every file that mentions Expressions.

## 5. Two more defects in the same file, found during the review

### 5a. A serialization failure escapes as a bare `TypeError`

When the value a path selected cannot be serialized at the target celltype, `_serialize_expression_result` (`checksum/expression.py` ~1046) lets the exception from `Buffer(value, celltype)` escape. For example, `Expression(struct_array_checksum, "[0]", input_celltype="mixed", celltype="plain")` raises `TypeError: Type is not JSON serializable: numpy.void`. Over a dispatch, that crosses the envelope as kind `execution`.

`expressions.md`, *Which refusal happens where*, places a failure caused by the value behind the checksum under `ExpressionEvaluationError`. The function already does exactly that for `binary` ("Expression result is not serializable as binary").

**Fix:** wrap the `Buffer(value, celltype)` call, and raise `ExpressionEvaluationError(f"Expression result is not serializable as {celltype}")` from the original exception.
**Test:** the example above raises `ExpressionEvaluationError`, both locally and through the error envelope.

### 5b. The synchronous local evaluator bypasses the member set (observed in the code, not verified)

`evaluate_expression` (to become `evaluate_expression_local`) goes straight to `_evaluate_expression_after_validation`. Unlike the asynchronous form, it never joins `_active_expressions`. So two threads that synchronously evaluate the same identity both do the work, and neither joins an in-flight asynchronous evaluation.

`expressions.md`, *Deduplication*, says the member set is shared by every caller that would do work. Decide whether the synchronous form should join it: wait on the shared future from a worker thread, as the synchronous `compute()` path already does for remote work. If not, the page should exempt synchronous local evaluation. Write a two-thread test first, to confirm the double evaluation.
