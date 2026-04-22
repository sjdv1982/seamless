# Post-Transformation Execution Records in `seamless.db`

## Status

Draft design, normal-mode scope. Audit-mode (deliberate re-execution to test the optimistic null) is out of scope for this document and discussed separately.

## Background

`seamless.db` reserves a `MetaData` table for a "post-transformation execution record" — a JSON blob keyed by `tf_checksum`, written after a transformation has executed. The current schema is a placeholder ported from legacy Seamless and matches the legacy shape exactly: `(checksum PRIMARY KEY, metadata JSON)`. The capture path that populates it is currently commented out in `seamless-transformer/seamless_transformer/run.py`.

Legacy Seamless built the record on the driver side via `get_global_info()` in `seamless/workflow/core/transformation.py`, snapshotting the local conda env, host hardware (via `lshw` / `nvidia-smi`), and a few execution stats, then merging them with per-job fields (execution time, success flag, exception). The blob was written via `database.set_metadata(tf_checksum, meta)` after every executed job.

This document specifies what the record should contain in the rewritten architecture, why each field exists, and what design constraints follow.

The scope is deliberately narrow. `seamless.db` is a provenance and evidence substrate for future auditing, not the audit framework itself. Its job is to preserve the execution facts that are hard or impossible to reconstruct later — what transformation ran, what result it produced, and in what execution context it actually ran — so that higher-level audit machinery can be built on top. Audit policy, replay orchestration, witness adequacy, attempt histories, annotations, and final conclusions belong outside `seamless.db`, even if they consume the records defined here. The relevant audit evidence corpus is therefore larger than `seamless.db` alone: it also includes the referenced Seamless buffers in the hashserver / buffer cache, insofar as those buffers are needed for reproduction, witness extraction, or diagnosis.

This document is concerned primarily with **reproducibility audit**: did a transformation that once succeeded remain reproducible under later recomputation or audit replay? It is not primarily about building a general-purpose execution log for all success/failure events. In Seamless, successful executions are the load-bearing case because they produce reusable identities (`tf_checksum`, `result_checksum`) that can later be shared, replayed, and audited.

## Conceptual frame

Seamless caching rests on an **optimistic null hypothesis**: for any given transformation, the scientifically meaningful result is invariant under variation in the execution environment (hardware, numerical libraries, time, host, parallelization details). The cache treats two runs of the same `tf_checksum` as equivalent, regardless of where or when they ran.

The execution record exists to make that null **falsifiable later**, even though the normal cache path never falsifies it. In normal operation, the record is not consulted to serve cache hits — but it is the only artifact preserved across the moment of execution that captures the environmental context. Without it, a future divergence is undiagnosable.

In normal mode, the record additionally serves three concrete purposes that have nothing to do with audit:

1. **Cache lifecycle decisions.** Resource cost (CPU time, memory peak, wall time) feeds eviction policy: keep the result buffer materialized, or evict and rely on fingertipping?
2. **Fingertipping diagnosis.** While fingertipping succeeds, the record is dormant. When it fails — or when null-hypothesis validation triggers a divergence — the entry migrates to the irreproducible cache, where the record becomes a lead for recovering the lost result.
3. **Trust under sharing.** When `seamless.db` is shared between users or labs, the record is the receipt that lets a recipient inspect "in what context was this result produced" without having to trust the publisher unconditionally.

There is no separate "shared provenance" usage. Provenance sharing folds into shared caching/fingertipping, where the operator decides per-share how much to ship. A "give me the provenance for this checksum" query is just a side effect of records being colocated with the data they describe.

## Normal-mode invariants

These are the load-bearing assumptions about how records are produced and consumed:

- **Write-once per `tf_checksum`.** The record is written exactly once, on the first cache-missing successful execution. Every subsequent call to that transformation is a cache hit on the `Transformation` table and never re-enters the metadata path. The table is not "last-write-wins"; it is "single-write." `tf_checksum` as primary key is the natural fit.

- **Successful executions only.** `MetaData` records are for transformations that completed successfully and yielded a `result_checksum`. Failed execution attempts are not the primary subject of this design. They may matter to other operational tooling, but they do not create the durable reusable identity that makes Seamless caching and reproducibility audit meaningful.

- **Worker-side capture.** The record describes the environment in which the transformation **actually ran**, not the environment from which it was submitted. In the legacy implementation, capture happened on the driver via a frozen module-level dict (`execution_metadata0`, `_got_global_info`), which silently produced wrong answers for any job dispatched to a remote worker. In the new architecture, capture must happen on the worker and the record must travel back with the result.

- **Records-as-corpus, not query targets.** The database does not need indexed columns to support reverse queries ("find all rows with `env_checksum = X`"). The intended consumers are (a) the cache eviction policy, which looks up by `tf_checksum`, and (b) human or agent investigators reading whole records when something has gone wrong. Field promotion out of JSON is therefore unnecessary in normal mode. The schema stays minimal.

- **Sharing redaction is policy, not schema.** Fields that look "local" (hostnames, exact timestamps) can become diagnostically load-bearing under failure modes tied to parallelization or node-specific hardware faults. They are not stripped reflexively. Whether to redact on export is decided per share, by the operator, the same way they decide how many buffers to ship — not encoded as a column boundary in the schema.

## What the record contains

A record consists of three categories of fields. All live in the `metadata` JSON blob; no field promotion to columns is proposed.

### 1. Environment signature

The set of axes along which the optimistic null can be tested. Five legs, partitioned into system-side and Seamless-side.

**System-side (large invariant payloads, content-addressed):**

- `hardware` — content-addressed pointer to a structured dict of **stable physical properties only**: CPU model, physical/logical core count, RAM total, GPU model and memory, OS/kernel, container detection. These change rarely (typically only on hardware reseating, kernel update, or node reprovision). Stored as a separate buffer in the buffer store; the record carries only the checksum. Massive deduplication: one buffer per worker class, shared across all jobs that ever run on that hardware.
- `runtime_config` — content-addressed pointer to **variable per-process numerics configuration**: BLAS backend identification (from `numpy.show_config()`), thread pool sizes (from `threadpoolctl.threadpool_info()`), and relevant numerics environment variables (`OMP_NUM_THREADS`, `MKL_NUM_THREADS`, `OPENBLAS_NUM_THREADS`, `OPENBLAS_CORETYPE`, `CUDA_VISIBLE_DEVICES`, `LD_PRELOAD`). **Kept separate from `hardware`** because thread pool sizes and numerics env vars vary per process invocation (set by SLURM allocations, job submission scripts, container entrypoints, user shells). Bundling them into `hardware` would force a new `hardware` checksum for every variation and collapse the deduplication that justified content-addressing in the first place. With the split, `hardware` deduplicates strongly (one buffer per worker class) while `runtime_config` deduplicates more weakly but only along its own axis. The split also isolates two real semantic boundaries: `hardware` is what the operator provisioned, `runtime_config` is what the job invocation chose.
- `python_packages` — content-addressed pointer to a structured dump of every package installed in the current Python environment, obtained from `importlib.metadata.distributions()`. This is the **interpreter's view**: a Python API call (no subprocess), unified across conda and pip installs, present regardless of whether conda is in use. It captures what Python sees, which is what determines the computation.
- `conda_env` — content-addressed pointer to a conda environment dump produced by `conda env export`. **Complementary** to `python_packages`, not a substitute: it is slower and conda-only, but it captures the **C library context** (BLAS implementation, linked numerical libraries, channel and build-string information) that `importlib.metadata` does not see. Captured only when conda is detected on the worker; null otherwise.

Neither package dump alone is complete: `python_packages` sees Python distributions but not the C libraries they link to; `conda_env` sees the conda installation state but misses pip overlays and is unavailable on venv / system Python / uv deployments. Capturing both lets a receiving audit tool degrade gracefully on whichever it has.

**Seamless-side:**

- `seamless_version` — string. Small enough to inline.
- `execution_mode` — string, one of `process | spawn | jobserver | daskserver`. Small scalar; the new-Seamless name for what legacy called the "executor."
- `metavars` — content-addressed pointer to the metavar dict actually applied at run time (`nparallel`, `chunksize`, scheduling hints, etc.). Metavars are by design excluded from the cache key but are in effect at execution time and can be load-bearing for diagnosing parallelization-induced divergences. Typically small dicts, but deduplicated by content addressing for consistency.
- Any other **dunder fields** (`__compilers__`, `__languages__`, future additions) that affect execution but not identity. The exact list is in flux as the new architecture stabilizes; the principle is: any dunder field that is not part of the cache key but is in effect at execution time goes into the record.

**Dunder persistence is not provided by execution records alone.** The execution record may copy or reference the dunder payload that was in effect for the successful run, because those values are audit evidence. But this record is written only after a successful cache-missing execution and is keyed by the normal result entry. Execution-only dunder values that are needed to rerun, audit, or materialize a transformation (`__env__`, `__compilation__`, `__schema__`, `__header__`, `__compilers__`, `__languages__`, and future equivalents) must therefore also be stored by the transformation/replay substrate outside the `MetaData` execution-record body. The record is a receipt of what happened; it is not the sole durable source of the "how to run" envelope.

### 2. Resource accounting (load-bearing for cache eviction)

Per-run scalars used by the cache eviction cost model:

- `cpu_time_seconds`
- `memory_peak_bytes`
- `wall_time_seconds`

These are inline in the JSON blob, not content-addressed (they're tiny and per-run unique).

### 3. Diagnostic context

Fields that are not strictly required for any current normal-mode consumer but preserve enough context to diagnose future divergences. Inline in the JSON blob:

- `started_at`, `finished_at` — wall-clock timestamps
- `hostname` — worker node identity
- Anything else the worker chooses to capture (executor-specific extras, NUMA topology, BLAS thread count, etc.)

These are kept because some failure modes — flaky cluster nodes, parallelization races, NUMA effects — are only diagnosable with this kind of context. Whether they ship across a `seamless.db` export is a per-share decision.

### Witness labels are descriptive metadata only

Some workflows may wish to mark a transformation or one of its outputs as a **witness**: a compact, meaning-bearing artifact that is especially useful for human inspection, regression testing, sharing, or audit tooling. Supporting such a mark is compatible with this design, but only as **descriptive metadata**.

Concretely:

- A `witness` label may be present in transformation metadata and should be preserved by `seamless.db` if present.
- The label is a hint for higher-level tooling, not a schema-level concept with special database semantics.
- Auditing must **not** depend on the presence, correctness, or uniqueness of a `witness` label. Valid audit strategies may be post hoc and external to the original workflow.
- The judgment that "this transformation is marked as a witness" is different from the audit-policy judgment that "this witness is sufficient for this audit question." The first may live in workflow metadata; the second belongs to higher-level audit machinery.

This keeps the separation of concerns clean: `seamless.db` may preserve witness annotations, but it does not define witness policy, witness adequacy, or audit conclusions.

## Schema sketch

The on-disk schema gains one column over the placeholder, so that X's row shape mirrors Y's (`IrreproducibleTransformation`) at the column level:

```python
class MetaData(BaseModel):
    checksum = ChecksumField(primary_key=True)  # tf_checksum
    result = ChecksumField(index=True, unique=False)  # result_checksum
    metadata = JSONField()
```

This means a `MetaData` row carries the same identifying columns (`checksum`, `result`) that an `IrreproducibleTransformation` row already carries, so migration of an entry from X (`MetaData`) to Y (`IrreproducibleTransformation`) is a literal row move at the column level — no manipulation of the JSON body required.

What changes more substantially is the **shape of the JSON blob**. A representative record:

```json
{
  "schema_version": 1,
  "checksum_fields": ["hardware", "runtime_config", "python_packages", "conda_env", "metavars"],

  "tf_checksum":      "<64-hex-checksum>",
  "result_checksum":  "<64-hex-checksum>",

  "hardware":         "<64-hex-checksum>",
  "runtime_config":   "<64-hex-checksum>",
  "python_packages":  "<64-hex-checksum>",
  "conda_env":        "<64-hex-checksum>",
  "metavars":         "<64-hex-checksum>",

  "seamless_version": "0.x.y",
  "execution_mode":   "jobserver",

  "cpu_time_seconds":  12.4,
  "memory_peak_bytes": 1234567890,
  "wall_time_seconds": 13.1,

  "started_at":  "2026-04-15T10:23:00Z",
  "finished_at": "2026-04-15T10:23:13Z",
  "hostname":    "node42.cluster",

  "dunder": {
    "__compilers__": "...",
    "__languages__": "..."
  }
}
```

### The record body is canonical and self-contained

The JSON blob is the **canonical record body**. It carries `tf_checksum`, `result_checksum`, the env signature, and all run-context fields. The schema's columns (`checksum` PK, `result` index) are a **layout convenience for lookup**, not the source of truth — they duplicate data that already lives in the body.

Three things follow from this:

- **X and Y record bodies are identical in shape.** Both `MetaData` rows and `IrreproducibleTransformation` rows wrap the same JSON record body. The only difference is the column-level constraints: X's `checksum` is a unique PK; Y's `checksum` and `result` are non-unique indexes. Migration X→Y is a body-level move plus a column reindex.
- **Records survive extraction from their row.** Pulled out for shipping to an agent, dumping to a file, or passing through a tool that doesn't preserve column context, the body retains its full identity — `tf_checksum` and `result_checksum` are inside it, not just in PK columns that get lost on extraction.
- **Substrate portability.** If `seamless.db` ever moves to a different storage backend, the record body alone is sufficient to reconstruct meaning. Columns are query performance, not content.

The cost of duplicating two checksums (~170 bytes per record) is negligible at typical scale (~50 MB on a 250 MB table for a few CPU-months of records) and remains workable at the worst case of 10 CPU years of one-second transformations (~50 GB on a ~300 GB table). The convenience justifies the storage.

### The `checksum_fields` convention

Some fields in the JSON blob carry literal values, others carry content-addressed pointers to separately stored buffers. The `checksum_fields` array lists the keys whose values should be interpreted as checksums rather than as the value itself. This avoids hard-coding "hardware and conda_env are special" into the schema and keeps the addition of new content-addressed fields backwards-compatible: a reader that doesn't recognize a new field name still sees, via `checksum_fields`, that it's a pointer.

The decision of which fields to checksum-instead-of-inline is made by the producer, not the schema. The default list is `["hardware", "conda_env", "metavars"]`, but the convention generalizes to any large-and-deduplicatable payload.

### Schema versioning

`schema_version` is an integer carried in every record. Readers check it before interpreting the rest. Schema evolution does not require database migration — old rows remain readable, and new rows can carry new fields without breaking older readers (as long as they're additive).

### Canonical serialization of content-addressed sub-dicts

The content-addressed sub-dicts listed in `checksum_fields` (`hardware`, `python_packages`, `conda_env`, `metavars`, and any future additions) only deduplicate correctly if two semantically identical dicts produce byte-identical buffers. Without canonical serialization, irrelevant variation (key ordering, whitespace, integer-vs-float representation) produces different checksums for what should be the same content, and the deduplication argument collapses silently.

Recommendation: use Seamless's own **"plain" celltype** serialization rather than rolling a separate canonicalization (e.g., `orjson` with sort-keys flags). The "plain" celltype is already designed for exactly this purpose — Seamless content-addresses plain data structures internally, which requires byte-stable, host-independent serialization, and the existing plain-serialization path is the obvious thing to reuse here.

Two upsides:

- The records inherit any future improvements or fixes to Seamless's plain serialization automatically, with no parallel canonicalization codebase to keep in sync.
- The checksums computed for these sub-dicts are interoperable with anything else in the Seamless ecosystem that handles plain data — they are first-class Seamless plain checksums, not a `seamless.db`-specific encoding.

### Write-once enforcement

The `BaseModel.create` override in `database_models.py` catches `IntegrityError` on primary-key collision and falls through to an upsert path (fetch the existing row, update its fields, save). For tables that genuinely need upsert behavior, this is correct. For `MetaData` it is unreachable in normal mode — the table is write-once per `tf_checksum`, and any second write attempt indicates either a bug in the worker capture path or an audit-mode write that should be going through a separate path entirely.

Recommendation for the implementation phase: opt `MetaData` out of the upsert fallback (let `IntegrityError` propagate). A second-write attempt then becomes a loud error rather than a silent overwrite, which is the correct behavior given the write-once invariant — it surfaces bugs that would otherwise corrupt the captured environment context for a transformation.

### Compatibility with Seamless 1.x `seamless.db`

Seamless 1.x `seamless.db` files are not content-compatible with the new architecture regardless of this design: the checksum algorithm has changed, so no row in a 1.x database refers to content that the new system can resolve. There is no "migrate 1.x records into the new `MetaData`" story to tell — every entry would be a dangling reference.

What this design has to handle is only the **structural** coexistence of a 1.x database file being opened by the new server. The 1.x `MetaData` table is, in practice, always empty: the legacy capture path in `seamless-transformer/seamless_transformer/run.py` is commented out and has been for the entire lifetime of the new architecture. No 1.x `seamless.db` in the wild contains metadata rows.

The schema change (adding the `result` column to `MetaData`) therefore reduces to a one-liner in [database_models.py:db_init](seamless-database/database_models.py#L171), immediately before the existing `_db.create_tables(_model_classes, safe=True)` call:

```python
_db.execute_sql("DROP TABLE IF EXISTS meta_data")
_db.create_tables(_model_classes, safe=True)
```

`DROP TABLE IF EXISTS` is a no-op on a fresh database and on any database that never had the table. On a 1.x database that does have the (empty) legacy table, it drops it, after which `create_tables(..., safe=True)` recreates it with the new two-column layout. No data is lost because there was no data. The one-liner belongs in `database_models.py::db_init` where `create_tables` is called — not in `database.py`, which has no schema responsibility.

The other 1.x tables (`Transformation`, `RevTransformation`, `BufferInfo`, `SyntacticToSemantic`, `Expression`, `IrreproducibleTransformation`) are unchanged by this design and continue to coexist structurally in an opened 1.x file, even though their contents are semantically meaningless under the new checksum algorithm. Semantic incompatibility is the operator's problem to recognize; structural compatibility is what `db_init` has to guarantee.

## Capture path

Capture happens on the worker that actually executes the transformation. The record is built locally on the worker after the transformation completes, then flows back to `seamless.db` via the same return channel as the result (or via an immediately-following side call — to be settled in the implementation phase).

The legacy pattern of a frozen module-level dict on the driver (`execution_metadata0` populated once via `get_global_info` and `deepcopy`-ed per job) is abandoned. It silently mis-attributed the environment for any non-local execution, including jobserver and daskserver backends.

For locally-executed transformations (`process`, `spawn`), "worker" and "driver" coincide, but the record is still constructed at the point of execution, not at submission time.

The `seamless_version` scalar is captured via `importlib.metadata.version("seamless-framework")`, not by parsing `conda list` output as legacy did. The legacy scrape was brittle (depended on conda CLI output formatting), conda-only, and unnecessary now that `importlib.metadata` is the standard mechanism for reading installed package versions in Python.

### Capture sources

Legacy Seamless captured hardware via `lshw` and `nvidia-smi` subprocess calls — both fragile (often missing on macOS, requires root for full output on Linux, format-dependent across versions, subject to silent failure). The new capture uses Python libraries wherever possible, falling back to direct `/proc` reads only for fields that have no library equivalent.

| Source | Provides | Why over subprocess |
| --- | --- | --- |
| `platform` (stdlib) | OS, kernel, machine, processor (rough) | No install, no privileges |
| `psutil` | physical/logical CPU count, frequency, RAM total | Cross-platform, structured |
| `/proc/cpuinfo` direct parse | CPU model, instruction set flags (AVX2, AVX512, SSE level) | Fast, no shell, Linux-only |
| `pynvml` | NVIDIA GPU model, memory, driver version | Library not subprocess; structured return |
| `numpy.show_config()` | BLAS/LAPACK backend identification | Captures the actual numerical backend in use |
| `threadpoolctl.threadpool_info()` | OpenMP/BLAS/MKL thread pool sizes | The actual parallelization knobs that affect numerical determinism |
| `/proc/1/cgroup` parse | Container detection (Docker/podman/LXC) | Major reproducibility variable, trivially readable |
| `/etc/os-release` parse | Distribution name and version | Stdlib parse, no shell |
| `importlib.metadata.distributions()` | Python package inventory (conda + pip unified) | Python API, fast, complete |
| `conda env export` (subprocess) | Conda env including C library context, channels, build strings | The only source of C library version info; kept despite the subprocess cost |

### Capture principles

- **Capture configuration, not state.** Include CPU model, RAM total, thread pool sizes. Exclude uptime, current free memory, current load average. The latter change every second and would defeat deduplication.
- **Canonicalize.** All sub-dicts use Seamless's plain-celltype serialization, so semantically identical dicts produce byte-identical buffers and dedupe correctly. (See "Canonical serialization of content-addressed sub-dicts" in Schema sketch.)
- **Failure-tolerant but not silent.** If `pynvml` isn't installed, record `"gpu": null`, not omit the key. The presence of every expected field, even when null, makes records comparable across sites and makes "field not captured" distinguishable from "field truly absent."
- **Per-dict schema versions.** Each content-addressed sub-dict carries its own `schema_version` integer, so the format of `hardware`, `runtime_config`, etc., can evolve independently of the outer record schema.

### Cache 1: per-machine hardware

The `hardware` dict captures stable physical properties that change rarely. Capturing it from scratch on every job — even with Python libraries instead of subprocess — costs tens of milliseconds and dominates the per-job overhead unless cached.

**Storage:** `~/.seamless/cache/hardware-{hostname}.json`. The hostname tag is essential on HPC clusters where `~` is NFS-mounted across many nodes — without it, every node would race over the same file. The hostname tag also makes the cache survive across reboots, which is correct: the hardware itself doesn't change just because the kernel did.

**Staleness detection — primary: `boot_id`.** Linux exposes `/proc/sys/kernel/random/boot_id`, a UUID regenerated on every boot. The cache file stores the boot_id alongside the hardware dict. On read, if the current boot_id differs from the cached one, the cache is stale. Cost: one tiny file read. This handles, automatically and almost for free:

- Reboots
- Kernel updates (require a reboot)
- GPU driver updates (require a reboot for driver replacement)
- VM cold starts
- Container restarts (new boot_id inside the container)

**Staleness detection — secondary: cheap probe.** A few millisecond-level checks that catch the rare cases boot_id misses — `psutil.virtual_memory().total` (hot-plug RAM, VM resizing), `os.cpu_count()` (cgroup CPU limit changes inside a long-lived container), `platform.release()` (running kernel version, redundant with boot_id but cheap). If boot_id matches AND these probe values match the cached ones, trust the cache.

Cache hit total cost: well under 10 ms versus tens to hundreds of milliseconds for fresh capture.

**Atomic writes.** Write to a temp file in the same directory, then `os.rename()`, so two workers on the same node racing don't corrupt each other.

### Cache 2: per-environment

The env-side payload — `python_packages`, `conda_env`, `runtime_config` — depends on inputs that vary across processes (different conda envs activated, different thread settings, different `CUDA_VISIBLE_DEVICES`). The cache is **content-keyed**: the cache filename embeds a hash over the inputs that determine its contents.

**Storage:** `~/.seamless/cache/env-{cache_key}.json`, where `cache_key` is a short hash over the cache key inputs.

**Cache key inputs:**

- `$CONDA_PREFIX` (which conda env is active, if any)
- `sys.executable` (which Python interpreter — guards against multiple Python versions in the same conda env)
- A normalized subset of `os.environ`: `OMP_NUM_THREADS`, `MKL_NUM_THREADS`, `OPENBLAS_NUM_THREADS`, `OPENBLAS_CORETYPE`, `CUDA_VISIBLE_DEVICES`, `LD_PRELOAD`, and any other vars known to affect numerics
- A **freshness token**: the mtime of `$CONDA_PREFIX/conda-meta/history` (conda appends to this file on every install/remove/update operation) and the mtime of `site-packages/` (catches pip overlays that don't show up in conda-meta)

Because the freshness token is part of the cache key, any package change automatically routes the lookup to a new cache filename — there is no comparison logic, the old entry simply isn't found and a fresh capture is performed (and stored under the new key).

**What the cache stores:** the assembled `python_packages`, `conda_env`, and `runtime_config` sub-dicts as a single bundle, ready to be checksummed and incorporated into a record.

Cache hit cost: ~1 ms (read the file, parse). Cache miss cost: dominated by `conda env export` (typically several seconds on large envs).

### Eager warm-up

The first capture on a new worker is unavoidable, but the cost can be moved off the critical path of the first transformation by warming both caches **explicitly at worker startup** rather than lazily on first use:

- The **jobserver** triggers the warm-up immediately after a worker process initializes, before any transformation is dispatched to it.
- The **dask worker plugin** does the same in its `setup()` callback (Dask's per-worker plugin lifecycle hook).
- For locally-executed transformations (`process`, `spawn`), the warm-up runs at Seamless library import time or at the first `direct`/`delayed` call — the latency is incurred once per Python process, not once per transformation.

After warm-up, every cached lookup is in the millisecond range, and the per-transformation overhead from environment capture becomes negligible.

### Edge cases worth pinning down before implementation

- **Corrupt cache file.** On `json.JSONDecodeError`, fall back to fresh capture and overwrite. Don't propagate the error.
- **Concurrent workers on the same node.** Atomic rename solves writes; reads tolerate brief inconsistency. Worst case is one redundant capture, harmless.
- **Per-user isolation.** Cache files include the UID (in path or filename) when multiple users share a node. Different users may have different conda envs activated even on the same hardware.
- **Containerized worker hardware probe.** The host's `boot_id` may not match the container's, and `cpu_count` may report cgroup limits or host counts depending on container backend. Worth testing explicitly on at least one container setup before committing the design.

## Relationship to the irreproducible cache

The `MetaData` table is for normal-mode records. The existing `IrreproducibleTransformation` table is for the audit / divergence-recovery side of the story. The interaction between them is bounded by three decisions:

**Migration trigger.** A transformation enters the irreproducible cache on either of two conditions:

1. **Fingertipping fails**: the result buffer has been scratched or evicted and recomputation produces different bytes than the cached `result_checksum`.
2. **An explicit audit re-run diverges**: an operator forces re-execution (bypassing the cache) and the new result checksum differs from the cached one.

On either trigger, the `MetaData` row is **moved** into `IrreproducibleTransformation`. Because the record body shape is the same on both sides and the column layouts converge (see "The record body is canonical and self-contained"), this is a body-level row move plus a column reindex — no manipulation of the JSON body required.

**Append-only write policy inside `IrreproducibleTransformation`.** Once an entry lives in the irreproducible cache, every subsequent reproduction attempt — agreeing, diverging, or failing — adds a new row rather than overwriting. The existing `IrreproducibleTransformation` schema already supports this (both `checksum` and `result` are non-unique indexes); the only change from legacy behavior is the write policy itself — actually writing on every attempt, not only on the first divergence. This accumulates the record corpus that an agent-driven hunt reads as leads when searching for an environment in which the original `result_checksum` can be reproduced.

**No structural change to `IrreproducibleTransformation`.** Since the converged record body shape (`tf_checksum`, `result_checksum`, env signature, run context) is identical on both sides, `IrreproducibleTransformation` rows wrap the same JSON blob as `MetaData` rows. The existing column layout (`checksum` and `result` as non-unique indexes, `metadata` as JSONField) is already what the design needs. Only the write policy changes.

An entry that has once entered `IrreproducibleTransformation` does not migrate back to `MetaData`, even if subsequent reruns all agree with the original result. Once a divergence has been observed, the optimistic null has been falsified for that transformation at least once, and the entry is permanently in the irreproducible category — "reproduction succeeded this time" cannot undo "reproduction failed that time."

## Analysis by Copilot GPT-5.4

Two findings from review are worth pinning down explicitly before implementation.

### Finding 1: additional load-bearing environment axes should be named explicitly

The environment signature is good, but it still misses some axes that are load-bearing in real divergence work. The split between `hardware`, `runtime_config`, `python_packages`, `conda_env`, and `metavars` is the right shape. What is still under-specified:

- locale and timezone, especially for CLI tools and sorting
- container image digest or OCI image ID, not just "container detected"
- non-conda shared-library provenance for venv, system Python, uv, and wheels with bundled native code
- CPU affinity and cgroup limits, not just core counts
- explicit determinism knobs such as `PYTHONHASHSEED`, `CUBLAS_WORKSPACE_CONFIG`, and framework-specific deterministic flags if those ecosystems are in play
- NUMA placement and GPU UUID / compute capability when GPU faults are node-specific

Some of this is already hinted at under diagnostic context, but if the goal is to capture all relevant hardware and environment details, these items should either be named as first-class expected fields or explicitly excluded by scope.

### Finding 2: the capture plan is intentionally platform-shaped and should say so

The capture plan is somewhat too Linux/NVIDIA/conda-shaped to justify the phrase "all relevant hardware and environment details." The current source choices are pragmatic and much better than the legacy subprocess scraping, but they degrade unevenly outside the target platform:

- `/proc`-based probes are Linux-only
- `pynvml` only covers NVIDIA
- `conda env export` disappears on venv, uv, pixi, and system Python
- `importlib.metadata` sees Python distributions, not native libraries loaded at runtime

For the current Linux-oriented Seamless use case, this is acceptable. But the design should say explicitly that this is a solid Linux baseline rather than a universally complete environment model.

## Out of scope

The following are explicitly **not** part of `seamless.db`:

- **Audit attempt tracking** (which environments have been tried, in what order, with what outcome).
- **Annotations and notes** from prior investigations.
- **Outcome tagging** beyond the binary "is this entry in the irreproducible cache or not."

Audit-mode storage has no synergy with the rest of `seamless.db` (caching, buffer info, transformation lookup) and should live in a separate store — likely a noSQL database or structured logs. The only thing `seamless.db` does for audit mode is preserve the record corpus that audit tools consume.
