# seamless-transformer

`seamless-transformer` is the computation engine of the [Seamless](https://github.com/sjdv1982/seamless) framework. It takes a *transformation* — a pure-functional computation defined as a checksum-addressed dict of inputs, code, and language — and executes it, returning a result checksum. It supports Python and bash transformations, multi-process worker pools with shared-memory IPC, and integration with the Seamless caching and remote infrastructure.

## Core concepts

A **transformation** in Seamless is a deterministic computation: given the same inputs and code (identified by their checksums), it always produces the same output. `seamless-transformer` is responsible for:

1. **Building** the transformation dict from the inputs and code, then computing its checksum (which serves as the transformation's identity for caching).
2. **Building** the execution namespace: resolving input buffers, compiling modules, injecting dependencies.
3. **Executing** the code — either Python (via `exec`) or bash (via subprocess with file-mapped pins).
4. **Returning** the result as a checksum, which can be cached and reused.

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
