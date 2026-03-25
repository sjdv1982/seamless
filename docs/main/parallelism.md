# Local parallelism

Seamless provides two independent mechanisms for local parallelism: worker processes for Python transformations, and a queue server for bash CLI workflows.

## `execution: spawn` — local worker pool

Setting `execution: spawn` in your configuration tells Seamless to run transformations in a pool of separate worker processes rather than in the current Python process. The number of workers defaults to the number of logical CPU cores.

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
