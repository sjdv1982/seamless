# Critique of bucket-recording.md

## Reviewer

GitHub Copilot (Claude Opus 4.6), 2026-04-18. Analysis based on `bucket-recording.md`, `execution-records-design.md`, both prior critiques (Claude and Codex), the Seamless agent contract docs (`contracts/identity-and-caching.md`, `contracts/scratch-witness-audit.md`, `contracts/execution-backends.md`, `contracts/compiled-transformers.md`, `contracts/modules-and-closures.md`), and the actual compiler flag defaults and execution paths in `seamless-transformer`.

## Scope

The primary risk is **determinants that cause a computation to succeed but with different results** — the threat to the optimistic null hypothesis. Determinants that cause success-vs-failure are secondary: the goal is for execution records to provide sufficient initial detail for an audit procedure to investigate whether environment variation could have caused result divergence. The bucket-recording design is evaluated as a revision of the earlier flat execution-records-design, so this critique focuses on what the bucket decomposition introduces, improves, or loses relative to the earlier design and its two prior critiques.

---

## 1. Structural flaw: Probe-actual equivalence fails for lazy-loaded libraries (Bucket 3)

The document states:

> **Probe-actual equivalence.** The probe must produce the same checksum as a capture during an actual job.

Bucket 3 (Node × Environment) lists **Loaded shared libraries** from `/proc/self/maps` as a captured field. This field is fundamentally incompatible with probe-based capture. The set of loaded `.so` files depends on what the executing code imports — a probe that imports numpy sees numpy's BLAS `.so`, but a transformation that also imports torch, scipy, or tensorflow will load additional native libraries that the probe never saw. The probe captures a *subset* of what runs during the actual job.

In the original `execution-records-design.md`, loaded shared libraries were in `runtime_config`, captured *at execution time on the worker*. Moving this to a bucket probe that runs separately is structurally less accurate for the primary risk. The probe checksum will be identical across two transformations that load different native math libraries (e.g., one uses `scipy.linalg` via MKL, the other uses a custom LAPACK binding), collapsing a real determinant distinction.

**Options:** Either (a) restrict Bucket 3's `/proc/self/maps` field to a smaller stable set of libraries known at probe time (the BLAS/LAPACK/OpenMP/CUDA ones that numpy and threadpoolctl reveal), or (b) add a per-job field that captures the delta between the probe snapshot and the post-execution loaded-library state.

The other Bucket 3 fields (`numpy.show_config()`, `threadpoolctl.threadpool_info()`, CUDA toolkit version, cuDNN version) are fine — they are environment-stable and genuinely invariant between probe and execution.

## 2. Critical gap: No place for per-transformation compilation context

Both the Claude critique and the Codex critique of `execution-records-design.md` identified this as the highest-priority gap. The bucket-recording design partially addresses it by putting compiler *versions* in Bucket 2 (`gcc --version`, `gfortran --version`, `$CC/$CXX/$FC`). But the actual compilation *command line* — the flags, include paths, and library paths that produce the `.so` — is per-transformation, not per-environment. It has no home in the bucket system.

The default flags are exactly the dangerous ones (from the language definitions in `seamless-transformer/seamless_transformer/languages/native/`):

```
C/C++:   -O3 -ffast-math -march=native -fPIC -fopenmp
Fortran: -O3 -fno-automatic -fcray-pointer -ffast-math -march=native -fPIC
```

- `-ffast-math` permits FP reordering; two gcc versions apply different rewrites → different results, same code, same inputs
- `-march=native` selects ISA features from the running CPU; Haswell (AVX2+FMA3) vs. Skylake-X (AVX-512) → different instruction selection → different rounding
- `-fopenmp` enables parallel reductions whose accumulation order depends on thread count/scheduling

The per-job record currently has timestamps, resource accounting, and hostname — but no `compilation_context`. This means the execution record for a compiled transformer that diverges under audit contains the compiler version but *not the flags that caused the divergence*. This is like recording the gas station brand but not whether you put diesel or regular in the car.

**Proposed fix:** Add a per-job `compilation_context` field (null for Python/bash transformations) that records:
- The full compile command as actually invoked
- `ldd` output on the resulting `.so`
- The `__compilation__` dunder values in effect
- `compilation_time_seconds` is already present, so the slot is natural

## 3. Critical gap: FPU/MXCSR control register state

No bucket and no per-job field captures the SSE MXCSR register. MKL sets the flush-to-zero (FTZ) and denormals-are-zero (DAZ) bits at import time, silently changing floating-point semantics for the entire process. A numpy linked to MKL has different FP behavior from one linked to OpenBLAS — not just in BLAS calls, but in *all subsequent floating-point operations in the same process*, including compiled transformers.

This is invisible to all proposed capture sources: `/proc/self/maps` shows which `.so` is loaded, `numpy.show_config()` shows the BLAS backend name, but neither reports whether FTZ/DAZ are active. It's readable via a small ctypes snippet (`_mm_getcsr()` equivalent). It belongs in either Bucket 3 (if captured at probe time, which is a reasonable approximation since it depends on the Node × Environment combination) or per-job (if accuracy under long-lived worker state drift matters).

This is the single most common source of "0.5 ULP" divergences in scientific computing, and it's entirely unrecorded.

## 4. High gap: OpenMP scheduling env vars

Bucket 5 (Queue × Node) captures `OMP_NUM_THREADS`, `MKL_NUM_THREADS`, `OPENBLAS_NUM_THREADS`. But for compiled transformers using `-fopenmp`, three additional variables control the *distribution* of parallel work, not just the thread count:

- `OMP_SCHEDULE` — static vs dynamic vs guided iteration partitioning
- `OMP_PROC_BIND` — thread-to-core binding policy (close, spread, master)
- `OMP_PLACES` — hardware placement of threads

These directly affect the order of floating-point accumulation in parallel reductions, which is a primary divergence mechanism under `-ffast-math -fopenmp`. They should be in Bucket 5 alongside `OMP_NUM_THREADS`.

## 5. High gap: Bash/subprocess ambient environment

Bucket 2 captures a named set of determinism-relevant env vars (`PYTHONHASHSEED`, `CUBLAS_WORKSPACE_CONFIG`, etc.). But bash transformations inherit the full `os.environ` (confirmed: `execute_bash.py` copies `os.environ` and passes it to `/bin/bash` via `Popen`). For bash transformations, many additional variables are primary divergence determinants:

| Variable | Divergence mechanism |
|----------|---------------------|
| `PATH` | Different binary resolved for the same command name |
| `LC_ALL` / `LC_NUMERIC` / `LC_COLLATE` / `LANG` | Different sort order, different `strtod()`/`printf()` float formatting |
| `TZ` | Different timestamp formatting in output |
| `TMPDIR` | Different temp directory → different intermediate file paths if tools embed paths in output |
| Tool-specific (`R_LIBS`, `PERL5LIB`, `JAVA_HOME`, `HDF5_PLUGIN_PATH`) | Different library/tool version resolved |
| `LOADEDMODULES` / `MODULEPATH` | HPC module system state |

Bucket 2 captures `locale.getlocale()`, which is good but not sufficient — `LC_NUMERIC` can override `LANG` at the process level, and the hierarchy matters for bash children.

Neither the buckets nor the per-job record captures `PATH`, which is arguably the single most important determinant for bash transformations: it determines *which executables run*.

## 6. High gap: External tool resolution and provenance

Related to the above but distinct: even if `PATH` were captured, the execution record doesn't record *which binaries were actually invoked*. For bash transformations, the ground truth is the resolved paths and versions of commands (`/usr/bin/sort` vs `/opt/conda/bin/sort`; coreutils 8.30 vs 9.1 produces different sort output on locale-sensitive data). The Codex critique's proposed `tools` sub-record — resolved command paths, `--version` output, executable hashes — fills this gap and doesn't fit into any existing bucket.

This is a genuine design tension: tool resolution is per-transformation (different transformations call different commands), so it can't be pre-probed into a bucket. It would need to be a per-job field, which conflicts with the bucket design's goal of minimizing per-job capture cost. A pragmatic middle ground: capture `PATH` and `LOADEDMODULES` in a bucket (they're typically stable per queue × environment), and add an optional per-job `tools` field populated only for bash transformations.

## 7. Medium gap: Per-transformation Docker environment

Bucket 2 captures the Docker image digest for the "outer" environment. But Seamless supports per-transformation `__env__` with `set_docker()` (per the compiled-transformers contract). That inner container's image digest is a per-transformation determinant that has no home in the bucket system. A mutable tag (`latest`) re-pulled between runs can produce a completely different userspace.

This belongs in the per-job record, not a bucket — it varies per transformation, not per environment.

## 8. Medium gap: Long-lived worker process state

Spawn, jobserver, and daskserver workers execute many transformations in the same process (confirmed: `worker.py` runs transformations in a thread pool executor within a long-lived process). A prior transformation can:
- Import a library that sets FTZ/DAZ
- Modify `os.environ` (including `OMP_NUM_THREADS`)
- Modify thread pool sizes
- Leave allocated GPU memory that constrains subsequent allocations

The compiled-transformers contract explicitly warns: "persistent native state causes silently incorrect caching and the runtime does not detect it."

The per-job record has `retry_count` and `hostname`, but nothing about worker identity: no PID, no process start time, no worker execution counter. When an audit finds that only late-in-lifetime executions on a specific worker diverged, this context is essential.

## 9. Medium gap: Package provenance for editable/local installs

Bucket 2 uses `importlib.metadata.distributions()` for Python packages. This reports name+version, but two editable installs at `mypackage==1.0.0` can have different source code. `direct_url.json` (PEP 610) containing VCS commit hashes, and `RECORD` file hashes, are the only way to distinguish them. Not capturing this means the execution record can contain identical `environment` checksums for environments that actually have different code.

## 10. Low-medium gap: `glibc` / system `libm` version

Bucket 3 captures `/proc/self/maps` which would show glibc's path — but glibc version is not explicitly extracted. Different glibc versions (2.31 vs 2.38) implement transcendental functions (`sin`, `cos`, `exp`, `log`) with different polynomial approximations, producing different last-bit results. This affects both compiled transformers (which call `libm` directly) and Python transformations (numpy/scipy often delegate to `libm`). The version should be an explicit named field, not buried in a `/proc/self/maps` dump.

## 11. Structural note: Bucket 4 is undefined

Bucket 4 (Queue) says:

> (TODO: enumerate these parameters!)

This isn't a flaw in the design thinking, but it means the bucket system currently has a hole — the queue parameters that affect thread counts, memory limits, and job script prologues are the bridge between what the scheduler provides and what the job sees. Until this is enumerated, Bucket 5 (Queue × Node) can't be properly validated as non-overlapping.

## 12. Stale-probe risk is operationally unbounded

The document states "Seamless never auto-detects staleness or auto-recaptures." This is clean operationally, but consider: a system library update (glibc security patch, OpenBLAS update) between probes means every transformation executed between the last probe and the next one has an inaccurate Bucket 1 or Bucket 3 checksum in its record. The execution record then contains evidence that is *provably wrong*, which can be worse for audit than no evidence — it falsely asserts a specific environment when a different one was in effect.

The original design's hardware cache used `boot_id` as a staleness trigger, which at least catches reboots (and most library updates require reboots or container restarts). The bucket design's "manual only" approach removes even that safety net. Consider adding a lightweight staleness check (not auto-recapture): a fast hash over the small set of Bucket 1 fields that can change without reboot (e.g., kernel version, driver version), compared against the cached probe result, producing a warning if they diverge. This preserves the "manual trigger" principle while adding a detection guardrail.

---

## Summary: determinants not captured by any bucket or per-job field

| Determinant | Primary risk | Where it should go |
|---|---|---|
| Actual compiler flags / full compile command | `-ffast-math` / `-march=native` rewriting differences | Per-job `compilation_context` |
| `ldd` of compiled `.so` | Different libm/libgomp/BLAS linked | Per-job `compilation_context` |
| MXCSR register (FTZ/DAZ) | MKL silently changes FP semantics for all subsequent FP ops | Bucket 3 or per-job |
| `OMP_SCHEDULE`, `OMP_PROC_BIND`, `OMP_PLACES` | Parallel reduction accumulation order | Bucket 5 |
| `PATH` | Bash resolves different binary | Bucket 2 or Bucket 5 |
| `LC_NUMERIC`, `LC_COLLATE`, `LANG` (full hierarchy) | Sort order, float formatting | Bucket 2 or Bucket 5 |
| Tool resolution (`which` + `--version`) | Different tool version produces different output | Per-job (bash only) |
| Per-transformation Docker image digest | `set_docker()` inner container | Per-job |
| Worker PID / execution counter / process age | Long-lived worker state drift | Per-job |
| Editable install VCS commit / `direct_url.json` | Same `mypackage==1.0.0`, different code | Bucket 2 |
| `/proc/self/maps` at *execution* time vs. probe time | Probe captures subset of loaded libs | Per-job delta or restrict Bucket 3 scope |
| `glibc` / `libm` version (explicit) | Different transcendental approximations | Bucket 1 (named field) |
| `GOMP_SPINCOUNT` / `GOMP_CPU_AFFINITY` | GCC-specific OpenMP runtime knobs | Bucket 5 |

---

## What the design gets right

- The five-bucket decomposition is a genuinely good caching strategy — it separates axes that change independently and enables massive deduplication. This is a substantial improvement over the original flat design, where the entire environment payload was per-job or at best per-machine.
- CPU microcode version is an excellent addition. Microcode patches can change instruction behavior (notably Intel erratum workarounds) and this is almost never captured by any other provenance system.
- GPU UUID, GPU ECC mode, GPU persistence mode, and GPU compute capability — these go well beyond what the original design had, and they are exactly what's needed to diagnose GPU-specific divergences.
- NUMA topology, transparent hugepages, ASLR, overcommit policy, filesystem types — these are all excellent additions that cover the "success-vs-failure" secondary risk, and in rare cases (NUMA placement affecting memory access patterns and thus cache behavior) can affect numerical results.
- `PYTHONHASHSEED`, `CUBLAS_WORKSPACE_CONFIG`, `TF_DETERMINISTIC_OPS`, `PYTORCH_CUDA_ALLOC_CONF` are now explicitly named in Bucket 2, addressing the Codex critique's concern about determinism knobs.
- Docker image digest (not just container detection) is now present in Bucket 2, addressing Item 10 of the Claude critique.
- The "redundant capture of shared concerns" principle is sound and audit-friendly — capturing `OMP_NUM_THREADS` in both Bucket 2 (where it might be set by activation scripts) and Bucket 5 (where it's resolved by the job prologue) preserves the causal chain for audit.
- Canonical serialization via Seamless plain celltype is the right choice, inherited from the original design.
- The exclusion list (specific cores, specific GPU indices, PID, SLURM job ID, free memory) is well-reasoned and directly serves probe-actual equivalence.
- The per-job resource accounting is comprehensive: splitting `cpu_time` into user and system, adding `gpu_memory_peak_bytes`, and adding `compilation_time_seconds` are all improvements over the original design's three-scalar model.

---

## Structural comparison with the original flat design

The bucket design addresses two real problems with the original flat design:

1. **Capture cost.** The original design acknowledged that environment capture is expensive (seconds for `conda env export`) and proposed a caching strategy, but the cache was ad hoc (hostname-keyed hardware cache, content-keyed env cache with freshness tokens). The bucket design formalizes this into a clean decomposition with explicit cache-key labels and manual triggers.

2. **Deduplication.** The original design's content-addressed sub-dicts (`hardware`, `runtime_config`, `python_packages`, `conda_env`) already deduplicated well, but the bucket design goes further by separating the per-machine axis (Bucket 1) from the per-environment axis (Bucket 2) from the cross-product (Bucket 3), giving finer-grained deduplication.

What the bucket design loses relative to the original:

1. **Per-job accuracy.** The original design captured everything at execution time on the worker. The bucket design captures most things at probe time, which is less accurate for fields that depend on what the transformation actually does (loaded libraries, tool resolution, thread pool state after imports). This is the fundamental trade-off; it's acceptable for fields that are genuinely environment-stable, but problematic for the lazy-loading case (§1 above).

2. **The `runtime_config` leg.** The original design had a separate `runtime_config` content-addressed sub-dict that captured per-invocation numerics configuration (BLAS backend, thread pool sizes, and numerics env vars). The bucket design distributes this across Bucket 3 (numpy/threadpoolctl) and Bucket 5 (thread count env vars), which is better for deduplication but makes it harder for an auditor to answer the single question "what were the effective numerics settings for this job?" without joining three buckets.
