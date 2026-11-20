## Porting a Seamless 0.x project to 1.5

Seamless 1.5 brings the 0.x workflow layer back on a new architecture (package `seamless-workflow`). Most of the interactive model survives; the API is close but not identical, saved graphs are not converted, and several 0.x features are absent. Legacy docs: `docs/` on the `legacy-seamless0.x` branch of the seamless repo. Behaviour of 1.5: the contracts named below (in `seamless/docs/agent/contracts/`).

### First: check for absent features

If the project depends on any of these, it cannot move as-is. Tell the user before porting.

| 0.x feature | 1.5 |
|---|---|
| Macros, the low-level API | absent |
| Libraries, libinstances, stdlib (`map`, `switch`, `select`, `merge`) | absent; replace `map` by a driver transformation that loops and launches one transformation per item |
| Silk schemas and validation | absent; `validator=` is accepted but every evaluation raises `NotImplementedError` (the cell fails) |
| IPython transformers (`language="ipython"`) | absent (the `ipython` celltype exists) |
| Sub-contexts with their own runtime | absent; `ctx.sub = Context()` only declares a namespace |
| Debug sessions, sandboxes | absent; use `.logs`, `.exception`, streaming |
| Vaults, zip export of a context | absent; buffers live in a hashserver/database; `ctx.shares.add_download` builds an archive of cell values on request |
| Cloudless, `seamless-new-project` | absent; use `seamless-config` projects and stages |
| Cycles, non-eager mode | absent |
| Context-wide `ctx.status` | absent; per node `.state`, `.block_reason`, `.exception`; HTTP `GET /<namespace>/state-graph` |
| Authentication on the shareserver | absent (also no TLS) |

### API mapping

| 0.x | 1.5 | Contract |
|---|---|---|
| `from seamless.highlevel import Context, Cell, Transformer` | `from seamless.workflow import Context, Cell, Transformer` | `workflow-context.md` |
| `ctx.tf = Transformer(); ctx.tf.language = "bash"` | `ctx.tf = Transformer("bash")` (language is fixed at construction) | `transformers.md` |
| `ctx.tf = func` | same | `transformers.md` |
| `ctx.tf.a = 5`, `ctx.tf.x = ctx.c` | `ctx.tf.pins.a = 5`, `ctx.tf.pins.x = ctx.c` | `pins.md` |
| `ctx.c = ctx.tf` | `ctx.c = ctx.tf.result` | `transformers.md` |
| `ctx.tf.code.mount("code.py")` | `ctx.code = Cell(celltype="python"); ctx.code.mount("code.py"); ctx.tf.code = ctx.code` | `mounts.md` (*Porting notes*) |
| `ctx.tf.x.mount(...)` (pin mount) | mount a cell and connect it: `ctx.x.mount(...); ctx.tf.pins.x = ctx.x` | `mounts.md` |
| `ctx.a.mount("a.json")`, `mode="w"` | same (`mode="rw"` default; `authority="file"` default) | `mounts.md` |
| directory mount (`as_directory`) | a `folder` cell (r/w/rw) or `deepfolder` cell (read only) mounted to a directory path | `mounts.md` |
| `ctx.translate()`, `await ctx.translation()` | no translation step; edits take effect through the controller | `workflow-context.md` |
| `ctx.compute()`, `await ctx.computation()` | same, graph-only barrier; `ctx.mounts.sync()` waits for files too | `workflow-context.md` |
| `ctx.x.celltype = "int"` | same (retyping converts the stored input) | `cells.md` |
| `ctx.sub = ctx.c[1]`, `ctx.c = ctx.b.sub1.x` (subcells) | same syntax: projections (connection targets: root or one level) | `cells.md` (*Projections*) |
| `ctx.c.share()`, `ctx.c.share("name.txt")` | `ctx.c.share(path=None, readonly=True)`; writable with `readonly=False`; one process-wide server (default `0.0.0.0:5813`) | `shares.md` |
| 0.x JavaScript client | `/seamless-client.js` served by the share server | `shares.md` |
| `ctx.c.traitlet()`, `ctx.c.output()` | `from seamless_workflow.jupyter import traitlet, output`; `traitlet(ctx.c).link(widget)`, `output(ctx.c)` | `widgets.md` |
| `ctx.save_graph(...)`, `load_graph(...)` | `json.dump(ctx.get_graph(), f)`; `ctx.set_graph(graph)`; 0.x graph files are not converted | `workflow-context.md` |
| `DeepCell`, `DeepFolderCell` | `Cell(celltype="deepcell")`, `Cell(celltype="deepfolder")` / `"folder"`; flat index, one-level paths | `deep-celltypes.md` |
| `ctx.tf.environment` (conda, docker) | `tf.environment.set_conda_env(...)` / `set_docker({"name": ...})`, set before binding (read-only on a bound node); entered by bash and CLI backends only | `environments.md` |
| compiled transformers (c, cpp, fortran) | `Transformer("c", compiled=True)` with a schema; 0.x compiled *modules* have no equivalent | `compiled-transformers.md` |
| `ctx.tf.debug` | `.logs`, `.exception`; `tf.streaming = True` on Dask | `transformation-logs.md` |

### Behaviour differences to expect

- **Reads never wait.** `ctx.c.value` is `None` until the node is `complete`; call `ctx.compute()` first. A failed node reads `None`; the error is on `.exception` (a string). `ctx.c.run()` raises.
- **Upstream failure makes dependents `blocked`**, not failed; `.block_reason` says why (`blocked-by-error`, `blocked-by-unwired`, `blocked-by-miswiring`).
- **One link carries a path or a conversion, never both.** `ctx.x = ctx.a[3]` into a cell of another celltype makes the target `miswired`; put an explicit `as_celltype` on the source.
- **"Any pin None gives result None" is gone.** A required pin of a celltype other than `plain`, `mixed`, `bytes` refuses null; Python defaults make a pin optional.
- **Cancellation is soft.** Superseded runs are softcancelled after a hold; `ctx.prune()` reclaims them early.
- **Concurrency**: one body per process by default; start `spawn` workers or use a cluster.
- **Storage**: graphs hold checksums only; values live in the buffer store. Set up persistent caching (`SEAMLESS_CACHE` and `seamless.config.init()`, or a cluster) before saving graphs you want to reopen.
- **Large graphs**: build with one `set_graph()`; node-by-node construction re-derives the whole graph per edit.

### Procedure

1. Inventory the 0.x project: cells, transformers (languages), mounts, shares, traitlets, macros/stdlib/Silk usage. Stop and discuss if absent features are central.
2. Recreate the graph in Python with the mapping above, in a fresh Context, without mounts and shares. Get it to `complete` with representative data.
3. Add mounts, then shares, then widgets, checking `.mount.status` / `.share.status` and `ctx.mounts.errors`.
4. Replace stdlib `map` and macros with driver transformations returning deep celltypes.
5. Save the graph (`get_graph()`), reload it in a fresh process with persistent caching, and compare node states and checksums.

For building and debugging the Context itself, use the `seamless-workflow` skill.
