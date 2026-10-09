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

Workflow graphs are written in format `0.6`, which stores mount and share
specifications. Graphs in formats `0.2` through `0.5` continue to load; older
`0.2`/`0.3` graphs require `target_celltype` to be absent or equal to
`celltype`. Constant producers retain their input encoding as `value.celltype`.
Loading a graph can write files or open share endpoints. For a graph of unknown
origin, use `ctx.set_graph(graph, mounts=False, shares=False)` to validate and
strip both kinds of attachment spec. Sensing cells cannot receive incoming
edges; mounted celltypes cannot change. Unmount first. Standalone cells,
sub-path projections, transformer pins and code handles cannot be mounted
directly: mount a whole cell and connect it instead.

File mounts currently use polling and a bounded daemon I/O pool. Diagnostics
include `seamless_workflow.diagnostics.record_attachments(ctx)` and the
controllable `attachments.manual.ManualDriver` for ordering tests.

Set `SEAMLESS_MOUNT_NATIVE=1` before the first mount to enable Linux inotify hints
alongside polling. Unsupported platforms and failed watches retain polling.

## HTTP shares

Share a whole Context cell to expose its served value over HTTP. Shares are
read-only by default; writable shares accept external edits and must be on a
cell with no incoming graph edge. Install `seamless-workflow[share]` to include
the HTTP server dependency.

```python
from seamless_workflow import Cell, Context, shareserver

shareserver.configure(host="127.0.0.1", port=0)  # before the first share
with Context() as ctx:
    ctx.input = Cell("int")
    ctx.input.set(4)
    ctx.input.share(readonly=False)

    ctx.result = Cell("text")
    ctx.result.set("ready")
    ctx.result.share()  # readonly=True

    print(ctx.input.share.url)
```

`share(path=None, readonly=True, *, mimetype=None, toplevel=False)` returns
`None`; `del ctx.input.share` removes that URL. The default path follows the
Context node path, and `ctx.shares.namespace` selects the Context's runtime URL
prefix while it has no shares. A read-only share can serve a connected computed
cell.

One process-wide server serves every Context on one port, with REST and
WebSockets on its own thread. It starts on the first share and remains until
`seamless.close()`. The default bind is `0.0.0.0:5813`; configure it before the
first share or set `SEAMLESS_SHARE_HOST` and `SEAMLESS_SHARE_PORT`. Use port `0`
to request a free port and read the selected value from `shareserver.port`.

The share URL supports GET and HEAD for the current canonical cell buffer and
PUT for writes. Bodies are raw bytes, without a JSON envelope or base64. A
writable PUT can include `?marker=<last-seen-marker>` for compare-and-set; a
stale marker receives `409`, and an accepted response arrives after the cell has
taken the value. A null value is `204`; a share with no value is `404`. GET
resolves the already-served checksum and never recomputes the cell. The namespace WebSocket provides an initial full share snapshot and
subsequent checksum/marker updates. `GET /openapi.json` describes active shares;
`ctx.shares.openapi()` and `shareserver.openapi()` return the same descriptions
in Python. The browser client is served at `/seamless-client.js` and connects
with `connect_seamless()`:

```javascript
const remote = connect_seamless();
remote.self.onsharelist = (keys) => {
  if (!keys.includes("input")) return;
  remote.input.onchange = () => render(remote.input.value);
};
function submit(value) {
  if (remote.input) remote.input.set(value);
}
```

Once a Context has shared a cell, `GET /<namespace>/state-graph` serves all of
its named nodes and graph connections, with each node's state, block reason,
exception and checksum. Snapshots can be up to half a second old. Set
`remote.self.onstategraph = () => renderGraph(remote.self.stategraph)` to fetch
and display snapshots when the namespace WebSocket announces a change. This
exposes node paths and error text for the entire Context to anyone who can
reach the server, including cells whose values are not shared.

The client keeps the latest value while one PUT per key is in flight and
refreshes after a stale-marker `409`.

Share specifications are serialized with workflow graph format `0.6`. The
default `ctx.set_graph(graph)` attaches them and can start the HTTP server;
`ctx.set_graph(graph, shares=False)` validates then strips share specs. Use that
with `mounts=False` for graphs from an unknown source.

The server has no built-in authentication or TLS, and permits cross-origin
requests. Its default wildcard bind makes shares reachable to hosts that can
reach the machine; bind to `127.0.0.1` or place a reverse proxy in front when
they should not be publicly reachable.

For notebooks, install `seamless-workflow[jupyter]` and use the public widget
helpers:

```python
from IPython.display import display
from seamless_workflow.jupyter import traitlet, output

display(output(ctx.c))
traitlet(ctx.a).link(slider)
```

The widget hub has its own runtime attachment slot and can coexist with
`ctx.a.mount("a.txt")` on the same cell. `ctx.mounts.sync()` reports both
sessions; `del ctx.a.mount` detaches only the file slot.

Widget attachments are runtime state and are never serialized. The underlying
`attachments.widget.WidgetDriver` remains an internal transport.
