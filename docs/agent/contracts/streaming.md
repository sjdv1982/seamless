# Streaming (Contract)

Streaming is an opt-in operational feature for `remote: daskserver`
transformations.

The [streaming plan](../../../plans/streaming-plan.md) describes the transport,
throttle limits, and implementation phases.

Enable it per transformation:

```python
tf.streaming = True
```

The flag is read at submission time. Changing it after `.compute()`, `.run()`,
`.start()`, or `.task()` has submitted the transformation does not affect the
in-flight run.

Streaming does not change transformation identity:

- it is not written into the transformation dictionary
- it is not written into dunder fields such as `__meta__`, `__env__`, or
  `__compilation__`
- it does not change `tf_checksum`
- it does not change persistent cache identity

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
