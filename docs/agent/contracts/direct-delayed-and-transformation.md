# `direct` / `delayed` / `Transformation` (Contract)

This page defines the minimum semantics an agent may rely on when porting code.

## One page of “how it behaves” (practical)

This is the smallest reliable example shape:

```python
from seamless.transformer import direct, delayed

@direct
def f(a, b):
    return 10 * a + 2 * b

@delayed
def g(a, b):
    return 10 * a + 2 * b

v = f(30, 12)          # returns a value now
tf = g(30, 12)         # returns a Transformation handle
cs = tf.compute()      # computes and returns a checksum identifier
v2 = tf.run()          # resolves checksum into the value
```

If you call the same transformer again with the same explicit inputs, Seamless may reuse cached results (when available) rather than recomputing.

## `direct`

- Treat `direct(f)` as “call returns the value now”.
- `direct` is for ergonomic call-sites and small steps where immediate evaluation is desirable.
- If called from an environment that forbids blocking (common in notebooks/event loops), prefer the async APIs of `Transformation` instead.

## `delayed`

- Treat `delayed(f)` as “call returns a `Transformation` handle”.
- `delayed` is the default for pipelines: you can build a graph of handles and decide when/how to run them.

## `Transformation` handle

Assume these meanings (confirm with docs/docstrings for exact behavior):
- `.compute()`: execute and return an identifier (checksum) for the result.
- `.run()`: execute and return the resolved/materialized value.
- `.start()`: schedule computation (useful when starting many tasks before collecting results).
- `.task()` / `await`: async execution; preferred in Jupyter/async contexts.

## Optional Dask backend

If Seamless’s Dask integration is available/configured:
- a `Transformation` may delegate execution/scheduling to Dask (distributed task graph execution)
- this improves HPC/distributed throughput without changing the “step identity” mental model

An agent should check docs for how Dask is configured/enabled and what requirements exist for worker environments.

## Composition

- Passing one `Transformation` as an input to another wires an explicit dependency.
- Avoid implicit dependencies via globals/closures unless explicitly injected and content-bound.

## Minimal examples

Prefer examples that don’t touch time/RNG/threads so caching and referential transparency are obvious.
