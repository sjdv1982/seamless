# HTTP shares (Contract)

A **share** is the attachment whose external resource is an HTTP endpoint served by this process. The cell's value is read with GET, written with PUT when the share is writable, and every change is announced over a websocket. **The attachment contract of `contracts/attachments.md` applies in full** — direction, scope, slots, spec versus session, the sense and actuate disciplines, delivery pacing, the cut barrier and the lifecycle. This page specializes it for values served over HTTP. It does not restate a rule from that page; each section says where the share driver makes a generic rule concrete.

Shares exist on the **workflow Context** only. A standalone `Cell` and a `direct`/`delayed` transformer have no HTTP integration. The `seamless-serve-graph` command loads workflow Contexts with their declared shares (*Serving saved graphs* below). **A share is unrelated to the `seamless-share` package**, which inspects and exports cached buffers and transformations.

Code locations:

| Concern | Module / symbol |
|---|---|
| Public handles | `seamless_workflow.attachments.share.api` (`ShareHandle`, `ContextShares`) |
| Server configuration | `seamless_workflow.shareserver` (`configure`, `host`, `port`, `url`, `openapi`, `close`) |
| Durable spec, celltype admission | `seamless_workflow.attachments.share.spec` (`ShareSpec`, `validate_celltype`) |
| Transport | `seamless_workflow.attachments.share.driver.ShareDriver` |
| Server, records, namespaces, holds | `seamless_workflow.attachments.share.server` (`ShareServer`) |
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

- **It starts with the first share** — a `share()` call, or a `set_graph` that attaches shares — and stops at `seamless.close()`. A Context that closes leaves its shares served for a hold window, so that a new Context can take them over, and they go when the window ends (*The hold on close*); the server stays.
- **It runs on its own thread and its own event loop.** It answers while user code blocks, in a script and under Jupyter, and it never runs on the caller's loop or the kernel's.
- **Defaults: host `0.0.0.0`, port `5813`** (ruled 2026-10-09). `shareserver.configure(host=, port=)` and the environment variables `SEAMLESS_SHARE_HOST` / `SEAMLESS_SHARE_PORT` override them; `port=0` asks the operating system for a free port, read back from `shareserver.port`. `configure()` after the server has started raises `RuntimeError`.
- **A busy port is an error.** The `share()` that would have started the server raises `OSError`, and nothing is installed.
- **There is no authentication and no TLS.** With the default bind address, every host that can reach the machine can read every share and PUT to every writable one. Bind to `127.0.0.1`, or put a reverse proxy in front, for anything else.
- **Cross-origin requests are allowed from any origin**, without credentials. The exposed headers are `ETag` and `X-Seamless-Marker`.

### Namespaces

**Every Context serves under one namespace, `ctx.shares.namespace`, default `"ctx"`** (ruled 2026-10-09).

- It is **runtime state**: not in the graph, and settable only while the Context has no shares.
- **A namespace belongs to one live Context.** The first share claims it; a second Context claiming a taken name raises `ValueError("Share namespace '<name>' is in use")`. **Closing the Context holds it**: the first Context that claims it inside the hold window takes it over, with its shares and its connections; otherwise it is released when the window ends (*The hold on close*).
- The same graph can therefore be loaded into several Contexts in one process, each under its own namespace.

## URL space

| Request | Answer |
|---|---|
| `GET`, `HEAD` `/<namespace>/state-graph` | the Context node state graph |
| `GET`, `HEAD`, `PUT` `/<namespace>/<path>` | a share |
| `GET`, `HEAD`, `PUT` `/<path>` | a `toplevel` share |
| `GET /<namespace>` with a websocket upgrade | the namespace's update stream |
| `GET /openapi.json` | the API description |
| `GET /seamless-client.js` | the browser client |
| `GET /` | `302` to `/index.html` when such a top-level share exists, else `404` |
| `GET /<namespace>/` | `302` to `/<namespace>/index.html` when that share exists, else `404` |
| `OPTIONS` anything | the CORS preflight answer |

`openapi.json`, `seamless-client.js` and every claimed or held namespace name are reserved top-level keys; a namespace cannot take the name of an existing top-level share. `state-graph` is a reserved namespace key: a non-top-level share with that exact path raises `ValueError`. A top-level share named `state-graph` remains legal. A key is matched whole: there is no access below a share.

## The state graph

**Once a Context has its first share, `GET /<namespace>/state-graph` serves its whole node state graph until the Context closes**, including after its last share is removed, and serves its last publication through the hold that follows the close (*The hold on close*). Changing the namespace after final unshare releases the old namespace and its URL; the next share establishes the new one. A Context that never shared anything has no state-graph URL. Exposure is always on: every node's path, celltype or transformer language, state, checksum and error text is served to anyone who can reach the server, including nodes whose values are not shared.

The JSON object has `nodes`, `anonymous_nodes` and `connections`. Each named node has `type`, `path`, `state`, `block_reason`, `exception` and `checksum`; cells additionally have `celltype`, transformers `language`. `state`, `block_reason` and `exception` match the bound handle's reporting. Checksums are hex strings or null. `connections` and `anonymous_nodes` have exactly the graph-format structure written by `get_graph()`, so node identities and anonymous source references can be resolved in the same way.

```json
{"nodes":[{"type":"cell","path":["a"],"celltype":"plain","state":"complete","block_reason":null,"exception":null,"checksum":"<hex>"},{"type":"transformer","path":["add"],"language":"python","state":"blocked","block_reason":{"a":"blocked-by-error"},"exception":null,"checksum":null}],"anonymous_nodes":{},"connections":[{"type":"connection","source":["a"],"target":["add","a"]}]}
```

The payload omits transformer code and configuration, per-pin states and the run ledger (generation, hold deadlines and superseded runs). It never resolves values or buffers, performs derivation or computes a result.

- **The digest is the SHA-256 of canonical JSON** (sorted keys, compact separators). It is a change token only; the body is not stored in the buffer cache or hashserver.
- **The marker increases only when the published digest changes.** It is monotonic per namespace for the lifetime of the server: a Context that takes over a held namespace continues the sequence, and its first publication is announced only if its digest differs from the held one. A client resets its state-graph marker memory on reconnect (*`seamless-client.js`*).
- **GET and HEAD answer `200 application/json`**, with `ETag: "<digest>"`, `X-Seamless-Marker` and `Cache-Control: no-cache`. `If-None-Match` matching the digest answers `304`. HEAD omits the body. PUT answers `405`; an unavailable Context, or a namespace that is neither claimed nor held, answers `404`; a refresh timeout answers `503`. During a hold, GET and HEAD answer the closed Context's last publication, or `404` if it never published one.
- **At most one snapshot is built per half-second per Context**, regardless of request rate. A snapshot may be up to one interval old. A GET reuses a publication younger than the interval, and refreshes an older dirty publication or the first publication. A connected namespace client requests a dirty refresh each interval; a clean Context returns the cached publication without a controller turn.
- **Without websocket clients or GET requests, no snapshot work runs.** Snapshot reads run on the controller thread as read turns, and never poison the Context on failure. Standard graphs of a few hundred nodes require a single small pass over nodes and edges, without copying transformer configuration.

## The record and the marker

The served state of a share is a **record**: a checksum, or none, and a **marker**.

- **The marker is an integer that increases by one every time the served checksum changes**, by a delivery from the cell or by an accepted PUT.
- **It is monotonic per URL for the lifetime of the server**, across unshare, re-share and a hold. It restarts with the process, so a marker lower than one already seen at the same URL means that the server process restarted. The browser client relies on this (*`seamless-client.js`*).
- **The record holds a claim on the served checksum**, so a value that was resolvable when it was announced stays resolvable while it is served, through a hold included.

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
- **Only complete values are served.** While the cell is `waiting`, `blocked` or `failed`, the share keeps answering with the last value it served, under the same marker. Before the first complete value it answers `404`, unless the share re-attached a held record: it then keeps answering with the held value, under the held marker (*The hold on close*). The node state graph reports the current state separately (*The state graph*).

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
| `404` | no such share; or a held share whose hold window ended before it was re-attached (*The hold on close*) |
| `405` | the share is read-only; `Allow: GET, HEAD` |
| `409` | `?marker=n` does not equal the current marker; JSON `{"checksum", "marker"}` of the record |
| `413` | the body exceeds the request limit |
| `422` | the body is not a value of the celltype; JSON `{"error": "<reason>"}` |
| `503` | the Context did not process the write within the wait limit (*Limits*); for a PUT to a held share, the wait for the re-attach counts |

- **The body is canonicalized with `canon_T`, and checked exactly as a user assignment of the same value is checked** — the rule of `contracts/mounts.md`, *Canonical bytes*, including that code celltypes get no syntax check. The cell holds the canonical bytes: a GET after a PUT of `{"a":1}` to a `plain` cell returns the canonical serialization.
- **An empty body, or `null`, writes null.**
- **An invalid body is refused and changes nothing.** It is an invalid request, not an invalid resource: the cell keeps its value and its state. **A share never puts a sense error on its cell.**
- **`?marker=n` makes the write conditional** (ruled 2026-10-09): `n` is the marker the client last saw, and the PUT is accepted only if it still is the current one. **Without the parameter the PUT is unconditional.**
- **A PUT of the value already served is accepted and changes nothing**: `200`, with the unchanged marker.
- **An accepted PUT is a sensed write** (`contracts/attachments.md`, *Sense*): a non-detaching authoritative write, with no privilege over a user assignment and none under it.
- **The `200` is sent after the write has been installed.** A `ctx.a.checksum` read, or a `ctx.compute()`, that starts after the response sees the PUT value or a newer one.
- **A PUT to a held share waits until the share is re-attached** (*The hold on close*), and is then processed as a PUT to the re-attached share, after that share's initial decision. If the decision changed the served value, a `?marker=` condition fails with `409`; if the share is now read-only, the answer is `405`; if the window ends first, `404`.
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

**A share that re-attaches to a held record makes the same decision** (*The hold on close*): the held record counts as an absent file and never writes to the cell. It only gives the served side a starting point. A delivery of the held checksum therefore changes nothing — no marker bump, no `update` message — and a read-only share on a cell without a complete value keeps serving the held value until the cell completes. A writable share on a cell without a value still installs null, which is an ordinary update unless null was held.

## The websocket

`GET /<namespace>` with a websocket upgrade opens the namespace's update stream. **The server only sends; anything a client sends is ignored.** Every message is a JSON array.

1. `["Seamless share update server", "1.0"]` — once, first.
2. `["shares", {<key>: {"url": "/ctx/a", "readonly": true, "content_type": "application/json", "binary": false, "checksum": "<hex>" | null, "marker": 3}, …}]` — the full state, after the handshake and again whenever a share is added to or removed from the namespace, or re-attached with a different `readonly`, `content_type` or `binary` (*The hold on close*). It includes the namespace's top-level shares.
3. `["update", [<key>, "<checksum hex>", <marker>]]` — on every change of a record.
4. `["state-graph", ["<digest>", <marker>]]` — announces a state graph publication; GET the state-graph URL for its body.

- **A client needs no request to learn the current state**: the first `shares` message carries every checksum and marker.
- **A new client receives its first state-graph announcement within one half-second interval after the initial share snapshot.** Further announcements arrive at most once per interval and only when the published digest differs from the last digest sent to that client. Changes that return to the previously published graph inside one interval produce no announcement.
- **`binary`** is `false` for `text/*`, `application/json`, `application/yaml`, `application/javascript`, `application/xml` and the `+json` / `+xml` types, and `true` otherwise.
- Liveness uses websocket ping frames, not a message.
- **A Context close does not close the connections.** They are held with the namespace and pass to the Context that takes it over (*The hold on close*). They are closed with code `1001` when the namespace is released — at the end of a hold that no Context took over, or when its owner changes namespace after its final unshare — and when the server stops.

## `openapi.json`

`GET /openapi.json` returns an **OpenAPI 3.1** document generated from the shares that exist at the moment of the request, held shares included, for every namespace. `ctx.shares.openapi()` returns the same document restricted to one Context, and `shareserver.openapi()` the whole one, without a request.

- **One state-graph path item per claimed or held namespace**, with GET and HEAD and the responses described in *The state graph*.
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

- PUT request schemas additionally accept null, and the request body is optional because an omitted or empty body writes null (*Writing: PUT*). GET value schemas remain as listed above; `mode=checksum` additionally returns `text/plain` checksum text.
- A `mimetype` argument replaces the content type; the schema is then a string for text types and binary otherwise.
- Each operation carries `x-seamless-celltype` and `x-seamless-node` (the node path).
- The websocket is described in `info.description` and by `x-seamless-updates` (`{"<namespace>": "/<namespace>"}`); OpenAPI itself cannot express it.
- Individual value endpoints describe only shared cells; the state-graph endpoint includes all named cells and transformers.

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
- **One entry per share whose mapped property is distinct and is not `self`**, `ctx[<key>]` with `/` written as `__`: `value`, `checksum`, `marker`, `binary`, `content_type`, `readonly`, `auto_read`, `set(value)`, `oninput`, `onchange`. `ctx.self` holds `sharelist`, `onsharelist`, `oninput`, `onchange`, `get_value()`, `connect()`, `ws`, `server`, `share_namespace`, `stategraph` and `onstategraph`. The property-mapping limitation is listed under *Implementation status and current limitations*.
- **`value` is text, or a `Blob` when the share is binary**; `null` for a null value. JSON is not parsed for you.
- **`auto_read`** is `false` for keys containing a `.` — pages, scripts, images — and `true` otherwise; only auto-read shares are fetched on change.
- **`set()` sends one PUT per key at a time**, conditional on the marker it last saw, and keeps only the latest value set meanwhile. On `409` the client drops the local change, adopts the record in the response and fetches the server's value. A record or value whose marker is lower than the client's own is adopted only once the client has concluded that the server restarted (below); before that, it is ignored.
- **Entries survive a new `shares` message**: handlers stay attached, and only added and removed keys change.
- **`ctx.self.onstategraph` enables state graph reads.** When set, an announcement triggers a GET of `/<namespace>/state-graph`; the parsed object is stored in `ctx.self.stategraph`, then the handler is called. Responses older than the newest marker seen are dropped, and marker memory resets on reconnect. Pages without the handler do no extra reads.
- **A lost connection is retried with backoff.** A Context close loses no connection: the connection is held and passes to the Context that takes over the namespace (*The hold on close*).
- **The first `shares` message after a reconnect tells a restarted server from the same one** (*The record and the marker*):
  - **Restarted**: a server marker is lower than the client's, for a key the client holds, beyond **one tolerated not-yet-processed PUT in total**. The snapshot may predate the processing of a PUT whose response the client already has, because the HTTP response can overtake the websocket. So when exactly one key is lower, by exactly one, and the client's marker for that key comes from the response to its own PUT, that is no evidence of a restart; any other lower marker is. On a restart, the client adopts the server's marker for every key it holds and **reads no value**: its values and checksums stand, and no `oninput` or `onchange` is called. Mounted cells were restored from their files, so the page's own state is taken to be current; if it is not, the user reloads the page. Keys new to the client, and keys whose value it never read, are read as on a first connection. So is every key whose dropped change the client could not correct, because it ignored a `409` record with a lower marker (`set()` above).
  - **Same server**: no marker is lower beyond that tolerance. The client adopts every server marker and checksum that is not lower than its own, and re-reads every auto-read share. The `update` for a tolerated PUT follows on the websocket.
- **A write that reaches a restarted server before the client has adopted its markers** carries a marker of the previous process and is normally refused with `409`, and the client drops the change. If it has not concluded the restart yet, it ignores the response's record and the value it then reads, both carrying a lower marker (`set()` above): the page keeps showing the dropped change until the reconnect, when the client concludes the restart and reads that key.

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
| `ValueError("Share path '<path>' is in use")` | another share of the namespace, or another top-level share, has the key — a held top-level share included, for every Context but the one that takes over its namespace; or the key is reserved |
| `ValueError("Share namespace '<name>' is in use")` | another live Context has claimed the namespace |
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

## Serving saved graphs

The `seamless-suite` distribution installs `seamless-serve-graph`, whose entry point is `seamless_workflow.serve_graph:main`, and includes `seamless-workflow[share]`.

```bash
seamless-serve-graph graph.json
```

- **The command takes exactly one local graph file.** It reads UTF-8 JSON and passes it to the current workflow graph loader. The graph must use the current workflow serialization; the command does not convert an original legacy `__seamless__` export. Share entries require workflow graph version `0.6`.
- **The Context uses its default `ctx` namespace.** Shares in the saved graph become URLs under `/ctx/`; top-level shares keep their declared paths. The runner restores shares and disables file mounts. It does not require the graph to declare a share.
- **Loading starts reactive derivation.** The runner does not perform a buffer-availability preflight. Its share server uses the ordinary modern HTTP/websocket protocol and bind configuration from `seamless_workflow.shareserver`.
- **The runner owns shutdown.** It waits for SIGINT or SIGTERM in the main thread, restores the previous signal handlers, closes the Context, and calls `seamless.close()`.
- **Remote storage and execution use `seamless-config`.** Define the cluster and execution mode in the normal Seamless configuration files before launch. The runner loads configuration relative to its launch directory and has no remote-service flags. See [Setting up a local cluster](../../main/cluster.md) and [Remote execution](../../main/remote.md).

## Lifecycle

- **Every detach removes the URL at once, except a Context close.** `del ctx.a.share`, deleting the node, an empty same-celltype builder and `set_graph()` all end in the same detach (`contracts/attachments.md`, *Attach, detach, close*). Requests then answer `404`, and the namespace's clients get a new `shares` message.
- **`ctx.close()` holds its shares**, and removes at the end of the hold window those that no new Context re-attached (*The hold on close*).
- **Slot detach is independent.** `del ctx.a.share` leaves a file mount and a widget hub in place.
- **A new share on the same URL continues its marker sequence.**
- **To change `path`, `readonly`, `mimetype` or `toplevel`, unshare and share again.**
- `del ctx.a.share` on a cell without a share is a no-op, and `.spec`, `.url`, `.status` and `.error` answer `None`.

## The hold on close

**`ctx.close()` does not remove its shares at once. The server holds them for a window, 10 s by default (*Limits*), and a Context that shares the same URLs inside the window takes them over.** Re-running a serving script with `%run -i` — close the old Context, build a new one — is therefore invisible to clients for every value that did not change.

- **What is held is the namespace**: every record of the closing Context, top-level ones included, each with its entry, checksum, marker and claim; the websocket connections; and the last state-graph publication. A Context that never claimed a namespace holds nothing.
- **The hold starts when `close()` stops sensing** (`contracts/attachments.md`, *Close*, step 1). The close flush still completes the deliveries already requested, as ordinary updates. After the flush, nothing the closing Context does changes a record or sends a message: its teardown is invisible. **The window starts when `close()` returns**; `close()` does not wait for it.
- **During the hold, held shares answer from their records.** GET, HEAD and `?mode=checksum` answer as before, and the connections stay open. A client that connects gets the handshake, a `shares` message with the held records and, if there is one, an announcement of the held state-graph publication, which the state-graph URL serves. `/openapi.json` keeps describing the held shares and the namespace's state-graph endpoint. A PUT waits for its share to be re-attached (*Writing: PUT*).
- **The first Context that claims the namespace inside the window takes it over** — by its first share, or by a `set_graph()` that attaches shares — instead of raising `ValueError("Share namespace '<name>' is in use")`. The connections, the held records and the state-graph marker sequence pass to it. The held top-level keys are refused to every other Context.
- **A share of that Context at the URL of a held record re-attaches to it**, whatever its node, celltype or flags. Its initial decision is that of a new share, and the held record only gives the served side its starting point (*The initial decision*):
  - a value equal to the held one is served under the held marker: no marker bump, no `update` message;
  - a different value is one ordinary update;
  - a read-only share on a cell without a complete value keeps serving the held value until the cell completes; a writable one installs null, which is an ordinary update unless null was held;
  - a `shares` message is sent only if `readonly`, `content_type` or `binary` changed.
- **A held record that is not re-attached by the end of its window is removed**, as by any detach: requests answer `404`, a waiting PUT answers `404`, and the namespace's clients get a new `shares` message. If no Context took the namespace over, the namespace is released with its records: its connections are closed with code `1001`, and its URLs, the state-graph URL included, answer `404`.
- **A Context that took over a namespace holds it again when it closes.** Its own records, re-attached ones included, get a new window; records still held from the earlier close keep theirs.
- **Only `ctx.close()` holds.** Every other detach removes the URL at once (*Lifecycle*). `seamless.close()` stops the server, which ends every hold.
- **A hold never feeds a Context.** A value that a browser wrote into an unmounted cell does not reach the new Context, which starts from its own script. State that must survive a reload belongs in a file mount (`contracts/mounts.md`).

## Limits

**The numbers are current defaults, not contract:**

| Knob | Current default |
|---|---|
| request body limit | 1 GiB |
| wait for a PUT to be installed | 60 s, then `503` |
| resolution timeout of a GET | 60 s, then `503` |
| websocket ping interval | 10 s |
| hold window after `ctx.close()` | 10 s |
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

The share API, HTTP/WebSocket server, persistence, OpenAPI description and browser client implement this contract. Focused tests in `seamless-workflow/tests/test_contract_shares.py`, `test_share_transport.py` and `test_share_client_js.py` pin the behavior. Browser acceptance passed against headless Chrome in `seamless-workflow/tests/test_share_browser.py`, including slider keyboard input, Python-to-browser updates, two-tab editing and mounted-page updates.

- **Topology refusals raised by generic code say "mount".** An incoming edge into a writably shared cell raises `AuthorityError("Sensing mount is the producer; unmount first")`, and clearing raises `AuthorityError("Cannot clear a mounted cell; unmount first")`. The remedy is `del ctx.a.share`.
- **The barrier is spelled `ctx.mounts`.**
- **A writable share cannot be made on a cell that should stay empty** (*The initial decision*).
- **The browser client's property mapping cannot represent every legal share key.** `a/b` and `a__b` both map to `ctx.a__b`, and `self` collides with the client control API. These remain valid HTTP share paths. For a namespace containing such keys, choose distinct share paths or use the HTTP endpoints through a custom client.

## Non-goals

- **Generating a web page or form from the graph.** A page is a `text` cell that you write and share.
- **Access below a share** (`/ctx/a/x`). Share a connected cell that holds the projection: `ctx.x = ctx.a.x; ctx.x.share()`.
- **PUT by checksum.** Deferred with a named condition: it needs the check that `ctx.a.checksum = …` performs, which a transport cannot perform today.
- **Directory and deep shares.** `folder`, `deepfolder` and `deepcell` cells are not shareable.
- **Computing on GET.** A GET resolves and never fingertips.
- **Authentication, TLS, sessions.** Every client of a namespace edits the same graph. Use a reverse proxy for access control, and one Context per user for isolation.
- **Standalone, sub-path, pin and code shares.** As for every attachment (`contracts/attachments.md`, *Non-goals*).
