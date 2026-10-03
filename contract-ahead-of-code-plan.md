# Contract gaps carried forward

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
