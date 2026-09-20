# Checksum Reference Lifecycle — Self-Contained Verification Completion Handoff

## 1. Purpose and current status

This document is the complete implementation handoff for closing the remaining checksum-reference
lifecycle verification gaps. It is intentionally test-focused. This file is independently
normative: an implementer must not need the original lifecycle or finalization handoffs to execute
it. Those documents are historical evidence only. Do not redesign the implemented reference
lifecycle or repeat completed production migrations unless a required negative control exposes a
new runtime defect.

At the start of this handoff:

- the two runtime defects found during finalization review are fixed by `seamless-workflow`
  commit `2eb593b` (`Transformer replacement now stages all roles and restores graph, runtime,
  edges, and ownership tables on failure.`);
- checksum-backed workflow module replacement now acquires the new role before publishing it and
  releases the old role afterward;
- failed Transformer replacement restores graph/config/runtime state and exact Context ownership,
  while leaving the replacement builder standalone;
- `tests/test_reference_lifecycle_binding.py` contains three focused regressions covering module
  replacement, failed replacement rollback, and successful replacement transfer;
- all 12 `seamless-workflow` test files pass individually in the `seamless1` environment
  (64 tests total, including the three focused regressions for these fixes);
- the `seamless-workflow` worktree is clean at this handoff baseline.

The remaining work is six verification packages:

1. core forced-expiry and cache-accounting evidence;
2. Transformer and workflow forced-expiry evidence with negative controls;
3. shutdown and atexit subprocess coverage;
4. real Dask publication/scratch/cancellation path coverage;
5. complete PreTransformation and CodeManager role-combination coverage;
6. final call-site audit, serial regression, backend coverage, and implementation report.

Completion means producing reproducible evidence for the existing contract, not merely adding
tests that happen to pass on the current implementation.

## 2. Handoff-ready criteria

This handoff is ready for an independent implementer only because it satisfies all of these
criteria:

1. It defines every load-bearing lifecycle term and invariant.
2. It distinguishes runtime correctness from shutdown verification.
3. It names the affected repositories, current modules, and misleading current behavior.
4. It gives exact ownership rules for every refholder class in scope.
5. It defines the cache fields and internal APIs precisely enough to implement directly.
6. It defines acquire, replacement, publication, handoff, cancellation, and cleanup ordering.
7. It resolves the choices identified by the language review rather than leaving them to the
   implementer.
8. It defines worker-process, scratch, remote-registration, and deep-checksum boundaries.
9. It supplies an ordered sequence in which every verification package ends in a testable working
   state.
10. It identifies current tests that encode superseded behavior and says how to rewrite them.
11. It supplies focused and full-suite commands for the `seamless1` conda environment.
12. It defines observable completion evidence, not merely desired test or production structure.

Section 17 maps each criterion to its normative sections. A future edit that breaks that map makes
this document no longer handoff-ready.

## 3. Runtime contract and terminology

The present tense is normative. "X refholds Y" means X owns exactly one logical reference for the
stated semantic role and must release exactly that reference at the stated lifecycle boundary.

**Checksum**
: A content address. A bare `Checksum` object owns no lifecycle reference merely by existing.

**Concrete checksum**
: A checksum known now, after the receiving API has applied its normalization rules. A result that
  has not been computed is non-concrete. Concreteness does not imply that its Buffer is locally
  available.

**Refholder and semantic claim**
: A registered live object implementing `_refheld_checksums()` and `_release_refholds()`. Each
  `(checksum, role)` item from `_refheld_checksums()` is one semantic claim. Duplicate checksums for
  distinct roles or multiplicities must be yielded repeatedly.

**Refholder reference**
: One unit in `BufferCache.refholder_counts[checksum]`, acquired through
  `incref_refholder()` and released through `decref_refholder()`. It never changes `manual_refs`.

**Manual reference**
: One unit in `StrongEntry.manual_refs`, acquired by the public low-level
  `Checksum.incref()`/`Buffer.incref()` lease API. Lifecycle owners must use refholder references,
  not manual references.

**Refholder bridge**
: `StrongEntry.has_refholder_bridge`. It is true exactly when the logical refholder count is
  positive. It protects the strong entry from demotion but is neither a manual reference nor a
  holder object.

**Tempref**
: Refreshable, decaying, unattributed cache interest for a bounded same-path handoff. It is not
  balanced by the lifecycle audit and is insufficient across an unbounded yield, wait, or queue.

**Publication**
: Recording a successful Expression or Transformation result checksum and making it visible.
  Local execution, cache, database, remote, jobserver, worker, and Dask success paths all publish.
  Every success temprefs before publication; repeated deterministic publication is idempotent for
  result ownership. Failure and cancellation publish nothing.

**Adoption and handoff**
: A consumer validates a concrete checksum, acquires its own semantic role, records that role, and
  only then yields or waits. Adoption is independent ownership; it does not transfer the producer's
  reference. An Expression consumer instead refreshes a tempref and consumes on the same path.

**Public result interest**
: An explicit user request to compute, schedule, or read an Expression/Transformation result. It
  enables that producer's optional `"result"` role. Framework bookkeeping and dependency access
  are internal interest and must remain producer-neutral.

**Demotion, eviction, and forced expiry**
: Demotion removes a strong-cache entry while any still-live Buffer may remain weakly reachable.
  Eviction is pressure-selected demotion and uses the same protection predicate. Forced expiry is
  a test procedure that removes every non-role survival path and invokes eviction; it is not a
  production lifecycle operation.

**Balanced**
: For every checksum before shutdown cleanup, logical count equals the number of live semantic
  claims and the bridge equals `(count > 0)`. After holder cleanup and forced accounting cleanup,
  counts, bridges, and manual references are zero; only a live-tempref entry with snapshot
  `(0, 0, False)` may remain.

### 3.1 Governing invariants

For every checksum `c` during normal runtime:

```text
refholder_count[c] == number of live semantic claims for c
has_refholder_bridge[c] == (refholder_count[c] > 0)
```

The absolute demotion predicate is:

```text
manual_refs == 0
and has_refholder_bridge is False
and no live tempref exists
```

Additional invariants:

- each owner acquires once per semantic role and releases once per semantic role;
- replacement is acquire new roles, publish new state, then release old roles, including equal
  checksum replacement;
- a producer result role represents public interest only; framework dependency access stays
  neutral;
- a Transformation adopts each dependency before waiting for another dependency;
- a bound Cell or Transformer handle owns no references; Context owns the bound state;
- finalizers are idempotent backstops, not the primary correctness mechanism;
- audit claims come from semantic fields or demand maps, not a generic acquisition mirror.

### 3.2 Runtime correctness versus shutdown verification

Runtime correctness is continuous: ownership must remain balanced and buffers must remain
resolvable while a semantic owner can still use them. Forced-expiry positive/negative tests prove
this independently of ordinary cache luck.

Shutdown verification is observational and then corrective. After new work is prohibited and
tracked work settles, the audit compares live claims, counts, bridges, and manual references;
flushes writers; releases holders; runs two GC passes; reports residue; and only then force-clears
accounting. Forced cleanup must not retroactively turn a warning-producing run into a passing one.
Balanced explicit close and atexit emit no `seamless.references` warnings.

## 4. Exact ownership and ordering contract

| Owner | Exact semantic roles | Acquisition and release boundary |
|---|---|---|
| Standalone `Cell` | `"input"` for an explicit checksum input | Acquire on construction/replacement; Context adopts before binding releases it. Bound handles own nothing. |
| `Expression` | `"result"` only after public result interest | Inputs are tempref-only. Internal evaluation publishes neutrally; first public call/read acquires an already-published result once. Cleanup releases only an acquired result. |
| Standalone `Transformer` builder | `"pin:<name>"`, `"code"`, `"module:<name>"` for checksum-backed fields | Wrapper mutation and cloning acquire independently. Context adopts all roles before the builder becomes a neutral bound handle. |
| `PreTransformation` | `"input:<pin>"` for converted non-scratch pins | Scratch pins are tempref-only and absent from `_value_refs`. Transformation acquires every input before PreTransformation releases. CodeManager roles remain separate. |
| `Transformation` | `"input:<pin>"` for direct and adopted dependency inputs; `"definition"`; optional public `"result"` | Definition is retained through completion. Each dependency is adopted immediately. Public entry/read enables result holding; internal access stays neutral. Terminal cancellation settles or detaches work, blocks late publication, then releases roles while fields remain intact. Cancellation after completed publication remains a no-op. |
| `CodeManager` | `"syntactic:direct"`, `"syntactic:guard"`, `"semantic:direct"`, `"semantic:guard"` | Each direct or guard multiplicity acquires and releases once. Guard creation/removal follows demand maps; `_release_refholds()` drains exact multiplicities idempotently. |
| Workflow `Context` | `"cell:<path>:literal"`; `"transformer:<path>:pin:<pin>"`; `"transformer:<path>:code"`; `"transformer:<path>:module:<name>"`; `"node:<path>:current"`; `"node:<path>:superseded:<generation>"` | Context acquires before publishing graph/runtime state and releases old state afterward. Current and producer roles are independent even for equal checksums. Superseded roles end on cap/deadline/prune/deletion/graph replacement/cleanup. Bound views own nothing. |

All public Expression/Transformation APIs that request, return, or schedule a result express public
interest. Dependency helpers, PreTransformation, workflow schedulers, backend publication code,
and internal CLI orchestration must use named internal evaluation/result accessors. No framework
path may create a producer result role merely to inspect a dependency.

## 5. Implemented substrate, repositories, and fixed boundaries

The implementation under verification spans:

| Repository | Primary implementation anchors | Verification responsibility |
|---|---|---|
| `seamless-core` | `seamless/caching/buffer_cache.py`, `seamless/reference_lifecycle.py`, `seamless/shutdown.py`, `seamless/cell_class.py`, `seamless/expression_class.py` | Accounting, registry/audit, Cell/Expression ownership, expiry helper, explicit/atexit shutdown. |
| `seamless-transformer` | `seamless_transformer/transformer_class.py`, `pretransformation.py`, `transformation_class.py`, `code_manager.py`, worker/publication paths | Builder, temporary transfer, dependency adoption, definition/result roles, cancellation, partial-coupling matrices. |
| `seamless-workflow` | `seamless_workflow/context.py`, `graph.py`, `scheduler.py`, `builder_state.py`, `adapters.py` | Context producer/current/superseded ownership, binding, replacement, deletion, graph lifecycle. |
| `seamless-dask` | `seamless_dask/transformation_mixin.py`, `client.py` | Actual cached/thin/fat result and definition publication, scratch, failure, cancellation. |

The cache's internal/test snapshot is:

```python
BufferCache.reference_snapshot() \
    -> dict[Checksum, tuple[refholder_count, manual_refs, has_refholder_bridge]]
```

`BufferCache.incref_refholder(checksum, buffer=None, scratch=False)` establishes the bridge on
`0 -> 1`; `decref_refholder()` clears it on `1 -> 0` and demotes only under the shared predicate.
`Checksum` and `Buffer` expose internal convenience wrappers with the same semantics.
`register_refholder()` uses an identity-keyed weak registry. Holder
`_refheld_checksums()` is side-effect free; `_release_refholds()` is idempotent.

Resolved scope boundaries:

- scratch acquisition does not register a buffer remotely; later non-scratch interest upgrades
  registration monotonically. Explicit public interest in a scratch result refholds and protects
  it; unrequested scratch results remain purgeable;
- only the top-level checksum of a deepcell/deepfolder is owned. Deep members rely on existing
  deep-buffer resolution and remote durability;
- execution workers use no-op registry/refholder wrappers and run no lifecycle audit. Parent-side
  objects retain ownership across IPC;
- remote/database/jobserver services publish or retrieve buffers but do not gain a new distributed
  reference-count protocol. Remote-registration status is not a semantic claim;
- shared-memory PID accounting and durable remote storage are outside this lifecycle count;
- no public attribution/report model, holder-token hierarchy, recursive deep ownership, or
  cross-process reference protocol is to be introduced by this handoff.

### 5.1 Starting implementation state and misleading evidence

The core architecture and production migrations already exist. The two defects fixed immediately
before this handoff are in `seamless-workflow/seamless_workflow/context.py`: checksum-backed module
replacement now stages the new role before releasing the old one, and failed bound-Transformer
replacement now restores semantic/runtime state and exact ownership. Commit `2eb593b` contains
both fixes and their three regressions in
`seamless-workflow/tests/test_reference_lifecycle_binding.py`. Treat that commit as baseline, not
work to reproduce.

Do not mistake the following existing green tests for completion evidence:

- the current forced-cap helper leaves remote resolution and recomputation controls to callers;
- the named forced-cap coverage proves only a Cell case unless V1/V2 are added;
- existing shutdown coverage does not by itself prove the full atexit, cleanup-exception, and
  corrupted-bridge subprocess matrix;
- helper-dispatch Dask tests do not exercise actual cached/thin/fat mixin branches;
- partial PreTransformation and CodeManager happy paths do not prove every role/multiplicity;
- a delayed-dependency test that expires data only after all dependencies finish does not prove
  per-result adoption before the next wait.

No remaining known test asserts superseded production semantics. Therefore the criterion in
section 2 does not authorize deleting a green assertion: these narrow tests must be extended as
specified in V1-V5. If a new defect proves an assertion superseded, first replace it with the
correct role/count/order assertion and a failing negative control. Any newly exposed production
defect receives a focused red regression, a separate fix in the owning repository, and a rerun of
the affected package before verification continues.

## 6. Normative verification rules

### 6.1 Test process isolation

Run one pytest process per test file. Buffer-cache state, holder registration, close state,
workers, and the `seamless.references` logger are process-global. A multi-file pytest invocation
is not primary evidence.

Every command in this handoff runs in the `seamless1` conda environment:

```bash
conda run -n seamless1 python -m pytest -q <test-file>
```

### 6.2 Positive tests require a negative control

Every test claiming that a lifecycle role retained a checksum must prove both sides:

```text
role acquired     -> forced expiry -> owner API succeeds -> repair counters remain zero
role not acquired -> forced expiry -> owner API fails in its normal way
```

The negative control may use a test-only acquisition bypass, an equivalent unowned object, or a
subprocess started from the same fixture. It must exercise the same payload shape and owning API.
Simply releasing a holder after the positive assertion is insufficient if a different cache or
repair path can still supply the data.

### 6.3 Defeat all six masking mechanisms

For every forced-expiry test, explicitly defeat or measure:

1. live temprefs;
2. caller-owned `Buffer` objects;
3. weak-cache or expression-result-buffer survival;
4. another holder claiming the same checksum;
5. local/remote durable-storage refetch;
6. Expression or Transformation recomputation/fingertip.

Use unique content, normally containing `uuid4().hex`, for each case. Do not use small/trivial
payloads whose checksum may be shared with another test or `TRIVIAL_CHECKSUMS`.

### 6.4 Assert attribution, not only aggregate counts

Whenever producer and consumer can claim the same checksum, assert all three:

- the producer's `_refheld_checksums()` contribution;
- the consumer's `_refheld_checksums()` contribution;
- the aggregate `(refholder_count, manual_refs, bridge)` snapshot.

This prevents one holder's accidental over-hold from masking another holder's omitted adoption.

### 6.5 Test-only instrumentation boundaries

Tests may inspect internal cache entries, registry snapshots, operational CodeManager maps, and
private lifecycle flags. Do not add a public attribution/report API. Test instrumentation must not
change production ownership semantics.

## 7. Shared forced-expiry test substrate

Repository: `seamless-core`.

Extend `tests/helpers/reference_lifecycle.py` rather than duplicating cache surgery in each
component.

### 7.1 Required helper behavior

Provide a helper/context fixture that:

- receives a concrete checksum and optional component-specific cleanup callbacks;
- asserts the payload is not a trivial checksum;
- clears the checksum's tempref;
- removes the checksum from the weak cache;
- removes it from `_expression_result_buffers` when present;
- removes raw fallback data from `checksum_cache` where the tested resolution path can consult it;
- drops caller-supplied Buffer holders before `gc.collect()`;
- temporarily sets soft/hard caps below the tested working set;
- runs one eviction pass and two GC passes;
- restores cap configuration even when the assertion fails;
- returns observable before/after cache snapshots and repair counters.

Do not clear the refholder bridge or count in the positive case. That bridge is the behavior under
test.

### 7.2 Repair guards

Each component test supplies monkeypatch guards appropriate to its owning API:

- `seamless_remote.buffer_remote.get_buffer`: return `None` and increment a refetch counter;
- `seamless_remote.database_remote.get_rev_transformations`: return no candidates and count calls;
- `seamless_remote.database_remote.get_rev_expressions`: return no candidates and count calls;
- Expression cache/reverse-expression entries: remove the target result mapping for negative
  controls;
- `recompute_from_transformation_checksum` and sync counterpart: raise/count instead of executing;
- Transformation cache result lookup: remove the target mapping where cache recovery would mask
  eviction;
- jobserver/Dask fallback hooks: fail/count rather than re-materialize a buffer.

Positive cases assert every repair counter is zero. Negative cases assert the owner fails without
silently succeeding through repair; a counter may be positive only when that owner normally tries
the guarded path before reporting failure.

### 7.3 Holder uniqueness check

Before expiry, collect registered claims for the checksum and assert the exact expected holder and
role list. This proves there is no same-checksum holder elsewhere in the process.

## 8. Verification package V1 — Core forced expiry and cache accounting

Repositories/files:

```text
seamless-core/tests/helpers/reference_lifecycle.py
seamless-core/tests/test_reference_lifecycle_forced_expiry.py
seamless-core/tests/test_reference_lifecycle_cache.py
seamless-core/tests/test_expression_reference_lifecycle.py
```

### 8.1 Forced-expiry cases

Add positive and negative controls for:

- standalone Cell checksum input;
- public Expression result published before public interest;
- public Expression result with interest enabled before publication;
- repeated public access, proving one result role;
- a top-level deepcell/deepfolder checksum, proving only the top-level checksum is refheld;
- distinct value-equal Expressions independently claiming the same result.

For Expression cases, remove `_expression_result_buffers`, `checksum_cache`, and relevant
expression-cache entries as applicable. Resolve through the public Expression result/value path,
not directly through an internal cache lookup.

### 8.2 Cache-accounting matrix

Complete the matrix in `test_reference_lifecycle_cache.py`:

- manual refs 0/1/many crossed with refholder refs 0/1/many;
- live tempref versus expired tempref on both decrement paths;
- scratch purge with no protection, bridge protection, manual protection, and non-scratch tempref;
- scratch-first followed by non-scratch acquisition and remote-registration monotonicity;
- user-requested scratch result protected versus unrequested scratch result purgeable;
- protected entries absent from candidate scoring/removal;
- over-cap warning emitted once, suppressed for unchanged state, and re-emitted after material
  state change;
- forced cleanup clears manual counts and bridges but preserves a live tempref entry with snapshot
  `(0, 0, False)`;
- corrupted count/bridge combinations remain observable to the audit before forced cleanup.

### 8.3 Acceptance and commands

```bash
for test_file in \
  tests/test_reference_lifecycle_cache.py \
  tests/test_cell_reference_lifecycle.py \
  tests/test_expression_reference_lifecycle.py \
  tests/test_reference_lifecycle_forced_expiry.py; do
  conda run -n seamless1 python -m pytest -q "$test_file" || exit 1
done
```

Acceptance evidence must name the repair guards used by every survival test and show its failing
negative control.

## 9. Verification package V2 — Transformer and workflow forced expiry

Repositories: `seamless-transformer`, `seamless-workflow`.

Create these focused files:

```text
seamless-transformer/tests/test_reference_lifecycle_forced_expiry.py
seamless-workflow/tests/test_reference_lifecycle_forced_expiry.py
```

### 9.1 Transformer role cases

Cover:

- standalone builder checksum pin;
- checksum-backed builder code;
- checksum-backed builder module;
- direct Transformation input;
- already-evaluated Transformation dependency result;
- one fast and one delayed dependency, proving per-result adoption before waiting;
- constructed Transformation definition retained after completion;
- public Transformation result before publication and after neutral internal publication;
- producer cleanup after consumer adoption;
- terminal cancellation release;
- scratch input tempref-only in PreTransformation then bridge-protected after Transformation
  adoption;
- user-requested scratch result retained until cleanup, with an unrequested scratch result as the
  purgeable control.

The delayed-dependency test must forcibly expire the fast result while the sibling remains
pending. It must fail when `_adopt_input_checksum()` is bypassed. A test that waits for both
dependencies and then expires the checksum does not prove handoff timing.

### 9.2 Workflow role cases

Cover:

- Cell literal and current result as two independent roles;
- Transformer pin, code, and checksum-backed module roles;
- Transformer current result;
- retained superseded result for its exact cap/deadline lifetime;
- eager and non-eager contexts;
- literal replaced by a connection;
- checksum-backed Cell and Transformer builder binding;
- same-checksum replacement;
- node and namespace subtree deletion;
- graph copy/load/replacement;
- prune, retention-cap eviction, and deadline expiry.

Resolve through bound Cell/Transformer APIs. Assert bound handles add no claim. For retained
superseded results, advance the policy clock deterministically; do not use real sleeps.

### 9.3 Commands

```bash
# seamless-transformer
for test_file in \
  tests/test_transformer_reference_lifecycle.py \
  tests/test_transformation_reference_lifecycle.py \
  tests/test_expression_transformation_dependencies.py \
  tests/test_reference_lifecycle_forced_expiry.py; do
  conda run -n seamless1 python -m pytest -q "$test_file" || exit 1
done

# seamless-workflow
for test_file in \
  tests/test_garbage_collection.py \
  tests/test_literal_retention.py \
  tests/test_reference_lifecycle_binding.py \
  tests/test_reference_lifecycle_forced_expiry.py \
  tests/test_runtime_and_prune.py; do
  conda run -n seamless1 python -m pytest -q "$test_file" || exit 1
done
```

## 10. Verification package V3 — Shutdown and atexit subprocess matrix

Repository/file:

```text
seamless-core/tests/test_reference_lifecycle_shutdown.py
```

Every scenario runs in a new subprocess. Do not call irreversible `seamless.close()` in the
parent pytest process.

### 10.1 Required cases

- balanced explicit close is quiet on `seamless.references`;
- balanced atexit-only close is quiet on `seamless.references` while allowing the existing general
  atexit notice;
- explicit close followed by atexit audits only once;
- refholder count greater than live claims;
- live claims greater than refholder count;
- dead-holder unattributed excess;
- missing bridge with positive count;
- present bridge with zero count;
- pre-existing manual leak warns once;
- a manual leak first introduced during holder cleanup is detected post-cleanup;
- manual and refholder decrement-underflow warnings;
- claim collection exception isolation;
- cleanup exception isolation;
- holder cycle/finalizer followed by two GC passes;
- residual count/bridge/manual state detected before forced clearing;
- buffer-writer flush occurs before holder cleanup and forced accounting cleanup;
- post-close accounting is empty, or contains only live-tempref entries with `(0, 0, False)`.

### 10.2 Determinism requirements

Use multiple checksums and holders in deliberately unsorted construction order. Assert sorted
checksum/class/role output. Normalize object IDs before comparison; never assert their numeric
values.

### 10.3 Command

```bash
conda run -n seamless1 python -m pytest -q \
  tests/test_reference_lifecycle_shutdown.py
```

Acceptance: every deliberate corruption produces its named warning before forced cleanup;
balanced explicit and atexit paths produce none.

## 11. Verification package V4 — Dask lifecycle publication paths

Repository/file:

```text
seamless-dask/tests/test_transformation_reference_lifecycle.py
```

The existing two tests only prove helper dispatch and neutral publication. Retain them, then add
coverage through actual `TransformationDaskMixin` execution branches.

### 11.1 Required unit paths

Using the repository's fake client/future patterns, exercise:

- definition publication on local cache hit;
- result publication on cached-result return;
- thin future success;
- fat future/value acquisition;
- neutral internal dependency evaluation;
- public-after-internal result acquisition exactly once;
- scratch definition/result temprefs;
- requested scratch result bridge protection;
- failure publishes no result role;
- cancellation and late future completion publish no result and leave no roles;
- definition/result assignments occur only through owner publication helpers.

Assert the actual Transformation fields, semantic claims, cache snapshot, and tempref scratch flag.
A mock owner that merely records helper calls is not sufficient for these cases.

### 11.2 Service-backed path

When Dask services are available, run one real cached/thin/fat lifecycle scenario and the existing
dependency/cancellation suites. If unavailable, retain the deterministic unit coverage and record
the service-backed command as skipped with the concrete reason.

### 11.3 Commands

```bash
for test_file in \
  tests/test_transformation_reference_lifecycle.py \
  tests/test_dependencies.py \
  tests/test_expression_inputs.py \
  tests/test_task_cancel.py \
  tests/test_dask_cancel_reclaim.py; do
  conda run -n seamless1 python -m pytest -q "$test_file" || exit 1
done
```

## 12. Verification package V5 — Partially coupled role invariants

Repository: `seamless-transformer`.

### 12.1 PreTransformation matrix

Extend `tests/test_pretransformation.py` with:

- mixed scratch and non-scratch pins in one object;
- repeated same checksum in two non-scratch pins;
- partial preparation failure after one successful conversion;
- scratch pin absent from `_value_refs` and logical counts;
- non-scratch `_value_refs` role/count agreement;
- acquire-before-release transfer into Transformation;
- release and double release;
- destructor cleanup and destructor-cleanup exception warning;
- CodeManager roles remaining attributed to CodeManager, never PreTransformation.

For transfer ordering, instrument snapshots at acquisition/release boundaries and assert the
bridge never becomes false.

### 12.2 CodeManager matrix

Extend `tests/test_code_manager.py` to cover:

- syntactic direct only;
- semantic direct only;
- syntactic direct creating semantic guard;
- semantic direct creating syntactic guard;
- every direct multiplicity greater than one;
- multiple syntactic variants for one semantic checksum;
- repeated same checksum across direct and guard roles;
- release orders in both directions;
- unknown decrement behavior;
- `_release_refholds()` and double cleanup;
- direct demand-map multiplicity, `_refheld_checksums()` multiplicity, cache count, and one bridge
  agreeing after every transition.

### 12.3 Command

```bash
for test_file in tests/test_pretransformation.py tests/test_code_manager.py; do
  conda run -n seamless1 python -m pytest -q "$test_file" || exit 1
done
```

A warning-free shutdown audit is not sufficient acceptance evidence for these partially coupled
roles.

## 13. Verification package V6 — Call-site audit and full regression

### 13.1 Manual-reference classification

Run:

```bash
rg -n '\.(incref|decref)\(' \
  seamless-core/seamless \
  seamless-transformer/seamless_transformer \
  seamless-workflow/seamless_workflow \
  seamless-dask/seamless_dask
```

Classify every match as:

- public/manual user lease;
- scoped CLI/transport lease with all return/exception releases;
- unrelated shared-memory PID accounting;
- defect.

No Cell, Expression, Transformer, PreTransformation, Transformation, CodeManager, or Context
lifecycle role may use the public manual API.

### 13.2 Hidden-public-result classification

Run:

```bash
rg -n '\.(compute|computation|result|result_checksum|buffer|value)\b' \
  seamless-transformer/seamless_transformer \
  seamless-workflow/seamless_workflow \
  seamless-dask/seamless_dask
```

Classify every match. Dependency, scheduler, PreTransformation, backend publication, and internal
CLI orchestration paths must use named internal accessors unless the call intentionally represents
user result interest. Distinguish unrelated `Future.result()`, process buffers, and workflow
record fields.

### 13.3 Full per-file serial suites

```bash
run_test_files() {
  while IFS= read -r -d '' test_file; do
    conda run -n seamless1 python -m pytest -q "$test_file" || return 1
  done < <(find tests -type f -name 'test_*.py' -print0 | sort -z)
}

for repository in \
  seamless-core \
  seamless-transformer \
  seamless-workflow \
  seamless-dask; do
  cd "/home/agent/seamless1/$repository" || exit 1
  run_test_files || exit 1
done
```

Run the backend-facing repositories with the same one-file-per-process rule:

```bash
for repository in seamless-remote seamless-jobserver; do
  cd "/home/agent/seamless1/$repository" || exit 1
  run_test_files || exit 1
done
```

The `seamless-transformer` full suite is the worker-path regression command; the
`seamless-dask`, `seamless-remote`, and `seamless-jobserver` loops are the backend integration
commands. Record each file's pass/fail/skip outcome. Do not describe a backend as exercised when
its required service was unavailable or its test skipped; give the exact skip reason and retain
the deterministic unit evidence separately.

### 13.4 Stability outcomes

Add or run named long-enough regressions proving:

- repeated workflow replacement reaches steady strong-cache use after superseded retention ends;
- a protected working set larger than the cap remains resolvable and emits a rate-limited warning;
- balanced test subprocesses leave `seamless.references` quiet;
- post-close accounting contains no count, bridge, or manual residue.

## 14. Ordered implementation and commit sequence

Execute V1 through V6 in order. After each package, run its focused commands and stop on failure;
the package is the rollback/commit boundary and must leave its repository green before the next
one begins. V5 may be developed alongside the Transformer part of V2, but it is not accepted until
both of its direct matrices pass. V6 starts only after V1-V5 evidence is complete.

Use one coherent commit per affected repository/package:

1. prerequisite checkpoint: from `seamless-workflow`, confirm
   `git merge-base --is-ancestor 2eb593b HEAD` succeeds and rerun
   `test_reference_lifecycle_binding.py`;
2. `seamless-core`: shared forced-expiry helper plus V1 tests;
3. `seamless-transformer`: V2 Transformer tests and V5 invariant tests;
4. `seamless-workflow`: V2 workflow forced-expiry/policy tests;
5. `seamless-core`: V3 shutdown/atexit matrix;
6. `seamless-dask`: V4 actual-path tests;
7. any production defect exposed by those tests, as a separate implementation commit in its owning
   repository followed by the test commit;
8. final evidence/report update, if the project keeps reports in-repository.

Before every commit, recheck status and preserve unrelated changes. Do not commit this handoff
document unless explicitly requested.

## 15. Final report requirements

The implementing agent's handoff report must contain:

1. one-line certification result;
2. commits grouped by repository and verification package;
3. exact focused and full-suite commands with pass/fail/skip totals;
4. the positive and negative result for every forced-expiry role;
5. the six masking mechanisms defeated in each component and all repair-counter values;
6. shutdown cases and normalized warning text;
7. Dask/remote/jobserver/worker services actually exercised;
8. complete manual-reference and hidden-public-call classifications;
9. final post-close accounting snapshots;
10. every new runtime defect discovered, its fix commit, and its regression test;
11. deviations from this plan with equivalent evidence.

## 16. Definition of done

Verification is complete only when:

- all six packages V1–V6 satisfy their acceptance criteria;
- every checksum-survival assertion has a failing unowned negative control;
- positive cases report zero refetch and recompute events;
- all partially coupled roles have direct state/count/bridge invariants;
- explicit close and atexit pass the complete subprocess matrix;
- actual Dask cached/thin/fat paths have deterministic coverage;
- all component tests pass one file per process in `seamless1`;
- backend skips are explicit and are not counted as coverage;
- the final report makes the certification independently reproducible.

## 17. Handoff-readiness coverage map

This table is the final self-containment check. The implementer should report a specification
blocker before coding if any referenced section is absent or contradictory.

| Criterion from section 2 | Normative coverage |
|---|---|
| 1. Terms and invariants | Section 3 defines terminology, accounting equivalence, demotion, and role invariants. |
| 2. Runtime versus shutdown | Section 3.2 separates continuous survival/balance from observational and forced shutdown cleanup; V3 supplies evidence. |
| 3. Repositories, modules, misleading evidence | Sections 1 and 5 name the repositories, anchors, fixed defects, and false-confidence gaps. |
| 4. Exact ownership | Section 4 defines every in-scope refholder class, stable roles, and boundaries. |
| 5. Cache fields and internal APIs | Section 5 defines the snapshot tuple, count/bridge transitions, registry, and holder protocol; sections 6-7 define test instrumentation. |
| 6. Lifecycle ordering | Sections 3.1 and 4 define replacement, publication, adoption, cancellation, and cleanup ordering. |
| 7. Resolved choices | Sections 4-7 fix public/internal interest, instrumentation, process isolation, and negative-control design; no listed item is optional. |
| 8. Worker/scratch/remote/deep boundaries | Section 5 fixes all four boundaries and non-goals. |
| 9. Ordered testable phases | Sections 8-14 define V1-V6, focused acceptance commands, gates, and commit boundaries. |
| 10. Superseded test behavior | Section 5.1 records that no known assertion remains superseded, identifies narrow misleading evidence, and defines the rewrite rule if verification exposes one. |
| 11. Focused and full commands | Sections 8-13 provide commands, all using `conda run -n seamless1`; section 13.3 covers all six component/backend repositories. |
| 12. Observable completion evidence | Sections 15-16 require negative controls, repair counters, warning text, snapshots, backend status, totals, and reproducible certification. |
