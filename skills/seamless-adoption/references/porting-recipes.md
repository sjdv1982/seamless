## Porting recipes (safe defaults)

### Recipe 0: Pick the right entry point (Python vs CLI vs hybrid)

Don’t assume Python-first.

- If the workflow is mainly **commands/pipelines over files**: start with `seamless-run` (CLI face).
- If the workflow is mainly **Python functions/values**: start with `@delayed` / `@direct` (Python face).
- If it’s mixed: make boundaries explicit (files vs values) and use both.

### Recipe 0.5: Pick the execution backend (ops choice, not a rewrite)

If the user cares about parallelism/HPC/remote execution, name the backend explicitly:
- `spawn` for local worker processes.
- `remote: jobserver` for the simple “remote-like” mode (daemon + worker pool; great for dev/test).
- `remote: daskserver` for Dask-backed scaling (HPC/distributed).

Then say the key reassurance: “We can port the pipeline once; backend choice is configuration/operations.” See `references/execution-backends.md`.

### Recipe A: Wrap a pure-ish Python function

Goal: keep call-site feeling normal.

- Use `@direct` for “call returns a value now”.
- Use `@delayed` for “call returns a handle; run/start later”.
- Make inputs explicit (arguments), and push I/O to separate steps where possible.
- If a function depends on helper code in the repo, include it via the module mechanism rather than “assuming it exists remotely”.

### Recipe B: Split I/O from compute

Goal: make step identity stable and caching effective.

- Step 1: load/parse inputs (file → structured value).
- Step 2: compute (structured → structured).
- Step 3: render/write outputs (structured → file/folder).

### Recipe C: Nesting and dependency wiring

Goal: define a pipeline as a composition of steps.

- Upstream transformations can be passed into downstream steps; treat them as explicit dependencies.
- Use `delayed(...).start()` when you want to schedule work, then `.run()` later.

#### Driver transformations (fan-out / map / conditional patterns)

The transformation cache is keyed by *content identity*, not by name or position.
This means nested transformations give you per-element caching automatically — no special machinery needed.

**Fan-out / map pattern**:

- Write a "driver" transformation that loops over inputs and spawns one sub-transformation per element.
- The driver itself is cheap — it just creates sub-transformations, not materializing large data.
- Each sub-transformation has its own checksum identity → independent caching and parallelism.
- When one input element changes, the driver re-runs, but unchanged sub-transformations hit cache.
- The driver's output should use a **deep celltype** to avoid materializing all results into a single large buffer.

**Conditional pattern**:

- A driver transformation that uses Python `if`/`else` to choose which sub-transformation to create.
- The unchosen branch is never instantiated — naturally lazy, no wasted computation.

**Reusable patterns**:

- A Python function that composes `delayed` calls *is* a reusable template.
- Python's own abstraction mechanisms (functions, classes, modules) are all you need.

### Recipe D: Module inclusion (avoid “copy this module”)

Goal: make helper code available in execution environments safely.

- Default to **content-bound code**:
  - **Embed your project modules** when you want the transformation to commit to exact code bytes (Seamless-style determinism). This can be reasonable even for large pure-Python modules.
  - For non-Python/compiled deps, prefer **pinned environments** (conda/image) and avoid “whatever is installed”.
- Packaging is fine *only if immutable*: install a wheel/sdist/image identified by a version+hash (not editable installs, not copying a mutable working tree).
- Avoid closure state or dynamically imported local files that won’t exist on workers unless they are explicitly included as module/code artifacts.

### Recipe E: Unix command steps

Goal: preserve Unix philosophy.

- Wrap commands/pipelines as explicit steps that declare which args are files vs values.
- Ensure scripts are idempotent and environment-stable (pin tools, avoid “latest”).
- Prefer output canonicalization (e.g. sort) when parallelism only changes ordering, so meaning becomes stable bytes.
