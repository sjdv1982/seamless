# Shareserver and `Cell.share()` — implementation plan

## Context

Legacy Seamless could expose a workflow cell over HTTP: `Cell.share()` registered the cell with a
server embedded in the process, which answered REST GET/PUT on one port (5813, aiohttp) and pushed
change notifications over a websocket on a second port (5138, `websockets`). A browser library,
`seamless-client.js`, kept JS variables in sync. Modern Seamless has none of this, and
`seamless/plans/workflow-authorize.md` already names "a shareserver (HTTP/websocket attachment
driver, not yet present)" as its prerequisite.

Scope given by the author:

- bring back the shareserver and `Cell.share()`;
- unify the REST and websocket halves under **one port**;
- **drop** the automatic web interface generator;
- **add** an auto-generated REST API specification (`openapi.json`);
- **port** `seamless-client.js`;
- **defer** the status graph.

Deliverables of this plan: the implementation steps below, and the agentic contract docs
(Appendix A is the full draft of the new page, Appendix B lists the edits to existing pages).
Plan mode allows writing only this file, so the contract text lives here until approval; step 1
moves it into `seamless/docs/agent/contracts/`.

## Inputs

### Legacy mechanism (Sonnet report 1, condensed)

All under `~/legacy-seamless/`.

| File | Role |
|---|---|
| `seamless/workflow/shareserver.py` (965 lines) | `Share` (per-key checksum, marker, readonly, celltype, mimetype), `ShareNamespace`, singleton `ShareServer` with both servers |
| `seamless/workflow/core/share.py` (397) | `ShareItem` (cell ↔ `Share`), singleton `ShareManager(0.2)`: bookkeeping and tick loop |
| `seamless/workflow/core/manager/manager.py:198-228` | the cell-change hook |
| `seamless/workflow/highlevel/Cell.py:1003-1044`, `Context.py:1200-1281` | `Cell.share()`, `hcell["share"]` in the graph, `_connect_share()` on every translation |
| `js/seamless-client.js` (326) | browser client |

- **Outbound is not an observer.** `Manager._upon_set_cell_checksum` writes `cell_updates[cell]`
  (a dict, so updates coalesce); a 0.2 s asyncio tick drains it into `Share.set_checksum`, which
  bumps an integer marker and sends `["update", [key, checksum, marker]]` to every websocket of
  the namespace. Pending cells are skipped; voiding is never pushed.
- **Inbound.** `PUT {"buffer"| "checksum", "marker"}` → validate by deserialize/serialize →
  `Share.set_checksum` → applied to the cell on the next tick (up to 0.2 s after the PUT returned).
  Writable shares require an independent cell.
- **Everything ran on the main thread's asyncio loop**, so nothing was served while user code
  blocked. Every re-translation destroyed and re-created all shares through a 20 s cache.
- **Out of scope layers are separable**: webgen (`graphs/webgen*`, `highlevel/webunits/`) and the
  status graph (`graphs/status-visualization*`, `metalevel/bind_status_graph.py`) sit on top; the
  shareserver imports neither. Legacy generated no API description of any kind.
- Legacy defects not to port: a newly connected websocket client got no current state; two
  clients PUTting from the same marker lost one update silently; `mode=checksum` was broken;
  no reconnect in the client; `allow_credentials` with a `*` origin.

### Modern hooks (Sonnet report 2, condensed; the ones I rely on I re-read myself)

Hypothesis confirmed: the attachment layer is the only place where an external bidirectional peer
is wired to a cell, and its transport protocol is what a share plugs into.

| Need | Hook | Status |
|---|---|---|
| cell → peer | `Context._after_turn` → `AttachmentRuntime._mount_after_turn` → `service.deliver(reg, Delivery)` (`seamless-workflow/seamless_workflow/attachments/runtime.py`) | reuse |
| coalescing | one `pending` + one `in_flight` per session | reuse |
| peer → cell | `Observation` through the sink → `_mount_observed` → `_mount_sense` (non-detaching authoritative write) | reuse |
| thread-safe ingress with a reply future | `Controller.enqueue(op, args, klass=3)` (`controller.py:62`) | reuse |
| writable needs independence | sensing-mode edge refusals (`_mount_validate`, `_mount_has_sensing`) | reuse |
| body validation | `canon_T(content, celltype)` (`seamless-core/seamless/checksum/canonical.py`) | reuse |
| bytes for a checksum | `Checksum.resolution()`, run as `FileSystemService._resolve` does (worker thread + `asyncio.run`) | reuse the pattern |
| barrier | `SyncPredicate` cuts every session; `ctx.mounts.sync()` | reuse |
| lifecycle | `_mount_detach`, `_mount_detach_all`, close flush, `lifecycle.close_contexts` | reuse |
| transport contract | duck-typed: `activate`, `deliver`, `request_cut`, `poll`, `unregister` → `Future`, `delivery_timeout`; registration needs `session_id`, `celltype`, `service`, `spec`, `active` | implement (`ManualDriver` is the minimal model, `WidgetDriver` the closest) |
| `Cell.share` member | next to `Cell.mount` (`seamless-core/seamless/cell_class.py:656-666`, `__getattr__` at 819-835), bound property at `context.py:485-496`, `MissingView.mount` (`views.py`) | extend |
| graph persistence | `get_graph` (`context.py` ~2890), `prepare_graph` (`serialization.py:41-43,102-111`), `load_graph` (`attachments/api.py:121`) | extend |
| marker, namespace, mime table, server, websocket, openapi, JS client | none | build |
| HTTP stack | aiohttp 3.13.5 is installed and already imported transitively; `AppRunner` + `TCPSite` pattern in `seamless-jobserver/jobserver.py`; `aiohttp_cors` absent | build on aiohttp, hand-written CORS |

Controller facts that shape the design: each Context has its own controller thread and loop;
`deliver` is called on that thread and must not block; a raising class-5 handler poisons the
Context, so acks must be well formed.

### In-flight work this plan builds on

**`seamless-workflow` and the contract docs are being edited by another session right now**
(uncommitted as of 2026-10-09 00:57; files changed while the subagent and I were reading them):

- sessions are keyed by `(node_path, driver)`; non-file specs live in `Node.attachments[driver]`;
  a node has one **file** slot and one **widget** slot (`tests/test_attachment_slots.py`);
- deliveries are paced at `DELIVERY_INTERVAL = 2/3` s per session, with a Context-owned wakeup
  timer;
- `attachments.md`, `mounts.md`, `widgets.md` already describe both.

This is exactly the slot generalisation the share needs, so **this plan adds a third slot and
does not touch the slot mechanism itself**. Step 0 waits for that work to be committed.

## Rulings (author, 2026-10-09)

| # | Question | Ruling |
|---|---|---|
| 1 | share alongside a mount or widget? | **own slot** |
| 2 | shares in the saved graph? | **yes**: `"share"` entry on cell nodes, format bump, `set_graph(graph, shares=True)` |
| 3 | wire protocol | **clean REST**: bodies are the value in the share's content type, `?marker=n`, checksum as ETag; no legacy envelope |
| 4 | URL namespace | **runtime** `ctx.shares.namespace`, default `"ctx"`, not in the graph, a taken name raises |
| 5 | meaning of `?marker=n` | **base marker, compare-and-set**; mismatch → 409 |
| 6 | bind defaults | **`0.0.0.0:5813`, fail if the port is busy** |

## Design

### 1. A share is the third attachment driver

- `ShareSpec` (frozen dataclass, own class — not the file-shaped `AttachmentSpec`):
  `path`, `readonly=True`, `mimetype=None`, `toplevel=False`; derived read-only `mode`
  (`"w"` / `"rw"`), `authority="cell"`, `persistent=True`, `driver="share"`; `to_graph()`.
- Stored in `Node.attachments["share"]`, session key `(node_path, "share")`.
- `ShareDriver` implements the transport protocol:
  - `deliver` → hand over to the server loop (`call_soon_threadsafe`): set the record's checksum,
    bump the marker, broadcast, ack `written`; ack `conflict` when a PUT arrived since the
    delivery's `expected_fingerprint`. **No payload is resolved at delivery.**
  - PUT → `canon_T` in the server's worker pool → update record, bump marker and fingerprint,
    broadcast → `Observation` via `controller.enqueue('_mount_observed', …, klass=3)` → await the
    reply future → respond. The existing classification makes the echo a non-event
    (`_mount_sense` sets `last_synced`).
  - `request_cut` → answer on the server loop after every already-accepted PUT has been enqueued.
  - `poll` → no-op (a share never has a sense error). `unregister` → remove the record, return a
    `Future`.
- Invalid PUT bodies are refused at the HTTP boundary (422); an `INVALID` observation is never
  sent, so **a share never fails its cell**.

### 2. One process-global server, one port

- `ShareServer` singleton (like `fs.service.get_service()`): a daemon thread with its own asyncio
  loop, one `aiohttp.web.Application` serving REST and websocket, a small private
  `ThreadPoolExecutor` for buffer resolution and canonicalization (never the default executor).
- Started lazily by the first share, which blocks until the socket listens; a bind failure raises
  from `share()` and installs nothing. Closed by `lifecycle.close_contexts` after the Contexts.
- It serves while user code blocks, in scripts and under Jupyter, because it never uses the
  caller's loop.
- Registry: `namespaces[name] → {key → record}`, a namespace claimed by one Context; per-URL
  marker floor kept for the life of the server so markers stay monotonic across re-share.

### 3. URL space, REST, websocket, OpenAPI, client

Specified in Appendix A (*URL space*, *Reading*, *Writing*, *The websocket*, *`openapi.json`*,
*`seamless-client.js`*). In short:

- `GET|HEAD|PUT /<namespace>/<path>` (or `/<path>` for `toplevel`), `GET /openapi.json`,
  `GET /seamless-client.js`, websocket upgrade on `GET /<namespace>`.
- GET returns the buffer byte for byte with `ETag: "<checksum>"` and `X-Seamless-Marker`;
  `If-None-Match` → 304; null → 204; no value yet → 404; unresolvable → 503.
- PUT body is the value; `?marker=n` is compare-and-set; response `{"checksum", "marker"}`.
- Websocket protocol `1.0`: handshake, `["shares", {...}]` with current state on connect and on
  every change of the share set, `["update", [key, checksum, marker]]`.
- `openapi.json`: OpenAPI 3.1 generated from the live registry, schema per celltype.
- Client: same JS API (`connect_seamless`, `ctx[key].value / set() / onchange`), one origin, raw
  bodies, one PUT in flight per key with latest-wins pending, reconnect with backoff.

### 4. Python API

`ctx.a.share(path=None, readonly=True, *, mimetype=None, toplevel=False)`, `del ctx.a.share`,
`ctx.a.share.{spec,url,status,error,clear_error()}`, `ctx.shares.{namespace,url,openapi()}`,
`seamless_workflow.shareserver.{configure,host,port,url,openapi,close}`,
`set_graph(graph, shares=True)`. Details in Appendix A, *The API*.

## Decisions that are mine, not ruled — overrule at review

1. **A writable share on a cell without a value installs null** — the existing sensing rule
   (`mounts.md`, no-value table, row 4; `widgets.md` says the same). Legacy left the cell empty.
   I kept the uniform rule rather than add a share-only exception.
2. **GET never computes**: it resolves like `.buffer`; unresolvable → 503. Legacy fingertipped.
   Follows `attachments.md`, *A delivery resolves; it never computes*.
3. **A share keeps serving its last complete value** while the cell is waiting, blocked or failed
   (the *Actuate* rule; also what legacy did). Node state over HTTP waits for the status graph.
4. **Null is `204 No Content`**; an empty PUT body, or `null`, writes null.
5. **The body is the checksum's buffer byte for byte** — no share-local re-serialization, so the
   ETag is verifiable.
6. **Content type**: `mimetype=` argument, else guessed from the share path's extension for
   `text` and `bytes` cells, else a celltype table. Cells carry no mimetype.
7. **Shareable celltypes are the file celltypes**; `folder`, `deepfolder`, `deepcell`,
   `checksum`, `module` are refused.
8. **Not ported, with reasons**: PUT by checksum (needs the check `ctx.a.checksum = …` performs,
   which a transport cannot reach today — deferred); sub-key GET (`/ctx/a/x/0`); `DeepCell`
   option shares; the dead `share_evaluate` / `"self"` entry.
9. **`share()` returns `None`**, like `mount()`; legacy returned the cell.
10. **CORS `*` by default**, without credentials; **request bodies up to 1 GiB** (legacy value).
    With ruling 6 the server is unauthenticated on all interfaces, as legacy was; the page says so.
11. **aiohttp becomes a declared dependency** as the extra `seamless-workflow[share]`.
12. **The client keeps the three-argument signature**; the first two arguments are aliases for
    the one server.
13. **Topology refusals raised by generic code keep their "mount" wording** (as for widgets);
    refusals raised by `share()` itself get share wording.
14. **Package placement**: `seamless_workflow/attachments/share/`, public module
    `seamless_workflow.shareserver`. The existing `seamless-share` package (cache diagnostics) is
    unrelated; the contract page says so in its first lines.

## Implementation steps

Contract first, then tests, then code — the order used for the other features.

0. **Precondition.** The per-driver slot work is committed in `seamless-workflow` and
   `seamless`. Re-verify the hook lines above. Copy this plan to
   `seamless/plans/shareserver-plan.md`.
1. **Contract docs.** Write `seamless/docs/agent/contracts/shares.md` from Appendix A; apply
   Appendix B; register the page (`docs/agent/README.md`, `index.md`, `config/mkdocs.yml`,
   `seamless/mkdocs.yml`); regenerate `index.json` with `docs/agent/scripts/gen_agent_docs.py`.
2. **Contract tests, red.** `seamless-workflow/tests/test_contract_shares.py`; each docstring
   names the section it pins. Helpers: an aiohttp/`requests` client and a `websockets` reader
   run from the test thread (the server has its own thread, so plain blocking calls work).
3. **Server core, no Context.** `attachments/share/server.py`, `mime.py`: registry, records,
   markers, REST, websocket, CORS, static client route. `tests/test_share_transport.py` drives it
   with a fake sink, as `test_mount_transport.py` does for the file service.
4. **Driver and API.** `attachments/share/spec.py`, `driver.py`, `api.py` (`ShareHandle`,
   `ContextShares`); `Cell.share` property + deleter and the `__getattr__` arbitration in
   seamless-core; bound property in `context.py`; `MissingView.share`; reserved `shares` on the
   Context (`context.py` `_assign`, `serialization.py`); share-aware admission and messages in
   `_mount_validate`; `ShareHandle.unshare` and `Context.__delattr__` use the share server's
   `delivery_timeout` for share futures; `close_shareserver()` in `lifecycle.close_contexts`.
5. **Persistence.** `get_graph` writes `entry["share"]`; `prepare_graph` parses and validates it
   (also with `shares=False`), accepts `0.6`, refuses a `share` entry below `0.6`;
   `load_graph(ctx, data, *, mounts=True, shares=True)` reserves and prepares share registrations
   and passes them in `mount_prepared`; writer emits `"0.6"`. `Node.attachments` is declared
   `compare=False`: check whether anything relies on `Node` equality, since the share spec is
   durable state and the widget spec is not.
6. **OpenAPI.** `attachments/share/openapi.py`; `/openapi.json`; `ctx.shares.openapi()`;
   `shareserver.openapi()`.
7. **Client.** Port to `attachments/share/static/seamless-client.js`; `package-data` in
   `seamless-workflow/pyproject.toml`; extra `share = ["aiohttp>=3.9"]`.
   `tests/test_share_client_js.py` runs the client under Node (v25 is installed; global `fetch`
   and `WebSocket`, a three-line `window.location` shim), skipped when `node` is absent.
8. **Human docs.** `seamless/docs/main/api/seamless-workflow.md`; `RELEASE-NOTES.md`; update the
   status line of `plans/workflow-authorize.md`.
9. **Real web server test (the last step; requested by the author).** Section 7 of
   `~/legacy-seamless/examples/basic-example.ipynb` — two `IntSlider(min=-10, max=30)` linked to
   `ctx.a` and `ctx.b`, and an output of `ctx.c` — ported to an HTML page with sliders.
   - **The example**, `seamless-workflow/examples/share-sliders/`:
     - `serve.py`: `build()` makes the workflow of the modern notebook (`ctx.a = 10`,
       `ctx.b = 20`, `ctx.add = add`, `ctx.c = ctx.add.result`, all `plain`), then
       `ctx.a.share(readonly=False)`, `ctx.b.share(readonly=False)`, `ctx.c.share()`, and a
       `text` cell **mounted** from `index.html` (`mode="r"`) and shared with
       `share("index.html", toplevel=True)` — so the file slot and the share slot are used on
       one cell. `__main__` prints the URL and blocks in `input()`.
     - `index.html`: `<script src="/seamless-client.js">`, two `<input type="range" min="-10"
       max="30">`, one `<output>`; about 25 lines of JS: `slider.oninput → ctx.a.set(value)`,
       `ctx.a.onchange → slider.value`, `ctx.c.onchange → output`. No build step, no framework.
     - Nothing calls `compute()`: the Context is eager, so slider → PUT → `ctx.a` → `add` →
       `ctx.c` → websocket → page.
   - **The automated test**, `seamless-workflow/tests/test_share_browser.py`: real server on a
     real port (`SEAMLESS_SHARE_PORT=0`), real page, **real browser**. `/usr/bin/google-chrome`
     is installed; Playwright and Selenium are not, so the test drives headless Chrome over the
     DevTools protocol with a ~60-line helper in `tests/helpers/` (aiohttp websocket client; no
     new dependency). Skipped when no Chrome is found. It asserts:
     1. the page loads from `/` (redirect to the top-level `index.html`) and shows 10, 20, 30;
     2. **browser → cell**: setting slider `a` to 7 and dispatching `input` makes
        `ctx.a.value == 7` in Python and the page show `c = 27`;
     3. **cell → browser**: `ctx.b = 8` in Python moves slider `b` to 8 and shows `c = 15`;
     4. **two tabs are two co-editors**: a slider moved in one tab moves in the other.
   - **By hand**: `python examples/share-sliders/serve.py`, open `http://localhost:5813/`, drag;
     `curl localhost:5813/ctx/c` follows; edit `a` from a Python prompt and watch the slider move.
   - **Notebook**: once the in-flight edits to `examples/basic-example.ipynb` are committed, add
     a short section "Share cells over HTTP" (legacy section 6) that shares `ctx.a`, `ctx.b`,
     `ctx.c` and the page and links to it. The Jupyter sliders of section 3 and the HTML sliders
     then drive the same cells — file, widget and share slot on one node.

## Files

New, in `seamless-workflow/seamless_workflow/`:
`attachments/share/{__init__,spec,driver,server,openapi,mime,api}.py`,
`attachments/share/static/seamless-client.js`, `shareserver.py`.

Modified: `seamless-workflow/seamless_workflow/{context.py,serialization.py,views.py,lifecycle.py}`,
`attachments/{runtime.py,api.py}`, `seamless-workflow/pyproject.toml`,
`seamless-core/seamless/cell_class.py`.

Docs: `seamless/docs/agent/contracts/shares.md` (new), `attachments.md`, `cells.md`,
`workflow-context.md`, `mounts.md`, `widgets.md`, plus the four registration files.

Tests: `seamless-workflow/tests/{test_contract_shares,test_share_transport,test_share_client_js,test_share_browser}.py`,
`tests/helpers/` (DevTools driver), one arbitration test in seamless-core.

Example: `seamless-workflow/examples/share-sliders/{serve.py,index.html}`; a new section in
`seamless-workflow/examples/basic-example.ipynb`.

## Verification

- Interpreter: `~/miniforge3/envs/seamless1/bin/python` with `PYTHONPATH` to the repos.
  **One pytest process per test file** (`seamless-workflow/tests/run-tests.sh`).
- New files green; then the whole `seamless-workflow` suite, with attention to
  `test_attachment_slots.py`, `test_contract_attachments.py`, `test_contract_mounts.py`,
  `test_widgets.py` (shared runtime), and the seamless-core suite.
- **The real web server test of step 9 is the acceptance test**: `test_share_browser.py` green
  against headless Chrome, and the slider page tried by hand.
- End to end against `examples/share-sliders/serve.py` while it sits in `input()` (which proves
  the server does not depend on the caller's loop):
  `curl -i localhost:5813/ctx/a`, `curl -X PUT --data 5 'localhost:5813/ctx/a?marker=1'`,
  a stale-marker PUT (409), an invalid body (422), `curl localhost:5813/openapi.json`, and a
  `websockets` reader on `ws://localhost:5813/ctx`. Edit the mounted `index.html` and watch the
  websocket update.
- `openapi.json` checked structurally in tests, and once by hand in an OpenAPI viewer.
- `ctx.get_graph()` → new Context → `set_graph(g)` serves the same URLs; `shares=False` serves
  none; a `0.5` graph still loads.

---

## Appendix A — `seamless/docs/agent/contracts/shares.md` (draft)

````markdown
# HTTP shares (Contract)

A **share** is the attachment whose external resource is an HTTP endpoint served by this process. The cell's value is read with GET, written with PUT when the share is writable, and every change is announced over a websocket. **The attachment contract of `contracts/attachments.md` applies in full** — direction, scope, slots, spec versus session, the sense and actuate disciplines, delivery pacing, the cut barrier and the lifecycle. This page specializes it for values served over HTTP. It does not restate a rule from that page; each section says where the share driver makes a generic rule concrete.

Shares exist on the **workflow Context** only. A standalone `Cell`, a `direct`/`delayed` transformer and the command-line face have no HTTP integration. **A share is unrelated to the `seamless-share` package**, which inspects and exports cached buffers and transformations.

Code locations:

| Concern | Module / symbol |
|---|---|
| Public handles | `seamless_workflow.attachments.share.api` (`ShareHandle`, `ContextShares`) |
| Server configuration | `seamless_workflow.shareserver` (`configure`, `host`, `port`, `url`, `openapi`, `close`) |
| Durable spec, celltype admission | `seamless_workflow.attachments.share.spec` (`ShareSpec`, `validate_celltype`) |
| Transport | `seamless_workflow.attachments.share.driver.ShareDriver` |
| Server, records, namespaces | `seamless_workflow.attachments.share.server` (`ShareServer`) |
| Content types | `seamless_workflow.attachments.share.mime` |
| API description | `seamless_workflow.attachments.share.openapi` |
| Browser client | `seamless_workflow/attachments/share/static/seamless-client.js` |
| Cell handle | `seamless.cell_class.Cell.share` (property plus deleter, seamless-core) |
| Session protocol, policy, barrier | as in `contracts/attachments.md` |

## The API

```python
ctx.a.share(path=None, readonly=True, *, mimetype=None, toplevel=False)   # blocking; returns None
del ctx.a.share                                                           # unshare

ctx.a.share.spec            # the ShareSpec, or None
ctx.a.share.url             # "http://<host>:<port>/<namespace>/<path>", or None
ctx.a.share.status          # the status dict, or None
ctx.a.share.error           # delivery error, or None
ctx.a.share.clear_error()

ctx.shares.namespace        # "ctx"; settable while this Context has no shares
ctx.shares.url              # "http://<host>:<port>/<namespace>", or None before the server runs
ctx.shares.openapi()        # the OpenAPI document for this Context's shares, a dict

from seamless_workflow import shareserver
shareserver.configure(host="0.0.0.0", port=5813)    # before the first share
shareserver.host, shareserver.port, shareserver.url
shareserver.openapi()       # the document for every namespace

ctx.set_graph(graph, shares=True)
```

- **`share` is a class attribute of `Cell`** — a property with a deleter — so `del ctx.a.share` reaches the deleter and never sub-path deletion. It addresses the share slot only. A value key named `share` is reachable only as `ctx.a["share"]` (`contracts/cells.md`, *API-name arbitration*).
- **`shares` is reserved on the Context.** `ctx.shares = x` raises `AttributeError("shares is reserved for the Context share API")`, and a graph node at path `("shares",)` is refused with `PathError("shares is a reserved Context API name")`.
- **`share()` blocks until the endpoint answers**: through server start, and through the first delivery when the cell has a complete value. It raises only for an invalid *request* (*Errors*).
- **`path` is the key inside the namespace.** `None` means the node path joined with `/`: `ctx.sub.a.share()` is served at `/<namespace>/sub/a`. A key is a non-empty string of `/`-separated segments; an empty segment, `.`, `..`, `?`, `#` and control characters are refused with `ValueError`.
- **`readonly=True` serves the value; `readonly=False` also accepts PUT** (*The share slot*).
- **`mimetype` selects the content type** (*Content types*). Cells carry no mimetype of their own.
- **`toplevel=True` serves at `/<path>` instead of `/<namespace>/<path>`.** A top-level key has one segment.
- **`status` has the keys of `contracts/mounts.md`, *`status`***, with `disk_checksum` read as the served checksum.
- **`url` uses `localhost` when the bind address is a wildcard.**

## The share slot

A node has one **share** slot, beside its file slot and its widget slot (`contracts/attachments.md`, *Scope*). They coexist in any combination: a mounted cell can be shared, and a shared cell can drive a widget.

- **A read-only share has mode `w`.** It never writes to the cell, so it is legal on a **connected** cell — that is how a computed value is served.
- **A writable share has mode `rw`.** It is a sensing attachment and therefore the node's producer: sharing a cell that has an incoming edge with `readonly=False` raises `AuthorityError`, and so does adding an incoming edge afterwards (`contracts/attachments.md`, *The topology rules an attachment imposes*).
- **The `authority` field is always `"cell"`.**
- **The celltype is frozen and clearing is refused** while the share exists, as for any attachment.
- **With a sensing file mount on the same cell, the newest accepted write wins**: a file edit is served and announced, and a PUT is written to the file.

### Shareable celltypes

`text`, `python`, `ipython`, `yaml`, `plain`, `str`, `int`, `float`, `bool`, `bytes`, `binary`, `mixed`. Any other celltype — `folder`, `deepfolder`, `deepcell`, `checksum`, `module` — raises `TypeError("Celltype '<ct>' is not shareable")`.

## The server

**One server per process serves every share of every Context, REST and websocket, on one port.**

- **It starts with the first share** — a `share()` call, or a `set_graph` that attaches shares — and stops at `seamless.close()`. A Context that closes takes its shares with it; the server stays.
- **It runs on its own thread and its own event loop.** It answers while user code blocks, in a script and under Jupyter, and it never runs on the caller's loop or the kernel's.
- **Defaults: host `0.0.0.0`, port `5813`** (ruled 2026-10-09). `shareserver.configure(host=, port=)` and the environment variables `SEAMLESS_SHARE_HOST` / `SEAMLESS_SHARE_PORT` override them; `port=0` asks the operating system for a free port, read back from `shareserver.port`. `configure()` after the server has started raises `RuntimeError`.
- **A busy port is an error.** The `share()` that would have started the server raises `OSError`, and nothing is installed.
- **There is no authentication and no TLS.** With the default bind address, every host that can reach the machine can read every share and PUT to every writable one. Bind to `127.0.0.1`, or put a reverse proxy in front, for anything else.
- **Cross-origin requests are allowed from any origin**, without credentials. The exposed headers are `ETag` and `X-Seamless-Marker`.

### Namespaces

**Every Context serves under one namespace, `ctx.shares.namespace`, default `"ctx"`** (ruled 2026-10-09).

- It is **runtime state**: not in the graph, and settable only while the Context has no shares.
- **A namespace belongs to one live Context.** The first share claims it; a second Context claiming a taken name raises `ValueError("Share namespace '<name>' is in use")`. Closing the Context releases it.
- The same graph can therefore be loaded into several Contexts in one process, each under its own namespace.

## URL space

| Request | Answer |
|---|---|
| `GET`, `HEAD`, `PUT` `/<namespace>/<path>` | a share |
| `GET`, `HEAD`, `PUT` `/<path>` | a `toplevel` share |
| `GET /<namespace>` with a websocket upgrade | the namespace's update stream |
| `GET /openapi.json` | the API description |
| `GET /seamless-client.js` | the browser client |
| `GET /` | `302` to `/index.html` when such a top-level share exists, else `404` |
| `GET /<namespace>/` | `302` to `/<namespace>/index.html` when that share exists, else `404` |
| `OPTIONS` anything | the CORS preflight answer |

`openapi.json`, `seamless-client.js` and every claimed namespace name are reserved top-level keys; a namespace cannot take the name of an existing top-level share. A key is matched whole: there is no access below a share.

## The record and the marker

The served state of a share is a **record**: a checksum, or none, and a **marker**.

- **The marker is an integer that increases by one every time the served checksum changes**, by a delivery from the cell or by an accepted PUT.
- **It is monotonic per URL for the lifetime of the server**, across unshare and re-share. It restarts with the process, which is why a client adopts the server's markers whenever it connects.
- **The record holds a claim on the served checksum**, so a value that was resolvable when it was announced stays resolvable while it is served.

## Reading: GET and HEAD

**The body is the buffer of the served checksum, byte for byte.** There is no share-local serialization, so the SHA-256 of the body is the checksum in the `ETag`.

| Status | When |
|---|---|
| `200` | the value; headers `Content-Type`, `ETag: "<checksum hex>"`, `X-Seamless-Marker: <n>`, `Cache-Control: no-cache` |
| `204` | the value is **null**; `ETag` and `X-Seamless-Marker` as above, no body |
| `304` | `If-None-Match` names the served checksum |
| `404` | no such share, or the share has no value yet; the JSON body says which |
| `503` | the value's bytes cannot be resolved |

- **`?mode=checksum`** returns the checksum hex as `text/plain` instead of the value.
- **`HEAD` never resolves bytes**; it answers from the record.
- **A GET resolves; it never computes.** It has exactly the powers of `.buffer`: the local buffer cache, then the remote buffer server. A value whose checksum arrived without its bytes — a remote result, a cache hit, a scratch result that was evicted — answers `503` until the bytes become resolvable (`contracts/attachments.md`, *A delivery resolves; it never computes*).
- **Only complete values are served.** While the cell is `waiting`, `blocked` or `failed`, the share keeps answering with the last value it served, under the same marker. Before the first complete value it answers `404`. Node state is read from the cell handle, not over HTTP.

### Content types

The content type is the first of:

1. the `mimetype` argument;
2. for a `text` or `bytes` cell, the type guessed from the extension of the share path (`index.html`, `logo.png`);
3. the celltype's default:

| Celltype | Content type |
|---|---|
| `text` | `text/plain` |
| `python`, `ipython` | `text/x-python` |
| `yaml` | `application/yaml` |
| `plain`, `str`, `int`, `float`, `bool` | `application/json` |
| `bytes`, `binary`, `mixed` | `application/octet-stream` |

`charset=utf-8` is added to `text/*`. A `str` cell serves a **quoted** JSON string; use `text` for raw text.

## Writing: PUT

**The request body is the value, in the cell's celltype** — the bytes a file mount would read for the same cell.

| Status | When |
|---|---|
| `200` | accepted; JSON `{"checksum": "<hex>", "marker": <n>}` — the record after the write |
| `400` | a malformed `marker` or `mode` parameter |
| `404` | no such share, or its Context is closing |
| `405` | the share is read-only; `Allow: GET, HEAD` |
| `409` | `?marker=n` does not equal the current marker; JSON `{"checksum", "marker"}` of the record |
| `413` | the body exceeds the request limit |
| `422` | the body is not a value of the celltype; JSON `{"error": "<reason>"}` |
| `503` | the Context did not process the write within the wait limit (*Limits*) |

- **The body is canonicalized with `canon_T`, and checked exactly as a user assignment of the same value is checked** — the rule of `contracts/mounts.md`, *Canonical bytes*, including that code celltypes get no syntax check. The cell holds the canonical bytes: a GET after a PUT of `{"a":1}` to a `plain` cell returns the canonical serialization.
- **An empty body, or `null`, writes null.**
- **An invalid body is refused and changes nothing.** It is an invalid request, not an invalid resource: the cell keeps its value and its state. **A share never puts a sense error on its cell.**
- **`?marker=n` makes the write conditional** (ruled 2026-10-09): `n` is the marker the client last saw, and the PUT is accepted only if it still is the current one. **Without the parameter the PUT is unconditional.**
- **A PUT of the value already served is accepted and changes nothing**: `200`, with the unchanged marker.
- **An accepted PUT is a sensed write** (`contracts/attachments.md`, *Sense*): a non-detaching authoritative write, with no privilege over a user assignment and none under it.
- **The `200` is sent after the write has been installed.** A `ctx.a.checksum` read, or a `ctx.compute()`, that starts after the response sees the PUT value or a newer one.
- **Every websocket client is told at acceptance**, before the cell has taken the value, and without delivery pacing.
- **A PUT beats a delivery that is in flight.** The delivery is acknowledged as a conflict, and the cell takes the PUT value.

## Cell to share

Delivery follows `contracts/attachments.md`, *Actuate*, without exception.

- **A delivery moves a checksum, never bytes.** It updates the record and announces it; nothing is resolved until a client asks.
- **Intermediate values are not queued**, and delivery starts are paced per session (`contracts/attachments.md`, *Actuate*): a rapidly changing cell is announced as its latest value.
- **A value sensed from a PUT is not delivered back.** The record already holds it.

## The initial decision

The initial decision is the table of `contracts/mounts.md`, *The initial decision table*, read with **the served value in the place of the file**, with `authority="cell"`, and with **a new share as an absent file**.

| Share | Cell | Result |
|---|---|---|
| read-only | `complete`, value *N* | *N* is served before `share()` returns |
| read-only | no complete value | nothing is served until the cell completes |
| writable | `complete`, value *N* | *N* is served before `share()` returns |
| writable | no complete value | **cell ← null**, and null is served |

The last row is row 4 of the no-value table and not a share rule: an absent resource attached in a sensing mode to a cell without a value installs null. Give the cell a value before sharing it when null is not wanted.

## The websocket

`GET /<namespace>` with a websocket upgrade opens the namespace's update stream. **The server only sends; anything a client sends is ignored.** Every message is a JSON array.

1. `["Seamless share update server", "1.0"]` — once, first.
2. `["shares", {<key>: {"url": "/ctx/a", "readonly": true, "content_type": "application/json", "binary": false, "checksum": "<hex>" | null, "marker": 3}, …}]` — the full state, after the handshake and again whenever a share is added to or removed from the namespace. It includes the namespace's top-level shares.
3. `["update", [<key>, "<checksum hex>", <marker>]]` — on every change of a record.

- **A client needs no request to learn the current state**: the first `shares` message carries every checksum and marker.
- **`binary`** is `false` for `text/*`, `application/json`, `application/yaml`, `application/javascript`, `application/xml` and the `+json` / `+xml` types, and `true` otherwise.
- Liveness uses websocket ping frames, not a message.
- When the Context closes, its connections are closed with code `1001`.

## `openapi.json`

`GET /openapi.json` returns an **OpenAPI 3.1** document generated from the shares that exist at the moment of the request, for every namespace. `ctx.shares.openapi()` returns the same document restricted to one Context, and `shareserver.openapi()` the whole one, without a request.

- **One path item per share**, at its URL: `get` and `head` always, `put` when the share is writable, with the status codes of this page.
- **Content type and schema follow the celltype:**

| Celltype | Schema |
|---|---|
| `int` | `{"type": "integer"}` |
| `float` | `{"type": "number"}` |
| `bool` | `{"type": "boolean"}` |
| `str` | `{"type": "string"}` |
| `plain` | `{}` — any JSON |
| `text`, `python`, `ipython`, `yaml` | `{"type": "string"}` |
| `bytes`, `binary`, `mixed` | binary content, no schema |

- A `mimetype` argument replaces the content type; the schema is then a string for text types and binary otherwise.
- Each operation carries `x-seamless-celltype` and `x-seamless-node` (the node path).
- The websocket is described in `info.description` and by `x-seamless-updates` (`{"<namespace>": "/<namespace>"}`); OpenAPI itself cannot express it.
- **The document describes shares, not the graph.** Cells that are not shared, and transformers, do not appear.

## `seamless-client.js`

`GET /seamless-client.js` serves a dependency-free browser client. It needs no share of its own.

```javascript
const ctx = connect_seamless()               // same origin, namespace "ctx"
ctx.self.onsharelist = function (keys) {
  ctx.a.onchange = function () { show(ctx.a.value) }
}
ctx.a.set("5")                               // PUT
```

- **`connect_seamless(update_server=null, rest_server=null, share_namespace="ctx")`.** The first two arguments name the one server and are aliases; `null` means the page's own origin. Each accepts a port number or a URL. If both are given and differ, the second wins and a warning is logged.
- **One entry per share**, `ctx[<key>]` with `/` written as `__`: `value`, `checksum`, `marker`, `binary`, `content_type`, `readonly`, `auto_read`, `set(value)`, `oninput`, `onchange`. `ctx.self` holds `sharelist`, `onsharelist`, `oninput`, `onchange`, `get_value()`, `connect()`, `ws`, `server` and `share_namespace`.
- **`value` is text, or a `Blob` when the share is binary**; `null` for a null value. JSON is not parsed for you.
- **`auto_read`** is `false` for keys containing a `.` — pages, scripts, images — and `true` otherwise; only auto-read shares are fetched on change.
- **`set()` sends one PUT per key at a time**, conditional on the marker it last saw, and keeps only the latest value set meanwhile. On `409` the local change is dropped and the server's value is fetched.
- **Entries survive a new `shares` message**: handlers stay attached, and only added and removed keys change.
- **A lost connection is retried with backoff**; on reconnect the client adopts the server's markers.

## The barrier

- **`ctx.mounts.sync()` cuts share sessions like any other.** A cut reports after every PUT accepted before it has been processed. Its `SyncReport` and `ctx.mounts.errors` carry an entry per share under the key `(node_path, "share")`.
- **`ctx.compute()` stays graph-only**, but because a PUT answers after its write is installed, a script that PUTs — from another thread or another process — and then computes needs no barrier in between.

## Threads and blocking

- **Every public call is an ordinary public Context operation.** `share()`, `del ctx.a.share`, `clear_error()` and setting `ctx.shares.namespace` block the caller, raise `ReentrantContextError` from the controller thread and `ClosedContextError` after `close()`.
- **Request handlers run on the server thread.** No user code runs in them.
- **A blocking HTTP call from the thread that owns the Context is fine**: the server does not need that thread.

## Errors

Raised at the call:

| Error | Raised when |
|---|---|
| `AttributeError("share is only available for bound workflow cells")` | a standalone `Cell` |
| `AttributeError("Only whole Context cell nodes can be shared")` | a sub-path projection (`ctx.a.b`); a read-only handle, **including a transformer's result, `ctx.tf.result`** |
| `NodeError("Shares require an existing whole cell node")` | the node does not exist or is not a cell |
| `ValueError("Cell is already shared; unshare first")` | the share slot is occupied |
| `ValueError("Share path '<path>' is in use")` | another share of the namespace, or another top-level share, has the key; or the key is reserved |
| `ValueError("Share namespace '<name>' is in use")` | another live Context holds the namespace |
| `ValueError` | an invalid key; an unparseable `mimetype`; a top-level key with more than one segment |
| `TypeError("Celltype '<ct>' is not shareable")` | *Shareable celltypes* |
| `AuthorityError("A writable share cannot have incoming edges; share it read-only")` | `readonly=False` on a connected cell |
| `AuthorityError` | an incoming edge into a writably shared cell; clearing a shared cell |
| `OSError` | the server cannot bind |
| `ImportError` | `aiohttp` is not installed (`seamless-workflow[share]`) |

The remedy for every scope refusal is the usual one: **share a cell and connect it.** `ctx.out = ctx.tf.result; ctx.out.share()` serves a transformer's result.

Of the three-way error model of `contracts/attachments.md`, a share has only the **delivery error**, on `ctx.a.share.error`: the server could not take the delivery. It is retried with the usual backoff. There is no sense error (*Writing: PUT*), and the oscillation detector cannot trip: a read-only share has no foreign writer, and a writable one never reasserts.

## Graph serialization

- **Format `0.6`** adds the `share` entry (ruled 2026-10-09). `0.2` to `0.5` graphs load; a `share` entry in a graph below `0.6` raises `PathError("share entries require workflow graph version 0.6")`.
- **The share entry** is `{"path", "readonly", "mimetype", "toplevel"}` on a cell entry — the spec after normalization, with the default key written out.
- **Every share entry is validated by `prepare_graph`**, also with `shares=False`: unknown fields, an invalid key, an unshareable celltype, a share on a non-cell node, a connection into a writably shared node, and two shares with one URL are refused as `PathError("Invalid share spec: …")`.
- **`shares=False` strips the (valid) specs.**
- **`shares=True` — the default — attaches every spec exactly as `share()` does.** It starts the server if needed, and it blocks through every first delivery, like `mounts=True`. A key or namespace that is taken raises, and the graph is not replaced.
- **The namespace is not in the graph.** Set `ctx.shares.namespace` before loading.
- **Loading a graph with shares opens a network endpoint.** Graphs of unknown origin must be loaded with `shares=False`.

## Lifecycle

- **Every detach removes the URL.** `del ctx.a.share`, deleting the node, an empty same-celltype builder, `set_graph()` and `ctx.close()` all end in the same detach (`contracts/attachments.md`, *Attach, detach, close*). Requests then answer `404`, and the namespace's clients get a new `shares` message.
- **Slot detach is independent.** `del ctx.a.share` leaves a file mount and a widget hub in place.
- **A new share on the same URL continues its marker sequence.**
- **To change `path`, `readonly`, `mimetype` or `toplevel`, unshare and share again.**
- `del ctx.a.share` on a cell without a share is a no-op, and `.spec`, `.url`, `.status` and `.error` answer `None`.

## Limits

**The numbers are current defaults, not contract:**

| Knob | Current default |
|---|---|
| request body limit | 1 GiB |
| wait for a PUT to be installed | 60 s, then `503` |
| resolution timeout of a GET | 60 s, then `503` |
| websocket ping interval | 10 s |
| delivery pacing | `contracts/attachments.md`, *Actuate* |

A value is held in memory in full for the duration of a request. There are no range requests.

## Porting notes

Stated as current behaviour, with no claim about what any earlier version did:

- **There is one port**, for REST and websocket.
- **Bodies are values.** A PUT body is the value itself, and so is a GET body; there is no JSON envelope and no base64.
- **`?marker=` is the marker you last saw**, not the one you propose.
- **A websocket client gets the current state on connect.**
- **Null is `204`.** `404` means there is no value.
- **A GET never recomputes a value.**
- **`share()` returns `None`.**
- **The content type is an argument of `share()`**, or follows the path's extension or the celltype.
- **The namespace is set on the Context at run time**, and a taken name raises.
- **A busy port raises.**
- **The client is served by the server**, at `/seamless-client.js`.
- **`ctx.compute()` does not wait for shares**, and does not need to after a PUT has answered.

## Implementation status and current limitations

This page is written ahead of the implementation; `seamless-workflow/tests/test_contract_shares.py` pins it.

- **Topology refusals raised by generic code say "mount".** An incoming edge into a writably shared cell raises `AuthorityError("Sensing mount is the producer; unmount first")`, and clearing raises `AuthorityError("Cannot clear a mounted cell; unmount first")`. The remedy is `del ctx.a.share`.
- **The barrier is spelled `ctx.mounts`.**
- **Node state is not served.** A client cannot tell `waiting` from `failed`; it sees the last value.
- **A writable share cannot be made on a cell that should stay empty** (*The initial decision*).

## Non-goals

- **Generating a web page or form from the graph.** A page is a `text` cell that you write and share.
- **A status graph.** Deferred; node states and the graph structure are not served.
- **Access below a share** (`/ctx/a/x`). Share a connected cell that holds the projection: `ctx.x = ctx.a.x; ctx.x.share()`.
- **PUT by checksum.** Deferred with a named condition: it needs the check that `ctx.a.checksum = …` performs, which a transport cannot perform today.
- **Directory and deep shares.** `folder`, `deepfolder` and `deepcell` cells are not shareable.
- **Computing on GET.** A GET resolves and never fingertips.
- **Authentication, TLS, sessions.** Every client of a namespace edits the same graph. Use a reverse proxy for access control, and one Context per user for isolation.
- **Standalone, sub-path, pin and code shares.** As for every attachment (`contracts/attachments.md`, *Non-goals*).
````

## Appendix B — edits to existing contract pages

Applied after the in-flight slot edits to these pages are committed.

- **`attachments.md`**
  - *Code locations*: add the share rows; "Public share API".
  - *Scope*: "one file slot, one widget slot and one **share** slot"; add `ctx.a.share` to the list of slot-addressing surfaces.
  - *The durable spec and the ephemeral session*: `Node.attachments` holds non-file specs by driver; **of these only `share` is serialized**. Round trip carries the file spec and the share spec.
  - *Sense*: a transport may refuse invalid input before it becomes an observation; the share driver does (`contracts/shares.md`, *Writing: PUT*).
  - *A delivery resolves; it never computes*: note that a share delivery does not even resolve.
  - *The driver roster*: add **share** (`share.driver.ShareDriver`), supported through `Cell.share`; serializable.
  - *Current limitations*: `SyncReport` driver values now include `"share"`; the share driver does not borrow the file service.
- **`cells.md`**, *API-name arbitration*: `share` joins `mount` and `block_reason` as a bound-only class member; `ctx.a["share"]` is the escape hatch.
- **`workflow-context.md`**: `shares` reserved beside `mounts`; `set_graph(graph, mounts=True, shares=True)` and its row in the blocking table; graph format `0.6`.
- **`mounts.md`**: *Graph serialization* → the contract format is `0.6`; `SyncReport` keys list `"share"` as a driver.
- **`widgets.md`**: *Current limitations* → "one file slot, one widget hub slot and one share slot per node".
- **Registration**: `docs/agent/README.md`, `docs/agent/index.md`, `docs/agent/config/mkdocs.yml`, `seamless/mkdocs.yml`; regenerate `index.json`. (`widgets.md` and `streaming.md` are currently missing from all four — worth fixing in the same pass.)
