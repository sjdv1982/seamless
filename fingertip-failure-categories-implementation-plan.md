# Result-record integrity and fingertip failure categories — implementation plan

**Goal.** Two linked changes.

1. **A recorded transformation result is never replaced.** Today, a recomputation that gives a different result overwrites the recorded one, both in the process-local forward cache and in seamless-database. After this plan, the recorded result stays in place, and the divergence is stored as an *automatic* irreproducible observation.
2. **A failed fingertip reports a failure category.** It still raises `CacheMissError(checksum)`, but the exception now carries the highest **failure category** that the search ran into, so that a forensic investigation knows where to look.

**Status.** These are author rulings from 2026-10-01 (see *Author rulings* below), and none of them is implemented yet. The contract pages still describe the old behaviour: a bare `CacheMissError`, with nothing recorded. Step 9 lists the changes to those pages and comes last, because the contract is under discussion separately.

**Tests.** Use the `seamless1` conda env and one pytest process per file (`tests/run-tests.sh` in each repo). Transformer tests that need a database use a `persistent: true` stage, as `seamless-transformer/tests/test_fingertip.py` does (stage `fingertip`).

## The bug

This was found by reading the code. The regression test in Step 7 reproduces it.

- **The fingertip never sees the recorded result.** `Checksum.fingertip` (`seamless-core/seamless/checksum_class.py`) recomputes a candidate with `recompute_from_transformation_checksum(..., scratch=True)`, which calls `TransformationCache.run(force_local=True, store_execution_record=False)`. `force_local` skips the database lookup, so the process never learns that T → R is recorded.
- **Both caches are overwritten.**
  - `_run_uncached` (`seamless-transformer/seamless_transformer/transformation_cache.py:867-870`) writes `set_transformation_result(T, R′)` unconditionally, unless it runs inside a worker.
  - `_register_transformation_result` (`:201-212`) overwrites the local entry.
- **The database row is overwritten.** In seamless-database, `Transformation.create` upserts on the primary key (`database_models.py:36-48`). Unlike `Expression`, `Transformation` is not on the exclusion list (`:198-205`). So T → R becomes T → R′. The reverse row R → T stays, now pointing at a transformation whose forward row says R′, and the execution record still says R.
- **The bug is not specific to fingertips.** With `require_value=True`, `TransformationCache.run` discards a database hit whose buffer is unreachable without registering it (`:273-283`). It then executes and reaches the same write.
- **Duplicate reverse rows.** The transformation PUT adds a duplicate reverse row on every identical write. `database.py:727-728` uses `RevTransformation.create`, and that table has no uniqueness constraint.

## Failure categories

| Rank | Category | Wire name | A candidate gets this category when |
|---|---|---|---|
| 1 | materialization | `materialization` | there is no candidate at all; or the candidate's definition or inputs cannot be obtained (a nested fingertip failed without a higher category); or its result matches but the buffer still cannot be resolved |
| 2 | failed transformation | `failed_transformation` | a transformation candidate raised while executing |
| 3 | irreproducible transformation | `irreproducible_transformation` | a transformation candidate executed and gave a result other than the wanted checksum |
| 4 | irreproducible expression | `irreproducible_expression` | an Expression candidate gave a different result, **or raised**. Every candidate has a recorded result, so it succeeded once |

The fingertip reports the **maximum over all candidates**, including the categories carried up by nested fingertips. The maximum does not depend on the order in which candidates are tried.

**These are not categories:**

- **Cancellation** (`asyncio.CancelledError`, `ExecutionCanceledError`).
- **Infrastructure errors** (`ClientConnectionError`, `ClientPayloadError`, timeouts).

Both propagate as themselves, because neither says anything about whether the checksum can be recovered.

## Step 1 — seamless-database

Changes in `database.py`, `_put`:

- **`type: transformation`.** Run the whole branch inside `db_atomic()`:

  | Stored row for T | Action |
  |---|---|
  | same result | ensure the reverse row with `_ensure_rev_transformation_row`; answer OK |
  | different result | answer `_conflict_response("Transformation already exists with different result")`; keep the stored row |
  | none | create the forward row, and the reverse row with `_ensure_rev_transformation_row` |

  A quarantined T has irreproducible rows and no forward row. Whether it may get a new forward row is open (see *Open*), so keep today's answer: allowed.
- **`type: irreproducible`, new optional field `mode`.**
  - Absent or `"manual"`: today's behaviour, unchanged.
  - `"automatic"`: the forward row must be present and hold a result other than the reported one. Otherwise answer 404 (no forward row) or 409 (the reported result is the recorded one).
    - Add `IrreproducibleTransformation(checksum=T, result=R′, metadata="")`, unless a row for (T, R′) already exists.
    - Leave the forward, reverse and metadata rows untouched.
    - Store no execution record (ruling 3).
- **Check the metadata refusal at `:763-766`.** It refuses a record once *any* irreproducible row exists for T, and with automatic rows a live T has such rows. Under Step 3 no runtime path should write a record for a T whose stored forward row has the same result (SAME writes nothing). Verify that this holds. If some path does reach the refusal, narrow it to "irreproducible rows and no forward row", and raise it with the author, because it touches *Open*.

Tests, in `seamless-database/tests/test_execution_records.py`:

- An identical transformation PUT is idempotent and leaves exactly one reverse row.
- A conflicting PUT answers 409 and keeps both the forward row and the reverse row.
- An automatic report:
  - adds a row, keeps the forward, reverse and metadata rows, and skips duplicates;
  - answers 404 without a forward row, and 409 for the recorded result.
- `test_put_irreproducible_moves_metadata_and_deletes_normal_rows` passes unchanged (manual mode).

## Step 2 — seamless-remote

Changes in `database_client.py` and `database_remote.py`:

- **`set_transformation_result`.** A 409 with `"Transformation already exists with different result"` raises a new `TransformationResultConflict`. It must not subclass `ClientConnectionError`, so that `_retry_operation` neither retries nor restarts the client. Other 4xx/5xx answers are unchanged.
- **New `report_irreproducible_result(tf_checksum, result_checksum)`.** It sends `PUT irreproducible` with `mode: automatic`. A 404 or 409 returns `False`, and the caller logs it; other errors behave as usual. Add a `database_remote` wrapper over the write clients.
- **New `database_remote.has_read_database()`.** It returns `False` when no read client is configured, or when the process is a worker child without remote clients (where `_ensure_not_child` would raise). Step 5 uses it to tell "no database here" from "the database failed".
- **`undo_transformation_result` stays** as the manual mode.
- `set_expression_result` already returns `False` on its own 409 (`contracts/expressions.md`, *Identity*). Nothing changes there.

Tests, in `seamless-remote/tests/test_database_client_execution_records.py`:

- A conflict raises the new exception after exactly one PUT, with no client restart.
- The automatic report works end to end.

## Step 3 — one write path for transformation results (seamless-transformer)

### `transformation_cache.py`

- **`_register_transformation_result` becomes insert-if-absent.**
  - Same result: no-op.
  - Different result: leave the entry and report the outcome to the caller (no exception).
  - The local reverse entry is added only on insert.
- **New `async _record_transformation_result(...)`.** It returns NEW, SAME or MISMATCH, and it is the only place that compares and writes.
  - **NEW** (no local entry):
    - Insert the entry. Then, outside workers, write `set_transformation_result` and the execution record exactly as today (`:867` onwards).
    - On `TransformationResultConflict`: get the stored result R_db, insert T → R_db locally (a learned mapping), and continue as MISMATCH against R_db.
  - **SAME:** write nothing, including no execution record.
  - **MISMATCH:**
    - Insert and write nothing.
    - Call `report_irreproducible_result(T, R′)`, and log a warning naming T, the recorded result and R′.
    - A worker child without remote clients forwards the report to its parent instead. Add a parent handler `report_irreproducible` next to `download`, `upload` and `ref_op` (`worker.py:830-833`); the parent calls `database_remote`.
  - **Order:** the comparison runs before the `not is_worker()` check. Only the database calls are skipped inside workers.
  - **Return value:** unchanged. The caller still gets R′: a plain `run()` returns R′ unrecorded (ruling 4), and the fingertip discards it.
- **Replace the write and the registration.** The write at `:867-870` and the local registration at `:982` both go through `_record_transformation_result`.
- **Learn every forward mapping.** In `run` (`:273-283`), register T → R from the database before discarding the hit for its unreachable buffer.
  - Only `require_value=False` callers use such an entry as a cache hit, and they would get the same answer from the database.
  - The only `force_local=True` callers are the two fingertip recomputes (`:1205`, `:1231`), and both pass `require_value=True`.
- **Lookups don't overwrite.** The lookups at `:266`, `:296` and `:1016` use insert-if-absent. A database hit that disagrees with the local entry is returned to the caller, because it is the reachable one. It is not inserted, and the disagreement is logged.
- **The recomputes stop swallowing errors.** In `recompute_from_transformation_checksum` and its sync twin (`:1183-1232`), narrow `except Exception: return None` to `CacheMissError`, which means the definition is unavailable. Other errors propagate.

### seamless-dask

- `client.py`, `_promise_and_write_result_async` (`:675`): call the shared function instead of `set_transformation_result`.
- `client.py`, `_fetch_cached_result_async` (`:510-532`): register the database hit locally even when its buffer is unreachable.
- `transformation_mixin.py:392` and `:551`: `register_transformation_result` follows insert-if-absent. Both calls already swallow exceptions.

## Step 4 — expressions never overwrite either (seamless-core)

Changes in `seamless/checksum/expression.py`:

- **Every write to `_expression_cache` becomes insert-if-absent:** `:461`, `:540`, `:547`, `:625` and `:836`.
- **A different result for a known key:**
  - It is not inserted.
  - It is not written to the database: no `register_expression_result` is queued.
  - It is logged at error level, with the identity tuple and both results.
- **The evaluation returns its own result, unrecorded,** as for transformations.
- **Log the background 409.** The 409 from the background writer (`seamless/caching/buffer_writer.py`) can still happen in a race. Log it at error level instead of dropping it silently.

## Step 5 — the fingertip reports a category (seamless-core)

### The exception

- In `seamless/__init__.py`, add `class FingertipCategory(IntEnum)` with the four members (values 1–4) and their wire names.
- `CacheMissError.__init__(self, *args, fingertip_category=None)` stores the category as an attribute. `args[0]` stays the checksum (contract).
- Pickling and `execution_error()` keep instance attributes, so no `__reduce__` is needed. Pin this with a test.

### The envelope

- In `seamless/error_envelope.py`, `encode_error` adds `"fingertip_category": <wire name>` to a `cache_miss` envelope when the category is set.
- `decode_error` validates and restores it. An unknown value makes the envelope malformed.
- Every process boundary already uses this codec: the jobserver (`seamless-jobserver/jobserver.py`), Dask (`seamless-dask/seamless_dask/client.py`) and the worker channel (`worker.py:708`, `:2030`).

### `Checksum.fingertip` (`checksum_class.py:308-445`)

- **Database candidate discovery** runs only if `has_read_database()` is true. Its errors propagate; today `:331`, `:338`, `:365` and `:372` swallow them.
- **Register candidates from the database reverse index** in the local forward caches (insert-if-absent) before trying them. This is what lets the comparisons in Steps 3 and 4 see the recorded result.
- **Classify each candidate** as in the table:
  - **Expression candidates:** keep the category of the input fingertip; today `:401-403` drops it.
  - **Transformation candidates:**

    | Outcome | Category |
    |---|---|
    | recompute returns `None` | materialization |
    | `CacheMissError` | its own category, or materialization if it has none |
    | any other exception | failed transformation |
    | result differs from the wanted checksum | irreproducible transformation |
- **Re-raise cancellation and infrastructure errors from every handler.** `ExecutionCanceledError` is a `RuntimeError`, so `except Exception` currently swallows it.
- **End with `raise CacheMissError(self, fingertip_category=<maximum>)`.**

### The nested path through a transformation

An input fingertip inside a candidate's execution (`transformation_namespace.py:214-226`, `fingertip_sync`) must reach the outer fingertip as a `CacheMissError` that still carries its category. Check the in-process execution path for exception flattening: a formatted traceback or a `RuntimeError` would turn it into "failed transformation". Fix it wherever it happens.

## Step 6 — seamless-share

`seamless_share/why_not/lookup.py:10-35` checks the irreproducible rows before the forward row, so with automatic rows it would label a live entry `IRREPRODUCIBLE`.

- Check the forward row first, and report `IRREPRODUCIBLE` only when there is none.
- A forward row together with irreproducible rows means automatic observations (ruling 3). The forward state wins, and the row count goes into `details`.
- Add a test in `seamless-share/tests`.

## Step 7 — runtime tests

In `seamless-transformer/tests/test_fingertip.py` (stage `fingertip`, persistent), one test function each:

1. **Regression.** Use a nondeterministic scratch transformer (for example, one that returns bytes from `os.urandom`), purge its result and fingertip it. Expect a `CacheMissError` with `irreproducible_transformation`. Afterwards:
   - the database forward row is still T → R, and the reverse row R → T is still there;
   - there is exactly one automatic row (T, R′);
   - the local cache still holds T → R.
2. **Plain re-run with the result buffer gone.** It returns R′, the forward row is unchanged, and an automatic row is added.
3. **Reproducible re-run.** It writes nothing: no second PUT and no execution-record conflict.
4. **`failed_transformation`.** Use a candidate that raises on recompute, for example one that reads an environment variable set only for the first run.
5. **`materialization`.** Cover both a checksum with no candidate, and a candidate whose input is gone and has no producer.
6. **Ranking.** Give one checksum two candidates (two transformer codes with the same output), one failing and one irreproducible. Expect `irreproducible_transformation`.
7. **Nesting.** Put the irreproducible transformation under an input fingertip of the outer candidate. The outer fingertip reports `irreproducible_transformation`.
8. **Propagation.** Cancellation propagates, and so does a `ClientConnectionError` from the reverse-index query (monkeypatched).

Elsewhere:

- **Envelope round trip,** with and without the category, in `seamless-core/tests`.
- **Expression mismatch.** This is hard to provoke for real. Monkeypatch a wrong recorded result into the Expression cache in `seamless-core/tests/test_expression_fingertip.py`. Assert `irreproducible_expression`, no overwrite and no database write.
- **Worker-child report forwarding** (Step 3), in `seamless-transformer/tests/test_nested_scratch_in_worker.py` (spawn stage).

## Step 8 — check the full suites

Run every touched repo's suite one file at a time: seamless-database, seamless-remote, seamless-core, seamless-transformer (including `dask/` and `persistent/`), seamless-dask and seamless-share.

## Step 9 — contract pages (last)

Coordinate this step with the ongoing contract discussion. It covers every place where the pages describe the old behaviour.

### `contracts/expressions.md`

- ***What a failed fingertip reports: the cache miss, and nothing else.*** Retitle the section and rewrite it around the new rule:
  - **The rule:** a failed fingertip raises `CacheMissError(checksum)` with `fingertip_category`.
  - **The categories:** the four of them and their ranking; why a maximum over a fixed ranking does not depend on trial order; and that a category is never a candidate's exception class.
  - **Not categories:** cancellation and infrastructure errors propagate.
  - **The three reasons:**
    - Rewrite the first: trial order now argues for a maximum over the ranking, not for silence.
    - Keep the second.
    - Replace the third with the envelope field.
  - **The investigation route:** the database (forward, reverse and irreproducible rows) plus the hashserver index. The forensic process does its own runs.
  - **The two consequences:**
    - "A mismatched environment is silent, by design" becomes: reported as an irreproducible transformation, plus an automatic row.
    - "Not sticky" stays. The automatic row is evidence, not a block: T stays in fingertip chains.
- ***Errors.*** The envelope gets an optional `fingertip_category` field on `cache_miss`.
- ***Identity***, the bullet "What the client does on that conflict":
  - The process cache is never overwritten.
  - A different result is returned unrecorded and logged.
  - The process cache and the database no longer disagree by this route.
- ***Current limitations***, "Irreproducible Expressions normally do not exist": keep the explanation of library drift. Replace "the client does not surface" with the logging and the category.

### `contracts/scratch-witness-audit.md`

- **The *Recording identity* row** of the evaluate / record / publish table: recording is insert-only. A different result is never recorded; it is reported as irreproducible.
- ***When the walk comes back empty it says only that*:** rewrite it for the categories.
- ***Fingertipping is where accidental nondeterminism surfaces*:** the divergence is now stored as an automatic irreproducible row.

### `contracts/execution-records.md`

- **Purpose 2 (line 12) and the conflict bullets (lines 20–26):** describe the automatic and manual modes. The forward row stays in place for automatic rows.
- **Database interface (lines 111–113):** the two `PUT irreproducible` modes, the transformation PUT refusing a different result, and the metadata refusal as settled in Step 1.
- **Client API (line 123):** add `report_irreproducible_result`.

### `contracts/identity-and-caching.md`

- **Line 93:** what `IrreproducibleTransformation` records, in both modes. Readers tell the modes apart by the forward row: present means an automatic observation, absent means quarantined (ruling 3).

## Author rulings (2026-10-01)

1. **The overwrite is a bug.** There are two guards against it:
   - The local forward cache learns every mapping and is never overwritten. The database is written only when a new local entry is created, and a different result is reported as irreproducible.
   - The database refuses to replace a transformation row.
2. **Irreproducible has two modes.**
   - **Automatic** (on any mismatch) adds (T, R′) and keeps the forward and reverse rows, for forensics.
   - **Manual** is today's `undo_transformation_result`: it moves T → R into the irreproducible table and removes T from future fingertip chains.
3. **No extra fields on automatic rows.**
   - They carry no execution record: the forensic process does its own runs.
   - There is no `kind` column: forward and reverse rows still present means automatic.
4. **Every mismatch site uses the automatic mode,** not only fingertips. A plain `run()` returns R′ unrecorded. A client whose environment diverges pays for T on every attempt; manual mode is the remedy.
5. **The fingertip reports the highest of the four categories.** Cancellation and infrastructure errors are not categories. An Expression that raises while it has a recorded result counts as an irreproducible Expression.
6. **Expressions get no irreproducible table;** a mismatch is logged loudly.

## Choices made in this plan (not author rulings)

- **Names:** `FingertipCategory`, `fingertip_category`, `TransformationResultConflict`, `report_irreproducible_result`, `has_read_database`, and `mode: automatic | manual`.
- **After a 409,** the client fetches the stored result with a GET instead of parsing the response text.
- **A worker child forwards its automatic report** to the parent rather than dropping it.
- **An Expression mismatch returns the new result unrecorded,** as for transformations, rather than raising.

## Open (not in this plan)

- **Re-recording after quarantine.** In manual mode, may a quarantined T get a new forward row? Today the transformation PUT allows it, but the metadata PUT refuses that row's execution record.
- **Repairing databases that were already overwritten.** Such databases contain reverse rows whose forward row holds a different result. A fingertip through one of them now reports `irreproducible_transformation`, and its automatic report is refused with 409. To list them:

  ```sql
  SELECT r.checksum, r.result, t.result
  FROM rev_transformation r JOIN transformation t ON r.checksum = t.checksum
  WHERE r.result != t.result;
  ```
- **Fingertips in worker children without a database.** Such a fingertip cannot query the database, so it can report `materialization` where its parent would have found candidates. This predates the plan; discovering candidates through the parent would fix it.
