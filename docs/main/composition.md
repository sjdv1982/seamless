# Composition

## Driver transformations

Because `delayed` functions return a `Transformation` handle, you can build *driver* transformations — functions that construct and dispatch sub-transformations as part of their own logic. Drivers are the primary way to express fan-out, conditionals, and reusable pipeline patterns.

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

### Reusable patterns

Any Python function that composes `delayed` calls is inherently a reusable template. Python's regular abstraction mechanisms — functions, classes, modules — all work as expected:

```python
def normalise_pipeline(raw_data, ref_data, params):
    """Returns a delayed transformation for the full normalisation pipeline."""
    bg = subtract_background(raw_data, ref_data)
    scaled = apply_scale(bg, params["scale"])
    return smooth(scaled, params["sigma"])  # returns a Transformation handle
```

Call `normalise_pipeline(...)` to get a handle, then `.run()` or `.start()` to execute.

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

compute.modules["my_package"] = "./my_package"
```

The module directory is checksummed and included in the transformation identity. If the source files change, the transformation checksum changes.

**Important**: the import must happen inside the function body. An import at the module level captures the current Python object from your local environment — it is not included in the transformation and is not available on the worker.

**Dynamic imports**: if your module uses dynamic imports (e.g., `importlib.import_module("utils")` inside a called function), make sure the dynamically imported modules are also included in `.modules`. Seamless cannot automatically discover dynamic import dependencies.

### Why this matters for remote execution

When transformations run locally (`execution: process` or `execution: spawn`), `.globals` and `.modules` are optional — the worker inherits your Python environment. When transformations run remotely (`execution: remote`), the worker is a clean process on a different machine that has no access to your local files. `.globals` and `.modules` ensure that every piece of code the transformation needs is bound by content and travels with the job.

Never rely on "the package is installed on the server" for code you actively develop. Installed packages drift and break identity. Use `.modules` to bind your development code by content; use conda or Docker environments (`.environment`) for third-party library dependencies.
