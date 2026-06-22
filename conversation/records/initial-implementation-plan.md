# Plan: Seamless Execution Records Implementation Document

## Context

Seamless caching rests on an optimistic null hypothesis: same transformation identity implies same result, regardless of execution environment. Execution records make this null **falsifiable** by recording the environmental context of each successful execution.

The design has been through several iterations:

1. **Flat design** (`execution-records-design.md`) — five content-addressed environment legs
2. **AI critiques** (Claude, Codex) — identified critical gaps: compiled transformer context, FPU/MXCSR, bash ambient env, tool provenance, container identity, GPU details, worker state
3. **Bucket design** (`bucket-recording.md`) — five manually-probed buckets: Node, Environment, Node×Env, Queue, Queue×Node
4. **Discussion** (`bucket-recording-discussion.md`) — forward-looking framing, contract-based native linkage, per-job cheap validators (pass/fail only), ldd/readelf as contract validation, verbose baseline mode
5. **Database storage** (`execution-record-storage.md`) — MetaData schema change, PUT/GET protocol, protocol 2.1. Already designed, not yet implemented.

The user wants a **consolidated implementation document** that synthesizes all of this into a single actionable specification.

## Key design decisions from discussion with user

### Probe launch mechanism

`seamless-probe` is **syntactic sugar for `seamless-run`**. It runs a named probe script (e.g., `seamless-probe node`) via `seamless-run probe-script.py`, routed to a queue/node through the standard `seamless.profile.yaml` mechanism. This means:

- Probes go through the exact same execution path as real transformations (probe-actual equivalence by construction)
- A **timestamp nonce** is automatically injected into every probe job's transformation inputs, giving it a unique `tf_checksum` so it never hits the transformation cache
- The probe result (the captured bucket dict) is content-checksummed separately from the nonce — the bucket identity is the checksum of the captured content, not of the probe transformation
- All five buckets are captured via `seamless-probe` (no separate local-only capture path)

### Node targeting

A `--node` flag is added to `seamless-run` (and thus available to `seamless-probe`). This propagates through `seamless-dask/wrapper.py` to the scheduler:

- SLURM: `--nodelist <node>`
- OAR: `-p "host='<node>'"`

This is needed so Bucket 1 (Node), Bucket 3 (Node×Env), and Bucket 5 (Queue×Node) probes can target specific nodes.

### Record mode

Record mode is a new setting in `seamless.yaml`, explicitly opted into (e.g., `record: true`). When active:

- Every successful transformation must produce an execution record
- All required bucket checksums must already exist in the probe cache for the execution context (correct node, environment, queue combination)
- If any required bucket is **missing**, the job **fails** — not proceeds with a partial record
- This makes probing a prerequisite step in cluster/environment setup, not an afterthought

When record mode is inactive (the default), no execution records are produced and no bucket probes are required.

## What to produce

A single markdown file at `seamless/conversation/records/execution-records-implementation.md`, alongside the existing design and critique documents.

### A. Final Record Shape

- Per-job JSON body with 5 bucket checksums, per-transformation fields (compilation_context, execution_envelope), per-job scalars (timestamps, resources, worker context), and contract validation result
- `checksum_fields` convention, `schema_version`

### B. Bucket Probe System

- `seamless-probe` as syntactic sugar for `seamless-run` with automatic timestamp nonce
- `--node` flag on `seamless-run`, propagated through `seamless-dask/wrapper.py` to scheduler
- Routing via `seamless.profile.yaml` (same as normal jobs)
- Storage: plain-celltype serialized buffers in hashserver, checksums in local probe cache
- Probe-actual equivalence constraints (excluded ephemeral values)
- Staleness tokens (boot_id, conda_meta_mtime) — stale bucket → job error
- Per-bucket field tables (consolidated from bucket-recording.md + critique additions)
- Bucket 4 (Queue) field enumeration from clusters.yaml structure

### C. Record Mode

- New `record: true` setting in `seamless.yaml`
- Strict enforcement: all required buckets must exist before jobs execute
- Missing bucket → job fails (error, not partial record)
- Stale bucket → job fails (error); staleness detected via per-bucket tokens:
  - Bucket 1 (Node): `boot_id` from `/proc/sys/kernel/random/boot_id`
  - Bucket 2 (Environment): `conda_meta_mtime` (mtime of `$CONDA_PREFIX/conda-meta/history`), `site_packages_mtime` (mtime of `sysconfig.get_path('purelib')`)
  - Bucket 3 (Node×Env): stale if either Bucket 1 or Bucket 2 is stale
  - Bucket 4 (Queue): (depends on queue config enumeration — TBD)
  - Bucket 5 (Queue×Node): stale if either Bucket 1 or Bucket 4 is stale
- Which buckets are required for which execution modes (local vs remote, with/without queue)

### D. Per-Job Capture Path

- Worker-side capture wrapping `run_transformation_dict()` in worker.py
- Four call sites: worker child process, jobserver, dask worker, local in-process
- Pre-execution: timestamp, rusage baseline, bucket lookup + existence check (fail if missing in record mode)
- Post-execution: timing deltas, memory peak, compilation_context for compiled transformers
- Record flows back with the result via IPC; database write via `set_execution_record()`

### E. Per-Job Contract Validators

#### E.1. Architecture

Contract validation runs per-job in the worker process, only when record mode is active. It wraps `run_transformation_dict()`:

1. **Pre-execution** (before `run_transformation_dict()`): bucket existence check (fatal), staleness check (fatal), then pre-execution validators (non-fatal).
2. **Post-execution** (after successful return): post-execution validators (non-fatal).

#### E.2. Policy

- **Uniform severity.** No distinction between "determinant-class escape" and "semantic correctness" validators — all violations are treated identically. The optimistic null hypothesis is either supported or it isn't; gradations add complexity without value.
- **Non-fatal.** Contract violation tags the execution record; the job succeeds normally.
- **Cache-transparent.** Violated-contract results enter the transformation cache and serve future cache hits. The cache key is the transformation identity; the contract violation is evidence about the environment, not the computation.
- **Distinct from staleness/missing.** Stale or missing buckets are pre-conditions that fail the job before execution begins. Contract validators run after those pre-conditions pass.

#### E.3. Declared Roots

Root-checking validators (V2, V3, V4, V6, V9, V10) compare filesystem paths against "declared roots" — the set of locations from which executable code and libraries may legitimately originate.

| Root | Source | Always present |
|------|--------|---------------|
| Environment prefix | `$CONDA_PREFIX` or `sys.prefix` | Yes |
| System ABI | `/lib`, `/lib64`, `/usr/lib`, `/usr/lib64`, arch-specific subdirs (e.g. `/usr/lib/x86_64-linux-gnu`) | Yes |
| GPU driver | Directory containing `libcuda.so` / `libnvidia-*.so` (from Bucket 1 or auto-detected) | Only if GPU present |
| User-declared native roots | `record.native_roots` list in `seamless.yaml` | No (opt-in) |
| Runner temp directories | Seamless-controlled work/build dirs | Yes (for compiled `.so`, temp files) |

For **PATH validation** (V2), declared bin roots are derived: `{root}/bin` and `{root}/sbin` for each declared root, plus `/usr/bin`, `/bin`, `/usr/sbin`, `/sbin`.

#### E.4. Validator Specifications

**V1: `env_hash` — Determinism-relevant environment variables**

- Phase: pre-execution
- Scope: all transformation types
- Reads: `os.environ` subset — the following variables (absent → null):
  ```
  PATH, LD_LIBRARY_PATH, LD_PRELOAD, PYTHONPATH, PYTHONHASHSEED,
  LC_ALL, LC_NUMERIC, LC_COLLATE, LANG, TZ,
  OMP_NUM_THREADS, OMP_SCHEDULE, OMP_PROC_BIND, OMP_PLACES,
  GOMP_SPINCOUNT, GOMP_CPU_AFFINITY, KMP_AFFINITY,
  MKL_NUM_THREADS, MKL_DYNAMIC, OPENBLAS_NUM_THREADS,
  CUBLAS_WORKSPACE_CONFIG, TF_DETERMINISTIC_OPS,
  PYTORCH_CUDA_ALLOC_CONF, CUDA_LAUNCH_BLOCKING
  ```
- Expected: hash from the bucket probe's capture of the same variable set (union of Bucket 2 + Bucket 5 env var fields). Since staleness checks have already passed, the bucket values are known-fresh.
- Method: build dict `{var: value_or_null}` from the var list, serialize via `orjson.dumps(option=OPT_SORT_KEYS)`, SHA-256 the bytes. Compare against the same hash computed from the bucket contents.
- Violation code: `ENV_HASH_MISMATCH`
- Cost: <1ms

**V2: `path_roots` — PATH components within declared roots**

- Phase: pre-execution
- Scope: all (critical for bash transformations)
- Reads: `os.environ['PATH']`
- Method: split on `:`, for each component check `any(component.startswith(root) for root in declared_bin_roots)`. Empty/absent PATH passes.
- Violation code: `PATH_OUTSIDE_DECLARED_ROOTS`
- Cost: <1ms

**V3: `ld_paths` — Dynamic linker search paths within declared roots**

- Phase: pre-execution
- Scope: all
- Reads: `os.environ.get('LD_LIBRARY_PATH', '')`, `os.environ.get('LD_PRELOAD', '')`
- Method: split LD_LIBRARY_PATH on `:`, LD_PRELOAD on whitespace or `:`. Each entry must be under a declared root, or the variable must be empty/unset.
- Violation codes: `LD_LIBRARY_PATH_OUTSIDE_DECLARED_ROOTS`, `LD_PRELOAD_OUTSIDE_DECLARED_ROOTS`
- Cost: <1ms

**V4: `sys_path` — Python import path within declared roots**

- Phase: pre-execution
- Scope: Python transformations only (skip for bash/compiled-only)
- Reads: `sys.path`
- Method: iterate `sys.path`, check each entry against declared roots (env prefix site-packages, stdlib dirs, runner temp dirs). Empty strings (cwd marker) pass.
- Violation code: `SYSPATH_OUTSIDE_DECLARED_ROOTS`
- Cost: <1ms

**V5: `cwd_umask` — Working directory and permission mask**

- Phase: pre-execution
- Scope: all
- Reads: `os.getcwd()`, umask via `old = os.umask(0); os.umask(old)`
- Expected: cwd is the runner-controlled work directory; umask matches the expected value (from the worker's initialization)
- Violation codes: `CWD_UNEXPECTED`, `UMASK_UNEXPECTED`
- Cost: <1ms

**V6: `mountinfo` — Filesystem mount policy**

- Phase: pre-execution
- Scope: all (most relevant in container/cluster contexts)
- Reads: `/proc/self/mountinfo`
- Method: parse each line (fields: mount_id, parent_id, major:minor, root, mount_point, mount_options, ..., fs_type, mount_source, super_options). Flag writable (`rw` in mount_options) bind mounts that overlay executable/library roots from undeclared sources.
- Violation code: `MOUNT_POLICY_VIOLATION`
- Cost: ~1ms

**V7: `worker_freshness` — Worker process reuse state**

- Phase: pre-execution
- Scope: spawn, jobserver, daskserver backends (skip for `process` — fresh by construction)
- Reads: worker execution counter (tracked by WorkerManager), worker PID, process start time (`psutil.Process().create_time()`)
- Method: WorkerManager tracks an execution counter per worker. At worker startup, record a baseline hash of `sys.modules` keys. Before each job, compare current `sys.modules` key hash against baseline. Also report execution counter and process age.
- Violation code: `WORKER_STATE_DRIFT`
- Cost: <1ms (sys.modules key hashing is ~0.1ms for typical module sets)

**V8: `gpu_policy` — GPU device configuration**

- Phase: pre-execution
- Scope: GPU transformations only (skip if `__gpu__` not in transformation envelope)
- Reads: `CUDA_VISIBLE_DEVICES`, pynvml queries (`nvmlDeviceGetCount`, `nvmlDeviceGetUUID`, `nvmlDeviceGetEccMode`, `nvmlDeviceGetComputeMode`)
- Expected: visible device count and UUIDs match the Bucket 5 (Queue×Node) GPU config; ECC/compute mode match Bucket 1 (Node)
- Violation code: `GPU_POLICY_VIOLATION`
- Cost: ~5ms (after pynvml initialization; pynvml init itself ~50ms but done once per worker lifetime)

**V9: `proc_maps` — Loaded library provenance**

- Phase: **post-execution** (captures libraries lazily loaded during the transformation)
- Scope: all
- Reads: `/proc/self/maps`
- Method: parse each line, filter for executable regions (`r-xp` permissions) with file paths. Extract unique file paths. Check each against declared roots. Exclude `[vdso]`, `[vsyscall]`, anonymous mappings.
- Violation code: `LOADED_LIB_OUTSIDE_DECLARED_ROOTS`
- Cost: 1–10ms (depends on mapping count; typically ~200–500 entries)

**V10: `readelf_compiled` — Compiled artifact linkage**

- Phase: post-compilation, **cached by `.so` content checksum**
- Scope: compiled transformations only
- Reads: the compiled `.so` file via `readelf -d`
- Method: run `readelf -d <.so>`, parse output lines for `DT_NEEDED`, `RPATH`, `RUNPATH`. Check that RPATH/RUNPATH entries are under declared roots. Cache the validation result keyed by SHA-256 of the `.so` file — subsequent jobs reusing the same `.so` get the cached result without re-running readelf.
- Violation code: `COMPILED_LINKAGE_OUTSIDE_DECLARED_ROOTS`
- Cost: 2–20ms per artifact; amortized to ~0 for reused artifacts

#### E.5. Storage

Per-job execution record fields for contract validation:

On pass:
```json
{
  "contract": "v1",
  "contract_ok": true
}
```

On violation:
```json
{
  "contract": "v1",
  "contract_ok": false,
  "violations": ["ENV_HASH_MISMATCH", "PATH_OUTSIDE_DECLARED_ROOTS"]
}
```

No bulky details stored for passing validators. On violation, only the violation codes are stored — no payloads.

#### E.6. Verbose Baseline Mode

For the first N jobs (configurable, default 5) per unique bucket-configuration tuple `(bucket_1, bucket_2, bucket_3, bucket_4, bucket_5)`, store a full validation snapshot:

- The env var dict used for V1
- Full PATH / LD_LIBRARY_PATH / sys.path lists (V2–V4)
- Full `/proc/self/maps` parsed output (V9)
- Full `readelf -d` output for compiled artifacts (V10)

The snapshot is serialized via Seamless plain celltype, checksummed, and stored as a buffer in the hashserver. The execution record carries a `validation_detail_checksum` field pointing to it. After N jobs with the same bucket tuple, this field is omitted and only `contract_ok` + violation codes are stored.

Counter is per-worker-process (not global) — avoids NFS coordination overhead. Restarting workers resets the counter, which is acceptable (more baselines is not harmful).

### F. Database Storage

- Reference to `execution-record-storage.md` (already designed)
- MetaData schema, PUT/GET protocol, IrreproducibleTransformation migration

### G. Implementation Phases

1. Database storage layer (execution-record-storage.md)
2. `--node` flag in `seamless-run` + `seamless-dask/wrapper.py` node targeting support
3. Bucket probe scripts + `seamless-probe` CLI wrapper
4. Record mode config in `seamless.yaml` + bucket existence enforcement
5. Per-job capture path integration into worker.py/run.py/jobserver.py
6. Contract validators
7. CLI for querying records

### H. Package Dependencies

- psutil (required for capture), nvidia-ml-py3 (optional), threadpoolctl (optional)
- All in seamless-transformer optional extras

### I. Open Questions

- ~~Exact contract policy defaults and declared roots~~ → resolved in E.2–E.3
- Per-transformation Docker image digest placement
- Bash tool provenance (deferred to opt-in feature)
- ~~Verbose baseline counter persistence on shared NFS~~ → resolved: per-worker-process counter, no NFS coordination (E.6)
- Which buckets are required per execution mode (e.g., local `process` mode: do Queue/Queue×Node buckets apply?)
- Bucket 4 (Queue) field enumeration and staleness token (C)

## Key source files referenced

- `seamless-database/database_models.py` — MetaData model (line 128), db_init (line 171)
- `seamless-database/database.py` — PUT metadata (line 679), PUT irreproducible (line 687)
- `seamless-database/execution-record-storage.md` — database layer design
- `seamless-transformer/seamless_transformer/run.py` — run_transformation_dict (line 81), commented-out legacy capture (line 93)
- `seamless-transformer/seamless_transformer/worker.py` — _execute_transformation_impl (line 616), _WorkerManager (line 737)
- `seamless-transformer/seamless_transformer/execute_bash.py` — os.environ.copy() → Popen
- `seamless-transformer/seamless_transformer/compiler/compile.py` — compiler invocation
- `seamless-core/seamless/checksum/json_.py` — json_dumps_bytes with orjson (canonical serialization)
- `seamless-dask/seamless_dask/worker_setup.py` — SeamlessWorkerPlugin.setup()
- `seamless-dask/seamless_dask/wrapper.py` — Dask cluster launcher, WrapperConfig, node targeting needed here
- `seamless-jobserver/jobserver.py` — _run_transformation handler
- `seamless-remote/seamless_remote/database_client.py` — remote client methods
- `seamless-cluster-config/config/*.yaml` — cluster/queue definitions

## Approach

Write the document at `seamless/conversation/records/execution-records-implementation.md`. It should:

- Be self-contained (not require reading the 7 prior design/critique documents)
- Reference the prior documents where relevant (not repeat them verbatim)
- Be precise enough that a developer can implement from it
- Include the consolidated record shape
- Include the per-bucket field tables
- Include the validator list with costs and sources
- Specify the phased implementation plan with file paths
- Reflect the probe-via-seamless-run, --node flag, and record mode decisions
