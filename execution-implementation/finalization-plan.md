# Execution Records Finalization — Implementer Handoff

## Goal

This document is the implementation handoff for closing the remaining execution-records work.
It replaces the earlier draft with an execution order, resolved decisions, exact file targets,
and acceptance criteria for the implementing agent.

The implementation is already largely in place. The remaining work is:

1. Close the missing test coverage from the review.
2. Remove duplicated record helpers.
3. Extract record assembly out of `transformation_cache.py`.
4. Add the missing compilation-context cache.
5. Change the default behavior to write a **minimal** execution record even when `record: false`.
6. Remove non-minimal record overhead from the `record: false` hot path.
7. Fix Dask strict-mode error handling so record failures are not silently lost.

## Resolved decisions

These points are no longer open questions. Implement against them directly.

- **Behavior change**: successful non-probe executions now write one execution record even when
  `record: false`; in that mode the record is **minimal**.
- **No schema change**: the database validator already accepts a minimal record as long as it
  includes `schema_version: 1`, `tf_checksum`, and `result_checksum`. Do not change
  `seamless-database/database.py` unless a failing test proves this assumption wrong.
- **Exactly one record write per successful execution**:
  - `record: false` → write one minimal record.
  - `record: true` → write one full record.
  - Do **not** write a minimal record first and then overwrite it with a full record.
- **Canonical persisted field names stay unchanged**:
  - persisted record: `cpu_time_user_seconds`, `cpu_time_system_seconds`
  - transport/runtime metadata may continue to use `cpu_user_seconds`, `cpu_system_seconds`
- **Probe jobs still write no execution record**.
- **Remote protocol note**: there is no explicit jobserver protocol-version mechanism today.
  Change server and client together, and keep the client tolerant of legacy string responses
  until all local call sites are updated.
- **Helper extraction scope**: do not move `probe_capture._utcnow_iso()`. It intentionally keeps
  microsecond precision and is not part of the execution-record hot path.

## Non-goals

Still out of scope for this implementation:

- Failed-job execution records.
- New user-facing query/CLI tooling beyond what already exists.
- Full forensic `ldd` logs or `/proc/self/maps` capture.
- Public “verbose-baseline” operator knobs.
- Unrelated cleanup outside the record path.

## Current facts to preserve

- The native-linkage check for `native_link_outside_conda_prefix` is already implemented in
  `seamless-transformer/seamless_transformer/transformation_cache.py`.
- The spawn path already routes through `TransformationCache.run()`; if the new spawn test fails,
  treat that as a real bug to fix, not a reason to weaken the test.
- The remote jobserver path already returns structured record data in `record: true` mode.
  The remaining work is to make that payload always structured and to carry the minimal-runtime
  data required for `record: false`.

## Required implementation order

Implement in this order. Do not start with the large refactor.

### Step 0 — Baseline and characterization

Before changing code, run the focused test suites that cover the touched paths:

- `seamless-transformer/tests/test_execution_records.py`
- `seamless-dask/tests/test_execution_records.py`
- `seamless-remote/tests/test_jobserver_client.py`

If there are unrelated pre-existing failures, note them and continue. Do not broaden scope.

### Step 1 — Add missing review coverage first

Add the missing tests before refactoring so the current behavior is pinned down.

Preferred test files:

- extend `seamless-transformer/tests/test_execution_records.py`
- add a new focused test file only if the existing file becomes unmanageable

Required new coverage:

- **Native-link violation**:
  - Build a compiled transformer that links against a `.so` outside the conda prefix.
  - Assert `contract_violations` contains `native_link_outside_conda_prefix`.
- **Spawn execution path**:
  - Execute with `execution: spawn` and `record: true`.
  - Assert exactly one execution record is written.
  - Assert persisted `execution_mode == "spawn"`.

If the spawn test currently records `"process"` instead of `"spawn"`, fix the production code.
Do not change the assertion.

### Step 2 — Extract shared helpers and add record-mode runtime cache

Create:

- `seamless-transformer/seamless_transformer/record_utils.py`
- `seamless-transformer/seamless_transformer/record_runtime.py`

Move these helpers into `record_utils.py`:

- `_utcnow_iso()`
- `_memory_peak_bytes()`
- `_process_create_time_epoch()`
- `_resolve_remote_target()`

Source locations to deduplicate:

- `seamless-transformer/seamless_transformer/transformation_cache.py`
- `seamless-transformer/seamless_transformer/probe_index.py`
- `seamless-jobserver/jobserver.py`
- `seamless-dask/seamless_dask/client.py`

Important detail:

- Use the broader `_resolve_remote_target()` behavior from `transformation_cache.py`.
- Leave `probe_capture._utcnow_iso()` alone.

Add a process-local record-mode cache in `record_runtime.py`:

```python
_CACHED_RECORD_MODE: bool | None = None

def get_record_mode() -> bool: ...
def invalidate_record_mode_cache() -> None: ...
```

Required invalidation points:

- `seamless-config/seamless_config/select.py::select_record()`
- `seamless-config/seamless_config/select.py::reset_record_before_load()`

Rationale: invalidating only on config-file reload is insufficient because `select_record()`
is public and can mutate the setting directly.

### Step 3 — Pure refactor: move record assembly out of `transformation_cache.py`

Create `seamless-transformer/seamless_transformer/record_assembly.py`.

Move record-specific code there without changing behavior yet:

- `build_execution_record()`
- validation-snapshot helpers
- compilation-context helpers
- job-validation helpers
- `compute_record_io_bytes()`
- `collect_compilation_runtime_metadata()`
- `load_bucket_contract_violations()`
- GPU sampler helpers/classes
- module-level caches currently owned by the record path

Keep `TransformationCache` and cache-execution control flow in
`seamless-transformer/seamless_transformer/transformation_cache.py`.

Compatibility requirement:

- Preserve the current public imports from `transformation_cache.py`.
- Update `seamless-transformer/seamless_transformer/transformation_cache.py:1967`
  `__all__` and re-export moved symbols as needed.

After this step, Step 1 tests must still pass without semantic changes.

### Step 4 — Cache `build_compilation_context_checksum()` by compiled-module digest

Add in `record_assembly.py`:

```python
_COMPILATION_CONTEXT_CACHE: dict[str, str] = {}
```

Required behavior:

- Key: compiled-module digest
- Value: resulting compilation-context checksum
- On cache hit: skip compiler-version subprocess calls and skip rebuilding the payload
- On miss: compute exactly as today and store the checksum

Do not merge this with `_COMPILED_VALIDATION_CACHE`; they solve different problems.

### Step 5 — Implement minimal records as the default persisted record

This is the main behavior change.

Add `build_minimal_execution_record()` to `record_assembly.py`.

The minimal persisted record contains exactly:

- `schema_version`
- `tf_checksum`
- `result_checksum`
- `seamless_version`
- `execution_mode`
- `remote_target`
- `wall_time_seconds`
- `cpu_time_user_seconds`
- `cpu_time_system_seconds`
- `memory_peak_bytes`
- `gpu_memory_peak_bytes`

Rules:

- Do not include `checksum_fields`.
- Do not include freshness, compilation, validation, envelope, hostname, pid, retry count,
  worker index, or other full-record-only fields.
- Do not add database-schema or validator changes to make this work.

Call-site behavior:

- Always gather the minimal runtime scalars needed for a minimal record.
- On successful non-probe execution:
  - `record: false` → build minimal record and call `set_execution_record()` once
  - `record: true` → build full record and call `set_execution_record()` once

This means the minimal builder should share runtime-scalar preparation with the full builder,
but the database write must happen only once per success.

Docs to update in the same patch series:

- `seamless/conversation/records/execution-records-implementation.md`

That document currently says `record: false` does not write execution records. After this change,
that statement is no longer true.

### Step 6 — Fix Dask strict-mode error handling

The review correctly identified the inner swallow in
`seamless-dask/seamless_dask/client.py`, but there are **two** swallow layers:

- the inner `except Exception: return` inside `_promise_and_write_result_async()`
- the outer `except Exception: pass` around the call site in `_run_base()`

Both must be addressed.

Required semantics:

- In `record: true`, record-writing failures must propagate out to the Dask caller.
- In `record: false`, minimal-record write failures may be best-effort **only** for narrowed
  transport/storage exceptions; they must emit a warning through `_LOGGER`.
- `RecordBucketError` must never be swallowed.
- Programmer errors and schema bugs must never be downgraded to warnings.

Implementation freedom:

- A dedicated exception type for strict record persistence failures is acceptable.
- Another structure is acceptable if it preserves the semantics above.

Do not leave a broad `except Exception` around the strict record-writing path.

### Step 7 — Remove `record: false` hot-path overhead

Once minimal records exist, remove the full-record overhead from the default path.

#### 7a. Transformer in-process path

In `seamless-transformer/seamless_transformer/transformation_cache.py`:

- Replace per-call `bool(get_record())` with `get_record_mode()`.
- When `get_record_mode()` is `False`, skip:
  - `is_record_probe()`-driven heavy record work beyond the final “do not write probe record” check
  - probe-context fetches
  - compilation-context assembly
  - validation snapshot construction
  - bucket-contract aggregation
  - job validation

The default path should only pay for:

- timing capture
- memory/GPU capture
- minimal record assembly
- one `set_execution_record()` call

#### 7b. `run.py` sync bridge

In `seamless-transformer/seamless_transformer/run.py`, replace the unconditional
`ensure_record_bucket_preconditions_sync(...)` call with:

```python
if get_record_mode() and not is_record_probe(transformation, tf_dunder):
    ensure_record_bucket_preconditions_sync(transformation, tf_dunder)
```

This removes the per-execution `asyncio.run()` / thread bridge overhead in the default mode.

#### 7c. Jobserver runtime payload

In `seamless-jobserver/jobserver.py`:

- Use `get_record_mode()`.
- Always capture the minimal runtime data required by the caller to write a minimal record:
  - `started_at`
  - `finished_at`
  - `wall_time_seconds`
  - `cpu_user_seconds`
  - `cpu_system_seconds`
  - `memory_peak_bytes`
  - `gpu_memory_peak_bytes`
- Only gather full-record-only runtime fields when `record: true`:
  - `hostname`
  - `pid`
  - `process_started_at`
  - `process_create_time_epoch`
  - `worker_execution_index`
  - `retry_count`
  - `compilation_time_seconds`

This is necessary because the parent process cannot reconstruct remote worker memory/timing
after the fact.

#### 7d. Jobserver wire format

Change the success payload returned by `seamless-jobserver` and parsed by
`seamless-remote/seamless_remote/jobserver_client.py`:

- Normal success must always return a JSON object, not a bare checksum string.
- Minimal required keys:
  - `result_checksum`
  - `record_runtime`
- Full-record mode may additionally include:
  - `probe_context`
  - `compilation_context`
  - `job_validation`

Remote-job materialization case:

- The current transport can also return a `RemoteJobWritten` marker.
- Preserve that behavior with an explicit structured payload, e.g. a dedicated field carrying the
  encoded marker or directory, and update both client and `TransformationCache.run()` to handle it.
- Do not regress `write_remote_job` behavior while optimizing away the failed `json.loads(...)`
  fallback.

Compatibility rule:

- `JobserverClient.run_transformation()` should remain tolerant of the legacy bare-string response
  until the server/client change lands together.

#### 7e. Dask path

In `seamless-dask/seamless_dask/client.py`:

- Cache `record_mode` once via `get_record_mode()`.
- Skip full-record-only work when `record_mode` is `False`.
- Continue writing the minimal record from the worker-side result-persistence path.

### Step 8 — Verification and docs

Add or extend tests for all new contracts.

Required coverage:

- Minimal record is written when `record: false`.
- Minimal record contains exactly the agreed field set and no full-record-only fields.
- Minimal record passes the existing database validator.
- No probe-index lookup happens when `record: false`.
- `invalidate_record_mode_cache()` is triggered by both `select_record()` and
  `reset_record_before_load()`.
- `_COMPILATION_CONTEXT_CACHE` skips compiler-version subprocess work on repeated calls.
- Dask strict mode propagates execution-record write failures.
- Dask minimal mode logs and continues on narrowed storage failures.
- Jobserver client accepts the new JSON success payload.
- Jobserver client still handles the remote-job materialization case.

Also update any documentation and README snippets affected by:

- minimal records becoming the default persisted behavior
- the jobserver success payload format

## Primary files expected to change

- `seamless-transformer/seamless_transformer/transformation_cache.py`
- `seamless-transformer/seamless_transformer/run.py`
- `seamless-transformer/seamless_transformer/probe_index.py`
- `seamless-transformer/seamless_transformer/record_utils.py`
- `seamless-transformer/seamless_transformer/record_runtime.py`
- `seamless-transformer/seamless_transformer/record_assembly.py`
- `seamless-transformer/tests/test_execution_records.py`
- `seamless-dask/seamless_dask/client.py`
- `seamless-dask/tests/test_execution_records.py`
- `seamless-jobserver/jobserver.py`
- `seamless-remote/seamless_remote/jobserver_client.py`
- `seamless-remote/tests/test_jobserver_client.py`
- `seamless-config/seamless_config/select.py`
- `seamless/conversation/records/execution-records-implementation.md`

## Final acceptance checklist

The implementation is complete only when all of the following are true:

- `record: true` still writes one full canonical execution record per successful non-probe run.
- `record: false` now writes one minimal execution record per successful non-probe run.
- No successful path writes two records for the same `(tf_checksum, result_checksum)`.
- Probe jobs still write no execution record.
- The spawn path is covered by tests and persists `execution_mode == "spawn"`.
- Dask no longer silently drops strict-mode record failures.
- The `record: false` hot path no longer does probe lookup, compilation-context work,
  validation-snapshot work, or failed `json.loads(...)` fallbacks on jobserver success.
- The spec/handoff doc now matches the implemented `record: false` behavior.
