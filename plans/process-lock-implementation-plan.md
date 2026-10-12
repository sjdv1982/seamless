# Process lock: implementation plan

Written 2026-10-11. Paths are relative to `/home/agent/seamless1`. Line numbers
are those of the working trees on that date.

This plan replaces `global_lock` with a per-process lock that every
transformation claims by default, removes the `chdir` from bash execution, and
makes nesting safe under that lock. It spans `seamless-transformer`,
`seamless-core`, `seamless-dask`, `seamless-workflow` and the docs in
`seamless/`.

## 0. What is ruled, and what this plan assumes

Ruled by the author (2026-10-11):

- **R1 — Bash stops changing the working directory.** The subprocess is started
  with `cwd=`, and job files are written by path. Bash keeps a lock.
- **R2 — `global_lock` becomes `process_lock`.** It is controlled by a meta
  parameter `process_lock` that is on by default: by default every
  transformation claims its process exclusively.
- **R3 — Dict level.** `driver` and `process_lock` are two boolean parameters
  in `__meta__`. Both true is invalid. Builders always write both. A reader
  treats an absent `driver` as false and an absent `process_lock` as
  `not driver`.
- **R4 — Runtime.** Any transformation that submits nested work drops the
  process lock, if it holds it, and never takes it again.
- **R5 — API.** On a Transformer, `process_lock` is true initially and becomes
  false when `driver` is set to true. Setting `driver` back to false does not
  set `process_lock` back to true. Setting `process_lock` to true while
  `driver` is true raises.
- **R6 — The inherited driver mark leaves the dict.** A transformation built
  while a driver runs no longer gets `driver: true` in its own meta. The mark
  travels as `driver_context` in the delegation payload. `driver` in the dict
  therefore means "this transformation is itself a driver".
- **R7 — `seamless-run` gets `--driver` and `--no-process-lock`.** `--driver`
  implies `--no-process-lock`.
- **R8 — Bash nesting is signalled, not inherited.** Every bash transformation
  that holds the lock exports an environment variable through which a nested
  `seamless-run` tells it "you are submitting nested work". The parent then
  drops its lock as in R4. The nested command keeps its own defaults; it does
  not become a driver.

- **R9 — A bound Transformer stores `process_lock` in the graph file's node
  metadata**, like `driver`. `driver`, `process_lock` and `scratch` are
  operational features and are part of the node's `config_token`. `streaming`
  is an interaction feature and is not.
- **R10 — The new `write_bash_job` parameter is keyword-only.**
- **R11 — The tests that take `global_lock` in a body declare the lock as
  metadata instead** (§5.3).

Proposed by this plan and accepted by the author (2026-10-11):

| | Choice | Why |
|---|---|---|
| A1 | The lock is dropped at submission, whether or not the nested result is a cache hit | Otherwise exclusivity depends on cache state |
| A2 | The R5 coupling is applied at the meta level, not only in the `driver` property | `tf.meta = {"driver": True}` is a separate route, and it is the one the `driver` setter uses |
| A3 | On a Transformation, both values are read-only | Its meta is already immutable |
| A4 | R4 covers submissions made through the Python API on the body's own thread or event loop. A thread that the body starts itself is not covered and needs `process_lock` off | Attribution follows the calling context (§3.4) |
| A5 | The lock is held around the body only, not around input resolution or result serialization | Holding it wider would also serialize downloads and uploads |
| A6 | A fingertip recompute counts as nested work | It runs a transformation in the same process while the requester waits |
| A7 | The name `global_lock` is retired without an alias | An alias to the real lock would self-deadlock every body that takes it |
| A8 | The signal of R8 is a named FIFO whose path is in the environment variable | A path survives `subprocess` with `close_fds=True`; an inherited file descriptor does not |
| A9 | A job that is cancelled while it waits for the lock in `process` mode does not run its body | Otherwise it starts later, when the lock frees |
| A10 | `_write_remote_bash_job` loses its `chdir` in the same phase as `execute_bash` | It shares `write_bash_job`, and it is the more damaging of the two defects (§2.5) |
| A11 | A relative read-folder path keeps failing as it does today | Making it absolute belongs in `_find_filesystem_path`, as a separate change |

## 1. The model

Terms used below:

- **Body**: the user code of a transformation, i.e. the Python function, the
  bash script or the compiled call.
- **Holder**: a body that currently holds the process lock.
- **Nested work**: a transformation whose execution is requested from inside a
  body.
- **Drop**: release the lock before the body ends and never take it again
  (R4).

There is one lock per process. The three legal states of a transformation:

| `process_lock` | `driver` | Meaning |
|---|---|---|
| true | false | Default. The body waits for the lock, runs while holding it, and drops it at its first nested submission |
| false | true | Declared driver. The body never takes the lock. Its submissions carry `driver_context` |
| false | false | Opt-out for a body that is safe to run next to others, for example I/O-bound work |

What the lock gives:

- **One active body per process.** `spawn(N)` and the jobserver then run at most
  N lock-claiming bodies at once. Today they run up to 3N (§2.1).
- **Protection of process-global state** for bodies that keep the default.

What it does not replace: the throttle slots, the Dask resource S and the
permission routine of [anti-deadlock.txt](../../seamless-dask/anti-deadlock.txt).
Those guard against idle parents exhausting slots and Dask threads. With R4 a
holder is never an idle parent, so the lock adds no resource that idle parents
can exhaust.

## 2. Code facts this plan relies on

Read in the source on 2026-10-11 unless marked **measured**. Measurements were
made with throwaway probes in the `seamless1` conda environment on a 14-core
machine; §5 describes them as tests.

### 2.1 The lock and concurrency today

- `global_lock` is a module-level `threading.Lock`
  ([\_\_init\_\_.py:17](../../seamless-transformer/seamless_transformer/__init__.py#L17)), re-exported by seamless-core
  ([transformer/\_\_init\_\_.py:14](../../seamless-core/seamless/transformer/__init__.py#L14)).
- In library code only `execute_bash` takes it
  ([execute_bash.py:223](../../seamless-transformer/seamless_transformer/execute_bash.py#L223), released at 369). Fourteen test files import or
  take it inside transformation bodies (§5.3).
- A worker child accepts up to three requests at once
  (`TRANSFORMATION_THROTTLE`, [worker.py:118](../../seamless-transformer/seamless_transformer/worker.py#L118); one semaphore per child,
  [worker.py:1315](../../seamless-transformer/seamless_transformer/worker.py#L1315)) and runs each on an executor thread ([worker.py:1076](../../seamless-transformer/seamless_transformer/worker.py#L1076)).
- Every body runs inside `run_transformation_dict` ([run.py:85](../../seamless-transformer/seamless_transformer/run.py#L85)). It has
  two callers: the worker child ([worker.py:1035](../../seamless-transformer/seamless_transformer/worker.py#L1035)) and in-process execution
  ([transformation_cache.py:131](../../seamless-transformer/seamless_transformer/transformation_cache.py#L131)). Inside it there are two body call sites:
  `call_compiled_transform(...)` and `_execute(...)`. Bash goes through
  `_execute`, whose code string calls `execute_bash`.
- Compiled calls in worker children take a second process-wide lock,
  `_COMPILED_OUTPUT_LOCK` ([run.py:715](../../seamless-transformer/seamless_transformer/run.py#L715)).
- **Measured**, 10 jobs of 1 s each:

  | Mode | Python, no lock | Python taking `global_lock` | Bash |
  |---|---|---|---|
  | `spawn(2)` | 6 at once, 3 per worker | 2 at once, 1 per worker | 2 at once, 1 per worker |
  | in-process | 10 at once | 1 | 1 |

### 2.2 Nested work today

- A nested submission from a worker child goes to the parent
  (`forward_to_parent`, [worker.py:3581](../../seamless-transformer/seamless_transformer/worker.py#L3581)). `_dask_available()` is false in
  workers ([transformation_class.py:306](../../seamless-transformer/seamless_transformer/transformation_class.py#L306)), so there is no other route.
- The parent dispatches it to a worker with a free slot, which can be the
  requester's own process, or refuses when all slots are taken
  ([worker.py:2490](../../seamless-transformer/seamless_transformer/worker.py#L2490)). On a refusal the child runs the nested job itself, on
  another thread of the same process ([worker.py:3650](../../seamless-transformer/seamless_transformer/worker.py#L3650)).
- In `process` mode a nested job runs in the same process on another executor
  thread ([transformation_cache.py:1039](../../seamless-transformer/seamless_transformer/transformation_cache.py#L1039)).
- A fingertip can recompute a transformation in the requesting process:
  `Checksum.fingertip` ([checksum_class.py:478](../../seamless-core/seamless/checksum_class.py#L478)) calls
  `recompute_from_transformation_checksum`
  ([transformation_cache.py:1458](../../seamless-transformer/seamless_transformer/transformation_cache.py#L1458); sync form at 1484) with `force_local=True`.
- The public entry points that schedule a Transformation are `start`
  ([transformation_class.py:1275](../../seamless-transformer/seamless_transformer/transformation_class.py#L1275)), `_compute` (1159; behind `compute`, `run`
  and a direct call), `computation` (1216) and `task` (1437). `parallel()`
  uses `task`. `seamless-run` uses `computation`
  (`compute_transformation_sync`, [transformation_class.py:1766](../../seamless-transformer/seamless_transformer/transformation_class.py#L1766)).
- **Measured**, emulating R2 with today's `global_lock` (leaves always hold
  it):

  | Outer transformation | in-process | `spawn(2)` |
  |---|---|---|
  | holds the lock throughout and waits on a `delayed` leaf | hangs with 1 outer | fine with 1 outer, hangs with 2 or 6 |
  | holds the lock throughout and calls a nested `@direct` function | hangs | hangs on `spawn(1)` |
  | holds the lock for its own work, drops it at the first nested launch | fine with 3 outers | fine with 8 outers |
  | never takes the lock | fine | fine |

  The third row was run with sync bodies and with bodies that await nested
  tasks in their own event loop. No two leaves overlapped in one process. The
  hangs are silent.

### 2.3 `driver` today

- `Transformer.driver` writes `meta["driver"]` through the `meta` setter
  ([transformer_class.py:722](../../seamless-transformer/seamless_transformer/transformer_class.py#L722), [transformer_class.py:648](../../seamless-transformer/seamless_transformer/transformer_class.py#L648)).
- A body whose meta has `driver` runs under a thread-local driver context
  ([run.py:36-50](../../seamless-transformer/seamless_transformer/run.py#L36-L50), [run.py:131](../../seamless-transformer/seamless_transformer/run.py#L131)).
- Every transformation built while that thread-local is active gets
  `driver: True` written into its own meta (`_collect_tf_dunder`,
  [transformation_class.py:1588](../../seamless-transformer/seamless_transformer/transformation_class.py#L1588)). `start()` re-establishes the thread-local on
  the loop and compute threads so that this write sees it
  ([transformation_class.py:1306-1340](../../seamless-transformer/seamless_transformer/transformation_class.py#L1306-L1340), `_compute_in_thread` at 1192).
- **Measured**: a leaf launched by a declared driver sees the driver context in
  `spawn(2)` and does not see it in-process.
- Readers of the flag:
  - the parent's delegate handlers skip the permission routine
    ([worker.py:2338](../../seamless-transformer/seamless_transformer/worker.py#L2338), [worker.py:2823](../../seamless-transformer/seamless_transformer/worker.py#L2823)). They also read a payload key
    `driver_context` that nothing sends;
  - `_skip_permission_gate` ([transformation_mixin.py:598](../../seamless-dask/seamless_dask/transformation_mixin.py#L598));
  - the Dask client: a driver submission skips the future cache and gets a
    fresh `-copy` key ([client.py:1632-1645](../../seamless-dask/seamless_dask/client.py#L1632-L1645), 1675, 1801, 1819).
- Every base task claims `S: 1`, drivers included ([client.py:1701](../../seamless-dask/seamless_dask/client.py#L1701)).

### 2.4 Meta transport

- `__meta__` is outside the transformation checksum
  ([transformation_utils.py:19](../../seamless-transformer/seamless_transformer/transformation_utils.py#L19), `tf_get_buffer` at 43). At execution it is
  merged from the dict and from `tf_dunder`, the latter winning
  ([transformation_utils.py:182](../../seamless-transformer/seamless_transformer/transformation_utils.py#L182)).
- Some executions carry no meta:
  - a fingertip recompute resolves the dict from its checksum and takes the
    dunder from an in-memory cache that returns `{}` when it has none
    ([transformation_cache.py:367](../../seamless-transformer/seamless_transformer/transformation_cache.py#L367));
  - `seamless-run-transformation` without a dunder file
    ([run_transformation.py:243](../../seamless-transformer/seamless_transformer/api/run_transformation.py#L243));
  - graphs saved before this change.
- A bound Transformer keeps `driver` in the node's `meta` mapping
  ([configuration.py:56](../../seamless-workflow/seamless_workflow/configuration.py#L56), [builder_state.py:1037](../../seamless-workflow/seamless_workflow/builder_state.py#L1037)). The graph serializes
  that mapping ([serialization.py:77](../../seamless-workflow/seamless_workflow/serialization.py#L77)), and it is part of the node's
  `config_token` ([configuration.py:96-100](../../seamless-workflow/seamless_workflow/configuration.py#L96-L100)). `streaming` is deliberately not in
  the token: "toggling it must never re-run a node".
- `seamless-run` builds its meta from `--ncores` and `--write-remote-job`
  ([main.py:665-674](../../seamless-transformer/seamless_transformer/cmd/api/main.py#L665-L674)) and puts it in the dict
  ([bash_transformation.py:119](../../seamless-transformer/seamless_transformer/cmd/bash_transformation.py#L119)). It has no `--driver`.

### 2.5 Bash

- `execute_bash` changes the process working directory at
  [execute_bash.py:227](../../seamless-transformer/seamless_transformer/execute_bash.py#L227) and back at 218 and 363. `_write_remote_bash_job` does
  the same without any lock ([run.py:293-320](../../seamless-transformer/seamless_transformer/run.py#L293-L320)).
- The wait loop multiplexes stdout and stderr with a selector and ends when
  both pipes close ([execute_bash.py:249-283](../../seamless-transformer/seamless_transformer/execute_bash.py#L249-L283)).
- A `seamless-run` started inside a bash body of a worker is an independent
  client of the same backend when `SEAMLESS_REMOTE_CLIENTS` is in the
  environment ([main.py:209](../../seamless-transformer/seamless_transformer/cmd/api/main.py#L209), [main.py:933](../../seamless-transformer/seamless_transformer/cmd/api/main.py#L933)). Its job can be dispatched to the
  process that runs the outer bash body.
- **Verification of R1** by a subagent, with a prototype swapped in for the
  real module (2026-10-11):
  - 38 scenarios compared current code and prototype on the returned
    environment, the job directory tree, the result or exception, and what bash
    sees (`$PWD`, file layout, environment). 35 were identical. The 3
    differences are the text of an `OSError` on failed job setup, which now
    carries the absolute temporary path.
  - With bash transformations running in-process, 3280 of 3650 relative-path
    reads in other threads failed on current code and 0 of 3257 on the
    prototype. A Python body in a spawned worker running nested bash: 746 of
    807 failed, then 0.
  - Two forced interleavings of `execute_bash` and `_write_remote_bash_job` on
    current code: "RESULT does not exist" with the remote job's files written
    to the process's start directory; and the process left permanently in the
    job directory.
  - One of 22 prototype runs printed an `_frozen_importlib._DeadlockError`
    from import code in seamless-remote and seamless-core. Results were
    correct and it did not recur. Unexplained (§8).

### 2.6 Cancellation

- In `process` mode a cancel marks the submission and fails its future. The
  body thread is not interrupted ([transformation_cache.py:749](../../seamless-transformer/seamless_transformer/transformation_cache.py#L749)).
- In a worker, a cancel terminates the child process, which releases any lock
  it held.

## 3. Design

### 3.1 The dict contract (R3)

One function in `transformation_utils.py` is the only place that interprets the
two keys:

```python
def resolve_lock_meta(meta) -> tuple[bool, bool]:
    """Return (process_lock, driver). Absent driver = False; absent
    process_lock = not driver. Raises on both true or on a non-boolean."""
```

- **Builders** call it and write both values back, so every dict they emit
  carries both. The builder choke point is `_collect_tf_dunder`
  ([transformation_class.py:1571](../../seamless-transformer/seamless_transformer/transformation_class.py#L1571)); `seamless-run` reaches it through
  `transformation_from_dict`.
- **The executor** calls it on the merged meta in `run_transformation_dict`,
  before anything else. An invalid combination fails the transformation with a
  message that names both keys.
- Code that passes an existing dict through, such as
  `seamless-run-transformation`, is a reader. It does not rewrite the meta.

### 3.2 The lock module

New module `seamless_transformer/process_lock.py`. It owns the lock; nothing
else touches it.

```python
NOTIFY_ENV = "SEAMLESS_PROCESS_LOCK_NOTIFY"

@contextmanager
def scope(claim: bool, *, should_abort=None): ...
def current_holder(): ...
def drop_for_nested_work() -> None: ...
```

- `scope(claim)` wraps one body. With `claim` true it waits for the lock,
  records a holder for the calling context and releases on exit unless the
  holder was dropped. With `claim` false it records "no holder" for the calling
  context, so a body without the lock never sees an outer holder.
- The wait is a loop of timed `acquire` calls. Between attempts it calls
  `should_abort()`; when that returns true it raises
  `TransformationCancelledError` and the body does not run (A9).
- `drop_for_nested_work()` releases the current holder's lock if it still
  holds it. It is idempotent, safe from any thread, and a no-op for a holder
  whose body has ended. With no holder in the calling context it notifies the
  parent process instead, if `NOTIFY_ENV` is set (§3.6).
- The holder is kept in a `contextvars.ContextVar`, not a thread-local. A
  context variable also reaches coroutines that the body starts and work
  scheduled with `run_coroutine_threadsafe`. It does not cross
  `run_in_executor` or a new thread, which is what gives every nested body a
  fresh context.

### 3.3 Where the lock is taken (A5)

In `run_transformation_dict`, around the two body call sites only
(`call_compiled_transform` and `_execute`). Input resolution, module building
and result serialization stay outside.

- `execute_bash` no longer takes a lock. It finds the holder with
  `current_holder()`.
- Lock order is process lock, then `_COMPILED_OUTPUT_LOCK`. A compiled body
  cannot submit nested work, so that order never inverts.
- `run_transformation_dict` gains an optional `should_abort` parameter and
  hands it to `scope`. The in-process caller passes one that reads its active
  submission. The worker child passes nothing: there a cancel kills the
  process.

### 3.4 Dropping on nested submission (R4, A1, A4, A6)

`drop_for_nested_work()` is called first thing in:

| Site | Covers |
|---|---|
| `Transformation.start` | `.start()` |
| `Transformation._compute` | `.compute()`, `.run()`, a direct call |
| `Transformation.computation` | `await tf.computation()`, `seamless-run` |
| `Transformation.task` | `.task()`, `parallel()`, `parallel_async()` |
| `recompute_from_transformation_checksum` and its sync form | fingertip recompute |

- The first four run on the thread that called them, which for a body is the
  body's thread or a coroutine of its loop. They fire before it is known
  whether the result is cached (A1).
- The fingertip site is reached through coroutine helpers. One of them,
  `_run_coro_in_worker_thread` ([checksum_class.py:33](../../seamless-core/seamless/checksum_class.py#L33)), starts a plain thread
  and loses the context. It must run its target inside
  `contextvars.copy_context()`.
- Not covered: a submission from a thread the body created itself (A4), and a
  body that only reads a handle it was given.

### 3.5 The driver context (R6)

- At the same four Transformation entry points, record on the Transformation
  whether the caller is inside a driver body (`is_driver_context()`).
- Pass that value down explicitly: the evaluators hand it to
  `TransformationCache.run`, which hands it to `forward_to_parent`, which puts
  `driver_context` in the payload. The parent's handlers already read it.
- Delete the write at [transformation_class.py:1588](../../seamless-transformer/seamless_transformer/transformation_class.py#L1588).
- Remove the two places that re-establish the thread-local off the body thread
  (`_run_with_driver` in `start`, and the `driver_context` argument of
  `_compute_in_thread`), once nothing reads it there.
- `_skip_permission_gate` returns true for the transformation's own `driver`
  or for the recorded context.

Consequences, both intended:

- A grandchild of a driver goes through the permission routine again, as
  [anti-deadlock.txt](../../seamless-dask/anti-deadlock.txt) describes.
- A leaf launched by a driver is deduplicated by the Dask client like any
  other transformation.

### 3.6 Bash (R1, R7, R8)

**No `chdir`.** `write_bash_job` gets a keyword-only `directory=None` and
resolves every job path under it. `execute_bash` and `_write_remote_bash_job`
pass it and never call `os.chdir`. The sites, by line in today's
`execute_bash.py`. The list comes from the verification of §2.5; lines 182,
218, 225-227 and 363 were re-checked for this plan:

| Lines | What | Change |
|---|---|---|
| 36-37 | `_write_file`: `makedirs`, `open` (callers at 73, 92, 120, 122) | join with `directory` |
| 78-80 | `makedirs` for a filesystem pin in a subdirectory | join |
| 84 | `os.symlink(v, pin)` | join the link name only |
| 86 | `open(v)` from a read folder | join, which keeps today's failure for a relative `v` (A11) |
| 98-105 | `write_to_directory(directory_pin, …)` | pass the joined path |
| 106 | `env[pin] = directory_pin` | **unchanged**: the variable stays relative |
| 126, 129 | numpy pins, written without `_write_file` | join |
| 140-143 | `conda info --base` | pass `cwd=directory` |
| 169-171 | script file and `chmod` | join |
| 182 | `resultfile = "RESULT"`, read at 308, 325, 328, 330-333, 354 | `os.path.join(tempdir, "RESULT")` |
| 225-227 | `getcwd`, `mkdtemp`, `chdir` | no `getcwd`, no `chdir`; `os.path.abspath(mkdtemp(...))` |
| 237-245 | `Popen` | add `cwd=tempdir` |
| 218, 363 | `chdir` back in the signal handler and in `finally` | remove |

In `run.py`, `_write_remote_bash_job` passes `directory=job_directory` and
loses its four `chdir`/`getcwd` lines (293, 306, 315, 320).

**Signalling a nested submission.** In `execute_bash`:

- If the current holder still holds the lock: create a FIFO next to the job
  directory (not inside it, so the script's file layout is unchanged), keep a
  read-write descriptor on it so the selector never sees end-of-file, put its
  path in `NOTIFY_ENV` in the child's environment, and register it with the
  selector.
- Otherwise remove `NOTIFY_ENV` from the child's environment, so a nested
  command does not signal a process further up.
- When a byte arrives, call the holder's drop.
- The loop must keep watching the FIFO until the process has exited, not only
  until both output pipes close.
- Remove the FIFO in `finally`.

The sending side is the last branch of `drop_for_nested_work()` (§3.2): a
process with no holder in the calling context and `NOTIFY_ENV` set opens the
FIFO for non-blocking write, writes one byte, and ignores every error. Once per
process is enough. `seamless-run` reaches this through
`Transformation.computation`; its `--qsubmit` path does not compute and calls
it explicitly.

The signal does not cross ssh or a container boundary. A bash body that nests
through one of those must be declared with `--driver` or `--no-process-lock`.

**Flags.** `seamless-run --driver` sets `driver: true`; `--no-process-lock`
sets `process_lock: false`; `--driver` implies the latter. Both go into the
meta that `prepare_bash_transformation` receives.

### 3.7 The API (R5, A2, A3)

One helper applies an update to a meta mapping and is used by every setter:

```python
def apply_lock_meta_update(meta: dict, update: dict) -> None: ...
```

| Update | Effect |
|---|---|
| `driver: True` | sets `driver: True` and `process_lock: False` |
| `driver: False` or `None` | clears `driver`; `process_lock` is left as it is |
| `process_lock: True` while `driver` is true | raises |
| `driver: True` and `process_lock: True` together | raises |
| `process_lock: False` | sets it |

- **Standalone Transformer.** New property `process_lock`. The `driver` and
  `process_lock` setters and the `meta` setter all go through the helper. A new
  Transformer has neither key in `_meta`; the properties return `True` and
  `False` by the absent rule, and the dict gets both explicitly when the
  Transformation is built.
- **Transformation.** Read-only, through `.meta`.
- **Bound Transformer (R9).** The same helper in `_set_node_config` for the
  fields `driver`, `meta` and a new `process_lock`. The value is stored in the
  node's `meta` mapping, next to `driver`, and is saved in the graph file with
  it.

### 3.8 Retiring `global_lock` (A7)

- Remove it from both export lists and from `seamless_transformer/__init__.py`.
- `seamless_transformer.__getattr__` raises an `AttributeError` for the name,
  with a message that points to the `process_lock` meta parameter when the
  attribute is accessed directly. A `from ... import global_lock` statement
  fails with Python's generic `ImportError`; its message need not contain the
  pointer.
- `seamless.transformer` has no module `__getattr__` today. It needs one that
  forwards the attribute access, so direct access gets the pointer message and
  a `from ... import global_lock` statement fails with the generic `ImportError`.
- No public lock object replaces it.

## 4. Phases

| Phase | Depends on | Changes behaviour for users? |
|---|---|---|
| A — Bash without `chdir` | nothing | No, apart from `OSError` text on failed job setup |
| B — Driver context leaves the dict | nothing | Dask: grandchildren of a driver go through permission; leaves under a driver are deduplicated |
| C — Dict contract and API | B | New properties and flags; no runtime effect yet |
| D — The runtime lock | C | Yes: this is the switch |
| E — Bash nesting signal | A, D | A bash body that calls `seamless-run` no longer blocks its own nested job |
| F — Bound Transformers | C | New node setting, saved in the graph file |
| G — Docs | written alongside | — |

B must land before C. Otherwise a default leaf built under a driver carries
both values as true and the builder rejects it.

Before Phase A, run every test file of seamless-transformer, seamless-dask and
seamless-workflow once, one pytest process per file, and keep the list of
failures as the baseline.

The user waived this full pre-change baseline for this run; no full baseline
was collected.

### Phase A — Bash without `chdir`

- The changes of §3.6, "No `chdir`". The lock is untouched: `execute_bash`
  still takes `global_lock`.
- **Exit:** the bash test files of §5.1 pass; `os.chdir` and `os.getcwd` no
  longer occur in `execute_bash.py` or in `_write_remote_bash_job`.

### Phase B — Driver context leaves the dict

- The changes of §3.5.
- **Exit:** the tests of §5.2 pass; `grep` finds no write of `driver` into a
  child's meta.

### Phase C — Dict contract and API

- `resolve_lock_meta` and `apply_lock_meta_update` (§3.1, §3.7).
- `_collect_tf_dunder` writes both keys.
- Standalone Transformer properties and setters.
- `seamless-run --driver` and `--no-process-lock`.
- The executor does not read `process_lock` yet.
- **Exit:** the tests of §5.2 for this phase pass; the baseline is unchanged.

### Phase D — The runtime lock

- `process_lock.py` (§3.2).
- `run_transformation_dict` resolves the two flags and wraps the body sites
  (§3.3). `execute_bash` stops taking a lock.
- The five drop sites and the context fix in seamless-core (§3.4).
- `should_abort` from the in-process caller (§3.3).
- Retire `global_lock` (§3.8) and remove it from the tests (§5.3).
- **Exit:** the tests of §5.2 for this phase pass; every difference from the
  baseline is classified as an intended timing change, a test that took
  `global_lock`, or a defect.

### Phase E — Bash nesting signal

- The FIFO in `execute_bash` and the sending branch (§3.6).
- **Exit:** the tests of §5.2 for this phase pass.

### Phase F — Bound Transformers

- `process_lock` in the node's `meta` mapping, with the coupling of §3.7 (R9).
- A graph saved without the key loads with the absent rule of R3.
- `process_lock` is part of the node's `config_token` with the rest of the
  `meta` mapping, as `driver` is. No special case (R9).
- **Exit:** a bound and a standalone Transformer with the same settings build
  dicts with the same two values.

### Phase G — Docs

The pages of §6.

## 5. Tests

Run with `/home/agent/miniforge3/envs/seamless1/bin/python`, one pytest process
per file, from the repository root of the package under test.

### 5.1 Existing tests that must change

Phase A:

- [test_contract_bash_output.py](../../seamless-transformer/tests/test_contract_bash_output.py): the two `write_bash_job` mocks
  (`lambda code, *args`) must accept keyword arguments.
- Same file, `test_bash_cleanup_failure_releases_lock_and_uses_safe_session`:
  it injects a failure into the `chdir` back. Rewrite it to inject the failure
  into `shutil.rmtree` and to assert that `os.chdir` is never called.
- [test_remote_job_paths.py](../../seamless-transformer/tests/test_remote_job_paths.py), `test_write_remote_bash_job_expands_user`: it
  asserts that the working directory is the job directory. Assert the
  `directory` argument instead.
- Must pass unchanged: `test_bash_transformer.py`,
  `test_execute_bash_directory_inputs.py`, `test_bash_pretransformation.py`,
  `test_write_remote_job_mode.py`, `test_meta_variables.py`, `test_metafile.py`.

Phase C:

- [test_run_transformation_cli.py](../../seamless-transformer/tests/test_run_transformation_cli.py) line 247 asserts an exact `__meta__`.
  It should stay true, because that CLI is a reader. Check it.

### 5.2 New tests

Phase A:

- A watcher thread asserts that `os.getcwd()` never changes while bash
  transformations run in-process, and a second thread does relative-path reads
  throughout.
- The same from a Python body in a spawned worker that runs nested bash.

Phase B:

- A leaf launched by a declared driver reports `is_driver_context()` false,
  in-process and on `spawn(2)`.
- The delegation payload of a driver's direct child has `driver_context` true;
  that of a grandchild launched by an undeclared child does not.

Phase C:

- Every row of the table in §3.7, through the `driver` setter, the
  `process_lock` setter and the `meta` setter.
- `driver = True` then `driver = False` leaves `process_lock` false.
- A built dict always carries both keys.
- `resolve_lock_meta`: both absent; only `driver: true`; both true; a
  non-boolean.
- `seamless-run --driver` and `--no-process-lock` produce the expected meta.

Phase D:

- **Exclusivity.** 10 sleeping jobs on `spawn(2)`: at most 1 at a time per
  worker pid, 2 overall. In-process: at most 1. For Python, bash and a compiled
  transformer.
- **Opt-out.** The same with `process_lock = False`: 3 per worker pid on
  `spawn(2)`.
- **Undeclared nesting does not hang.** The outer does its own work, then
  launches two leaves. Variants: `.run()`, `.start()` then `.run()`, a nested
  `@direct` call, an async body that gathers `.task()` results, and
  `.start()` followed by a sleep loop that polls the handle. In-process with
  3 outers and on `spawn(2)` with 8 and with 12. Both exceed the six slots, so
  that some nested jobs are refused and run inline. No two leaves overlap in
  one process.
- **The outer's own work is exclusive until its first launch.**
- **A declared driver starts while its process's lock is busy.**
- **Fingertip inside a holding body.** A body that fingertips a checksum whose
  buffer must be recomputed; also from a coroutine of the body's own loop,
  which takes the `_run_coro_in_worker_thread` route.
- **Invalid meta.** A dict with both values true fails before the body runs.
- **Cancellation.** In-process, a job queued behind a long holder is
  cancelled; its body never runs (observe a side-effect file). Then run the
  whole `tests/cancellation` suite.
- **Retired name.** Direct attribute access through `seamless_transformer` or
  `seamless.transformer` raises `AttributeError` with the pointer to
  `process_lock`. A `from seamless.transformer import global_lock` statement
  fails with Python's generic `ImportError`; do not assert pointer text there.

Phase E:

- Without services: call `execute_bash` inside `scope(True)` with a script
  that writes one byte to `"$SEAMLESS_PROCESS_LOCK_NOTIFY"` and then sleeps.
  A second thread acquires the process lock while the script still runs.
- The variable is absent from the script's environment under `scope(False)`
  and after the holder was dropped.
- A script that closes stdout and stderr before it writes the byte still gets
  its lock dropped.
- With a jobserver started with `--workers 1`: an undeclared bash
  transformation whose script runs `seamless-run` on a leaf completes.

### 5.3 Test files that take `global_lock` in a body (R11)

Fourteen files. They are adapted to test the lock as metadata, not merely
stripped of the old name. In each file:

- Remove the import and the `with global_lock:` block.
- Declare on the transformer what its body used to do: `process_lock = True`
  where the body took the lock, and `process_lock = False` where the body did
  not take it and the test's timing depends on bodies overlapping in one
  process. For a transformer that is created inside another body, set it
  there.
- Use the `process_lock` property in some files and the `meta` setter in
  others, so that both routes are exercised.
- Keep the timing assertions; they now test the metadata.
- Assert that the built transformation carries the declared value in its meta.

The files:

- seamless-transformer/tests: `test_dependencies.py`,
  `test_nested_transformations_multi.py`,
  `test_nested_transformations_multi_async.py`,
  `test_nested_transformations_multi_spawn.py`, `test_sync_in_running_loop.py`,
  `test_transformation.py`, `test_transformation_async.py`,
  `test_transformation_async_spawn.py`.
- seamless-transformer/tests/dask: `test_dependencies.py`,
  `test_nested_transformations_multi.py`, `test_transformation.py`,
  `test_transformation_async.py`.
- seamless-dask/tests: `test_dependencies.py`,
  `test_nested_transformations_multi.py`.

`test_contract_bash_output.py` monkeypatches the lock itself and is rewritten
in Phase D against `process_lock.py`.

Other tests, outside these fourteen, that rely on bodies overlapping in
`process` mode will slow down or fail their timing bounds. Give those bodies
`process_lock = False` where the overlap is what the test is about; otherwise
adjust the bound.

## 6. Docs

- [anti-deadlock.txt](../../seamless-dask/anti-deadlock.txt): add the lock, the rule R4, and why it is not a
  resource that idle parents can exhaust.
- [parallelism.md](../docs/main/parallelism.md): `process` mode runs one body at a time by default;
  `spawn(N)` runs N; how to opt out.
- [composition.md](../docs/main/composition.md): nesting works without a declaration; what `.driver = True`
  adds.
- Contract pages: `transformers.md` (`process_lock`, `driver`),
  `execution-backends.md` (concurrency per backend),
  `seamless-run-and-argtyping.md` (the two flags), `cancellation.md` (a job
  queued on the lock), and `scratch-witness-audit.md` line 136, which says a
  launched transformation carries `__meta__["driver"]`.
- [seamless-dask/README.md](../../seamless-dask/README.md) and its copy under `docs/main/api/`.
- The generated API pages under `docs/agent/api/python/`: regenerate.
- Other plans:
  - `bash-docker-conda-transformers-plan.md`: D12, §4.1 and the Phase 1
    bullet say the lock goes. Under R2 it stays as the process lock, so
    container jobs run one per process unless `process_lock` is off. That plan
    is still being drafted in another session. The author will have it follow
    the decisions of this plan; this plan does not edit it.
  - `transformation-logs-porting-plan.md` §6: the `chdir` entry is resolved
    by Phase A.
  - `julia-r-support.md`: the `SEAMLESS_INTERPRETER_THREAD=0` switch names
    `global_lock`.

## 7. Decisions

None are open. Everything this plan needed decided is in §0, ruled or accepted
by the author on 2026-10-11.

## 8. Risks and unverified points

- **Nothing in this plan was run on Dask.** The deadlock reasoning for Dask in
  §1 is from the code.
- **The unexplained `_DeadlockError`** of §2.5. Watch for it in Phase A.
- **In-process context propagation.** §3.4 depends on the context variable
  reaching the fingertip recompute. Only the helper named there was read; the
  Phase D fingertip tests are the check.
- **A body that starts its own threads** and submits from them is not covered
  (A4). The symptom is the silent hang of §2.2.
- **The signal of R8 needs a shared filesystem view** between the bash body
  and the nested command.
- **Timing-sensitive tests.** `process` mode becomes serial for every body
  that keeps the default.
- **Load figure.** A job that waits for a lock occupies a throttle slot. The
  permission routine reads slot occupancy as load
  ([permissions.py:170](../../seamless-dask/seamless_dask/permissions.py#L170)) and will deny more often. Not measured.
- **A hung body now blocks its process**, not one slot, until it is cancelled.

## 9. Noticed, not in this plan

- **The dispatcher does not know about the lock.** `_dispatch` still puts a
  second and third job on a worker whose lock is busy
  ([worker.py:1410](../../seamless-transformer/seamless_transformer/worker.py#L1410)), and they cannot move when another worker frees up.
  Counting lock-claiming jobs per worker in the dispatcher would fix that.
- **S could be exact.** The permission routine raises S by one per granted
  nested submission. The number of dropped locks on a Dask worker is the exact
  number of idle parents there.
- **Drivers pin S.** A driver skips the permission routine but keeps its
  `S: 1` while idle, and nothing lends it back.
