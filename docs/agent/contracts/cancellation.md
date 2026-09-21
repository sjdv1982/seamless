# Cancellation (Contract)

**Cancellation is deregistration from a membership set, not a kill.** Wherever deduplication happens there is a set whose members are the participants who still want a run that has not finished, and exactly two operations act on it: `softcancel` removes one member, and only an emptied set stops the underlying run; `cancel` declares the run *wrong* and kills it for everyone. One pattern, three sites, and the same pattern again one layer down at buffer materialization.

This page is the cancellation substrate **for transformations**. Materialization cancellation — the per-checksum waiting set in the buffer layer, latch-on, the linger, and the fact that there is no hard cancel there at all — belongs to `contracts/expressions.md`; it is pointed at, not restated, in the "one layer down" section below.

**The set's membership *is* the count.** There is no separately maintained integer refcount and no `refholding` flag. This is deliberately a different mechanism, with a different lifetime and a different vocabulary, from the checksum reference lifecycle (`contracts/internal/checksum-reference-lifecycle.md`). One tracks who still wants work that has not finished; the other keeps a buffer alive once it exists. Do not conflate them, and do not call a membership set a refcount.

Code locations:

| Concern | Module / symbol |
|---|---|
| In-process membership set, both operations | `seamless_transformer.transformation_cache` (`TransformationCache`, `_ActiveSubmission`, `_run_active_or_execute`, `_detach_active_member`, `softcancel_by_checksum` and its `_async` form, `_softcancel_leaf`, `cancel_by_checksum`) |
| Handle verb | `seamless_transformer.transformation_class.Transformation` (`cancel`, `cancel_async`, `_cancel_local_futures`, `_mark_cancelled`) — see `contracts/direct-delayed-and-transformation.md` |
| Worker slots | `seamless_transformer.worker` (`cancel_by_checksum`) |
| Server-side set | `seamless-jobserver/jobserver.py` (`_active_transformations`, `_run_transformation`, `_cancel_transformation`, `_transformation_status`); the clients are `seamless_remote.jobserver_remote` and `seamless_remote.jobserver_client` (`softcancel_transformation(tf_checksum, member_id)`, `cancel_transformation(tf_checksum)`) |
| Latch-on set | `seamless_dask.client` (`submit_transformation`, `release_transformation_futures`, `softcancel_by_checksum(tf_checksum, member_id)`, `cancel_by_checksum(tf_checksum)`) over `seamless_dask.types.TransformationFutures` |
| Reactive policy | `seamless_workflow.reactive.Reactive` (`_suspend`, `_expire_run`) and `seamless_workflow.context.Context.prune` — `contracts/workflow-context.md` |
| Materialization layer | `seamless.checksum.expression` (`softcancel_expression`, `cancel_expression`) — `contracts/expressions.md` |
| Contract test suite | `seamless-transformer/tests/cancellation` |

## The pattern

- **Execution is owned by the deduplication site, never by the first caller.** In process, the actual run is a detached background task owned by the transformation cache; **every** participant, the first one included, is a mere awaiter. This decoupling is what makes soft cancellation possible at all: while the first caller owns the execution, cancelling that caller kills the work for everyone.
- A participant **registers on entry and deregisters in `finally`**, which covers normal completion, an exception and task cancellation alike.
- **A pure cache hit is never a member.** It returns before the site is consulted.

The three sites:

| Site | The set | A member is |
|---|---|---|
| **In process** (`seamless-transformer`'s transformation cache) | an awaiter set per `tf_checksum` | a coroutine awaiting the shared submission future |
| **Jobserver** | the same pattern, an independent instance **inside the jobserver** | a latched client process, identified by a member id it sends with its request |
| **Dask** | a first-runner → set-of-latch-on-runners map | a latch-on runner; the first runner is itself a counted **quasi-member** — counted for cancellation and for result delivery, but **not** the lifecycle owner, because the cache/set owns the future reference |

The jobserver having a set of its own is what stops one client's cancel from deleting a sibling client's job.

These three are the **transformation** sites. The same pattern appears twice more outside this page's scope, and both are `contracts/expressions.md`'s: a set per **Expression identity**, whose members are the callers sharing one in-flight evaluation (a standalone `Expression` joins as `id(self)`, the workflow Context as its demand key); and, one layer further down, the per-checksum **waiting set** at a buffer materialization (below). Neither is a `tf_checksum` site, and neither takes a hard cancel.

## The two operations

**`softcancel` — remove this member from the set; if the set is now empty, cancel the underlying run.** Above zero the run continues for the remaining members. On a completed or forgotten checksum it is a no-op.

- **It is pure deregistration: no signal reaches the member being removed.** A softcancel is a member voluntarily leaving because its owner stopped wanting the result, so the whole operation is `set.discard(member)` plus the empty check. A cancellation signal is delivered **only** when the set empties, and **only** to the underlying run.

**`cancel` (hard) — cancel the underlying run outright, and signal and cancel every member.** Unlike softcancel it *does* signal members, because the run is being declared **wrong**, not abandoned.

- Hard cancel means "**this run is wrong and must be killed and resubmitted**": a wrong dunder envelope, or wrong hardware. It does **not** mean "I lost interest".
- **Its cross-tenant reach is correct, not a footgun.** The execution envelope is orthogonal to the `tf_checksum` (`contracts/identity-and-caching.md`), so the same `tf_checksum` may be running under the wrong envelope for every latcher at once, and all of them need it killed and resubmitted. Hard cancel is the deliberate escape hatch for the `strict_dunder` envelope-contention check.
- A wrong *input* is usually a **different** `tf_checksum`, which is unlikely to be shared, so softcancel suffices there.

## Three constraints

1. **Softness composes across layers — this is load-bearing.** The "cancel the underlying run" step inside `softcancel` is itself a **softcancel of the next layer down** when the underlying run is a shared remote submission: an emptied in-process set means *leave the jobserver or Dask set*, never kill it. **A real termination happens only at the leaf set** — the one co-located with the actual executor — when *that* set empties. If an emptied set hard-cancelled the remote instead, the unconditional kill would simply move one process hop downstream and the hazard would be unfixed.
2. **Cross-process membership liveness is deliberately not built.** An in-process set self-cleans through `finally`; a server-side set does not. **A leaked member is benign, and often correct.** It causes *under*-cancellation, never a peer kill: a crashed or disconnected client that never sends a softcancel does not pin a peer's job and corrupts nothing — the job runs to completion and deposits its result in the content-addressed cache, which is usually exactly what the crashed holder needs on reconnect, since a crash is not a statement that the work became uninteresting. TTL heartbeats that forced cancellation on disconnect would destroy work that is still wanted. Connection-scoped auto-deregistration may be taken **where it is free**, but it must not be relied on as a cancellation trigger.
3. **Per-set atomicity.** "Remove the last member → empty → cancel" races "a new submitter wants to latch on", so the membership change and the empty-check-and-cancel are one atomic step under a per-set lock. A lost race merely causes a fresh run to be submitted; it can never corrupt anything, because results come from the content-addressed cache and never from the set.

## Policy: which operation, where

- **The reactive workflow `Context` uses `softcancel` exclusively**, including for node deletion, node supersession, `prune()` and `close()`. The reactive loop only ever *loses interest*, which is precisely softcancel. See `contracts/workflow-context.md`.
- **CLI and SIGINT stay hard.** An explicit command-line cancel means "stop this submitted run now", and prompt slot reclamation is part of that contract.
- **Hard cancellation is checksum-addressed.** It is aimed at a `tf_checksum`, not at a handle, because a wrong run is wrong for everyone holding it.
- **A caller never manages server-side membership directly.** It softcancels its own participation; **each site decides when to actually kill, by its own set.**

## The API

| Name | Meaning |
|---|---|
| `TransformationCache.softcancel_by_checksum(tf_checksum, member=None, *, remote=True)`, and its `_async` form | remove one member; at zero, cancel the cache-owned background task and *leave* the remote set through the remote soft API |
| `TransformationCache.cancel_by_checksum(tf_checksum)` | hard: fail every local awaiter, and hard-cancel worker, Dask and jobserver |
| `Transformation.cancel(*, recursive=False)` / `await Transformation.cancel_async(...)` | a **handle** verb — see below |
| jobserver `softcancel_transformation(tf_checksum, member_id)` / `cancel_transformation(tf_checksum)` | the same two operations on the server-side set |
| Dask `softcancel_by_checksum(tf_checksum, member_id)` / `cancel_by_checksum(tf_checksum)` | the same two operations on the latch-on set |

**A handle verb and a substrate verb are not the same thing.** `contracts/expressions.md` states the substrate vocabulary — `softcancel` means deregister, `cancel` means hard kill — and that rule governs the **checksum-addressed** API above. A **handle**'s `.cancel()` means "this handle gives up": it makes *that* handle terminal and softcancels its participation, leaving the shared run alive for every other member.

So `Transformation.cancel()`:

- marks the handle terminal — `status` reports canceled, `result_checksum` raises, and `clear_exception()` does **not** revive it; a retry needs a new handle;
- **softcancels this handle's participation** in the shared run, which continues for any other member;
- returns `True` if it transitioned active work (or a local promise) to canceled, `False` if nothing was active;
- with `recursive=True`, cascades the **same soft semantics** to known upstream dependency handles;
- **never invalidates the `tf_checksum`.** A later submission of the same checksum is a new submission, latching on or starting fresh as usual.

An `Expression` handle has nothing terminal to mark, which is why its only verb is `softcancel()` (`contracts/expressions.md`).

## What cancellation is *not* for

- **Not for correctness.** Results are content-addressed, so a late result is *unwanted*, never *wrong*; and because cancellation is best-effort, the Context must ignore late results from superseded runs in any case. The value of a cancel is exactly: remaining resource cost × the chance that nobody else wants the output.
- **Not a state to clear.** There is no cancelled state that must be reset before work can proceed; a caller that changes its mind asks again. (A *handle* made terminal by `.cancel()` is the handle's own state, not the substrate's.)
- **Not a guarantee that the work stopped.** A softcancel that returns `True` means "I was registered and have now left", and nothing more.

## Materialization is the same pattern, one layer down

Buffer materialization — a remote fetch of a buffer, which Expression evaluation, transformation input resolution, `.buffer` reads and attachment deliveries all share (`contracts/attachments.md`: a delivery resolves through `Checksum.resolution()` and never fingertips) — has its **own waiting set, keyed by checksum, at the materialization site in the buffer layer**. `contracts/expressions.md` specifies it, including latch-on and the linger; this page does not repeat it. Three consequences matter here:

- the same membership model applies, so a fetch shared with a live requester survives another requester's departure;
- there is **no hard cancel at that layer at all**, by design, so a hard `cancel_by_checksum` has no materialization counterpart;
- an abandoned **fingertip chain** deregisters softly down every step, and a step shared with a live chain survives — the membership model of this page, applied one layer down. The leaf Transformation needs no special case: the linger keeps its member registered, and it is killed only when its own set empties, which is this page's softness-cascades rule reaching the leaf.

Two premises of that layer are worth carrying back here, because they are what make it a *different* mechanism rather than a copy of this one: a materialization's cost is **unbounded** (a fingertip chain may contain Transformations), and a materialization's chance that **nobody else wants the output is low** — sibling projections, a Transformation over the same checksum, and a revert all want the same buffer. That is why the buffer layer adds latch-on and a linger, which this page's transformation sites do not have.

Vocabulary: that set is a **waiting set**, never a refcount.

## Implementation status and current limitations

Settled contract that the code does not yet implement, or implements differently. Where a design document and the code disagree, **the code wins**, and the disagreement is listed here.

The in-process substrate is **delivered and verified** by a contract-driven suite at `seamless-transformer/tests/cancellation` (a README charter, a shared harness, in-process files, and remote multi-tenant jobserver and Dask files). The suite's README describes the two gaps below as `xfail(strict=False)`, but that is a description, not a fact about the test files: `test_jobserver_both_softcancel_leaf_kill` and `test_dask_first_runner_softcancel_latcher_survives` carry no `@pytest.mark.xfail` decorator and no dynamic xfail marking anywhere in `seamless-transformer/tests/cancellation/`, so running the suite today surfaces them as plain failures, not xfails. Verified in process: deduplication; softcancel as deregistration with peer survival; softcancel at zero cancelling the underlying run; a cache hit never becoming a member; hard cancel as kill-all; `strict_dunder` envelope rejection; and per-set atomicity. Verified across processes: jobserver deduplication, jobserver softcancel with peer survival, hard cross-tenant cancel, and the benign crashed-member case; Dask deduplication, latch-on-runner softcancel leaving the first runner alive, and hard cross-tenant cancel.

Two gaps remain, both at the server boundary; their in-process equivalents pass.

- **The jobserver soft cascade does not reach the leaf.** A local `cancel()` detaches the local awaiter but sends **no server-side deregistration**; the jobserver log shows the job attached and completed with no cancel message, so an all-soft-cancelled jobserver job runs to completion. Only a hard `cancel_by_checksum` stops a jobserver job. This is **under-cancellation, so it is benign** by constraint 2 — it wastes a slot; it never kills a peer.
- **A Dask first-runner softcancel kills its latchers.** When the first runner softcancels, a latcher receives `TransformationError("Transformation was canceled")` instead of the result, because the shared future is released out from under it: across separate client processes the set does not yet own the future. This one is **not benign** — it is a wrong answer to a caller that never asked to stop.

Also:

- **A jobserver cancel does not free the worker slot.**
- The **Expression and materialization layer** has an implementation-status list of its own — the local-key mismatch that makes `Expression.cancel()` a silent no-op for local evaluations, the missing linger, `Expression.softcancel()` not existing yet, `cancel_expression` still being an alias, non-interruptible Dask-dispatched Expressions, and the missing fingertip-chain cascade. It is in `contracts/expressions.md` and is not duplicated here.

## Non-goals

- **Liveness machinery.** No TTL, no heartbeat, no forced deregistration on disconnect (constraint 2).
- **Hard cancellation of a materialization**, and hard cancellation of an Expression: documented non-features, not missing work (`contracts/expressions.md`).
- **Making instantaneous local work cancellable.** Deserializing, walking a path, converting and hashing are CPU-bound and cheap; there is no useful interruption point.
- **Changing identity, retry classification, scheduling priority or cache eviction.** Cancellation touches none of them; in particular a cancelled run leaves its `tf_checksum` meaning exactly what it meant (`contracts/identity-and-caching.md`).
- **Making the first caller special.** It is one member among equals; anything that gives it ownership of the execution reintroduces the bug this model exists to remove.
