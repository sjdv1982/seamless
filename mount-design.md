# File mounts — implementation design

## Current Cell, Pin, and null contract

`celltype` is the produced value type. CellConfig keeps only that type; read-only
`input_celltype` comes from the source or stored producer. Retypes convert the
original input. Public `input_ref` is retired: `.source` reports the configured
upstream handle, while `.checksum` reads output and writes a literal input.
Root value/buffer/checksum assignments detach; `set*` methods check ownership.
`None` stores canonical null; checksum/buffer None clears, and mounted clearing
is refused. A Pin is a whole input handle sharing CellBase with Cell, cannot be a
source, and converts before the Transformer is constructed. Its failed conversion
blocks the Transformer on that pin.

Every supported celltype accepts stored null (`b"null\n"`). Missing, zero-byte,
and canonical-null files read as the same null checksum. A read does not rewrite
those representations. Null delivery writes a physically empty file, including
compressed paths. Missing directories mean null; empty directories mean `{}`.
Directory null delivery represents absence. Explicit nonpersistent unmount cleanup
is a separate policy. Historical audit excerpts below retain original identifiers
and observations; they do not override this implemented contract.


> **Status.** Implementation design. It builds on the Context controller in
> `seamless-workflow` as it exists today; §2 summarises the parts of that
> contract a mount implementation touches.
>
> **Scope.** Attaching whole Context cell nodes to files and directories: the
> generic attachment layer, the file driver, a process-global filesystem service,
> an external synchronisation barrier, and the implementation plan. Legacy
> Seamless (0.x) is the reference for user-visible policy; §17 compares the two
> and lists every intentional deviation.

---

## 1. What a mount is

An **attachment** connects one Context node to an external resource, in one or
both directions:

- **sense** — external state becomes an authoritative value write to the node:
  a user assignment from a different source;
- **actuate** — after a turn in which the node's value changed, that value is
  delivered to the resource.

A **file mount** is the attachment driver whose resource is a file or a
directory. It is the only production driver in this design. A deterministic
*manual* driver exists for tests (M2).

The attachment layer is deliberately narrow: identity, direction, message
ownership, error state and delivery discipline. It does not pretend that every
transport shares filesystem fingerprints, widget callback recursion, web
acknowledgements or one conflict policy. Echo suppression and conflict detection
have a common *place* in the session but are driver-specific *protocols*. The
contract is declared generic only after a second driver has been built on it
(M6).

**In scope:** Context-bound cell nodes, whole-node values, files (including
`.gz`/`.zst`) and deep-folder directories, modes `r`/`w`/`rw`, legacy
`authority` and `persistent`, graph serialisation, an external barrier.

**Out of scope for the first version:**

- mounting a standalone `Cell` — it has no controller and no update stream;
- sub-path mounts (`ctx.a.b.mount(...)`) — only nodes carry checksums;
- mounting transformer code or pins directly — both are transformer
  configuration, not cell values; mount a cell and connect it (§17.4);
- mounting a whole (sub)context to a directory with automatic child paths;
- continuous external ownership (a file that forbids later user assignment);
- cross-process locking.

---

## 2. The controller contract this builds on

- **Single owner.** Only the Context's controller thread reads or mutates live
  graph state. Code running on it is synchronous, non-yielding, and performs no
  I/O, hashing or materialisation (`controller.Controller.assert_owner`).
- **Sequenced ingress.** Every operation enters as an immutable
  `ContextMessage` carrying a monotonically increasing acceptance sequence
  (`Controller.enqueue`). Acceptance order is processing order. Background
  producers use `Controller.notify`, which silently drops the message if the
  Context is closed or has failed — and whose reply future nobody reads.
- **Message classes.** 1 procedure (close, barriers), 2 topology and
  configuration, 3 authoritative value write, 4 read, 5 E/T notification. An
  exception in a class-5 handler poisons the Context (`ControllerFailedError`);
  an exception in any other handler completes that message's reply future.
- **Producer-side preparation.** Serialisation, hashing and code preparation run
  on the caller's thread *before* ingress (`ingress.controller_method`,
  `_prepare_assignment`). The controller receives checksum-ready payloads,
  protected by `sidework.Lease` refholds for the duration of the call.
- **Authority.** A value write is decided against topology alone
  (`Context._validate_write`); a non-detaching write is refused if any incoming
  edge overlaps the written path. Installation is `_set_cell_root_with_edges`
  followed by the cascade (`_derive_all`).
- **Post-turn hook.** `Context._after_turn` runs the effects collected during the
  turn, then re-evaluates barrier predicates (`RuntimeAPI._check_barriers`). It
  runs after failed turns too, and returns early once the Context is closing.
  Effects must not block.
- **Barriers are predicates.** A barrier installs a predicate and a future, ends
  its turn, and is resolved by the first later turn that satisfies it; only the
  caller blocks. `timeout=None` waits; expiry raises `TimeoutError`, withdraws
  the predicate and cancels nothing (`ingress._wait`, `_wait_async`).
- **Side work.** A per-Context `SideLoop` runs E/T and expression work off the
  controller and never touches graph state.
- **Close.** `Context.close()` closes admission, runs `_begin_close` as a class-1
  turn (fails barriers, cancels runs), shuts the side loop down, releases graph
  refholds in `_finish_close`, and joins both threads. Contexts are registered
  with `seamless.close()`.
- **Diagnostics.** `seamless_workflow.diagnostics.record_turns` records immutable
  per-turn node snapshots; `seamless.diagnostics.record_materialisation()` records
  every serialisation, hash and resolution on every thread.

Five consequences shape everything below:

1. Everything slow — stat, read, decompress, canonicalise, hash, resolve, write —
   happens in the filesystem service or on the caller's thread, never in a turn.
2. A sense is a class-3 message whose payload is already a checksum plus a live
   buffer.
3. Observations arrive through `notify`, so their handler must route its own
   failures to the session. An exception left on the reply future is lost.
4. Attachment bookkeeping that runs as class 5 must treat every stale or
   unexpected input as data. Raising would poison the Context.
5. The external barrier is a completion predicate. It never holds the
   controller's processed frontier.

---

## 3. Decisions at a glance

1. **Mounts attach to whole cell nodes.** One mount per node.
2. **The spec is durable node state; the session is runtime state.** Sessions are
   never copied or restored.
3. **One process-global filesystem service** with three parts — registry, watch
   broker, I/O pool. It knows nothing about graphs.
4. **Inbound carries content.** An `Observation` contains the canonical checksum
   *and* a live buffer, not a dirty bit.
5. **Outbound carries a usable payload:** a checksum plus a delivery lease,
   resolved in the I/O pool. Never a bare checksum.
6. **A sense is a user write from another source:** same authority rule, same
   validation, never detaching.
7. **The session keeps one belief about the file** — its canonical checksum and
   fingerprint. Echo detection, write skipping and write preconditions all derive
   from it.
8. **Writes are atomic** (temporary file + rename) **and conditional** on the
   believed fingerprint.
9. **Canonical bytes come from the existing serialiser.** A mount parses neither
   more leniently nor more strictly than a user assignment of the same value.
10. **Legacy `authority` resolves the initial conflict only.** It is not a
    continuous ownership rule.
11. **A mount never gives up because of the file.** `mount()` blocks, and raises
    only for an invalid request. A file that is missing, unreadable or invalid
    becomes the *cell's* exception, a failed write becomes the mount's error, and
    in every case monitoring continues until the file is fixed.
12. **`ctx.compute()` stays graph-only.** `ctx.mounts.sync()` is the external
    finite cut. There is no `settled()` predicate.

---

## 4. Architecture

```text
 caller thread              Context controller             filesystem service (one per process)
 ─────────────              ──────────────────             ────────────────────────────────────
 ctx.a.mount(path)
   ├─ reserve path ─────────────────────────────────────▶  registry
   ├─ initial stable read ──────────────────────────────▶  I/O pool
   └─ _mount_attach ─────▶  turn: decide, install
                            post-turn: Delivery ────────▶  I/O pool ── conditional atomic write ──▶ file
                            ◀──────────── DeliveryAck ───
                                                            watch broker ─── stat poll ────────────── file
                                                                │ Dirty (internal, coalesced)
                                                                ▼
                                                            I/O pool ── stable read, canonicalise, hash
                            ◀──────────── Observation ───
                            turn: classify, write node,
                            cascade; post-turn actuation
```

Threads: one controller and one side loop per Context (existing); one broker
thread and a bounded I/O pool per process (new).

Ownership rules:

- The service holds no Context, node or graph objects. A registration holds a
  path, a session id and a *sink*: a callable bound to a weak reference to the
  Context's controller.
- The service never holds a bare checksum it intends to resolve later. Every
  `Observation` carries a live buffer. Every `Delivery` carries a lease owned by
  the controller.
- A message routed to a closed Context is dropped at the sink. Whoever drops a
  message releases the payload leases it carries.

Why the boundary carries content: if only a dirty path crossed it, every Context
would have to schedule its own I/O, shared read-only mounts would read the same
file twice, and "the event" would be undefined once the file changed again. If
only a checksum crossed it, the buffer's resolvability and lifetime would become
an implicit cross-system precondition. A dirty bit stays *inside* the service,
where it can be coalesced before any Context ordering claim is made. Once a
Context has accepted an `Observation`, the observation is immutable and is
processed exactly once. The controller does no coalescing of its own.

### 4.1 A driver has two halves

| half | runs on | contains | tested by |
|---|---|---|---|
| **policy** | controller turns; pure and synchronous | spec validation, initial decision table (§7.2), observation classification (§8.2), reassert rule (§9.4), oscillation detector (§12.2) | table-driven unit tests with no threads (M1) |
| **transport** | filesystem service threads | registration, polling, stable reads, canonicalisation, writes, cuts | service tests with no Context (M3) |

The manual driver keeps the file driver's policy half and replaces its
transport half with a queue the test controls.

### 4.2 Suggested layout

```text
seamless-core/seamless/checksum/canonical.py     canon_T per celltype (§10); shared with the CLI file loader
seamless-workflow/seamless_workflow/attachments/
    spec.py        AttachmentSpec; validation; graph (de)serialisation
    policy.py      decide_initial, classify_observation, reassert, detector   (pure)
    session.py     MountSession; the disk belief
    runtime.py     Context mixin: message handlers, post-turn actuation, sync predicate
    api.py         MountHandle (ctx.a.mount), ContextMounts (ctx.mounts)
    manual.py      deterministic manual driver
    fs/registry.py, fs/broker.py, fs/io_pool.py, fs/service.py
```

`runtime.py` is a mixin, like `Reactive` and `RuntimeAPI`, because the
controller dispatches messages to Context methods by name.

---

## 5. Spec and session

### 5.1 The durable spec

```text
AttachmentSpec(
    driver,        # "file"   (the manual driver is test-only and never serialised)
    mode,          # "r" | "w" | "rw"          — sense, actuate, or both
    config,        # frozen and driver-specific; for "file":
                   #   path        as given; resolved against the CWD at attach time
                   #   authority   "file" | "cell" | "file-strict"
                   #   persistent  bool
)
```

Validation and normalisation, all with legacy parity:

- defaults are `mode="rw"`, `authority="file"`, `persistent=True`;
- `authority="file"` with a mode lacking `r` is stored as `"cell"`;
- `"file-strict"` requires `r` in the mode and `persistent=True`;
- modes containing `r` require that the node has no incoming edge at any path;
- whether the mount is a file or a directory follows from the celltype (§10,
  §13), not from a flag.

**Storage.** The spec lives in a dedicated `Node.mount` field, *not* in
`CellConfig`. Only attach and detach messages change it; the parameterised
configuration path (`_set_node_config` / `_publish_config`) cannot. In
`get_graph()` a cell entry gains `"mount": {"mode", "path", "authority",
"persistent"}`, and the format version is bumped. `prepare_graph` must validate
the object (unknown fields or bad values raise `PathError`) and must refuse graph
versions newer than it understands. Today it reads neither the version nor keys
it does not know, so an older reader would silently drop a mount.

**Lifetime.** The spec survives value writes and every configuration edit that
leaves the node a cell. It is removed, and the session unmounted, when the node
is deleted or replaced by a transformer. Operations that would change the
celltype or target celltype of a mounted cell are refused ("unmount first"),
because the celltype defines how the file's bytes are read (§10).

**The sensing mount is the node's producer.** While a node has a mount whose mode
contains `r`, any operation that would add an incoming edge to it — at the root
or at any sub-path — is refused with `AuthorityError` ("unmount first"). That
includes assignment syntax, which would otherwise detach and connect. The check
belongs in the single place edges are added. It is the same rule as "a target
has at most one producer", and it is what makes a sensed write's authority check
unable to fail.

### 5.2 The runtime session

```text
MountSession(
    session_id,     # fresh per session and never reused; stale messages are recognised by mismatch
    node_path,
    spec,           # frozen copy
    registration,   # handle in the filesystem service
    disk,           # the belief: (checksum | ABSENT | INVALID, fingerprint) — comparison-only
    processed_ws,   # highest watch sequence accounted for, by observations and by acks
    last_synced,    # node checksum last requested for delivery or last sensed — the actuation baseline
    pending,        # at most one Delivery not yet dispatched
    in_flight,      # at most one dispatched Delivery awaiting its ack
    delivery_seq,
    reasserts,      # timestamps, for the oscillation detector
    sense_error,    # MountError reported as the cell's exception | None
    error,          # delivery or conflict error, reported on the mount | None
    state,          # active | tripped | closing
)
```

- A fresh `session_id` per session plays the role of a generation. Replacing a
  spec, remounting or reloading the graph closes the old session and opens a new
  one. Every late message from the old session fails the id match and is
  discarded.
- `disk.checksum` and `last_synced` are **comparison-only**. They are never
  resolved and hold no refholder. The session holds references only through its
  pending and in-flight deliveries (§9.3).
- Problems are reported where they belong, and none of them stops monitoring:
  - **Sense errors.** The file that sources the cell is unreadable or cannot be
    canonicalised. Missing files are valid null observations, even under `file-strict`. The error becomes the
    *cell's* exception (§8.2). It is cleared by the next valid observation, or by
    any later value write to the node.
  - **Delivery errors.** A write, or the resolution of its payload, failed. The
    cell's value is valid; only the file is behind. The error stays on the mount
    (`ctx.a.mount.error`), the delivery is retried (§9.7), and the next
    successful delivery clears it.
  - **Conflict errors.** The oscillation detector tripped (§12.2). The error is
    latched on the mount until `clear_error()`.

---

## 6. Messages

| message | from → to | class | payload | stale handling |
|---|---|---|---|---|
| `_mount_attach` | caller → controller | 2, with a class-3 half | node path, spec, registration, initial observation | reply future |
| `_mount_detach` | caller → controller | 2 | node path | reply future |
| `_mount_observed` | I/O pool → controller, via `notify` | 3 | session id, watch sequence, fingerprint, and one of: checksum + buffer + lease / `ABSENT` / `REJECTED(reason)` | discard; release lease |
| `_mount_delivered` | I/O pool → controller, internal | 5 | session id, delivery seq, watch sequence, and one of: written checksum + fingerprint / `CONFLICT(fingerprint)` / `ERROR(reason)` | discard |
| `_mount_cut` | service → controller, internal | 5 | session id, cut id, watch sequence resolved through | discard |
| `_mount_sync` | caller → controller | 1 | installs a completion predicate | withdrawn on timeout |
| `Delivery` | controller → I/O pool (post-turn effect) | — | session id, seq, checksum, celltype, codec, expected fingerprint, lease | — |
| `Dirty` | broker → I/O pool | internal to the service | registration, watch sequence, fingerprint | coalesced |

Handler rules:

1. Every handler first matches the session id. On a mismatch it releases the
   payload leases and returns.
2. `_mount_observed` catches its own failures and records them in the session's
   error slot (§2, consequence 3).
3. Class-5 handlers never raise on external input (§2, consequence 4).
4. No handler does I/O, hashing or resolution.

Acks and cut results must keep flowing while `close()` flushes deliveries
(§15), after ordinary admission has closed. They are therefore enqueued as
internal messages. `Controller.notify` needs an `internal=True` variant that
still swallows `ClosedContextError` once the controller has stopped.

---

## 7. Attaching

### 7.1 The attach protocol

`ctx.a.mount(path, mode="rw", authority="file", *, persistent=True)` does the
following on the caller's thread:

1. **Validate arguments:** the mode/authority/persistent combination, and
   whether the celltype is mountable (§10).
2. **Snapshot the node** (class 4). It must exist, be a cell and have no mount.
   For modes containing `r`, it must have no incoming edge.
3. **Resolve the path and reserve it** in the registry (§11.1). The broker starts
   watching now, so a change after the initial read is not lost: it becomes a
   later watch-sequence event.
4. **Run the initial stable read** in the I/O pool and wait for it. The result is
   `ABSENT`, `(canonical checksum, buffer, lease, fingerprint)` or
   `REJECTED(reason)`.
5. **Submit one `_mount_attach` message.** In its turn the controller:
   - re-validates topology and the absence of a mount;
   - evaluates the decision table (§7.2) against the node's value *at that turn*;
   - installs spec and session;
   - applies a file → node write if the table says so (an ordinary class-3
     install plus cascade), or sets a sense error if the file cannot supply
     that value;
   - queues an initial delivery if the table says node → file.
6. **If an initial delivery was queued, wait for its ack.** A failed write does
   not make `mount()` raise; it becomes the mount's error, and the write is
   retried.

**What `mount()` raises for.** Only an invalid *request*:

- bad arguments;
- a missing or non-cell node, or one that is already mounted;
- a mode containing `r` on a node with incoming edges;
- an unmountable celltype;
- a path that conflicts with another mount in this process;
- a closed Context, or a call from the controller thread.

Then nothing is installed and the reservation is released.

**What it never raises for** is the file's *state*: missing under `file-strict`,
unreadable, empty, invalid for the celltype, or not writable. In all of these
the mount is installed and monitoring:

- a problem reading the file becomes the cell's exception (§8.2);
- a problem writing it becomes the mount's error (§9.7);
- each is logged once.

When the file is fixed, the broker sees the change and the mount recovers
without user action. A permission fix changes the file's ctime, which is part of
the fingerprint (§11.2), so even an unreadable file is picked up again.

Three points need stating:

- **Why the read happens before the message.** Every other write already
  prepares its payload on the producer side, and doing the same here lets the
  whole decision happen in one turn. Deciding against a file read slightly
  earlier is not a race. For a single-threaded user no other message can
  intervene, because public calls block. A file change after the read is sensed
  after the attach turn.
- **Why `mount()` waits for the initial ack.** So that
  `ctx.a.mount("a.txt"); open("a.txt")` works, as it did in legacy Seamless,
  where initialisation wrote synchronously. If the write failed, `mount()` still
  returns, and `ctx.a.mount.error` says why the file is not there.
- **What it does not wait for.** A `w` mount on a node that is still computing
  returns immediately. The file is written when the node completes, and
  `ctx.mounts.sync()` is the way to wait for that.

### 7.2 The initial decision table

Inputs: the effective mode and authority; the file state (absent, present with
canonical checksum *F*, or rejected); the node state (no value, value *N*, or —
for `w` only — not yet complete). *F* and *N* are compared as canonical
checksums. "No value" means the node has no checksum.

| # | mode | authority | file | node | action | legacy |
|---|---|---|---|---|---|---|
| 1 | r, rw | file, file-strict | absent/empty/null | any | node ← canonical null; preserve file representation | changed |
| 2 | r, rw | cell | absent/empty/null | no value | node ← canonical null | changed |
| 3 | r | cell | absent/empty/null | *N* | preserve initial node value; record null baseline | same authority rule |
| 4 | rw, w | cell | absent/empty/null | *N* | write *N* only when different from null baseline | canonical comparison |
| 5 | r, rw | file, file-strict | *F* | no value | node ← *F* | same |
| 6 | r, rw | file, file-strict | *F* | *N* = *F* | nothing | same |
| 7 | r, rw | file, file-strict | *F* | *N* ≠ *F* | node ← *F*; log once | same (printed a warning) |
| 8 | r, rw | cell | *F* | no value | node ← *F* | same |
| 9 | r | cell | *F* | *N* | nothing; *F* becomes the baseline, later file changes flow in | **differs**: the first poll overwrote the node with *F* |
| 10 | rw, w | cell | *F* | *N* = *F* | nothing | rewrote identical bytes |
| 11 | rw, w | cell | *F* | *N* ≠ *F* | write *N*; log once for `rw` | same effect, silent |
| 12 | w | cell | *F* | no value / not complete | nothing now; write when complete | same |

**Rejected files.** A file may be unreadable, or impossible to canonicalise as
the celltype (§10). Where the table would install *F* into the node (rows 5, 7
and 8; row 6 cannot match), the cell gets a sense error instead: it becomes
`failed` with a `MountError`, and the mount keeps monitoring. Everywhere else a
rejected file counts as a present file that differs from *N*. Either way, the
session starts with `disk := INVALID`.

Legacy also counted a node as having no value if it held an empty string, an
empty object or an empty array — the JSON documents `""` (two quote characters),
`{}` and `[]`. That rule is not ported (§17.3).

### 7.3 Graph loading

`ctx.set_graph(graph, *, mounts=True)`:

- With `mounts=True`, every mount spec in the new graph is attached as in §7.1.
  All reservations and initial reads are prepared on the producer side, in
  parallel. One message replaces the graph and all sessions atomically, and the
  call waits for every initial ack. As with `mount()`, the state of a file never
  makes the load fail. It becomes a cell exception or a mount error, and that
  mount keeps monitoring.
- The old sessions close in the same turn. Reservations for the new graph may
  overlap registrations of the same Context that the replacement releases. The
  registry supports this as an **atomic swap**, which commits with the turn and
  is abandoned if the message fails.
- A released session with `persistent=False` does **not** delete its file when
  the new graph re-attaches the same path. (Legacy needed a 20-second garbage
  delay for this, because re-translation destroyed and recreated every mount.)
- `mounts=False` strips mount specs (legacy parity, confirmed in M1).

**Loading a graph with mounts writes files.** A graph with `w` or `rw` mounts
performs file writes when loaded. Graphs of unknown origin should be loaded with
`mounts=False`, and the API documentation must say so.

---

## 8. Sensing

### 8.1 From file change to `Observation` (filesystem service)

1. The broker sees a fingerprint change, or a racy file (§11.2). It advances the
   registration's watch sequence and emits `Dirty(ws, fingerprint)`. Each
   registration has at most one queued read; a newer dirty record replaces the
   queued one.
2. The I/O pool does a **stable read**: stat, read, stat. It retries with bounded
   backoff if the two fingerprints differ. `ENOENT` gives `ABSENT`.
3. It decompresses if the path has a compression suffix, then canonicalises
   (§10). Failure gives `REJECTED(reason)`.
4. It hashes the canonical bytes, registers the buffer with the buffer cache and
   takes an observation lease. This is how a user write already makes its buffer
   resolvable (`adapters.checksum_for_value`).
5. It emits `Observation(session_id, ws, fingerprint, checksum, buffer, lease)`
   through the registration's sink. `ws` is the watch sequence current at the
   read's *first* stat.

For read-only registrations shared by several sessions there is one read and one
buffer, with a separate lease per session.

### 8.2 Controller handling

In the `_mount_observed` turn:

1. **Session id mismatch** → discard.
2. **`ws <= processed_ws`** → stale → discard. Otherwise `processed_ws := ws`. A
   stale observation is either a duplicate or content read *before* one of our
   own writes landed, even if it reached ingress after that write's ack (§9.6).
   Discarding loses nothing: if the discarded read happened to see a newer
   foreign change, the broker detects that change again, because its baseline
   moves only with its own polls and with completed writes (§11.2).
3. **Classify** against the belief:

   | class | condition | effect |
   |---|---|---|
   | `unchanged` | checksum = `disk.checksum` | update `disk.fingerprint` only; identical-content rewrites and `touch` end here |
   | `echo` | checksum = the in-flight delivery's checksum | our own write, seen before its ack: `disk := (checksum, fingerprint)` |
   | `rejected` | unreadable, or not canonicalisable | `disk := (INVALID, fingerprint)`; modes with `r`: sense error; `w`: reassert |
   | `absent` | file missing | normalize to canonical null, then use unchanged/echo/foreign classification |
   | `foreign` | anything else | see below |

4. **Foreign, mode contains `r`:** install the checksum as a non-detaching value
   write — `_validate_write(path, (), detach=False)`, then
   `_set_cell_root_with_edges(..., clear_edges=False)`, then the cascade. Set
   `disk := (checksum, fingerprint)` and `last_synced := checksum`, so that
   actuation does not write the value back. The value write clears any sense
   error.
5. **Foreign, mode `w`:** reassert (§9.4).
6. Release the observation lease at the end of the turn. The node's producer
   claim now holds the checksum.

The authority check in step 4 cannot fail while the edge rule of §5.1 holds. If
it fails anyway, the failure is recorded in the session, not raised.

**How a sense error reaches the cell.** The session holds the error. When
`_derive_cell` derives a cell whose sensing mount has a sense error set, it
reports the cell as `failed` with that `MountError`. Downstream nodes then
become `blocked-by-error`, as for any other failure: a cell never presents a
stale value as valid while its source is broken.

- **The stored value is kept, but masked.** `get_graph()` still records the last
  good value, and unmounting unmasks it.
- **Any later value write clears the error,** whether it is a valid observation
  or a user assignment. This follows the accepted order: the newest
  authoritative input wins. Under `rw`, a user assignment is then written to the
  file, which repairs the file too. Every value write goes through
  `_set_cell_root_with_edges`, so that is the one place to clear the error.
- **`ctx.a.clear_exception()`** on such a cell requests an immediate re-read.

A brief error is cheap. If the file returns to its previous content, the
downstream transformations get their old identities back, and can re-latch onto
their held runs within the supersession grace window instead of recomputing.

**Why one belief instead of an echo list.** The belief handles the case that
defeats a naive "ignore what we last wrote" rule. We deliver *C1*; a foreign
writer replaces it with *C2*, which is sensed; the writer then reverts to *C1*.
A last-written list would discard that final *C1* as our own echo and leave the
node at *C2* while the file holds *C1*. Against the belief (`disk` = *C2* by
then) it is correctly classified `foreign`.

### 8.3 What sensing deliberately does not do

- **Invalid content does not stop monitoring.** It fails the cell (above), and
  the next valid content recovers it without user action. Editors that save by
  atomic rename never expose a half-written file; editors that truncate and then
  write may, briefly, and that shows as a short-lived exception.
- **Content that is merely wrong for the program is not rejected.** A Python
  syntax error in a `python` cell passes, because a user assignment of the same
  text passes. The failure surfaces where it would for a user write: in the
  transformer that runs it.
- **A deleted file does not clear the node.** Removing a value is an explicit
  graph operation. Under `file-strict`, where the file is required, deletion is a
  sense error instead.
- **Non-canonical bytes are not rewritten.** User formatting of a JSON file
  survives until the node's value actually changes.

---

## 9. Actuation

### 9.1 When a delivery is requested

At the end of every turn — in `_after_turn`, before barrier predicates are
re-evaluated — one pass runs over the Context's sessions whose mode contains
`w`:

```text
N = node checksum if node.state == "complete" else None
if N is not None and N != session.last_synced:
    session.last_synced = N
    if N != session.disk.checksum:
        request a delivery of N
```

The pass is O(number of mounts) per turn and needs no changed-set from the
cascade. A node that is `waiting`, `computing`, `blocked`, `failed` or `unwired`
produces nothing: transient states never delete or rewrite a file.

Actuation is triggered by *node changes*, never by a mismatch between node and
disk alone. That is why a rejected file in `rw` mode — someone mid-edit — is not
overwritten: the cell has a sense error, and a failed node delivers nothing until
a new value arrives.

### 9.2 Latest discipline

A session has at most one pending and one in-flight delivery. A new request
replaces the pending one and releases its lease. An in-flight write is never
cancelled. When it is acknowledged, the pending delivery, if any, is dispatched —
unless it now equals `disk.checksum`.

### 9.3 Payload and lease

`Delivery(session_id, seq, checksum, celltype, codec, expected_fingerprint,
lease)`. The lease is acquired in the requesting turn, under the role
`mount:<session_id>:delivery:<seq>`. The controller owns it and releases it on
supersession, acknowledgement, timeout or session close; the I/O pool never
releases it.

The I/O pool resolves the buffer as side work. It may fetch the buffer remotely,
or recompute a scratch result, exactly as any read would. If resolution fails,
the ack reports `ERROR`: the mount records a delivery error and retries (§9.7).

### 9.4 Reassert (`w` mode)

A foreign, rejected or absent observation in `w` mode means someone else changed
an output the Context owns. If the node is complete, the controller requests a
delivery of *N* even though `last_synced == N`, records a reassert timestamp and
runs the oscillation detector (§12.2). If the node is not complete, nothing
happens until it is.

### 9.5 Conditional writes

A delivery carries `expected_fingerprint`, the value of `disk.fingerprint` when
it was requested. Just before the atomic rename, the I/O pool re-stats the
target. On a mismatch it deletes the temporary file, requests a read, and acks
`CONFLICT`. The controller only clears `in_flight`; the observation that follows
decides the outcome — in `rw` the node takes the file's value, in `w` the Context
reasserts.

This precondition is what makes a mount converge. Suppose a user edit is being
written while a foreign writer saves: without the check, our write would land
over a change we have never seen, and the next read would classify our own
content as an echo — leaving the foreign edit silently lost. The window between
the re-stat and the rename remains. It is microseconds wide and is accepted,
because there is no portable filesystem compare-and-swap. Legacy Seamless had
the same race at poll-interval width, and resolved it by always letting the
outbound write win (§17.2).

### 9.6 Acknowledgement

`DeliveryAck(session_id, seq, ws, written_checksum, fingerprint)`. The
controller sets `disk := (written_checksum, fingerprint)`, advances
`processed_ws := max(processed_ws, ws)`, releases the lease, dispatches the
pending delivery if one is still needed, and clears any delivery error.

`ws` is the registration's watch sequence *advanced by the write itself*. The
service advances the sequence when a write completes, under the same
registration lock that orders a read's first stat. So any observation whose
content predates the write carries a smaller sequence and is discarded as stale
(§8.2, step 2), however late it reaches ingress. Without this, a read taken just
before our write could be accepted just after the ack, and would revert the node
to its previous value. That is the stale-echo problem legacy Seamless addressed
with `_renounce` (§17.2).

### 9.7 Delivery errors

Delivery errors — a failed write, a failed payload resolution, a timeout —
belong to the mount. They never mark the node failed, because its value is
valid; only the file is behind (see §20.11).

The mount does not give up. A failed delivery is retried with capped exponential
backoff (1 s, doubling, capped at 60 s), and immediately whenever the node's
value changes, until it succeeds or is superseded. A deleted target directory,
a full disk or a permission fix therefore recovers by itself. While it waits,
the retrying delivery keeps its lease (at most one per mount). A per-attempt
timeout bounds external hangs.

---

## 10. Canonical bytes

For each mountable celltype *T*, the mount uses exactly two functions, both
defined by the existing serialiser and deserialiser in seamless-core
(`checksum/serialize.py`, `checksum/parse_buffer.py`):

- **write:** the canonical buffer of the node's checksum, byte for byte
  (compressed, if the path carries a compression suffix);
- **read:** `canon_T(bytes) = serialize(deserialize(bytes, T), T)`. The observed
  checksum is the checksum of `canon_T(bytes)`. If deserialisation raises, the
  observation is `REJECTED`.

So a file written by the mount reads back as an exact echo, a user-formatted
file maps to the checksum of its value, and there is no mount-local parsing.
`canon_T` must be idempotent; M1 property-tests that.

*T* is always the cell's output `celltype`, including connected cells. The
producer's input type is stored separately. Retyping while mounted is refused.

| celltype | file mount | `canon_T` (read) | notes |
|---|---|---|---|
| `text`, `python`, `ipython`, `yaml` | yes | strict UTF-8; strip trailing `\n`, append exactly one | no CRLF conversion (CRLF is content); syntax not validated beyond what a user write validates |
| `plain` | yes | JSON parse, canonical re-serialisation | user formatting survives until the value changes; JSON only (§17.3) |
| `str` | yes | JSON parse (with the deserialiser's `str()` coercion), re-serialise | the file holds a *quoted* JSON string; use `text` for raw text |
| `int`, `float`, `bool` | yes | JSON parse with coercion, re-serialise | |
| `bytes` | yes | identity for nonempty content; empty → null | null resolves as empty bytes |
| `binary` | yes | must deserialise as a pure-binary (NumPy) value; round trip | |
| `mixed` | yes | must deserialise as mixed; round trip | |
| `deepfolder`, `folder` | directory only | §13 | |
| `checksum`, `deepcell`, `module` | no | — | `mount()` raises (an invalid request) |

**Null files.** Missing, zero-byte, and `b"null\n"` files read as canonical null
before celltype-specific parsing. This applies to int, plain, binary, and every
supported mounted type. A newline-only file is not a zero-byte file and still
undergoes normal parsing. A null read preserves the physical representation;
null delivery truncates to an empty file. Bytes null reads as `b""`.

**Compression.** A `.gz` or `.zst` suffix means: decompress before `canon_T` on
read, and compress the canonical bytes on write — deterministically (gzip with
`mtime=0`, fixed levels). As everywhere else in Seamless, the canonical checksum
is taken over the decompressed bytes. Compressed bytes are not stable across
compressor versions and settings, so every comparison uses canonical checksums.
Fingerprints only decide whether a read is worth doing. A foreign recompression
of identical content is `unchanged`.

**Placement.** `canon_T` belongs in seamless-core, next to the serialiser, so the
CLI file loader and mounts share one definition.

---

## 11. The filesystem service

### 11.1 Registry

- **Normalisation.** Paths are made absolute, with symlinks in the parent chain
  resolved. If the target itself is a symlink, the registration resolves to the
  link's target; writes then replace the target file and the link survives.
- **Conflicts.** Two registrations overlap if their paths are equal, or if one
  is a directory prefix of the other. Overlapping registrations are refused if
  either actuates or cleans up a directory. `r`-only registrations may overlap;
  equal `r`-only paths share one watch and one read. The check covers every
  Context in the process (legacy checked only within one root context).
- **Swap.** For `set_graph`, a reservation can name the registrations it
  replaces; the swap commits or aborts with the controller turn (§7.3).
- **Non-guarantees.** Other processes, hardlinks, bind mounts, case-insensitive
  filesystems and network-filesystem aliases are outside the check. It is a
  safety net, not an exclusivity guarantee.

### 11.2 Watch broker

- One thread polls each registration's `stat` every `poll_interval` (default
  0.2 s, the legacy latency).
- **Fingerprint:** existence plus `(st_dev, st_ino, st_size, st_mtime_ns,
  st_ctime_ns)`. The inode makes atomic replacement visible even when size and
  mtime match. The ctime makes permission and ownership changes visible, so a
  file that was unreadable is read again once it is fixed.
- **Racy files.** A file whose mtime lies within `racy_window` (default 2 s,
  which covers FAT and common NFS granularity) of the moment it was stat-ed is
  re-read at the next poll even if its fingerprint is unchanged, until it ages
  out. Otherwise a same-size rewrite within one mtime tick is invisible. This is
  the same fix git applies to "racily clean" index entries.
- **Watch sequences** are per registration and owned by the service. They
  advance on every detected change and every completed write, under the
  registration's lock. So a detected change always carries a larger sequence
  than every write completed before it.
- **Baseline.** The fingerprint the broker compares against is moved only by its
  own polls and by completed writes (to the written fingerprint). A read never
  moves it: a read that is later discarded as stale must not hide the change it
  happened to see.
- **Cuts** (for §14): `request_cut(registration)` polls immediately, then reports
  the watch sequence through which every dirty record has been resolved — to an
  observation, `unchanged`, `rejected` or `absent`. It reports even when nothing
  changed.
- **Directories** are scanned by a recursive stat walk at a slower cadence.
  Native notifications (inotify, FSEvents) can later be added as an optional
  producer of the same `Dirty` records (M6).
- The broker never reads content, hashes, resolves or calls a Context.

### 11.3 I/O pool

A bounded thread pool (default 4 workers).

- **Stable reads,** as in §8.1.
- **Atomic conditional writes:**
  1. Write to a temporary file in the target's directory, named
     `.<name>.seamless-<random>.tmp`.
  2. Copy the existing target's mode bits onto it; otherwise the umask default
     applies.
  3. Re-check the precondition (§9.5).
  4. `os.replace` onto the target.

  The broker and directory scans ignore the temporary-name pattern. There is no
  `fsync` by default: mounts serve live editing, not durability. Replacing a
  hardlinked target breaks the link, so other names keep the old content — this
  is documented, not prevented.
- **Conditional deletes,** for `persistent=False` (§15).
- **Payload resolution,** with a per-operation timeout.
- **Directory reads and writes** (§13).

### 11.4 Lifecycle

The service starts lazily on the first reservation. It registers with
`seamless.close()` so that it shuts down *after* all Contexts, which flush on
close (§15): stop the broker, drain the pool with a bound, join. Its threads are
daemon threads, so an abandoned interpreter can still exit.

---

## 12. Two writers

### 12.1 Within one process

Two writers in one process are prevented: the registry refuses incompatible
overlaps (§11.1), and a sensing mount refuses incoming edges (§5.1).

### 12.2 Across processes

Conditional writes (§9.5) stop us overwriting a change we have not seen. They do
not stop two processes taking turns. That needs a detector, because two
notebooks or two script runs on one file are a *common* accident, and legacy
Seamless turned that accident into an endless fight (§17.2).

A foreign write is not itself the signal. Under a sensing mount it is the whole
point — the user editing in an editor. The signal is narrower: **our actuation
restoring a value that a foreign writer had just replaced.**

```text
we deliver C1  →  a foreign C2 ≠ C1 is observed  →  we deliver C1 again
```

Count these reasserts per session and **trip at three within a rolling window
(default 20 s, tunable in 10–30 s)**. The window matters. A human editing and
reverting over hours produces the same signature with no conflict, whereas a
machine fight runs at the poll rate and crosses the threshold in under a second.

On trip:

- record a latched `ConflictError` in the session, carrying the path and the
  alternating checksums, and log it once;
- stop actuating;
- keep the registration. The mount keeps sensing (modes with `r`) or watching
  (`w`), so its status stays current — tracking the other writer beats
  diverging silently. A tripped mount is paused, never dead.

Recovery of actuation is manual, via `clear_error()`. The detector is a counter and a
timestamp over state the session already keeps, so it ships with echo handling
(M4) rather than with hardening.

**Scope.** The detector finds *oscillation*. It does not fire on two `rw` mounts
over independent nodes in two processes: those converge silently on the last
writer, coupling the two workflows through the filesystem so that one's results
depend on whether the other was running. Nothing here can detect that across
processes. It is a documented warning, not a promise of detection.

---

## 13. Directory mounts

- **Celltypes.** `deepfolder` and `folder`. The node's value is the deep-folder
  index — relative path → leaf checksum, serialised as plain JSON — and the
  session tracks only the top-level checksum.
- **Read.** Walk the tree, ignoring temporary names. For each file, strip a
  compression suffix from the name and decompress the content, as the CLI loader
  does (`seamless_transformer.cmd.file_load.files_to_checksums`). Hash the raw
  bytes: leaves are bytes, so no text decoding is needed. Build the index,
  serialise it, hash it, and emit one `Observation` whose buffer is the index.
- **Leaf retention.** Leaves must stay resolvable while the node holds the index.
  M5 must establish how the reference lifecycle retains the leaves of a deep
  value owned by a node. Until that claim exists, the observation carries leaf
  leases as well.
- **Limits.** A maximum file count, a maximum total size and a scan timeout.
  Exceeding any of them makes the observation `REJECTED`.
- **Write.** Replace each changed leaf atomically, then remove extraneous files
  where cleanup applies (legacy rule: iff `mode == "w"` or
  `authority == "cell"`). Ack after the whole tree is written. The tree as a
  whole is not replaced atomically, so while a directory delivery is in flight
  the broker holds that registration's dirty records: a half-written tree is
  never sensed.
- **Starting point.** `seamless.util.mount_directory.write_to_directory` is where
  to start, but it is neither atomic nor does it do buffer bookkeeping — its own
  docstring says so.
- **Empty directories** are not representable in the index; they are neither
  sensed nor created.

---

## 14. The external barrier: `ctx.mounts.sync()`

"Every queue is empty" is not a settledness criterion: a watcher can always be
between detecting a change and finishing its read. `sync()` establishes a finite
cut instead. It is a stateful completion predicate, and one round is:

1. request a cut from every registration of this Context;
2. wait for each registration's `_mount_cut` result. The service sends it only
   after enqueueing every observation that resolves dirty records at or below
   the cut. Ingress is FIFO, so by the time the controller processes the cut
   result, those observations have been processed too;
3. wait for graph quiescence — no node `waiting` or `computing`;
4. wait until no session has a pending or in-flight delivery. A delivery that
   failed and is waiting for its retry counts as settled, with its error
   reported;
5. if the round involved any foreign observation or any delivery, start another
   round — a delivery is itself a filesystem event after the cut; otherwise
   resolve.

Our own writes are normally consumed as `echo` or `unchanged` in the final
round. A genuinely concurrent foreign write starts another one.

**Return value.** A `SyncReport` listing, per mount: node checksum, disk
checksum, `in_sync`, and any sense, delivery or conflict error. `sync()` returns
even when a cell has a sense error, a mount is in error, or a `w` node is not
complete — just as `compute()` returns with failed nodes. The report says which.

**Timeout.** Same contract as `compute(timeout=...)`: `None` waits; expiry raises
`TimeoutError`, withdraws the predicate and cancels nothing. Continuous external
mutation can prevent convergence, which is what the timeout is for. Per-attempt
delivery timeouts are a different mechanism: a delivery that fails or times out
becomes a mount error and waits for its retry. For step 4 it counts as resolved,
so the cut completes with the shortfall recorded.

**Guarantee.** *Settled through the final cut:* every file change before the
final cut has been sensed and propagated, and every node value that was complete
at the end is on disk, or its session reports why not. A change after the cut is
outside the promise.

**Relation to `compute()`.** `ctx.compute()` is graph-only and never waits for
files. Legacy `ctx.compute()` also waited for the mount thread to drain its
outbound writes. A ported script that reads a mounted output after `compute()`
must call `ctx.mounts.sync()` as well.

**No `settled()` predicate.** "Is everything settled?" cannot be answered without
a cut. `sync()` is the only external-settlement promise.

**Implementation.** `_barriers` entries are fixed tuples today; they become
predicate objects, so the sync predicate can keep its round state. Cut requests
are post-turn effects. `_begin_close` fails sync barriers as it fails the others.
An async form, `await ctx.mounts.synchronization(timeout=None)`, mirrors
`computation()`.

---

## 15. Unmount, persistence and close

- **Unmounting.** `del ctx.a.mount` is class 2. It closes the session, drops the
  pending delivery (releasing its lease) and releases the registration; a late
  ack fails the id match. Unmounting clears the cell's sense error, if any,
  which unmasks the cell's stored value. Node deletion and replacement by a
  transformer unmount in the same way.
- **`persistent=False`.** The file is deleted on unmount, on node deletion and on
  close — but **only if its fingerprint still equals `disk.fingerprint`**. A
  file that a foreign writer has changed since is left alone, and that is
  logged. Legacy deleted unconditionally after a 20-second delay.
- **Close flushes.** `close()` gains a step after admission closes and before
  the side loop shuts down:
  1. stop sensing;
  2. for each persistent session, dispatch its pending delivery, if any;
  3. wait for in-flight acks, bounded by the delivery timeout. Failed
     deliveries are not retried at close; they are logged;
  4. run conditional deletes for `persistent=False` sessions, which are not
     flushed;
  5. unregister.

  This is so that `with Context() as ctx: ...` leaves output files current,
  which legacy scripts relied on. The flush completes only deliveries that
  ordinary actuation has already requested; it never compares node and disk
  afresh, so a file someone is mid-way through editing under `rw` is not
  overwritten at close. A close triggered by garbage collection on the
  controller thread cannot wait, and does not flush.
- **Interpreter exit.** `seamless.close()` closes the Contexts, each flushing,
  and then the filesystem service.

---

## 16. Public API

Naming is provisional; the semantics are not.

```python
ctx.a.mount(path, mode="rw", authority="file", *, persistent=True)
                           # blocking; raises only for an invalid request (§7.1)
del ctx.a.mount            # unmount

ctx.a.mount.spec           # the spec, or None
ctx.a.mount.status         # state, disk checksum, in_sync, pending/in-flight, errors
ctx.a.mount.error          # delivery or conflict error
ctx.a.mount.clear_error()

ctx.a.exception            # a MountError while the file cannot supply the cell's value
ctx.a.clear_exception()    # on such a cell: re-read the file now

report = ctx.mounts.sync(timeout=None)
report = await ctx.mounts.synchronization(timeout=None)
ctx.mounts.errors          # {node path: error}

ctx.set_graph(graph, mounts=True)
```

- **`mount` on cells.** `mount` becomes a class attribute (a property with a
  deleter) of `Cell`. `Cell` already treats class attributes as API members in
  `__getattr__`, `__setattr__` and `__delattr__`, so `del ctx.a.mount` reaches
  the deleter, never sub-path deletion. The cost is that a value key named
  `mount` is reachable only as `ctx.a["mount"]`, as for `value` or `checksum`.
- **Standalone cells.** A standalone `Cell` raises the bound-only
  `AttributeError` the class already uses for Context-only members.
- **`mounts` on Context.** It is plural, so it cannot be mistaken for mounting
  the Context itself, which legacy supported. Assigning a child named `mounts`
  must raise, rather than create a node that attribute access cannot reach.
- **Transformer handles** have no `mount`.
- **Calling from the controller thread.** `mount()`, `sync()` and unmounting
  raise `ReentrantContextError` there, like every public call.

---

## 17. Comparison with legacy Seamless

### 17.1 Architecture

Legacy mounts ran on one daemon thread per process, polling every file's mtime
every 0.2 s. The same thread drained a deque of outbound cell updates. A global
lock guarded both directions. Echoes were suppressed by `MountItem._renounce`,
and initialisation ran in the main thread during translation.

Traitlets and HTTP shares had their own schedulers, locks and echo suppressors.
Because foreign threads could mutate cells at any time, "no pending tasks"
stopped meaning "settled", and `ctx.compute()` had to consult the mount manager
(`must_run_mount`, `last_run`) before declaring the graph idle.

This design removes all of that coupling. Only the controller mutates the graph.
Mounts talk to it through immutable messages. Graph barriers remain graph-only,
and external settlement is a separate barrier.

Not ported, because stable node identity and explicit sessions remove their
reason to exist: translation-time `scan()`, the remount checksum cache, the
20-second garbage delay, `must_run_mount`, and symlink `LinkItem`s.

Legacy anchors are in `seamless/workflow/core/mount.py`: `MountItem.init`,
`conditional_read`, `conditional_write`, `set` and `MountManager.run_once`.

### 17.2 Legacy behaviour, as implemented

**Initialisation** is the "legacy" column of §7.2, plus:

- `authority="file"` without `r` silently became `"cell"`; `"file-strict"`
  required `r` and `persistent=True`. A missing file under `"file-strict"` made
  the mount raise.
- A cell holding an empty string, an empty object or an empty array (the JSON
  documents `""`, `{}` and `[]`) counted as having no value.
- With `authority="cell"` and `mode="r"`, initialisation did nothing *and did not
  record the file's mtime*. The first poll therefore read the file and overwrote
  the cell, so `authority="cell"` had no effect in `r` mode.
- With `authority="cell"`, a mode containing `w` and an existing differing file,
  the file was overwritten silently, although the docstring promises a warning.
- `rw` plus `authority="cell"` on a cell still being computed busy-waited up to
  1 s for a value.

**Ongoing behaviour:**

- Reads were gated on mtime; the checksum decided whether anything changed.
- `r`/`rw`: a changed file was loaded into the cell. `w`: a foreign change printed
  "write-only file … has changed on disk, overruling" and rewrote the file, at
  the poll rate, indefinitely — so two contexts sharing a path fought forever.
- A cell with a pending outbound update skipped its read in that tick. The
  outbound write won, and a file edit made in the same 0.2 s was overwritten
  silently.
- Clearing a cell's value left the file alone. For `r`/`rw`, the next poll
  appears to restore the cell from the mount's remembered checksum (M1 to
  confirm).
- A deleted file was not recreated until the cell changed again. A deleted
  directory was recreated, even in `r` mode.
- `plain` cells in modes containing `w` parsed the file as CSON, and wrote the
  normalised JSON back whenever normalisation changed the bytes. Editors then
  reported "file changed on disk".
- Text celltypes normalised trailing newlines on read, without writing back.
- `persistent=False` deleted the file 20 s after unmount unless something
  remounted it, whatever the file then contained.
- Duplicate paths were refused only within one root context, with no prefix
  check.
- `ctx.compute()` waited for the mount manager to drain outbound updates.

### 17.3 Intentional deviations

| behaviour | legacy | this design | why |
|---|---|---|---|
| `r` + `authority="cell"`, differing file at mount | file overwrites the cell at the first poll | cell kept; the file is the baseline | the legacy result is an unrecorded-mtime accident, not a policy |
| "no value" | no checksum, or an empty string, object or array | no checksum | the extra rule compensated for auto-initialised structured cells |
| `file-strict` with a missing file, at mount | raised | canonical null, with monitoring active | missing is an ordinary null observation |
| identical content at mount | rewritten | skipped | pointless write; bumps mtime for editors |
| cell edit and file edit within one poll | outbound wins silently | acceptance order decides; a conditional write refuses to overwrite an unseen change | a silent lost update |
| `w` + foreign change | rewrite forever | reassert; the detector trips after three reasserts in 20 s | endless fights |
| clearing an `r`/`rw` cell's value | apparently undone at the next poll | stays cleared; the file is untouched | clearing is an explicit graph operation |
| deleted `r` directory | recreated | not recreated | `r` never writes |
| `plain` file syntax | CSON accepted, JSON written back | JSON only, no write-back | one canonical form; no editor fights |
| invalid or unreadable file (modes with `r`) | to characterise in M1 | the cell's exception (`MountError`), downstream blocked; cleared by the next valid content or a user assignment; monitoring continues | the cell reflects its source, and a mount never gives up |
| failed write | traceback printed once; not retried until the cell changes again | mount error; retried with backoff until it succeeds or is superseded | a mount never gives up |
| `persistent=False` | unconditional delete after 20 s | conditional delete at unmount/close; `set_graph` swaps keep the file | never delete someone else's content |
| path overlap | exact duplicates, per root context | prefixes too, process-wide | directory/file overlaps are real conflicts |
| `ctx.compute()` | waits for outbound mount writes | graph-only; `ctx.mounts.sync()` waits for files | keeps graph quiescence meaningful |

### 17.4 Migration

| legacy | this design |
|---|---|
| `ctx.a.mount(path, mode, authority, persistent=...)` | unchanged |
| `del ctx.a.mount` | unchanged |
| `ctx.tf.code.mount("code.py")` | `ctx.code = Cell(celltype="python"); ctx.code.mount("code.py"); ctx.tf.code = ctx.code`, with pins declared on `ctx.tf` |
| `ctx.tf.x.mount(path)` (pin) | mount a cell and connect it: `ctx.tf.pins.x = ctx.x` |
| context mounts, `path=None` auto-paths, `set_file_extension` | explicit per-cell paths |
| `as_directory=True` on a mixed cell | a `deepfolder`/`folder` cell mounted to a directory |
| `directory_text_only`, `persistent=None`, `Module.mount`, `cson` cells | not ported |
| `ctx.compute()`, then read a mounted output | `ctx.compute(); ctx.mounts.sync()` |
| `set_graph(graph, mounts=...)` | unchanged |

The first row matters more than its length suggests. Editing transformer code in
an external editor through a code-cell mount was among the most common legacy
uses, and the only supported way now is a code cell connected by an edge —
which the Context already supports.

---

## 18. Implementation plan

### M1 — Policy, canonical bytes, legacy characterisation (no threads)

- `decide_initial`, `classify_observation`, the reassert rule and the detector as
  pure functions, with table-driven tests: one per row of §7.2, one per class of
  §8.2, one per deviation in §17.3.
- `canon_T` for every mountable celltype, in seamless-core, with property tests:
  idempotence; write-then-read is an exact echo; user-formatted JSON maps to the
  value's checksum; representative rejected inputs per celltype.
- Characterise legacy against a runnable 0.x installation where one exists,
  converting the print-based legacy mount scripts into assertions. Confirm every
  claim in §7.2 and §17.2, especially the quirks and every item marked "M1 to
  confirm" or "to characterise in M1". A claim that turns out wrong corrects the
  legacy column; it does not change the new policy by itself.

**Exit evidence:** the policy can be reviewed, and is fully tested, with no
controller and no filesystem.

### M2 — Spec, sessions and the manual driver (no filesystem)

- `Node.mount`; graph format, validation and version check; spec lifetime; the
  edge-refusal and celltype-refusal rules of §5.1.
- The Context mixin: attach, detach, observation and ack handlers; post-turn
  actuation; latest discipline; delivery leases with named roles; transient and
  latched errors; status.
- The manual driver: the test supplies observations, captures deliveries, and
  issues acks and cut results.
- An **attachment event recorder**, bounded and immutable like `record_turns`:
  each observation's class, each delivery request, dispatch, ack and conflict,
  reasserts and detector state.
- Tests:
  - a user edit against an observation, in both accepted orders;
  - an E/T result against an observation;
  - the stale-echo interleaving of §9.6: an observation read before a write but
    accepted after its ack must be discarded;
  - the foreign-revert case of §8.2;
  - unmounting with a delivery in flight;
  - stale-session messages after a remount;
  - close with pending and in-flight deliveries, followed by a clean refholder
    audit;
  - a rejected observation fails the cell and blocks downstream; a later valid
    observation, or a user assignment, clears it; unmounting unmasks the stored
    value; `get_graph()` keeps the last good value throughout;
  - an attach whose initial read is rejected,
    installs the mount with the cell failed, and a later valid observation
    recovers it;
  - sense and actuation turns materialise nothing on the controller thread
    (`record_materialisation`).

Why the event recorder is needed: an echo misclassified as foreign usually
re-installs the checksum the node already has, which no state or value assertion
can see. Only the classification record separates "echo suppressed" from "echo
applied as a no-op write". And only a forced interleaving exposes the harmful
variant, where the echo is stale and reverts a newer value.

**Exit evidence:** every interleaving of user edits, E/T results, observations,
acks, unmount and close can be forced deterministically, and is asserted by event
records as well as by values.

### M3 — The filesystem service (no Context; in parallel with M2)

- Registry, broker, I/O pool, stable reads, conditional atomic writes,
  conditional deletes, cuts and lifecycle.
- A fault-injecting shim around `stat`, `read` and `replace`, so races are
  scheduled rather than hoped for.
- Tests:
  - rewrite during a read;
  - identical-content `touch`;
  - editor-style atomic rename, and in-place truncate-and-write;
  - a same-size rewrite within one mtime tick (the racy rule);
  - write failure (permissions, simulated disk full, a missing target
    directory), and recovery by retry once the fault is removed;
  - timeouts;
  - a symlinked target;
  - mode-bit preservation;
  - precondition conflicts;
  - unregistering during a read or a write;
  - overlap refusal, including prefixes;
  - shared `r` registrations;
  - shutdown with work in flight.

**Exit evidence:** the service contract holds under fault injection with no graph
code present, and no component stores Context objects or bare resolvable
checksums.

### M4 — File mounts end to end, and `sync()`

- The attach protocol with the producer-side initial read; `set_graph` with
  mounts and the registry swap; unmount; persistence; the close flush.
- The `sync()` barrier. It belongs here, not with directory mounts: M4's
  integration tests cannot be deterministic without it.
- The oscillation detector.
- Tests:
  - the §7.2 table against real files;
  - `mount()` on an invalid or unreadable file
    returns with the cell failed and the mount active, and fixing the file —
    content or permissions — clears the exception without user action;
  - missing (`file-strict` included), zero-byte, and canonical-null files read
    as null without a cell error or a physical rewrite;
  - `mount()` on an unwritable path returns with a mount error, and the file
    appears once the path becomes writable;
  - the post-initialisation behaviour of each mode;
  - foreign modification under `w` and `rw`;
  - a user edit against a file edit, both orders;
  - a simulated foreign writer trips the detector within its window, while a
    slow edit-and-revert across the window does not;
  - ported legacy mount scripts, using `compute()` followed by
    `ctx.mounts.sync()`.

**Exit evidence:** integration tests use `sync()` and never sleep to infer
settledness. After `sync()`, every `rw` mount with no sense, delivery or conflict
error has file content equal to the node's value (canonical checksums). No file
problem ever leaves a mount unmonitored.

### M5 — Directory mounts

- Deep-folder reads and writes, leaf retention (§13), limits, cancellation of
  long scans, partial write failure, the cleanup rule, and holding sensing while
  a delivery is in flight.

**Exit evidence:** large trees, partial failures and cleanup behave as
specified, and the `sync()` guarantee holds unchanged for directories.

### M6 — Harden and generalise

- Measure broker load (registrations × poll rate), I/O pool sizing, sense-turn
  latency and buffer retention.
- Add native filesystem notifications behind the broker contract.
- Tune the detector's threshold and window against observed behaviour; M4 ships
  defaults, not evidence.
- Build a second driver (widget or HTTP) on the attachment contract before
  calling it generic.

### Dependency order

```text
M1 ─┐
M2 ─┼──▶ M4 ──▶ M5 ──▶ M6
M3 ─┘
```

M1, M2 and M3 are independent: M2 can stub the pure functions until M1 lands,
and M3 needs no Context. Real filesystem work must never be used to debug
controller ordering; that is what the manual driver is for.

---

## 19. Test instruments

| instrument | status | use |
|---|---|---|
| `seamless_workflow.diagnostics.record_turns` | exists | node states per turn around sense and actuation |
| `seamless.diagnostics.record_materialisation()` | exists | assert that mount turns materialise nothing on the controller thread |
| attachment event recorder | new (M2) | classification and delivery counts: echo vs foreign, conflicts, reasserts |
| manual driver | new (M2) | deterministic interleavings without a filesystem |
| fault-injecting filesystem shim | new (M3) | scheduled races in the service |
| `ctx.mounts.sync()` | new (M4) | the only way an integration test waits for files |

Never infer settledness from `sleep` or from temporarily empty queues.

---

## 20. Open decisions

Each has a recommendation; settle it before the milestone named.

1. **`w` file deleted by someone else** (M1). Recommended: reassert promptly. The
   Context owns the output, and deletion is a foreign modification like any
   other. Legacy waited for the next value change.
2. **`r`/`rw` file deleted** (M1). Recommended: leave the node unchanged, report
   status `absent`, and let the next node change recreate the file (`rw`). Under
   `file-strict`, deletion is a sense error (§8.3).
3. **Delivering a scratch result** (M2). Recommended: resolve it through the
   ordinary path, which may recompute it, and report a failure as a delivery
   error. Rejecting the mount forbids a legitimate use; forcing durable storage
   contradicts `scratch`.
4. **Fingerprints on network filesystems** (M3). Recommended: the §11.2
   fingerprint plus the racy rule, plus an optional per-mount `rehash_interval`
   for filesystems known to cache attributes (NFS `actimeo`). The checksum
   remains the correctness guard throughout.
5. **Initial limits** (M3). Suggested starting points:

   | limit | value |
   |---|---|
   | I/O workers | 4 |
   | poll interval | 0.2 s |
   | racy window | 2 s |
   | delivery timeout | 60 s |
   | maximum file size | 1 GiB (the buffer is held in memory) |
   | directory scan | 100 000 files, 10 GiB, 60 s |

6. **Close-flush bound** (M4). Recommended: the delivery timeout, with an
   optional `close(timeout=...)` override.
7. **Celltype change on a mounted cell** (M2). Recommended: refuse in the first
   version (§5.1). Re-initialising in place is possible later, but it needs a
   multi-turn protocol that a configuration edit does not have.
8. **Detector threshold and window** (M6). Ship three reasserts in 20 s, then
   tune.
9. **Leaf retention for directory mounts** (M5). Establish what the reference
   lifecycle guarantees for leaves of a node-held deep value; §13 falls back to
   observation-held leaf leases.
10. **Continuous external ownership** (`edit_policy="external-owned"`: a file
    that forbids later user assignment). Deferred. If added, it gets its own name
    and specification. It must not be expressed by redefining
    `authority="file"`, which would be an incompatible change hidden under a
    familiar option.
11. **Write failures on the cell?** (M2). Recommended: no. A read problem
    becomes the cell's exception, because the file *is* the cell's value source.
    A write problem stays on the mount (§9.7), because the value is valid and
    only the file is behind: failing the cell would block every downstream
    consumer of a correct result, merely because a copy on disk could not be
    made. The cost is visibility — the problem shows in `ctx.a.mount.error`, the
    one-time log line and the `sync()` report, not in `ctx.a.exception`.

Executor libraries, exact exception names and logging formats are left to the
implementation.
