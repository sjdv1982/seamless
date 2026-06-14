# Cells, Expressions, And HashType: Handoff-Ready Implementation Plan

## Scope

Implement the structural layer described in `seamless/cells-and-expressions-implementation-plan.md` and the checksum classification design described in `seamless-core/type_bits_design.md`.

Important naming rule: the design document says `TypeBits`; code, tests, database payloads, and user-facing implementation notes must call the concept `HashType`.

The end state is:

- `Expression` is an immutable structural node keyed by `(input_checksum, path, celltype, target_celltype)`.
- `Cell` is the mutable builder whose navigation accumulates a path and whose build/call snapshots an `Expression`.
- Expressions evaluate locally and remotely, cache by their composite identity, and write reverse provenance.
- Transformations accept expression futures as inputs, including local, jobserver, and Dask paths.
- `HashType` is computed for checksums, cached locally and remotely, and used to reject impossible deserialization, expression paths, conversions, and transformation inputs early.
- Validators are left as explicit TODO code paths: they are orthogonal reject-only gates, excluded from expression identity, and must not coerce values.

## Repositories And Current Anchors

The work spans these repositories:

- `seamless-core`: `seamless/expression_class.py`, `seamless/cell_class.py`, `seamless/buffer_class.py`, `seamless/checksum/*`, local caches, expression evaluation, HashType calculation/validation.
- `seamless-transformer`: `seamless_transformer/transformation_class.py`, `transformer_class.py`, `transformation_cache.py`, transformation input construction and dependency resolution.
- `seamless-database`: `database_models.py`, `database.py`, schema/API support for expressions and checksum-to-HashType rows.
- `seamless-remote`: `seamless_remote/database_client.py`, `database_remote.py`, `jobserver_client.py`, `jobserver_remote.py`, remote expression/cache/HashType clients.
- `seamless-jobserver`: `jobserver.py`, new expression-evaluation endpoint modeled on transformation endpoints.
- `seamless-dask`: `seamless_dask/types.py`, `client.py`, `transformation_mixin.py`, expression futures and transformation inputs with `kind="expression"`.
- Possibly `hashserver`: only if the final "evaluate at data" path needs hashserver-side expression evaluation instead of jobserver/database-side evaluation.

Branch note: `seamless-core`, `seamless-remote`, `seamless-database`, and `seamless-jobserver` are already on `cells-and-expressions`. Before editing any additional repo, check its current branch and run `git checkout -b cells-and-expressions` only if the branch does not already exist there.

Current code observations:

- `seamless-core/seamless/expression_class.py` and `cell_class.py` already contain skeleton immutable/builder classes.
- `Expression.compute()`, `run()`, and `cancel()` are stubs.
- `seamless-database` already has an `Expression` model and `expression` / `rev_expression` GET/PUT stubs.
- Expressions are not currently stored in `seamless.db`, so there is no stored expression compatibility burden. Choose the final canonical expression path representation now, then make the core class, database model, and remote payloads use it consistently.
- Existing `BufferInfo` code lives in `seamless-core/seamless/checksum/buffer_info.py`, but it is not currently used in a meaningful way. Treat it as replaceable scaffolding: new implementation work should use `HashType` directly rather than preserving `BufferInfo` behavior.
- Existing Buffer-to-value deserialization is in `seamless-core/seamless/checksum/parse_buffer.py`; HashType validation must be added here when the Buffer checksum is known.

## Non-Negotiable Contracts

- Expression identity is the composite key `(input_checksum, path, celltype, target_celltype)`, not a derived expression checksum.
- `validator` and `validator_language` are excluded from expression identity. A validator may reject only; it must not change the successful value. Implement validator hooks as TODOs for now.
- An expression over an unresolved expression/transformation input is constructed before it is keyed; forming the database key waits for the upstream result checksum.
- Expressions have no execution envelope and no spawn-worker path. Placement follows data availability.
- Empty-path expressions are celltype conversions and use the same expression cache as non-empty paths.
- Deep checksum navigation with a non-empty path should choose sub-checksums from the manifest without materializing the parent buffer.
- Successful expression cache writes are idempotent. A different result for the same expression key is corruption, not irreproducibility.
- `HashType` is total: either absent for a checksum, or a complete 13-bit word with all fields definite.
- `HashType` queries must provide:
  - `deserializable_as(checksum, celltype) -> bool`
  - `convertible_to(checksum, source, target, preserving=True|False) -> True | -1 | None | False`
  - expression capability checks relative to `(HashType, source_celltype)`.
- Mandatory HashType validation must run when:
  - an Expression is evaluated;
  - a Checksum is assigned to a Transformation input;
  - a Transformation or Expression handle assigned to a Transformation input resolves to a Checksum;
  - a Buffer is deserialized to a value, assuming the Buffer's checksum is known.


## Phase 0: Test Helper And HashType Witness Corpus

Goal: create the fixture/helper that drives every later phase.

Implementation:

- Add a helper module in `seamless-core/tests/` or `seamless-core/tests/helpers/`, for example `expression_hashtype_cases.py`.
- Generate witnesses for all valid `HashType` words described by the design. Expect roughly 70 reachable words after multiplying the 26 structural classes by reachable `Length` buckets.
- For each witness, store:
  - the raw buffer;
  - the value, if needed to build the buffer;
  - the source checksum;
  - the expected packed `HashType` integer;
  - the most-informative celltype (MIC);
  - 1 to 4 evaluatable expressions whose source checksum has that HashType;
  - 2 unevaluatable expressions.
- Vary expression components deliberately:
  - source celltype is MIC vs non-MIC;
  - empty path vs item path vs slice path;
  - string/attribute access vs integer access;
  - target celltype equal to source vs conversion target;
  - plain/mixed/binary structural sources vs flat text/bytes sources.
- Include deep-celltype cases separately. Deepness is a declared celltype fact, not a HashType bit, so the helper should mark deep cases as source-celltype variants over JSON-object/array buffers.
- Keep invalid expressions meaningful:
  - incompatible source celltype;
  - impossible path capability, such as map access on a list or sequence access on a scalar;
  - impossible target conversion;
  - path disallowed for a non-structural source where applicable.

Smoke tests:

- All valid and invalid helper expressions can be constructed and normalized.
- The chosen path representation round-trips through core and database serialization.
- Expected HashType integers are unique where they should be and pass a `HashType.is_valid_word()` well-formedness check.

Acceptance:

- A single parametrized test can iterate all helper cases and report the witness name, HashType integer, source celltype, target celltype, and path on failure.

## Phase 1: Local Expression Evaluation In `seamless-core`

Goal: evaluate expressions over concrete input checksums locally.

Implementation:

- Complete `Expression.compute()` and async counterpart if needed. If no async API exists yet, add one deliberately instead of blocking inside remote paths later.
- Complete `Expression.run()` as `compute()` followed by checksum resolution and `Buffer.deserialize(target_celltype)`.
- Implement a local evaluator module, for example `seamless/checksum/expression.py`, that accepts `(input_checksum, path, celltype, target_celltype)` and returns a result checksum or a typed failure.
- Evaluation order:
  - resolve expression input to a concrete checksum;
  - check local expression cache;
  - validate source HashType and expression path capability where HashType exists;
  - for empty path, perform conversion;
  - for deep checksum plus non-empty path, navigate the manifest and return the sub-checksum without materializing the parent;
  - otherwise materialize the input as `celltype`, apply the path, serialize as `target_celltype`, compute result checksum, and register the result buffer.
- Keep validator hooks as explicit TODOs. Suggested code shape:
  - `# TODO validators: reject-only gate, excluded from expression identity.`
  - raise `NotImplementedError` only if a validator is actually present; do not block validator-free expressions.

Tests:

- Parametrize over the Phase 0 helper.
- All valid expressions evaluate to the expected checksum/value.
- All invalid expressions fail with deterministic exception classes and useful messages.
- Empty-path conversion expressions behave like the old conversion helpers but write/read through expression cache.
- Deep navigation tests assert parent buffer materialization is not called.
- Expression identity ignores validator fields; two expressions differing only by validator share the same database/cache key.

Acceptance:

- The helper's valid expressions evaluate locally.
- The helper's invalid expressions fail locally without accidental buffer pulls for cases HashType can reject.

## Phase 2: Cell-Built Expression Variant

Goal: prove `Cell` is a functional builder, not a resolving object.

Implementation:

- Keep navigation (`cell.foo`, `cell["foo"]`, `cell[0]`, `cell[:]`) returning `Cell`.
- Ensure `Cell.build()` / `Cell.expression()` snapshots:
  - concrete checksums as checksums;
  - expression/transformation inputs as immutable future edges;
  - mutable plain Python input containers by value where current code already does this.
- Decide whether `Cell.__call__` returns an `Expression` or runs it. The existing code returns `Expression`; the design says `cell()` / `cell.run()` may resolve. Choose the existing code and make tests/docs match it. A conservative public API choice is:
  - `cell.build()` and `cell.expression()` return `Expression`;
  - `cell.compute()` returns result checksum; (syntactic sugar over `cell.build().compute()`)
  - `cell.run()` returns value (syntactic sugar over `cell.build().run()`);
  - leave `cell()` returning `Expression` if changing it would break current tests, but document the choice.

Tests:

- Rebuild the Phase 0 expressions from Cells instead of constructing `Expression` directly.
- Mutating a Cell after `build()` does not affect the built Expression.
- A single Cell can build multiple independent Expressions after reassignment.
- Navigation of a derived Cell does not mutate the parent Cell.

Acceptance:

- The direct-expression and Cell-built helper variants have identical valid results and invalid failures.

## Phase 3: Remote Expression Cache In `seamless-remote` And `seamless-database`

Goal: expressions cache remotely like transformations, including reverse provenance.

Implementation:

- Extend `seamless-remote` database client/remote modules with:
  - `get_expression_result(input_checksum, path, celltype, target_celltype)`
  - `set_expression_result(input_checksum, path, celltype, target_celltype, result_checksum)`
  - `get_rev_expressions(result_checksum)`
- Normalize the expression path payload exactly once at the API boundary.
- In `seamless-database`, define the final `Expression` model/API without preserving old expression rows:
  - keep composite primary key `(input_checksum, path, celltype, target_celltype)`;
  - keep `result` indexed;
  - persist `validator` fields only if needed for audit, never in the primary key;
  - ensure PUT updates are idempotent and reject conflicting results for the same key unless the corruption policy says overwrite.
- Because expression rows are not already present in `seamless.db`, path storage can change freely. Prefer one canonical path encoding in the database instead of adding compatibility readers.

Tests:

- First process:
  - load helper expressions;
  - monkey-patch local evaluator/cache lookup points to log `cache_hit` vs `de_novo`;
  - valid expressions take the de novo path and write remote cache rows;
  - invalid expressions take the de novo path and do not write successful expression rows.
- Second process:
  - repeat the same operation against the same database;
  - valid expressions take the remote cached path;
  - invalid expressions still take the de novo path and fail again.
- Reverse lookup returns the producing expression key for each cached result.

Acceptance:

- Remote expression cache behavior mirrors transformation cache behavior for hits, misses, and reverse provenance.

## Phase 4: Transformation Inputs Accept Expression Handles

Goal: transformation pins accept expression futures symmetrically with transformation futures.

Implementation:

- In `seamless-transformer`, allow pin values to be:
  - concrete checksum;
  - transformation future;
  - expression future.
- Track expression dependencies separately or generalize `_upstream_dependencies` to dependency objects with `kind`.
- When constructing a transformation:
  - do not snapshot an unresolved expression as `None`;
  - resolve expression dependencies before hashing the transformation payload if the payload needs concrete input checksums;
  - preserve enough future structure for Dask submission.
- Extend error propagation so expression dependency failures appear as dependency failures on the transformation.
- Extend cancellation so cancelling a transformation recursively cancels expression dependencies, and expression cancellation recursively cancels upstream dependencies.

Dask-specific implementation:

- Extend `seamless-dask/seamless_dask/types.py`:
  - `TransformationInputSpec.kind` becomes `"checksum" | "transformation" | "expression"`.
- Extend `TransformationDaskMixin._build_dask_submission()` to recognize expression dependencies.
- Add client methods to create expression futures and to convert expression futures into fat/thin checksum futures as needed.
- Ensure `allow_input_fingertip` works when the expression result is missing but reverse expression provenance can recover it.

Tests:

- Local transformation consumes expression result.
- Transformation consumes expression over transformation result.
- Expression consumes transformation result and then feeds another transformation.
- Dependency failure from invalid expression blocks the transformation with a clear message.
- Dask tests:
  - expression dependency submitted once and shared by multiple downstream transformations;
  - cache hit path avoids duplicate expression work;
  - cancellation releases expression futures;
  - `allow_input_fingertip` can recover expression-produced inputs.

Acceptance:

- Mixed expression/transformation DAGs resolve as one lazy graph locally and in Dask.

## Phase 5: HashType Computation And Local Caching In `seamless-core`

Goal: compute and cache `HashType` for every checksum when the checksum is computed over a buffer.

Implementation:

- Add `seamless/checksum/hash_type.py` with:
  - packed integer representation;
  - `Kind`, `Length`, `DType`, `Rank`, `Flag`;
  - pack/unpack helpers;
  - `is_valid_word`;
  - `from_buffer(buffer, checksum=None, value=None, celltype=None, semantic=False)`;
  - query methods from the design.
- Do not preserve `BufferInfo` as an implementation layer. Delete, bypass, or leave it as an unused legacy module as appropriate, but new logic should call `HashType` directly.
- Compute HashType from the cheapest authoritative source:
  - constants for `true`, `false`, `null`;
  - length and magic/header peek first;
  - value-in-hand for JSON family and raw text/bytes when available;
  - MIC materialization only as a last resort.
- Hook HashType computation into both checksum paths:
  - `cached_calculate_checksum()`;
  - `cached_calculate_checksum_sync()`.
- If method 2 needs the value that was just serialized/deserialized, adjust `serialize_cache`, `parse_buffer_cache`, or the checksum LRU so the value remains available long enough to compute HashType.
- Add a local cache mapping `Checksum -> HashType int`. Keep it separate from buffer cache so it can survive value eviction.
- Register HashType when `Buffer(checksum=..., value_or_buffer=...)` is constructed with a known checksum and buffer bytes.

Tests:

- Compute HashType for every Phase 0 helper source checksum and compare with the expected integer.
- Re-run after cache eviction to ensure recomputation gives the same integer.
- Test all well-formedness invariants:
  - non-numpy means `DType.NA`;
  - non-numpy means `Rank.SCALAR`;
  - `NUMPY_BYTES` only for scalar nonnumeric numpy;
  - `NUMERIC_SCALAR` only for JSON number/string;
  - `SEMANTIC` only for raw text.
- Test query methods against representative conversion and capability examples from the design.

Acceptance:

- HashType is total, deterministic, locally cached, and available to expression/deserialization/transformer validation.

## Phase 6: Mandatory HashType Validation

Goal: reject structurally impossible operations at every checksum boundary.

Implementation:

- Add a validation module, for example `seamless/checksum/hash_type_validation.py`, with shared exception classes and message builders.
- Expression evaluation validation:
  - source checksum must be deserializable as `Expression.celltype`;
  - path steps must be supported by capabilities relative to source celltype;
  - empty-path target conversion must be feasible;
  - non-empty path target conversion must be feasible for the result where statically knowable.
- Transformation input assignment validation:
  - when a concrete Checksum is assigned to a pin, validate it against pin celltype/subcelltype if HashType is available or computable;
  - if HashType is absent and buffer is unavailable, defer until resolution/fingertipping obtains enough data.
- Future-resolution validation:
  - when a Transformation or Expression handle assigned to a transformation input resolves to a Checksum, validate that checksum before using it in the transformation payload;
  - include Dask worker-side validation so invalid remote dependencies fail before running user code.
- Buffer-to-value deserialization validation:
  - in `parse_buffer()` and `parse_buffer_sync()`, when `checksum` is known, look up or compute `HashType`;
  - call `deserializable_as(checksum, celltype)` before parsing;
  - reject impossible deserializations with a HashType-based message;
  - keep value-level validation for cases HashType can only screen, such as exact checksum hex, python/ipython/yaml validity, and int integrality.
- Validator TODOs:
  - add TODO hooks after structural evaluation and before returning successful expression results;
  - do not include validator fields in identity or cache lookup.

Tests:

- Phase 0 valid expressions still evaluate.
- Phase 0 invalid expressions now fail with HashType-specific errors where applicable.
- `Buffer.deserialize(celltype)` and async deserialize reject impossible known-checksum cases before parse work.
- Concrete transformation checksum inputs reject incompatible HashType at assignment/construction time.
- Transformation and Expression future inputs reject incompatible HashType after resolution.
- Dask tests cover:
  - invalid expression dependency;
  - invalid transformation future dependency;
  - invalid expression future assigned to transformation pin;
  - validation error propagation from worker to client.

Acceptance:

- No known-checksum path can silently deserialize or pass a checksum into user code when HashType proves the celltype incompatible.

## Phase 7: Remote Checksum-To-HashType Cache

Goal: share `Checksum -> HashType int` through remote database services.

Implementation:

- In `seamless-database`, add a model/table such as `HashType`:
  - primary key `checksum`;
  - integer `hash_type`;
  - optional provenance/version fields only if needed.
- Add GET/PUT request types:
  - `hash_type`;
  - optional batch GET/PUT if helper tests show single-row chatter is too high.
- In `seamless-remote`, add:
  - `get_hash_type(checksum)`;
  - `set_hash_type(checksum, hash_type)`;
  - optional batch methods.
- Validate remote payloads with `HashType.is_valid_word()` before accepting them.
- Local lookup order:
  - local HashType cache;
  - remote database;
  - compute from local buffer/value if available;
  - if unavailable, defer or fingertip buffer depending on caller policy.

Tests:

- First process:
  - load helper source checksums;
  - monkey-patch HashType lookup to log `remote_hit` vs `computed`;
  - all HashTypes compute de novo and write remote rows.
- Second process:
  - repeat with empty local cache;
  - all helper source HashTypes come from remote cache.
- Invalid remote HashType words are rejected.

Acceptance:

- HashType caching works like a checksum metadata cache: stable, total, and independent of expression result caching.

## Phase 8: Remote Expression Evaluation

Goal: evaluate expressions remotely when policy and data availability require it.

Implementation:

- Add `execution: remote` support for expressions, modeled on transformation dispatch but without a transformation envelope.
- In `seamless-remote`:
  - add expression dispatch function, for example `run_expression(expression_key)`;
  - add jobserver client method and remote wrapper;
  - add database cache lookup/write around dispatch.
- In `seamless-jobserver`:
  - add `/run-expression` endpoint;
  - payload includes `input_checksum`, `path`, `celltype`, `target_celltype`;
  - response returns result checksum or structured failure;
  - no worker pool dispatch for expressions unless the implementation intentionally runs it inline in the jobserver process. The design says expressions should not consume spawn-worker slots.
- Dask support:
  - add expression future creation to `seamless-dask/client.py`;
  - expression tasks run where the input data is available;
  - expression futures can be dependencies of transformation futures.
- Placement ladder:
  - expression result cache hit returns immediately;
  - deep path navigates manifest without parent materialization;
  - if input buffer exists in local buffer cache or configured buffer folders, evaluate locally;
  - if input data is only available through hashserver/remote storage, delegate remote evaluation;
  - never dispatch expression evaluation to a generic spawn worker.
- Data availability detection:
  - expose a small policy function such as `choose_expression_evaluation_location(input_checksum) -> "local" | "remote"`;
  - make it monkey-patchable for tests;
  - check local buffer cache and buffer folders before deciding remote.

Tests:

- Simple remote expression evaluates and caches.
- Local buffer available means local expression path is used even when `execution: remote`.
- Buffer only available via hashserver means remote expression path is used.
- Cache hit avoids both local materialization and remote dispatch.
- Dask:
  - expression over Dask-produced checksum evaluates in the worker context where data landed;
  - expression result feeds downstream Dask transformation;
  - local-vs-remote path is logged with monkey-patches.

Acceptance:

- Remote expression evaluation is cache-aware, data-local, Dask-compatible, and never uses the spawn transformation worker path.

## Phase 9: Fingertipping And Reverse Provenance Across Expressions

Goal: missing results can be recovered by walking expression and transformation provenance.

Implementation:

- Extend `Checksum.fingertip()` / reverse resolution code to query:
  - reverse transformations;
  - reverse expressions.
- For reverse expression rows:
  - fingertip the input checksum recursively;
  - apply the expression path/conversion;
  - write the result buffer/checksum and expression cache row.
- Ensure expression reverse rows carry all four identity fields.

Tests:

- Delete an expression result buffer but leave reverse expression provenance; fingertip recovers it.
- Chain expression -> expression -> transformation and recover the missing leaf.
- Chain transformation -> expression -> transformation and recover through both reverse indexes.

Acceptance:

- Expression-produced checksums are as recoverable as transformation-produced checksums.

## Phase 10: Migration, Compatibility, And Cleanup

Implementation:

- Replace any remaining meaningful `BufferInfo` usage with `HashType` queries.
- Do not add new `buffer_info` remote/database compatibility work. If old `buffer_info` APIs are unused, leave them alone or remove them in a focused cleanup.
- Do not recreate cached conversion-result fields from `BufferInfo`; empty-path Expressions own those checksums.
- Add release-note level documentation of:
  - `HashType` replacing `BufferInfo`;
  - expression cache identity;
  - new transformation input kind.
- Add a focused deprecation note if public APIs change, especially `Cell.__call__`.

Tests:

- Existing conversion tests still pass or are deliberately updated to expression-cache expectations.
- Existing transformation, remote database, jobserver, and Dask tests pass.
- New helper-driven suites run in local-only and remote-enabled modes.

Acceptance:

- The old `BufferInfo` decision surface is no longer part of meaningful execution; `HashType` is the single source of truth for new validation and conversion decisions.

## Cross-Phase Test Matrix

Run these at minimum before handoff completion:

- `seamless-core`: expression helper tests, HashType pack/query tests, Buffer.deserialize HashType validation tests.
- `seamless-transformer`: transformation inputs with checksum, transformation future, expression future, and mixed dependency graphs.
- `seamless-database`: expression GET/PUT/reverse, HashType GET/PUT, final schema creation/update.
- `seamless-remote`: database client/remote expression and HashType methods, jobserver expression client parsing.
- `seamless-jobserver`: expression endpoint success/failure/cache integration.
- `seamless-dask`: expression futures, expression inputs to transformations, validation failure propagation, cache hit reuse.
- Multi-process tests:
  - expression cache first process de novo, second process cached;
  - HashType cache first process computed, second process remote hit.

## Error Message Requirements

HashType-based errors should include:

- checksum hex;
- operation kind: deserialization, expression evaluation, transformation input, future resolution;
- source celltype and target celltype where relevant;
- path segment that failed where relevant;
- HashType integer and decoded `Kind`/`Length`/`DType`/`Rank` summary;
- short reason, such as `not deserializable as binary`, `MAP access unavailable for JSON_ARRAY read as plain`, or `conversion plain -> binary is value-dependent and must materialize`.

Avoid exposing `TypeBits` in code-facing messages.

## Open Decisions To Resolve Before Coding The Affected Phase

- Path representation: keep string paths from current `Expression` skeleton or move to structured path steps. Resolve before Phase 0 tests and database API work; no stored expression rows need compatibility.
- `Cell.__call__`: keep current "build Expression" behavior or switch to "run value" per the design doc. Resolve before Phase 2 public tests.
- Expression conflict policy: if database already has a different result for the same expression key, hard error vs overwrite. Recommended: hard error.
- Remote expression host: database/hashserver-side evaluation vs jobserver endpoint. The rough outline requests jobserver API support; if hashserver-side data locality is needed, keep jobserver as the API front door and push only the data-local operation down.
- Semantic HashType producer: leave `SEMANTIC` support as an explicit producer hook. Do not infer it from bytes.
- Validator implementation: deliberately deferred. Only TODO hooks and reject-only contract checks belong in this plan.

## Handoff Self-Review

Criteria for handoff readiness:

- The plan names concrete repos and current modules.
- Work is ordered so each phase has a usable test harness before it is needed by later phases.
- Every cache has first-process miss and second-process hit tests.
- Local, remote, jobserver, and Dask paths are all covered.
- HashType validation triggers include Expression evaluation, Transformation checksum assignment, future resolution, and Buffer-to-value deserialization with known checksum.
- Validators are explicitly scoped as TODO hooks, not silently omitted.
- Open decisions are isolated and tied to phases.

Review result: no adaptation needed after adding Buffer-to-value deserialization validation as a mandatory trigger, separating direct Expression tests from Cell-built Expression tests, removing expression-storage compatibility/migration requirements because expressions are not currently stored in `seamless.db`, and treating `BufferInfo` as replaceable unused scaffolding rather than a compatibility surface.
