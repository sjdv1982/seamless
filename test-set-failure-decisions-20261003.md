# Test set failure decisions (2026-10-03)

Source: `test-set-classification-results-20261003T084831Z.tsv`.

## Config helper scripts

Files: `seamless-config/tests/launch-test-json.py`, `test-daskserver.py`,
`test.py`, `test2.py`, `test3.py`, and `test4.py`.

Decision: these six bare invocations are non-contract/manual harness scripts,
not failing product tests. `launch-test-json.py` requires a JSON file path in
`sys.argv[1]`, which the classifier did not provide. The other five scripts
require a selected cluster; the `tests/seamless.yaml` used by their bare
invocations specifies only a project. They configure services and print JSON,
with no assertions. The observed `IndexError` and `ConfigurationError` follow
from the missing invocation context. Production configuration validation should
continue rejecting a missing cluster.

Regression: `tests/test_tools_hashserver.py` (4 passed) and
`tests/test_execution_command.py` (27 passed), each run in its own pytest
process in the `seamless1` conda environment.

## Database hash type fixture

File: `seamless-database/tests/test_contract_hashtype_db.py`.

Decision: the `unused-kind-12` test case was stale. Kind 12 is the valid
`JSON_NULL` member, so the test incorrectly expected it to be rejected. The
fixture now uses unknown kind 13, preserving the malformed-kind check.

Regression: `test_contract_hashtype_db.py` (26 passed) and
`test_hash_type_tightening.py` (15 passed), each run in its own pytest process
in the `seamless1` conda environment.
