# seamless-workflow

Reactive workflow `Context` layer for Seamless.

Context nodes are exposed through the canonical `seamless.Cell` and
`seamless_transformer.Transformer` handles. The experimental wrapper/view surface
described by the earlier context handoff documents is superseded by
[`context-internals-followup-plan.md`](https://github.com/sjdv1982/seamless/blob/main/seamless-workflow/../seamless/context-internals-followup-plan.md).

Construct cells with `Cell("int")` or `Cell(celltype="int")`; the default type
is `"mixed"` without a typed source. Initial references are keyword-only, for example
`Cell("int", checksum=checksum)`. Assign values with `.set(value)`.

`celltype` is the output type; `input_celltype` is read-only and follows the
source or the constant's declared serialization type. Creating `ctx.a = ctx.b`
copies `b.celltype` once. Rewiring an existing cell retains its type. Retyping
converts the original input; `.build().run()` agrees with `.value`. A cell's own
conversion failure reports `failed` with `.exception`.

`cell.source` reports the configured source. On a projection it reports the edge
at that path, else the nearest enclosing source, else None. `.checksum` reads
the produced checksum. Public `input_ref` and `target_celltype` are retired.

`ctx.tf.pins.x` returns a fresh Pin, also when unwired. Read `.value`, `.checksum`,
`.buffer`, `.source`, `.input_celltype`, `.state`, or `.exception` explicitly.
`pin.celltype` and `ctx.tf.celltypes.x` are linked. Pins convert their original
inputs before transformation construction; a failed conversion leaves the Pin
failed and the Transformer blocked on its name. A Pin is not a source; connect
`pin.source`. There are no sub-pin targets, validators, or mounts.

For Cells and Pins, `.value`, `.buffer`, and `.checksum` assignments declare a
new input and detach connections; `set`, `set_buffer`, and `set_checksum` check
ownership. `set_checksum(cs, input_celltype=...)` declares the input encoding.
`.value = None` stores canonical null; `.buffer = None` and `.checksum = None`
clear the input. All Cell types allow null. Required pins allow null only for
plain/mixed/bytes; optional pins of any type drop null before conversion.
A connected optional pin whose upstream has no checksum blocks.

`del ctx.a` deletes a node. `del ctx.tf.pins.x` deletes a declaration only for
signatureless code; use `.checksum = None` to clear a fixed-signature pin.

Whole Context cells can be mounted to files:

```python
from seamless.workflow import Cell, Context, Transformer

with Context() as ctx:
    ctx.config = Cell("plain")
    ctx.config.mount("config.json")
    ctx.output = Cell("text")
    ctx.output.set("ready")
    ctx.output.mount("output.txt", mode="w")
    report = ctx.mounts.sync(timeout=10)
```

`mount(path, mode="rw", authority="file", persistent=True)` blocks through the
initial read and first write attempt. Modes are `r`, `w`, and `rw`. Authority
chooses the initial winner; subsequent file edits are authoritative inputs in
sensing modes. A missing path supplies no value, while zero-byte and `null\n`
files supply null. At mount time, missing, zero-byte, and an empty directory do
not override an existing cell value. A sensing mount on a cell without a value
installs null; `file-strict` instead fails when the path is missing. Invalid or
unreadable input fails the cell, preserves its stored last good value, and
continues monitoring. Delivery failures appear on `ctx.output.mount.error` and
retry with backoff; they do not invalidate the cell's value.

`ctx.compute()` waits only for graph work. Call `ctx.mounts.sync()` before
reading mounted outputs externally, or `await ctx.mounts.synchronization()` in
async code. The returned mapping contains status and errors per node path.
Synchronization establishes a finite filesystem cut; continuously changing
external files can prevent completion, so interactive clients can set a timeout.

Use `del ctx.config.mount` to unmount. `persistent=False` conditionally deletes
unchanged files at unmount or close. Explicit Context close flushes already
requested persistent deliveries, bounded by `close(timeout=60)`. A foreign
modification is never deleted based solely on its path. Two incompatible mounts
of overlapping paths within one process are refused. Write-only mounts pause
after three foreign-write reassertions in 20 seconds; inspect `.mount.error` and
call `.mount.clear_error()` to resume.

Null writes truncate an existing file to zero bytes, including `.gz` and `.zst`
paths, but do not create a missing file. Deleting a sensed file preserves the
stored cell value; under `file-strict` it raises a recoverable sense error. An
initially empty directory supplies no value, while a directory emptied after
mounting reads as `{}`. Directory null delivery leaves the tree in place and the
mount out of sync. Clearing a mounted cell is refused; unmount first. These rules
are separate from explicit nonpersistent unmount cleanup.

Text/code, JSON scalar/plain, bytes, binary, and mixed celltypes are supported.
`.gz` and `.zst` paths compress canonical bytes. `folder` and `deepfolder` use
directories, with per-leaf atomic replacement. `folder` mounts in `r`, `w` or
`rw`; `deepfolder` is read-only (sensing) and may only be mounted with
`mode="r"`. Directory trees are not replaced
atomically. Mounts follow a target symlink and preserve it; atomic file writes
break hardlink sharing. Cross-process exclusion and filesystem aliases such as
hardlinks are not covered by the registry.

Graphs retain mount specifications (format `0.4`). Legacy 0.2/0.3 graphs load
only when `target_celltype` is absent or equals `celltype`; conflicting graphs
raise `PathError`. Constant producers retain their input encoding as `value.celltype`. **Loading a graph can write
files:** use `ctx.set_graph(graph, mounts=False)` for graphs of unknown origin.
Sensing cells cannot receive incoming edges; mounted celltypes cannot change.
Unmount first. Standalone cells, sub-path projections, transformer pins and code
handles cannot be mounted directly: mount a whole cell and connect it instead.

The transport currently uses polling and a bounded daemon I/O pool. Diagnostics
include `seamless_workflow.diagnostics.record_attachments(ctx)` and the
controllable `attachments.manual.ManualDriver` for ordering tests.

Set `SEAMLESS_MOUNT_NATIVE=1` before the first mount to enable Linux inotify hints
alongside polling. Unsupported platforms and failed watches retain polling.
The experimental `attachments.widget.WidgetDriver(widget).attach(ctx.cell)`
exercises the same session protocol with a traitlets-style callback widget;
widget and manual-driver sessions are never serialized. This is an experimental
second transport, not a promise that arbitrary external services share file
mount conflict policy.
