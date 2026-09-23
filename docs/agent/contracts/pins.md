# Pins (Contract)

**A Pin is a Transformer's input slot, and the sister class of Cell.** `Pin` and `Cell` share `CellBase` — the value, type, evaluation and ownership API — but `Pin` is *not* a subclass of `Cell`. A Pin is a **deferred Expression** in exactly the sense `contracts/cells.md` defines, `(input, input_celltype, celltype)`, with one difference that shapes everything else: its output is consumed by one Transformer rather than by the graph. The Transformer that owns the pin collection, snapshots it and may be bound to a workflow node is `contracts/transformers.md`.

Everything a Pin shares with a Cell is in `contracts/cells.md` and is **not repeated here**: the two write families and their authority rule, the `.source` / `.checksum` split, the value / buffer / checksum matrix, the "a `Checksum` is a value only for celltype `checksum`" rule, the read and materialization pipeline, and how a failure sticks to the handle until it is cleared. This page states what is Pin-specific — routing to a Transformer, which pins exist, the null rules of features 6 and 7, conversion at the pin boundary, and the ways a Pin is deliberately narrower than a Cell.

The modes are the same two:

- **standalone** — the state is private to the Transformer object;
- **bound** — the state is owned by a workflow `Context` node, and the Pin handle is a *view* onto it.

`tf.pins.x` returns a **fresh handle** every time — standalone, compiled and bound alike, and including for a declared-but-unwired pin, which reads as an unwired Pin and never as `None`. Handle identity carries no meaning.

Being a separate class is load-bearing: `isinstance(pin, Cell)` is false, so every existing source check refuses a Pin **by type** rather than by a per-site check (see *A Pin is not a source*).

Code locations:

| Concern | Module / symbol |
|---|---|
| Shared value/type/evaluation/ownership API | `seamless.cell_class.CellBase` |
| Pin handle | `seamless_transformer.pin_class.Pin` (a thin subclass of `CellBase`) |
| Standalone pin state and reads | `seamless_transformer.pin_class.StandalonePinBackend` |
| Pin storage on a standalone transformer | `seamless_transformer.transformer_class.ArgsWrapper` |
| Pin celltypes | `seamless_transformer.transformer_class.CelltypesWrapper` |
| Optional-pin drop and the null rules | `seamless_transformer.transformation_utils` (`normalize_optional_pins_for_construction`, `validate_pin_null`, `json_null_checksum`, `sufficiently_connected`) |
| Call-time argument conversion | `seamless_transformer.transformer_class.TransformerCore._convert_pin_arguments` |
| Null results | `seamless_transformer.run` |
| Bound pin handle and writes | `seamless_workflow.builder_state` (`BoundPinBackend`, `WorkflowTransformerPins`, `BoundTransformerBackend`) |
| Bound pin derivation, blocking and conversion | `seamless_workflow.reactive.Reactive._derive_transformer` |
| Bound snapshot conversion | `seamless_workflow.runtime_api` (`_snapshot_transformer`) |
| Pin writes through the controller | `seamless_workflow.context.Context._set_transformer_pin` |

## Reaching pins

**`tf.pins.x` is the only pin path.** `tf.args.x` is an exact alias: `args` and `pins` are the same object in both modes (*Verified:* `TransformerCore.pins` returns `self.args`; `BoundTransformerBackend.args` returns `self.pins`). Prefer `.pins` in new code.

The old sugar is **gone**: there is no `tf.x` and no `tf["x"]`. Attribute assignment on a Transformer raises `AttributeError` whose message names the replacement — `'<T>' object has no attribute 'x'; transformer input pins are reached as .pins['x']` — and a Transformer has no `__getitem__` at all. The removal was driven by the Context's name-collision problem: a pin name could otherwise collide with any API member of the handle.

- `tf.pins.x` for a name that is not a declared pin raises `AttributeError`. `tf.pins["x"]` is the same operation; the item form is not an escape hatch.
- **`result` is never a valid pin name.** `tf.pins.result` raises `AttributeError`, as do `tf.pins["result"] = v` and `del tf.pins["result"]`. `result` is the *output* celltype slot, `tf.celltypes.result` (below), and on a **bound** transformer `tf.result` is the result handle, not a pin.

**One pin has one producer.** A pin holds exactly one input — a literal checksum, or one connection. It therefore never faces the root-literal-plus-sub-path-edges ambiguity a Cell can face, and `pin.source` and `pin.checksum` answer unambiguously: `pin.source is None` means "nothing upstream feeds this pin", `pin.checksum is None` means "not complete", with no path to walk up in search of the responsible edge.

## Which pins exist

| Transformer code | Pin set |
|---|---|
| a Python callable | **fixed** by the signature |
| signature-less code (text / bash-style) | **declared** by the user |

- With a **Python callable** the signature fixes the pin set: a name outside the signature is rejected, and `del tf.pins.x` raises. (`ArgsWrapper` and `CelltypesWrapper` call this the *fixed* state.)
- With **signature-less code** the user declares the pins, so `tf.pins.x = v` or `tf.celltypes.x = ct` **creates** the declaration, and `del tf.pins.x` / `del tf.celltypes.x` **removes** it. Deleting a declaration removes the pin from `pins`, from `celltypes` and from `optional_pins`, and clears its input.

`del` therefore means "the declaration is gone", never "empty it". Clearing a pin's *input* while keeping the declaration is `pin.checksum = None` (below). This is the same `del`-versus-clear split `contracts/cells.md` states for Cells, and **both modes now behave identically**: the bound `del ctx.tf.pins.x` that used to clear the producer is retired.

## Celltypes

**`pin.celltype` and `tf.celltypes.x` are one setting**, settable from either side and linked in both directions. The Transformer owns the storage; the Pin stores none. The setter validates and normalizes the name, and accepts a Python type, reducing it to its name (`int` → `"int"`).

**`pin.input_celltype` is read-only** and comes from the input, by the same rules `contracts/cells.md` gives for a Cell:

| The input is | `input_celltype` is |
|---|---|
| a typed reference (Cell, Expression, Transformation, bound endpoint) | that reference's own `celltype`, read **live** — retyping a source Cell changes the pin's `input_celltype`, and an `Expression` has resolved its own once, at construction |
| a value, written as `tf.pins.x = v` or `pin.set(v)` | the celltype it was serialized in — the pin's `celltype` at that moment |
| a bare `Checksum` | the celltype declared with it (`pin.set_checksum(cs, input_celltype=…)`), defaulting to the pin's `celltype` |
| absent | `None` |

Which celltypes are accepted depends on the slot (*Verified:* `CelltypesWrapper.__setitem__`):

| Slot | Accepts |
|---|---|
| an **input pin** | every ordinary celltype, plus `deepcell`, `deepfolder`, `folder` and `module` |
| the **result** | every ordinary celltype, plus `deepcell` and `folder`; `deepfolder` and `module` are rejected with `TypeError` |

Setting `pin.celltype` **resets the pin's memoized result and its recorded exception**, so a retype re-derives from the stored input rather than reinterpreting it.

## Pins hold checksums, never values

`tf.pins.x = v` is the same operation as `tf.pins.x.set(v)` except for the authority check (below).

- A **literal value is serialized immediately**, with the pin's `celltype`, and the pin stores the resulting checksum plus the celltype it was serialized in. An invalid value raises **at assignment**, exactly as `Cell.set` does; standalone and bound agree on this.
- A **typed reference** — a `Cell`, an `Expression`, a `Transformation`, a bound endpoint — is stored as a reference and is not resolved.
- **A `Checksum` is a value exactly when the pin's celltype is `checksum`**; for every other celltype a `Checksum` is read as a declared input reference. This is the single rule `contracts/cells.md` states, unchanged at a pin.

**Pin storage never holds a raw Python object.** (The pre-rename implementation stored Python objects on the standalone path and resolved them in whatever celltype they had been stored in, which went stale after a retype. That is gone.)

## Writes: the same two verb families

The vocabulary, and the reason for the split, are in `contracts/cells.md`; only the pin spellings are given here.

| Family | Spellings on a pin | On a connected pin |
|---|---|---|
| **Declare the input** | `tf.pins.x = X`, `pin.value =`, `pin.buffer =`, `pin.checksum =` (including `= None`) | **make it so** — replaces the producer or the edge |
| **Write what you own** | `pin.set()`, `pin.set_buffer()`, `pin.set_checksum()` | **check** — `AuthorityError` |

The standalone `AuthorityError` message is: `The pin is controlled by a source; assign .value, .buffer or .checksum to replace it`.

- **Clearing.** `pin.checksum = None` — and equally `pin.buffer = None` and `pin.set_checksum(None)` — removes the input and keeps the declaration. The pin then reads as `unwired`, and the transformer is blocked on it.
- **Null.** `pin.value = None` and `pin.set(None)` store the **null value**, which for a required pin is legal only for celltypes `plain`, `mixed` and `bytes` (below). The `= None` / clear / `del` distinction is exactly the one `contracts/cells.md` draws.
- **A pin has no sub-path.** There are no sub-pin targets and no projections, and therefore no sub-path writes and no augmented assignment.

## Null, required pins, optional pins

**One representation.** Absence and the null value share the canonical JSON-null checksum (`b"null\n"`, `38e0b9de…`), which is celltype-independent and trivially resolvable; see `contracts/celltypes-and-conversion.md`. Empty bytes under celltype `bytes` **canonicalize to null before any pin rule is applied** (*Verified:* `normalize_optional_pins_for_construction` and `Reactive._derive_transformer` both call `canonicalize_checksum` first), so an optional `bytes` pin cannot distinguish empty from absent.

**Strict at the function boundary, union in storage.** A Cell is a slot and admits `None` whatever its celltype; a pin and a result are the function's declared interface and do not.

| Position | Rule |
|---|---|
| **Required pin**, celltype `plain`, `mixed` or `bytes` | null is an ordinary value — for `bytes` it resolves as `b""` |
| **Required pin**, any other celltype | null is rejected: `TypeError: Required pin '<name>' with celltype '<ct>' cannot accept null`. A literal raises at assignment; one arriving from upstream is reported on the pin |
| **Optional pin**, any celltype | null **means that pin's absence**: it is compared, then dropped, and never deserialized |
| **Result**, celltype `plain`, `mixed` or `bytes` | a `None` return is the null result |
| **Result**, any other celltype | `RuntimeError: Null result is not allowed for celltype '<ct>'` |

*Verified:* `validate_pin_null` implements the required-pin rule; `run.py` raises the result error on both the Python and the compiled path.

**Optional pins are supported only for Python transformers.** `tf.optional_pins` is a read-only, set-like view derived from named parameters with defaults in the Python callable signature, including keyword-only parameters. `*args` and `**kwargs` are ignored and do not declare pins. Signature-less code and non-Python transformers have no optional pins. Neither assignment to the collection nor set mutation is allowed.

**Each signature default can be disabled and re-enabled.** For `def f(a=1, *, b=3)`, `tf.optional_pins == {"a", "b"}`. Calling `tf.optional_pins.a.disable()` makes `a` required and removes it from membership and iteration. It remains in `dir(tf.optional_pins)` and accessible as `tf.optional_pins.a`, so `tf.optional_pins.a.enable()` restores optionality. Item access supports names that collide with collection methods. Replacing callable code derives a new set from its signature; cloning and workflow binding preserve the enabled subset.

Optionality is **metadata**, kept out of the hashed transformation payload. Defaults stay in the Python code and are never pre-bound pin inputs: an absent pin is not passed, so the function receives its own default.

**The identity rule** — the contract of feature 6:

- an **unconnected** optional pin is simply absent from the transformation;
- a **connected** optional pin that resolves to canonical null is **dropped from the transformation dictionary before the transformation checksum is computed**;
- therefore *optional pin `x` absent* and *optional pin `x` connected and resolving to null* produce **the same transformation checksum**;
- a connected optional pin resolving to anything else stays in the transformation and participates in its identity;
- a **required** pin holding null (legal only for `plain`, `mixed` and `bytes`) stays present, so required-null and optional-null are **different** identities.

**What optionality does not do:**

- it does not make a connected pin lazy — a connected optional pin is computed exactly like a required one;
- a **failing** upstream on an optional pin is still a failure: optionality normalizes a successful null, never an error;
- a **missing checksum blocks**, whatever the pin's optionality — a connected optional pin whose source is unwired, blocked or still computing blocks the transformer exactly as a required pin would. Only an *unconnected* optional pin is skipped;
- the unresolved placeholder in a pin's internal tuple (`None` in the checksum slot) means "not computed", and is never absence.

The drop happens **before** the pin conversion below, so an optional `int` pin fed a null is dropped rather than failing a `null → int` conversion. Absence is decided by **comparing checksums, never by deserializing**, which is why it works for every celltype. (An earlier design restricted optional-pin absence to `plain` and `mixed` pins; that restriction is lifted.)

`sufficiently_connected(required_pins, optional_pins, wired_pins)` is the low-level predicate: all required pins wired, unconnected optional pins acceptable.

## Conversion at the pin

**The transformation receives each input converted to the pin's celltype**, through the same conversion machinery Cells use (`contracts/celltypes-and-conversion.md`, `contracts/expressions.md`). Conversion is skipped when the input celltype already equals the pin celltype.

This holds for **every route into a pin** — a pre-bound standalone pin, a call-time argument `tf(x=…)`, and a bound edge — and **reactive and snapshot runs agree**, including on the resulting checksum identity: `ctx.tf.run()` and `ctx.tf().run()` produce the same transformation checksum for the same inputs. (*Verified:* `_convert_pin_arguments` wraps a `Transformation` or `Expression` call-time argument whose celltype differs in `Expression(arg, input_celltype=arg.celltype, celltype=<pin celltype>)`; a pre-bound pin reaches the same conversion through `Pin.build()`, which wraps *any* typed reference the same way before `_convert_pin_arguments` runs; `runtime_api._snapshot_transformer` builds the same converting Expression for a bound edge and for a stored producer; `Reactive._derive_transformer` converts through the Context's projection path. Call-time Cell arguments are wrapped in a converting Expression as well.)

**A retype converts again from the stored input**; it never reinterprets the stored bytes. This is the pin counterpart of the Cell rule in `contracts/cells.md` ("retyping converts; it does not reinterpret the stored input"), and it is the reason a pin stores `(input, input celltype)` rather than a value.

**The wiring rule applies to a pin exactly as to a cell.** `tf.pins.x = <source>` is legal iff the source carries **no path**, or its celltype equals the pin's `celltype`; and a pin whose input arrives through a path has `celltype == input_celltype` (`contracts/cells.md`, *Connecting*). So `tf.pins.x = ctx.b[3]` with `x` declared `plain` and `b` of celltype `text` is **refused**, with the same two-spelling message, and `tf.pins.x = ctx.b[3].as_celltype("plain")` or `tf.pins.x = ctx.b.as_celltype("plain")[3]` says which was meant. Retyping the pin — `tf.celltypes.x`, the same setting — obeys the same invariant; retyping an upstream **source** is never refused and leaves the pin `miswired`.

**A miswired pin makes the transformer `miswired`, not `blocked`.** That is the sister rule doing its work: an *unwired* pin makes the transformer `unwired` rather than describing it in terms of its upstreams, and miswiring is the slightly-higher-precedence sister of unwired in all things (`contracts/node-state-lifecycle.md`). It does not collide with the runtime rule below, because the two sit on opposite sides of *topology before values*: a miswiring is a static defect in the graph, a failed conversion is a value that did not convert.

**A failed conversion is reported on the pin, before any transformation exists.** The pin's state is `failed` and `pin.exception` holds the failure as a string; the transformer is `blocked` with block reason `blocked-by-error` and the pin's name among its blocking pins; **no transformation is built and none is submitted**. A conversion failure is therefore never blamed on execution.

A bare `Checksum` written with no `input_celltype=` is taken to be already in the pin's celltype.

## Reads, state and work

The read API is `CellBase`'s, so `contracts/cells.md` governs: what `.checksum` may evaluate, that `.buffer` and `.value` resolve and never fingertip, what `fingertip()` does, which materialization failures are recorded, and how `clear_exception()` works. Only the Pin-specific parts are stated here.

**The surface.** A Pin exposes `source`, `checksum`, `buffer`, `value`, `celltype`, `input_celltype`, `state`, `exception`, `clear_exception()`, `build()`, `compute()` / `compute_async()`, `run()`, `fingertip()`, and the write API above. It has **no** `path`, no projection, no `mount`, no validator and no `prune()`.

- `pin.source` is the connected upstream handle, or `None`. `pin.checksum` is the pin's **current converted value**, and `None` when the pin is not complete — the same meaning as for a Cell.
- **Standalone.** `pin.checksum` evaluates the pin's own (cheap) expression and memoizes it per `(input, input_celltype, celltype)` identity; a changed input, input celltype or pin celltype resets both the memo and the exception. `pin.state` is one of `unwired`, `waiting`, `complete`, `failed`. `pin.exception` reads `pin.checksum` first, so it is a read that can do that cheap work. Materialization failures follow the Cell rule: a `CacheMissError` on the result is re-raised and **not** recorded; every other failure is recorded and raised.
- **Bound.** Every read is a snapshot of the controller-derived per-pin state — state, exception, source, input celltype, checksum — so a bound read never waits. Exceptions are exposed as strings or `None`. `pin.compute()` / `pin.compute_async()` wait on the **transformer node's** barrier and then return the pin's checksum; `timeout=` is meaningful there, and a barrier timeout raises `TimeoutError`.
- `pin.build()` returns the pin's `Expression`. Standalone it accepts a one-shot input override; bound it does not (`TypeError: Pin.build does not accept a replacement input`, and likewise for `compute`).
- `pin.run()` computes and materializes; for celltype `bytes` it returns raw `bytes`.
- **`pin.fingertip()` is `Cell.fingertip()` on a pin**, with the same contract and for the same reason: a Pin is an owner, so a fingertip through it can decide whether the recovered buffer persists, where a bare `Checksum.fingertip()` cannot. It never forces `pin.checksum`, so it is a **no-op returning `None`** when the pin has no result checksum; it returns the recovered **buffer**; and it never records `.exception` (`contracts/cells.md`, *`.buffer` and `.value`*).

**Transformer-level reporting.** On a bound Transformer, `tf.state` is the node state (`unwired`, `miswired`, `blocked`, `waiting`, `computing`, `complete`, `failed`) and **`tf.block_reason` is a dict `{pin name: reason}`** covering every input responsible for the current pending state, including `"code"` where applicable — a detached copy, and `None` in any other state. This is the same shape a Cell uses: the bare enum when there is one input and nothing to name, a dict keyed by input when there are several. A transformer always has several, so it is always the dict. When pins are in mixed states the precedence is `miswired`, then `unwired`, then `blocked-by-miswiring`, then `blocked-by-unwired`, then `blocked-by-error`, then `waiting` — topology before values (`contracts/node-state-lifecycle.md`). **Every responsible pin appears, in every state, with its own reason**; the winning category is the maximum of the dict's values under that precedence, not a separate field. The state machine itself is feature 10's node state lifecycle, documented separately, and is not specified here.

## A Pin is not a source

**A Pin cannot feed anything.** It is refused as a Cell input, as an Expression input, as the source of a Context assignment target, as an edge source and as a call argument. The refusal is **by type** — a Pin is not a `Cell` and defines none of the source protocols — and the explicit checks only improve the message, which points at `pin.source`.

To route a pin's upstream elsewhere, connect `pin.source`:

```python
ctx.tf2.pins.y = ctx.tf.pins.x.source   # works
ctx.tf2.pins.y = ctx.tf.pins.x          # TypeError, naming pin.source
```

## Implementation status and current limitations

Settled contract that the code does not yet implement, or implements differently. Where a design document and the code disagree, **the code wins** and the disagreement is listed here.

- **Compiled transformers have their own, stricter pin contract.** A compiled pin's celltype is governed by the transformer's schema, and the rules of this page — in particular the optional-pin and null rules above — do not carry over unchanged; see the compiled-pin contract page (`contracts/compiled-pins.md`). Today's code does not yet honour a compiled pin's declared celltype; that is implementation lag, not contract.
- **Assigning a standalone `Cell` or `Expression` directly to a bound pin fails.** A bound pin has one producer slot, which cannot hold a deferred expression. This is out of scope rather than a bug; connect a bound endpoint instead.


## Non-goals

- **A Pin as a source.** Deliberate. A future graph source kind for a pin's converted value could change this; nothing today may depend on it.
- **Sub-pin targets and projections.** Whole pins only.
- **Validators and mounts on pins.** Neither exists on `CellBase`'s pin side; a Pin is never mounted.
- **Per-pin settings beyond `celltype`.** The legacy per-pin `io` / `as_` settings are gone; `optional_pins` lives on the Transformer, not on the pin.
- **Handle identity.** As for Cells: `tf.pins.x is not tf.pins.x`, and nothing may be keyed on a handle.
