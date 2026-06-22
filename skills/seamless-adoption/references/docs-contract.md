## Porting without Seamless source code

This skill is designed so an agent can start porting code to Seamless **without** reading Seamless’s implementation or tests.
Assume official Seamless documentation exists at least at the level of docstrings (API contracts).

Local agent docs (this checkout):
- `docs/agent/README.md`
- `docs/agent/index.json`
Notable contract pages:
- `docs/agent/contracts/direct-delayed-and-transformation.md`
- `docs/agent/contracts/seamless-run-and-argtyping.md`
- `docs/agent/contracts/execution-backends.md`
- `docs/agent/contracts/content-addressed-files-and-dirs.md`
- `docs/agent/contracts/cache-storage-and-limits.md`

### How to use docs/docstrings (recommended workflow)

Before proposing a port, confirm the contracts of the primitives you will rely on:
- Read the docstrings for the exact symbols you will use (e.g. `direct`, `delayed`, `Transformation.run`, `Transformation.start`, module inclusion APIs).
- If a detail affects determinism/caching/remote execution, don’t guess: ask the user or consult docs.

### Minimal contracts to confirm (checklist)

**Identity / caching**
- What defines a transformation’s identity (code, inputs, metadata, environment, module definitions)?
- Whether caches are local-only, shared, or remote-backed; how to force recomputation/audit.
- What “scratch” means (what is retained, what can be recomputed, what can be fingertipped).

**Execution model**
- `direct`: does it compute+materialize immediately? error surface in async/Jupyter?
- `delayed`: what object is returned (Transformation handle), and what do `.run()`, `.compute()`, `.start()`, `.task()` mean?
- Concurrency semantics: in-process vs worker pool vs remote; how nested transformations behave.
- If “remote” is in scope: what the supported remote targets are (e.g. `jobserver` vs `daskserver`), how they are selected, and what operational constraints each imposes.

**Inputs and celltypes**
- How inputs are serialized and when they are materialized (resolved) before execution.
- How to pass a **checksum identifier** as an input (so code can resolve/materialize it itself), versus passing the resolved value.
  - This is important for “content-addressed I/O is not a side effect” patterns.

**Modules and closures**
- How to include helper modules/package code in a transformation (“bind code by content”).
- What parts of Python state are captured automatically (closures usually are not) and what must be made explicit.

**Remote execution safety**
- What is required for remote workers to execute (environment, dependencies).
- The supported “content-bound” patterns (embedding modules vs immutable artifacts); avoid ad-hoc copying.

### What to ask the user (if docs don’t answer)

If the user’s project is real (not a toy), ask for:
- Target execution backends (local only vs remote/workers), and constraints (no Docker? pinned conda?).
- Whether bitwise reproducibility is required or whether they will provide a witness+comparison step.
- Whether large artifacts are allowed to be non-fingertippable (scratch) and what witness outputs must remain available.

### Guardrail

If the contract is unclear, default to:
- conservative, local execution,
- explicit inputs/config (no closures),
- content-bound helper code inclusion,
- non-scratched witness outputs.
