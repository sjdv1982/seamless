## Seamless primitives (agent cheat sheet)

This file is meant to help an agent *port/refactor* code to use Seamless effectively, not just explain it.

### Core mental model

- A Seamless “step” is a **transformation**: (code identity + explicit inputs) → output.
- Caching/memoization is valid when the step is **referentially transparent** with respect to its declared inputs.
- If a computation is sensitive to the environment, treat that as a *falsifiable* concern (`env-null-hypothesis.md`), and preserve a small non-scratched witness for comparison.

### `direct` vs `delayed` (Python)

- Use `direct` when you want the call-site to behave like a normal function call that returns a value.
- Use `delayed` when you want a handle you can:
  - `.run()` later (sync),
  - `.task()` / `await` later (async),
  - `.start()` to schedule many tasks and then collect results.

Porting rule of thumb:

- Start with `delayed` for pipelines; optionally layer `direct` for convenience at the edges.

#### Minimal code that actually runs (shape-level example)

```python
from seamless.transformer import direct, delayed

@direct
def add(a, b):
    return a + b

@delayed
def add_later(a, b):
    return a + b

assert add(1, 2) == 3              # immediate value

tf = add_later(1, 2)               # Transformation handle
cs = tf.compute()                  # checksum (identity of result)
val = tf.run()                     # materialized value
```

Practical note for agents: Seamless can make the second call faster when the identity matches and the result is already cached.

### Dependency wiring (nesting/composition)

- Treat upstream results as explicit dependencies by passing them into downstream steps. Note that the mechanism is different for Python or for CLI tools (which may be written in Python).
- Avoid “hidden” dependencies through globals, working directory, environment variables, or ad-hoc files.
- Prefer **content-addressed I/O**: it’s fine for a step to “read arbitrarily” *if* what it reads is identified by an explicit checksum input (materialization), not by an ambient path/URL (“whatever is there”).

### Inputs, defaults, and closures

Closures are a portability trap: captured values are *implicit inputs*.

Porting patterns:

- Make captured values explicit arguments (including config) so they become part of the step identity.
- If a value is a small constant/config blob, inject it explicitly (e.g. via a globals mechanism) rather than relying on outer scope.
- Avoid using time, randomness, PIDs, hostnames, and other ambient sources unless explicitly parameterized and recorded.

### Imports and helper modules (project code)

Goal: ensure the executed code is **bound by content**, not “whatever is on disk remotely”.

Good options:

- **Embed helper modules** into the transformation/module mechanism when you want “code is data” determinism.
- **Or install immutable artifacts** (wheel/image) pinned by version+hash (avoid editable installs and copying a working tree).

Practical cautions for embedding:

- Embedding often captures *what is currently imported/loaded*; dynamic imports and package data may not be included automatically.
- If you embed a package, ensure the required submodules are imported so the embedded module definition is complete.
- Keep an eye on payload size and update cadence (large embedded code artifacts can be operationally heavy even if deterministic).

### Compiled/system deps (NumPy/BLAS/GPU)

- Don’t assume they “don’t matter”; treat them as part of the environment envelope.
- If determinism matters: pin versions/backends and record the env signature for later audits.
- If you accept “optimistic null”: keep cache keys env-agnostic but store env signature as provenance and provide an audit path that forces recomputation.

### Dask execution (HPC/distributed)

If Seamless’s Dask integration is available/configured:

- treat Dask as an execution backend, not as a competing “workflow vs compute” framework.
- prefer `delayed` pipelines so many tasks can be scheduled efficiently.
- ask/confirm cluster constraints (networking, environments, packaging) instead of assuming “it will just work”.

### Scratch vs witness outputs

- Scratch is for bulky intermediates that you can recompute.
- Do **not** scratch the meaning-bearing witness outputs needed for cross-run / cross-environment checks.
- If a fingertip/materialization fails, recompute the witness and compare (byte-identical best case; otherwise user-defined interpretation).

### Unix/bash pipelines (`seamless-run` style)

Seamless can also wrap Unix-y steps.

Porting patterns:

- Make inputs/outputs explicit (files vs literal values).
- Canonicalize outputs when parallelism only changes ordering (e.g. sort records) so meaning becomes stable bytes.
- Control locale-dependent behavior for classic tools (e.g. sort order): set/record `LC_ALL` and similar knobs.

#### Minimal CLI example (mental model)

```bash
# Runs a command as a transformation; inputs/outputs are tracked by identity.
seamless-run paste data/a.txt data/b.txt
```

### What not to suggest (remote)

- Don’t propose “scp the repo/module to the server” or “assume the remote has your checkout”.
- Prefer content-bound embedding or immutable artifacts; see `remote-donts.md`.
