# Hardening `Transformation` Immutability And Dunder Separation

## Summary

Implement `Transformation` as an immutable computation definition plus mutable
execution promise. The immutable definition must include both the
checksum-defining payload and the frozen orthogonal dunder envelope. Execution
state such as futures, computed transformation checksum, result checksum, and
status remains mutable.

First add checksum-addressed cancellation. The immutability hardening depends on
a real inactive state for in-flight submissions, because the same `tf_checksum`
with a different orthogonal dunder envelope may be submitted only after the
prior submission is no longer active. "Canceled" must therefore be a public,
observable terminal state, not only backend cleanup.

This intentionally drops backward cache compatibility for affected
transformations. Moving `__meta__` and `__env__` out of the checksum and moving
`__schema__` into the checksum changes transformation identity. Existing cache
entries under the old checksum boundary may be missed and recomputed.

Clean up the dunder model at the same time. A dunder is not automatically
non-identity. Each dunder must be classified as one of:

- **Load-bearing**: part of the checksum-defining transformation payload;
  changing it changes `tf_checksum`.
- **Orthogonal**: frozen and carried with the `Transformation`, but excluded
  from `tf_checksum`; changing it changes execution envelope, not computation
  identity.
- **Derived/eliminable**: not independent; regenerate from load-bearing data or
  carry temporarily only as validated support.

Hard constraint for this implementation: `seamless-transformer` still cannot
generally handle the same `tf_checksum` running concurrently with different
dunder envelopes. A differently dundered submission for an existing checksum is
allowed only when the original submission is no longer active: failed,
succeeded, or canceled through the checksum-addressed cancellation API.

Handoff-ready self-check:

- Goal and contract are explicit: immutable definition, mutable promise state.
- The dunder classification is complete for all known transformation dunders.
- Ambiguous implementation choices are fixed below: use recursive read-only
  public views, reject active differently dundered submissions, and validate
  derived support dunders deterministically.
- The plan includes API impact, data flow, backend cancellation behavior,
  intentional cache invalidation, concurrency constraints, tests, and
  assumptions.

## Dunder Classification

Use this classification in code comments, tests, and the later docs update.

Load-bearing dunders:

- `__language__`: selects code interpretation and execution semantics.
- `__output__`: defines output name/celltype/subcelltype.
- `__as__`: maps pin names into the execution namespace; code can observe this.
- `__format__`: defines filesystem/deep/file pin materialization semantics.
- `__schema__`: compiled function ABI/signature; not derivable from `code` and
  affects declared call semantics.

Orthogonal dunders:

- `__meta__`: independent execution envelope. Operational keys include `local`,
  `driver`, `allow_input_fingertip`, `__direct_print__`, `transformer_path`,
  `ncores`, `write_remote_job`, and compiled `metavars`. Metavars are not
  load-bearing by definition; they are execution/resource/allocation bounds and
  must not affect the returned value except by failure.
- `__env__`: independent execution environment checksum; not derivable from
  `tf_checksum`.
- `__compilation__`: independent compiled execution settings;
  compiler/debug/profile choices are excluded from identity under the compiled
  transformer contract.
- `__record_probe__`: independent probe/record control.
- `__code_checksum__`: syntactic/debug fallback for code resolution;
  determinant code identity is the plain `code` pin.
- `__code_text__`: fallback/debug materialization aid; validate against
  determinant code whenever the determinant code checksum can be resolved.
- `__compilers__`, `__languages__`: legacy execution registry/config; accept as
  orthogonal compatibility support if present.

Derived/eliminable dunders:

- `__compiled__`: derive from compiled transformation shape, especially presence
  of `__schema__`; keep only as compatibility support and validate if present.
- `__header__`: derive from `__schema__` via `seamless-signature`; do not store
  as independent immutable definition state.
- `__deps__`: derive from the frozen dependency graph and child transformation
  checksums; generate into transport `tf_dunder` only.

`META__*` keys are not dunders; they remain orthogonal execution metaparameters
and excluded from `tf_checksum`.

## Implementation Changes

### Phase 1: Cancellation API

Add checksum-addressed cancellation before the immutability/dunder hardening.
This phase is complete when the current active submission for a `tf_checksum`
can be made inactive across local, spawn/delegation, Dask, and jobserver paths,
with documented best-effort limits.

Cancellation is submission-centric. In the active `seamless.config.init` /
`seamless-init` namespace, there is at most one current submission per
`tf_checksum`. A current submission is:

```text
tf_checksum + frozen orthogonal dunder envelope + backend execution state
```

Canceling means canceling the current submission for that checksum. The checksum
itself is never invalidated, and a later submission with the same checksum is a
new current submission.

Cancellation contract:

- Add `seamless-cancel <tf_checksum>` as the primary public cancellation surface.
- Add backend API `cancel_by_checksum(tf_checksum)` for the active Seamless
  namespace.
- `Ctrl-C` / SIGTERM from `seamless-run` and
  `seamless-run-transformation` cancels the current submission by checksum.
- `Transformation.cancel(*, recursive: bool = False) -> bool` and
  `await Transformation.cancel_async(*, recursive: bool = False) -> bool` are
  frontend wrappers. If the transformation checksum is known, cancel by checksum.
  If it is unresolved, cancel the local promise/wait and, with `recursive=True`,
  cancel known upstream dependency checksums.
- Return `True` if the call transitions an active submission or local promise to
  canceled, or requests backend cancellation for active work; return `False` if
  there is no active submission/promise or it is already terminal.
- After Python-object cancellation, `status` reports `"Status: canceled"`,
  `exception` reports a stable cancellation message, and `result_checksum`
  raises `TransformationError("Transformation was canceled")`.
- Cancellation is terminal for that Python `Transformation` instance.
  `clear_exception()` must not revive a canceled transformation; retries require
  creating a new submission/object.
- Cancellation is best-effort for already-running CPU work. The API guarantees
  that the Seamless submission becomes inactive and no longer blocks active
  dunder-envelope reuse; it does not guarantee that arbitrary Python or shell
  code already executing in another thread/process is preempted immediately.

Add explicit cancellation state to `Transformation`:

- `_cancelled: bool`;
- `_cancel_requested: bool` if needed to distinguish requested cancellation from
  backend acknowledgment;
- `_cancel_message: str`, defaulting to `"Transformation was canceled"`;
- helper `_mark_cancelled(message: str | None = None)` that clears active
  memoized futures and updates `_evaluated`/`_constructed` consistently without
  changing the frozen definition.

Backend cancellation requirements:

- Local asyncio path: cancel `_computation_task` with `task.cancel()`, await it
  in `cancel_async()`, and swallow `asyncio.CancelledError` through
  `_future_cleanup()`.
- Thread/executor local path: call `_computation_future.cancel()` when possible
  and mark the promise canceled even if the executor has already started the
  callable. Do not pretend this kills already-running Python code.
- Dask path: if `_dask_futures` exists, call
  `release_transformation_futures(futures, cancel=True)` on the active Seamless
  Dask client for the checksum registry entry; otherwise cancel any
  `_computation_task` that is awaiting Dask submission. Release local references
  after cancellation.
- Spawn/delegation path: preserve and expose the existing delegate cancel
  mechanism. When a child-side proxy future is canceled, the existing
  `delegate_transformation_cancel` request must reach the parent. When the
  parent owns a delegated Dask submission, release it with `cancel=True`. When
  the parent owns a direct worker-pool dispatch that is already executing,
  cancellation is best-effort and must at least free the Seamless promise and
  release capacity once the worker returns.
- Jobserver path: expose checksum-addressed submit/status/cancel behavior
  instead of only blocking on `/run-transformation`. Jobserver cancellation must
  route to its worker-pool/delegate/Dask machinery by checksum. If an
  already-running worker process cannot be interrupted, mark the current
  submission canceled and drop/ignore its eventual result for that submission.

Required jobserver API changes:

- Keep `/run-transformation` as compatibility behavior, but ensure client
  interruption cancels the current submission by checksum before releasing its
  wait.
- Add checksum-addressed status/cancel endpoints or equivalent client methods
  for `seamless-cancel <tf_checksum>` and fire-and-forget monitoring. The public
  contract is keyed by `tf_checksum`.

Active-submission registry requirements:

- Track active submissions by normalized `tf_checksum`.
- Store a normalized checksum of the orthogonal dunder envelope for each active
  submission.
- Treat `done`, `failed`, and `canceled` as inactive and remove registry entries
  promptly.
- Reject same-checksum/different-dunder submissions while the existing registry
  entry is active.
- Cancellation must remove or terminally mark the active entry before a
  differently dundered replacement can be accepted.

Phase 1 tests:

- Local asyncio transformation started with `start()` can be canceled and reports
  canceled status.
- Canceling a task returned by `tf.task()` marks the underlying `Transformation`
  canceled or, if no underlying computation was shared, does not leave active
  registry state behind.
- Dask cancellation calls `release_transformation_futures(..., cancel=True)` and
  permits a differently dundered same-checksum re-submission afterwards.
- Spawn/delegation cancellation sends `delegate_transformation_cancel` and
  releases delegated Dask futures when present.
- `seamless-cancel <tf_checksum>` cancels active submissions created by
  `seamless-run`, `seamless-run-transformation`, Python `Transformation`, spawn,
  jobserver, and Dask paths.
- `Ctrl-C` during `seamless-run` / `seamless-run-transformation` cancels the
  current checksum submission.
- Jobserver checksum-addressed status/cancel works, and canceling the client
  wait for compatibility `/run-transformation` cancels by checksum.
- `clear_exception()` does not revive a canceled `Transformation`.

### Phase 2: Immutability And Dunder Separation

Document the cache break before replacing production checksum lookups:

- the new load-bearing/orthogonal split is the only checksum algorithm;
- do not implement legacy checksum aliases;
- existing cache entries whose old checksum included `__meta__` or `__env__`, or
  omitted now-load-bearing `__schema__`, may not be found;
- users who need those results must rely on recomputation or external/manual
  migration outside this implementation.

Replace the current `tf_get_buffer()` key split with explicit load-bearing
versus orthogonal sets. The checksum buffer must include plain pins plus
load-bearing dunders, and exclude orthogonal and derived/eliminable dunders.
Update `NON_CHECKSUM_ITEMS`, `extract_tf_dunder()`, `extract_job_dunder()`,
why-not classification, and docs/comments to use the same vocabulary.

Introduce a private frozen definition object for `Transformation`:

- stores a copy-owned checksum payload template;
- stores a copy-owned orthogonal dunder envelope;
- stores an immutable mapping of dependency pin names to child `Transformation`
  handles;
- stores scratch policy and result celltype;
- builds prepared execution dicts by combining checksum payload, orthogonal
  envelope, and resolved dependency result checksums.

Build this frozen definition in `transformation_from_pretransformation()` using
`PreTransformation.build_partial_transformation(upstream_dependencies)`.
Non-Transformation pins are prepared to checksums at factory time.
Transformation-valued pins remain dependency edges. The original
`PreTransformation` remains only for resource lifetime/release.

Make returned `Transformation` definition-immutable:

- pass `scratch` into `__init__`;
- deep-copy internal metadata and dunder envelope;
- expose `meta` as a recursively read-only `MappingProxyType` view, and make
  assigning `tf.meta` raise;
- make assigning `tf.scratch` raise;
- keep execution promise fields mutable: `_transformation_checksum`,
  `_result_checksum`, `_constructed`, `_evaluated`, `_exception`,
  `_computation_task`, `_computation_future`, `_dask_futures`.

Adapt local execution:

- construction computes `tf_checksum` from the frozen checksum payload plus
  resolved dependency result checksums;
- evaluation passes the prepared execution dict and frozen orthogonal dunder
  envelope to `run_sync()` / `run()`;
- `clear_exception()` may clear failed memoization only, never re-read mutable
  construction state.

Adapt Dask:

- `_build_dask_submission()` uses the frozen definition, not live
  `PreTransformation`;
- dependency pins remain `kind="transformation"` with `checksum=None`;
- parent checksums may remain unknown until dependency futures resolve;
- no-dependency checksum fast paths compute from the frozen checksum payload;
- Dask payloads deep-copy transformation dict and dunder envelope.

Adapt compiled transformers:

- stop rewriting constructor functions after `Transformation` creation;
- replace deferred validation mutation with optional post-prepare hooks passed
  into the factory;
- move `__schema__` into the checksum payload;
- generate `__header__` from schema when needed. If a caller supplied
  `__header__`, validate that its checksum matches the generated header checksum
  and then discard it from immutable definition state;
- derive `__compiled__` from the presence of compiled definition state. If a
  caller supplied `__compiled__`, validate that it agrees and then discard it
  from immutable definition state;
- keep `__compilation__`, `__env__`, and `__meta__.metavars` in the orthogonal
  envelope.

Adapt `seamless-run-transformation` and related run APIs:

- when a caller supplies a `tf_checksum`, resolve the checksum payload from the
  checksum buffer and combine it with dunders supplied via
  CLI/options/transformation dict into an orthogonal envelope;
- CLI flags such as `--direct-print`, `--fingertip`, and `--scratch` must spice
  the orthogonal envelope, not alter the checksum payload;
- reject concurrent submission of the same `tf_checksum` with a different active
  dunder envelope, with a clear error that names the checksum and says the prior
  submission must finish or be canceled first;
- allow differently dundered re-submission only after the existing
  active submission is done, failed, or canceled through the Phase 1 API;
- record/cache a normalized checksum of the active dunder envelope per running
  `tf_checksum` so this constraint is enforceable without retaining mutable
  caller-owned objects.

## Test Plan

Add checksum classification tests:

- changing `__language__`, `__output__`, `__as__`, `__format__`, or `__schema__`
  changes `tf_checksum`;
- changing `__meta__`, `__env__`, `__compilation__`, `__record_probe__`,
  `__code_checksum__`, `__code_text__`, `__compilers__`, `__languages__`, or
  `META__*` does not change `tf_checksum`;
- `__header__` and `__compiled__` are validated as derived support when present.

Add cache-invalidation tests:

- moving `__meta__` or `__env__` out of the checksum produces the new expected
  checksum, even though it does not match the old checksum;
- moving `__schema__` into the checksum produces the new expected checksum, even
  though it invalidates old compiled cache keys;
- no legacy checksum aliases are consulted by cache, active-submission, Dask,
  jobserver, or `seamless-cancel` paths.

Add immutability tests:

- returned `Transformation` rejects `tf.scratch = ...`, `tf.meta = ...`, and
  `tf.meta[...] = ...`;
- mutating original `meta`, `tf_dunder`, `PreTransformation`, or ordinary input
  objects after factory return does not affect checksum or execution;
- dependency graph edges are frozen while dependency result/checksum promise
  state remains mutable.

Add cancellation tests:

- `cancel()` and `cancel_async()` expose a consistent terminal canceled state;
- canceled transformations are not revived by `clear_exception()`;
- same-checksum/different-dunder submission is allowed after public
  checksum-addressed cancellation;
- `seamless-cancel <tf_checksum>` cancels active submissions without requiring
  caller-side stored submission state;
- `Ctrl-C` / SIGTERM from `seamless-run` and `seamless-run-transformation`
  cancels the current checksum submission;
- backend-specific cancellation paths are exercised for local asyncio,
  thread/executor best-effort, Dask, spawn/delegation, and jobserver.

Add Dask tests:

- parent Transformation with child input submits before parent checksum exists;
- parent checksum resolves after dependency futures produce result checksums;
- frozen dunder envelope is used in Dask submission;
- same-checksum/same-dunder future reuse still works;
- same-checksum/different-dunder concurrent submission is rejected with the
  documented clear error;
- same-checksum/different-dunder re-submission after completion is allowed.

Add `seamless-run-transformation` tests:

- running a supplied checksum with `--direct-print`, `--fingertip`, or
  `--scratch` does not mutate or recalculate the checksum payload;
- supplied dunders are passed through execution and record/probe paths;
- differently dundered active submissions for the same checksum hit the hard
  constraint with a clear error.

Run targeted existing suites: transformer construction/execution, bash
pretransformation, compiled transformer tests, Dask transformation/execution
record tests, probe/record tests, why-not diff tests, and CLI
run-transformation tests.

## Assumptions

Dunder payloads are small and may be deep-copied freely.

Changing orthogonal dunders may change where/how/whether execution succeeds, but
must not change the denoted result value. If a supposedly orthogonal dunder can
change successful return value, that is a contract breach and it must be
promoted to load-bearing.

This pass may move some errors earlier to factory/construction time because
non-Transformation pins are snapshotted before execution.

The concurrency limitation for differently dundered same-checksum submissions is
intentional for now and must be documented, not designed around. Phase 1
cancellation makes this limitation operational by providing a public way to move
an active promise into an inactive terminal state.
