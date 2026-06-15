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

## Storage prerequisite (by-checksum submission, shared hashserver)

Remote execution — `jobserver` **and** `daskserver` alike — submits work **by checksum, not by value**. A remote target receives input *checksums*; it **materializes the input buffers server-side from a shared hashserver**, writes produced (non-`scratch`) results back to that hashserver, and records `tf_checksum → result_checksum` in the shared database. So a **shared hashserver and database, reachable by the remote workers, are a hard prerequisite for any remote backend** — they are what make server-side input materialization and result persistence possible. (A minimal local cluster that defines a hashserver/database but no jobserver/daskserver therefore cannot run `execution: remote`; it must use `execution: process` — see `../main/cluster.md`.)

Consequences an agent may rely on:

- **Inputs are not necessarily uploaded at submission.** They may be **pre-present** — staged by a prior upload, or **by design**, when the client already holds the checksum of a large server-side dataset. Only buffers actually missing on the server are staged (e.g. `--upload`, or `--write-remote-job` which implies it).
- **Results are durable out-of-process.** A remote run's non-`scratch` results live in the shared hashserver/database independently of the submitting client, so tearing the client down does not lose them. (A `scratch` result is the exception: not stored, recomputed at a consumer via input fingertipping — see `contracts/scratch-witness-audit.md`.)
- **Materialization is content-addressed, not a side effect.** A worker resolving an input checksum is performing materialization, not "reading whatever is on disk" (see `contracts/identity-and-caching.md`).

## Testing surface

Agents should not assume HPC or scheduler-backed testing lives only in `seamless-dask`.

- HPC/Dask-oriented tests also exist in `seamless-transformer/tests/dask`.
- The `seamless-transformer/tests/cmd` suite is backend-agnostic: it tests the `seamless-run` CLI contract rather than a specific backend.
- Those `tests/cmd` cases can be, and have been, exercised against a SLURM-backed `remote: daskserver` cluster.

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
