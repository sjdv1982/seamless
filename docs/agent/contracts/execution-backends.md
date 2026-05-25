# Execution Backends (Contract)

This page defines the minimum operational model an agent may rely on when discussing “remote execution” or HPC with Seamless.

## Terms

- **Execution mode**: how transformations execute: `process`, `spawn`, or `remote`.
- **Remote target** (only relevant when `execution: remote`): `jobserver` or `daskserver`.
- **Mutual exclusivity**: a single configured cluster/frontend should not expose both jobserver and daskserver without explicitly selecting one.

**This page is about Transformations.** Expressions also run on a jobserver or daskserver, but they are placed by a different rule and on a different axis — see *Expressions are placed, not configured* below. Do not read the `execution:` configuration key and an Expression's `execution=` argument as the same setting.

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
   - Supports opt-in live stdout/stderr streaming per transformation; see
     [Streaming](streaming.md).

### Current limitation: fingertipping in a worker needs Dask

In `spawn` and `remote: jobserver`, a transformation runs in a worker process that cannot see its parent's fingertip candidates: neither the parent's reverse caches nor its database. A fingertip in such a worker tries only the producers that the worker itself launched (nested transformations). If those do not recover the buffer, it raises `NotImplementedError`, and the job fails with that error in its traceback. It does not report a `CacheMissError`, because the search was incomplete.

- **What this blocks.** A transformation with `allow_input_fingertip` whose input buffer is absent (a `scratch` result, or an evicted one) fails in `spawn` and `remote: jobserver`, unless the worker launched the input's producer itself.
- **What still works.** `process` (the fingertip runs in the caller's process, which holds the candidates) and `remote: daskserver` (the workers of a Dask worker can query the database).
- **This is a limitation, not the contract.** The contract is that an input fingertip inside a job works on every backend (`contracts/scratch-witness-audit.md`, *Case 1*).

## Expressions are placed, not configured

A jobserver or daskserver also evaluates **Expressions** (the jobserver endpoint is `GET /run-expression`). Three differences from the transformation backends above matter:

- **It is not a backend choice but a placement rule.** An Expression is evaluated *where the data is*: local when no buffer is needed or the input buffer is already in this process's memory, otherwise dispatched. Selecting a backend does not turn this on or off.
- **`execution="auto" | "local" | "remote"` is a per-Expression argument, not the `execution:` config key.** Here `"local"` means *in this process's memory* and `"remote"` means *not in this process's memory* — independently of which transformation backend is configured. One deliberate deviation: for placement, a buffer in an explicitly configured read-buffer directory also counts as local (`contracts/expressions.md`, *Placement*). A Context fixes the policy for its own Expression jobs with `Context(expression_execution=…)`.
- **A daskserver is a jobserver *mode* for Expressions**, not a competing backend: both expose the same checksum, error, caching and HashType contracts.

The full rule, the resolution order, the no-silent-fallback rules and the two open placement questions are `contracts/expressions.md`, *Placement*.

## Storage prerequisite (by-checksum submission, shared hashserver)

Remote execution — `jobserver` **and** `daskserver` alike — submits work **by checksum, not by value**. A remote target receives input *checksums*; it **materializes the input buffers server-side from a shared hashserver**, writes produced (non-`scratch`) results back to that hashserver, and records `tf_checksum → result_checksum` in the shared database. So a **shared hashserver and database, reachable by the remote workers, are a hard prerequisite for any remote backend** — they are what make server-side input materialization and result persistence possible. (A minimal local cluster that defines a hashserver/database but no jobserver/daskserver therefore cannot run `execution: remote`; it must use `execution: process` — see `../main/cluster.md`.)

Consequences an agent may rely on:

- **Inputs are not necessarily uploaded at submission.** They may be **pre-present** — staged by a prior upload, or **by design**, when the client already holds the checksum of a large server-side dataset. Only buffers actually missing on the server are staged (e.g. `--upload`, or `--write-remote-job` which implies it).
- **Results are durable out-of-process.** A remote run's non-`scratch` results live in the shared hashserver/database independently of the submitting client, so tearing the client down does not lose them. (A `scratch` result is the exception: a scratch transformation may be dispatched, but its result is not stored. It is recomputed at a consumer via input fingertipping, or on the client by `Transformation.run()`, which then runs the transformation a second time — see `contracts/scratch-witness-audit.md`. Input fingertipping does not yet work on every backend: see *Current limitation: fingertipping in a worker needs Dask* above.)
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
