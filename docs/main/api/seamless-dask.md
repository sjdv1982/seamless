# seamless-dask

`seamless-dask` is the Dask integration layer for the [Seamless](https://github.com/sjdv1982/seamless) ecosystem. It submits Seamless transformations to a Dask cluster, manages worker pools inside Dask workers, and provides a supervised cluster launcher for HPC environments. It is the distributed-execution alternative to the simpler single-machine `seamless-jobserver`.

**This is an internal infrastructure package.** User workflow code never imports `seamless-dask` directly — the user-facing API (`direct`, `delayed`) lives in `seamless-transformer`. When a Dask backend is configured, `seamless-config` and `seamless-remote` wire everything up behind the scenes.

## Core components

### SeamlessDaskClient

Wraps a `distributed.Client` with Seamless-specific logic: buffer caching, transformation submission, fat/thin checksum management, and cache pruning. Registered globally via `set_seamless_dask_client()` so that `seamless-transformer` can discover it.

### TransformationDaskMixin

A mixin class that extends `seamless-transformer`'s `Transformation` with Dask execution. When a `SeamlessDaskClient` is registered and a transformation's `compute()` is called:

1. Fast-path: check the Seamless database cache (via `seamless-remote`) before submitting anything.
2. Request a permission token from the throttle manager.
3. Submit the transformation to the Dask cluster.
4. Store the result back in the cache.

If the cluster is at capacity, permission requests may be denied; when remote execution is optional, the caller retries and may eventually fall back to local execution.

### Worker plugin

`SeamlessWorkerPlugin` (a Dask `WorkerPlugin`) runs inside each Dask worker. On setup it:

- Spawns a pool of Seamless worker processes (via `seamless-transformer`)
- Configures remote clients (via `seamless-config`) so workers can reach the hashserver and database
- Registers permission-counter resources with the Dask scheduler

### Permission manager

An anti-deadlock throttle that prevents the Dask cluster from over-committing. Tracks a capacity counter based on `TRANSFORMATION_THROTTLE × workers`. When at capacity, batches new requests per 10-second epoch and grants based on system load. This prevents nested transformations from starving the cluster.

### Dummy scheduler

An in-process Dask scheduler for development and testing. Creates a `Scheduler` + N `Worker` instances in a background thread, useful for local runs without a full cluster.

---

## Relation to the Seamless ecosystem

```text
    seamless-transformer                (user-facing API: direct, delayed)
        │
        │  delegate job
        ▼
    seamless-remote
        │  daskserver_remote
        ▼
    seamless-dask-wrapper              ◄── CLI from this package
        │
        │  Dask scheduler
        ▼
    Dask workers
        │  SeamlessWorkerPlugin
        │  spawns seamless-transformer workers
        │
        ▼  nested transformations call seamless-remote again
```

The `seamless-dask-wrapper` CLI is the entry point that `seamless-remote`'s `daskserver_remote` talks to. Inside each Dask worker, the full Seamless stack runs again — `seamless-transformer` dispatches work to its own worker processes, and calls `seamless-remote` for buffer resolution and cache operations. This recursion is what makes nested transformations work.

---

## CLI: seamless-dask-wrapper

The only CLI script. It launches and supervises a Dask cluster:

1. Waits for a JSON status file written by the caller (typically `seamless-config` via `remote-http-launcher`).
2. Reads cluster parameters from the status file.
3. Evaluates a "cluster string" (`MODULE::SYMBOL`) to instantiate the cluster — supports `dask.distributed.LocalCluster` and `dask_jobqueue` backends (SLURMCluster, OARCluster, PBSCluster, etc.).
4. Launches the cluster with adaptive scaling.
5. Writes the scheduler and dashboard ports back to the status file.
6. Monitors activity and shuts down after an inactivity timeout.

### Status file

`seamless-dask-wrapper` receives all its configuration through a JSON **status file**, following the protocol defined by `remote-http-launcher`. The launcher creates the file with `"status": "starting"` and a `"parameters"` dict containing cluster configuration. The wrapper polls for this file on startup, reads the parameters, picks free ports for the scheduler and dashboard, launches the cluster, and then writes back to the same file with `"status": "running"` and the selected ports. If startup fails, it writes `"status": "failed"` instead. On clean shutdown it deletes the file.

This is a general-purpose handshake: the launcher doesn't need to know anything about Dask — it just writes parameters and waits for `"status"` to change. The wrapper doesn't need to know who launched it — it just reads the file. The `"parameters"` dict inside the status file carries the cluster configuration described below.

### Key parameters (from status file)

| Category | Parameters |
| --- | --- |
| Job | `walltime`, `cores`, `memory`, `tmpdir`, `partition`, `project`, `job_extra_directives` |
| Scheduler | `unknown-task-duration`, `target-duration`, `internal-port-range`, `lifetime` |
| Worker | `transformation_throttle` (default 3), `dask-resources` |
| Cluster | `interactive`, `maximum_jobs`, `extra_dask_config`, `timeout` |

Worker threads are auto-set to `cores × transformation_throttle` to match Seamless worker pool sizing.

### Parameter details

#### Job parameters

These parameters configure the HPC job that each Dask worker runs in. Most map to `dask_jobqueue` cluster constructor options.

- **`walltime`** — Passed directly to `dask_jobqueue` as `walltime`.
- **`cores`** — Multiplied by `transformation_throttle` to produce `job_cores`, which is passed to `dask_jobqueue` as `cores`. The original value controls how many Seamless worker processes are spawned per Dask worker.
- **`memory`** — Passed directly to `dask_jobqueue` as `memory`.
- **`tmpdir`** — Seamless-specific name. Mapped to two Dask config keys: `local-directory` and `temp-directory`. Defaults to `/tmp`.
- **`partition`** — Renamed to `queue` when passed to `dask_jobqueue` (matching its terminology for SLURM partitions / OAR queues).
- **`project`** — Passed directly to `dask_jobqueue` as `project` (the scheduler accounting/billing project).
- **`job_extra_directives`** — Passed to `dask_jobqueue` as `job-extra-directives` (hyphenated). Wrapped with `ensure_list()` so a single string is accepted.

#### Scheduler parameters

These tune the Dask scheduler and worker lifecycle.

- **`unknown-task-duration`** — Passed directly to Dask config as `distributed.scheduler.unknown-task-duration`. Default: `"1m"`.
- **`target-duration`** — Passed directly to Dask config as `distributed.scheduler.target-duration`. Also used to compute adaptive scaling intervals. Default: `"10m"`.
- **`internal-port-range`** — Seamless-specific. Normalized into a port range string and passed as `--worker-port` and `--nanny-port` worker args, plus Dask config keys `distributed.worker.port` and `distributed.nanny.port`.
- **`lifetime`** — Passed to Dask config as `distributed.worker.lifetime.duration`, but the value is computed: `walltime − lifetime-stagger − grace_period`. Set to `None` when `maximum_jobs == 1` (a single worker has no need for rolling restarts).

#### Worker parameters

These control Seamless-specific behavior inside each Dask worker.

- **`transformation_throttle`** — How many concurrent Seamless transformations each worker process handles. Exported as the environment variable `SEAMLESS_WORKER_TRANSFORMATION_THROTTLE` into worker job scripts. Also determines worker thread count (`cores × transformation_throttle`). Default: `3`.
- **`dask-resources`** — Custom Dask resource annotations for workers, passed to `distributed.worker.resources`. In exclusive mode, automatically includes `{"S": 1.0}` for resource-aware scheduling. The `"S"` resource value is also used as a scaling factor for adaptive target duration.

#### Cluster parameters

These govern the cluster lifecycle managed by `seamless-dask-wrapper`.

- **`interactive`** — When `true`, the cluster keeps at least one worker alive even when idle (minimum jobs = 1 instead of 0). Also prevents premature shutdown while tasks are still processing.
- **`maximum_jobs`** — Maximum number of Dask workers for adaptive scaling. Renamed to `maximum` when passed to Dask's adaptive scaling class. When set to `1`, worker lifetime rotation is disabled. Default: `1`.
- **`extra_dask_config`** — Escape hatch: a dict of arbitrary Dask config keys and values, merged directly into the Dask configuration. Useful for tuning settings not exposed as dedicated parameters.
- **`timeout`** — Inactivity timeout (in seconds) after which `seamless-dask-wrapper` shuts down the cluster. Not a Dask concept — this is managed by the wrapper's own monitoring loop.

### SLURM examples

These examples show minimal status file parameters and the SLURM job script that `dask_jobqueue.SLURMCluster` generates from them. Both request 24 cores, 54 GB memory, and 1 hour of walltime on the `all` partition.

#### Pure Dask (`pure_dask: true`)

This mode uses Seamless infrastructure without using Seamless itself. You get `seamless-dask-wrapper` (controlled by `seamless-config`) as a managed Dask cluster launcher — with status-file handshake, adaptive scaling, port management, and inactivity timeout — but the workers are plain Dask workers. No `SeamlessWorkerPlugin`, no transformation throttle, no `seamless-core` or `seamless-transformer` involvement. Your code talks to the `distributed.Client` directly.

This is useful when you already have Dask workloads and want to take advantage of Seamless's cluster lifecycle management on HPC without adopting the Seamless computation model.

The wrapper passes `cores` through unchanged and defaults to 2 worker threads. No Seamless-specific environment variables are injected.

**Status file parameters:**

```json
{
    "parameters": {
        "pure_dask": true,
        "cores": 24,
        "memory": "54000MB",
        "walltime": "01:00:00",
        "partition": "all",
        "maximum_jobs": 4
    }
}
```

**Generated SLURM job script:**

```bash
#!/usr/bin/env bash

#SBATCH --job-name=dask-worker
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=24
#SBATCH --mem=54000M
#SBATCH --time=01:00:00
#SBATCH --partition=all

export DASK_DISTRIBUTED__WORKER__DAEMON=False
export DASK_DISTRIBUTED__SCHEDULER__UNKNOWN_TASK_DURATION=1m
export DASK_DISTRIBUTED__SCHEDULER__TARGET_DURATION=10m
export PYTHON_CPU_COUNT=$SLURM_JOB_CPUS_PER_NODE

dask worker \
    --nthreads 2 \
    --name worker-$SLURM_JOB_ID \
    tcp://<scheduler_ip>:<scheduler_port>
```

24 SLURM cores, 2 Dask worker threads. Standard Dask behaviour — most cores sit idle unless your tasks release the GIL or you set `worker_threads` explicitly.

#### Seamless Dask (default)

Without `pure_dask`, the wrapper multiplies `cores × transformation_throttle` (default 3) to determine both the SLURM core request and the worker thread count. This matches the Seamless worker pool: each of the 24 worker processes handles up to 3 concurrent transformations, so 72 threads are needed.

**Status file parameters:**

```json
{
    "parameters": {
        "cores": 24,
        "memory": "54000MB",
        "walltime": "01:00:00",
        "partition": "all",
        "maximum_jobs": 10,
        "interactive": true,
        "tmpdir": "/tmp"
    }
}
```

**Generated SLURM job script:**

```bash
#!/usr/bin/env bash

#SBATCH --job-name=dask-worker
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=72
#SBATCH --mem=54000M
#SBATCH --time=01:00:00
#SBATCH --partition=all

export SEAMLESS_DASK_QUEUE_EXCLUSIVE=0
export SEAMLESS_WORKER_TRANSFORMATION_THROTTLE=3
export DASK_DISTRIBUTED__WORKER__DAEMON=False
export DASK_DISTRIBUTED__SCHEDULER__UNKNOWN_TASK_DURATION=1m
export DASK_DISTRIBUTED__SCHEDULER__TARGET_DURATION=10m
export DASK_DISTRIBUTED__WORKER__LIFETIME__DURATION=55m
export DASK_DISTRIBUTED__WORKER__LIFETIME__STAGGER=4m
export PYTHON_CPU_COUNT=$SLURM_JOB_CPUS_PER_NODE

dask worker \
    --nthreads 72 \
    --local-directory /tmp \
    --name worker-$SLURM_JOB_ID \
    tcp://<scheduler_ip>:<scheduler_port>
```

72 SLURM cores (`24 × 3`), 72 worker threads, lifetime rotation enabled (55 minutes = 60 min walltime − 4 min stagger − 1 min grace). The `SeamlessWorkerPlugin` running inside this worker will spawn 24 Seamless worker processes, each handling up to 3 transformations concurrently.

---

## Installation

```bash
pip install seamless-dask
```

Requires Python >= 3.10. Dependencies: `dask`, `distributed`, `dask_jobqueue`, `bokeh>=3.1.0`, `seamless-core`, `seamless-config`, `seamless-remote`, `seamless-transformer`.
