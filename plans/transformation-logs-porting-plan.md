# Transformation logs porting plan

This plan ports the legacy `Transformer.logs` attribute (stdout, stderr and
execution time of a transformation) to the current codebase. It also fixes the
output-capture bugs found on the way and removes `direct_print`, which
`streaming` supersedes.

It spans `seamless-transformer`, `seamless-dask`, `seamless-jobserver`,
`seamless-remote`, `seamless-workflow` and the docs in `seamless/`.

## 0. What is ruled, and what this plan adds

Ruled by the author (2026-10-10):

- **Streaming is Dask-only.** `process`, `spawn` and `remote: jobserver` ignore
  the flag. That is contract, not a gap.
- **Execution time is the dispatcher-side measurement**, the same number as the
  execution record's `wall_time_seconds`. It includes queueing, IPC and input
  resolution, so it is not comparable to the legacy child-side number. That is
  contract.
- **`direct_print` is superseded by `streaming`.** Its wiring is removed or
  replaced.
- **The stdout race and the deadlocks are bugs.**
- **Otherwise legacy `.logs` behaviour is the contract, more or less.**

Eight further points, D1 to D8, go beyond those rulings. The author ruled all
eight as listed here (2026-10-10).

| | Legacy | Ruled | Reason |
|---|---|---|---|
| D1 | Bash stderr merged into stdout (`stderr=STDOUT`); everything under "Standard output" | Keep the two streams separate; drain both pipes together | Merged lines are `print`ed to stdout. In `process` mode that is the caller's stdout, where `seamless-run` writes its result ([main.py:1384](../../seamless-transformer/seamless_transformer/cmd/api/main.py#L1384)). A command's stderr would land in the result stream. Cost: the log loses the interleaving order of the two streams. |
| D2 | In-process execution captured nothing and had no logs; the default was a forked child, which did capture | Capture in-process too, as a tee: output still goes live to the caller's streams and is also retained | `process` is today's default. Without capture, `.logs` in the default mode carries no output. Rejected alternative: no capture, with `.logs` in `process` mode holding the Execution time only. |
| D3 | Failure text ended with an `Execution time` line (child clock) | No time line on failure; time is reported for successful runs only | The ruled clock feeds the execution record, and records are success-only. Adding the line means measuring and appending at three dispatch sites and changes `.exception` text on every backend. |
| D4 | A "Result" section showed the decoded value (truncated), or `<checksum …>` when a buffer server took the result | No Result section | Author's ruling, replacing an earlier one for a `<checksum HEX>` line. The result is read from the handle. A log that showed the value would have to resolve the result buffer, which is unwanted for scratch results and can fail with a cache miss. |
| D5 | `.logs` was `None` after a successful remote run | Jobserver and Dask return the logs | The legacy `None` was a transport limitation. Truncation bounds the payload to about 20,000 characters per run. |
| D6 | Logs lived in memory per transformation, unbounded for imperative use | One process-wide store keyed by `tf_checksum`, with a size-bounded LRU; an evicted entry reads as `None` | The result cache next to it is unbounded, but each of its entries is a pair of checksums; a log entry can hold about 20,000 characters. |
| D7 | Compiled transformers: fd-level capture (`wurlitzer`) around the call | Port it, in worker children only, under a child-wide lock | fd redirection is process-global, so correct attribution allows one compiled call at a time per child. Adds the `wurlitzer` dependency. Rejected alternative: leave C-level output uncaptured, as `contracts/streaming.md` states today. |
| D8 | `--direct-print` on `seamless-run` and `seamless-run-transformation` | Replace with `--streaming`; streamed text is rendered on stderr | Both CLIs write their result or checksum on stdout. |

## 1. Code facts this plan relies on

All read in the source on 2026-10-10; none of it was run.

**Capture today**

- A worker child handles up to three requests at once
  (`TRANSFORMATION_THROTTLE`, [worker.py:117](../../seamless-transformer/seamless_transformer/worker.py#L117)), each on an executor thread
  ([worker.py:891](../../seamless-transformer/seamless_transformer/worker.py#L891)).
- Each request assigns the process-global `sys.stdout` and `sys.stderr` and
  restores the previous values in `finally`
  ([worker.py:745-767](../../seamless-transformer/seamless_transformer/worker.py#L745-L767)). There is no lock and no per-thread routing.
- The buffers are read only when the result is a failure string
  ([worker.py:777-797](../../seamless-transformer/seamless_transformer/worker.py#L777-L797)). On success they are dropped.
- A nested transformation that the child runs itself after a refused
  delegation goes through `_execute_transformation`, which sets up no capture
  ([worker.py:656](../../seamless-transformer/seamless_transformer/worker.py#L656); call sites at 3158, 3174, 3195).
- In-process execution has no capture
  (`run_in_executor(None, run_transformation_dict, …)` in `_run_uncached`,
  [transformation_cache.py:728](../../seamless-transformer/seamless_transformer/transformation_cache.py#L728)).

**Bugs**

- *Race.* With requests A and B overlapping in one child: A's later prints go
  to B's buffer; when A exits, B's prints go to the real stdout; when B exits
  it restores A's wrapper, which A has already detached. From then on the
  child's `sys.stdout` is a detached wrapper whenever no request is running,
  and a print outside a request raises `ValueError`.
- *tqdm.* `_active_patch()` returns the last installed patch
  ([stream_tqdm.py:23](../../seamless-transformer/seamless_transformer/stream_tqdm.py#L23)), so a bar created by request A binds to
  request B's stream. The module-level `tqdm` is patched once and restored by
  whichever patch exits first, so a second streaming request loses its patch
  mid-run.
- *Bash deadlock.* stdout and stderr are separate pipes
  ([execute_bash.py:231-239](../../seamless-transformer/seamless_transformer/execute_bash.py#L231-L239)). stderr is read only after stdout reaches
  EOF and only on a non-zero exit. A script that fills the stderr pipe blocks
  forever, holding `global_lock`, which blocks every later bash transformation
  in that process.
- *Bash lock leak.* `global_lock.acquire()` sits inside the `try`, and
  `finally` runs `os.chdir(old_cwd)` before `global_lock.release()`
  ([execute_bash.py:219](../../seamless-transformer/seamless_transformer/execute_bash.py#L219), 324-326). If that `chdir` raises, the lock is
  never released.
- *Bash `preexec_fn`.* `preexec_fn=os.setsid` runs Python code between fork
  and exec in a multi-threaded process, which the `subprocess` docs warn can
  deadlock the child.

**Transport seams**

- The child returns `Checksum` on success, `str` on an execution failure and
  an error-envelope `dict` otherwise
  ([worker.py:803-868](../../seamless-transformer/seamless_transformer/worker.py#L803-L868)).
- `dispatch_to_workers` ([worker.py:2955](../../seamless-transformer/seamless_transformer/worker.py#L2955)) has three callers that own a
  dispatcher-side clock: `_run_uncached` (spawn), the jobserver
  ([jobserver.py:644](../../seamless-jobserver/jobserver.py#L644)) and Dask's `_run_base`
  ([client.py:972](../../seamless-dask/seamless_dask/client.py#L972)).
- The delegation path also sends `execute_transformation` requests and
  type-checks the bare `Checksum` reply
  (`_handle_delegate_transformation`, [worker.py:2358](../../seamless-transformer/seamless_transformer/worker.py#L2358); `forward_to_parent`,
  [worker.py:3118](../../seamless-transformer/seamless_transformer/worker.py#L3118)).
- The jobserver's success response is a dict that already carries
  `record_runtime` ([jobserver.py:707-719](../../seamless-jobserver/jobserver.py#L707-L719)).
- Dask's base result is a 4-tuple and the thin result a 3-tuple
  ([client.py:1308-1344](../../seamless-dask/seamless_dask/client.py#L1308-L1344)). The thin tuple is unpacked in three places:
  [transformation_mixin.py:339](../../seamless-dask/seamless_dask/transformation_mixin.py#L339), line 482, and the delegate
  `_submit` in `worker.py`.
- `TransformationCache` keeps `tf_checksum → result` in a plain dict for the
  life of the process ([transformation_cache.py:187](../../seamless-transformer/seamless_transformer/transformation_cache.py#L187)).
  `TransformationCache.run` returns only a `Checksum`.

**Surface**

- `Transformation.logs` raises `NotImplementedError`
  ([transformation_class.py:1473](../../seamless-transformer/seamless_transformer/transformation_class.py#L1473)).
- A bound node's current run record holds its `tf_checksum` as
  `identity_checksum` ([reactive.py:368-380](../../seamless-workflow/seamless_workflow/reactive.py#L368-L380)).
- `direct_print` is stored, serialized into `get_graph()` and included in the
  node's `config_token` ([configuration.py:96](../../seamless-workflow/seamless_workflow/configuration.py#L96)), but no execution code
  reads `__direct_print__`.

## 2. Target behaviour

### 2.1 Surface

- `Transformation.logs` is a property returning `str | None`. It never
  triggers construction or execution.
- A bound Transformer has `ctx.tf.logs` with the same return type. On an
  unbound Transformer the attribute raises `AttributeError`, like
  `.exception`.
- There is no separate `.stdout`, `.stderr` or `.execution_metadata`.
  Execution records stay "not a query target"
  (`contracts/execution-records.md`).

### 2.2 What `.logs` returns

| Situation | Value |
|---|---|
| Not run yet, running, or canceled | `None` |
| Failed | the same string as `.exception` |
| Ran successfully in this process, or through a remote backend from it | the success log below |
| Result came from the cache or database, and this process holds no log for that `tf_checksum` | `None` |
| Same `tf_checksum` ran earlier in this process and its entry is still stored | that run's log |

A fresh execution of a `tf_checksum` replaces its stored entry: the entry is
cleared at dispatch and set on success. Failures are not stored; they live on
the handle, as `.exception` does.

### 2.3 Success layout

The legacy layout, character for character, minus its Result section (D4):

```
*************************************************
* Standard output
*************************************************
{stdout}
*************************************************
* Standard error
*************************************************
{stderr}
*************************************************
Execution time: {wall_time_seconds:.1f} seconds
*************************************************
```

- The two stream sections appear only when that stream is non-empty. With both
  empty, the log is the Execution time block alone: its three last lines.
- There is no trailing newline.
- Each stream longer than 10,000 characters is cut to its first 4,960
  characters, then `"\n...(skipped N characters)...\n"`, then its last 5,000.

### 2.4 Failure text

Unchanged: the pruned traceback, then the `* Standard output` and
`* Standard error` trailers, untruncated. No execution-time line (D3).

### 2.5 Per backend

| Backend | Streams in the success log | Live output |
|---|---|---|
| `process` | captured by the tee (Phase E, D2); none before it | caller's streams, as today |
| `spawn` | captured in the child | none |
| `remote: jobserver` | captured in the child, returned in the HTTP response | none |
| `remote: daskserver` | captured in the child, returned with the thin result | only with `streaming` |

## 3. Phases

### Phase A — Output routing bugs

No API change. Lands first; everything else builds on it.

**A1. Per-thread output routing in worker children.**

- Add a routing stream: a file-like object that sends each write to the sink
  bound to the calling thread, or to a fallback stream when the thread has
  none.
- Install it once as `sys.stdout` and `sys.stderr` in `_child_initializer`,
  with the child's original streams as fallback. Nothing assigns `sys.stdout`
  or `sys.stderr` after that.
- `_execute_transformation_request` builds its two sinks as today (a
  `TextIOWrapper` over `BytesIO`, or a `_StreamingTap`) and binds them to its
  thread for the duration of the request.
- A thread started by a routed thread inherits its route. This is done by
  wrapping `threading.Thread.start` in worker children only. Without it,
  output from threads that user code starts would leave the capture, which the
  global swap catches today. `requires-python` is `>=3.10`, so the 3.14
  context-inheritance flag is not available as a substitute.
- A write from a thread whose route has ended falls through to the fallback.
- `_execute_transformation` (nested local execution) runs under its own route.
- Known limit, to document: user code that itself replaces `sys.stdout`
  (`contextlib.redirect_stdout`) displaces the router for every thread in the
  child while it is active.

**A2. tqdm patch attribution.**

- `_active_patch()` resolves the patch from the calling thread's route. An
  unrouted or non-streaming thread gets `None`, and `StreamingTqdm` already
  behaves as plain `tqdm` in that case.
- The module-level patch is reference-counted: installed when the first
  streaming request enters, removed when the last one exits.

**A3. Bash.**

- Read stdout and stderr together in the calling thread with `selectors`,
  splitting each into lines. Stdout lines go to `sys.stdout` as today; stderr
  lines go to `sys.stderr`. No helper thread, so routing needs no inheritance.
- Remove the read of `process.stderr` after exit. Stderr is now retained on
  success and arrives live under `streaming`.
- Replace `preexec_fn=os.setsid` with `start_new_session=True`.
- Acquire `global_lock` before the `try`, and release it in a `finally` of its
  own so that no cleanup failure can skip the release.

### Phase B — Remove `direct_print`

- **`seamless-transformer`**: the `Transformer.direct_print` property, the
  constructor keyword on `PythonTransformer`, `BashTransformer` and
  `CompiledTransformer`, the `FrozenTransformer` field, and the
  `__direct_print__` meta key.
- **CLIs**: `--direct-print` on `seamless-run`
  ([main.py:484](../../seamless-transformer/seamless_transformer/cmd/api/main.py#L484)) and `seamless-run-transformation`
  ([run_transformation.py:161](../../seamless-transformer/seamless_transformer/api/run_transformation.py#L161)) becomes `--streaming`, which sets
  `Transformation.streaming` before the run. Streamed text is rendered on
  stderr for these two CLIs (D8).
- **`seamless-workflow`**: the `TransformerConfig.direct_print` field, its
  coercion and its place in `fingerprint`, the node property in
  `builder_state.py`, the `get_graph()` entry, and the uses in `context.py`
  and `runtime_api.py`. The graph loader stops reading the key and ignores it
  in graphs written earlier.
- Removing the field from `fingerprint` changes every node's `config_token`.
  The token is computed at runtime and not persisted, so nothing migrates.
- Tests: `test_frozen_transformer.py`, the docstring in
  `test_correctness_modules.py`, and the CLI tests.

### Phase C — Success logs: capture, transport, store

**C1. Child.** A request may carry `want_logs`. When it does and the run
succeeds, the child returns the result together with
`{"stdout": …, "stderr": …}`, each truncated by the 2.3 rule. Without
`want_logs` the reply is the bare `Checksum`, so the delegation call sites
keep working unchanged. Failure replies do not change.

**C2. Worker manager.** `_dispatch` sets `want_logs` when its caller asks, and
unwraps the reply. `dispatch_to_workers` gains `with_logs: bool = False`; with
it set, it returns `(result, logs)`.

**C3. Store.** `TransformationCache` gains a log store keyed by `tf_checksum`.
An entry holds `stdout`, `stderr` and `wall_time_seconds`.
`_run_uncached` clears the entry before dispatch and writes it after success,
using the `wall_time_seconds` it already computes. The store is a
size-bounded LRU (D6). Formatting happens on read, not on write.

**C4. Jobserver.** The success response gains a `logs` field next to
`record_runtime`. `seamless_remote.jobserver_client` passes it through, and
the `remote` branch of `_run_uncached` reads it. A response without the field
gives a log with no stream sections.

**C5. Dask.** The base result gains a fifth slot and the thin result a fourth,
holding `{"stdout", "stderr", "wall_time_seconds"}`. `_run_base` fills it from
its own clock. The worker-side cache fast path leaves it `None`. The three
thin-tuple consumers are updated; the client stores the log where it calls
`register_transformation_result`. A second Transformation that joins an
in-flight run shares the futures and therefore the log.

### Phase D — The `.logs` surface

- One formatter function produces the 2.3 layout from a store entry.
- `Transformation.logs`: `.exception` if the handle failed; otherwise the
  formatted store entry for its `tf_checksum`; otherwise `None`.
- Bound: `ctx.tf.logs` returns `ctx.tf.exception` when the node has failed.
  Otherwise it looks up the store by the current run record's
  `identity_checksum`. A node with no current run returns `None`.
- `Transformer.logs` delegates to the workflow backend the way `.exception`
  does.

### Phase E — In-process capture (D2)

- The same routing stream, installed in the caller's process only while at
  least one in-process transformation runs, and removed afterwards if it is
  still the installed stream.
- The sink is a tee: every write is forwarded to the stream that was installed
  before, and also retained.
- No `Thread.start` wrapping in the caller's process. Output from threads that
  user code starts stays live-only.
- In-process failure text gains the same trailers as the other backends, so
  `.exception` reads the same on every backend.

### Phase F — Nested transformations

- A nested transformation that the child executes itself (refused delegation)
  writes its log into the child's own store, so `.logs` works on the nested
  handle.
- A delegated one: the `delegate_transformation_submit` and poll replies carry
  the log when the parent has one, and the child stores it.

### Phase G — Compiled C-level output (D7)

- Around `lib.transform` ([run.py:806](../../seamless-transformer/seamless_transformer/run.py#L806)), in worker children only: redirect
  fds 1 and 2 with `wurlitzer`, flush C stdio, then write the captured text to
  `sys.stdout` and `sys.stderr`, which route it to the request.
- A child-wide lock allows one compiled call at a time per child.
- In-process compiled calls are not redirected.
- Under `streaming`, C-level output arrives when the call returns, not live.

### Phase H — Docs

- New contract page `contracts/transformation-logs.md` holding section 2.
- `contracts/streaming.md`: bash stderr is live; the compiled line if Phase G
  lands.
- `contracts/transformers.md` (builder state), `identity-and-caching.md`
  (the direct-print example), `direct-delayed-and-transformation.md` and
  `workflow-context.md` (the `.logs` surface), `execution-backends.md` (the 2.5
  table).
- `docs/main/api/index.md`, `docs/main/api/seamless-transformer.md`,
  `docs/main/sharing.md`, the `seamless-transformer` README and both
  `RELEASE-NOTES.md` files: `--direct-print` and `.direct_print`.
- Regenerate `docs/agent/api/python/` and `docs/agent/index.json`.
- Contract pages state behaviour only: no fix records, dates or commits.

## 4. Tests

Run with `~/miniforge3/envs/seamless1/bin/python`, one pytest process per test
file.

**Phase A**
- Race: one worker, two overlapping failing transformations that each print a
  distinct marker around a sleep. Each `.exception` trailer holds only its own
  marker. Run it solo; a warm-up can mask it.
- A print after the overlap, outside any request, does not raise.
- Output from a thread started by user code lands in that request's capture.
- Two overlapping streaming requests each receive only their own tqdm bars; a
  non-streaming neighbour's bar is not suppressed.
- Bash: a script writing 1 MiB to stderr completes, both with exit 0 and with
  a non-zero exit, under a timeout.
- Bash: a later bash transformation runs after one whose cleanup fails.

**Phase B**
- `direct_print` is rejected as attribute and as constructor keyword.
- `get_graph()` has no such key; a graph that has it still loads.
- `--direct-print` is rejected; `--streaming` sets the flag.

**Phases C and D**
- Golden test of the formatter: exact layout, omitted sections, truncation
  marker, no trailing newline.
- Per backend (spawn, jobserver, Dask): success log with both streams; failure
  gives `.logs == .exception`; a cache hit in a fresh process gives `None`; a
  second handle with the same `tf_checksum` in the same process sees the log.
- A re-execution replaces the stored entry.
- Jobserver response without `logs` is tolerated.
- Dask: streaming and logs together; the existing
  `test_streamed_exception_preserves_full_output_trailer` stays green.
- Bound: `ctx.tf.logs` after success, after failure, and `None` after an input
  change until the next run completes.
- `.logs` never triggers construction or execution.

**Phases E to G**
- In-process: output still reaches the caller's stream and is in `.logs`;
  `sys.stdout` is the caller's original object once nothing runs.
- Nested: `.logs` on a nested handle, for local and delegated execution.
- Compiled: `printf` output appears in `.logs`; two overlapping compiled calls
  in one child keep their output apart.

## 5. Order and dependencies

No phase waits on a ruling.

1. **Phase A** — first. A1, A2 and A3 are independent of each other.
2. **Phase B** — independent of everything else.
3. **Phase C, then D** — require A1.
4. **Phase E** — requires A1 and D.
5. **Phase F** — requires C and D.
6. **Phase G** — requires A1.
7. **Phase H** — written alongside each phase, finished last.

## 6. Noticed, not in this plan

- `execute_bash` changes the process working directory while it holds
  `global_lock`. The lock is cooperative: in library code only `execute_bash`
  takes it. It therefore serialises bash against bash, and against user code
  that itself runs `with global_lock:`. A Python transformation that does not
  take it runs at the same time and sees the working directory change. A probe
  in `process` mode confirmed both halves (2026-10-10).
  `_write_remote_bash_job` ([run.py:304](../../seamless-transformer/seamless_transformer/run.py#L304)) also changes the working
  directory, and does not take the lock.
  **Resolved (2026-10-11)** by
  [process-lock-implementation-plan.md](process-lock-implementation-plan.md), Phase A: neither `execute_bash` nor
  `_write_remote_bash_job` changes the working directory any more. The same
  plan replaces `global_lock` with the process lock, which every
  transformation claims by default.
- `_dispatch` re-dispatches a request whose worker died, for up to three times
  the number of workers attempts in total
  ([worker.py:1262](../../seamless-transformer/seamless_transformer/worker.py#L1262)). A compiled transformation that calls
  `exit()` would be re-run that many times. Legacy reported "Transformation
  exited with code N". Not checked by running.
