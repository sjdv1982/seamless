# Execution Records Implementation Review

## Supercommit Grouping

Commits are grouped by the 2-minute proximity rule (each commit within 2 minutes of the previous one in the group).

---

## Supercommit 1 — 2026-04-26 17:13:50 — Foundation

**Commits:**
- `[seamless-config]` Add record mode and node selection plumbing
- `[seamless-database]` Implement execution record storage
- `[seamless-remote]` Add remote execution record APIs
- `[seamless-transformer]` Add seamless-run node targeting

### Feature coverage

Implements Phase 1 (database storage) and the bulk of Phase 2 (config/CLI surface):

- `record: true` config command: `select_record()`, `get_record()`, `reset_record_before_load()` — all present, correct semantics. Reset logic properly distinguishes "command"-source from "manual"-source state, consistent with existing patterns for other config commands.
- `node` config command + `--node` CLI flag: implemented, validated to be daskserver-only.
- `seamless-database`: `MetaData` gets a `result` field. PUT metadata now validates `tf_checksum`/`result_checksum` identity, enforces atomic conflict detection, and blocks writes when the transformation already has an irreproducible record. GET for `irreproducible` type implemented (was PUT-only before). Schema migration helper handles empty legacy tables.
- `seamless-remote`: `get_execution_record`, `get_irreproducible_records`, `set_execution_record` added to both `DatabaseClient` and `database_remote`. Pattern-consistent with existing remote methods.
- Protocol bumped from 2.0 → 2.1.

### Code quality

Good. The database changes are the most complex piece and they're well-handled:
- `_get_transformation_row`/`_get_metadata_row` helpers avoid repetition.
- Atomic transactions properly wrap all multi-row operations.
- `_ensure_meta_data_schema()` handles the schema upgrade corner case cleanly.

**Minor issues:**
- `_normalize_metadata_value()` accepts a string and JSON-parses it, which seems unnecessary since the PUT caller always sends a dict. Dead code path.
- In `database_remote.set_execution_record`, the `ok is not False` check counts `None` as success, which is inconsistent with `set_transformation_result` in the same file — that also does `ok is not False`, but `client.set_execution_record` returns `None` on success (no explicit return). This is a latent logic issue, not functional.
- `node` constraint in `--node` validation allows only `daskserver`, but the spec also says jobserver should be rejected clearly — this is done, but only via the implicit `remote_target != "daskserver"` check. The error message "only supported for remote daskserver execution" is clear enough.

---

## Supercommit 2 — 2026-04-26 18:10:53 — Local and Dask Record Capture

**Commits:**
- `[seamless-transformer]` Record successful executions in transformer runtime
- `[seamless-dask]` Record Dask execution metadata

### Feature coverage

Phase 5 (per-job record assembly) skeleton:

- `build_execution_record()` produces a canonical dict matching the spec schema exactly: all required fields, correct `checksum_fields` list, `execution_envelope` with all required sub-fields, timing fields, metadata fields.
- Wall time and CPU times (user+system) are measured around the actual execution in both the transformer and Dask paths.
- Record is written to the database after the transformation result is stored.
- `record_mode` gate: requires a database write server.

**Issue in this commit (corrected in SC5):** `environment` is set to the raw `__env__` dunder checksum rather than the bucket checksum from the probe index. The spec says bucket checksum fields must come from the probe index. This is a placeholder that gets corrected once the probe context is wired in SC5.

### Code quality

`build_execution_record()` is well-structured. The `execution_envelope` construction correctly reads `__meta__` for `scratch` and `allow_input_fingertip`, and resolves `language_kind`. The function is pure (no side effects).

**Issue:** In `seamless_dask/client.py`, the entire record-writing block sits inside `except Exception: return`, which silently discards any bug in record assembly. This is labeled "best-effort" in a comment, but it hides real implementation errors. Preflight validation errors (like a missing probe) would be silently swallowed here, which contradicts the strictness of `record: true` mode. This pattern persists through later supercommits.

**Minor:** `_utcnow_iso()` is defined identically in `transformation_cache.py` and `dask/client.py`, and will be duplicated again in `jobserver.py`. A shared utility would be cleaner.

---

## Supercommit 3 — 2026-04-26 18:14:58 — Probe Index Storage

**Commits:**
- `[seamless-database]` Add shared bucket probe index
- `[seamless-remote]` Expose bucket probe database APIs

### Feature coverage

Section 8 of the spec (shared probe index):

- `BucketProbe` model with composite primary key `(bucket_kind, label)`, correct fields (bucket_checksum, captured_at, freshness_tokens).
- GET returns the current row or None. PUT upserts (update-or-create).
- `BUCKET_KINDS` constant validates bucket kinds on write.
- Protocol bumped 2.1 → 2.2.
- `database_remote.get_bucket_probe` and `set_bucket_probe` follow the same patterns as the existing remote functions.

### Code quality

Clean. The upsert logic is clear. The bucket_probe route correctly bypasses the standard checksum-parsing flow (since it uses (bucket_kind, label) as its key, not a checksum).

**Minor:** `BUCKET_KINDS` is placed at the bottom of `database.py`, after the main class and all functions. It's referenced in `_validate_bucket_probe_request()` at the top, which is fine since Python resolves names at call time, but the placement is surprising.

---

## Supercommit 4 — 2026-04-26 18:20:06 — Record-Mode Preflight Enforcement

**Commits:**
- `[seamless-transformer]` Enforce record-mode bucket preflight

### Feature coverage

Phase 4 (record-mode preflight enforcement):

New `probe_index.py` module implements:
- `resolve_probe_plan()`: derives execution, remote_target, hostname, env info, labels, live tokens. Correctly handles all three environment types (docker, conda, plain python).
- `ensure_record_bucket_preconditions()`: fetches probe-index entries, compares freshness tokens, raises `RecordBucketError` on missing or stale buckets.
- `ensure_record_bucket_preconditions_sync()`: thread-based async-to-sync bridge for use from `run.py`.
- Label conventions match the spec exactly: `node=hostname`, `environment=conda:<prefix>`, `node_env=<node_checksum>:<env_checksum>`, etc.
- Required bucket kinds depend on backend: process/spawn/jobserver get `[node, environment, node_env]`; daskserver gets all five.

The hook in `run.py` calls the sync bridge before any user code starts — correct placement per spec.

### Code quality

Good modular design. The separation of `resolve_probe_plan()` (pure, returns a plan dict) from `ensure_record_bucket_preconditions()` (async, side-effectful DB check) is appropriate and will allow sharing with `seamless-probe`.

**Issue:** `database_remote` is imported at module level with a try/except. This binds the reference at import time. If the seamless remote is initialized after `probe_index` is imported, the module-level `database_remote` will be `None` even after remote initialization. This is a latent issue (the `ensure_record_bucket_preconditions` function checks `database_remote is None` but uses the module-level binding). In practice this probably works because `probe_index` is imported lazily enough, but it's fragile.

**Issue:** `_resolve_remote_target()` is duplicated from `transformation_cache.py`. Same logic, same name, separate definitions. This is a code organization problem.

**Minor:** The thread-based sync bridge in `ensure_record_bucket_preconditions_sync()` spawns a new thread every call. For the normal execution path (one record per job), this is fine. The `asyncio.get_running_loop()` / except-RuntimeError dance is necessary but verbose.

---

## Supercommit 5 — 2026-04-26 20:29:06 — Freshness Data in Records

**Commits:**
- `[seamless-dask]` Include freshness data in Dask records
- `[seamless-transformer]` Populate execution record freshness fields

### Feature coverage

Completes Section 6.5 (`freshness` field) and corrects the bucket checksum fields:

- `build_execution_record()` now accepts `probe_context` and derives `node`, `environment`, `node_env`, `queue`, `queue_node` from `required_bucket_checksums`. Previously these were placeholders.
- `freshness` dict is correctly populated from the probe context.
- For local/spawn execution, `ensure_record_bucket_preconditions()` is called after the execution to get the probe context.
- For jobserver remote, probe context comes from the jobserver response (wired in SC6).

### Code quality

The change to `build_execution_record()` is clean — `probe_context` is an optional parameter (defaults to None/empty), so the function remains backward-compatible.

**Minor:** `env_checksum` was previously used directly as the `environment` field in SC2. After SC5, it's no longer used at all in the bucket fields (they all come from probe_context). The dead code (`env_checksum` computed at the top of the function) remains as a contributor to `execution_envelope.resolved_env_checksum`, which is correct.

---

## Supercommit 6 — 2026-04-26 21:15:50 — Jobserver Probe Context

**Commits:**
- `[seamless-jobserver]` Return probe context for record mode
- `[seamless-remote]` Parse structured jobserver success payloads
- `[seamless-transformer]` Use jobserver probe context in records

### Feature coverage

Implements the return-path design from Section 10.3:

- Jobserver calls `ensure_record_bucket_preconditions()` after successful execution and includes the result in a JSON dict response payload alongside `result_checksum`.
- `jobserver_client.py` now parses the JSON dict response, returning `{"result_checksum": ..., "probe_context": ...}`.
- `transformation_cache.py` extracts `probe_context` from the dict and skips the local probe fetch for jobserver remote. The local probe fetch is used only when probe_context is None (i.e., for non-jobserver backends).

### Code quality

Good. The return-path design is correctly implemented — probe context is computed once (on the worker side) and returned to the manager, which writes the record. This avoids the manager having to re-fetch probe context from the database.

**Minor:** The jobserver changes `response_payload = result_checksum.hex()` to a JSON string when record mode is active. This changes the wire format for the jobserver endpoint. Older clients that expect a bare checksum hex string would break. This is acceptable if all clients are updated simultaneously (which they appear to be), but is a protocol change without a version bump.

---

## Supercommit 7 — 2026-04-27 09:12:30 — Probe Job Skipping + seamless-probe

**Commits:**
- `[seamless-dask]` Skip execution records for probe jobs
- `[seamless-jobserver]` Skip probe preflight payloads on jobserver
- `[seamless-transformer]` Add seamless-probe bucket refresh path

### Feature coverage

Phase 2 remainder (seamless-probe):

- `is_record_probe()` detection via `__record_probe__` key in tf_dunder. Probe jobs skip execution record writing in both Dask and jobserver paths. This is correct per spec (probes run through the normal execution path but don't produce execution records themselves).
- `probe_capture.py` (new file): bucket payload builders for all 5 kinds (node, environment, node_env, queue, queue_node). Each builder collects the appropriate facts:
  - `node`: CPU info, RAM, GPU inventory (skeleton at this point, expanded in SC20-SC21), boot_id, OS info.
  - `environment`: Python packages, conda env export, compiler info, locale, relevant env vars.
  - `node_env`: numpy config, threadpool info, CUDA toolkit version.
  - `queue`: normalized config dict from `configure_daskserver()`.
  - `queue_node`: OMP/MKL/OPENBLAS env vars, cgroup memory limit, resource limits.
- `seamless-probe` CLI: registered as entry point. Uses `probe_mode=True` to inject `__record_probe__` into tf_dunder. Implements `--force` flag (reprobes even fresh buckets).
- The probe runs through the normal backend path (not a separate framework), consistent with spec Section 5.3 and 2.3.

### Code quality

`probe_capture.py` is large but well-organized — one function per bucket kind, and each function returns a plain dict with the common fields (schema_version, bucket_kind, contract_ok, contract_violations, validation_snapshot) as required by spec Section 7.0. The contract fields are initialized to sane defaults (contract_ok=True, violations=[]) for buckets without mechanistic checks yet.

**Issue:** The `seamless-probe` code path in `main.py` is embedded in the same `_main()` function as `seamless-run`, controlled by a `probe_mode` boolean. This makes the shared function complex. A separate function could be cleaner, though the shared argument parsing justifies the approach.

**Minor:** `is_record_probe()` checks `tf_dunder.get("__record_probe__")` — the key is not validated further. Any truthy value triggers the skip. This is simple and sufficient.

---

## Supercommit 8 — 2026-04-27 09:14:52 — Bucket Contract Violations

**Commits:**
- `[seamless-dask]` Carry bucket contract violations into Dask records
- `[seamless-transformer]` Aggregate bucket contract violations in records

### Feature coverage

Section 6.6 (validation fields) — bucket-scoped contract aggregation:

- `load_bucket_contract_violations()`: resolves each bucket payload by checksum (from probe_context), extracts `contract_violations`, aggregates into a sorted, deduplicated list.
- `build_execution_record()` now accepts `bucket_contract_violations` and `job_contract_violations`, computes `contract_violations` as their sorted union.
- Both transformer and dask paths call `load_bucket_contract_violations()`.

### Code quality

Clean implementation. The spec's rule ("jobs must not repeat heavy bucket-level contract analysis; bucket-level contract outcomes must already be stored by probe payloads") is correctly followed — the code just reads from the already-stored bucket payload.

**Minor:** `load_bucket_contract_violations()` catches broad `Exception` per checksum resolution. This means a hashserver failure silently skips violations. Given the best-effort nature, this is acceptable.

---

## Supercommit 9 — 2026-04-27 10:21:27-10:22:48 — Compiled Context + Buffer Sizes

**Commits:**
- `[seamless-dask]` Attach compiled contexts to Dask records
- `[seamless-jobserver]` Return compiled context from jobserver
- `[seamless-remote]` Parse compiled context from jobserver payloads
- `[seamless-transformer]` Store compiled execution contexts in records
- `[seamless-dask]` Include buffer sizes in Dask records
- `[seamless-transformer]` Record input and output buffer sizes

### Feature coverage

Section 6.4 (compilation_context) and Section 6.1 buffer sizes:

- `build_compilation_context_checksum()`: builds the canonical compilation context payload matching the spec (language, target, compiler paths/versions, options, object names, link options, compiled-module digest). Serializes as plain celltype buffer, stores in hashserver, returns checksum. Non-compiled transformers return None.
- `compute_record_io_bytes()`: sums input buffer lengths and the result buffer length.
- Both are correctly wired through all three execution paths (local, dask, jobserver).

### Code quality

`build_compilation_context_checksum()` is a substantial function but logically follows the spec's payload definition. Compiler version is retrieved via `--version` subprocess call.

**Issue:** `build_compilation_context_checksum()` is not cached by compiled-module digest at the application level. The spec notes "content-addressing makes repeated compiled contexts deduplicate naturally" — this is true for hashserver storage, but the CPU work of building the payload (including subprocess calls for compiler versions) is done on every record-writing call. Adding a process-level cache by digest would be a meaningful optimization.

**Issue:** `build_compilation_context_checksum()` uses `await Checksum(code_checksum).resolution("text")` — if `code_checksum` is None (e.g., compiled transformer with no code key), this will fail. The code gets `code_checksum = transformation_dict.get("code", (None, None, None))[2]` which handles missing keys, but `Checksum(None)` would raise. This is likely guarded upstream by the `__compiled__` check.

**Minor:** `input_total_bytes` and `output_total_bytes` are set on the record by direct dict mutation after `build_execution_record()` returns, rather than being parameters. This inconsistency with other fields (which are parameters) is not wrong but makes the API less clean.

---

## Supercommit 10 — 2026-04-27 10:27:24 — Validation Snapshots

**Commits:**
- `[seamless-dask]` Attach validation snapshots to Dask records
- `[seamless-transformer]` Store validation snapshots for early record runs

### Feature coverage

Section 11.6 (verbose baseline mode):

- `build_validation_snapshot_checksum()`: implements "first N jobs per bucket configuration" logic. Key is `(execution, sorted(required_bucket_checksums.items()), compilation_context)`. Uses `SEAMLESS_RECORD_VALIDATION_SNAPSHOT_LIMIT` env var (default 1).
- Snapshot payload captures all relevant diagnostic context (env vars, PATH, sys.path, process info, etc.).
- Returns hashserver checksum or None.

### Code quality

The "first N per configuration" counting logic is correct. The key correctly captures the unique execution context. The snapshot payload is comprehensive.

**Minor:** `_VALIDATION_SNAPSHOT_COUNTS` is a process-level dict (not persisted). Restarting the process resets counts. This is acceptable for v1.

---

## Supercommit 11 — 2026-04-27 10:32:47 — Compiled Linkage Validation Helpers

**Commits:**
- `[seamless-transformer]` Prepare compiled linkage validation helpers

### Feature coverage

Phase 6 (validator/diagnostic checks) setup:

- `compiler/__init__.py` refactored: `build_compiled_module()` delegates to `get_compiled_module_info()`, which caches by digest and returns a dict including `compilation_time_seconds` and the module path. This enables downstream validation code to find the `.so` file without needing to track it separately.
- `transformation_cache.py` adds `_allowlisted_library_name()`, `_path_allowed_for_contract()`, ELF parsing helpers using `readelf -d`. These are the building blocks for the v1 native-linkage contract.

### Code quality

The refactor of `build_compiled_module()` to `get_compiled_module_info()` is well done — backward compatible, and the new info dict is the right shape. The compilation timer (`compile_started`) is correctly placed outside the cache check (so cache hits don't record a fake 0s time; they return the originally-measured time).

The allowlist in `_allowlisted_library_name()` matches the spec exactly. `_path_allowed_for_contract()` correctly handles the conda prefix check plus the allowlisted system libraries. The `readelf -d` parsing is defensive (handles missing readelf, subprocess failures).

---

## Supercommit 12 — 2026-04-27 10:38:17 — Job Validation

**Commits:**
- `[seamless-dask]` Carry job validation into Dask records
- `[seamless-jobserver]` Return job validation from jobserver
- `[seamless-remote]` Parse job validation from jobserver payloads
- `[seamless-transformer]` Validate compiled job linkage in records

### Feature coverage

Phase 6 completion — the v1 contract (conda/prefix-first native linkage):

- `collect_job_validation()`: checks RPATH/RUNPATH via `readelf -d` and LD_LIBRARY_PATH at job time. Results cached by compiled-module digest (`_COMPILED_VALIDATION_CACHE`). Reports violation codes matching spec exactly: `rpath_outside_conda_prefix`, `runpath_outside_conda_prefix`, `ld_library_path_outside_conda_prefix`.
- Bug fix within this commit: three `allow_system_roots=True` changed to `allow_system_roots=False` for rpath/runpath/LD_LIBRARY_PATH checks. System roots are not a valid escape from the conda-prefix requirement for these checks (only the allowlisted ABI libraries are).
- `_normalize_job_validation_payload()` provides safe deserialization of the payload whether it comes from the jobserver or local computation.
- Job validation is included in the jobserver response payload (consistent with the return-path design).

### Code quality

The cached-by-digest approach for `collect_job_validation()` correctly avoids re-running `readelf` for the same compiled module in repeated executions. This is the implementation of "compiled-module digest validator cache" from the spec.

**Minor:** The `_COMPILED_VALIDATION_CACHE` is a process-level cache, not shared across restarts. Acceptable.

**Minor:** `collect_job_validation()` is only called for compiled transformers in conda environments. Non-conda and non-compiled jobs get empty violations. This matches the spec scope.

---

## Supercommit 13 — 2026-04-27 10:47:54 — Runtime Metadata

**Commits:**
- `[seamless-jobserver]` Return runtime metadata from jobserver
- `[seamless-remote]` Parse jobserver runtime metadata payloads
- `[seamless-transformer]` Use jobserver runtime metadata in records

### Feature coverage

Populates the scalar execution facts:

- Jobserver captures wall/CPU time, memory peak, hostname, pid, process_started_at, worker_execution_index (per-process counter), retry_count. These are returned in the JSON response payload.
- Transformer extracts these from the dict result and applies them to the record.
- `_process_started_at` is a module-level constant in jobserver.py (set at process start time). Correct approach.

### Code quality

Good. The runtime metadata dict is passed explicitly and applied cleanly. The `record_runtime` dict in jobserver.py is assembled and included in the response payload straightforwardly.

**Issue (duplication):** `_memory_peak_bytes()` with identical logic is defined in both `transformation_cache.py` and `jobserver.py`. Since these are separate processes, some duplication is inevitable, but a shared utility module (e.g., `seamless_transformer.record_utils`) could eliminate it.

**Issue (duplication):** `_utcnow_iso()` appears in three separate files (transformation_cache.py, dask/client.py, jobserver.py). Same function, three copies.

---

## Supercommit 14 — 2026-04-27 10:50:25 — Memory Usage

**Commits:**
- `[seamless-dask]` Populate Dask record memory usage
- `[seamless-transformer]` Populate local record memory usage

### Feature coverage

`memory_peak_bytes` field:

- Both transformer and dask paths call `_memory_peak_bytes()` (via `resource.getrusage`).
- Linux: `ru_maxrss` is in KB, multiplied by 1024. Other platforms: taken as-is. This matches POSIX behavior.
- For dask, memory is sampled from the worker process (calling `_memory_peak_bytes()` on the dask worker side is correct since the work runs there).

### Code quality

Correct and simple. Tests assert the value appears in the record. No issues.

---

## Supercommit 15 — 2026-04-27 10:52:44 — Retry Counts

**Commits:**
- `[seamless-jobserver]` Track jobserver retry counts in records
- `[seamless-remote]` Assert parsed jobserver retry counts
- `[seamless-transformer]` Assert jobserver retry count passthrough

### Feature coverage

`retry_count` field:

- Jobserver increments `retry_count` whenever a restartable error triggers a retry. Correct.
- Tests are assertion-only (no new production code in seamless-remote and seamless-transformer, just test assertions).

### Code quality

Minimal and correct.

---

## Supercommit 16 — 2026-04-27 10:54:47-57 — Compilation Times

**Commits:**
- `[seamless-dask]` Carry compilation times into Dask records
- `[seamless-jobserver]` Return compilation times from jobserver
- `[seamless-remote]` Assert parsed jobserver compilation times
- `[seamless-transformer]` Populate compilation times in records

### Feature coverage

`compilation_time_seconds` field:

- `compiler/__init__.py` stores `compilation_time_seconds` per module info (measured from just before compilation to after).
- `collect_compilation_runtime_metadata()` retrieves it from the module info cache and returns it.
- For cache hits (module already compiled in this process), `compilation_time_seconds` reflects the original compilation time. For cache misses, it's freshly timed. This is correct — the time is meaningful only on first compilation.

### Code quality

Clean vertical slice. The value is `None` if the module was pre-cached from a previous session (only in-memory cache exists), which is correct — the field should not claim zero compilation time when compilation didn't happen in this run.

---

## Supercommit 17 — 2026-04-27 11:12:57 — GPU Memory

**Commits:**
- `[seamless-dask]` Carry GPU memory into Dask records
- `[seamless-jobserver]` Return GPU memory from jobserver
- `[seamless-remote]` Assert parsed jobserver GPU memory
- `[seamless-transformer]` Track GPU memory in local records

### Feature coverage

`gpu_memory_peak_bytes` field:

- `_GpuMemorySampler` class: background thread polls `nvidia-smi --query-compute-apps=pid,used_gpu_memory` every 0.1s, tracks peak MiB by PID, converts to bytes.
- Used in both transformer (local) and Dask worker paths.
- Returns `None` when GPU is not present or nvidia-smi is unavailable.

### Code quality

Solid implementation. The sampler correctly filters by PID, handles nvidia-smi failures gracefully, converts units. The thread is daemonized.

**Minor:** The sampler runs during dispatch to workers (not during local execution). For local transformer execution, `start_gpu_memory_sampler()` / `stop_gpu_memory_sampler()` wrap the appropriate scope.

---

## Supercommit 18 — 2026-04-27 18:05:58-07:10 — Record Tooling Alignment + CUDA Probe

**Commits:**
- `[seamless-transformer]` Align record tooling with discussion guidance
- `[seamless-transformer]` Capture CUDA probe details

### Feature coverage

Improvements to probe_capture.py:

- `_python_packages()` now includes `direct_url.json` for editable installs — more complete package identity.
- `_numpy_show_config()` prefers `np.show_config(mode="dicts")` (structured output, available since NumPy 2.0) with fallback to the legacy string capture.
- `_cuda_toolkit_version()`: tries torch.version.cuda, CUDA_HOME/version.txt, and nvcc --version in order.
- `_visible_gpu_mapping()`: captures CUDA_VISIBLE_DEVICES mapping.
- `_GpuMemorySampler.stop()` calls `_cleanup()` (resource cleanup fix).

### Code quality

Good defensive coding — multiple fallbacks for CUDA version detection, exception handling throughout. The preference for `np.show_config(mode="dicts")` is the right choice (structured, machine-readable).

---

## Supercommit 19 — 2026-04-27 18:15:56 — Environment Freshness Tokens

**Commits:**
- `[seamless-transformer]` Strengthen environment freshness tokens

### Feature coverage

Improvement to environment freshness token construction:

- Was: `conda_meta_mtime_ns` (mtime of the conda-meta directory itself).
- Now: `conda_history_mtime_ns` (mtime of conda-meta/history, changes on every install/remove) + `purelib_mtime_ns` (mtime of site-packages directory, changes on pip install).
- Non-conda Python prefix: adds `purelib_mtime_ns`.

This is a better staleness signal: conda-meta directory mtime doesn't change reliably on all operations; conda-meta/history does.

### Code quality

Good change. Helper renamed from `_conda_meta_mtime_ns` to `_path_mtime_ns` (generalized). Token keys renamed accordingly in the freshness dict — this is a breaking change for any existing probe-index entries using the old key name, which forces a re-probe. Correct behavior.

---

## Supercommit 20 — 2026-04-27 18:18:58-19:55 — Worker Freshness + GPU Inventory

**Commits:**
- `[seamless-dask]` Carry worker freshness into Dask records
- `[seamless-jobserver]` Return worker freshness from jobserver
- `[seamless-remote]` Assert parsed worker freshness payloads
- `[seamless-transformer]` Record worker freshness diagnostics
- `[seamless-transformer]` Capture node GPU inventory

### Feature coverage

Worker freshness diagnostics (Section 11.4 candidate check #6):

- `_process_create_time_epoch()` via psutil: more accurate process start time than the module import timestamp.
- `build_validation_snapshot_checksum()` now includes `process_started_at`, `process_create_time_epoch`, `worker_execution_index`, and derived `worker_fresh_process` (True if index==1, meaning first job in this process).
- `_node_gpu_inventory()` via pynvml: GPU model, UUID, memory, compute capability, ECC mode, persistence mode for each GPU in the node bucket.

### Code quality

Good. `worker_fresh_process = worker_execution_index == 1` is a clean way to flag first-execution state. psutil dependency for `_process_create_time_epoch` is correctly guarded with try/except.

The GPU inventory in pynvml uses getattr for optional methods (`nvmlDeviceGetCudaComputeCapability`, `nvmlDeviceGetEccMode`, `nvmlDeviceGetPersistenceMode`) — defensive and correct since pynvml versions differ.

**Minor:** `_process_create_time_epoch()` is defined identically in both `transformation_cache.py` and `jobserver.py`. Same duplication pattern as `_memory_peak_bytes()`.

---

## Supercommit 21 — 2026-04-27 19:20:16 — Node Probe System Facts

**Commits:**
- `[seamless-transformer]` Capture node probe system facts

### Feature coverage

Node bucket payload (Section 7.1):

- `_cpuinfo_summary()`: reads `/proc/cpuinfo`, extracts model_name, microcode, CPU flags.
- `_numa_topology()`: reads `/sys/devices/system/node/node*/cpulist`.
- `_os_release()`: reads `/etc/os-release`.
- These feed into the `node` bucket payload.

### Code quality

All reads are defensive (try/except, None returns). Parsing is minimal — just what the spec requires. The code correctly handles the case where these paths don't exist (non-Linux).

---

## Supercommit 22 — 2026-04-27 19:57:36 — Final Validation Coverage + Closure Checklist

**Commits:**
- `[seamless-dask]` Pass probe context into Dask record validation
- `[seamless-jobserver]` Pass probe context into jobserver validation
- `[seamless-transformer]` Complete execution record validation coverage
- `[seamless]` Add execution records closure checklist

### Feature coverage

Final wiring:

- `collect_job_validation()` now receives `probe_context` — allowing it to know which conda prefix is active (from the environment bucket) and use it for more accurate allowlist checks.
- `probe_capture.py`: large additions for environment-bucket contract analysis (LD_LIBRARY_PATH/LD_PRELOAD checks at probe time). Adds `_split_path_like`, `_split_preload`, `_normalize_path`, `_stable_digest` helpers. These enable the environment bucket to set `contract_violations` for LD_LIBRARY_PATH/LD_PRELOAD escapes at probe time.
- Closure checklist: a single-line empty file (just the heading `# Execution Records Remaining Checklist`). The checklist content is absent.

### Code quality

The probe_capture additions are well-structured. `_split_preload` correctly handles both space and colon separators per LD_PRELOAD conventions. Path normalization via `realpath` is appropriate.

**Issue:** The closure checklist file is empty (only a heading). This is either a placeholder or an incomplete commit.

---

## Cross-Cutting Observations

### Feature coverage vs. spec

All phases are substantially implemented:
- ✅ Phase 1: Database storage with full round-trip, conflict detection, irreproducible migration
- ✅ Phase 2: `record`, `--node`, `seamless-probe`, `seamless-probe --force`
- ✅ Phase 3: All 5 bucket builders, freshness tokens, label constructors, missing/stale detection, probe registration
- ✅ Phase 4: Pre-execution hard failures for missing/stale buckets, wired into all three backends
- ✅ Phase 5: Full record assembly with all schema fields populated
- ✅ Phase 6: v1 native-linkage contract (`rpath`, `runpath`, `LD_LIBRARY_PATH`), cached by compiled-module digest, validation snapshots
- ⬜ Phase 7: `get_execution_record` / `get_irreproducible_records` exist in seamless-remote but no CLI query helpers

**Not implemented (correctly deferred):** failed-job records, full per-job ldd logs, public operator knobs for snapshot mode, public audit CLI.

### Gaps requiring verification

1. **Phase 7 query CLI absent**: The spec lists "optional CLI in `seamless-transformer`" as a Phase 7 deliverable. The remote-level API functions (`get_execution_record`, `get_irreproducible_records`) are present, but no user-facing CLI command was added. The word "optional" in the spec leaves this ambiguous, but it is not implemented.

2. **`native_link_outside_conda_prefix` violation code not confirmed**: The spec's primary v1 violation code is `native_link_outside_conda_prefix` — triggered when a *resolved* (not just declared) non-allowlisted native library lies outside the conda prefix. SC12 implements `rpath_outside_conda_prefix`, `runpath_outside_conda_prefix`, and `ld_library_path_outside_conda_prefix` (all declaration/environment checks via `readelf -d` and env var inspection), but it is not confirmed that actual library resolution (checking where the dynamic linker would find each dependency) is implemented anywhere. If `native_link_outside_conda_prefix` is not generated by any code path, the test matrix item "compiled transformer linking outside the conda prefix produces `native_link_outside_conda_prefix`" is also unmet.

3. **`spawn` execution path not covered**: The spec test matrix requires "successful record creation in `spawn`". The `spawn` mode routes through `worker.py::_execute_transformation_impl`, a different code path from local `process` execution. The diffs reviewed cover `process` (via `transformation_cache.py`) and `remote` (jobserver + dask) paths, but no changes to `worker.py` appear in any commit, and no test for the `spawn` record path was found. It is unclear whether the `spawn` path inherits record writing automatically or requires its own wiring.

### Code organization issues

1. **Duplicate utility functions**: `_resolve_remote_target()`, `_utcnow_iso()`, `_memory_peak_bytes()`, `_process_create_time_epoch()` are each defined 2-3 times across `transformation_cache.py`, `dask/client.py`, and `jobserver.py`. A shared `seamless_transformer.record_utils` module would eliminate this.

   Line counts per copy:
   - `_utcnow_iso()`: 6 lines × 3 copies (`transformation_cache.py`, `jobserver.py`, `dask/client.py`)
   - `_memory_peak_bytes()`: 13 lines × 2 copies (`transformation_cache.py`, `jobserver.py`)
   - `_process_create_time_epoch()`: 11 lines × 2 copies (`transformation_cache.py`, `jobserver.py`)
   - `_resolve_remote_target()`: 15 lines (`transformation_cache.py`) + 12 lines (`probe_index.py`) = 2 copies

   Total duplicated lines: 6×2 + 13 + 11 + 12 = 48 lines that could be consolidated.

2. **Module-level binding in probe_index.py**: `database_remote` is bound at import time. This is fragile if the remote is configured after import.

3. **Silent exception swallowing in dask path**: The entire record-writing block in `_promise_and_write_result_async` is inside `except Exception: return`. In `record: true` mode, this can silently discard real errors, contradicting the strict intent of that mode.

4. **`transformation_cache.py` growth**: This file has grown substantially (the build_execution_record, load_bucket_contract_violations, build_compilation_context_checksum, compute_record_io_bytes, build_validation_snapshot_checksum, collect_job_validation, collect_compilation_runtime_metadata, _GpuMemorySampler, and all their helpers). Record-specific logic could be extracted into a dedicated `record_assembly.py` module to keep transformation_cache.py focused on cache logic.

5. **`build_compilation_context_checksum()` not cached by digest at the call-site level**: The hashserver deduplicates storage (content-addressing), but compiler subprocess calls are repeated per record-writing call for the same compiled transformer.
