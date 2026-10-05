# seamless-transformer

`seamless-transformer` is the computation engine of the [Seamless](https://github.com/sjdv1982/seamless) framework. It takes a *transformation* — a pure-functional computation defined as a checksum-addressed dict of inputs, code, and language — and executes it, returning a result checksum. It supports Python and bash transformations, multi-process worker pools with shared-memory IPC, and integration with the Seamless caching and remote infrastructure.

## Branch notes: `jupyter-sync` (sync API inside Jupyter)

This branch lets the sync API (`func()` of a `@direct` transformer, `tf.run()`, `tf.compute()`) be used from a Jupyter cell, or from any thread whose own event loop is running. On `cells-and-expressions` (5162312) every sync entry point is refused there with "not supported within Jupyter". The branch was re-created from `cells-and-expressions`. It replaces the December 2025 attempt (91bec26, still on `origin/jupyter-sync`), which deadlocked `test_nested_transformations_multi.py`.

### Why the December attempt hung

The December attempt sent every in-process computation to one shared background event loop. Transformer bodies run on that loop's default thread pool (`loop.run_in_executor(None, run_transformation_dict, ...)`), which holds `min(32, cpu+4)` threads: 18 on a 14-core machine. A nested sync `.run()` blocks its pool thread while it waits for its children. The nested multi test needs about 40 such threads at once (10 outer, 10 middle and 20 leaf), so the pool starves and everything deadlocks.

- **Stack dump:** it shows exactly 18 threads, all waiting in a nested `run()` inside `_compute_sync`.
- **Larger pool:** the same patch passes with a 200-thread pool.
- **Still reproduces:** the hang still happens with that patch ported onto 5162312.
- **Spawn and Dask:** those variants never hit it, because they don't share the in-process pool.

### The fix (`transformation_class.py`)

- **Only the Jupyter thread changes.** `_sync_task_loop()` sends work from a thread whose own loop is running (a notebook cell, or sync code inside a coroutine) to a shared background *driver* loop. Every other thread keeps its current behaviour, where each thread gets its own loop from `get_event_loop()`. Transformer bodies run on threads without a loop, so nested calls never share a pool and can't starve it. Loops patched by nest_asyncio keep their old code path.
- **Dask.** The sync Dask path (`_try_database_cache_sync`, `_run_local_fallback_sync`) runs a private event loop on the calling thread. That fails in Jupyter with "Cannot run the event loop while another loop is running". When the caller's loop is running, `_compute_sync` now runs that path on `_COMPUTE_EXECUTOR`.
- **Waiting across loops.** A task started in a cell now lives on the driver loop, so it can't simply be awaited from the cell's loop. `_await_task_any_loop()` handles this in two places:
  - the Dask branch of `await tf.computation()`, which used to raise;
  - `await tf.cancel_async()`, which used to return before the cancellation had finished.

### Verification

- **Real Jupyter kernel** (driven by `tests/manual/jupyter-wrapper`): all of the following work, in-process and on a local Dask cluster:
  - direct calls, `.run()`, `.compute()` and dependencies;
  - `start()` followed by `.run()`;
  - nested transformations;
  - `await tf.task()` and `await tf.computation()`.
- **Spawned workers** already worked in a running loop before this branch.
- **`tests/test_sync_in_running_loop.py`** has 6 tests. They include the nested stress case that deadlocked the December attempt, and `cancel_async`. They pass on Python 3.13 and on 3.14.
- **`test_nested_transformations_multi.py`**, and **`test_nested_transformations_multi_async.py`** copied from the December branch, both pass (about 20 s each).
- **Full suite:** run one pytest process per file, every file has the same pass/fail result as 5162312. The failures that also occur on 5162312 are environmental or come from work in progress:
  - `target_celltype` errors in the expression tests;
  - `seamless_dask` missing from the base environment;
  - the service launcher rejecting conda env `base`;
  - `seamless-signature` import errors in the compiled tests.
- **In-process cancellation tests:** all pass.

### Caveats

- **Don't wake the loop in `start()`.** A task created from another thread only runs once someone waits for it, and `construct()` relies on that to stay lazy: `_run_dependencies()` calls `self.start()`, which schedules the whole computation. When a wake-up was added, `construct()` started computing eagerly and `test_is_cached` failed with an extra database query. This behaviour exists on `cells-and-expressions` too.
- **Blocking now happens inside any running loop.** Sync calls inside `asyncio.run()` scripts now block instead of raising. To keep that guard outside Jupyter, `_sync_task_loop()` could check `running_in_jupyter()`. The plain-asyncio behaviour is what allows testing without a kernel.
- **Not tested:** the jobserver remote path, and nest_asyncio.
- `tests/dask/dask_sync.jupyter.py` is a manual notebook check on Dask. Run it from `tests/dask` with `tests/manual/jupyter-wrapper`.

## Core concepts

A **transformation** in Seamless is a deterministic computation: given the same inputs and code (identified by their checksums), it always produces the same output. `seamless-transformer` is responsible for:

1. **Building** the transformation dict from the inputs and code, then computing its checksum (which serves as the transformation's identity for caching).
2. **Building** the execution namespace: resolving input buffers, compiling modules, injecting dependencies.
3. **Executing** the code — either Python (via `exec`) or bash (via subprocess with file-mapped pins).
4. **Returning** the result as a checksum, which can be cached and reused.

## Transformer construction

There are three canonical construction paths:

- `direct(function)` and `delayed(function)` create non-workflow Python Transformers;
- assigning a function to a workflow Context (`ctx.tf = function`) creates a bound Python Transformer;
- `Transformer(language="python", compiled=False, direct=False)` creates a code-less configurable builder for any scenario.

`direct` and `delayed` are Python-only and have no `language` argument. The factory accepts `"python"` or `"bash"` when `compiled=False`; when `compiled=True`, it forwards the language to the compiled implementation. Set `direct=True` for immediate call semantics.

```python
from seamless_transformer import Transformer

bash = Transformer("bash", direct=True)
bash.code = "cat input > RESULT"

c = Transformer("c", compiled=True)
c.schema = "..."
c.code = "..."
```

Python and Bash builder languages are fixed and read-only. The factory is also available as `seamless.transformer.Transformer`; `seamless.workflow` exports `Transformer`, `Context`, and `Cell` together.

## Transformer pins

`tf.pins.x` (also `tf.args.x`) returns a fresh `Pin` handle in standalone and
workflow-bound modes. An unset declared pin is an unwired Pin; undeclared names
raise `AttributeError`. Pins share `CellBase` with Cells but are not Cells, have
no projection/validator/mount API, and cannot be sources. Connect `pin.source`
when you want its upstream source.

```python
from seamless_transformer import delayed

@delayed
def echo(value):
    return value

echo.celltypes.value = "str"
echo.pins.value = "42"       # serializes now, with a retained input checksum
echo.pins.value.celltype = int
assert echo.pins.value.input_celltype == "str"
assert echo.pins.value.value == 42
assert echo().run() == 42
```

A pin's `celltype` and `tf.celltypes.x` are the same Transformer-owned setting.
Its read-only `input_celltype` follows a typed input, or records its original
serialization/declared checksum type. Retyping converts from that stored input.
Prebound and call-time Transformation/Expression inputs convert to the pin type;
the transformation identity contains the converted checksum. Pins store input
references and checksum claims, never Python literal values. Compiled builders
expose the same Pin API; the native schema still constrains accepted values.

`pin.source` reports a connection; `pin.checksum`, `.buffer`, and `.value` read
the produced value. Assigning any of those three declares the input and detaches
a source. `.set()`, `.set_buffer()`, and `.set_checksum()` check ownership.
`pin.set_checksum(cs, input_celltype="int")` declares a checksum's input type.
Invalid literals fail at assignment. A bound pin conversion failure sets
`pin.state == "failed"` and `pin.exception`; its Transformer blocks on that pin
with `blocked-by-error`, before constructing a transformation.

Null has one canonical checksum. Required plain/mixed/bytes pins accept it;
other required types reject it. Optional pins of **any type** treat null as
absence, comparing checksums and dropping the pin before conversion/decoding.
A connected optional input with no checksum still blocks. Functions may return
None for plain/mixed/bytes results; bytes null reads as `b""`. Other result types
reject None. Empty bytes also canonicalize to null, so optional bytes pins cannot
carry an empty byte string as a distinct present value.

`.value = None` stores null. `.checksum = None` and `.buffer = None` clear the
input and retain the declaration. `del tf.pins.x` removes the declaration only
for signatureless code; a fixed Python/compiled signature refuses deletion.

## Worker pool

For production use, `seamless-transformer` can spawn a pool of worker processes (`seamless_transformer.worker.spawn()`). Workers run in separate processes using the `spawn` multiprocessing context, and communicate with the parent via a custom IPC channel built on `multiprocessing.Connection` and shared memory.

- The parent distributes transformation requests to the least-loaded worker.
- Workers can delegate sub-transformations back to the parent (which redistributes them).
- Buffer data is exchanged through shared memory to avoid serialization overhead.
- Workers automatically restart on crash (segfault, etc.).

## Bounded parallel execution

In Python, for large batches of delayed transformations, use `parallel()` or `parallel_async()` instead of manually calling `.start()` and `.run()` on thousands of objects.

## Integration with the Seamless ecosystem

- **seamless-core**: provides the `Checksum`, `Buffer`, and buffer-cache primitives that `seamless-transformer` builds on.
- **seamless-dask**: optionally offloads transformations to a Dask cluster (`TransformationDaskMixin`).
- **seamless-remote**: used by the transformation cache to (a) look up cached results in the database before running, (b) access the buffer server for buffer data, and (c) submit transformations to the jobserver for remote execution (an alternative to local execution, not a cache lookup).
- **seamless-config**: supplies project/stage selection for storage routing.
- **seamless-jobserver**: depends on `seamless-transformer` to execute transformations received from the job queue.

## CLI scripts

Installing `seamless-transformer` provides:

| Command | Description |
|---------|-------------|
| `seamless-run` | The CLI face of Seamless: wrap a bash command or pipeline as a transformation, using file/directory argument names as pin names |
| `seamless-upload` | Upload input files/directories to the buffer server and write `.CHECKSUM` sidecar files, staging inputs for `seamless-run` |
| `seamless-download` | Fetch result files/directories from the buffer server using `.CHECKSUM` sidecar files produced by `seamless-run` |
| `seamless-run-transformation` | Universal transformation executor: run any Seamless transformation (Python, bash, or other) by checksum and print the result checksum |
| `seamless-queue` | Run a queue server that executes `seamless-run --qsubmit` jobs concurrently — the CLI face's parallelization mechanism beyond `&` |
| `seamless-queue-finish` | Signal the queue server to drain remaining jobs and shut down |
| `seamless-mode-bind.sh` | Shell script: source it to bind seamless-mode commands and hotkeys into the current shell session |

### `seamless-run-transformation`

`seamless-run-transformation` executes an pre-constructed transformation. It
takes a transformation checksum, resolves the transformation dict that checksum
identifies, builds a synthetic `Transformation` object from that dict, and runs
the normal `Transformation` lifecycle. 

The command prints the result checksum:

```bash
seamless-run-transformation <transformation-checksum>
```

It also accepts a checksum sidecar file:

```bash
seamless-run-transformation transformation.json.CHECKSUM
```

When the argument is a `*.CHECKSUM` file, the command automatically reads
`dunder.json` from the same directory if it exists. You can override that with
`--dunder PATH`. The dunder payload is merged into the execution envelope, while
`--scratch`, `--fingertip`, `--direct-print`, and `--strict` are passed into the
synthetic `Transformation` execution path.

There are two common producer paths.

The standalone job-directory path is produced by `seamless-run --dry-run`:

```bash
seamless-run --dry-run --upload -j X 'sleep 10.48 && echo 48'
seamless-run-transformation X/transformation.json.CHECKSUM
```

With `--upload`, `seamless-run` uploads the prepared transformation dict and
small job buffers, then writes `X/transformation.json.CHECKSUM`. If the job has
execution dunder metadata, `X/dunder.json` is written too and run-transformation will pick it
up automatically.

The alternative Python path starts from a delayed `Transformation`:

```python
import seamless
import seamless.config as seamless_config
from seamless.transformer import delayed

seamless_config.init()

@delayed
def add(a, b):
    return a + b

tf = add(19, 23)
tf.construct()

# Make the transformation identity buffer available to the run-transformation process.
tf.transformation_checksum.resolve().incref()

print(tf.transformation_checksum.hex())
seamless.close()
```

Then run-transformation that printed checksum:

```bash
seamless-run-transformation <printed-transformation-checksum>
```

For this path, the producer must keep the transformation dict and its referenced
buffers available to the run-transformation process. In practice, use the same configured
project, hashserver, or `SEAMLESS_CACHE` for both processes, and persist the
transformation identity buffer as shown above.
### Managing dependencies with `seamless-run`

The canonical ways to declare inputs and execution hints that are not positional command arguments:

| Flag | Description |
|------|-------------|
| `-i PATH` / `--input PATH` | Add a single file or directory as an explicit input (repeatable) |
| `-I FILE` / `--input-file FILE` | Read input file paths (one per line) from `FILE`; each becomes an explicit input (repeatable) |
| `--metafile FILE` | Read meta-variable definitions (`NAME=VALUE`, one per line) from `FILE` (repeatable). Same semantics as `--metavar`: variables are available as `$NAME` in the bash command but do **not** contribute to the transformation identity. Use for thread counts, verbosity, temp dirs, and other execution hints that should not invalidate the cache. |

These three flags (`-i`, `-I`, `--metafile`) are the recommended mechanism for dependency management when the wrapped command does not already surface all inputs as positional file arguments.

## Execution records

Every successful, non-probe transformation persists one execution record in `seamless.db` (the `MetaData` table), keyed by `tf_checksum`. The default body is **minimal** (timing, memory, execution mode, remote target). The full record — environment fingerprints, compilation context, validation snapshots, contract violations, freshness — is opt-in via `seamless.config.select_record(True)` (or `- record: true` in `seamless.profile.yaml`).

Capture is worker-side: timing, memory, GPU usage, and compilation-context checksums are collected wherever the transformation actually ran (process, spawn child, jobserver worker, or Dask worker). The shared assembly code lives in `seamless_transformer/record_assembly.py`; the runtime mode flag is cached process-locally and invalidated on `select_record()` calls. The hot path under `record: false` pays only timing/memory capture and one database write.

For the agent contract, see `docs/agent/contracts/execution-records.md` in the main seamless repository.

## Compiled language support

`seamless-transformer` can wrap compiled source code as Seamless transformations. The compiled source defines a `transform()` function whose signature is described by a YAML schema; `seamless-signature` generates the C header, and CFFI builds the Python extension at runtime.

Built-in languages: C, C++, Fortran, Rust. **The set is open** — additional languages can be registered at runtime with `define_compiled_language()`. To add permanent support for a new language, create a file in `seamless_transformer/languages/native/` following the pattern of `rust.py` (a single `define_compiled_language()` call with compiler name, flags, and compilation mode) and submit a pull request.

This requires the `compiled` optional-dependency group:

```bash
pip install seamless-transformer[compiled]
```

See `docs/agent/contracts/compiled-transformers.md` for the full behavioral contract.

## Installation

```bash
pip install seamless-transformer
```

### Setting up seamless-mode

After installing, `seamless-mode-bind.sh` is available on your `PATH`. Source it in your shell session to activate the `seamless-mode-on`, `seamless-mode-off`, `seamless-mode-toggle` commands and the `Ctrl-U U` hotkey.

**Manual (any environment) — add to `~/.bashrc` or `~/.zshrc`:**

```bash
source $(which seamless-mode-bind.sh)
```

**Conda — auto-activate with the environment:**

```bash
cp $(which seamless-mode-bind.sh) $CONDA_PREFIX/etc/conda/activate.d/
```

**venv / virtualenv — append to the environment's activate script:**

```bash
echo "source $(which seamless-mode-bind.sh)" >> $VIRTUAL_ENV/bin/activate
```

**virtualenvwrapper — add to the environment's postactivate hook:**

```bash
echo "source $(which seamless-mode-bind.sh)" >> $VIRTUAL_ENV/bin/postactivate
```
