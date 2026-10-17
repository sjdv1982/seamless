# Julia and R interpreter-thread experiment

**Status: complete.** This is the Phase 6 experiment from §6 of
[`julia-r-support.md`](julia-r-support.md). The corrected first-attempt matrix
contains all 80 planned cells: 48 Julia and 32 R. No helper or framework code
was changed for this experiment.

## Setup and scope

Each cell made three public `Transformer(...).build().run()` calls with
changing input values in one driver process. `inprocess` used `tf.local=True`;
`spawn` sent all three calls through one spawned worker. Every body-start event
recorded `process_lock=True`. Julia helper settings were
`SEAMLESS_INTERPRETER_THREAD=1` and `=0`. With the helper off, Julia explicitly
compared `PYTHON_JULIACALL_HANDLE_SIGNALS=no` and `yes`. For helper-on Julia
cells this variable was unset, and the handler's default made the effective
body setting `yes`; therefore the explicit no/yes comparison is the helper-off
pair. R received the helper environment values as a control; ryp does not use
the Julia helper.

The eight snippets were pure computation, sleep, print, async/fetch, thread
spawn/fetch, subprocess, allocation with forced garbage collection, and a
10-second body. R used a delayed promise and `parallel::mcparallel` for the
scheduler-shaped cases; these are repeated-execution controls, not tests of
Julia task scheduling. Each cell ran in its own process group with a 45-second
timeout, or 90 seconds for the 10-second body. Timed-out groups were killed.
The two language runners ran concurrently (at most two active cell process
groups); cells within each runner were sequential. JSONL was synced after each
cell, and the harness can resume by skipping completed records.

The corrected run used `conda run --live-stream -n seamless1` with the
repository `PYTHONPATH`. Versions were Python 3.14.4, juliacall 0.9.36, Julia
1.13.1, ryp 0.5.0, R 4.5.3, and NumPy 2.4.4. `JULIA_PROJECT` and
`PYTHON_JULIACALL_THREADS` were unset. Native runtime versions were recorded
from user code: Julia 1.13.1 in 133 observations and R 4.5.3 in 93.

The first, superseded run is excluded. It used R integers that overflowed the
int32 stimulus and did not compose the Julia allocation/GC source correctly.
Those stimulus issues were corrected before this matrix; the old logs and
harness snapshot remain outside the repository under `/tmp`.

## Results

| Language and settings | Cells | Pass | Nonzero error | Timeout | Observed result |
|---|---:|---:|---:|---:|---|
| R, helper environment 1, both modes | 16 | 16 | 0 | 0 | All three calls per cell completed in one body PID. |
| R, helper environment 0, inprocess | 8 | 7 | 1 | 0 | The only error was a Python import deadlock before any R body ran. |
| R, helper environment 0, spawn | 8 | 8 | 0 | 0 | All three calls per cell completed in one body PID. |
| Julia, helper on, inprocess | 8 | 7 | 1 | 0 | One pre-body Python import deadlock; the other seven cells passed. |
| Julia, helper on, spawn | 8 | 2 | 6 | 0 | Six cells observed ping-timeout worker restarts and changed body PIDs. |
| Julia, helper off, signals=no, inprocess | 8 | 0 | 0 | 8 | All timed out: two during process shutdown and six during body/initialization. |
| Julia, helper off, signals=no, spawn | 8 | 2 | 2 | 4 | Two passed, two closed the worker connection, and four timed out in body/initialization. |
| Julia, helper off, signals=yes, inprocess | 8 | 0 | 0 | 8 | All timed out: two during process shutdown and six during body/initialization. |
| Julia, helper off, signals=yes, spawn | 8 | 2 | 3 | 3 | Two passed, three had errors, and three timed out in body/initialization. |
| **Total** | **80** | **44** | **13** | **23** | **No confirmed native crash.** |

`Pass` required three expected results from three real body executions, a
stable body PID, a completed close, and exit status zero. `Nonzero error`
includes pre-body import errors, closed worker connections, and cells rejected
by those validation criteria. Timeouts are recorded separately as
`hang(timeout)` and were killed with SIGKILL; none is classified as a native
crash. No native fatal, segmentation-fault, or abort marker was found in
the captured stdout or stderr. The return code is the driver process's status;
it does not expose every worker termination signal. These records therefore
do not rule out an unreported native worker crash. The complete per-cell
outcome, return code, timeout phase, stdout, stderr, event list, versions, and
configuration fingerprint are in the raw records.

## Failure details and thread evidence

Two cells failed before any handler body started:

- `r/0/inprocess/default/sleep` raised Python 3.14.4
  `_frozen_importlib._DeadlockError` while acquiring the
  `seamless.util.pylru` import lock.
- `julia/1/inprocess/default/compute` raised the same import-lock error.

Neither has a native R/Julia version observation. These startup import errors
are separate from interpreter-affinity behavior and are retained as first
attempts for the independent review to retry.

The cell `julia/0/inprocess/no/subprocess` is another, later failure: it
recorded one verified result before Python raised
`_frozen_importlib._DeadlockError` on the `seamless.util.get_event_loop` import
lock. This is not one of the two pre-body startup errors.

In the six helper-on Julia spawn errors, `compute`, `threads_spawn`, and
`allocation_gc` recorded all three expected values, but worker restarts caused
extra body executions and changed PIDs. `println`, `async`, and `subprocess`
ended with a closed worker connection before all three outputs were verified.
The worker logs say `ping timeout`; the trace does not establish why those
timeouts occurred. With the helper off, signals=no `compute` and `async` spawn
cells ended on a closed worker connection. Under signals=yes, `println` and
`threads_spawn` produced three correct values but had extra body executions
and changed PIDs; `async` ended on a closed worker connection.

Of the 23 Julia timeouts, 19 occurred in body/initialization and four during
shutdown. For the four shutdown timeouts (helper-off, inprocess `compute` and
`println` under both signal settings), all three expected results and the
explicit `seamless.close()` completed; the process then failed to exit before
the 45-second limit. The other 19 reached the body/initialization timeout
phase. The 10-second-body cells had a 90-second limit.

The event log contains 139 Julia `body_start` events across 76 observed body
PIDs and 119 distinct Python native thread IDs. Of 48 cells, 30 had one body
PID, 12 had three, five had two, and the pre-body import failure had none. R
recorded 93 body starts across 31 PIDs and 89 distinct Python native thread
IDs; 31 cells had one body PID and the pre-body failure had none. Every
successful R cell retained one body PID. The thread identifiers here are
Python handler thread IDs and inventories; they do not identify Julia's
internal scheduler thread IDs. Raw event records preserve each PID, thread
inventory, `process_lock` value, requested setting, and effective signal
setting.

The seven helper-on inprocess passes changed Python handler native thread IDs
between calls while the inventories retained one stable
`seamless-interpreter-juliacall_0` thread. The two helper-on spawn passes,
`sleep` and `long10`, used the same handler native thread for all three calls.
Among helper-off spawn passes, `println` with signals=no alternated handler
threads, whereas `allocation_gc` with signals=no and `compute` and `long10`
with signals=yes each used one handler thread. The harness checks the body
PID but does not require caller-thread variation. It demonstrates repeated
execution in one child for passes; it does not establish that every spawn
cell exercised the changing-caller condition described in §6.

## Timing and interpretation

Julia cell elapsed times summed to 1,617.4 seconds (median 39.5 seconds,
maximum 90.2); the Julia runner's wall interval was about 27 minutes. R cell
times summed to 234.9 seconds (median 3.8 seconds, maximum 33.8); its wall
interval was about 4 minutes 22 seconds. Timing includes the per-cell driver
and worker lifecycle, so it is specific to this host and environment.

The corrected R control completed 31 of 32 cells, with its single error before
ryp started. Julia helper-on inprocess passed seven cells apart from the
separate Python import error, while every helper-off inprocess cell timed out
under both signal settings. That evidence favors keeping the helper for Julia
inprocess execution. Spawned Julia workers showed ping-timeout restarts and
changed PIDs with the helper on, and mixed errors/timeouts with it off, so this
matrix does not establish reliable spawned-worker execution. The final helper
retention decision remains with the author.

These are first-attempt outcomes from one host, one conda environment, and one
Julia/R installation pair, with three calls per cell. Targeted replicas of the
two pre-body Python import errors and representative helper-on cells are
reported below; they do not alter the original 80-cell results or hashes.

## Raw data

- [Julia first-attempt JSONL](artifacts/julia-r-interpreter-thread-julia-first-attempt.jsonl) — 48 complete records; SHA-256 `b71d2162958f2c9c8b8c041dfb7ed2b6cb1db6c5b09c0cf78473bc0b0fc24717`.
- [R first-attempt JSONL](artifacts/julia-r-interpreter-thread-r-first-attempt.jsonl) — 32 complete records; SHA-256 `47d79de66c1531d372aad4b0bc577dffe6629eb66f0032737ee112790c29a59b`.

## Supplemental verification (2026-10-12)

This separate five-cell selection used the same `run_cell` runner and body
validation from `seamless-transformer/tests/diagnostics/interpreter_thread_matrix.py`.
It ran with `conda run --live-stream -n seamless1`, Python 3.14.4,
juliacall 0.9.36, Julia 1.13.1, ryp 0.5.0, R 4.5.3, and NumPy 2.4.4;
`JULIA_PROJECT` and `PYTHON_JULIACALL_THREADS` were unset. Each cell made
three calls with `process_lock=True`.

| Cell | Supplemental result |
|---|---|
| Julia helper=1, inprocess, compute | Pass; three results and one body PID. |
| Julia helper=1, inprocess, allocation/GC | Pass; three results and one body PID. |
| Julia helper=1, spawn, compute | Pass; three results and one body PID, with no worker restart. |
| Julia helper=0, inprocess, signals=no, compute | `hang(timeout)` during shutdown after three verified results and completed close; the harness killed the process group at 45 seconds. |
| R helper=0, inprocess, sleep | Pass; three results and one body PID. |

The two first-attempt import failures did not recur in these replicas. The
original Julia helper-on spawn compute record contains two `ping timeout`
worker-restart messages and three body PIDs. Its driver exit status was zero,
but its validation failed because worker restarts changed PIDs. The supplemental
replica emitted no such messages and passed. This is one successful repeat,
not evidence that spawned worker execution is consistently reliable.

The original startup failures have Python `_frozen_importlib._DeadlockError`
tracebacks while importing `seamless.util.pylru`, before a body or native
runtime version was observed. Captured logs for the reviewed original and
supplemental cells contain no segmentation-fault, abort, or native-fatal
marker. Worker `ConnectionClosed` and `ping timeout` messages establish
connection/restart failures, not their underlying cause. Driver return codes
do not expose every worker termination signal, so the absence of a captured
native marker does not rule out an unreported native worker crash. For the
signals=no shutdown timeout, return code -9 is the diagnostic harness's
SIGKILL after its deadline, not an observed Julia signal.

The validator checks body/result counts, the process lock, body PID, execution
mode, and close completion; it does not require the handler caller thread to
change. The supplemental spawn compute used the same handler caller thread for
all three calls, so this selection does not establish changing-caller-thread
coverage. The observations are limited to this host and one environment and
runtime pair.

The reproducible selection invocation used the included
[supplemental runner](artifacts/julia-r-interpreter-thread-supplemental-runner-20261012.py)
with absolute repo paths in `PYTHONPATH` and separate Julia/R output files.
The [Julia JSONL](artifacts/julia-r-interpreter-thread-julia-supplemental-verification-20261012.jsonl)
and [R JSONL](artifacts/julia-r-interpreter-thread-r-supplemental-verification-20261012.jsonl)
preserve all events and captured output. The original first-attempt records
above remain unchanged.

## Ruling and final verification (2026-10-17)

**Ruled by the author: the helper stays.** `run_in_interpreter_thread` is
public handler API, and the Julia in-memory backend always calls Julia, and
runs Julia's exit hook, on its interpreter thread. `SEAMLESS_INTERPRETER_THREAD`
is removed; its effective value is fixed at the helper-on setting. Inline
Julia (`helper=0`) was a negative control: on a changed caller thread it
stalled, and with an unchanged one it hung at Python shutdown. It is not a
supported mode, so no cell of it is retained.

The spawned-worker failures with the helper on were worker health-check
restarts (`ping timeout`) while a transformation ran. The process manager no
longer restarts a worker that has a transformation in flight when it misses
a ping; it restarts only on process exit or a closed connection.

After both changes, all 32 helper-on cells (16 Julia, 16 R, `inprocess` and
`spawn`, eight snippets each, three calls per cell) passed, each with one body
PID and no worker restart. The 10-second bodies took 31–35 s per cell in total.
Same environment as the supplemental run above (Python 3.14.4, juliacall
0.9.36, ryp 0.5.0, NumPy 2.4.4; `JULIA_PROJECT` and `PYTHON_JULIACALL_THREADS`
unset), run with `conda run --live-stream -n seamless1`.

- [Julia helper=1 JSONL](artifacts/julia-r-interpreter-thread-julia-helper1-final-20261017.jsonl) — 16 complete records; SHA-256 `5c1f4fb9ad0e99facc83f9490f7c6617f6cbba80b7330ff82077f1e5abc3940f`.
- [R helper=1 JSONL](artifacts/julia-r-interpreter-thread-r-helper1-final-20261017.jsonl) — 16 complete records; SHA-256 `ea41a49aa588cc27109437e6915bc3f2a751ad85a9cb71f9199a4bd84f2f41ee`.

With the question settled, `seamless-transformer/tests/diagnostics/interpreter_thread_matrix.py`
and its checked-in `interpreter-thread-matrix.jsonl` (the helper=0 record with
15 timeouts) were removed from `seamless-transformer`; both remain in its git
history. The supplemental runner in `artifacts/` imports that script and runs
only against a checkout that still has it.
