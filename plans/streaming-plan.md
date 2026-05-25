# Streaming Plan: live stdout/stderr (and later tqdm) for daskserver transformations

This plan adds live streaming of stdout/stderr from a remote transformation that
is being executed via `remote: daskserver` back to the client process that
submitted it. The mechanism is **opt-in per transformation** via a new
`Transformation.streaming` bool attribute and is **daskserver-only** (it does
not apply to `process`, `spawn`, or `remote: jobserver`).

Two phases:

- **Phase 1**: streaming of stdout/stderr text chunks
- **Phase 2**: streaming of tqdm progress bars, piggy-backed on phase 1

The streaming flag is processed at the Dask submission level. It **does not**
become part of the transformation checksum, the `transformation_dict`, or any
of the persistent dunder fields (`__meta__`, `__env__`, `__compilation__`, ...).
That means two transformations that differ only in `.streaming` resolve to the
same `tf_checksum`, hit the same cache entries, and produce the same execution
records. `.streaming` only changes *how* the daskserver sub-system is asked to
report progress while the transformation is running.

## Glossary

- **client process** — the user's Python process where `Transformation` lives.
- **Dask scheduler** — central distributed.Scheduler process.
- **Dask worker** — distributed.Worker process; runs `_run_base` and hosts the
  Seamless worker pool (`SeamlessWorkerPlugin`).
- **child process** — the Seamless transformer child that actually executes the
  user code (spawned by `seamless_transformer.worker._WorkerManager`).
- **owner_dask_key** — the deterministic Dask task key of a transformation's
  `base` future; already passed end-to-end ([client.py:1067-1080](seamless-dask/seamless_dask/client.py#L1067-L1080), [worker.py:626-674](seamless-transformer/seamless_transformer/worker.py#L626-L674)). Used as the
  streaming topic key.

## Choice of Dask transport: structured events (`log_event` / `subscribe_topic`)

Dask exposes a built-in event ledger that fits this use case exactly:

- `distributed.get_worker().log_event(topic, msg)` (or `Scheduler.log_event` /
  `Client.log_event`) — push a msgpack-serializable event to the scheduler.
- `Client.subscribe_topic(topic, handler)` — receive every event on a topic in
  the client process, asynchronously.
- `Client.unsubscribe_topic(topic)` — stop.

Each event is a single scheduler RPC. The Dask scheduler is single-threaded;
its budget is on the order of a few thousand small messages per second total,
shared with normal task accounting. We therefore size streaming defaults to
stay well below that ceiling even with many concurrent streaming transformations.

Alternatives considered and rejected:

- **distributed.Pub/Sub**: also works, but the topic ledger has cleaner
  subscribe semantics and is the path the Dask team recommends for
  diagnostics-style channels.
- **Reusing the Seamless `process.channel`**: that channel only spans
  child↔Dask-worker. It cannot reach the client without an extra Dask hop, so
  events still flow through Dask in the end. We use the channel for
  child→Dask-worker only, then `log_event` for Dask-worker→scheduler→client.

## Defaults (server side)

Targets are conservative and chosen to keep scheduler load negligible even at
moderate scale. The user-stated caps ("payloads >8–10 KB are irrelevant for
streaming; frequencies >0.5 msg/s are irrelevant") are the ceiling.

| parameter | default | notes |
|---|---|---|
| `max_payload_bytes` (per chunk) | **8192** | hard upper bound 10 240; truncate excess from the **head** of the buffer (keep the most recent text) |
| `min_interval_seconds` (per stream, per transformation) | **2.0** | i.e. ≤ 0.5 messages/s/stream/transformation |
| `max_chunks_per_second_per_worker` | **4** | soft cap enforced by the worker-side flusher across all concurrent transformations on that Dask worker |
| `max_chunks_per_second_aggregate` | **50** | scheduler-side threshold; above this the scheduler asks workers to back off |

Rationale: with 50 msg/s aggregate at 8 KB each that is ~400 KB/s through the
scheduler. That is well within what a single-threaded scheduler can handle
without measurable impact on task scheduling. The 2-second per-stream cadence
matches typical human-perceivable progress and matches the user's stated
ceiling of 0.5 Hz being the practical maximum useful frequency.

Override knobs (env vars, read once at Dask worker / client startup):

- `SEAMLESS_STREAM_MAX_PAYLOAD_BYTES`
- `SEAMLESS_STREAM_MIN_INTERVAL_SECONDS`
- `SEAMLESS_STREAM_AGGREGATE_THROTTLE_RATE`

These exist mainly for tests and emergency knob-turning; defaults should be
fine in production.

# Phase 1 — stdout/stderr streaming

## 1.1 Client API

### 1.1.1 New attribute on `Transformation`

In [seamless-transformer/seamless_transformer/transformation_class.py](seamless-transformer/seamless_transformer/transformation_class.py):

```python
# in __init__
self._streaming: bool = False

@property
def streaming(self) -> bool:
    return self._streaming

@streaming.setter
def streaming(self, value: bool) -> None:
    self._streaming = bool(value)
```

`.streaming` is read at submission time only. Changing it after `.run()` /
`.task()` has been called has no effect on the in-flight job.

### 1.1.2 Plumb through to `TransformationSubmission`

In [seamless-dask/seamless_dask/types.py](seamless-dask/seamless_dask/types.py) add `streaming: bool = False`
to `TransformationSubmission`.

In [seamless-dask/seamless_dask/transformation_mixin.py](seamless-dask/seamless_dask/transformation_mixin.py) `_build_dask_submission`,
pass `streaming=getattr(self, "_streaming", False)`.

In [seamless-dask/seamless_dask/client.py](seamless-dask/seamless_dask/client.py) `submit_transformation`, copy
`submission.streaming` into the `payload` dict under key `"streaming"`. The
field is **not** placed in `transformation_dict` and **not** placed in
`tf_dunder`, so it has no impact on `tf_get_buffer` / `tf_checksum` / dunder
identity.

### 1.1.3 Cache-bypass for streaming runs

A streaming run that hits the database cache returns immediately with the
cached result and produces **no** stream output. That is the desired behavior:
streaming is only meaningful for an actual fresh execution.

If the user explicitly wants the cache to be ignored while streaming, they
already have `Transformation.scratch` and the existing rerun semantics; no new
knob is needed.

## 1.2 Submission-side: client subscribes to scheduler topic

In `SeamlessDaskClient.submit_transformation`, when `payload["streaming"]` is
true:

1. Compute the topic name: `topic = f"seamless-stream-{base_key}"`. (`base_key`
   is already the deterministic and unique-per-submission Dask key — for driver
   submissions it is already disambiguated by `_resolve_driver_key`, so two
   concurrent streaming runs of the same transformation have distinct topics.)
2. Register a per-submission stream handler with
   `self._client.subscribe_topic(topic, handler)`. The handler is a small
   callable that takes one event `(timestamp, msg)` and forwards `msg["text"]`
   to local `sys.stdout` or `sys.stderr` (depending on `msg["stream"]`).
3. Attach a done-callback to `base_future` that calls
   `self._client.unsubscribe_topic(topic)` and flushes any final buffered text.
4. Store the topic on `TransformationFutures` so
   `release_transformation_futures` can also unsubscribe defensively.

`subscribe_topic` is idempotent for the same `(topic, handler)` per Dask
client; we still guard with a `set[str]` of active topics to make double-submit
safe.

The handler prints with a stable per-transformation prefix
`f"[{base_key[:12]}] "` so users can disambiguate parallel streams. If the
client process is interactive (tty) we keep ANSI colors off by default; an
env knob `SEAMLESS_STREAM_COLOR=1` enables a per-stream color.

## 1.3 Dask worker side: forward child notifications to scheduler

In [seamless-dask/seamless_dask/client.py](seamless-dask/seamless_dask/client.py) `_run_base`:

- Extract `streaming = bool(payload.get("streaming", False))`.
- Pass `streaming=streaming` into `transformer_worker.dispatch_to_workers(...)`.
- No log_event calls happen here directly; the Dask-worker-side glue lives in
  `_WorkerManager` (see below). `_run_base` only forwards the flag.

In [seamless-transformer/seamless_transformer/worker.py](seamless-transformer/seamless_transformer/worker.py):

- `dispatch_to_workers` and `_WorkerManager.run_transformation_async` /
  `run_transformation_sync` / `_dispatch` each take a new `streaming: bool`
  keyword.
- In `_dispatch`, `payload["streaming"] = streaming` so the child knows it has
  to emit stream chunks.
- Before sending the `execute_transformation` request, `_dispatch` registers a
  per-call handler for incoming **`stream_chunk` notifications** on the
  child channel keyed by `owner_dask_key`. The handler:
  1. Looks up the current throttle parameters
     (`max_payload_bytes`, `min_interval_seconds`) from a module-level
     `_STREAM_THROTTLE` cell (updated by the scheduler-driven subscriber, see
     §1.5).
  2. Truncates `msg["text"]` from the **head** to at most `max_payload_bytes`,
     recording `truncated_head_bytes` so the client can show a marker.
  3. Calls `distributed.get_worker().log_event(topic, msg)` where
     `topic = f"seamless-stream-{owner_dask_key}"`.
  Logging happens on the Dask worker's loop thread; `log_event` is non-blocking
  from the caller's perspective.
- On dispatch finalize (success, retry, or error), unregister the handler.

## 1.4 Child process side: tap stdout/stderr and emit chunks

The child today wraps `sys.stdout` / `sys.stderr` with `TextIOWrapper`s only
on the exception path; it does not emit anything mid-run
([worker.py:561-619](seamless-transformer/seamless_transformer/worker.py#L561-L619)). We extend that.

### 1.4.1 Extend the child channel with one-way notifications

[seamless-transformer/seamless_transformer/process/channel.py](seamless-transformer/seamless_transformer/process/channel.py) currently
supports request/response only. Add a third message kind `"event"`:

```python
# Endpoint
def add_event_handler(self, op: str, handler: Callable[[Any], Any]) -> None: ...

async def notify(self, op: str, payload: Any) -> None:
    """Fire-and-forget; no reply expected."""
    message = {"kind": "event", "op": op, "payload": payload}
    await self._send(message)
```

`_handle_message` adds a branch for `kind == "event"`: it looks up the
registered handler and runs it without sending a response, ignoring missing
handlers (we don't want a noisy log when the parent has torn down its handler
between submit and finalize).

### 1.4.2 Streaming-aware stdout/stderr wrapper

In [seamless-transformer/seamless_transformer/worker.py](seamless-transformer/seamless_transformer/worker.py) (new module
`stream_capture.py` so the diff stays small):

```python
class _StreamingTap(io.TextIOBase):
    """Captures writes for the buffer used in the exception path
    AND forwards chunks to the parent via channel.notify()."""

    def __init__(self, *, stream_name: str, sink: io.BufferedIOBase,
                 notifier: Callable[[dict], None],
                 max_payload: int, min_interval: float):
        ...

    def write(self, s: str) -> int:
        # append to local buffer (for exception path),
        # also append to a bounded streaming deque keeping at most
        # max_payload * 4 bytes; schedule a flush.
        ...

    def _maybe_flush(self) -> None:
        # called from a background timer thread; if min_interval has passed
        # since last flush and there is pending content, build a chunk:
        #
        # 1. take all pending bytes
        # 2. if len > max_payload: drop the head (keep last max_payload),
        #    set truncated_head_bytes = dropped
        # 3. call notifier({"stream": stream_name, "text": text,
        #                   "truncated_head_bytes": dropped, "seq": ...,
        #                   "ts": time.time()})
```

`_execute_transformation_request` keeps its current contract (capture full
text for the exception path) but, when `payload.get("streaming")`, also wires
the `notifier` to `channel.notify("stream_chunk", msg)` via a closure over
the child channel.

A single background flusher thread (one per child process, started lazily on
first streaming transformation) ticks every `min(min_interval/2, 0.5)` seconds
and asks each active tap whether to flush. Flushes are coalesced per stream.

On exception or normal return:

1. Force a final flush of both stdout and stderr so the last lines are not
   stranded in the in-process buffer.
2. Detach taps and restore the previous `sys.stdout` / `sys.stderr`.

### 1.4.3 Throttle updates pushed *into* the child

The parent (`_WorkerManager`) may receive a throttle change from the scheduler
mid-run (see §1.5). It pushes the new params to the child via
`channel.notify("stream_throttle", {"max_payload": ..., "min_interval": ...})`.
The child has a handler that updates the active `_StreamingTap` instances in
place. This avoids polling.

The initial throttle params are carried in the
`execute_transformation` payload (`payload["stream_throttle"] = {...}`) so they
take effect from the first byte. (NB: the *aggregate* throttle is approximated
at startup using the worker's count of concurrent streaming transformations;
the scheduler's broadcast is what fine-tunes once the system warms up.)

## 1.5 Scheduler-side throttle controller

A new `SeamlessStreamThrottlePlugin(SchedulerPlugin)` registered alongside
`SeamlessWorkerPlugin` (or as a separate `dask_client.register_plugin(...)`
call from `SeamlessDaskClient.__init__`). Implementation lives in
`seamless-dask/seamless_dask/stream_throttle.py`.

Responsibilities:

1. **Observe rate.** On a 1-second periodic callback (asyncio task on the
   scheduler's loop), look at `scheduler.events` for any topic starting with
   `"seamless-stream-"` over the last sliding 5-second window, computing:
   - global aggregate events/sec
   - per-worker events/sec (using `scheduler.events`' implicit per-event
     `_worker` field that `log_event` from a Worker stamps automatically)
2. **Decide throttle.** Compare against thresholds:
   - If `aggregate < target` (50 msg/s): use defaults
     (`max_payload=8192`, `min_interval=2.0`).
   - Else escalate in steps, halving `max_payload` (floor 1024) and doubling
     `min_interval` (ceiling 30 s) until projected aggregate ≤ target.
   - Per-worker hot-spot: any worker individually above
     `4 msg/s` for >5 s gets a stricter param set targeted at it.
3. **Broadcast.** When the chosen params change, publish a
   `"seamless-stream-throttle"` event with payload
   `{"max_payload": ..., "min_interval": ..., "per_worker": {worker_addr: {...}}}`.
4. **Hysteresis.** Don't shrink throttle parameters more than once every
   3 seconds; don't relax (loosen) more than once every 10 seconds. Don't emit
   a throttle event if nothing changed.

Each Dask worker (via `SeamlessWorkerPlugin`) subscribes to
`"seamless-stream-throttle"` and updates module-level
`_STREAM_THROTTLE = {"max_payload": ..., "min_interval": ...}`.
`_WorkerManager._dispatch` reads from this cell when forwarding a chunk and
forwards in-band to the child via `stream_throttle` notifications when it
changes.

The scheduler-side rate counter ignores `tqdm` chunks vs. text chunks; from
its perspective each event has equal cost. Phase 2 messages flow through the
same topic and counter without changes.

## 1.6 Edge cases & guarantees

- **No streaming for cached results.** If the no-deps cache path hits in
  `_compute_with_dask`, return as today — no submission, no topic, no chunks.
- **Streaming for nested transformations.** Each Transformation has its own
  `_streaming` flag. Parent streaming does *not* propagate to children
  automatically. (We could add `.streaming_recursive` later; YAGNI for v1.)
- **Worker restarts mid-run.** If the Dask worker that holds the base task
  dies, Dask retries (`retries=3`). The new attempt re-subscribes its handler;
  the client's `subscribe_topic` is per-client and survives. Late chunks from
  the dead worker simply don't arrive.
- **Driver tasks** (`is_driver`): driver tasks already get unique base keys,
  so each driver-mode submission gets its own topic without collisions.
- **Stream output as part of the exception payload still works**: we keep the
  in-process buffer too. If the transformation fails, the appended
  `"* Standard output / error"` block still appears in `result` exactly as
  today. The streamed-then-failed text is what the client already received.
- **Client process exits before transformation finishes.** Topic events sit in
  `scheduler.events` and are discarded when their TTL elapses; no resource
  leak. The done-callback that calls `unsubscribe_topic` is best-effort.

## 1.7 Files to add or modify (phase 1)

- modify: [seamless-transformer/seamless_transformer/transformation_class.py](seamless-transformer/seamless_transformer/transformation_class.py)
  — add `streaming` attribute and property.
- modify: [seamless-transformer/seamless_transformer/worker.py](seamless-transformer/seamless_transformer/worker.py)
  — extend `_execute_transformation_request`, `_dispatch`,
  `run_transformation_async`/`_sync`, `dispatch_to_workers` to thread the
  `streaming` flag and the per-call stream handlers.
- modify: [seamless-transformer/seamless_transformer/process/channel.py](seamless-transformer/seamless_transformer/process/channel.py)
  — add `kind: "event"` (one-way) message support and
  `add_event_handler` / `notify` methods on `Endpoint` (mirrored on
  `ChildChannel`).
- add: `seamless-transformer/seamless_transformer/stream_capture.py`
  — `_StreamingTap` + lazy background flusher thread.
- modify: [seamless-dask/seamless_dask/types.py](seamless-dask/seamless_dask/types.py) — `streaming` field on
  `TransformationSubmission`.
- modify: [seamless-dask/seamless_dask/transformation_mixin.py](seamless-dask/seamless_dask/transformation_mixin.py) —
  set `streaming` on submission.
- modify: [seamless-dask/seamless_dask/client.py](seamless-dask/seamless_dask/client.py) — copy
  `streaming` into `_run_base` payload; in `submit_transformation`,
  subscribe/unsubscribe the topic; in `_run_base`, pass `streaming` into
  `dispatch_to_workers`.
- modify: [seamless-dask/seamless_dask/worker_setup.py](seamless-dask/seamless_dask/worker_setup.py) — register
  the throttle subscriber on each Dask worker.
- add: `seamless-dask/seamless_dask/stream_throttle.py`
  — `SeamlessStreamThrottlePlugin` scheduler plugin + worker subscriber
  helper.
- modify: tests under `seamless-dask/tests/` — new
  `test_streaming.py` covering: streaming on/off, truncation-at-head,
  per-stream prefix, no-streaming-on-cache-hit, parallel transformations get
  separate streams, throttle escalation, `tf_checksum` unchanged when
  `streaming` flips.

## 1.8 Test plan (phase 1)

1. **API identity**: a transformation with `.streaming = True` and one with
   `False` produce the same `tf_checksum`. Set both, compute, assert equality.
2. **Round-trip text**: a transformation that prints `"hello\n"` and sleeps
   3 s, then prints `"world\n"`, with `streaming=True` and daskserver, makes
   the client see `"hello\n"` before completion.
3. **Truncation from head**: a transformation that prints a 200 KB blob in a
   tight loop produces at most ~8 KB-sized chunks, with `truncated_head_bytes`
   > 0 on overflow, and the *tail* of the printed text is preserved.
4. **Parallel isolation**: two streaming transformations submitted
   concurrently produce two independent streams (verified by prefix /
   handler-side dispatch).
5. **No effect when streaming is False**: no `subscribe_topic` call, no extra
   scheduler events.
6. **Throttle escalation**: force a synthetic 100-events/s situation and
   assert that within ~3 s the scheduler publishes a tighter throttle and the
   child observes it.
7. **No streaming on cache hit**: pre-populate the database cache, then submit
   with `streaming=True`; assert no chunks arrive (only the result).
8. **Exception path unchanged**: a streaming transformation that raises still
   produces the standard "Standard output / Standard error" trailer in the
   exception text.

# Phase 2 — tqdm progress bars over the phase-1 channel

Build on phase 1's transport. The objective: when `streaming=True` and the
user code uses `tqdm`, the client sees a *real* `tqdm` progress bar that
ticks in step with the remote one, with no extra setup.

## 2.1 Server-side: monkey-patch tqdm inside the child

When the child runs an `execute_transformation` request with
`streaming=True`, before invoking user code, it imports and monkey-patches
tqdm. Implementation in
`seamless-transformer/seamless_transformer/stream_tqdm.py`:

```python
def install_tqdm_patch(notifier: Callable[[dict], None]) -> contextlib.AbstractContextManager:
    """Replace tqdm.std.tqdm / tqdm.tqdm / tqdm.auto.tqdm with a streaming subclass
    for the duration of the context. Restores originals on exit."""
```

The streaming subclass overrides:

- `__init__` — assign a stable per-instance bar id
  (`f"{os.getpid()}-{id(self)}"`), capture initial parameters
  (`desc`, `total`, `unit`, `unit_scale`, `mininterval`, `bar_format`).
  Send a `tqdm_open` chunk.
- `update(n)` and `refresh()` — instead of writing to the real terminal,
  send a `tqdm_update` chunk with
  `{"bar_id": ..., "n": self.n, "total": self.total, "elapsed": ...,
    "rate": ..., "postfix": ...}`.
  Local `display()` is suppressed (write to `os.devnull`).
- `close()` — send a `tqdm_close` chunk with the final state.

Streaming-side rate limiting is the *same* as phase 1: the notifier coalesces
calls; the flusher thread emits at most once per `min_interval` per bar id
(default 2 s). Since tqdm's internal `mininterval` defaults to 0.1 s, this
naturally reduces the high tick rate of typical loops to the configured
streaming cadence.

The patch is installed only inside the request handler and removed in
`finally:`, so non-streaming transformations and other library code in the
child are unaffected.

`tqdm.notebook` is **out of scope** for v1 (Jupyter remote rendering is an
extra hop). `tqdm.auto`, `tqdm.std`, and `tqdm` itself are patched if
already imported; if `tqdm` is imported later by user code, we use a thin
`sys.meta_path` finder hook installed at patch time that re-applies the
patch after first import.

## 2.2 Client-side: render proxy tqdm bars

In `SeamlessDaskClient.submit_transformation`, the same stream handler that
prints text now dispatches on the chunk type:

- `"stream"` (phase 1) → `print(...)` as before.
- `"tqdm_open"` → create a local `tqdm.tqdm` instance bound to
  `chunk["bar_id"]`, with the same `desc` / `total` / `unit`, written to
  the local `sys.stderr`. Keep a `dict[str, tqdm]` per Transformation
  (cleared on done-callback).
- `"tqdm_update"` → call `local_bar.n = chunk["n"]; local_bar.refresh()`.
- `"tqdm_close"` → `local_bar.close()`, drop from dict.

On the topic unsubscribe path, close any still-open bars so the terminal
state is clean even if the run was interrupted.

If `tqdm` is not installed on the client, fall back to printing one-line
updates like `"[bar_id] 42/100"` — no hard dependency added.

## 2.3 Interleaving with phase-1 text

tqdm normally writes its bar to stderr and rewrites it with `\r` on each
update. Our proxy keeps that look-and-feel locally (since the local tqdm
draws it), so phase-1 prints and phase-2 bars interleave correctly. We must
*not* also let the patched server-side tqdm print to the captured stderr
(else we'd duplicate the bar through phase 1), so the patch redirects its
`file=` to `os.devnull` and inhibits ANSI control writes.

## 2.4 Throttle interaction

`tqdm_update` chunks count as 1 event per emission in the scheduler's rate
counter. Per-bar rate is throttled by the same `min_interval` as text. Many
nested bars on one transformation share the per-transformation interval; the
flusher emits at most one event per (stream/bar, tick) per interval.

## 2.5 Files to add or modify (phase 2)

- add: `seamless-transformer/seamless_transformer/stream_tqdm.py`
  — monkey-patch + meta_path finder.
- modify: `seamless-transformer/seamless_transformer/worker.py`
  — wire `install_tqdm_patch(notifier)` into
  `_execute_transformation_request` when `streaming=True`.
- modify: `seamless-dask/seamless_dask/client.py` — extend the topic
  handler to dispatch on chunk kind and manage per-bar local tqdm
  instances. Keep all phase-1 behavior intact.
- modify: tests — `test_streaming_tqdm.py`:
  1. A 10-iteration tqdm loop with sleep produces ≥ 2 update events and
     the local bar's `n` reaches 10 by the time the transformation ends.
  2. Nested tqdm bars produce two separate `bar_id`s; both are closed.
  3. tqdm with `total=None` (indeterminate) still works.
  4. Mixed `print(...)` and tqdm in the same transformation produces both
     stream-text events and tqdm events, in order.

## 2.6 Non-goals for v1 of phase 2

- Jupyter / `tqdm.notebook` rendering on the client side. (Stretch.)
- `rich.progress` or `alive_progress`. (Stretch.)
- Streaming of compiled-language stdout (Fortran/C++/Rust) — those bypass
  Python's `sys.stdout`. Phase 1's tap therefore won't catch them; that is a
  known limitation, called out in the streaming docs page once written.
  A follow-up could pipe the subprocess `stdout=PIPE` reader into the same
  notifier.

# Migration & docs

- Add a short page `seamless/docs/agent/contracts/streaming.md`:
  "Streaming is daskserver-only, opt-in per Transformation via
   `.streaming = True`. It does **not** change `tf_checksum`, dunder, or
   cache identity. Cached runs do not stream. Compiled-language stdout is
   not yet captured."
- Cross-link from `execution-backends.md` and `direct-delayed-and-transformation.md`.

# Roll-out order

1. Land the channel `event` primitive (small, mechanical) with unit tests.
2. Land the `Transformation.streaming` attribute + payload plumbing with a
   no-op server side (chunks logged but not yet forwarded), assert
   `tf_checksum` invariance.
3. Land the child `_StreamingTap` + `_dispatch` forwarder + client subscribe.
4. Land the scheduler-side throttle plugin and worker subscriber.
5. Land phase-2 tqdm patch and client-side bar renderer.

Each step is independently shippable and individually testable.
