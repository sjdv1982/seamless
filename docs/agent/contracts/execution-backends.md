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
   - By default, one transformation runs its code at a time (*The process lock*).

2) **`spawn`**
   - Runs in local spawned worker processes.
   - Still “single machine”, but parallel: by default, one transformation runs its code at a time in each worker process.

3) **`remote: jobserver`**
   - Uses a jobserver process plus a worker pool, reached over HTTP.
   - Intended as a low-ops remote mode (development/testing/single-node remote execution).

4) **`remote: daskserver`**
   - Uses Dask as the execution/scheduling substrate.
   - Intended for HPC/distributed throughput; can integrate with schedulers (commonly via `dask-jobqueue` on SLURM/OAR).
   - Operationally: typically long-lived/bundled workers execute many tasks (not one scheduler submission per Seamless step).
   - Supports opt-in live stdout/stderr streaming per transformation; see
     [Streaming](streaming.md).

### Output and logs per backend

A transformation's stdout and stderr are captured on every backend. After a successful run they are in `Transformation.logs`, followed by the execution time. After a failure they are in the trailers of `.exception`. Backends differ in where the capture happens and in whether the output is also visible while the run is in flight:

| Backend | Streams in the success log | Live output while the run is in flight |
|---|---|---|
| `process` | captured by a tee in the caller's process | on the caller's stdout and stderr |
| `spawn` | captured in the worker child | none |
| `remote: jobserver` | captured in the worker child, returned in the jobserver's response | none |
| `remote: daskserver` | captured in the worker child, returned to the client with the result | only with `streaming` |

- **Streaming is Dask-only.** `process`, `spawn` and `remote: jobserver` ignore the flag (`contracts/streaming.md`).
- **A log exists only for a run that executed.** A result that comes from a cache or from the database has no log, on any backend.
- **The execution time in the log is the dispatcher's measurement**, the same number as `wall_time_seconds` in the execution record. It includes queueing, inter-process transfer and input resolution.

The log's layout, its per-process store, what is and is not captured, and the rules for bash and compiled transformers are `contracts/transformation-logs.md`.

### Environments are entered on the executing host

A transformation can name a conda environment or a Docker image. A CLI backend, which is the bash transformer and the CLI backends of Python, R and Julia (`contracts/language-backends.md`), runs its script there (`contracts/environments.md`). The **executing host** is the machine on which the script runs. It enters the environment, so it must provide it.

| Backend | Executing host | Its settings are read from |
|---|---|---|
| `process`, `spawn` | the submitting machine | the environment of the submitting process |
| `remote: jobserver` | the jobserver host | the environment the jobserver was started in |
| `remote: daskserver` | the Dask worker nodes | the queue's `job_script_prologue` |

- **For a conda environment, the executing host needs that environment and a conda launcher.**
- **For a Docker image, the executing host needs a container runtime and the image.** The runtime is docker, podman or apptainer. The host chooses it, by the setting `SEAMLESS_CONTAINER_RUNTIME` or else by detection. A transformation never names a runtime. By default no image is pulled.
- **Every backend behaves the same.** The job is wrapped where it executes, and no backend does anything of its own for an environment. A host that cannot enter the environment fails the job. No backend falls back to running the script on the plain host.
- **A fingertip needs the environment where the buffer is wanted.** A fingertip is never dispatched, so the process that asks for the buffer enters the environment itself (`contracts/scratch-witness-audit.md`, *Fingertipping*).
- **An in-memory backend is never wrapped.** Its code runs inside the process that executes it: Python in memory, compiled transformations, and the in-memory backends of R, Julia and other handler languages. A Docker image on one is an error, on every backend. A conda environment is a requirement on that process, which must already be in exactly that environment (`contracts/language-backends.md`, *The in-memory rule*). The process is the one that the execution backend runs bodies in: the calling process in `process`, a worker process otherwise.
- **Required binaries are looked up where the code runs.** For a CLI backend that is the executing host's environment or image, after it is entered, and for an in-memory backend the `PATH` of the executing process (`contracts/language-backends.md`, *Required binaries*).
- **A specification that could never work is refused when the transformation is dispatched** on the submitting side: a conda environment together with a Docker image, and an unknown key of the image spec. It is checked again on the executing host before launch (`contracts/language-backends.md`, *The check happens at dispatch*).
- **The image spec's `gpus` does not place a job.** It gives the container access to the GPUs of the host on which the job runs. Which host that is follows from the backend and the queue, as for any transformation.

`contracts/environments.md` has the settings, the failures and the limitations.

### Current limitation: fingertipping in a worker needs Dask

In `spawn` and `remote: jobserver`, a transformation runs in a worker process that cannot see its parent's fingertip candidates: neither the parent's reverse caches nor its database. A fingertip in such a worker tries only the producers that the worker itself launched (nested transformations). If those do not recover the buffer, it raises `NotImplementedError`, and the job fails with that error in its traceback. It does not report a `CacheMissError`, because the search was incomplete.

- **What this blocks.** A transformation with `allow_input_fingertip` whose input buffer is absent (a `scratch` result, or an evicted one) fails in `spawn` and `remote: jobserver`, unless the worker launched the input's producer itself.
- **What still works.** `process` (the fingertip runs in the caller's process, which holds the candidates) and `remote: daskserver` (the workers of a Dask worker can query the database).
- **This is a limitation, not the contract.** The contract is that an input fingertip inside a job works on every backend (`contracts/scratch-witness-audit.md`, *Case 1*).

## The process lock

Two terms are used below. The **body** of a transformation is its user code: the Python function, the bash script or the compiled call. For a handler language such as R or Julia, the body is the call of the handler that runs the code (`contracts/handler-languages.md`). For Python under its CLI backend, the body is the run of the job. **Nested work** is a transformation whose execution is requested from inside a body.

**Every process that runs bodies has one process lock, and by default a body runs while holding it.** A transformation whose `process_lock` is true waits for the lock of the process it was placed in, runs its body while holding the lock, and releases the lock when the body ends. `process_lock` is true by default (`contracts/transformers.md`, *`process_lock` and `driver`*). Among such transformations, at most one body runs at a time in any one process. This holds on every backend, and for Python, bash, handler-language and compiled transformers alike.

- **The lock is held around the body only.** Input resolution, module building and result serialization happen outside it. Several transformations in one process therefore download and upload at the same time.
- **The lock keeps holders apart, and nothing else.** A body that does not hold the lock can run next to a holder in the same process. Three kinds of body do not hold it: a body with `process_lock` false, a driver (*Drivers*), and a body that gave the lock up (*Nested work gives the lock up*). Code outside any transformation, such as the script that submits work in `process` mode, never waits for the lock.
- **What the lock is for.** It protects state that the bodies of one process share, such as the working directory, environment variables or a library that is not thread-safe, as long as every body there keeps the default. It also fixes how many bodies run at once: one per process (*Concurrency per backend*).
- **The lock is controlled by metadata only.** There is no lock object for user code to take. The name `global_lock` is retired without an alias. Neither `seamless_transformer` nor `seamless.transformer` exports it, and reading it as an attribute of either module raises `AttributeError` with a message that points to `process_lock`. Code that took it inside a body declares `process_lock` on the transformer instead.

### Nested work gives the lock up

**A body that submits nested work gives up the lock at that moment, if it holds it, and never takes it again.**

- **It happens at submission**, before it is known whether the nested result is cached. Whether a body keeps its lock therefore does not depend on the state of any cache.
- **The reason is that nested work can land in the submitter's own process.** In `process` mode it always does. In a worker pool it does when the nested transformation is dispatched to the worker that submitted it, and when the pool is full, in which case the worker runs it itself. A parent that kept the lock would wait for a child that waits for the parent's lock.
- **Afterwards the body runs without the lock until it ends.** That includes the code that follows the return of the nested results. A body has its process to itself only up to its first nested submission.
- **No declaration is needed.** A transformation that keeps every default may submit nested work.

These calls, made by a body, are nested submissions:

| Call | Kind |
|---|---|
| `tr.start()` | scheduling |
| `tr.compute()`, `tr.run()`, a call of a direct Transformer | synchronous execution |
| `await tr.computation()`, `tr.task()` | asynchronous execution |
| `parallel()`, `parallel_async()` | batches |
| a fingertip that recomputes a transformation | recovery of an absent buffer by running its producer again (`contracts/scratch-witness-audit.md`, *Fingertipping*) |

Building a Transformation without running it is not a submission. Neither is reading a handle: `status`, `exception`, `result_checksum`, `value`, `buffer`, `logs`.

**The rule covers the body's own thread and the coroutines of its event loop.** A submission from a thread that the body started itself is not attributed to the body, and the lock stays held. A workflow Context created inside a body is such a case, because a Context submits its nodes from its own controller thread. A body that submits in this way must have `process_lock` false, or be a driver. If it keeps the default, a nested transformation that lands in its process waits for the lock while the body waits for the transformation. The two then hang, and no error is raised.

### Drivers

A **driver** is a transformation declared with `driver` true: its body mainly launches other transformations and waits for them.

- **A driver never takes the lock.** Its body starts even while the lock of its process is held, and it runs next to whatever else runs there.
- **Its submissions are marked as coming from a driver.** On `remote: daskserver`, a nested submission normally asks for permission before it goes to Dask. It can be made to wait, and it can be handed back to the submitter to run itself. This is the anti-deadlock routine described in `seamless-dask/anti-deadlock.txt`. A submission made by a driver's body skips the routine. So does the submission of a driver itself.
- **The mark is not inherited.** A transformation launched by a driver is an ordinary transformation. It takes or leaves the lock according to its own settings, it is deduplicated as usual, and the nested work that it submits in turn asks for permission again.

**Nested work from a CLI job** gets what its configuration gives it:

- **A nested `seamless-run` finds its configuration** from `SEAMLESS_CACHE`, or from `SEAMLESS_REMOTE_CLIENTS` together with the Dask scheduler, or else from a configuration file in its working directory. For a job, the working directory is the job directory, which holds none.
- **Only the Dask worker exports these variables.** Under `remote: daskserver` a nested `seamless-run` from a bash job, and a nested transformation from a Python CLI job (`contracts/language-backends.md`, *Drivers and nested work*), therefore go to the same cluster and share its caches. On `process`, `spawn` and `remote: jobserver` nothing is exported. A nested `seamless-run` there fails for lack of a configuration, unless one of the variables is in the environment that the job inherits, and a nested call in a Python CLI job runs inside the job's own process, with no cache and no dispatch.
- **A submission from the job's own process skips the permission routine**, because the process is neither a worker nor one that has spawned workers. The mark of a driver is not what decides it.
- **Inside a container nothing is exported and the nesting signal does not cross.** Nested work from a containerized job is not supported.

Declaring a driver is never needed for correctness, because an undeclared body gives the lock up at its first nested submission. The declaration matters in two cases: when the body should not wait for the lock at all, and on Dask, where it lifts the permission routine from the body's launches.

### Bash bodies

**What this section says of a bash body holds for the body of every CLI backend**: the bash transformer, and the CLI backends of Python, R and Julia (`contracts/language-backends.md`). A job in any of them is a process of its own, started by the process that runs the transformation, and is signalled and torn down in the same way.

- **A bash transformation never changes the working directory of the process that runs it.** The script runs in a job directory of its own, which is its working directory. The process keeps the working directory it had, so a relative path used by other code in that process keeps its meaning.
- **A bash body takes the lock like any other body**, unless `process_lock` is false or the transformation is a driver. For `seamless-run` these are `--no-process-lock` and `--driver` (`contracts/seamless-run-and-argtyping.md`).
- **A bash body that holds the lock is told when its script submits nested work.** The script's environment contains the variable `SEAMLESS_PROCESS_LOCK_NOTIFY`. A Seamless program that the script starts, such as `seamless-run`, uses the variable to signal the body when it first submits a transformation. The body then gives the lock up, as any body does. `seamless-run --qsubmit` signals as well. The script itself has nothing to do.
- **The nested command keeps its own defaults.** It does not become a driver, and neither does the bash transformation whose script started it.
- **The variable is set only when the body holds the lock as its script starts.** Otherwise the body removes it from the script's environment, so that a nested command never signals a process further up.
- **The signal works for as long as the script's process runs**, also after the script has closed its stdout and stderr.
- **The signal is a named pipe on the local filesystem.** The nested command must see the same filesystem as the body, and the signal does not cross `ssh` or a container boundary. A bash body that submits nested work through one of those must be declared a driver, or have `process_lock` false.
- **A bash body with an environment is a bash body like any other** (`contracts/environments.md`). It takes the lock and holds it until its script ends, so a long container job occupies its process for that time. A script under a conda environment has the variable and is signalled as a plain script is. A script in a container made from the transformation's Docker image is behind a container boundary: the variable is not passed in, and the previous rule applies.

### Handler languages and embedded interpreters

A handler-language transformation runs R, Julia or another registered language through a handler. The R and the Julia handler each have two ways to run the code, which this section calls a CLI backend and an in-memory backend. Python has both as well: in memory by default, and as a CLI job with `BACKEND="cli"`. These are **language backends**, selected per Transformer, and they are independent of the execution backends of this page. `contracts/language-backends.md` specifies the two kinds and the Python CLI backend, and `contracts/handler-languages.md` the handler ones.

- **A CLI backend starts one interpreter process for each run**, on the machinery of bash transformations. *Bash bodies* holds for it: the process keeps its working directory, and the body is told when the code starts a nested `seamless-run`. By default one such run is in flight per process. With `process_lock` false they run side by side, each in its own interpreter process.
- **An in-memory backend embeds the interpreter in the process that runs the body.** That is the caller's process in `process` mode, and each worker process otherwise. A process has one embedded interpreter per language. It starts at its first use and lives until the process ends.
- **An in-memory backend of a handler language refuses to run without the lock.** A transformation that has `process_lock` false fails when its body starts, and so does a driver. The message names the CLI backend as the alternative. A result that is already recorded is still returned, because nothing runs. Python and compiled bodies in memory have no such rule: they run without the lock when `process_lock` is false, as always.
- **The process lock is the only lock around an embedded interpreter.** Among transformations that hold it, one body runs at a time in a process, so one transformation at a time uses the interpreter.
- **An in-memory body holds the lock from its start to its end.** It cannot give the lock up: there is no nesting signal as for a bash body. Code that submits nested work, for example by running `seamless-run`, belongs under the CLI backend.

Two facts about where bodies run matter to whoever writes a handler:

- **The lock gives exclusion, not a fixed thread.** A body never runs on the main thread of its process, and successive bodies in one process run on different threads. In `process` mode the thread that ran one body may no longer exist when the next body runs. An interpreter that must always be called from the same thread gets that thread from `run_in_interpreter_thread` (`contracts/handler-languages.md`, *Threads, and `run_in_interpreter_thread`*), not from the lock.
- **A body must not hold Python's GIL for seconds.** A worker pool checks each of its worker processes about once a second and restarts one that does not answer. A body that keeps the GIL for several seconds, as a call into an embedded interpreter can, makes its worker miss the check. The worker is restarted and the transformation fails. This holds in `spawn` and in both remote modes.

### Concurrency per backend

The lock is per process, so the number of bodies that run at once follows from the number of processes in which a backend runs bodies. A worker process accepts up to three transformations at once. That number is the transformation throttle. The lock then decides how many of their bodies run.

| Backend | Processes that run bodies | Bodies at once when every transformation keeps the default | Bodies at once with `process_lock` false |
|---|---|---|---|
| `process` | the caller's process | 1 | not limited by the lock |
| `spawn` with N workers | N worker processes | N, one per worker | up to 3 per worker, 3N in total |
| `remote: jobserver` with N workers | N worker processes | N, one per worker | up to 3 per worker, 3N in total |
| `remote: daskserver` | the Seamless worker processes inside each Dask worker | one per Seamless worker process | up to the throttle per Seamless worker process |

- **A transformation that waits for the lock occupies one of the slots of its worker while it waits.**
- **Bodies that do not hold the lock are not counted in the third column.** A parent that gave the lock up keeps its slot in its worker while it waits for its nested work, and so does a driver, but neither holds the lock.
- **On `remote: daskserver`, the lock does not decide how many transformations a Dask worker accepts.** Dask resources and the permission routine decide that (`seamless-dask/anti-deadlock.txt`).
- **The second column is also the number of embedded interpreters.** A handler language under an in-memory backend keeps one R or Julia interpreter in each process that has run such a body (*Handler languages and embedded interpreters*).

### Current limitations of the process lock

- **Dispatch does not look at the lock.** In a worker pool, a transformation can be given to a worker whose lock is held. It then waits for that lock, and it does not move when another worker becomes free.
- **A body that hangs blocks its process, not one slot.** Every transformation that is placed in that process afterwards and takes the lock waits behind it. In a worker pool, cancelling the hung transformation terminates its worker process and frees the lock. In `process` mode a cancel does not interrupt a body that runs inside the process, such as Python code, a compiled call or an embedded interpreter, so the lock stays held until the body returns (`contracts/cancellation.md`, *A transformation that waits for the process lock*). A bash body is different: a cancel kills its script, and the body then returns and frees the lock (`contracts/cancellation.md`, *A bash run that is cancelled*).

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
