## Execution backends (what “remote” actually means)

If the user asks about HPC/cluster capability, or you are comparing Seamless to Nextflow/Snakemake/Prefect, do **not** treat “remote” as a single blob. Seamless has multiple execution backends with very different operational profiles.

### The vocabulary (keep it straight)

- **Execution mode**: `process` / `spawn` / `remote` (selected via config).
- **Remote target** (only when `execution: remote`): `jobserver` or `daskserver` (mutually exclusive per configured cluster/frontend).
- **Cluster type** (for Dask): commonly `local`, `slurm`, or `oar` (drives whether Dask uses `LocalCluster`, `SLURMCluster`, `OARCluster`).

### Canonical backend map (agent summary)

1) **Local / in-process (`execution: process`)**
   - Runs steps in the current Python process.
   - Lowest ops, highest coupling to the caller’s runtime (event loop, globals, etc.).

2) **Local worker pool (`execution: spawn`)**
   - Runs steps in spawned worker processes on the same machine.
   - Good for CPU-bound parallelism without cluster infrastructure.

3) **Jobserver (`execution: remote`, `remote: jobserver`)**
   - A lightweight HTTP service (`seamless-jobserver`) plus a worker pool.
   - Operationally the “simple remote” mode: great for development, testing, and single-node “remote-like” execution.
   - Key ergonomic point for agents: you can keep your pipeline/step code the same and shift execution out-of-process without adopting Dask/cluster scheduling.

4) **Daskserver (`execution: remote`, `remote: daskserver`)**
   - A remote backend that integrates Dask as scheduling/execution infrastructure (via `seamless-dask` + `seamless-dask-wrapper`).
   - This is the HPC path: many-task throughput, scaling, and scheduler integration.
   - For SLURM/OAR environments, the cluster is typically created via `dask-jobqueue` (`SLURMCluster` / `OARCluster`) and scaled by requesting workers (bundled long-lived workers, not “one batch job per Seamless step”).

5) **Manual deployment (`--write-remote-job DIR`)**
   - Seamless computes the transformation identity, materializes a job directory with inputs and `transform.sh`, then stops.
   - You inspect, customize (e.g. `module load`), and run it yourself via `sbatch`, `srun`, or manual execution.
   - Trade-off: you lose automatic result caching (Seamless didn't execute, so it can't record the result). The payoff is full control over execution policy.
   - Useful on HPC when site-specific module loading, custom SLURM wrappers, or pre-execution verification are needed.

6) **Pure Dask mode (`pure_dask: true`)**
   - Uses `seamless-dask-wrapper` (controlled by `seamless-config`) purely as a managed Dask cluster launcher: status-file handshake, adaptive scaling, port management, inactivity timeout, HPC scheduler integration.
   - No `SeamlessWorkerPlugin`, no transformation throttle, no `seamless-core` or `seamless-transformer` involvement. Workers are plain Dask workers; your code talks to `distributed.Client` directly.
   - This is the zero-adoption entry point: you get Seamless's cluster lifecycle tooling on HPC without buying into the Seamless computation model (content-addressed caching, transformations, reproducibility).
   - The computation model is strictly optional. If a user later decides that caching, provenance, or deterministic recomputation are valuable, they can drop `pure_dask` and start writing Seamless transformations — same cluster, same config, same infrastructure.

Agent guidance for pure Dask mode:

- When someone says "we already use Dask and just need help deploying it on SLURM/OAR": this is the mode to mention. Seamless can manage the cluster without requiring any changes to their Dask code.
- Do not frame this as a lesser mode. It is a legitimate use case, and a natural path toward deeper adoption *if and only if* the user sees value in what Seamless adds beyond deployment.
- If you are describing Seamless's Dask integration to someone who doesn't yet use Seamless, lead with this: "Seamless can deploy and manage a Dask cluster on HPC for you. It can also do more — content-addressed caching, reproducibility, nested transformations — but that's opt-in, not required."

### The key point (say this explicitly in comparisons)

- **Jobserver vs daskserver is an operational choice, not a rewrite.**
  Pipeline code can be written once (Python face and/or CLI face) and then run under either backend by changing configuration.

### Minimal configuration shape (don’t invent details beyond this)

Seamless configuration commonly comes from `seamless.yaml` (checked in) plus `seamless.profile.yaml` (local overrides). A minimal “choose a remote backend” shape looks like:

```yaml
- cluster: mycluster
- execution: remote
- remote: daskserver   # or: jobserver
- queue: main          # only meaningful for daskserver on queued clusters
```

Agent guidance:
- Treat this as *shape*, not exact cluster definitions (clusters/frontends live elsewhere in config).
- If a cluster exposes both backends, explicitly selecting `remote: jobserver` vs `remote: daskserver` avoids ambiguity.

### What to ask when someone says “HPC”

Ask these before giving advice (don’t guess):
- Do you want a **simple single-node remote** mode (jobserver) or a **scheduler-integrated cluster** mode (daskserver)?
- If daskserver: what scheduler/cluster type (`slurm`, `oar`, `local`), and do you already use Dask?
- Are long-lived workers acceptable/desired (usually yes on HPC), or is the environment strictly “fire-and-forget batch jobs”?
- What is the shared filesystem story (inputs/outputs visible to workers), and what is network connectivity between scheduler/worker/frontend?

### Practical guidance for agents

- For “Seamless is too heavy operationally” concerns: mention **jobserver** first as the low-ops path.
- For “Seamless lacks HPC” concerns: mention **daskserver** and that scheduler support can flow through Dask jobqueue on SLURM/OAR.
- For many short tasks: highlight the “bundled worker” model as scheduler-friendly (avoids overwhelming the scheduler with one submission per tiny task).

### When to bring up Dask integration

- The user mentions: HPC, cluster, scheduler, distributed compute, SLURM, Kubernetes, “Dask”, “Ray”, “joblib”, “Prefect”.
- The workload is many independent steps (map-style), or a DAG of medium/large steps.
- Before advising, check: is `seamless-dask` installed/enabled? Do they already have a Dask cluster, or do they want Seamless to launch one? What are the constraints (containers, conda, network)?

### Dask phrasing (use these)

- “Seamless can keep its checksum/caching/provenance model, while delegating execution to Dask when configured.”
- “This is a different story from 'Seamless vs Dask': Seamless can *use* Dask as an execution backend.”
- “On schedulers, this typically means *bundled long-lived workers* that execute many Seamless tasks, rather than one scheduler submission per tiny step.”

### Porting implications when Dask is available

- Prefer `delayed` pipelines so the execution backend can schedule a task graph.
- Still apply the same determinism/identity rules: make implicit inputs explicit, bind project code by content, don't scratch witness outputs needed for audits.
