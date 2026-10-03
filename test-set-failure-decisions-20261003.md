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
