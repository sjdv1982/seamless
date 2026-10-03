# Scratch at the pin — implementation plan (ruling 4)

**Goal.** Make the code follow the rule now written in the contract pages:

- `contracts/pins.md`, *Scratch at the pin* (the public statement);
- `contracts/internal/checksum-reference-lifecycle.md`, §1 (*Input-side claims never follow the transformer's scratch*), §8 (*Buffer persistence*, *The definition write*) and the role table in §4;
- `contracts/expressions.md`, *The requester's scratch decision* (the owner row and the transformation-input row), *A value request is answered only by bytes the requester can reach*, and *Status: publication and fingertipping*;
- `contracts/scratch-witness-audit.md`, *Scratch*.

**The rule, in one paragraph.** A transformer's `scratch` governs its result only. The definition and every **literal** pin (a checksum the pin holds itself: a value serialized at assignment, a function's code, a `Checksum`) are always published. Every other pin is scratch exactly when the transformer has `allow_input_fingertip`. A scratch pin asks for a checksum (`scratch=True`); a non-scratch pin asks for a **value** (`scratch=False`, and a recorded checksum without a reachable buffer is not an answer). Every Expression that produces the pin's input carries the pin's scratch, and a non-scratch pin overrules a scratch producer: its claim publishes the producer's result, and its value request reaches a producer whose result was never written. A Context dispatches such a producer non-scratch from the start. Separately, every link of a Context edge into a **cell** carries that cell's scratch (this is the "R bug" fix).

**Tests.** `seamless1` conda env (`/home/agent/miniforge3/envs/seamless1/bin/python -m pytest`), `PYTHONPATH` = `<repo>/tests` plus all repo roots, **one pytest process per test file**. Take a frozen copy of each repo before changing it, so every new test can be shown to fail before the change.

## What the code does today

| Site | Today | Required |
|---|---|---|
| `seamless-transformer/seamless_transformer/pretransformation.py`, end of `_to_checksum` (~:298-311) | a checksum that is already a scratch ref, or any pin under `allow_input_fingertip`, is tempref-only; everything else is claimed non-scratch | literal → non-scratch claim; non-literal → scratch iff `allow_input_fingertip`. The `is_scratch_ref` branch goes: it is exactly the case where a non-scratch pin must overrule a scratch producer |
| `pretransformation.py`, `_prepare_pin_value` (two classes, ~:179-200 and ~:331-352): Expression dependency | `_evaluate_internal(execution="auto", scratch=False, materialize=False)` | scratch pin: `scratch=True, materialize=False`; non-scratch pin: `scratch=False, materialize=True` (value request) |
| `pretransformation.py`, `_prepare_pin_value`: Transformation dependency | `value._compute_dependency()`, under the dependency's own scratch | non-scratch pin: a value request with a request-level `scratch=False` (see Step 1c) |
| `seamless-transformer/seamless_transformer/transformation_class.py`, `_replace_input_role` (:392) and the increfs at ~:443, ~:448 | `scratch=self._scratch` (the Transformation's result policy) | direct (literal) inputs and envelope roles: `scratch=False`; adopted dependency inputs: `scratch=self.allow_input_fingertip` (`transformation_class.py:657`) |
| `seamless-workflow/seamless_workflow/context.py`, `_source_state` (~:1866) | `edge_scratch = target_node.kind != "transformer"`: every link into a pin non-scratch, every link into a cell scratch | pin target: the pin's scratch; cell target: `cell_config.scratch`; code target: the code pin's scratch |
| `context.py`, `_projection` → `evaluate_expression_placed` (~:1781-1795) | always a checksum request (`materialize=False`) | a link into a non-scratch pin is a value request (`materialize=True`); a link into a cell stays a checksum request. The demand key must include the request kind |
| `seamless-workflow/seamless_workflow/reactive.py:96-100` (pin conversion) | `scratch=False` | the pin's scratch, as a value request when non-scratch |
| Context claims on edge-fed pins | none: an edge-fed pin's input is held only by the source node's claim and, during a run, by the Transformation's `input:<pin>` claim | a `transformer:<path>:pin:<pin>` claim under the pin's scratch, for as long as the edge's current value stands (Step 2c) |
| Context literal pins, code, modules (`context.py` ~:741-759, :921-923, :933-946, `_sync_module_refholds`) | claimed `scratch=False` | unchanged (already right) |
| Transformer dispatch in a Context (`runtime_api._freeze_transformer`, `scratch=cfg.scratch`) | the node's own scratch | `False` when the result feeds a non-scratch pin or a non-scratch cell, directly or through cells and edges (Step 2d) |

## Step 1 — seamless-transformer

**1a. Which pins are literals.** A literal is a checksum the pin holds itself. In `PreTransformation`, that is every value that reaches `_to_checksum` without going through the Transformation/Expression branches of `_prepare_pin_value`, and the code. For a Context-built transformation, `FrozenTransformer.args` mixes literal pins (`transformer_pin_producers`) and edge-fed pins; carry a per-pin `literal` flag (or the set of literal pin names) into the `FrozenTransformer` and on to the `PreTransformation`. A `PreparedPreTransformation` built from a prepared transformation dict cannot tell; treat every input there as literal (it is a re-run of a recorded transformation, whose inputs nothing else may hold).

**1b. The claim.** In `_to_checksum`, replace the `scratch_ref` logic with `scratch_pin = allow_input_fingertip and not literal`. `scratch_pin` → `checksum.tempref()`; otherwise `checksum.incref_refholder(scratch=False)` and append to `_value_refs`. In `Transformation`, give each input role the same derived scratch (table above). Keep the definition write as it is (`_publish_definition`, non-scratch, already right).

**1c. The request.** Thread the pin's scratch into `_prepare_pin_value`:
- Expression dependency: as in the table.
- Transformation dependency: add a request-level override to `_compute_dependency` / `_compute_dependency_async` (they already take `require_value`), for example `require_value=True, scratch_override=False`, that reaches `TransformationCache.run(..., scratch=...)` and so the jobserver/Dask dispatch (`transformation_cache.py:728` passes `scratch=`). Under `require_value=True`, a recorded result whose buffer is unreachable is not an answer, so a dependency that already ran as scratch elsewhere is run again, non-scratch. The dependency's own result claim keeps its own scratch; only the request changes.
- A dependency that ran locally needs nothing extra: the pin's non-scratch claim publishes the buffer that is here (lifecycle §8, *Claim after buffer*).

**1d. `Pin.fingertip()`.** `StandalonePinBackend.fingertip` (`pin_class.py:272`) calls a bare `checksum.fingertip_sync()`. Persistence then follows whoever holds the pin's input claim. Check that the Transformer builder holds a non-scratch claim for a non-scratch pin's input (it does for literals; for an Expression- or Cell-fed pin there is no builder-level claim) and add one if needed, so that `pin.fingertip()` persists exactly when the pin is non-scratch.

## Step 2 — seamless-workflow

**2a. Edge scratch.** Replace `edge_scratch` in `_source_state` with a helper `_edge_target_scratch(target_node, target_local)`:
- cell target → `node.cell_config.scratch`;
- transformer pin or code → `not literal and transformer_config.allow_input_fingertip` (`builder_state.py:996` stores it in `cfg.meta`); an edge-fed pin is never a literal, so this is `allow_input_fingertip`.

It applies to **every** link of the edge, the deep step (`_evaluate_deep_step`) included: an Expression never fingertips its input (`seamless-core/seamless/checksum/expression.py`, "Recovering it is fingertip's job"), so a non-scratch last link can only be evaluated where the earlier links left their results reachable. The anonymous-node claims (`anonymous:<symbol>:current`, `(checksum, True)` at ~:1447) stay scratch: the dispatch writes on the target's behalf, and the intermediates stay unheld.

**2b. Value requests into non-scratch pins.** `_projection` gains a `materialize` argument (or a request kind), passed to `evaluate_expression_placed`, and included in the demand key next to `scratch`. A link into a non-scratch pin passes `materialize=True`; every other link `False`. `reactive.py:96-100` does the same for the pin conversion.

**2c. Context claims on edge-fed pins.** Hold the converted input of each edge-fed pin under `transformer:<path>:pin:<pin>` with the pin's scratch, released when the edge's value changes or the edge goes. Report it in `_refheld_checksums` (~:1319) like a literal pin's claim. This is what makes "a non-scratch pin holds its input under a non-scratch claim" true in a Context, and it keeps the published input from being an unheld write that nothing protects.

**2d. Producer dispatch.** In the reactive layer, compute a transformer's dispatch scratch as `cfg.scratch and not feeds_non_scratch_consumer(path)` (`contracts/cells.md`, *Scratch policy*: a non-scratch cell overrules a scratch transformer too), where `feeds_non_scratch_consumer` follows edges from the transformer's result through cells (identity or Expression edges, anonymous nodes included) and is true if any cell it reaches is non-scratch, or any transformer pin it reaches is non-scratch. Pass it as `FrozenTransformer.scratch` for the dispatch only; the node's result claim (`node:<path>:current`) keeps `cfg.scratch`. Recompute it when edges or `allow_input_fingertip` change; a change does not by itself invalidate a completed result (the pin's value request covers a result that was never written).

**2e. Comments.** Update the comments that cite the old rule: `context.py` ~:1864 ("A transformer's pin or code edge is input-side…"), `reactive.py:97`, `pretransformation.py` ("Input-side: a dispatched input is written by the executing side; any recorded checksum answers (lifecycle §1)").

## Step 3 — tests

**Change (they pin the old rule):**
- `seamless-workflow/tests/test_contract_reference_lifecycle_scratch.py` and `test_contract_scratch_transformer_remote.py`: the old §10 gap ("a scratch transformer's pin, code and module claims do not publish"). Rewrite them against the new rule; the code-checksum `CacheMissError` case must pass.
- `seamless-transformer/tests/test_transformer_reference_lifecycle.py::test_literal_pin_is_published_whatever_the_transformer_scratch` stays; check its siblings for assertions on `is_scratch_ref` behaviour.
- Grep all repos' tests for `edge_scratch`, `is_scratch_ref`, `allow_input_fingertip` and "input-side" and re-check each hit.

**Add** (each docstring quotes `pins.md`, *Scratch at the pin*):
1. Standalone and bound: a literal pin of a scratch transformer with `allow_input_fingertip` is published.
2. Standalone and bound: a Cell-/Expression-fed pin is published without the opt-in, and not with it.
3. The overrule, local: a scratch producer's local result feeding a non-scratch pin is published; with the opt-in it is not.
4. The overrule, dispatched (fake remotes, as in `seamless-workflow/tests/test_contract_handle_reads.py`): standalone, a scratch dependency that already ran remotely is run again non-scratch and the consumer succeeds; bound, the producer is dispatched once, with `scratch=False`, and the consumer succeeds.
5. Through a conversion: the Expression into a non-scratch pin is a value request (`materialize=True`), and a dispatched link writes its result.
6. A chain into a non-scratch **cell**: every link is dispatched `scratch=False`; into a scratch cell, every link `scratch=True` (the R bug).
7. `pin.fingertip()` persists exactly when the pin is non-scratch.
8. Two consumers of one scratch result, one with the opt-in and one without: the result is published once, and the fingertipping consumer's claim is scratch.

## Step 4 — full suites

seamless-core, seamless-transformer (including `dask/` and `persistent/`), seamless-workflow, seamless-dask; one file per process.

## Open points for the author (not decided by this plan)

- **1a, prepared transformation dicts:** treating every input of a `PreparedPreTransformation` as literal publishes inputs of a re-run that was not asked to publish anything. The alternative is neutral (tempref-only) claims there. Which?
- **2c:** whether the Context should hold edge-fed pin inputs between runs (this plan says yes) or only during a run.
