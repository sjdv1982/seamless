# Anonymous nodes, symbols and handles: implementation plan

This plan implements ruling 2 and its follow-ups, all ruled on 2026-10-02.

## Rulings

1. **Handle-only entries are not saved (ruling 2).** `get_graph()` serializes an `anonymous_nodes` entry only when an edge, or another serialized entry, names it. An entry that only a live handle refers to is runtime state, and is excluded.
2. **Handles create and hold nothing.** An anonymous node exists while an edge, or another entry, refers to its recipe. It is created when the first such reference appears, and removed when the last one goes.
3. **Symbols are assigned eagerly.** A symbol is assigned when its anonymous node is created, and stored from then on. Colliding symbols are therefore suffixed in arrival order, so `contracts/cells.md:194` holds by construction. A node whose edge is later collapsed on save (rule 5) still claims its symbol. This is accepted.
4. **Assignment never renames and never invalidates.**
   - A handle assigned to a **new name** creates the named node with the handle's celltype. That node is fed by a **dummy edge** (an identity: no path, same celltype) from the handle's anonymous node.
   - The handle stays a handle to its anonymous node, and every other handle stays valid. A later `ctx.d = x` feeds `d` the same way.
   - A handle assigned to an **existing name** gets an edge from its anonymous node, as now.
5. **`get_graph()` collapses dummy edges from single links.** When an anonymous node is a single link that reads directly from a named node, a dummy edge from it to a cell or pin is saved as the target's own incoming link: `(b, [3]) → a`, or `b → a` for a conversion. The entry is then saved only if something else names it. Chains are saved as ruling 1 laid down: every link is an entry, with an edge from the outermost one. Collapsing a chain's outer dummy edge could leave a conversion behind a path, which reloads `miswired`.

The saved graph therefore keeps exactly the forms that ruling 1 laid down. Only the runtime and the handle semantics change.

## Prerequisite: fix handle reads first

Today, after `ctx.a = x`, the handle `x` is re-pointed at `a` and reads `a` correctly. Under rule 4, `x` stays an anonymous handle, and anonymous-handle reads currently **ignore the handle's conversion steps**. `ctx.b.as_celltype("plain")[3].value` over the text `"[10, 20, 30, 40]"` gives `","`, and `ctx.b.as_celltype("plain").compute()` returns `b`'s unconverted checksum. The relevant code is `ingress.py:318-366` and `builder_state.py:181-216` and `386-440`.

So step D below would be a regression for `x` unless that read bug is fixed first. It is the HIGH finding of the 2026-10-01 commit review, and it has no plan yet.

## How the code works today

- **The runtime graph has no anonymous-node objects.** An anonymous node is the recipe prefix of an `Edge`: the source node, a local path, and `source_conversion_steps` (`graph.py:117`).
  - `get_graph()` builds entries from converting edges (`add_anonymous_chain`, `context.py:2531`).
  - `set_graph()` flattens entries back into edges (`serialization.py:154-246`).
  - Symbols live in `ContextGraph.anonymous_symbol_by_recipe` (`graph.py:134`). `set_graph` fills it from loaded entries (`serialization.py:151`); otherwise `symbol_for` fills it lazily, inside `get_graph()` (`context.py:2498`).
  - Rule 2 therefore already matches the runtime model. What remains is the serialization, when symbols are assigned, and how handles are adopted.
- **Live handles are serialized**, added in `f6a87dc`:
  - every handle with a local path or conversion steps registers a second time, under a `("handle", …)` key (`builder_state.py:51-60`);
  - `get_graph()` serializes the chain of every live handle (`context.py:2557-2566`).
  - Effects: the graph depends on which Python objects are alive; review finding 7 (a transformer-result handle produces a graph that `set_graph()` crashes on at `serialization.py:170`); symbols are claimed in nondeterministic `set` order; and the `("handle", …)` keys are never removed.
- **Edge serialization:**
  - a non-converting edge is written directly (`["b", 3]`, or `{"node": [...]}`);
  - a converting edge is written as entries for every link, plus an edge from the outermost symbol. A single-link `as_celltype` into an existing cell of the same celltype is therefore saved with an entry today, where rule 5 wants a direct edge.
- **Adoption on a new name.** `_adopt_anonymous_handle` (`context.py:473`) is called only from new-name assignment (`:461`). For a pathless `as_celltype` handle whose recipe no other edge uses, it:
  - marks every sibling handle stale;
  - rewrites the incoming edge as a non-converting edge;
  - re-points the backend at `a`.

  Projection handles return early, so they already behave as rule 4 says.
- **A bug found while reading:** `_copy_subcontext` copies an edge as `Edge(new_source, new_target)` (`context.py:2683`). That drops `source_celltype` and every conversion field, so copying a subcontext loses its conversions.

## Changes

### A. Stop serializing live handles (ruling 2)

1. Delete the `live_handles` block in `get_graph()` (`context.py:2557-2566`).
2. Delete the `("handle", …)` registration in `BoundCellBackend.__init__` (`builder_state.py:51-60`). Its only reader is the block deleted in step 1.

### B. Assign symbols eagerly

1. Factor the link decomposition out of `add_anonymous_chain` into a pure function. It takes `(source_node, local_path, conversion_steps)` and the source node's celltype, and returns the chain of `(recipe, entry)` pairs, innermost first.
2. Move the suffixing logic in `symbol_for` into a `ContextGraph` method, `assign_symbol(recipe)`, which leaves an existing symbol unchanged. Move the base hash into a module-level `_symbol_base(recipe)`, so that tests can force collisions.
3. Add `Context._register_edge_symbols(edge)`. For an edge whose source has a local path or conversion steps, it assigns symbols to every recipe in the chain, in order, including single links (rule 3). Call it:
   - in `_add_endpoint_edge`, right after the edge is appended (`context.py:1195`);
   - in `set_graph`, once the edges are loaded (`serialization.py:246`), in file order. Recipes loaded from 0.5 entries already have their stored symbols. Edges from 0.4 graphs, and collapsed single links, get new ones;
   - in `_copy_subcontext`, which also needs the fix below.
4. In `get_graph()`, `symbol_for` becomes a lookup. A missing symbol is an internal error: assert on it, so that a missed call site shows up in tests.
5. **Fix `_copy_subcontext`** (`context.py:2683`): build each copy with `dataclasses.replace(edge, source=…, target=…)`, so that `source_celltype` and the conversion fields survive. Then register its symbols.

### C. Collapse dummy edges on save (rule 5)

In the edge loop of `get_graph()`, write a converting edge **directly**, with the conversion fields dropped, when all of these hold:
- its chain is a single link: one conversion step, and no local path;
- the source is a named node;
- the celltype at the target endpoint equals the converted celltype (`_celltype_for_path` for a cell or a join slot, the pin celltype for a pin).

The target then converts implicitly. That is legal, because a pathless conversion has no ordering ambiguity. Single-link projections are already written directly. The entry for the link is then emitted only if another edge or entry names it.

### D. Remove adoption (rule 4)

1. Delete `_adopt_anonymous_handle` and its call (`context.py:461`). The handle keeps its anonymous semantics, no sibling becomes stale, and `a`'s incoming edge stays a converting edge at runtime. Step C collapses it on save.
2. `_anonymous_handle_backends` then has no readers left: its current readers are `context.py:476`, `:497` and `:2559`. Remove it (`context.py:88`), along with the `_anonymous_recipe` registration (`builder_state.py:42-50`). Grep first to confirm.
3. `StaleWorkflowHandleError` remains for handles to deleted nodes.

## Contract edits

**Applied to the working tree on 2026-10-02**, docs-as-if-landed, so the code must now catch up with them. Besides the rows below, these were also changed: `cells.md:5` (a handle is a handle to a recipe), `cells.md:173-176` (an anonymous cell exists while an edge refers to its recipe, and assigning a handle creates it), and `cells.md:406` ("After a rename …" became "Assignment does not change the handle"). The line numbers below are from before the edits.

| Where | Change |
|---|---|
| `cells.md:182` *The handle creates the node* | Replace with: **A handle neither creates nor holds a node.** An anonymous cell exists while an edge, or another entry, refers to its recipe. It is created, and its symbol assigned, when the first such reference appears, and the controller removes it when the last one goes. |
| `cells.md:183` | "Handles to the same recipe share one node" becomes "References to the same recipe share one node: a second edge from the same recipe attaches to the existing entry." Keep the sentence about handles being fresh. |
| `cells.md:191` *A new name takes the anonymous cell over* | Replace with rule 4: the new node gets the handle's `celltype` and a dummy edge from the handle's anonymous cell. Nothing is renamed, no handle is invalidated, and the handle stays anonymous. The chain sentence from ruling 1 stays. Add: "`get_graph()` saves a single-link handle's dummy edge as the new node's own incoming link (*Which entries are serialized*)." |
| `cells.md:192` | Drop "whereas, had `ctx.a = x` created `a`, `ctx.d = x` would be `ctx.d = ctx.a`". |
| `cells.md:194` | Add: "A symbol is assigned when its anonymous cell is created." |
| `cells.md:226` | "so neither is taken over" becomes "so both links are saved as entries, and `a` gets an edge from the outer one". |
| `cells.md:229` *Which entries are serialized* | Add rule 5: dummy edges from single links are collapsed, while chains are saved as they are, with the reason. |
| `cells.md:88` *Copy once* | "assigned to a new name it becomes that node, or for a chain … feeds it" becomes "assigned to a new name it feeds the new node through a dummy edge, and the new node keeps the handle's `celltype`". |
| `cells.md:683` *Handle identity* | Drop the renaming sentence. Nothing now depends on a particular handle object. |
| `workflow-context.md:63` | Replace the takeover cell with rule 4. |
| `workflow-context.md:182` | Drop "or a handle to an anonymous node was invalidated because another handle to that node was assigned to a new name". |
| `workflow-context.md:236` *Handle identity* | Drop the renaming sentence. |

## Tests

All in `seamless-workflow/tests/` unless noted. Run each file in its own pytest process.

1. **Ruling 2.** Rewrite the three `*_creates_anonymous_node_immediately` tests (`test_contract_cells_handles.py` ~333-370). Each holds its handle and asserts that `get_graph()["anonymous_nodes"] == {}`. It then assigns the handle to an existing cell of a **different** celltype and asserts that the entry now appears; with a matching celltype, the edge would collapse. Add regression tests for finding 7 (a held `ctx.tf.result["x"]`, with code from a `def` function, then `set_graph(get_graph())`), and for determinism (the same graph before a handle exists, while it is alive, and after `del` plus `gc.collect()`).
2. **Rule 4.** Rewrite `test_assigning_to_a_new_name_takes_the_anonymous_node_over` (~287). Name it, for example, `test_assigning_to_a_new_name_feeds_it_through_a_dummy_edge`. Check that:
   - `x` and `y` both stay valid and read `[10, 20, 30, 40]` (this needs the prerequisite fix);
   - `get_graph()` shows no entries and a direct edge `b → a`;
   - `ctx.d = x` gives `d` its own direct edge from `b`.
3. **Rule 5.**
   - An `as_celltype` handle into an existing cell of the same celltype, and into a pin of the same celltype, saves as a direct edge with no entry. Of a different celltype, the entry is kept, as in `test_assigning_to_an_existing_name_adds_an_edge_from_the_symbol`, which is unchanged.
   - Chains keep their entries: `test_projected_as_celltype_assignment_roundtrips_through_outermost_symbol` and `test_same_recipe_shares_one_symbol_and_entries_use_tagged_refs` are unchanged.
   - Every case round-trips through `set_graph(get_graph())` with equal values.
4. **Rule 3.** Use `_symbol_base` to force two recipes to collide, and assign them in the order A, B: A gets the base and B gets `-1`. In the reverse order, the suffixes are reversed. Interleaving `get_graph()` calls changes nothing. A symbol assigned before a save is the one that appears in it.
5. **`_copy_subcontext`.** Copying a subcontext that contains a converting edge keeps the conversion: same values, and same saved form apart from the paths.

Unchanged tests to re-run: `test_cells_wiring_contract.py`, `test_contract_cells_bound.py`, `test_contract_reference_lifecycle_anonymous.py`, `test_contract_workflow_context.py`, `test_contract_mounts.py`, and the rest of `test_contract_cells_handles.py`.

## Order of work

1. The prerequisite: the handle-read fix, which has its own plan.
2. A, with test 1.
3. B, including the `_copy_subcontext` fix, with tests 4 and 5.
4. C, with test 3.
5. D, with test 2.
6. Check the code against the applied contract edits.

## Related, still separate

- **Review finding 3: binding a standalone chain.** It now gives the right value, but it is stored as a root Expression, so it is lost on reload, and the cell is `unwired` afterwards. Under rule 2 it should create edges with anonymous links, exactly like assigning the equivalent bound handle chain. Once A–D have landed, that path can reuse `_register_edge_symbols`.
