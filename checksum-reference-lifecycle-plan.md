# Checksum Reference Lifecycle Plan

## 1. Purpose

Seamless uses integer reference counts to keep checksum-addressed buffers locally
available for as long as a live object promises that it can use or expose them.
Reference counting has two distinct layers:

1. **Per-object lifecycle management** acquires and releases references during normal
   operation.
2. **Global lifecycle collection and audit** runs during `seamless.close()` and at
   interpreter shutdown. It releases all still-live Seamless refholders, verifies that
   every `incref` was matched by exactly one `decref`, and reports lifecycle bugs.

The global collector is a safety net and auditor. It is not a substitute for correct
per-object ownership.

This plan deliberately retains **integer refcounts**. Holder bookkeeping is additional
diagnostic information: the integer is the retention count, while holder records explain
which objects contributed to it and identify an invalid decrement.

## 2. Scope

This plan covers normal buffer-cache references held by:

- standalone `Cell` objects;
- immutable `Expression` objects where they explicitly retain an observable result (ordinary
  expression inputs use tempref-backed immediate evaluation, not normal references);
- standalone `Transformer` builders;
- concrete `Transformation` objects;
- workflow `Context` nodes, including cell values, transformer-pin literals, and current
  cell/transformer results;
- process-global managers such as `CodeManager`;
- explicit user calls to `Buffer.incref()` or `Checksum.incref()`.

It also covers dependency-result handoff between an `Expression` or `Transformation` and
a downstream `Transformation`.

Temporary references remain a separate, decaying cache-interest mechanism. They are not
included in the normal-reference balance report. Remote durability is also orthogonal:
the existence of a remote copy does not satisfy a live object's local reference contract.

Running-transformation awaiter sets and cancellation ownership are out of scope except
where shutdown ordering must release their buffer references before the audit.

## 3. Terminology

**Checksum**
: A content address. A bare `Checksum` is not itself a reference holder.

**Normal reference**
: One unit in an integer refcount. While the count is positive, the buffer-cache entry and
  its local buffer must not be discarded by normal eviction.

**Temporary reference**
: Decaying interest used for cache convergence, completed results that nobody promises to
  retain, and other best-effort availability. Expiry is valid and is not a lifecycle bug.

**Holder**
: An object or subsystem responsible for one or more normal-reference units. A holder is
  represented diagnostically by a stable token and descriptive metadata; it is not a
  lease object and does not replace the integer count.

**Role**
: The reason a holder retains a checksum, for example `cell.input`, `transformer.pin:x`,
  `transformation.input:x`, `transformation.result`, or `workflow:sub.tf.result`.

**Underflow / over-decrement**
: A `decref` for which the named holder has no matching reference. The decrement must be
  rejected and recorded; it must never consume another holder's reference.

**Leak / undecremented reference**
: A positive normal reference remaining after global lifecycle collection.

## 4. Contract

### 4.1 Fundamental invariant

Every live object that promises future local materialization of a checksum owns one normal
reference for the duration of that promise.

For every checksum `C`:

```text
normal_refcount[C] == sum(
    holder.references[C, role]
    for every registered holder and role
) >= 0
```

The equality must hold after every atomic `incref` or `decref`. Holder-registry counters
explain the integer; they do not replace it.

### 4.2 Acquisition and release

- Acquisition is explicit and atomic with publishing the new object state.
- Replacement acquires the new checksum before releasing the old checksum. This keeps
  same-checksum replacement safe and gives exception-safe mutation.
- Deletion, explicit `close()`/`destroy()`, replacement, and `__del__` all converge on one
  idempotent release method.
- Copying or snapshotting creates an independent owner and therefore increments again.
  Ownership is never transferred implicitly.
- Serialization stores checksums but owns no process-local references. Deserialization
  into a live object acquires fresh references.
- Repeated destruction is a no-op at the object layer. It must not issue a second
  `decref`.
- A failed acquisition must not be entered into object state or holder bookkeeping.
- A failed release is a lifecycle error and must be recorded without changing the global
  integer count.

### 4.3 Holder attribution

Each refholding object receives a monotonically allocated holder ID. Do not use `id(obj)`
as the sole identity because Python may reuse it. Holder metadata contains only immutable
diagnostics and must not keep the object alive:

```python
@dataclass(frozen=True)
class ReferenceHolder:
    holder_id: int
    kind: str             # e.g. "Expression", "Transformation", "Context"
    label: str | None     # path/name when known
```

Every registered holder contains a `Counter[tuple[Checksum, str]]`. A holder may own
multiple units for distinct roles or repeated manual increments:

```text
holder.references[checksum, role] -> positive integer
```

The weak registry can aggregate these counters by checksum for the final report. This
permits reports to name both the object and the field/pin/result responsible for a leak
without duplicating a holder map inside every buffer-cache entry.

If a holder dies incorrectly without decrementing, it disappears from the weak registry and
cannot be named later. This is acceptable. At shutdown, its leaked count appears as the
difference between the cache's integer count and the sum attributed to holders that are
still alive. The report lists those live holders, if any, and labels the excess count as
unattributed; it must not retain dead-holder tombstones merely to improve diagnostics.

### 4.4 Decrement validation

`decref(checksum, holder, role)` performs these checks under the same lifecycle lock:

1. Does the live holder's local counter own a positive count for `(checksum, role)`?
2. Is the checksum's total integer count positive?
3. Would decrementing preserve the cache-integer/registry-sum invariant?

If any check fails:

- do not decrement or clamp the integer;
- record an `OverDecrefEvent` with the checksum, attempted holder and role, current count,
  and current holders;
- return `False`;
- optionally print immediately in debug mode, but always include it in the final audit.

This is stricter than merely testing whether the checksum has *some* reference: one holder
must never consume a sibling holder's reference.

### 4.5 Raw public `incref` compatibility

Internal Seamless calls must always pass an attributed holder and role.

Existing public calls remain source-compatible:

```python
checksum.incref()
checksum.decref()
buffer.incref()
buffer.decref()
```

Unattributed calls use a distinguished `manual/unattributed` holder. They still participate
in integer accounting and final leak reporting. Add optional keyword-only attribution for
advanced callers:

```python
checksum.incref(holder=holder, role="application-cache")
checksum.decref(holder=holder, role="application-cache")
```

`Buffer` may lazily create a per-instance manual holder so `buffer.incref()` and
`buffer.decref()` can be attributed to that buffer. A bare `Checksum` remains a value
object and does not silently become a holder merely by being constructed.

### 4.6 Scratch data

Scratch controls persistence/remote registration, not object ownership. A live holder that
promises scratch data remains locally available must take a normal reference with
`scratch=True`. It must not substitute a decaying tempref for a required lifetime.

The current `PreTransformation._to_checksum` path mixes these concepts: scratch inputs can
receive only a tempref but are still appended to `_value_refs`, whose cleanup calls
`decref`. Replace that with explicit normal scratch references or keep tempref-only entries
out of the normal-reference list.

### 4.7 Eviction

A positive normal refcount is a non-eviction guarantee. Cache eviction may expire temprefs
and remove zero-normal-ref entries, but it must not delete the accounting or buffer for an
entry with `normal_refcount > 0`.

The eviction candidate set must therefore exclude normal-refheld entries. If the hard cap
cannot be met because all remaining buffers have normal references, report memory pressure;
do not erase the refcount. This is required for both correctness and a trustworthy final
audit.

## 5. Ownership matrix

| Object/subsystem | Checksums it owns | Release point |
|---|---|---|
| Bare `Checksum` | none | n/a |
| `Buffer` | only explicit manual increments | matching manual decrement or global audit |
| Standalone `Cell` | concrete checksum input needed by future `build`/`compute` | input replacement, destruction, shutdown collection |
| `Expression` | no normal input reference; only an explicitly retained observable result, if the API provides one | result replacement, destruction, shutdown collection |
| Standalone `Transformer` builder | checksum-bound pins and any checksum-only code/module inputs | pin/code replacement or deletion, destruction, shutdown collection |
| `Transformation` | direct concrete inputs, resolved dependency results, and constructed transformation checksum while needed; a result only when explicit user interest is represented by this object/API | input no longer needed, destruction, shutdown collection |
| `CodeManager` | semantic/syntactic code checksums represented by its integer maps | manager decrement and shutdown hook |
| Workflow `Context` | cell literal producers, transformer-pin literals, current node results, and any retained superseded results | mutation, node deletion, graph replacement, context destruction, shutdown collection |
| Bound workflow `Cell`/`Transformer` handle | none; it is an ephemeral view | n/a |

Two live owners of the same checksum contribute two references. Deduplication across owners
is incorrect; independent owners must be independently releasable.

Within one object, count ownership by semantic role. If the same checksum is both an input
and a result, two role entries are acceptable and make mutation logic auditable.

## 6. Dependency handoff contract

Dependency handoff must have no interval in which a required result has no owner.

### 6.1 Expression input

An `Expression` does **not** acquire a normal reference to its checksum input. Expression
evaluation is cheap and starts immediately once an input becomes concrete. The producer or
input serialization supplies a tempref whose expiry horizon is on the order of dozens of
seconds or longer, which is ample for this immediate evaluation and cache handoff.

An Expression deliberately kept dormant beyond that tempref horizon does not create
indefinite retention merely by existing. It may resolve the input from durable storage,
fingertip/recompute it when provenance permits, or report a cache miss according to the
availability policy. `.item()`, `.slice()`, `.as_celltype()`, and `dataclasses.replace` do
not increment the input checksum.

Validator checksums follow the same rule if validation happens as part of immediate
evaluation. A separately configured validator object that promises availability while
dormant must define its own ownership; the Expression should not retain it implicitly.

### 6.2 Dependency handoff by dependent type

When a downstream `Transformation` resolves an `Expression` dependency:

1. the input's existing tempref covers the cheap, immediate Expression evaluation;
2. evaluation creates or discovers a result checksum with a fresh temporary producer hold;
3. before that result tempref can expire, the downstream `Transformation` acquires a normal
   reference under `dependency-result:<pin>`;
4. only then may execution be deferred;
5. the downstream transformation releases that reference on destruction or after it no
   longer promises it can execute/re-execute.

The current `_prepared_dict_with_dependencies` logic injects dependency result checksums
without adding them to the transformation's normal input refs. Correct that path explicitly.

When the dependent is another `Expression`, it does not acquire a normal input reference.
Instead, make or refresh the input checksum's tempref and immediately evaluate the dependent
Expression. Every Expression in a chain produces/refreshed a tempref for its own result, so
the cheap chain remains covered without normal references.

Thus “the dependent holds its input” has two concrete meanings:

- dependent `Transformation`: normal `incref`, because it may wait for other inputs;
- dependent `Expression`: fresh/refreshed tempref followed by immediate evaluation.

### 6.3 Explicit result interest

A completed Expression or Transformation result receives a tempref with the normal
dozens-of-seconds-or-longer handoff horizon. It does not automatically receive a normal
reference merely because its producer stores or returns the checksum.

If only a dependent is interested, apply §6.2 as soon as the checksum becomes concrete. No
producer-side normal result reference is needed.

An explicit public call to an Expression or Transformation's `compute()` / `compute_async()`
or `run()` / `task()` marks that producer's result as user-interesting. The object takes one
normal result reference when the result checksum is concrete and keeps it until destruction
or explicit result release. Repeated explicit calls do not increment repeatedly: result
interest is a boolean lifecycle state per producing object.

Set explicit interest immediately upon entry to the public call:

- if no result exists yet, eventual successful completion notices the flag and increfs once;
- if an implicit dependency evaluation completed earlier, the explicit call finds the
  existing checksum and increfs it immediately;
- if no checksum exists because evaluation failed or was cancelled, there is nothing to
  hold. The interest flag may remain set so a later successful retry acquires its result.

These are the same rule applied at different object states; the already-complete case does
not contradict marking interest at public-call entry.

Evaluation initiated solely by a dependent uses an internal origin-aware call and does not
set explicit result interest. Current internal code that calls public `compute()` must be
changed so it cannot accidentally make a dependency-only result user-held.

A standalone `Cell`, workflow Context result, explicit manual `incref`, or another holder
may independently express interest in the same result. Each owner contributes its own
integer reference.

In a workflow, the `Context` node independently acquires the current result before
publishing `node.current_checksum`, because the workflow exposes that current result as
observable state. Superseding or deleting the node releases the Context's current-result
reference according to the runtime retention policy.

## 7. Core implementation

### 7.1 Buffer-cache state

Keep normal-reference state under `BufferCache.lock` and add a weak holder registry guarded
by the same lock (or by one outer lifecycle lock that always encloses cache mutation):

```python
@dataclass
class StrongEntry:
    buffer: Buffer | None
    size: int | None
    normal_refs: int = 0
    tempref: TempRef | None = None
    ...

@dataclass(frozen=True)
class OverDecrefEvent:
    checksum: str
    holder: ReferenceHolder
    role: str
    normal_refs: int
    current_holders: tuple[HolderCount, ...]
```

Each live holder stores its own checksum/role counter. During normal mutation, assert that
the cache integer is not lower than the aggregate count from currently live holders:

```python
assert entry.normal_refs >= sum(
    holder._checksum_refs[checksum, role]
    for holder in reference_holders
    for role in holder._roles_for(checksum)
)
```

Equality is checked by the final audit. A greater cache integer is possible only after a
holder has died without decrementing or through unattributed/manual ownership; preserve
that discrepancy for the shutdown audit.
For zero-ref entries removed from `strong_cache`, no live holder should retain that
checksum. Preserve over-decrement events in a bounded process-level list until the final
audit. Do not preserve successful zeroed histories by default.

### 7.2 Atomic API

The conceptual implementation atomically updates the cache integer and the live holder's
local counter:

```python
def incref(self, checksum, *, buffer=None, scratch=False, holder, role):
    with self.lock:
        entry = self._ensure_strong_entry(checksum, buffer, scratch=scratch)
        self.reference_holders.require(holder)
        entry.normal_refs += 1
        holder._checksum_refs[checksum, role] += 1
        self._assert_ref_invariant(checksum, entry)

def decref(self, checksum, *, holder, role) -> bool:
    with self.lock:
        entry = self.strong_cache.get(checksum)
        registered = holder in self.reference_holders
        key = (checksum, role)
        if (
            not registered
            or holder._checksum_refs[key] == 0
            or entry is None
            or entry.normal_refs == 0
        ):
            self._record_over_decref(checksum, holder, role, entry)
            return False
        holder._checksum_refs[key] -= 1
        if holder._checksum_refs[key] == 0:
            del holder._checksum_refs[key]
        entry.normal_refs -= 1
        self._assert_ref_invariant(checksum, entry)
        if entry.normal_refs == 0 and entry.tempref is None:
            self._demote(checksum, entry)
        return True
```

Production code should retain backward-compatible defaults for public manual calls, while
internal helper functions require explicit attribution.

### 7.3 Per-object integer bookkeeping

Each refholder stores its stable metadata/token and its integer checksum/role counter. No
lease objects are introduced:

```python
self._refholder = new_reference_holder("Expression", label)
self._checksum_refs: Counter[tuple[Checksum, str]] = Counter()
```

Shared helpers update cache and holder counters atomically. The release-all operation is
idempotent at the object layer:

```python
def _release_checksum_refs(self):
    if self._checksum_refs_releasing or self._checksum_refs_released:
        return
    self._checksum_refs_releasing = True
    try:
        refs = tuple(self._checksum_refs.items())
        for (checksum, role), count in refs:
            for _ in range(count):
                checksum.decref(holder=self, role=role)
    finally:
        self._checksum_refs_releasing = False
        self._checksum_refs_released = not self._checksum_refs
```

The re-entry flag prevents double release while leaving the live counter available for
`decref` validation. Cleanup catches individual failures and continues so the final report
sees the complete state. A fully emptied counter marks the object released.

### 7.4 Refholder registry

Maintain a process-global weak registry of live refholding objects. It exists to invoke
idempotent release during `seamless.close()` and attribute counts held by objects that are
still alive. It must not prolong object lifetime.

A `WeakValueDictionary[holder_id, object]` is preferable to relying on object equality and
hashing in `WeakSet`, but either is valid if membership is identity-based. Traversing its
live values is the only operation required for attribution and global collection.

Registry entries contain:

- the weakly held object, which exposes its immutable holder metadata;
- its checksum/role integer counter;
- optional creation traceback only when `SEAMLESS_REF_DEBUG=1`.

Classes using `slots` must support weak references (`__weakref__` or
`weakref_slot=True`). Ordinary weak-registry removal is silent. A holder that disappears
without decrementing is detected later as an unattributed excess in the cache integer.

## 8. Class-by-class changes

### 8.1 `seamless-core`

**`Cell`**

- Acquire concrete checksum inputs in `__init__`, `input_ref` assignment, and derived-copy
  construction.
- Release on input replacement and destruction.
- Do not treat ordinary literal inputs as checksum holds unless the existing API already
  classifies them as checksums.
- A bound workflow Cell delegates ownership to the Context and acquires nothing itself.

**`Expression`**

- Do not acquire normal references for concrete inputs or validators.
- Ensure evaluation refreshes or creates suitable temprefs for its result before returning
  the checksum to a downstream handoff.
- Add hidden execution/interest and holder/counter state excluded from equality, hash,
  identity keys, repr, and serialization.
- Public `compute`/`compute_async`/`run` sets result interest; internal dependency evaluation
  does not. Acquire the result once it is concrete when that flag is set.
- An explicit `result` passed through `with_result` is ref-neutral unless the API separately
  documents it as observable user interest; the public-call flag remains authoritative.
- `replace`-based derivations remain ref-neutral unless they copy an explicitly owned
  result-interest state, which they should not do by default.
- Release explicit result ownership idempotently in `__del__` and shutdown collection.

**`BufferCache` / `Checksum` / `Buffer`**

- Add holder-aware integer accounting and audit APIs.
- Fix eviction so positive normal refs cannot disappear.
- Keep public manual APIs compatible while migrating every internal call to attributed
  ownership.

### 8.2 `seamless-transformer`

**Standalone `Transformer` builder**

- Add one holder token and a local counter.
- Acquire checksum-bound pin values when configured.
- Release on pin replacement/deletion and object destruction.
- A builder snapshot/concrete `Transformation` independently acquires the checksums it
  needs; calling a builder does not transfer or reduce the builder's ownership because the
  reusable builder still promises it can be called again.
- A Context-bound builder handle owns nothing; its backend routes mutation to Context.

**`PreTransformation` and `Transformation`**

- Replace `_value_refs: list[Checksum]` with role-aware integer bookkeeping.
- Attribute direct inputs by pin.
- Acquire resolved dependency result checksums before publishing a constructed execution
  dictionary.
- Acquire `_transformation_checksum` for as long as later execution needs its buffer.
- Give completed `_result_checksum` a suitable tempref before publishing it. Acquire a
  normal result reference exactly once when the public-call result-interest flag is set;
  dependency-only results are handled according to the downstream type instead.
- Split public evaluation from internal dependency evaluation with an origin/interest flag;
  internal code must not signal user interest by calling the public `compute()` method.
- Release all owned inputs/results/code-related refs exactly once on destruction or explicit
  close.
- Keep `PreTransformation.release()` idempotent. Consolidate ownership so both
  `Transformation.__del__` and `PreTransformation.__del__` cannot race or obscure which
  object owns a count.
- Preserve separate `CodeManager` integer counts, but register its holder identity and roles
  in the same global audit.

### 8.3 `seamless-workflow`

Refactor the Context's current `_checksum_holds` integer map to holder-attributed cache
calls while preserving one Context-owned integer per producer/result role.

- Literal cell producer: `cell:<path>:literal`.
- Literal transformer pin: `transformer:<path>:pin:<name>`.
- Current cell result: `cell:<path>:result`.
- Current transformer result: `transformer:<path>:result`.
- Retained superseded result: include generation and hold kind.

Mutation rules:

- acquire new producer/result before publishing it;
- release replaced producer/result immediately;
- connections release displaced literal producers;
- node deletion releases all node-owned roles;
- `set_graph` releases old graph ownership, then newly loaded nodes acquire their own refs;
- subcontext copy independently increments copied producers/results as appropriate;
- Context destruction releases everything idempotently;
- bound handles never increment or decrement.

Do not serialize holder IDs or runtime refcounts in `get_graph()`.

## 9. Global collection and audit

### 9.1 Shutdown ordering

Integrate reference collection into `seamless.close()` after new work is prohibited but
before buffer-cache teardown:

1. Mark Seamless closed to new operations.
2. Cancel/settle running local and remote work.
3. Traverse the weak holder registry and build an immutable pre-cleanup reverse index:

   ```text
   checksum -> {(holder, role): count}
   ```

   Include live object holders, process-global holders, and the manual/unattributed holder.
   This snapshot preserves attribution even when subsequent cleanup clears live holder
   counters.
4. Snapshot the cache's integer normal refcounts and compare them with the reverse index
   before cleanup:

   - `actual == known`: all current references are attributed;
   - `actual > known`: record `actual - known` leaked/unattributed references, potentially
     from holders that died incorrectly, and list the holders still alive for that checksum;
   - `actual < known`: record missing references/over-decrement or accounting corruption and
     list the live holders that still believe they own references.

   Any positive `manual/unattributed` holder count is also a lifecycle leak: unlike a
   registered object owner, it has no automatic destruction contract that legitimately
   defers its matching decrement to global collection.
5. Flush required buffers while their owners still retain them.
6. Invoke shutdown hooks for transformation caches, `CodeManager`, workflow runtimes, and
   other process-global holders.
7. Ask every live weak-registered object refholder to run its idempotent release method.
   Do not silently release manual/unattributed counts; preserve them for the report and the
   final forced-cleanup phase.
8. Run `gc.collect()` at least twice, allowing cycles and finalizers exposed by the first
   pass to settle.
9. Snapshot the post-cleanup buffer-cache integer counts, remaining holder counters, and accumulated
   over-decrement events.
10. Validate all integer/live-holder-sum invariants. Use the pre-cleanup reverse index to name the
   likely responsible holders if cleanup erased or corrupted the post-cleanup attribution.
11. Emit and store the final audit report. It includes both pre-cleanup attribution errors
    and post-cleanup residuals; successful automatic cleanup does not erase earlier evidence.
12. After reporting, force-clear any residual cache refs so process shutdown cannot hang or
    retain memory. Mark the tracker finalized so later Python destructors no-op rather than
    generating secondary underflow noise.

Explicit `seamless.close()` and atexit use the same collector. Atexit remains best-effort,
but reference bugs are not suppressed merely because collection was initiated by atexit.

### 9.2 Report model

Provide a programmatic immutable report:

```python
@dataclass(frozen=True)
class ReferenceAuditReport:
    balanced: bool
    pre_cleanup_normal_ref_total: int
    pre_cleanup_mismatches: tuple[CountMismatch, ...]
    manual_leaks: tuple[LeakedChecksum, ...]
    post_cleanup_residuals: tuple[LeakedChecksum, ...]
    over_decrefs: tuple[OverDecrefEvent, ...]
    cleanup_failures: tuple[CleanupFailure, ...]

@dataclass(frozen=True)
class LeakedChecksum:
    checksum: str
    count: int
    holders: tuple[HolderCount, ...]

@dataclass(frozen=True)
class CountMismatch:
    checksum: str
    actual_count: int
    live_holder_count: int
    unattributed_count: int
    live_holders: tuple[HolderCount, ...]
```

The report is balanced only when:

- the pre-cleanup cache integers match the live-holder sums;
- no manual/unattributed reference is still open;
- no positive normal refs remain after registered-holder collection;
- no over-decrement event occurred;
- no refholder cleanup failed.

Store the last report for tests and applications:

```python
seamless.get_last_reference_audit() -> ReferenceAuditReport | None
```

Optionally expose a non-destructive diagnostic snapshot before shutdown:

```python
seamless.reference_status() -> ReferenceStatus
```

It must be clearly named as a status snapshot, not a leak audit, because positive refs are
expected while objects are alive.

The audit core should remain small and deterministic. Conceptually:

```python
def collect_reference_audit() -> ReferenceAuditReport:
    live_holders = tuple(reference_holders.values())

    checksum_to_holders = defaultdict(Counter)
    for holder in live_holders:
        for (checksum, role), count in holder._checksum_refs.items():
            checksum_to_holders[checksum][holder._refholder, role] += count

    actual_before = buffer_cache.normal_refcounts()
    mismatches = []
    for checksum in actual_before.keys() | checksum_to_holders.keys():
        actual = actual_before.get(checksum, 0)
        known = sum(checksum_to_holders[checksum].values())
        if actual != known:
            mismatches.append(
                CountMismatch(
                    checksum=checksum.hex(),
                    actual_count=actual,
                    live_holder_count=known,
                    unattributed_count=actual - known,
                    live_holders=freeze(checksum_to_holders[checksum]),
                )
            )

    manual_leaks = snapshot_manual_refs(checksum_to_holders)

    cleanup_failures = []
    for holder in live_holders:
        if holder is MANUAL_HOLDER:
            continue
        try:
            holder._release_checksum_refs()
        except BaseException as exc:
            cleanup_failures.append(describe_cleanup_failure(holder, exc))

    gc.collect()
    gc.collect()
    residuals = snapshot_positive_normal_refs(buffer_cache, checksum_to_holders)

    return ReferenceAuditReport(
        balanced=not (
            mismatches
            or manual_leaks
            or residuals
            or over_decref_events
            or cleanup_failures
        ),
        pre_cleanup_normal_ref_total=sum(actual_before.values()),
        pre_cleanup_mismatches=tuple(sorted(mismatches, key=mismatch_key)),
        manual_leaks=tuple(sorted(manual_leaks, key=leak_key)),
        post_cleanup_residuals=tuple(sorted(residuals, key=leak_key)),
        over_decrefs=tuple(over_decref_events),
        cleanup_failures=tuple(cleanup_failures),
    )
```

The production function must take snapshots and mutate counts under the lifecycle/cache
lock, but it must not hold that lock while invoking arbitrary holder cleanup methods or
`gc.collect()`.

### 9.3 Human-readable final report

Print nothing when balanced. On failure, print one deterministic stderr report, sorted by
checksum, holder kind/ID, and role. Example:

```text
[seamless.references] checksum reference lifecycle errors
  leaked normal references: 2 across 1 checksum
  checksum 8f...21: count=2
    holder Transformation#17 (pipeline.normalize), role=dependency-result:input: 1
    holder Transformation#24 (normalize), role=dependency-result:data: 1
  over-decrements: 1
  checksum 31...af:
    attempted by Context#9 (ctx), role=transformer:tf:pin:x
    available count=0; holders=none
```

If holder counters and the integer disagree, print both values prominently; this is an
internal accounting corruption, not an ordinary leak.

Creation tracebacks are appended only in reference-debug mode to avoid routine memory and
runtime cost.

### 9.4 Forced cleanup semantics

Forced cleanup happens only after the immutable report has been created. It must not mutate
the report or turn a failed audit into a passing one. Its purpose is deterministic process
cleanup, not concealment.

## 10. Migration strategy

Implement in stages so each repository remains testable:

1. **Core accounting foundation**
   - holder IDs/metadata;
   - integer plus holder counters;
   - over-decrement event recording;
   - eviction correction;
   - status/audit snapshot APIs.
2. **Core object ownership**
   - standalone `Cell` lifecycle and Expression tempref contract;
   - weak refholder registry;
   - copy/replace/destructor behavior.
3. **Transformer ownership**
   - standalone builder pins;
   - direct inputs and scratch semantics;
   - dependency-result handoff;
   - transformation result and transformation-checksum ownership;
   - `CodeManager` attribution.
4. **Workflow ownership**
   - migrate existing producer holds;
   - add current and retained-result holds;
   - mutation/load/copy/destruction paths.
5. **Global collector and report**
   - shutdown ordering;
   - weak-registry collection;
   - immutable report and deterministic formatting;
   - forced post-report cleanup.
6. **Audit all call sites**
   - search every repository for `incref`, `decref`, and direct normal-ref mutation;
   - require an explicit holder/role for internal calls;
   - document any intentional unattributed public/manual use.

Do not temporarily make `decref` clamp or silently steal another holder's count during the
migration. Missing attribution should use the explicit unattributed holder until migrated.

## 11. Tests

### 11.1 Buffer-cache accounting

- integer count equals holder-counter sum after every operation;
- two holders of one checksum increment to two and release independently;
- a holder cannot decrement another holder's reference;
- over-decrement returns `False`, records one event, and leaves the count unchanged;
- repeated valid increments from one holder are counted correctly;
- zero-ref demotion preserves buffer weak caching;
- eviction never removes an entry with positive normal refs;
- mixed scratch/non-scratch holders preserve correct retention and remote-registration
  policy;
- concurrent increments/decrements remain atomic.

### 11.2 Standalone objects

- a checksum-backed Cell survives forced tempref expiry;
- replacing or deleting its input releases exactly once;
- derived Cells own independent refs; derived Expressions do not acquire normal input refs;
- Expression evaluation succeeds within an artificially shortened but nonzero tempref
  handoff window;
- an intentionally dormant Expression does not keep its input normal-refheld;
- an uncalled Transformer builder retains checksum-bound pins;
- builder pin replacement/deletion releases old refs;
- calling a reusable builder gives the Transformation an independent ref;
- destroying builder and Transformation in either order is balanced;
- cycles are collected and released.

### 11.3 Transformation dependency handoff

- an Expression result survives an artificial delay before downstream Transformation
  execution because the Transformation normal-refholds it immediately;
- an Expression-to-Expression handoff refreshes the tempref and evaluates immediately,
  without changing the normal count;
- upstream Transformation result survives downstream construction/execution;
- a concrete Transformation result is tempref-backed by default and does not survive expiry
  merely because the producer object lives after implicit dependency evaluation;
- explicit public compute/run makes an Expression or Transformation retain its result once;
- repeated explicit calls do not multiply the result reference;
- implicit completion followed by explicit compute/run acquires the already concrete result;
- deleting the producer does not invalidate an independently holding downstream consumer;
- scratch inputs/results obey live-owner guarantees without remote registration;
- success, exception, cancellation, clear-exception, and destructor paths all balance.

### 11.4 Workflows

- literal cells and transformer pins retain and release as already tested;
- current cell and transformer results remain available after forced tempref expiry;
- result replacement/supersession releases according to policy;
- node deletion, graph replacement, subcontext copy, and Context destruction balance;
- bound handle creation/destruction does not change counts;
- same checksum in multiple nodes produces matching independent counts;
- externally induced underflow names the Context path and role.

### 11.5 Final audit

- a balanced script prints no reference warning and returns `balanced=True`;
- a deliberately leaked manual incref reports checksum, count, and manual holder;
- an undeleted standalone owner is released by global collection and does not report as a
  leak if cleanup succeeds;
- a holder that dies without decrementing produces an unattributed positive difference;
  any other live holders of that checksum are still listed;
- the weak registry itself never keeps a holder alive;
- a deliberately broken owner that fails cleanup is reported;
- an over-decrement is reported even if all final counts are zero;
- an integer/holder mismatch is reported as accounting corruption;
- report ordering and formatting are deterministic;
- forced cleanup occurs after snapshot and does not alter the stored report;
- explicit `seamless.close()` and atexit exercise the same audit logic;
- shutdown remains idempotent.

## 12. Acceptance criteria

The work is complete when:

- every internal normal `incref` and `decref` is attributed to a holder and role;
- standalone and workflow objects retain every checksum they promise to materialize later;
- dependency handoff has no unowned interval;
- positive normal refs prevent eviction;
- all object cleanup paths are idempotent and balanced;
- shutdown produces no output for a balanced run;
- leaks, over-decrements, cleanup failures, and count mismatches produce a deterministic
  report naming the responsible holders;
- the final report is available programmatically;
- all component suites pass in the `seamless1` conda environment, including forced
  tempref-expiry and cyclic-GC tests.
