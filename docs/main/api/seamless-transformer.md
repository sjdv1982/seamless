# seamless-transformer

`seamless-transformer` is the computation engine of the [Seamless](https://github.com/sjdv1982/seamless) framework. It takes a *transformation* — a pure-functional computation defined as a checksum-addressed dict of inputs, code, and language — and executes it, returning a result checksum. It supports Python and bash transformations, multi-process worker pools with shared-memory IPC, and integration with the Seamless caching and remote infrastructure.

## Bounded parallel execution

For large batches of delayed transformations, use `parallel()` or `parallel_async()` instead of manually calling `.start()` and `.run()` on thousands of objects.

The concurrency limit is configured globally via `nparallel` in `seamless.profile.yaml` (or with `seamless.config.set_nparallel()` / `seamless_config.set_nparallel()`):

```yaml
- nparallel: 4
```

```python
from seamless.transformer import delayed, parallel
import seamless.config

seamless.config.set_nparallel(4)

@delayed
def add(a, b):
    return a + b

tfs = [add(i, i) for i in range(20)]
for tf in parallel(tfs):
    print(tf.value)
```

`parallel()` is a synchronous iterator. It yields completed transformations in input order, but streams them as soon as the prefix is ready: transformation `N` is yielded as soon as `0..N` have all finished.

In async code, use `parallel_async()`:

```python
from seamless.transformer import delayed, parallel_async

@delayed
def add(a, b):
    return a + b

async def main():
    async for tf in parallel_async([add(i, i) for i in range(20)]):
        print(tf.value)
```

For progress reporting and error tracking, wrap the list in `TransformationList`:

```python
from seamless.transformer import TransformationList, parallel

tflist = TransformationList([add(i, i) for i in range(20)], show_progress=True)
for tf in parallel(tflist):
    pass

print(tflist._finished, tflist._errors)
```

`parallel()` cannot be called from inside a running event loop; use `parallel_async()` there.

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
