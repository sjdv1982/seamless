## Debugging a Context

Contracts: `node-state-lifecycle.md` (states, block reasons, holds), `workflow-context.md` (reads, barriers, errors), `cells.md` (writes, authority, failures, wiring), `pins.md`, `transformers.md`.

### Triage procedure

1. Wait with a bound: `ctx.compute(timeout=60)`. A `TimeoutError` withdraws the wait and cancels nothing.
2. List every named node with its state:

```python
def node_report(ctx):
    for node in ctx.get_graph()["nodes"]:
        h = ctx
        for step in node["path"]:
            h = h[step]
        print("/".join(node["path"]), node["type"], h.state, h.block_reason,
              (h.exception or "")[:200])
```

   With shares active, `GET http://<host>:<port>/<namespace>/state-graph` returns the same states, block reasons and edges as JSON.
3. Find the **root cause**: the most upstream node that is `failed`, `miswired` or `unwired`. Everything downstream of it is `blocked`, and that is expected.
4. Fix it, then re-run `ctx.compute()`. A failed node is retried after `node.clear_exception()` or after any change to its inputs or code.
5. For a transformer, read `ctx.tf.exception` (the traceback text) and `ctx.tf.logs` (stdout/stderr of the run). For live output from a long run, set `streaming` on a Dask backend.
6. If remote execution is involved and the error mentions connections, services or timeouts, switch to the `seamless-remote-debugging` skill.

### By state

| State | Meaning | Typical cause | Action |
|---|---|---|---|
| `unwired` | not enough inputs connected | a transformer pin without a source; a cell with no value | connect the pin (`ctx.tf.pins.x = ...`) or give the cell a value |
| `miswired` | an incoming link both projects and converts | the source was retyped after a projection was connected; nothing runs | restore the source celltype, or connect through an explicit conversion (`ctx.src.as_celltype("plain")["k"]` or `ctx.src["k"].as_celltype("text")`); `run()` raises `NodeError` |
| `blocked` | something upstream is unwired, miswired, blocked or failed | see `.block_reason` | `blocked-by-unwired`: wire something upstream; `blocked-by-error`: fix the failed upstream node (or a pin with no valid checksum); `blocked-by-miswiring`: fix the miswired link. On a transformer, `block_reason` is a dict per pin |
| `waiting` | inputs are not all concrete checksums yet, or a cell's own work is in flight | upstream still computing | wait (`ctx.compute()`); if it persists with nothing computing upstream, report it |
| `computing` | submitted: queued or running | long computation; queued behind the process lock (one body per process by default) or backend concurrency | `ctx.tf.logs` after it ends; streaming on Dask; more workers (`spawn`, cluster) for parallelism |
| `complete` | a result checksum exists | | if `.value` raises `CacheMissError`, the buffer is not available here (see below) |
| `failed` | this node's own evaluation failed | exception in transformer code; failed conversion or projection; invalid file contents sensed by a mount; a missing input buffer | read `.exception`; fix code, data or file; `clear_exception()` to retry |

Upstream failure never makes a node `failed`, only `blocked`. A node in `complete` may still have a superseded run in flight; `ctx.prune()` softcancels such runs and returns `{"cancelled": n}`.

### By error

| Error | When | What to do |
|---|---|---|
| `TypeError: would convert X -> Y behind a projection` | assigning a projection into a cell of a different celltype | use one of the two spellings the message suggests |
| `AuthorityError: ... controlled by an incoming edge` | `.set()` / `.set_buffer()` / `.set_checksum()` on a connected cell | assign instead (`ctx.a = v` detaches the edge), or write the source |
| `AuthorityError` with "Sensing mount" | connecting into a cell with an `r`/`rw` mount or a linked widget hub, or linking a widget to a connected cell | an output cell takes `mode="w"` mounts and `traitlet(...).connect()` (one-way); unmount or `traitlet(cell).destroy()` first |
| `ValueError: Mounted celltype cannot change; unmount first` | retyping a mounted cell | `del ctx.a.mount`, retype, mount again |
| `StaleWorkflowHandleError` | using a handle whose node was deleted or renamed | fetch a fresh handle (`ctx.a`) |
| `DependencyError` | the edge would close a cycle, or a handle from another Context | restructure; handles belong to one Context |
| `ReentrantContextError` | a public Context call from inside a controller turn | move the call out of the callback |
| `ControllerFailedError` | an internal failure poisoned the Context | only `close()` works; recreate the Context and report the bug with the traceback |
| `ClosedContextError` | use after `close()` | create a new Context |
| `ConcurrentUpdateError` | a sub-path write lost 8 optimistic attempts to concurrent writers | retry; serialize the writers |
| `ValueUnavailableError` | a sub-path write into a cell that has no value and is not waiting | give the root a value first |
| `NodeError` (from `run()`) | the node is `unwired`, `miswired` or `blocked` | follow the state table |
| `CacheMissError` on `.value` of a `complete` node | the result buffer is not reachable from this process | after `set_graph()` in a new process: configure persistent caching (`SEAMLESS_CACHE` + `seamless.config.init()`) before creating the Context; for a scratch result: `ctx.a.fingertip()`; `.value` never fingertips by itself |
| `NotImplementedError: Expression validators are not implemented yet` | a cell with `validator=` | remove the validator |
| `PathError` | a node named `mounts` or `shares`, or an invalid path | rename |
| `TimeoutError` from `compute(timeout=...)` | the graph did not settle in time | inspect states; the wait was withdrawn, work continues |

### Things that look like bugs but are not

- `ctx.c.value` is `None` right after an assignment: reads never wait. Call `ctx.compute()`.
- `ctx.compute()` returns while a mounted output file still has old contents: use `ctx.mounts.sync()`.
- `ctx.tf.logs` is `None` for a completed transformer: the result came from the cache, or was computed in another process. Logs live in process memory only.
- Several independent transformers run one after another in `process` mode: the per-process lock. Use `spawn` workers or a cluster.
- A superseded run keeps a worker busy after an edit: it is held briefly in case the edit is reverted. `ctx.prune()`.
- A Python syntax error in a mounted `python` cell is accepted as a value; the transformer using it fails when it runs.
- Retyping a source makes its projecting consumers `miswired` instead of raising: valid edits never raise for someone else's wiring.
