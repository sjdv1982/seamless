## 1.5 execution semantics that surface as remote failures

Each section names its contract (in `seamless/docs/agent/contracts/`). Read the contract before concluding that observed behaviour is a bug.

### What the remote services do (`execution-backends.md`, `expressions.md`)

- **Transformations** go to the configured backend: `process` (in the caller), `spawn` (local workers), `remote: jobserver`, `remote: daskserver`. Submission is by checksum; workers fetch inputs from the shared hashserver and record results in the shared database.
- **Expressions** (projections, conversions) and **cell joins** are *placed*, not configured: evaluated locally when no buffer is needed or the input is already in this process (memory or a local buffer source), otherwise dispatched. A jobserver is tried first (`GET /run-expression`, `GET /run-celljoin`); with only a daskserver, the client submits to the Dask scheduler; a jobserver with a Dask client forwards. Responses are checksums only.
- Placement policy: `"auto"` (default) may fall back; explicit `"local"` never dispatches; explicit `"remote"` raises when no client is configured. Once a configured server fails there is **no silent fallback**. A Context sets the policy with `Context(expression_execution=...)`; `"local"` is useful to rule dispatch out while debugging.
- Jobserver routes: `/`, `/status`, `/healthcheck`, `/run-transformation`, `/run-expression`, `/run-celljoin`, `/transformation-status/{tf_checksum}`, `POST /cancel-transformation/{tf_checksum}`, `POST /softcancel-transformation/{tf_checksum}` (`seamless-jobserver/jobserver.py`).
- Error envelope: the exception type a client sees does not depend on where an Expression ran.

### The process lock (`execution-backends.md`, `transformers.md`)

- Each process that runs transformation bodies has one lock; by default a body takes it, so one body runs per process. A body gives it up at its first nested submission and never retakes it. A driver (`driver=True`) never takes it.
- A worker accepts up to three transformations (the throttle); the lock decides how many bodies run. A transformation waiting for the lock occupies a slot.
- **Dispatch ignores the lock**: a job can be queued on a worker whose lock is held and will not move to an idle worker.
- **A hung body blocks its whole process.** In a worker pool, cancelling it terminates the worker process. In `process` mode a cancel does not interrupt Python code, a compiled call or an embedded interpreter; the lock stays held until the body returns. A bash body is killed on cancel.
- An embedded R/Julia interpreter (`BACKEND = "mem"`) requires the lock; it fails as a driver or with `process_lock = False`.
- A nested `seamless-run` inside a bash body releases the outer lock through `SEAMLESS_PROCESS_LOCK_NOTIFY`.
- Nested CLI jobs find a configuration only under `remote: daskserver` (the Dask worker exports `SEAMLESS_CACHE` / `SEAMLESS_REMOTE_CLIENTS`); elsewhere a nested `seamless-run` fails for lack of configuration unless the worker environment provides it. Nested work from inside a container is not supported.

### Environments (`environments.md`, `language-backends.md`)

- Bash bodies and CLI backends run inside the requested conda environment or container image **on the executing host**. The runtime is chosen there: `SEAMLESS_CONTAINER_RUNTIME` (`docker`, `podman`, `apptainer`, `none`; default: the first that works), `SEAMLESS_CONTAINER_PULL` (`never`, `missing`), `SEAMLESS_APPTAINER_DIR` (`<image>.sif`), `SEAMLESS_CONTAINER_ARGS`, `SEAMLESS_CONDA_EXE`. These must be set where the worker runs, not only on the client.
- A job never falls back to the plain host. conda together with Docker, and legacy image keys (`options`, `version`, `checksum`), are refused at dispatch.
- In-memory backends (default Python, compiled, `"mem"` R/Julia) cannot enter an environment: a conda name must match the worker's `CONDA_DEFAULT_ENV`/`CONDA_PREFIX`, and a Docker image fails the run. `set_which` binaries are checked where the code runs.
- The environment is outside identity: a cached result is returned without checking the environment, and the execution record does not say which image ran.
- Not supported: building environments or images, a remote Docker daemon, `singularity` (apptainer is), commas in mount paths under docker/podman.
- Service launch (not jobs): if a service's conda environment is missing from the launcher's cached list, the launcher refreshes it once with `rhl-cache-conda` before failing.

### Cancellation (`cancellation.md`)

- One membership set per deduplication site. **Softcancel** removes one member; the run continues for the others and stops when the last leaves. **Cancel** kills for everyone.
- `Transformation.cancel()` is a soft handle verb: the handle becomes terminal (`status` canceled; `clear_exception()` does not revive it). Hard kill: `seamless-cancel <tf_checksum>`, SIGINT on `seamless-run`, `TransformationCache.cancel_by_checksum`.
- Real termination happens only at the leaf. Jobserver: an emptied set cancels the job and frees the worker slot. Dask: an emptied set releases the futures and does **not** terminate a running task.
- A workflow Context only ever softcancels (supersession after a hold, `prune()`, deletion, `set_graph`, `close`).
- Crashed members are never detected (no heartbeats): a run may continue that nobody waits for. Cancellation does not reach the executing side of a dispatched Expression. A run waiting for the process lock never starts its code if cancelled.

### Fingertipping (`scratch-witness-audit.md`, `execution-backends.md`)

- A fingertip (recomputing an absent buffer from its producer) always runs in the process that wants the buffer and never writes to the hashserver.
- **Inside a `spawn` or jobserver worker**, an input fingertip sees only producers launched by that job; otherwise the job fails with `NotImplementedError`. `process` and `remote: daskserver` work.
- A failed fingertip raises `CacheMissError` with `fingertip_category` (`materialization`, `failed_transformation`, `irreproducible_transformation`, `irreproducible_expression`), the highest-ranked outcome among candidates.
- `.value` / `.buffer` never fingertip; call `fingertip()` explicitly.

### Logs and streaming (`transformation-logs.md`, `streaming.md`)

- Every backend returns the log of a successful run; the jobserver returns it with the result. `Transformation.logs` / `ctx.tf.logs` hold it in process memory only (LRU), keyed by `tf_checksum`; `None` after a cache hit, including a Dask worker answering from the database. A failed run's log is the `.exception` text.
- The execution time is the dispatcher's wall time (queueing and input resolution included).
- Not captured: output written straight to file descriptors 1 and 2.
- Streaming (`tf.streaming = True`, `--streaming`) works only on `remote: daskserver`: 8192-byte chunks every 2 s per stream, head truncation with a dropped-byte count; tqdm bars become local bars (not `tqdm.notebook`). Cached runs stream nothing. `spawn` and jobserver show nothing while a job runs.

### Database and irreproducibility (`execution-records.md`, `identity-and-caching.md`)

- Protocol 2.3 (package `seamless-database` 2.2.0). Upgrade the server with the clients.
- `PUT transformation` is insert-only: a different result for an existing `tf_checksum` answers 409. The client then logs `Irreproducible transformation <tf>: recorded <A>, produced <B>`, keeps A, and reports B as an **automatic** irreproducible observation (`report_irreproducible_result`); without a database only the warning is logged. A **manual** quarantine (`PUT irreproducible`, default mode) removes the forward row so the next run recomputes. `seamless-run --undo` reports through the *automatic* mode instead, which refuses an unchanged result (409), so in 1.5 it fails with "Transformation could not be declared irreproducible".
- A cache hit never runs code, so it never detects nondeterminism. Divergence surfaces on recomputation: fingertipping, independent sites, or after a quarantine.
- Every successful run writes a minimal execution record; `record: true` adds environment fingerprints. Records are write-once per `tf_checksum` and not consulted on cache hits.

### Local buffer sources (`cache-storage-and-limits.md`)

Resolution order: buffer cache, then local buffer sources (configured read-buffer directories, including the directory of a hashserver this process launched locally, and leaf files of directory write mounts), then remote read servers. A process can therefore read buffers while its local hashserver process is down; check the service directly.
