# Checksum Reference Lifecycle Plan

## 1. Purpose

Seamless uses two parallel integer reference-count systems to keep checksum-addressed
buffers available while live objects still need them: a logical count for Seamless
refholder classes and the existing cache count used by explicit manual
`incref`/`decref` calls. Correctness comes from per-object lifecycle management. A small
global audit at `seamless.close()` checks that both systems balanced.

The design has three deliberately simple pieces:

1. a refholder multiplicity count whose zero-crossings toggle one aggregate eviction
   bridge in the cache entry;
2. a weak registry containing every live Seamless refholding object;
3. a shutdown audit that derives `checksum -> live holders` from those objects and compares
   it with the cache counts.

There are no lease objects, holder IDs, holder-history records, generic per-object checksum
counters, or structured audit-report object.

## 2. Terminology

**Refholder**
: A live Seamless object whose class contract says it owns one or more checksum references.

**Refholder reference**
: A cache reference acquired and released by a refholder as part of its lifecycle.

**Manual reference**
: A reference acquired by a direct public `Buffer.incref()` or `Checksum.incref()` call.

**Tempref**
: Decaying cache interest. It supports short handoffs and cheap Expression evaluation but
  is not part of normal reference-count auditing.

## 3. Refcounts and cache bridge

Rename the existing cache-entry `normal_refs` integer to `manual_refs`, preserving its
current behavior for explicit public `incref`/`decref`. Add a boolean eviction bridge:

```python
@dataclass
class StrongEntry:
    buffer: Buffer | None
    size: int | None
    manual_refs: int = 0
    has_refholder_bridge: bool = False
    tempref: TempRef | None = None
```

Maintain the logical refholder multiplicity outside the cache entry:

```text
refholder_count[checksum] -> non-negative integer
```

The refholder count controls the boolean bridge:

- on `refholder_count` transition `0 -> 1`, set `has_refholder_bridge = True`;
- transitions `N -> N + 1`, for `N > 0`, do not change it;
- transitions `N -> N - 1`, for `N > 1`, do not change it;
- on transition `1 -> 0`, set `has_refholder_bridge = False`.

The bridge is an implementation detail, not a holder object or a manual reference. Its
only purpose is to prevent eviction while at least one refholder exists. Refholder-count
zero-crossings and bridge updates must be atomic under the appropriate lifecycle/cache
lock. The `0 -> 1` path creates or promotes the strong cache entry just as an ordinary
cache increment currently does; the `1 -> 0` path demotes it only if neither manual refs
nor a tempref remain. Remote registration and scratch policy remain orthogonal to this
eviction bridge.

### 3.1 Manual API

Existing public calls keep their meaning:

```python
checksum.incref()
checksum.decref()
buffer.incref()
buffer.decref()
```

They modify `manual_refs` only. A manual `decref` when `manual_refs == 0` does nothing and
emits a warning through the logger. It cannot consume the boolean refholder bridge.

### 3.2 Refholder API

Internal lifecycle code uses a separate API:

```python
checksum.incref_refholder()
checksum.decref_refholder()
buffer.incref_refholder()
buffer.decref_refholder()
```

These modify `refholder_count` and toggle the cache bridge only on the zero-crossing
transitions described above. `decref_refholder()` when that count is already zero does
nothing and emits a warning. No event history is stored.

This API does not receive the holder object. Holder attribution is reconstructed when
needed by traversing the weak registry and inspecting each live object's known ownership
fields.

### 3.3 Eviction

An entry can be demoted or evicted only when all three conditions hold:

```text
manual_refs == 0
and has_refholder_bridge is False
and no live tempref exists
```

Thus any nonzero `refholder_count` gives exactly the required eviction protection.
Temprefs may expire normally. If memory limits cannot be met because all remaining buffers
have references, report memory pressure rather than deleting referenced data or its
accounting.

## 4. Weak refholder registry

Maintain a process-global identity-based weak collection of every live refholding object.
A `weakref.WeakSet` is sufficient. Classes using slots must support weak references.

Register an object when it becomes capable of holding its first reference. It may remain in
the weak set after its current held-checksum list becomes empty; this is harmless. Object
destruction removes it automatically.

No explicit holder key is needed. `id(obj)` is sufficient for formatting diagnostics while
the object is alive. We do not preserve information about dead holders.

Each refholding class implements a small audit protocol:

```python
def _refheld_checksums(self) -> Iterable[tuple[Checksum, str]]:
    """Yield one item per currently held reference.

    The string describes the owning field or pin for warning output.
    Repeated checksums are yielded repeatedly when the object owns multiple refs.
    """
```

There is no generic `_checksum_refs` counter. The method derives ownership directly from
the object's real state. For example:

- a standalone Cell yields its checksum input;
- a standalone Transformer yields each checksum-bound pin;
- a Transformation yields its concrete inputs and, when applicable, its held result;
- a Context yields each literal producer and current/retained result it owns.

Because the registry is weak, a holder that dies incorrectly without decrementing cannot
be named at shutdown. Its effect is still detected as an excess `refholder_count` not
explained by any live holder. Other live holders of the same checksum can still be listed.

## 5. General lifecycle contract

- Every object that promises later use of a checksum calls `incref_refholder()`.
- It calls `decref_refholder()` on replacement, deletion, explicit destruction, or normal
  object destruction.
- Cleanup is idempotent.
- Replacement acquires the new checksum before releasing the old one.
- Copying a refholding object creates an independent reference.
- Serialization stores checksums but owns no local references. Deserialization into a live
  object acquires new references.
- A bare `Checksum` is not a refholder.
- Two objects holding the same checksum contribute two to `refholder_count`, while setting
  only one boolean cache bridge.
- One object holding the same checksum through two independent fields contributes two
  references and yields it twice from `_refheld_checksums()`.

## 6. Ownership by object type

### 6.1 Standalone Cell builder

A standalone Cell refholds a concrete checksum input because it promises a future
`build()`, `compute()`, or `run()` remains possible. It releases the old checksum when the
input changes and releases its current checksum on destruction.

The standalone Cell builder has no result-checksum state and no `.value` API. An explicitly
built Expression owns its own result state; standalone `Cell.compute()` and `Cell.run()`
delegate through a temporary Expression.

A bound Cell's `.value` does not build an Expression. It asks the Context to materialize
the Context-owned current checksum (or projection) directly. The result ownership in that
case therefore remains with the Context.

`Cell.compute()` creates a temporary Expression and returns a tempref-backed checksum. The
temporary Expression's explicit-result hold ends when that temporary object dies; the Cell
does not adopt the result. `Cell.run()` resolves the value immediately.

### 6.2 Expression

An Expression does not normal-refhold its input. Expression evaluation is cheap and occurs
immediately once the input is concrete. A fresh or refreshed tempref, with an ordinary
expiry of dozens of seconds or longer, covers evaluation and handoff.

An Expression deliberately left dormant beyond that horizon does not retain its input
indefinitely merely by existing. It may resolve from durable storage, fingertip/recompute,
or report a cache miss according to the normal availability policy.

An Expression has:

```python
refhold_result: bool = False
```

An explicit public `compute()`, `compute_async()`, or `run()` call performs the ownership
operation:

```python
expression.refhold_result = True
```

On the `False -> True` transition, the Expression increfs its result if already present. If
the result is not present, later successful result publication sees the flag and increfs it.
Repeated assignment of `True` does nothing. Transition to `False` during explicit release
or destruction decrefs a held result.

Dependency evaluation uses an internal method that does not enable `refhold_result`.

### 6.3 Standalone Transformer builder

A standalone Transformer refholds every concrete checksum-bound pin, code input, or module
input that it promises to use on a later call. Pin replacement/deletion and builder
destruction release the corresponding references.

Calling the reusable builder does not transfer its references away. The resulting
Transformation independently acquires the concrete inputs it needs.

The Transformer builder has no result or result-checksum state. `Transformer.compute()`
returns a tempref-backed checksum from a temporary Transformation, and
`Transformer.run()` resolves the value immediately. Persistent result interest requires
retaining an explicitly built Transformation or adopting its checksum into another holder.

### 6.4 Transformation

A Transformation normal-refholds each concrete input as soon as that input becomes
available. This includes dependency results that arrive while other dependencies are still
pending. It releases those inputs when it can no longer execute/re-execute or when it is
destroyed.

A Transformation also has `refhold_result = False`, with the same transition semantics as
Expression. Explicit public `compute()`, `computation()`, `run()`, or `task()` only enables
this mode. Internal dependency evaluation does not.

Every result receives a fresh/refreshed tempref on publication. When
`refhold_result is True`, result publication additionally calls `incref_refholder()`.

### 6.5 Context and context-bound handles

`Context` is a refholder class and registers itself in the weak refholder registry. Bound
Cell and Transformer handles are ephemeral views and hold no references themselves. The
Context owns:

- cell literal producers;
- Transformer-pin literals;
- current cell and Transformer results exposed as workflow state;
- any deliberately retained superseded results.

The Context acquires a result before publishing it as current/retained state and releases
the old result on replacement, node deletion, graph replacement, or Context destruction.

Context-private Expressions and Transformations are scheduler evaluation objects. They:

- hold concrete inputs only while evaluation may need them;
- publish outputs under a tempref;
- keep `refhold_result = False`;
- release inputs and normally die after completion, once the Context has adopted any result
  it retains.

Calling `compute()` or `run()` through a bound handle changes Context demand/result
ownership. It does not enable `refhold_result` on a private E/T.

### 6.6 Process-global managers

Managers such as `CodeManager` that own checksum refs register as refholders and implement
the same `_refheld_checksums()` protocol. Existing manager-specific integer maps may remain
their source of ownership state.

## 7. Dependency handoff

Handoff must occur before the producer's tempref may expire.

### 7.1 Dependent Transformation

When an Expression or Transformation result becomes a concrete input of a downstream
Transformation, the downstream Transformation immediately calls `incref_refholder()` for
that input. It can then safely wait for other inputs. The producer needs no normal result
reference on behalf of this dependent.

The current Transformation dependency-preparation path must be audited so every resolved
dependency checksum becomes a held concrete input.

### 7.2 Dependent Expression

When the dependent is another Expression, make or refresh a tempref on the input checksum
and evaluate the dependent immediately. The dependent Expression does not increment the
refholder count. Its result receives another fresh/refreshed tempref.

## 8. Global collection and audit

The audit is intentionally procedural and logger-based. No `ReferenceAuditReport` class or
public report object is required.

### 8.1 Shutdown sequence

Integrate the following into `seamless.close()` after new work is prohibited but before
buffer-cache teardown:

1. Cancel or settle running local and remote work.
2. Snapshot the weak registry and build a reverse index from live holders:

   ```text
   checksum -> [(holder_object, description), ...]
   ```

   Iterate `_refheld_checksums()` and include one entry per held reference. Use `id(obj)`,
   class name, repr/path where useful, and the yielded description only for formatting.
3. Snapshot each checksum's logical `refholder_count`, `manual_refs`, and
   `has_refholder_bridge`.
4. For each checksum, compare:

   ```text
   len(reverse_index[checksum]) == refholder_count[checksum]
   ```

   A mismatch emits a warning. If the integer is larger, report the unexplained excess and
   note that a holder may have died without decrementing. If the reverse index is larger,
   report missing refholder refs/over-decrement. List all still-live holders for the
   checksum.
5. Verify `has_refholder_bridge == (refholder_count > 0)` and warn on a mismatch. Warn for
   every positive `manual_refs` count.
6. Flush required buffers while references still retain them.
7. Invoke cleanup hooks and call the idempotent cleanup method of every live registered
   refholder.
8. Run `gc.collect()` twice.
9. Inspect the cache again:
   - `refholder_count` must be zero; otherwise warn that lifecycle cleanup/general Python GC
     did not release all refholder references;
   - `has_refholder_bridge` must be false;
   - `manual_refs` must be zero; any positive count consists entirely of unmatched manual
     refs.
10. Force-clear residual counts after warnings so shutdown finishes deterministically.

The pre-cleanup mismatch warnings are not erased by successful forced cleanup. Explicit
`seamless.close()` and atexit use the same audit.

### 8.2 Warning format

Use a dedicated logger, for example `seamless.references`. Balanced shutdown emits no
warning.

Warnings should be deterministic and concise:

```text
Checksum <hex> has refholder count 3, but 2 live holders were found
  Transformation 0x... input:x
  Context 0x... transformer:tf:result
  1 reference is unattributed; its holder may have died without decref

Checksum <hex> has 2 unmatched manual references at shutdown

Checksum <hex> has refholder count 1 but its eviction bridge is absent

Manual decref ignored for checksum <hex>: manual refcount is already zero
```

No creation traceback, dead-holder tombstone, or stored event history is required.

## 9. Implementation order

1. **Refholder counter and cache bridge**
   - add the checksum-indexed `refholder_count`;
   - rename the cache-entry count to `manual_refs` and add `has_refholder_bridge`;
   - add refholder APIs;
   - toggle the bridge only on `0 -> 1` and `1 -> 0` refholder transitions;
   - warn on zero-count decrefs;
   - evict only when the manual count, bridge, and tempref all permit it.
2. **Weak registry and audit protocol**
   - add the identity-based weak set;
   - add registry helpers;
   - implement reverse-index construction and logger warnings.
3. **Standalone core lifecycle**
   - Cell input refholding;
   - Expression tempref input behavior and `refhold_result`.
4. **Transformer lifecycle**
   - standalone builder input refs;
   - Transformation concrete-input refs;
   - dependency handoff;
   - Transformation `refhold_result`;
   - CodeManager registration.
5. **Workflow lifecycle**
   - migrate literal producer refs to `incref_refholder`;
   - add current/retained result refs;
   - cover mutation, copy/load, deletion, and destruction;
   - keep private E/T result-ref-neutral.
6. **Shutdown integration**
   - settle work;
   - audit before cleanup;
   - clean live holders and run Python GC;
   - audit residual counts and warn;
   - force-clear.
7. **Call-site audit**
   - inspect every `incref`/`decref` in all repositories;
   - classify each as manual or refholder-owned;
   - migrate internal lifecycle calls to the refholder API.

## 10. Tests

### Cache and registry

- multiple logical refholders set exactly one boolean cache bridge;
- the first logical refholder creates the bridge and the last removes it;
- manual refcounts remain unchanged alongside zero, one, and many logical refholders;
- neither decrement API consumes the other system's count or bridge;
- zero-count decrements warn and leave counts unchanged;
- a positive refholder count prevents eviction through the bridge;
- weak registration does not keep objects alive;
- reverse-index multiplicity matches independently held fields.

### Standalone objects

- Cell checksum inputs survive forced tempref expiry;
- Cell input replacement/destruction balances refs;
- Transformer checksum-bound pins survive forced expiry;
- pin replacement/deletion/destruction balances refs;
- builders have no result-checksum state;
- builder `compute()` returns a tempref-backed result without builder result ownership;
- explicitly built E/T public compute/run enables `refhold_result` once;
- repeated public calls do not add refs;
- implicit completion followed by public compute/run refs the existing result;
- implicit dependency evaluation does not enable `refhold_result`;
- dormant Expressions do not normal-refhold inputs;
- Expression-to-Expression handoff refreshes temprefs;
- Transformation dependencies are normal-refheld as soon as concrete.

### Workflows

- Context registers weakly as a refholder and reports all workflow-owned checksums;
- literal cell and pin producers balance;
- current results remain available after tempref expiry;
- result replacement, node deletion, graph replacement, copy/load, and Context destruction
  balance refs;
- bound handles add no refs;
- private E/T outputs remain normal-ref-neutral;
- bound compute/run changes Context ownership only.

### Shutdown audit

- a balanced run emits no reference warnings;
- an intentionally leaked refholder count produces a mismatch warning with live holders;
- a holder that dies incorrectly produces an unattributed excess warning;
- a refholder undercount reports the live holders that still claim the checksum;
- positive manual refs warn;
- manual decref at zero warns immediately;
- cleanup plus two GC passes leaves the refholder count and manual count zero and the bridge
  false in a balanced run;
- residual counts warn and are force-cleared;
- explicit close and atexit are idempotent.

## 11. Acceptance criteria

- Seamless maintains a logical integer refholder count, a cache-entry integer manual count,
  and exactly one boolean cache bridge while the logical count is positive.
- All refholding classes register weakly and expose their currently held checksums directly
  from real object state.
- A workflow `Context` is the refholder for its literals and current/retained results;
  context-bound Cell and Transformer handles are not refholders.
- Standalone builders retain configured inputs but never own results.
- Transformations retain concrete inputs while waiting; Expressions use temprefs and
  immediate evaluation.
- Explicit public E/T evaluation controls result ownership solely through
  `refhold_result`.
- Context-private E/T outputs remain unheld by their producer and are adopted by Context
  when needed.
- Shutdown compares live-holder multiplicity with `refholder_count`, checks that the bridge
  matches whether that count is positive, cleans live holders, runs Python GC, and verifies
  the refholder and manual counts reach zero and the bridge becomes false.
- Balanced execution emits no reference-lifecycle warning.
