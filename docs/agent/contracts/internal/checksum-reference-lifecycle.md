# Checksum reference lifecycle (internal contract)

**A buffer survives because a live object makes a semantic claim on its checksum.** The claim is registered, attributable, acquired once per role and released once per role, and it is audited at shutdown. Nothing else keeps data from being demoted: not a `Checksum` object, not a tempref, not a remote registration.

This mechanism is **internal**. It lives in `contracts/internal/`, apart from the user-visible contract pages, because it is not user-visible behaviour: the only trace a user ever sees is a `seamless.references` warning at shutdown. It still needs a precise written contract, and this page is that contract.

Two neighbouring mechanisms are kept apart on purpose, with their own vocabularies:

- **The workflow node state lifecycle** is the `Context`'s seven-state node machine, its cascade and its speculative supersession. It is user-visible behaviour, documented in `contracts/node-state-lifecycle.md`. This page is only about who keeps a checksum's buffer alive. Where the two meet (a speculative grace hold), the node state lifecycle decides *when* to hold, and this page owns only the claim (§6).
- **The cancellation waiting set** is the membership set of callers that still want a shared, in-flight Expression evaluation, keyed by **Expression identity** (`contracts/expressions.md`, *Deduplication* and *Cancellation*). It tracks who still wants a result; a reference keeps a buffer alive once it exists. The waiting set is a "waiting set", never a "refcount". It does hold **one** refholder claim of its own, on the evaluation's input, which is neutral (§1, §6).

Code locations:

| Concern | Repository and modules |
|---|---|
| Accounting, the weak registry, the audit, explicit and `atexit` shutdown | `seamless-core`: `seamless/caching/buffer_cache.py`, `seamless/reference_lifecycle.py`, `seamless/shutdown.py` |
| Cell and Expression ownership, the waiting set's claim, the forced-expiry test helper | `seamless-core`: `seamless/cell_class.py`, `seamless/expression_class.py`, `seamless/checksum/expression.py` |
| Builder roles, temporary transfer, dependency adoption, definition and result roles, cancellation | `seamless-transformer`: `transformer_class.py`, `pretransformation.py`, `transformation_class.py`, `code_manager.py`, and the worker paths |
| Context producer, current and superseded ownership; binding, replacement, deletion, graph lifecycle | `seamless-workflow`: `context.py`, `graph.py`, `scheduler.py`, `builder_state.py`, `adapters.py` |
| Cached, thin and fat result publishing, scratch, failure, cancellation | `seamless-dask`: `transformation_mixin.py`, `client.py` |
| Stored Expression rows (the one durable refholder, §6) | `seamless-database`: `database.py`, `database_models.py` |

## 1. Terminology

The present tense is normative.

**Checksum**: a content address. A bare `Checksum` object owns no lifecycle reference merely by existing.

**Concrete checksum**: a checksum known now, after the receiving API has applied its normalization rules. A result that has not been computed is non-concrete. Concreteness does not imply that the buffer is locally available.

**Refholder / semantic claim**: a registered live object implementing `_refheld_checksums()` and `_release_refholds()`. Each `(checksum, role)` item that `_refheld_checksums()` yields is **one semantic claim**. A checksum held for distinct roles, or with a multiplicity, is yielded once per claim.

**Refholder reference**: one unit in `BufferCache.refholder_counts[checksum]`, acquired through `incref_refholder()` and released through `decref_refholder()`. It never changes `manual_refs`.

**Manual reference**: one unit in `StrongEntry.manual_refs`, acquired through the public low-level lease API `Checksum.incref()` / `Buffer.incref()`. **Lifecycle owners use refholder references, never manual ones.**

**Refholder bridge**: `StrongEntry.has_refholder_bridge`, true exactly when the logical refholder count is positive. It protects the strong entry from demotion. It is neither a manual reference nor a holder object.

**Tempref**: refreshable, decaying, unattributed cache interest for a bounded same-path handoff. It is **not** balanced by the lifecycle audit and is **insufficient across an unbounded yield, wait or queue**. A tempref **never writes** a buffer to the hashserver and is **neutral about scratch status**: it neither marks a checksum scratch nor clears that mark.

**Scratch status**: membership of the buffer cache's scratch set. It records an owner's or producer's *decision*, never the mere absence of a durable claim.
- It is set by a scratch `incref` / `incref_refholder`, or by `mark_scratch()`: a scratch Transformation's result, a buffer an Expression evaluation produced, a fingertipped buffer.
- It is cleared by a non-scratch `incref` / `incref_refholder`, or by a `transfer_write()`.
- `PreTransformation` reads it to decide whether an input gets a refholder claim or only a tempref.

**Transfer write**: `transfer_write()`, an explicit write of a buffer to the hashserver made on a requester's behalf, without any claim (§8). It clears scratch status.

**Claim kinds.** `BufferCache.incref_refholder(checksum, buffer=None, scratch=…)` takes three values of `scratch`, and every claim is exactly one of them:

| `scratch=` | Kind | Protects from eviction | Publishes | Scratch status |
|---|---|---|---|---|
| `False` (the default) | non-scratch owner claim | yes | **yes** (§8) | cleared |
| `True` | scratch owner claim | yes | no | set |
| `None` | **neutral claim** | yes | no | unchanged |

A **neutral claim** is for a claim that is not an owner's decision about persistence. The neutral claims are:
- a `Context`'s snapshot and in-flight leases;
- an `Expression`'s `"result"` role (§6);
- an anonymous or projection handle's `"result"` role (§6);
- **the waiting set's in-flight claim** on an evaluation's input, which it holds until the shared task finishes, including through the linger (§6).

An owner's claim is `scratch=False` or `scratch=True`, and follows the owner's scratch policy (`Cell.scratch`, the Transformer's or Transformation's `scratch`, a Context node's configured scratch).

**No claim held for a scratch node publishes.** This is a ruling, and it covers every claim the `Context` holds for a scratch node:
- the current claim (`node:<path>:current`, and `anonymous:<symbol>:current`);
- superseded-run claims (`node:<path>:superseded:<generation>`);
- literal claims (`cell:<path>:literal`);
- transformer pin, code and module claims;
- copied-current claims, which a subcontext copy acquires for the copied node.

Each such claim neither publishes nor clears scratch status. (Several of these do today; see §10.) Whether the ruling also covers the definition write of a scratch Transformation is deferred (§8, *The definition write*).

**Recording**: making a successful Expression or Transformation result **checksum** visible. Local execution, cache, database, remote, jobserver, worker and Dask success paths all record. Every success temprefs before recording, and repeated deterministic recording is idempotent for result ownership. **Failure and cancellation record nothing.**

**Publishing**: writing a **buffer** to the hashserver. For results it happens on a **non-scratch incref** and nowhere else (§8, *Buffer persistence*); a transfer write is the one non-claim write (§8).

> **One vocabulary across every page (ruled 2026-09-21).** *Publishing* is the buffer write; *recording* is what happens to a result checksum. They follow different rules: recording always happens on success, and a buffer is written only when somebody increfs it non-scratch. `contracts/scratch-witness-audit.md`, `contracts/expressions.md` and `contracts/identity-and-caching.md` use the same vocabulary. The code's former `_publish_expression_result` did neither; it is now **`_tempref_expression_result`**, which registers a tempref and marks a buffer the evaluation produced as scratch.

**Adoption / handoff**: a consumer validates a concrete checksum, acquires its own semantic role, records that role, and only then yields or waits. Adoption is independent ownership: it does not transfer the producer's reference. An Expression consumer instead refreshes a tempref and consumes on the same path (§7).

**Public result interest**: an explicit user request to compute, schedule or read an Expression or Transformation result, or a pull through an anonymous or projection handle. It enables that producer's `"result"` role. Framework bookkeeping and dependency access are **internal interest** and stay producer-neutral.

**Demotion, eviction, forced expiry**: demotion removes a strong-cache entry while a still-live Buffer may remain weakly reachable. Eviction is pressure-selected demotion under the same predicate. **Forced expiry is a test procedure** that removes every non-role survival path and then evicts; it is not a production operation.

**Balanced**: for every checksum before shutdown cleanup, the logical count equals the number of live semantic claims, and the bridge equals `(count > 0)`. After holder cleanup and forced accounting cleanup, counts, bridges and manual references are zero; only a live-tempref entry with snapshot `(0, 0, False)` may remain.

## 2. Three kinds of cache interest, one demotion predicate

`StrongEntry` carries `buffer`, `size`, `manual_refs`, `has_refholder_bridge` and `tempref`. The logical refholder multiplicity lives **outside** the entry, as `refholder_count[checksum]`: the entry holds one boolean where the count holds an integer, and the integer is what is audited.

| Interest | Where it lives | Who sets it | Attributable | Audited | Survives an unbounded yield |
|---|---|---|---|---|---|
| Manual reference | `StrongEntry.manual_refs` | any caller of the public lease API | no | counted, and warned when positive at shutdown | yes, until `decref()` |
| Refholder reference | `refholder_count[checksum]`, mirrored on the entry as one boolean bridge | lifecycle owners, through the internal API | yes, through the weak registry | yes | yes, until `decref_refholder()` |
| Tempref | `StrongEntry.tempref` | any producer or consumer on a bounded same path | no, by design | no | **no** |

The bridge follows the count's zero crossings only:

| Transition | Effect |
|---|---|
| `0 → 1` | sets `has_refholder_bridge = True` and creates or promotes the strong cache entry |
| `N → N+1` and `N → N−1` for `N > 1` | nothing |
| `1 → 0` | clears the bridge, and demotes the entry **only if** no manual refs and no live tempref remain |

Zero crossings and bridge updates are atomic under the lifecycle/cache lock.

**The demotion predicate:**

```text
manual_refs == 0
and has_refholder_bridge is False
and no live tempref exists
```

A nonzero refholder count therefore gives exactly the required eviction protection, no more and no less. Temprefs expire normally. If a memory limit cannot be met because every remaining buffer is referenced, Seamless **reports memory pressure** rather than deleting referenced data or its accounting.

## 3. The two APIs

|  | Public, manual | Internal, lifecycle |
|---|---|---|
| Spellings | `checksum.incref()` / `checksum.decref()`, `buffer.incref()` / `buffer.decref()` | `checksum.incref_refholder()` / `checksum.decref_refholder()`, and the `Buffer` equivalents |
| Backing call | — | `BufferCache.incref_refholder(checksum, buffer=None, scratch=False)` / `decref_refholder()`; `scratch` takes `False`, `True` or `None` (§1) |
| Modifies | `manual_refs` only | `refholder_count`, and the bridge on zero crossings only |
| Called at zero | does nothing, warns through the logger | does nothing, warns |
| Receives the holder object | n/a | **no**: attribution is reconstructed from the registry when needed |
| Who uses it | users, low-level leases | lifecycle owners only |

The manual API can never consume the refholder bridge, and the lifecycle API stores **no event history**.

**Snapshot (internal/test):** `BufferCache.reference_snapshot() -> dict[Checksum, tuple[refholder_count, manual_refs, has_refholder_bridge]]`.

## 4. The weak refholder registry

The registry is a process-global, **identity-keyed weak** collection of every live refholding object. A `WeakSet` suffices, and slotted classes must support weak references. It is populated by `register_refholder()`.

- An object registers when it becomes able to hold its first reference. It may stay registered after its held list empties; that is harmless. Destruction removes it automatically.
- No holder key is needed: `id(obj)` suffices for formatting while the object is alive, and nothing about dead holders is kept.
- Each refholding class implements:

```python
def _refheld_checksums(self) -> Iterable[tuple[Checksum, str]]:
    """Yield one item per currently held reference; the string names the owning field or pin."""
```

`_refheld_checksums()` is **side-effect free** and derives ownership from the object's real state; there is no generic acquisition mirror and no generic `_checksum_refs` counter. `_release_refholds()` is **idempotent**.

Because the registry is weak, a holder that dies without decrementing cannot be named. Its effect is still detected, as an excess `refholder_count` that no live holder explains, and the other live holders of the same checksum are still listed (§9).

## 5. Governing invariants

For every checksum `c` during normal runtime:

```text
refholder_count[c] == number of live semantic claims for c
has_refholder_bridge[c] == (refholder_count[c] > 0)
```

And:

- each owner acquires once per semantic role and releases once per semantic role;
- **replacement is: acquire the new roles, install the new state, then release the old roles**, including when the replacing checksum equals the replaced one;
- a producer `"result"` role represents **public** interest only; framework dependency access stays neutral;
- a Transformation **adopts each dependency before waiting for another dependency**;
- **a bound handle onto a named node owns no references**; the Context owns the bound state. **Anonymous and projection handles are the exception:** each holds a scratch-neutral `"result"` claim on what it pulled, and releases it when the handle dies (§6);
- audit claims come from semantic fields or demand maps, not from a generic acquisition mirror.

**Finalizers are idempotent backstops, not the primary correctness mechanism.** Explicit paths (replacement, deletion, `close()`, graph replacement) are what release claims in the normal case. A release that can only belong to object death, such as a handle's `"result"` claim, runs from the finalizer, but correctness never depends on its timing: a late finalizer only keeps a buffer alive longer, and `seamless.close()` releases every live registered holder anyway (§9, step 7). A finalizer never mutates shared state that another thread owns. **In particular, the finalizer of an anonymous node's handle does no accounting of its own: it only posts a removal to the Context's controller.** The controller removes the symbol entry and releases `anonymous:<symbol>:current` on its own thread, under the normal replacement and deletion ordering. A posted removal for an entry that is already gone is a no-op, so the post is idempotent.

General rules:

- every object that promises later use of a checksum calls `incref_refholder()`, and calls `decref_refholder()` on replacement, deletion, explicit destruction or normal object destruction;
- cleanup is idempotent;
- copying a refholding object (including `copy.copy` and `copy.deepcopy` of a Cell or an Expression) creates an **independent** reference;
- serialization stores checksums and owns no local references; deserialization into a live object acquires new ones;
- a bare `Checksum` is not a refholder;
- two objects holding one checksum contribute **two** to the count while setting **one** boolean bridge; one object holding it through two independent fields contributes two and yields it twice.

## 6. Ownership by object type

This table is the normative ownership and ordering contract. The *Kind* column uses the three claim kinds of §1.

| Owner | Semantic roles | Kind | Acquisition and release |
|---|---|---|---|
| Standalone `Cell` | `"input"` for an explicit checksum input; `"result"` for its evaluated result | owner: the Cell's scratch policy | Acquire on construction or replacement. The Context adopts before binding releases it. |
| `Expression` | `"result"`, only after public result interest | **neutral** | Inputs are tempref-only. Internal evaluation records without a claim; the first public call or read acquires the already-recorded result once. The claim protects the result from eviction and does **not** publish it or change its scratch status. Cleanup releases only an acquired result. |
| Waiting-set entry (one per in-flight shared Expression evaluation, keyed by Expression identity) | the evaluation's input (logged as `expression materialization`) | **neutral** | Acquired when the shared evaluation starts; held until its task completes or is cancelled, **including through the linger** after the last member leaves (`contracts/expressions.md`, *Cancellation*); released when the task finishes or the linger expires and the task is cancelled. An unreleased claim here is exactly what the shutdown audit catches. |
| Anonymous or projection handle | `"result"` on the checksum it pulled | **neutral** | Acquired when the handle pulls; a re-pull replaces it (§5 ordering); released when the handle dies. |
| Standalone `Transformer` builder | `"pin:<name>"`, `"code"`, `"module:<name>"` for checksum-backed fields | owner | Wrapper mutation and cloning acquire independently. The Context adopts all roles before the builder becomes a neutral bound handle. |
| `PreTransformation` | `"input:<pin>"` for converted non-scratch pins | owner | Scratch pins are tempref-only and absent from `_value_refs`. The Transformation acquires every input before the PreTransformation releases. CodeManager roles stay separate. |
| `Transformation` | `"input:<pin>"` for direct and adopted dependency inputs; `"definition"`; optional public `"result"` | owner: the Transformation's scratch policy (but see §8 for `"definition"`, and §10 for inputs) | The definition is retained through completion. Each dependency is adopted immediately. A public entry or read enables result holding; internal access stays neutral. Terminal cancellation settles or detaches work, blocks late recording, then releases roles while the fields stay intact. Cancellation after completed recording is a no-op. |
| `CodeManager` | `"syntactic:direct"`, `"syntactic:guard"`, `"semantic:direct"`, `"semantic:guard"` | owner | Each direct or guard multiplicity acquires and releases once. Guard creation and removal follow the demand maps; `_release_refholds()` drains exact multiplicities idempotently. |
| Workflow `Context` | `"cell:<path>:literal"`; `"transformer:<path>:pin:<pin>"`; `"transformer:<path>:code"`; `"transformer:<path>:module:<name>"`; `"node:<path>:current"`; `"node:<path>:superseded:<generation>"`; `"anonymous:<symbol>:current"` | owner: the node's scratch policy; **never publishing for a scratch node** (§1). Snapshot and in-flight leases are neutral. | The Context acquires before installing graph or runtime state and releases the old state afterwards. Current and producer roles are independent even for equal checksums. Superseded roles end on the cap, the deadline, `prune()`, node deletion, graph replacement or cleanup. `anonymous:<symbol>:current` exists **only for non-elided anonymous nodes**, which the Context evaluates itself; it ends when the controller removes the entry (§5). Bound handles onto named nodes own nothing. |
| `seamless-database` stored Expression row, when it stores its path indirectly | the path buffer's checksum | **durable**, out of process | See *The durable refholder* below. |

**Public versus internal interest is a hard rule.** Every public Expression or Transformation API that requests, returns or schedules a result expresses public interest. Dependency helpers, `PreTransformation`, workflow schedulers, backend result-recording code and internal CLI orchestration use named *internal* evaluation and result accessors. **No framework path may create a producer result role merely to inspect a dependency.**

**Anonymous nodes and handles.** A handle's `"result"` claim behaves like an Expression read with public interest: it protects what the handle pulled and never publishes. The Context's `anonymous:<symbol>:current` is a separate claim, held for the node rather than for any handle, and it exists only when the node is not elided. An elided anonymous node is fused into its consumer's Expression and has no result of its own for the Context to hold.

**The Context's `current` and `superseded:<generation>` roles are what makes a speculative grace hold real.** A superseded run's result stays resolvable for as long as the Context holds its role. The policy that decides *when* to hold belongs to the node state lifecycle (`contracts/node-state-lifecycle.md`); this page owns only the claim, and that claim follows the scratch rule of §1.

**The durable refholder.** When a `seamless-database` Expression row stores its path indirectly, as the checksum of the path buffer (because the serialized path is too long to store inline), the row is a **durable claim** on that path buffer: fingertipping the row later needs the buffer, so it must not be evicted from under the row. This is the one refholder outside a Python process. It is not part of `refholder_count`, not seen by the weak registry and not audited at shutdown; it is a property of the database's storage, like the durable remote storage of §8. It does not introduce a cross-process reference-count protocol (§11).

## 7. Dependency handoff

Handoff happens **before the producer's tempref may expire**.

| Consumer | What it does with a concrete producer result | What it owns |
|---|---|---|
| Dependent Transformation | calls `incref_refholder()` for the input **immediately**, and only then may it wait for other inputs | its own `"input:<pin>"` role; the producer needs no result reference on its behalf |
| Dependent Expression | makes or refreshes a tempref on the input checksum and evaluates immediately; it does **not** increment the refholder count | nothing; its own result receives a fresh or refreshed tempref |

A shared Expression evaluation's input is additionally held by the waiting set's neutral claim (§6). That claim belongs to the waiting-set entry, not to the Expression object.

## 8. Scratch, deep checksums, workers, services

**Scratch.** Scratch acquisition does not register a buffer remotely, and later non-scratch interest upgrades registration monotonically. **Explicit public interest in a scratch result refholds and protects it**; an unrequested scratch result stays purgeable. `contracts/scratch-witness-audit.md` defines what scratch means.

**Fingertipping never publishes.** A **fingertip chain always runs locally and never publishes, at any site** (client, jobserver or Dask worker alike). There is no exception: neither an input fingertip inside a job nor a manual fingertip writes to the hashserver, not even the chain's end result. A buffer recovered by fingertipping is temprefed and marked scratch. It is persisted only through a non-scratch claim, as the next paragraph describes (`contracts/scratch-witness-audit.md`, *Where a fingertip chain runs, and what it leaves behind*; the two cases are summarized in `contracts/identity-and-caching.md`).

### Buffer persistence: a non-scratch claim is the only publisher

This is the mechanism behind the rule that neither evaluation nor fingertipping writes a result buffer to the hashserver. This page owns it.

- **A non-scratch claim publishes, in either order.**
  - *Claim after buffer:* a non-scratch `incref` / `incref_refholder` on a checksum whose buffer is in the local cache discards the checksum from the scratch set and queues the buffer for the remote store. One act overturns scratch status and is the write.
  - *Buffer after claim:* a non-scratch claim acquired while no buffer is here marks the entry remote-registered and writes nothing. When the buffer arrives later, `BufferCache.register` writes it, because it arrives under an existing non-scratch claim. A buffer that arrives under a scratch claim only is not written.
  - So **`Cell.fingertip()` persists the recovered buffer only on a non-scratch Cell**: a non-scratch Cell holds its result under a non-scratch claim, and a scratch Cell under a scratch one.
  - Both orders are tested (`seamless-core/tests/test_contract_reference_lifecycle.py`, `seamless-core/tests/test_contract_reference_lifecycle_late_buffer.py`). The one caveat is a `purge_scratch()` that lands between a local evaluation and a later non-scratch claim.
- **Only an owner with a scratch policy publishes.** A Cell, a Transformation and a Context node have one. An `Expression`, a handle and the waiting set do not, which is why their claims are neutral (§6). Reading `Expression.checksum` therefore cannot write a buffer, and a scratch decision cannot be defeated through a property read. (One case looks like an exception and is not: a bare `Expression` asked for a **value** across a dispatch; see the transfer-write bullet below.)
- Therefore **persistence is a property of who holds, never of who computed.** An evaluator that writes its result buffer is asserting an interest it does not have. A fingertip site in particular holds a bare checksum, with **no owner and no scratch intent**, so it cannot decide.
- **Interest travels with a dispatch.** When work runs elsewhere, the buffer may never reach this process (a jobserver returns a checksum only), so a claim acquired here afterwards has nothing to write. That is why `scratch` is a request parameter and the executing side publishes on the requester's behalf, rather than the client applying interest afterwards.
- **A transfer write is not an ownership claim.** When the requester is a bare `Expression` asking for a *value*, the dispatch carries `scratch=False` although nobody will hold the result, because the hashserver is the only channel by which the bytes can reach the requester (`contracts/expressions.md`, *The requester's scratch decision, and what a bare Expression carries*). For Expressions the executing side writes the end result explicitly (`buffer_remote.write_buffer`); on the transformation path it calls `transfer_write()` next to a tempref. Either way no durable claim is created, and with nothing holding it, the entry is as evictable as any other unheld buffer. Asking for a *checksum* carries `scratch=True` and writes nothing at all.

A tempref never writes (`BufferCache.tempref` has no scratch parameter), so Expression evaluation queues no hashserver write on any terminal branch, and a buffer it produces is marked scratch (`contracts/expressions.md`, *Status: publication and fingertipping*).

### The definition write

`Transformation._publish_definition` writes the transformation definition with `transfer_write()` and then claims it under `"definition"` with a non-scratch claim, **even for a scratch Transformation**. The definition is provenance, not a result: another process can fingertip the scratch result only if it can read the definition. **Whether the scratch ruling of §1 covers this write is deferred.** Until it is ruled, this is the behaviour, and it is recorded neither as a gap nor as settled contract.

### Deep checksums

Only the **top-level** checksum of a `deepcell`, `deepfolder` or `folder` is owned. Members rely on ordinary deep-buffer resolution and remote durability; there is no recursive deep ownership. This covers the **result** side as well as the input side: a Transformation that produces a deep result claims the index checksum under its `"result"` role and makes **no claim on the leaves** (`contracts/deep-celltypes.md`, *The output side*). The one permanent exception is on the mount sense path: leaves that a mount *sensed* keep a claim for as long as the node holds that index, including after unmounting (`contracts/attachments.md`, *Leaf retention*).

### Workers and services

**Execution workers** use no-op registry and refholder wrappers and run no lifecycle audit. Parent-side objects keep ownership across IPC.

**Remote, database and jobserver services** publish or retrieve buffers but have no distributed reference-count protocol. Remote-registration status is not a semantic claim. The database's stored path rows are the one durable claim (§6).

**Shared-memory PID accounting and durable remote storage** are outside this count.

## 9. Runtime correctness versus shutdown verification

**Runtime correctness is continuous**: ownership stays balanced, and buffers stay resolvable while a semantic owner can still use them. Forced expiry proves this independently of ordinary cache luck. A positive forced-expiry test is meaningless without a negative control.

**Shutdown verification is observational, then corrective.** Forced cleanup must never retroactively turn a warning-producing run into a passing one. A balanced explicit close and a balanced `atexit` emit no `seamless.references` warnings.

### The shutdown audit

The audit runs inside `seamless.close()`, after new work is prohibited and before buffer-cache teardown; `atexit` uses the same audit. The sequence:

1. cancel or settle running local and remote work;
2. snapshot the weak registry and build a reverse index `checksum -> [(holder, role), ...]`, one entry per live claim;
3. snapshot each checksum's `refholder_count`, `manual_refs` and `has_refholder_bridge`;
4. compare `len(reverse_index[c])` with `refholder_count[c]`. A mismatch warns and lists every live holder of the checksum: an excess count is unattributed (a holder may have died without decrementing), and an excess of claims means a missing acquisition or an over-decrement;
5. verify `has_refholder_bridge == (refholder_count > 0)`, and warn for every positive `manual_refs`;
6. flush required buffers while references still retain them;
7. invoke cleanup hooks and every live registered refholder's idempotent cleanup;
8. run `gc.collect()` twice;
9. re-inspect: counts must be zero, bridges false, manual refs zero;
10. force-clear residual counts after the warnings, so that shutdown finishes deterministically.

Pre-cleanup warnings are **not** erased by a successful forced cleanup.

### Warning format

Warnings go to a dedicated logger, `seamless.references`. Balanced shutdown emits nothing. Warnings are deterministic and concise. Each holder line is `  <class name> 0x<id> <role>`. The shapes are:

```text
Checksum <hex> has refholder count 3 but only 2 live claims; 1 is unattributed
  Transformation 0x... input:x
  Context 0x... node:tf:current

Checksum <hex> has refholder count 1 but 2 live claims
  Cell 0x... input
  Context 0x... cell:a:literal
  A reference was not acquired or was released by code that did not own it

Checksum <hex> has refholder count 1 but its eviction bridge is absent

Checksum <hex> has 2 unmatched manual references at shutdown

Manual decref ignored for checksum <hex>: manual refcount is already zero
```

There is no creation traceback, no dead-holder tombstone and no stored event history.

## 10. Implementation status

Settled contract that the code does not yet implement, or implements differently. The rules above are the test oracle; each gap below is pinned by an `xfail(strict=False)` test whose reason reads "contract ahead of code". Where the code disagrees with a rule above, the rule above wins.

**Gaps (xfail-pinned):**

- **A superseded hold on a scratch node publishes.** `node:<path>:superseded:<generation>` is acquired with `incref_refholder()`, i.e. `scratch=False`, which writes the speculative result and clears its scratch status (`seamless-workflow/tests/test_contract_reference_lifecycle_scratch.py`).
- **A subcontext copy publishes a scratch node's result.** `Context._copy_subcontext` acquires the copied node's current claim with `scratch=False` (`context.py:1704`; same test file).
- **A scratch cell's literal claim publishes.** `_retain_producer` uses `incref_refholder()`, i.e. `scratch=False` (same test file).
- **A scratch transformer's pin and code claims publish.** They are acquired with `scratch=False` whatever the transformer's scratch (same test file). The module claims are acquired the same way (`context.py:637`) and fall under the same ruling, but no test pins them yet.
- **The waiting set's claim is not neutral.** `hold_input` (`seamless/checksum/expression.py`) claims with `scratch=True`, so an input that a non-scratch holder owns and has published is marked scratch (`seamless-remote/tests/test_contract_reference_lifecycle_linger.py`).
- **A superseded claim on a cell node never ends at the hold deadline.** `Context._update_runtime` calls `ContextRuntime.supersede()`, which records a `hold_deadline` but never schedules the expiry timer — only the transformer path (`Reactive._suspend`) does. A superseded cell claim therefore ends only at the cap, on `prune()`, on node deletion or on cleanup, never at the deadline on its own. Whether the deadline rule is meant to cover cell nodes at all is unconfirmed (`seamless-workflow/tests/test_reference_lifecycle_forced_expiry.py`; the transformer case is tested and passes).
- **Copying a converted projection raises instead of copying.** `copy.copy`/`copy.deepcopy` of a Cell built through a projection-plus-conversion (e.g. `root["x"].as_celltype("text")`) raises `TypeError("Cannot implicitly convert behind a projection")` from `Cell.__copy__` rebuilding the Cell through its constructor, instead of giving an independent claim as §5 says copying should (`seamless-core/tests/test_contract_reference_lifecycle.py`). This narrows the "copy defect fixed" item under *Fixed* below: the fix covers a plain Cell or Expression, not this projection-conversion combination.
- **The anonymous-node roles have narrow pins, not none.** `anonymous:<symbol>:current` and the handles' `"result"` claim belong to the bound anonymous-node model, which is not implemented (`contracts/cells.md`, *Implementation status*), so the Context-side role can only be pinned failing at binding (`TypeError`). But a plain bound projection handle (e.g. `ctx.b["k"]`) already exhibits the handle-side half of the gap today — it pulls the right checksum while holding no claim at all — and that narrower case is xfail-pinned (`seamless-workflow/tests/test_contract_reference_lifecycle_anonymous.py`).

**Deferred (not gaps):**

- A scratch `Transformation` claims its inputs with `scratch=self._scratch` (`transformation_class.py`), so it marks as scratch an input that a non-scratch holder owns. Whether that is correct is not ruled.
- Whether the scratch ruling covers `_publish_definition` (§8, *The definition write*).

**Fixed.** These were code-versus-contract findings of the 2026-09-24 coverage pass, and the code now follows the page:
- an `Expression`'s inputs are tempref-only, with no refholder claim (§6, §7);
- the `Expression` `"result"` claim is neutral (§6);
- `copy.copy` and `copy.deepcopy` of a plain Cell or an Expression acquire an independent claim (§5) — except a Cell built through a projection-plus-conversion, which is a newly-found gap, listed above under *Gaps*.

Two earlier defects in the workflow `Context` were fixed before the verification handoff: checksum-backed **module replacement** now stages the new role before releasing the old one, and **failed bound-Transformer replacement** now restores semantic and runtime state and exact ownership.

The waiting set's linger claim (§6) exists and is tested: the claim holds through the linger and is released when the linger expires.

The database's path storage (§6, *The durable refholder*) currently keeps every path inline, so no indirect row, and therefore no durable claim, arises yet.

**Verification is incomplete.** Six verification packages remain:

1. core forced expiry and cache accounting;
2. transformer and workflow forced expiry;
3. the shutdown/`atexit` subprocess matrix;
4. Dask publishing paths;
5. the partially coupled `PreTransformation` and `CodeManager` role invariants;
6. a call-site audit plus full regression.

Until they land, green tests are not completion evidence. The forced-cap helper leaves remote resolution and recomputation controls to callers; the named forced-cap coverage proves only a Cell case; shutdown coverage does not prove the full `atexit` / cleanup-exception / corrupted-bridge matrix; helper-dispatch Dask tests do not exercise the real cached, thin and fat branches; partial happy paths do not prove every role multiplicity; and a delayed-dependency test that expires data only after all dependencies finish does not prove per-result adoption before the next wait. Also uncovered: the superseded role ending at the hold **deadline** (only the cap and `prune()` are tested). The 2026-09-24 coverage pass reported the counts, audit, registry, shutdown and Dask publishing paths as covered, but did not re-audit this list package by package.

**One open imbalance.** A refholder-balance warning at `seamless.close()` was observed on a Cell derivation path with shared input checksums, the path the now-retired `SubCell` class used to take. It was never diagnosed, and it looked like a real imbalance rather than an audit artefact. The copy defect fixed above was a suspected cause; whether the warning survives that fix has not been re-checked.

Tests run **one process per file**: process-global cache and refholder state carries between files, and combining Seamless test files in one pytest run produces spurious failures.

## 11. Non-goals

- A public attribution or report model, a holder-token hierarchy, recursive deep ownership, or a cross-process reference protocol. (The database's durable path claim of §6 is a storage property, not such a protocol.)
- Automatic retry, eviction policy, or memory-pressure strategy. This contract says only that referenced data is never deleted to satisfy a limit.
- Making temprefs auditable. A tempref is deliberately unattributed and deliberately bounded to a same-path handoff.
- Replacing the node state lifecycle or the cancellation waiting set, which are different mechanisms with different vocabularies.
