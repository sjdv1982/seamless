# Local parallelism

Seamless provides three related mechanisms for parallel work: for Python transformations, there are worker processes and bounded batch draining of large transformation lists; for bash CLI workflows, there is a queue server .

## One transformation per process at a time

By default, the code of a transformation has its process to itself while it runs. Every process has one lock, the *process lock*, and a transformation's code runs while holding it. This protects code that changes process-wide state, such as the working directory or environment variables. It also means that the number of processes is the number of transformations that run at once:

| Execution | Transformations that run their code at once |
|---|---|
| `execution: process` (the current Python process; the default without a cluster) | 1 |
| `execution: spawn`, or `spawn(N)`, with N workers | N |

In `process` mode, twenty transformations that are started together therefore run one after the other. To run them in parallel, use a worker pool (below) or a remote backend.

Only the code itself runs one at a time. Several transformations in one process still download their inputs and upload their results at the same time.

### Opting out: `process_lock = False`

Some code is safe to run next to other code in the same process, typically because it spends its time waiting: for I/O, or for an external program. Turn the lock off for such a transformer:

```python
from seamless.transformer import delayed

@delayed
def convert(data):
    import subprocess
    # the work happens in the external program; this code only waits for it
    proc = subprocess.run(["mytool"], input=data, capture_output=True, check=True)
    return proc.stdout

convert.process_lock = False
```

For `seamless-run`, the flag is `--no-process-lock`.

Transformations with the lock off run next to each other, and next to the one transformation that holds the lock. A worker process accepts up to three transformations at once, so `spawn(N)` runs up to 3N of them. In `process` mode the lock no longer limits them at all.

The setting is not part of a transformation's checksum, so it has no effect on caching.

A transformation that launches other transformations needs no setting: it gives up the lock by itself when it launches the first one. See [Composition](composition.md).

## `execution: spawn` — local worker pool

Setting `execution: spawn` in your configuration tells Seamless to run transformations in a pool of separate worker processes rather than in the current Python process. The number of workers defaults to the number of logical CPU cores. Each worker runs the code of one transformation at a time, unless the transformation has `process_lock = False`.

In `seamless.yaml` or `seamless.profile.yaml`:

```yaml
- execution: spawn
```

Worker processes are started lazily on the first transformation and reused across calls. They communicate via shared memory and a multiprocessing IPC channel, which avoids serialization overhead for large numpy arrays.

### `spawn(N)` in Python

You can also activate the worker pool programmatically, specifying the number of workers explicitly:

```python
from seamless.transformer import spawn

spawn(4)   # start 4 worker processes

@delayed
def compute(x):
    import time
    time.sleep(1)
    return x * 2

handles = [compute(i) for i in range(20)]
for h in handles:
    h.start()                    # schedule all 20 jobs

results = [h.run() for h in handles]  # collect results (blocks until each is done)
```

`spawn()` with no argument uses the CPU count. Call `spawn()` once at the start of your script; all subsequent `delayed` calls will use the worker pool.

`has_spawned()` returns `True` if a worker pool is active:

```python
from seamless.transformer import has_spawned

if not has_spawned():
    spawn()
```

### Concurrent scheduling with `.start()`

`.start()` schedules a transformation for execution on an available worker without blocking. Use it to fan out work before collecting results:

```python
@delayed
def process(item):
    ...

handles = [process(item) for item in items]
for h in handles:
    h.start()                    # fire and forget

results = [h.run() for h in handles]  # .run() blocks until done (cache hit if already finished)
```

`.run()` on an already-started transformation returns immediately if the result is ready, or blocks until it is. `.task()` is the async/await equivalent of `.run()`, useful in async code.

### `parallel()` / `parallel_async()` for large batches

For large batches of delayed transformations, prefer `parallel()` or `parallel_async()` over manually calling `.start()` on every transformation first. These helpers keep at most `nparallel` transformations active at once.

Set the global limit in `seamless.profile.yaml`:

```yaml
- nparallel: 4
```

or in Python:

```python
import seamless.config

seamless.config.set_nparallel(4)
```

The limit travels with transformations submitted to Dask: a transformation runs with the `nparallel` of the process that submitted it, so a `parallel()` call inside a nested (driver) transformation needs no configuration of its own. Calling `set_nparallel()` inside a transformation changes the limit for the transformations it submits in turn. The value is held per worker process, which runs several transformations at once; if they were submitted with different limits, the most recently started one determines the value.

Synchronous usage:

```python
from seamless.transformer import delayed, parallel

@delayed
def process(item):
    ...

tfs = [process(item) for item in items]
for tf in parallel(tfs):
    print(tf.value)
```

Async usage:

```python
from seamless.transformer import delayed, parallel_async

@delayed
def process(item):
    ...

async def main():
    async for tf in parallel_async([process(item) for item in items]):
        print(tf.value)
```

The iterator is streaming but ordered: transformation `N` is yielded as soon as transformations `0..N` have all completed.

To attach progress reporting and error tracking, wrap the list in `TransformationList`:

```python
from seamless.transformer import TransformationList, parallel

tflist = TransformationList([process(item) for item in items], show_progress=True)
for tf in parallel(tflist):
    pass
```

`parallel()` is synchronous and must not be called from within a running event loop; use `parallel_async()` there.

---

## `seamless-queue` — parallelizing CLI workflows

For bash workflows using `seamless-run`, the equivalent of `spawn` is `seamless-queue` combined with the `--qsubmit` flag.

`seamless-queue` starts a queue server that accepts transformation jobs and executes them concurrently:

```bash
# Start a queue server with 8 concurrent workers in the background
seamless-queue --workers 8 &

# Submit jobs to the queue instead of running them inline
seamless-run --qsubmit paste data/a.txt data/b.txt
seamless-run --qsubmit paste data/c.txt data/d.txt
seamless-run --qsubmit paste data/e.txt data/f.txt
# ... all three run concurrently on the queue server

# Wait for all jobs to complete and shut down the queue
seamless-queue-finish
```

Each `seamless-run --qsubmit` invocation submits the job to the running queue server and exits immediately. `seamless-queue-finish` signals the server to drain remaining jobs, wait for them to complete, and then shut down.

### When to use `seamless-queue`

For a small, fixed number of parallel commands, plain shell backgrounding is sufficient and simpler:

```bash
seamless-run paste data/a.txt data/b.txt &
seamless-run paste data/c.txt data/d.txt &
seamless-run paste data/e.txt data/f.txt &
wait   # block until all three finish
```

Use `seamless-queue` when you want to control the degree of parallelism with `--workers`.

If jobs depend on each other's outputs, you do not need to order submissions or insert `seamless-queue-finish` between stages. Seamless writes a `.FUTURE` sidecar alongside an output file while it is being computed. When a subsequent `seamless-run` invocation encounters `result.txt.FUTURE` as a file argument, it waits (polling every 0.5 s) for the `.FUTURE` to disappear before the job is dispatched to the queue. This means all jobs can be submitted quickly; inter-job dependencies resolve themselves at runtime.

### Limiting concurrency

The `--workers N` flag controls how many jobs run concurrently. If not specified, it defaults to the number of logical CPU cores. For CPU-bound work, matching the core count avoids oversubscription. For I/O-bound or mixed work, a higher value may improve throughput.
