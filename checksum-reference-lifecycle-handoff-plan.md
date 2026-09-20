# Checksum Reference Lifecycle — Handoff-Ready Implementation Plan

## 1. Purpose and status

This document is the implementation handoff for checksum reference lifecycle management
across `seamless-core`, `seamless-transformer`, `seamless-workflow`, and the Transformation
publication hooks in `seamless-dask`. It is self-contained:
the implementer may consult design history for context, but no other document is normative.

The work prevents two classes of lifecycle failure:

- **under-holding**: a live object stores a checksum it may need later, but the corresponding
  buffer can be evicted before that use, producing a cache miss, refetch, or recomputation;
- **over-holding**: an acquisition is not released, so the buffer remains strongly cached and
  memory use grows until process shutdown.

The runtime keep-alive mechanism is deliberately small: all live refholder references for one
checksum share one boolean bridge in the strong cache entry. The integer refholder count exists
for lifecycle balance and audit, not to make eviction protection N times stronger.

The verification mechanism compares two quantities that are independently derived wherever the
holder's semantic state permits it:

1. `refholder_count[checksum]`, changed only by acquire/release calls; and
2. the references claimed by live refholder objects, derived from their actual semantic state.

If the count is larger, references were over-held or their holder died without releasing them.
If live claims are larger, an acquisition was omitted or a release happened too early. A
framework-level per-object reference counter is forbidden because updating it alongside the
global count would make the two values agree by construction and make the audit ineffective.
Some roles necessarily use semantic demand state that also drives acquisition. Their audit
evidence is partially coupled rather than useless; section 13 requires direct invariant tests
for those roles.

The existing status and workflow literal-exception work is already present in the component
repositories. This handoff does not reimplement `Cell.status`, `Transformer.status`, or the
capture of unavailable workflow literals into `.exception`; it migrates and generalizes the
reference lifecycle underneath those features.

## 2. Handoff-ready criteria

This document is handoff-ready only if all of the following are true:

1. It defines every load-bearing lifecycle term and invariant.
2. It distinguishes runtime correctness from shutdown verification.
3. It names the affected repositories, current modules, and misleading current behavior.
4. It gives exact ownership rules for every refholder class in scope.
5. It defines the cache fields and internal APIs precisely enough to implement directly.
6. It defines acquire, replacement, publication, handoff, cancellation, and cleanup ordering.
7. It resolves the choices identified by the language review rather than leaving them to the
   implementer.
8. It defines worker-process, scratch, remote-registration, and deep-checksum boundaries.
9. It supplies an ordered sequence in which every phase ends in a testable working state.
10. It identifies current tests that encode superseded behavior and says how to rewrite them.
11. It supplies focused and full-suite commands for the `seamless1` conda environment.
12. It defines observable completion evidence, not merely the desired internal structure.

## 3. Normative terminology

The present tense in this document is normative. “X refholds Y” means that X must acquire
exactly one refholder reference for the stated semantic role and must release it at the stated
lifecycle boundary.

**Checksum**
: A content address. A bare `Checksum` object owns no reference merely by existing.

**Concrete checksum**
: A content address known now after the receiving API has applied its normalization rules. It
  may have arrived as a `Checksum` or as checksum-like bytes/text accepted by that API; an
  ordinary string remains literal data where the API defines it as such. An `Expression`,
  `Transformation`, or builder whose result is not yet known is non-concrete. Concreteness says
  nothing about whether the buffer is locally available; a reference on a checksum with no local
  buffer is still real and must balance.

**Refholder class**
: A class whose live instances may own refholder references. Being a refholder is a property
  of the class, not of its current count; an instance may currently hold zero checksums.

**Refholder reference**
: One unit in the checksum-indexed logical `refholder_count`, acquired through
  `incref_refholder()` and released through `decref_refholder()`. It never increments or
  decrements `manual_refs`.

**Manual reference**
: One unit in a strong cache entry's `manual_refs`, acquired through the existing public
  `Checksum.incref()` or `Buffer.incref()` API. After migration, user-facing or deliberately
  low-level leases are the only manual references; object lifecycle code uses the refholder
  API.

**Refholder bridge**
: `StrongEntry.has_refholder_bridge`, a boolean equal to whether the checksum's logical
  refholder count is positive. It protects the entry from demotion but is not itself a manual
  reference or a holder object.

**Tempref**
: Refreshable, decaying cache interest used only for bounded handoff and opportunistic
  availability. Temprefs are not attributed, counted, or balanced by the lifecycle audit.

**Publication**
: The moment an Expression or Transformation records a successful result checksum and makes
  it visible to dependents. Cache hits publish too. Re-evaluation or cache recovery may publish
  the same deterministic checksum again; every publication path is idempotent with respect to
  result ownership. Failure and cancellation publish nothing.

**Adoption**
: A consumer records a concrete checksum in semantic state and acquires its own refholder
  reference. Adoption transfers no reference from the producer; it creates independent
  ownership.

**Handoff**
: Adoption, or an Expression tempref refresh, on the same code path that observes publication,
  before awaiting, yielding, or queueing later work.

**Demotion**
: Removing a `StrongEntry` and its eviction interest while leaving any still-live `Buffer` in
  the weak cache. It does not delete a durable remote copy.

**Eviction**
: Demotion selected by the memory-pressure pass. The same protection predicate gates explicit
  demotion and eviction.

**Balanced**
: Before cleanup, every checksum's refholder count equals its live semantic claims and its
  bridge matches whether the count is positive. At shutdown, all manual references have also
  been released. After registered-holder cleanup, the refholder-count map is empty, every
  bridge is false, and every manual count is zero.

## 4. Governing ownership rule

A concrete checksum is refheld when it is stored for possible use after control may yield or
wait. A tempref is sufficient only when consumption completes on the same bounded observation
path, without an intervening yield, wait, or queue handoff. Potentially unbounded delay is a
useful signal for refholding, not a universal if-and-only-if rule: a technically bounded async
delay may outlive a tempref, while a dormant Expression deliberately does not refhold its input.

| State | Use boundary | Required protection |
|---|---:|---|
| Standalone Cell checksum input | Stored across calls | Refholder reference |
| Standalone Transformer checksum-bound input | Stored across calls | Refholder reference |
| Expression input during evaluation | Same immediate observation path | Refresh tempref; no refholder reference |
| Transformation concrete input | May wait for sibling inputs/re-execution | Refholder reference |
| User-requested Expression/Transformation result | Stored for later user access | Producer refholds result |
| Result consumed by Transformation | Consumer may wait | Consumer adopts as input |
| Result consumed by Expression | Same immediate observation path | Consumer refreshes tempref |
| Context literal/current/retained workflow state | Stored across scheduler turns | Context refholds it |
| Context-private evaluation result before Context decision | Same scheduler path | Tempref; Context adopts if retained |

An unrecognized ownership site is a specification error: if neither the implementation nor
`_refheld_checksums()` treats a field as owned, the shutdown comparison cannot discover it.
The per-class rules below are therefore part of the correctness contract, not examples.

## 5. Resolved implementation decisions

There are no blocking design choices left for the implementer in this handoff.

### 5.1 Scratch and remote registration

`incref_refholder()` accepts `scratch=False`, matching the existing manual API. The bridge
controls local eviction only. On a checksum's first refholder acquisition, entry creation and
buffer adoption follow the current `BufferCache.incref()` path, except that `manual_refs` is
untouched. A non-scratch acquisition registers an available buffer remotely and makes the entry
non-scratch. A scratch acquisition does not register it remotely.

Scratch status is conservative for the lifetime of a strong entry: once any non-scratch
interest has existed, the entry does not revert to scratch-only merely because that particular
holder releases. This matches the existing monotonic `remote_registered` behavior and avoids a
second per-checksum scratch multiplicity system. `purge_scratch()` must never remove an entry
whose refholder bridge is set or whose manual count is nonzero.

A user-requested result on a scratch Transformation is refheld like any other result. Its bridge
makes that checksum immune to `purge_scratch()` until the Transformation releases it. This is
intentional: explicit user interest outranks scratch. A scratch input is tempref-only and
purgeable during the bounded PreTransformation path; if the final Transformation stores it
across a yield or wait, that Transformation acquires a scratch refholder reference and the
bridge then protects it until release. Unrequested scratch results remain purgeable.

### 5.2 Completed Transformation inputs

A completed standalone Transformation continues to refhold its concrete inputs and its
transformation-definition checksum. The object may be asked to resolve or execute again after a
result cache miss. It releases them only through `_release_refholds()`, terminal cancellation
after in-flight work has settled, or object destruction. Context-private Transformations are
short-lived, so their inputs are released when the Context drops the private object.

### 5.3 Manual references at shutdown

Any positive `manual_refs` at shutdown is a lifecycle warning. The pre-cleanup pass emits the
warning once. The post-cleanup pass does not duplicate the same message; it verifies the count
is still nonzero before forced accounting cleanup. Public manual decref at zero warns
immediately, returns `False`, and changes nothing.

### 5.4 Result-hold flag

`refhold_result` is internal mutable evaluation state, excluded from identity, equality,
hashing, serialization, and public documentation. Public result-obtaining methods and public
property access that exposes a result enable it; scheduler/internal dependency entry points and
internal property access do not. Direct user assignment to the flag is not supported API. This
read-side behavior is deliberate because a bare returned checksum owns no reference; the narrow
internal accessor required in section 9.4 prevents framework bookkeeping or logging from
expressing user interest accidentally.

### 5.5 Expression-chain temprefs

The consuming Expression refreshes or creates the tempref on its concrete input on every
resolution attempt, then evaluates without waiting. The producer is not responsible for
refreshing a result on behalf of consumers.

### 5.6 Deep checksums

This implementation refholds the top-level checksum only. It does not recursively acquire
references for deep-checksum members. Existing deep-buffer resolution and remote durability
remain responsible for members. Add a focused top-level deep-checksum regression test, but a
new recursive member-reference model is out of scope.

## 6. Runtime substrate in `seamless-core`

### 6.1 Strong cache entry

Modify `seamless-core/seamless/caching/buffer_cache.py`. Only changed fields are shown; retain
`tempref_scratch`, `remote_registered`, and other existing fields.

```python
@dataclass
class StrongEntry:
    buffer: Buffer | None = None
    size: int | None = None
    manual_refs: int = 0
    has_refholder_bridge: bool = False
    tempref: TempRef | None = None
    # existing remaining fields unchanged
```

`BufferCache` owns a map protected by its existing `threading.RLock`:

```python
self.refholder_counts: dict[Checksum, int] = {}
```

Only positive entries exist. Missing means zero; the `1 -> 0` transition deletes the key.
The count update and bridge toggle happen under one acquisition of `BufferCache.lock`, so no
thread can observe a positive count with a false bridge or vice versa.

### 6.2 Cache methods

Implement these methods on `BufferCache`:

```python
def incref_refholder(
    self,
    checksum: Checksum,
    *,
    buffer: Buffer | None = None,
    scratch: bool = False,
) -> None: ...

def decref_refholder(self, checksum: Checksum) -> bool: ...

def reference_snapshot(self) -> dict[Checksum, tuple[int, int, bool]]: ...

def force_clear_reference_accounting(self) -> None: ...
```

The snapshot tuple is `(refholder_count, manual_refs, has_refholder_bridge)` and is copied under
the lock. It is internal/test API, not a public report model.

Refholder transition rules:

- `0 -> 1`: create/promote the strong entry, set the bridge, then store count 1;
- `N -> N+1`: update only the logical count, while applying any non-scratch remote-registration
  side effect requested by this acquisition;
- `N -> N-1`, `N > 1`: update only the count;
- `1 -> 0`: delete the count, clear the bridge, and demote only if no manual ref or live tempref
  remains;
- decrement at zero: log one `WARNING` on `seamless.references`, return `False`, change nothing.

Factor current entry creation/adoption into one locked helper used by manual incref, refholder
incref, and tempref. Do not call blocking or re-entrant remote code between the count write and
bridge write.

Rename all `normal_refs` code and tests to `manual_refs`. Existing public incref side effects
remain; the only count it changes is `manual_refs`. Public decrement with no entry or zero
manual count warns, returns `False`, and must not clear the bridge.

### 6.3 Protection and interest

The absolute demotion predicate is:

```text
entry.manual_refs == 0
and entry.has_refholder_bridge is False
and entry has no live tempref
```

Implement this predicate once in a locked helper and use it from every demotion, eviction,
purge, and test-reset path. It is a correctness boundary, not merely a refactoring preference.

Update all of these current paths, not merely `decref()`:

- expired-tempref cleanup in `run_eviction_once()`;
- candidate construction and candidate removal in `run_eviction_once()`;
- `purge_scratch()`;
- explicit demotion after either decrement API;
- any cache-reset/test helper.

Current `run_eviction_once()` builds candidates from every strong entry and deletes selected
entries without checking `normal_refs`; this must be fixed. A protected entry is never a
candidate. A live tempref is interest above `TEMPREF_MINIMAL_INTEREST`; once below that threshold
the pass clears it before applying the predicate.

`StrongEntry.interest()` retains `manual_refs + int(has_refholder_bridge)` plus current tempref
interest for diagnostic and test use. Refholder multiplicity never changes the score. The
manual and bridge terms cannot affect eviction ordering because the protection predicate removes
those entries from the candidate list before `_candidate_score()` calls `interest()`.

If caps cannot be met because all remaining entries are protected or have infinite score, emit a
rate-limited warning on `seamless.references`, naming before/after bytes, the cap, and the number
protected. Warn on transition into this state and again only after a material state change or the
rate-limit interval, not on every background pass. Return normally; never discard protected data
or accounting.

### 6.4 Public-class internal wrappers

Add internal methods to `Checksum` and `Buffer`:

```python
Checksum.incref_refholder(*, scratch=False) -> None
Checksum.decref_refholder() -> bool
Buffer.incref_refholder(*, scratch=False) -> None
Buffer.decref_refholder() -> bool
```

They live on public classes for convenience but are excluded from public docs and carry no
compatibility promise. `Buffer` passes itself to the cache on acquisition. Workers patch these
methods to no-ops alongside the existing ref methods.

## 7. Refholder registry and verification substrate

Add `seamless-core/seamless/reference_lifecycle.py`. Do not add a `ReferenceHolder` base class,
holder token, event class, or audit-report object.

### 7.1 Identity-safe weak registry

Use an identity-keyed weak value dictionary, not `weakref.WeakSet`:

```python
_refholders: weakref.WeakValueDictionary[int, object]
_registry_lock: threading.RLock

def register_refholder(obj: object) -> None:
    _refholders[id(obj)] = obj
```

`Expression` has value equality and hashing, so `WeakSet` would collapse distinct-but-equal
objects. `id(obj)` is unique among simultaneously live objects and is sufficient within one
audit. Never persist it and never assert its value in tests.

Initialize neutral fields first, register the instance, and only then acquire and publish any
initial held field. Registration raises `TypeError` if the object is not weak-referenceable;
silently skipping an instance is forbidden. Add `"__weakref__"` to `Cell.__slots__`; use
`weakref_slot=True` for slotted dataclasses such as `Expression`; confirm Transformer and
Transformation instances are already weak-referenceable.

In worker processes `register_refholder()` is a no-op, the refholder Checksum/Buffer methods are
no-ops, and `seamless.close()` continues returning early. No lifecycle audit runs in workers.

### 7.2 Per-class protocol

Every refholder class implements:

```python
def _refheld_checksums(self) -> Iterable[tuple[Checksum, str]]:
    """Yield one item per semantic refholder reference currently owned."""

def _release_refholds(self) -> None:
    """Release all current refholder references; idempotent."""
```

`_refheld_checksums()`:

- derives claims from the object's real fields/tables, never a generic lifecycle counter;
- yields duplicates for distinct roles holding the same checksum;
- uses stable role strings defined in the ownership table below;
- performs no I/O, evaluation, buffer resolution, or cache-lock acquisition;
- does not block and is safe on partial initialization;
- yields nothing once `_release_refholds()` has completed;
- need not order output; the audit sorts it;
- should not raise, but the audit catches and warns if it does.

Any field normalized to a `Checksum` is an ownership site. Its class must either assign it a
role in section 8 or list it as exempt with a reason. Current exemptions are `Cell._validator`
and `Expression.validator`: validator evaluation raises `NotImplementedError`. When validators
are implemented, add role `"validator"` to both classes and apply the standard same-path versus
stored-use rule.

An idempotent boolean such as `_refholds_released` is allowed to make finalization safe. It is
not a checksum counter and does not replace deriving the pre-cleanup claims from semantic state.
Public definition fields may remain readable after cleanup; Seamless is closed and execution is
prohibited, while `_refholds_released` makes the audit protocol yield nothing.

Finalizers call `_release_refholds()` as a backstop and suppress destructor exceptions after
logging. Normal owners and `seamless.close()` call it explicitly; correctness must not depend
solely on `__del__` because shutdown ordering, resurrection, escaped cleanup failures, and
partially destroyed module state make finalization an unreliable primary cleanup mechanism.

### 7.3 Mutation rule

Every replacement is acquire-before-release, including replacement by the same checksum:

1. determine and acquire the new semantic roles;
2. publish the new object field/state;
3. release the old roles.

This prevents the logical count reaching zero and the bridge disappearing between two equal
assignments. A field that never acquired a reference never releases one. Copies and derived
builders acquire independent references.

## 8. Exact ownership by class

### 8.1 Standalone `Cell`

Repository/module: `seamless-core/seamless/cell_class.py`.

- A standalone Cell owns one refholder reference when `_input_ref` is explicitly a `Checksum`.
- It does not reinterpret an arbitrary 64-character Python string as a checksum; callers use
  `set_checksum()`/`Checksum` to express checksum semantics.
- Python values, Buffers held directly, other builders, and futures are not checksum fields of
  the Cell and acquire no Cell refholder reference.
- Role string: `"input"`.
- `input_ref` replacement, `set()`, `set_checksum()`, derivation/copy, and binding into a Context
  all obey acquire-before-release.
- Each derived standalone Cell returned by path/celltype helpers independently refholds its
  copied checksum input.
- Binding transfers no reference: the Context first adopts its producer state, then the builder
  releases its standalone role and becomes a bound handle.
- A bound Cell handle owns nothing and is not registered as a separate holder.
- A standalone Cell has no `.value` or result checksum state. `build()` returns an independent
  Expression. `compute()`/`run()` use a temporary Expression; the Cell never adopts its result.

### 8.2 `Expression`

Repository/modules: `seamless-core/seamless/expression_class.py` and
`seamless-core/seamless/checksum/expression.py`.

- Expression input checksums are never refheld. Every local/remote/internal evaluation refreshes
  or creates an input tempref immediately before resolution.
- Add mutable identity-excluded state using internal `object.__setattr__` while retaining the
  frozen public definition contract:

  ```python
  _result_checksum: Checksum | None = field(init=False, default=None, compare=False, repr=False)
  _refhold_result: bool = field(init=False, default=False, compare=False, repr=False)
  _result_refheld: bool = field(init=False, default=False, compare=False, repr=False)
  _refholds_released: bool = field(init=False, default=False, compare=False, repr=False)
  ```

  Keep all four out of `identity_key`, `__eq__`, `__hash__`, and serialization. Preserve any
  compatibility-facing `result` property by returning `_result_checksum`; do not leave an
  independently mutable constructor field that conflicts with publication.
- Public `compute()`, `compute_async()`, `run()`, and `__call__` first enable result holding.
- Public result/result-checksum/value/buffer properties that exist for Expression enable result
  holding; framework code uses the internal accessor instead.
- The internal dependency evaluation entry points do not enable it.
- Publication always temprefs the result, including identity expressions, local cache hits,
  database hits, and remote results. If `_refhold_result` is true and the result is not already
  held, publication acquires exactly one reference and marks `_result_refheld`.
- A public call after internal publication performs the false-to-true transition and acquires
  the already-present result once. Repeated public calls do not multiply the reference.
- Failure/cancellation publishes and acquires nothing.
- `_release_refholds()` releases the result only when `_result_refheld` is true.
- `_refheld_checksums()` derives the semantic `"result"` claim from `_refhold_result` plus a
  published `_result_checksum`, not from `_result_refheld`. After cleanup,
  `_refholds_released` suppresses the claim. `_result_refheld` remains bookkeeping used only to
  prevent double acquisition and release of a reference that was never acquired.
- Role string: `"result"`.
- `item()`, `slice()`, `as_celltype()`, and other definition-changing `replace()` operations
  create a fresh Expression with no carried result/hold. Two distinct equal Expressions remain
  separately registered and independently own results.

Replace `_expression_result_buffers`, currently a process-global strong dictionary, with weak
or buffer-cache-backed storage. It must not keep every Expression result alive independently of
temprefs and refholder references. Expression checksum/provenance caches may retain checksums,
but not strong Buffer objects.

### 8.3 Standalone `Transformer` builder

Repository/module: `seamless-transformer/seamless_transformer/transformer_class.py`.

- A standalone builder owns one role for every explicitly stored `Checksum` in its pre-bound
  arguments, code/module checksum fields, or other checksum-bearing builder fields that a later
  call reads.
- An ordinary Python literal remains stored as Python data and needs no checksum reference.
  When a literal is converted to a checksum during Transformation building, the temporary
  PreTransformation/Transformation contract below takes over.
- A Buffer stored directly is already kept alive by the builder's Python reference; do not add a
  second checksum hold unless the builder replaces it with a checksum-only representation.
- Stable role strings are `"pin:<name>"`, `"code"`, and `"module:<name>"`.
- Wrapper mutations (`ArgsWrapper`, `ModulesWrapper`, code setters, deletion, snapshot/binding)
  must call owner helpers; direct mutation of backing dictionaries that bypasses lifecycle logic
  is forbidden.
- A snapshot/build creates independent downstream ownership. The reusable builder retains its
  own configured roles.
- Context binding adopts all checksum-only builder state first and then releases the builder's
  standalone roles.
- The builder has no result checksum state. Convenience `compute()`/`run()`/`task()` create a
  temporary Transformation and never adopt its result.

### 8.4 Temporary `PreTransformation`

Repository/module: `seamless-transformer/seamless_transformer/pretransformation.py`.

`PreTransformation` is a short-lived refholder because it converts pins one by one before the
final Transformation exists. It registers like every other refholder.

- `_value_refs` becomes semantic state containing each successfully converted, non-scratch
  checksum input that will be passed to the final Transformation; role strings identify
  `"input:<pin>"`. It is not a generic acquisition ledger. `_refheld_checksums()` derives its
  claims from this converted-input state, while the mutation helper separately performs the
  corresponding acquisition.
- A scratch tempref-only input is never appended to this refheld collection and is never
  decremented on release. This fixes the current bug in which scratch inputs are temprefed but
  still appended and later manually decref'ed.
- CodeManager acquisitions remain CodeManager roles, not duplicated PreTransformation claims.
- When the Transformation is created, it acquires its own direct-input roles before
  PreTransformation releases its non-scratch temporary roles. For a scratch input, which the
  PreTransformation only temprefs, the Transformation adopts a scratch refholder role on that
  same construction path before any yield or wait. There is no unprotected transfer interval.
- `release()` becomes/uses `_release_refholds()` and is idempotent.

### 8.5 `Transformation`

Repository/module: `seamless-transformer/seamless_transformer/transformation_class.py`.

Transformation semantic roles are:

- every direct concrete input: `"input:<pin>"`;
- every dependency result once concrete: `"input:<pin>"`;
- its constructed transformation-definition checksum: `"definition"`;
- its result only when explicitly held: `"result"`.

Requirements:

- Direct inputs transfer from PreTransformation acquire-before-release.
- A dependency input is adopted on the same code path that observes its result and before any
  wait for other dependencies.
- The async path must not `gather()` all dependencies and adopt afterward. Use per-task done
  handling or `asyncio.as_completed()` so each successful result is adopted before waiting for
  the rest. The sync path applies the same ordering.
- Construction publication temprefs and refholds the transformation-definition checksum. This
  stored checksum may be needed later for cache lookup/re-execution.
- A live completed Transformation retains inputs and definition until cleanup/cancellation.
- Add `_refhold_result`/`_result_refheld` state with the Expression semantics above.
- User-facing `compute()`, `computation()`, `run()`, `task()`, and `start()` enable result
  holding. Public `result_checksum`, `buffer`, or `value` access also enables it; introduce
  private accessors for internal code so scheduler calls do not accidentally enable it.
- `_compute`, `_computation`, dependency helpers, and Context/scheduler paths accept or use an
  internal origin that never enables result holding.
- DirectTransformer's user call path enables the mode before internal execution.
- Every successful result path temprefs before publication: local execution, cache hit, remote,
  jobserver, and Dask. Scratch results use scratch temprefs.
- Terminal cancellation waits for/detaches work, then releases all input/definition roles and
  any held result. Cancellation of an already completed Transformation remains a no-op and does
  not silently discard a user-held result.
- `__del__` delegates reference cleanup and existing Dask/destructor cleanup exactly once.

### 8.6 `CodeManager`

Repository/module: `seamless-transformer/seamless_transformer/code_manager.py`.

The current CodeManager is prior art for the bridge shape: its local count maps toggle one
manual cache reference through `_syntactic_active`/`_semantic_active`. Migrate it as follows:

- register the singleton when instantiated;
- remove `_syntactic_active` and `_semantic_active` as cache-reference bookkeeping;
- each direct or guard acquisition calls `incref_refholder()` once and each release calls
  `decref_refholder()` once; the global cache bridge performs zero-crossing aggregation;
- `_refheld_checksums()` derives repetitions from the operational direct/guard maps and emits
  roles `"syntactic:direct"`, `"syntactic:guard"`, `"semantic:direct"`, and
  `"semantic:guard"`;
- `_release_refholds()` walks those maps, releases their exact multiplicities, clears maps and
  semantic Buffer holds, and is idempotent.

The audit must not read the removed active sets. Agreement for CodeManager is necessarily less
independent than for field-based classes because its direct/guard demand maps also drive
acquisition. Those maps still express real semantic demand, so their claims are useful rather
than vacuous. Document the partial coupling in code comments, keep the four role maps visible in
warnings, and use direct multiplicity tests as the stronger evidence for this class.

### 8.7 Workflow `Context`

Repository/modules: `seamless-workflow/seamless_workflow/context.py`, `graph.py`, and
`scheduler.py`.

`Context` itself is the refholder class. Bound Cell/Transformer backends and public handles are
views and own no references.

For each `Context` instance, initialize neutral lifecycle fields, register it, and only then
acquire or publish initial roles. Subcontexts are path prefixes within that instance, not
separate holders. Remove `_checksum_holds`: it is a generic mirror counter and would make the
audit self-confirming. Derive claims by traversing the graph/runtime state directly.

The Context owns these exact roles:

- every `Node.cell_root_producer`: `"cell:<path>:literal"`;
- every `Node.transformer_pin_producers[pin]`:
  `"transformer:<path>:pin:<pin>"`;
- every checksum-only transformer code/config dependency used later:
  `"transformer:<path>:code"` or a specific module role;
- every non-`None` `Node.current_checksum`: `"node:<path>:current"`;
- every superseded `RunRecord.result_checksum` retained by scheduler policy:
  `"node:<path>:superseded:<generation>"`.

If a literal producer and current result contain the same checksum, they are two semantic roles
and yield twice. Current RunRecord results are aliases of `Node.current_checksum` and do not add
a third role while current. On supersession, acquire the retained-run role before replacing the
node current result. Release it when the superseded cap evicts it, its deadline expires, prune
removes it, its node/subcontext is deleted, the graph is replaced, or the Context is cleaned.

Introduce helpers that are the only legal mutation paths:

```python
_replace_producer(owner_path, old, new)
_replace_current_checksum(node_path, new_checksum)
_retain_superseded_record(record)
_release_superseded_record(record)
_release_refholds()
_refheld_checksums()
```

Rewrite every direct assignment of `node.current_checksum`, including unwired/blocked/failure
transitions, through `_replace_current_checksum`. Acquire the new checksum before making it
visible and before releasing the old checksum. Do the same for producer replacement, node and
subcontext deletion, `set_graph()`, `_copy_subcontext()`, and Context destruction.

The current workflow evaluator calls Python callables directly; it does not yet construct
private Expressions/Transformations. Do not invent them for this task. If a later substrate
migration creates private evaluation objects, it must use their internal entry points, adopt a
retained result into Context before dropping them, and leave their result-hold mode false.

`Context._release_refholds()` releases current results, retained superseded results, literal
producers, pin/code/module roles, and then marks cleanup complete. It replaces the current
stderr-printing `_release_all_producers()` and `_report_refcount_error()` path. Underflow is
reported centrally through `seamless.references`.

## 9. Dependency and publication timing

### 9.1 Producer rule

Every successful Expression/Transformation result is temprefed at publication even if the
result came from a cache/database hit. A producer refholds a result only for explicit user
interest. It never takes a result reference merely because a dependent exists.

### 9.2 Transformation consumer

When a producer publishes to a downstream Transformation, the consumer:

1. observes and validates the result checksum;
2. calls its input-adoption helper, which acquires the refholder role and records it;
3. only then awaits or inspects another dependency.

Once adopted, it may wait indefinitely. The producer may release its own optional result role
without affecting the consumer.

### 9.3 Expression consumer

When the consumer is an Expression, it refreshes/creates the input tempref and evaluates on that
same code path. It acquires no refholder reference. Expression chains repeat this at each link.

### 9.4 No hidden public calls

Current dependency helpers call `Expression.compute()`, `Transformation.compute()`, and
`Transformation.computation()`, which are public and would incorrectly turn on result holding.
They also read public result properties that enable holding. Replace both calls and reads with
named internal methods/accessors. The migration must include
`Transformation._dependency_result_checksum`, the current `pretransformation.py` reads around
dependency inspection and result assembly, and every scheduler/Context path that reads an
Expression or Transformation's public `result`, `result_checksum`, `.buffer`, or `.value`. Keep
one internal checksum accessor
(`_result_checksum_internal()` or an equivalently explicit name) so internal code cannot drift
back to public read semantics. Future public entry points that return/schedule/access a result
inherit the user-interest rule; future scheduler entry points inherit the neutral rule.

## 10. Shutdown audit and global lifecycle collection

Implement the procedural audit in `seamless-core/seamless/reference_lifecycle.py` and integrate
it into `seamless-core/seamless/shutdown.py`. It returns no public report object.

Use the logger `logging.getLogger("seamless.references")`. All lifecycle messages in this
document are `WARNING`. Balanced execution emits nothing on this logger. Existing unrelated
atexit/shutdown messages are outside that assertion.

### 10.1 Pre-cleanup audit invariant

After new work is prohibited and in-flight work has settled, but before holder cleanup, for
every checksum `c`:

```text
refholder_count[c] == number of live semantic claims for c
has_refholder_bridge[c] == (refholder_count[c] > 0)
```

The first comparison finds lifecycle bugs. The second finds corruption in the cache bridge.

### 10.2 Shutdown sequence

Integrate this ordering with the existing close phases:

1. Set `_closing`/`_closed` and prohibit new work, as today.
2. Run close hooks and settle/cancel worker, local, remote, and Dask activity within existing
   shutdown timeouts. Keep the existing single `_run_close_hooks()` call here; do not introduce a
   second hook phase. Reference audit begins only after the timeouts have elapsed as applicable
   and every tracked task is done or explicitly detached, so ended work has released its roles.
3. Snapshot the weak registry into a strong local list. This intentionally stabilizes the live
   population during comparison.
4. For each holder, call `_refheld_checksums()` and build:

   ```text
   checksum -> [(holder_object, role), ...]
   ```

   Catch a holder exception, warn with class/id, and continue.
5. Snapshot cache accounting. Iterate the union of reverse-index checksums,
   `refholder_counts`, and strong entries, sorted by checksum hex.
6. Compare live claim multiplicity with `refholder_count`:
   - count larger: warn about the unattributed excess; a dead holder or missed release is
     likely;
   - claims larger: warn about missing acquisitions/premature releases and list every claimant.
7. Verify the bridge equivalence and warn for each positive manual count. Sort holders by class
   name and role. IDs are printed only to correlate report lines and are never tested.
8. Flush every pending buffer-writer entry while references still retain buffers, preserving
   the existing short/long flush behavior.
9. Call `_release_refholds()` on every holder in the snapshot; catch and warn per holder. This
   step introduces no new close-hook mechanism; after the per-holder pass, continue only the
   subsystem teardown that already follows close hooks today.
10. Drop the strong snapshot, then run `gc.collect()` twice. The first pass may run finalizers;
    the second collects objects released by them.
11. Snapshot accounting again. Warn if any refholder count remains, any bridge remains true, or
    any manual count remains. Do not duplicate a manual warning already emitted in step 7.
12. After all warnings and buffer flushes, force-clear residual accounting and demote entries
    for which no live tempref remains. This never retroactively makes the audit pass.
13. Continue existing remote-client/shared-memory/resource-tracker teardown.

The pre-cleanup pass detects lifecycle mismatch. The post-cleanup pass detects failure of
cleanup or Python finalization; do not describe them as the same check.

### 10.3 Warning forms

Messages must be deterministic except for object IDs. Examples:

```text
Checksum <hex> has refholder count 3 but only 2 live claims; 1 is unattributed
  Context 0x... node:tf:current
  Transformation 0x... input:x

Checksum <hex> has refholder count 1 but 2 live claims
  Context 0x... cell:data:literal
  Context 0x... node:data:current
  A reference was not acquired or was released by code that did not own it

Checksum <hex> has refholder count 1 but its eviction bridge is absent

Checksum <hex> has 2 unmatched manual references at shutdown

Manual decref ignored for checksum <hex>: manual refcount is already zero
Refholder decref ignored for checksum <hex>: refholder count is already zero
```

A holder already garbage-collected cannot be named. Its excess count remains detectable. A
short-lived under-hold whose holder also died before shutdown leaves no audit evidence; forced
tempref-expiry tests are the runtime complement.

## 11. Current code anchors and migration hazards

Repository state observed while writing this handoff: `seamless-core`,
`seamless-transformer`, `seamless-dask`, and `seamless-remote` are on
`cells-and-expressions`; `seamless-workflow` is on `main`. These are observations, not branch
creation instructions. Recheck branch and dirty state immediately before implementation and do
not overwrite unrelated user changes.

### 11.1 `seamless-core`

- `seamless/caching/buffer_cache.py`: `StrongEntry.normal_refs`, manual APIs, temprefs,
  `purge_scratch()`, and eviction. Current eviction can remove positive-ref entries.
- `seamless/checksum_class.py` and `buffer_class.py`: existing public manual APIs and bool
  decrement return values.
- `seamless/cell_class.py`: slotted Cell without weakref support; direct `_input_ref` mutation;
  bound handles are backend views.
- `seamless/expression_class.py`: frozen/slotted value-equal Expression with no weakref slot and
  no mutable result-hold state.
- `seamless/checksum/expression.py`: all cache-hit/public/internal result paths; current
  `_expression_result_buffers` strong dictionary masks result expiry.
- `seamless/shutdown.py`: existing worker settling, buffer flush, remote/shared-memory teardown,
  and atexit integration.

### 11.2 `seamless-transformer`

- `transformer_class.py`: mutable builder dictionaries and wrappers, snapshot/call/convenience
  methods, and Context binding hooks.
- `pretransformation.py`: `_value_refs` currently uses manual refs and incorrectly mixes
  scratch temprefs with later decref.
- `transformation_class.py`: dependency helpers currently call public methods; async gather
  adopts no input refs; result and definition publication need centralized helpers.
- `code_manager.py`: local multiplicity plus `_active` sets already approximates a bridge but
  uses manual cache refs.
- `worker.py`: primitive monkeypatches must include new refholder methods. Parent IPC
  `incref/decref` operations remain manual transport/user leases unless a separate owning class
  is explicitly introduced.
- `cmd/api/main.py`: transformation-buffer manual increfs used for upload/write flows require a
  matching decref on every return/exception path or a deliberately scoped owner.

### 11.3 `seamless-workflow`

- `context.py`: `_checksum_holds` plus one manual cache ref per producer is the superseded N-ref
  model; many direct `node.current_checksum` assignments currently have no result ownership.
- `graph.py`: producer, config, and current-result state from which Context claims are derived.
- `scheduler.py`: superseded `RunRecord` retention/cap/prune transitions require explicit
  adoption/release callbacks.
- `tests/test_garbage_collection.py`: assertions such as `normal_refs == 2` for two Context
  fields encode the old model. Rewrite as logical `refholder_count == 2`,
  `manual_refs == 0`, and one true bridge.
- `tests/test_literal_retention.py`: provides the existing forced-expiry pattern and exception
  capture baseline.

### 11.4 `seamless-dask` and remote boundaries

- `seamless-dask/seamless_dask/transformation_mixin.py` directly assigns both
  `_transformation_checksum` and `_result_checksum` on cache-hit, thin, and fat paths. Route
  every such assignment through the publication helpers implemented on Transformation, so
  definition refholding, result temprefs, and optional user-result ownership are backend
  independent.
- `seamless-dask/seamless_dask/client.py` creates/temprefs buffers in worker/client tasks. These
  are handoff mechanics, not holder attribution; keep them unless a publication helper makes a
  call redundant, and prove the final path has at least one tempref.
- `seamless-remote` returns checksums and owns no local object lifecycle reference. No remote
  database refcount change is expected. Core Expression/Transformation publication must run
  after remote results return, so remote cache/database hits receive the same tempref/hold
  treatment as local results.

## 12. Implementation phases and testable milestones

Do not implement all repositories in one unreviewable change. Each phase ends with the stated
invariant and focused tests in the `seamless1` conda environment. Commit implementation changes
after the phase's focused tests pass; cross-repository phases require one coherent commit per
affected repository. Do not commit this handoff document unless separately requested.

Run one pytest process per test file, as the existing `tests/run-tests.sh` scripts do. The buffer
cache, close state, worker manager, and `seamless.references` logger are process-global, so a
batched multi-file invocation shares lifecycle state across files. Treat a lifecycle failure
that appears only in a batched run as cross-test pollution until it reproduces in a single-file
process; do not change implementation code to chase it.

Every forced-expiry lifecycle test that says a checksum survived must also demonstrate a
negative control: with the relevant acquisition disabled, the assertion fails. A test that
passes with and without the reference proves no retention contract.

### Phase 0 — Baseline, inventory, and test helpers

Implementation:

- Record branch/status for core, transformer, workflow, Dask, and remote repositories and
  preserve unrelated changes.
- Add a reusable forced-expiry helper in core tests. It clears the checksum tempref, removes
  known alternative strong Buffer holds (including `_expression_result_buffers` until Phase
  3), drops Python Buffer references, sets caps low enough to exercise eviction, runs one
  eviction pass, and calls `gc.collect()`. It must also defeat repair: disable remote/database
  resolution and fingertip/recompute for the tested checksum, or assert fetch/recompute counters
  remain zero. Every lifecycle case uses a unique payload such as `uuid4().hex`, preventing
  another holder in the process from protecting the same content address.
- Add internal snapshot assertions for the existing cache without changing behavior yet.
- Inventory every `.incref()`/`.decref()` call with `rg` and classify it in the eventual commit
  message as `manual`, `refholder lifecycle`, or unrelated (for example shared-memory PID refs).

Acceptance after Phase 0:

- Existing suites still pass.
- Later tests can prove a bridge, rather than a surviving tempref/global Buffer map, retained a
  buffer.
- Every current call site has a documented migration category.

Focused commands:

```bash
conda run -n seamless1 python -m pytest -q tests/test_buffer_cache.py
for test_file in tests/test_literal_retention.py tests/test_garbage_collection.py; do
  conda run -n seamless1 python -m pytest -q "$test_file" || exit 1
done
```

Run the first command from `seamless-core`, the second from `seamless-workflow`.

### Phase 1 — Core manual count and boolean bridge

Implementation:

- Rename `normal_refs` to `manual_refs`.
- Add `refholder_counts`, bridge fields, cache APIs, Checksum/Buffer wrappers, and worker no-ops.
- Centralize entry creation/demotion.
- Correct every eviction and scratch-purge gate.
- Add logger warnings and bool return semantics for both decrement systems.

Acceptance after Phase 1:

- One and one thousand logical refholder refs set one bridge and produce identical eviction
  interest.
- Manual refs and the bridge cannot decrement one another.
- Protected entries survive a zero-cap eviction pass; unprotected expired entries demote.
- Equal-checksum acquire-before-release never exposes a false bridge.
- Acquiring a refholder ref for a checksum whose buffer is absent balances correctly.

Focused command from `seamless-core`:

```bash
for test_file in tests/test_buffer_cache.py tests/test_reference_lifecycle_cache.py; do
  conda run -n seamless1 python -m pytest -q "$test_file" || exit 1
done
```

### Phase 2 — Identity registry and audit primitives

Implementation:

- Add `reference_lifecycle.py`, identity-safe registration, snapshot/reverse-index helpers, and
  deterministic warning formatting.
- Add protocol test doubles with semantic fields, idempotent cleanup, duplicate roles, failing
  claim methods, and deliberately broken finalizers.
- Do not integrate full `seamless.close()` yet; invoke audit helpers directly in unit tests.

Acceptance after Phase 2:

- The registry never keeps a holder alive.
- Two distinct value-equal objects are both registered.
- A non-weak-referenceable holder fails registration loudly.
- Count greater than claims and claims greater than count produce different warnings.
- A holder claim method that raises is warned and cannot abort other auditing.

Focused command:

```bash
conda run -n seamless1 python -m pytest -q tests/test_reference_lifecycle_registry.py
```

### Phase 3 — Standalone Cell and Expression lifecycle

Implementation:

- Add Cell weakref support, registration, checksum-input replacement/copy/binding cleanup, and
  protocol methods.
- Add Expression weakref support and identity-excluded result lifecycle state.
- Split public and internal evaluation paths.
- Centralize input-tempref refresh and result publication for all local/remote/cache paths.
- Remove the strong Expression-result Buffer dictionary.

Acceptance after Phase 3:

- A standalone checksum-backed Cell survives forced tempref expiry and releases on replacement,
  derivation destruction, binding, and cleanup.
- Standalone Cell has no result ownership; its temporary Expression convenience path leaves only
  result tempref protection after return.
- Dormant Expression does not refhold its input.
- Public Expression evaluation holds one result ref; repeated calls do not multiply it; internal
  evaluation holds none.
- A result internally published first is acquired once when a later public call expresses
  interest.
- Distinct equal Expressions hold and release independently.

Focused command:

```bash
for test_file in \
  tests/test_cell_reference_lifecycle.py \
  tests/test_expression_reference_lifecycle.py \
  tests/test_expression_local_evaluation.py \
  tests/test_expression_remote_evaluation.py \
  tests/test_expression_fingertip.py; do
  conda run -n seamless1 python -m pytest -q "$test_file" || exit 1
done
```

### Phase 4 — Transformer builder, PreTransformation, and CodeManager

Implementation:

- Make builder wrappers lifecycle-aware and register standalone builders.
- Add temporary PreTransformation ownership and acquire-before-release transfer.
- Migrate CodeManager from manual active sets to logical refholder calls/protocol.
- Audit code/module/pin replacement, deletion, snapshots, Context binding, and destructor paths.
- Create `tests/test_pretransformation.py` and `tests/test_code_manager.py`; these are new focused
  lifecycle files, not alternate names for existing tests.

Acceptance after Phase 4:

- Checksum-bound standalone pins survive forced expiry before a call.
- Ordinary Python literal pins remain direct data and add no premature checksum hold.
- Replacement/deletion/binding/destruction balance exact roles.
- PreTransformation scratch temprefs are never decref'ed as refholder/manual references.
- Several CodeManager roles for one checksum yield the correct logical multiplicity and one
  bridge; manager cleanup returns it to zero.

Focused command from `seamless-transformer`:

```bash
for test_file in \
  tests/test_transformer_reference_lifecycle.py \
  tests/test_pretransformation.py \
  tests/test_code_manager.py; do
  conda run -n seamless1 python -m pytest -q "$test_file" || exit 1
done
```

Do not substitute `test_bash_pretransformation.py`; it covers a different subject. Add other new
focused files rather than hiding lifecycle cases in unrelated broad suites.

### Phase 5 — Transformation inputs, handoff, definition, and result

Implementation:

- Store/directly enumerate all concrete input roles.
- Refactor sync and async dependency completion so each concrete result is adopted before any
  further wait.
- Refhold the constructed definition checksum.
- Add result-hold mode and public/internal entry-point split across local, remote, worker, and
  Dask paths.
- Route every Dask definition/result assignment through the same Transformation publication
  helpers; do not duplicate lifecycle logic in the mixin.
- Integrate cancellation and destructor cleanup.

Acceptance after Phase 5:

- A Transformation input survives an artificial delay while another dependency is pending.
- The test fails without adoption even when temprefs are forced to expire immediately.
- Expression-to-Expression chains refresh temprefs without logical refholder counts.
- Public result entry points hold exactly once; internal dependency evaluation holds no producer
  result.
- Downstream adoption outlives producer cleanup.
- Definition and input roles remain held after completion and release on cleanup/cancellation.
- Failure and cancellation publish no result ref.

Focused command:

```bash
for test_file in \
  tests/test_transformation_reference_lifecycle.py \
  tests/test_expression_transformation_dependencies.py; do
  conda run -n seamless1 python -m pytest -q "$test_file" || exit 1
done
for test_file in tests/cancellation/test_*.py; do
  conda run -n seamless1 python -m pytest -q "$test_file" || exit 1
done
```

Then from `seamless-dask` run the existing Transformation mixin/client tests plus a new focused
lifecycle-publication test:

```bash
conda run -n seamless1 python -m pytest -q tests/test_transformation_reference_lifecycle.py
```

Use the repository's actual test module name if its suite groups mixin tests differently. Run
relevant Dask dependency tests when the optional Dask services are available; the
public/internal flag split must not diverge by backend.

### Phase 6 — Context ownership and workflow collection

Implementation:

- Register Context, remove `_checksum_holds`, and migrate producer refs.
- Route every current-result mutation through acquire-before-release helpers.
- Add retained superseded-result lifecycle to scheduler transitions.
- Cover builder binding, connection replacement, node/subcontext deletion, copy, graph load,
  prune, deadline/cap expiry, and Context cleanup.
- Rewrite `tests/test_garbage_collection.py` from the superseded N-manual-ref assertions to
  logical refholder multiplicity, zero manual refs, and one boolean bridge.
- Replace direct stderr underflow reporting with central logger behavior.

Acceptance after Phase 6:

- Context literals, pins, code dependencies, current results, and retained superseded results
  survive forced expiry for exactly their policy lifetime.
- Two Context roles for one checksum produce logical count two, manual count zero, and one
  bridge.
- Bound handle creation/destruction changes no count.
- Graph copy/load produces independent roles; delete/replacement/prune/destruction releases them.
- A missing workflow literal remains captured in `.exception` with no console output.
- Context `_refheld_checksums()` exactly matches graph/runtime semantic state without a mirror
  counter.

Focused command from `seamless-workflow`:

```bash
for test_file in \
  tests/test_garbage_collection.py \
  tests/test_literal_retention.py \
  tests/test_runtime_and_prune.py \
  tests/test_context_basics.py \
  tests/test_dependencies_and_pins.py; do
  conda run -n seamless1 python -m pytest -q "$test_file" || exit 1
done
```

### Phase 7 — Shutdown integration and final call-site migration

Implementation:

- Place the audit/cleanup phases into `seamless.close()` in the exact order in §10.
- Ensure worker processes remain excluded.
- Complete the repository-wide manual/refholder call-site migration.
- Add matching release paths for intentional CLI/transport manual refs.
- Test explicit close and atexit in subprocesses; never call irreversible `seamless.close()` in
  the middle of a shared pytest process.

Acceptance after Phase 7:

- A balanced subprocess emits no `seamless.references` warning.
- Deliberate over-hold, under-hold, dead-holder leak, missing bridge, manual leak, manual
  over-decref, refholder over-decref, and cleanup exception each produce the intended warning.
- Close is idempotent and atexit uses the same audit once.
- Buffer flush precedes forced reference cleanup.
- Post-cleanup maps/counts/bridges are zero/empty in a balanced subprocess.
- Final `rg` shows only reviewed manual calls and no internal lifecycle use of public manual refs.
- A separate `rg` over Seamless modules shows no scheduler/dependency read of public
  `result`, `result_checksum`, `buffer`, or `value`; all such reads use the designated internal
  accessor.

Focused commands:

```bash
conda run -n seamless1 python -m pytest -q tests/test_reference_lifecycle_shutdown.py
conda run -n seamless1 python -m pytest -q tests/test_garbage_collection.py
```

### Phase 8 — Full regression and outcome audit

Run every test file in a fresh pytest process. The component repositories are also run serially:

```bash
run_test_files() {
  while IFS= read -r -d '' test_file; do
    conda run -n seamless1 python -m pytest -q "$test_file" || return 1
  done < <(find tests -type f -name 'test_*.py' -print0 | sort -z)
}

for repository in seamless-core seamless-transformer seamless-workflow seamless-dask; do
  cd "/home/agent/seamless1/$repository" || exit 1
  run_test_files || exit 1
done
```

Then run repository-integrated remote/Dask tests used by the existing CI configuration. Do not
claim those backends covered if their services were unavailable; record the skipped command and
reason in the final implementation report.

Acceptance after Phase 8:

- Repeated replacement of workflow values reaches steady strong-cache usage after superseded
  retention expires/prunes; it does not grow per edit.
- Under a cap smaller than the protected working set, every checksum claimed by a live holder
  remains locally available and memory pressure is warned instead of protected data being
  removed.
- A named forced-cap lifecycle suite sets the soft cap below the live protected working set,
  runs eviction, resolves every claimed checksum through its owning API, and asserts zero
  refetch/recompute events. No ordinary resolution/evaluation failure, using whatever exception
  that owning API normally exposes, is caused by eviction of a checksum still claimed by a live
  refholder.
- All component suites pass and balanced runs leave the `seamless.references` logger empty.

## 13. Required test matrix

In addition to phase-focused tests, preserve this matrix as a review checklist.

### Cache accounting

- zero/one/many refholder count with one boolean bridge;
- zero/one/many manual refs alongside each refholder state;
- both decrement-underflow directions;
- absent-buffer acquisition;
- equal-checksum replacement;
- live/expired tempref interaction;
- scratch purge with/without bridge/manual refs;
- user-requested scratch result protected until Transformation cleanup, alongside an
  unrequested scratch result that remains purgeable; scratch input tempref-only during
  PreTransformation and bridge-protected after Transformation adoption;
- remote registration for first scratch then non-scratch acquisition;
- protected entries excluded from candidate lists and rate-limited memory-pressure warning.

### Object lifecycle

- construction, partial-construction exception, mutation, equal replacement, deletion, copy,
  binding, explicit cleanup, finalizer, and double cleanup;
- repeated same checksum in two roles yields twice;
- holder cycles collected without silent count residue;
- dead broken holder leaves unattributed excess;
- holder claim failure does not abort audit.

### Evaluation and handoff

- local, cached, remote/database, jobserver, worker, and Dask result publication temprefs;
- public-before-result and public-after-internal-result hold transitions;
- multiple public calls exactly one result ref;
- producer cleanup after Transformation adoption;
- immediate Expression chain with fresh tempref at every link;
- one fast and one delayed dependency proves per-result adoption timing;
- success, cache hit, exception, cancellation, and recomputation.

### Partially coupled audit roles

The audit is strongest where claims come from fields independently of acquisition calls. Three
role families are partially coupled to the code that acquires them and therefore need direct
invariant tests in addition to audit tests:

- Expression/Transformation `"result"`: across public-before-result,
  public-after-internal-result, repeated public calls, internal dependency evaluation, failure,
  and cancellation, assert that the semantic claim (`_refhold_result` plus a published result)
  agrees with that object's actual contribution to `refholder_count`, while `_result_refheld`
  accurately gates release;
- CodeManager: exercise every syntactic/semantic direct/guard acquisition and release, including
  several roles for one checksum, and assert the demand-map multiplicity, logical count, and one
  bridge agree. The demand maps express semantic demand and remain useful audit evidence, but
  they also drive acquisition, so the comparison is not fully independent;
- PreTransformation: mix scratch and non-scratch pins; assert `_value_refs` contains exactly the
  converted non-scratch inputs destined for the Transformation, logical counts match those
  semantic roles, scratch pins are tempref-only, and transfer is acquire-before-release.

A clean audit line alone is not sufficient evidence for these roles. Conversely, independently
derived Cell, Transformer-builder, Transformation input/definition, and Context claims must be
tested to produce a claims-larger-than-count warning when their acquisition is deliberately
omitted.

### Forced-expiry controls

- each checksum-survival test uses unique content and removes temprefs, live Buffer references,
  and weak-cache survival;
- remote/database refetch and fingertip/recompute are disabled or observed with counters;
- each test has a negative-control variant or equivalent mutation evidence showing that removal
  of the acquisition makes the assertion fail.

### Workflow

- cell literal and current result roles;
- transformer literal pin, code, current result, and superseded result roles;
- eager/non-eager demand;
- connection replacing literals;
- node/subcontext delete;
- graph copy/load/replacement;
- retention cap, deadline expiry, and prune;
- bound handles remain neutral;
- unavailable literals populate `.exception` without stderr/logger noise unrelated to the
  deliberate failure.

### Shutdown

- balanced explicit close and atexit;
- each mismatch direction and bridge corruption;
- positive manual refs and both zero-decref warnings;
- deterministic checksum/holder-role ordering;
- IDs excluded from assertions;
- cleanup exception isolation;
- two GC passes and residual detection;
- forced cleanup happens only after warnings and buffer flush.

## 14. Non-goals

- No `ReferenceHolder` class, lease object, holder ID allocator, tombstone, traceback history,
  over-decref event object, generic `_checksum_refs`, or structured audit report.
- No public API for querying holder attribution. Internal snapshot helpers may exist for tests.
- No recursive deep-checksum member ownership.
- No remote/database-side refcount protocol change.
- No audit in execution worker processes; worker primitives remain no-ops.
- No guarantee across `fork()` after threads/cache initialization beyond current Seamless
  process rules.
- No redesign of shared-memory PID reference counts; they are a different subsystem.
- No conversion of current workflow direct-call evaluation into private E/T objects.
- No attempt to name a holder that was already garbage-collected.

## 15. Final implementation report requirements

The implementing agent's final report must include:

1. one-line outcome summary;
2. component commits, grouped by repository and phase;
3. exact focused and full-suite commands run in `seamless1`, with pass/fail/skip counts;
4. remote/Dask coverage actually exercised and any services unavailable;
5. final `rg` classification of remaining public manual incref/decref call sites;
6. confirmation that balanced subprocess shutdown emitted no `seamless.references` warning;
7. confirmation that forced-expiry tests defeated all six masking mechanisms—temprefs, live
   Buffer references, weak-cache survival, same-checksum holders elsewhere in the process,
   durable-storage refetch, and recompute—naming any deliberately retained mechanism and why;
8. negative-control evidence that each checksum-survival test fails when its intended
   acquisition is removed;
9. any deviation from this handoff, with rationale and a test proving the replacement contract.

## 16. Coverage map against the handoff-ready criteria

- The plan names concrete repositories, modules, current fields, and current misleading tests,
  including Dask paths that currently bypass central result publication.
- Runtime keep-alive and verification are separate; audit inputs are independently derived where
  semantic state permits, and partially coupled roles have direct invariant tests.
- Ownership is generated by the same-observation-path rule and then made exact per class.
- The identity-registry, slotted weakref, frozen Expression state, current eviction bug, and
  global Expression Buffer hold identified by language review are explicit implementation work.
- Scratch behavior, completed Transformation input lifetime, manual shutdown refs,
  `refhold_result` visibility, and Expression-chain refresh ownership are resolved.
- Context is explicitly the workflow refholder; bound handles are neutral.
- Each phase ends in a working invariant with per-file-process `seamless1` commands before later
  phases depend on it.
- Existing N-manual-ref workflow tests are explicitly migrated to N logical claims plus one
  boolean bridge.
- Worker, deep-checksum, remote-count, fork, and shared-memory boundaries are explicit.
- Acceptance criteria include steady memory, protected-data availability, absence of
  live-holder resolution failures or hidden repair, and warning-free balanced shutdown—not just
  structural conformance.
