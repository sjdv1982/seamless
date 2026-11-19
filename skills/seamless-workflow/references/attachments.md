## Attachments: mounts, widgets, shares

An attachment connects a bound cell to something outside the Context. Each cell node has at most one file slot, one widget hub and one share slot. Attachments work on whole named cells only: no standalone cells, sub-paths, pins or transformer code. To feed code or a pin from a file, mount a cell and connect it. Contracts: `attachments.md`, `mounts.md`, `widgets.md`, `shares.md`.

**Sensing makes a producer.** An `r` or `rw` mount, and a widget hub after its first `link()`, are the cell's producer: such a cell cannot also have an incoming edge (`AuthorityError`). Outputs take `mode="w"` mounts, `traitlet(...).connect()` or `observe()` (one-way), and read-only shares.

**Errors never raise after attach.** Attaching raises only for an invalid request. Afterwards, a bad file or a failed delivery shows up as the cell's `.exception` (sense errors) or the attachment's `.error` (delivery errors), and monitoring continues. An oscillation detector pauses an attachment after 3 reasserts in 20 s; `clear_error()` resumes it.

### Mounts

```python
ctx.a.mount(path, mode="rw", authority="file", *, persistent=True)   # blocks; returns None
del ctx.a.mount
ctx.a.mount.spec, ctx.a.mount.status, ctx.a.mount.error, ctx.a.mount.clear_error()
report = ctx.mounts.sync(timeout=None)      # external barrier; returns a SyncReport
ctx.mounts.errors                           # {(node_path, driver): error}
```

- **Modes**: `r` (file -> cell), `w` (cell -> file), `rw` (both).
- **Authority** decides who wins at attach time when both sides have a value: `file` (default; the file wins), `cell` (the cell wins), `file-strict` (the file must exist). An absent or empty file never overrides an existing cell value.
- **Mountable**: `text`, `python`, `ipython`, `yaml`, `plain`, `str` (a quoted JSON string; use `text` for raw text), `int`, `float`, `bool`, `bytes`, `binary`, `mixed` as files; `folder` (`r`/`w`/`rw`) and `deepfolder` (`r` only) as directories. Not `checksum`, `deepcell`, `module`.
- `rw` rewrites a non-canonical sensed file in canonical form (for example re-serialized JSON); `r` leaves the file alone.
- Paths ending in `.gz` or `.zst` hold compressed canonical bytes.
- `ctx.compute()` does not wait for files; call `ctx.mounts.sync()` before reading a mounted output from outside.
- `persistent=True` (default) leaves the file when unmounting or closing.
- Polling by default; `SEAMLESS_MOUNT_NATIVE=1` uses inotify.
- Limits: no `fsync`; no cross-process exclusivity (two processes mounting one file are not coordinated); default caps 1 GiB per file and 100 000 files / 10 GiB / 60 s per directory scan; on network filesystems a change that keeps size and mtime may be noticed late. A null value on a directory mount is terminal for that session.
- Loading a graph attaches its mounts and may write files: `set_graph(graph, mounts=False)` for untrusted graphs.

### Jupyter widgets

```python
from seamless_workflow.jupyter import traitlet, output

t = traitlet(ctx.a)                     # the cell's hub (one per cell)
t.link(slider, target_attr="value")     # bidirectional; makes the hub the producer
t.connect(label, target_attr="value")   # one way: cell -> widget
t.observe(handler, names="value")       # called at once, then on each change
t.status, t.error, t.clear_error(), t.destroy()

out = output(ctx.c, layout=None, mimetype=None)   # an OutputWidget; display(out)
```

- Functions, not cell methods: `ctx.a.traitlet` is a sub-path projection, not this API.
- `None` from a widget means "no value" and never clears the cell.
- Assign values; in-place mutation of a list or array in `value` is not seen.
- Widgets are runtime objects and are not saved in the graph. Hubs also work without a kernel (any `HasTraits` object).
- `traitlets`, `ipywidgets` and `aiohttp` are regular dependencies of `seamless-workflow`; there is no `[jupyter]` extra to install.

### HTTP and WebSocket shares

```python
ctx.a.share(path=None, readonly=True, *, mimetype=None, toplevel=False)   # blocks; returns None
del ctx.a.share
ctx.a.share.url             # http://localhost:5813/ctx/a (localhost shown for a wildcard bind)
ctx.shares.namespace        # "ctx" by default; settable while the Context has no shares
ctx.shares.openapi()        # the live OpenAPI document

from seamless_workflow import shareserver
shareserver.configure(host="127.0.0.1", port=5813)   # before the first share; port=0 picks a free one
```

- **Security**: one process-wide server, default bind `0.0.0.0:5813` (all interfaces), **no authentication, TLS or sessions**. Bind to localhost or put an authenticating reverse proxy in front. `SEAMLESS_SHARE_HOST` / `SEAMLESS_SHARE_PORT` set the defaults. One Context per user if users must be isolated.
- **Reading**: `GET`/`HEAD` return the raw value (no envelope); `204` means null; `404` means no value. A GET never computes.
- **Writing** (`readonly=False`): `PUT` the raw value; the share becomes the cell's producer, so the cell cannot have an incoming edge. Compare-and-set: `PUT ...?marker=n` with the marker you last saw.
- A websocket on the same port streams updates; a new client gets the current state on connect. `/seamless-client.js` is a dependency-free browser client; `/openapi.json` describes the current shares.
- Shareable: `text`, code celltypes, `plain`, `str`, `int`, `float`, `bool`, `bytes`, `binary`, `mixed`. Not deep celltypes. To expose part of a cell, share a cell that holds the projection (`ctx.x = ctx.a.x; ctx.x.share()`).
- **Downloads**: `ctx.shares.add_download(["title", "results/table"], path="download", format="tar.gz")` (also `tar`, `tar.xz`, `zip`) returns the URL; cells are named by path strings. The archive is built per GET from one consistent cut, held in memory, never computed. `remove_download`, `ctx.shares.downloads`.
- **State graph**: `GET /<namespace>/state-graph` returns every node's path, state, block reason, checksum and error text (rate-limited). Anyone who can reach the server sees it.
- **Hold on close**: after `ctx.close()` the namespace is held for 10 s, so re-running a script (`%run -i`) takes over the URLs without breaking connected browsers.
- **Serving a saved graph**: `seamless-serve-graph graph.json` loads it with shares on and mounts off into namespace `ctx`, and serves until SIGINT/SIGTERM. It needs a current-format graph (legacy 0.x exports are not converted) and, like any reload, persistent storage holding the graph's buffers.
- A page is a `text` cell you write and share, either at a path ending in `.html` (`ctx.page.share("index.html")`) or with `mimetype="text/html"`; there is no page generator. Worked examples: `share-sliders`, `share-download.py`, `mixlangstatus` in the `seamless-workflow` repo's `examples/`, and the agent guide `docs/agent/guides/seamless-web-server.md` in the `seamless` repo (it still mentions a `[share]` extra, which no longer exists).
