# Feature 5 Cell test alignment — 2026-09-22

## Contract decision

`docs/agent/contracts/cells.md` now incorporates Appendix F's decisions:

- remove constructor `path=` and the `SubCell` class/exports;
- make `.path` and its `.path_python` alias read-only (the follow-up ruling);
- put handle-value guards on `CellBase`, including root Cells and Pins;
- convert heterogeneous join members to the join's celltype;
- make bound checksum reads non-evaluating and non-waiting, apart from the dummy case;
- allow standalone `miswired` state;
- store anonymous nodes under `anonymous_nodes` in graph format `0.5`.

The writable `.path` property was the remaining decision needed after Appendix F.
With the read-only ruling, the contract is precise enough for this alignment.
The obsolete constructor round-trip exception, the standalone four-state restriction,
and the conflicting assertion that the two ordering examples fuse to the same recipe
have been removed. Contract-ahead-of-code passages are marked explicitly.

No production implementation was changed. Workflow implementation source was not
inspected; bound behavior was tested through the public API. Existing public-API
failures were not treated as evidence that the contract should change.

## Test map

Files named in both columns are separate tests in the respective repository's `tests/`
directory. Common cases have matching names; fixtures bind the workflow versions to a
real Context. Known-gap marks can differ when only one mode fails.

| Contract surface | seamless-core | seamless-workflow |
|---|---|---|
| Constructor, type declarations, live source types, root 3×2 writes, authority, value-only setters, null/clear, empty bytes, checksum values | `test_cells_contract_alignment.py` | `test_cells_contract_alignment.py` |
| Read-only paths, removed SubCell, root/projection guards, name collisions and retired names | `test_cells_contract_alignment.py` | `test_cells_contract_alignment.py` |
| Parent links, syntax order, constructor/with_input wiring refusals, retyping and miswiring | `test_cells_contract_alignment.py` | `test_cells_contract_alignment.py` |
| Path/path fusion, conversion/path fusion and barriers, consecutive conversions, deep-step barrier and member-checksum identity | `test_cells_contract_alignment.py` | `test_cells_contract_alignment.py`, `test_cells_wiring_contract.py` |
| Evaluation versus materialization, stable string failures, retry, missing projections, missing result buffers, no implicit fingertip | `test_cells_contract_alignment.py`, `test_standalone_cell_reads.py` | `test_cells_contract_alignment.py`, `test_execution_error_types.py`, `test_cell_inspection_contracts.py` |
| Frozen snapshots, build aliases, one-shot overrides, async compute, configuration-only operations | `test_cells_contract_alignment.py` | `test_cells_contract_alignment.py` |
| Deep typed indexes and member access; deferred validator refusal, including a cached recipe | `test_cells_contract_alignment.py` | `test_cells_contract_alignment.py` |
| All six projection writes and connected-target refusal | `test_cells_projection_writes.py`: writes must be refused | `test_cells_projection_writes.py`: transactions must update the root and enforce authority |
| Existing Cell/Expression witness corpus: identity, valid results, invalid recipes | `test_cell_expression_builder.py` | `test_cell_expression_builder.py` with a shim loading the same core witness data |
| Cell rejects Pin inputs; CellBase guards also apply to Pins | `test_cells_transformer_boundary.py` | `test_cells_transformer_boundary.py` |

The common alignment files contain **44 named tests / 113 parametrized cases per mode**.
The Expression corpus has **702 cases per mode**, plus four existing standalone
builder tests whose bound counterparts are in the common alignment file.

The current contract specifies joins only through bound sub-path connections:
[*Connecting*](docs/agent/contracts/cells.md#connecting-a-path-and-a-conversion-may-not-share-one-link)
says that a one-level connection target exists only in a workflow, and
[*Projections*](docs/agent/contracts/cells.md#projections) explicitly forbids standalone
sub-path assignment. It supplies no alternative standalone multi-source constructor or
builder method. That is why this contract-alignment pass did not invent standalone join
tests or an API for them. This is a contract boundary, not an inherent limitation:
a standalone join could retain multiple source links and assemble them lazily on a read.
Supporting it would extend the construction/wiring API and require defining its standalone
failure and snapshot behavior; a Context is not intrinsically required to assemble values.

Join tests, together with the bound-only node deletion, graph round-trip, anonymous-node
table and elision tests, are in the workflow projection/wiring files and
`test_cell_joins.py`. Those cover heterogeneous conversion,
member input-type lookup, per-edge blocking reasons, graph 0.5, symbol stability,
anonymous-node garbage collection, stored collision suffixes, named versus anonymous
fusion/elision, and a gated test proving a bound checksum read does not wait for active
core evaluation. Collision loading is tested with explicitly suffixed stored symbols;
the suite does not depend on probabilistically generating a hash collision.

The existing standalone running-loop refusal test is retained; bound getter behavior
is covered separately because it must not enter evaluation at all. Mount behavior and
checksum ownership beyond the Cell child/parent lifetime check remain in their existing
attachment/reference-lifecycle suites. Future validator semantics are deliberately not
asserted: only the settled deferred refusal and identity exclusion are tested.

## Existing test corrections

- Builder snapshot tests mutate the root, not a standalone projection or its now-read-only
  path. Navigation asserts parent links and a separate pathless conversion child.
- The child-lifetime test retains the parent through the child instead of requiring a
  duplicate bare-checksum hold, which the child-link contract does not promise.
- Invalid witness recipes may be rejected during Expression construction. Tests now
  compare rejection at construction/evaluation, rather than requiring every failure to
  wait until `compute()`.
- Constructor `path=` and projection retyping in read/error tests use explicit navigation
  and conversion links instead.
- The section 3.4 item 3 projection-failure test still uses non-strict xfail, and explicitly
  asserts that `.exception` is a nonempty string before comparing successive reads.
- Cache-miss retry and stored-result tests no longer require exception objects. Their
  retry/cache assertions remain ordinary regressions; string representation is tested
  independently so it cannot hide those checks behind an xfail.
- Join failure setup uses a Cell conversion failure instead of building a Transformer.
  Join block reasons now assert the per-edge dict contract. The join file already used
  the corrected `["value"]` spelling at the start of this pass.
- The literal graph round-trip no longer pins format 0.4; a dedicated version test asserts
  0.5, so the known format gap cannot hide the literal round-trip regression.
- A constructor test retains its input Buffer rather than relying on expired weak-cache
  residency. The fake remote supplies the read-folder client list and accepts `scratch`,
  allowing the existing running-loop test to exercise its intended behavior.
- The remote missing-input integration test uses the new chain spelling and string
  exception contract. It was collected, not executed against live services.

## Expected failures and additional findings

Known gaps use `xfail(strict=False)` with a specific contract rule or observed defect.
There is no general workflow-implementation xfail. Initially passing known-gap cases
were promoted to ordinary regressions, including bound path immutability, existing
projection guards, bound deep-index reads, and standalone deep member access.

Four additional discrepancies were established by paired tests:

| Case | Failing mode | Passing counterpart |
|---|---|---|
| Empty-buffer checksum assigned to a `bytes` Cell does not become null | bound checksum write | standalone checksum write; value and buffer writes |
| `as_celltype()` / `build()` on an unwired Cell raises instead of returning a recipe | bound | standalone |
| `compute()` raises the deferred-validator failure instead of returning `None` | bound | standalone |
| Null retyped to `int` is rejected for `python`, `ipython`, `deepcell`, `deepfolder`, `folder`, `module` | standalone | bound, for all six |

These are also recorded in `cells.md` and the known-issues document. They were marked
only after observing the failures, without inspecting workflow implementation source.

The Transformer-dependent files were added **last**, after reading
`contracts/direct-delayed-and-transformation.md` and the relevant Pin contract.
They build an unwired Transformer to obtain a Pin, and execute no Transformer body.
Per the explicit task instruction, all their cases retain an ahead-of-code xfail:
**five input-rejection cases XPASS and nine guard cases XFAIL in each mode**.

## Validation

Run in the **`seamless1` conda environment**, with **one pytest process per file** and
the corresponding repository as working directory. Every executed file exits zero.
No suite-wide combined pytest process was used.

| Repository | Files executed | Passed | XFAIL | XPASS |
|---|---:|---:|---:|---:|
| seamless-core | 14 | 902 | 60 | 5 |
| seamless-workflow | 10 | 676 | 234 | 5 |
| **Total** | **24** | **1578** | **294** | **10** |

The 10 XPASS cases are the explicitly marked Transformer-dependent input rejections
above. The rest of the executed tests have no unexpected failures or XPASS results.

For each file below, the command was:

```bash
# Working directory: seamless-core or seamless-workflow as listed below
conda run -n seamless1 python -m pytest tests/<file>.py -q --tb=short -rxX
```

| Repository | Test file | Final result |
|---|---|---|
| seamless-core | [`test_cell_backend_contract.py`](../seamless-core/tests/test_cell_backend_contract.py) | 1 passed |
| seamless-core | [`test_cell_base.py`](../seamless-core/tests/test_cell_base.py) | 4 passed |
| seamless-core | [`test_cell_expression_builder.py`](../seamless-core/tests/test_cell_expression_builder.py) | 704 passed, 2 xfailed |
| seamless-core | [`test_cell_input_ref.py`](../seamless-core/tests/test_cell_input_ref.py) | 35 passed |
| seamless-core | [`test_cell_reference_lifecycle.py`](../seamless-core/tests/test_cell_reference_lifecycle.py) | 2 passed, 1 xfailed |
| seamless-core | [`test_cell_running_loop_refusal.py`](../seamless-core/tests/test_cell_running_loop_refusal.py) | 1 passed |
| seamless-core | [`test_cell_semantics.py`](../seamless-core/tests/test_cell_semantics.py) | 35 passed |
| seamless-core | [`test_cells_contract_alignment.py`](../seamless-core/tests/test_cells_contract_alignment.py) | 74 passed, 39 xfailed |
| seamless-core | [`test_cells_projection_writes.py`](../seamless-core/tests/test_cells_projection_writes.py) | 4 passed, 9 xfailed |
| seamless-core | [`test_cells_transformer_boundary.py`](../seamless-core/tests/test_cells_transformer_boundary.py) | 9 xfailed, 5 xpassed |
| seamless-core | [`test_checksum_celltype.py`](../seamless-core/tests/test_checksum_celltype.py) | 6 passed |
| seamless-core | [`test_expression_result_never_undone.py`](../seamless-core/tests/test_expression_result_never_undone.py) | 9 passed |
| seamless-core | [`test_retired_names.py`](../seamless-core/tests/test_retired_names.py) | 22 passed |
| seamless-core | [`test_standalone_cell_reads.py`](../seamless-core/tests/test_standalone_cell_reads.py) | 5 passed |
| seamless-workflow | [`test_cell_expression_builder.py`](../seamless-workflow/tests/test_cell_expression_builder.py) | 538 passed, 164 xfailed |
| seamless-workflow | [`test_cell_inspection_contracts.py`](../seamless-workflow/tests/test_cell_inspection_contracts.py) | 1 passed, 1 xfailed |
| seamless-workflow | [`test_cell_joins.py`](../seamless-workflow/tests/test_cell_joins.py) | 4 passed, 2 xfailed |
| seamless-workflow | [`test_cell_semantics.py`](../seamless-workflow/tests/test_cell_semantics.py) | 37 passed |
| seamless-workflow | [`test_cells_contract_alignment.py`](../seamless-workflow/tests/test_cells_contract_alignment.py) | 78 passed, 35 xfailed |
| seamless-workflow | [`test_cells_projection_writes.py`](../seamless-workflow/tests/test_cells_projection_writes.py) | 9 passed, 8 xfailed |
| seamless-workflow | [`test_cells_transformer_boundary.py`](../seamless-workflow/tests/test_cells_transformer_boundary.py) | 9 xfailed, 5 xpassed |
| seamless-workflow | [`test_cells_wiring_contract.py`](../seamless-workflow/tests/test_cells_wiring_contract.py) | 1 passed, 13 xfailed |
| seamless-workflow | [`test_execution_error_types.py`](../seamless-workflow/tests/test_execution_error_types.py) | 8 passed |
| seamless-workflow | [`test_undeserializable_expression_result.py`](../seamless-workflow/tests/test_undeserializable_expression_result.py) | 2 xfailed |

The separately edited `seamless-workflow/tests/test_expression_execution.py` collected
all five integration cases successfully. Live jobserver/daskserver/hashserver integration
was not run. Whitespace checks passed for the changed contract and both test repositories.
