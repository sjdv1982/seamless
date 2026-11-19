---
name: seamless-workflow
description: Use when building, running, saving, serving or debugging a reactive Seamless workflow (seamless.workflow.Context, the workflow face of Seamless 1.5) - cells and transformers wired by assignment, projections, as_celltype, cell joins, node states (unwired, miswired, blocked, waiting, computing, complete, failed) and block reasons, ctx.compute() barriers, file and directory mounts, Jupyter widgets (traitlet, output), HTTP/WebSocket shares, downloads, the state graph, seamless-serve-graph, and get_graph/set_graph. Triggers on reactive or interactive notebooks with Seamless, a cell synced to a file, serving a cell or a computation as a web API, a node stuck in blocked/miswired/unwired/waiting, AuthorityError, StaleWorkflowHandleError, ReentrantContextError, or CacheMissError after reloading a graph. For porting a legacy Seamless 0.x context, use together with the seamless-porting skill.
license: MIT
---

# Seamless workflow face (Context)

Everything here holds for the **workflow face** only. Do not generalize it to `direct`/`delayed` or `seamless-run`. Contracts in `seamless/docs/agent/contracts/` are authoritative: `workflow-context.md`, `node-state-lifecycle.md`, `cells.md`, `pins.md`, `transformers.md`, `expressions.md`, `attachments.md`, `mounts.md`, `shares.md`, `widgets.md`. The human docs have no workflow guide yet; the examples are in the `seamless-workflow` repo under `examples/` (start with `basic-example.ipynb`).

## Mental model

- A Context is a DAG of **nodes** (cells and transformers) plus a runtime that keeps it in equilibrium. On every change it rebuilds immutable Expressions and Transformations from fresh checksums; the content-addressed cache reuses whatever did not change. A transformer run in a Context has the same `tf_checksum` as the same call through `delayed`.
- One **controller thread** per Context is the only mutator. Public calls are queued to it; calling the Context from inside a turn raises `ReentrantContextError`.
- **Handles carry no identity**: `ctx.a is not ctx.a`. A handle to a deleted node raises `StaleWorkflowHandleError`.
- **Reads never wait.** `ctx.c.value` is `None` until `c` is `complete`. **Waiting is explicit**: `ctx.compute()` (whole graph) or `ctx.c.compute()` (that node and its upstream).
- The Context **only softcancels**; superseded runs are released after a hold, or at once with `ctx.prune()`.

## Quick start

```python
from seamless.workflow import Context, Cell, Transformer

def add(a, b):
    return a + b

ctx = Context()                 # or: with Context() as ctx:
ctx.a = 10                      # a value creates a cell
ctx.b = 20
ctx.add = add                   # a callable creates a transformer
ctx.add.pins.a = ctx.a          # connecting is assignment
ctx.add.pins.b = ctx.b
ctx.c = ctx.add.result          # a named cell fed by the result
ctx.compute()
ctx.c.value                     # 30
ctx.add.state, ctx.add.logs     # "complete", captured output (None after a cache hit)

ctx.a.mount("a.json")           # file <-> cell, both directions (mode="rw")
ctx.c.share()                   # GET http://localhost:5813/ctx/c (binds all interfaces, no auth: see Attachments)
ctx.close()
```

Other languages: `ctx.sh = Transformer("bash")`, then `ctx.sh.code = "..."` and declare pins with `ctx.sh.pins.x = ...`. Same for `Transformer("r")`, `Transformer("julia")`, `Transformer("c", compiled=True)`.

## Wiring rules

- `ctx.x = <value>` creates or writes a cell; `ctx.x = <handle>` connects; `ctx.x = <callable or Transformer>` creates a transformer. A **string is always a value**, never code: set code with `ctx.tf.code = ...` or connect a code cell (`ctx.tf.code = ctx.code`).
- Pins: `ctx.tf.pins.x = ctx.a` (never `ctx.tf.x`). Pin celltypes: `ctx.tf.celltypes.x = "int"`; result: `ctx.tf.celltypes.result`. `ctx.tf.result` is read-only.
- Projections and conversions create anonymous nodes: `ctx.a["k"]`, `ctx.a.k`, `ctx.a[3]`, `ctx.a.as_celltype("plain")`. **One link carries a path or a conversion, never both**: assigning a projection into a cell of another celltype raises `TypeError` with two suggested spellings; a later retype that makes an existing link convert leaves the consumer `miswired`.
- Connection targets are the cell root or one level below it. A cell with sub-path edges holds only a literal at its root: that is a **cell join** (`ctx.join = {}; ctx.join.left = ctx.left`).
- Two write families: assignment (`.value =`, `.checksum =`, `ctx.a = v`) declares the input and detaches an incoming edge; `.set()`, `.set_buffer()`, `.set_checksum()` write what you own and raise `AuthorityError` on a cell fed by an edge.
- Retyping (`ctx.a.celltype = "text"`) converts the stored input. A mounted, shared or widget-linked cell cannot be retyped.
- Cycles raise `DependencyError` at declaration. `mounts` and `shares` are reserved names. `ctx.sub = Context()` declares a namespace, not a sub-runtime.
- `environment` is read-only on a bound transformer: configure it on a `Transformer(...)` builder, then assign the builder. `streaming` is not saved in the graph; `process_lock`, `driver`, `scratch`, `metavars.BACKEND` are.

## Reads, barriers and failures

| Call | Behaviour |
|---|---|
| `.value`, `.buffer`, `.checksum` on a named node | never wait; `None` unless `complete`; a `complete` result that cannot be fetched raises `CacheMissError` |
| `ctx.compute(timeout=None)` / `await ctx.computation()` | wait until no node is `waiting` or `computing` |
| `node.compute()` | wait for that node and its upstream; return the checksum or `None` |
| `node.run()` | same wait; return the value; raise the node's exception, or `NodeError` naming the state |
| `ctx.mounts.sync()` / `await ctx.mounts.synchronization()` | also wait until files and other attachments have caught up |

`.exception` is a string; `clear_exception()` retries. Upstream failure makes dependents `blocked`, never `failed`. In tests, use `run()` or assert `.state == "complete"`.

## Node states

`unwired` (not enough inputs connected), `miswired` (an incoming link is ill-formed; nothing runs), `blocked` (something upstream is unwired, miswired, blocked or failed; `.block_reason` is `blocked-by-unwired`, `blocked-by-error` or `blocked-by-miswiring`, per pin on a transformer), `waiting`, `computing`, `complete`, `failed` (this node's own evaluation failed). Compare against the strings. Diagnosis by state and by error: `references/debugging.md`.

## Attachments: files, widgets, web

One file slot, one widget hub and one share per cell. Whole bound cells only: to feed a pin or transformer code from a file, mount a cell and connect it. Full API and limits: `references/attachments.md`.

- **Mounts**: `ctx.a.mount(path, mode="rw", authority="file")`; `folder` cells mount directories. Mount problems never raise after attach: the cell fails with a message and monitoring continues (`ctx.a.mount.status`, `.error`, `ctx.mounts.errors`).
- **Widgets**: `from seamless_workflow.jupyter import traitlet, output`; `traitlet(ctx.a).link(slider)`; `display(output(ctx.c))`. Not saved in the graph.
- **Shares**: `ctx.a.share(readonly=True)`; `readonly=False` accepts PUT. One process-wide server on `0.0.0.0:5813` by default; **no authentication or TLS**. Bind to localhost unless the network is trusted: `from seamless_workflow import shareserver; shareserver.configure(host="127.0.0.1")` before the first share, or `SEAMLESS_SHARE_HOST`. `ctx.shares.add_download(["a", "c"])` serves an archive; `GET /ctx/state-graph` exposes every node's state and error text.

## Saving, loading, serving

- `graph = ctx.get_graph()` (JSON, format `0.7`); `ctx.set_graph(graph)` replaces the whole graph.
- **The graph stores checksums, not data.** Reloading it in another process needs persistent storage: `export SEAMLESS_CACHE=...` and `seamless.config.init()` before creating the Context (or a configured cluster). Without it, reads raise `CacheMissError`.
- `set_graph()` attaches the graph's mounts and shares, so it can write files and open ports: use `set_graph(graph, mounts=False, shares=False)` for graphs of unknown origin.
- Build large graphs as one dict and load them with one `set_graph()`; node-by-node construction re-derives the whole graph per edit.
- `seamless-serve-graph graph.json` loads a graph with shares on and mounts off, and serves until interrupted. `ctx.close()` keeps a share namespace for 10 s, so `%run -i script.py` takes it over without breaking connected browsers.

## Execution

- Transformers run on the configured backend (`process`, `spawn`, jobserver, Dask). By default one transformation body runs per process, so independent transformers in `process` mode run one after another; use `spawn` workers or a cluster for parallelism.
- Projections, conversions and joins run where the data is; `Context(expression_execution="auto" | "local" | "remote")` sets the policy.
- Determinism is assumed: same inputs, same result checksum.

## Not available (versus Seamless 0.x)

Macros, stdlib (`map`, `switch`), Silk validation (a cell with a validator fails), sub-contexts, cycles, IPython transformers, a context-wide status, pin or code mounts, authentication on shares. Use a driver transformation (`ctx.tf.driver = True`) for data-dependent fan-out.

## Reference map

- `references/debugging.md`: state-by-state and error-by-error diagnosis, and a triage procedure.
- `references/attachments.md`: mounts, widgets, shares, downloads and the state graph in detail, with limits.
