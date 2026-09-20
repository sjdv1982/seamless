# Tests for §10.4–§10.6: remote reads, error types, database HashTypes

## Handoff-ready test plan

This plan covers the parts of Part V that
[expression-where-the-data-is.md](expression-where-the-data-is.md) left out. That plan
implemented §10.1–§10.3 (where an expression is evaluated). This one designs the tests
for the three remaining sections of
[celltype-rename-review-decisions.md](celltype-rename-review-decisions.md):

- §10.4, the remote steps of standalone reads;
- §10.5, errors that keep their type across the jobserver;
- §10.6, HashTypes in the database.

Line numbers refer to the working tree of 2026-09-16. Uncommitted §10.1–§10.3 changes
must be preserved.

## 0. Decisions

The five points these tests waited on are settled (2026-09-16). The rulings are in
[celltype-rename-review-decisions.md](celltype-rename-review-decisions.md) §10.4–§10.6;
below is the short form and what each one means for the tests. The `(P1)`…`(P5)` markers
on the tests now mark a dependency on the *implementation*, not on a pending decision.

**P1 — the jobserver error envelope** (§10.5). HTTP status describes the request, the
body describes the job. A 4xx or 5xx means no job answered — malformed JSON, an invalid
payload, a record-mode mismatch, a crash — and only those become `ClientConnectionError`
and are retried. A 200 carries an answer about the job: a result, or
`{"error": {"kind": …, "message": …, "checksum": …}}`. `message` is what the exception
prints, in the form `Transformation.exception` already holds: `str(exc)` without a
traceback for the substrate classes §5 keeps, and the frame-filtered
`_format_exception` text for everything else. `kind` comes from §5's keep-list —
`cache_miss`, `hash_type_validation`, `expression_evaluation`, `conversion`,
`execution`, plus `canceled`. `checksum` is present for the kinds that name one, and is
the checksum whose buffer was missing. One module in seamless-core owns the mapping and
is shared by the jobserver, the client, the dask worker and `execution_error`.

**P2 — result HashTypes** (§10.6). There is no rule about evaluators. The local HashType
cache is write-through: a read misses to the database, and an instance uploads whatever
word it creates or tightens. The instance holding the result buffer classifies it and so
uploads it; an instance that only receives a result checksum uploads nothing. Tests
27–29 assert that invariant at three sites, not three different writers.

**P3 — the synchronous upload** (§10.6). Fire-and-forget. At the point where
`set_hash_type` actually changes the cache, and only there, it hands the pair to the
writer thread `buffer_writer` already runs. Uploads may arrive out of order with no harm:
the database applies the tightening rule per write, so correct words converge on the
tightest one whatever the order. An equal or looser write returns early and uploads
nothing; a contradiction with what the instance knows raises in the caller before
anything is queued; the caller never blocks. Test 26 flushes the writer and asserts one
`"database:set_hash_type"`.

**P4 — the looser write** (§10.6). The database applies the same three-way rule as the
local cache, importing `_hash_type_implies` from seamless-core rather than copying it:
tighter replaces, equal or looser is accepted and changes nothing, only a contradiction
is a 409, and comparison and write are one transaction. All three accepted outcomes
answer `"OK"`. Since a 409 now means a genuine contradiction, `database_client` stops
returning `False` for it and raises `ValueError`.

**P5 — §8.3 sequencing.** §8.3 lands before these tests. Until it does, tests 5 and 13
are written with their full assertions as strict xfail, the precedent §3.2 item 7 set
with `test_expression_result_never_undone.py`; a weakened version of test 13 proves
nothing test 11 does not. Test 5 also changes: §10.4 now rules that a running-loop
refusal is not an evaluation failure, so the state is `waiting` with no exception.

## 1. Shared test helper

`_install_fake_remotes` in
[test_expression_remote_evaluation.py](../seamless-core/tests/test_expression_remote_evaluation.py)
already fakes `database_remote`, `jobserver_remote` and `buffer_remote`, records an
ordered `calls` list, and supports `buffers=` and `jobserver_available=`. The §10.4
tests need the same helper, and the §10.6 tests need its `database_remote` half.

Move it, together with `_drop_buffer`, to `seamless-core/tests/helpers/fake_remotes.py`,
following the existing `tests/helpers/expression_hashtype_cases.py` precedent. Keep the
call-recording strings (`"database:get"`, `"database:set"`, `"jobserver:run"`,
`"hashserver:get"`) unchanged, because the §10.1–§10.3 tests assert on them.

Add to the helper, for §10.6:

- `hash_type_rows`, with `get_hash_type` / `set_hash_type` recording
  `"database:get_hash_type"` and `"database:set_hash_type"`;
- an optional gate (an `asyncio.Event` or `threading.Event`) on `run_expression`, so
  two evaluations can be forced to overlap (test 3).

## 2. §10.4 — Remote steps of standalone reads

New file `seamless-core/tests/test_standalone_read_remote_steps.py`.

These tests exercise the `Cell.checksum` property
([cell_class.py:105-127](../seamless-core/seamless/cell_class.py#L105-L127)), not
`Expression.compute()`. The §10.1–§10.3 tests cover the Expression entry points; §8.1's
resolution order is about the getter, and nothing tests it against a remote today.

**1. `test_database_hit_satisfies_getter`** — step 3 of §8.1.

- Standalone Cell over a bare checksum with a path; `_drop_buffer` on the input.
- Fake remotes hold the expression row; jobserver available.
- Assert `cell.checksum == result_checksum` and `calls == ["database:get"]`.
- Catches a getter that dispatches to the jobserver before consulting the database.

**2. `test_hashserver_only_input_dispatches_from_getter`** — step 6 of §8.1.

- Same setup, no database row, jobserver result present.
- Assert the getter returns the result, and
  `calls == ["database:get", "jobserver:run", "database:set"]`.
- Catches a getter that fails or returns `None` instead of waiting for the jobserver.

**3. `test_concurrent_getters_share_one_dispatch`** — "running is visible in this process".

- Two Cells with the same recipe, read from two threads, with the fake `run_expression`
  gated so the calls overlap.
- Assert exactly one `"jobserver:run"` and the same result in both threads.
- Extends `test_remote_expression_members_share_one_active_request` from `Expression` to
  the getter, which is where `_active_expressions` deduplication actually matters for a
  user.

**4. `test_jobserver_merges_duplicate_requests`** — cross-process merge.

- Two subprocesses evaluate the same slow expression against one real jobserver, using
  the `_write_remote_config` subprocess pattern from
  [test_expression_remote_schema.py](../seamless-transformer/tests/test_expression_remote_schema.py).
- Assert both return the same checksum, and that the jobserver's expression-evaluation
  counter advanced by one.
- §10.4 puts the merge in core: `evaluate_expression_async` gains the same
  `_active_expressions` deduplication that `_execute_remote_expression` has, so
  `_run_expression` ([jobserver.py:729-765](../seamless-jobserver/jobserver.py#L729-L765))
  keeps no state of its own. It only counts evaluations and reports the count, which is
  what turns this test from "both agree" into "it ran once".
- Pair it with a same-process test that two concurrent `evaluate_expression_async` calls
  for one `cache_key` produce a single evaluation — that is where the new dedup lives,
  and it needs no subprocesses.

**5. `test_remote_getter_in_running_loop_is_not_a_failure`** — §10.4's Jupyter
constraint. *(P5)*

- Inside `asyncio.run`, a standalone Cell whose input is only on the hashserver.
- Assert `cell.checksum is None`, that no dispatch happened, and — this is the part that
  changes — `cell.state == "waiting"` with `cell.exception is None`.
- Pair with a memory-local Cell read in the same loop, which must return its checksum
  (the `Expression`-level counterpart is `test_memory_local_compute_inside_running_loop`).
- The getter swallows the bridge `RuntimeError` into `_standalone_exception`
  ([cell_class.py:119-124](../seamless-core/seamless/cell_class.py#L119-L124)), so
  `.state` is `"failed"` today and `clear_exception()` is needed to recover from a
  condition that is not an error. §10.4 rules that wrong. Strict xfail until it lands.

## 3. §10.5 — Errors across the jobserver

### 3.1 Server

New file `seamless-jobserver/tests/test_run_expression_errors.py`. Call
`JobserverServer._run_expression` directly with a stub request whose `.json()` returns
the payload — the pattern the database tests use with `server._put`
([test_execution_records.py:124-152](../seamless-database/tests/test_execution_records.py#L124-L152)).

**6. `test_missing_input_returns_structured_cache_miss`** *(P1)*

- Payload naming a checksum with no buffer anywhere.
- Assert the chosen status, `kind == "cache_miss"`, and the missing checksum in the body.
- Today every failure is `web.Response(status=500, text=str(exc))`
  ([jobserver.py:761](../seamless-jobserver/jobserver.py#L761)), which is exactly what
  §10.5 requires changing.

**7. `test_invalid_expression_returns_structured_evaluation_error`** *(P1)*

- An impossible path or conversion.
- Assert a different `kind`, with the message preserved.
- Catches an implementation that reports every failure as a cache miss.

### 3.2 Client

Additions to [test_jobserver_client.py](../seamless-remote/tests/test_jobserver_client.py),
which already stubs `seamless` and fakes sessions.

**8. `test_cache_miss_response_raises_cache_miss_error`** *(P1)*

- A faked response carrying the cache-miss envelope.
- Assert `CacheMissError`, carrying the checksum — not `ClientConnectionError`
  ([jobserver_client.py:111-113](../seamless-remote/seamless_remote/jobserver_client.py#L111-L113)).

**9. `test_transport_and_malformed_bodies_stay_connection_errors`** *(P1)*

- A genuine transport failure; a 500; and a 200 whose body is not JSON or carries no
  `kind`.
- Assert `ClientConnectionError` in all three.
- Catches an over-eager mapping that turns unrelated 500s into cache misses.

**9b. `test_unknown_kind_is_an_execution_error`** *(P1)*

- A well-formed envelope whose `kind` this client does not know.
- Assert `WorkflowExecutionError` carrying the message and the unrecognized kind — not
  `ClientConnectionError`, which would retry a deterministic failure and name the wrong
  cause.
- This is the forward-compatibility half of §10.5's ruling; it is what lets a newer
  jobserver add a kind without older clients mis-reporting it.

### 3.3 Retry policy

Addition to [test_client_recovery.py](../seamless-remote/tests/test_client_recovery.py),
inside `JobserverRemoteRecoveryTests`.

**10. `test_run_expression_does_not_retry_cache_miss`** *(P1)*

- A fake client whose `run_expression` raises `CacheMissError`.
- Assert the client was called once and the type survives.
- `run_expression` retries only on `ClientRestartRequiredError`
  ([jobserver_remote.py:166-169](../seamless-remote/seamless_remote/jobserver_remote.py#L166-L169));
  §10.5 warns that a miss must not be mistaken for a connection problem. The existing
  restart test is the contrast case.

### 3.4 Routing

Addition to `test_expression_remote_evaluation.py`.

**11. `test_jobserver_cache_miss_propagates_without_fallback`** *(P1)*

- Parametrized over `execution="auto"` and `"remote"`.
- Assert `CacheMissError` carrying the **input** checksum, and
  `"hashserver:get" not in calls`.
- The typed counterpart of the existing
  `test_auto_does_not_fallback_after_jobserver_failure`, which uses a generic
  `ConnectionError`.

### 3.5 Integration

Subprocess pattern from `test_expression_remote_schema.py` and
[test_expression_execution.py](../seamless-workflow/tests/test_expression_execution.py).

**12. `test_run_resolves_jobserver_result_through_hashserver`** — §10.7 bullet 4.

- Evaluate on the jobserver, evict every process-local cache, then `.run()`.
- Assert the value comes back; then, with the hashserver emptied, assert
  `CacheMissError`.
- Confirms §8.4's rule that `.run()` materializes through `Checksum.resolve()`.

**13. `test_missing_input_through_jobserver_fails_and_recovers`** — §10.7 bullet 5.
*(P5)*

- Standalone and bound.
- Assert `.exception` is a `CacheMissError` showing the checksum with no traceback,
  `.state == "failed"` and `.checksum is None`; then upload the buffer, call
  `clear_exception()`, and assert the read succeeds.
- Standalone `clear_exception()` raises today
  ([cell_class.py:522-527](../seamless-core/seamless/cell_class.py#L522-L527)). Write the
  assertions in full as strict xfail and let §8.3 flip them; a version that drops the
  recovery half tests nothing beyond test 11.

### 3.6 Dask parity

Additions to [seamless-dask/tests/test_expression_inputs.py](../seamless-dask/tests/test_expression_inputs.py).

**14. `test_expression_task_reports_structured_cache_miss`** *(P1)*

- Patch `evaluate_expression_remote` to raise `CacheMissError`.
- Assert the third tuple element identifies kind and checksum, instead of a bare
  `traceback.format_exc()` ([client.py:825-826](../seamless-dask/seamless_dask/client.py#L825-L826)).

**15. `test_transformation_input_cache_miss_keeps_its_type`** *(P1)*

- `_run_base` passes an input error straight through
  ([client.py:961-963](../seamless-dask/seamless_dask/client.py#L961-L963)).
- Assert that a transformation whose expression input missed surfaces a cache miss
  rather than an opaque string.
- This is §10.5's "not yet discussed" review finding.

**16. `test_expression_and_transformation_errors_share_one_envelope`** — optional *(P1)*

- Assert the transformation endpoint and the expression endpoint emit the same envelope
  for the same failure.
- The reason to implement P1 as one shared helper rather than twice.

## 4. §10.6 — HashTypes in the database

Build words with `seamless.checksum.hash_type.pack`, never literals. The existing
database tests use `HASH_TYPE_WORD = 4`, which never reaches the untested levels. Use
the ladder `UNTESTED` (9) → `UTF8_UNTESTED` (10) → `JSON_UNTESTED` (11) →
`JSON_STRING` (7), holding `Length` constant.

### 4.1 Server

New file `seamless-database/tests/test_hash_type_tightening.py`, with the
`_init_db(tmp_path)` plus `server._put` / `server._get` pattern.

**17. `test_tighter_word_replaces_stored_word`** — each rung of the ladder, asserting
`"OK"` and the new stored word.

**18. `test_equal_word_is_accepted_and_changes_nothing`**.

**19. `test_looser_word_is_accepted_and_keeps_stored_word`** *(P4)* — the behaviour
change from today's blanket 409. Assert `"OK"` and that the tighter word survives.

**20. `test_contradictory_word_conflicts_and_keeps_stored_word`** — sibling Kinds, a
differing `Length`, and a differing `NUMERIC_SCALAR`, each in both orders. Assert a 409
([database.py:799-801](../seamless-database/database.py#L799-L801)), the stored word
unchanged, and that the conflict is logged.

**21. `test_server_and_local_cache_agree`** — one parametrized table of word pairs, run
against both `server._put` and `set_hash_type`, asserting the same
accept / keep / conflict outcome. `_hash_type_implies`
([hash_type.py:308-323](../seamless-core/seamless/checksum/hash_type.py#L308-L323)) is
the single rule; the server already imports core for `_valid_hash_type_word`
([database.py:58-65](../seamless-database/database.py#L58-L65)), so it should import the
implication rule too rather than growing a second copy. This test is what stops the two
from drifting.

### 4.2 Client

Additions to `seamless-remote/tests/`, alongside
[test_database_client_execution_records.py](../seamless-remote/tests/test_database_client_execution_records.py).

**22. `test_hash_type_conflict_raises_value_error`** *(P4)* — a 409 surfaces as
`ValueError`, matching local `set_hash_type`, rather than `ClientConnectionError` or the
silent `False` returned today
([database_client.py:486-491](../seamless-remote/seamless_remote/database_client.py#L486-L491)).
Under P4 a 409 is no longer routine, so swallowing it would hide a bug or a rules change.

**23. `test_looser_hash_type_write_reports_success`** *(P4)*.

### 4.3 Uploading a changed local word

Additions to [test_hash_type_remote_cache.py](../seamless-core/tests/test_hash_type_remote_cache.py).

**24. `test_tightening_uploads_new_word`** — tighten an existing local word; assert the
fake rows hold it.

**25. `test_equal_or_looser_write_uploads_nothing`** — no redundant traffic; assert no
`"database:set_hash_type"` call.

**26. `test_sync_tightening_uploads`** *(P3)* — a synchronous `set_hash_type` that
tightens, then a writer flush; assert exactly one `"database:set_hash_type"` with the new
word, and that the call did not block or raise. Add the negative: an equal or looser
synchronous write queues nothing. Today only `register_hash_type_for_buffer_async`
reaches the database.

### 4.4 Result HashTypes

These three are one invariant at three sites (P2): the instance that classifies a buffer
uploads the word. Nothing here is specific to results, or to expressions.

**27. `test_local_evaluation_stores_result_hash_type`** *(P2)* — in
`test_expression_remote_evaluation.py`. After `evaluate_expression_remote`, assert the
fake rows hold `HashType.from_buffer(result_buffer).word` for the **result** checksum.
Only the input gets one today (`ensure_hash_type_async`).

**28. `test_jobserver_evaluation_stores_result_hash_type`** *(P2)* — real servers; read
the word back from the database for the result checksum. §10.7 bullet 2. The jobserver is
the instance holding the result buffer, so it is the one that classifies and uploads.

**29. `test_dask_worker_stores_result_hash_type`** *(P2)* — optional parity.

### 4.5 Synchronous lookup and retrieval validation

Additions to [test_hash_type_validation.py](../seamless-core/tests/test_hash_type_validation.py).

**30. `test_ensure_hash_type_consults_database`** — no local entry, no buffer, database
holds the word. Assert it is returned. Today `ensure_hash_type` returns `None`
([hash_type_validation.py:50-64](../seamless-core/seamless/checksum/hash_type_validation.py#L50-L64)),
silently skipping validation.

**31. `test_ensure_hash_type_in_running_loop_does_not_block`** — the same call inside
`asyncio.run`. Assert it never blocks and returns `None` rather than raising: per §10.4 a
running-loop refusal is not a failure, so validation is skipped, not failed.

**32. `test_validation_with_database_only_hash_type`** — §10.7 bullet 3. No local cache
entry, no buffer: a proven negative (`UTF8_UNTESTED` with `binary`) raises
`HashTypeValidationError`, and an allowed celltype passes.

**33. `test_database_word_enters_cache_and_then_conflicts`** — a word loaded by
`get_hash_type_remote` enters the local cache
([hash_type.py:348](../seamless-core/seamless/checksum/hash_type.py#L348)); a later
contradictory local write raises and keeps it.

## 5. Coverage of §10.7's moved tests

| §10.7 bullet | Tests |
|---|---|
| Tightening in the database; a tightened local word is uploaded | 17–26 |
| Result HashType stored, locally and on the jobserver | 27–28 |
| Validation from a HashType only the database knows | 30, 32 |
| `Expression.run()` of a jobserver result resolves through the hashserver | 12 |
| Missing input through the jobserver, with `clear_exception()` recovery | 13 (needs §8.3) |

## 6. Test hygiene

- seamless-core test files each run in their own pytest process; combining them in one
  run produces spurious failures.
- The database tests need a fresh `hash_type` table per case (`_init_db(tmp_path)`).
  Under §3.2 item 5 a wrong stored word can no longer be repaired by writing a correct
  one, so a leaked row poisons later cases.
- Any change to the classification rules requires clearing the `hash_type` table in
  development databases, exactly as phase 3 did for the `expression` table.

## 7. Verification commands

Run in the `seamless1` conda environment, one file per process:

```bash
cd /home/agent/seamless1/seamless-core
conda run -n seamless1 pytest -q tests/test_standalone_read_remote_steps.py
conda run -n seamless1 pytest -q tests/test_expression_remote_evaluation.py
conda run -n seamless1 pytest -q tests/test_hash_type_remote_cache.py
conda run -n seamless1 pytest -q tests/test_hash_type_validation.py
```

```bash
cd /home/agent/seamless1/seamless-database
conda run -n seamless1 pytest -q tests/test_hash_type_tightening.py
```

```bash
cd /home/agent/seamless1/seamless-jobserver
conda run -n seamless1 pytest -q tests/test_run_expression_errors.py
```

```bash
cd /home/agent/seamless1/seamless-remote
conda run -n seamless1 pytest -q tests/test_jobserver_client.py tests/test_client_recovery.py
```

```bash
cd /home/agent/seamless1/seamless-transformer
conda run -n seamless1 pytest -q tests/test_expression_remote_schema.py
```

```bash
cd /home/agent/seamless1/seamless-dask
conda run -n seamless1 pytest -q tests/test_expression_inputs.py
```
