# Wrapping Python and bash

## Wrapping Python with `direct` and `delayed`

```python
from seamless.transformer import direct, delayed
```

`direct` wraps a Python function so that calling it behaves normally — arguments in, value out — but behind the scenes, Seamless checksums the function's code and inputs, executes the function, checksums the result, and caches the mapping. If you call the same function with the same inputs again, the cached result is returned without re-execution.

```python
from seamless.transformer import direct

@direct
def add(a, b):
    import time
    time.sleep(2)  # just to make execution slow
    return a + b

result = add(2, 3)     # runs the function, returns 5
result = add(2, 3)     # cache hit, returns 5 immediately
```

`delayed` wraps a function the same way, but calling it returns a `Transformation` handle instead of executing immediately. This lets you control when and how execution happens:

```python
from seamless.transformer import delayed

@delayed
def add(a, b):
    return a + b

tf = add(2, 3)          # returns a Transformation handle, does not execute
tf.start()              # start execution in the background
checksum = tf.compute() # execute and return the result's checksum (its identity)
value = tf.run()        # execute (or use cache) and return the materialized value
```

The handle also supports `.task()` for async/await integration.

When the same `delayed` function is called with the same arguments, the resulting transformation has the same checksum — the same identity. This is the foundation of Seamless's caching: identity is determined by content, not by when or where the computation runs.

### In-process caching

The examples above work without any infrastructure. With no configuration, Seamless runs transformations in the current Python process and caches results in memory for the duration of the session. Calling the same `direct` function twice with the same arguments will hit the cache on the second call — useful for exploration and verifying that your functions behave as expected.

This in-process cache is lost when the process exits. For persistent caching across sessions, see [Setting up persistent caching](#setting-up-persistent-caching) below.

---

### Python pitfalls

Seamless executes transformation code in a sandboxed namespace. Only the explicitly declared inputs and code are available inside the transformation — outer-scope names are not. This is by design: it is how Seamless detects missing dependencies (the function errors) rather than silently caching incorrect results.

#### Import closure

Imports that happen *outside* the function body are not part of the transformation and are not available in the sandbox. Referencing an outer-scope import will raise a `NameError` at execution time:

```python
import numpy as np  # outer import — not visible in the sandbox

@direct
def process(data):
    return np.mean(data)  # NameError: np is not defined
```

Always import inside the function body:

```python
@direct
def process(data):
    import numpy as np  # inside the function = available in the sandbox
    return np.mean(data)
```

#### Function closure

A helper function defined outside the wrapped function is not available in the sandbox. Calling it will raise a `NameError`:

```python
def normalize(x):
    return x / x.max()

@direct
def process(data):
    return normalize(data)  # NameError: normalize is not defined
```

Inject helper functions via `.globals` so they are bound into the transformation and available in the sandbox:

```python
def normalize(x):
    return x / x.max()

@direct
def process(data):
    return normalize(data)  # OK: normalize is injected as a declared global

process.globals.normalize = normalize
```

For larger collections of helpers — a whole module or package — use `.modules` instead. See [Composition](composition.md) for the full `.globals` and `.modules` documentation.

#### Implicit random seed

Non-deterministic functions are a silent correctness issue: two executions with the same declared inputs produce different results, so the cached result depends on when the computation first ran. A colleague or a remote worker re-running the same transformation will get a different result — which Seamless will flag as a reproducibility failure. Declare the seed as an explicit input instead:

```python
@direct
def sample(n, seed):
    import random
    random.seed(seed)
    return [random.random() for _ in range(n)]
```

---

## Wrapping bash with `seamless-run`

`seamless-run` is the command-line face of Seamless. It wraps a bash command as a transformation, with file arguments automatically detected as inputs, and stdout plus any declared output files captured as results.

### Basic usage

```bash
export SEAMLESS_CACHE=~/.seamless/cache     # global persistent caching

seamless-run 'seq 1 10 | tac && sleep 5'    # runs, caches result
seamless-run 'seq 1 10 | tac && sleep 5'    # cache hit — instant
```

Seamless infers which arguments are files (arguments with a file extension that exist on disk), checksums them, runs the command, and caches the result. The next time you run the same command with the same inputs, the cached result is returned instantly without re-executing.

Wrapping bash requires a persistent cache. For Python, it is optional: without it, the cache lasts as long as the Python session. `SEAMLESS_CACHE` is a quick way to set up a global persistent cache. For finer control, [Setting up a local cluster](cluster.md). For more, details, see [Caching, identity, and sharing](caching.md).

### Declaring inputs and outputs

Beyond the automatic inference from command arguments, you can explicitly declare additional inputs and outputs:

```bash
# Additional input file not in the command arguments
seamless-run mycommand --input config.json

# Capture an output file produced by the command
seamless-run mycommand --capture output.csv
# Capture with renaming (server-side name : local name)
seamless-run mycommand --capture result.dat:local-result.dat

# Capture stdout to a file
seamless-run mycommand --capture :log.txt

# Inject a variable input (becomes part of the transformation identity)
seamless-run mycommand --var seed=42
```

For how caching works in detail, see [Caching, identity, and sharing](caching.md).

### Environment and execution control

`seamless-run` accepts flags that control where and how the transformation runs:

```bash
# Specify a conda environment for the command
seamless-run --conda myenv mycommand input.txt

# Select project and stage (controls storage namespace)
seamless-run --project myproject --stage prod mycommand input.txt
```

---

### Bash pitfalls

#### Missing file dependencies

If your command reads files that are not declared as arguments (and therefore not automatically detected), Seamless won't track those files as inputs. A change to such a file won't trigger re-execution. Use `--input` to declare additional inputs explicitly:

```bash
# config.json is read by mycommand but not in the argument list

seamless-run mycommand data.txt --input config.json
```

#### Non-deterministic output ordering

Many Unix tools return output in non-deterministic order (e.g., `grep` over multiple files, `find`, directory listings). This means two runs that produce the same logical result can have different checksums, causing unnecessary re-execution and broken caching. Pipe through `sort` where order doesn't matter:

```bash
seamless-run bash -c "ls *.txt | sort > file_list.txt" --capture file_list.txt
```

More generally, any command whose output is sensitive to ordering, timing, or process IDs should be made deterministic before wrapping with Seamless.

#### Multi-command pipelines

`seamless-run` only analyses the *first* command in a compound expression for input files. So while this works:

```bash
seamless-run paste data/a.txt data/b.txt
```

this does not automatically detect `data/a.txt` and `data/b.txt` as inputs:

```bash
seamless-run 'echo START; paste data/a.txt data/b.txt'  # input files not detected
```

Fix it with `--primary N` to nominate which command to analyse (1-based), or with `-i`/`--input` to declare the input files explicitly:

```bash
seamless-run --primary 2 'echo START; paste data/a.txt data/b.txt'
# or
seamless-run 'echo START; paste data/a.txt data/b.txt' -i data/a.txt -i data/b.txt
```
