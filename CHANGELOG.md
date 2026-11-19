# Seamless Changelog

Detailed, log-oriented record of changes, written for AI agents and maintainers.
For a human-oriented summary, see [RELEASE-NOTES.md](RELEASE-NOTES.md).
Behavioural detail lives in the contract pages under
[docs/agent/contracts/](docs/agent/contracts/); every entry names its contract, or says that none exists.
Where this file and a contract disagree, the contract wins.

## 1.5 (pre-release)

Baseline: Seamless 1.4.0 (tag `v1.4.0`, 2026-06-10). Seamless 1.5 is the first
1.x release on feature parity with legacy Seamless 0.x; see *Legacy parity*
for what is partial or absent.

### Conventions

- **Faces.** `[PY]` Python face (`direct`/`delayed`, `Transformer`,
  `Transformation`, standalone `Cell`/`Pin`/`Expression`). `[UX]` Unix face
  (`seamless-run` and friends). `[WF]` workflow face
  (`seamless.workflow.Context`, package `seamless-workflow`). `[ALL]` the
  property holds on every face. A property without a tag holds only on the
  face named in its entry. Never generalize a `[WF]` property to Seamless as a
  whole.
- **Status.** NEW (not in 1.4), CHANGED (behaviour or surface differs from
  1.4), BREAKING (CHANGED, and existing code or cache entries are affected),
  FIX (bug fix with a visible effect).
- **Contracts** are named by file name relative to `docs/agent/contracts/`.
  "No contract found" means no contract page covers the claim.
- **Commit refs** are `repo:hash`: `core`=seamless-core,
  `tf`=seamless-transformer, `wf`=seamless-workflow, `rem`=seamless-remote,
  `dask`=seamless-dask, `job`=seamless-jobserver, `db`=seamless-database,
  `sig`=seamless-signature, `cfg`=seamless-config, `rhl`=remote-http-launcher,
  `share`=seamless-share, `top`=seamless.

### Package versions

| Package | Version |
|---|---|
| seamless-suite | 1.5 |
| seamless-core | 0.2 |
| seamless-transformer | 0.7.0 |
| seamless-workflow | 0.1.0 (new) |
| seamless-remote | 0.5.0 |
| seamless-dask | 0.5.0 |
| seamless-jobserver | 0.4.0 |
| seamless-database | 2.2.0 (wire protocol 2.3) |
| seamless-config | 0.3.3 |
| seamless-signature | 0.1.2 |
| hashserver | 1.1.0 |
| seamless-share | 0.1.0 (separate package, not installed by `seamless-suite`) |
| remote-http-launcher | 0.4.5 |

`seamless-workflow` depends on `traitlets`, `ipywidgets` and `aiohttp`
directly; there are no `[share]` or `[jupyter]` extras.

### Known issues

- The Julia CLI backend locates `seamless/julia/Project.toml` relative to a
  source checkout of `seamless-transformer`
  (`seamless_transformer/languages/handlers/julia.py`), so it raises when
  `seamless-transformer` is installed from PyPI.
- `seamless-run --undo` always fails ("Transformation could not be declared
  irreproducible"): it reports through `report_irreproducible_result`
  (`mode: "automatic"`), which answers 409 when the reported result equals the
  recorded one. In 1.4 it raised `NotImplementedError`. No contract covers it.
- `go` is a registered compiled language (`available_languages()` lists it),
  but no contract documents it.
- `contracts/widgets.md` and `guides/seamless-web-server.md` mention
  `seamless-workflow[jupyter]`/`[share]` extras; these no longer exist
  (wf:ece5940): `traitlets`, `ipywidgets` and `aiohttp` are hard dependencies.
- `contracts/execution-records.md` names `seamless.config.select_record`; the
  function is `seamless_config.select.select_record`.
- Self-edit revert hold: `node-state-lifecycle.md` says 30 s, `expressions.md`
  says the code uses 15 s.
- The human docs (`docs/main`) lag the code: they still say the workflow
  features "are being ported" and have no workflow-face guide. Treat the
  contracts as authoritative.

### Shipped in 1.4.x patch releases

Inside the commit window but released as 1.4.x patches, not 1.5: the nested
Dask delegation fix (issue 268, tf:d56f4fa) and the `remote-http-launcher`
conda-cache fixes (v0.4.4, v0.4.5; rhl:417d891, rhl:0930cca). They are listed
under R11 and R12 for completeness.

### Features by face and area

#### Workflow face (`seamless-workflow`, all NEW unless stated)

**W1. Context: nodes, assignment, namespaces.** NEW. `[WF]`. A Context is a DAG of nodes plus a runtime in equilibrium; it stores only nodes (never Cells, Expressions or Transformations). `Context(expression_execution="auto"|"local"|"remote")` (keyword only), `with Context() as ctx`, idempotent `close()` (ordered shutdown, softcancels memberships; `seamless.close()` closes all Contexts). Nodes are created by assignment (`ctx.a = ...`, dispatch table by value type); unknown paths are namespace views (`ctx.sub.a = 1`); `ctx.sub = Context()` only declares a namespace (no sub-runtime); `mounts` and `shares` are reserved names; `del ctx.a`. Cycles raise `DependencyError`; connection targets are the root or one level below it. Handles carry no identity (`ctx.a is not ctx.a`; `StaleWorkflowHandleError`). Contract: `workflow-context.md`. Commits: wf:1fbe9f3, wf:2cff608, wf:1ccb336, wf:62ae4af, wf:6697ee7, wf:2eb593b.

**W2. Reactive runtime, reads and barriers.** NEW. `[WF]`. One controller thread per Context is the sole mutator; reads of a named node never wait (`.checksum/.buffer/.value` report the current result or `None`). Waiting is explicit: `ctx.compute(timeout=None)` / `await ctx.computation()` (no node `waiting`/`computing`), `node.compute()` / `node.run()` (that node and its upstream cone). `compute()` reports (checksum or `None`), `run()` raises. Sub-path writes are optimistic read-modify-set (8 attempts, then `ConcurrentUpdateError`). An internal failure poisons ingress (`ControllerFailedError`; only `close()` works). Errors: `ClosedContextError`, `ReentrantContextError`, `NodeError`, `ReadOnlyEndpointError`, `AuthorityError`, `PathError`. Contract: `workflow-context.md`. Commits: wf:57b29f5, wf:33d2762, wf:870b66c, wf:1b06262, wf:223f832.

**W3. Node states, block reasons, speculation, `prune`.** NEW. `[WF]`. Seven derived states: `unwired`, `miswired`, `blocked`, `waiting`, `computing`, `complete`, `failed`; `.state`, `.block_reason` (exactly `blocked-by-unwired`, `blocked-by-error`, `blocked-by-miswiring`), `.exception` (a string), `clear_exception()`. Upstream failure makes dependents `blocked`, never `failed`. Replacement work launches immediately; the superseded run is softcancelled only after a hold (self-edit revert hold 30 s (may change); upstream-confirmation hold and completed-downstream retention bounded by an upstream event under a five-minute backstop). `ctx.prune()` / `ctx.a.prune()` softcancel superseded work and return `{"cancelled": n}`. The Context only ever softcancels. Contract: `node-state-lifecycle.md`, `workflow-context.md` (*Speculation control*). Commits: wf:9120258, wf:dc68ac6, core:bb72a42, tf:99becf1, tf:c6e4486.

**W4. Cell handles (bound).** NEW. `[WF]` (and `[PY]` standalone, see P3). `Cell(celltype=None, *, checksum=None, source=None, input_celltype=None, validator=None, validator_language=None)`. `celltype` is the output type; `input_celltype` is read-only; `.source` (derivation) versus `.checksum` (current value). Two write families: declare the input (`.value =`, `.buffer =`, `.checksum =`, assignment; detaches an incoming edge) versus `.set()`/`.set_buffer()`/`.set_checksum(cs, input_celltype=...)` (checks authority). `.value = None` stores canonical null; `.checksum = None` clears. Retyping converts the original input; `ctx.a = ctx.b` copies `b.celltype` once. `target_celltype` and `input_ref` are retired (`AttributeError`); there is no `SubCell`. Validators are accepted and stored but every evaluation raises `NotImplementedError`. Contract: `cells.md`. Commits: core:266ed7b, core:b5fcfb0, core:7d5f669, core:fcfae10, wf:87b57c5, wf:1695b27, wf:ce915d8.

**W5. Projections, `as_celltype`, anonymous nodes, fusion.** NEW. `[WF]` (child Cells also standalone). `ctx.a.b`, `ctx.a[3]`, `ctx.b.as_celltype("plain")` return handles to anonymous cell nodes; a run of edges fuses into one Expression; one link carries either a path or a conversion, never both (violation: `miswired` with a repair message naming the two celltypes). Writes through projection handles are pathed writes to the root; clearing a sub-path is refused. Anonymous nodes are saved under `anonymous_nodes`. Contract: `cells.md` (*Connecting*, *Projections*), `expressions.md` (*Fusion*). Commits: wf:7a44627, wf:f6a87dc, wf:1bdcde7, wf:4eecfce.

**W6. Cell-level joins (celljoin).** NEW. `[WF]`. `ctx.join = {}; ctx.join.left = ctx.left; ctx.join["k"] = ctx.x`. A join is evaluated as a content-addressed `CellJoin` Expression with identity `(celljoin checksum, celltype)`: no Transformation, never observed `computing`, recorded with forward and reverse rows. `mixed`/`plain` members convert to the join celltype first; deep joins (`deepcell`/`deepfolder`/`folder`) insert member checksums (`deep_member: true` in the graph). Placement: local if all inputs local, dispatched if all on the hashserver, mixed fetch otherwise; a cache miss on an input is final (do not scratch what feeds a join); fingertip walks through joins. A root edge together with sub-path edges is refused. Contract: `cells.md` (*Cell-level joins*), `expressions.md` (*Cell joins*), `scratch-witness-audit.md`. Commits: core:1e07ced, core:467871f, core:e36af51, core:8dba2cf, core:684145c, core:2bccba0, wf:5bda32a, db:97c79c9, rem:f36831e, rem:10044fd, job:7d83682, dask:4d9bd2c, tf:8cbbf7f.

**W7. Transformers in a Context.** NEW. `[WF]`. `ctx.tf = function` or `ctx.tf = Transformer(...)` binds the builder (a move, not a copy). `ctx.tf.pins.x`, `ctx.tf.celltypes.x`, read-only `ctx.tf.result` (a Cell), live-node members `.state/.block_reason/.exception/.logs` (standalone raises `AttributeError`), `prune()`, `clear_exception()`, `build()` (detached snapshot). Node-level settings `process_lock`, `driver`, `scratch`, `metavars.BACKEND` are saved in the graph; `streaming` is not (and never re-runs the node); `environment` is a read-only copy (set before binding). The Context freezes the node into a private `FrozenTransformer` per run. Replacement of a transformer stages all roles and rolls back on failure. A code string assigned to a name is a cell value, not code. Contract: `transformers.md`, `workflow-context.md`. Commits: wf:2cff608, wf:926d579, wf:2eb593b, wf:f5dee32, wf:3ead83a, wf:38374b1, wf:6adaaae, tf:22bf0df, tf:f05806c.

**W8. Pins as handles.** NEW. `[WF]` and `[PY]`. `tf.pins.x` returns a fresh `Pin` (sister class of `Cell`, not a source; connect `pin.source`). Pin sets: fixed by a Python signature, user-declared for signature-less code (bash, handler languages). Per-pin celltype (`tf.celltypes.x`); typed inputs convert before transformation construction; a failed conversion leaves the Pin `failed` and the transformer `blocked`. Pins hold checksums, never values. No sub-pin targets, validators or mounts; the 0.x per-pin `io`/`as_` settings are gone. `yaml` and `python` input pin celltypes are not supported: building raises `NotImplementedError`. A standalone Cell/Expression cannot be assigned to a bound pin. Contract: `pins.md`. Commits: tf:afb0ab0, tf:91e0cf3, tf:e68c1e2, wf:5664da5, wf:6449e8b, wf:f240a0f.

**W9. Celltypes in the graph.** NEW/CHANGED. `[WF]`. Output-typed cells; conversions live on edges (`as_celltype`, retyping); retyping a source with projecting consumers makes each consumer `miswired` (never refused); a mounted, shared or widget-linked cell cannot be retyped; `all Cell types allow null`; text-to-plain writes the canonical plain buffer. Contract: `cells.md`, `celltypes-and-conversion.md`. Commits: wf:66dbf12, wf:ca35c2a, wf:87b57c5, core:c5aa996, core:a00ea2c.

**W10. Deep celltypes in a Context.** NEW. `[WF]`. A deep cell admits one string-item step (`ctx.d["k"]`) and the zero-path index conversions; the step yields a member checksum without materializing the parent; `.value` is the index (`{key: Checksum}`); a deep link outside the table makes the target `miswired`; writes at `k` are allowed, below `k` are not. Contract: `deep-celltypes.md`, `cells.md`. Commits: wf:bb2c0d6, wf:4bb2fdb, wf:f8575bd, tf:a5c758a.

**W11. Attachments framework.** NEW. `[WF]`. One cell node has at most one file slot, one widget-hub slot and one share slot. Sense (external change becomes an authoritative write) and actuate (deliver after a turn once `complete`; a delivery resolves and never computes or fingertips). Three-way error model (sense errors fail the cell; write failures stay on the attachment; objects on the attachment, strings on the cell). Oscillation detector (3 reasserts in 20 s trips; paused, never dead; `clear_error()`). External cut barrier `ctx.mounts.sync(timeout=None)` / `await ctx.mounts.synchronization()` returns a `SyncReport`; `ctx.mounts.errors`. Not a plugin API. Contract: `attachments.md`. Commits: wf:14ea755, wf:07a47c3, wf:c88af88.

**W12. File and directory mounts.** NEW. `[WF]`. `ctx.a.mount(path, mode="rw", authority="file", *, persistent=True)`, `del ctx.a.mount`, `.mount.spec/.status/.error/.clear_error()`. Modes `r`/`w`/`rw`; authority `file`/`cell`/`file-strict`. Mountable: text/code, plain, str, int, float, bool, bytes, binary, mixed as files; `folder` (r/w/rw) and `deepfolder` (r only) as directories; `.gz`/`.zst` paths compress canonical bytes. Conditional atomic writes, fingerprints and polling (optional inotify with `SEAMLESS_MOUNT_NATIVE=1`), path-overlap registry (within a process), null truncates a file, null on a directory mount is terminal (`in_sync` stays false). Mount failures never raise after attach: the cell fails with a string and monitoring continues. Directory write mounts register their leaves as local buffer sources. Loading a graph can write files: use `set_graph(graph, mounts=False)` for untrusted graphs. Contract: `mounts.md`. Commits: wf:c88af88, wf:27f2822, wf:4bb2fdb, wf:cf0d498, wf:5f4ec2f, wf:fc75225, core:a2a1d4c, core:6953bd1, core:e6dbe92.

**W13. Jupyter widgets.** NEW. `[WF]`. `from seamless_workflow.jupyter import traitlet, output`; `t = traitlet(ctx.a)` (one hub per cell), `t.link(widget, target_attr="value")` (bidirectional, upgrades the hub to `rw`), `t.connect(...)` (one way), `t.observe(...)`, `t.status/.error/.clear_error()/.destroy()`; `output(ctx.c, layout=None, mimetype=None)` returns an `OutputWidget`. Hubs work without a kernel; widgets are runtime-only (not in the graph); `None` is absence; a widget cannot clear a cell. Contract: `widgets.md`. Commits: wf:a2f6d4f, wf:07a47c3.

**W14. HTTP and WebSocket shares.** NEW. `[WF]`. `ctx.a.share(path=None, readonly=True, *, mimetype=None, toplevel=False)`, `del ctx.a.share`, `.share.url/.spec/.status/.error`. One process-wide server (host `0.0.0.0`, port `5813`; `shareserver.configure(host=, port=)`, `SEAMLESS_SHARE_HOST/PORT`), own thread and loop. GET/HEAD/PUT of raw bodies (no envelope); marker-based compare-and-set (`?marker=n`); `204` for null; websocket update stream; live `/openapi.json` (`ctx.shares.openapi()`); `/seamless-client.js` browser client; `ctx.shares.namespace` (default `ctx`). Read-only shares work on connected cells; writable shares make the cell's producer. Shareable: text/code, plain, str, int, float, bool, bytes, binary, mixed. No auth, no TLS. Contract: `shares.md`. Commits: wf:372893f, wf:443f256, wf:61b2977, wf:9cfd439, wf:fd958e0, wf:1450f0d, core:bd69bbc.

**W15. Share downloads, state graph, hold on close.** NEW. `[WF]`. `ctx.shares.add_download(cells, path="download", *, format="tar.gz"|"tar"|"tar.xz"|"zip")` (archive built per GET from one consistent cut; never computes), `remove_download`, `ctx.shares.downloads`. `GET /<ns>/state-graph` serves node states, block reasons and connections (rate-limited to one snapshot per 0.5 s). `ctx.close()` holds the namespace for 10 s so a re-run script takes it over invisibly (`%run -i`). Contract: `shares.md` (*Downloads*, *The state graph*, *The hold on close*). Commits: wf:9b7c5cc, wf:04f7217, wf:9d0d0fc, wf:ef7b896, top:4760d1bd.

**W16. `seamless-serve-graph`.** NEW. `[WF]`/`[UX]`. `seamless-serve-graph graph.json` loads one local graph with `set_graph(graph, mounts=False, shares=True)` into namespace `ctx`, serves until SIGINT/SIGTERM, then closes. Needs current workflow graph format (share entries `0.6`+); does not convert legacy `__seamless__` exports. Contract: `shares.md` (*Serving saved graphs*), `workflow-context.md`. Commits: wf:50a2313, top:f01d358e.

**W17. Graph serialization.** NEW. `[WF]`. `ctx.get_graph()` returns the durable graph (format `0.7`: nodes, configs, edges, literal producers, `anonymous_nodes`, mount and share specs, download specs); `ctx.set_graph(graph, mounts=True, shares=True)` replaces wholesale, softcancels all runs, and blocks until attachments acknowledge. Run generations never reused; loading never executes code to rebuild callables. Format history in this branch: 0.3/0.4 (mounts, celltype rename), 0.6 (shares), 0.7 (downloads). Contract: `workflow-context.md`, `cells.md`, `mounts.md`, `shares.md`. Commits: wf:87b57c5, wf:61b2977, top:4760d1bd.

**W18. Examples and web-server guide.** NEW. `[WF]`. `seamless-workflow/examples/` (basic notebook, `share-sliders`, `share-download.py`, `mixlangstatus`, `cython-in-ipython`) and `docs/agent/guides/seamless-web-server.md` (shared cells as REST API, hot reload, deployment; the pack tool and Cloudless are marked "not yet implemented"). The examples have no contract page. Commits: wf:1450f0d, wf:baa7ea7, wf:2078afe, top:fba9978e.

#### Python face

**P1. `Transformer` factory and builder.** CHANGED/BREAKING. `[PY]`. `Transformer(language="python", compiled=False, direct=False)` (importable from `seamless_transformer`, `seamless.transformer`, `seamless.workflow`) builds code-less builders for `python`, `bash`, handler languages (`r`, `julia`, registered ones) and compiled languages; `available_languages()` maps names to `native`/`compiled`/`handler`. `language` is read-only. Builder state is mutable; `build()` / `transformation()` / `get_transformation()` return an immutable `Transformation` and never run it. Contract: `transformers.md`. Commits: tf:a69feb6, tf:a55d8b6, tf:d3fc802, top:f48c25e1.

**P2. `direct` / `delayed`.** CHANGED. `[PY]`. Both return a Transformer (Python only, one argument: function or Transformer to clone; no `language`). `delayed_tf(...)` is `build(...)`; `direct_tf(...)` is `build(...).run()`. Named work methods `compute/computation/run/task` work in both modes on both call modes. Contract: `direct-delayed-and-transformation.md`, `transformers.md`. Commits: tf:a69feb6, top:f48c25e1.

**P3. Standalone Cell, Pin, Expression.** NEW. `[PY]`. A standalone Cell has nothing running in the background: it pulls (reads evaluate, `compute()` starts missing upstream work), unlike a bound node. Standalone children (`c[3]`, `c.as_celltype(...)`) link to their parent. Sync evaluation inside a running event loop is refused (`RunningLoopRefusal`); a Cell getter turns that into `None` and stays `waiting`. `.build()` / `cell()` freezes to an `Expression`. `Cell.fingertip()` and `Pin.fingertip()` exist. Contract: `cells.md`, `pins.md`, `expressions.md`. Commits: core:7d5f669, core:1afac3b, tf:ebd8f3f, core:93365c3.

**P4. Failure delivery rule.** CHANGED. `[ALL]` for Cell, Pin, Transformer, Transformation. `.checksum/.buffer/.value/compute()` never raise for a recorded failure (answer `None`; failure on `.state`/`.exception`); `run()` raises (`TransformationError` for a Transformation; the recorded exception or `NodeError` bound). A failure to materialize an existing result is raised on every read and never recorded. `Expression.compute()/run()` raise (an Expression records nothing). Contract: `cells.md` (*Failures*), `direct-delayed-and-transformation.md`, `pins.md`. Commits: top:a3be4db3, core:b641f4f, tf:857f3ab, tf:a4762ad, wf:870b66c.

**P5. `Transformation.logs`.** NEW (was a `NotImplementedError` stub in 1.4). `[PY]` (and `ctx.tf.logs` `[WF]`). Captured stdout and stderr of a successful run followed by an execution-time block; failed handle returns the same string as `.exception`; canceled returns `None`; cache hits have no log (`None`). In-memory store per process, keyed by `tf_checksum`, bounded (LRU), never persisted. Execution time is the dispatcher's wall time (includes queueing and input resolution; not comparable to 0.x). Bash stdout/stderr kept as two streams; compiled C-level output captured in worker children (so a worker runs one compiled call at a time); `process` mode tees (live and retained). Not captured: output written straight to fds 1 and 2. Contract: `transformation-logs.md`. Commits: tf:ffecc38, tf:98f3475, tf:9a63cc8, tf:4caef32, tf:f92b832, tf:09a6532, dask:9b7d185, job:7deb8e3, rem:c002f33, wf:3ead83a.

**P6. `Transformation.cancel()` is a handle verb with soft substrate semantics.** CHANGED. `[PY]`. `cancel(recursive=False)` / `cancel_async` makes this handle terminal and softcancels its participation; the shared run continues for other members and stops when the last leaves. Terminal state is not revived by `clear_exception()`. Hard, checksum-addressed kill remains `seamless-cancel <tf_checksum>`, SIGINT on `seamless-run*`, and `TransformationCache.cancel_by_checksum`. `Expression` has only `softcancel()`; `Expression.cancel` raises `NotImplementedError`. Contract: `cancellation.md`, `expressions.md`. Commits: tf:6a1c5db, tf:62a3360, tf:e0bd31d, tf:b67d94b, core:243f3ca.

**P7. Optional pins.** NEW. `[PY]`/`[WF]`. Python signature defaults only. `tf.optional_pins` is a read-only set-like view; `tf.optional_pins.a.disable()/.enable()`. A null reaching an optional pin over a legal conversion pair is dropped before the transformation checksum is computed, so "unconnected" and "connected to null" give the same `tf_checksum`; a connected optional pin whose source has no checksum still blocks. Not available for bash, handler, or compiled transformers. Contract: `pins.md` (*Null, required pins, optional pins*), `compiled-pins.md`. Commits: tf:a55d8b6, dask:547fd03, wf:8982916.

**P8. `streaming` flag.** NEW. `[PY]`, `[WF]` node setting. `t.streaming = True` on a Transformation, `f.streaming = True` on a Transformer (copied at `build()`). Dask only (other backends ignore it). Does not change identity; cached runs emit nothing; bound flag is not saved in the graph and never re-runs the node. Contract: `streaming.md`. Commits: tf:5542064, tf:9c69f8e, tf:1b27a25, dask:7efe0d1, wf:6528d60.

**P9. Sync API inside Jupyter.** FIX. `[PY]`. Sync calls (`direct` calls, `tf.run()`, `tf.compute()`) from a thread whose own event loop is running now schedule on a shared background driver loop (an earlier attempt, 91bec26, deadlocked on executor starvation). No contract found. Commits: tf:9f23234, tf:eb8715b.

**P10. Environment object.** BREAKING. `[PY]`. `tf.environment.set_conda_env(name)`, `set_conda(yaml)` (stored, never acted upon), `set_docker({"name", "gpus", "shm_size"})`, `set_which([...])`, plus `get_*`. `set_powers`/`get_powers` removed (old saved state loads but is not re-saved). Now enforced where the job runs (see L4). Contract: `environments.md`, `compiled-transformers.md`. Commits: tf:2666294, tf:ddfa70f, tf:b087da9.

**P11. Fingertip and scratch policy.** CHANGED. `[ALL]`. Scratch applies to the result, never to the definition (the transformation dict is always published). A non-scratch pin or Cell holding a scratch producer's result publishes it; `allow_input_fingertip = True` (Python) / `--fingertip` (CLI) makes pins scratch. Fingertipping always runs locally in the process that wants the buffer and never writes to the hashserver; failures report the highest `fingertip_category` (`materialization`, `failed_transformation`, `irreproducible_transformation`, ...). `Cell.buffer/.value` never fingertip. Contract: `scratch-witness-audit.md`, `identity-and-caching.md`, `pins.md` (*Scratch at the pin*). Commits: tf:bd1b20b, tf:353d899, tf:36fbac4, tf:51e4eca, core:6174032, core:3479eb8.

**P12. Lazy root construction.** FIX. `[PY]`. `construct()` no longer starts the root transformation; only `start/compute/run` do. Documented in the API page only (no contract). Commits: tf:7b75170, top:00a667af.

#### Unix face

**U1. `seamless-run --conda ENV` / `--docker IMAGE` are enforced.** CHANGED (flags existed but were metadata-only in 1.4). `[UX]`. Aliases `--conda-env`, `--conda-environment`, `--docker-image`. The command runs in the conda environment (as under `conda run -n`; a name containing `/` is a path) or in a container; the two together are refused at dispatch; `--docker` sets the image name only. Neither flag changes the checksum, and a cached result is returned without checking. Contract: `seamless-run-and-argtyping.md`, `environments.md`. Commits: tf:ddfa70f, tf:b087da9, tf:1cdbbd3, tf:2666294, tf:0ffaec0.

**U2. Process-lock flags.** NEW. `[UX]`. `--no-process-lock` (`process_lock: false`), `--driver` (`driver: true`, implies no lock). Neither changes the checksum. `seamless-run-transformation` has neither flag. A nested `seamless-run` inside a script needs no flag (see R1). Contract: `seamless-run-and-argtyping.md`, `transformers.md`. Commits: tf:b486ae9, tf:9b24df9.

**U3. `--streaming`.** BREAKING (rename). `[UX]`. `seamless-run --streaming` and `seamless-run-transformation --streaming` replace `--direct-print`; all streamed text goes to stderr because stdout carries the result; Dask only. Contract: `streaming.md`. Commits: tf:4425c08.

**U4. Directory arguments and result targets are `folder`.** BREAKING. `[UX]`. See B1. The executing host writes the directory from its index and members from any buffer source (no longer requires seeing the submitter's buffer directory). Contract: `seamless-run-and-argtyping.md`, `deep-celltypes.md` (*In bash*). Commits: tf:65990d5, top:34e8f5d7.

**U5. First word of a command.** NEW. `[UX]`. An existing local file wins over a same-named tool on `PATH` and is uploaded (`chmod +x` applied to uploaded first words only); without `--conda/--docker`, tools in standard `bin|sbin|usr` directories stay names; with an environment the host `PATH` is never consulted. Contract: `seamless-run-and-argtyping.md`. Commits: not identified individually (part of the environment work, tf:ddfa70f to tf:2666294).

**U6. `--write-remote-job DIR` with environments.** CHANGED. `[UX]`. The job directory runs as `bash transform.sh`; with an environment, `transform.sh` is a one-command launcher and the script is `transform-inner.sh`. Contract: `seamless-run-and-argtyping.md`, `environments.md` (*The job directory on disk*). Commits: tf:936f44a, tf:ddfa70f, top:44741b0b.

**U7. `.SEAMLESS.yaml` / `.SEAMLESS.py` interface files removed; `--metafile`.** BREAKING/NEW. `[UX]`. The canonical-command machinery (`cmd/canonical.py`, interface-file lookup) was deleted; dependencies are declared with `-i`, `-I`, and the new `--metafile FILE` (checksummed and injected as `META__FILE__<name>`, excluded from identity; carried through the dunder and restored for bash in tf:621d149). No contract found for either. Commits: tf:b22e606 (merged by tf:1eb55f9), tf:621d149.

**U8. seamless-mode hooks.** CHANGED. `[UX]`. New entry points `seamless-mode-venv-hook` and `seamless-mode-shell`; `seamless-mode-bind.sh` for conda, POSIX venv/uv and Pixi. Contract: none (docs: `docs/main/seamless-mode.md`). Commits: tf:b639f05, top:49b79505.

**U9. `seamless-serve-graph`.** NEW. See W16.

#### Languages

**L1. Handler languages: R and Julia.** NEW. `[PY]` + `[WF]` only (not `seamless-run`, not `direct`/`delayed`). `Transformer("r", direct=True)`, `Transformer("julia", ...)`; code is source text, pins are declared through `tf.pins` (default celltype `mixed`), output is `result`. `register_language_handler` adds languages (`available_languages()`, `is_handler_language`); a handler travels with the transformation (`__handler__`, outside identity) and must be registered where a graph is loaded. Deep pins and results with `Checksum` classes of the language (a naked 64-hex string is a value). No optional pins. Contract: `handler-languages.md`, `identity-and-caching.md`. Commits: tf:444c918, tf:0ab7c3d, tf:452f06a, tf:fcca629, tf:495cc06, share:98774d0, top:e1bf5777.

**L2. Language backends `"cli"` / `"mem"`.** NEW. `[PY]` + `[WF]`. `tf.metavars.BACKEND` selects: R and Julia default `"cli"` (an `Rscript` or `julia` process per run), `"mem"` embeds the interpreter (`ryp`, `juliacall`); Python defaults `"mem"`; bash is CLI only; compiled is in-memory only. Any other value is refused at assignment. `BACKEND` is outside identity; backends must agree bit for bit when both succeed (a backend may fail where the other succeeds). `check_in_memory_environment` and `execute_cli` are the two public functions that honour environments. Contract: `language-backends.md`, `handler-languages.md`. Commits: tf:0ffaec0, tf:fc7d427, tf:6419657, tf:1d8664c, tf:8d06e4d, tf:6112096, wf:c8b7596, wf:6a6e011.

**L3. Python CLI backend.** NEW. `[PY]` + `[WF]`. `tf.metavars.BACKEND = "cli"` runs the Python code in its own process in a job directory, honours conda and Docker; no modules/globals; deep/`checksum` pins need seamless-core inside the job; every run pays an interpreter start. Results are type-matched with the in-memory backend (a `bytes` pin arrives as `bytes`). Contract: `language-backends.md`. Commits: tf:6419657, tf:1d8664c, tf:62f1bc0, top:8fcda23c, top:5ffca12b.

**L4. Conda / Docker / Podman / Apptainer for bash and CLI backends.** NEW (was metadata-only). `[ALL]`. `tf.environment` or `--conda/--docker`; the container runtime is chosen on the executing host: `SEAMLESS_CONTAINER_RUNTIME` (`docker|podman|apptainer|none`, default first that works), `SEAMLESS_CONTAINER_PULL` (`never|missing`), `SEAMLESS_APPTAINER_DIR` (SIF files named `<image>.sif`), `SEAMLESS_CONTAINER_ARGS`, `SEAMLESS_CONDA_EXE`. Image spec keys `name`, `gpus`, `shm_size`; legacy keys (`options`, `version`, `checksum`) refused with a pointer. A job never falls back to the plain host; cache hits need nothing. Jobs are torn down on cancellation. Contract: `environments.md`, `execution-backends.md` (*Environments are entered on the executing host*). Commits: tf:ddfa70f, tf:b087da9, tf:1cdbbd3, tf:28e4bb0, dask:7696c77, top:cf8fa2f7, top:765e0646.

**L5. Required binaries.** CHANGED. `[ALL]`. `set_which([...])` (and a CLI backend's own needs) is checked where the code runs, at dispatch; an in-memory backend can only check that its process already is in the requested conda environment (`CONDA_DEFAULT_ENV`/`CONDA_PREFIX`) and fails for a Docker image. Record probes are exempt. Contract: `language-backends.md`, `environments.md`. Commits: tf:0ffaec0.

**L6. Compiled transformer redesign and compiled pins.** CHANGED/BREAKING (details in B13). `[PY]` + `[WF]`. `Transformer(language, compiled=True, direct=...)` for c, cpp, fortran, rust (and go, present in code, undocumented). Schema is the only ABI source (`__schema__` in identity). Pin celltype whitelist per schema parameter; numeric scalars admitted by kind and range; arrays exact dtype; no optional pins; null rejected (including empty `bytes` passed as length 0 with a valid pointer); schema `char` is C `unsigned char`; Stage 1 (data-independent) and Stage 2 (data-dependent) validation; no conda/Docker wrapping (in-memory only). Contract: `compiled-transformers.md`, `compiled-pins.md`, `seamless-signature-schema.md`. Commits: tf:5202436, core:b624b9a, wf:7cf4efc, dask:ce98546, sig:32ca0dc, tf:fa6ecde.

**L7. Bash execution mechanics.** CHANGED. `[ALL]`. A bash body runs `bash transform.sh` from its materialized job directory and never changes the process cwd; stdout and stderr are separate streams; a cancelled run kills the script; `META__FILE__*` pins are restored; `SEAMLESS_PROCESS_LOCK_NOTIFY` (named pipe) lets a nested `seamless-run` release the outer lock. Bash refuses `deepcell` and `deepfolder` pins. Contract: `execution-backends.md` (*Bash bodies*), `environments.md`, `cancellation.md` (*A bash run that is cancelled*). Commits: tf:936f44a, tf:ec487b7, tf:28e4bb0, tf:621d149, tf:1fb4889.

**L8. Interpreter thread for embedded R/Julia.** NEW. `[PY]` + `[WF]`. `run_in_interpreter_thread` gives a handler a fixed thread; `SEAMLESS_INTERPRETER_THREAD` was removed before release (the thread stays for Julia); an in-memory handler backend refuses to run without the process lock (including as a driver). One embedded interpreter per language per process, never unloaded. Contract: `handler-languages.md` (*Threads*), `execution-backends.md`. Commits: tf:3db40f2, tf:44fb295, tf:02969fa, top:ffef6f98, top:2c92e0d8.

#### Core

**C1. Celltypes, canonical null, virtual values.** NEW/CHANGED. `[ALL]`. 13 celltypes: `binary, mixed, text, python, ipython, plain, yaml, str, bytes, int, float, bool, checksum`. Hierarchy edges keep the checksum. Canonical null is `b"null\n"` (`38e0b9de...`); empty `bytes` canonicalizes to null; virtual values (null, true, false) resolve without buffers; `bool` accepts only the four canonical boolean checksums plus null; `str(Checksum(NULL))` is `"NULL"`. Contract: `celltypes-and-conversion.md`. Commits: core:36af72c, core:adc2450, core:746ca7d.

**C2. Conversion engine.** CHANGED/BREAKING for checksums (B14). `[ALL]`. Rewritten, ported from legacy: rule categories trivial / reinterpret / reformat / possible / values, `conversion_needs_buffer` dry-run; `text -> plain` always writes the canonical plain buffer; `binary -> bytes` converts every `S`-dtype array to bytes; `X -> checksum` yields the source checksum itself; non-finite floats rejected in `binary -> plain` and `float` targets. Empty-path conversions are cached as empty-path Expressions. Contract: `celltypes-and-conversion.md`. Commits: core:3701453, core:c77d688, core:0f4a131, core:827bd5b, core:a00ea2c, core:6f2f14e.

**C3. HashType.** NEW. `[ALL]`. A checksum-level classification ("word") that disproves readings and conversions without fetching buffers (`False` = proof of impossibility, raises `HashTypeValidationError`) and, proves a reading when `deserializable_as` answers `True` (used only to skip a fetch). Computed locally, cached, stored in the database `hash_type` table, only ever tightens. Never asked about `deepcell/deepfolder/folder/module`. Contract: `hashtype.md`. Commits: core:746a4e8, core:09532c9, core:b9dd0da, core:57f872e, core:0d3ccfb, core:d7fb85a, core:70e4cc7, db:52f2ba0, tf:855153c, dask:97110b6.

**C4. Expressions.** NEW. `[PY]` + `[WF]`. See W-list; core facts: `Expression(input_ref, path="", *, input_celltype, celltype)` is frozen; identity `(input_checksum, path, input_celltype, celltype)`; project, then convert; at most one conversion; cost class decided from checksum-level facts (free / one child / all children); failures never cached; result cache is process-global (unbounded) plus database `expression` and `rev_expression` tables; `evaluate_expression_placed` order: process cache, database, local, dispatch, local materialize. Placement values `"auto"|"local"|"remote"`; "local" includes registered local buffer sources. Contract: `expressions.md`. Commits: core:a51d43d, core:8e00718, core:e449bfb, core:422865e, core:4bb486c, core:5d7a542, db:31b31d8.

**C5. Deep celltypes (`deepcell`, `deepfolder`, `folder`).** CHANGED/BREAKING. `[ALL]`. Flat index `{string key: 64-hex checksum}` serialized as `plain`; `folder` and `deepfolder` index buffers are byte-identical, conversion free; `deepcell` members are `mixed`. Outside bash: `deepcell` and `deepfolder` pins are dicts of checksum objects, `folder` pin is a dict of contents; bash gets `folder` as a materialized directory and refuses the other two; a deep result is an index (nothing holds claims on members); a transformer cannot produce a `deepfolder`; a naked 64-hex in a result is a value (wrap with `Checksum`). `module` is not a deep celltype. Contract: `deep-celltypes.md`, `content-addressed-files-and-dirs.md`. Commits: tf:a5c758a, tf:65990d5, tf:9bb38ae, dask:3086d64, top:f6b1db93, top:34e8f5d7.

**C6. Null at the function boundary.** NEW. `[ALL]`. A Cell admits null for any celltype; a required pin or result admits null only for `plain`, `mixed`, `bytes` (else `TypeError` / `RuntimeError: Null result is not allowed...`); empty bytes canonicalize to null first. Contract: `pins.md`, `celltypes-and-conversion.md`. Commits: tf:91e0cf3, core:adc2450, tf:e0ae171.

**C7. Compression.** CHANGED. `[ALL]`. `.zst`/`.gz` handling is a materialization detail; a `folder` pin follows the suffix in its name (`mydata.zst` gives members `file.npy.zst`); `deepfolder` pins expose no stored form; symlinked buffers a container cannot follow are copied. Mount paths ending `.gz`/`.zst` compress canonical bytes. Contract: `compression.md`. Commits: tf:65990d5, tf:bd1b20b.

**C8. Local buffer sources.** NEW. `[ALL]`. An internal, process-wide registry (not an extension point) of read-buffer directories (including a locally launched hashserver's directory) and directory-write-mount leaf files. Resolution order: buffer cache, local sources, remote read servers. Bytes are validated by checksum; a source is not a claim; process-local only. Placement counts a source as local. Contract: `cache-storage-and-limits.md`. Commits: core:b571259, core:e6dbe92, core:16f0989, rem:19bf588, core:42e33f2, core:6974b08.

**C9. Provenance as a derivation graph.** NEW (contract, partial tooling). `[ALL]`. The provenance of a result is the graph of recorded producers (Transformation, Expression, cell join) reached through reverse rows; a Context's derivation is complete; leaves are original data or coverage gaps; each `seamless.db` is a shard. The driver link is not recorded. No dedicated tool. Contract: `scratch-witness-audit.md` (*Provenance*). Commits: db:97c79c9, core:2bccba0.

**C10. Identity updates.** CHANGED. `[ALL]`. `__handler__` is an orthogonal envelope key; `__format__` carries the pin `filesystem` entry and is load-bearing; `__meta__` carries `process_lock`, `driver`, `metavars`; `seamless-run` directory celltypes enter identity through `__format__` and `__output__`. Only implicit canonicalization is empty bytes to null. Contract: `identity-and-caching.md`, `pins.md` (*Pins on file*). Commits: share:98774d0, tf:65990d5.

**C11. Error types.** NEW. `[ALL]`. `ValueUnavailableError` (exported as `seamless.ValueUnavailableError`), `CacheMissError.fingertip_category`, `HashTypeValidationError`, `ExpressionEvaluationError`, structured error envelope (the exception type does not depend on where an Expression ran). Contract: `cells.md`, `expressions.md`, `hashtype.md`. Commits: core:108a1f1, core:6174032.

#### Remote and services

**R1. Process lock and drivers.** NEW/BREAKING. `[ALL]`. Every process that runs bodies has one lock; by default a body holds it (one body per process; `process_lock` default true). A body that submits nested work gives it up at submission and never retakes it (`tr.start/compute/run`, `parallel`, fingertip recompute). `driver=True` never takes it; setting `driver` forces `process_lock` false; both true is invalid. On Dask the permission routine (anti-deadlock) is skipped for driver submissions. A worker accepts up to three transformations at once (the throttle); the lock decides how many bodies run. `global_lock` is retired (`AttributeError`). Contract: `execution-backends.md`, `transformers.md`. Commits: tf:b486ae9, tf:e4d5834, tf:9b24df9, tf:6b034d4, tf:c42e897, dask:822c3c4, dask:d464bfd, top:7b9a97e1.

**R2. Expressions placed where the data is.** NEW. `[ALL]`. A jobserver or daskserver is closer to the hashserver than the client; an Expression whose input the client does not hold is dispatched there (checksum-only responses); no silent fallback once a configured server fails; explicit `"local"`/`"remote"` never fall back. Jobserver `run-expression`; Dask cache-aware expression tasks. Contract: `expressions.md` (*Placement*), `execution-backends.md` (*Expressions are placed, not configured*). Commits: core:8e00718, core:e449bfb, job:77bfdb8, job:2f88770, dask:2bc56ea, dask:17349e2, dask:f939170, rem:65cc871, rem:c70ef4b.

**R3. Cancellation membership model.** CHANGED. `[ALL]`. One membership set per deduplication site; softcancel = deregister (never kills a shared run), cancel = kill-all; real termination only at the leaf (jobserver: an emptied set cancels the job and frees the worker slot; Dask: an emptied set releases futures and does not terminate). Crashed members cause benign under-cancellation (no heartbeats). Expressions have a 3 s linger. `member=None` softcancel is a no-op returning `False`. A run waiting for the process lock never starts its code if cancelled. Contract: `cancellation.md`. Commits: job:99d9232, rem:1ec9794, dask:33ba59c, dask:f0a7171, dask:cda2719, tf:6a1c5db, core:243f3ca.

**R4. Jobserver.** CHANGED. `[ALL]`. Inline expression and celljoin endpoints, soft cancellation by member id, logs returned with results, import-lock race fix at startup, completed transformations marked done. Contract: `execution-backends.md`, `cancellation.md`. Commits: job:77bfdb8, job:99d9232, job:7d83682, job:7deb8e3, job:1261700, job:0289ff4.

**R5. Dask backend.** CHANGED. `[ALL]`. Expression and celljoin tasks on workers, HashType validation, deep-cell checksums, `nparallel` propagation, environment validated before dispatch, optional pins, log transport with fresh-run invalidation, streaming events, nested dispatch correlation, results routed through lifecycle publication. Contract: `execution-backends.md`, `streaming.md`. Commits: dask:2bc56ea, dask:4d9bd2c, dask:3086d64, dask:a93a2e8, dask:7696c77, dask:9b7d185, dask:bd06923, tf:ef6a5bc.

**R6. Database (protocol 2.3).** CHANGED. `[ALL]`. New tables/rows for Expression results (forward and reverse), HashType words, and celljoin pairs `(celljoin checksum, celltype)`; `PUT transformation` is idempotent and a different result answers HTTP 409; `PUT irreproducible` has manual and `mode: "automatic"`; legacy `BufferInfo` removed. Package 2.2.0; protocol bumped to 2.3. Contract: `execution-records.md`, `identity-and-caching.md`, `hashtype.md`. Commits: db:31b31d8, db:52f2ba0, db:dfc6985, db:46e993e, db:97c79c9, db:d78df47.

**R7. Automatic irreproducible observations.** NEW. `[ALL]`. When a recomputation yields a different result for a recorded `tf_checksum`, an automatic observation row is added without replacing the forward result or the original execution record; `report_irreproducible_result(tf_checksum, result_checksum)` (returns `False` on 404/409); manual quarantine (`PUT irreproducible` default mode) still moves the entry; `PUT metadata` refuses once any irreproducible row exists. `seamless-share` keeps live lookup state for such observations. Contract: `execution-records.md`, `identity-and-caching.md`, `scratch-witness-audit.md`. Commits: rem:ceb432c, db:46e993e, share:0f5046e, tf:36fbac4.

**R8. Execution records.** CHANGED. `[ALL]`. Probing remains manual (five independently cached buckets); one sanctioned exception: a missing conda environment triggers a single `rhl-cache-conda` refresh in the launcher. The record's `language` field reports `python` for handler languages. Contract: `execution-records.md`. Commits: rhl:417d891, rhl:0930cca, tf:5e46407.

**R9. Streaming transport (Dask).** NEW. `[ALL]` (Dask only). Worker `log_event` + client `subscribe_topic`; 8192 bytes per chunk, 2 s per stream; head truncation with dropped-byte count; tqdm bars (`tqdm`, `tqdm.std`, `tqdm.auto`) become progress events rendered as local bars (`tqdm.notebook` out of scope); throttle relay via the public Dask control path. Contract: `streaming.md`. Commits: dask:7efe0d1, dask:48568b5, dask:33be141, dask:d53ba5d, tf:1b27a25.

**R10. Remote materialization dedup.** NEW. `[ALL]`. Concurrent resolutions of one checksum share one fetch (and local-source lookups share too); the fetch is aborted when its last waiter leaves. Contract: `expressions.md` (*Deduplication*). Commits: rem:7840e1f, core:16f0989.

**R11. Nested Dask hang fixes.** FIX. `[ALL]`. Worker health checks no longer restart a worker whose body holds the GIL (the check is about once a second); nested delegation no longer wedges (issue 268, shipped in 1.4.x); nested scratch inside spawned workers fixed. Contract: `execution-backends.md` (*GIL*). Commits: tf:d56f4fa, tf:ff6b19f, tf:51e4eca, tf:44fb295.

**R12. Service tooling and config.** CHANGED (minor). rhl conda-cache fixes (`rhl-cache-conda`, stale conda bin) shipped in 1.4.x (v0.4.4, v0.4.5); `seamless-config` selects local `process` execution for its smoke scripts; `seamless-service-*` and `rhl-*` helpers unchanged. hashserver: no functional change. Contract: `service-management.md` (unchanged). Commits: rhl:417d891, rhl:0930cca, rhl:565dfc5, rhl:b16fda1, cfg:3c170b0.

#### Other

**O1. Reference lifecycles.** NEW (internal; user-visible effects under *Internal changes with user-visible effect*). Contract: `internal/checksum-reference-lifecycle.md`.

---

### Breaking changes since 1.4

1.4 adoption is limited, so these are informational, not a migration guide.

| # | Change | Where | Migration hint |
|---|---|---|---|
| B1 | `seamless-run` directory arguments and result targets are `folder` (were `deepfolder`); new transformation checksums | `seamless-run-and-argtyping.md`; tf:65990d5 | Re-run once to recompute; update stored `tf_checksum`s. Bash now refuses `deepfolder` pins |
| B2 | A naked 64-hex string in a `deepcell`/`folder` result is a value (a `folder` result raises `TypeError`) | `deep-celltypes.md`; tf:452f06a | Wrap checksums: `Checksum(s)` / language checksum classes |
| B3 | Outside bash, `deepfolder` pins are dicts of checksum objects (like `deepcell`), `folder` is always a dict of contents; bash refuses `deepcell` and `deepfolder` | `deep-celltypes.md`; tf:65990d5 | Declare the pin `plain` to get 64-hex strings; use `folder` for bash |
| B4 | Every file of a deepcell `RESULT` must parse as `mixed` | `deep-celltypes.md` | Write files as JSON or use `folder` |
| B5 | conda + Docker together and unknown image keys are refused at dispatch (legacy keys `options`, `version`, `checksum` named in the message) | `environments.md` | Pick one; use `gpus`, `shm_size`, `name@sha256:...` |
| B6 | A `bytes` pin reaches Python code as `bytes`, not `seamless.Buffer` | `pins.md`; tf:62f1bc0 | Use the value itself instead of `value.content` |
| B7 | `BACKEND` accepts only `"cli"` and `"mem"` (`"ryp"`, `"juliacall"` were never released values) | `language-backends.md` | None |
| B8 | `direct_print` property/keyword and `__direct_print__` meta key removed; `--direct-print` becomes `--streaming` (Dask only); graph key `direct_print` ignored on load | `streaming.md`; tf:4425c08 | Use `streaming`. Streamed output only with `remote: daskserver`; in `process` mode output reaches the terminal anyway (the log tees it) |
| B9 | `global_lock` retired (`AttributeError`); default-on per-process lock changes concurrency (one body per process, released on nested submission) | `execution-backends.md`; tf:b486ae9, tf:e4d5834 | Set `process_lock=False` (or `driver=True`) on the transformer / `--no-process-lock` / `--driver` |
| B10 | `CompiledTransformer` and `DirectCompiledTransformer` are no longer exported | `compiled-transformers.md`; tf:a69feb6 | `Transformer("c", compiled=True, direct=...)` |
| B11 | Transformer pin sugar removed: `tf.x`, `tf["x"]`, `del tf.x` raise `AttributeError` (use `.pins`); `ctx.tf.x = v` is gone | `transformers.md`, `pins.md`; tf:d3fc802, top:9e0a2797 | `tf.pins.x` (or `tf.args.x`) |
| B12 | `Environment.set_powers` / `get_powers` and the `powers` key removed (old state loads, is not re-saved) | `environments.md`; tf:2666294 | Drop the call |
| B13 | Compiled transformer redesign: `char` in generated headers is `unsigned char`; scalar admission by kind and range; no optional pins; null rejected; pin celltype whitelist; `set_conda_env` is a requirement on the worker process, `set_docker` fails at run time (previously metadata only) | `compiled-pins.md`, `compiled-transformers.md`; tf:5202436, sig:32ca0dc | Recheck kernels and pin declarations against the contract |
| B14 | Conversion engine rewrite: `text -> plain` writes the canonical plain buffer (checksum changes for non-canonical JSON), `binary -> bytes` turns `S` arrays into bytes, non-finite floats rejected, `bool` strictness | `celltypes-and-conversion.md`; core:3701453, core:a00ea2c, core:0f4a131 | Expect different checksums for the same non-canonical inputs; canonicalize with `plain -> text -> plain` |
| B15 | `Transformation.cancel()` is soft for the shared run (handle goes terminal, run continues for other members) | `cancellation.md` | Use `seamless-cancel <tf_checksum>` or `cancel_by_checksum` for a hard kill |
| B16 | `.SEAMLESS.yaml` / `.SEAMLESS.py` interface files for `seamless-run` removed | tf:b22e606 (no contract) | `-i`, `-I`, `--metafile` |
| B17 | Required pins of celltype other than `plain`/`mixed`/`bytes` now reject null (`TypeError`). Results: 1.4 refused every `None` result (`RuntimeError("Result is empty")`); 1.5 accepts null for `plain`/`mixed`/`bytes` results and raises `RuntimeError: Null result is not allowed...` otherwise | `pins.md`; tf:91e0cf3 | Pass values to required pins, or make the pin optional (Python) |
| B18 | Database wire protocol 2.1 to 2.3: automatic vs manual irreproducible modes, `PUT transformation` conflict `409`, `BufferInfo` removed | `execution-records.md`; db:dfc6985, db:d78df47 | Upgrade the database package (2.2.0) with the clients; automatic schema upgrade only for empty legacy tables |
| B19 | Rename family `target_celltype` to `celltype`, `input_ref` to `source`/`checksum`, `Cell.status` to `Cell.state`, `TransformerBuilderSnapshot` to `FrozenTransformer`, `SubCell` removed. Not breaking relative to 1.4 (these classes were not released); breaking only for pre-release branch users | `cells.md` (*Retired names*) | Retired names raise `AttributeError` naming the replacement |
| B20 | Graph format: workflow graphs are `0.7`; 0.2/0.3 graphs load only when `target_celltype` is absent or equals `celltype`; legacy `__seamless__` exports are not converted. First released format, so no 1.4 migration | `workflow-context.md`, `seamless-workflow/README.md` | Re-save graphs |

---

### Known limitations

From the contract pages (file in brackets):

- **Workflow.** No sub-contexts, cycles, non-eager mode, mandatory preemption, transient-failure state or storage of Cells/Expressions/Transformations in a Context [`workflow-context.md`]. Future-wiring and fire-and-forget are deferred; there is no dependency-declaration contract; no buffer-arrival subscription (a missing input buffer is a `failed` node, retry via `clear_exception()`); node-by-node construction of large graphs is slow, derivation re-derives the whole graph each turn [`workflow-context.md`, `node-state-lifecycle.md`].
- **Cells.** Validators not implemented; standalone `clear_exception()` does not clear a memoized result; deep connection targets only one level; no persistent sub-path overlays; `.buffer`/`.value` never fingertip [`cells.md`]. Exception classes are unspecified for: root edge plus sub-path edges, write under stored null, write below a deep key, malformed builder calls, refused `process_lock`/`driver` writes [`cells.md`, `transformers.md`].
- **Pins.** `yaml`/`python` input-pin celltypes deferred; no sub-pin targets, validators, mounts; a standalone Cell cannot be assigned to a bound pin [`pins.md`]. Compiled pins: no optional pins, null rejected, restricted celltype whitelist [`compiled-pins.md`].
- **Attachments.** Only whole bound cell nodes (no standalone, sub-path, pin or code attachments); one file, one widget and one share slot per node; not a plugin API; generic layer is file-shaped; the barrier is spelled `ctx.mounts`; no continuous external ownership; no hard cancel of in-flight deliveries; no `settled()` predicate [`attachments.md`].
- **Mounts.** No durability (`fsync`), no cross-process exclusivity, no context mounts or automatic paths, `rw` rewrites non-canonical sensed bytes, deletion leaves a sensing node unchanged, null on a directory is terminal, caps (1 GiB file, 100 000 files / 10 GiB / 60 s directory), network filesystems can miss same-size same-mtime changes [`mounts.md`].
- **Shares.** No auth, TLS or sessions; no deep or directory shares; `folder` downloadable, `deepfolder`/`deepcell` not; no PUT by checksum; GET never computes; a download holds the archive in memory; no range requests; no generated pages [`shares.md`]. `state-graph` exposes every node's path, state, checksum and error text to anyone who can reach the server.
- **Widgets.** `ipywidgets` marshalling onto the kernel loop is a non-goal; widgets are not saved; cannot clear a cell; debounce not public [`widgets.md`].
- **Languages.** R and Julia not available through `seamless-run`, `direct` or `delayed`; no optional pins; R and Julia code cannot resolve checksums; CLI backends cannot take Seamless-mixed pins; failures under any CLI backend are titled "Bash transformer exception"; embedded interpreters are never unloaded; the execution record reports handler languages as `python`; no CLI backend for compiled code; no modules/globals under the Python CLI backend [`handler-languages.md`, `language-backends.md`].
- **Environments.** No building of conda environments or images; no remote Docker daemon; comma in a mount path unsupported under docker/podman; `singularity` not supported (apptainer is); nested Seamless inside a container unsupported; the record does not say which image ran; a bound node's environment cannot be changed [`environments.md`].
- **Execution.** Dispatch ignores the process lock; a hung body blocks its process; in `process` mode a cancel does not interrupt running Python code; Streaming is Dask-only; output written straight to fds 1/2 is neither logged nor streamed [`execution-backends.md`, `streaming.md`, `transformation-logs.md`].
- **Cancellation.** Cancellation does not reach the executing side of a dispatched Expression; a shared run's task is owned by the first caller's event loop (xfail-pinned); no liveness machinery [`cancellation.md`, `expressions.md`].
- **Expressions / HashType.** Process-local Expression cache is unbounded; no Expression counterpart of `IrreproducibleTransformation`; HashType cannot prove Seamless-mixed, `python`/`ipython`/`yaml` syntax or `checksum` hex; `plain -> yaml` is not exact [`expressions.md`, `hashtype.md`, `celltypes-and-conversion.md`].
- **Provenance.** Driver-to-launched-transformation link not recorded [`scratch-witness-audit.md`].
- **Not designed in.** Workflow authorizer (deferred), Cloudless, pack tool, compiled-module parity, Silk, macros, libraries.

---

### Legacy parity (Seamless 0.x versus 1.5)

Legacy source: `seamless/docs/legacy/*.html`. "Complete" means the 0.x capability has a documented 1.5 equivalent with no known missing part. "Partial" lists what is missing.

| 0.x capability | 1.5 equivalent | Status | Missing / different |
|---|---|---|---|
| Contexts with reactive cells | `seamless.workflow.Context` (W1-W3) | **Partial** | No sub-contexts (`ctx.sub = Context()` is a namespace), no macros, no cycles, no non-eager mode, no future-wiring / fire-and-forget (runtime is checksum-wired only), validators not implemented. Reconciles the whole graph per node edit: build large graphs with one `set_graph` |
| Cell types and conversion | 13 celltypes + deep (C1, C2) | **Complete** (plus HashType) | 0.x "structured"/Silk celltype is absent |
| Subcell / alternative subcell syntax | Projections `ctx.a.b`, `ctx.a[3]`, `as_celltype` (W5) | **Partial** | Connection targets limited to root or one level; deeper writes are read-modify-set transactions; no persistent sub-path overlays |
| Transformer pins (`ctx.tf.x = 10`, `ctx.tf["x"]`) | `ctx.tf.pins.x` (W8) | **Partial** | Attribute/item sugar removed; "any pin None gives result None" replaced by explicit null/optional-pin rules; no per-pin `io`/`as_`; pins cannot be mounted |
| Python transformers | `ctx.tf = func`, `direct`/`delayed` (W7, P1-P2) | **Complete** | Executes under the default per-process lock; thread isolation is by process, not by directory |
| Bash transformers | `Transformer("bash")`, `seamless-run` (L7) | **Complete** | |
| IPython transformers (`language="ipython"`) | none as a language; `ipython` celltype exists | **Absent** | Cython example uses an `.ipy` cell (`examples/cython-in-ipython`); no contract |
| Compiled transformers (c, cpp, fortran) | `Transformer(lang, compiled=True)` (L6; + rust, go) | **Complete** for transformers | 0.x compiled *modules* (Modules page) have no direct equivalent; `tf.objects` (`CompiledObject`) links additional objects |
| R transformers | `Transformer("r")` (L1) | **Partial** | New backends and rules; R CLI backend refuses `float32` and >2-D arrays; R code cannot resolve checksums |
| Julia transformers | `Transformer("julia")` | **New** (not in 0.x) | CLI backend project files are located relative to a source checkout (see *Known issues*) |
| Adding new transformer languages | `define_compiled_language`, `register_language_handler` | **Complete** | |
| Transformer status / exception / logs | `.state`, `.block_reason`, `.exception`, `.logs` (W3, P5) | **Partial** | Logs are per process memory, `None` for cache hits, one stdout/stderr text; there is no context-wide `ctx.status` aggregate (no contract found) |
| Preliminary results and progress | `streaming` + tqdm (P8, R9) | **Partial** | Dask only; no preview values from a running transformer |
| Jupyter integration (traitlets, ipywidgets) | `seamless_workflow.jupyter.traitlet/output` (W13) | **Partial** | Function API instead of cell methods; widgets are live objects and not saved; no state display in widgets; `folder` unspecified, `deepfolder` refused |
| File mounting | `cell.mount(...)`, `ctx.mounts.sync()` (W12) | **Partial** | No context mounts, no automatic per-cell paths, no extension inference, no pin/code/sub-path/standalone mounts (mount a cell and connect it); no cross-process exclusivity; no `fsync`; network filesystems documented as limited |
| Shareserver: REST + websocket | `cell.share()` (W14, W15) | **Partial** | One port; no authentication, TLS or sessions; deep celltypes not shareable; no web-interface/status generator (a page is a `text` cell you write); browser-client property mapping cannot represent every share key |
| Collaborative web interfaces | shares + `seamless-client.js` + hold on close (W14-W16) | **Partial** | No auth; one Context per user for isolation |
| Web status generator / visualization | `/<ns>/state-graph` JSON (W15), `examples/mixlangstatus` | **Partial** | No HTML generator |
| Deep cells (incl. mapping contexts) | `deepcell`, `deepfolder`, `folder` (C5, W10) | **Partial** | One-step path only, flat index, no `deepcell` mounts or shares, no macro-based mapping contexts |
| Libraries / libinstances / stdlib (`merge`, `select`, `switch`, `map`) | none | **Absent** | |
| Macros and the low level | none | **Absent** | No contract found |
| Modules (Python modules, `module` cells) | `module` pin celltype, `modules` in builders, embedded modules (`modules-and-closures.md`) | **Partial** | `module` is not mountable; IPython modules and compiled modules have no equivalent |
| Environments (transformer, context) | `tf.environment`, `--conda/--docker` (L4) | **Partial** | No context-level environments; conda spec stored but never built; no image building; no remote Docker daemon; compiled code cannot be wrapped |
| Validation (Silk schemas) | `validator=` accepted, `NotImplementedError` | **Absent** | |
| Debugging (print, debug sessions, sandbox) | logs, streaming, traceback fixes | **Partial** | No debug mode / sandbox sessions |
| Data storage: database, vaults, zips | `seamless.db`, hashserver, `seamless-upload/download`, `seamless-share` | **Different** | No vault or zip export of a Context; graphs hold checksums only, buffers live in the hashserver |
| Job management / "jobless" | jobserver, Dask, `seamless-cancel` (R2-R5) | **Complete** (different design) | |
| Cloudless deployment | none | **Absent** | Guide marks it "not yet implemented" |
| Seamless projects (`seamless-new-project`, collaborative hosts) | `seamless-config` projects/stages/clusters | **Different** | Project scaffolding tools absent |
| Save the entire state of a context | `get_graph()` / `set_graph()` (W17) | **Partial** | Format is new; 0.x exports are not converted |
| Cancellation on pin change | softcancel of superseded runs after a hold; `prune()` | **Changed** | Superseded runs may occupy slots until the hold or `prune()` |
| Concurrent execution without blocking the shell | controller thread + workers | **Partial** | Default one body per process unless `process_lock=False` or workers |

---

### Internal changes with user-visible effect

- **Checksum reference lifecycle (claims, holds, shutdown audit).** Effect: buffers survive eviction while a live Cell, Pin, Expression or Transformation holds a claim; non-scratch owners publish results; `seamless.close()` can report outstanding claims; fixed a buffer-cache refcount deadlock and underflow reporting. Commits: core:d88aa1a, core:7d9693c, core:ecb191d, core:57084bc, core:d4be619, core:b88a919. Contract: `internal/checksum-reference-lifecycle.md`.
- **Controller thread with sequenced ingress.** Effect: atomic invalidation, no dual-write window, reads that never wait, `ReentrantContextError` when a public call is made from inside a turn. Commits: wf:ed22f1d, wf:57b29f5.
- **Membership sets per dedup site.** Effect: cancelling one caller no longer kills a run another caller wants; crashed clients cannot kill peers. Commits: tf:6a1c5db, job:99d9232, dask:33ba59c.
- **Jupyter executor-starvation fix** (scoped driver loop). Effect: `direct` calls and `tf.run()` work from a notebook cell. Commits: tf:9f23234.
- **Nested Dask hang fixes.** Effect: nested Dask dependencies no longer wedge after cancel/release; workers running a long GIL-holding call are not restarted. Commits: tf:d56f4fa, tf:ff6b19f, tf:44fb295.
- **Insert-only result recording, centralized.** Effect: a recompute no longer overwrites a recorded T-to-R mapping; fingertip failures keep their category. Commits: tf:36fbac4, db:46e993e.
- **Bash job directories, no `chdir`.** Effect: the cwd of a process running bash transformations never changes. Commits: tf:ec487b7, tf:936f44a.
- **Remote fetch sharing.** Effect: fewer duplicate downloads when many Expressions need one checksum. Commits: rem:7840e1f.
- **HashType replaces BufferInfo.** Effect: invalid readings are rejected before any fetch; old `BufferInfo` metadata is not used. Commits: core:3701453, db:d78df47.
- **Jobserver startup race fix.** Effect: no import-lock race at worker start. Commits: job:1261700.
- **Disabled refholder accounting in workers; scoped CLI upload references.** Effect: lower overhead in workers. Commits: tf:9a951ab, tf:1c869da.

---
