# Bound fusion gapfix: implementation plan

The contract docs already describe the fixed state. The "contract ahead of code" paragraph at the end of *Fusion* in `docs/agent/contracts/expressions.md`, and its *Implementation status* item, have been removed.

Scope: `Context._fused_projection_source` in `seamless-workflow/seamless_workflow/context.py` (~2316). It has two callers: `_derive_cell` (~1477) and `_build_cell_expression` (~2205).

## The defects

All the cases below were probed on 2026-10-01 with `Expression.__post_init__` monkeypatched to record every Expression built. The defects show up only for **named** intermediates. Anonymous chains go through `_build_cell_expression` and already fuse and elide correctly.

### 1. The walk gives up where it should stop

When the walk reaches a node it cannot pass through, it returns `None`. The consumer then falls back to a one-edge projection over its direct source, so nothing fuses at all. The walk should instead stop at that node and use the node's own current checksum as the root of the run.

| Chain (`ctx.r` is the consumer) | Expressions built today | After the fix |
|---|---|---|
| constant root, named intermediate `ctx.mid = ctx.root["a"]; ctx.r = ctx.mid["b"]` | `a`, `a.b` | `a`, `a.b` |
| constant root, anonymous intermediate `ctx.r = ctx.root["a"]["b"]` | `a.b` | `a.b` |
| transformer-fed root (`ctx.root = ctx.tf`), named intermediate | `a`, `b` | `a`, `a.b` |
| transformer-fed root, anonymous intermediate | `a.b` | `a.b` |
| `text` cell → named `plain` cell `p` (a reformat edge), `ctx.m = ctx.p["a"]; ctx.r = ctx.m["b"]` | `''`, `a`, `b` | `''`, `a`, `a.b` |

In the "after" column, the named intermediate still builds its own `a`, because a named node is never elided. The consumer builds `a.b` over the checksum of the node where the walk stopped. From the code, a join node and a cell with a root Expression upstream give up in the same way. These two were not probed.

### 2. A root cell with a different input celltype is projected before its conversion

For a cell with a root producer, the walk returns `producer.checksum` and `producer.celltype`. That is the input *before* the cell's own conversion. The path is then walked over the unconverted value:

```python
ctx.a = Cell("plain")
ctx.a.set_checksum(text_checksum, input_celltype="text")   # '{"x": {"y": 4}}'
ctx.m = ctx.a["x"]
ctx.compute()
# ctx.a.value == {'x': {'y': 4}}
# ctx.m: failed, "Illegal path step ('item', 'x') in 'x' for text"   (a single hop)
```

This breaks *project, then convert*. `text → plain` produces a new buffer, so it is a fusion barrier, and the run must start at `a`'s own converted checksum. A checksum-preserving input conversion (such as `mixed` input under a `plain` cell) only works by accident: the checksum is the same, and so is the value.

## The fix

Rewrite the walk so that it remembers the last node that can root the run, and stops where it cannot continue:

```python
_DEEP_CELLTYPES = {"deepcell", "deepfolder", "folder"}

def _fused_projection_source(self, node_path, local):
    """Root of the maximal fusible run that ends in projecting `local` from `node_path`.

    Returns (root checksum, root celltype, concatenated path), or None when
    `node_path` has no current checksum. The walk passes upstream through cell
    nodes fed by one non-converting, same-celltype root edge, and stops at the
    first node it cannot pass through: the run is rooted at that node's own
    current checksum, at that node's own celltype.
    """
    node_path, path = tuple(node_path), tuple(local)
    root, visited = None, set()
    while node_path not in visited:
        visited.add(node_path)
        node = self._graph.nodes[node_path]
        checksum = node.current_checksum
        if node.kind != "cell" or checksum is None:
            break
        celltype = self._node_celltype(node_path)
        root = (checksum, celltype, path)
        incoming = self._incoming_for(node_path)
        edge = incoming.get(())
        if edge is None or len(incoming) > 1:  # a root cell, or a join
            break
        if edge.source_conversion or edge.source_conversion_steps:
            break  # an explicit conversion closes the run
        source_path, source_local = self._graph.resolve_existing(edge.source)
        if self._graph.nodes[source_path].kind != "cell":
            break  # e.g. a transformer output: the run starts at this cell
        source_type = edge.source_celltype or self._celltype_for_path(source_path, source_local)
        if source_type != celltype:
            break  # an implicit conversion closes the run
        if source_local and self._node_celltype(source_path) in _DEEP_CELLTYPES:
            break  # a deep step is a barrier
        path = tuple(source_local) + path
        node_path = source_path
    return root
```

Notes:

- **Defect 2 goes away by construction.** The root is always a node's own current checksum at that node's own celltype, never `producer.checksum` / `producer.celltype`.
- **A checksum-preserving conversion needs no special case.** The walk stops at the converted node, whose checksum equals its source's. So `(that checksum, path, converted celltype, celltype)` is exactly the identity the contract's "absorb into `input_celltype`" rule gives.
- **Graceful degradation.** The first iteration roots the run at the direct source itself. "Nothing to fuse" therefore yields today's one-edge projection, not `None`. Both callers keep working unchanged. `None` now means only that the direct source has no checksum, and `_derive_cell` calls the walk only once that source is `complete`.
- **Checksum accessor.** Use `node.current_checksum`, as `_derive_cell` does for the direct source. Check that it is set for a `complete` cell whose root is a producer.
- **Anonymous symbols on the walk.** `resolve_existing` already resolves an edge source that names an anonymous symbol. Keep that.
- **Out of scope.** The `mixed → plain` special cases in `_build_cell_expression` (~2160–2190) serve the anonymous path, which already works. Leave them for now. Once the named path is fixed they may turn out to be redundant.

## Tests

In `seamless-workflow/tests/test_cells_wiring_contract.py`:

1. **Parametrize `test_named_and_anonymous_intermediates_fuse_identically` over root kinds:** constant; transformer-fed; a named `plain` cell fed by a `text` cell (reformat barrier); a named `plain` cell fed by a `mixed` cell (checksum-preserving); a join cell; a root cell set with `input_celltype="text"`. For each, assert:
   - the named consumer's `build().identity_key` equals the anonymous consumer's;
   - the recorded Expressions contain the fused path, and never the bare tail path (`"b"`);
   - the values are equal.
2. **Regression test for defect 2:** a single hop over a root cell set with `input_celltype="text"` yields the projected value.
3. **Extend `test_only_anonymous_fusible_intermediates_are_elided`** with the transformer-fed root.
4. **Deep barrier.** It cannot be tested end to end yet: `ctx.d["member"]["x"]` over a `deepcell` comes out `miswired`, and its named form is `blocked`. That is the known gap that a bound handle one step below a deep parent keeps the deep celltype (`contracts/cells.md`, *Implementation status*). Add the bound deep test when that gap closes. Until then, rely on the walk's explicit barrier check and on the Expression-level test `test_deep_step_is_a_fusion_barrier`.

Run every seamless-workflow test file that mentions projections or Expressions, one pytest process per file.

## Found while verifying, out of scope here

- **Binding a standalone chain silently drops its path.** `s = Cell("mixed"); s.set({"a": [1, 2]}); ctx.c = s["a"]` gives `ctx.c.value == {'a': [1, 2]}`; the same happens with `s["a"].as_celltype("plain")` and with `s.as_celltype("plain")["a"]`. The graph shows auto-named nodes (`cell1`, `cell2`), an edge `source: ['cell1']` with no path, and no `anonymous_nodes`. The contract (`contracts/cells.md`, *Anonymous cells*) says the intermediates become anonymous cells. The result is a wrong value with no error. Binding also trips the reference lifecycle: `Checksum … has refholder count 0 but 1 live claims` (`Cell … input`, "A reference was not acquired or was released by code that did not own it"), then `Refholder decref ignored … refholder count is already zero`. The bound cell probably takes over the standalone Cell's input reference without acquiring its own. Fix it together with the path loss.
- **A bound projection handle is still a view, not a node.** `ctx.b["a"]` is a `BoundCellBackend` with a `local_path` (`builder_state.py`). Its anonymous node is created only when the handle is assigned: with live handles, `get_graph()["anonymous_nodes"]` is `{}`. The contract says that "the handle creates the node". A bound `as_celltype` *is* now a bound handle (`BoundCellBackend.derive` with conversion steps), no longer a standalone snapshot.
- **Stale `contracts/cells.md` notes, now removed.** The *Connecting* block "Contract ahead of code — bound Cells only", the *Contract ahead of code* sentence in *Binding*, and the two *Implementation status* bullets ("The model is not implemented" and "`Cell(source=<handle>)` is accepted") have been deleted. Verified first: capturing a projection or `as_celltype` handle with `Cell(source=…)` raises `DependencyError`, assigning either kind into another Context raises `DependencyError`, and a bound `as_celltype` assigns into its own Context.
