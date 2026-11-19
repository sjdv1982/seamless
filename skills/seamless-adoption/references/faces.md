## The three faces, and which property lives where

Seamless 1.5 has three entry points ("faces"). They share one transformation identity and one cache, but many features exist on one or two faces only. When you describe a property, name the face. "Seamless reacts to file edits" is wrong; "a mounted cell in a workflow Context reacts to file edits" is right.

- **Python face**: `direct`, `delayed`, the `Transformer(...)` factory, `Transformation` handles, standalone `seamless.Cell` / `Pin` / `Expression`. Your program decides what runs next.
- **Unix face**: `seamless-run` and its companions (`seamless-upload`, `seamless-download`, `seamless-queue`, `seamless-cancel`, `seamless-run-transformation`, Seamless mode). Your shell script decides what runs next.
- **Workflow face**: `from seamless.workflow import Context, Cell, Transformer` (package `seamless-workflow`). A reactive runtime owns a DAG of cells and transformers and keeps it up to date.

### Property table

`PY` = Python face, `UX` = Unix face, `WF` = workflow face. Contract pages are in `docs/agent/contracts/`.

| Property | Faces | Notes (contract) |
|---|---|---|
| Python transformers | PY, WF | `direct`/`delayed` (PY), `ctx.tf = func` (WF) (`transformers.md`) |
| Bash transformers | all | `Transformer("bash")` (PY, WF); `seamless-run` is bash (UX) |
| R, Julia (handler languages) | PY via `Transformer("r")`, WF | not `direct`/`delayed`, not `seamless-run` (`handler-languages.md`, *Faces*) |
| Compiled (C, C++, Fortran, Rust) | PY, WF | `Transformer("c", compiled=True)`; in-memory only (`compiled-transformers.md`) |
| Optional pins | PY, WF | Python signature defaults only; not bash, handler or compiled (`pins.md`) |
| Persistent caching | all | optional in Python (`seamless.config.init()`), mandatory for `seamless-run` (`SEAMLESS_CACHE` or a cluster) |
| Standalone Cell / Expression (pull, nothing runs in the background) | PY | `cells.md`, `expressions.md` |
| Reactive graph, node states, block reasons, `prune()` | WF | `workflow-context.md`, `node-state-lifecycle.md` |
| File and directory mounts | WF | whole bound cells only (`mounts.md`) |
| Jupyter widgets | WF | `seamless_workflow.jupyter.traitlet/output` (`widgets.md`) |
| HTTP/WebSocket shares, downloads, state graph, `seamless-serve-graph` | WF | `shares.md` |
| Cell joins | WF | `cells.md` (*Cell-level joins*) |
| Save/load a graph (`get_graph`/`set_graph`) | WF | graph holds checksums, not data (`workflow-context.md`) |
| `.logs` | PY (`Transformation.logs`), WF (`ctx.tf.logs`) | per-process memory, `None` on cache hits (`transformation-logs.md`) |
| Streaming of stdout/stderr/tqdm | PY (`.streaming`), UX (`--streaming`), WF (node setting, not saved) | Dask only (`streaming.md`) |
| conda / Docker / Podman / Apptainer | PY, WF (`tf.environment`), UX (`--conda`, `--docker`) | entered only by bash and CLI backends (`environments.md`, `language-backends.md`) |
| `process_lock` / `driver` | PY, WF (node settings), UX (`--no-process-lock`, `--driver`) | `transformers.md`, `execution-backends.md` |
| Failure delivery: reads and `compute()` give `None`, `run()` raises | PY, WF handles | a `direct` call is a `run()` and raises; `seamless-run` uses its exit code (`cells.md`, *Failures*) |
| Soft cancel of a handle | PY (`Transformation.cancel()`), WF (Context only softcancels) | hard kill: `seamless-cancel <tf_checksum>` (`cancellation.md`) |
| Expression placement policy | PY (per-Expression `execution=`), WF (`Context(expression_execution=...)`) | `expressions.md` (*Placement*) |

### Identity across faces

- The same Python function with the same inputs has the same `tf_checksum` whether it runs through `delayed` or as a node in a Context, so the two faces share results.
- `seamless-run` builds a bash transformation whose code is the command line, mapped file names included. It is a different transformation from a Python or `Transformer("bash")` step that does the same work over values, and they do not share cache entries. This is deliberate: on the Unix face file names are load-bearing, as in Make or Snakemake; elsewhere only content is.

### Workflow face: what is not there (versus Seamless 0.x)

From the contracts (`workflow-context.md`, `cells.md`, `mounts.md`, `shares.md`, `widgets.md`):

- No macros, no library/stdlib (`map`, `switch`, `select`), no Silk validation (a cell with a validator fails with `NotImplementedError`), no IPython-language transformers.
- No sub-contexts with their own runtime (`ctx.sub = Context()` only declares a namespace); no cycles; no non-eager mode.
- Connection targets are the root of a cell or one level below it.
- Mounts: whole bound cells only (mount a cell, then connect it to a pin or to transformer code); no context-wide mounts or automatic paths; no cross-process exclusivity; no `fsync`.
- Shares: no authentication, TLS or sessions; the server listens on `0.0.0.0:5813` by default; deep celltypes are not shareable.
- Widgets are runtime objects and are not saved in the graph.
- Every edit reconciles the whole graph: build large graphs with one `set_graph()` call.
- A saved graph holds checksums only. Reloading it in another process needs persistent storage (hashserver and database, e.g. via `SEAMLESS_CACHE` plus `seamless.config.init()`).
- By default one transformation body runs per process, so independent transformers in a local `process`-mode Context run one after another; use `spawn` workers or a cluster for parallelism.
