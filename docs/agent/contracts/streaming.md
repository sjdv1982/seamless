# Streaming (Contract)

Streaming is an opt-in operational feature for `remote: daskserver`
transformations.

The [streaming plan](../../../plans/streaming-plan.md) describes the transport,
throttle limits, and implementation phases.

Enable it on a Transformation, or on the Transformer that builds it:

```python
t = f(1, 2)          # f is a delayed Transformer, t a Transformation
t.streaming = True   # this Transformation only

f.streaming = True   # every Transformation that f builds from now on
```

Both flags default to `False`.

**A Transformer's flag is the starting value for the Transformations it
builds.** `build()` copies the Transformer's current flag onto the new
Transformation. So does every operation layered on `build()`: calling the
Transformer, and its `.compute()`, `.computation()`, `.run()` and `.task()`
([Transformers](transformers.md), *Building a Transformation*). Changing the
Transformer's flag afterwards affects later builds only. A built
Transformation keeps its own flag, which stays assignable.

A direct Transformer builds and runs in one call, so the Transformer's flag is
the only way to stream a direct call:

```python
@direct
def g(n): ...

g.streaming = True
g(10)                # the Transformation behind this call has streaming on
```

The Transformation's flag is read at submission time. Changing it after
`.compute()`, `.run()`, `.start()`, or `.task()` has submitted the
transformation does not affect the in-flight run.

Every Transformer has the flag: ordinary and compiled, delayed and direct,
standalone and bound. `direct(f)` and `delayed(f)` copy it to the clone.

**A bound Transformer's flag belongs to its workflow Context node.** Every
view of `ctx.tf` reads and writes the one value. Binding a standalone
Transformer carries its flag into the node. `ctx.tf.build()` copies the flag
onto the detached Transformation, as a standalone build does.

The Context reads the node's flag each time it submits a run for the node.

**Assigning the node's flag never re-runs the node.** It applies from the
node's next run. A Context submits a run as soon as a node's inputs are
complete, so set the flag before completing the inputs:

```python
ctx.tf = f
ctx.tf.streaming = True   # before the pins: the first run streams
ctx.tf.pins.a = 1
```

Assigned after the last input, the flag is stored, but the run already in
flight does not stream. Neither does a node that is already complete.

The node's flag is not part of the durable graph. `ctx.get_graph()` does not
contain it, and a graph loaded with `ctx.set_graph()` starts with streaming
off on every node.

Streaming does not change transformation identity:

- it is not written into the transformation dictionary
- it is not written into dunder fields such as `__meta__`, `__env__`, or
  `__compilation__`
- it does not change `tf_checksum`
- it does not change persistent cache identity

The same holds for the Transformer's flag, standalone or bound. It is not part
of the Transformer's `meta`, and a Transformer builds the same `tf_checksum`
with the flag on or off.

Cached runs do not stream. If a daskserver worker can return the result from
the database cache, the transformation completes immediately and emits no
stdout/stderr chunks. Use the existing scratch/rerun controls when a fresh
execution is required.

Current scope:

- captured: Python `sys.stdout` and `sys.stderr` writes from the child
  transformation process
- backend: `remote: daskserver` only
- not captured yet: compiled-language subprocess stdout/stderr that bypasses
  Python `sys.stdout` / `sys.stderr`

Text is delivered through Dask's structured events: the worker calls
`Worker.log_event`, and the submitting client uses `Client.subscribe_topic`.
Stdout and stderr remain separate, with a stable transformation prefix on
local output. Streaming does not propagate automatically to nested
transformations; each child transformation has its own flag.

Streaming buffers are bounded and keep recent text when output exceeds the
chunk limit. Defaults are 8192 bytes per chunk and a 2-second interval per
stream. Truncation removes text from the head and includes a visible dropped
byte count. The child drains pending stream output on completion and restores
its previous stdout/stderr. Streaming failures retain the existing full
stdout/stderr exception trailers.

Scheduler throttle updates use the public Dask control path:
`Scheduler.log_event` → async `Client.subscribe_topic` handler → `Client.run`
on workers. Worker state updates push throttle notifications into active
Seamless child processes. Address-specific limits can tighten global limits.
This relay requires a connected client; workers keep their last applied
limits if clients disconnect. The child-process `Endpoint` notification
channel is separate from this Dask transport.

A distributed client shares one throttle relay across its Seamless wrappers.
Late clients read the latest retained control event after subscribing, and
joining workers receive the scheduler's current state. Duplicate or older
control revisions are ignored on the worker. Adaptive updates are best-effort
with retries; a failed relay does not stop transformation execution.

With streaming enabled, terminal progress bars created through `tqdm`,
`tqdm.std`, and `tqdm.auto` use the same event channel. The client renders
separate local bars for nested progress bars, including bars without a known
total. The child suppresses its terminal bar output so progress is not also
duplicated as captured stderr. Ordinary stdout/stderr continues to stream.
The client clears and redraws active terminal bars around streamed text,
including bars from parallel transformations.

Progress updates coalesce to the latest state at the configured cadence and
share the streaming throttle limits. Completion sends the final count and
closes each bar. Topic cleanup also closes bars left open by interruption.
The child restores patched tqdm aliases and its import hook on normal return
or exception. The patch is active only during a streaming request.

The client does not require tqdm: when it is unavailable, progress falls back
to text counts. `tqdm.notebook`, other progress libraries, and compiled-language
subprocess output remain outside the current scope. Progress streaming does
not change the transformation checksum, cache behavior, or supported backend.
