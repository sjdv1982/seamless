# Codex Critique of `execution-records-design.md`

## Scope

This critique reviews [execution-records-design.md](execution-records-design.md) against the primary audit risk:

> A transformation succeeds, but later succeeds again with a different result.

Determinants that mostly cause success versus failure are still relevant, but secondary. The execution record does not need to store failed computation records in normal mode; it should, however, preserve enough successful-run context to guide an audit procedure when a later divergence is found.

The current design has the right overall shape: the cache key remains environment-agnostic, and execution records preserve evidence for falsifying that optimistic null later. The gaps below are mostly about the breadth and timing of the captured environment, not about the core schema idea.

## Summary

The proposed five-leg environment signature is a useful baseline:

- `hardware`
- `runtime_config`
- `python_packages`
- `conda_env`
- Seamless-side execution fields such as `execution_mode`, `metavars`, and dunders

But it is still too Python-numerics/conda/Linux shaped for the determinant surface that Seamless actually exposes. Seamless also executes bash commands, native compiled code, and long-lived worker processes. Those paths introduce successful-divergence determinants that are not reliably captured by `platform`, `psutil`, `/proc/cpuinfo`, `pynvml`, `numpy.show_config()`, `threadpoolctl`, `/proc/1/cgroup`, `/etc/os-release`, `importlib.metadata`, or `conda env export`.

The most important missing class is not "more hardware facts" in isolation. It is ambient runtime state: executable resolution, shell environment, dynamic linker state, native library selection, container image identity, GPU identity, and long-lived process state.

## Findings

### 1. Bash and subprocess ambient environment is under-captured

Severity: high.

The design's `runtime_config` currently emphasizes numerical configuration: BLAS/LAPACK, thread pools, and a narrow set of environment variables such as `OMP_NUM_THREADS`, `MKL_NUM_THREADS`, `OPENBLAS_NUM_THREADS`, `OPENBLAS_CORETYPE`, `CUDA_VISIBLE_DEVICES`, and `LD_PRELOAD`.

That is not enough for bash-language transformations. `execute_bash()` constructs the subprocess environment from `os.environ.copy()` and passes it to `/bin/bash`:

- [execute_bash.py](../seamless-transformer/seamless_transformer/execute_bash.py#L190)
- [execute_bash.py](../seamless-transformer/seamless_transformer/execute_bash.py#L242)

This means many determinants can affect successful output bytes without appearing in the proposed record:

- `PATH`, `SHELL`, and shell startup behavior
- `LC_ALL`, `LANG`, `LANGUAGE`, and other locale variables
- `TZ`
- `HOME`, `XDG_CONFIG_HOME`, `XDG_CACHE_HOME`, and other config roots
- `TMPDIR`, `TEMP`, `TMP`
- `PYTHONHASHSEED`
- tool-specific variables such as `R_LIBS`, `PERL5LIB`, `JAVA_HOME`, `GATK_LOCAL_JAR`, `HDF5_PLUGIN_PATH`, `GDAL_DATA`, `PROJ_LIB`
- scheduler variables that change tool behavior or thread discovery, such as `SLURM_CPUS_PER_TASK`

The agent contract for `seamless-run` explicitly says command determinism depends on avoiding ambient dependencies and calls out locale-sensitive behavior. The execution record should therefore not treat these as optional extras.

Recommendation: add a separate `process_environment` or `ambient_runtime` sub-record. It should include a documented allowlist for high-value variables, plus a redaction policy for sensitive variables. At minimum, make locale, timezone, `PATH`, temp-dir variables, home/config roots, `PYTHONHASHSEED`, and scheduler CPU/GPU allocation variables first-class.

### 2. External command and tool provenance is missing

Severity: high.

For bash transformations, package inventories do not tell an auditor which executables actually ran. `python_packages` does not cover `/usr/bin/sort`, `/bin/bash`, `awk`, `grep`, `Rscript`, Java tools, command-line bioinformatics tools, custom compiled binaries, or module-provided HPC tools. `conda_env` only helps when those tools came from the active conda environment.

Two successful runs can diverge because:

- `PATH` resolves `sort` or `python` to a different binary.
- A site module updates a command in place.
- A custom tool is uploaded or found by path but its version changed.
- A command's output depends on coreutils, bash, awk, sed, Perl, R, Java, or glibc version.

The design currently captures `__env__` and may capture `Environment.set_which()` as part of dunder/environment data, but the execution record should preserve what was actually resolved on the worker, not only what was requested.

Recommendation: for bash/CLI transformations, add a `tools` sub-record:

- command words resolved through `PATH`
- absolute paths
- `--version` or equivalent output where cheap and safe
- executable hashes for declared tools where feasible
- `type -a` or equivalent resolution diagnostics for ambiguous commands
- the shell path and version, at least `/bin/bash --version`

This is especially important for successful divergent text results, where the root cause is often `sort`/locale/tool version rather than CPU model.

### 3. Compiled transformer toolchain provenance is incomplete

Severity: high.

Compiled transformers intentionally exclude compilation settings from the cache key. The compiled-transformer contract says compiler flags are execution-only metadata, not determinant identity. That is consistent with the optimistic null, but it makes the execution record responsible for preserving enough evidence to diagnose flag/toolchain sensitivity.

Current execution resolves compiler definitions from the language registry and then invokes compiler binaries:

- [compile.py](../seamless-transformer/seamless_transformer/compiler/compile.py#L31)
- [compile.py](../seamless-transformer/seamless_transformer/compiler/compile.py#L62)

CFFI then builds the Python extension using Python build settings and linker behavior:

- [cffi_wrapper.py](../seamless-transformer/seamless_transformer/compiler/cffi_wrapper.py#L48)

The proposed record mentions dunders such as `__compilation__`, `__compilers__`, and `__languages__`, but that does not capture the actual worker toolchain:

- compiler absolute path
- compiler version and target triple
- linker and linker version
- libc, libstdc++, libgfortran, libgcc, OpenMP runtime
- Python `sysconfig` compiler/linker variables used by CFFI
- `CFLAGS`, `CXXFLAGS`, `FFLAGS`, `RUSTFLAGS`, `GOFLAGS`
- `CPATH`, `C_INCLUDE_PATH`, `CPLUS_INCLUDE_PATH`, `LIBRARY_PATH`, `LD_LIBRARY_PATH`, `PKG_CONFIG_PATH`
- CPU-specific compiler defaults and `-march=native` consequences

These are classic successful-divergence determinants for floating-point and vectorized native code.

Recommendation: add a `toolchain` sub-record for compiled transformations. It should record the completed module definition, actual compiler/linker paths, versions, relevant build environment variables, Python build config, and a summary of linked dynamic libraries for the built extension.

### 4. Native shared-library provenance is too weak outside conda

Severity: high.

The design correctly states that `importlib.metadata` sees Python distributions but not C libraries, while `conda_env` is unavailable or incomplete outside conda. The current wording treats this as graceful degradation. For the primary risk, it is a real determinant gap.

Successful divergent results can be caused by native libraries that are invisible to both package dumps:

- system `libm`, `glibc`, `libstdc++`, `libgcc`, `libgfortran`
- OpenMP runtimes (`libgomp`, `libiomp5`, `libomp`)
- BLAS/LAPACK libraries selected by dynamic linker state
- HDF5, NetCDF, GDAL, PROJ, image codecs, compression libraries
- CUDA, cuDNN, cuBLAS, NCCL, ROCm, oneAPI/MKL runtime libraries
- bundled wheel `.so` files that changed under an editable/local install

`numpy.show_config()` and `threadpoolctl` are helpful but not a complete dynamic-library manifest.

Recommendation: add `native_runtime`:

- loaded shared objects from `/proc/self/maps` on Linux, or best-effort platform equivalents
- resolved paths and build IDs/hashes for determinant libraries
- dynamic linker variables such as `LD_LIBRARY_PATH`, `LD_PRELOAD`, `DYLD_LIBRARY_PATH` where applicable
- `ldd` or equivalent output for compiled extension modules and key native modules
- glibc/libstdc++/libgfortran/OpenMP runtime versions

This should be captured after imports/toolchain loading as well as before user execution where possible, because native libraries are often loaded lazily.

### 5. Container identity is not captured by container detection

Severity: high.

The design proposes container detection in `hardware`. Detection alone is not enough. A mutable Docker tag or Singularity image path can point to different bytes over time while producing successful but different results.

The relevant determinant is image identity, not merely "this ran in a container".

Recommendation: record:

- container runtime (`docker`, `podman`, `singularity`/`apptainer`, Kubernetes, etc.)
- image digest or OCI image ID, not just tag
- image tag/name as display metadata
- container ID
- bind mounts that expose mutable host paths
- relevant cgroup namespace and resource limits
- whether the worker is inside a container but compiling/linking against host-mounted paths

If image digest cannot be obtained, record that explicitly as `"image_digest": null` with a capture error or unsupported reason.

### 6. GPU identity and GPU runtime details are too shallow

Severity: high for GPU workflows; medium otherwise.

GPU model, memory, and driver version are useful but not sufficient. `CUDA_VISIBLE_DEVICES=0` identifies a process-visible index, not a stable physical device. On shared GPU nodes, index 0 can be a different card across allocations. MIG partitions make this more complicated.

Successful divergent results can be caused by:

- different GPU UUID or PCI bus ID with the same model
- different compute capability
- MIG partition differences
- CUDA runtime/toolkit mismatch
- cuDNN/cuBLAS/NCCL version differences
- TF32, deterministic algorithm, and workspace settings
- GPU clocking/ECC/MPS settings in rare cases

Recommendation: extend `hardware` and `runtime_config`:

- GPU UUID, PCI bus ID, compute capability, MIG UUID/profile
- CUDA driver and runtime versions
- cuDNN/cuBLAS/NCCL/ROCm versions where loaded
- `CUBLAS_WORKSPACE_CONFIG`, `NVIDIA_TF32_OVERRIDE`, PyTorch/JAX/TensorFlow deterministic flags if detectable
- framework-level device and precision settings when those libraries are loaded

### 7. Capture timing can record the wrong determinant state

Severity: medium-high.

The design says the record is built after the transformation completes. That is appropriate for resource accounting and result identity, but not always for determinant capture.

Python user code can mutate:

- `os.environ`
- threadpool settings
- current working directory
- imported modules and loaded native libraries
- random/global process state

Bash execution copies the environment before `Popen`; the determinant environment is the pre-execution environment passed to the child, not necessarily the worker environment after completion.

Recommendation: split capture into:

- `runtime_config_pre`: captured immediately before user code/subprocess/native call
- `runtime_observed_post`: captured after execution for loaded libraries, imports, threadpool state, and diagnostic observations

For bash, preserve the exact child environment after redaction, or at least the allowlisted determinant subset from the child environment passed to `Popen`.

### 8. Long-lived worker and process state is diagnostically relevant

Severity: medium-high.

Spawn, jobserver, and daskserver workers may execute many transformations in the same process. The worker spawning spec says workers listen forever and run requests in worker threads:

- [spawnworkers.md](../seamless/docs/agent/repos/seamless-transformer/source/spawnworkers.md#L8)
- [spawnworkers.md](../seamless/docs/agent/repos/seamless-transformer/source/spawnworkers.md#L10)

The compiled-transformer contract explicitly warns that persistent native state can cause silently incorrect caching and that the runtime does not detect it.

Execution records cannot capture arbitrary process state. But they can provide audit leads:

- PID
- process start time
- worker ID/address
- Dask worker address
- scheduler job ID/allocation ID
- worker execution counter
- thread ID or thread-pool worker identity
- whether execution happened in a fresh process or a reused long-lived worker

Recommendation: add these to diagnostic context. They are especially useful when a later audit finds that only a subset of workers or only late-in-lifetime executions diverged.

### 9. Package inventory needs provenance, not just names and versions

Severity: medium.

A dump from `importlib.metadata.distributions()` can list names and versions, but names and versions are not enough for local, editable, or direct-url installs.

Successful drift examples:

- same package version, different editable source tree
- same local version, different wheel contents
- same package metadata, changed non-Python package data
- installed package imports a native `.so` outside the distribution metadata

Recommendation: specify the `python_packages` schema to include:

- distribution name/version
- install location
- editable/direct-url metadata from `direct_url.json`
- wheel `RECORD` hashes where present
- local path and VCS commit when available
- whether files are missing hashes
- top-level import packages if cheaply available

Without this, `python_packages` is too easy to overinterpret as a complete interpreter provenance record.

### 10. Concurrent successful cache misses need explicit conflict handling

Severity: medium-high.

The design says `MetaData` is write-once per `tf_checksum`. That is correct for normal cache hits, but there is a race case: two workers can compute the same cache-missing transformation concurrently and both can succeed. If they produce different `result_checksum`s, this is not a failed computation and is directly within the primary risk class.

Recommendation:

- make normal result insertion detect conflicting successful results
- preserve both successful execution records
- move the transformation into `IrreproducibleTransformation` immediately, or otherwise create an equivalent divergence record
- avoid letting "first writer wins" discard the second successful context

This is separate from storing failed attempts.

## Secondary Issues

### Hardware cache staleness should include resource limits

The hardware cache uses hostname and boot ID, with cheap probes such as RAM total, CPU count, and kernel version. That misses changes that can affect successful numerical results or scheduling behavior without reboot:

- CPU affinity
- cpuset/cgroup CPU masks
- memory cgroup limits
- NUMA binding
- scheduler allocation shape

Some of these belong in `runtime_config` rather than `hardware`, because they are per-process/allocation rather than stable physical properties.

### Filesystem and storage behavior can be determinant for some tools

This is usually secondary, but some tools read directory entries without sorting, inspect file mtimes, use filesystem block size, or depend on case sensitivity. Seamless should push users toward explicit/canonicalized inputs, but execution records can still help audits by recording:

- working directory path
- filesystem type for temp/work directories
- temp directory path
- umask
- whether result directories were traversed in sorted order before checksumming

This is less central than command/tool/native-library provenance, but worth naming.

### Network and external services remain out of model

If user code reads "latest" from the network, queries a mutable database, or uses a license/service endpoint that changes behavior, no environment record can repair the identity model. This should remain framed as an implicit-input violation, not as a missing execution-record field.

However, for audit diagnostics it may still be useful to record proxy variables, hostname, and network namespace/container identity. Do not treat this as sufficient provenance for mutable external state.

## Recommended Additions to the Record Shape

The design should consider these additional content-addressed sub-records. They can be optional and schema-versioned independently.

### `process_environment`

Purpose: child/worker environment determinants.

Suggested fields:

- allowlisted environment variables
- redaction metadata
- locale and timezone
- `PATH` and shell identity
- temp/home/config roots
- scheduler allocation variables
- capture time: pre-execution or child environment

### `tools`

Purpose: command-line executable provenance.

Suggested fields:

- shell path/version
- resolved command paths
- declared `which` tools
- version outputs
- executable hashes where feasible
- module system state if detectable (`LOADEDMODULES`, `MODULEPATH`)

### `toolchain`

Purpose: compiled-transformer build provenance.

Suggested fields:

- compiler/linker paths and versions
- completed compilation definition
- build env vars
- Python `sysconfig` compiler/linker settings
- CFFI version and extension suffix
- linked objects and dynamic dependencies

### `native_runtime`

Purpose: loaded native library provenance.

Suggested fields:

- loaded shared libraries and paths
- build IDs/hashes for determinant libraries
- dynamic linker variables
- libc/libstdc++/libgfortran/OpenMP runtime versions
- CUDA/ROCm/cuDNN/cuBLAS/NCCL versions where relevant

### `accelerators`

Purpose: stable GPU/accelerator identity and runtime.

Suggested fields:

- GPU UUID, PCI bus ID, compute capability
- MIG identity/profile
- visible-device mapping
- driver/runtime versions
- framework deterministic/precision knobs

### `worker_context`

Purpose: audit leads for long-lived workers and scheduling.

Suggested fields:

- PID and process start time
- worker ID/address
- Dask worker address or jobserver worker ID
- scheduler job/allocation ID
- worker execution counter
- thread ID if user code runs inside a worker thread

## Dunder Persistence

The design document now notes that execution records may copy or reference dunders, but execution records are not the only durable storage for execution-only dunder values. That is important.

Execution-only dunders such as `__env__`, `__compilation__`, `__schema__`, `__header__`, `__compilers__`, and `__languages__` are needed to rerun or audit the transformation. Because `MetaData` is only written after successful cache-missing execution, those dunders need durable storage in the transformation/replay substrate independent of the execution-record body.

The execution record should still include the dunder payload or checksums as evidence of what was actually in effect for that successful run.

## Bottom Line

The current design is a good provenance substrate for Python/NumPy/conda-style computations, but it is not yet broad enough for Seamless's full execution surface.

The primary missing determinants are:

- bash child environment
- executable/tool resolution
- native shared libraries
- compiled toolchains
- container image identity
- stable GPU identity/runtime
- pre-execution capture timing
- long-lived worker context

These are not all cache-key determinants. Most should remain outside the transformation checksum under the optimistic-null model. But they should be captured as execution evidence, because they are exactly the clues an audit needs when the same `tf_checksum` succeeds with a different `result_checksum`.
