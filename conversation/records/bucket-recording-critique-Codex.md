# Codex Critique of `bucket-recording.md`

## Scope

This critique reviews [`bucket-recording.md`](bucket-recording.md) against the
primary audit risk:

> A transformation succeeds, but later succeeds again with a different result.

Determinants that mostly cause success versus failure are still relevant, but
secondary. The execution record design does not need to store failed
computation attempts in normal mode. It does, however, need to preserve enough
successful-run context to guide a later audit when a divergent successful result
is observed.

The bucket design is a useful optimization. Deduplicating stable environment
facts is the right instinct. The main risk is that the buckets can describe a
manual probe rather than the actual successful job. If that happens, the record
becomes confidently misleading: it points audit at an environment that did not
actually produce the result.

## Summary

The proposed five buckets:

- `node`
- `environment`
- `node_env`
- `queue`
- `queue_node`

cover many of the important axes identified in
[`execution-records-design.md`](../seamless-database/execution-records-design.md)
and the two prior critiques:

- CPU model, microcode, flags, NUMA, GPU UUID, OS, filesystem type
- Python package and conda inventories
- selected compiler versions and determinism variables
- loaded libraries, NumPy BLAS config, thread pools
- selected queue and cgroup/resource-limit facts

This is better than the original five-leg execution-record sketch in several
places, especially around CPU microcode, GPU UUID, NUMA, filesystem type,
container identity, and cgroup/resource limits.

The remaining gaps are mostly about timing, freshness, actual resolution, and
per-job allocation state. Those are exactly the areas that can cause a job to
succeed with different bytes while all bucket checksums still look plausible.

## Critical Findings

### 1. Manual probes can create stale, misleading records

Severity: critical.

The design says buckets are captured by manually triggered probes and reused
until the next explicit trigger. Content-addressing proves what the probe saw;
it does not prove the probe matched a later job.

Silent divergence examples:

- A conda env is modified with `pip install -e`, but no new `environment` probe
  is triggered.
- A site module changes an executable under the same path.
- A Docker tag or Singularity image path is updated.
- A queue prologue, cluster wrapper, or scheduler default changes without a
  `queue` probe.
- A GPU driver or microcode change occurs outside the operator's mental model.
- A bind-mounted tool or data directory changes while the container digest stays
  fixed.

The resulting execution record would point at old bucket checksums. That is
worse than missing data, because audit will initially trust the wrong context.

Recommendation: every successful execution record should include cheap
freshness or equivalence tokens alongside bucket checksums. Examples:

- `node`: boot ID, kernel release, CPU count, RAM total, GPU UUID list
- `environment`: `sys.executable`, `CONDA_PREFIX`, conda history mtime,
  `site-packages` mtime, image digest or image file checksum
- `queue`: fully resolved cluster/queue config hash, generated job-script hash,
  dask-jobqueue wrapper version
- `queue_node`: cgroup CPU/memory masks, allocation env vars, resource limits
- `node_env`: relevant `LD_LIBRARY_PATH`/`PATH` hash and loaded-library summary

If a token differs from the bucket metadata, the record should either trigger a
fresh probe or mark the bucket reference as stale/suspect.

### 2. Probe transformations must bypass normal transformation caching

Severity: critical.

The probe is described as "a probing script wrapped in a dummy transformation
job." If that dummy transformation has a stable `tf_checksum`, normal Seamless
caching can return the old probe result without executing the probe. Manual
recapture would then silently fail.

Recommendation: probe execution needs an explicit cache-bypass path. If that is
not available, include a nonce/request ID in the probe transformation identity
while ensuring the bucket identity itself remains the checksum of the captured
content.

This is separate from audit-mode replay. It is a requirement for the recording
mechanism itself.

### 3. Excluded per-job allocation values are real determinants

Severity: critical.

The design excludes specific CPU affinity, `CUDA_VISIBLE_DEVICES` indices, PID,
SLURM job ID, and free memory/current load to preserve probe-actual equivalence.
That is reasonable for bucket deduplication, but not for execution records.

Some excluded values can affect successful output bytes:

- CPU affinity and cpuset can change OpenMP reduction order, NUMA placement, and
  library auto-tuning.
- `CUDA_VISIBLE_DEVICES=0` maps to different physical GPUs or MIG instances
  across allocations.
- PID, job ID, and allocation ID are sometimes used by user code or tools as
  implicit seeds.
- Free memory and current load are usually secondary, but can affect algorithms
  that auto-select chunking, memory modes, or GPU workspace sizes.

Recommendation: keep these out of stable bucket checksums, but record them as
per-job diagnostic context:

- `sched_getaffinity()` mask
- cgroup cpuset and memory limit
- NUMA binding or `numactl` state where available
- `CUDA_VISIBLE_DEVICES` plus visible-index to GPU UUID/MIG UUID mapping
- PID and process start time
- scheduler job/allocation ID
- selected free-memory/load diagnostics if cheap and clearly marked transient

The audit record does not need these to be deduplicated. It needs them to be
available when a divergence is later found.

### 4. The transformation execution envelope is missing

Severity: high.

The per-job JSON points to bucket checksums, but it does not include
`metavars` or execution dunders. The execution-record design explicitly treats
metavars and dunders as load-bearing execution evidence:

- `metavars` can affect parallelization, output maxima, chunking, and scheduling
  behavior.
- `__env__` describes requested conda/Docker/which/powers settings.
- `__compilation__`, `__schema__`, `__header__`, and `__compiled__` affect
  compiled-transformer execution.
- `__languages__` and `__compilers__` can affect language/toolchain resolution.
- `__meta__` may carry execution-only control such as driver/write-remote-job
  behavior.

Recommendation: add a content-addressed `execution_envelope` bucket or explicit
record fields containing the actual applied dunders and metavars. This should
be per transformation, not per node or per queue.

### 5. `node_env` probes do not capture actual lazy native runtime state

Severity: high.

Bucket 3 records loaded shared libraries from `/proc/self/maps`, NumPy BLAS
config, `threadpoolctl`, CUDA toolkit version, and cuDNN version. This is useful
baseline information, but a probe can only observe libraries it loads.

Actual transformations may lazily load determinant libraries that the probe
does not touch:

- SciPy extension modules
- h5py/HDF5, NetCDF, GDAL, PROJ, image codecs, compression libraries
- PyTorch, TensorFlow, JAX, CUDA, cuDNN, cuBLAS, NCCL, ROCm
- compiled Seamless transformer extensions
- OpenMP runtimes loaded by a compiled extension
- subprocess tool libraries

Recommendation: split native runtime recording into two layers:

- `node_env_baseline`: probe-time baseline for common numerical stack facts
- `native_runtime_observed_post`: per-job or transformation-class-specific
  observation captured after actual execution, including loaded shared objects
  and determinant library versions

For compiled transformations, also record `ldd` or equivalent dynamic
dependency output for the built extension.

## High-Priority Findings

### 6. Compiled toolchain provenance is still under-modeled

Severity: high.

Bucket 2 captures `gcc --version`, `gfortran --version`, and `$CC`/`$CXX`/`$FC`.
That is not enough for compiled transformers. The actual compiled execution
surface includes:

- compiler absolute paths
- `g++`, `rustc`, `go`, and any registered custom language compiler
- compiler target triples
- linker path and version
- Python `sysconfig` compiler/linker settings used by CFFI
- CFFI version and extension suffix
- full compile and link command lines
- default flags from the language registry
- user overrides from `__compilation__`
- `CFLAGS`, `CXXFLAGS`, `FFLAGS`, `RUSTFLAGS`, `GOFLAGS`
- `CPATH`, `C_INCLUDE_PATH`, `CPLUS_INCLUDE_PATH`
- `LIBRARY_PATH`, `LD_LIBRARY_PATH`, `PKG_CONFIG_PATH`
- linked `libm`, `libstdc++`, `libgcc`, `libgfortran`, and OpenMP runtime

This is a primary successful-divergence surface because Seamless's compiled
transformers may use aggressive flags such as `-ffast-math`, `-march=native`,
and OpenMP. Different compiler versions, CPU feature sets, linker choices, and
OpenMP runtimes can all produce successful but different numerical results.

Recommendation: add a transformation-specific `toolchain` or
`compilation_context` checksum populated for compiled transformations and null
for Python/bash transformations.

### 7. The queue bucket is too underspecified

Severity: high.

Bucket 4 explicitly says `TODO: enumerate these parameters`. That TODO is
load-bearing. Queue behavior is not just "queue name."

Potential successful-divergence determinants include:

- resolved `clusters.yaml` and profile/project overrides
- generated job script content
- dask-jobqueue parameters
- scheduler account/partition/QOS/defaults
- `job_script_prologue`
- module loads in prologue
- conda activation behavior
- worker process/thread counts
- Dask worker resources and nanny settings
- dask/distributed/dask-jobqueue versions
- site wrapper scripts

Recommendation: store the fully resolved queue configuration and generated job
script content or hash. Do not rely on a queue label. Include the Dask and
dask-jobqueue package versions in the queue or environment record.

### 8. Effective child/process environment is not captured

Severity: high.

Bucket 2 records selected environment variables from activation scripts, and
Bucket 5 records selected variables inside a queue job. But bash and subprocess
transformations depend on the actual child environment passed to `/bin/bash` or
other tools.

Important variables not comprehensively covered:

- `PATH`, `SHELL`, `BASH_ENV`
- `LD_LIBRARY_PATH`, `LD_PRELOAD`, `DYLD_LIBRARY_PATH`
- `LC_ALL`, `LANG`, `LANGUAGE`, `LC_NUMERIC`, `LC_COLLATE`
- `TZ`
- `HOME`, `XDG_CONFIG_HOME`, `XDG_CACHE_HOME`
- `TMPDIR`, `TEMP`, `TMP`
- `PYTHONPATH`, `PYTHONNOUSERSITE`, `PYTHONHASHSEED`
- `R_LIBS`, `PERL5LIB`, `JAVA_HOME`, `CLASSPATH`
- `HDF5_PLUGIN_PATH`, `GDAL_DATA`, `PROJ_LIB`
- `OMP_SCHEDULE`, `OMP_PROC_BIND`, `OMP_PLACES`
- `GOMP_CPU_AFFINITY`, `GOMP_SPINCOUNT`, `KMP_AFFINITY`
- `CUDA_LAUNCH_BLOCKING`, `NVIDIA_TF32_OVERRIDE`
- framework determinism/precision variables
- scheduler variables such as `SLURM_CPUS_PER_TASK`

Recommendation: add `process_environment_pre` or `child_environment` with an
allowlist and redaction policy. For bash, this should reflect the exact
environment passed to `Popen`, not a post hoc worker environment snapshot.

### 9. External command and tool provenance is missing

Severity: high for bash/CLI transformations.

Package inventories do not tell an auditor which executable actually ran.
Successful divergences can be caused by `PATH` resolving to a different binary,
site modules changing in place, coreutils behavior changes, R/Java/Perl tool
differences, or mutable custom tools.

Recommendation: add a `tools` sub-record for bash/CLI transformations:

- shell path and version, at least `/bin/bash --version`
- command words resolved through `PATH`
- declared `Environment.set_which()` tools and their actual resolution
- absolute paths
- executable hashes where feasible
- `--version` or equivalent output where cheap and safe
- module-system state: `LOADEDMODULES`, `MODULEPATH`, and `module list` output
  if available

This record can be best-effort. It should distinguish "not captured" from "not
present."

### 10. Container identity is split across the wrong buckets

Severity: medium-high.

Container detection currently lives in Bucket 1, while Docker image digest lives
in Bucket 2. That split is awkward:

- A container image is not a node property.
- A container can expose mutable host bind mounts.
- Singularity/Apptainer image paths can be mutable unless hashed.
- Kubernetes/podman/containerd identity may not be visible through Docker
  inspect.
- A worker may be inside a container while compiling/linking against host-mounted
  paths.

Recommendation: make container/runtime either its own bucket or a clearly
versioned sub-record:

- runtime: Docker, podman, Singularity/Apptainer, Kubernetes, etc.
- image name/tag and immutable digest or image file checksum
- container ID
- root filesystem/overlay identity
- bind mounts and their read-only/read-write status
- namespace IDs and cgroup identity
- explicit capture errors, e.g. `"image_digest": null` with reason

### 11. GPU runtime details need actual allocation mapping

Severity: high for GPU workflows, medium otherwise.

The node bucket captures useful stable GPU facts: model, UUID, memory, compute
capability, driver, ECC, and persistence mode. But the actual job needs a
mapping from process-visible devices to stable physical devices.

Successful divergences can be caused by:

- `CUDA_VISIBLE_DEVICES=0` mapping to a different GPU UUID
- MIG instance/profile differences
- different PCI bus IDs with same model
- CUDA runtime/toolkit mismatch
- cuDNN/cuBLAS/NCCL/ROCm differences
- TF32 and deterministic algorithm settings
- MPS or GPU clock/power state in rarer cases

Recommendation: record per job:

- `CUDA_VISIBLE_DEVICES`
- visible index to GPU UUID/PCI bus/MIG UUID mapping
- CUDA driver and runtime versions
- loaded cuDNN/cuBLAS/NCCL/ROCm versions where available
- framework deterministic and precision knobs when libraries are loaded

## Medium-Priority Findings

### 12. Long-lived worker state is diagnostically important

Severity: medium-high.

Workers in `spawn`, `remote: jobserver`, and `remote: daskserver` can execute
many transformations in the same process. User code can mutate process state:

- `os.environ`
- current working directory
- `sys.path`
- imported modules
- loaded native libraries
- threadpool limits
- FPU/MXCSR rounding, FTZ, and DAZ state
- global RNG state
- native library global state

Execution records cannot fully capture arbitrary process state. But they can
provide audit leads.

Recommendation: add per-job worker context:

- PID and process start time
- worker ID/address
- Dask worker address or jobserver worker ID
- scheduler job/allocation ID
- worker execution counter
- thread ID or worker-thread identity
- fresh process vs reused long-lived worker
- current working directory
- temp directory root
- umask
- FPU/MXCSR state where available

### 13. Capture timing should be explicit

Severity: medium-high.

Some facts must be captured before execution; others only become visible after
execution.

Pre-execution examples:

- child environment
- cwd, tempdir, umask
- affinity/cgroup/device visibility
- threadpool limits
- FPU/MXCSR state

Post-execution examples:

- loaded shared libraries after lazy imports
- imported modules
- native extension dependencies
- GPU memory peak
- resource accounting

Recommendation: distinguish `pre`, `post`, and `probe` capture phases in every
bucket/sub-record schema. Do not allow a post-run snapshot to stand in for the
environment actually passed to a bash subprocess.

### 14. Package inventory needs provenance, not just package names

Severity: medium.

`importlib.metadata.distributions()` is a good base, but it is easy to
overinterpret. Names and versions do not capture:

- editable installs
- direct-url installs
- local path installs
- VCS commit
- changed source trees under the same version
- missing wheel `RECORD` hashes
- package data changes
- bundled native `.so` files

Recommendation: define the `python_packages` schema to include:

- distribution name/version
- install location
- `direct_url.json`
- editable/local/VCS metadata where available
- wheel `RECORD` hashes where present
- missing-hash indicators
- native extension file paths and hashes/build IDs where feasible

### 15. Filesystem behavior can be determinant for some tools

Severity: medium.

The node bucket records filesystem types for key mount points, which is useful.
For bash/CLI tools, additional details can matter:

- working directory path
- temp directory path
- result directory traversal order
- case sensitivity
- timestamp granularity
- file mtimes if tools inspect them
- whether output directory entries are sorted before checksumming

Recommendation: record cwd/temp paths per job, and document whether Seamless
canonicalizes directory output traversal before computing result checksums.

### 16. Network and external services remain outside the identity model

Severity: medium, mostly policy.

If user code reads from "latest" URLs, mutable databases, license servers, or
service endpoints, no environment record can turn that into a valid cache key.
That is an implicit-input violation, not just a missing bucket field.

For audit diagnostics, it can still help to record:

- proxy variables
- hostname and network namespace/container identity
- relevant service endpoint environment variables after redaction

This should be framed explicitly as diagnostic context, not sufficient
provenance for mutable external state.

## Secondary Issues

### Resource accounting misses child-process cases

The design says resource accounting wraps `run.py:run_transformation_dict()` and
uses `RUSAGE_SELF`, with a note to check `RUSAGE_CHILDREN` for spawn. Bash
transformations also run child processes, and compiled/native libraries can
spawn threads or subprocesses. This mainly affects eviction/cost modeling, but
it should be corrected.

Recommendation: account for child processes consistently for bash and spawn,
and document limitations for thread/native-library accounting.

### `datetime.utcnow()` should be timezone-aware

The design uses `datetime.datetime.utcnow()` for timestamps. Prefer
timezone-aware UTC timestamps, e.g. `datetime.now(timezone.utc).isoformat()`.
This is not a determinant gap, but it avoids ambiguous timestamp handling in
audit tooling.

### Bucket labels should not imply identity

The design correctly says labels are operational convenience and content
checksum is identity. The record should preserve both:

- label used to select or trigger the probe
- checksum of captured content

This matters when two labels intentionally converge to the same content or one
label changes content over time.

## Recommended Record Shape Changes

Keep the five buckets, but add actual-job evidence around them.

Suggested checksum fields:

- `node`
- `environment`
- `node_env_baseline`
- `queue`
- `queue_node`
- `execution_envelope`
- `process_environment_pre`
- `tools` for bash/CLI transformations
- `toolchain` for compiled transformations
- `native_runtime_observed_post`
- `container_runtime` if not folded into `environment`

Suggested inline per-job fields:

- `tf_checksum`
- `result_checksum`
- `seamless_version`
- `execution_mode`
- `started_at`
- `finished_at`
- `hostname`
- `worker_id`
- `worker_pid`
- `worker_process_start_time`
- `worker_execution_counter`
- `thread_id`
- `scheduler_job_id`
- `affinity_mask`
- `cgroup_cpuset`
- `cuda_visible_devices`
- `visible_gpu_mapping`
- `cwd`
- `tmpdir`
- `umask`
- `bucket_freshness_tokens`
- resource accounting fields

The exact field set can be schema-versioned and best-effort. The key rule is
that audit must be able to tell whether the bucket facts plausibly matched the
actual successful job.

## Bottom Line

Bucket recording is a good deduplication strategy, but it should not be the only
source of execution evidence. A probe is evidence about the probe. A successful
execution record must still contain enough cheap actual-job context to verify
that the probe was applicable.

The strongest version of this design is:

- stable buckets for expensive, reusable baseline facts
- transformation-specific buckets for dunders, metavars, tools, and toolchains
- per-job inline diagnostics for freshness, allocation, worker identity, and
  effective runtime state
- explicit `pre`, `post`, and `probe` capture phases

That preserves the performance benefit of bucket reuse without discarding the
clues needed when the same `tf_checksum` later succeeds with a different
`result_checksum`.
