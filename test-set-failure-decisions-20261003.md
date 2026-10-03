# Test set failure decisions (2026-10-03)

Source: `test-set-classification-results-20261003T084831Z.tsv`.

## Config helper scripts

Files: `seamless-config/tests/launch-test-json.py`, `test-daskserver.py`,
`test.py`, `test2.py`, `test3.py`, and `test4.py`.

Decision: the five configuration scripts failed because their shared
`tests/seamless.yaml` fixture selected a project but no cluster. The user's
`~/.seamless/clusters.yaml` defines `local`, which can be selected. The fixture
now selects `cluster: local` and `execution: process` (needed because `local`
offers both jobserver and daskserver). All five scripts now complete and print
launch configurations. They remain manual smoke scripts with no assertions.

The bare `launch-test-json.py` invocation is non-contract: it requires a JSON
file path in `sys.argv[1]`, which the classifier did not provide. It failed
before any remote operation, so there is no server-side failure to debug. A
real launcher test must supply a launch specification.

Regression: the five config scripts passed individually;
`tests/test_tools_hashserver.py` (4 passed) and
`tests/test_execution_command.py` (27 passed) each passed in its own pytest
process in the `seamless1` conda environment.

## Database hash type fixture

File: `seamless-database/tests/test_contract_hashtype_db.py`.

Decision: the `unused-kind-12` test case was stale. Kind 12 is the valid
`JSON_NULL` member, so the test incorrectly expected it to be rejected. The
fixture now uses unknown kind 13, preserving the malformed-kind check.

Regression: `test_contract_hashtype_db.py` (26 passed) and
`test_hash_type_tightening.py` (15 passed), each run in its own pytest process
in the `seamless1` conda environment.

## Core conversion and binary demo

Files: `seamless-core/tests/test_contract_celltypes_conversion.py` and
`seamless-core/tests/binary.py`.

Decision: the conversion test's exact call count was faulty. Planning calls
`convert_checksum` to determine whether a buffer is needed, then execution
calls it again. The test now requires that every observed call has the expected
conversion pair and retains its result checksum assertions. The full test file
passed (686 tests). `binary.py` is an intentional failing demo: it writes to a
read-only array at a line annotated `# error!`; its bare nonzero exit is
non-contract, so no product change is warranted.

Regression: `test_conversion_engine.py` (50 passed) and
`test_contract_canonical_bytes.py` (34 passed), each run in its own pytest
process in the `seamless1` conda environment.

## Core expression evaluation

Files: `seamless-core/tests/test_contract_expressions.py` and
`seamless-core/tests/test_expression_errors.py`. Regression also covered
`test_expression_materialize.py`.

Decision: the fingertip tests' fake database module was incomplete. Production
`database_remote` defines `has_read_database()`, but the fake omitted it. The
fake now returns false, consistent with its lack of a reverse lookup database.
The wrong `CacheMissError` checksum was a real product regression: local
evaluation of a known result with no reachable direct input now reports the
requested result checksum. The guard is in the local branch so valid remote
dispatch remains possible.

Regression: `test_contract_expressions.py` (320 passed),
`test_expression_errors.py` (8 passed), and `test_expression_materialize.py`
(11 passed), each run in its own pytest process in `seamless1`.

## Remote expression evaluation

Files: `seamless-remote/tests/simple2.py`,
`test_core_remote_integration.py`, and `test_expression_remote_evaluation.py`.

Decision: the bare `simple2.py` run is non-contract in this checkout. It
selects no cluster/profile and expects a checksum buffer absent from the
configured local buffer store. Its cache miss occurs before any server
connection. No fixture data was invented or seeded.

The integration test's exact asynchronous file-read count was an incidental
implementation assertion; it retains the checksum and resolved-value checks.
The expression test fake omitted `get_buffer_lengths`, which production uses
for reachability checks. Several tests asserted queued database writes before
the writer flushed. The fake now implements the production API, and the tests
flush the writer before asserting persistence. No production code changed.

Regression: `test_core_remote_integration.py` (2 passed),
`test_expression_remote_evaluation.py` (23 passed), and
`test_hash_type_remote_cache.py` (7 passed), each run in its own pytest
process in `seamless1`. These pytest files are classified non-remote in the
source TSV; `simple2.py` did not pass and had no remote service interaction.

## Remote lifecycle and materialization

Files: `seamless-remote/tests/test_contract_reference_lifecycle_linger.py`,
`test_materialization_waiter_contract.py`, and
`test_reference_lifecycle_forced_expiry.py`.

Decision: the forced-expiry test called the removed private method
`Expression._publish_result`; the current private hold method is
`_hold_result`, so the test reference was stale. Its independent result-claim
assertions remain. The linger and waiter timeouts exposed a real core bug:
local expression evaluation rejected an input before `Checksum.resolution()`
could ask configured read clients for it. That premature guard was removed.
The stubbed tests had no server connection, so no server log or service cache
was involved.

Regression: the three assigned files passed (3, 9, and 6 tests). Also passed:
`seamless-core/tests/test_expression_errors.py` (8),
`test_expression_materialize.py` (11), and
`seamless-remote/tests/test_contract_expression_linger.py` (4). Each file ran
in its own `seamless1` pytest process.

## Transformer remote execution and input publication

Files: `seamless-transformer/tests/cmd/manyjobs.sh`, `cmd/simple-dir.sh`, and
`tests/test_contract_input_side_reverse_publish.py`.

Decision: a bare `manyjobs.sh` run under the classifier's 600-second cap is
non-contract stress work. Its defaults submit 1,000 jobs of 1,000,000,000 dots
each, with about 330 seconds of submission delay alone. Its timeout is not
evidence of a product defect; the stress defaults were left unchanged.

The reverse-publish test setup allowed direct reads from the local cluster's
shared hashserver folder and used a default `mixed` pin, which wrapped its
`str` Expression in a scratch intermediate. The test now disables the direct
read-folder shortcut and types the pin as `str`, so it actually exercises the
non-scratch pin-facing Expression. Its hashserver publication assertion remains.
The public `allow_input_fingertip=False` setter also dropped its metadata key;
it now preserves explicit false so remote dispatch receives the policy. The
separate scratch-chain contract showed that nested intermediates must remain
scratch; no nested Expression behavior was changed.

`simple-dir.sh` passed twice for the subagent and once for the parent on cold
local `cmd-test` service/cache state. Fresh daskserver and hashserver logs had
no errors. Parent regression also passed the reverse-publish file (2 tests)
and `test_pin_scratch_contract.py` (15 tests), each in its own pytest process.

## Transformer local reads and execution records

Files: `seamless-transformer/tests/test_cell_transformation_reads.py` and
`tests/test_execution_records.py`.

Decision: neither test file is faulty or non-contract. The Cell test requires
checksum and state inspection to leave an unresolved source transformation
unstarted and the Cell waiting. Core Expression evaluation now returns no
checksum when `run_source=False` and the source has no result, preserving that
state contract. The execution-record failures were a closure scoping bug:
`write_execution_record` assigns the outer probe and compilation contexts
without declaring them `nonlocal`.

Assigned-file checks passed in separate `seamless1` pytest processes:
`test_cell_transformation_reads.py` (1 test) and
`test_execution_records.py` (14 tests). Parent regression also passed
`test_probe_capture.py` (11 tests) and
`seamless-core/tests/test_standalone_cell_laziness.py` (11 tests), each in its
own pytest process.

## Workflow reference ownership

Files: `seamless-workflow/tests/test_contract_reference_lifecycle_anonymous.py`
and `test_reference_lifecycle_binding.py`.

Decision: the anonymous-node test expected canonical `plain` bytes after a
`text -> plain` conversion of valid JSON. That conversion preserves the source
text checksum, so the test now compares the hold to `ctx.b.checksum` while
retaining its role, count, and value assertions. The binding test called
`audit_reference_accounting(holders=[ctx])`, which compares the global cache
against only one holder and omits a live fact `Lease`. It now audits all
registered holders and retains the no-warning assertion.

The projection-chain cases also exposed a real ownership bug:
`CellBase._release_refholds` and `_refheld_checksums` read `_input_ref`, which
delegates to a bound backend after binding. That let a bound cell release a
checksum it had never acquired as a standalone input. Both lifecycle paths now
inspect `_standalone_input_ref`, the reference owned by that cell.

Regression: the two assigned files passed (7 and 14 tests), plus
`test_contract_reference_lifecycle_scratch.py` (8) and
`seamless-core/tests/test_cell_reference_lifecycle.py` (4), each in its own
`seamless1` pytest process.
