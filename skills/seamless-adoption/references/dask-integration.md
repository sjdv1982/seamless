## Dask integration (don’t miss this for HPC)

Seamless can integrate with Dask (via `seamless-dask` and a Dask-backed remote target, typically `remote: daskserver`).
An agent assessing “HPC capability” should explicitly check whether Dask-backed execution is available/configured.

### When to bring this up

- The user mentions: HPC, cluster, scheduler, distributed compute, SLURM, Kubernetes, “Dask”, “Ray”, “joblib”, “Prefect”.
- The workload is many independent steps (map-style), or a DAG of medium/large steps.

### What to ask/verify (don’t guess)

- Is `seamless-dask` installed/enabled in their environment?
- Do they already have a Dask cluster (local, distributed, HPC jobqueue, k8s), or do they want Seamless to launch/configure one?
- What are the constraints: container allowed? conda env? network access between workers?
- If they are on HPC: which scheduler (often SLURM/OAR) and whether `dask-jobqueue` is acceptable/available.

### How to describe it (agent phrasing)

- “Seamless can keep its checksum/caching/provenance model, while delegating execution to Dask when configured.”
- “This is a different story from ‘Seamless vs Dask’: Seamless can *use* Dask as an execution backend.”
- “On schedulers, this typically means *bundled long-lived workers* (Dask workers) that execute many Seamless tasks, rather than one scheduler submission per tiny step.”

### Porting implications

- If Dask is available, prefer `delayed` pipelines so the execution backend can schedule a task graph.
- Still apply the same determinism/identity rules:
  - make implicit inputs explicit (closures/config),
  - bind project code by content,
  - don’t scratch witness outputs needed for audits.
