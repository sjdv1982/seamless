# Critique of execution-records-design.md

## Reviewer

Claude Opus 4.6, 2026-04-18. Analysis based on the design document, the Seamless agent contract docs (`contracts/identity-and-caching.md`, `contracts/scratch-witness-audit.md`, `contracts/execution-backends.md`, `contracts/compiled-transformers.md`, `contracts/modules-and-closures.md`), and the actual compiler flag defaults and execution paths in `seamless-transformer`.

## Scope of this critique

The design document's five environment signature legs (`hardware`, `runtime_config`, `python_packages`, `conda_env`, `metavars`) are well-chosen for **Python transformations**. This critique focuses on determinants that can cause a computation to **succeed with different results** — the primary threat to the optimistic null hypothesis. Determinants that cause success-vs-failure are noted where relevant but are secondary.

---

## Critical: the compiled-transformer compilation context is almost entirely uncaptured

Compiled transformers are a first-class execution mode in Seamless. The default compiler flags for C, C++, and Fortran (defined in `seamless-transformer/seamless_transformer/languages/native/{c,cpp,fortran}.py`) are:

```
C/C++:   -O3 -ffast-math -march=native -fPIC -fopenmp
Fortran: -O3 -fno-automatic -fcray-pointer -ffast-math -march=native -fPIC
```

These three flags — `-ffast-math`, `-march=native`, `-fopenmp` — together create the largest silent-divergence surface in the system, and none of the proposed capture tools sees the critical context.

### 1. `-ffast-math` + compiler version = non-deterministic floating-point across gcc versions

`-ffast-math` permits the compiler to reorder floating-point operations, use reciprocal approximations, assume no NaN/Inf, and apply associativity transforms. Two different gcc versions (e.g., gcc 11 vs gcc 13) apply these rewrites differently, producing bitwise-different results for the same source code on the same CPU.

The design captures `__compilers__` and `__languages__` in the `dunder` dict, but these record **what the user requested** (e.g., `"gcc"`), not **what was actually resolved on the worker** (e.g., `gcc (Ubuntu 13.2.0-23ubuntu4) 13.2.0`). Neither `python_packages` nor `conda_env` sees system-installed compilers. The actual compiler version and path (`which gcc`, `gcc --version`) need to be captured, and they belong in a compilation-context payload rather than in `hardware` or `runtime_config`.

### 2. `-march=native` + CPU microarchitecture = different instruction selection

`-march=native` tells gcc to use the host CPU's full instruction set. On a Haswell node this means AVX2 with FMA3; on a Skylake-X node it adds AVX-512. FMA changes results because `fma(a,b,c)` has one rounding step versus `a*b + c` which has two — a 0.5 ULP difference that propagates through iterative computations.

The `hardware` dict captures "CPU model" and the capture sources table mentions "instruction set flags (AVX2, AVX512, SSE level)" from `/proc/cpuinfo`, which is good. But the design should call out explicitly that ISA feature flags are **load-bearing for divergence diagnosis** under `-march=native`, not merely diagnostic context. When an audit observes a divergence in a compiled transformer, the first question is "did the two runs use different instruction sets?" — that question is only answerable if ISA flags are prominent in the record, not buried in a general-purpose hardware dump.

### 3. `-fopenmp` + thread scheduling = non-deterministic reductions

OpenMP parallel reductions (`#pragma omp parallel for reduction(+:sum)`) produce different floating-point results depending on thread count, scheduling policy, and runtime chunk decisions. The design captures `OMP_NUM_THREADS` in `runtime_config`, but misses:

- `OMP_SCHEDULE` — controls loop iteration distribution (static, dynamic, guided)
- `OMP_PROC_BIND` — controls thread-to-core binding (close, spread, master)
- `OMP_PLACES` — controls the placement of threads on hardware resources
- `GOMP_SPINCOUNT` / `GOMP_CPU_AFFINITY` — GCC-specific OpenMP runtime knobs

More fundamentally, even with identical settings, OpenMP runtime scheduling can differ between runs, making some compiled transformations inherently non-reproducible at the bit level. The record should capture enough to let an auditor know that `-fopenmp` was in effect — which currently it does not, because the flags come from language definitions, not from the transformation's `__compilation__` dunder.

### 4. System `libm` version

Compiled transformers calling `sin()`, `cos()`, `exp()`, `log()` link against the system's `libm`. Different glibc versions (2.31 vs 2.35 vs 2.38) implement transcendentals with different polynomial approximations, yielding different last-bit results. This is not visible to `python_packages`, `conda_env`, `numpy.show_config()`, or `threadpoolctl`. The glibc/libc version is capturable (e.g., from the dynamic linker or `/proc/self/maps`), but no proposed capture source does this.

### 5. Linked shared libraries for the compiled extension

The resulting `.so` file links against libraries resolved at load time by the dynamic linker. `ldd` output or `/proc/self/maps` inspection after `dlopen` would show exactly which `libgomp.so`, `libm.so`, `libblas.so` etc. were loaded — this is the ground truth of "what code actually ran." Currently uncaptured.

### Proposed addition: a `compilation_context` content-addressed sub-dict

For compiled transformers, the record should include a sixth content-addressed payload:

- **Compiler identity**: `gcc --version` / `g++ --version` / `gfortran --version` output, resolved path
- **Linker identity**: `ld --version`
- **Actual flags used**: the full command line passed to the compiler (from the language definition + `__compilation__` overrides + target selection)
- **Linked libraries**: `ldd` output on the resulting `.so`, or at minimum the dynamic linker's resolution of key libraries (`libm`, `libgomp`, `libblas`)

This sub-dict would only be populated for compiled transformations (null for Python), and would deduplicate well: same compiler + same flags + same linked libraries across many jobs on the same worker class.

---

## High-priority gaps

### 6. `PYTHONHASHSEED`

`PYTHONHASHSEED` affects `dict` and `set` iteration order in Python. Any transformation that accumulates floating-point values while iterating over a dict or set — extremely common in scientific code — produces order-dependent results. Python randomizes hash seeds by default (`PYTHONHASHSEED` unset = random). This is a real, common source of silent non-determinism. It should be a named field in `runtime_config`'s env var list, not just mentioned in the GPT-5.4 review as a possible addition.

### 7. FPU / MXCSR state

The SSE MXCSR register controls rounding mode and the flush-to-zero (FTZ) and denormals-are-zero (DAZ) flags. Some BLAS implementations — MKL in particular — set FTZ/DAZ at import time for performance, which affects all subsequent floating-point operations in the same thread/process. This is a per-process state inherited silently: importing numpy with MKL changes the floating-point semantics for a subsequent compiled transformer running in the same process.

No proposed capture source reads MXCSR. It is readable via `ctypes` and a small inline assembly wrapper, or via `numpy`'s internal state. If the record is to explain why two runs of the same compiled transformer diverged, FPU state is essential context.

### 8. System libm / glibc version for Python transformations too

Even for Python transformations, some numpy/scipy operations ultimately call into system `libm` (e.g., `scipy.special` functions, or numpy's own transcendental implementations on platforms where they delegate to libm). The glibc version is not captured by `python_packages` or `conda_env` (conda captures conda-installed packages, not the host glibc that the conda Python links against). Worth capturing in `hardware` alongside the OS/kernel information — it changes rarely and deduplicates with `hardware`.

---

## Medium-priority gaps

### 9. GPU determinism knobs

For GPU transformations, several environment variables determine whether computation is reproducible at all:

- `CUBLAS_WORKSPACE_CONFIG` — must be `:4096:8` or `:16:8` for deterministic cuBLAS
- `CUDA_LAUNCH_BLOCKING` — forces synchronous kernel launches, removing one source of non-determinism
- Framework-specific: `PYTORCH_CUDA_ALLOC_CONF`, `TF_DETERMINISTIC_OPS`

These aren't in the proposed `runtime_config` env var list. The design captures `CUDA_VISIBLE_DEVICES` (which GPU to use) but not the determinism-controlling variables. For an audit investigating GPU-related divergence, knowing whether deterministic mode was even enabled is the first diagnostic question.

### 10. Docker / container image identity

If `__env__` specifies `set_docker({"name": "image:tag"})`, the container image digest is the single most important environment determinant — it pins the entire userspace. The design captures "container detection" (Docker/podman/LXC) in `hardware` via `/proc/1/cgroup`, but not the **image identity**. Two runs in `myimage:latest` could use completely different images if the tag was updated between runs. The image digest (`docker inspect --format='{{.Id}}'`) should be captured when a Docker environment is in use.

### 11. Locale

`LC_NUMERIC` affects `strtod()` / `printf()` behavior for floating-point formatting — relevant for bash transformations that parse numerical output. `LC_COLLATE` affects sort order, which can change the result of any computation that depends on lexicographic ordering. These should be added to `runtime_config`'s env var list, especially since bash transformations inherit the full parent environment without filtering (as seen in `execute_bash.py`).

### 12. Pip wheel native library provenance

A pip-installed numpy can bundle OpenBLAS (as the PyPI wheels do) or link against system MKL. `importlib.metadata` shows `numpy 1.26.4` but not which BLAS is bundled. The design addresses this partially — `numpy.show_config()` captures the BLAS backend for numpy specifically — but other packages that bundle their own native libraries (scipy, torch, tensorflow) may not have equivalent introspection APIs. This is acknowledged as a platform gap by the GPT-5.4 review; the design should state explicitly that `numpy.show_config()` covers numpy's BLAS but not the native-library provenance of other packages.

---

## Minor issues

### 13. `checksum_fields` default list inconsistency

The prose in "The `checksum_fields` convention" section says:

> The default list is `["hardware", "conda_env", "metavars"]`

But the representative JSON record shows:

```json
"checksum_fields": ["hardware", "runtime_config", "python_packages", "conda_env", "metavars"]
```

The JSON is presumably correct — the prose omits `runtime_config` and `python_packages`.

### 14. The design is Python-transformation-shaped

The five environment legs, the capture sources table, and the caching strategy are all designed around Python transformations. Compiled transformers are mentioned via `__compilers__` / `__languages__` in the `dunder` section, but the compilation pipeline — which introduces its own large set of environment determinants (see items 1-5 above) — doesn't have a corresponding capture strategy. The design should either scope itself to Python transformations explicitly, or extend the capture plan to cover compilation context.

### 15. Bash transformations inherit unfiltered environment

`execute_bash.py` copies the full `os.environ` into the subprocess environment. For bash transformations that call external tools, any environment variable can potentially affect the result — `PATH` order, `LANG`, `TMPDIR`, tool-specific variables. The design can't realistically capture the entire environment, but it should acknowledge that bash transformations have a wider implicit-input surface than Python transformations, and that the `runtime_config` env var list is a selected subset rather than a complete enumeration.

---

## What the design gets right

- The content-addressing and deduplication strategy for large sub-dicts is well-designed. The `hardware` / `runtime_config` split correctly separates stable-per-machine from variable-per-invocation axes.
- Capturing `numpy.show_config()` and `threadpoolctl.threadpool_info()` covers the main Python-side numerical determinism axes — these are the right tools for the job.
- The write-once invariant with `IntegrityError` propagation is correct and prevents silent corruption.
- The X-to-Y migration model for irreproducible entries is clean: same record body, different table constraints, literal row move.
- Storing the record body as a self-contained JSON blob with column duplication is a good trade — it survives extraction from the database context.
- The eager warm-up strategy and per-machine / per-environment cache split are well-thought-out for minimizing per-transformation overhead.
- Using Seamless's own plain-celltype serialization for canonical sub-dict encoding avoids a parallel canonicalization codebase.
- The `schema_version` + per-sub-dict versioning approach handles evolution without migration.

---

## Summary table

| Priority | Gap | Proposed fix |
|----------|-----|--------------|
| Critical | Compiler version/path not captured for compiled transformers | Add `compilation_context` content-addressed sub-dict |
| Critical | Actual compiler flags (incl. `-ffast-math`, `-march=native`) not recorded in execution record | Include full compile command in `compilation_context` |
| Critical | `-fopenmp` active but OpenMP scheduling env vars not captured | Add `OMP_SCHEDULE`, `OMP_PROC_BIND`, `OMP_PLACES` to `runtime_config` |
| High | System libm / glibc version not captured | Add to `hardware` (changes rarely, deduplicates well) |
| High | `PYTHONHASHSEED` not in the env var list | Add to `runtime_config` env var list |
| High | Linked shared libraries for compiled `.so` not captured | Include `ldd` output in `compilation_context` |
| High | FPU/MXCSR state (FTZ/DAZ, rounding mode) not captured | Capture at execution time, add to `runtime_config` |
| Medium | GPU determinism knobs (`CUBLAS_WORKSPACE_CONFIG` etc.) missing | Add to `runtime_config` env var list |
| Medium | Docker image digest not captured | Capture when Docker environment is in use |
| Medium | Locale vars (`LC_NUMERIC`, `LC_COLLATE`) not captured | Add to `runtime_config` env var list |
| Low | `checksum_fields` default list in prose doesn't match JSON example | Fix prose |
| Low | Bash environment inheritance surface not acknowledged | Add a note in the design |
