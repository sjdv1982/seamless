## Seamless primitives (agent cheat sheet)

For porting and refactoring, not just explaining. Contracts in `docs/agent/contracts/` are authoritative.

### Core mental model

- A step is a **transformation**: (code identity + explicit inputs) -> result. Identity is the `tf_checksum`; the result is a checksum too.
- Reuse is valid when the step is referentially transparent with respect to its declared inputs.
- Environment sensitivity is a falsifiable concern (`env-null-hypothesis.md`); keep a small non-scratched witness.
- Between steps, **Expressions** select part of a value and/or convert its celltype (project, then convert, at most one conversion). They run no user code and are cached like transformations.

### Python face: `direct`, `delayed`, `Transformer`

```python
from seamless.transformer import direct, delayed

@direct
def add(a, b):
    return a + b

@delayed
def add_later(a, b):
    return a + b

assert add(1, 2) == 3        # runs now; a failure raises

tf = add_later(1, 2)         # Transformation handle
cs = tf.compute()            # result checksum, or None on failure (see tf.exception)
val = tf.run()               # value; raises on failure
log = tf.logs                # captured stdout/stderr + execution time; None after a cache hit
```

- `tf.start()` schedules, `tf.task()` / `await tf.computation()` for async. Start many, collect later.
- Other languages go through the factory: `Transformer("bash")`, `Transformer("r")`, `Transformer("julia")`, `Transformer("c", compiled=True)`. Their pins are declared, not read from a signature:

```python
from seamless.transformer import Transformer

tf = Transformer("bash", direct=True)
tf.code = "cat input > RESULT"
tf.pins.input = "hi"         # declares pin "input" and sets it
tf()                         # "hi\n"
```

- Pins are reached only as `tf.pins.x` (the 1.4 shortcuts `tf.x` / `tf["x"]` are gone); per-pin celltypes as `tf.celltypes.x`; the result celltype as `tf.celltypes.result`.
- Python signature defaults become optional pins (`tf.optional_pins`); none for bash, R, Julia or compiled code.
- Settings outside identity: `tf.process_lock`, `tf.driver`, `tf.streaming`, `tf.metavars.BACKEND` (`"mem"` default for Python, `"cli"` for R/Julia), `tf.environment.set_conda_env(...)` / `set_docker({"name": ...})` / `set_which([...])`, `tf.scratch`.

Porting rule of thumb: start with `delayed` for pipelines, use `direct` at the edges.

### Standalone Cells and Expressions (Python face)

```python
from seamless import Cell

c = Cell("plain")
c.value = {"a": [1, 2, 3]}
c["a"][1].value              # 2: a projection, evaluated when read
c.as_celltype("text").value  # a conversion
```

A standalone Cell has nothing running in the background: reads pull. Inside a running event loop (Jupyter), a read that would need remote evaluation returns `None` and leaves the Cell `waiting`. `cell.build()` freezes it into an immutable `Expression`. Contracts: `cells.md`, `expressions.md`.

### Workflow face: Context

```python
from seamless.workflow import Context

def double(x):
    return x * 2

ctx = Context()
ctx.x = 21
ctx.tf = double                 # a callable becomes a transformer
ctx.tf.pins.x = ctx.x           # connecting is assignment
ctx.y = ctx.tf.result
ctx.compute()                   # barrier: wait until nothing is waiting/computing
ctx.y.value, ctx.tf.state       # 42, "complete"
```

Reads never wait; `compute()` is the barrier; seven node states with block reasons explain stuck nodes. Use the `seamless-workflow` skill for detail.

### Failure delivery (Cells, Pins, Transformers, Transformations)

Reads (`.value`, `.checksum`, `.buffer`) and `.compute()` return `None` for a failure and keep the error on `.exception`; `.run()` raises (and a `direct` call is a `run()`). A result that exists but cannot be fetched (`CacheMissError`) raises on every read. `Expression.compute()` / `.run()` raise. Contract: `cells.md` (*Failures*).

### Dependency wiring

- Pass upstream results (handles, checksums, values) into downstream steps. Mechanisms differ per face: Python passes handles; the Unix face passes files; a Context connects by assignment.
- No hidden dependencies through globals, working directory, environment variables or ad-hoc files.
- Content-addressed I/O is fine: reading a buffer whose checksum is an explicit input is materialization, not a side effect.

### Drivers and nesting

A transformation may launch transformations while it runs. Declare it (`tf.driver = True`; `seamless-run --driver`) when it mainly launches and waits; a non-driver body gives up the process lock at its first nested submission anyway. Return a deep celltype (`tf.celltypes.result = "deepcell"`, members as `Checksum` objects) so the aggregate is not materialized. Note: a 64-character hex string in a deep result is a value, not a checksum; wrap real checksums in `Checksum(...)`.

### Inputs, defaults and closures

Closures are implicit inputs. Make captured values explicit arguments; inject constants explicitly (`tf.globals`); avoid time, randomness, PIDs and hostnames unless parameterized.

### Helper modules (project code)

Bind code by content: embed helper modules (`tf.modules`, contract `modules-and-closures.md`) or install immutable artifacts pinned by version and hash. Embedding captures what is imported; make sure submodules are loaded. The Python CLI backend (`BACKEND = "cli"`) supports no modules or globals.

### Compiled and system dependencies

Treat NumPy/BLAS/GPU stacks as part of the environment. If determinism matters, pin them and record the environment; otherwise accept the optimistic null and keep an audit path. Real environments are now enforceable for bash and CLI backends (`tf.environment`, `seamless-run --conda/--docker`).

### Scratch versus witness outputs

Scratch is for bulky intermediates you can recompute; each consumer that may receive a missing scratch input needs input fingertipping enabled (`allow_input_fingertip = True` in Python, `--fingertip` for a CLI transformation checksum). Never scratch a witness. A non-scratch consumer pin that holds a scratch producer's result publishes it anyway.

### Unix pipelines (`seamless-run`)

```bash
seamless-run paste data/a.txt data/b.txt          # files are inputs by content
seamless-run --conda myenv samtools view -c in.bam # runs inside the conda env "myenv"
```

Make inputs explicit (files versus literal values; `-i`, `-I`, `--var`, `--metavar` for non-identity hints, `--metafile` for non-identity files). Canonicalize outputs when parallelism only changes order. Set `LC_ALL`. Directory arguments and result targets are `folder` (materialized directories).

### What not to suggest (remote)

No "scp the repo to the server". Embed code by content or install immutable artifacts; see `remote-donts.md`.
