# Feature 5: standalone Cell implementation — 2026-09-22

The seamless-core Cell tests now run as ordinary regressions: **931 passed**,
with no remaining xfail marks in seamless-core. This does not close the bound
workflow gaps in `cells-and-expressions-known-issues.md`.

## Implementation

- Projection and explicit conversion builders retain their parent. Expression
  snapshots preserve syntax order, fuse eligible links, and retain conversion
  and deep-step barriers. Dummy upstream Expressions are removed; a barrier's
  published input checksum is available for its database key without evaluation.
- Constructor `path=` and `SubCell` are removed. Paths are read-only, and handle
  guards live on `CellBase`, including Pins. Internal recipe tracking uses
  checksum values and object identities, never Cell comparisons.
- Implicit conversion behind a projection and standalone projection writes are
  refused. Source retyping makes projecting consumers miswired; restoring the
  type restores their usability. Parent configuration changes invalidate a
  child's cached result or failure.
- Standalone getters pull upstream Expressions while stopping at Transformation
  execution, including already-completed dependencies. One-shot overrides do
  not change the Cell's configured value.
- Public exceptions are strings; the private exception retains its type for
  raising. Buffer and value reads report recorded failures consistently, and
  materialization failure suppresses the public checksum until cleared.
- Deep buffers validate through their plain representation. Null conversions
  short-circuit static conversion rejection, including through child builders.
- Cells hold their computed results and release them when their recipe changes.
  `fingertip()` uses only an existing result, without triggering Cell evaluation.

## Test changes and repository boundaries

- Removed resolved Cell xfails, retaining their assertions.
- Corrected the paired two-conversion checksum oracle in core and workflow:
  `text -> plain` preserves JSON-parseable bytes. `b"[1,2]\n"` therefore need not
  have the checksum of canonically serialized `[1, 2]`. This follows
  `docs/agent/contracts/celltypes-and-conversion.md`, not a new conversion rule.
- Updated the older value-only setter test to preserve a projection's parent
  and initial state when a write is rejected.
- Replaced the remaining core remote-read test's constructor `path=` with
  navigation. Migrated the workflow backend's corresponding constructor call;
  its `with_input` regression passes.
- Moved `test_cells_transformer_boundary.py` to seamless-transformer. Its 14
  cases pass without xfails. Moved the source-Transformation read test into
  `seamless-transformer/tests/test_cell_transformation_reads.py`; it also passes.
- Moved `test_materialization_waiter_contract.py` to seamless-remote. These three
  non-Cell tests import that package. Their existing marks remain: the relocated
  file reports one XFAIL and two XPASS, with no implementation changes there.
- Added regressions for available Transformation dependencies, null conversion
  children, fingertipping without evaluation, and computed-result ownership.

## Validation

All tests used the **seamless1 conda environment**, with **one pytest process per
file**, invoked as `python -m pytest` from the owning repository.

| Core Cell file | Passed |
|---|---:|
| `test_cell_backend_contract.py` | 1 |
| `test_cell_base.py` | 4 |
| `test_cell_expression_builder.py` | 706 |
| `test_cell_input_ref.py` | 35 |
| `test_cell_reference_lifecycle.py` | 4 |
| `test_cell_running_loop_refusal.py` | 1 |
| `test_cell_semantics.py` | 35 |
| `test_cells_contract_alignment.py` | 113 |
| `test_cells_projection_writes.py` | 13 |
| `test_standalone_cell_reads.py` | 12 |
| `test_standalone_read_remote_steps.py` | 7 |
| **Total** | **931** |

The broader run covered all 47 core `test_*.py` files. Completed files report
**2,917 passed and 60 failed**. The five failing files were separately run against
an untouched archive of seamless-core HEAD; their exact failing test IDs match:

| Existing failing file | Failures | Cause |
|---|---:|---|
| `test_celltype_buffer_footprint.py` | 3 | Deep fixtures contain ordinary values instead of checksum members |
| `test_expression_errors.py` | 2 | Fake remote lacks `_read_folders_clients` |
| `test_expression_hashtype_cases.py` | 27 | Tests expect construction to accept statically invalid paths |
| `test_expression_local_evaluation.py` | 27 | Same construction-versus-evaluation expectation |
| `test_reference_lifecycle_forced_expiry.py` | 1 | Deep fixture contains a non-checksum member |

`test_expression_remote_evaluation.py` timed out after 90 seconds, both with
these changes and on untouched HEAD, with the same partial output
(`...........F`). It is not counted in the completed-file totals. These unrelated
failures and the timeout were not changed as part of the Cell implementation.
