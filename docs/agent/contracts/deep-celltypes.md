# Deep Celltypes: `deepcell`, `deepfolder`, `folder` (Contract)

This page defines the three **deep celltypes** — `deepcell`, `deepfolder` and `folder` — as they behave under checksums, Expressions, Cells and transformer pins. `module` is **not** a deep celltype; see [`module` is not a deep celltype](#module-is-not-a-deep-celltype).

The 13 ordinary celltypes, the reference parser and the conversion rule table are defined in `contracts/celltypes-and-conversion.md`; checksum-level classification in `contracts/hashtype.md`; the directory-identity idea in `contracts/content-addressed-files-and-dirs.md`.

## Where this page sits: a carve-out, not a layer

The ordinary stack is celltypes and the type hierarchy → HashType → conversion → Expressions → Cells (`contracts/celltypes-and-conversion.md`, *Where this page sits*). **The deep celltypes are not a sixth layer; they are a carve-out at the Expression level**, and most of this page is about which Expression shapes over a deep checksum are legal.

| Ordinary stack | For a deep checksum |
|---|---|
| 13 celltypes, the subtype→supertype edges, and the rule table | **none of it applies.** The legal conversions are the table in *Zero-path conversions* below, and nothing else |
| HashType classifies the checksum | **no deep vocabulary, and it is never asked.** `deserializable_as` **raises `ValueError`** for a celltype outside the 13, and neither `capabilities` nor `conversion_feasible` is consulted for a deep step or a deep pair. Deep feasibility is structural and is settled here instead (`contracts/hashtype.md`; *Where deep validation happens*, below) |
| An Expression is a path plus at most one conversion, applied **project-then-convert** | **unchanged, and load-bearing.** Project-then-convert is what lets one step select a child checksum without materializing the parent; this shape could not exist under the opposite order (`contracts/expressions.md`, *Application order*) |
| Path length is unlimited | **exactly one step**, and it is a string item. A deep step is also a **fusion barrier** (`contracts/expressions.md`, *Fusion*) |
| An edge may carry a path **or** a conversion, never both | **carved out.** A deep step necessarily changes the celltype, so path and conversion always travel together; the criterion is this page's table instead (`contracts/cells.md`, *Connecting*) |
| Cost class can turn on the checksum's nullity and cached `HashType` | **shape alone decides** — see *The organising principle* |

One thing *is* ordinary: a deep buffer is plain JSON with an ordinary checksum, and everything downstream of a child checksum is ordinary wiring again.

The rules on this page are implemented, with the exceptions listed under [Implementation status](#implementation-status).

Code locations:

| Concern | Module / symbol |
|---|---|
| Buffer-layer mapping | `seamless.buffer_class.Buffer._map_celltype` (seamless-core) |
| The deep celltype set | `seamless.checksum.deep.DEEP_CELLTYPES` (seamless-core); `seamless_transformer.transformation_utils.DEEP_CELLTYPES`, `is_deep_celltype` |
| The shared flatness validator | `seamless.checksum.deep.validate_deep_structure` (seamless-core) |
| Construction-time shape check (deep conversions and the one-step path) | `seamless.checksum.expression.validate_expression_shape` (seamless-core) |
| Deep conversions in the engine | `seamless.checksum.convert.convert_checksum` (seamless-core) |
| Pin-level presentation and result packing | `seamless_transformer.transformation_utils.unpack_deep_structure`, `pack_deep_structure` |
| Pin presentation to a transformer | `seamless_transformer.transformation_namespace.build_transformation_namespace_sync`, `_to_checksum_dict` |
| Directory celltypes (mounts) | `seamless.checksum.canonical.DIRECTORY_CELLTYPES` (seamless-core); the mount rules are `contracts/mounts.md` |
| Mount read/write of an index | `seamless_workflow.attachments.fs.service.FileSystemService._read`, `._write_directory` |
| Index construction from files | `seamless_transformer.cmd.file_load` |
| Module definition buffers | `seamless_transformer.module_builder.pypackage_to_moduledict` |

## The organising principle

**Within the deep celltypes, an Expression's cost class is a function of its identity tuple `(input_celltype, path shape, celltype)` alone, never of the data behind the checksum.** Over the 13 ordinary celltypes this is weaker — cost can also turn on the checksum's own nullity and its cached `HashType` (`contracts/expressions.md`, *Cost class*) — but no deep conversion branches on anything but the declared celltypes, so here shape alone decides.

Every restriction below follows from that one rule. It is what makes the rules decidable at construction, before any buffer is materialized: two Expressions with the same shape must cost the same, so a shape may not sometimes be a free index read and sometimes a fan-out over all children. It is also why the legal set is small: each admitted shape has exactly one cost.

**The three cost classes are named here, and other pages use these words.** They classify **how many members a shape involves**, which is the thing that must not vary with the data:

| Class | Members involved | Buffers fetched to **evaluate** | Deep shapes in it |
|---|---|---|---|
| **free** | none | **none** — the result checksum comes from the rule alone | the identity conversion, and every index conversion in *Zero-path conversions* |
| **one child** | exactly one | **one: the index** | the one-step path, either target (*What the one step yields*) |
| **all children** | all of them | the index, **plus every member** | `folder → mixed`, and nothing else |

Two distinctions this table exists to keep straight:

- **Evaluating is not materializing.** A cost class is the cost of producing the **result checksum**. Reading the *value* of any result — deep or ordinary — needs that result's buffer, and that is a separate act with its own cost. So a *free* conversion is free to evaluate even though `.value` on its result still fetches the index buffer; and the *one child* class fetches the index to evaluate, and the member only if someone then asks for the member's value.
- **"One child" is about fan-out, not about buffers.** Only `folder → mixed` fetches members during evaluation.

`contracts/expressions.md`, *Cost class*, uses the same three names for the ordinary celltypes, where *one child* is simply *one buffer* — the input — because an ordinary value has no members.

## Where deep validation happens

**Deep feasibility is structural**: it turns on the declared celltypes and the shape of the path, never on the data behind the checksum. That is why it is decided **at Expression construction**, by this page's tables, and never by a checksum-level classification. An Expression outside the tables is refused at construction with `ValueError`.

| Expression | Vetted by |
|---|---|
| **pathless**, deep on either side | the **conversion engine**'s deep table: the conversions of *Zero-path conversions* |
| **pathed**, deep on either side | the **deep path table** of *Paths*, below: exactly one string-item step, and the member-celltype rules |

**HashType is not consulted, and must not be asked.** `deserializable_as` accepts only the 13 ordinary celltypes and raises `ValueError` on anything else; it does not answer `False` for a deep name, and it does not learn the four structural names (`contracts/hashtype.md`). The division is: **this page validates structure, ahead of any data; HashType validates what a checksum's own word proves, once the value is known** — which for a deep index is the ordinary `JSON_OBJECT` classification of a `plain` buffer, nothing deep. One shared validator, `validate_deep_structure`, checks flatness for the Expression layer, for Cell reads and for pins (*Nesting is not contract*); it lives on this side of the line, not inside HashType.

`contracts/expressions.md`, *When an Expression is vetted*, states the same split from the Expression side.

## What a deep buffer is

- **At the buffer layer there is no deep format.** `Buffer._map_celltype` maps `deepcell`, `deepfolder`, `folder` (and `module`) to `plain`. A deep buffer is ordinary plain JSON, serialized and parsed by the `plain` rules, and its checksum is an ordinary checksum.
- **A deep buffer is an index**: a **flat** dict with string keys and 64-character lowercase hex checksum strings as values. Nothing else. Flatness is contract (see [Nesting is not contract](#nesting-is-not-contract)).
- **Keys are opaque strings.** They carry no path semantics at this layer. Only the mount layer reads `/` as a directory separator. `deepfolder` and `folder` keys routinely contain `/`.
- **The members are referenced, not contained.** The index commits to the child checksums, and a deep checksum can be held, compared and passed around without any child buffer being present.

**Requesting the *value* of a deep checksum yields the index.** This holds at every layer that can be asked for a value — `Checksum.resolution(celltype)`, `Buffer.get_value`, `Cell.value`, a `Pin`, a transformer result. There is no deep format below the index to unpack: `_map_celltype` sends the deep celltypes to `plain`, and the index is what a `plain` parse of that buffer gives, validated for flatness. So:

- the value is that index, **with each member presented as a `Checksum` object**: `{key: Checksum}`. The 64-hex strings are the **buffer's** form; `Checksum` is the **API's** form, and they are the same index. Serializing such a dict back at a deep celltype writes the same hex JSON, so the round trip preserves the checksum;
- `.buffer` at a deep celltype returns the index buffer; it validates against the same mapped celltype as `.value`;
- **nothing is resolved.** No member buffer is touched, and the cost class is *free*. A `Checksum` object is not a buffer: wrapping is typing, not resolution;
- the dict of `Checksum` objects that a `deepcell` or `deepfolder` **pin** hands a transformer (*How deep values reach a transformer*) is therefore not a pin-layer special case — it is this rule, at the pin layer;
- the `folder` pin's dict of child *contents* **is** a pin-layer presentation, and it is the one place that resolves children on the input side, because the pin also carries `{"filesystem": {"mode": "directory"}}`. The value-level equivalent is the explicit `folder → mixed` conversion, which is *all children* and is priced as such.

The three celltypes share this buffer shape exactly. They differ only in **what their members are**, and in what a consumer is declaring it wants:

| Celltype | A member checksum is | Member celltype | Intent |
|---|---|---|---|
| `deepcell` | a buffer deserializable as `mixed` | `mixed` | a collection of Seamless values, addressed by key |
| `deepfolder` | an arbitrary raw byte buffer | `bytes` | the **index** of a directory; the contents stay by reference |
| `folder` | an arbitrary raw byte buffer | `bytes` | the **contents** of a directory; consumers want the bytes |

`deepfolder` and `folder` therefore have the same member type and differ only in intent. `deepcell` is the strict one: its member type is a subtype of the other two.

**A `folder` index buffer is byte-identical to a `deepfolder` index buffer.** There is no extra field and no per-celltype marker: the mount layer builds one index for both celltypes (`FileSystemService._read` treats either directory celltype identically and emits `Buffer(index, "plain")` with `{relative path: checksum hex}`), `_write_directory` consumes that same shape, and `Buffer(index, "folder")` and `Buffer(index, "deepfolder")` produce the same bytes and the same checksum. That is why `folder → deepfolder` and `deepfolder → folder` are genuinely checksum-preserving.

**The intent is load-bearing in exactly one place: `deepfolder` is sense-only on a mount.** `folder` mounts in `r`, `w` and `rw`; `deepfolder` may only be mounted with `mode="r"`, because a write mount materializes every leaf onto disk — which is precisely what "the contents stay by reference" declares it does not do. The restriction costs one retype, since the conversion between the two is free in both directions, and a transformer cannot produce a `deepfolder` at all. Directory mounts — index construction from a tree, per-leaf atomic writes, the sense-only rule and leaf retention on the sense path — are specified in `contracts/mounts.md`; the retention exception to the no-recursive-deep-ownership rule is in `contracts/attachments.md`.

## `module` is not a deep celltype

`DEEP_CELLTYPES = ("deepcell", "deepfolder", "folder")`. `module` is deliberately not in it, and **none of the rules on this page apply to `module`.**

A `module` buffer is a plain JSON *module definition* holding literal code strings, not checksums:

```
{"language": ..., "type": "interpreted",
 "code": <str> | {"<dotted.name>": {"language", "code", "dependencies"}, ...}}
```

It travels as celltype `plain` with subcelltype `module` (`pretransformation` builds the pin as `{"celltype": "plain", "subcelltype": "module"}`), and a transformer pin declared `module` is resolved by the module builder, not by any deep unpacking. Some older notes group `module` with the deep celltypes; that grouping is wrong. The only property `module` shares with them is that `Buffer._map_celltype` sends it to `plain`. The conversion engine does not accept `module` (`TypeError`; `contracts/celltypes-and-conversion.md`).

## Nesting is not contract

Legacy Seamless allowed deep structures with nested dicts and lists and checksums at the leaves. That generality has no producer and no consumer in current Seamless. **A deep index that is not flat is invalid.**

Flatness is enforced by **one shared validator**, `validate_deep_structure`, used at the Expression layer, on Cell and `Buffer` reads at a deep celltype, and at the pin layer (`unpack_deep_structure`, `pack_deep_structure`). Two independent checks would drift, and pins would then accept values that Expressions refuse — which would mean the two layers disagree about what a deep value is.

Flatness is a property of the **index**, not of the members. A `deepcell` member is a `mixed` value behind a checksum, and that value may itself be a dict or a list (*The output side*); what may not be nested is the index that references it.

### When flatness is checked, and what a false deep claim does

**Flatness is a property of the buffer, so it can only be checked with the buffer in hand.** That fixes the phase exactly:

| Operation | Is the index parsed? | Flatness checked? |
|---|---|---|
| declaring a celltype, or constructing a deep Expression | no | no — construction checks celltypes and path *shape* only (`contracts/expressions.md`, *When an Expression is vetted*) |
| a checksum-preserving zero-path conversion (`deepcell → deepfolder`, `deepcell → plain`, …) | **no** | **no** |
| a one-step path | yes | **yes** |
| reading `.value` at a deep celltype | yes | **yes** |
| reading `.buffer` at a deep celltype | yes | **yes** |
| `folder → mixed` | yes | **yes** |
| pin unpacking or result packing (`unpack_deep_structure` / `pack_deep_structure`) | yes | **yes** |

So **a checksum falsely declared deep is not detected by a free conversion, and that is by design.** `deepcell → deepfolder` on a checksum whose buffer is not an index at all succeeds silently and yields the same checksum, exactly as `plain → mixed` succeeds on a checksum whose buffer is not valid `plain`. A declared celltype is a *claim* about a checksum; a conversion that never looks at the bytes never tests the claim. The claim is tested at the first operation that parses the index, and it fails there.

**The one checksum-level check that is available** is the *mapped* one: a deep buffer is a `plain` buffer, so `deserializable_as(checksum, "plain")` is a legitimate cheap disproof — a non-JSON buffer declared `deepcell` can be refused without a fetch. That is also the only way HashType ever participates in a deep decision: it sees `plain`, never a deep name (`contracts/hashtype.md`).

**The failure.** The shared validator raises `ValueError`, naming the offending key or shape — a non-dict, nesting, a non-string key, or a member that is not a 64-character lowercase hex string. Inside an Expression it surfaces as `ExpressionEvaluationError` (error-envelope kind `expression_evaluation`), like any other failure of a path step; at the pin layer it becomes the pin's failure, reported on the pin before any transformation is built (`contracts/pins.md`). It is **not** a `HashTypeValidationError`: no checksum-level classification was consulted and none could have answered. (Contrast the member check of a one-step path, *What the one step yields*, which *is* a HashType disproof and raises `HashTypeValidationError`.)

## Conversions

### Zero-path conversions

Only these are legal. Every one of them is **free** — no buffer fetched to evaluate and no child touched — except `folder → mixed`. (Free to *evaluate*: reading the resulting index's value still fetches the index buffer, as reading any value does.)

| Conversion | Cost class | Checksum | Notes |
|---|---|---|---|
| identity (source celltype = target celltype) | free | preserved | the dummy Expression; always legal |
| `deepcell → plain` | free | preserved | read the index as what it already is |
| `deepfolder → plain` | free | preserved | idem |
| `folder → deepfolder` | free | preserved | drop the intent to materialize; the index is unchanged |
| `deepfolder → folder` | free | preserved | add the intent to materialize |
| `deepcell → deepfolder` | free | preserved | widen the member type |
| `folder → mixed` | **all children** | new buffer | the only conversion in the system that materializes children |
| everything else | — | — | **illegal**: refused at construction with `ValueError`; the engine, if called directly, raises `SeamlessConversionError` without fetching |

Illegal pairs worth spelling out:

- **`deepfolder → deepcell` is illegal.** This is the celltype hierarchy (`contracts/celltypes-and-conversion.md`, *The celltype hierarchy is a checksum hierarchy*) applied one level down, to members: a subtype→supertype edge means every checksum valid as the subtype is valid, unchanged, as the supertype. `deepcell` members must be deserializable as `mixed`; `deepfolder` members are arbitrary bytes. So `deepcell → deepfolder` widens and is free, and the reverse would require proving a property of every member — work proportional to the number of children, hidden behind a shape that looks free.
- **`folder → plain` is illegal**, although `deepfolder → plain` is legal and the two have identical buffers. Admitting it would put a free index read and an all-children fan-out under the same identity tuple, depending only on which celltype the source happened to be declared as. Convert `folder → deepfolder → plain` (both free) if the index is what you want.
- **`plain → deepcell`, `plain → deepfolder` and `plain → folder` are illegal**: promoting an arbitrary plain value to an index would require validating every entry.

**Null does not make an illegal pair legal**. The canonical null short-circuits only on the **legal** pairs of the table above: there a null input yields the canonical null result without evaluating (for `folder → mixed`, a null index has no children, so nothing is fetched). On an illegal deep pair, null is refused exactly like any other checksum — `ValueError` at construction, `SeamlessConversionError` from the engine. Null being deserializable as every celltype is a statement about readings, not a licence to convert along a pair the table refuses (`contracts/celltypes-and-conversion.md`, *Null and conversion legality*; `contracts/hashtype.md`). The same holds for the forbidden *ordinary* pairs (`contracts/celltypes-and-conversion.md`, *Null and conversion legality*).

### `folder → mixed`

- **All-or-nothing.** The result is the complete dict of children, or an error. There is no partial result.
- **Per-child failure is not sticky.** A child that could not be resolved does not poison the deep checksum; a later attempt may succeed (for example once the buffer is reachable again).
- **Resolution order and concurrency are unspecified.** Children may be resolved in any order, sequentially or in parallel. Concurrency here is an optimization, not contract. Do not depend on an observed order, and do not treat parallelism as guaranteed.
- **It is the only Expression that needs more than one buffer.** Every other Expression materializes **at most** one checksum — exactly one where it needs a buffer at all, and none where it is *free* (the identity conversion, every index conversion above, a null short-circuit). `folder → mixed` needs the index plus every child. That is a further reason the fan-out is confined to this one conversion.
- **Three mechanisms are involved, and they are distinct** (`contracts/expressions.md`, *Deduplication*). The evaluation has one **member set**, keyed by its Expression identity like any other Expression's, and cancellation reaches the children only through it. Each child fetch is an ordinary **shared fetch**, keyed by the child's checksum and shared with any other request for that child (`contracts/expressions.md`, *Buffer fetches are shared by checksum*). A **multi-checksum waiter**, which would fetch all children in parallel and leave all their fetches when the evaluation is cancelled, is **deferred**: today the children are fetched one after another, so the evaluation waits on one fetch at a time (*Implementation status*).
- **Each child is a 1-D NumPy `S1` array, one element per byte** (`np.frombuffer(content, dtype="S1")`), **never a 0-dimensional `S<N>` scalar.** Only the 1-D form round-trips faithfully — a 0-d scalar's `.tobytes()` turns an empty child into `b"\x00"`, and `.item()` strips trailing NULs (`b"ab\x00\x00"` reads back as `b"ab"`), because NumPy's `S` dtype strips trailing NULs on scalar extraction. Serializing a dict of Python `bytes` into `mixed` produces 0-d scalars and must never be the route by which a `folder` value is serialized as `mixed`. The `folder` pin handing the transformer Python `bytes` (*How deep values reach a transformer*) is a separate, in-process presentation, not this serialization route.

### Conversion stops at `mixed`

**There is no conversion that yields a dict of decoded strings.** `folder → mixed` delivers each child as raw bytes in the `S1` form above, and conversion ends there.

A value-level route for `mixed → plain` was considered and rejected. `mixed → plain` is a pure *reinterpretation* (`conversion_reinterpret`: the same bytes must parse as JSON, and the checksum is preserved). Giving it a value-level route would make every `S` array in every `mixed` buffer decode to text, everywhere in the system, and would make the pair only *sometimes* checksum-preserving. That is too much global semantics to buy one convenience.

Decode it yourself instead:

- **per file**: take the child's checksum (a one-step path, below) and run an ordinary `bytes → text` Expression on it — keyed at the child checksum, so it is shared by every parent that references that child;
- **per folder**: decode inside a transformer. This is the idiomatic route: decoding a folder's files is content transformation, not celltype reinterpretation.

**Footnote (not a bug).** An *empty* folder does survive the chain `folder → mixed → plain`. Its `mixed` buffer is literally `b"{}\n"`, which is valid JSON, so the reinterpretation succeeds and the checksum is preserved. Every non-empty folder serializes to a framed Seamless-mixed buffer (`b"\x94SEAMLESS-MIXED\x0bmixed-plain..."`), classified `MIXED_OBJECT`, for which `conversion_feasible` answers `False` and `convert_checksum` raises `SeamlessConversionError` — for all-UTF-8 contents exactly as much as for binary ones. So `{}` succeeds where every non-empty folder is rejected. This is a consequence of buffer identity, not a special case for empty folders.

## Paths

**A deep Expression admits exactly one path step, and that step is a string item.** It selects one member of the index. The result celltype is either the member celltype or `checksum`; nothing else is legal.

| Source | Member celltype | Legal one-step targets |
|---|---|---|
| `deepcell` | `mixed` | `mixed`, `checksum` |
| `deepfolder` | `bytes` | `bytes`, `checksum` |
| `folder` | `bytes` | `bytes`, `checksum` |

**Write the step in bracket form.** Keys are opaque and routinely contain `/`, `.` and other characters that attribute access cannot express: use `expr["path/to/file.txt"]`, not `expr.file`.

### What the one step yields

Both targets are evaluated from **the index buffer alone**: the child's checksum is read out of the index, and **no member buffer is fetched to produce the result**. They differ in what the result *is*.

| One-step Expression | Result checksum | New buffer? | To evaluate | To read `.value` |
|---|---|---|---|---|
| `(index, "['k']", deep, member celltype)` | **the child's own checksum** | no | the index | the **child's** buffer |
| `(index, "['k']", deep, "checksum")` | the checksum of a **new** `checksum`-celltype buffer holding the child's digest | yes — 64 bytes | the index | that 64-byte buffer, giving a `Checksum` |

Consequences, all of them ordinary machinery rather than deep special cases:

- **`→ member celltype` is the cheap handle on a child.** Its result checksum *is* the child's, so `compute()` answers the child's checksum, and every later Expression over that result is keyed at the **child** — shared by every parent index that references it. The reverse index gains a route from the child checksum back to `(parent index, key)`, which is exactly what makes a child recoverable by fingertipping the parent.
- **`→ checksum` is the *reference* form**, and it obeys the ordinary `checksum` celltype rules (`contracts/celltypes-and-conversion.md`): a `checksum`-celltype buffer is the 64-character hex digest, classified `EQ64`. Converting it onwards is `checksum → X`, which **dereferences** — it returns the referenced checksum as its result with no new buffer — so the child's own conversions end up keyed at the child there too. The two targets therefore converge; `→ checksum` simply costs one extra tiny buffer and one extra Expression on the way.
- **The member check stays at checksum level, and its failure is `HashTypeValidationError`.** Whether the child is really deserializable at the member celltype is a question for the child's own `HashType`, asked without fetching the child. When that HashType proves the member celltype impossible (for example, a `deepcell` member whose buffer is known not to be `mixed`), the step raises **`HashTypeValidationError`**. When it cannot decide (`None`), the step succeeds; the step never fetches a member to check it.
- **`run()` differs accordingly**: on `→ member celltype` it materializes the child's value; on `→ checksum` it returns a `Checksum`.

Why the rule is exactly one step, with exactly these targets:

- **An empty path is the fan-out.** The no-step shapes are the index conversions and `folder → mixed`; the one-step shape is exactly one child. Keeping them distinct keeps the cost classes distinct.
- **A longer path would have to continue into the child.** The child is a different checksum, and therefore a different Expression. A two-step deep path would smuggle a second, unrelated evaluation into one identity tuple.
- **Restricting the result to the member celltype keys the child's own conversion at the child checksum.** `deepfolder[k] → bytes → text` is two Expressions: the second is identified by the *child's* checksum, so its result is shared by every parent index that references that child, and by anyone holding the child checksum directly. Allowing `deepfolder[k] → text` in one step would re-key that same work under each parent.
- **The step is only expressible because Expressions project before they convert.** `input_celltype` decides what the path walks — here, the index — and `celltype` renders only what the step selected. Under the opposite order the output celltype would decide the structure being walked, and "select a child of this index without materializing the parent" would have nowhere to live (`contracts/expressions.md`, *Application order*).
- **The step is a fusion barrier.** A run of projecting edges collapses into one Expression everywhere else; it stops at a deep step, because the step's result is a *checksum*, and a following path would project into the checksum rather than into what it names. Fusing past it would also re-key the child's shared work under each parent (`contracts/expressions.md`, *Fusion*).

No HashType capability is involved in admitting the step: it is admitted or refused at construction by the table above. A flat index is an ordinary `JSON_OBJECT` buffer, and `capabilities` classifies it as a map under `plain` or `mixed` like any other JSON object (`contracts/hashtype.md`), but that answer is never asked for a deep name.

### Handles and writes one step below a deep parent

A Cell projection is the same one-step Expression, so the table above applies to it (`contracts/cells.md`, *Deep celltypes on a Cell*, *Projections*).

**One step below a deep parent, a projection or handle carries the member celltype** — `mixed` below a `deepcell`, `bytes` below a `deepfolder` or `folder` — for bound and standalone Cells alike. `d["k"].celltype` is the member celltype, `d["k"].checksum` is the child's checksum, and `d["k"].value` is the child's value. `d["k"].as_celltype("checksum")` gives the reference form.

**Writes at `k` replace `index[k]` with a member checksum.** As with every write through a handle, they are pathed writes to the parent: a read-modify-set of the index, with authority checked on the root (`contracts/cells.md`, *Writes through a handle*). What gets inserted is always a checksum, so the index stays flat:

| Write at `k` | What goes into `index[k]` |
|---|---|
| `.checksum = cs`, `.set_checksum(cs)` | the member checksum `cs`, resolved at the member celltype |
| `.buffer = buf`, `.set_buffer(buf)` | the checksum of `buf`, validated at the member celltype |
| `.set(v)`, `.value = v` | the checksum of `v` serialized at the member celltype (`mixed` for `deepcell`, `bytes` for `deepfolder`/`folder`) |

Every other entry of the index is unchanged, and the parent's new checksum is the checksum of the new index. A member that cannot be resolved raises `CacheMissError` to the caller, and nothing is recorded. Clearing through the handle follows the general sub-path rule of `contracts/cells.md` (`ValueError`).

**Writes below `k` are illegal** — for example, `d["k"]["x"] = v` or `d["k"]["x"].set(v)`. A member is behind a checksum; a write into it would be a write into a different checksum. The exception class is an open question the author has deferred; do not rely on a specific class.

### Bound wiring around the step

- **Writing an ill-formed deep link raises `ValueError`**, the class the Expression constructor uses for a statically ill-formed shape (`contracts/expressions.md`, *Which refusal happens where*). This covers an integer key, a slice, a second step and an illegal deep conversion, and the graph is left unchanged. `set_graph` does not refuse a graph that contains such an entry. The entry is ill-formed, and the cells it feeds are `blocked` with reason `blocked-by-miswiring` (`contracts/node-state-lifecycle.md`).
- **The reference form must be spelled out.** `ctx.x = ctx.d["k"].as_celltype("checksum")` gives it. Assigning the bare handle `ctx.d["k"]` into an existing `checksum` cell is refused with the wiring rule's `TypeError`, because the handle carries a path at the member celltype and the target would convert behind it (`contracts/cells.md`, *Connecting*).
- **Built through a handle, the reference form is two Expressions.** The first is the step to the member celltype, which yields the child's own checksum. The second is `member celltype → checksum` over the child. The result checksum equals that of the one-step `→ checksum` Expression in *What the one step yields*, but the identity differs, because the step forms no pair (*Paths*).
- **A conversion before the step is never elided.** In `ctx.d.as_celltype("deepfolder")["k"]`, the conversion's result is the index that the step reads. The step forms no pair, so the anonymous cell holding the converted index is evaluated (`contracts/cells.md`, *Anonymous cells, symbols and elision*).

### Graph edges into a deep cell

In the workflow layer, `seamless_workflow.context.PIN_CELLTYPES = {"plain", "mixed", "deepcell", "deepfolder", "folder"}` is — despite its name — about Cells, not transformer pins. It is the set of Cell celltypes that may be the **target of a sub-path edge**, such as the join `ctx.c["k"] = ctx.x`. A sub-path edge into a Cell of any other celltype is refused with `PathError("Cell subvalue connections require a container-capable Cell")`.

For a deep target, `ctx.d["k"] = ctx.x` requires the source to carry the target's member celltype: `mixed` for `deepcell`, `bytes` for `deepfolder` and `folder`. Other source celltypes are refused with `TypeError` before the graph changes; a non-string target key is refused with `ValueError`, and so are the reserved names `"<root>"` and `"<numeric>"` (`contracts/cells.md`, *Projections*; the exception class for those two is deferred). The edge contributes the member checksum directly to the flat index, with no conversion to the root celltype and no member resolution. A literal root index may supply other entries; a root source cannot coexist with sub-path edges. Later changes to either celltype that make the member combination incompatible make the join `miswired`. Compatible failed members leave it `blocked` with `blocked-by-error`. See `contracts/cells.md`, *Cell-level joins*, for an executable example and reactive behavior.

**A deep join is a `deepcell` or `deepfolder` cell join** (`contracts/expressions.md`, *Cell joins*). A join into a `folder` cell forms a `deepfolder` cell join; the two give byte-identical results. A deep join is always evaluated in this process and is never dispatched. It needs no member buffer, however large the members are and wherever they are stored: only the root index, when there is one, must be reachable from this process.

This rule is not the deep one-step path rule. It applies to `plain` and `mixed` as much as to the deep celltypes, and its one-level limit comes from the general rule that a connection target is the root or one level below it (`contracts/cells.md`, *Projections*). The two rules only happen to stop at the same depth.

## How deep values reach a transformer

This is the pin layer, not the Expression layer; the shared flatness validator applies here too.

| Pin celltype | Value handed to the transformer |
|---|---|
| `deepcell` | dict of `Checksum` objects (no resolution; `_to_checksum_dict`) |
| `deepfolder` | dict of `Checksum` objects (no resolution) |
| `folder` | dict of child **contents** as Python `bytes`, resolved (`unpack_deep_structure`, one buffer per child) |

`deepfolder` and `folder` pins additionally carry `{"filesystem": {"mode": "directory"}}`, which is how a bash transformer gets the directory written to disk. A compiled transformer cannot take a directory this way: a deep celltype is never compatible with a compiled pin, and declaring one raises (`contracts/compiled-pins.md`).

### The output side: a deep result is an index

The table above is the **input** side. The output side is not a second contract: **a deep result is an index, exactly like a deep input.**

A result may be declared `deepcell` or `folder`, **not** `deepfolder` and not `module` (`transformer_class`). A result names what the transformer produced, and producing an index of buffers the transformer never wrote is not a claim it can make.

`pack_deep_structure` turns the produced dict into an index. The produced dict must be flat at the key level — a dict with string keys — and each member is either a checksum (a `Checksum` or a 64-hex string), inserted as is, or a value, serialized and replaced by its checksum. **A `deepcell` member may be any `mixed` value, including a dict or a list**: it is serialized as `mixed`, and the index stays flat because it holds only that member's checksum. (An earlier refusal of dict and list members in `pack_deep_structure` was a bug; it is fixed.)

The transformation's result checksum is that index's checksum, so a `Transformation` handle, a Cell fed by it, a pin fed by it **and a direct call** all end up with that index. A transformation returns a checksum, as it always does; for a deep celltype the corresponding value is the index, `{key: Checksum}` — the general rule of *What a deep buffer is*, with nothing added for results. This includes the direct compiled transformer (`Transformer(..., compiled=True, direct=True)`): a `deepcell` result is returned as the validated index of `Checksum` objects, with no child resolved.

Two consequences follow, and both are contract:

- **No fan-out on the way out.** Reading a deep result never resolves its children. `folder` is not a special case here: a caller that wants the bytes asks for them, through the one conversion that materializes children (`folder → mixed`, above), and pays that cost explicitly. Sugar that resolves all children behind a property read would hide an *all children* cost inside a shape that looks free, which is what *The organising principle* exists to prevent.
- **No claim on the leaves.** A transformation that produces a deep result holds a reference on the **index checksum only**, never on the members — the general no-recursive-deep-ownership rule, of which this is one instance (`contracts/internal/checksum-reference-lifecycle.md`, §8). Members rely on ordinary deep-buffer resolution and remote durability.

## Implementation status

Deep `.buffer` reads now validate both the mapped `plain` celltype and index flatness, in standalone and bound Cells and Pins. They return the index buffer without resolving its children; failures are raised on each read and leave the owner complete. Focused plain tests cover these routes in the deep-celltype and Pin contract test files.

**Current limitations** (not contract violations):

- **`folder → mixed` fetches its children one at a time.** `_evaluate_expression_async` awaits each child's `resolution()` in index order, the synchronous path calls `resolve()` per child, and the `folder` pin (`unpack_deep_structure`) does the same. Resolution order and concurrency are unspecified (*`folder → mixed`*), so this is not a gap. The parallel multi-checksum waiter is deferred.

## Agent guidance

- Treat a deep checksum as an index you may pass around freely. Holding it costs nothing and materializes nothing; reading its value gives `{key: Checksum}`, which is still nothing materialized.
- Use `deepfolder` when you want to refer to a directory, `folder` only when the consumer needs the bytes. The conversion between them is free, so declare the cheap one and widen late.
- Reach a single child with the one-step path, `cell["key"]` (bracket form): it yields the child's checksum at the member celltype, or at `checksum` for the reference form. Do not chain a second step or a second conversion into it; apply further conversions as separate Expressions, keyed at the child.
- Never write a nested deep index. Flat, string keys, 64-hex values. A `deepcell` *member* may be any `mixed` value, dicts and lists included.
- To change one member, write at `k` (`d["k"].set(v)`, `.checksum =`, `.buffer =`); never write below `k`.
- Do not expect null to rescue an illegal deep conversion: an illegal pair fails for null too.
- Do not expect a decoded-text view of a `folder`. Decode per file with `bytes → text`, or decode the whole folder inside a transformer.
- Do not depend on the order in which `folder → mixed` resolves children, nor on it being parallel.
- A deep **result** is an index, like a deep input: reading it resolves no children, and nothing holds a claim on the leaves.
