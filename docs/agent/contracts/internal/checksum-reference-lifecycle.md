# Checksum reference lifecycle (internal contract)

**A buffer survives because a live object makes a semantic claim on its checksum.** The claim is registered, attributable, acquired once per role and released once per role, and it is audited at shutdown. Nothing else keeps data from being demoted: not a `Checksum` object, not a tempref, not a remote registration.

This mechanism is **internal**. It is deliberately not one of the main pages of `seamless/docs/agent/contracts/` — it lives one level down, in `contracts/internal/`, apart from the user-visible contract pages — because it is not user-visible behaviour: the only trace a user ever sees is a `seamless.references` warning at shutdown. It nevertheless needs a precise written contract, and this repository is where that contract lives.

> **Do not confuse this with the workflow node state lifecycle.** That is the `Context`'s seven-state node machine, its cascade and its speculative supersession — user-visible behaviour, documented in the agentic contracts. This document is about who keeps a checksum's buffer alive.

It is also not the **cancellation waiting set**, the per-checksum set of requesters of an in-flight materialization: different thing, different lifetime — a reference keeps a buffer alive once it exists, the waiting set tracks who still wants a fetch that has not finished. The vocabulary is kept apart on purpose; the waiting set is a "waiting set", never a "refcount".

Code locations:

| Concern | Repository and modules |
|---|---|
| Accounting, the weak registry, the audit, explicit and `atexit` shutdown | `seamless-core`: `seamless/caching/buffer_cache.py`, `seamless/reference_lifecycle.py`, `seamless/shutdown.py` |
| Cell and Expression ownership, the forced-expiry test helper | `seamless-core`: `seamless/cell_class.py`, `seamless/expression_class.py` |
| Builder roles, temporary transfer, dependency adoption, definition and result roles, cancellation | `seamless-transformer`: `transformer_class.py`, `pretransformation.py`, `transformation_class.py`, `code_manager.py`, and the worker/publication paths |
| Context producer, current and superseded ownership; binding, replacement, deletion, graph lifecycle | `seamless-workflow`: `context.py`, `graph.py`, `scheduler.py`, `builder_state.py`, `adapters.py` |
| Cached, thin and fat result publication, scratch, failure, cancellation | `seamless-dask`: `transformation_mixin.py`, `client.py` |

## 1. Terminology

The present tense is normative.

**Checksum** — a content address. A bare `Checksum` object owns no lifecycle reference merely by existing.

**Concrete checksum** — a checksum known now, after the receiving API has applied its normalization rules. A result that has not been computed is non-concrete. Concreteness does not imply that the buffer is locally available.

**Refholder / semantic claim** — a registered live object implementing `_refheld_checksums()` and `_release_refholds()`. Each `(checksum, role)` item yielded by `_refheld_checksums()` is **one semantic claim**; duplicate checksums held for distinct roles or multiplicities are yielded repeatedly.

**Refholder reference** — one unit in `BufferCache.refholder_counts[checksum]`, acquired through `incref_refholder()` and released through `decref_refholder()`. It never changes `manual_refs`.

**Manual reference** — one unit in `StrongEntry.manual_refs`, acquired through the public low-level lease API `Checksum.incref()` / `Buffer.incref()`. **Lifecycle owners must use refholder references, never manual ones.**

**Refholder bridge** — `StrongEntry.has_refholder_bridge`, true exactly when the logical refholder count is positive. It protects the strong entry from demotion; it is neither a manual reference nor a holder object.

**Tempref** — refreshable, decaying, unattributed cache interest for a bounded same-path handoff. It is **not** balanced by the lifecycle audit and is **insufficient across an unbounded yield, wait or queue**. A tempref **never writes** a buffer to the hashserver and is **neutral about scratch status**: it neither marks a checksum scratch nor clears that mark.

**Scratch status** — membership of the buffer cache's scratch set. It records an owner's or producer's *decision*, never the mere absence of a durable claim. It is set by a scratch `incref` / `incref_refholder` or by `mark_scratch()` (a scratch Transformation's result, a buffer an Expression evaluation produced, a fingertipped buffer), and cleared by a non-scratch `incref` / `incref_refholder` or a `transfer_write()`. `PreTransformation` reads it to decide whether an input gets a refholder claim or only a tempref.

**Transfer write** — `transfer_write()`: an explicit write of a buffer to the hashserver made on a requester's behalf, without any claim (§8).

**Neutral claim** — `incref_refholder(scratch=None)`: a refholder reference that protects a buffer from eviction and neither publishes nor changes scratch status. It is for claims that are not an owner's decision: a Context's snapshot and in-flight leases. An owner's claim is `scratch=False` (publishes, clears scratch status) or `scratch=True` (marks scratch); a Context node's claim on its current result follows the node's policy (`Cell.scratch`, or the transformer's `scratch`).

**Recording** — recording a successful Expression or Transformation result **checksum** and making it visible. Local execution, cache, database, remote, jobserver, worker and Dask success paths all record. Every success temprefs before recording; repeated deterministic recording is idempotent for result ownership. **Failure and cancellation record nothing.**

**Publishing** — writing the result **buffer** to the hashserver. It happens on a **non-scratch incref** and nowhere else (§8, *Buffer persistence*).

> **One ruled vocabulary, across every page (2026-09-21).** *Publishing* is the buffer write; *recording* is what happens to a result checksum. This page previously used "publication" for the second act; it no longer does, and the pages that already used "publishing" for the buffer write (`contracts/scratch-witness-audit.md`, `contracts/expressions.md`, `contracts/identity-and-caching.md`) are the ones in agreement. The two acts have different rules: recording always happens on success, writing the buffer only when somebody increfs it non-scratch. The code's former `_publish_expression_result` was named for neither act; it is now **`_tempref_expression_result`** and registers a tempref (marking a buffer the evaluation produced as scratch).

**Adoption / handoff** — a consumer validates a concrete checksum, acquires its own semantic role, records that role, and only then yields or waits. Adoption is independent ownership: it does not transfer the producer's reference. An Expression consumer instead refreshes a tempref and consumes on the same path.

**Public result interest** — an explicit user request to compute, schedule or read an Expression/Transformation result. It enables that producer's optional `"result"` role. Framework bookkeeping and dependency access are **internal interest** and stay producer-neutral.

**Demotion, eviction, forced expiry** — demotion removes a strong-cache entry while a still-live Buffer may remain weakly reachable; eviction is pressure-selected demotion under the same predicate; **forced expiry is a test procedure** that removes every non-role survival path and invokes eviction — it is not a production operation.

**Balanced** — for every checksum before shutdown cleanup, the logical count equals the number of live semantic claims and the bridge equals `(count > 0)`. After holder cleanup and forced accounting cleanup, counts, bridges and manual references are zero; only a live-tempref entry with snapshot `(0, 0, False)` may remain.

## 2. Three kinds of cache interest, one demotion predicate

`StrongEntry` carries `buffer`, `size`, `manual_refs`, `has_refholder_bridge`, `tempref`. The logical refholder multiplicity lives **outside** the entry, as `refholder_count[checksum]`: the entry holds one boolean where the count holds an integer, and the integer is the thing that is audited.

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
| `1 → 0` | clears the bridge and demotes the entry **only if** neither manual refs nor a live tempref remain |

Zero-crossings and bridge updates are atomic under the lifecycle/cache lock.

**The absolute demotion predicate:**

```text
manual_refs == 0
and has_refholder_bridge is False
and no live tempref exists
```

Any nonzero refholder count therefore gives exactly the required eviction protection — no more, and no less. Temprefs expire normally. If a memory limit cannot be met because every remaining buffer is referenced, Seamless **reports memory pressure** rather than deleting referenced data or its accounting.

## 3. The two APIs

|  | Public, manual | Internal, lifecycle |
|---|---|---|
| Spellings | `checksum.incref()` / `checksum.decref()`, `buffer.incref()` / `buffer.decref()` | `checksum.incref_refholder()` / `checksum.decref_refholder()`, and the `Buffer` equivalents |
| Backing call | — | `BufferCache.incref_refholder(checksum, buffer=None, scratch=False)` / `decref_refholder()` |
| Modifies | `manual_refs` only | `refholder_count`, and the bridge on zero crossings only |
| Called at zero | does nothing, warns through the logger | does nothing, warns |
| Receives the holder object | n/a | **no** — attribution is reconstructed from the registry when needed |
| Who uses it | users, low-level leases | lifecycle owners only |

The manual API can never consume the refholder bridge, and the lifecycle API stores **no event history**.

**Snapshot (internal/test):** `BufferCache.reference_snapshot() -> dict[Checksum, tuple[refholder_count, manual_refs, has_refholder_bridge]]`.

## 4. The weak refholder registry and the audit protocol

The registry is a process-global, **identity-keyed weak** collection of every live refholding object — a `WeakSet` suffices, and slotted classes must support weak references. It is populated by `register_refholder()`.

- An object registers when it becomes capable of holding its first reference. It may stay registered after its held list empties; that is harmless. Destruction removes it automatically.
- No holder key is needed: `id(obj)` suffices for formatting while the object is alive, and nothing about dead holders is preserved.
- Each refholding class implements:

```python
def _refheld_checksums(self) -> Iterable[tuple[Checksum, str]]:
    """Yield one item per currently held reference; the string names the owning field or pin."""
```

`_refheld_checksums()` is **side-effect free** and derives ownership from the object's real state — there is no generic acquisition mirror and no generic `_checksum_refs` counter. `_release_refholds()` is **idempotent**.

Because the registry is weak, a holder that dies without decrementing cannot be named. Its effect is still detected, as an excess `refholder_count` that no live holder explains, and other live holders of the same checksum are still listed.

## 5. Governing invariants

For every checksum `c` during normal runtime:

```text
refholder_count[c] == number of live semantic claims for c
has_refholder_bridge[c] == (refholder_count[c] > 0)
```

And:

- each owner acquires once per semantic role and releases once per semantic role;
- **replacement is: acquire the new roles, install the new state, then release the old roles** — including when the replacing checksum is equal to the replaced one;
- a producer `"result"` role represents **public** interest only; framework dependency access stays neutral;
- a Transformation **adopts each dependency before waiting for another dependency**;
- **a bound Cell or Transformer handle owns no references**; the Context owns the bound state;
- finalizers are idempotent backstops, not the primary correctness mechanism;
- audit claims come from semantic fields or demand maps, not from a generic acquisition mirror.

The general rules that follow:

- every object that promises later use of a checksum calls `incref_refholder()`, and calls `decref_refholder()` on replacement, deletion, explicit destruction or normal object destruction;
- cleanup is idempotent;
- copying a refholding object creates an **independent** reference;
- serialization stores checksums and owns no local references; deserialization into a live object acquires new ones;
- a bare `Checksum` is not a refholder;
- two objects holding one checksum contribute **two** to the count while setting **one** boolean bridge; one object holding it through two independent fields contributes two and yields it twice.

## 6. Ownership by object type

This table is the normative ownership and ordering contract.

| Owner | Exact semantic roles | Acquisition and release boundary |
|---|---|---|
| Standalone `Cell` | `"input"` for an explicit checksum input | Acquire on construction/replacement; the Context adopts before binding releases it. Bound handles own nothing. |
| `Expression` | `"result"` only after public result interest, and the claim is **scratch-neutral** | Inputs are tempref-only. Internal evaluation records neutrally; the first public call/read acquires an already-recorded result once. The claim protects the result from eviction and does **not** publish it: it neither queues the buffer for the remote store nor discards the checksum from the scratch set. Cleanup releases only an acquired result. |
| Standalone `Transformer` builder | `"pin:<name>"`, `"code"`, `"module:<name>"` for checksum-backed fields | Wrapper mutation and cloning acquire independently. The Context adopts all roles before the builder becomes a neutral bound handle. |
| `PreTransformation` | `"input:<pin>"` for converted non-scratch pins | Scratch pins are tempref-only and absent from `_value_refs`. The Transformation acquires every input before PreTransformation releases. CodeManager roles stay separate. |
| `Transformation` | `"input:<pin>"` for direct and adopted dependency inputs; `"definition"`; optional public `"result"` | The definition is retained through completion. Each dependency is adopted immediately. A public entry/read enables result holding; internal access stays neutral. Terminal cancellation settles or detaches work, blocks late recording, then releases roles while the fields stay intact. Cancellation after completed recording is a no-op. |
| `CodeManager` | `"syntactic:direct"`, `"syntactic:guard"`, `"semantic:direct"`, `"semantic:guard"` | Each direct or guard multiplicity acquires and releases once. Guard creation and removal follow the demand maps; `_release_refholds()` drains exact multiplicities idempotently. |
| Workflow `Context` | `"cell:<path>:literal"`; `"transformer:<path>:pin:<pin>"`; `"transformer:<path>:code"`; `"transformer:<path>:module:<name>"`; `"node:<path>:current"`; `"node:<path>:superseded:<generation>"` | The Context acquires before installing graph/runtime state and releases the old state afterwards. Current and producer roles are independent even for equal checksums. Superseded roles end on cap, deadline, prune, deletion, graph replacement or cleanup. Bound views own nothing. |

**Public versus internal interest is a hard rule.** All public Expression/Transformation APIs that request, return or schedule a result express public interest. Dependency helpers, `PreTransformation`, workflow schedulers, backend result-recording code and internal CLI orchestration use named *internal* evaluation/result accessors. **No framework path may create a producer result role merely to inspect a dependency.**

**The Context's `current` / `superseded:<generation>` roles are what makes a speculative grace hold real.** A superseded run's result stays resolvable for as long as the Context holds its role, and the role ends on the cap, the deadline, `prune()`, node deletion, graph replacement or cleanup. The policy that decides *when* to hold is the node state lifecycle's, documented elsewhere; this document owns only the claim.

## 7. Dependency handoff

Handoff must happen **before the producer's tempref may expire**.

| Consumer | What it does with a concrete producer result | What it owns |
|---|---|---|
| Dependent Transformation | calls `incref_refholder()` for the input **immediately**, and only then may it wait for other inputs | its own `"input:<pin>"` role; the producer needs no result reference on its behalf |
| Dependent Expression | makes or refreshes a tempref on the input checksum and evaluates immediately; it does **not** increment the refholder count | nothing; its own result receives a fresh or refreshed tempref |

## 8. Scratch, deep checksums, workers, services

**Scratch.** Scratch acquisition does not register a buffer remotely, and later non-scratch interest upgrades registration monotonically. A **fingertip chain always runs locally and never publishes, at any site** (client, jobserver or Dask worker alike), and there is no exception: neither an input fingertip inside a job nor a manual fingertip writes to the hashserver, not even the chain's end result. A buffer recovered by fingertipping is temprefed and marked scratch; it is persisted only if a non-scratch owner increfs it afterwards (`contracts/scratch-witness-audit.md`, *Where a fingertip chain runs, and what it leaves behind*; the two cases are summarized in `contracts/identity-and-caching.md`). **Explicit public interest in a scratch result refholds and protects it**; an unrequested scratch result stays purgeable. See `contracts/scratch-witness-audit.md` for what scratch means.

**Buffer persistence: a non-scratch incref is the only publisher.** This is the load-bearing mechanism behind the rule that neither evaluation nor fingertipping writes a buffer to the hashserver, and it is stated here because this page owns it:

- A **non-scratch** `incref` / `incref_refholder` both **discards the checksum from the scratch set** and **queues its buffer for the remote store**. So one act does two things: it overturns any scratch status, and it is the write.
- **Only an owner with a scratch policy publishes.** A Cell, a Transformation and a Context node have one; an `Expression` does not, which is why its `"result"` role is scratch-neutral (§6). Reading `Expression.checksum` therefore cannot write a buffer, and a scratch decision cannot be defeated through a property read. (One case *looks* like an exception and is not — a bare `Expression` asked for a **value** across a dispatch; see the transfer-write bullet below.)
- Therefore **persistence is a property of who holds, never of who computed.** An evaluator that writes its result buffer is asserting an interest it does not have; a fingertip site in particular holds a bare checksum, with **no owner and no scratch intent**, so it cannot decide.
- **No promotion machinery is needed** *for that ordering*. After a local evaluation the buffer is already in the local cache, so a later non-scratch incref finds the cached buffer and writes it then. The one caveat is a `purge_scratch()` landing in between. The **reverse** ordering — a non-scratch claim acquired while no buffer exists, and a buffer arriving afterwards, as when a Cell fingertips a result it already holds — is not covered by that argument, and the mechanism for it is not settled; see `cells-and-expressions-feature-1-4.md`.
- **The converse limits what a late incref can repair.** A non-scratch incref on a checksum whose buffer is *not* in this process marks the entry remote-registered and writes nothing — there is no buffer here to write. This is why interest must travel **with** a dispatch (`scratch` as a request parameter, the executing side publishing on the requester's behalf) rather than being applied by the client afterwards.
- **A transfer write is not an ownership claim, and it is the one case that looks like an exception.** When the requester is a bare `Expression` asking for a *value*, the dispatch carries `scratch=False` although nobody will hold the result: the hashserver is the only channel by which the bytes can reach the requester (`contracts/expressions.md`, *The requester's scratch decision, and what a bare Expression carries*). For Expressions the executing side writes the end result explicitly (`buffer_remote.write_buffer`); on the transformation path it calls `transfer_write()` next to a tempref. Either way no durable claim is created: with nothing increfing it, the entry is as evictable as any other unheld buffer. Asking for a *checksum* carries `scratch=True` and writes nothing at all.

*Implemented:* a tempref never writes (`BufferCache.tempref` has no scratch parameter), so Expression evaluation queues no hashserver write on any terminal branch, and a buffer it produces is marked scratch (`contracts/expressions.md`, *Status: publication and fingertipping*).

**Deep checksums.** Only the **top-level** checksum of a `deepcell` / `deepfolder` / `folder` is owned. Members rely on ordinary deep-buffer resolution and remote durability; there is no recursive deep ownership. This covers the **result** side as well as the input side: a Transformation that produces a deep result claims the index checksum under its `"result"` role and **no claim on the leaves** (`contracts/deep-celltypes.md`, *The output side*). The one permanent exception is on the mount sense path: leaves that a mount *sensed* keep a claim for as long as the node holds that index, including after unmounting (`contracts/attachments.md`, *Leaf retention*).

**Execution workers.** Workers use no-op registry/refholder wrappers and run no lifecycle audit. Parent-side objects retain ownership across IPC.

**Remote, database and jobserver services.** They publish or retrieve buffers but gain no distributed reference-count protocol. Remote-registration status is not a semantic claim.

**Shared-memory PID accounting and durable remote storage** are outside this count.

## 9. Runtime correctness versus shutdown verification

**Runtime correctness is continuous**: ownership stays balanced and buffers stay resolvable while a semantic owner can still use them. This is provable independently of ordinary cache luck by *forced expiry* — the test procedure that removes every non-role survival path and then evicts. A positive forced-expiry test is meaningless without a negative control.

**Shutdown verification is observational, then corrective.** Forced cleanup must never retroactively turn a warning-producing run into a passing one. A balanced explicit close and a balanced atexit emit no `seamless.references` warnings.

### The shutdown audit

The audit is integrated into `seamless.close()` after new work is prohibited and before buffer-cache teardown; `atexit` uses the same audit. The sequence:

1. cancel or settle running local and remote work;
2. snapshot the weak registry and build a reverse index `checksum -> [(holder, description), ...]`, one entry per held reference;
3. snapshot each checksum's `refholder_count`, `manual_refs` and `has_refholder_bridge`;
4. compare `len(reverse_index[c]) == refholder_count[c]`; a mismatch warns — an excess integer is unattributed (a holder may have died without decrementing), a larger reverse index means missing refs or over-decrement. List every still-live holder for the checksum;
5. verify `has_refholder_bridge == (refholder_count > 0)`, and warn for every positive `manual_refs`;
6. flush required buffers while references still retain them;
7. invoke cleanup hooks and every live registered refholder's idempotent cleanup;
8. run `gc.collect()` twice;
9. re-inspect: counts must be zero, bridges false, manual refs zero;
10. force-clear residual counts after the warnings, so that shutdown finishes deterministically.

Pre-cleanup warnings are **not** erased by a successful forced cleanup.

### Warning format

Warnings go to a dedicated logger, `seamless.references`. Balanced shutdown emits nothing. Warnings are deterministic and concise:

```text
Checksum <hex> has refholder count 3, but 2 live holders were found
  Transformation 0x... input:x
  Context 0x... transformer:tf:result
  1 reference is unattributed; its holder may have died without decref

Checksum <hex> has 2 unmatched manual references at shutdown

Checksum <hex> has refholder count 1 but its eviction bridge is absent

Manual decref ignored for checksum <hex>: manual refcount is already zero
```

No creation traceback, no dead-holder tombstone, no stored event history.

## 10. Implementation status

The core architecture and the production migrations exist. Two defects were fixed immediately before the verification handoff, both in the workflow `Context`:

- checksum-backed **module replacement** now stages the new role before releasing the old one;
- **failed bound-Transformer replacement** now restores semantic and runtime state, and exact ownership.

**Verification is incomplete.** Six verification packages remain:

1. core forced expiry and cache accounting;
2. transformer and workflow forced expiry;
3. the shutdown/atexit subprocess matrix;
4. Dask publication paths;
5. the partially coupled `PreTransformation` and `CodeManager` role invariants;
6. a call-site audit plus full regression.

**Until those land, existing green tests are not completion evidence.** The forced-cap helper leaves remote resolution and recomputation controls to callers; the named forced-cap coverage proves only a Cell case; existing shutdown coverage does not prove the full atexit / cleanup-exception / corrupted-bridge matrix; helper-dispatch Dask tests do not exercise the real cached/thin/fat branches; partial happy paths do not prove every role multiplicity; and a delayed-dependency test that expires data only after all dependencies finish does not prove per-result adoption before the next wait.

**One open imbalance**: a refholder-balance warning at `seamless.close()` on a `Cell` / `SubCell` derivation path with shared input checksums. Observed, not yet diagnosed; it looks like a real imbalance rather than an audit artefact.

**Design intent, not yet built: where the cancellation waiting set will meet this lifecycle.** The materialization-layer linger before a softcancel's abort (`contracts/cancellation.md`, *Materialization is the same pattern, one layer down*) does not exist in code yet. Once it does, the waiting-set site itself is expected to hold a lifecycle claim on the checksum for the duration of the linger and release it when the abort fires — an unreleased claim there is exactly what the shutdown audit above should catch. This is recorded from a 2026-09-17 design discussion, not yet verified against code.

Tests are run **one process per file**: process-global cache and refholder state carries between files, and combining Seamless test files in one pytest run produces spurious failures.

## 11. Non-goals

- A public attribution or report model, a holder-token hierarchy, recursive deep ownership, or a cross-process reference protocol.
- Automatic retry, eviction policy, or memory-pressure strategy. This contract says only that referenced data is never deleted to satisfy a limit.
- Making temprefs auditable. A tempref is deliberately unattributed and deliberately bounded to a same-path handoff.
- Replacing the node state lifecycle or the cancellation waiting set, which are different mechanisms with different vocabularies.
