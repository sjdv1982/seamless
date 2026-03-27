# HPC specifics

This guide covers Seamless deployment on HPC clusters with SLURM or OAR schedulers. It assumes you have read [Remote execution](remote.md) and have a working daskserver cluster definition.

## The big picture

Seamless does not make a great difference between a HPC cluster config and a local cluster config. In both cases, Seamless cluster services (hashserver, database, Dask scheduler) are launched, and are available to the local machine over the network (potentially via SSH tunnel). Dask will accept both Python transformations and `seamless-run` commands, no matter where it runs. If it runs on an HPC frontend, then `seamless-run` commands will run directly on a compute node, with input files uploaded automatically.

## Queue definitions

HPC queue definitions live inside the cluster entry in `~/.seamless/clusters.yaml`, under the `queues` key. Each queue entry maps to a `dask_jobqueue` cluster constructor call (SLURMCluster, OARCluster, etc.), plus Seamless-specific lifecycle parameters.

A minimal SLURM cluster with two queues:

```yaml
hpc:
  tunnel: true
  type: slurm
  frontends:
    - hostname: login.hpc.example
      hashserver:
        bufferdir: /scratch/seamless/buffers
        conda: hashserver
        network_interface: 0.0.0.0
        port_start: 60100
        port_end: 60199
      database:
        database_dir: /scratch/seamless/db
        conda: seamless-database
        network_interface: 0.0.0.0
        port_start: 60200
        port_end: 60299
      daskserver:
        network_interface: 0.0.0.0
        port_start: 60300
        port_end: 60399

  default_queue: standard
  queues:
    standard:
      conda: seamless-dask
      walltime: "02:00:00"
      cores: 16
      memory: 64000MB
      tmpdir: /scratch/tmp
      maximum_jobs: 20
      unknown_task_duration: 1m
      target_duration: 10m
      lifetime_stagger: 4m

    highmem:
      TEMPLATE: standard      # inherit all fields from 'standard', then override
      cores: 4
      memory: 256000MB
      maximum_jobs: 4
```

The `TEMPLATE` key lets a queue inherit all parameters from another queue, then override specific fields. This avoids repeating common settings.

### Key parameters

| Parameter | Meaning |
|---|---|
| `hostname` | SSH hostname. Must be reachable without password |
| `walltime` | Maximum wall-clock time for each Dask worker job |
| `cores` | CPU cores per worker job (controls Seamless worker pool size per Dask worker) |
| `memory` | Memory per worker job |
| `tmpdir` | Local scratch directory on compute nodes |
| `maximum_jobs` | Maximum number of concurrent Dask worker jobs (adaptive scaling upper bound) |
| `unknown_task_duration` | Dask scheduler's estimate for tasks with no timing history |
| `target_duration` | Dask scheduler's target task duration for adaptive scaling decisions |
| `lifetime_stagger` | Stagger worker restarts to avoid all workers expiring simultaneously |

### Selecting a queue

In `seamless.profile.yaml`:

```yaml
- stage hpc:
    - cluster: hpc
    - execution: remote
    - remote: daskserver
    - queue: highmem
```

From the CLI: `seamless-run --stage hpc --queue highmem mycommand input.txt`.

---

## Adaptive scaling

Seamless uses Dask's adaptive scaling to grow and shrink the worker pool based on workload. When many transformations are submitted concurrently, Dask scales up (adding worker jobs to the SLURM/OAR queue) until `maximum_jobs` is reached. When the cluster is idle, it scales down (workers exit and are not resubmitted).

The parameters `target_duration`, `unknown_task_duration`, and `lifetime_stagger` tune the adaptive strategy:

- **`target_duration`** (default: `10m`): the scheduler aims for each worker to run for about this long before being considered for scale-down. Shorter values make the cluster more responsive to idle periods but increase scheduler overhead.
- **`unknown_task_duration`** (default: `1m`): how long the scheduler assumes an unknown-duration task will take when making scaling decisions. Set this to a reasonable estimate of your typical transformation runtime.
- **`lifetime_stagger`** (default: `4m`): workers are given a rolling lifetime of `walltime − lifetime_stagger − grace_period`. Staggering prevents all workers from expiring at the same time and causing a temporary gap in capacity.

When `maximum_jobs` is set to `1`, worker lifetime rotation is disabled — there is no point in rolling restarts with a single worker.

---

## OAR clusters

For OAR (as used on some French HPC centres), use `type: oar` in the cluster definition. The queue parameters are the same; Seamless passes them to `dask_jobqueue.OARCluster`.

```yaml
hpc:
  tunnel: true
  type: oar
  frontends:
    - hostname: login.oar.example
      # ... same as SLURM ...
  queues:
    default:
      conda: seamless-dask
      walltime: "01:00:00"
      cores: 8
      memory: 32000MB
      tmpdir: /tmp
      maximum_jobs: 10
      target_duration: 5m
```

---

## Pure Dask mode

`seamless-dask-wrapper` supports a `pure_dask` mode that uses Seamless infrastructure — service lifecycle management, SSH tunnelling, status files, adaptive scaling, port management — without adopting the Seamless computation model. Workers are plain Dask workers; no `SeamlessWorkerPlugin` is loaded, and no `seamless-transformer` or `seamless-core` packages are needed on the workers.

This is the zero-adoption entry point for teams that already use Dask and want to take advantage of Seamless's managed cluster launcher on HPC:

```yaml
# ~/.seamless/clusters.yaml

dask-only:
  tunnel: true
  type: slurm
  frontends:
    - hostname: login.hpc.example
      daskserver:
        pure_dask: true
        network_interface: 0.0.0.0
        port_start: 60300
        port_end: 60399
  queues:
    default:
      conda: my-dask-env    # any conda env with dask installed
      walltime: "02:00:00"
      cores: 24
      memory: 96000MB
      maximum_jobs: 10
```

With `pure_dask: true`, the `distributed.Client` is available directly after `seamless.config.init()`. You submit Dask futures as normal, bypassing the Seamless transformation layer entirely. Caching, identity, and the `direct`/`delayed` API are not available in this mode.

If you later want to adopt Seamless caching for specific steps, you can do so incrementally: remove `pure_dask: true` from the daskserver definition, add `seamless-dask` to the worker conda environment, and wrap those steps with `direct` or `delayed`.
