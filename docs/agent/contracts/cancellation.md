# Cancellation (Contract)

**Cancellation is deregistration from a membership set, not a kill.** Wherever deduplication happens there is a set whose members are the participants that still want a run that has not finished. Exactly two operations act on it:

- `softcancel` removes one member. Only an emptied set can stop the underlying run, and at the Dask site not even that does (*The two operations*).
- `cancel` declares the run *wrong* and kills it for everyone.

One pattern, three transformation sites, and the same pattern again in the Expression layer.

This page is the cancellation substrate **for transformations**. Expression cancellation (a member set keyed by Expression identity, the linger, and the absence of any hard cancel there) belongs to `contracts/expressions.md`. The section *The Expression layer is the same pattern* below points at it and does not restate it.

**The set's membership *is* the count.** There is no separately maintained integer refcount and no `refholding` flag. This is deliberately a different mechanism, with a different lifetime and a different vocabulary, from the checksum reference lifecycle (`contracts/internal/checksum-reference-lifecycle.md`). A membership set tracks who still wants work that has not finished; the reference lifecycle keeps a buffer alive once it exists. Do not conflate them, and do not call a membership set a refcount.

Code locations:

| Concern | Module / symbol |
|---|---|
| In-process membership set, both operations | `seamless_transformer.transformation_cache` (`TransformationCache`, `_ActiveSubmission`, `_run_active_or_execute`, `_detach_active_member`, `softcancel_by_checksum` and its `_async` form, `_softcancel_leaf`, `cancel_by_checksum`) |
| Handle verb | `seamless_transformer.transformation_class.Transformation` (`cancel`, `cancel_async`, `_cancel_local_futures`, `_mark_cancelled`); see `contracts/direct-delayed-and-transformation.md` |
| Worker slots | `seamless_transformer.worker` (`cancel_by_checksum`) |
| Server-side set | `seamless-jobserver/jobserver.py` (`_active_transformations`, `_run_transformation`, `_softcancel_transformation`, `_detach_transformation_member`, `_cancel_transformation`, `_transformation_status`). The clients are `seamless_remote.jobserver_remote` and `seamless_remote.jobserver_client` (`softcancel_transformation(tf_checksum, member_id)`, `cancel_transformation(tf_checksum)`) |
| Latch-on set | `seamless_dask.client` (`submit_transformation`, `release_transformation_futures`, `softcancel_by_checksum(tf_checksum, member_id)`, `cancel_by_checksum(tf_checksum)`) over `seamless_dask.types.TransformationFutures` |
| Reactive policy | `seamless_workflow.reactive.Reactive` (`_suspend`, `_expire_run`) and `seamless_workflow.context.Context.prune`; see `contracts/workflow-context.md` |
| Expression layer | `seamless.checksum.expression` (`softcancel_expression`, `_active_expressions`, `_lingering_expressions`); see `contracts/expressions.md` |
| Contract tests | `seamless-transformer/tests/cancellation` (in process, and remote multi-tenant jobserver and Dask); `seamless-jobserver/tests/test_contract_cancellation_membership.py`; `seamless-dask/tests/test_strict_dunder.py`; `seamless-workflow/tests/test_contract_cancellation_policy.py` |

## The pattern

- **Execution is owned by the deduplication site, never by the first caller.** In process, the actual run is a detached background task owned by the transformation cache. **Every** participant, the first one included, is a mere awaiter. This decoupling is what makes soft cancellation possible at all: if the first caller owned the execution, cancelling that caller would kill the work for everyone. (*Implementation status*: the background task is still tied to the first caller's event loop.)
- A participant **registers on entry and deregisters in `finally`**. That covers normal completion, an exception and task cancellation alike.
- **A pure cache hit is never a member.** It returns before the site is consulted.

The three sites:

| Site | The set | A member is |
|---|---|---|
| **In process** (`seamless-transformer`'s transformation cache) | an awaiter set per `tf_checksum` | a coroutine awaiting the shared submission future |
| **Jobserver** | the same pattern, as an independent instance **inside the jobserver** | a latched client process, identified by a member id that it sends with its request |
| **Dask** | a first-runner → set-of-latch-on-runners map | a latch-on runner. The first runner is itself a counted **quasi-member**: it counts for cancellation and for result delivery, but it is **not** the lifecycle owner, because the set owns the future reference. So the first runner leaving does not take the future away from its latchers |

The jobserver's own set is what stops one client's softcancel from deleting a sibling client's job.

These three are the **transformation** sites. The Expression layer has a set of its own, keyed by **Expression identity** rather than by a `tf_checksum`, and it takes no hard cancel (*The Expression layer is the same pattern*, below).

## The two operations

**`softcancel`: remove this member from the set; if the set is now empty, cancel the underlying run.** While members remain, the run continues for them. On a completed or forgotten checksum it is a no-op.

- **It is pure deregistration: no signal reaches the member being removed.** A softcancel is a member voluntarily leaving because its owner stopped wanting the result. The whole operation is `set.discard(member)` plus the empty check. A cancellation signal is delivered **only** when the set empties, and **only** to the underlying run.
- **Exception: Dask.** When the last member softcancels a Dask run, the client releases its futures and drops the entry, and it does **not** cancel the submission on the scheduler. This is desired behaviour, not a gap: on Dask, a softcancel never kills the run. Only a hard `cancel` does. (The Dask latch-on set is per client process, while tenants in separate client processes can latch onto one scheduler submission, so a client's emptied set is not evidence that nobody wants the run.) `seamless-dask/tests/test_strict_dunder.py::test_dask_softcancel_last_member_detaches_without_scheduler_cancel` pins this.
- **Open inconsistency: the Expression layer.** `softcancel_expression` cancels the *leaving* member's own pending call (`waiter.get_loop().call_soon_threadsafe(waiter.cancel)`), so the member that asked to leave does receive a signal — from itself, not from a peer, but still a signal this "no signal reaches the member being removed" rule says shouldn't exist. `contracts/expressions.md`'s *Cancellation* section names this explicitly as unresolved, since this page's own text is ambiguous about whether the "same pattern" statement (*The Expression layer is the same pattern*, below) extends this exact clause to Expressions or stops short of it. Not ruled; do not treat either page's current wording as settling it.

**`cancel` (hard): cancel the underlying run outright, and signal and cancel every member.** Unlike softcancel it *does* signal members, because the run is being declared **wrong**, not abandoned.

- Hard cancel means "**this run is wrong and must be killed and resubmitted**", because of a wrong dunder envelope or wrong hardware. It does **not** mean "I lost interest".
- **Its cross-tenant reach is correct, not a footgun.** The execution envelope is orthogonal to the `tf_checksum` (`contracts/identity-and-caching.md`). So the same `tf_checksum` may be running under the wrong envelope for every latcher at once, and all of them need it killed and resubmitted. Hard cancel is the deliberate escape hatch for the `strict_dunder` envelope-contention check.
- A wrong *input* usually gives a **different** `tf_checksum`, which is unlikely to be shared, so softcancel suffices there.

## Three constraints

1. **Softness composes across layers, and this is load-bearing.** When the underlying run is a shared remote submission, the "cancel the underlying run" step inside `softcancel` is itself a **softcancel of the next layer down**. An emptied in-process set means *leave the jobserver or Dask set*, never *kill it*. **A real termination happens only at the leaf set**, the one co-located with the actual executor, when *that* set empties. The jobserver is such a leaf: when its set empties it cancels the job and frees its worker slot. **Dask is the exception:** its set never terminates the run on a softcancel (*The two operations*), so an all-softcancelled Dask run is not killed by Seamless at all. That is under-cancellation, which constraint 2 makes benign. If an emptied set hard-cancelled the remote instead, the unconditional kill would only move one process hop downstream and the hazard would be unfixed.
2. **Cross-process membership liveness is deliberately not built.** An in-process set cleans itself up through `finally`; a server-side set does not. **A leaked member is benign, and often correct.** It causes *under*-cancellation, never a peer kill. A crashed or disconnected client that never sends a softcancel does not pin a peer's job and corrupts nothing. The job runs to completion and deposits its result in the content-addressed cache, which is usually exactly what the crashed holder needs on reconnect: a crash does not say the work became uninteresting. TTL heartbeats that forced cancellation on disconnect would destroy work that is still wanted. Connection-scoped auto-deregistration may be taken **where it is free**, but it must not be relied on as a cancellation trigger.
3. **Per-set atomicity.** "Remove the last member → empty → cancel" races "a new submitter wants to latch on". The membership change and the empty-check-and-cancel are therefore one atomic step under a per-set lock. A lost race merely causes a fresh run to be submitted. It can never corrupt anything, because results come from the content-addressed cache, never from the set.

## Policy: which operation, where

- **The reactive workflow `Context` uses `softcancel` exclusively**, including for node deletion, node supersession, `prune()` and `close()`. The reactive loop only ever *loses interest*, which is precisely softcancel. See `contracts/workflow-context.md`.
- **CLI and SIGINT stay hard.** An explicit command-line cancel means "stop this submitted run now", and prompt slot reclamation is part of that contract.
- **Hard cancellation is checksum-addressed.** It is aimed at a `tf_checksum`, not at a handle, because a wrong run is wrong for everyone holding it.
- **A caller never manages server-side membership directly.** It softcancels its own participation, and **each site decides by its own set when to actually kill.**

## The API

| Name | Meaning |
|---|---|
| `TransformationCache.softcancel_by_checksum(tf_checksum, member=None, *, remote=True)`, and its `_async` form | remove one member. At zero, cancel the cache-owned background task and *leave* the remote set through the remote soft API. The meaning of `member=None` is not yet confirmed (below) |
| `TransformationCache.cancel_by_checksum(tf_checksum)` | hard: fail every local awaiter, and hard-cancel the worker, Dask and the jobserver |
| `Transformation.cancel(*, recursive=False)` / `await Transformation.cancel_async(...)` | a **handle** verb; see below |
| jobserver `softcancel_transformation(tf_checksum, member_id)` / `cancel_transformation(tf_checksum)` | the same two operations on the server-side set |
| Dask `softcancel_by_checksum(tf_checksum, member_id)` / `cancel_by_checksum(tf_checksum)` | the same two operations on the latch-on set, **except** that an emptied set releases its futures and does not cancel the run (*The two operations*) |

**`member=None` (proposed, not confirmed).** The proposed wording is: with no member given, `softcancel_by_checksum` is **a no-op returning `False`**, because a caller can only softcancel its own participation. The author has deferred confirmation. The in-process suite already asserts the proposed behaviour (`test_contract_substrate.py::test_softcancel_by_checksum_noop_cases`).

**A handle verb and a substrate verb are not the same thing.** The substrate vocabulary (`softcancel` means deregister, `cancel` means hard kill; `contracts/expressions.md`, *API*) governs the **checksum-addressed** API above. A **handle**'s `.cancel()` means "this handle gives up". It makes *that* handle terminal and softcancels its participation, leaving the shared run alive for every other member.

So `Transformation.cancel()`:

- marks the handle terminal. `status` reports canceled, `result_checksum` raises, and `clear_exception()` does **not** revive it; a retry needs a new handle. The exception that `result_checksum` raises is proposed to be **`TransformationError`**; the author has deferred confirmation.
- **softcancels this handle's participation** in the shared run, which continues for any other member;
- returns `True` if it moved active work (or a local promise) to canceled, and `False` if nothing was active. Whether `cancel()` on an already completed handle still marks it terminal is deferred;
- with `recursive=True`, cascades the **same soft semantics** to known upstream dependency handles;
- **never invalidates the `tf_checksum`.** A later submission of the same checksum is a new submission, which latches on or starts fresh as usual.

An `Expression` handle has nothing terminal to mark, which is why its only verb is `softcancel()` (`contracts/expressions.md`).

## What cancellation is *not* for

- **Not for correctness.** Results are content-addressed, so a late result is *unwanted*, never *wrong*. Because cancellation is best-effort, the Context must ignore late results from superseded runs in any case. The value of a cancel is exactly: remaining resource cost × the chance that nobody else wants the output.
- **Not a state to clear.** There is no cancelled state that must be reset before work can proceed; a caller that changes its mind asks again. (A *handle* made terminal by `.cancel()` has a state of its own, but that is the handle's, not the substrate's.)
- **Not a guarantee that the work stopped.** A softcancel that returns `True` means "I was registered and have now left", and nothing more.

## The Expression layer is the same pattern

Expression evaluation has its **own member set, keyed by the full Expression identity** (the 4-tuple used for evaluation and caching), not by a `tf_checksum` and not by a checksum in the buffer layer. A standalone `Expression` joins it as `id(self)`, and the workflow Context joins it with its demand key. `contracts/expressions.md` (*Deduplication*, *Cancellation*) owns this set, including the linger; this page does not repeat it. Three consequences matter here:

- the same membership model applies, so an evaluation shared with a live requester survives another requester's departure;
- there is **no hard cancel at that layer at all**, by design, so a hard `cancel_by_checksum` has no Expression counterpart;
- an abandoned **fingertip chain** is meant to deregister softly down every step, and a step shared with a live chain survives. This is the membership model of this page applied to Expressions. The leaf Transformation needs no special case: the linger keeps its member registered, and it is killed only when its own set empties, which is this page's softness-composes rule reaching the leaf.

Two premises of that layer explain why it is a *different* mechanism rather than a copy of this one. An Expression's cost is **unbounded**, because a fingertip chain may contain Transformations. And the chance that **nobody else wants the output is low**: sibling projections, a Transformation over the same checksum and a revert all want the same result. That is why the Expression layer adds a linger (a requester arriving during it rejoins the evaluation), which this page's transformation sites do not have.

Vocabulary: that set is a **member set**, never a refcount.

## Implementation status and current limitations

This section lists where the code does not yet implement the contract above, or implements it differently. **The contract wins**: the rules above are the test oracle, and every contract-ahead-of-code item below is pinned by an `xfail(strict=False)` test whose reason reads "… contract ahead of code: …".

**What is verified.** The contract suite at `seamless-transformer/tests/cancellation` (a README charter, a shared harness, in-process files, and remote multi-tenant jobserver and Dask files) verifies, together with the per-package suites listed under *Code locations*:

- **In process:** deduplication; softcancel as deregistration with peer survival; softcancel at zero cancelling the underlying run; a cache hit never becoming a member; hard cancel as kill-all; `strict_dunder` envelope rejection; per-set atomicity.
- **Jobserver:** deduplication; member-id softcancel with peer survival; leaf kill when the set empties, which cancels the job and frees its worker slot, both locally (`seamless-jobserver/tests/test_contract_cancellation_membership.py::test_jobserver_all_softcancel_kills_at_the_leaf`) and on a real multi-tenant cluster (`test_remote_multitenant_jobserver.py::test_jobserver_both_softcancel_leaf_kill`); hard cross-tenant cancel; the benign crashed-member case.
- **Dask:** deduplication; a latch-on runner's softcancel leaving the first runner alive; the last member's softcancel releasing the futures without a scheduler cancel; hard cross-tenant cancel; on a real cluster, the first runner softcancelling while a latcher survives and still receives the result (`test_remote_multitenant_dask.py::test_dask_first_runner_softcancel_latcher_survives`).

**Contract ahead of code** (xfail-pinned):

- **A shared run's background task is owned by the first caller's event loop.** The cache-owned task is created on the loop of the first caller (for a workflow Context, the controller's loop). When that loop ends (`asyncio.run` returns), or on `Context.close()`, the task is cancelled and every surviving peer receives `ExecutionCanceledError`. This violates "execution is owned by the deduplication site, never by the first caller" (*The pattern*): a first caller that merely stopped wanting the result kills it for everyone. Pinned by `seamless-transformer/tests/cancellation/test_contract_substrate.py::test_first_callers_loop_ending_does_not_kill_peer` and `seamless-workflow/tests/test_contract_cancellation_policy.py::test_close_softcancels_and_peer_survives`.

**Open verification item.** An earlier version of this page said "a jobserver cancel does not free the worker slot". The sentence did not say whether it meant soft or hard cancel, and it looks stale for both: both the emptied-set path (`_detach_transformation_member`) and the hard path (`_cancel_transformation`) now call `worker.cancel_by_checksum`, and the jobserver unit suite asserts the worker kill on the soft path. **This needs confirmation on a cluster** before it is dropped, for both soft and hard cancel.

**Latent hazard (not a contract statement).** The jobserver's `_run_transformation` handler awaits the shared job task directly (`await entry["task"]`), without shielding it. This is harmless while aiohttp's `handler_cancellation` is off. With `handler_cancellation` enabled, one client disconnecting would cancel its handler, the cancellation would propagate into the shared task, and the job would be killed for every member. That would turn a disconnect into a peer kill, against constraint 2. Anyone enabling that option must first shield the shared task, so that a disconnect can at most deregister its own member.

**The Expression layer's status is in `contracts/expressions.md`.** Three items this page used to list there are stale: the Expression-keyed linger exists, `Expression.softcancel()` exists, and `cancel_expression` is gone (`softcancel_expression` is the module-level entry point). Three other items were carried here in the past: a local-key mismatch that made `Expression.cancel()` a silent no-op for local evaluations, non-interruptible Dask-dispatched Expressions, and the missing fingertip-chain cascade. They are unverified, and `contracts/expressions.md` does not currently list any of them. The first is at least moot as stated, since `Expression.cancel` is retired and raises.

## Non-goals

- **Liveness machinery.** No TTL, no heartbeat, no forced deregistration on disconnect (constraint 2).
- **Hard cancellation of an Expression**, including of the materialization it performs. This is a documented non-feature, not missing work (`contracts/expressions.md`).
- **Making instantaneous local work cancellable.** Deserializing, walking a path, converting and hashing are CPU-bound and cheap; there is no useful interruption point.
- **Changing identity, retry classification, scheduling priority or cache eviction.** Cancellation touches none of them. In particular, a cancelled run leaves its `tf_checksum` meaning exactly what it meant (`contracts/identity-and-caching.md`).
- **Making the first caller special.** It is one member among equals. Anything that gives it ownership of the execution reintroduces the bug this model exists to remove.
