---
name: seamless-remote-debugging
description: Guides AI agents through debugging failures in Seamless remote and multi-process execution (hashserver, seamless-database, seamless-jobserver, Dask, spawn workers). Covers the service topology, error propagation across repos, server-side logs and state files (seamless-service-*, rhl-*), clean restarts, and clearing caches to prevent false passes; plus 1.5 behaviour that shows up as remote failures - Expressions and cell joins dispatched to jobserver or Dask, database protocol 2.3, the per-process lock (hangs, serialized jobs), conda/Docker/Apptainer environments entered on the worker, soft versus hard cancellation, fingertipping in workers, logs and Dask streaming, irreproducible-result warnings. Triggers when a Seamless integration test fails, a client raises ClientConnectionError or a timeout, a remote job hangs or never starts, a workflow Context node fails with a remote error, local and remote results differ, or an HPC/Dask workflow misbehaves.
license: MIT
---

# Seamless Remote Debugging

## The cardinal rule

**When a remote operation fails, consider that the bug is on the server side.** Seamless clients talk to separate server processes (hashserver, database, jobserver, Dask scheduler and workers), in different repos, possibly on different machines, with their own dependencies. A `ClientConnectionError` in `seamless-remote` may mean the hashserver crashed on a Starlette change. Read the server-side logs before attempting any fix, and fix the problem in the repo where it originates.

The contract pages in `seamless/docs/agent/contracts/` are authoritative, especially `execution-backends.md`, `service-management.md`, `expressions.md` (*Placement*), `cancellation.md`, `environments.md`, `execution-records.md`, `transformation-logs.md` and `streaming.md`.

## Topology

```
client (test, script, notebook, workflow Context)
  |  seamless-config: reads seamless.yaml + seamless.profile.yaml + cluster YAML;
  |                   selects cluster, queue, execution mode
  v
remote-http-launcher: launches services (locally or over SSH), writes PID/status JSON
  |                   and a log file, opens SSH tunnels, healthchecks
  v
hashserver          buffers by checksum            (repo hashserver: FastAPI/uvicorn)
seamless-database   transformation/expression results, HashType, records
                                                    (repo seamless-database: aiohttp + peewee)
seamless-jobserver  HTTP job dispatch + worker pool (repo seamless-jobserver: aiohttp;
                                                     workers run seamless-transformer)
seamless-dask-wrapper  Dask scheduler + SLURM/OAR workers (repo seamless-dask)
  |
  v  (daskserver) worker nodes: each is also a client of hashserver + database
```

Client libraries: `seamless-remote` (aiohttp clients for all services), `seamless-core`, `seamless-transformer`, `seamless-workflow`.

Remote execution is **by checksum**: workers receive input checksums and fetch buffers from the shared hashserver, then write results back and record them in the shared database. A remote backend without a reachable shared hashserver and database cannot work.

## Debugging checklist

1. **Read the full traceback.** Which client call failed, with which exception?
2. **Identify the service.** `buffer_client.py` -> hashserver; `database_client.py` -> database; `jobserver_client.py` -> jobserver; Dask errors -> scheduler or workers. In 1.5 the jobserver and Dask also evaluate **Expressions and cell joins** (`/run-expression`, `/run-celljoin`), so a failing projection or conversion can be a remote failure too.
3. **Read the server log.** `seamless-service-logs --service <name> --tail 100`, `seamless-service-inspect --service <name>`. Raw access via `seamless-service-resolve` then `ssh <host> rhl-logs <key>`. Read logs **before** removing state. Commands: `references/service-commands.md`.
4. **Read the job's own output.** `tr.logs` / `ctx.tf.logs` and `.exception` carry the worker's stdout, stderr and traceback, on every backend. Live output needs `streaming` and `remote: daskserver`.
5. **Classify the cause**: code bug, dependency incompatibility, version mismatch between client and services, stale process, environment missing on the worker, process-lock wait, network. Use the symptom table below.
6. **Fix in the right repo**, then reinstall it where the service runs and restart the service (a local edit does not change a running remote service).
7. **Clear the caches** for a true re-execution: `references/restart-and-clear.md`.
8. **Verify on a cold cache.** A pass on a warm cache proves nothing.

## 1.5 symptom table

| Symptom | Likely cause | Look at / do |
|---|---|---|
| `ClientConnectionError` after retries | server crashed or not running; `_retry_operation` already retried 5 times, so it is not a blip | server log; server JSON status |
| `asyncio.TimeoutError` | server alive but hung or overloaded | server log; process lock (below) |
| HTTP 4xx/5xx from the database after an upgrade | client and `seamless-database` disagree on protocol (1.5 needs package 2.2.0, protocol 2.3) | upgrade the database package with the clients; restart it |
| job stays `computing` / never starts on one worker | it waits for that worker's process lock behind another body; dispatch ignores the lock, and a hung body blocks its whole process | which body holds the worker (logs); cancel the hung one; mark launch-only steps `driver=True` |
| parallel jobs run one at a time | default one body per process | expected; more workers, or `process_lock = False` for code safe to run side by side |
| nested submissions on Dask wait, or come back to run in the submitter | the anti-deadlock permission routine (`seamless-dask/anti-deadlock.txt`) | expected; a step that mainly launches work can be declared `tf.driver = True` / `seamless-run --driver`, which skips the routine for its launches |
| a nested `seamless-run` inside a bash job fails for lack of configuration | only a Dask worker exports `SEAMLESS_CACHE` / `SEAMLESS_REMOTE_CLIENTS` to jobs; on `process`, `spawn` and jobserver nothing is exported; inside a container nesting is unsupported | run under `remote: daskserver`, or make the variables part of the worker's environment |
| a job fails because its conda env or image is missing, or no container runtime works | environments are entered on the **executing host**; a job never falls back to the plain host | create the env / provide the image on the workers; the runtime is chosen there (`SEAMLESS_CONTAINER_RUNTIME`, `SEAMLESS_CONTAINER_PULL`, `SEAMLESS_APPTAINER_DIR`, `SEAMLESS_CONTAINER_ARGS`, `SEAMLESS_CONDA_EXE` in the worker's environment) |
| a **service** fails to launch because its conda env is absent | the launcher's cached conda list is stale; it refreshes once (`rhl-cache-conda`) and re-checks before failing | install the env on the host, then `ssh <host> rhl-cache-conda` |
| Python step with `set_docker` fails; conda mismatch error on an in-memory step | in-memory backends cannot enter environments, only check `CONDA_DEFAULT_ENV`/`CONDA_PREFIX` | install deps in the worker env, or `tf.metavars.BACKEND = "cli"` |
| a configured remote fails and nothing runs locally | by design: no silent fallback once a configured server fails | fix the service; or select `process` explicitly |
| `NotImplementedError` from a fingertip inside a job | input fingertipping in `spawn` / `remote: jobserver` workers only sees producers the job launched | use `remote: daskserver` or `process`, or avoid scratch for that input |
| `CacheMissError` with `fingertip_category` | the buffer is absent and recomputation could not recover it (`materialization`, `failed_transformation`, `irreproducible_transformation`, ...) | the category says why; check the hashserver holds the buffer |
| log line "Irreproducible transformation X: recorded A, produced B" | a recomputation gave a different result; the database kept A and recorded B as an automatic observation | nondeterministic step, or environment dependence; compare execution records |
| a job keeps running after `Transformation.cancel()` | `cancel()` is soft: it leaves the run to other members | `seamless-cancel <tf_checksum>` for a hard kill; on Dask an emptied membership releases futures but does not terminate a running task |
| `.logs` is `None` | cache hit, or the result was computed by another process | expected; logs are per-process memory |
| `--streaming` prints nothing | not on `remote: daskserver`, or a cache hit | expected outside Dask |
| reads succeed although the hashserver is down | a locally launched hashserver's directory is read directly as a local buffer source | check the service itself (`seamless-service-ps`, `rhl-handshake`) |
| workflow node `failed` with a remote error text | the node's Transformation or Expression failed remotely; `.exception` is the remote traceback string | same procedure; `Context(expression_execution="local")` isolates Expression placement |
| test passes but should not | warm cache: nothing ran | clear caches, rerun cold |

Detail and the reasoning behind each row: `references/execution-semantics.md`.

## Local fix is not a live fix

Remote services run the **installed** packages of their conda environment. After fixing source: reinstall into the service's environment on that host, restart the service, clear caches if needed. For local clusters, check that the service's conda env (the `conda` field in the cluster YAML) is the one with editable installs: `pip show <package> | grep "Editable project location"`.

## Environment variables for diagnostics

| Variable | Effect |
|---|---|
| `SEAMLESS_CLIENT_DEBUG=1` | logs client session lifecycle events |
| `SEAMLESS_DEBUG_REMOTE_DB=1` | debug logging for database operations |
| `SEAMLESS_REMOTE_CONNECT_TIMEOUT` | TCP connect timeout (default 10 s) |
| `SEAMLESS_REMOTE_READ_TIMEOUT` | socket read timeout (default 1200 s) |
| `SEAMLESS_REMOTE_TOTAL_TIMEOUT` | overall request timeout (default unlimited) |
| `SEAMLESS_REMOTE_HEALTHCHECK_TIMEOUT` | healthcheck timeout (default 10 s) |
| `SEAMLESS_DATABASE_MAX_INFLIGHT` | max concurrent database requests (default 30) |
| `REMOTE_HTTP_LAUNCHER_DIR` | override `~/.remote-http-launcher` |

## Reference map

- `references/service-commands.md`: `seamless-service-*` and `rhl-*` commands, SSH guard, server-side install, file locations, reading logs.
- `references/restart-and-clear.md`: clean restart, clearing buffer and database caches, what the database holds in 1.5.
- `references/execution-semantics.md`: 1.5 execution behaviour behind the symptom table (placement, process lock, environments, cancellation, fingertipping, logs, irreproducibility).
- `references/key-derivation.md`: how service keys are built from cluster/project/stage.
- `references/launcher-lifecycle.md`: the remote-http-launcher lifecycle (launch, monitor, handshake, tunnel, teardown).
