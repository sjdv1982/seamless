# New Code Paths Triggered When record_mode=False

Scope: code added by the implementation commits (Apr 26–27) that executes during normal
Seamless operation when `record: false` (the default). Test files are excluded.

Classifications:
- **yes** — executes unconditionally, or conditionally on something independent of record_mode
  that is true in the normal/default case
- **potential** — executes only under a specific runtime condition (compiled transformer,
  GPU present, dask backend, jobserver backend, etc.)

"yes" paths that sit inside a larger "yes" block but have their own internal condition
are split out individually.

---

## seamless-transformer: transformation_cache.py

**Process: seamless-transformer**

### Module load (once per process) — yes

| Lines | What |
|-------|------|
| 7 | `from datetime import datetime, timezone` — new import |
| 14 | `import resource` — new import |
| 21 | `import threading` — new import |
| 22 | `import time` — new import |
| 27 | `from .probe_index import ensure_record_bucket_preconditions, is_record_probe` — loads entire probe_index module |
| 35–43 | Extended `seamless_config.select` import: adds `check_remote_redundancy`, `get_node`, `get_queue`, `get_record`, `get_remote` |
| 73 | `_PROCESS_STARTED_AT = datetime.now(timezone.utc)` — evaluated at process start |
| 74 | `_EXECUTION_RECORD_COUNTER = itertools.count(1)` — evaluated at process start |
| 75 | `_VALIDATION_SNAPSHOT_COUNTS: dict[tuple, int] = {}` |
| 76 | `_COMPILED_VALIDATION_CACHE: dict[str, dict[str, Any]] = {}` |

### Per-transformation (every call to `TransformationCache.run()`) — yes

| Lines | What |
|-------|------|
| 1476 | `record_mode = bool(get_record())` — one `get_record()` call per transformation |
| 1522 | `record_probe = is_record_probe(transformation_dict, tf_dunder)` — two `dict.get()` calls |
| 1530 | `remote_target = _resolve_remote_target(execution)` — one function call |
| 1539 | `started_at = _utcnow_iso()` — `datetime.now()` call |
| 1540 | `wall_start = time.perf_counter()` |
| 1541 | `cpu_start = os.times()` |
| 1542–1546 | Four `None` assignments (`probe_context`, `compilation_context`, `job_validation_payload`, `runtime_metadata`, `gpu_memory_peak_bytes`) |
| 1647 | `finished_at = _utcnow_iso()` — after execution |
| 1648 | `wall_time_seconds = round(time.perf_counter() - wall_start, 6)` |
| 1649 | `cpu_end = os.times()` |
| 1650 | `cpu_user_seconds = round(cpu_end.user - cpu_start.user, 6)` |
| 1651 | `cpu_system_seconds = round(cpu_end.system - cpu_start.system, 6)` |
| 1652 | `if isinstance(runtime_metadata, dict):` — evaluates to False (runtime_metadata=None); inner block skipped |

### Per-transformation, in-process execution only — potential

(Only when `execution == "process"`, i.e. no dask/jobserver remote configured)

| Lines | What |
|-------|------|
| 1629 | `gpu_sampler = start_gpu_memory_sampler()` — tries to import pynvml; returns None immediately if not installed |
| 1630–1640 | try/finally wrapper around `run_in_executor` call (was a bare `await` before) |
| 1641 | `gpu_memory_peak_bytes = stop_gpu_memory_sampler(gpu_sampler)` — no-op if sampler is None |

---

## seamless-transformer: run.py

**Process: seamless-transformer** (in-process execution path only, called via executor thread)

### Module load — yes

| Lines | What |
|-------|------|
| 28 | `from .probe_index import ensure_record_bucket_preconditions_sync, is_record_probe` |

### Per in-process transformation call — yes

| Lines | What |
|-------|------|
| 135 | `if not is_record_probe(transformation, tf_dunder):` — two `dict.get()` calls |
| 136 | `ensure_record_bucket_preconditions_sync(transformation, tf_dunder)` — always called (see below) |

`ensure_record_bucket_preconditions_sync` (probe_index.py:310–345) is called on every
non-probe in-process transformation. Since `run.py` runs in an executor thread (no running
event loop), the sync wrapper calls `asyncio.run()`, which creates and tears down a new event
loop. Inside, `ensure_record_bucket_preconditions` immediately returns `None` at line 223
because `get_record()` is False. The net result is asyncio event-loop creation overhead per
in-process transformation.

---

## seamless-transformer: probe_index.py (new file)

**Process: seamless-transformer and seamless-jobserver**

Imported at module load of `transformation_cache.py` (line 27) and `run.py` (line 28) and
`jobserver.py` (lines 17–20). All module-level code runs once per process.

### Module load — yes

| Lines | What |
|-------|------|
| 1–31 | Standard library and project imports |
| 34 | `class RecordBucketError` definition |
| 38 | `RECORD_PROBE_DUNDER = "__record_probe__"` constant |
| 41–50 | `is_record_probe()` function definition |
| 53–64 | `_resolve_remote_target()` function definition |
| 66–209 | `resolve_probe_plan()` and helpers — defined but not called without record_mode |
| 216–345 | `ensure_record_bucket_preconditions()` and `ensure_record_bucket_preconditions_sync()` — defined |

`ensure_record_bucket_preconditions()` (line 216) returns `None` at line 223 immediately
when `get_record()` is False, so its body never executes even though the sync wrapper
spawns `asyncio.run()` to call it.

---

## seamless-transformer: pretransformation.py

**Process: seamless-transformer**

### Per-transformation checksum computation — yes

| Line | What |
|------|------|
| 23 | `"__record_probe__"` added to `NON_CHECKSUM_ITEMS` tuple — one extra string comparison when filtering dunder keys before checksum computation |

---

## seamless-transformer: transformation_utils.py

**Process: seamless-transformer**

### Module load — yes

| Line | What |
|------|------|
| 17 | `"__record_probe__"` added to `TRANSFORMATION_EXECUTION_DUNDER_KEYS` set |

---

## seamless-transformer: compiler/__init__.py

**Process: seamless-transformer** (compiled transformations only)

### Module load — yes

| Line | What |
|------|------|
| 24 | `_MODULE_INFO_CACHE: dict[str, dict[str, Any]] = {}` — new process-level cache dict |

### Per compiled-transformer invocation — potential

| Lines | What |
|-------|------|
| 52 | `build_compiled_module()` now delegates to `get_compiled_module_info()` and extracts `["module"]` — adds one dict allocation and one key lookup per call (cache hit or miss) |
| 56–91 | `get_compiled_module_info()` builds and caches an info dict; on cache miss, records `compilation_time_seconds` via `time.perf_counter()` |

---

## seamless-dask: client.py

**Process: seamless-dask worker**

### Module load — yes

| Lines | What |
|-------|------|
| 67–70 | `_utcnow_iso()` function definition |

### Per Dask transformation (_run_base) — yes

| Lines | What |
|-------|------|
| 656 | `started_at = _utcnow_iso()` |
| 657 | `wall_start = time.perf_counter()` |
| 658 | `cpu_start = os.times()` |
| 659 | `gpu_memory_peak_bytes = None` |
| 804 | `finished_at = _utcnow_iso()` |
| 805 | `wall_time_seconds = round(time.perf_counter() - wall_start, 6)` |
| 806 | `cpu_end = os.times()` |
| 807 | `cpu_user_seconds = round(cpu_end.user - cpu_start.user, 6)` |
| 808 | `cpu_system_seconds = round(cpu_end.system - cpu_start.system, 6)` |
| 809–827 | Extra keyword arguments passed to `_promise_and_write_result_async` (timing values, transformation_dict, tf_dunder, scratch) — always passed, but inside the function only used when `get_record()` is True |

### Per Dask worker dispatch (not cache hits) — potential

| Lines | What |
|-------|------|
| 759 | `from seamless_transformer.transformation_cache import start_gpu_memory_sampler, stop_gpu_memory_sampler` — lazy import per call (cached by Python after first import) |
| 764 | `gpu_sampler = start_gpu_memory_sampler()` |
| 765–775 | try/finally wrapper around worker dispatch |
| 777 | `gpu_memory_peak_bytes = stop_gpu_memory_sampler(gpu_sampler)` |

---

## seamless-dask: transformation_mixin.py

**Process: seamless-dask worker**

### In `_remote_storage_error()` — potential

Called when the dask mixin checks whether remote storage is configured. When
`record_mode=False` and `execution != "remote"`, the method returns `None` immediately
after the new guard (same result as before, one extra `get_record()` call).

| Lines | What |
|-------|------|
| ~83 | `record_mode = bool(get_record())` — new: evaluated before the early-return check |
| ~84 | `if execution != "remote" and not record_mode: return None` — early return condition broadened; when record_mode=False and execution!="remote", returns at same point as before |

(Exact lines depend on current file; the logic is in the modified `_remote_storage_error` body.)

---

## seamless-jobserver: jobserver.py

**Process: seamless-jobserver**

### Module load / process startup — yes

| Lines | What |
|-------|------|
| 4 | `from datetime import datetime, timezone` — new import |
| 8 | `import resource` — new import |
| 17–20 | `from seamless_transformer.probe_index import ensure_record_bucket_preconditions, is_record_probe` — loads probe_index module |
| 24 | `from seamless_config.select import get_record` |
| 41 | `_PROCESS_STARTED_AT = datetime.now(timezone.utc)` — captured at process start |
| 42 | `_EXECUTION_RECORD_COUNTER = 0` |
| 45–48 | `_utcnow_iso()` definition |
| 51–52 | `_process_started_at_iso()` definition |
| 55–65 | `_memory_peak_bytes()` definition |
| 68–76 | `_process_create_time_epoch()` definition |
| 79–82 | `_next_execution_record_index()` definition |

### Per transformation handled by jobserver — yes

| Lines | What |
|-------|------|
| 302 | `started_at = _utcnow_iso()` |
| 303 | `wall_start = time.perf_counter()` |
| 304 | `cpu_start = os.times()` |
| 305–308 | Lazy import of `start_gpu_memory_sampler`, `stop_gpu_memory_sampler` (cached after first call) |
| 310 | `gpu_sampler = start_gpu_memory_sampler()` |
| 311 | `gpu_memory_peak_bytes = None` |
| 313 | `retry_count = 0` |
| 356 | `gpu_memory_peak_bytes = stop_gpu_memory_sampler(gpu_sampler)` — in `finally` block |
| 364 | `finished_at = _utcnow_iso()` |
| 365 | `wall_time_seconds = round(time.perf_counter() - wall_start, 6)` |
| 366 | `cpu_end = os.times()` |
| 367 | `cpu_user_seconds = round(cpu_end.user - cpu_start.user, 6)` |
| 368 | `cpu_system_seconds = round(cpu_end.system - cpu_start.system, 6)` |
| 369–384 | Full `record_runtime` dict assembled unconditionally — includes calls to `_memory_peak_bytes()` (line 375), `_process_create_time_epoch()` (line 381), and `_next_execution_record_index()` (line 382, increments global counter) |
| 385 | `record_runtime["gpu_memory_peak_bytes"] = gpu_memory_peak_bytes` |
| 386 | `response_payload = result_checksum.hex()` |

The `record_runtime` dict (lines 369–385) is built and all three helper functions
are called on every successful transformation regardless of record_mode. The dict is
then discarded when `get_record()` is False (line 387 guard is not entered).

---

## seamless-remote: jobserver_client.py

**Process: seamless-transformer** (called when using jobserver remote)

### Per jobserver call — potential

(Only when `execution == "remote"` and `remote_target == "jobserver"`)

| Lines | What |
|-------|------|
| 55–58 | `try: json.loads(result0) except Exception: payload = None` — attempted JSON parse of the plain hex-string response. Raises `json.JSONDecodeError`; caught, payload set to None. One failed parse per jobserver call when record_mode=False |
| 59 | `if isinstance(payload, dict):` — False; inner block skipped |

---

## seamless-config: config_files.py and select.py

**Process: seamless-transformer** (and any process that loads seamless-config)

### Per config-file load — yes

| Code | What |
|------|------|
| `reset_record_before_load()` call in `load_config_files` | Resets `_current_record`, `_record_source`, `_record_command_seen` to defaults |
| `reset_node_before_load()` call in `load_config_files` | Resets `_current_node`, `_node_source` to defaults |

These run once per `seamless-run` invocation during config loading. Each resets a handful of
module-level variables; negligible overhead.

---

## seamless-database: database.py and database_models.py

**Process: seamless-database server**

### Server startup — yes

New routes and schema are always registered/created regardless of whether any client
uses record mode:
- `BucketProbe` ORM model always added to schema
- `MetaData.result` column always present
- `/execution-record/` GET and PUT routes always registered
- `/bucket-probe/` GET and PUT routes always registered

These are one-time startup costs with no per-request overhead unless the endpoints are called
(which requires record_mode=True on the client side).

---

## Summary of notable overhead when record_mode=False

| Where | Per-occurrence cost |
|-------|-------------------|
| `transformation_cache.py`:1476,1522,1530,1539–1546 | ~8 cheap calls per transformation |
| `transformation_cache.py`:1647–1652 | 2× `time.perf_counter()`, 2× `os.times()`, arithmetic per transformation |
| `run.py`:135–136 | `asyncio.run()` (new event loop) per in-process transformation |
| `jobserver.py`:369–385 | `resource.getrusage()`, `psutil.Process().create_time()`, global counter increment per jobserver transformation |
| `jobserver_client.py`:55–58 | Failed JSON parse per jobserver call |
