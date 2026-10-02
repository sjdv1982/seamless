# Pins (Contract)

**A Pin is a Transformer's input slot, and the sister class of Cell.** `Pin` and `Cell` share `CellBase` (the value, type, evaluation and ownership API), but `Pin` is *not* a subclass of `Cell`. A Pin is a **deferred Expression** in exactly the sense `contracts/cells.md` defines, `(input, input_celltype, celltype)`, with one difference that shapes everything else: its output is consumed by one Transformer rather than by the graph. The Transformer that owns the pin collection, snapshots it and may be bound to a workflow node is `contracts/transformers.md`.

Everything a Pin shares with a Cell is in `contracts/cells.md` and is **not repeated here**: the two write families and their authority rule, the `.source` / `.checksum` split, the value / buffer / checksum matrix, the "a `Checksum` is a value only for celltype `checksum`" rule, the read and materialization pipeline, and how a failure sticks to the handle until it is cleared. This page states what is Pin-specific: how pins are reached, which pins exist, call-time arguments, the null and optional-pin rules of features 6 and 7, conversion and wiring at the pin, pin and transformer state reporting, and the ways a Pin is deliberately narrower than a Cell.

**Compiled transformers** keep this general layer but restrict which pin celltypes may be declared, reject null, have no optional pins, and split pin failures from transformer failures by schema validation. That is `contracts/compiled-pins.md`; where it is stricter, it wins.

The modes are the same two as for Cells:

- **standalone**: the state is private to the Transformer object;
- **bound**: the state is owned by a workflow `Context` node, and the Pin handle is a *view* onto it.

`tf.pins.x` returns a **fresh handle** on every access, in every mode, including for a declared but unwired pin, which reads as an unwired Pin and never as `None`. Handle identity carries no meaning.

Being a separate class is load-bearing: `isinstance(pin, Cell)` is false, so every existing source check refuses a Pin **by type** rather than by a per-site check (*A Pin is not a source*).

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
| Bound call-time conversion | `seamless_workflow.runtime_api` (`_freeze_transformer`) |
| Pin writes through the controller | `seamless_workflow.context.Context._set_transformer_pin` |

## Reaching pins

**`tf.pins.x` is the only pin path.** `tf.args` is an exact alias of `tf.pins`: in both modes they are **the same collection**, reached through two names, so `tf.args.x` and `tf.pins.x` are the same pin. They are not the same *object*: each access builds a fresh wrapper, so `tf.args is tf.pins` is false, and nothing may depend on wrapper identity. Prefer `.pins` in new code.

The old sugar is **gone**: there is no `tf.x` and no `tf["x"]`. Attribute assignment on a Transformer raises `AttributeError` whose message names the replacement (`'<T>' object has no attribute 'x'; transformer input pins are reached as .pins['x']`), and a Transformer has no `__getitem__` at all. The sugar was removed because a pin name could otherwise collide with any API member of the handle.

- `tf.pins.x` for a name that is not a declared pin raises `AttributeError`. `tf.pins["x"]` is the same operation; the item form is not an escape hatch.
- **`result` is never a valid pin name.** `tf.pins.result` raises `AttributeError`, as do `tf.pins["result"] = v` and `del tf.pins["result"]`. `result` is the *output* celltype slot, `tf.celltypes.result` (*Celltypes*), and on a **bound** transformer `tf.result` is the result handle, not a pin.

**One pin has one producer.** A pin holds exactly one input: a literal checksum, or one connection. It has no sub-path edges, so none of a Cell's join rules apply, and `pin.source` and `pin.checksum` answer unambiguously: `pin.source is None` means "nothing upstream feeds this pin", and `pin.checksum is None` means "not complete", with no path to walk up in search of the responsible edge.

## Which pins exist

| Transformer code | Pin set |
|---|---|
| a Python callable | **fixed** by the signature |
| signature-less code (Bash, or a code-less builder) | **declared** by the user |

- With a **Python callable**, the signature fixes the pin set: a name outside the signature is rejected, and `del tf.pins.x` raises. (`ArgsWrapper` and `CelltypesWrapper` call this the *fixed* state.)
- With **signature-less code**, the user declares the pins: `tf.pins.x = v` or `tf.celltypes.x = ct` **creates** the declaration, and `del tf.pins.x` or `del tf.celltypes.x` **removes** it. Removing a declaration removes the pin from `pins`, `celltypes` and `optional_pins`, and clears its input.

`del` therefore means "the declaration is gone", never "empty it". Clearing a pin's *input* while keeping the declaration is `pin.checksum = None` (*Writes*). This is the same `del`-versus-clear split `contracts/cells.md` states for Cells, and it is the same in both modes.

**Only a write through `tf.pins` or `tf.celltypes` declares a pin.** A call-time argument never does (*Call-time arguments*).

## Celltypes

**`pin.celltype` and `tf.celltypes.x` are one setting**, settable from either side. The Transformer owns the storage; the Pin stores none. The setter validates and normalizes the name, and accepts a Python type, reducing it to its name (`int` becomes `"int"`).

**`pin.input_celltype` is read-only** and comes from the input, by the rules `contracts/cells.md` gives for a Cell:

| The input is | `input_celltype` is |
|---|---|
| a typed reference (Cell, Expression, Transformation, bound endpoint) | that reference's own `celltype`, read **live**: retyping a source Cell changes the pin's `input_celltype`. An `Expression` resolved its own once, at construction |
| a value, written as `tf.pins.x = v` or `pin.set(v)` | the celltype it was serialized in: the pin's `celltype` at that moment |
| a bare `Checksum` | the celltype declared with it (`pin.set_checksum(cs, input_celltype=…)`), defaulting to the pin's `celltype` |
| absent | `None` |

Which celltypes a slot accepts (*Verified:* `CelltypesWrapper.__setitem__`):

| Slot | Accepts |
|---|---|
| an **input pin** | every ordinary celltype, plus `deepcell`, `deepfolder`, `folder` and `module` |
| the **result** | every ordinary celltype, plus `deepcell` and `folder`; `deepfolder` and `module` are rejected with `TypeError` |

**`yaml` and `python` input pins are deferred.** The setter accepts both, but building a transformation that has such a pin raises `NotImplementedError`. Whether they are legal input-pin celltypes, and so whether the setter or the build is to change, has not been ruled. Do not rely on either behaviour.

Setting `pin.celltype` **resets the pin's memoized result and its recorded exception**, so a retype re-derives from the stored input rather than reinterpreting it (*Conversion at the pin*). A retype also obeys the wiring invariant (*Wiring*).

## Pins hold checksums, never values

`tf.pins.x = v` is the same operation as `tf.pins.x.set(v)` except for the authority check (*Writes*).

- A **literal value is serialized immediately** under the pin's `celltype`, and the pin stores the resulting checksum and the celltype it was serialized in. An invalid value raises **at assignment**, exactly as `Cell.set` does, in both modes.
- A **typed reference** (a `Cell`, an `Expression`, a `Transformation`, a bound endpoint) is stored as a reference and is not resolved.
- **A `Checksum` is a value exactly when the pin's celltype is `checksum`**; for every other celltype a `Checksum` is read as a declared input reference. This is the single rule `contracts/cells.md` states, unchanged at a pin. A bare `Checksum` written with no `input_celltype=` is taken to be in the pin's celltype already.

**Pin storage never holds a raw Python object.**

**A handle belongs to its own mode.** An anonymous or projection handle of a bound Cell (`ctx.c[0]`, `ctx.b.as_celltype("plain")`) is refused as the input of a **standalone** pin, as it is as the source of any standalone consumer (ruling 1(g); `contracts/cells.md`, *Binding*). Its exception class is not separately ruled for pins; `contracts/cells.md` rules `DependencyError` for the Cell counterpart, `Cell(source=<handle>)`. Assigning such a handle to a pin of a transformer bound to **another** Context raises `DependencyError`, as for named nodes. In the other direction, a standalone `Cell` or `Expression` assigned to a **bound** pin fails (*Implementation status*, *Current limitations*).

## Writes: the same two verb families

The vocabulary, and the reason for the split, are in `contracts/cells.md`; only the pin spellings are given here.

| Family | Spellings on a pin | On a connected pin |
|---|---|---|
| **Declare the input** | `tf.pins.x = X`, `pin.value =`, `pin.buffer =`, `pin.checksum =` (including `= None`) | **make it so**: replaces the producer or the edge |
| **Write what you own** | `pin.set()`, `pin.set_buffer()`, `pin.set_checksum()` | **check**: `AuthorityError` |

The standalone `AuthorityError` message is `The pin is controlled by a source; assign .value, .buffer or .checksum to replace it`.

- **Clearing.** `pin.checksum = None`, and equally `pin.buffer = None` and `pin.set_checksum(None)`, removes the input and keeps the declaration. The pin then reads as `unwired`, and so does the transformer (*Transformer-level reporting*).
- **Null.** `pin.value = None` and `pin.set(None)` store the **null value**, which a required pin accepts only under celltypes `plain`, `mixed` and `bytes` (*Null*). The `= None` / clear / `del` distinction is exactly the one `contracts/cells.md` draws.
- **A pin has no sub-path.** There are no sub-pin targets and no projections, and therefore no sub-path writes and no augmented assignment.

## Call-time arguments

`tf(x=…)` supplies an input for the pin `x` for **that one build only**; it changes no builder state. Call-time arguments combine with pre-bound pin inputs as `contracts/transformers.md` describes.

- **A call-time argument never declares a pin.** On a builder with signature-less code, a keyword that names no declared pin is an **unknown keyword**, which is a malformed call argument: building raises, and the exception class is unspecified (`contracts/transformers.md`, *Unspecified exception classes*). So `Transformer("bash", direct=True)(input="hi")`, with no `input` pin declared, must raise when building rather than run the Bash code without the input. Declare the pin first (`tf.pins.input = "hi"`). *Contract ahead of code* (*Implementation status*).
- **A call-time argument is converted to the pin's celltype** like every other input (*Conversion at the pin*), and a null on an optional pin follows *Null* like every other input.
- **The wiring rule does not apply to call-time arguments.** It governs assigning an input to a pin (*Wiring*); a call-time argument is not such an assignment.
- **Whether Cells are allowed at all as call-time arguments is undecided.** Today a call-time Cell argument is accepted and wrapped in a converting Expression, like a `Transformation` or `Expression` argument. That is current behaviour, not contract; do not rely on it.

## Null, required pins, optional pins

**One representation.** Absence and the null value share the canonical JSON-null checksum (`b"null\n"`, `38e0b9de…`), which is celltype-independent and trivially resolvable (`contracts/celltypes-and-conversion.md`). Empty bytes under celltype `bytes` **canonicalize to null before any pin rule is applied** (*Verified:* `normalize_optional_pins_for_construction` and `Reactive._derive_transformer` both call `canonicalize_checksum` first), so an optional `bytes` pin cannot distinguish empty from absent.

**Strict at the function boundary, union in storage.** A Cell is a slot and admits `None` whatever its celltype; a pin and a result are the function's declared interface and do not.

| Position | Rule |
|---|---|
| **Required pin**, celltype `plain`, `mixed` or `bytes` | null is an ordinary value; under `bytes` it resolves as `b""` |
| **Required pin**, any other celltype | null is rejected: `TypeError: Required pin '<name>' with celltype '<ct>' cannot accept null`. A literal raises at assignment; a null arriving from upstream fails the pin, and no transformation is built (*Pin failures*) |
| **Optional pin** | a null that reaches the pin over a **legal** conversion pair **means that pin's absence**: it is compared, then dropped, and never deserialized (*The identity rule*) |
| **Result**, celltype `plain`, `mixed` or `bytes` | a `None` return is the null result |
| **Result**, any other celltype | `RuntimeError: Null result is not allowed for celltype '<ct>'` |

*Verified:* `validate_pin_null` implements the required-pin rule; `run.py` raises the result error on both the Python and the compiled path.

**Optional pins exist only for Python transformers.** `tf.optional_pins` is a read-only, set-like view derived from the named parameters with defaults in the Python callable's signature, keyword-only parameters included. `*args` and `**kwargs` declare no pins. Signature-less code and non-Python transformers have no optional pins. The collection cannot be assigned or mutated as a set.

**Each signature default can be disabled and re-enabled.** For `def f(a=1, *, b=3)`, `tf.optional_pins == {"a", "b"}`. `tf.optional_pins.a.disable()` makes `a` required and removes it from membership and iteration; it stays in `dir(tf.optional_pins)` and reachable as `tf.optional_pins.a`, so `tf.optional_pins.a.enable()` restores it. Item access supports names that collide with collection methods. Replacing callable code derives a new set from the new signature; cloning and workflow binding preserve the enabled subset.

Optionality is **metadata**, kept out of the hashed transformation payload. Defaults stay in the Python code and are never pre-bound pin inputs: an absent pin is not passed, so the function receives its own default.

### The identity rule

This is the contract of feature 6:

- an **unconnected** optional pin is absent from the transformation;
- a **connected** optional pin that resolves to canonical null over a legal conversion pair is **dropped from the transformation dictionary before the transformation checksum is computed**, together with everything the dictionary records for it;
- therefore *optional pin `x` absent* and *optional pin `x` connected and resolving to null* produce **the same transformation checksum**;
- a connected optional pin that resolves to anything else stays in the transformation and participates in its identity;
- a **required** pin holding null (legal only under `plain`, `mixed` and `bytes`) stays present, so required-null and optional-null are **different** identities.

**The drop happens before conversion, and only on a legal pair.** The null checksum short-circuits a conversion only when the conversion from the input celltype to the pin celltype is **legal** (the identity conversion included); illegal conversions stay illegal even for null (`contracts/celltypes-and-conversion.md`, `contracts/deep-celltypes.md`, *Zero-path conversions*). So:

- an optional `int` pin fed a null from a `plain` source is **dropped**: `plain → int` is legal, the null never meets the `null → int` value conversion, and absence is decided by **comparing checksums, never by deserializing**;
- an optional `deepcell`, `deepfolder` or `folder` pin fed a null from a `plain` source is **not** absence: `plain → <deep>` is illegal, so the input is refused like any other value on that pair. Whether that refusal leaves the pin `failed` (and the transformer `blocked` with `blocked-by-error`) or `miswired` is **deferred**; do not rely on either.

"Illegal" includes the forbidden ordinary pairs such as `python → int` (`contracts/celltypes-and-conversion.md`, *Null and conversion legality*).

### What optionality does not do

- It does not make a connected pin lazy: a connected optional pin is computed exactly like a required one.
- A **failing** upstream on an optional pin is still a failure: optionality normalizes a successful null, never an error.
- A **missing checksum blocks**, whatever the pin's optionality: a connected optional pin whose source is unwired, blocked or still computing holds the transformer back exactly as a required pin would. Only an *unconnected* optional pin is skipped.
- The unresolved placeholder in a pin's internal tuple (`None` in the checksum slot) means "not computed", never absence.

`sufficiently_connected(required_pins, optional_pins, wired_pins)` is the low-level predicate: every required pin wired; unconnected optional pins acceptable.

## Conversion at the pin

**The transformation receives each input converted to the pin's celltype**, through the conversion machinery Cells use (`contracts/celltypes-and-conversion.md`, `contracts/expressions.md`). Conversion is skipped when the input celltype already equals the pin celltype.

**Every route converts, and reactive and snapshot runs agree**, including on the resulting checksum identity: `ctx.tf.run()` and `ctx.tf().run()` produce the same transformation checksum for the same inputs. The routes are:

- a **pre-bound standalone pin**: `Pin.build()` wraps any typed reference in a converting Expression;
- a **bound edge** or stored producer: `runtime_api._freeze_transformer` builds the same converting Expression, and `Reactive._derive_transformer` converts through the Context's projection path;
- a **call-time argument**: `_convert_pin_arguments` wraps a typed argument whose celltype differs in `Expression(arg, input_celltype=arg.celltype, celltype=<pin celltype>)`. Call-time arguments are converted, but the wiring rule below does not apply to them, and whether Cells may be passed at all is undecided (*Call-time arguments*).

**A retype converts again from the stored input**; it never reinterprets the stored bytes. This is the pin counterpart of the Cell rule in `contracts/cells.md` ("retyping converts; it does not reinterpret the stored input"), and it is why a pin stores `(input, input celltype)` rather than a value.

### Wiring: a path and a conversion may not share one link

**The wiring rule applies to a pin input exactly as to a cell input** (`contracts/cells.md`, *Connecting*). Assigning an input to a pin, `tf.pins.x = <source>`, is legal iff the source carries **no path**, or its celltype equals the pin's `celltype`. A pin whose input arrives through a path therefore has `celltype == input_celltype`.

- **A symbol whose entry carries a path counts as carrying a path.** An anonymous cell is referenced by its symbol, but the rule looks through the symbol to its `anonymous_nodes` entry, as for a cell.
- **Retyping the pin** (`tf.celltypes.x` or `pin.celltype`, the same setting) obeys the same invariant, and is refused on a pin fed through a path.
- **Retyping an upstream source is never refused.** It is a valid request, and it leaves the pin **`miswired`**, standalone and bound alike (*Pin state*).

**The refusal is a `TypeError`, and its message text is contract**, in the format `contracts/cells.md` defines: a header line `would convert <in> -> <out> behind a projection.`, followed by the two spellings that say which reading was meant, each glossed with a `# item k of …` comment. With `x` declared `plain` and `b` of celltype `text`:

```
ctx.tf.pins.x = ctx.b[3]
TypeError: would convert text -> plain behind a projection.
  ctx.tf.pins.x = ctx.b[3].as_celltype("plain")   # item 3 of the text (a character), as plain
  ctx.tf.pins.x = ctx.b.as_celltype("plain")[3]   # item 3 of the parsed list
```

**Unknown names are omitted.** A standalone transformer and a standalone Cell have no name the message could know, so the omitted part is left out and the spelling starts at the step, as `…[3].as_celltype("plain")` and `….as_celltype("plain")[3]`. Whether the text of the *pin-retype* refusal is also contract is deferred; assert only on its `TypeError`.

### Pin failures

**A miswired pin makes the transformer `miswired`, not `blocked`.** An unwired pin makes the transformer `unwired` rather than describing it in terms of its upstreams, and miswiring is the higher-precedence sister of unwired (`contracts/node-state-lifecycle.md`). It does not collide with the failure rule below, because the two sit on opposite sides of *topology before values*: a miswiring is a static defect in the graph; a failed conversion is a value that did not convert.

**A pin that has no valid checksum for its celltype never fails the transformer.** A pin's **own** failure (a failed conversion into the pin celltype, or a null rejected by the required-pin rule) is reported on the pin, before any transformation exists:

- the pin's state is `failed`, and `pin.exception` holds the failure as a string;
- bound, the transformer is `blocked`, with a **`blocked-by-error` entry for that pin in `tf.block_reason`**. A failed upstream gives the pin no checksum either, and gives the same `blocked-by-error` entry;
- bound, **`tf.exception` is not set**: it stays `None`, because nothing of the transformer's own has failed. (Standalone, a Transformer has no `exception` at all: reading it raises `AttributeError`, and the failure is on the pin and on the Transformation that `tf()` returns; `contracts/transformers.md`, *Live-node members*);
- **no transformation is built and none is submitted.** Standalone, `tf()` still returns a `Transformation` handle, but it constructs no transformation checksum (`construct()` returns `None`), and running it raises `TransformationError` naming the failed dependency.

A failure of this kind is therefore never blamed on execution. The opposite case, where every pin has a valid checksum but the transformer cannot use one of them, is the transformer's own failure: `failed`, with `tf.exception` set. For ordinary transformers that case is a failure of the run itself; for compiled transformers it also includes schema validation of a valid pin value (`contracts/compiled-pins.md`, section 5; `contracts/node-state-lifecycle.md`, *Transformer nodes*).

## Scratch at the pin

**A pin's scratch is derived, never configured, and the transformer's `scratch` plays no part in it.** A transformer's `scratch` governs its *result* only (`contracts/scratch-witness-audit.md`). A pin is an input, and one question decides whether its claim is scratch: can the bytes be recovered where the transformation runs?

- **A literal pin is never scratch.** A literal is a checksum the pin holds itself, however it was written: a value serialized at assignment, the code of a function, or a `Checksum`. Nothing produces it, so nothing can fingertip it, and no other owner holds it. The transformation's definition is always published for the same reason (`contracts/internal/checksum-reference-lifecycle.md`, §8, *The definition write*).
- **Any other pin is scratch exactly when the transformer fingertips its inputs** (`allow_input_fingertip = True`; `contracts/scratch-witness-audit.md`, *Scratch*). The process that runs the transformation, or that later fingertips its result, then recomputes a missing input itself, so nothing has to be stored for it. Without the opt-in the pin is non-scratch, because that process looks for the bytes in its own memory and on the hashserver, and nowhere else.

**What a pin's scratch decides:**

- **Its claim.** A non-scratch pin holds its input under a non-scratch claim, which publishes it (`contracts/internal/checksum-reference-lifecycle.md`, §8, *Buffer persistence*). A scratch pin's claim writes nothing.
- **Its request.** A scratch pin asks for a checksum, which is all a transformation's identity needs. A non-scratch pin asks for its input's **value**: a recorded checksum whose buffer cannot be reached does not answer it. Every Expression that produces the input, whether a pin conversion or a link of a bound edge, is requested under the pin's scratch (`contracts/expressions.md`, *The requester's scratch decision*).
- **`pin.fingertip()`.** It persists the recovered buffer exactly when the pin is non-scratch, as `Cell.fingertip()` does for a non-scratch Cell.

**A non-scratch pin overrules a scratch producer.** When a scratch transformer feeds a non-scratch pin, directly or through cells and Expressions, the pin's need wins and the producer's result is published:

- If the producer's buffer is in this process, the pin's claim publishes it.
- If the producer ran elsewhere as scratch, its result was never written. The value request reaches the producer and asks for its result again, non-scratch, so the producer runs a second time: the cost that a value request on a scratch result always carries (`contracts/scratch-witness-audit.md`, *Scratch*). A Context knows its graph, so it dispatches a transformer non-scratch from the start when its result feeds a non-scratch pin, and the transformer runs once.
- Through a projection or a conversion, the producer's whole result is published, not only the part the pin receives, because the Expression in between needs the producer's bytes where it is evaluated.

The way to keep a scratch producer scratch is the opt-in: a transformer that fingertips its inputs has scratch pins, and they overrule nothing. That is the common use of scratch, a bulky intermediate regenerated where its consumer runs (`contracts/scratch-witness-audit.md`, *Where a fingertip chain runs*, case 1). Several consumers of one result never conflict, because publishing is per holder: a non-scratch pin publishes the result, and a scratch pin's claim on the same checksum is simply redundant.

## Reads, state and work

The read API is `CellBase`'s, so `contracts/cells.md` governs what `.checksum` may evaluate, that `.buffer` and `.value` resolve and never fingertip, what `fingertip()` does, how a failure is delivered (reads and `compute()` report, `run()` raises), that materialization failures are never recorded, and how `clear_exception()` works. Only the Pin-specific parts are stated here.

**The surface.** A Pin exposes `source`, `checksum`, `buffer`, `value`, `celltype`, `input_celltype`, `state`, `exception`, `clear_exception()`, `build()`, `compute()` / `compute_async()`, `run()`, `fingertip()`, and the write API above. It has **no** `path`, projection, `mount`, validator or `prune()`, and no `block_reason`.

- `pin.source` is the connected upstream handle, or `None`. `pin.checksum` is the pin's **current converted value**, and `None` when the pin is not complete, as for a Cell.
- `pin.build()` returns the pin's `Expression`. Standalone, it accepts a one-shot input override; bound, it does not (`TypeError: Pin.build does not accept a replacement input`, and likewise for `compute`).
- `pin.run()` computes and materializes; under celltype `bytes` it returns raw `bytes`. **It is the pin call that raises** (ruled 2026-09-28; `contracts/cells.md`, *Failures*, *How a failure is delivered*): it re-raises the pin's recorded failure, and raises any failure to materialize the pin's result. Bound, a pin that settles with no checksum for any other reason makes `run()` raise `NodeError` naming the pin's state. `.checksum`, `.buffer`, `.value` and `compute()` answer `None` for a recorded failure and whenever the pin has no checksum. A failure to materialize a result that exists is the exception: `.buffer` and `.value` raise it too, on every read, and never record it (*Pin state*, below); `.checksum` and `compute()` do not materialize, so they return the checksum.
- **`pin.fingertip()` is `Cell.fingertip()` on a pin**, with the same contract and for the same reason: a Pin is an owner, so a fingertip through it can decide whether the recovered buffer persists, where a bare `Checksum.fingertip()` cannot. It persists exactly when the pin is non-scratch (*Scratch at the pin*). It never forces `pin.checksum`, so it is a **no-op returning `None`** when the pin has no result checksum; it returns the recovered **buffer**; and it never records `.exception` (`contracts/cells.md`, *`.buffer` and `.value`*).
- **`pin.exception` is a string or `None`**, in both modes. Whether every `.exception` string carries the exception class name, as ruled for compiled pins (`contracts/compiled-pins.md`, D5), is deferred.

### Pin state

**Standalone**, `pin.state` is one of `unwired`, `miswired`, `waiting`, `complete` and `failed`. `blocked` and `computing` are Context-node states, and `block_reason` is bound-only.

- `pin.checksum` evaluates the pin's own (cheap) Expression and memoizes the result per `(input, input_celltype, celltype)` identity; a changed input, input celltype or pin celltype resets both the memo and the exception.
- **`miswired`** (ruling 5): a pin fed through a path whose upstream source is retyped, so that the link would both project and convert, is `miswired`, like a standalone Cell consumer (`contracts/cells.md`, *Connecting*). Its `.checksum` is `None`, and its `.exception` is `None`: miswiring is a static defect, not a failure, and no work is attempted. A call of the transformer constructs no transformation, as for a failed pin.
- **Inspection is not passive on a standalone Pin.** `pin.state` and `pin.exception` read `pin.checksum` first, so an inspection can do the pin's cheap conversion work and record its failure. This deviates from `CellBase` inspection, which is passive in both modes (`contracts/cells.md`, *Failures*). The deviation is stated here as the current rule; whether the Pin is to become passive like a Cell has not been ruled.
- Materialization failures follow the Cell rule: a failure to materialize a result that exists — a `CacheMissError`, a validation or a deserialization failure — is raised on every read and **not** recorded, and the pin stays `complete` (ruled 2026-09-28). *Contract ahead of code:* only a `CacheMissError` is left unrecorded; every other materialization failure is recorded, and it makes the pin `failed`.

**Bound**, every read is a snapshot of the controller-derived per-pin state (state, exception, source, input celltype, checksum), so a bound read never waits. `pin.compute()` / `pin.compute_async()` wait on the **transformer node's** barrier and then return the pin's checksum, or `None` when the pin has none. They never raise for the pin's state or the transformer's (`contracts/node-state-lifecycle.md`, *States as seen through barriers and handles*); `timeout=` is meaningful there, and a barrier timeout raises `TimeoutError`. A bound materialization failure on a pin is raised and not recorded, as standalone. *Contract ahead of code:* today it is recorded on the pin, which makes the transformer `blocked` with `blocked-by-error`.

### Transformer-level reporting

On a bound Transformer, `tf.state` is the node state: one of `unwired`, `miswired`, `blocked`, `waiting`, `computing`, `complete` and `failed`. The state machine itself is feature 10's node state lifecycle (`contracts/node-state-lifecycle.md`) and is not specified here.

**`tf.block_reason` is a dict `{input name: reason}`**, keyed by pin name, with `"code"` for the code input. It is a **detached copy**: mutating it changes nothing.

- **Entries:** one per input that is neither `complete` nor `waiting`. A `complete` or `waiting` input never appears, so there is no `waiting` and no `complete` value.
- **Values:** exactly one of the five members `miswired`, `unwired`, `blocked-by-miswiring`, `blocked-by-unwired` and `blocked-by-error`.
- **Label:** the transformer's category is the maximum of the dict's values under the precedence

  ```
  miswired  >  unwired  >  blocked-by-miswiring  >  blocked-by-unwired  >  blocked-by-error
  ```

  that is, topology before values. There is no separate "winning category" field. The precedence decides the label, never which entries appear: every input that is neither `complete` nor `waiting` has an entry, whichever category won.
- **`None`:** a transformer that is itself `waiting` reports `None`, as does one that is `computing`, `complete` or `failed`.

This is the shape `contracts/node-state-lifecycle.md` gives every node: a single value for a cell whose only input is at the root, and a dict keyed by input for a node with several inputs. A transformer always has several (its code and its pins), so it always reports the dict.

**`tf.exception` is the transformer's own failure only.** It is set when the transformer is `failed`. A pin without a valid checksum never sets it (*Pin failures*); read the pin instead, following its `blocked-by-error` entry.

## A Pin is not a source

**A Pin cannot feed anything.** It is refused as a Cell input, as an Expression input, as the source of a Context assignment, as an edge source and as a call argument. The refusal is **by type** (a Pin is not a `Cell` and defines none of the source protocols); the explicit checks only improve the message, which points at `pin.source`.

To route a pin's upstream elsewhere, connect `pin.source`:

```python
ctx.tf2.pins.y = ctx.tf.pins.x.source   # works
ctx.tf2.pins.y = ctx.tf.pins.x          # TypeError, naming pin.source
```

## Implementation status and current limitations

The rules above are the test oracle. Where the code differs, **the contract wins**, and the difference is listed here. Each gap is pinned by an `xfail(strict=False)` test whose reason reads "… contract ahead of code: …" (`seamless-transformer/tests/test_contract_pins.py`, `seamless-workflow/tests/test_contract_pins_bound.py`), unless the entry says otherwise.

- **An optional `folder` or `deepfolder` null leaves `__format__` behind (F1).** When a connected optional pin of either celltype resolves to null, the pin is dropped but its `__format__[pin]` entry stays in the transformation dictionary, so "connected and null" gets a different transformation checksum from "absent" (*The identity rule*). This happens on every route, in both modes.
- **A required `module` pin fed null from upstream still builds (F3).** The pin correctly reports `failed` with the required-pin message, but `tf().construct()` succeeds: a module pin is stored as celltype `plain` in the transformation dictionary, so `validate_pin_null` lets the null through (*Pin failures*).
- **Bound `del tf.celltypes.x` resets the pin to `mixed` (F4).** On signature-less code it keeps the pin and its input instead of removing the declaration (*Which pins exist*). Standalone removes it.
- **A standalone Pin never becomes `miswired` (ruling 5).** After the upstream source of a pin fed through a path is retyped, the pin reports `waiting`, and `tf()` still constructs a transformation (*Pin state*).
- **A bound handle is accepted on a standalone pin (ruling 1(g)).** `tf.pins.x = ctx.c[0]` on a standalone transformer is accepted rather than refused (*Pins hold checksums, never values*).
- **Bound `as_celltype` spellings are refused.** `ctx.tf.pins.x = ctx.b[3].as_celltype("plain")` and `ctx.tf.pins.x = ctx.b.as_celltype("plain")[3]` both raise, and so does the symbol-with-path retype check that depends on them: a bound `as_celltype` does not yet return an anonymous cell (`contracts/cells.md`, *Implementation status*).
- **Waiting inputs are listed in `tf.block_reason`.** Inputs that are `waiting` appear with the value `waiting`, and a `waiting` transformer reports a dict with every input as `waiting` instead of `None` (*Transformer-level reporting*).
- **A null plain Cell on an optional deep pin is dropped instead of refused.** On an optional `deepcell`, `deepfolder` or `folder` pin, the null crosses the illegal `plain → <deep>` pair and is treated as absence: standalone the transformation builds with the absent identity, and bound the transformer completes (*The identity rule*).
- **The wiring refusal uses the short text.** The message is `Cannot implicitly convert behind a projection; use as_celltype() before or after projecting`, not the contract format (*Wiring*).
- **A code-less Bash builder drops an undeclared keyword argument.** `Transformer("bash", direct=True)(input="hi")` with no `input` pin builds without raising and runs the Bash code without the input, which then fails inside Bash (*Call-time arguments*). Pinned by `test_bash_undeclared_keyword_raises_at_build` in `seamless-transformer/tests/test_contract_transformer_builder.py`, not by the pins test files.

**Current limitations** (out of scope, not gaps):

- **A standalone `Cell` or `Expression` cannot be assigned to a bound pin.** A bound pin has one producer slot, which cannot hold a deferred expression. Connect a bound endpoint instead.

## Non-goals

- **A Pin as a source.** Deliberate. A future graph source kind for a pin's converted value could change this; nothing today may depend on it.
- **Sub-pin targets and projections.** Whole pins only.
- **Validators and mounts on pins.** A Pin has neither, and is never mounted.
- **Per-pin settings beyond `celltype`.** The legacy per-pin `io` / `as_` settings are gone; `optional_pins` lives on the Transformer, not on the pin.
- **Handle identity.** As for Cells: `tf.pins.x is not tf.pins.x`, and nothing may be keyed on a handle.
