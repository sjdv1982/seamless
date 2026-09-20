# The node state lifecycle (Contract)

**A workflow node is always in exactly one of seven states, and every one of them is *derived*, never assigned.** The Context is a DAG of nodes plus a runtime that keeps it in equilibrium (`contracts/workflow-context.md`); this page is the state machine that runtime implements — what the seven states mean, how each is derived from a node's own configuration and its upstreams, how a change cascades through the downstream cone without ever producing an inconsistent intermediate result, how superseded work is speculatively retained, and how a user reclaims it.

A **node** is a Context-bound builder — `ctx.a`, `ctx.tf` — and `Cell`, `Pin` and `Transformer` handles are *views* onto one (`contracts/workflow-context.md`, `contracts/cells.md`, `contracts/pins.md`). State is a property of the node, so two handles onto one node always report the same state, and a handle carries none of it.

This page owns: the state vocabulary, the derivation rules, block reasons and their precedence, the cascade and its glitch-freedom invariant, the hold/supersession policy, and what `prune` reclaims. It does **not** own the Context API (`contracts/workflow-context.md`), the handle-side read/write API (`contracts/cells.md`, `contracts/pins.md`), what softcancel means (`contracts/cancellation.md`), or Expression-level cancellation and materialization (`contracts/expressions.md`).

Code locations:

| Concern | Module / symbol |
|---|---|
| The state vocabulary and node record | `seamless_workflow.graph` (`NodeState`, `Node.state`, `Node.block_reason`, `Node.block_pins`, `Node.pin_states`, `Node.exception`) |
| Derivation pass and cell derivation | `seamless_workflow.context.Context` (`_derive_graph`, `_derive_node`, `_derive_cell`, `_apply_pending`, `_apply_upstream_state`, `_source_state`, `_demand`, `_clear_exception`) |
| Transformer derivation and dispatch | `seamless_workflow.reactive.Reactive` (`_derive_transformer`, `_publish_run`, `_suspend`, `_expire_run`) |
| Supersession, holds and the run ledger | `seamless_workflow.scheduler` (`Scheduler`, `ContextRuntime.supersede`, `ContextRuntime.prune`, `RunRecord`) |
| Handle-side reporting | `seamless_workflow.builder_state` (`BoundCellBackend.state` / `.block_reason`, `BoundTransformerBackend.state` / `.block_reason` / `.clear_exception`, `BoundPinBackend.state` reading `Node.pin_states`) |
| Barriers over states | `seamless_workflow.runtime_api.RuntimeAPI._check_barriers` |

## The seven states

| state | meaning |
|---|---|
| `unwired` | not yet sufficiently connected |
| `miswired` | connected, but an incoming edge carries **both a path and a conversion** — statically ill-formed, no work attempted |
| `blocked` | sufficiently connected, but some upstream is unwired, blocked or failed — **not itself errored** |
| `waiting` | the node's inputs are not all concrete checksums yet |
| `computing` | the node's inputs are concrete and its own work has been **submitted** — queued behind backend concurrency, or already running |
| `complete` | a result checksum is available |
| `failed` | this node's **own** evaluation failed |

**`miswired` is a static defect, not a failure.** A node is `miswired` when an incoming edge carries **both a path and a conversion** — the edge projects into its source *and* that source's celltype differs from this node's `celltype`. No work is attempted, so there is no exception; the node carries a repair description naming the edge, the two celltypes and the two disambiguating spellings (`contracts/cells.md`). Writing such an edge **directly raises** instead: an invalid request raises, and only a *valid* request that invalidates someone else's wiring — retyping a source that has projecting consumers — leaves a node `miswired`. `Context.set_graph` **derives** the state rather than rejecting the graph, so a graph can be saved and handed on mid-repair.

Three rules fix the vocabulary. They are the places where a plausible reading is wrong.

**1. `waiting` versus `computing` is decided at dispatch, not by the backend.** `computing` means *submitted*, not *executing*. No backend is asked to report start-of-execution, because jobserver and Dask may not surface it, and a state that depended on such a report would be unobtainable for some backends and racy for the rest. Two consequences:

- A transformer whose pins are all literals has nothing to wait for, so it goes **straight to `computing` and is never observed `waiting`**. Only its downstream shows `waiting`.
- A node is `computing` **from dispatch onwards, including the window in which its transformation identity is still being constructed.** There is no separate "constructing" state, and `computing` is not delayed until the identity exists (`contracts/workflow-context.md` states the same rule from the execution side).

**2. `computing` is a transformer-node state.** A cell node's own work — a conversion, a projection, a validator, a cell-level join — reports **`waiting`** while it is in flight, and a **cell node is never observed `computing`**. This is the same vocabulary the standalone subset uses in `contracts/cells.md`, where a Cell's states are `unwired`, `waiting`, `complete` and `failed`.

**3. Upstream failure never propagates as `failed`.** A dependent of a failed node is **`blocked`**, with block reason `blocked-by-error`. `failed` is reserved for a node's **own** evaluation, and a node's `.exception` is its own, never a borrowed copy of an upstream's. Reading a failure therefore always identifies the node that produced it; to find the cause of a `blocked` node, follow the block reason upstream.

## Equilibrium, quiescence, and what they do not mean

| kind | states | leaves only via |
|---|---|---|
| equilibrium | `complete`, `failed`, `blocked`, `unwired`, `miswired` | an **external change** |
| out of equilibrium | `waiting`, `computing` | **autonomously** |

An external change perturbs; the Context relaxes. Nothing else moves a node.

- **Quiescence ⇔ no node is `waiting` or `computing`.** Within scope — a DAG of reproducible transformations — quiescence is guaranteed reachable in finite steps after a finite burst of edits.
- **Quiescence is a property of node states only.** A `complete` node may still have a **superseded run in flight** — work that is obsolete by construction and whose result nothing will consume. It does not count against quiescence. So **quiescent ≠ cluster-idle**; `prune` is what makes the two coincide (below, and `contracts/workflow-context.md`).
- **Quiescence ≠ success.** Equilibrium includes `failed`, `blocked`, `unwired` and `miswired`. Success is the strictly stronger condition that every witness or otherwise observable node is `complete`. A graph-wide barrier returning is a statement about motion, not about outcomes.

## Connectivity: when is a node sufficiently connected

**Sufficiently connected = every required pin wired, and every connected-optional pin wired.** An unconnected optional pin is accepted and is simply not part of the transformation; it does not gate. The rule itself is substrate and belongs to `contracts/pins.md` (`sufficiently_connected`); the Context only consumes its verdict.

- A node reaches `computing` iff every required upstream is `complete` **and** every connected-optional upstream is either `complete` or definitively in its empty/dropped case — the upstream resolving to the canonical JSON null, which **on a connected optional pin means that pin's absence** and drops it from the transformation. "Pin absent" and "pin present-but-null" canonicalize to the same transformation checksum; that is intended and is feature 6's identity rule (`contracts/pins.md`).
- A connected optional pin therefore **gates exactly like a required pin.** Its only relaxation is that *resolving to null satisfies the gate* rather than failing it. An **errored** connected-optional upstream **blocks** the node like any other failed upstream; it is never skipped. Optionality normalizes a successful null, never an error.
- **Admitted trade-off: connected-optional pins lose laziness.** The upstream always runs, even when its null is then dropped. "Optional" means "may be absent **or** null, but if connected, always computed" — the opposite of the intuitive reading. Optional pins can be difficult to use, and this is the reason.

## How each state is derived

**Derivation happens once per controller turn, for the whole graph, in one synchronous non-yielding pass in topological order** (sources before consumers). Every state below is the outcome of that pass. **No state is ever set from a background thread**: a result arriving from execution enters as a continuation on the controller and is applied by the *next* pass, exactly like an edit (`contracts/workflow-context.md`).

Topological order is what makes the derived states mutually consistent within one turn: a consumer is always derived against upstream states that have already been derived in the same pass, never against a half-updated picture.

### Transformer nodes

For the code input and for every declared pin, **in name order**:

1. A pin with **no edge and no stored value**, and not declared optional, is a **locally missing** input: the node's state is **`unwired`**, and the pin is named. The **code input counts as a pseudo-pin under the name `"code"`** and follows the same rule.
2. An input whose upstream node is **not `complete`** makes the node non-current. The upstream's state maps to a pending reason:

   | Upstream state | Pending reason contributed |
   |---|---|
   | `failed`, or `blocked` with reason `blocked-by-error` | `blocked-by-error` |
   | `unwired`, or `blocked` with reason `blocked-by-unwired` | `blocked-by-unwired` |
   | `waiting`, `computing` (anything still progressing) | `waiting` |

3. A pin's **own** failure — a null rejected by the required-pin rule, or a failed conversion from the upstream celltype to the pin celltype — fails **the pin**. The node is **`blocked`** with reason `blocked-by-error`, naming that pin. The pin's failure is readable on the pin handle (`contracts/pins.md`), and **the transformer's own `.exception` stays `None`**: no transformation was built, so nothing of the transformer's own failed.
4. With **no pending input**, the node is dispatched and becomes **`computing`**. When its run answers, it becomes `complete`, or — on its **own** failure — `failed`, with the failure as its `.exception`.

The winning label among several pending inputs is decided by the precedence in *Block reasons* below.

### Cell nodes

| Situation | State |
|---|---|
| no producer and no incoming edge | **`unwired`** |
| a literal producer, or an upstream that is `complete`, with no conversion to do | **`complete`** |
| a conversion, projection, validator or cell-level join that must run | **`waiting`** while the job is in flight, then `complete` |
| that job fails | **`failed`**, with the error as `.exception` |
| an upstream that is not `complete` | **`blocked`** (or `waiting`), by the same mapping as for transformers |

- **A cell's own conversion failure is `failed`, not `blocked`.** This is the cell-level counterpart of a transformer's own failure: the work that failed was the cell's, so the exception is the cell's. Contrast the transformer *pin* case above, where the conversion failure belongs to the pin and the transformer node is merely `blocked`.
- **A mount that cannot sense its file fails the cell** (`failed`) with the sense error, and `clear_exception()` on such a node **re-polls the mount** rather than re-deriving (`contracts/attachments.md`, *Sense errors fail the cell*). The stored value is kept but masked, and unmounting unmasks it.
- **A cell-level join is plain local Python — no Transformation and no Expression behind it** — assembled in-process from its root value and connected sub-path sources, which is why it is never observed `computing`, only `waiting` then `complete`. This is **provisional**: a future re-implementation is to cache joins and evaluate them where the data is, and **no join identity is promised**. The full observable contract is `contracts/cells.md`, *Cell-level joins*; this table states only where a join sits in the state machine.

## Block reasons

**The block reason is a first-class, queryable enumeration**, with exactly three members:

| reason | means | the user action it implies |
|---|---|---|
| `blocked-by-unwired` | something upstream is not connected | wire something |
| `blocked-by-error` | something upstream failed | fix code or data |
| `blocked-by-miswiring` | something upstream is `miswired` | re-wire it with an explicit conversion |

The three members are those **literal strings**; `BlockReason` (and `NodeState` above) is a `Literal` type alias, not an `enum.Enum`, so compare against the string and do not expect member attributes. All three are the one state `blocked` — each needs an external change to leave — but they imply different user actions, so the reason must be inspectable by UIs and tests rather than recoverable only from prose.

### Precedence

When several inputs are pending at once (author's ruling, 2026-09-18):

```
miswired  >  unwired  >  blocked-by-miswiring  >  blocked-by-unwired  >  blocked-by-error  >  waiting
```

- **A local defect wins over routine incompleteness.** `unwired` is a state every node passes through while a graph is built; `miswired` is always a defect, and no amount of further wiring dissolves it. If `unwired` won, a miswired edge on a join would hide behind an unwired sibling edge until the wiring was finished — exactly when it should already have been visible. The same tiebreak carries over to the upstream reasons, which is why `blocked-by-miswiring` beats `blocked-by-unwired`.
- **A *locally* missing input wins outright**: the node is `unwired`, not `blocked`. A node that is not sufficiently connected is never described in terms of its upstreams.
- **Among upstreams, `blocked-by-unwired` beats `blocked-by-error`.** The rationale: **having all inputs wired — the correct topology — has priority over errors, which are about correct values**; and an errored upstream is quite often errored *only* because something below *it* is still unwired. Report the missing wiring first, because fixing it may dissolve the error.
- **`waiting` loses to every blocking reason.** A node with one progressing input and one blocked input is `blocked`, not `waiting`: the progressing input will settle on its own, the blocked one will not, so the honest report is that the node is stuck.

### Where each form is visible

**Both forms are the same shape: a dict from input to reason.** A node with one input reports the bare enum, because there is nothing to name; a node with several — a transformer, or a cell that is a join — reports `{input: reason}`, keyed by pin name or by edge. There is no separate field for “which category won”: it is the maximum of the dict's values under the precedence below.

| Read | Reports |
|---|---|
| a bound Cell's `.block_reason` (including `tf.result`) | the **enum**, or `None` — except on a cell carrying edges **beyond the root edge**, where it is a **dict** keyed by edge, values the enum; a **detached copy** |
| a bound Transformer's `.block_reason` | a **dict** `{pin name: reason}` covering every responsible input, including `"code"`; a **detached copy** (mutating it changes nothing); `None` unless the node is `unwired`, `miswired`, `blocked` or `waiting` |

**Every responsible input appears, in every state, with its own reason.** The dict is the complete report, so there is no mode in which it is filtered to the winning category and no second surface to disagree with it — `tf.result.block_reason` is simply the ordinary cell reading of the result endpoint, not the authority on which category won. **The precedence decides the label, never the completeness of the dict.** `contracts/pins.md` states the same from the handle side.

**A join names its edges.** A cell with any one-level sub-path edge reports a **dict** in place of a bare enum: keys are the edge paths, with the literal `"<root>"` standing for the root edge — whose path string is `""` and would otherwise be an invisible key — and values the enum. Only blocking edges appear. The **shape is decided by topology, not by state**, so a consumer knows which form to expect from the graph alone, and the winning category is the maximum by the precedence above rather than a second field: unlike a transformer, a cell has no `.result` handle to carry one.

**`.state` says whether the defect is local; the dict says where to look.** A `blocked-by-miswiring` entry means a miswiring *at or above* that edge, exactly as `blocked-by-unwired` already names a missing wire any distance upstream. When the node's own state is **`miswired`** the walk terminates at the named edge; when it is `blocked`, follow that edge upstream. No fourth enum member is needed for "this edge itself".

### Transitivity

**All three reasons propagate.** A consumer of an error-blocked node is itself `blocked-by-error`; a consumer of an unwired or unwired-blocked node is `blocked-by-unwired`; a consumer of a `miswired` node — or of one already `blocked-by-miswiring` — is `blocked-by-miswiring`; where several apply, the precedence above decides. A downstream node therefore reports **why the graph is stuck**, not merely that its immediate input is not ready — a node ten edges below a missing wire still says `blocked-by-unwired`.

## Leaving a state

- **An equilibrium state is left only by an external change**: wiring or unwiring, an edit, a graph replacement, or `clear_exception()`. Nothing in the runtime retries, ages out, or re-derives an equilibrium node on its own.
- **`clear_exception()` is the external change that releases `failed`.** It is forwarded to the node's Context-private Expression/Transformation, and it:
  1. drops the recorded exception,
  2. discards the cached failure fact,
  3. **softcancels** the node's current run (`contracts/cancellation.md`),
  4. re-derives the node from its **current** inputs.

  It is a **no-op on a node with no exception**. There is **no automatic retry**: classifying a failure as transient and retrying it is a Transformation/backend concern, not Context logic (*Non-goals*).
- **A repaired failure must revoke before it recomputes.** After the edit that repairs a failure, no downstream node is left `complete` on the failed node's stale state, and **a failure never survives the edit that repairs it**. This is the cascade invariant below, applied to the `failed` state.
- **Only the failing node reports the exception.** Its dependents report `blocked` with no exception of their own.
- **A node's failure is reported identically on the node and on its result handle**: `ctx.tf.exception` and `ctx.tf.result.exception` are the same failure.
- **A failure is an event, not a string.** Re-deriving after an edit produces a **new** failure even when the message is identical; nothing may treat two equal messages as one failure, and nothing may suppress a re-raised failure because it "looks the same".

## The cascade, and glitch-freedom

A **change** is an update to a node's value, config or identity, or to connectivity. The cascade rule:

> On any change to a node's identity or connectivity, the node re-derives its own state. If it **leaves `complete`**, every downstream node **re-derives its own state** — landing in `waiting` *or* `blocked` per its full upstream set — **synchronously, before** the wavefront recompute is launched.

Two refinements over a blunt "all downstream become pending":

- **Re-derive, don't force-set.** A multi-input downstream may belong in `blocked`, not `waiting`, because it also depends on a failed or unwired node. Each downstream computes its own state against its **full** upstream set; the cascade tells it to recompute its state, not what state to take.
- **The trigger is "leaves `complete`"**, which is broader than "an input checksum changed". It includes:
  - **self-edits** — editing a node's code or load-bearing metadata changes its **own** transformation identity with no input change;
  - **disconnection** — removing a required pin moves a node `complete → unwired`, and its downstream to `blocked`.

### The glitch-freedom invariant

> **Invalidation dominates recomputation.** On any change, mark the whole downstream cone non-current — revoke it from `complete` — *before* launching the wavefront recompute. **Never fire a node on a stale-completed input.**

The textbook diamond: with `a = 1; b = a + 1; c = a + b`, when `a → 10` the danger is `c` firing on the **new** `a` and `b`'s **stale** result, giving a transient `c = 12` that corresponds to no consistent state of the graph. The invariant forbids it: the instant `a` changes, `b` and `c` are synchronously revoked to `waiting`, so `c` cannot fire until `b` recompletes to `11`, and `c` then gives `21`. **The only visible effect of the invariant is an honest `waiting` on `c`.**

The two halves are decoupled and have very different costs:

| half | cost | timing requirement |
|---|---|---|
| **marking** the cone non-current | cheap in-process bookkeeping — state flips, no I/O | must complete in **one non-yielding pass before any descendant is evaluated for firing** |
| **building and launching** the refreshed work | real work — identity construction, submission | lazy and prioritised; **need not** be synchronous |

That ordering is the whole requirement. A node becomes eligible to fire only once **all** its inputs are current, so glitch-freedom holds regardless of when the replacement work is rebuilt.

### The negative half is contract too

**Nothing outside the cone may leave `complete`.** The cone of an edited node is its **transitive consumers**: two consumers of one root are not in each other's cones, and an input is never in its consumer's cone.

Over-invalidation **never produces a wrong answer**, which is exactly what makes it insidious: a deterministic body recomputes to the same checksum, so state comparisons and checksum comparisons see nothing while work was thrown away and a cluster was kept busy. The contract is therefore **both** that the whole cone is revoked **and** that nodes outside it are untouched — including **not re-executed**.

### There is no exception for cache hits

**A turn that makes a node newly eligible to compute leaves it pending in that turn**; its result — or its failure — is settled by a **later** turn. No public operation returns a freshly computed result, and **a locally cached result is not allowed to install `complete` in the writing turn**.

The reason is that otherwise node state would become **history-dependent**: re-setting a pin to a previously computed value would complete in-turn, while the first setting of the same value did not, so the same graph and the same write would give different observable state depending on what the process had computed earlier.

When a recompute yields the **same** checksum — an inert edit — downstream nodes re-complete through the **ordinary content-addressed cache hit**: one turn later, not zero (`contracts/identity-and-caching.md`, and `contracts/workflow-context.md` on cache hits arriving through a controller turn).

## Speculation: launch immediately, delay cancellation

On a change, for the changed node and everything downstream, **launch of the replacement is never debounced; only cancellation of the superseded run is delayed.** Latency is never traded for the possibility that the user is still typing. What *is* bought by delay is the avoidance of killing running work that may still be needed — an inconsequential upstream edit, a reverted edit, an oscillation.

The organising fact is content-addressing: **a node's transformation identity is a hash of its own code and its upstreams' *output* checksums.** Two consequences drive the whole policy:

- a node's running work survives an upstream edit **iff the upstream's output is unchanged** — even though the upstream's *code* changed;
- editing a node's **own** code always changes its own identity, so its own running work is reusable **only on a literal revert**.

That splits the holds into three cases.

### (a) Upstream-confirmation hold — event-driven; the load-bearing case

Node `B` is `computing`, possibly nearly finished, when a changed upstream `A` starts recomputing. `A`'s edit may be inconsequential, in which case `B`'s identity is unchanged and its in-flight run **is still the current run**.

**Hold `B`'s run until the changed upstream resolves**, then compare:

| `A` re-resolves to | action on `B`'s held run |
|---|---|
| the **same** output checksum | **reinstate** |
| a **different** output checksum | **cancel and relaunch** |

The window is **event-driven**, under a **fixed maximum of about five minutes**: if the upstream has not resolved by then, release the hold. The ceiling keeps `B` held while a genuinely slow upstream is still resolving, and stops a *stuck* upstream from pinning a superseded run indefinitely.

### (b) Self-edit revert hold — a fixed window

A `computing` node's **own** code or load-bearing metadata is edited, so its identity changes and the old run is reusable only on a revert. No upstream event governs this case; it is a **behavioural bet on a revert**, so a **fixed human-timescale window of seconds** is the right shape, **independent of the run's runtime**. Holding a superseded two-hour run for a few seconds is worthwhile precisely because a revert within those seconds saves the whole restart.

It is a **fixed lifetime** — hold until a deadline, then release — with **no decay curve**. Decay is the buffer cache's general memory-pressure mechanism and is not duplicated here (`contracts/cache-storage-and-limits.md`). For a very expensive run the lifetime shrinks toward zero.

### (c) Completed-downstream retention — buffer retention, event-bounded

Node `Y` is already `complete` when an upstream changes. There is **no running work to protect**, and reinstating a completed node is a pure cache hit, so what is held is **`Y`'s output buffer** (and the upstream's old output), so that the hit lands if the upstream re-resolves to the same output. Its lifetime is bounded by the **same upstream event**, with the **same five-minute backstop**. Memory pressure may evict it early; that is the correct compute-versus-memory trade-off and needs no separate policy.

**(a) and (c) are the same event-driven downstream hold**, split only by whether the downstream is still `computing` or already `complete`. **(b)** keeps a fixed window because no upstream event governs it.

### Reinstatement is not a special operation

**Reinstating a held run is mechanically nothing.** The node re-derives the **same** identity and **re-latches onto the still-running submission through the ordinary membership set** (`contracts/cancellation.md`). There is no surgical resurrection, no rebinding of a saved future, and no separate reinstatement code path: **the hold merely keeps that submission alive long enough for the re-derivation to find it.**

A held run that had already produced a result or an error still delivers it as a **later fact**, through a subsequent turn — never as a cache lookup performed by the editing turn. This is the same rule as *There is no exception for cache hits* above.

### Nodes do not hang on to completed work

Correctness and most of the performance benefit come from the **content-addressed cache**, which is global, shared and outlives any node. Retention of **running** work is a different thing and is load-bearing, because once cancelled an in-flight run's **partial progress is gone** and nothing in the cache can bring it back.

### Holder policy and bounds

- **A node holds at most one current run plus a small bounded set of superseded *in-flight* runs, capped at three.** The cap is on in-flight runs only: when a superseded run **completes**, it leaves the cap, and its result is retained — if at all — by the ordinary buffer reference, not by the holder.
- **A superseded run evicted from that set is softcancelled — never hard-killed**, because the submission may be shared with sibling nodes, with other runs, and with other processes (`contracts/cancellation.md`). The reactive layer never issues a hard cancel (`contracts/workflow-context.md`).
- **No global budget is needed.** Only `computing` nodes have running work to supersede, and the wavefront of actually-running work is bounded by backend concurrency, so superseded in-flight runs are bounded by **3 × backend concurrency**, independent of graph size.
- **Preemption is optional, not contract.** Reclaiming a slot from a superseded run in favour of a current run elsewhere is at most a nicety; the supported control is `prune`, because **the user knows which held run is still worth keeping** and the scheduler does not.

## `prune`: reclaiming obsolete work

The API surface is in `contracts/workflow-context.md`; what belongs here is what it means for states and holds.

- **`ctx.prune()` softcancels every superseded or grace-held run immediately**, leaving only the current wavefront, and reports how many it cancelled. It is **lightweight and repeatable** — not a freeze, not a commit, and not a barrier.
- **`ctx.a.prune()` does the same for `ctx.a` and its downstream cone only**; `ctx.prune()` is that same call at the graph root. This is the **user's manual control** over which superseded work to reclaim; the scheduler does not guess a tighter automatic policy. Machinery to call it automatically — edit-rate, saturation or cost driven — can be layered on later and is **not part of v1**.
- **`prune` changes no node state.** It cancels obsolete work only; a `complete` node stays `complete` and a `computing` node's *current* run is untouched.
- **After `prune`, all running work is current work**, so once the wavefront finishes the cluster is genuinely idle: **quiescence == idle**.

## States as seen through barriers and handles

The barrier API itself is `contracts/workflow-context.md`; only what depends on states is stated here.

| Barrier | Waits until | Then |
|---|---|---|
| **node barrier** — `ctx.a.compute()` | the node **and its upstream cone** are out of `waiting`/`computing` | `failed` → **re-raises the node's recorded exception**; `unwired`, `miswired` or `blocked` → raises `NodeError` naming the state **and** the block reason or repair description; otherwise returns the checksum |
| **graph-wide barrier** — `ctx.compute()` | **no node** is `waiting` or `computing` | returns; it does **not** raise for nodes that settled into `blocked`, `unwired`, `miswired` or `failed` |

- **The graph-wide barrier is a statement about motion, not about outcomes.** Quiescence is not success; check states afterwards.
- A handle whose node no longer exists raises `StaleWorkflowHandleError`.
- **Standalone handles have a narrower vocabulary.** A standalone `Cell` or `Pin` reports only `unwired`, `waiting`, `complete` and `failed`, and `block_reason` is **bound-only**. `blocked` and `computing` are Context-node states, because only a Context has upstreams to be blocked by and a runtime to dispatch to (`contracts/cells.md`, `contracts/pins.md`).

## Determinism and scope

- **Determinism is assumed.** The retain-and-compare loop of the hold policy assumes that the same inputs give the same result checksum. Irreproducible transformations are out of scope for workflows, and accidental nondeterminism being **masked** by the content-addressed cache is a universal Seamless property, not a Context hazard (`contracts/identity-and-caching.md`, `contracts/scratch-witness-audit.md`).
- **Cycles are out of scope**, not merely unimplemented: the cascade assumes a DAG. (`contracts/workflow-context.md` rejects a cycle-closing edge at declaration time.)
- **Headless advance is forward-only**, and is deferred with fire-and-forget. Only the autonomous `waiting → computing → complete` transitions could occur without a live Context; the `failed` and `blocked` branches never resolve headlessly, because leaving them needs an intervention that cannot happen headless. **The entire reactive apparatus — the cascade, the holds, supersession, invalidation — is online-only.**

## Implementation status and current limitations

**This page is the contract.** These notes record where today's code diverges, so that an agent reading the code is not misled into taking the code's behaviour for the rule.

- **Block-reason precedence is inverted in the code.** Today `blocked-by-error` beats `blocked-by-unwired`, in **both** the transformer derivation and the cell derivation, and the A0 contract suite asserts that order. The contract is the precedence given above — **topology before values** — ruled 2026-09-18; the code **and that test** must change.
- **The three hold cases are not implemented as three.** Every supersession currently gets the same **fixed window — the self-edit case (b) — of 15 seconds**. The event-driven upstream-confirmation hold **(a)** and the completed-downstream retention **(c)** do not exist yet, and the five-minute figure appears only as a **ceiling on the expiry timer**. What *is* implemented: the cap of **three** superseded in-flight runs, **eviction-by-softcancel**, **reinstatement by re-latching**, and **`prune` at both scopes**.
- **Future-wiring is not implemented; the runtime is checksum-wired only.** A node leaves `waiting` for `computing` exactly when all of its inputs are **concrete checksums**. Consequently a `waiting` node holds **no submitted continuation**, and fire-and-forget is deferred (`contracts/workflow-context.md`).
- **Derivation re-derives the whole graph, topologically, on every turn**, rather than only the invalidated cone. This is a **cost** property, not a semantic one: the outcome is identical, and the design's bound-to-the-cone cost is the target.
- **`.exception` holds an exception object, not a string.** The settled convention is one string convention across Cell, Pin and Transformation; the same item is recorded in `contracts/cells.md` and `contracts/pins.md`.
- **The node-transition contract suite cannot currently run** in this working tree — it errors during buffer writing, before it asserts anything — so the divergences above were established by **reading the code**, not by a red test.

## Non-goals

- **A transient-failure state.** `failed` is one state, and the block-reason vocabulary has exactly two members. Retry classification is a Transformation/backend concern, not Context logic.
- **Mandatory preemption** of a superseded run's slot in favour of a current run elsewhere; `prune` is the supported control.
- **Epoch-stamping of the invalidation cone.** The cone is marked **eagerly**; a generation/epoch scheme was considered and rejected.
- **A "constructing" state**, and any state whose derivation depends on a backend reporting start-of-execution.
- **A single `status` string** folding `waiting` and `computing` into one "pending": removed in favour of the seven-state vocabulary plus `block_reason`.
- **Cycles**, and **automatic retry** of any kind.
