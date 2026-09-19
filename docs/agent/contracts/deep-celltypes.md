# Deep Celltypes: `deepcell`, `deepfolder`, `folder` (Contract)

This page defines the three **deep celltypes** — `deepcell`, `deepfolder` and `folder` — as they behave under checksums, Expressions and conversion. `module` is **not** a deep celltype; see [`module` is not a deep celltype](#module-is-not-a-deep-celltype).

The 13 ordinary celltypes, the reference parser and the conversion rule table are defined in `contracts/celltypes-and-conversion.md`; checksum-level classification in `contracts/hashtype.md`; the directory-identity idea in `contracts/content-addressed-files-and-dirs.md`.

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

**An Expression's cost class is a function of its identity tuple `(input_celltype, path shape, celltype)`, never of the data behind the checksum.**

Every restriction below follows from that one rule. It is what makes the rules decidable at validation time, before any buffer is materialized: two Expressions with the same shape must cost the same, so a shape may not sometimes be a free index read and sometimes an N-child fan-out. It is also why the legal set is small: each admitted shape has exactly one cost — free (checksum-preserving), one child, or all children.

## What a deep buffer is

- **At the buffer layer there is no deep format.** `Buffer._map_celltype` maps `deepcell`, `deepfolder`, `folder` (and `module`) to `plain`. A deep buffer is ordinary plain JSON, serialized and parsed by the `plain` rules, and its checksum is an ordinary checksum.
- **A deep buffer is an index**: a **flat** dict with string keys and 64-character lowercase hex checksum strings as values. Nothing else. Flatness is contract (see [Nesting is not contract](#nesting-is-not-contract)).
- **Keys are opaque strings.** They carry no path semantics at this layer. Only the mount layer reads `/` as a directory separator. `deepfolder` and `folder` keys routinely contain `/`.
- The members are *referenced*, not contained: the index commits to the child checksums, and a deep checksum can be held, compared and passed around without any child buffer being present.

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

## Conversions

### Zero-path conversions

Only these are legal. Every one of them is free (checksum-level, no child touched), except `folder → mixed`.

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

### The `folder` note: conversion stops at `mixed`

**Conversion stops at `folder → mixed`.** The children arrive as raw byte arrays (NumPy 0-dimensional `S`-dtype values, the standard `mixed` representation of Python `bytes`). **There is no conversion that yields a dict of decoded strings.**

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

Why:

- **An empty path is the fan-out.** The no-step shapes are the index conversions and `folder → mixed`; the one-step shape is exactly one child. Keeping them distinct keeps the cost classes distinct.
- **A longer path would have to continue into the child.** The child is a different checksum, and therefore a different Expression. A two-step deep path would smuggle a second, unrelated evaluation into one identity tuple.
- **Restricting the one-step result to the member celltype keys the child's own conversion at the child checksum.** `deepfolder[k] → bytes → text` is two Expressions: the second is identified by the *child's* checksum, so its result is shared by every parent index that references that child, and by anyone holding the child checksum directly. Allowing `deepfolder[k] → text` in one step would re-key that same work under each parent.

**Write the step in bracket form.** Keys are opaque and routinely contain `/`, `.` and other characters that attribute access cannot express: use `expr["path/to/file.txt"]`, not `expr.file`.

No new HashType capability is needed for the step itself: a flat index is a JSON object, and `capabilities` already yields `{"MAP"}` for a `JSON_OBJECT` word under `plain`/`mixed` (`contracts/hashtype.md`). Only the source-celltype dispatch would have to learn the deep celltypes, which currently fall through to the empty set.

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

## Current status: none of this is enforced yet

The rules above are the settled contract. **The code does not implement them.** Verified by inspection and by probing:

- **Deep celltypes are absent from the Expression path.** `seamless.checksum.expression`, `seamless.expression_class` and `seamless.checksum.hash_type_validation` contain no mention of `deepcell`, `deepfolder`, `folder` or `module`. There is no deep conversion table, no deep path rule and no flatness validator anywhere.
- **Every deep Expression currently fails.** `HashType.deserializable_as` returns `False` for any celltype outside the 13 (its final `return False`), so `validate_deserializable_as` raises `HashTypeValidationError` for a deep `input_celltype` *or* a deep target celltype. Probing confirms this for all of `deepfolder → plain`, `deepfolder → folder`, `deepcell → plain`, `folder → mixed`, the identity conversion, and any one-step path: all raise `HashTypeValidationError`, none of the legal shapes above works.
- **A deep `Cell` behaves like `plain` today.** With no path and the same input celltype, `Cell.checksum` short-circuits before building an Expression, so `.value` returns the raw index dict for celltype `deepcell`, `deepfolder`, `folder` and `module` alike — no member typing, no fan-out. `.buffer` raises `HashTypeValidationError` (it calls `validate_deserializable_as` explicitly), and any projection or celltype change raises as well. A projected Cell inherits the parent's deep celltype rather than the member celltype. That short-circuit is the dummy-Expression fast path; see `contracts/cells.md` for the Cell read contract it belongs to.
- **Nesting is still accepted at the pin layer.** `unpack_deep_structure` and `pack_deep_structure` recurse through nested dicts and lists. The shared flatness validator does not exist.
- **The only fan-out that exists is the pin-level one**, and it is not the conversion described above: it resolves each child and returns `buffer.content`, i.e. Python `bytes`.

### Points not settled by the code

- **`folder → mixed` child representation.** The contract says children arrive as NumPy `S`-dtype byte values; the only implemented fan-out (`unpack_deep_structure`) returns Python `bytes`. The conversion itself does not exist, so the code does not settle which is normative. Note that the two are not interchangeable at the edges: serializing a dict of Python `bytes` as `mixed` and reading it back gives 0-dimensional `S`-dtype arrays whose width is the child's length, so a child of `b""` comes back as dtype `S1` and `.tobytes()` yields `b"\x00"`, and the byte identity of an empty child is lost. A `bytes`-valued dict has no such problem.

### What *is* settled by the code

- **A `folder` index buffer is byte-identical to a `deepfolder` index buffer.** There is no extra field and no per-celltype marker: the mount layer builds one index for both celltypes (`FileSystemService._read` treats `reg.directory`, i.e. either celltype, identically and emits `Buffer(index, 'plain')` with `{relative path: checksum hex}`), `_write_directory` consumes that same shape, and `Buffer(index, "folder")` and `Buffer(index, "deepfolder")` produce the same bytes and the same checksum. `folder → deepfolder` and `deepfolder → folder` are therefore genuinely checksum-preserving.
- **Directory mounts work**, and they are the one deep surface that is fully implemented: index construction from a tree, per-leaf atomic writes, the `deepfolder` sense-only rule, and leaf retention on the sense path. `contracts/mounts.md` specifies them; `contracts/attachments.md` specifies the retention exception to the no-recursive-deep-ownership rule.

## Agent guidance

- Treat a deep checksum as an index you may pass around freely. Holding it costs nothing and materializes nothing.
- Use `deepfolder` when you want to refer to a directory, `folder` only when the consumer needs the bytes. The conversion between them is free, so declare the cheap one and widen late.
- Never write a nested deep structure. Flat, string keys, 64-hex values.
- Address a member in bracket form, and take `→ checksum` when you intend further work on it: the follow-up Expression is then keyed at the child and shared.
- Do not expect a decoded-text view of a `folder`. Decode per file with `bytes → text`, or decode the whole folder inside a transformer.
- Do not depend on the order in which `folder → mixed` resolves children, nor on it being parallel.
- Until the rules are implemented, do not put deep celltypes on Expressions or on any Cell that is projected or retyped: it raises `HashTypeValidationError`. The working surfaces today are transformer pins and mounts.
