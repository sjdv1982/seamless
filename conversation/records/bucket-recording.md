# Bucket-Based Environment Recording for Seamless Execution Records

## Background

Seamless caching rests on an optimistic null hypothesis: for any given transformation, the scientifically meaningful result is invariant under variation in the execution environment (hardware, numerical libraries, time, host, parallelization details). The execution record exists to make that null falsifiable later, even though the normal cache path never falsifies it.

Environment capture is expensive (seconds for a full introspection), but the execution context is stable across many transformation jobs that share the same hardware, software environment, and queue configuration. The recording system exploits this by splitting the environment into five independently cacheable buckets, each captured once via a manually triggered *probe* (i.e. a probing script wrapped in a dummy transformation job) and reused by checksum for all subsequent jobs under the same conditions.

## Design principles

- **Content-addressed identity.** Bucket labels (hostname, conda env name, queue name) are operational convenience for triggering probes. The actual identity is always the content checksum of the captured data. Two probes executed on identical hardware produce the same bucket-1 checksum. Two probes executed in the same conda env produce the same bucket-2 checksum.
- **Manual triggers only.** Seamless never auto-detects staleness or auto-recaptures. The operator explicitly triggers a probe; the result is cached and reused until the next explicit trigger.
- **Probe-actual equivalence.** The probe must produce the same checksum as a capture during an actual job. This means certain ephemeral values (CPU core placement, GPU device indices , PIDs; as opposed to CPU/GPU device details themselves) are excluded from checksummed content. If they matter for computation, that is an accepted limitation.
- **Redundant capture of shared concerns.** Values that can be set in multiple places (e.g., `OMP_NUM_THREADS` in both conda activation scripts and queue job prologues) are captured in every bucket where they could originate. Audit resolves precedence; the record preserves the facts.
- **Canonical serialization.** All sub-dicts use Seamless's "plain" celltype serialization to ensure byte-identical buffers for semantically identical content, enabling correct deduplication.

## Bucket definitions

### Bucket 1: Node

Cache key label: hostname (or node identifier).
Trigger: manual, when hardware changes or a new node is provisioned.

Captures stable physical properties of a specific machine.

| Field | Source | Notes |
|-------|--------|-------|
| CPU model | `/proc/cpuinfo` | |
| CPU microcode version | `/proc/cpuinfo` | Affects instruction behavior via Intel/AMD errata patches |
| CPU flags (full) | `/proc/cpuinfo` | AVX2, AVX-512 subsets (avx512f, avx512bw, ...), FMA, SSE levels |
| Physical/logical core count | `psutil` | |
| RAM total | `psutil.virtual_memory().total` | |
| NUMA topology | `/sys/devices/system/node/node*/cpulist` | Per-node core mapping |
| GPU model | `pynvml` (`nvmlDeviceGetName`) | Per GPU |
| GPU UUID | `pynvml` (`nvmlDeviceGetUUID`) | Identifies the specific physical GPU |
| GPU memory | `pynvml` (`nvmlDeviceGetMemoryInfo`) | Per GPU |
| GPU compute capability | `pynvml` (`nvmlDeviceGetCudaComputeCapability`) | Per GPU |
| GPU driver version | `pynvml` (`nvmlSystemGetDriverVersion`) | |
| OS/kernel version | `platform.release()`, `platform.machine()` | |
| Distribution | `/etc/os-release` | |
| Container identity | `/.dockerenv`, `/run/.containerenv`, `$SINGULARITY_CONTAINER`, `$APPTAINER_CONTAINER` | Image digest from overlay root in `/proc/self/mountinfo` where available |
| Filesystem types | `/proc/self/mountinfo` | For key mount points (working dir, tmp, buffer dirs) |
| Transparent hugepages | `/sys/kernel/mm/transparent_hugepage/enabled` | |
| ASLR | `/proc/sys/kernel/randomize_va_space` | |
| Overcommit policy | `/proc/sys/vm/overcommit_memory` | |
| Byte order | `sys.byteorder` | Practically always `'little'`; load-bearing for binary data |
| GPU ECC mode | `pynvml` (`nvmlDeviceGetEccMode`) | Per GPU. ECC on/off affects both performance and silent error behavior |
| GPU persistence mode | `pynvml` (`nvmlDeviceGetPersistenceMode`) | Per GPU. Affects driver initialization latency and GPU state retention |

### Bucket 2: Environment

Cache key label: environment identifier (conda prefix, later Docker image ID, Singularity container path).
Trigger: manual, when the environment is created or modified (`pip install`, `conda install`, image rebuild).

Captures what is installed, independent of which machine runs it.

| Field | Source | Notes |
|-------|--------|-------|
| Python version | `sys.version_info` | Major.minor.micro; affects bytecode, hash behavior, float formatting |
| Python packages | `importlib.metadata.distributions()` | Unified view across conda and pip |
| Conda env export | `conda env export` (subprocess) | Captures C library context, channels, build strings. Null when conda not detected |
| `gcc` version | `gcc --version` | |
| `gfortran` version | `gfortran --version` | |
| `$CC`, `$CXX`, `$FC` | `os.environ` | Compiler selection env vars |
| Locale | `locale.getlocale()` | Affects sorting, string collation, number formatting |
| Timezone | `time.tzname`, `$TZ` | Affects timestamp-dependent code |
| `PYTHONHASHSEED` | `os.environ` | As set in activation scripts |
| `CUBLAS_WORKSPACE_CONFIG` | `os.environ` | As set in activation scripts |
| `TF_DETERMINISTIC_OPS` | `os.environ` | As set in activation scripts |
| `PYTORCH_CUDA_ALLOC_CONF` | `os.environ` | As set in activation scripts |
| Docker image digest | `docker inspect --format='{{.Id}}'` or registry API | For Docker-based environments. Resolves mutable tags (`latest`) to content-addressed image identity |

### Bucket 3: Node x Environment

Cache key label: (node checksum, environment checksum).
Trigger: manual, when either parent changes.

Captures what emerges from running this environment on this hardware: which libraries are actually loaded and how they bind to hardware features.

| Field | Source | Notes |
|-------|--------|-------|
| Loaded shared libraries | `/proc/self/maps` | Actual `.so` files mapped into the process (libopenblas, libmkl_rt, libcuda, etc.) |
| NumPy BLAS config | `numpy.show_config()` | Which BLAS backend NumPy actually binds to at runtime |
| Thread pool info | `threadpoolctl.threadpool_info()` | Active thread pools and their backing libraries |
| CUDA toolkit version | `torch.version.cuda` or `$CUDA_HOME/version.txt` | Depends on both installed packages and driver |
| cuDNN version | `torch.backends.cudnn.version()` | Depends on both installed packages and driver |

### Bucket 4: Queue

Cache key label: queue name within a cluster.
Trigger: manual, when the queue configuration changes in `clusters.yaml`.

The content is queue parameters (in principle SLURM/OAR parameters) that are controlled by Seamless:
clusters.yaml => seamless-dask wrapper.py => dask_jobqueue => SLURM/OAR
(TODO: enumerate these parameters!)
Related to: cores, memory, walltime, partition, exclusive, job_extra_directives, job_script_prologue, conda, worker_threads, processes, etc.
Will need to be updated when cloud support is added to Seamless.
` |  |

### Bucket 5: Queue x Node

Cache key label: (queue checksum, node checksum).
Trigger: manual, by submitting a probe job to this queue that lands on this node.

Captures the invariant shape of what the queue's job script produces on this specific node. Only values that are deterministic for the (queue, node) pair are included.

| Field | Source | Notes |
|-------|--------|-------|
| `OMP_NUM_THREADS` | `os.environ` (inside job) | As resolved by job prologue and SLURM |
| `MKL_NUM_THREADS` | `os.environ` (inside job) | As resolved by job prologue and SLURM |
| `OPENBLAS_NUM_THREADS` | `os.environ` (inside job) | As resolved by job prologue and SLURM |
| Allocated core count | `$SLURM_JOB_CPUS_PER_NODE` or equivalent | Count, not placement |
| Allocated GPU count | SLURM/OAR allocation info | Count, not specific device indices |
| cgroup memory limit | `/sys/fs/cgroup/memory.max` (v2) or `/sys/fs/cgroup/memory/memory.limit_in_bytes` (v1) | |
| Resource limits | `resource.getrlimit()` | `RLIMIT_AS`, `RLIMIT_NOFILE`, `RLIMIT_NPROC`, `RLIMIT_STACK` |
| `PYTHONHASHSEED` | `os.environ` (inside job) | As set by job script prologue |
| `CUBLAS_WORKSPACE_CONFIG` | `os.environ` (inside job) | As set by job script prologue |
| Other determinism env vars | `os.environ` (inside job) | As set by job script prologue |

## Recorded separately (per-job, not cached)

These values are unique to each job execution and cannot be cached across jobs.

### Timestamps

| Field | Source | Notes |
|-------|--------|-------|
| `started_at` | `datetime.datetime.utcnow()` | Wall-clock timestamp before execution |
| `finished_at` | `datetime.datetime.utcnow()` | Wall-clock timestamp after execution |

### Resource accounting

Measured by wrapping the execution path in `run.py:run_transformation_dict()`.

| Field | Source | Notes |
|-------|--------|-------|
| `wall_time_seconds` | `time.perf_counter()` delta | Most precise wall-clock timer |
| `cpu_time_user_seconds` | `resource.getrusage(RUSAGE_SELF).ru_utime` delta | User-mode CPU time. For `spawn` mode, also check `RUSAGE_CHILDREN` |
| `cpu_time_system_seconds` | `resource.getrusage(RUSAGE_SELF).ru_stime` delta | Kernel-mode CPU time |
| `memory_peak_bytes` | `/proc/self/status` VmPeak, or `resource.getrusage().ru_maxrss * 1024` | Peak resident memory. `ru_maxrss` is in KB on Linux |
| `gpu_memory_peak_bytes` | `torch.cuda.max_memory_allocated()` or `pynvml` queries | Peak GPU memory during execution. Null when no GPU used |
| `input_total_bytes` | Sum of input buffer sizes | Total bytes of transformation inputs |
| `output_total_bytes` | `len(result_buffer)` | Total bytes of result |
| `compilation_time_seconds` | `time.perf_counter()` around `build_compiled_module()` | For compiled transformers only. Null for Python/bash |

### Execution context

| Field | Source | Notes |
|-------|--------|-------|
| `hostname` | `socket.gethostname()` | Which node actually ran this job |
| `retry_count` | `worker.py:_dispatch` retry tracking | Number of worker process retries before success (normally 0) |

## Excluded entirely

These values are ephemeral and vary between jobs on the same node under the same queue. Including them would break probe-actual equivalence:

| Field | Reason for exclusion |
|-------|---------------------|
| `sched_getaffinity()` specific cores | SLURM assigns different cores each job |
| `CUDA_VISIBLE_DEVICES` specific indices | SLURM assigns different GPU indices each job |
| PID | Ephemeral |
| SLURM job ID | Ephemeral |
| Free memory / current load | Transient system state |

## Per-job record structure

Each transformation job record carries checksums pointing to the relevant bucket buffers, plus per-job scalars:

```json
{
  "schema_version": 1,
  "checksum_fields": ["node", "environment", "node_env", "queue", "queue_node"],

  "tf_checksum":     "<checksum>",
  "result_checksum": "<checksum>",

  "node":            "<bucket-1-checksum>",
  "environment":     "<bucket-2-checksum>",
  "node_env":        "<bucket-3-checksum>",
  "queue":           "<bucket-4-checksum>",
  "queue_node":      "<bucket-5-checksum>",

  "seamless_version": "0.x.y",
  "execution_mode":   "daskserver",

  "wall_time_seconds":        13.1,
  "cpu_time_user_seconds":    11.8,
  "cpu_time_system_seconds":  0.6,
  "memory_peak_bytes":        1234567890,
  "gpu_memory_peak_bytes":    null,
  "input_total_bytes":        4567890,
  "output_total_bytes":       123456,
  "compilation_time_seconds": null,

  "started_at":  "2026-04-15T10:23:00Z",
  "finished_at": "2026-04-15T10:23:13Z",
  "hostname":    "gros-42.nancy.grid5000.fr",
  "retry_count": 0
}
```

The full environment context is reconstituted by fetching the buffers for each checksum from the buffer cache.
