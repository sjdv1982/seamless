## Porting a pipeline or notebook into a workflow Context

A Context is a DAG framework: you build the graph and hand control to a runtime that keeps it up to date. Choose it when the reactive behaviour pays: inputs that people edit (files, widgets, HTTP), long-lived sessions, a web front end, or a 0.x project. A batch pipeline that runs top to bottom is usually simpler on the Python face (`delayed`), and the two share cache entries for the same Python steps.

Contracts: `workflow-context.md`, `cells.md`, `pins.md`, `transformers.md`, `node-state-lifecycle.md`, `mounts.md`, `shares.md`, `widgets.md`. Building and debugging detail: the `seamless-workflow` skill.

### Mapping steps to nodes

| Pipeline element | Context node |
|---|---|
| Input value or parameter | a cell: `ctx.params = {...}`; set a celltype with `ctx.params = Cell(celltype="plain")` first if it matters |
| Input file | a cell mounted to the file: `ctx.data = Cell(celltype="text"); ctx.data.mount("data.txt", mode="r")` |
| Input directory | a `folder` cell mounted to the directory (modes `r`/`w`/`rw`), or a `deepfolder` cell (read-only mount; pins receive checksums, not contents) |
| Python step | `ctx.step = function`; `ctx.step.pins.a = ctx.params` |
| Bash, R, Julia, compiled step | `ctx.step = Transformer("bash")` (or `"r"`, `"julia"`, `"c", compiled=True`); set `ctx.step.code`, declare pins with `ctx.step.pins.x = ...` |
| Selecting part of a value | a projection: `ctx.sizes = ctx.clusters["sizes"]` (an Expression, no code) |
| Changing representation | `ctx.txt = ctx.data.as_celltype("plain")` |
| Collecting several values into one | a cell join: `ctx.join = {}; ctx.join.left = ctx.a; ctx.join.right = ctx.b` |
| Fan-out over a data-dependent number of items | one driver transformer (`ctx.fan.driver = True`) whose code loops and launches transformations, returning a deep celltype |
| Output | `ctx.out = ctx.step.result`; mount it with `mode="w"`, share it, or read `ctx.out.value` after `ctx.compute()` |

### Rules that bite during a port

- **Connecting is assignment**; there is no `connect()`. A string assigned to a new name is a cell value, never code.
- **Transformer code and pins cannot be mounted**: mount a cell and connect it (`ctx.tf.code = ctx.code`).
- **Settings go on the transformer before or after binding**, except `environment`, which is read-only on a bound node: build `Transformer(...)`, set its environment, then assign it into the Context.
- **`streaming` is not saved in the graph**; `process_lock`, `driver`, `scratch` and `metavars.BACKEND` are.
- **Reads never wait; `ctx.compute()` is the barrier**. `ctx.compute()` does not wait for files: use `ctx.mounts.sync()` before reading a mounted output externally.
- **Concurrency**: one body per process by default; independent nodes run in parallel only with `spawn` workers or a remote backend.
- **Graph persistence**: `ctx.get_graph()` holds checksums; reopen it only with persistent caching configured. Load graphs of unknown origin with `set_graph(graph, mounts=False, shares=False)`.
- **Large graphs**: assemble the graph dict and call `set_graph()` once rather than adding thousands of nodes one by one.

### Wrapping an existing script whole

A script built on `seamless-run` or `direct` can become a single node first (a bash or Python transformer that receives the script's declared inputs), which makes it reactive without a rewrite. The node cannot see inside the script, and it reruns whole when an input changes. Move steps out into their own nodes one at a time, rechecking states and results after each move.

### Exit checks for a workflow port

- Every node is `complete` after `ctx.compute()`; no `blocked`, `miswired` or `unwired` node remains.
- An edit to an input reruns only the affected cone (verify with a print or a counter inside the step code, or by timing; untouched nodes keep their checksums).
- Mounts and shares report no errors (`ctx.mounts.errors`, `.share.error`).
- The saved graph reloads in a fresh process with the same result checksums.
