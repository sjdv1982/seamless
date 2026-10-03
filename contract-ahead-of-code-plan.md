# Contract gaps carried forward

The original carried entries below are complete as of 2026-10-03. Focused tests rechecked the already implemented entries and cover the remaining deep buffer, Pin read and direct Expression binding fixes. The old status-section gap bullets were removed after verification; deferred features and non-gap limitations remain on their contract pages.

These are the live inline “contract ahead of code” notes moved from the contract pages on 2026-10-03. Line numbers refer to the pages before this move. The contract text on each page remains the test oracle.

| Page and former line | Implementation work |
|---|---|
| `mounts.md:67` | Make the specified `NodeError` reachable through the public mount API for a missing or non-cell node. |
| `pins.md:115` | Reject undeclared call-time keywords on signature-less direct builders in `seamless-transformer`. |
| `pins.md:252` | Keep validation and deserialization failures from changing a standalone Pin to `failed` in `seamless-transformer/pin_class.py`. |
| `pins.md:254` | Keep bound Pin materialization failures out of its recorded state and transformer block reason in `seamless-workflow`. |
| `node-state-lifecycle.md:271` | Change the workflow replacement hold default from 15 to the ruled 30 seconds. |
| `transformers.md:125` | Make the bound Transformer barrier return `None` for failed and incomplete states instead of raising. |
| `cells.md:441` | Keep Cell result read failures unrecorded in standalone and bound modes, and avoid parsing a result while deriving a Context node. |
| `cells.md:458` | Make bound projections start with their own non-scratch policy and preserve `scratch` through bound `with_input()` and `with_validator()`. |
| `cells.md:591` | Refuse a root source edge and sub-path edges on the same cell in either assignment order. |
| `cells.md:593` | Convert each join member to the join celltype in `seamless-workflow/sidework.py`, and enforce the pathless rule on heterogeneous members. |
| `deep-celltypes.md:134` | Implement `.buffer` reads at deep celltypes according to that page’s read contract. |

The inline notes at `mounts.md:325` and `cells.md:122`, `:165`, `:313`, and `:504` described behavior already fixed in the current tree and were removed rather than carried forward.

## Reconcile the implementation-status sections

Several pages repeat old gap notes in their *Implementation status* sections. Implement the entries above, then recheck the corresponding status bullets and their focused `xfail` tests. Remove a bullet when the code now satisfies the contract; move any other live gap here as its own entry with its page, former line, and code owner. In particular, check `cells.md`, `mounts.md`, `pins.md`, `node-state-lifecycle.md`, `attachments.md`, and `workflow-context.md`: their status sections still contain duplicate or older descriptions of the wiring, mount, join, and handle gaps fixed during the 2026-10-01 review. Keep deferred features and non-gap limitations on their contract pages.


## Remaining gaps found during reconciliation

The three gaps first listed here are closed. The upstream-confirmation hold and completed-downstream retention (`node-state-lifecycle.md`) and Expression fusion and elision across named and anonymous intermediates (`cells.md`) are implemented. The root Expression serialization gap (`workflow-context.md`) needed no format change: with fusion in place, a direct Expression that projects and converts in one operation is bound as a path link followed by a conversion link, which fuse back into that Expression, so the cell is saved in the ordinary 0.5 format. Focused tests are plain tests in `seamless-workflow/tests/`: `test_contract_upstream_hold.py`, `test_contract_bound_fusion.py` and `test_contract_direct_expression_binding.py`.

What is left, found while implementing them:

| Page | Implementation work and code owner |
|---|---|
| `workflow-context.md`, *Graph serialization* | A direct Expression whose innermost input is not a checksum (no input, or a live object such as a Transformation) is still retained as `Node.cell_root_expression` by `Context._replace_cell_from_builder`. It has no durable form, so `get_graph()` omits it and the cell reloads `unwired`. Decide between refusing such a binding and resolving the input to a checksum; owner `seamless-workflow/context.py`. |
| `cells.md`, *Anonymous cells, symbols and elision* | `seamless-workflow/tests/test_contract_reference_lifecycle_anonymous.py::test_context_holds_anonymous_current_for_a_non_elided_node` fails, as it did before this work. The non-elided `text → plain` intermediate is evaluated and held, but the test expects the canonical `plain` serialization's checksum, and the conversion keeps the JSON-parseable bytes. Either the test's expectation or the conversion is wrong; owner `seamless-core` conversion, or the test. |
| `workflow-context.md`, `close()` | Closing a Context with a cell bound from a `Cell(source=<direct Expression>)` logs `Refholder decref ignored … refholder count is already zero`, for the source's input and the Expression's result. It predates this work and shows in `test_undeserializable_expression_result.py`; owner `seamless-workflow/context.py::_replace_cell_from_builder` and the release of the bound Cell's holds. |

## Awaiting a ruling: hold kinds where the contract is silent

`node-state-lifecycle.md`, *Speculation*, describes the upstream-confirmation hold for an upstream that is recomputing. The implementation had to answer two cases the section does not state. Both answers keep more work alive rather than less, and neither is yet in the contract page.

- **An upstream change that resolves within the same turn** (a literal edit of an upstream cell, passed on through a same-celltype edge). The downstream's identity changes with every input resolved, so there is no upstream event to wait for. The code gives the superseded run the fixed 30-second window, as before, instead of cancelling it at once as the table's "different output" row would. `test_runtime_and_prune.py::test_node_level_prune_scopes_to_downstream_cone` and the scratch superseded-hold test depend on this.
- **An upstream that settles without a result** (`failed`, `blocked`, `unwired`). There is no output checksum to compare, so the code keeps the upstream hold until the five-minute backstop, or until `prune()`.

The hold kind is decided once, when the run is superseded: `upstream` when a node feeding it is `waiting` or `computing` at that moment, `self-edit` otherwise.
