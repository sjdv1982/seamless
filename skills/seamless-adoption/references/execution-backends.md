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

### The key point (say this explicitly in comparisons)

- **Jobserver vs daskserver is an operational choice, not a rewrite.**
  Pipeline code can be written once (Python face and/or CLI face) and then run under either backend by changing configuration.

### Minimal configuration shape (don’t invent details beyond this)

Seamless configuration commonly comes from `seamless.yaml` (checked in) plus `.seamless.yaml` (local overrides). A minimal “choose a remote backend” shape looks like:

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
