# File mounts (Contract)

A **mount** is the attachment whose external resource is a file or a directory. **The attachment contract of `contracts/attachments.md` applies in full — direction, scope, spec versus session, the sense and actuate disciplines, the three-way error model, the detector mechanism, the cut barrier and the lifecycle — and this page specializes it for bytes on a filesystem.** Nothing here restates a rule from that page; every section says where the file driver makes a generic rule concrete.

Code locations:

| Concern | Module / symbol |
|---|---|
| Public handles | `seamless_workflow.attachments.api` (`MountHandle`, `ContextMounts`, `load_graph`) |
| Spec, normalization, celltype admission | `seamless_workflow.attachments.spec` (`AttachmentSpec`, `validate_celltype`) |
| Initial decision, classification, reassert, detector | `seamless_workflow.attachments.policy` (pure functions) |
| Transport: registry, broker, I/O pool | `seamless_workflow.attachments.fs.service` (`FileSystemService`, `Registration`, `FileSystem`, `get_service`, `close_service`) |
| Optional inotify hints | `seamless_workflow.attachments.fs.native.NativeNotifications` |
| Canonical bytes | `seamless.checksum.canonical` (`canon_T`, `FILE_CELLTYPES`, `DIRECTORY_CELLTYPES`) — seamless-core, shared with the CLI file loader |
| Graph entry and validation | `seamless_workflow.serialization.prepare_graph`; `Context.get_graph` / `set_graph` |
| Errors | `seamless_workflow.attachments.session` (`MountError`, `ConflictError`), `seamless_workflow.errors` (`AuthorityError`, `NodeError`, `PathError`, `ReentrantContextError`) |

## The API

```python
ctx.a.mount(path, mode="rw", authority="file", *, persistent=True)   # blocking; returns None
del ctx.a.mount                                                      # unmount

ctx.a.mount.spec            # the AttachmentSpec, or None
ctx.a.mount.status          # the status dict, or None
ctx.a.mount.error           # delivery or conflict error, or None
ctx.a.mount.clear_error()

report = ctx.mounts.sync(timeout=None)
report = await ctx.mounts.synchronization(timeout=None)
ctx.mounts.errors           # {node path: error}

ctx.set_graph(graph, mounts=True)
```

- **`mount` is a class attribute of `Cell`** — a property with a deleter — so `del ctx.a.mount` reaches the deleter and never sub-path deletion. The cost is that a value key named `mount` is reachable only as `ctx.a["mount"]`, as for `value` or `checksum` (`contracts/cells.md`, *API-name arbitration*).
- **`mounts` is reserved on the Context.** `ctx.mounts = x` raises `AttributeError("mounts is reserved for the Context mount API")`, and a graph node at path `("mounts",)` is refused with `PathError("mounts is a reserved Context API name")`. The plural is deliberate: it cannot be mistaken for mounting the Context itself.
- **`mount()` blocks through the initial read and the first delivery attempt, and raises only for an invalid *request*** — never for the state of the file. See `contracts/attachments.md`, *Attach, detach, close*.
- **`path` normalization.** Anything `os.fspath` accepts — a `str` or an `os.PathLike` — is accepted; an empty path or one containing a NUL raises `ValueError("mount path must be a nonempty text path")`. The spec stores the path **as given**; `spec.path` is that string. The registry resolves it against the current working directory **at attach time** (absolute, with symlinks in the parent chain resolved). Whether the mount is a file or a directory follows from the **celltype**, not from a flag or from the path.

### `status`

`ctx.a.mount.status` is `None` on an unmounted cell; otherwise a dict whose keys are contract:

| Key | Value |
|---|---|
| `state` | `"active"`, `"tripped"` (the detector has fired) or `"closing"` |
| `node_checksum` | the node's checksum hex if the node is `complete`, else `None` |
| `disk_checksum` | the believed file checksum: a 64-hex string, or one of the two sentinel strings `"ABSENT"` and `"INVALID"` (`attachments.policy.ABSENT` / `.INVALID`) |
| `in_sync` | `node_checksum` is not `None`, equals `disk_checksum` (a null node value with an absent file also counts), and there is no sense error |
| `pending` | a delivery is queued but not dispatched |
| `in_flight` | a delivery has been dispatched and not yet acknowledged |
| `sense_error` | the `MountError` currently failing the cell, or `None` |
| `error` | the `MountError` / `ConflictError` on the mount, or `None` |

`sense_error` and `error` are **`Exception` objects**, while `Cell.exception` is a string; see `contracts/attachments.md`, *Error typing*.

### Errors

| Error | Raised when |
|---|---|
| `ValueError` | a bad `path`, `mode` or `authority`; an illegal `file-strict` combination; a cell that is already mounted; a path that overlaps another registration in this process |
| `TypeError` | `persistent` is not a `bool`; the celltype is not mountable; `deepfolder` with a mode other than `"r"` |
| `NodeError` | the node does not exist, or is not a cell |
| `AuthorityError` | a sensing mount on a node with an incoming edge; an incoming edge into a sensing-mounted node; clearing a mounted cell |
| `PathError` | **any invalid mount spec in a graph** — unknown fields, a bad mode or authority, an illegal `file-strict` combination, a non-mountable or sense-only celltype — plus a mount on a non-cell node, an unreadable graph version and a graph connection into a sensing-mounted node. **An invalid *request* raises `TypeError` / `ValueError`; the same fault inside a *graph* raises `PathError`**, and a fault the spec itself would have raised is wrapped as `"Invalid mount spec: <original message>"` |
| `ReentrantContextError` | `mount()`, `clear_error()`, unmounting or the barrier called from the controller thread |
| `TimeoutError` | `sync()` / `synchronization()` expiry; the predicate is withdrawn and nothing is cancelled |
| `KeyError` | `clear_error()` on an unmounted cell — an inconsistency, not a designed refusal |
| `MountError` | never raised; it is *reported*, on the cell (as a string) or on the mount (as an object) |

## Spec validation and normalization

`mode`, `authority` and `persistent` live on the generic `AttachmentSpec` class, but **their semantics are file semantics** and belong here.

| Field | Values | Meaning |
|---|---|---|
| `mode` | `"r"`, `"w"`, `"rw"` | which directions are active: sense, actuate, or both |
| `authority` | `"file"`, `"cell"`, `"file-strict"` | **resolves the initial conflict only.** It is *not* a continuous ownership rule: after the initial decision, every later file change is an authoritative input in a sensing mode, and every later node change is delivered in an actuating one |
| `persistent` | `bool` | whether the file survives unmounting (below) |

Validation, in the order the spec applies it:

- `mode` must be one of the three: `ValueError("mode must be r, w or rw")`;
- `authority` must be one of the three: `ValueError("invalid mount authority")`;
- `persistent` must be exactly a `bool` — a truthy value is not accepted: `TypeError("persistent must be bool")`;
- `"file-strict"` requires a sensing mode **and** `persistent=True`: `ValueError("file-strict requires sensing and persistent=True")`. `file-strict` means *the file is required*; a missing path is a sense error rather than a silently absent value, and deleting the file at unmount would contradict the declaration;
- **`mode="w"` with `authority="file"` is silently normalized to `authority="cell"`.** A write-only mount never reads, so there is no initial file value for the file to win with. The normalization is visible: `spec.authority` reads `"cell"`, and that is what `get_graph()` serializes.

An unmountable celltype raises at attach time and at graph load.

## Mountable celltypes

| Celltype | Mounts as | `canon_T` on read | Notes |
|---|---|---|---|
| `text`, `python`, `ipython`, `yaml` | file | strict UTF-8; the trailing newline is normalized to exactly one | no CRLF conversion — CRLF is content. **Code text is not syntax-checked**, because a user assignment of the same text is not either |
| `plain` | file | JSON parse, canonical re-serialization | JSON only. User formatting survives until the value changes |
| `str` | file | JSON parse (with the deserializer's `str()` coercion), re-serialize | the file holds a **quoted** JSON string; use `text` for raw text |
| `int`, `float`, `bool` | file | JSON parse with coercion, re-serialize | |
| `bytes` | file | identity for non-empty content; empty → null | null resolves back as `b""` |
| `binary` | file | must deserialize as a pure-binary (NumPy) value; round trip | |
| `mixed` | file | must deserialize as mixed; round trip | |
| `folder` | **directory**, `r` / `w` / `rw` | see *Directory mounts* | |
| `deepfolder` | **directory**, `r` only | see *Directory mounts* | |
| `checksum`, `deepcell`, `module` | — | — | not mountable: `TypeError("Celltype '<ct>' is not mountable")` |

### `deepfolder` is sense-only

**`folder` mounts in `r`, `w` and `rw`. `deepfolder` may only be mounted with `mode="r"`.**

The reason is what the two celltypes declare. A write mount **materializes every leaf onto disk**, which is exactly what `deepfolder` — "an index; the contents stay by reference" — says it does not do, while `folder` means "the contents of a directory" (`contracts/deep-celltypes.md`). The restriction costs one retype and nothing else: the two index buffers are **byte-identical** and the conversion between them is free in both directions. And a transformer **cannot produce a `deepfolder` at all**, so `folder` is the only celltype a computed directory can arrive in.

There are two enforcement points, and they raise different types — the general split for mounts, worth learning once:

- **An invalid *request* to `mount()` raises `TypeError`.** Because the default mode is `rw`, the bare `ctx.a.mount(path)` on a `deepfolder` cell raises too — deliberately, with a message naming both remedies:

  ```text
  TypeError: Celltype 'deepfolder' can only be sensed: mount with mode='r', or use celltype 'folder' to write
  ```

- **An invalid mount spec in a *graph* raises `PathError`**, wrapping the same text:

  ```text
  PathError: Invalid mount spec: Celltype 'deepfolder' can only be sensed: mount with mode='r', or use celltype 'folder' to write
  ```

  This refusal happens in `prepare_graph`, so it applies **with `mounts=False` as well**: the graph is malformed regardless of whether this loader would attach it. The same holds for every other invalid mount entry — unknown fields, a bad mode, a mount on a non-cell node, a sensing mount with an incoming connection.

`validate_celltype(celltype, mode)` is the single enforcement point, called from `_mount_validate`, from `load_graph` and from `prepare_graph`. Its `mode` parameter is **required**, deliberately, so that no caller can skip the rule.

## The initial decision table

At attach time the controller evaluates one decision against the node's value **in that turn** and the initial observation. Inputs are the effective mode and authority, the file state, and whether the node has a **complete value**. *F* and *N* are compared as **canonical checksums**.

**"No value" means the node has no checksum**, and is distinct from a null value. On the file side, an **absent path, a zero-byte file and an initially empty directory all additionally report "no value"**, which is what makes them unable to override an existing cell value; an explicit `null\n` file does not, and can.

**In both tables the rows are ordered, and the first matching row wins** — that is how the policy function is written.

**The node has no complete value:**

| # | mode | authority | file | action |
|---|---|---|---|---|
| 1 | `w` | any | any | nothing now; write when the node completes |
| 2 | `r`, `rw` | any | rejected | sense error |
| 3 | `r`, `rw` | `file-strict` | absent | node ← null, **and** a sense error (the null is stored but masked) |
| 4 | `r`, `rw` | `file`, `cell` | absent | node ← null |
| 5 | `r`, `rw` | any | zero-byte / empty directory | node ← null |
| 6 | `r`, `rw` | any | *F* | node ← *F* |

**The node has a complete value *N*:**

| # | mode | authority | file | action |
|---|---|---|---|---|
| 1 | `r`, `rw` | `file-strict` | absent | sense error; *N* is kept |
| 2 | any | any | absent / zero-byte / empty directory, and *N* is null | nothing |
| 3 | `w`, `rw` | any | absent / zero-byte / empty directory | write *N* |
| 4 | `r` | any | absent / zero-byte / empty directory | nothing |
| 5 | `w` | (`cell`) | *F* = *N* | nothing |
| 6 | `w` | (`cell`) | *F* ≠ *N*, or rejected | write *N* |
| 7 | `rw` | `cell` | *F* ≠ *N*, or rejected | write *N*; logged once |
| 8 | `r`, `rw` | `cell` | otherwise | nothing; *F* becomes the baseline, and later file changes flow in |
| 9 | `r`, `rw` | `file`, `file-strict` | rejected | sense error |
| 10 | `r`, `rw` | `file`, `file-strict` | *F* = *N* | nothing |
| 11 | `r`, `rw` | `file`, `file-strict` | *F* ≠ *N* | node ← *F*; logged once |

**Rejected files.** A file may be unreadable, or impossible to canonicalize as the celltype. Where the table would install *F* into the node, the cell gets a **sense error** instead — `failed`, with a `MountError`, monitoring active. Everywhere else a rejected file counts as **a present file that differs from *N***. Either way the session starts with the belief `INVALID`.

**Nothing in this table is a continuous rule.** It runs exactly once per session, at attach; every later observation goes through the classification below.

## Observation classification, and the one belief about the file

The session keeps **one belief about the file**: a checksum (or the sentinel `ABSENT` / `INVALID`) plus a fingerprint. It is **comparison-only** — never resolved, holding no claim on anything. Echo detection, write skipping and write preconditions all derive from it.

Every observation carries a **watch sequence**, owned by the transport and advanced under the registration's lock on every detected change **and on every completed write**.

| Class | Condition | Effect |
|---|---|---|
| `stale` | `ws <= processed_ws` | discard |
| `unchanged` | checksum equals the belief (for `ABSENT`/`INVALID`, the fingerprint too) | update the fingerprint only. Identical-content rewrites and `touch` end here |
| `rejected` | unreadable, or not canonicalizable as the celltype | belief := `INVALID`; modes with `r`: sense error; `w`: reassert |
| `absent` | the file is missing | the node is left unchanged; `file-strict`: sense error; otherwise any sense error is cleared; `w`: reassert |
| `echo` | checksum equals the **in-flight** delivery's checksum | our own write, seen before its acknowledgement: adopt it as the belief |
| `foreign` | anything else | modes with `r`: sense it; `w`: reassert |

Four rules make this converge:

- **Why one belief instead of a list of what we last wrote.** Consider: we deliver *C1*; a foreign writer replaces it with *C2*, which is sensed; the writer then reverts to *C1*. A last-written list would discard that final *C1* as our own echo and leave the node at *C2* while the file holds *C1*. Against the belief — which is *C2* by then — it is correctly classified `foreign`.
- **A stale observation is discarded, and that loses nothing.** It is either a duplicate, or content read *before* one of our own writes landed, even if it reached ingress after that write's acknowledgement. If the discarded read happened to see a newer foreign change, the broker detects that change again, because **its baseline moves only with its own polls and with completed writes** — a read never moves it.
- **A write advances the watch sequence.** An acknowledgement carries the sequence the write itself produced, so any observation whose content predates the write carries a smaller sequence and is discarded as stale, however late it arrives. Without this, a read taken just before our write could be accepted just after its acknowledgement and revert the node.
- **An `unchanged` observation can still clear a sense error.** If a sense error is set and the observation carries a real checksum — rather than `ABSENT` or `INVALID` — the value is re-installed and the error is cleared. This is the defensive case that lets a forced re-poll recover a cell whose file has not changed since.

A `foreign` observation in a sensing mode installs the checksum, sets the belief and the actuation baseline in the same turn — so the value is not written straight back — and clears the sense error. A zero-byte file maps to null; an emptied directory maps to `{}`.

## Canonical bytes

For each mountable celltype *T* the mount uses exactly two functions, both defined by the **existing serializer and deserializer**:

- **write:** the canonical buffer of the node's checksum, byte for byte (compressed, if the path carries a compression suffix);
- **read:** `canon_T(bytes) = serialize(deserialize(bytes, T), T)`, and the observed checksum is the checksum of `canon_T(bytes)`. If deserialization raises, the observation is `rejected`.

Four consequences:

- a file written by the mount **reads back as an exact echo**;
- a user-formatted file maps to **the checksum of its value**, so reformatting JSON by hand is not a change;
- there is **no mount-local parsing**: a mount parses neither more leniently nor more strictly than a user assignment of the same value — which is why **code text is not syntax-checked**;
- **non-canonical bytes are never rewritten.** User formatting survives until the node's value actually changes. `canon_T` is idempotent, and that is property-tested.

*T* is always the cell's **output `celltype`**, including for a connected cell; the producer's input type is stored separately (`contracts/cells.md`). Retyping while mounted is refused.

### Null files

- **A missing path is `absent`**, never null. At mount time it cannot override an existing value; under `file-strict` it is a sense error.
- **A zero-byte file and `b"null\n"` both read as null**, before celltype-specific parsing. The difference is at mount time only: the zero-byte file reports "no value" and cannot override, the explicit `null\n` can. A newline-only file is not special and undergoes normal parsing.
- **A null delivery truncates an existing file to zero bytes** — also for compressed paths, where it writes zero bytes and not a compressed empty stream — **and never creates a missing file**: a null delivery whose belief is `ABSENT` is suppressed at dispatch. A null value with an absent file therefore counts as **in sync**.
- **`bytes` null reads as `b""`.** `bytes` is the one celltype where empty *is* null, in both directions (`contracts/cells.md`).

### Compression

A `.gz` or `.zst` suffix means: decompress before `canon_T` on read, and compress the canonical bytes on write — **deterministically** (gzip with `mtime=0` at level 6; zstd at level 3).

**The canonical checksum is always taken over the decompressed bytes**, as everywhere else in Seamless (`contracts/compression.md`). Compressed bytes are not stable across compressor versions and settings, so every comparison that decides an action is a canonical-checksum comparison; fingerprints only decide whether a read is worth doing. A foreign recompression of identical content therefore classifies as `unchanged`.

## Fingerprints, polling and the racy window

- **Fingerprint:** existence plus `(st_dev, st_ino, st_size, st_mtime_ns, st_ctime_ns)`. The **inode** makes atomic replacement visible even when size and mtime match. The **ctime** makes permission and ownership changes visible, so a file that was unreadable is read again once it is fixed. A directory's fingerprint is the root stat plus the sorted `(relative path, stat)` list of every non-temporary leaf.
- **One broker thread** polls every registration's `stat` at the poll interval.
- **Racy files.** A file whose mtime is within the racy window of the present moment — for a directory, any leaf's mtime — is **re-read at the next poll even when its fingerprint is unchanged**, until it ages out. Otherwise a same-size rewrite within one mtime tick would be invisible. This is the fix git applies to "racily clean" index entries.
- **Stable read:** stat, read, stat; retried with bounded backoff if the two fingerprints differ, and rejected as `OSError("File changed throughout stable read")` after five attempts. An editor that saves by atomic rename never exposes a half-written file; one that truncates and rewrites in place may, briefly, and that shows as a short-lived sense error.
- **Shared reads.** Equal `r`-only registrations of the same path **and celltype** share one poll and one read; each session gets its own claim on the resulting buffer.
- **Native hints are optional and advisory.** `SEAMLESS_MOUNT_NATIVE=1`, set before the first mount, adds Linux inotify watches — on the **parent directories**, so that editor-style target replacement does not invalidate a watch. They only mark registrations dirty. **Polling remains the correctness fallback**, and still owns watch sequences and stable reads. Unsupported platforms, failed watches and a queue overflow fall back to polling silently.

## Conditional atomic writes and conflicts

1. write to a temporary file in the target's directory, named `.<name>.seamless-<random>.tmp`, created exclusively;
2. copy the existing target's mode bits onto it when the target exists, so permissions survive replacement; otherwise the umask default applies;
3. **re-stat the target and compare it with the delivery's expected fingerprint** — the belief's fingerprint at dispatch;
4. `os.replace` onto the target.

On a mismatch the temporary is removed and the delivery acknowledges **`conflict`**. The controller only clears `in_flight`; the transport forces a poll, and **the observation that follows decides the outcome** — under `rw` the node takes the file's value, under `w` the Context reasserts.

**The precondition is what makes a mount converge.** Without it, a write launched before a foreign save would land over a change we have never seen, and the next read would classify our own content as an echo — silently losing the foreign edit.

The residual race — between the re-stat and the rename — remains. It is microseconds wide and is accepted, because there is no portable filesystem compare-and-swap.

Three further properties of the write path:

- **No `fsync` by default.** Mounts serve live editing, not durability.
- **Replacing a hardlinked target breaks the link**, so other names keep the old content. This is documented, not prevented.
- Temporary names are ignored by the broker, by directory scans and by directory cleanup, and a failed write removes its temporary file and leaves the target untouched.

## Reassert, and the detector's thresholds

A `foreign`, `rejected` or `absent` observation in mode **`w`** on a **`complete`** node means someone else changed an output this Context owns. The controller requests a delivery of *N* even though *N* is already the actuation baseline, records a timestamp and runs the detector. If the node is not complete, nothing happens until it is.

**Threshold: three reasserts within a rolling 20-second window** (a current default, not contract — see *Limits*).

**The window is the whole point.** A human editing and reverting over hours produces the same signature with no conflict; a machine fight runs at the poll rate and crosses the threshold in under a second. Counting reasserts without a window would fire on the first; a window without a threshold would fire on any ordinary editing session.

The trip mechanism — the latched `ConflictError`, actuation stopping, the registration staying, `clear_error()` as the only recovery — is in `contracts/attachments.md`. The error message names the path and the two alternating checksums.

### Two writers

- **Within one process, two writers are prevented**: the registry refuses incompatible overlaps, and a sensing mount refuses incoming edges.
- **Across processes, they are detected, not prevented.** Conditional writes stop us overwriting a change we have not seen; they do not stop two processes taking turns. Two notebooks, or two runs of one script, over one file is a *common* accident, and without a detector it becomes an endless fight at the poll rate.
- **Scope, stated as a warning rather than a promise.** The detector finds **oscillation**. It does **not** fire on two `rw` mounts over *independent* nodes in two processes. Those converge silently on the last writer, coupling the two workflows through the filesystem so that one's results depend on whether the other happened to be running. **Nothing here can detect that across processes.**

## Directory mounts

The node's value is the **deep-folder index** — `{relative path: leaf checksum hex}`, serialized as `plain` — and the session tracks only its top-level checksum. Index shape, member typing and the free `folder` ↔ `deepfolder` conversion are `contracts/deep-celltypes.md`.

**Read.** Walk the tree, ignoring temporary names. For each file, strip a compression suffix from the *name* and decompress the content, then hash the **raw bytes** — leaves are bytes, so no text decoding happens and no `canon_T` applies to a leaf. Build the index, serialize it, hash it, and emit one observation whose buffer is the index. Two leaves whose names collide after suffix stripping are rejected.

**Symlinks.** A **symlink leaf is rejected** (`ValueError("Directory mounts do not follow leaf symlinks")`), and **symlinked subdirectories are not traversed**. A delivery path that would escape the mount through a symlink is refused.

**Write.** Each changed leaf is replaced **atomically and individually**, then extraneous files are removed where cleanup applies. **The tree as a whole is not replaced atomically** — only each leaf is. A leaf whose content already matches is skipped; a leaf that changed under us fails the whole delivery, which is then retried. The acknowledgement comes after the whole tree is written, and the registration serializes its own I/O, so a half-written tree is never sensed. Compressed physical names are preserved: a leaf previously stored as `a.gz` is rewritten as `a.gz`, and index keys with an unsafe shape — absolute, empty, `.` or `..` components — are refused.

**Cleanup applies only when `mode == "w"` or `authority == "cell"`.** Otherwise extraneous files are left in place. Empty subdirectories are then pruned.

**Empty directories.** An **initially empty** directory supplies **no value** (and so cannot override an existing cell value), while a directory **emptied after mounting** reads as the empty index `{}`.

**Leaf retention** — leaves that a mount *sensed* stay resolvable while the node holds that index, including after unmounting; a *computed* directory gets no such claims — is in `contracts/attachments.md`.

### Null on a directory mount is terminal

A `w`/`rw` directory cell holding **null**: **the delivery is suppressed, the tree is left in place, and the mount reports `in_sync: False` permanently — with no error, because nothing failed.**

Contrast files, which always converge: a null value truncates the file to zero bytes, and a null value with an absent file counts as in sync. There is no equivalent for a directory. "Delete the tree" is not it — removing a value is an explicit graph operation, and a mount never deletes content it did not put there.

**The sharp edge, stated explicitly: the only signal is `in_sync: False` with an empty `ctx.mounts.errors`, so a "sync until `in_sync`" loop never terminates.** The exits are assigning a non-null value, or unmounting. Given that `deepfolder` is sense-only, this case can only arise for `folder`.

## `sync()`: spelling and the report

```python
report = ctx.mounts.sync(timeout=None)
report = await ctx.mounts.synchronization(timeout=None)
```

The semantics, the round structure and the *settled through the final cut* guarantee are in `contracts/attachments.md`. What is file-specific is the spelling and the report.

**`SyncReport` is a `dict` subclass keyed by node path** (a tuple, as everywhere in the Context), whose values are detached copies of the `status` dict above, plus two properties:

| Member | Value |
|---|---|
| `report[node_path]` | that mount's `status` dict at the moment the cut resolved |
| `report.errors` | `{node path: error or sense_error}` for every entry that has one |
| `report.in_sync` | `True` when **every** entry has `in_sync` true and no `error` |

`ctx.mounts.errors` is the same mapping as `report.errors`, computed on demand **without** a cut — a cheap status read, not a barrier.

A Context with no mounts returns an empty report immediately.

**`ctx.compute()` never waits for files.** A script that computes and then reads a mounted output from outside the process must call `ctx.mounts.sync()` as well; graph quiescence says nothing about the filesystem.

## Unmount, persistence and close

Unmounting, and what it clears, is in `contracts/attachments.md`. File-specific:

- **The unmount call waits for the transport's cleanup**, bounded by the delivery timeout, so a `persistent=False` deletion has happened by the time `del ctx.a.mount` returns.
- **`persistent=False` deletes conditionally.** The file — or, for a directory mount, the whole tree — is deleted at unmount, at node deletion and at close, **only if its fingerprint still equals the belief's fingerprint**, and only if no other live registration names the path. A file a foreign writer has changed since is **left alone**, and that is logged. Seamless never deletes content based on a path alone.
- **A `set_graph` swap keeps the file.** Graph replacement detaches every session with deletion disabled, so a non-persistent file survives a reload whether or not the new graph re-attaches the same path.
- **The close flush is file-shaped only in its bound**: `close(timeout=60)` covers the flush and the conditional deletes together.
- **`seamless.close()` closes the Contexts first, each flushing, and then the filesystem service**, which stops the broker, unregisters everything that is left (running the conditional deletes) and drains the I/O pool. Service threads are daemon threads, so an abandoned interpreter can still exit. The service itself starts **lazily, on the first reservation**, and a `get_service()` after a close starts a fresh one.

## The path-overlap registry

- **Normalization.** Paths are made absolute with symlinks in the parent chain resolved. **If the target itself is a symlink, the registration resolves to the link's target**: writes then replace the target file and the link survives.
- **Overlap.** Two registrations overlap if their paths are equal, or if one is a directory prefix of the other.
- **Refusal.** An overlap is refused — `ValueError("Mount path overlaps existing registration: …")` — if either side **actuates** (`w` in its mode) or either side is a **non-persistent directory** (one that would delete a tree). `r`-only registrations may overlap freely.
- **The check covers every Context in the process**, not just one graph.
- **Swaps.** A `set_graph` reservation names the registrations it replaces, and the swap commits or aborts with the controller turn. A reservation that is refused leaves the existing mounts installed and active.
- **Non-guarantees.** Other processes, hardlinks, bind mounts, case-insensitive filesystems and network-filesystem aliases are **outside** the check. It is a safety net, not an exclusivity guarantee.

## Graph serialization

- **Format `0.4`.** `0.2` and `0.3` graphs still load; an unknown version raises `PathError("Unsupported workflow graph version: …")`.
- **The mount entry** is `{"path", "mode", "authority", "persistent"}` on a cell entry — the spec after normalization, without the driver. Only `driver == "file"` is serialized at all, so manual and widget sessions leave no entry.
- **Every mount entry is validated by `prepare_graph`, before `mounts` is consulted at all.** Unknown fields, a bad mode or authority, an illegal `file-strict` combination, an unmountable celltype, a `w`/`rw` `deepfolder`, a mount on a non-cell node and a connection into a sensing-mounted node are all refused as `PathError` — **including when `mounts=False`**, because a malformed spec makes the graph malformed whether or not this loader attaches it.
- **`mounts=False` strips the (valid) specs** and loads the graph as an ordinary one.
- **`mounts=True` attaches every spec exactly as `mount()` does.** All reservations and initial reads are prepared in parallel on the caller's side; **one message replaces the graph and all sessions atomically**; and the call waits for every initial acknowledgement. As with `mount()`, the state of a file never makes the load fail — it becomes a cell exception or a mount error, with that mount monitoring.
- **Loading a graph with `w`/`rw` mounts writes files.** This is the one place where loading a graph has an effect outside the process. **Graphs of unknown origin must be loaded with `mounts=False`.**
- Consequently `ctx.set_graph(graph, mounts=True)` **blocks** — through the initial reads and acknowledgements — unlike the plain form, which does not wait (`contracts/workflow-context.md`).

## Limits and platform notes

**The shape is contract:**

- a cap exists on file size, on directory file count, on total tree size and on scan duration;
- **exceeding a cap makes the observation `rejected`** — so a sensing mount fails its cell and keeps monitoring, and a `w` mount reasserts. Exceeding one during a *delivery* is an ordinary delivery error, retried;
- **the checksum, never the fingerprint, is the correctness guard.** A fingerprint only decides whether a read is worth doing. Every comparison that decides an action is a canonical-checksum comparison, so a stale or coarse fingerprint can make a mount notice a change *late*, and can never make it install the wrong value.

**The numbers are current defaults, not contract.** They are class attributes of `FileSystemService` and may change without a contract change:

| Knob | Current default |
|---|---|
| I/O workers | 4 |
| poll interval | 0.2 s |
| racy window | 2 s |
| delivery timeout | 60 s |
| maximum file size | 1 GiB, before **and** after decompression (the buffer is held in memory) |
| directory scan | 100 000 files, 10 GiB, 60 s |
| oscillation detector | 3 reasserts in 20 s |

**Network filesystems are a documented limitation.** The fingerprint plus the racy rule cover the ordinary cases, but **on an attribute-caching filesystem a change that preserves both size and `mtime_ns` may go unseen until the next change**. **There is no per-mount `rehash_interval`, and none is planned.** The correctness guard still holds — nothing wrong is installed — but the change is noticed late, or on the next event.

Other platform notes: there is no `fsync`; replacing a hardlinked target breaks the link; a symlinked target is followed and preserved, while symlinks *inside* a directory mount are refused or skipped; case-insensitive filesystems are outside the overlap check.

## Porting notes

Stated as current behaviour, with no claim about what any earlier version did:

- **`ctx.compute()` is graph-only.** Computing and then reading a mounted output externally requires `ctx.mounts.sync()`.
- **Transformer code and pins are not mountable.** Mount a cell and connect it: `ctx.code = Cell(celltype="python"); ctx.code.mount("code.py"); ctx.tf.code = ctx.code`, and `ctx.tf.pins.x = ctx.x` for a pin.
- **There are no context mounts, no automatic per-cell paths and no file-extension inference.** Every mount names its own path.
- **A directory is a `folder` (or, for sensing only, `deepfolder`) cell mounted to a directory path.** There is no `as_directory` flag.

## Implementation status and current limitations

Settled contract that the code does not yet implement, or implements differently. Where a design document and the code disagree, **the code wins**, and the disagreement is listed here.

- **`Cell.exception` is an exception object in code, not the contractual string.** A sense error is installed on the node as the `MountError` itself; see `contracts/cells.md` and `contracts/attachments.md`.
- **`clear_error()` on an unmounted cell raises a bare `KeyError`**, while `.spec`, `.status` and `.error` answer `None` and `del ctx.a.mount` is a silent no-op. An inconsistency, not a refusal.
- **A `set_graph` never deletes a non-persistent file**, which is wider than the design's promise ("not when the new graph re-attaches the same path"). Do not rely on a graph replacement to clean anything up.
- **The `ConflictError` message hardcodes "three reasserts in 20 seconds."** Retuning the detector would leave the message stale; treat the message as prose and `isinstance(..., ConflictError)` as the check.
- **The vocabulary of the code is `mount`, not `attachment`**, all the way down to `Node.mount` and the `_mount_*` handlers; `AttachmentSpec` carries file fields. See `contracts/attachments.md`, *Implementation status*, for the four places the generic layer is file-shaped.
- **Delivery retries have no timer of their own.** The broker's per-poll no-op tick causes a turn, and the post-turn pass dispatches a due retry — so on an idle Context a backoff fires within about one poll interval. See `contracts/attachments.md`.

**Superseded and stale sources.** These are wrong; do not carry them forward:

- `mount-design.md` §20.3 ("resolve it through the ordinary path, **which may recompute it**") is **superseded**: a delivery resolves and never fingertips (`contracts/attachments.md`).
- `mount-design.md` §17.3, the row "clearing an `r`/`rw` cell's value stays cleared": the code **refuses** the clear outright, with `AuthorityError("Cannot clear a mounted cell; unmount first")`. The refusal is the contract.
- `mount-design.md` §16's "naming is provisional": the names are now fixed by the code.
- `mount-implementation.md` says graph format `0.3`; the code and the workflow README say `0.4`.
- `attachments-and-mount-design.md` Part II §21 still discusses a `settled()` predicate and spells the barrier `ctx.mount.sync()` (singular). Both are dead. Where that document and `mount-design.md` differ, `mount-design.md` plus the code wins.
- **Every "legacy Seamless" claim anywhere in the design documents is unverified.** The 0.x characterization never ran, so this page carries **no** comparison with it — including in the decision table, whose "legacy" column is not reproduced here.

## Non-goals

- **Durability.** No `fsync`; a mount serves live editing.
- **Cross-process exclusivity or locking.** The registry is a within-process safety net; across processes the tools are conditional writes and the detector.
- **Rewriting a file into canonical form.** User formatting survives until the value changes; a mount does not fight the editor.
- **Recreating a file the user deleted, on its own.** Deletion leaves a sensing node unchanged; an actuating mount rewrites the file at the *next* value change, or at the next reassert in `w` mode.
- **Mounting a whole (sub)context to a directory, automatic child paths, or file-extension inference.**
- **Continuous external ownership** (`edit_policy="external-owned"`). Deferred with a condition: it must not be expressed by redefining `authority="file"`.
- **Detecting two `rw` mounts over *independent* nodes in two processes.** The detector finds oscillation, not silent coupling through the filesystem. See *Two writers*.
