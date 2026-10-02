# Outstanding issues from the 2026-10-01 commit review — plan

**Scope.** Everything still open from the review of the commits after 2026-10-01 15:00 (14 findings, nits, "plan items still unimplemented"), plus what the four fix agents of 2026-10-02 reported but did not fix. Rulings 1–6 of the review are handled elsewhere: 1–3 and 6 are done, ruling 4 has its own plan (`pin-scratch-implementation-plan.md`), ruling 5 is in `NEW REGISTER.md`.

**Status check.** Each item below was re-checked on 2026-10-02 against the tree as the fourth agent left it (handles follow their parent, miswiring derived through `ContextGraph.edge_miswiring`, dummy edges looked through), by a probe or by reading the code. The third agent has since finished its three deep-handle items (garbled refusal message fixed; `ctx.x = ctx.d` into an `int` cell now refused with `ValueError`; the write-at-`k` notes were stale and are deleted from `deep-celltypes.md` and `cells.md`, together with the stale bound sub-path write notes, after a probe).

**Already resolved, no action:** finding 1 and 2 (void after ruling 1), 4 (ruling 3), 7 (ruling 2: live handles are not serialized), 10 (probe: a named consumer's `build()` gives `(root, "a.b")` live and after a reload), the validator TODO nit (all three entry points carry it), the end-to-end deep-barrier test (third agent), and "a bound projection handle is still a view" (now the contract: handles create nothing).

**Tests.** `seamless1` conda env, `PYTHONPATH` = `<repo>/tests` plus all repo roots, one pytest process per file, a frozen copy before each change, and every new test shown failing on the frozen copy.

## Phase 0 — rulings needed first

Each has a lean. Phases 2–4 implement the lean unless you rule otherwise.

| # | Question | Source | My lean |
|---|---|---|---|
| R1 | A handle's `compute()` after a recorded failure evaluates again, while its reads stay `None` until `clear_exception()`. Is that the "automatic retry" the contract forbids? | handle-read agent | Not a retry: `compute()` is an explicit request for work, as standalone `Cell.compute()` is. State it in `cells.md`, *Failures* |
| R2 | A handle over an unwired parent reports `waiting`. | handle-read agent | `unwired`, as a named cell fed by that parent would report |
| R3 | A defective **single** link (looked through, saved as the target's own edge) makes its target `miswired`; a defective **chain** makes the anonymous cell `miswired` and its consumers `blocked-by-miswiring`. | fourth agent, deviation 1 | Accept: after a reload the single link *is* the target's edge, and live must equal reload. Add the distinction to `cells.md`, *The handle and the node* |
| R4 | `get_graph()` keeps an ill-formed single deep link as an entry plus an edge, instead of collapsing it, because the collapsed form would reload as a legal link and silently repair it. | fourth agent, deviation 2 | Accept. Contract: "a single link is collapsed unless the collapsed form would read differently" |
| R5 | Standalone, a Cell's getters evaluate a chain's intermediate links as scratch, while `Cell.compute()` passes the owner's scratch to every link. | handle-read agent, ambiguity 2 | Every link carries the owner's scratch, in both, as ruling 4 now says for Context edges: an Expression never fingertips its input, so a dispatched non-scratch last link needs its input reachable |
| R6 | Ruling 5 (client-side record after a dispatch). | `NEW REGISTER.md` | Queued, best-effort (see the register) |
| R7 | The wiring-refusal message offers only the spellings that are legal: for `ctx.x = ctx.d["member"]` into a `checksum` cell it names only `ctx.d["member"].as_celltype("checksum")`, because `ctx.d.as_celltype("checksum")` is illegal. `cells.md`, *Connecting*, says the message names both spellings. | third agent | Accept; *Connecting* says "the legal ones of the two spellings" |

## Phase 1 — seamless-core

**1a. Finding 11: a failed queued write blocks `flush()` and `close()` forever.** `seamless/caching/buffer_writer.py`: `_process_entry` (~:385-410) leaves a failed entry in `_entries`; `_register_metadata` (~:111) then deduplicates every later record of the same key away; `flush()` (~:166) calls `entry.future.result()` on it and raises, before the buffer flush and `_stop_worker` (`shutdown.py`). Fix: a failed metadata entry is retried a bounded number of times with backoff, then removed and logged at error level; `flush()` reports failures (log, or one aggregated exception after draining everything) but always drains the rest and lets `close()` finish. Ask the author whether `flush()` should raise at all after a failed identity write; recording "must keep happening" (`expressions.md`, *Recording identity*), but a closing process cannot do more than report.

**1b. Ruling 5, if ruled per the lean.** `_execute_remote_expression` (`checksum/expression.py`, ~:650-660): replace the inline `database_remote.set_expression_result` with `_record_expression_result`. Do this together with the fingertip-categories plan's Step 4, which rewrites the same writes (insert-if-absent, mismatch logged and returned unrecorded). Then `test_contract_expressions.py::test_expression_result_registration_failures_are_visible` (finding 13) must be re-read: it pins that a failure to *queue* a record raises, which is a programming error and may stay; it must not be read as "a failed database write fails the evaluation". Update `expressions.md:111` and `:228` as the register says.

**1c. Finding 12: the synchronous member set.** `evaluate_expression_local` (`checksum/expression.py`, ~:156-215):
- a free Expression (no buffer needed: *Cost class*) must return before the member set is consulted (`expressions.md`, *Deduplication*: "never become members");
- the member id must be the caller's (`id(self)` for a standalone `Expression`, the demand key for a Context), threaded in, with `object()` only for the anonymous callers the contract lists;
- the `RunningLoopRefusal` raised when the same identity is in flight on the running loop: check it against `expressions.md` (`compute()` "evaluates only when the location is local") and against `cells.md` ("a running-loop refusal is not a failure"). If the contract allows the refusal there, state it; otherwise evaluate unshared, as the materialize path already does.

**1d. Finding 13, the other half.** The docstring of `test_sync_local_evaluation_joins_member_set_between_threads` (`tests/test_contract_expressions.py:445`) claims sync and async callers share work but tests only sync with sync. Add a sync-joins-async and a sync-joins-dispatch case (the ruling-3 tests cover only the materializing caller).

**1e. Nits.** `seamless/expression_class.py` docstrings at ~:205, :216, :247 still say "publish" (they mean record or tempref). In `seamless-dask/tests/test_expression_inputs.py` (:70, :109, :142), the stub that replaces `evaluate_expression_placed` is named `evaluate_expression_local`.

## Phase 2 — seamless-workflow: `build()` and handle methods never do work, and build the contract's Expression

These findings share one cause: `build()` assembles its Expression by its own logic, which evaluates intermediate conversions and fuses differently from the derivation and from handle reads. Rewrite it once.

- **Finding 6 (probe-confirmed):** `ctx.b.as_celltype("plain")[3].build()`, on a handle and on a named node alike, leaves the `text→plain` Expression in the process cache: `build()` evaluated it (`_build_conversion_expression` and `project()` call `.compute()`). Contract: `cells.md`, *Work*: `build()` does no work. It runs on the controller loop, ignores `expression_execution`, raises `RunningLoopRefusal` when the parent's buffer is not here, and blocks the controller when it is.
- **Finding 8 (probe-confirmed):** for `ctx.b["x"].as_celltype("plain")["y"]` (`b` mixed), `build()` returns the single fused `(b, "x.y", mixed, plain)`, while the node evaluates two links. Contract: `expressions.md`, *Fusion*: a conversion that follows a path closes the run.
- **Finding 9 (probe-confirmed):** for a plain cell `a` set with `set_checksum(cs, input_celltype="text")`, `ctx.a.as_celltype("mixed").build()` returns `(cs, "", text, mixed)`, i.e. `text→str`, instead of `(cs, "", plain, mixed)`. The run must be rooted at the node's own checksum and celltype.
- **Handle `build()` fuses upstream through named nodes** (handle-read agent, item 6), so its identity can differ from the Expression its reads evaluate over the parent's checksum.
- **`fingertip()` on a handle forces the handle's evaluation** (handle-read agent, item 7). Contract: `fingertip()` never forces `.checksum`.

**The fix.** `build()` returns the chain as nested Expressions, each link's input being the previous link's Expression (an Expression input is a legal identity: `("expression", …)`), rooted at the node's own current checksum and celltype, decomposed with the same function the derivation and the handle reads use (`graph.anonymous_links` plus the fusion rules), and never evaluated. A named consumer fuses through its source exactly as the derivation does, no more. `fingertip()` on a handle fingertips the handle's recorded result checksum, or returns `None` when there is none, as `Pin.fingertip()` does.

**Tests:** one test per bullet above, each asserting the returned identity and that the Expression cache is unchanged by `build()`; the probes in this session's scratchpad (`test_zz_probe_review.py`) are a starting point.

## Phase 3 — seamless-workflow: the derivation evaluates the contract's chain

- **Finding 14, now worse than reported (probe-confirmed).** `_projection` (`context.py`, ~:1802-1805) short-cuts an empty-path `text→mixed` with `checksum.resolve("mixed")`:
  - it records nothing, so fingertipping cannot recover the result;
  - it gives the **wrong value**: `text→mixed` is `=text→str` (`celltypes-and-conversion.md`, the matrix and *Composition is not associative*), but `resolve("mixed")` parses the text as JSON, so `"[1, 2]"` gives a list instead of the string;
  - for text that is not JSON it **raises out of the derivation**: `ctx.m = Cell("mixed"); ctx.m = ctx.t`, with `t` the text `"hello world"`, raises `HashTypeValidationError` from the assignment itself.

  Fix: delete the shortcut; the ordinary Expression path handles the pair. Also make sure no conversion error can escape `_derive_all` (the third agent saw the same class of crash, `ControllerFailedError`, for deep conversions): a conversion failure is the node's `failed` state.
- **Finding 5 (probe-confirmed):** `ctx.r = ctx.t.as_celltype("plain")["a"]["b"]` evaluates `(t, "", text, plain)`, `(P, "a")`, `(A, "b")`; path + path must fuse to `(P, "a.b")` (`expressions.md`, *Fusion*), as `build()` already does. Fix in `_source_state`'s conversion-step loop (~:1940-1990): after a conversion, consecutive path segments form one projection.
- **The `mixed→plain` elision** in `_source_state` (`elided = current_type == "mixed" and converted_type == "plain"`) and in `_build_cell_expression`, which the bound-fusion plan left for later. It projects at `mixed` and relabels the result `plain` with no Expression and no validation. `mixed→plain` is a reinterpret (RI): validated, and it may raise (`{"x": np.arange(3)}` is not plain). Either evaluate it as the Expression it is, or keep the elision only where HashType proves the plain reading, recording the identity either way.
- **Finding 3 (probe-confirmed): binding a standalone chain.** `ctx.c = s["a"]`, with `s` a standalone Cell, stores a root Expression on the node (`ingress.py` ~:53-66, `context.py` root-expression branch). `get_graph()` writes no edge and no anonymous entry for it, so after `set_graph(get_graph())` the cell is `unwired`. It is evaluated by a bare `expression.compute()` (scratch whatever the node's policy, and on the controller loop). Contract: `cells.md`, *Binding*: every intermediate link of a bound standalone chain becomes an anonymous cell. Implement that: the chain's root becomes the cell's literal input (or its source, if it is bound), each link an anonymous node with an eagerly assigned symbol, through the same `register_edge_symbols` path as `ctx.a = ctx.b[...]`.

## Phase 4 — seamless-workflow: wiring and reporting

- **`.source` on an edge that is not looked through** (fourth agent, 5a): from an anonymous cell it returns the bare node handle without the conversion, so for an existing `str` cell fed by `b.as_celltype("plain")`, `.source.celltype` is `mixed` while `input_celltype` is `plain`. Contract: `cells.md:122`, "one lookup". `.source` must return the link's handle, whose celltype is `input_celltype`.
- **A legal retype is refused** (fourth agent, 5b): after `ctx.a = ctx.b["x"].as_celltype("plain")`, retyping `a` raises `TypeError`, because `_publish_config` checks the source *path* rather than the outer link, which is a pathless conversion. Fix the check to look at the outer link.
- **Join slots** (fourth agent, 4): a join reports a miswired member as `blocked` / `{"k": "blocked-by-miswiring"}`; this is the existing `_apply_pending` gap that `cells.md:505` records. Fix it there, with the scalar-vs-dict reporting the same note describes.
- **`compute(timeout=…)` on a handle inside a running loop** evaluates in place, so the timeout does not apply (handle-read agent, item 5). Either bound it or state in `cells.md` that a timeout bounds only waiting.
- **R1, R2** as ruled.
- **`set_checksum(cs, input_celltype=X)` on a sub-path does not convert (new, probe-confirmed, both modes).** On a `plain` cell, `p = a["b"]; p.set_checksum(cs_text_7, input_celltype="text")` inserts the string `'7'`; the contract (`cells.md`, *Writes through a handle*) says it converts from `X` to the handle's celltype first, which gives `7`. Standalone in `seamless-core/seamless/cell_class.py`, bound in `ingress._edit`.
- **Standalone refusal message** (third agent): `_check_projected_source` in `seamless-core/seamless/cell_class.py` still falls back to the old short text for string-keyed paths, deep ones included, and glosses "(a character)" for `plain` sources. Bring it in line with the bound `_projected_source_type_error`.
- **Conversion order at one position** (third agent): `graph.anonymous_links` sorts conversion steps by `(position, celltype)`, so `ctx.b.as_celltype("text").as_celltype("str")` is recorded as `str → text`. Sort stably by position, as `split_deep_step` now does. This changes the symbols of such chains in saved graphs, which have the wrong recipe today anyway.
- **Dead parameter:** `BoundCellBackend` still passes `_handle_id` to `_build_cell_expression(_handle_id=…)`, which ignores it.

## Phase 5 — contract pages

- Write rulings R1–R7 into the pages.
- **Sweep every "Contract ahead of code" note** against the current tree. Several are probably stale after today's work, e.g. `cells.md:122` (`input_celltype` drops the local path), `cells.md:165` ("bound cell targets are not checked at all … a cell consumer is never derived `miswired`"), (the write-at-`k` and bound sub-path write notes are already deleted). Delete the stale ones. For the live ones, your rule is that code lag belongs in plan files; say whether to move them all into a plan file, or leave the existing ones and apply the rule to new text only.
- `contracts/internal/checksum-reference-lifecycle.md` §10 still has a **"Fixed."** list, a fix record. Delete it.

## Order of work

1. (Done: the third agent's deep-handle items.)
2. Phase 2, then Phase 3, in one agent: both rewrite the same parts of `context.py` and `builder_state.py`.
3. `pin-scratch-implementation-plan.md` Step 2 (it changes `_source_state` and `_projection` again; do it after Phase 3), with its Step 1 in seamless-transformer in parallel.
4. Phase 4.
5. seamless-core: the fingertip-categories plan with Phase 1 folded into its Step 4 (same functions).
6. Phase 5, then every touched repo's full suite, one file per process.
