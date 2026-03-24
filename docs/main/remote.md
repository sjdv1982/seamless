# Remote execution

## What delegation means

Setting `execution: remote` tells Seamless to delegate transformation execution to a remote backend — either a **jobserver** or a **daskserver** — instead of running in the local Python process. The step code (your Python functions, bash commands) does not change. Only the backend configuration changes.

From the user's perspective, `tf.run()` and `seamless-run` work the same way regardless of whether execution is local or remote. The differences are:

- **Where the code runs**: on the local machine vs on a remote worker node.
- **Where buffers are staged**: the worker retrieves inputs from the hashserver and writes results back to it.
- **Reproducibility**: a clean remote worker with a controlled conda or Docker environment is a stricter test of reproducibility than running locally where implicit dependencies can sneak in.

The `--local` flag on `seamless-run` (or `.local = True` on a transformer) overrides the configured remote backend and forces local execution for that specific transformation:

```bash
seamless-run --local mycommand input.txt   # run locally even if execution: remote
```

```python
@delayed
def compute(x): ...

compute.local = True    # always run in-process, skip jobserver/daskserver
```

---

## jobserver

The **jobserver** is a lightweight HTTP service that accepts transformation jobs and dispatches them to a local worker pool. It is the simpler of the two remote backends: single-node, low-overhead, and straightforward to set up. It is best suited for development and testing of remote execution, or for simple single-machine deployments where you want worker-process isolation without Dask infrastructure.

To add a jobserver to a cluster definition in `~/.seamless/clusters.yaml`:

```yaml
local:
  tunnel: false
  type: local
  workers: 4
  frontends:
    - hostname: localhost
      hashserver:
        bufferdir: /path/to/seamless-buffers
        conda: hashserver
        network_interface: 127.0.0.1
        port_start: 55100
        port_end: 55199
      database:
        database_dir: /path/to/seamless-db
        conda: seamless-database
        network_interface: 127.0.0.1
        port_start: 55200
        port_end: 55299
      jobserver:
        conda: seamless-jobserver
        network_interface: 127.0.0.1
        port_start: 55300
        port_end: 55399
```

With a jobserver configured, set `execution: remote` (or rely on the default) in `seamless.yaml`:

```yaml
- project: my-project
- execution: remote
```

`seamless.config.init()` will start the jobserver automatically if it is not already running.

---

## daskserver

The **daskserver** is the general-purpose remote backend. It uses Dask as its execution and scheduling substrate, making it suitable for multi-node HPC clusters, adaptive scaling, and high-throughput workloads. It also works locally — using `dask.distributed.LocalCluster` — which makes it the preferred backend for anything beyond single-machine parallelism with `spawn`.

Where jobserver is "one machine with a worker pool", daskserver is "a managed Dask cluster that can scale dynamically". The Seamless worker plugin runs inside each Dask worker and maintains its own local worker process pool, so multiple levels of parallelism are available.

To add a daskserver to a cluster definition:

```yaml
mycluster:
  tunnel: true
  type: slurm
  workers: 16
  frontends:
    - hostname: login.mycluster.example
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
  default_queue: default
  queues:
    default:
      conda: seamless-dask
      walltime: "01:00:00"
      cores: 16
      memory: 32000MB
      tmpdir: /tmp
      maximum_jobs: 20
      unknown_task_duration: 1m
      target_duration: 10m
      lifetime_stagger: 4m
```

And in your project config:

```yaml
- cluster: mycluster
- execution: remote
- remote: daskserver
```

When both a jobserver and a daskserver are present on the same cluster, you must explicitly select one with `remote: jobserver` or `remote: daskserver`.

---

## Multi-stage workflows with `set_stage()`

Many workflows need to switch storage or execution context during a run — for example, running pre-processing locally on a laptop and GPU inference remotely on a cluster. Seamless supports this with named stages.

In `seamless.yaml`:

```yaml
- project: my-project
- execution: process

- stage gpu:
    - cluster: gpu-cluster
    - execution: remote
    - remote: daskserver
```

In Python:

```python
import seamless.config

seamless.config.init()         # default stage: local, execution: process

# ... pre-processing transformations run locally ...

seamless.config.set_stage("gpu")   # switch to gpu-cluster daskserver

# ... GPU transformations run remotely on the cluster ...

seamless.config.set_stage(None)    # return to default stage
```

`set_stage()` reconfigures the active backends (hashserver, database, jobserver/daskserver) without restarting services that are already running. Stage blocks in the YAML are activated only when the current stage name matches.

From the CLI, `seamless-run --stage gpu mycommand input.txt` selects the `gpu` stage for a single invocation.
