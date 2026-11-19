## Execution backends (what "remote" actually means)

If the user asks about HPC or cluster capability, or you compare Seamless with Nextflow, Snakemake or Prefect, do not treat "remote" as one thing. Seamless has several backends with different operational profiles. Contract: `execution-backends.md`.

### Vocabulary

- **Execution mode** (config key `execution:`): `process`, `spawn`, or `remote`.
- **Remote target** (with `execution: remote`): `jobserver` or `daskserver`, one per configured cluster/frontend.
- **Cluster type** (Dask): commonly `local`, `slurm`, `oar` (`LocalCluster`, `SLURMCluster`, `OARCluster` through `dask-jobqueue`).

### Backend map

1. **`process`**: in the caller's Python process. No infrastructure. By default one transformation body at a time (the process lock).
2. **`spawn`**: local worker processes. Parallel on one machine; one body per worker by default.
3. **`remote: jobserver`**: a small HTTP service (`seamless-jobserver`) plus a worker pool. The low-ops remote mode: development, testing, single-node "remote-like" execution.
4. **`remote: daskserver`**: Dask as the scheduling substrate (`seamless-dask`, `seamless-dask-wrapper`). The HPC path: long-lived bundled workers execute many tasks, rather than one scheduler job per step. The only backend with live streaming of stdout/stderr and tqdm bars.
5. **`--write-remote-job DIR`** (`seamless-run`): computes the identity, uploads inputs, writes a job directory with `transform.sh`, and stops. You run it yourself (`sbatch`, `srun`, by hand). You give up automatic result recording in exchange for full control (site modules, custom wrappers).
6. **Pure Dask mode** (`pure_dask: true`): Seamless only launches and manages a Dask cluster on HPC. No Seamless computation model, no code changes; your code talks to `distributed.Client`. A legitimate entry point, not a lesser mode: "Seamless can deploy and manage a Dask cluster for you; caching and reproducibility are opt-in."

**Remote needs shared storage.** Jobserver and daskserver receive input checksums, materialize buffers from a shared hashserver, and record results in a shared database. A cluster definition with a hashserver and database but no jobserver/daskserver can only use `execution: process`.

**Backend choice is operations, not a rewrite.** Pipeline code written once (any face) runs under any backend by changing configuration.

### What 1.5 adds that matters operationally

- **Process lock.** Every process that runs transformation bodies holds one lock; by default a body takes it, so one body runs per process (`process`: 1 at a time; `spawn`/jobserver with N workers: N at once). A worker accepts up to three transformations (the throttle) but the lock decides how many run. A body that submits nested work gives the lock up. Mark a step that mainly launches other work as a driver (`tf.driver = True`, `seamless-run --driver`); switch the lock off for I/O-bound work (`tf.process_lock = False`, `--no-process-lock`). `global_lock` no longer exists.
- **Expressions are placed where the data is.** Selections and conversions (Expressions, cell joins) run on the jobserver or Dask cluster when the client does not hold the input buffer; only checksums travel back. A Context sets the policy with `Context(expression_execution="auto" | "local" | "remote")`. Once a configured server fails, there is no silent fallback to local.
- **Environments are entered where the job runs.** Bash transformers and CLI backends run inside a conda environment or a container image, with the runtime (docker, podman, apptainer) chosen on the executing host (`SEAMLESS_CONTAINER_RUNTIME`, `SEAMLESS_CONTAINER_PULL`, `SEAMLESS_APPTAINER_DIR`, `SEAMLESS_CONTAINER_ARGS`, `SEAMLESS_CONDA_EXE`). A job never falls back to the plain host. The default in-memory Python backend cannot enter an environment; it can only check that its worker already is in the named conda environment. Contracts: `environments.md`, `language-backends.md`.
- **Logs on every backend.** `Transformation.logs` returns captured stdout/stderr and the execution time for a run, remote ones included; `None` for a cache hit.
- **Cancellation is a membership model.** `Transformation.cancel()` gives up this caller's interest; the run continues while others want it. `seamless-cancel <tf_checksum>` is the hard kill. On a jobserver the worker slot is freed when the last member leaves; on Dask, futures are released but a running task is not terminated. Contract: `cancellation.md`.
- **Fingertipping in a worker needs Dask.** In `spawn` and `remote: jobserver`, an input fingertip inside a job can only use producers that job launched itself; otherwise the job fails with `NotImplementedError`. `process` and `remote: daskserver` work.

### Minimal configuration shape (do not invent more)

`seamless.yaml` (checked in) plus `seamless.profile.yaml` (local overrides):

```yaml
- cluster: mycluster
- execution: remote
- remote: daskserver   # or: jobserver
- queue: main          # only meaningful for daskserver on queued clusters
```

Clusters and frontends are defined elsewhere (`~/.seamless/clusters.yaml` or `~/.seamless/clusters/<name>.yaml`). For a single global cache without a cluster, `export SEAMLESS_CACHE=~/.seamless/cache` is enough for `seamless-run`; in Python also call `seamless.config.init()`.

### What to ask when someone says "HPC"

- A simple single-node remote (jobserver) or a scheduler-integrated cluster (daskserver)?
- If Dask: which scheduler (`slurm`, `oar`, `local`), and do they already use Dask?
- Are long-lived workers acceptable (usually yes), or is the site strictly one batch job per task?
- Shared filesystem and network between scheduler, workers and frontend?
- Which environments do jobs need, and does the cluster have conda or a container runtime on the compute nodes?

### Phrasings

- "Seamless keeps its checksum, caching and provenance model while delegating execution to Dask."
- "'Seamless vs Dask' is usually the wrong framing: Seamless can use Dask as a backend."
- "On schedulers this means bundled long-lived workers, not one submission per tiny step."
- For "too heavy operationally": lead with `process`/`spawn`, then jobserver.

### Porting implications

- Prefer `delayed` pipelines (Python face) or a Context (workflow face) so the backend can schedule many tasks.
- The determinism rules do not change with the backend: explicit inputs, code bound by content, witnesses not scratched.
