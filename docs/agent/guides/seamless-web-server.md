# Making a Seamless web server (Guide)

This page is a **guide**, not a contract. It tells you how to build a web application whose server side is a workflow Context: how to think about it, how to develop it with hot reloading on both sides, and how to deploy it. The normative behaviour lives in `contracts/shares.md`, `contracts/mounts.md` and `contracts/workflow-context.md`; this page links to them instead of restating them.

A few parts describe tools that do not exist yet: `seamless-serve-graph`, the pack tool and Cloudless in the deployment tactics. They are marked *(not yet implemented)* where they occur and collected under *Implementation status*.

## The idea: shared cells are the REST API

A Seamless web server is a **workflow Context plus shares**. There is no route table, no request handler and no serializer to write. **A shared cell is the whole REST API you need, and the reactive workflow does the work behind it.**

| You need | You write | The browser sees |
|---|---|---|
| Show a value | `ctx.x.share()` | `GET /<ns>/x`, pushed again on every change over the websocket |
| Take input | `ctx.x.share(readonly=False)` | `PUT /<ns>/x`, optionally conditional with `?marker=n` |
| Serve a computed result | `ctx.out = ctx.tf.result; ctx.out.share()` | `GET /<ns>/out`; the workflow recomputes it when its inputs change |
| Serve a page or an asset | a `text` or `bytes` cell, `share(path="index.html")` | `GET` with the right content type |
| Describe the API | nothing | `/openapi.json`, `/<ns>/state-graph` |
| Receive live updates | nothing | the websocket at `/<ns>`, wrapped by `/seamless-client.js` |

What happens on a request:

- **A PUT is a write to the cell.** Its dependents recompute under the reactive Context, and a result that reaches a share is announced to every websocket client.
- **A GET resolves stored bytes and never computes.** The request handlers run on the server's own thread and run no user code.
- **All logic lives in the graph**: transformers between cells. The serving script builds the graph and shares some of its cells; it does not respond to requests.

### Design rules

1. **One cell per quantity the page shows or edits.** The share key defaults to the node path (`ctx.sub.a` is served at `/<ns>/sub/a`).
2. **Inputs are writable shares, outputs are read-only shares of connected cells.** A writable share is the node's producer, so it cannot have an incoming edge. To serve a computed value, connect it into a cell and share that cell read-only.
3. **A user action is a write.** For request and response, use a writable input cell and a read-only result cell, connected by a transformer.
4. **Pick the celltype by what the page reads.** `plain` serves JSON, `text` serves raw text, `bytes` serves a file as it is. A `str` cell serves a *quoted* JSON string. Shareable celltypes are listed in `contracts/shares.md`.
5. **Everything in a namespace is shared by every visitor.** There is no authentication and no sessions. For isolation between users, give each user their own Context and namespace.

### A minimal server

Adapted from `seamless-workflow/examples/share-sliders/serve.py` (install `seamless-workflow[share]`):

```python
import os
from pathlib import Path

import seamless
from seamless import Cell
from seamless_workflow import Context, shareserver


def build(ctx, page_path=None):
    """Populate ctx with the application's cells, transformers and shares."""
    def add(a, b):
        return a + b

    ctx.a = Cell(celltype="plain")
    ctx.a.set(10)
    ctx.b = Cell(celltype="plain")
    ctx.b.set(20)
    ctx.add = add
    ctx.add.pins.a = ctx.a
    ctx.add.pins.b = ctx.b
    ctx.c = Cell(celltype="plain")
    ctx.c = ctx.add.result

    ctx.a.share(readonly=False)                     # inputs: PUT allowed
    ctx.b.share(readonly=False)
    ctx.c.share()                                   # output: read-only

    if page_path is not None:                       # a hand-written page; a built front end is packed instead
        ctx.page = Cell(celltype="text")
        ctx.page.mount(page_path, mode="r")
        ctx.page.share(path="index.html", toplevel=True)


def start(page_path=Path(__file__).with_name("index.html")):
    """Configure the server once per process, then build a fresh live Context."""
    if shareserver.url is None:                     # configure() after the server started raises
        host = os.environ.get("SEAMLESS_SHARE_HOST", "127.0.0.1")
        port = int(os.environ.get("SEAMLESS_SHARE_PORT", shareserver.port))
        shareserver.configure(host=host, port=port)
    ctx = Context()
    ctx.shares.namespace = "app"                    # runtime state; set before the first share
    try:
        build(ctx, page_path)
    except Exception:
        ctx.close()
        raise
    return ctx
```

`build(ctx)` is the part that is independent of how the server is run; the pack tool of *Deployment* calls the same function.

The page is a plain file. `seamless-client.js` is served by the share server itself:

```html
<script src="/seamless-client.js"></script>
<script>
  const app = connect_seamless(null, null, "app");   // same origin, namespace "app"
  const slider = document.getElementById("a"), sum = document.getElementById("c");
  app.self.onsharelist = keys => {                   // keys of the shares that exist now
    app.c.onchange = () => { sum.value = app.c.value; };
    slider.oninput = () => app.a.set(slider.value);  // PUT
  };
</script>
```

- **`value` is text** (a `Blob` for binary shares). JSON is not parsed for you.
- **Handlers are attached in `onsharelist`**, because entries appear and disappear with the shares of the namespace.
- **The server is one per process**: REST and websocket on one port, started by the first share, stopped by `seamless.close()`. It defaults to `0.0.0.0:5813`, with no authentication and no TLS. Bind to `127.0.0.1` for development (`SEAMLESS_SHARE_HOST`, `SEAMLESS_SHARE_PORT`, `shareserver.configure`).

## Development

### Two processes

Put the front end's dev server (Vite or similar) in front, and the Seamless process behind it.

- **The dev server compiles and hot-reloads the front end.** It proxies the share namespace and the client script to the Seamless process.
- **The Seamless process holds the Context** and the share server. A share server only serves stored bytes and cannot proxy or hot-reload a front end.
- **Same origin in development and production.** The proxy means the front end code is identical in both. CORS is open, so `connect_seamless(5813)` would also work, but it builds the port into the code.

Start the two in separate terminals. The backend runs interactively, so the Context stays inspectable and editable:

```bash
# terminal 1: backend
conda activate <env>
python -i backend.py
```

```bash
# terminal 2: front end
conda activate <env>
npm run dev
```

**vite.config.ts**

```ts
export default defineConfig({
  base: './',
  plugins: [/* the framework plugin */],
  server: { proxy: {
    '/app':                { target: 'http://127.0.0.1:5813', ws: true },  // REST and websocket
    '/seamless-client.js': 'http://127.0.0.1:5813',
    '/openapi.json':       'http://127.0.0.1:5813',
  }},
})
```

- **`ws: true` is needed on the namespace entry**, because the websocket is `GET /<ns>` with an upgrade.
- **Choose a namespace name that no front end route starts with.** Vite matches proxy keys by prefix.
- **Load the client with a plain `<script src="/seamless-client.js">` tag** and call `connect_seamless(null, null, "<ns>")` once, from its own small module that turns shared cells into the framework's reactive state. Hot-swapping a component re-evaluates its module; keeping the connection in its own module prevents a second websocket.
- **State kept in writable shared cells survives full page reloads** and is visible to Python. Keep the front end's durable state there.
- **A no-build page** can instead be a `text` cell mounted with `mode="r"` (as in the example). An edit is served within the mount's polling interval, but the browser is not told and must be reloaded by hand.
- **Do not compile inside the Context.** A build step run as a transformer puts the sources and `node_modules` into the cache key and pays a full build per save. Compile offline; let the graph record only the result.

### Three ways to change the Seamless side

The front end hot-reloads by itself. The Seamless side has three mechanisms, which differ in what they cost and what state they keep.

| | 1. Live edit | 2. `%run -i` reload | 3. Restart |
|---|---|---|---|
| What you do | change cells and the graph in the live session | re-run the script in IPython | stop and start the process |
| Context | the same object | closed, a new one built | a new process |
| Share server | untouched | untouched | restarted |
| State written from a browser | kept | reset to the script's defaults, unless mounted | reset, unless mounted |
| Front end | `shares` message on the websocket | no disconnect; only changed values are announced | disconnect, then reconnect |
| Requires | the script kept in step | a script that is safe to re-run | mounted state; a hardened client |

#### 1. Live edit in the interactive session

Zero restart. Assign cells, transformers and connections in the running session, by hand or by a coding agent attached to it; the workflow recomputes and the browser follows.

- **The script is the source of truth; the live session is a preview.** Every live change must also be made in `backend.py`, or the next reload or restart reverts it.
- **Adding or removing a share is announced to the front end** as a new `shares` message on the websocket, which calls `onsharelist`. Attach handlers for new keys there.
- **`/openapi.json` is generated per request and is always current.** There is no push for it. A front end that keeps a copy (generated types, a key list) re-fetches it after the cell list changes; the websocket `shares` message is the trigger.

#### 2. `%run -i`: reload the script, keep the server

The script is re-run in IPython's interactive namespace. This is the equivalent of a hot reload. The workflow Context is replaced (the `ctx` variable is re-defined); **the share server is not**, because it exists independently of Contexts.

Write the script so that it is safe to re-run:

```python
# backend.py: run with `python -i backend.py`, reload with `%run -i backend.py`
try:
    ctx.close()                  # the previous run's Context; frees its namespace
except NameError:
    pass                         # first run
ctx = start()
```

- **Close the old Context first.** A second live Context claiming a taken namespace raises `ValueError("Share namespace '<name>' is in use")`.
- **Guard `shareserver.configure`** with `if shareserver.url is None`, as `start()` above does. `configure()` after the server started raises `RuntimeError`.
- **Do not call `seamless.close()` in a reloadable script.** It stops the share server. Keep it for a non-interactive `main()` that runs once and exits.
- **A reload resets state that browsers wrote.** The new Context starts from the script's defaults. Mount the cells that must survive (mechanism 3).
- **Markers keep increasing across the reload.** A re-shared URL continues its marker sequence for the lifetime of the server.

**The hold on close** keeps the reload invisible in the browser for values that did not change (`contracts/shares.md`, *The hold on close*):

- `ctx.close()` does not remove the shares at once. The server keeps serving them, with their checksums and markers, for a **hold window** (10 s by default), and keeps the websockets open. The Context's teardown is not visible, and `/openapi.json` does not drop to an empty document.
- The new Context's first share takes the namespace over, and each share at a held URL **re-attaches**. A cell whose value is unchanged produces no marker bump and therefore no websocket update. A cell whose value differs produces one ordinary update.
- A PUT sent during the reload waits for its share to be re-attached, and is then processed by the new Context.
- A held share that the new script no longer makes is removed when the window ends, as on any close.
- The hold serves; it never carries a value into the new Context. State that a browser wrote into an unmounted cell still returns to the script's default.

#### 3. Mounts with `authority="file"`: persistent state

A mounted cell keeps its value in a file. That makes state survive a `%run -i` reload and a **full restart of the Seamless process**, a "tepid reload".

```python
ctx.params = Cell(celltype="plain")
ctx.params.set({"threshold": 0.5})                         # the default; set it before mounting
ctx.params.mount("state/params.json", mode="rw", authority="file")
ctx.params.share(readonly=False)
```

- **First run**: the file is absent, so the default is written to it. **Every later run**: the file wins over the script's default (`contracts/mounts.md`, *The initial decision table*, row 11, logged once).
- **Every accepted PUT is written to the file**, and an edit of the file is served and announced.
- **`authority` resolves only the initial conflict.** After attach, every file change and every cell change flows as usual.
- **Mount only state worth keeping.** Do not mount derived cells; they are recomputed. Keep the state directory out of version control.
- **`persistent=True` is the default**; the file survives unmount and Context close.

#### Hardening the front end for restarts

A restarted process restarts its markers. The front end must cope with a server that vanishes and comes back.

- **Reconnect automatically.** `seamless-client.js` retries a lost websocket with backoff (1 s, doubling, up to 30 s).
- **Every connection starts with a `shares` message** that carries the checksum and marker of every share in the namespace.
- **The client's restart rule** (`contracts/shares.md`, *`seamless-client.js`*): if, after reconnecting, the markers are **lower** than the ones the front end already holds, the server process restarted. One key that is exactly one lower, because the server has not yet processed the client's own PUT to it, does not count. Mounted cells were restored from their files, so the front end's own state is current: the client adopts the new markers and does not re-read the values. If that was wrong (unmounted state was reset), the user reloads the page by hand.
- **A write sent after a restart, before the client has adopted the new markers, carries the old marker.** It is normally refused with `409`, and the client drops the local change. Until the reconnect lets the client conclude that the server restarted, it ignores the server's lower marker, so the page keeps showing the dropped change until the reconnect; the client then reads that value. Show a disconnected state instead of letting the user edit as if connected.

## Deployment

Development needs Node, a dev server and a live interactive Context. Deployment needs none of them: a built, static front end, and a Context that serves it. There are two levels.

### Level 1: the serving script

For a front end that is one hand-written file, **the development script is already the deployment**, as in `examples/share-sliders`: a `text` cell mounted with `mode="r"` and shared at the top level, plus the data cells. Run `python serve.py`, bind explicitly, and put a reverse proxy in front.

A **built** application (many hashed files) runs into five limits of this level:

1. **One cell per file.** Folder cells cannot be shared.
2. **Top-level share keys have one segment.** `/assets/x.js` cannot be a top-level share; inside a namespace a key may have several segments.
3. **Hashed names change on every build**, so the set of mounted shares changes.
4. **The browser client never reports changes of file-like shares.** Keys with a `.` are not auto-read.
5. **The redirect from `/` and `/<ns>/` to `index.html` drops the query string.**

Level 2 absorbs the first limit in the pack tool, and removes the other four: files are shared under a namespace at their relative paths, every build is a new graph so changing names cost nothing, a running graph's files never change, and the proxy can redirect `/` with the query string kept.

### Level 2: pack the build into a graph

Compile offline, pack `dist/` into a Context with one `bytes` cell per file, each shared at its path, and save the graph. The graph holds only checksums; the bytes live on a hashserver. A generic server loads the graph and serves it. The server needs no Node and no application code.

```
src/  --npm run build-->  dist/  --pack-->  Context (one bytes cell per file + backend nodes)
                                              | get_graph()                    | publish
                                              v                               v
                                          graph.json (checksums)          hashserver  --rsync-->  deploy hashserver
                                              |                                                       |
                                              +-----> generic server: set_graph(mounts=False, shares=True) --resolves--+
```

#### 1. Build with a relative base

Set `base: './'` in the Vite config and run the production build:

```bash
npm ci                        # reproducible install; pin the Node version
npm run build                 # vite build -> dist/
```

- **`base: './'`** makes the page load its assets relative to wherever `index.html` is served, so the same build works under any namespace.
- **Keep Vite's content hashes in deployment builds.** Each build produces a new graph, so changing names cost nothing, and the proxy can mark assets immutable.
- **Files loaded at run time** (workers, `.wasm`, fonts) must be in `dist/` too, with pinned content types.

#### 2. Pack

The pack tool is generic: it walks `dist/`, makes a cell per file, shares it at its relative path and writes the graph. If the application has a backend, call its `build(ctx)` first (without a `page_path`), so static files and backend nodes end up in one graph.

```python
import json, mimetypes
from pathlib import Path

import seamless, seamless.config
from seamless import Cell
from seamless_workflow import Context, shareserver

NULL_CONTENTS = (b"", b"null\n", b"null")      # these are null: the share would answer 204

def node_name(rel):
    # "assets/index-DD5wxIS0.js" -> "web__assets__index_DD5wxIS0_js"
    return "web__" + "".join(c if c.isalnum() else "_" for c in rel.replace("/", "__"))

def pack(dist, graph_out, backend=None):
    seamless.config.init()                            # build stage: a writable hashserver
    shareserver.configure(host="127.0.0.1", port=0)   # share() records specs; nothing is exposed
    ctx = Context()
    try:
        if backend is not None:
            backend(ctx)                              # the application's own nodes
        names = set()
        for f in sorted(Path(dist).rglob("*")):
            if not f.is_file():
                continue
            rel = f.relative_to(dist).as_posix()
            data = f.read_bytes()
            if data in NULL_CONTENTS:
                raise ValueError(f"{rel}: content would be served as null (204)")
            name = node_name(rel)
            if name in names:
                raise ValueError(f"{rel}: node name collision")
            names.add(name)
            mimetype = mimetypes.guess_type(rel)[0] or "application/octet-stream"
            setattr(ctx, name, Cell(celltype="bytes"))
            cell = getattr(ctx, name)
            cell.set(data)
            cell.share(path=rel, mimetype=mimetype)   # pinned into the graph's share entry
        graph = ctx.get_graph()
    finally:
        ctx.close()
        seamless.close()                              # flushes pending hashserver writes
    Path(graph_out).write_text(json.dumps(graph, indent=1, sort_keys=True))
```

What the pack tool must get right:

- **Run it as its own process.** `seamless.close()` ends Seamless for the whole process: no Context can be built afterwards, and neither can a second `pack` or a `serve`. The same holds for the serving process below.
- **Celltype `bytes` for every file.** It is the one celltype whose buffer is the file as it is, so the served body is the built file byte for byte.
- **Pin the content type at pack time.** Without a `mimetype`, the server guesses from the extension on the *serving* host, and a browser refuses a module script that is not served with a JavaScript type. The pinned value is stored in the graph's share entry.
- **Refuse null contents.** An empty file, or one that is exactly `null`, is the null value, and a share answers `204` with no body.
- **Generated node names.** The share path carries the real file name; the node name is only an identifier.
- **Publishing is automatic**: a non-scratch cell publishes its literal to the hashserver when the Context claims it. `seamless.close()` reports buffers it could not write; treat that as a failed build.
- **Verify before shipping.** Batch-check every checksum in the graph against the hashserver's `GET /has-now`, which, unlike `/has`, does not count buffers that are only promised.

#### 3. Hashserver

| | Build side | Deploy side |
|---|---|---|
| Mode | writable | read-only when the graph has no writable shares and no transformers; writable once PUT values or computed results must survive |
| Contents | every buffer the Context published | a copy: the buffer directory is plain files named by checksum, so `rsync` transfers only what is new |
| Reachability | build machine or CI only | the serving process only; never public |

Unchanged files are never uploaded or transferred again.

#### 4. Serve

The serving process does nothing application-specific. Everything it needs is in the graph, the deployment configuration and its command line:

```python
import signal, threading
import seamless, seamless.config
from seamless_workflow import Context, shareserver

def serve(graphs, host="127.0.0.1", port=5813):
    seamless.config.init()
    shareserver.configure(host=host, port=port)
    contexts = []
    try:
        for namespace, graph in graphs.items():
            preflight(graph)                  # /has-now on every checksum; refuse to start if one is missing
            ctx = Context()
            contexts.append(ctx)
            ctx.shares.namespace = namespace
            ctx.set_graph(graph, mounts=False, shares=True)
        stop = threading.Event()
        for sig in (signal.SIGTERM, signal.SIGINT):
            signal.signal(sig, lambda *_: stop.set())
        while not stop.wait(1.0):
            pass
    finally:
        for ctx in contexts:
            ctx.close()
        seamless.close()
```

- **`preflight(graph)` is not shown.** It reads every checksum in the graph (`value.checksum` of each cell node) and asks the hashserver `GET /has-now` for them in a batch; it raises if any is missing.
- **`serve` installs signal handlers**, so it runs in the main thread of its process.
- **`mounts=False`, always.** A server must never read or write files because a graph says so.
- **The namespace is runtime state, not part of the graph.** It comes from the command line; the same graph can be loaded several times under different names in one process.
- **Run the startup check.** Without it, a missing buffer first shows up as a `503` in a browser.
- **Shut down on SIGTERM and SIGINT**: close the Contexts, then `seamless.close()`.
- **There is no health endpoint.** `GET /openapi.json` answers whenever the server runs.
- A generic command, `seamless-serve-graph --graph <ns>=<graph.json or checksum> --host 127.0.0.1 --port 5813`, is **planned** and is not ported yet *(not yet implemented)*. Until then, the code above is the whole server.

#### 5. Reverse proxy

The share server has no compression, no TLS and no long-lived caching. A reverse proxy (nginx, Caddy) supplies them:

- **Compression and TLS termination.**
- **`Cache-Control: public, max-age=31536000, immutable` on `/<ns>/assets/*`.** This is safe only because the deployment build keeps content hashes. Every share response otherwise carries `Cache-Control: no-cache` with the checksum as `ETag`, so every page load revalidates every file.
- **Redirect `/` straight to `/<ns>/index.html`**, keeping the query string, instead of relying on the server's own `302`, which drops it.
- **Access control**, and the exposure rules below.

### Exposure, state and releases

- **Every share is readable by anyone who reaches the port**, and every writable share is writable by them. Bind to loopback and let the proxy do access control.
- **`/<ns>/state-graph` and `/openapi.json` are always served.** The state graph carries every node's path, celltype, state, checksum and error text, also for nodes that are not shared. Block the state-graph path at the proxy if it must not be public.
- **Loading a graph opens endpoints and can run transformer code.** Load only graphs you built, named by checksum in the deployment configuration. A graph of unknown origin is loaded with `shares=False`, and `mounts=False`.
- **One Context means one shared state.** For a tool where each user has their own state, load the static graph once at a fixed namespace, and give each session its own backend Context at its own namespace, built from a template graph. The page reads the session id from its URL and calls `connect_seamless(null, null, "s-" + id)`. Sessions share the static buffers, because the checksums are the same. The share server has no custom routes, so creating sessions needs a small control listener, with idle expiry *(not yet implemented)*.
- **A release is a graph checksum.** Store `graph.json` on the hashserver as a buffer and name its checksum in the deployment configuration. Rolling back means naming the previous checksum; its buffers are still there unless the hashserver was cleared.
- **The compile step is outside Seamless identity.** The graph records what was built, not how. Record the "how" in a cell (git commit, lockfile checksum, exact Node version) and share it read-only, so the page can show it.

### Taking it further: serve a workflow as data

The destination of level 2 is that the **static front end and the Python backend ship as one kind of artifact**: a graph, identified by one checksum, served by a generic server, with the backend nodes recomputed or cache-hit on the server's execution backend. That needs two things that are not ported from legacy Seamless yet *(not yet implemented)*: `seamless-serve-graph`, and Cloudless for per-session instances. Build the application so that its server side is a `build(ctx)` function: that is the part that moves into the graph unchanged.

## Checklist

1. Model each shown or edited quantity as a cell; inputs are writable shares, outputs are read-only shares of connected cells.
2. Keep all logic in the graph. Add no request code.
3. Develop with the dev server in front, `python -i backend.py` behind, a namespace of its own, and `/seamless-client.js` and `/openapi.json` proxied.
4. Keep the script in step with every live edit; keep it safe to re-run with `%run -i` (close the old Context, guard `configure`, no `seamless.close()`).
5. Mount, with `authority="file"`, the state that must survive reloads.
6. Harden the client: reconnect, tolerate a restarted server, never assume a write succeeded.
7. Deploy with relative base, pinned content types, hashed names, a hashserver copy, a startup check and a reverse proxy.

## Implementation status

Exercised against the code: `bytes` cells shared at multi-segment paths with a pinned `mimetype`; the `share` entry in `get_graph()` and the absence of a `mount` entry for unmounted cells; `set_graph(graph, mounts=False, shares=True)` into a fresh Context under the same namespace, with markers continuing; the `ValueError` for a namespace that a live Context holds; the share server staying up after `ctx.close()`; `authority="file"` persistence of a PUT across two Contexts; the `build`/`start` example and its `%run -i` header (a PUT to `a` recomputes `c`; the old Context is closed, the namespace is re-claimed and the defaults return); and the pack and serve sketches, run in a single process over the local buffer cache. That run showed the graph holding only `value.checksum` per cell node, pinned content types, no `mount` entries, bodies equal to the files, and `GET /<ns>/` answering the `index.html` share.

Not implemented, and described above as the intended behaviour:

- **`seamless-serve-graph`**, the **pack tool** as a shipped command (the code above is a sketch) and **Cloudless**.

Not verified:

- The hold on close and the client's restart rule (`contracts/shares.md`) in the reload and restart workflows above.
- The hashserver round trip: pack and serve as separate processes, with the buffers transferred through a hashserver, and the startup check against `/has-now`.
- Whether a Context with a read-only hashserver tries to publish the literals it fetches. Declare the hashserver read-only in the deployment configuration and look for write attempts in its log.
- Behaviour of `Cell.set()` for a single value of several MB. The contract states a 1 GiB request limit for PUT.
