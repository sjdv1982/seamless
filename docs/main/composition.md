# Composition

## Driver transformations

Because `delayed` functions return a `Transformation` handle, you can build *driver* transformations — functions that construct and dispatch sub-transformations as part of their own logic. Drivers are the primary way to express fan-out and conditionals.

### Fan-out

A driver that loops over a collection and spawns one sub-transformation per element:

```python
from seamless.transformer import delayed

@delayed
def process_one(item, config):
    return item * config["scale"]

@delayed
def process_all(items, config):
    results = []
    for item in items:
        tf = process_one(item, config)
        tf.start()              # schedule for concurrent execution
        results.append(tf)
    return [tf.run() for tf in results]  # collect results

process_all.globals.process_one = process_one  # ESSENTIAL: To embed the sub-transformation's source code
```

Each `process_one` transformation has its own cache key (`item` + `config` + code). If `items` changes partially, only the affected sub-transformations re-execute — the rest are cache hits. The fan-out scales automatically with the number of elements.

The driver's result (the list returned by `process_all`) is itself cached. If neither `items` nor `config` changes, the entire pipeline — driver plus all sub-transformations — is a cache hit.

**Return type note**: when a driver returns a large collection of checksums rather than materialized values, consider using the `checksum` cell type for the return value to avoid materializing large aggregates. See `.celltypes` in the [seamless-transformer reference](api/seamless-transformer.md).

### Conditionals

Conditionals are plain Python `if`/`else` in a driver. Unchosen branches are never instantiated and never execute:

```python
@delayed
def pipeline(data, use_fast_path):
    if use_fast_path:
        return fast_process(data).run()
    else:
        return slow_process(data).run()
```

Because the driver itself is a cached transformation, changing `use_fast_path` from `True` to `False` (with the same `data`) produces a new driver transformation checksum and re-executes the driver. The slow path runs; the fast path never runs. On the next call with `use_fast_path=True`, the driver is a cache hit and the fast-path result is returned immediately.

### Nesting needs no declaration

A transformation that launches other transformations is written like any other. Nothing has to be declared.

By default, the code of a transformation runs while holding the lock of its process, so that one transformation runs at a time per process (see [Local parallelism](parallelism.md)). A driver that kept this lock while it waits would block its own sub-transformations. It does not keep it. The first time its code launches a transformation, the driver gives the lock up, and it does not take it again. A launch is `.start()`, `.run()`, `.compute()`, `.task()`, a call of a `direct` function, or `parallel()`. In the fan-out example above, `process_all` holds the lock until its first `tf.start()`. From then on, the `process_one` transformations can run in the driver's process as well.

Two things follow:

- What the driver does before its first launch, it does with its process to itself. What it does afterwards, such as combining the results, it does next to other transformations.
- The launch must come from the driver's own thread, or from a coroutine of its event loop. If the driver starts a thread of its own and launches from there, the lock stays held, and the pipeline can hang without an error. Give such a driver `process_lock = False`, or declare it as a driver (below).

### Declaring a driver: `.driver = True`

```python
process_all.driver = True
```

This says that the code mainly launches other transformations and waits for them. The declaration adds two things:

- **The driver never takes the lock.** It starts at once, even while another transformation runs in its process, and it holds nothing up while it prepares its first launch. Setting `.driver = True` also sets `.process_lock` to `False`.
- **On a Dask cluster, its launches are not held back.** Seamless limits how fast a transformation that runs on the cluster can submit further transformations, so that the cluster does not fill up with parents that wait for their children. Launches made by a declared driver skip this limit.

The declaration applies to the driver alone. The transformations that it launches are ordinary transformations with their own settings.

Declare a driver when its own work is negligible. A driver that does substantial work before its first launch is better left undeclared, so that this work has the process to itself.

For a `seamless-run` command that itself calls `seamless-run`, the flag is `--driver`. The flag is needed only when the inner command runs over `ssh` or inside a container. Otherwise the outer command gives up its lock by itself.

---

## Module inclusion

When a transformation runs on a remote worker, it has no access to your local filesystem or Python environment. Code that is defined in modules you've written — helper functions, data classes, utilities — must be explicitly bound into the transformation.

### `.globals` — inject helper functions and values

`.globals` is a dict of values that are injected into the transformation's execution namespace. Use it for helper functions defined in your script, or small configuration objects:

```python
def my_helper(x):
    return x * 2

@delayed
def compute(data):
    return my_helper(data)  # my_helper is referenced but not defined

compute.globals["my_helper"] = my_helper
```

Globals are serialized by their source code (for functions) or value (for other objects). If `my_helper` changes, the transformation checksum changes and re-execution is triggered.

### `.modules` — include Python packages

`.modules` is for including entire Python packages or multi-file modules. Each entry specifies a module name and a directory path; Seamless packages the directory's source files into the transformation so they are available on the worker:

```python
import my_package  # a local package in ./my_package/

@delayed
def compute(data):
    from my_package import process
    return process(data)

compute.modules["my_package"] = my_package
```

The my_package source files are checksummed and included in the transformation identity. If the source files change, the transformation checksum changes.

### Local vs remote execution

Seamless always executes transformation code in a sandboxed namespace — outer-scope names are never available regardless of whether the worker is local or remote. `.globals` and `.modules` are therefore always required for any helper or value defined outside the function body.

With local execution (`execution: process` or `execution: spawn`), the worker happens to be on the same machine, so file paths you reference inside the transformation will resolve. But doing so creates an implicit dependency that Seamless cannot track: the file is not part of the transformation identity, so changes to it won't trigger re-execution and results may be silently stale. Always declare file dependencies explicitly rather than reading local paths inside a transformation.

For remote workers, third-party library dependencies must be declared explicitly via conda or Docker environments (`.environment`); the remote machine has no access to your local Python installation or filesystem.
