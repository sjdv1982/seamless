---
name: seamless-porting
description: Use when creating, porting, upgrading, or debugging Seamless 1.5 pipelines; porting Python, bash, R, Julia or compiled code, an existing Snakemake/Nextflow/script pipeline, or a legacy Seamless 0.x context; upgrading Seamless 1.4 code (direct_print, global_lock, tf.x pin sugar, CompiledTransformer, deepfolder directories, .SEAMLESS.yaml); choosing between the Python face (direct/delayed/Transformer), the Unix face (seamless-run) and the workflow face (reactive Context with mounts, shares, widgets); selecting the active concern in a staged, non-linear port; checking Seamless contract compliance; activating persistent caching, local-cluster remote execution, conda/container environments, drivers and the process lock; or optimizing parallelism, incremental recomputation and dataflow.
license: MIT
---

# Seamless Porting

Treat Seamless pipeline work as a staged, non-linear progression. Seamless wrapping syntax is small, but a minor syntactic change can have large semantic and operational effects. Agents mispredict Seamless behaviour when they change wrapping, wiring, capability activation, execution placement and optimization at the same time.

This skill routes attention. Consider one active concern at a time, but do not treat it as an edit boundary: a change often touches step code, wrapper syntax, wiring, data movement, cache policy, backend configuration and granularity at once. The active concern decides why an edit is made, what evidence counts, and which exit check must pass.

The contract pages in `seamless/docs/agent/contracts/` are authoritative. The human docs in `seamless/docs/main/` lag the 1.5 code; do not port from them where a contract exists.

## Operating model

Before nontrivial edits, state or infer:

- Active concern:
- Why this concern:
- Touched surfaces:
- Exit check:

Concern selection priority: (1) user-named concern; (2) symptom-implied concern; (3) failed prerequisite of the selected concern; (4) earliest unfinished concern.

Default stage order: 1. DAG design and face choice; 2. plain step behaviour; 3. minimal wrapping; 4. Seamless contract; 5. scaling and realism; 6. capability activation; 7. optimization.

Move on when the exit check passes, when the user changes focus, or when a failure proves another concern is active.

## Required returns

- Return to **contract** after any semantic change to wrapper syntax, wiring, data movement, cache policy, materialization, backend, parallelization, granularity or environment.
- Return to **scaling and realism**, then contract, after any significant move toward real inputs, real environments or restored production steps.
- If optimization fails because result semantics are unclear, return to DAG design or plain step behaviour. If remote differs from local, return to contract first.

## Hard rules

- Do not start with Seamless syntax. Design or recover the DAG and step boundaries first.
- Pick the face per part of the pipeline deliberately (stage 1). Never generalize a property of one face to Seamless as a whole.
- Do not add remote execution, parallelization, incremental computation or optimization before a small wrapped pipeline passes contract checks.
- Do not fix a failed small pipeline by adding wiring until the plain step and the individual wrapper have both been smoke-tested.
- Do not pass Python class instances across Seamless boundaries. Use JSON-like values, NumPy arrays, buffers, files or checksums. Do not let HDF5, `.npz` or pickle cross a step boundary unless accepted as opaque blobs.
- For large data, decide explicitly between value, checksum and handle wiring.
- Name the backend when execution placement matters: `process`, `spawn`, `remote: jobserver`, `remote: daskserver`.
- Use 1.5 API names only: `tf.pins.x` (never `tf.x`), `tf.streaming` / `--streaming` (never `direct_print`), `process_lock` / `driver` (never `global_lock`), `Transformer(lang, compiled=True)` (never `CompiledTransformer`), `-i` / `-I` / `--metafile` (never `.SEAMLESS.yaml`). Upgrading 1.4 code: `references/upgrading-from-1.4.md`.
- Failure delivery: `.compute()` and reads return `None` on failure; check `.exception`. Smoke tests must use `.run()` (or a `direct` call), which raise, or assert that `.exception` is `None`.
- A transformation that mainly launches other transformations is a driver: set `tf.driver = True` / `seamless-run --driver`.
- If scratch plus fingertip is used, enable input fingertipping on every consumer that may receive a missing scratch input (`allow_input_fingertip = True` on the downstream Python transformer before building; `--fingertip` for a CLI transformation checksum). Scratch on the producer is not enough, and a non-scratch consumer pin publishes the result anyway.
- For substantive ports, implement persistent caching and local-cluster remote execution by default after the small wrapped pipeline passes contract checks, unless out of scope or blocked by missing cluster configuration.
- End with a capability report (below).

## Contract references

Load the relevant contract before changing the associated semantics (paths under `seamless/docs/agent/contracts/`):

- Identity and caching: `identity-and-caching.md`. Python wrappers and Transformation handles: `direct-delayed-and-transformation.md`. Transformer factory, `build()`, `process_lock`/`driver`: `transformers.md`. Pins, optional pins, null: `pins.md`.
- Unix face: `seamless-run-and-argtyping.md`.
- Workflow face: `workflow-context.md`, `node-state-lifecycle.md`, `cells.md`, `expressions.md`, `mounts.md`, `shares.md`, `widgets.md`, `attachments.md`. Agent guide: `seamless/docs/agent/guides/seamless-web-server.md`.
- Data: `celltypes-and-conversion.md`, `deep-celltypes.md`, `content-addressed-files-and-dirs.md`, `hashtype.md`, `compression.md`.
- Languages and environments: `handler-languages.md` (R, Julia), `language-backends.md` (`BACKEND = "cli"`/`"mem"`), `compiled-transformers.md`, `compiled-pins.md`, `seamless-signature-schema.md`, `environments.md`, `modules-and-closures.md`.
- Execution: `execution-backends.md`, `cancellation.md`, `transformation-logs.md`, `streaming.md`.
- Storage and audit: `scratch-witness-audit.md`, `cache-storage-and-limits.md`, `execution-records.md`, `service-management.md`.

## 1. DAG design and face choice

Entry triggers: new port, unclear structure, de novo pipeline; implicit, notebook-shaped or side-effect-heavy code; optimization or contract work fails because step meaning is unclear.

Start without Seamless syntax. For a de novo pipeline, design an abstract DAG of referentially transparent steps with I/O at the boundaries. For existing step code, check purity first, then wiring. For an implicit pipeline, isolate the steps and rewire them explicitly. For an explicit pipeline (Snakemake, Nextflow), check that steps do not grossly violate purity, then move on. Effects (uploads, notifications, deletions) stay outside Seamless.

Then choose the face for each part:

- **Unix face** (`seamless-run`): CLI tools over files. File names are part of identity.
- **Python face** (`direct`/`delayed`, `Transformer(...)`): functions over values; drivers and fan-out loops; R, Julia, bash, compiled steps via the factory.
- **Workflow face** (`Context`): interactive or long-lived use (edited inputs, file sync, widgets, HTTP front end), and every port of a Seamless 0.x project. See `references/workflow-face-porting.md`; for 0.x, `references/legacy-0x-to-1.5.md`; for building and debugging Contexts, the `seamless-workflow` skill.

Exit check: each step has explicit inputs and outputs; hidden dependencies and side effects are removed, parameterized or recorded as risks; each part has a face.

## 2. Plain step behaviour

Entry triggers: a step is wrong before Seamless is involved; its plain behaviour is untested; a wrapper failure may be an ordinary Python, bash, tool or environment failure.

Make each step concrete and smoke-tested as plain Python, bash, R or Julia. Prefer function-shaped Python steps and command-shaped bash steps with explicit file, stdin, stdout and environment boundaries.

Exit check: the unwrapped step passes a small smoke test with representative input.

## 3. Minimal wrapping

Entry triggers: plain behaviour passes; the first wrapper attempt fails; Seamless syntax is in use without a small wrapped proof.

Wrap individual steps in the simplest form first: `direct` for a Python step, `seamless-run` for a command, `Transformer("r", direct=True)` (pins declared through `tf.pins`) for R or Julia. Reuse the plain smoke tests.

Then wire a small linear pipeline of 2 to 5 wrapped steps with the simplest wiring: concrete values (Python), files (Unix), or cells connected by assignment (workflow: `ctx.tf.pins.x = ctx.x`, `ctx.y = ctx.tf.result`, then `ctx.compute()` and check `.state` and `.exception`). Prefer `delayed` handles once the goal is an explicit Python graph.

If it fails, revisit plain behaviour and individual wrapping before blaming the wiring. Known traps: class instances as inputs; a `bytes` pin arrives as `bytes`; a required pin of a celltype other than `plain`, `mixed`, `bytes` refuses null; a 64-hex string in a deep result is a value unless wrapped in `Checksum(...)`; in a Context, a code string assigned to a name is a cell value, not code.

Exit check: one wrapped step and one small wrapped pipeline pass smoke tests.

## 4. Seamless contract

Entry triggers: unexpected cache hit, miss or reuse; same apparent inputs, different results; local and remote disagree; hidden files, imports, closures, working directory, environment variables, RNG, network or class instances are suspected; wrapper, wiring, backend, materialization, cache policy, parallelization, granularity or environment changed.

Assess compliance by relating the code to the exact semantics of the wrappers in use; if in doubt, run tests. Check at least:

- Inputs and outputs are explicit; no hidden filesystem, network, global, working-directory or environment dependency.
- Boundary values use supported, canonical formats.
- Large data is not accidentally materialized.
- Code identity, modules, closures, compiled schemas and command environments match the wrapper contract. The environment is outside identity: if a tool version must count, make it an input.
- Repeated runs give the same result, or nondeterminism is seeded. A cache hit proves nothing: test determinism with the cache cleared or by recomputing.
- Cache identity matches the chosen granularity and wiring. A `seamless-run` step and a Python step never share cache entries.

Exit check: the contract has been checked against the wrappers in use and the small pipeline still passes.

## 5. Scaling and realism

Entry triggers: the small example works and the next step is real data, real tools, real environments or restored steps; a failure appears only at size or in the real environment.

Move gradually toward real usage; re-evaluate DAG, contract, capabilities and optimization after each significant step.

Exit check: the next more realistic case passes, or the failure is traced to an earlier concern.

## 6. Capability activation

Entry triggers: the user asks for persistent caching, remote or HPC execution, environments, parallelism, incremental computation, interactivity or observability; a small pipeline passes and the next goal needs a capability.

Defaults for substantive ports:

1. **Persistent caching.** Mandatory on the Unix face (`SEAMLESS_CACHE` or a cluster). In Python and in a Context, call `seamless.config.init()` after setting it up; without it, results and saved workflow graphs do not survive the process.
2. **Local-cluster remote execution.** `remote: jobserver` or `remote: daskserver` on a configured local or nearby service.

Keep local-cluster remote distinct from HPC remote (scheduler-managed `remote: daskserver` or `--write-remote-job`); do not configure HPC unless asked or already configured.

Other capabilities, when they serve the goal (details in `references/languages-and-environments.md`):

- **Environments**: bash steps and CLI backends run inside conda envs or images (`seamless-run --conda/--docker`, `tf.environment`); the in-memory Python backend cannot.
- **Concurrency**: one body per process by default; `spawn` workers or a cluster for parallelism; `process_lock = False` only for code that is safe next to other code.
- **Observability**: `.logs` after a run; `streaming` for live output (Dask only).
- **Interactivity** (workflow face): mounts, shares, widgets (`seamless-workflow` skill).
- **Execution records**: minimal by default; `record: true` only for environment-drift debugging, audits or a shared `seamless.db`.

For remote or backend failures, switch to the `seamless-remote-debugging` skill.

Exit check: the capability works on the small pipeline and the contract has been rechecked.

## 7. Optimization

Entry triggers: performance, data movement, cache pressure, large intermediates, parallelism, incremental recomputation.

Ask first: are edges values, checksums, handles, files or deep checksums? Which outputs carry meaning and must stay materializable? Which bulky intermediates can be scratch, and which consumers then need input fingertipping? Is granularity right for both caching and placement? Which backend is active?

Then consider explicitly:

1. Scratch plus fingertip, for cache pressure and data colocalization (fingertipping inside a worker currently works only with `process` and `remote: daskserver`).
2. Wiring by value, checksum or handle; materialize large data only where needed. Selections and conversions (Expressions, cell joins) already run where the data is.
3. Parallel execution: `delayed` handles with `start()`, `spawn`, `parallel`, `seamless-queue`; in a Context, independent nodes run concurrently up to the backend's capacity.
4. Granularity, including nesting (a driver launching sub-transformations; heterogeneous nesting such as `seamless-run` wrapping a Python script that launches transformations). In a Context, `ctx.prune()` reclaims superseded runs early.

Exit check: the optimization is justified by observed or expected behaviour, and the contract still holds.

## Capability report

End every porting or debugging task with: implemented capabilities (what is actually active: wrapping per face, persistent caching, local-cluster remote, parallelism, environments, scratch/fingertip, incremental computation, HPC, mounts/shares/widgets); relevant follow-ups with a reason or blocker; and why any default capability was not implemented.

## Reference map

- `references/upgrading-from-1.4.md`: 1.4 to 1.5 breaking changes with the replacement for each.
- `references/legacy-0x-to-1.5.md`: porting a Seamless 0.x context; API mapping and what is absent.
- `references/workflow-face-porting.md`: porting a pipeline or notebook into a `Context`.
- `references/languages-and-environments.md`: R, Julia, compiled, backends, conda and containers, process lock.
