# Workflow Authorizer — Design

> **Status.** Design-level plan for a future feature. Not an implementation handoff.
>
> **Depends on** the reactive `Context` runtime (phase A4 of
> [attachments-and-mount-design.md](attachments-and-mount-design.md)) and a shareserver
> (HTTP/websocket attachment driver, not yet present). The feature is most useful on top of
> the shareserver, and this document is scoped to that use.
>
> **Terminology** follows [context-internals-design-pass3.md](context-internals-design-pass3.md)
> (node states, grace holds, `softcancel`) and
> [attachments-and-mount-design.md](attachments-and-mount-design.md) (controller, inbox classes).
>
> **Origin.** Design discussion of 2026-09-12. §10 records the rejected designs and why.

---

## 1. The requirement

Seamless web servers are **reactive and collaborative**. A shared cell is a live view of one
graph node. A browser PUT is an ordinary authoritative edit that propagates reactively, and every
connected client is notified over the websocket. There are no sessions: N browser tabs are N
co-editors of one graph. (Legacy: `seamless/workflow/shareserver.py`, marker protocol;
`sphinx/source/explained.md`, "Using Seamless as a reactive web framework".)

A typical scientific web server has two stages:

1. **Parameter validation** — fast. Live reactivity without a submit button is exactly right.
2. **Heavy computation** — long and expensive. Here live reactivity is a disadvantage:
   - every keystroke would launch compute (cancellation limits the damage, but queue slots,
     allocations and partial work are already spent);
   - a parameter set that passes validation is still not a decision: editing A before B passes
     through an intermediate combination nobody meant to run;
   - collaboration amplifies both — another user's half-finished edit spends shared resources;
   - launching a multi-hour job is a decision about cost and allocation, not a side effect of
     typing.

The intended user workflow is:

> "Stop, that's wrong. Now hold off computation and let me modify this. OK, that's better."

That is: an **unsubmit** button, live editing with validation feedback, and a **submit** button.

### 1.1 Gate execution, not propagation

The obvious pattern — submit copies the validated parameters into a separate "committed" source
cell that the heavy stage depends on — needs no new machinery, but it gates **propagation**: the
heavy stage only ever sees committed values, even when the result for the live values is already
in the cache.

The authorizer gates **execution** instead. The heavy stage stays reactive up to the point of
launching new work:

- its transformation checksum is derived as usual;
- a cache hit, or a run of that checksum already in flight, is taken immediately;
- only *launching a new run* requires authorization.

Reactivity survives wherever it costs nothing, and returning to previously computed parameters
stays instant without a submit.

## 2. Scope and assumptions

- **Web-server scope.** The only external events are **PUTs on authoritative cells** (class-3
  writes). There are no topology changes, no `clear_exception()`, and no barrier calls
  (`ctx.compute()` etc.). Topology and node configuration are static while serving.
- **Fingertipping is unaffected.** Recompute-on-buffer-absence happens below the Context and is
  not gated.
- **UI presentation is orthogonal.** Whether a page shows a stale result marked as stale, or clears
  it, is not part of this design.
- Behaviour outside web-server scope is listed in §11 but not designed.

## 3. Decisions at a glance

1. An **authorizer** is attached to one or more nodes. Its **cone** is those nodes and everything
   downstream of them.
2. An authorizer holds an **authorization record**: one checksum per **boundary edge**, or none.
   **Submit** records the current boundary checksums. **Unsubmit** clears the record.
3. **Held is derived, never stored.** An entry node is held when a boundary checksum differs from
   the authorized one. Any other node is held when any of its in-cone direct upstream nodes is
   held.
4. Held is evaluated **when a node would enter `computing`**, never at PUT time. No cone is marked
   on a PUT.
5. A held node enters **`computing-on-hold`**: it may take a cache hit or join a running
   submission, but never launches new work.
6. **Unsubmit cancels immediately**, with no grace period, using `softcancel`, not hard `cancel`.
7. **Submit authorizes a state, not a launch.** Edits after submit supersede running work exactly
   as anywhere else in the graph. Returning to the authorized state is authorized again.
8. **Last writer wins.** No generation counters or conflict protocol on submit.

## 4. Concepts

**Authorizer.** A durable specification attached to a set of nodes, with an `enabled` flag. A
disabled authorizer gates nothing.

**Cone.** The attached nodes plus all nodes downstream of them.

**Boundary edge.** A dependency edge whose source is outside the cone and whose target is inside
it. An authoritative cell *inside* the cone has no incoming edge; it counts as its own boundary
edge, and its own checksum is what is compared. A boundary edge from a sub-path of a cell
compares the checksum of that sub-path's expression result (per **[MOD-3]**, sub-path values are
E results, not stored node checksums).

**Entry node.** A node in the cone that is the target of at least one boundary edge (including an
authoritative cell inside the cone).

**Authorization record.** Per authorizer: either *none* (unsubmitted), or a map from each boundary
edge to an authorized checksum or to *pending* (§7.1).

## 5. The held predicate

For an enabled authorizer `A` and a node `N` in `A`'s cone:

```text
held_A(N) =  A has no authorization record
          or some boundary edge into N has a current checksum ≠ its authorized checksum
          or some direct upstream node U of N, inside A's cone, has held_A(U)

held(N)   =  held_A(N) for any enabled authorizer A whose cone contains N
```

- A node with no boundary edges and no in-cone upstream (for example a transformer with only
  constant pins) is held only while its authorizer is unsubmitted. Its identity cannot change
  through PUTs.
- **Overlapping or nested authorizers need no extra mechanism.** Each authorizer contributes its
  own predicate. Submitting one authorizer cannot release a node that another still holds.

### 5.1 When it is evaluated

Held is evaluated at the moment `N` would leave `waiting` for `computing`. At that moment every
upstream node of `N` is `complete` (glitch-freedom, pass3 §I.4), so every boundary checksum
upstream of `N` is concrete and the predicate is always decidable.

`held_A(U)` for the upstream nodes is evaluated **at that same moment**. It is not remembered from
when `U` completed, because a submit or unsubmit may have arrived in between. `U` may have
completed while held, through a cache hit or a join.

In a web-server-sized graph, walking upstream within the cone is cheap. The recursion never needs
a precomputed node-to-boundary-edge mapping.

### 5.2 Why it is not a flag

The predicate is a pure function of the authorization records, the current checksums and the
topology. It is idempotent: a redundant re-evaluation lands on the same answer. That is pass3's
"re-derive, don't force-set" rule applied to gating, and it fits the controller's licence for
blunt reconciliation (attachments §8).

## 6. `computing-on-hold`

A held node whose inputs are all concrete enters `computing-on-hold` instead of `computing`. It
issues a **join-only** lookup (§9) for its transformation checksum:

| outcome | effect |
|---|---|
| **hit** | the result is taken; the node completes as usual |
| **joined** | the node becomes a member of the running submission and completes when it does; it is effectively `computing`, since its result arrives without an external change |
| **absent** | the node waits, keeping interest in its cache key (attachments §13), until a submit re-evaluates it or a matching cache entry appears |

Nodes downstream of a held node are themselves held (§5), and are `waiting` until their inputs are
concrete.

There is no parking. The absent case ends its turn, and every later outcome arrives as a class-5
notification or a submit message.

## 7. Operations

The operations are controller messages. Proposed classification: **class 2** (they change what is
demanded, as node configuration does, without changing any checksum). Their order relative to PUTs
is therefore the acceptance order (attachments §5.2), which is what makes "an edit before the
submit" and "an edit after the submit" well defined.

### 7.1 Submit

1. For each boundary edge whose source is `complete`, record its current checksum.
2. For each boundary edge whose source is not `complete`, record *pending*. When that source next
   completes, its checksum is adopted into the record in that turn (last writer wins, over a window
   as long as validation takes). A source that fails leaves the entry *pending*; the entry node is
   `blocked` anyway.
3. Re-evaluate held for the nodes in `computing-on-hold` in the cone. Those no longer held launch
   through the normal path.

### 7.2 Unsubmit

1. Clear the authorization record. The whole cone is held.
2. **Immediately** `softcancel` every run in the cone: current runs **and** superseded runs still
   retained under grace holds (pass3 §I.5). This is `ctx.a.prune()` plus current runs, over the
   cone.

Two properties are load-bearing:

- **No grace period.** "Stop, that's wrong" must stop now. The speculative second chance that grace
  holds provide is deliberately given up.
- **`softcancel`, not hard `cancel`.** Hard cancel means "this run is wrong" and kills every member
  of the run, including other Contexts on a shared jobserver or daskserver (pass3 §III.5).
  Unsubmit means "this Context withdraws its authorization". A run nobody else is waiting on still
  dies immediately.

### 7.3 Enable and disable

- **Disable**: the authorizer gates nothing. Held work in its cone is re-evaluated and launches if no
  other authorizer holds it. The record is irrelevant while disabled.
- **Unsubmit on a disabled authorizer** enables it, with no record, so the whole cone is held.
- **Submit on a disabled authorizer**: not specified; see §11.

## 8. Interaction with edits, grace holds and cancellation

**Submit snapshots the shared state; authorized runs are not special.** A consequential PUT after
submit changes a boundary checksum. The entry node becomes held, and running work that depended on
the old values is superseded and `softcancel`led under the ordinary grace-hold rules, exactly as
anywhere else in the graph.

| situation | running heavy work | held |
|---|---|---|
| inconsequential edit (validation output unchanged) | reinstated (pass3 case (a)) | nothing |
| revert that arrives before validation resolves | reinstated | nothing |
| consequential edit | cancelled once validation resolves to a different output | entry and everything downstream |
| revert after validation resolved the intermediate value | already cancelled | nothing: the run **relaunches without a new submit** |

Two consequences must be documented, not discovered:

- **Relaunch on revert.** The authorizer authorizes a state, not a launch. Reverting to the
  authorized parameters relaunches a killed run from scratch. A collaborator switching back and
  forth can kill and restart the run repeatedly, but only ever with the authorized parameters.
- **Grace holds are short here.** With a fast validation stage, pass3 case (a) cancels running
  heavy work within validation latency (milliseconds) of a consequential edit, so a human-speed
  "oops, put it back" never saves the run. A human-timescale protection would belong in grace-hold
  policy (a fixed window like case (b)), not in the authorizer.

**Collaborative races.** An edit accepted before the submit is included in what is authorized,
including edits whose validation is still pending (§7.1). An edit accepted after the submit
supersedes. An edit landing just after a submit is unfortunate but inherent to shared state, and is
a UI matter. No generation counters are used.

## 9. Substrate requirement: join-only lookup

`computing-on-hold` needs **"hit or join, never execute"**. No such call exists today: every
deduplication site joins if running and **starts** otherwise, in one step. Adding a join-only
variant is minor at each site.

| site | today | join-only change |
|---|---|---|
| in-process | [`TransformationCache.run`](../seamless-transformer/seamless_transformer/transformation_cache.py#L191) checks the local cache, then the database, then [`_run_active_or_execute`](../seamless-transformer/seamless_transformer/transformation_cache.py#L282) joins-or-starts under `_active_lock` | return *absent* instead of creating the submission; thread a flag through `run()`. When remote execution is configured and nothing is active locally, fall through to the remote join-only lookup rather than answering *absent* |
| jobserver | [`_run_transformation`](../seamless-jobserver/jobserver.py#L519) looks up the entry and adds the member with no `await` in between, so it is already atomic | a request flag; answer *absent* instead of creating the task (a few lines) |
| daskserver | cross-client sharing through deterministic scheduler keys ([`submit_transformation`](../seamless-dask/seamless_dask/client.py#L1360)); [`_dask_key_exists`](../seamless-dask/seamless_dask/client.py#L113) exists | check the key, then join by submitting with the same key. Not atomic: if the run disappears in between, a new run starts. Benign for successful runs, since the worker checks the database before executing ([L1063](../seamless-dask/seamless_dask/client.py#L1063)); only a run that failed or was cancelled in that window is re-executed despite the hold |

The lookup must be atomic with membership changes where the site allows it (pass3 §III.4). Its
outcome reaches the controller as a class-5 notification.

## 10. Design history: why checksums at entry nodes

### 10.1 The holder design

The first design used **holders**:

- on a PUT, compute (downstream of the edited cell) ∩ (cones of enabled holders) and set a `held`
  flag on those nodes;
- `hold-all` (unsubmit) sets the flag on the whole cone and cancels; `unhold-all` (submit) clears
  it.

Walking through it found two defects:

1. **Overlap.** With nested cones, one holder's submit clears the flag on nodes another holder
   still holds. A per-node set of holders fixes it.
2. **Stalls.** A PUT holds the cone whether or not it changes anything. After an inconsequential
   edit or a revert, a running heavy run survives (joined), but the stages after it that had not
   started are held, so the submitted pipeline stops until someone submits again. If the run
   finishes overnight, the next stage waits for a human.

### 10.2 The rejected fix

**Hold when an output changes, not when a PUT arrives.** This fixes inconsequential edits cheaply,
but it breaks "edit a field, then click Submit". The PUT is accepted, validation starts, the submit
unholds, then validation resolves to a new output and holds the cone again. The submit is silently
undone. The holder design gets that case right, because its hold happens at PUT time, before the
unhold.

### 10.3 The reduction

In both designs, an interior node is held iff any in-cone direct upstream node is held: marking
always covers everything downstream, and submit and unsubmit always cover the whole cone. The two
designs differ **only** in the predicate at entry nodes:

| entry predicate | holder | authorizer |
|---|---|---|
| held iff | a PUT reached this edge's upstream since the last submit | this edge's checksum ≠ its authorized checksum |

It is a dirty bit versus a content comparison: mtime versus checksum, the trade-off Seamless
resolves in favour of checksums elsewhere (attachments §20.2). The recursion also removes the need
for any node-to-boundary-edge mapping.

### 10.4 What the checksum predicate buys

- **Inconsequential edits** hold nothing. This requires the authorizer to sit on the heavy stage,
  not on the parameter cells: an authoritative cell inside the cone is compared by its own
  checksum.
- **Reverts** hold nothing.
- **Self-validating persistence.** A saved checksum can be checked against reloaded values; a saved
  dirty bit cannot.
- **An authorization has content**: which inputs were approved. That enables an audit trail, a unit
  for quota accounting, and a "validated parameters differ from submitted ones" view with a diff.
- **Optional "submit what I saw"** (§11).

Not attributable to the checksum predicate: per-node precision (the holder's intersection already
has it), handling of an edit just before submit (both designs handle it), overlap handling and
order-independence for interior nodes (these come from the recursion, which a holder could also
use).

## 11. Open details

1. **Persistence.** Is the authorization record stored in the graph? If yes, a server restart
   resumes submitted pipelines, including heavy compute, without anyone asking. If no, every
   restart needs a fresh submit. The authorizer specification (attached nodes, `enabled`) is
   durable either way; see the spec/session split in attachments §16.1.
2. **Submit on a disabled authorizer.** No effect, or enable with the current state authorized?
3. **"Submit what I saw".** The shareserver pushes checksums of shared cells to clients. If the
   validated values are shared, the client can send the checksums it displayed, and the server
   authorizes exactly those. An unseen collaborator edit then cannot be launched in the submitter's
   name, and a third party could approve a parameter set before it becomes current. This reverses
   the decision that an edit accepted just before a submit is included, so it is a choice, not a
   free improvement.
4. **Shareserver API surface.** How authorizers, submit and unsubmit are exposed: dedicated
   endpoints, or shared control cells.
5. **Naming of `computing-on-hold`,** and how it maps onto pass3's six node states (a seventh
   state, or a status of `computing`).
6. **Outside web-server scope** (not designed):
   - topology changes, which add or remove boundary edges and so require remapping the
     authorization record;
   - `clear_exception()` and configuration edits inside a cone;
   - quiescence barriers: a node in `computing-on-hold` with an absent lookup would have to count
     as equilibrium, or `ctx.compute()` hangs by construction.
