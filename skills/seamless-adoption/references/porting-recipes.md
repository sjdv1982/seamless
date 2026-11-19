## Porting recipes (safe defaults)

For carrying out a port step by step, use the `seamless-porting` skill. These recipes are for sketching one.

### Recipe 0: pick the face (or the mix)

- Mostly **commands and pipelines over files**: `seamless-run` (Unix face).
- Mostly **Python functions over values**: `delayed` / `direct` (Python face); R, Julia, bash and compiled steps through `Transformer(...)`.
- **Interactive or long-lived** (a notebook you keep tweaking, files you edit, a web front end, a 0.x project): a workflow `Context`.
- Mixed: make boundaries explicit. Remember that a `seamless-run` step and a Python step of the same logic do not share cache entries (`faces.md`).

### Recipe 0.5: pick the execution backend (an ops choice, not a rewrite)

`process` (default) -> `spawn` (local workers) -> `remote: jobserver` (simple daemon + worker pool) -> `remote: daskserver` (HPC). Say: "we port once; the backend is configuration." See `execution-backends.md`.

### Recipe A: wrap a pure-ish Python function

- `@direct` when the call should return a value now; `@delayed` for a handle to run, start or await later.
- Inputs as arguments; push I/O into separate steps.
- Helper code from the repo goes in through the module mechanism (`tf.modules`), never "assume it exists remotely".
- In tests, use `.run()` (raises) rather than `.compute()` (returns `None` on failure).

### Recipe B: split I/O from compute

1. Load/parse (file -> structured value).
2. Compute (structured -> structured).
3. Render/write (structured -> file or `folder`).

### Recipe C: nesting and drivers

- Pass upstream handles into downstream steps; `start()` many, then `run()` or await.
- **Fan-out**: a driver transformation (`tf.driver = True`) loops over inputs and launches one sub-transformation per element. Each has its own identity, so per-element caching and parallelism come for free; when one element changes, the others hit the cache. Return a deep celltype (`tf.celltypes.result = "deepcell"`, members wrapped as `Checksum(...)`) so the aggregate is not materialized.
- **Conditionals**: Python `if`/`else` in a driver; the unchosen branch is never built.
- **Data-dependent fan-out**: iterate a deep checksum (a `folder` or `deepcell` index) and launch one step per member, without fetching the members.
- **Reusable patterns**: a Python function that composes `delayed` calls is a template.

### Recipe D: bind code and environments by content

- Embed project modules when the transformation should commit to exact code bytes.
- Third-party dependencies: for the default in-memory Python backend, install them in the worker's own environment (a cluster queue's `conda:` entry); `tf.environment.set_conda_env(name)` only asserts that the worker is already in it. To run a step **inside** a conda environment or container, use bash (`seamless-run --conda/--docker`, `Transformer("bash")`) or a CLI backend (`tf.metavars.BACKEND = "cli"` for Python; the default for R and Julia). Image specs: `{"name": "image@sha256:...", "gpus": ..., "shm_size": ...}`.
- The environment is outside identity and a cached result is returned without checking it. If a tool version must count, make it an input (a version string or the tool binary's checksum).
- Packaging is fine only if immutable (wheel or image pinned by version and hash). No editable installs or copied working trees for remote execution.

### Recipe E: Unix command steps

- Declare which arguments are files and which are values; add extra inputs with `-i` / `-I`, identity-neutral hints with `--metavar` and `--metafile`.
- Idempotent, environment-stable scripts (pinned tools, no "latest").
- Canonicalize output when parallelism only changes order (`sort`, `LC_ALL=C`).
- A script that itself calls `seamless-run` needs no flag; a script that mostly launches other steps can be declared `--driver`.

### Recipe F: a reactive front end (workflow face)

- Put the stable pipeline steps behind transformers in a Context; keep inputs that users edit as cells.
- Mount editable inputs to files (`ctx.params.mount("params.json")`), or share them over HTTP (`ctx.params.share(readonly=False)`; no authentication, bind to localhost unless the network is trusted).
- Expose results read-only (`ctx.result.share()`), or as a download archive (`ctx.shares.add_download(["result"])`).
- Save with `ctx.get_graph()`; reload needs persistent storage (`SEAMLESS_CACHE` plus `seamless.config.init()`), because the graph holds checksums only.
