# Checksum Reference Lifecycle — Finalization Handoff Plan

## 1. Purpose, authority, and current verdict

This document is the handoff for finishing the implementation described by
`checksum-reference-lifecycle-handoff-plan.md`. The original handoff remains the normative
contract for ownership roles, cache accounting, publication, shutdown ordering, and the
required test matrix. This document records the independently verified state of the committed
implementation and gives the shortest safe path from that state to full compliance.

The assessment was made against these component heads on 2026-08-13:

| Repository | Head | Relevant implementation state |
|---|---|---|
| `seamless-core` | `cd86151` | bridge, registry, Cell/Expression, shutdown, one forced-cap case |
| `seamless-transformer` | `559cc5a` | builder, PreTransformation, CodeManager, Transformation, cancellation fixes |
| `seamless-workflow` | `94548d1` | Context lifecycle integration |
| `seamless-dask` | `59afe07` | centralized Dask publication calls |
| `seamless-remote` | `a23b22e` | no lifecycle-specific local ownership change |
| `seamless-jobserver` | `0289ff4` | existing jobserver integration |

All component worktrees were clean at assessment time.

**Verdict:** the cache bridge and broad ownership architecture are implemented, but the current
code is not plan-complete. There are confirmed runtime/accounting defects in addition to the
public/internal PreTransformation violation reported by Luna. The missing tests are material:
several of them would fail on the committed code, and one current Transformation test passes for
the wrong reason.

Do not claim completion until every confirmed defect in section 3 is fixed, every evidence gap
in section 4 is closed, and the exit criteria in section 10 are recorded.

## 2. Assessment method and evidence

The assessment compared the normative requirements in sections 3–13 of the original handoff
against the committed call sites and lifecycle tests. Focused tests were run one file per pytest
process in the required `seamless1` conda environment.

Passing assessment commands:

```bash
# seamless-core: 20 passed
for test_file in \
  tests/test_reference_lifecycle_cache.py \
  tests/test_reference_lifecycle_registry.py \
  tests/test_cell_reference_lifecycle.py \
  tests/test_expression_reference_lifecycle.py \
  tests/test_reference_lifecycle_forced_expiry.py \
  tests/test_reference_lifecycle_shutdown.py; do
  conda run -n seamless1 python -m pytest -q "$test_file" || exit 1
done

# seamless-transformer: 8 passed
for test_file in \
  tests/test_transformer_reference_lifecycle.py \
  tests/test_pretransformation.py \
  tests/test_code_manager.py \
  tests/test_transformation_reference_lifecycle.py; do
  conda run -n seamless1 python -m pytest -q "$test_file" || exit 1
done

# seamless-workflow: 24 passed
for test_file in \
  tests/test_garbage_collection.py \
  tests/test_literal_retention.py \
  tests/test_runtime_and_prune.py \
  tests/test_context_basics.py \
  tests/test_dependencies_and_pins.py; do
  conda run -n seamless1 python -m pytest -q "$test_file" || exit 1
done
```

These 52 passing tests establish that the implemented happy paths are stable. They do not
establish full compliance. Isolated `conda run -n seamless1` probes reproduced all defects marked
“reproduced” below without modifying a worktree.

## 3. Confirmed implementation defects

### 3.1 Internal dependency evaluation still creates public result interest

This is broader than the two PreTransformation call sites previously reported.

1. `seamless_transformer/pretransformation.py` reads
   `Transformation.result_checksum` and calls `Expression.compute()` in both
   `PreTransformation` and `PreparedPreTransformation` (current lines 159–166 and 279–286).
2. `Transformation._compute(api_origin="dependency")` calls `self.start(loop=task_loop)` without
   `_internal=True` (current `transformation_class.py` lines 925–935). Public `start()` enables
   result holding, so the supposedly internal dependency path sets `_refhold_result` and acquires
   the producer result.
3. The sync and async Expression dependency helpers call low-level evaluators directly. They do
   not publish the result into the Expression object via `_publish_result()`. Consequently the
   real internal-before-public transition is not implemented; the existing core test simulates
   it by calling `_publish_result()` manually.

Reproduced result: calling `producer._compute(api_origin="dependency")` changes
`(_refhold_result, _result_refheld)` from `(False, False)` to `(True, True)`.

Required outcome:

- Add named internal Expression sync/async evaluation methods that publish but never express
  user interest.
- Add named internal Transformation sync/async dependency methods. Do not rely on a string that
  can later fall through to a public `start()` call.
- Make public methods enable result holding and then delegate to the internal methods.
- Make PreTransformation and all dependency/scheduler code call only those internal methods and
  `_result_checksum_internal()`.
- Add an `rg` guard test or review command covering public `compute`, `computation`, `result`,
  `result_checksum`, `buffer`, and `value` reads in framework internals.

### 3.2 The sync already-evaluated dependency path does not adopt results

`Transformation._run_dependencies()` returns immediately when all dependencies are already
evaluated (current lines 779–785). Those dependency pins are excluded from direct-input adoption
in `__init__`, and `_prepared_dict_with_dependencies()` only reads their checksums. The consumer
therefore constructs without acquiring `"input:<pin>"` roles.

The current test `test_internal_dependency_evaluation_does_not_hold_producer_result` is a false
positive: its observed count of one comes from defect 3.1 (the producer accidentally holds its
result), not from consumer adoption.

Required outcome:

- Remove the early return as an ownership shortcut.
- For every dependency, evaluated or not, observe its successful result and call
  `_adopt_input_checksum()` before moving to the next dependency.
- Keep async `FIRST_COMPLETED`/per-task adoption ordering; add the same already-evaluated case to
  both sync and async tests.
- In tests, assert the producer contributes zero result claims while the consumer contributes
  exactly one `input:<pin>` claim. Then release the producer and force expiry before the consumer
  continues.

### 3.3 Public Transformation `buffer` and `value` reads do not express result interest

`Transformation.buffer` reads `_result_checksum_internal()` directly and `value` delegates to
`buffer` (current lines 1212–1221). If a result was published internally, either public property
returns it without setting `_refhold_result` or acquiring the result role.

Reproduced result: after `_publish_result()` with neutral internal state, reading `.buffer`
leaves the result snapshot `(0, 0, False)` and `_refhold_result is False`.

Required outcome: both public properties must call `_enable_result_holding()` before using the
internal accessor. Framework code needing a Buffer/value must use explicitly named internal
helpers that remain neutral.

### 3.4 Terminal cancellation does not release Transformation ownership

`cancel()` and `cancel_async()` call `_mark_cancelled()` but never `_release_refholds()` (current
lines 492–572). `_mark_cancelled()` also clears `_result_checksum` before any possible held-result
release (lines 431–442), which can make a racing result hold unreleasable by the object.

Reproduced result: cancelling an unstarted Transformation leaves its direct input and code input
counts and semantic claims live.

Required outcome:

1. request cancellation;
2. settle or explicitly detach tracked local/remote/Dask work using the existing timeout policy;
3. prevent later publication into the cancelled object;
4. release input, definition, and any held result while their checksum fields are intact;
5. only then clear terminal state fields.

Cancellation of an already completed Transformation remains a no-op and retains user-held
state, as required by the original handoff.

### 3.5 CodeManager repeated semantic release is unbalanced

`CodeManager.incref_semantic()` acquires on every direct increment, but
`decref_semantic()` decrements the cache only on the `1 -> 0` transition (current
`code_manager.py` lines 71–91).

Reproduced result: two semantic increments followed by one decrement leave cache count two while
the semantic demand map and `_refheld_checksums()` claim one.

Required outcome: release one semantic direct refholder reference on every successful decrement.
Only syntactic guard removal is conditional on the semantic direct count reaching zero. Exercise
all four role families and all multiplicities directly.

### 3.6 Transformer builder mutation and copying leak or omit references

There are two independent bugs.

- `ArgsWrapper.__delitem__()` deletes a checksum-bearing argument without calling the owner
  replacement helper (current `transformer_class.py` lines 778–783). Reproduced result: the
  semantic claim disappears while refholder count one and the bridge remain after deletion and
  even after builder cleanup.
- `direct(existing_transformer)` and `delayed(existing_transformer)` construct objects with
  `__new__` and copy `__dict__` (current lines 44–93). They neither register the new builder nor
  independently acquire its checksum roles. The delayed form also aliases mutable state.
  Reproduced result: two builders each claim the same checksum, the count remains one, and the
  second builder is absent from the weak registry.

Required outcome:

- Route argument deletion through acquire/publish/release owner helpers.
- Replace raw `__dict__` cloning with one lifecycle-aware clone/snapshot constructor that
  initializes neutral fields, registers the new object, copies definition state without aliasing,
  and independently acquires every checksum pin/code/module role.
- Test copy/conversion, equal replacement, deletion, independent mutation, independent cleanup,
  and partial-copy failure rollback.

### 3.7 Checksum-backed builder binding into Context is broken and does not transfer ownership

`checksum_for_value()` always serializes its argument as a Python value
(`seamless_workflow/adapters.py` line 13). Context uses it for a standalone Cell input and
Transformer pin during binding (current `context.py` lines 198–219 and 270–293). A `Checksum`
therefore raises `TypeError` instead of being adopted as checksum state.

Even for states that do bind, Context changes `_workflow_backend` but never calls the standalone
builder's `_release_refholds()`. That contradicts the required adoption-first, builder-release
handoff and leaves a bound builder as an extra holder.

Required outcome:

- Preserve the API distinction between literal values and explicit `Checksum` objects. Do not
  reinterpret ordinary 64-character strings.
- Bind transactionally: Context acquires all literal/pin/code/module/current roles first; only
  after successful adoption publish the backend and release the standalone builder roles.
- On failure, roll back newly acquired Context roles and leave the builder standalone and
  unchanged.
- When replacing an existing bound transformer, acquire replacement pin roles before releasing
  removed/old roles. Do not clear the old pin table first.

### 3.8 Namespace deletion does not delete its subtree or release roles

For a path present only in `ContextGraph.namespaces`, `_delete()` removes namespace markers but
does not remove descendant nodes, runtime records, edges, or references (current `context.py`
lines 174–177).

Reproduced result: after `del ctx.sub`, `('sub', 'value')` remains in the graph and both its
literal and current roles remain held.

Required outcome: factor one subtree-deletion helper used for node roots and namespace roots. It
must acquire nothing, remove all descendant nodes/runtime records/edges, release current,
producer, code, module, and superseded roles exactly once, and then derive the remaining graph.

### 3.9 Context code claims are derived from an acquisition mirror

`Context._refheld_checksums()` reads `_code_refholds` rather than
`node.transformer_config.code_checksum` (current lines 653–669). A missing code acquisition would
therefore remove both the count and the audit claim, defeating the intended independent check.

Required outcome: derive the `"transformer:<path>:code"` claim from graph/config semantic state.
Keep operational tables only where needed to balance mutations; never use them as audit evidence.
Add a deliberate omitted-acquisition test that yields a claims-greater-than-count warning.

### 3.10 Forced shutdown cleanup leaves manual accounting live

`BufferCache.force_clear_reference_accounting()` clears refholder counts and bridges but not
`manual_refs` (current `buffer_cache.py` lines 337–344).

Reproduced result: after a deliberate manual leak and `seamless.close()`, the snapshot remains
`(0, 1, False)`. This violates the required final forced-accounting cleanup.

The post-cleanup audit also calls `audit_reference_accounting(..., warn_manual=False)`. That
avoids duplicate warnings, but it would silently miss a manual reference first introduced during
holder cleanup.

Required outcome:

- Pre-cleanup: warn once for each checksum with positive manual refs and remember which checksums
  were warned internally.
- Post-cleanup: warn for positive manual refs not present in the pre-cleanup warned set; do not
  duplicate existing warnings.
- Forced cleanup: set residual `manual_refs` to zero, clear refholder counts/bridges, and demote
  entries allowed by the shared tempref predicate.
- Assert the residual snapshot after deliberate leaks is empty or contains only live-tempref
  entries with `(0, 0, False)`.

### 3.11 Most holder finalizers suppress cleanup exceptions without logging

Cell, Expression, Transformer, Transformation, PreTransformation, and CodeManager finalizers
generally catch and silently discard lifecycle cleanup exceptions. The normative contract
requires a warning followed by suppression so shutdown/finalization continues.

Required outcome: use one small internal safe-release helper, or consistent local implementations,
that logs holder class/id and the exception on `seamless.references`. It must be safe during
partial module teardown and must not double-warn for an already completed cleanup.

## 4. Required evidence still missing

The following are completion blockers even after section 3 is fixed.

### 4.1 Forced-expiry and forced-cap proof

The current helper deliberately leaves remote resolution and recomputation controls to callers,
but current callers do not supply complete controls. The named forced-cap suite contains only a
Cell case.

Add survival plus negative-control coverage for:

- standalone Cell checksum input;
- standalone Transformer checksum pin, code checksum when checksum-backed, and module checksum;
- Transformation direct input, already-evaluated dependency input, delayed dependency input,
  and definition;
- public Expression and Transformation results;
- Context literal, pin, code/module, current result, and retained superseded result;
- top-level deep checksum;
- user-requested scratch Transformation result, with an unrequested scratch result as the
  purgeable control.

Every case must use unique content and defeat all six masking mechanisms: tempref, caller-owned
Buffer, weak-cache survival, another same-checksum holder, durable-storage refetch, and
recomputation/fingertip. Record zero refetch/recompute counters. Then disable the intended
acquisition in a negative-control variant and prove the owning API fails in the normal way.

The reusable helper may remain cache-focused, but each caller must provide explicit repair
guards/counters. A helper docstring saying repair is caller-owned is not evidence that callers
did it.

### 4.2 Cache accounting combinations

Extend `tests/test_reference_lifecycle_cache.py` for:

- zero/one/many manual refs crossed with zero/one/many refholder refs;
- live and expired temprefs during decrements and eviction;
- scratch purge with bridge, manual ref, tempref-only, and no protection;
- scratch-first then non-scratch remote registration;
- protected candidate exclusion and rate-limited over-cap warning;
- forced cleanup of residual manual refs;
- absent entry and corrupted bridge post-cleanup behavior.

### 4.3 Partially coupled role invariants

Add direct state/count/bridge assertions, not only clean-audit assertions, for:

- Expression/Transformation result mode across public-before-result,
  internal-before-public, repeat access, exception, cancellation, and backend publication;
- all CodeManager syntactic/semantic direct/guard acquisition and release combinations,
  including multiplicity greater than one;
- PreTransformation mixed scratch/non-scratch pins, partial failure, idempotent release, and
  acquire-before-release transfer into Transformation.

### 4.4 Shutdown subprocess matrix

Expand `tests/test_reference_lifecycle_shutdown.py`. Every close scenario must run in its own
subprocess. Cover:

- balanced explicit close;
- balanced atexit-only close and explicit-close-plus-atexit idempotency;
- count excess, claim excess, dead-holder excess, and bridge corruption;
- pre-existing manual leak and manual leak introduced by cleanup;
- both decrement-underflow warnings;
- claim collection failure and cleanup failure isolation;
- broken finalizer/cycle followed by two GC passes and residual detection;
- buffer-writer flush occurring before forced accounting cleanup;
- corrupted bridge/manual state cleared only after it was warned.

Assertions may normalize object IDs, but must assert deterministic checksum, class, and role
ordering.

### 4.5 Backend publication and workflow policy coverage

- Add a focused `seamless-dask/tests/test_transformation_reference_lifecycle.py` covering cached,
  thin, and fat publication through `_publish_definition()`/`_publish_result()`, neutral internal
  evaluation, public-after-internal acquisition, scratch behavior, and cancellation cleanup.
- Exercise local, remote/database, jobserver, worker, and Dask result publication. If a service is
  unavailable, record a skip and do not claim that backend as covered.
- Complete workflow tests for eager/non-eager demand, checksum-backed builder binding, code and
  module roles, namespace deletion, graph replacement/copy/load, superseded cap/deadline/prune,
  and bound-handle neutrality.

## 5. Ordered implementation phases

Each phase ends in a reviewable state and one commit per affected repository. Preserve unrelated
work and recheck branch/status before every phase. Write the regression tests first so each
confirmed defect is observed failing before its fix.

### Phase F0 — Lock in red regressions

Repositories: `seamless-core`, `seamless-transformer`, `seamless-workflow`.

Add minimal failing tests for every defect in section 3. In particular, split producer and
consumer contributions in the existing Transformation test; do not assert only the aggregate
checksum count.

Acceptance before implementation: each new test fails for the named reason on the assessed
commit, and no existing test is weakened or deleted.

### Phase F1 — Repair core shutdown and audit cleanup

Repository: `seamless-core`.

Implement section 3.10, safe finalizer warning support from 3.11, and the cache/shutdown tests in
sections 4.2 and 4.4. Keep audit and cleanup as separate phases. Do not introduce a public report
object or a second close-hook phase.

Focused commands:

```bash
for test_file in \
  tests/test_reference_lifecycle_cache.py \
  tests/test_reference_lifecycle_registry.py \
  tests/test_reference_lifecycle_shutdown.py; do
  conda run -n seamless1 python -m pytest -q "$test_file" || exit 1
done
```

Acceptance: all mismatch warnings precede forced cleanup; balanced explicit/atexit subprocesses
emit no `seamless.references` warning; deliberate residual accounting is zeroed after warning.

### Phase F2 — Repair builder, PreTransformation, and CodeManager balance

Repository: `seamless-transformer`.

Implement sections 3.1's PreTransformation portion, 3.5, 3.6, and the applicable finalizer
logging. Ensure PreTransformation uses the new internal evaluation API introduced in F3; if the
API is not yet available, land F3's small core API commit first and keep the transformer commit
dependent on it.

Focused commands:

```bash
for test_file in \
  tests/test_transformer_reference_lifecycle.py \
  tests/test_pretransformation.py \
  tests/test_code_manager.py; do
  conda run -n seamless1 python -m pytest -q "$test_file" || exit 1
done
```

Acceptance: mutation/copy/binding-preparation paths balance exact semantic multiplicity; every
CodeManager role combination returns to zero; scratch pins are never decremented as logical refs.

### Phase F3 — Repair Expression/Transformation publication, handoff, and cancellation

Repositories: `seamless-core`, `seamless-transformer`, then `seamless-dask`.

Implement sections 3.1–3.4. Centralize the following contracts:

```text
public Expression/Transformation entry
  -> enable result interest once
  -> call neutral internal evaluation
  -> centralized publication

dependency/scheduler entry
  -> call neutral internal evaluation
  -> centralized publication
  -> consumer adopts or temprefs on the observation path
```

Do not duplicate lifecycle logic in Dask. Its mixin must call owner publication helpers for every
cache-hit, thin, and fat path.

Focused commands:

```bash
# seamless-core
for test_file in \
  tests/test_expression_reference_lifecycle.py \
  tests/test_expression_local_evaluation.py \
  tests/test_expression_remote_evaluation.py \
  tests/test_expression_fingertip.py; do
  conda run -n seamless1 python -m pytest -q "$test_file" || exit 1
done

# seamless-transformer
for test_file in \
  tests/test_transformation_reference_lifecycle.py \
  tests/test_expression_transformation_dependencies.py; do
  conda run -n seamless1 python -m pytest -q "$test_file" || exit 1
done
for test_file in tests/cancellation/test_*.py; do
  conda run -n seamless1 python -m pytest -q "$test_file" || exit 1
done

# seamless-dask
conda run -n seamless1 python -m pytest -q \
  tests/test_transformation_reference_lifecycle.py
```

Acceptance: internal producer contribution is zero; consumer adoption is one; forced tempref
expiry cannot break a claimed dependency; public post-publication access acquires exactly once;
terminal cancellation leaves no roles; completed cancellation remains a no-op.

### Phase F4 — Repair Context adoption, deletion, and independent claims

Repository: `seamless-workflow`.

Implement sections 3.7–3.9 and the workflow coverage in 4.5. Use transactional helpers for
producer/code/module/current replacement and one subtree-removal helper. Claims must traverse
graph/runtime semantic state.

Focused commands:

```bash
for test_file in \
  tests/test_garbage_collection.py \
  tests/test_literal_retention.py \
  tests/test_runtime_and_prune.py \
  tests/test_context_basics.py \
  tests/test_dependencies_and_pins.py \
  tests/test_reference_lifecycle_binding.py; do
  conda run -n seamless1 python -m pytest -q "$test_file" || exit 1
done
```

`test_reference_lifecycle_binding.py` is a new focused file. It must include checksum-backed Cell
and Transformer binding, successful adoption-before-release, rollback on binding failure,
replacement with the same checksum, and namespace subtree deletion.

Acceptance: bound handles own no standalone roles; Context owns every adopted semantic role;
deleting/replacing/copying/loading state returns all removed roles to zero; deliberately omitted
code acquisition is detected as claim excess.

### Phase F5 — Complete forced-expiry, scratch, backend, and policy evidence

Repositories: all affected components.

Implement section 4.1 and the remaining items in 4.3–4.5. Keep each lifecycle case focused and
run each test file in a fresh process. The named forced-cap suite must cover more than Cell and
must resolve checksums through their owning APIs with repair counters at zero.

Suggested focused files:

```text
seamless-core/tests/test_reference_lifecycle_forced_expiry.py
seamless-transformer/tests/test_reference_lifecycle_forced_expiry.py
seamless-workflow/tests/test_reference_lifecycle_forced_expiry.py
seamless-dask/tests/test_transformation_reference_lifecycle.py
```

Acceptance: every positive survival case has a demonstrated failing negative control and lists
which hooks disabled remote/database/fingertip/recompute repair.

### Phase F6 — Call-site audit and full serial regression

Classify every remaining public manual reference call as user/manual lease, scoped transport/CLI
lease, or unrelated shared-memory accounting. There must be no object lifecycle call left on the
manual API.

Run and review:

```bash
rg -n '\.(incref|decref)\(' \
  seamless-core/seamless \
  seamless-transformer/seamless_transformer \
  seamless-workflow/seamless_workflow \
  seamless-dask/seamless_dask

rg -n '\.(compute|computation|result|result_checksum|buffer|value)\b' \
  seamless-transformer/seamless_transformer \
  seamless-workflow/seamless_workflow \
  seamless-dask/seamless_dask
```

For the second command, review every match. Scheduler/dependency/PreTransformation paths must use
the named internal APIs; public-facing wrappers and unrelated Future/Buffer members are expected
and must be classified.

Then run every test file in a fresh process:

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

Run the repository-integrated remote, jobserver, worker, and Dask commands used by CI after the
serial component suites. Record unavailable services and skips exactly.

## 6. Test design rules that may not be relaxed

1. One pytest process per test file. Process-global cache/close/logger state makes a batched
   multi-file invocation unsuitable as primary evidence.
2. Assert per-holder roles as well as aggregate counts whenever more than one holder can claim a
   checksum. Aggregate-only assertions caused the existing false positive.
3. Use acquire-before-publish-before-release for equal and unequal replacement.
4. A checksum-survival test without a failing negative control is incomplete.
5. A clean shutdown audit alone is insufficient for partially coupled Expression/Transformation
   result state, CodeManager maps, and PreTransformation converted-input state.
6. Do not weaken current cancellation/error-propagation tests to accommodate cleanup changes.
7. Do not add recursive deep-member refholding; only the top-level deep checksum is in scope.
8. Worker refholder APIs remain no-ops and workers do not run the lifecycle audit.

## 7. Commit boundaries

Use one coherent commit per repository per phase. Recommended order:

1. `seamless-core`: red regressions and internal Expression API;
2. `seamless-transformer`: builder/CodeManager/PreTransformation fixes;
3. `seamless-transformer`: Transformation dependency/cancellation fixes;
4. `seamless-dask`: backend lifecycle tests and any routing correction;
5. `seamless-workflow`: binding/subtree/audit fixes;
6. `seamless-core`: shutdown/atexit/forced cleanup if not already landed;
7. per-repository evidence-only test completion.

Cross-repository commits must identify their dependency commit hashes in the messages. Do not
commit either planning document unless explicitly requested.

## 8. Completion checklist by ownership role

| Holder/role | Runtime proof | Release proof | Audit proof |
|---|---|---|---|
| Cell `input` | forced expiry | replace/derive/bind/finalize | deliberate missing acquire |
| Expression `result` | internal/public transition | cleanup/finalize | direct result-state invariant |
| Transformer pin/code/module | forced expiry/copy | delete/bind/finalize | field-derived claim excess |
| PreTransformation input | mixed scratch transfer | partial failure/double cleanup | direct converted-state invariant |
| Transformation input | delayed and pre-evaluated dependency | cancel/cleanup/finalize | per-holder adoption assertion |
| Transformation definition | cap pressure/recompute readiness | cancel/cleanup | field-derived claim excess |
| Transformation result | all publication backends | cancel/finalize | direct result-state invariant |
| CodeManager four roles | every direct/guard combination | every multiplicity transition | demand-map/count/bridge equality |
| Context literal/pin/code/module | forced expiry | replace/delete/graph reset | graph-derived claims |
| Context current/superseded | cap/deadline lifetime | prune/delete/cleanup | runtime-derived claims |

## 9. Final implementation report requirements

The implementing agent must report:

1. one-line outcome and whether the original handoff is now fully satisfied;
2. commits grouped by repository and phase;
3. exact `seamless1` commands with pass/fail/skip totals;
4. backend services actually exercised;
5. the final manual-call and hidden-public-call classifications;
6. balanced explicit-close and atexit logger results;
7. forced-expiry controls and repair counters for every role family;
8. negative-control results;
9. post-close residual snapshots for balanced and deliberately corrupted subprocesses;
10. any deviation from either handoff document, with rationale and equivalent test evidence.

## 10. Definition of done

The lifecycle work is complete only when all of the following are true:

- every confirmed defect in section 3 has a regression test that failed before and passes after;
- every required evidence item in section 4 is present;
- internal framework evaluation never creates public result interest;
- every stored concrete checksum role is adopted before a wait/yield and released exactly once;
- protected buffers survive cap pressure without refetch/recompute;
- Context binding and subtree deletion are transactional and balanced;
- explicit close and atexit audit the same lifecycle exactly once;
- warnings precede forced cleanup, and residual accounting is cleared afterward;
- all component suites pass serially in the `seamless1` conda environment;
- the final report contains enough command and counter evidence for another engineer to reproduce
  the certification without relying on implementation intent.
