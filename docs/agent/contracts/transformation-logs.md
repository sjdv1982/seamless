# Transformation logs (Contract)

**A transformation's log is the standard output and standard error captured from one successful execution, followed by its execution time.** `Transformation.logs` returns it, and so does `ctx.tf.logs` on a bound Transformer. After a failure the same attribute returns the failure text.

A log is a diagnostic. The process that ran or submitted the transformation keeps it in memory. It is not part of the transformation's identity, it is not a result, and it is never written to the database or to the hashserver.

This page owns the `.logs` surface, the layout of a log, and which output is captured on each backend. Other pages own the rest:

- live output while a transformation runs: `contracts/streaming.md`;
- how a failure is recorded and delivered: `contracts/direct-delayed-and-transformation.md`, and `contracts/cells.md`, *Failures*;
- the durable per-transformation record, which holds the same execution time: `contracts/execution-records.md`.

## The surface

```python
from seamless.transformer import delayed

@delayed
def add(a, b):
    print("adding", a, b)
    return a + b

t = add(1, 2)
t.logs            # None: nothing has run
t.compute()
print(t.logs)
```

```text
*************************************************
* Standard output
*************************************************
adding 1 2

*************************************************
Execution time: 0.1 seconds
*************************************************
```

- **`Transformation.logs` is a read-only property that returns a `str` or `None`.**
- **Reading it is passive.** It never constructs the transformation, never executes it and never waits. It reads this process's memory only.
- **A bound Transformer has `ctx.tf.logs`**, with the same return type (*Bound Transformers*). On a standalone Transformer, reading `.logs` raises `AttributeError`, as `.exception` does (`contracts/transformers.md`, *Live-node members*). The log is on the Transformation that `build()` returns.
- **There is no separate `.stdout`, `.stderr` or `.execution_metadata`.** The log is one string. Execution records stay "not a query target" (`contracts/execution-records.md`).

## What `.logs` returns

The answer is decided in this order:

1. **The handle failed:** the same string as `.exception`.
2. **The handle was canceled:** `None`, whatever `.exception` holds.
3. **Otherwise:** the log that this process holds for the handle's `tf_checksum`, or `None` when it holds none.

Step 3 reads a store. These rules govern it:

- **There is one store per process, keyed by `tf_checksum`.** An entry holds the two captured streams and the execution time of one successful run. The log belongs to the `tf_checksum`, not to the handle. Every handle in the process with that `tf_checksum` reads the same entry. That includes a second handle built later, and a handle that joined a run already in flight.
- **A fresh execution replaces the entry.** The entry is cleared when the execution is dispatched and set when it succeeds. In between, `.logs` is `None`.
- **Only a successful execution stores an entry.** A failure is kept on the handle, as `.exception` is, and never in the store. A failed or canceled execution leaves its `tf_checksum` without a log, because the entry was cleared at dispatch.
- **A result that was not executed has no log.** When the result comes from a cache or from the database, nothing ran. `.logs` is then `None`, unless an earlier run of the same `tf_checksum` left an entry in this process.
- **The store is bounded.** It evicts its least recently used entries, and an evicted entry reads as `None`. The size of the bound is not part of the contract.
- **Nothing persists.** A new process starts with an empty store. No database query, command-line tool or other process can recover a log.

| Situation | `.logs` |
|---|---|
| The handle failed | the same string as `.exception` |
| The handle was canceled | `None` |
| A fresh execution of the `tf_checksum` is in flight | `None` |
| The process holds an entry: the `tf_checksum` executed successfully in this process, or on a remote backend that this process submitted it to, and the entry has not been evicted | the success log |
| The process holds no entry: nothing has run yet, the result came from a cache or the database, or the entry was evicted | `None` |

The fourth row does not ask which handle ran. A handle that has executed nothing itself reads the log once its `tf_checksum` is known and the store has an entry for it. A handle whose `tf_checksum` is not known yet reports `None`, because reading `.logs` never constructs.

**`None` means "no log held", not "no output".** A run that wrote nothing still has a log, which is the Execution time block alone (*The success log*).

## The success log

```text
*************************************************
* Standard output
*************************************************
{stdout}
*************************************************
* Standard error
*************************************************
{stderr}
*************************************************
Execution time: {seconds:.1f} seconds
*************************************************
```

- **A stream's section appears only when that stream is non-empty.** With both streams empty, the log is the Execution time block alone: the last three lines.
- **The separator is a line of 49 asterisks.**
- **A stream's text is inserted as captured, followed by one newline.** Text that ends in a newline, as `print` output does, shows as a blank line before the next separator.
- **The log has no trailing newline.**
- **A long stream is truncated.** A stream longer than 10,000 characters is cut to its first 4,960 characters, then `"\n...(skipped N characters)...\n"`, then its last 5,000 characters. `N` is the number of characters left out. Each stream is truncated on its own.
- **Truncation happens where the output is captured.** A remote run therefore returns at most about 20,000 characters of log.
- **There is no result section.** The result is read from the handle (`.result_checksum`, `.value`, `.run()`). The log never resolves the result buffer.

## The failure text

On a failed handle, `.logs` and `.exception` are the same string. That string is:

1. the failure message. For Python code this is the pruned traceback. For bash it is the *Bash transformer exception* report, with the return code and the command;
2. a `* Standard output` trailer and a `* Standard error` trailer, each between separator lines, and each present only when that stream is non-empty.

- **The trailers are not truncated.** They carry the full captured text of each stream.
- **There is no execution-time line.** Execution time is reported for successful runs only.
- **The text reads the same on every backend**, `process` included.
- A failure that happens before the code runs, such as an input that cannot be resolved, has no captured output and so no trailers.

## Execution time

- **The execution time is the dispatcher's measurement.** It is the same number as `wall_time_seconds` in the transformation's execution record (`contracts/execution-records.md`), printed with one decimal.
- **The dispatcher is the process that hands the run to its executor:** the calling process for `process` and `spawn`, the jobserver for `remote: jobserver`, and the Dask worker for `remote: daskserver`.
- **It includes queueing, inter-process transfer and input resolution**, not only the time spent in the transformation's code. It is not a benchmark of the code. It is also not comparable to the execution time that legacy Seamless (0.x) reported, which was measured inside the executing process.

## Capture, per backend

| Backend | Streams in the success log | Live output while the run is in flight |
|---|---|---|
| `process` | captured by a tee in the caller's process | on the caller's stdout and stderr |
| `spawn` | captured in the worker child | none |
| `remote: jobserver` | captured in the worker child, returned in the jobserver's response | none |
| `remote: daskserver` | captured in the worker child, returned to the client with the result | only with `streaming` (`contracts/streaming.md`) |

- **Every backend returns the log of a successful run**, the remote ones included.
- **`process` tees.** The code runs in the caller's process. Its output still goes live to the caller's streams, and is also retained for the log.
- **A daskserver worker that answers from the database cache returns no log.** That is a cache hit, and `.logs` is `None`.
- **A jobserver that returns no log with its result still yields one: the Execution time block alone.** Against such a jobserver, a log without stream sections does not show that the run was silent.

Backend semantics are `contracts/execution-backends.md`.

## What is captured

**Capture works on Python's `sys.stdout` and `sys.stderr`.** Bash commands and compiled transformers get rules of their own, below.

**Output is attributed to the transformation whose code wrote it.**

In a worker child (`spawn`, `remote: jobserver`, `remote: daskserver`):

- **A child runs several requests at once, each on its own thread, and each write goes to the request that owns the writing thread.** Overlapping requests in one child never share output and never lose it to each other.
- **A thread that transformation code starts inherits the route of the thread that started it.** Its output is in the log.
- **A write from a thread that outlives its request is not captured.** It goes to the child's own streams.
- **Limit: code that replaces `sys.stdout` or `sys.stderr` itself displaces the routing for the whole child.** `contextlib.redirect_stdout` is the common case. While the replacement is active, output from every other request running in that child goes to the replacement and is missing from those requests' logs.

In `process` mode:

- **`sys.stdout` and `sys.stderr` are routing objects while at least one in-process transformation runs.** Once none runs, they are the caller's original objects again.
- **Only the transformation's own thread is retained.** Output from the caller's other threads passes through unchanged.
- **Output from threads that transformation code starts is live only.** It reaches the caller's streams and is not in the log.

Not captured on any backend: output that a Python transformation sends straight to file descriptors 1 and 2, bypassing `sys.stdout` and `sys.stderr`. Examples are a subprocess that inherits the descriptors and a C extension that calls `printf`.

### Bash transformations

- **A bash command's stdout and stderr are two separate streams.** Stdout goes to the Standard output section and stderr to the Standard error section.
- **Both are read together while the command runs**, and relayed line by line. A command that writes a large amount to stderr does not stall.
- **The log does not record how the two streams interleaved.**
- **Stderr is retained on success as well as on failure.**

### Compiled transformers

- **In a worker child, a compiled transformer's C-level output is captured.** This is whatever the native code writes to file descriptors 1 and 2, such as C `printf` or Fortran `print`. It is captured around the call and added to the request's stdout and stderr.
- **A worker child runs one compiled call at a time.** Redirecting file descriptors affects the whole process, so correct attribution requires it. Other compiled requests in that child wait.
- **In `process` mode a compiled call is not redirected.** Its C-level output goes to the process's own stdout and stderr, and is not in the log.

## Nested transformations

Transformation code may itself build and run transformations.

- **A nested transformation has a log of its own**, read as `.logs` on the nested handle by the code that launched it.
- **This holds wherever the nested transformation ran.** If the worker child ran it itself, the child stored the log. If the child delegated it to its parent, the log comes back with the result, when the parent holds one.
- **The outer log holds the outer code's own output only.** A nested transformation's output is not repeated in the log of the transformation that launched it.
- **A worker child has a store of its own.** The log of a nested transformation that the child ran itself stays in that child. It is not returned to the process that submitted the outer transformation.

## Bound Transformers

```python
ctx.tf = add
ctx.tf.pins.a = 1
ctx.tf.pins.b = 2
ctx.tf.compute()
ctx.tf.logs
```

- **On a `failed` node, `ctx.tf.logs` returns `ctx.tf.exception`.**
- **Otherwise it returns the stored log of the node's current run**, looked up by that run's `tf_checksum` under the rules in *What `.logs` returns*.
- **A node with no current run reports `None`.**
- **It is passive**, like `.state` and `.exception`. It never waits and never demands the node.
- **It follows the node's current run.** An input or code change gives the node a new transformation identity. `ctx.tf.logs` is then `None` until the new run succeeds, unless this process already holds a log for the new identity.
- **It reports the node's own failure only.** A node that is `blocked` by a failed pin or a failed upstream has no exception of its own and no run, so it reports `None`. Read the failing pin or node instead (`contracts/pins.md`, *Pin failures*; `contracts/node-state-lifecycle.md`).
- **The Context adds no rule.** A Transformation that the Context fires is logged like one submitted by hand. A node whose result came from a cache therefore follows the rule above: nothing executed, so there is no log.
- **`ctx.tf.result.logs` is not the log.** `ctx.tf.result` is a Cell, and attribute access on a Cell is a projection (`contracts/cells.md`, *Projections*). Cells and Pins have no log.

## Logs and streaming

Streaming and the log are independent. Streaming delivers output while a `remote: daskserver` run is in flight. The log holds the output afterwards.

- **A streamed run's output is also retained.** After success it is in `.logs`, and after a failure it is in the trailers of `.exception`.
- **Progress bars differ.** With streaming on, `tqdm` bars travel as progress events and are not written to the captured stderr, so they are absent from the log. With streaming off, a bar's terminal output is ordinary stderr text and is in the log.
- **Neither is produced by a cache hit.**

See `contracts/streaming.md`.

## Non-goals

- **Persistence.** A log lives in one process's memory. It is not stored with the result, the execution record or the workflow graph.
- **A result section.** The result is read from the handle.
- **Stream interleaving.** Stdout and stderr are kept apart, and their relative order is not recorded.
- **Execution time on failure.**
- **Live output outside streaming.** `spawn` and `remote: jobserver` show nothing while a run is in flight. Their output appears in `.logs` after success and in `.exception` after a failure.
- **Identity.** A log never affects `tf_checksum`, cache identity or the result.
