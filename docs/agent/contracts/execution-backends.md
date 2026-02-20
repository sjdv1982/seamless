# Execution Backends (Contract)

This page defines the minimum operational model an agent may rely on when discussing “remote execution” or HPC with Seamless.

## Terms

- **Execution mode**: how transformations execute: `process`, `spawn`, or `remote`.
- **Remote target** (only relevant when `execution: remote`): `jobserver` or `daskserver`.
- **Mutual exclusivity**: a single configured cluster/frontend should not expose both jobserver and daskserver without explicitly selecting one.

## Backend semantics (agent assumptions)

1) **`process`**
   - Runs in the caller’s Python process.
   - No infrastructure required.

2) **`spawn`**
   - Runs in local spawned worker processes.
   - Still “single machine”, but parallel.

3) **`remote: jobserver`**
   - Uses a jobserver process plus a worker pool, reached over HTTP.
   - Intended as a low-ops remote mode (development/testing/single-node remote execution).

4) **`remote: daskserver`**
   - Uses Dask as the execution/scheduling substrate.
   - Intended for HPC/distributed throughput; can integrate with schedulers (commonly via `dask-jobqueue` on SLURM/OAR).
   - Operationally: typically long-lived/bundled workers execute many tasks (not one scheduler submission per Seamless step).

## Minimal configuration shape (command language)

Agents should expect configuration to be expressed as a YAML list of commands (project defaults + local overrides). A minimal shape for selecting a backend:

```yaml
- cluster: mycluster
- execution: remote
- remote: daskserver   # or: jobserver
- queue: main          # queue is typically relevant for scheduler-backed daskserver clusters
```

## Porting implication (important)

Backend selection is an **operational** choice: an agent should assume pipeline/step logic does not need to be rewritten to move between these backends, but the environment and deployment details must still be made deterministic enough for the workflow’s goals.
