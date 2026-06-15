# Cancellation Substrate - Handoff-Ready Implementation Plan

## Purpose

Split cancellation into two explicit operations across the transformation execution stack:

- Soft cancellation: one participant loses interest in a running checksum.
- Hard cancellation: the running checksum is wrong and must be stopped for every
  participant.

The work spans:

- in-process transformation deduplication in `seamless-transformer`;
- worker/process-pool cancellation;
- jobserver request deduplication;
- Dask transformation-future deduplication;
- byte-moving expression evaluation in `seamless-core`.

This plan is self-contained. A handoff engineer should be able to implement and test the
feature from this document alone.

## Required Behavior

- A running transformation checksum may have multiple participants.
- A participant is represented by membership in a set.
- The membership set is the refcount; there is no separate integer refcount.
- `softcancel` removes one member from the set.
- If members remain after `softcancel`, the underlying run continues and remaining
  members receive the result or error.
- If the set becomes empty after `softcancel`, the deduplication layer leaves its own
  downstream membership. At the leaf executor, empty-set soft cancellation terminates the
  actual work.
- `cancel` is hard cancellation. It cancels the underlying run outright and signals every
  member.
- Pure cache hits do not create membership.
- Caller task cancellation deregisters that caller in `finally`.
- The first caller is not the owner of the work. Execution is owned by the cache or
  server-side active-entry object.

## Implementation Boundary

This implementation changes cancellation and active-run ownership only. It leaves
transformation identity, retry classification, scheduling priority, and cache eviction
policy unchanged.

Expression support is intentionally narrow: byte-moving expression paths get active
tracking and cancellation; instant local expression operations return `False` from
`cancel()` because there is no running work to interrupt.

## Out Of Scope

- Do not change transformation checksum construction.
- Do not change cache-hit behavior except to ensure pure cache hits create no active
  membership.
- Do not change retry classification or retry counts.
- Do not change Dask scheduling priorities.
- Do not add heartbeat or TTL-based membership expiry.
- Do not make instant local expression operations cancellable; they should return
  `False` when no active byte-moving work exists.

## Local Decisions Before Coding

1. Jobserver disconnect semantics:
   - Option A: a dropped HTTP connection removes that request's member.
   - Option B: only an explicit softcancel request removes that member.
   - Both are correct for peer safety. Option A reclaims slots sooner after client
     crashes; Option B preserves jobs after client crashes when work may still be wanted.

2. CLI/SIGINT semantics:
   - Existing command-line behavior is hard cancellation: stop this submitted run now.
   - Preserve that behavior unless the command-line contract is deliberately changed.

3. `Expression.cancel()` naming:
   - Either add `Expression.softcancel()` and let `Expression.cancel()` mean hard cancel,
     or make `Expression.cancel()` the soft operation for consistency with object-level
     "lose interest" semantics.
   - The tests should encode the chosen contract.

## Current Code Anchors

- `seamless-transformer/seamless_transformer/transformation_cache.py`
  - `_ActiveSubmission`
  - `_active_submissions`
  - `_run_active_or_execute()`
  - `cancel_by_checksum()`
  - `_await_with_active_cancellation()`
- `seamless-transformer/seamless_transformer/transformation_class.py`
  - `Transformation.cancel()`
  - `Transformation.cancel_async()`
  - `_cancel_local_futures()`
  - `_release_dask_futures()`
- `seamless-transformer/seamless_transformer/worker.py`
  - `cancel_by_checksum()` and worker-slot reclamation
- `seamless-jobserver/jobserver.py`
  - `_active_transformations`
  - `_run_transformation()`
  - `_cancel_transformation()`
  - `_transformation_status()`
- `seamless-remote/seamless_remote/jobserver_client.py`
  - `run_transformation()`
  - `cancel_transformation()`
- `seamless-remote/seamless_remote/jobserver_remote.py`
  - `run_transformation()`
  - `cancel_transformation_async()`
- `seamless-dask/seamless_dask/client.py`
  - `TransformationFutures`
  - `_transformation_cache`
  - `_active_transformation_envelopes`
  - `submit_transformation()`
  - `release_transformation_futures()`
  - `cancel_by_checksum()`
- `seamless-core/seamless/expression_class.py`
  - `Expression.cancel()` stub
- `seamless-core/seamless/checksum/expression.py`
  - `evaluate_expression_async()`
  - `evaluate_expression_remote()`

## Terminology

- Member: one participant currently awaiting or holding interest in a running checksum.
- Local member: an in-process coroutine/task calling `TransformationCache.run()`.
- Remote member: this process's participation in a jobserver or Dask server-side set.
- Leaf set: the set co-located with the actual executor.
- Soft path: deregistration of one member, with execution continuing above zero.
- Hard path: kill-all cancellation for a checksum.

## Phase 1 - In-Process Awaiter Set

Goal: make `TransformationCache` own execution independently of the first caller.

1. Replace the current `_ActiveSubmission` shape with a cache-owned active object.

   Suggested shape:

   ```python
   @dataclass
   class _ActiveSubmission:
       envelope_checksum: str
       result_future: asyncio.Future
       background_task: asyncio.Task
       awaiters: set[object]
       canceled: bool = False
   ```

   If `run_sync()` and async `run()` use different loop mechanics, choose a future/task
   primitive that preserves the invariant: the active object owns execution; callers only
   await.

2. In `_run_active_or_execute()`:
   - Look up or create the active object under `_active_lock`.
   - On creation, start one detached background task that calls `_run_uncached()`.
   - Register every caller, including the first, as a member.
   - Await the shared result through shielding so caller cancellation cannot cancel shared
     execution while other awaiters remain.
   - Deregister the member in `finally`.
   - When the last member leaves and the background task is still running, trigger
     empty-set soft cancellation.

3. Keep cache hits membership-neutral.
   - The existing cache-hit fast paths stay before `_run_active_or_execute()`.
   - Add a unit test that a cached result returns without touching `_active_submissions`.

4. Preserve strict dunder behavior.
   - An active checksum under a different envelope still rejects a new
     `strict_dunder=True` submitter.
   - Hard cancellation remains the way to declare the active run wrong and make strict
     resubmission possible.

## Phase 2 - Local Soft And Hard APIs

Goal: expose separate soft and hard local operations.

1. Add `TransformationCache.softcancel_by_checksum(tf_checksum, member=None, *, remote=True)`.
   - With a known member token, remove only that member.
   - With no known member token, return `False` unless the current caller's token can be
     identified.
   - Above zero, leave the active run untouched.
   - At zero, cancel the cache-owned background task and leave remote membership through
     the remote soft API.

2. Keep `TransformationCache.cancel_by_checksum()` as hard cancellation.
   - Fail every local awaiter.
   - Call hard cancel on worker, Dask, and jobserver.
   - Preserve strict-resubmission tests that rely on the active entry being removed.

3. Update `Transformation.cancel()` and `cancel_async()`.
   - The Python object becomes terminal as today.
   - This object's local waiting task/future is canceled.
   - This object's active checksum participation leaves via softcancel.
   - Recursive object cancellation follows the same soft semantics unless a hard API is
     explicitly introduced.

4. Preserve command-line hard cancellation.
   - SIGINT and explicit command-line cancel continue to call hard `cancel_by_checksum()`.
   - Existing command-line tests expect prompt slot reclamation.

## Phase 3 - Softness Across Remote Layers

Goal: an empty local set leaves this process's remote membership without killing remote
siblings.

1. Add jobserver client APIs.
   - `JobserverClient.softcancel_transformation(tf_checksum, member_id)`.
   - `jobserver_remote.softcancel_transformation_async(...)`.
   - Synchronous wrapper if `TransformationCache` needs one.

2. Include a member/request ID in jobserver `run_transformation()` payloads.
   - The client generates the ID per submitted participation.
   - The server registers that ID in the server-side set for `tf_checksum`.

3. In local empty-set handling:
   - A local active object that submitted to jobserver calls jobserver softcancel for its
     member ID.
   - The soft path never calls jobserver hard `cancel_transformation()`.

4. Keep the hard remote path intact.
   - Local hard `cancel_by_checksum()` continues to call jobserver hard cancel.
   - Wrong-envelope and wrong-hardware recovery use the hard path.

## Phase 4 - Jobserver Membership Set

Goal: duplicate jobserver clients sharing one `tf_checksum` should not cancel one another
through soft cancellation.

1. Replace the current single-entry `_active_transformations[tf_checksum]` shape with an
   active object:

   ```python
   {
       "task": asyncio.Task,
       "members": set[str],
       "status": "running" | "canceled" | "failed" | "done",
       "result": ...,
       "exception": ...,
   }
   ```

2. In `_run_transformation()`:
   - Parse `member_id`.
   - Under a per-entry lock, add the member to an existing active entry when the checksum
     is already running.
   - If no active entry exists, create the task and add the first member.
   - Existing members await the same task/result rather than dispatching duplicate worker
     work.
   - Apply the chosen disconnect semantics from the local decision section.

3. Add `_softcancel_transformation()`.
   - Remove only `member_id`.
   - Above zero, return a payload that communicates "this member detached; work
     continues."
   - At zero, cancel/terminate the underlying worker dispatch and return canceled.

4. Keep `_cancel_transformation()` as hard cancellation.
   - Mark the active entry canceled.
   - Signal all waiters.
   - Cancel Dask/worker execution as today.

5. Status reporting:
   - `running` while the task is running.
   - `canceled` after hard cancel or leaf empty-set cancel.
   - `done` or `failed` from task result.

## Phase 5 - Dask Membership Set

Goal: Dask latch-on follows the same membership pattern as in-process and jobserver
deduplication.

1. Extend `TransformationFutures` or wrap cached futures with member metadata.
   - Track `members: set[str]`.
   - Track the first-runner as a counted quasi-member.
   - The cached active entry owns the futures object while members remain.

2. In `submit_transformation()`:
   - Generate or accept a member ID.
   - If `_cached_transformation_for_submission()` returns active futures, add the new
     member and return the same futures.
   - If creating futures, register the first member immediately.

3. Add `softcancel_by_checksum(tf_checksum, member_id)`.
   - Remove only that member.
   - Above zero, release only references owned by that member.
   - At zero, mark scheduler cancellation and release futures as the current hard path
     does.

4. Keep `cancel_by_checksum()` hard.
   - Hard cancel marks scheduler cancellation for the transformation/submission and
     releases futures for everyone.

5. Preserve the Dask latch-on grace window.
   - Future-wired cancellation after checksum-wired submission waits about 10 seconds so
     latch-on can happen.
   - Existing `fat_future_ttl` and transformation future caching behavior continue to
     work.

## Phase 6 - Expression Cancellation Tail

Goal: replace `Expression.cancel()`'s `NotImplementedError` with truthful behavior.

1. Fast paths return `False`.
   - Identity expressions, manifest navigation, and in-memory get-item/get-attr/slice
     complete without a meaningful cancellation point.
   - `Expression.cancel()` returns `False` when no active byte-moving work exists.

2. Add active tracking around byte-moving paths.
   - Remote expression evaluation via jobserver.
   - Input materialization/fingertip when it is async/remote and cancellable.
   - Output writing/materialization when an active task exists.

3. Use the same membership-set model.
   - Key by expression database key: `(input_checksum, path, celltype, target_celltype)`.
   - Pure cache hits do not register members.
   - Last-member softcancel cancels the active I/O task or remote expression request.

4. Implement the chosen expression cancellation API.
   - If `Expression.softcancel()` is added, it removes one member.
   - If `Expression.cancel()` is the soft operation, document that in its docstring.
   - Hard expression cancellation, if implemented, signals every member for that
     expression key.

## Tests

### In-Process Cache Tests

1. Two awaiters share one active run.
   - Softcancel one awaiter.
   - Backend continues.
   - Other awaiter receives the result.

2. Last awaiter cancellation reclaims work.
   - When the final member leaves, the background run is canceled.
   - For worker-backed execution, the worker slot is reclaimed.

3. Caller task cancellation does not kill peers.
   - Cancel the first caller task while a second caller remains.
   - The second caller still receives the result.

4. Pure cache hit is membership-neutral.
   - A cached result returns without adding active members.

5. Hard cancel remains hard.
   - `cancel_by_checksum()` fails all awaiters.
   - Strict dunder resubmission works after hard cancel.

### Jobserver Tests

1. Duplicate same-checksum requests share one worker dispatch.
2. Softcancel from one member leaves sibling request running.
3. Softcancel from the last member cancels the worker dispatch.
4. Hard cancel kills all members.
5. Status endpoint reports running, canceled, failed, and done.

### Dask Tests

1. Cached `TransformationFutures` gain multiple members.
2. Softcancel first member leaves futures alive for a sibling.
3. Last-member softcancel marks scheduler cancellation.
4. Hard `cancel_by_checksum()` cancels all latchers.
5. Existing Dask cancel CLI tests continue to pass.

### Expression Tests

1. Fast-path expression cancel returns `False` and does not raise.
2. Remote/materializing expression registers as active.
3. Softcancel one expression member leaves sibling running.
4. Last-member softcancel cancels the active I/O/remote task.

## Acceptance Criteria

- The first caller no longer owns execution in `TransformationCache`; execution is
  cache-owned.
- Every active participant is represented by set membership and deregisters in `finally`.
- Softcancel above zero never signals or cancels peers.
- Empty-set softcancel cascades softly to the next remote deduplication layer.
- Only the leaf empty set terminates the actual executor.
- Hard cancel remains available and kill-all.
- Existing strict-dunder conflict behavior is preserved.
- Existing CLI/SIGINT cancellation behavior remains prompt.
- `Expression.cancel()` no longer raises `NotImplementedError`; it returns a meaningful
  boolean for the supported cancellation surface.

## Risks And Mitigations

- Risk: Local task cancellation propagates into the shared background task.
  - Mitigation: await shared results through shielding; deregister in `finally`.

- Risk: Empty local set hard-cancels jobserver/Dask and kills remote siblings.
  - Mitigation: add separate remote softcancel APIs and use them only from soft paths.

- Risk: First-runner softcancel releases Dask futures while latchers remain.
  - Mitigation: Dask futures are owned by the member set/cache.

- Risk: Jobserver member leaks after client crash.
  - Mitigation: choose disconnect semantics before implementation and test that behavior.

- Risk: Existing hard-cancel tests become ambiguous.
  - Mitigation: keep hard `cancel_by_checksum()` and add new softcancel tests.

- Risk: Sync `run_sync()` and background event-loop ownership become tangled.
  - Mitigation: implement Phase 1 around the actual event loop used by
    `TransformationCache` and add tests for sync and async callers sharing one active
    run.

## Rollout Strategy

1. Ship in-process membership sets and local soft/hard APIs with current tests passing.
2. Switch `Transformation.cancel()` to soft participation cancellation after local peer
   survival tests pass.
3. Add jobserver soft APIs and jobserver membership tests.
4. Add Dask membership semantics and preserve existing CLI/SIGINT tests.
5. Implement the expression cancellation tail once the transformation cancellation API is
   stable.

## Handoff Readiness Check

- Goal is concrete: member-set soft cancellation plus explicit hard cancellation.
- Code anchors are listed across all affected packages.
- Layer-by-layer semantics are specified.
- Tests cover local, jobserver, Dask, expression, and CLI behavior.
- Remaining decisions are local policy choices: jobserver disconnect handling,
  CLI/SIGINT contract, and expression method naming.
