# Deep Celltypes: `deepcell`, `deepfolder`, `folder` (Contract)

This page defines the three **deep celltypes** — `deepcell`, `deepfolder` and `folder` — as they behave under checksums, Expressions and conversion. `module` is **not** a deep celltype; see [`module` is not a deep celltype](#module-is-not-a-deep-celltype).

The 13 ordinary celltypes, the reference parser and the conversion rule table are defined in `contracts/celltypes-and-conversion.md`; checksum-level classification in `contracts/hashtype.md`; the directory-identity idea in `contracts/content-addressed-files-and-dirs.md`.

## Where this page sits: a carve-out, not a layer

The ordinary stack is celltypes and the type hierarchy → HashType → conversion → Expressions → Cells (`contracts/celltypes-and-conversion.md`, *Where this page sits*). **The deep celltypes are not a sixth layer; they are a carve-out at the Expression level**, and everything below is about which Expression shapes over a deep checksum are legal.

| Ordinary stack | For a deep checksum |
|---|---|
| 13 celltypes, the subtype→supertype edges, and the rule table | **none of it applies.** The legal conversions are the table in *Zero-path conversions* below, and nothing else |
| HashType classifies the checksum | **no deep vocabulary, and it is never asked.** `deserializable_as` **raises `ValueError`** for a celltype outside the 13, `capabilities` is not the oracle for a deep step, and `conversion_feasible` never reaches a deep pair. Deep feasibility is structural and is settled here instead (`contracts/hashtype.md`; *Where deep validation happens*, below) |
| An Expression is a path plus at most one conversion, applied **project-then-convert** | **unchanged, and load-bearing.** Project-then-convert is what lets one step select a child checksum without materializing the parent; this shape could not exist under the opposite order (`contracts/expressions.md`, *Application order*) |
| Path length is unlimited | **exactly one step**, and it is a string item. A deep step is also a **fusion barrier** (`contracts/expressions.md`, *Fusion*) |
| An edge may carry a path **or** a conversion, never both | **carved out.** A deep step necessarily changes the celltype, so path and conversion always travel together; the criterion is this page's table instead (`contracts/cells.md`, *Connecting*) |
| Cost class can turn on the checksum's nullity and cached `HashType` | **shape alone decides** — see *The organising principle* |

One thing *is* ordinary: a deep buffer is plain JSON with an ordinary checksum, and everything downstream of a child checksum is ordinary wiring again.

**Implementation status: the rules on this page are contract, not current behaviour.** Nothing in the Expression or conversion path implements deep celltypes today. See [Current status](#current-status-none-of-this-is-enforced-yet) before relying on any of it.

Code locations:

| Concern | Module / symbol |
|---|---|
| Buffer-layer mapping | `seamless.buffer_class.Buffer._map_celltype` (seamless-core) |
| The deep celltype set | `seamless_transformer.transformation_utils.DEEP_CELLTYPES`, `is_deep_celltype` |
| Pin-level fan-out / fan-in | `seamless_transformer.transformation_utils.unpack_deep_structure`, `pack_deep_structure` |
| Pin presentation to a transformer | `seamless_transformer.transformation_namespace.build_transformation_namespace_sync`, `_to_checksum_dict` |
| Directory celltypes (mounts) | `seamless.checksum.canonical.DIRECTORY_CELLTYPES` (seamless-core); the mount rules are `contracts/mounts.md` |
| Mount read/write of an index | `seamless_workflow.attachments.fs.service.FileSystemService._read`, `._write_directory` |
| Index construction from files | `seamless_transformer.cmd.file_load` |
| Module definition buffers | `seamless_transformer.module_builder.pypackage_to_moduledict` |

## The organising principle

**Within the deep celltypes, an Expression's cost class is a function of its identity tuple `(input_celltype, path shape, celltype)` alone, never of the data behind the checksum.** (Over the 13 ordinary celltypes this is weaker — cost can also turn on the checksum's own nullity and its cached `HashType`, see `contracts/expressions.md`, "Cost class" — but no deep conversion below branches on anything but the declared celltypes, so here shape alone decides.)

Every restriction below follows from that one rule. It is what makes the rules decidable at validation time, before any buffer is materialized: two Expressions with the same shape must cost the same, so a shape may not sometimes be a free index read and sometimes an N-child fan-out. It is also why the legal set is small: each admitted shape has exactly one cost.

**The three cost classes, named once — this page is where they are named, and other pages use these words.** They classify **how many members a shape involves**, which is the thing that must not vary with the data:

| Class | Members involved | Buffers fetched to **evaluate** | Deep shapes in it |
|---|---|---|---|
| **free** | none | **none** — the result checksum comes from the rule alone | the identity conversion, and every index conversion in *Zero-path conversions* |
| **one child** | exactly one | **one: the index** | the one-step path, either target (*What the one step yields*) |
| **all children** | all of them | the index, **plus every member** | `folder → mixed`, and nothing else |

Two distinctions this table exists to keep straight:

- **Evaluating is not materializing.** A cost class is the cost of producing the **result checksum**. Reading the *value* of any result — deep or ordinary — needs that result's buffer, and that is a separate act with its own cost. So a *free* conversion is free to evaluate even though `.value` on its result still fetches the index buffer; and the *one child* class fetches the index to evaluate, and the member only if someone then asks for the member's value.
- **"One child" is about fan-out, not about buffers.** Only `folder → mixed` fetches members during evaluation.

`contracts/expressions.md`, *Cost class*, uses the same three names for the ordinary celltypes, where *one child* is simply *one buffer* — the input — because an ordinary value has no members, and where the class can additionally turn on the checksum's nullity and its cached `HashType`. Here shape alone decides.

## Where deep validation happens

**Deep feasibility is structural**: it turns on the declared celltypes and the shape of the path, never on the data behind the checksum. That is why it is decided **at Expression construction**, by this page's tables, and never by a checksum-level classification:

| Expression | Vetted by |
|---|---|
| **pathless**, deep on either side | the **conversion engine**, whose rule table carries the deep-to-deep conversions of *Zero-path conversions* |
| **pathed**, deep on either side | the **deep table** of *Paths*, below: exactly one string-item step, and the member-celltype rules |

**HashType is not consulted, and must not be asked.** `deserializable_as` accepts only the 13 ordinary celltypes and raises `ValueError` on anything else; it does not answer `False` for a deep name, and it does not learn the four names (`contracts/hashtype.md`). The division is: **this page validates structure, ahead of any data; HashType validates what the input checksum's own word proves, once the value is known** — which for a deep index is the ordinary `JSON_OBJECT` classification of a `plain` buffer, nothing deep. The same one shared validator serves the Expression layer and pin unpacking (*Nesting is not contract*); it lives on this side of the line, not inside HashType.

`contracts/expressions.md`, *When an Expression is vetted*, states the same split from the Expression side.

## What a deep buffer is

- **At the buffer layer there is no deep format.** `Buffer._map_celltype` maps `deepcell`, `deepfolder`, `folder` (and `module`) to `plain`. A deep buffer is ordinary plain JSON, serialized and parsed by the `plain` rules, and its checksum is an ordinary checksum.
- **A deep buffer is an index**: a **flat** dict with string keys and 64-character lowercase hex checksum strings as values. Nothing else. Flatness is contract (see [Nesting is not contract](#nesting-is-not-contract)).
- **Keys are opaque strings.** They carry no path semantics at this layer. Only the mount layer reads `/` as a directory separator. `deepfolder` and `folder` keys routinely contain `/`.
- The members are *referenced*, not contained: the index commits to the child checksums, and a deep checksum can be held, compared and passed around without any child buffer being present.

**Requesting the *value* of a deep checksum yields the index.** This is general, and it holds at every
layer that can be asked for a value — `Checksum.resolution(celltype)`, `Buffer.get_value`, `Cell.value`,
a `Pin`, a direct-called transformer result. There is no deep format below the index to unpack:
`_map_celltype` sends the deep celltypes to `plain`, and the index is simply what a `plain` parse of that
buffer gives. So:

- the value is that index, **with each member presented as a `Checksum` object**: `{key: Checksum}`
  (ruled 2026-09-21). The 64-hex strings are the **buffer's** form; `Checksum` is the **API's** form, and
  they are the same index. Serializing such a dict back at a deep celltype writes the same hex JSON, so
  the round trip preserves the checksum;
- **nothing is resolved.** No member buffer is touched, and the cost class is *free*. A `Checksum` object
  is not a buffer: wrapping is typing, not resolution;
- the dict of `Checksum` objects that a `deepcell` / `deepfolder` **pin** hands a transformer
  (`_to_checksum_dict`, *How deep values reach a transformer*) is therefore not a pin-layer special
  case — it is this rule, at the pin layer;
- the `folder` pin's dict of child *contents* **is** a pin-layer presentation, and it is the one place
  that resolves children on the input side, because the pin also carries `{"filesystem": {"mode":
  "directory"}}`. The value-level equivalent is the explicit `folder → mixed` conversion, which is
  *all children* and is priced as such.

The three celltypes share this buffer shape exactly. They differ only in **what their members are**, and in what a consumer is declaring it wants:

| Celltype | A member checksum is | Intent |
|---|---|---|
| `deepcell` | a buffer deserializable as `mixed` | a collection of Seamless values, addressed by key |
| `deepfolder` | an arbitrary raw byte buffer | the **index** of a directory; the contents stay by reference |
| `folder` | an arbitrary raw byte buffer | the **contents** of a directory; consumers want the bytes |

`deepfolder` and `folder` therefore have the same member type and differ only in intent. `deepcell` is the strict one: its member type is a subtype of the other two.

**The intent is load-bearing at exactly one place today: `deepfolder` is sense-only on a mount.** `folder` mounts in `r`, `w` and `rw`; `deepfolder` may only be mounted with `mode="r"`, because a write mount materializes every leaf onto disk — which is precisely what "the contents stay by reference" declares it does not do. The restriction costs one retype, since the conversion between the two is free in both directions, and a transformer cannot produce a `deepfolder` at all. See `contracts/mounts.md`.

## `module` is not a deep celltype

`DEEP_CELLTYPES = ("deepcell", "deepfolder", "folder")`. `module` is deliberately not in it, and **none of the rules on this page apply to `module`.**

A `module` buffer is a plain JSON *module definition* holding literal code strings, not checksums:

```
{"language": ..., "type": "interpreted",
 "code": <str> | {"<dotted.name>": {"language", "code", "dependencies"}, ...}}
```

It travels as celltype `plain` with subcelltype `module` (`pretransformation` builds the pin as `{"celltype": "plain", "subcelltype": "module"}`), and a transformer pin declared `module` is resolved by the module builder, not by any deep unpacking. Some older notes group `module` with the deep celltypes; that grouping is wrong. The only property `module` shares with them is that `Buffer._map_celltype` sends it to `plain`.

## Nesting is not contract

`unpack_deep_structure` and `pack_deep_structure` recurse through nested dicts and lists with checksums at the leaves. That generality is legacy: it has no producer and no consumer in current Seamless. **A deep value whose index is not flat is invalid.**

Nested structures must be rejected at the Expression layer *and* at pin unpacking, through one shared validator. Two independent checks would drift, and pins would then accept values that Expressions refuse — which would mean the two layers disagree about what a deep value is.

### When flatness is checked, and what a false deep claim does

**Flatness is a property of the buffer, so it can only be checked with the buffer in hand.** That fixes the phase exactly:

| Operation | Is the index parsed? | Flatness checked? |
|---|---|---|
| declaring a celltype, or constructing a deep Expression | no | no — construction checks celltypes and path *shape* only (`contracts/expressions.md`, *When an Expression is vetted*) |
| a checksum-preserving zero-path conversion (`deepcell→deepfolder`, `deepcell→plain`, …) | **no** | **no** |
| a one-step path | yes | **yes** |
| reading `.value` / `.buffer` at a deep celltype | yes | **yes** |
| `folder → mixed` | yes | **yes** |
| pin unpacking or packing (`unpack_deep_structure` / `pack_deep_structure`) | yes | **yes** |

So **a checksum falsely declared deep is not detected by a free conversion, and that is by design.** `deepcell → deepfolder` on a checksum whose buffer is not an index at all succeeds silently and yields the same checksum, exactly as `plain → mixed` succeeds on a checksum whose buffer is not valid `plain`. A declared celltype is a *claim* about a checksum; a conversion that never looks at the bytes never tests the claim. The claim is tested at the first operation that parses the index, and it fails there.

**The one checksum-level check that is available** is the *mapped* one: a deep buffer is a `plain` buffer, so `deserializable_as(checksum, "plain")` is a legitimate cheap disproof — a non-JSON buffer declared `deepcell` can be refused without a fetch. That is also the only way HashType ever participates in a deep decision: it sees `plain`, never a deep name (`contracts/hashtype.md`).

**The failure.** The shared validator raises `ValueError`, naming the offending key or shape — nesting, a non-string key, or a value that is not a 64-character lowercase hex string. Inside an Expression it surfaces as `ExpressionEvaluationError` (error-envelope kind `expression_evaluation`), like any other failure of a path step; at the pin layer it becomes the pin's failure, reported on the pin before any transformation is built (`contracts/pins.md`). It is **not** a `HashTypeValidationError`: no checksum-level classification was consulted and none could have answered.

## Conversions

### Zero-path conversions

Only these are legal. Every one of them is **free** — decided at checksum level, no buffer fetched to evaluate and no child touched — except `folder → mixed`. (Free to *evaluate*: reading the resulting index's value still fetches the index buffer, as reading any value does.)

| Conversion | Cost | Checksum | Notes |
|---|---|---|---|
| identity (source celltype = target celltype) | free | preserved | the dummy Expression; always legal |
| `deepcell → plain` | free | preserved | read the index as what it already is |
| `deepfolder → plain` | free | preserved | idem |
| `folder → deepfolder` | free | preserved | drop the intent to materialize; the index is unchanged |
| `deepfolder → folder` | free | preserved | add the intent to materialize |
| `deepcell → deepfolder` | free | preserved | widen the member type |
| `folder → mixed` | **N children** | new buffer | the only conversion in the system that materializes children |
| everything else | — | — | **rejected** |

Rejections worth spelling out:

- **`deepfolder → deepcell` is forbidden.** This is the celltype hierarchy (`contracts/celltypes-and-conversion.md`, "The celltype hierarchy is a checksum hierarchy") applied one level down, to members: a subtype→supertype edge means every checksum valid as the subtype is valid, unchanged, as the supertype. `deepcell` members must be deserializable as `mixed`; `deepfolder` members are arbitrary bytes. So `deepcell → deepfolder` widens and is free, and the reverse would require proving a property of every member — work proportional to N, hidden behind a shape that looks free.
- **`folder → plain` is rejected**, although `deepfolder → plain` is legal and they have identical buffers. Admitting it would put a free index read and an N-child fan-out under the same identity tuple, depending only on which celltype the source happened to be declared as. Convert `folder → deepfolder → plain` (both free) if the index is what you want.
- **`plain → deepcell` / `plain → deepfolder` / `plain → folder`** are rejected: promoting an arbitrary plain value to an index would require validating every entry.

### `folder → mixed`

- **All-or-nothing.** The result is the complete dict of children, or an error. There is no partial result.
- **Per-child failure is not sticky.** A child that could not be resolved does not poison the deep checksum; a later attempt may succeed (for example once the buffer is reachable again).
- **Resolution order and concurrency are unspecified.** Children may be resolved in any order, sequentially or in parallel. Concurrency here is an optimization, not contract. Do not depend on an observed order, and do not treat parallelism as guaranteed.
- **This is the only shape in the system that waits on more than one buffer.** Every other Expression materializes exactly one checksum, so the buffer layer's waiting set is keyed by a single checksum; `folder → mixed` is the sole reason a **multi-checksum waiter** has to exist at all (`contracts/expressions.md`, *Cancellation*). It is a further reason the fan-out is confined to this one conversion.
- **Child representation is settled: a 1-D NumPy `S1` array, one element per byte** (`np.frombuffer(content, dtype="S1")`), **never a 0-dimensional `S<N>` scalar.** Only the 1-D form round-trips faithfully — a 0-d scalar's `.tobytes()` turns an empty child into `b"\x00"`, and `.item()` strips trailing NULs (`b"ab\x00\x00"` reads back as `b"ab"`), because NumPy's `S` dtype strips trailing NULs on scalar extraction. Serializing a dict of Python `bytes` into `mixed` produces 0-d scalars and must never be the route by which a `folder` value is serialized as `mixed`. The pin-level fan-out (`unpack_deep_structure`) handing the transformer Python `bytes` is a fine in-process presentation; it is not this serialization route.

### The `folder` note: conversion stops at `mixed`

**Conversion stops at `folder → mixed`.** The children arrive as raw byte arrays — a 1-D NumPy `S1` array per child, one element per byte, not the 0-dimensional `S`-dtype scalar that serializing a Python `bytes` dict would give (see the representation rule above). **There is no conversion that yields a dict of decoded strings.**

A value-level route for `mixed → plain` was considered and rejected. `mixed → plain` is a pure *reinterpretation* (`conversion_reinterpret`: the same bytes must parse as JSON, and the checksum is preserved). Giving it a value-level route would make every `S`-array in every `mixed` buffer decode to text, everywhere in the system, and would make the pair only *sometimes* checksum-preserving. That is too much global semantics to buy one convenience.

Decode it yourself instead:

- **per file**: take the child's checksum (a one-step path, below) and run an ordinary `bytes → text` Expression on it — keyed at the child checksum, so it is shared by every parent that references that child;
- **per folder**: decode inside a transformer. This is the idiomatic route: decoding N files is content transformation, not celltype reinterpretation.

**Footnote (not a bug).** An *empty* folder does survive the chain `folder → mixed → plain`. Its `mixed` buffer is literally `b"{}\n"`, which is valid JSON, so the reinterpretation succeeds and the checksum is preserved. Every non-empty folder serializes to a framed Seamless-mixed buffer (`b"\x94SEAMLESS-MIXED\x0bmixed-plain..."`), classified `MIXED_OBJECT`, for which `conversion_feasible` answers `False` and `convert_checksum` raises `SeamlessConversionError` — for all-UTF-8 contents exactly as much as for binary ones. So `{}` succeeds where every non-empty folder is rejected. This is a consequence of buffer identity, not a special case for empty folders.

## Paths

**A deep Expression admits exactly one path step, and that step is a string item.** It selects one member of the index.

| Source | `→ checksum` | member value |
|---|---|---|
| `deepcell` | the child's checksum | `→ mixed` |
| `deepfolder` | the child's checksum | `→ bytes` |
| `folder` | the child's checksum | `→ bytes` |

No other target celltype is legal for the one-step result.

#### What the one step yields

Both targets are evaluated from **the index buffer alone**: the child's checksum is read out of the index, and **no member buffer is fetched to produce the result**. They differ in what the result *is*.

| One-step Expression | Result checksum | New buffer? | To evaluate | To read `.value` |
|---|---|---|---|---|
| `(index, "['k']", deep, member celltype)` — `mixed` for `deepcell`, `bytes` for `deepfolder`/`folder` | **the child's own checksum** | no | the index | the **child's** buffer |
| `(index, "['k']", deep, "checksum")` | the checksum of a **new** `checksum`-celltype buffer holding the child's digest | yes — 64 bytes | the index | that 64-byte buffer, giving a `Checksum` |

Consequences, all of them ordinary machinery rather than deep special cases:

- **`→ member celltype` is the cheap handle on a child.** Its result checksum *is* the child's, so `compute()` answers the child's checksum, and every later Expression over that result is keyed at the **child** — shared by every parent index that references it. The reverse index gains a route from the child checksum back to `(parent index, key)`, which is exactly what makes a child recoverable by fingertipping the parent.
- **`→ checksum` is the *reference* form**, and it obeys the ordinary `checksum` celltype rules (`contracts/celltypes-and-conversion.md`): a `checksum`-celltype buffer is the 64-character hex digest, classified `EQ64`. Converting it onwards is `checksum→X`, which **dereferences** — it returns the referenced checksum as its result with no new buffer — so the child's own conversions end up keyed at the child there too. The two targets therefore converge; `→ checksum` simply costs one extra tiny buffer and one extra Expression on the way.
- **Validation of the member stays at checksum level.** Whether the child is really deserializable at the member celltype is a question for the child's own `HashType`, asked without fetching it, and answerable `None`. The step never fetches a member to check one.
- **`run()` differs accordingly**: on `→ member celltype` it materializes the child's value; on `→ checksum` it returns a `Checksum`.

Why:

- **An empty path is the fan-out.** The no-step shapes are the index conversions and `folder → mixed`; the one-step shape is exactly one child. Keeping them distinct keeps the cost classes distinct.
- **A longer path would have to continue into the child.** The child is a different checksum, and therefore a different Expression. A two-step deep path would smuggle a second, unrelated evaluation into one identity tuple.
- **Restricting the one-step result to the member celltype keys the child's own conversion at the child checksum.** `deepfolder[k] → bytes → text` is two Expressions: the second is identified by the *child's* checksum, so its result is shared by every parent index that references that child, and by anyone holding the child checksum directly. Allowing `deepfolder[k] → text` in one step would re-key that same work under each parent.

**Write the step in bracket form.** Keys are opaque and routinely contain `/`, `.` and other characters that attribute access cannot express: use `expr["path/to/file.txt"]`, not `expr.file`.

- **The step is only expressible because Expressions project before they convert.** `input_celltype` decides what the path walks — here, the index — and `celltype` renders only what the step selected. Under the opposite order the output celltype would decide the structure being walked, and "select a child of this index without materializing the parent" would have nowhere to live (`contracts/expressions.md`, *Application order*).
- **The step is a fusion barrier.** A run of projecting edges collapses into one Expression everywhere else; it stops at a deep step, because the step's result is a *checksum*, and a following path would project into the checksum rather than into what it names. Fusing past it would also re-key the child's shared work under each parent (`contracts/expressions.md`, *Fusion*).

No new HashType capability is needed for the step itself: a flat index is a JSON object, and `capabilities` already yields `{"MAP"}` for a `JSON_OBJECT` word under `plain`/`mixed` (`contracts/hashtype.md`). Only the source-celltype dispatch would have to learn the deep celltypes, which currently fall through to the empty set.

### Reading a deep child before the rules are enforced

The contract route to a child — the one-step path above — raises `HashTypeValidationError` right now
(*Current status*). Until it works, the only way to reach a child checksum is to read the parent's value
and index it yourself:

> On a `Cell("deepfolder")` (or `deepcell`, or `folder`) holding an index, with **no path and no
> retyping**, read `.value` and index the resulting dict. `.value` resolves through `Buffer.get_value`,
> which maps the deep celltypes to `plain` before parsing, so you get the `{key: hex}` index.

**The read itself is not the anomaly.** Requesting the value of a deep checksum *is* the index (*What a
deep buffer is*), so this returns what the contract says it should — except in its member typing: the
contract presents each member as a `Checksum`, and the code hands back the raw hex strings. What is
anomalous is everything around it: the read succeeds only because the dummy-Expression fast path skips
validation altogether, `.buffer` on the same Cell **raises** where `.value` succeeds (`CellBase.buffer`
validates against the un-mapped celltype), and every typed route — a path step, a retype — raises as
well. So the member typing that the value rule promises is left to the reader for now.

**Ruled (2026-09-21): the anomaly is to be fixed in the code first, and this passage removed from the
page afterwards.** What goes in the code is the anomaly and not the value rule — the unvalidated fast
path and the `.buffer` / `.value` split — which §4 item 3 of `cells-and-expressions-feature-1-4.md`
addresses anyway. This passage goes with it, because the one-step path then makes it unnecessary, not
because reading an index becomes illegal. The order matters: deleting the passage while the typed routes
still raise would leave agents concluding that Seamless cannot reach a deep child at all. Both halves are
tracked in `cells-and-expressions-feature-1-4.md`.

## How deep values reach a transformer

This is the pin layer, not the Expression layer; it is the place where the one shared flatness validator must also apply.

| Pin celltype | Value handed to the transformer |
|---|---|
| `deepcell` | dict of `Checksum` objects (no resolution; `_to_checksum_dict`) |
| `deepfolder` | dict of `Checksum` objects (no resolution) |
| `folder` | dict of child **contents**, resolved (`unpack_deep_structure`, one buffer per child) |

`deepfolder` and `folder` pins additionally carry `{"filesystem": {"mode": "directory"}}`, which is how a bash/compiled transformer gets the directory written to disk.

A transformer **result** may be declared `deepcell` or `folder`, but not `deepfolder` and not `module` (`transformer_class`): a result names what the transformer produced, and producing an index of buffers that the transformer never wrote is not a thing it can claim. `pack_deep_structure` turns a produced dict into an index.

In the workflow layer, `PIN_CELLTYPES = {"plain", "mixed", "deepcell", "deepfolder", "folder"}` is the set of Cell celltypes that admit a one-component subvalue connection (`seamless_workflow.context`) — the same "exactly one step" rule, expressed for graph edges.

### The output side: a deep result is an index

The table above is the **input** side. The output side is not a second contract: **a deep result is an index, exactly like a deep input.**

A result may be declared `deepcell` or `folder`, **not** `deepfolder` and not `module`. A result names what the transformer produced, and producing an index of buffers the transformer never wrote is not a claim it can make. `pack_deep_structure` turns the produced dict into an index, and the transformation's result checksum is that index's checksum — so a `Transformation` handle, a Cell fed by it, a pin fed by it **and a direct call** all end up with that index. A transformation returns a checksum, as it always does; for a deep celltype the corresponding value is the index — the general rule of *What a deep buffer is*, with nothing added for results.

Two consequences follow, and both are contract:

- **No fan-out on the way out.** Reading a deep result never resolves its children. `folder` is not a special case here: a caller that wants the bytes asks for them, through the one conversion that materializes children (`folder → mixed`, above), and pays that cost explicitly. Sugar that resolves N children behind a property read would hide an *all children* cost inside a shape that looks free, which is what *The organising principle* exists to prevent.
- **No claim on the leaves.** A transformation that produces a deep result holds a reference on the **index checksum only**, never on the members — the general no-recursive-deep-ownership rule, of which this is one instance (`contracts/internal/checksum-reference-lifecycle.md`, §8). Members rely on ordinary deep-buffer resolution and remote durability.

**Current behaviour, and it is ruled a defect.** `DirectCompiledTransformer.__call__` (`seamless-transformer/seamless_transformer/compiled_transformer.py:771-778`) checks `tf.celltype == "deepcell"` and returns `unpack_deep_structure(value, "deepcell")`, which resolves **every** child and returns a dict of deserialized `mixed` values — the opposite of the input side, where a `deepcell` pin hands over unresolved `Checksum` objects. The branch tests `deepcell` only, so a `folder` result already returns the raw index; that is the *correct* behaviour reached by accident, not a second bug. `unpack_deep_structure` was wrongly ported from legacy Seamless and **is to be replaced** — the same replacement that *Nesting is not contract* requires, since that function is also where the legacy nesting generality lives. Nothing may depend on its present behaviour.

## Current status: none of this is enforced yet

The rules above are the settled contract. **The code does not implement them.** Verified by inspection and by probing:

- **Deep celltypes are absent from the Expression path.** `seamless.checksum.expression`, `seamless.expression_class` and `seamless.checksum.hash_type_validation` contain no mention of `deepcell`, `deepfolder`, `folder` or `module`. There is no deep conversion table, no deep path rule and no flatness validator anywhere.
- **Every deep Expression currently fails, and for the wrong reason.** `HashType.deserializable_as` returns `False` for any celltype outside the 13 (its final `return False`), so `validate_deserializable_as` raises `HashTypeValidationError` for a deep `input_celltype` *or* a deep target celltype. Under the contract that fallthrough raises `ValueError` instead, and a deep Expression is admitted or refused at construction (*Where deep validation happens*). Probing confirms this for all of `deepfolder → plain`, `deepfolder → folder`, `deepcell → plain`, `folder → mixed`, the identity conversion, and any one-step path: all raise `HashTypeValidationError`, none of the legal shapes above works.
- **A deep `Cell` behaves like `plain` today.** With no path and the same input celltype, `Cell.checksum` short-circuits before building an Expression, so `.value` returns the raw index dict — **hex strings, where the contract presents `Checksum` objects** — for celltype `deepcell`, `deepfolder`, `folder` and `module` alike; no member typing, no fan-out. `.buffer` raises `HashTypeValidationError` (it calls `validate_deserializable_as` explicitly), and any projection or celltype change raises as well. A projected Cell inherits the parent's deep celltype rather than the member celltype. That short-circuit is the dummy-Expression fast path; see `contracts/cells.md` for the Cell read contract it belongs to.
- **Nesting is still accepted at the pin layer.** `unpack_deep_structure` and `pack_deep_structure` recurse through nested dicts and lists. The shared flatness validator does not exist.
- **The only fan-out that exists is the pin-level one**, and it is not the conversion described above: it resolves each child and returns `buffer.content`, i.e. Python `bytes`.

### What *is* settled

- **`folder → mixed` child representation, settled by ruling (2026-09-18), not yet by code.** The contract requires the 1-D `S1` array form above (see "`folder → mixed`"). The conversion itself does not exist yet, so nothing in the code implements this; the only existing fan-out (`unpack_deep_structure`, at the pin layer) returns Python `bytes`, which is a different, in-process-only presentation and must not be read as evidence for the `mixed`-serialization format.
- **A `folder` index buffer is byte-identical to a `deepfolder` index buffer.** There is no extra field and no per-celltype marker: the mount layer builds one index for both celltypes (`FileSystemService._read` treats `reg.directory`, i.e. either celltype, identically and emits `Buffer(index, 'plain')` with `{relative path: checksum hex}`), `_write_directory` consumes that same shape, and `Buffer(index, "folder")` and `Buffer(index, "deepfolder")` produce the same bytes and the same checksum. `folder → deepfolder` and `deepfolder → folder` are therefore genuinely checksum-preserving.
- **Directory mounts work**, and they are the one deep surface that is fully implemented: index construction from a tree, per-leaf atomic writes, the `deepfolder` sense-only rule, and leaf retention on the sense path. `contracts/mounts.md` specifies them; `contracts/attachments.md` specifies the retention exception to the no-recursive-deep-ownership rule.

## Agent guidance

- Treat a deep checksum as an index you may pass around freely. Holding it costs nothing and materializes nothing; reading its value gives `{key: Checksum}`, which is still nothing materialized.
- Use `deepfolder` when you want to refer to a directory, `folder` only when the consumer needs the bytes. The conversion between them is free, so declare the cheap one and widen late.
- Never write a nested deep structure. Flat, string keys, 64-hex values.
- Address a member in bracket form, and take `→ checksum` when you intend further work on it: the follow-up Expression is then keyed at the child and shared.
- Do not expect a decoded-text view of a `folder`. Decode per file with `bytes → text`, or decode the whole folder inside a transformer.
- Do not depend on the order in which `folder → mixed` resolves children, nor on it being parallel.
- Until the rules are implemented, do not put deep celltypes on Expressions or on any Cell that is projected or retyped: it raises `HashTypeValidationError`. The working surfaces today are transformer pins and mounts.
- If you need a child checksum before the rules land, read the parent's value and index it yourself (*Reading a deep child before the rules are enforced*) — the value of a deep checksum is the index, so this is sound; what is missing is the typed one-step route.
- A deep **result** is an index, like a deep input: reading it resolves no children, and nothing holds a claim on the leaves. Do not build on what the code does today — a direct-called `deepcell` result is materialized through a function that is ruled a mis-port and is to be replaced. See *The output side*.
