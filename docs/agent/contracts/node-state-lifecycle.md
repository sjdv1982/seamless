# The node state lifecycle (Contract)

**A workflow node is always in exactly one of seven states, and every state is *derived*, never assigned.** The Context is a DAG of nodes plus a runtime that keeps it in equilibrium (`contracts/workflow-context.md`). This page is the state machine that runtime implements: what the seven states mean, how each is derived from a node's own configuration and its upstreams, how a change cascades through the downstream cone without ever producing an inconsistent intermediate result, how superseded work is speculatively retained, and how a user reclaims it.

A **node** is a Context-bound builder, such as `ctx.a` or `ctx.tf`. `Cell`, `Pin` and `Transformer` handles are *views* onto one (`contracts/workflow-context.md`, `contracts/cells.md`, `contracts/pins.md`, `contracts/transformers.md`). State is a property of the node, not of the handle, so **two handles onto one named node always report the same state**. **Anonymous and projection handles are exempt.** Their `.state` is passive and local to the handle (`contracts/cells.md`, *Anonymous and projection handles*), and the state the Context derives for the underlying anonymous node is invisible through the API.

This page owns the state vocabulary, the derivation rules, block reasons and their precedence, the shape of `block_reason`, the cascade and its glitch-freedom invariant, the hold and supersession policy, and what `prune` reclaims. It does **not** own the Context API (`contracts/workflow-context.md`), the handle-side read and write API (`contracts/cells.md`, `contracts/pins.md`), what softcancel means (`contracts/cancellation.md`), or Expression-level cancellation and materialization (`contracts/expressions.md`).

Code locations:

| Concern | Module / symbol |
|---|---|
| The state vocabulary and node record | `seamless_workflow.graph` (`NodeState`, `BlockReason`, `Node.state`, `Node.block_reason`, `Node.block_pins`, `Node.pin_states`, `Node.exception`) |
| Derivation pass and cell derivation | `seamless_workflow.context.Context` (`_derive_graph`, `_derive_node`, `_derive_cell`, `_apply_pending`, `_apply_upstream_state`, `_source_state`, `_demand`, `_clear_exception`) |
| Transformer derivation and dispatch | `seamless_workflow.reactive.Reactive` (`_derive_transformer`, `_publish_run`, `_suspend`, `_expire_run`) |
| Supersession, holds and the run ledger | `seamless_workflow.scheduler` (`Scheduler`, `ContextRuntime.supersede`, `ContextRuntime.prune`, `RunRecord`) |
| Handle-side reporting | `seamless_workflow.builder_state` (`BoundCellBackend.state` / `.block_reason`, `BoundTransformerBackend.state` / `.block_reason` / `.clear_exception`, `BoundPinBackend.state` reading `Node.pin_states`) |
| Barriers over states | `seamless_workflow.runtime_api.RuntimeAPI._check_barriers` |

## The seven states

| state | meaning |
|---|---|
| `unwired` | not yet sufficiently connected |
| `miswired` | connected, but an incoming link is statically ill-formed (below); no work is attempted |
| `blocked` | sufficiently connected, but some upstream is unwired, miswired, blocked or failed; **not itself errored** |
| `waiting` | the node's inputs are not all concrete checksums yet, or a cell node's own work is in flight |
| `computing` | the node's inputs are concrete and its own work has been **submitted**: queued behind backend concurrency, or already running |
| `complete` | a result checksum is available |
| `failed` | this node's **own** evaluation failed |

`NodeState` is a `Literal` type alias over these seven strings, not an `enum.Enum`: compare against the string.

### `miswired` is a static defect, not a failure

A node is `miswired` when an incoming link is statically ill-formed. There are two criteria, depending on the source:

- **Ordinary sources: a path and a conversion on one link.** The edge projects into its source *and* the source's celltype differs from the target's `celltype` (the wiring rule, `contracts/cells.md`, *Connecting*). **A symbol whose entry carries a path counts as a path-carrying source**, so routing a projection through an anonymous node does not escape the rule.
- **Deep sources: the deep table.** When the source is `deepcell`, `deepfolder` or `folder`, the criterion is the table of legal deep links in `contracts/deep-celltypes.md`. A link outside that table is ill-formed in the same way, and the outcome is the same. The carve-out covers only the link whose source is deep; everything downstream of the resulting child checksum is ordinary wiring again.

No work is attempted, so there is no exception. The node carries a repair description naming the edge, the two celltypes and the two disambiguating spellings; that message text is contract and is specified in `contracts/cells.md`, *Connecting*.

**Writing an ill-formed link directly raises.** An invalid request raises. Only a *valid* request that invalidates someone else's wiring leaves a node `miswired`: retyping a source that has projecting consumers is never refused, and each affected consumer becomes `miswired`. `Context.set_graph` **derives** the state rather than rejecting the graph, so a graph can be saved and handed on mid-repair.

**Standalone consumers can be `miswired` too.** A standalone Cell `c = b[3]`, or a standalone Pin wired to `b[3]`, reports `miswired` after `b` is retyped so that the link would project and convert. Its `.checksum` is `None` (`contracts/cells.md`, `contracts/pins.md`).

### Three rules that fix the vocabulary

These are the places where a plausible reading is wrong.

**1. `waiting` versus `computing` is decided at dispatch, not by the backend.** `computing` means *submitted*, not *executing*. No backend is asked to report start-of-execution: jobserver and Dask may not surface it, and a state that depended on such a report would be unobtainable for some backends and racy for the rest. Two consequences:

- A transformer whose pins are all literals has nothing to wait for. It goes **straight to `computing` and is never observed `waiting`**; only its downstream shows `waiting`.
- A node is `computing` **from dispatch onwards, including the window in which its transformation identity is still being constructed.** There is no separate "constructing" state, and `computing` is not delayed until the identity exists (`contracts/workflow-context.md` states the same rule from the execution side).

**2. `computing` is a transformer-node state.** A cell node's own work (a conversion, a projection, a validator, a cell-level join) reports **`waiting`** while it is in flight, and a **cell node is never observed `computing`**. The standalone vocabulary agrees: a standalone Cell or Pin reports only `unwired`, `miswired`, `waiting`, `complete` and `failed` (*States as seen through barriers and handles*).

**3. Upstream failure never propagates as `failed`.** A dependent of a failed node is **`blocked`**, with block reason `blocked-by-error`. `failed` is reserved for a node's **own** evaluation, and a node's `.exception` is its own, never a borrowed copy of an upstream's. Reading a failure therefore always identifies the node that produced it; to find the cause of a `blocked` node, follow its `block_reason` upstream.

## Equilibrium, quiescence, and what they do not mean

| kind | states | leaves only via |
|---|---|---|
| equilibrium | `complete`, `failed`, `blocked`, `unwired`, `miswired` | an **external change** |
| out of equilibrium | `waiting`, `computing` | **autonomously** |

An external change perturbs; the Context relaxes. Nothing else moves a node.

- **Quiescence ⇔ no node is `waiting` or `computing`.** Within scope (a DAG of reproducible transformations), quiescence is guaranteed reachable in finite steps after a finite burst of edits.
- **Quiescence is a property of node states only.** A `complete` node may still have a **superseded run in flight**: work that is obsolete by construction and whose result nothing will consume. It does not count against quiescence. So **quiescent ≠ cluster-idle**; `prune` is what makes the two coincide (below, and `contracts/workflow-context.md`).
- **Quiescence ≠ success.** Equilibrium includes `failed`, `blocked`, `unwired` and `miswired`. Success is the strictly stronger condition that every witness or otherwise observable node is `complete`. A graph-wide barrier returning is a statement about motion, not about outcomes.

## Connectivity: when is a node sufficiently connected

**Sufficiently connected = every required pin wired, and every connected optional pin wired.** An unconnected optional pin is accepted and is simply not part of the transformation; it does not gate. The rule itself is substrate and belongs to `contracts/pins.md` (`sufficiently_connected`); the Context only consumes its verdict.

- A node reaches `computing` iff every required upstream is `complete` **and** every connected optional upstream is either `complete` or definitively in its empty case: the upstream resolves to the canonical JSON null, which **on a connected optional pin means that pin's absence** and drops it from the transformation. "Pin absent" and "pin present but null" canonicalize to the same transformation checksum; that is intended, and is the identity rule of `contracts/pins.md`.
- A connected optional pin therefore **gates exactly like a required pin.** Its only relaxation is that *resolving to null satisfies the gate* rather than failing it. An **errored** connected optional upstream **blocks** the node like any other failed upstream; it is never skipped. Optionality normalizes a successful null, never an error.
- **Admitted trade-off: connected optional pins lose laziness.** The upstream always runs, even when its null is then dropped. "Optional" means "may be absent **or** null, but if connected, always computed", which is the opposite of the intuitive reading. This is why optional pins can be difficult to use.

## How each state is derived

**Derivation happens once per controller turn, for the whole graph, in one synchronous non-yielding pass in topological order** (sources before consumers). Every state below is the outcome of that pass. **No state is ever set from a background thread**: a result arriving from execution enters as a continuation on the controller and is applied by the *next* pass, exactly like an edit (`contracts/workflow-context.md`).

Topological order is what makes the derived states mutually consistent within one turn: a consumer is always derived against upstream states that were already derived in the same pass, never against a half-updated picture.

### Transformer nodes

**A compiled Stage 1 failure comes first.** If a compiled transformer fails its static, data-independent Stage 1 checks (`contracts/compiled-pins.md`, section 5), that is the transformer's **own** failure, whatever its inputs: the node is **`failed`**, `block_reason` is `None`, and the Stage 1 diagnostic is its `.exception`. No pin is resolved and no transformation is built.

Otherwise, each input is classified. The inputs are the code, which counts as a **pseudo-pin named `"code"`**, and every declared pin, taken **in name order**:

1. **Locally missing.** An input with no edge and no stored value, and not declared optional, makes the node **`unwired`**. The input's entry is `unwired`.
2. **Locally miswired.** An input whose incoming link is ill-formed (*`miswired` is a static defect*) makes the node **`miswired`**. The input's entry is `miswired`. This is the sister rule of step 1: a node that is not correctly connected is never described in terms of its upstreams.
3. **The pin's own failure.** A pin can fail in two ways, and they are reported differently. The dividing line is whether the pin **has a valid checksum for its celltype**:

   | The pin | Transformer state | The pin's entry | `tf.exception` |
   |---|---|---|---|
   | has **no valid checksum** for its celltype: a null rejected by the required-pin rule, a failed conversion from the upstream celltype to the pin celltype, or a checksum not deserializable as the pin celltype | **`blocked`** | `blocked-by-error` | **`None`** |
   | **has** a valid checksum that the transformer cannot use: for example a truly mixed value on a compiled transformer (`contracts/compiled-pins.md`, section 5) | **`failed`** | none (`block_reason` is `None`) | **set**: the diagnostic, naming the pin |

   In the first row the failure belongs to the pin: the pin's state is `failed` and its failure is readable as `pin.exception` (`contracts/pins.md`). No transformation is built, so nothing of the transformer's own has failed. In the second row the pin is fine and the failure is the transformer's own, so it is reported as one. **The state follows this rule, not where the check happens to run**: a rejection detected before hashing and one detected in the executor give the same state.
4. **An upstream that is not `complete`.** The upstream's state maps to the input's entry:

   | Upstream state | Entry contributed |
   |---|---|
   | `miswired`, or `blocked` with reason `blocked-by-miswiring` | `blocked-by-miswiring` |
   | `unwired`, or `blocked` with reason `blocked-by-unwired` | `blocked-by-unwired` |
   | `failed`, or `blocked` with reason `blocked-by-error` | `blocked-by-error` |
   | `waiting`, `computing` (still progressing) | none: the input is waiting |

5. **Dispatch.** With every input complete (or, for a connected optional pin, resolved to null), the node is dispatched and becomes **`computing`**. When its run answers, it becomes `complete`, or, on its **own** failure, `failed` with the failure as its `.exception`.

If any input has an entry, the node's state and label are the maximum entry under the precedence in *Block reasons*: `miswired` or `unwired` is the node's state, and a `blocked-by-…` value makes it `blocked` with that reason. If inputs remain but none has an entry, the node is **`waiting`**.

### Cell nodes

| Situation | State |
|---|---|
| no producer and no incoming edge | **`unwired`** |
| an incoming link that is ill-formed | **`miswired`** |
| a literal producer, or an upstream that is `complete`, with no own work to do | **`complete`** |
| a conversion, projection, validator or cell-level join that must run | **`waiting`** while the job is in flight, then `complete` |
| that job fails | **`failed`**, with the error as `.exception` |
| an upstream that is not `complete` | **`blocked`** or **`waiting`**, by the same mapping as for transformers (step 4) |

- **A cell's own conversion failure is `failed`, not `blocked`.** This is the cell-level counterpart of a transformer's own failure: the work that failed was the cell's, so the exception is the cell's. Contrast the transformer *pin* case above, where a conversion into the pin celltype leaves the pin with no valid checksum, so the failure belongs to the pin and the transformer node is merely `blocked`.
- **A mount that cannot sense its file fails the cell** (`failed`) with the sense error, and `clear_exception()` on such a node **re-polls the mount** rather than re-deriving (`contracts/attachments.md`, *Sense errors fail the cell*). The stored value is kept but masked, and unmounting unmasks it.
- **A root edge and sub-path edges are mutually exclusive.** If a cell has sub-path edges, its root may hold only a checksum (a literal), never a source. So `ctx.join = ctx.base; ctx.join["k"] = ctx.other` is **refused**, and so is the reverse order; a literal root with sub-path edges is a legal join. The exception class is unspecified (deferred). `contracts/cells.md` states the same rule from the wiring side.
- **A cell-level join is plain local Python, with no Transformation and no Expression behind it.** It is assembled in-process from its root value and its connected sub-path sources, which is why it is never observed `computing`, only `waiting` then `complete`. This is **provisional**: a future re-implementation is to cache joins and evaluate them where the data is, and **no join identity is promised**. The full observable contract is `contracts/cells.md`, *Cell-level joins*; this table states only where a join sits in the state machine.

### Elided anonymous nodes

An anonymous node that is elided by fusion (`contracts/cells.md`; `contracts/expressions.md`, *Fusion*) is **excluded from state derivation and from barriers**. It has no state, is never `waiting`, never holds a barrier open, and contributes no entry to anyone's `block_reason`. **A node below an elided one derives from the root of the fused run**, the non-elided source whose checksum the fused Expression starts from, as though the whole fused run were one link.

## Block reasons

**The block reason is a first-class, queryable enumeration with exactly three members:**

| reason | means | the user action it implies |
|---|---|---|
| `blocked-by-unwired` | something upstream is not connected | wire something |
| `blocked-by-error` | something upstream failed, or a pin has no valid checksum | fix code or data |
| `blocked-by-miswiring` | something upstream is `miswired` | re-wire it with an explicit conversion |

The three members are those **literal strings**. `BlockReason`, like `NodeState`, is a `Literal` type alias, not an `enum.Enum`, so compare against the string and do not expect member attributes. All three are the one state `blocked`, and each needs an external change to leave it, but they imply different user actions. That is why the reason must be inspectable by UIs and tests rather than recoverable only from prose.

**Per-input entries use a five-member domain**: the three block reasons, plus the two local defects `miswired` and `unwired`. An entry of `miswired` or `unwired` names an input of *this* node that is itself miswired or missing; a `blocked-by-…` entry names an input whose upstream is stuck.

### Precedence

When several inputs have entries, the node's label is the maximum under this order (author's ruling, 2026-09-18):

```
miswired  >  unwired  >  blocked-by-miswiring  >  blocked-by-unwired  >  blocked-by-error
```

- **A local defect wins over routine incompleteness.** `unwired` is a state every node passes through while a graph is built; `miswired` is always a defect, and no amount of further wiring dissolves it. If `unwired` won, a miswired edge on a join would hide behind an unwired sibling edge until the wiring was finished, which is exactly when it should already have been visible. The same tiebreak carries over to the upstream reasons, which is why `blocked-by-miswiring` beats `blocked-by-unwired`.
- **A local defect wins outright over upstream reasons**: the node is `miswired` or `unwired`, not `blocked`. A node that is not correctly connected is never described in terms of its upstreams.
- **Among upstreams, `blocked-by-unwired` beats `blocked-by-error`.** Having all inputs wired, the correct topology, has priority over errors, which are about correct values. And an errored upstream is quite often errored *only* because something below *it* is still unwired. Report the missing wiring first, because fixing it may dissolve the error.
- **A waiting input loses to everything.** It contributes no entry at all. A node with one progressing input and one blocked input is `blocked`, not `waiting`: the progressing input will settle on its own and the blocked one will not, so the honest report is that the node is stuck. A node is `waiting` only when no input has an entry.

### Where each form is visible

`block_reason` is a **detached copy** (mutating it changes nothing) and is bound-only. Its shape is decided by **topology, not by state**, so a consumer knows which form to expect from the graph alone:

| Node | `.block_reason` when the node is `unwired`, `miswired` or `blocked` |
|---|---|
| a **transformer** | a **dict** `{input name: entry}`, keyed by pin name, with `"code"` for the code pseudo-pin |
| a **cell with one-level inputs** (a join) | a **dict** `{edge path: entry}`, keyed by the edge's one-level path |
| a **cell whose only input is at the root** (including `tf.result`) | a **single value** from the five-member domain |

- **The dict holds one entry per input that is neither `complete` nor `waiting`**, and only those. Its values are drawn from the five-member domain.
- **The label is the maximum of the entries under the precedence.** There is no separate field for "which category won". `tf.result.block_reason` is simply the ordinary single-value reading of the result cell, whose one input is the transformer; it is not a second surface for the transformer's label.
- **A node that is itself `waiting` reports `None`**, not an empty dict. So does a node that is `computing`, `complete` or `failed`: in particular, a compiled Stage 1 failure and a valid-but-unusable pin value both report `None` alongside the transformer's `.exception`.
- A root input and one-level inputs never coexist (*Cell nodes*), so the two cell forms do not overlap, and there is no key for the root.

**`.state` says whether the defect is local; the entries say where to look.** A `blocked-by-miswiring` entry means a miswiring *at or above* that input, exactly as `blocked-by-unwired` names a missing wire any distance upstream. A `miswired` or `unwired` entry means the defect is on that input itself, and the walk ends there. Otherwise, follow that input upstream.

`contracts/pins.md` states the transformer form from the pin side, and `contracts/cells.md` the cell forms from the cell side; this section is the canonical statement.

### Transitivity

**All three reasons propagate.** A consumer of an error-blocked node is itself `blocked-by-error`. A consumer of an unwired or unwired-blocked node is `blocked-by-unwired`. A consumer of a `miswired` node, or of one already `blocked-by-miswiring`, is `blocked-by-miswiring`. Where several apply, the precedence above decides. A downstream node therefore reports **why the graph is stuck**, not merely that its immediate input is not ready: a node ten edges below a missing wire still says `blocked-by-unwired`.

## Leaving a state

- **An equilibrium state is left only by an external change**: wiring or unwiring, an edit, a graph replacement, or `clear_exception()`. Nothing in the runtime retries, ages out, or re-derives an equilibrium node on its own.
- **`clear_exception()` is the external change that releases `failed`.** It is forwarded to the node's Context-private Expression or Transformation, and it:
  1. drops the recorded exception;
  2. discards the cached failure fact;
  3. **softcancels** the node's current run (`contracts/cancellation.md`);
  4. re-derives the node from its **current** inputs.

  It is a **no-op on a node with no exception**. There is **no automatic retry**: classifying a failure as transient and retrying it is a Transformation or backend concern, not Context logic (*Non-goals*).
- **A repaired failure must revoke before it recomputes.** After the edit that repairs a failure, no downstream node is left `complete` on the failed node's stale state, and **a failure never survives the edit that repairs it**. This is the cascade invariant below, applied to the `failed` state.
- **Only the failing node reports the exception.** Its dependents report `blocked` with no exception of their own.
- **`.exception` is a string**, on nodes as on standalone Cells, Pins and Transformations. A node's failure is reported identically on the node and on its result handle: `ctx.tf.exception` and `ctx.tf.result.exception` are the same failure.
- **A failure is an event, not a message.** Re-deriving after an edit produces a **new** failure even when the message is identical. Nothing may treat two equal messages as one failure, and nothing may suppress a re-raised failure because it "looks the same".

## The cascade, and glitch-freedom

A **change** is an update to a node's value, configuration or identity, or to connectivity. The cascade rule:

> On any change to a node's identity or connectivity, the node re-derives its own state. If it **leaves `complete`**, every downstream node **re-derives its own state**, landing in `waiting` *or* `blocked` per its full upstream set, **synchronously, before** the wavefront recompute is launched.

Two refinements over a blunt "all downstream become pending":

- **Re-derive, don't force-set.** A multi-input downstream may belong in `blocked`, not `waiting`, because it also depends on a failed or unwired node. Each downstream computes its own state against its **full** upstream set; the cascade tells it to recompute its state, not what state to take.
- **The trigger is "leaves `complete`"**, which is broader than "an input checksum changed". It includes:
  - **self-edits**: editing a node's code or load-bearing metadata changes its **own** transformation identity with no input change;
  - **disconnection**: removing a required pin moves a node `complete → unwired`, and its downstream to `blocked`.

### The glitch-freedom invariant

> **Invalidation dominates recomputation.** On any change, mark the whole downstream cone non-current (revoke it from `complete`) *before* launching the wavefront recompute. **Never fire a node on a stale completed input.**

The textbook diamond: with `a = 1; b = a + 1; c = a + b`, when `a → 10` the danger is `c` firing on the **new** `a` and `b`'s **stale** result, giving a transient `c = 12` that corresponds to no consistent state of the graph. The invariant forbids it. The instant `a` changes, `b` and `c` are synchronously revoked to `waiting`, so `c` cannot fire until `b` recompletes to `11`, and `c` then gives `21`. **The only visible effect of the invariant is an honest `waiting` on `c`.**

The two halves are decoupled and have very different costs:

| half | cost | timing requirement |
|---|---|---|
| **marking** the cone non-current | cheap in-process bookkeeping: state flips, no I/O | must complete in **one non-yielding pass before any descendant is evaluated for firing** |
| **building and launching** the refreshed work | real work: identity construction, submission | lazy and prioritised; **need not** be synchronous |

That ordering is the whole requirement. A node becomes eligible to fire only once **all** its inputs are current, so glitch-freedom holds regardless of when the replacement work is rebuilt.

### The negative half is contract too

**Nothing outside the cone may leave `complete`.** The cone of an edited node is its **transitive consumers**: two consumers of one root are not in each other's cones, and an input is never in its consumer's cone.

Over-invalidation **never produces a wrong answer**, which is exactly what makes it insidious. A deterministic body recomputes to the same checksum, so state comparisons and checksum comparisons see nothing, while work was thrown away and a cluster was kept busy. The contract is therefore **both** that the whole cone is revoked **and** that nodes outside it are untouched, including **not re-executed**.

### There is no exception for cache hits

**A turn that makes a node newly eligible to compute leaves it pending in that turn**; its result, or its failure, is settled by a **later** turn. No public operation returns a freshly computed result, and **a locally cached result is not allowed to install `complete` in the writing turn**.

Otherwise node state would become **history-dependent**: re-setting a pin to a previously computed value would complete in-turn, while the first setting of the same value did not. The same graph and the same write would then give different observable state depending on what the process had computed earlier.

When a recompute yields the **same** checksum (an inert edit), downstream nodes re-complete through the **ordinary content-addressed cache hit**: one turn later, not zero (`contracts/identity-and-caching.md`, and `contracts/workflow-context.md` on cache hits arriving through a controller turn).

## Speculation: launch immediately, delay cancellation

On a change, for the changed node and everything downstream, **launch of the replacement is never debounced; only cancellation of the superseded run is delayed.** Latency is never traded for the possibility that the user is still typing. What delay *does* buy is not killing running work that may still be needed: after an inconsequential upstream edit, a reverted edit, or an oscillation.

The organising fact is content-addressing: **a node's transformation identity is a hash of its own code and its upstreams' *output* checksums.** Two consequences drive the whole policy:

- a node's running work survives an upstream edit **iff the upstream's output is unchanged**, even though the upstream's *code* changed;
- editing a node's **own** code always changes its own identity, so its own running work is reusable **only on a literal revert**.

That splits the holds into three cases.

### (a) Upstream-confirmation hold: event-driven, and the load-bearing case

Node `B` is `computing`, possibly nearly finished, when a changed upstream `A` starts recomputing. `A`'s edit may be inconsequential, in which case `B`'s identity is unchanged and its in-flight run **is still the current run**.

**Hold `B`'s run until the changed upstream resolves**, then compare:

| `A` re-resolves to | action on `B`'s held run |
|---|---|
| the **same** output checksum | **reinstate** |
| a **different** output checksum | **cancel and relaunch** |

The window is **event-driven**, under a **fixed maximum of about five minutes**: if the upstream has not resolved by then, the hold is released. The ceiling keeps `B` held while a genuinely slow upstream is still resolving, and stops a *stuck* upstream from pinning a superseded run indefinitely.

### (b) Self-edit revert hold: a fixed window

A `computing` node's **own** code or load-bearing metadata is edited, so its identity changes and the old run is reusable only on a revert. No upstream event governs this case. It is a **behavioural bet on a revert**, so a **fixed human-timescale window** is the right shape, **independent of the run's runtime**. Holding a superseded two-hour run for a few seconds is worthwhile precisely because a revert within those seconds saves the whole restart.

**The window is 30 seconds** (ruled 2026-09-21, pending measurement). *Contract ahead of code:* the implemented default is 15 seconds (*Implementation status*).

**This is its own knob, independent of the Expression linger** (author's ruling 7). The linger of `contracts/expressions.md`, *Cancellation*, keeps a shared Expression evaluation alive briefly after its last requester leaves. The two answer different events, a person reverting an edit versus a requester re-arriving for the same evaluation, so they are not one shared constant, and each may be measured and moved without touching the other.

The hold is a **fixed lifetime** (hold until a deadline, then release) with **no decay curve**. Decay is the buffer cache's general memory-pressure mechanism and is not duplicated here (`contracts/cache-storage-and-limits.md`). For a very expensive run the lifetime shrinks toward zero.

### (c) Completed-downstream retention: buffer retention, event-bounded

Node `Y` is already `complete` when an upstream changes. There is **no running work to protect**, and reinstating a completed node is a pure cache hit. What is held is **`Y`'s output buffer** (and the upstream's old output), so that the hit lands if the upstream re-resolves to the same output. Its lifetime is bounded by the **same upstream event**, with the **same five-minute backstop**. Memory pressure may evict it early; that is the correct compute-versus-memory trade-off and needs no separate policy.

**(a) and (c) are the same event-driven downstream hold**, split only by whether the downstream is still `computing` or already `complete`. **(b)** keeps a fixed window because no upstream event governs it.

### Reinstatement is not a special operation

**Reinstating a held run is mechanically nothing.** The node re-derives the **same** identity and **re-latches onto the still-running submission through the ordinary membership set** (`contracts/cancellation.md`). There is no surgical resurrection, no rebinding of a saved future, and no separate reinstatement code path: **the hold merely keeps that submission alive long enough for the re-derivation to find it.**

A held run that had already produced a result or an error still delivers it as a **later fact**, through a subsequent turn, never as a cache lookup performed by the editing turn. This is the rule of *There is no exception for cache hits*.

### Nodes do not hang on to completed work

Correctness and most of the performance benefit come from the **content-addressed cache**, which is global, shared and outlives any node. Retention of **running** work is a different thing and is load-bearing, because once cancelled an in-flight run's **partial progress is gone**, and nothing in the cache can bring it back.

### Holder policy and bounds

- **A node holds at most one current run plus a small bounded set of superseded *in-flight* runs, capped at three.** The cap is on in-flight runs only: when a superseded run **completes** it leaves the cap, and its result is retained, if at all, by the ordinary buffer reference, not by the holder.
- **A superseded run evicted from that set is softcancelled, never hard-killed**, because the submission may be shared with sibling nodes, with other runs, and with other processes (`contracts/cancellation.md`). The reactive layer never issues a hard cancel (`contracts/workflow-context.md`).
- **No global budget is needed.** Only `computing` nodes have running work to supersede, and the wavefront of running work is bounded by backend concurrency, so superseded in-flight runs are bounded by **3 × backend concurrency**, independent of graph size.
- **Preemption is optional, not contract.** Reclaiming a slot from a superseded run in favour of a current run elsewhere is at most a nicety. The supported control is `prune`, because **the user knows which held run is still worth keeping** and the scheduler does not.

## `prune`: reclaiming obsolete work

The API surface is in `contracts/workflow-context.md`; this section states what it means for states and holds.

- **`ctx.prune()` softcancels every superseded or grace-held run immediately**, leaving only the current wavefront, and reports how many it cancelled. It is **lightweight and repeatable**: not a freeze, not a commit, and not a barrier.
- **`ctx.a.prune()` does the same for `ctx.a` and its downstream cone only**; `ctx.prune()` is the same call at the graph root. This is the **user's manual control** over which superseded work to reclaim; the scheduler does not guess a tighter automatic policy. Machinery to call it automatically (driven by edit rate, saturation or cost) can be layered on later and is **not part of v1**.
- **`prune` changes no node state.** It cancels obsolete work only: a `complete` node stays `complete`, and a `computing` node's *current* run is untouched.
- **After `prune`, all running work is current work**, so once the wavefront finishes the cluster is genuinely idle: **quiescence == idle**.

## States as seen through barriers and handles

The barrier API itself is in `contracts/workflow-context.md`; only what depends on states is stated here.

| Barrier | Waits until | Then |
|---|---|---|
| **node barrier**: `ctx.a.compute()` on a **named** node | the node **and its upstream cone** are out of `waiting` and `computing` | `complete`: returns the checksum. Any other state: returns **`None`**. It never raises for the state it finds |
| **run**: `ctx.a.run()` on a **named** node | as the node barrier | `failed`: **re-raises the node's recorded exception**. `unwired`, `miswired` or `blocked`: raises **`NodeError`** naming the state and what to repair (below). `complete`: returns the materialized value |
| **graph-wide barrier**: `ctx.compute()` | **no node** is `waiting` or `computing` | returns; it does **not** raise for nodes that settled into `blocked`, `unwired`, `miswired` or `failed` |

- **Barriers report outcomes; `run()` raises them** (ruled 2026-09-28). The node barrier is a statement about motion, as the graph-wide one is: it tells the caller that the cone has settled and hands back the checksum if there is one. The same rule holds for Cells, Pins, Transformers and Transformations in both modes (`contracts/cells.md`, *Failures*, *How a failure is delivered*).
- **`NodeError` belongs to `run()` on named nodes only.** Its message names the state and what to repair: for `blocked`, the block reason; for `miswired`, the miswired edge and its two celltypes; for `unwired`, the missing pin. A Pin's barrier is its owning Transformer's (`contracts/pins.md`). `compute()` on an anonymous or projection handle is **not a barrier**: it evaluates the handle's own Expression, and neither it nor the handle's `run()` ever raises `NodeError` (`contracts/workflow-context.md`, *Barriers*).
- **The graph-wide barrier is a statement about motion, not about outcomes.** Quiescence is not success; check states afterwards.
- A handle whose node no longer exists raises `StaleWorkflowHandleError`.
- **Standalone handles have a narrower vocabulary.** A standalone `Cell` or `Pin` reports only `unwired`, `miswired`, `waiting`, `complete` and `failed`, and `block_reason` is **bound-only**. `blocked` and `computing` are Context-node states, because only a Context has upstreams to be blocked by and a runtime to dispatch to (`contracts/cells.md`, `contracts/pins.md`). An anonymous or projection handle in a Context reports the same narrower vocabulary, passively (see the top of this page).

## Determinism and scope

- **Determinism is assumed.** The retain-and-compare loop of the hold policy assumes that the same inputs give the same result checksum. Irreproducible transformations are out of scope for workflows. Accidental nondeterminism being **masked** by the content-addressed cache is a universal Seamless property, not a Context hazard (`contracts/identity-and-caching.md`, `contracts/scratch-witness-audit.md`).
- **Cycles are out of scope**, not merely unimplemented: the cascade assumes a DAG, and `contracts/workflow-context.md` rejects a cycle-closing edge at declaration time.
- **Headless advance is forward-only**, and is deferred with fire-and-forget. Only the autonomous `waiting → computing → complete` transitions could occur without a live Context. The `failed` and `blocked` branches never resolve headlessly, because leaving them needs an intervention. **The entire reactive apparatus (the cascade, the holds, supersession, invalidation) is online-only.**

## Implementation status and current limitations

Settled contract that the code does not yet implement, or implements differently. The rules above define the test oracle, including the rules marked *contract ahead of code*. Each gap below is pinned by an `xfail(strict=False)` test whose reason names the section of this page (`seamless-workflow/tests/test_contract_node_state_lifecycle.py`, `seamless-workflow/tests/test_transformer_block_reason.py`). Where a design document disagrees with a rule above, the rule above wins.

- **Miswiring does not propagate into cells.** A cell fed by a `miswired` transformer, or below a `blocked-by-miswiring` node, stays `waiting` forever, because `Context._apply_upstream_state` has no branch for either. As a result the graph never quiesces, and `ctx.compute()` and `ctx.mounts.sync()` time out. Transformers below a miswiring are derived correctly.
- **Block-reason precedence is inverted for cell nodes — and only the first incomplete edge is looked at.** `Context._apply_pending` ranks `blocked-by-error` above `blocked-by-unwired`, but in practice it only ever inspects the join's first incomplete edge, so the stated ranking rarely matters. What actually happens: a join whose first edge has errored and second edge is unwired reports `blocked-by-error` where the contract wants `blocked-by-unwired`; a join whose first edge is still computing and second edge is blocked reports `waiting` where the contract wants `blocked`. Transformer derivation follows the contract precedence and looks at every input.
- **The deep-table rule for `miswired` is not implemented for transformer pins.** A source outside the one-step deep-conversion table (for example a `folder` source feeding a `plain` pin, where `folder → plain` is not in the table) should make the transformer `miswired`. Instead the link is accepted at write time, and if the conversion later fails, the pin's own conversion failure makes the transformer `blocked`/`blocked-by-error` instead. This is the pin-side counterpart of "bound cell targets are never derived `miswired`", below.
- **A `blocked` transformer can keep a stale `.exception` from a prior failure.** If a transformer fails, and its upstream is then edited so the *upstream* itself fails, the transformer becomes `blocked`/`blocked-by-error` (correctly), but `tf.exception` still returns the old failure instead of `None`. Two causes: `Reactive._derive_transformer` clears `node.exception` only when the node becomes `unwired`, not when it becomes `blocked`; and `BoundTransformerBackend.exception` exposes the stored exception for `blocked` nodes as well as `failed` ones. This holds for ordinary, non-compiled transformers and breaks "blocked: not itself errored".
- **`block_reason` does not have the ruled shape.**
  - Waiting inputs are still listed in a transformer's dict, with the value `waiting`, and a waiting node reports a dict instead of `None`.
  - A join reports a single value, not a dict keyed by edge.
- **A root edge plus a sub-path edge is accepted**, in both orders; in the root-after-sub-path order the sub-path edge is silently dropped.
- **Bound cell targets are never derived `miswired`.** Only transformer pins are checked (`contracts/cells.md`, *Implementation status*).
- **A standalone Pin never becomes `miswired`.** After its projected source is retyped, it reports `waiting`.
- **The rule-3 split is not implemented for compiled transformers.**
  - A failed conversion into a compiled pin copies the pin's error into `tf.exception`; the contract is `None`.
  - A valid value that compiled validation rejects before hashing (for example a JSON list on a `mixed` pin) reports `blocked` with `blocked-by-error`; the contract is `failed`. The same rejection found in the executor already reports `failed`.

  For non-compiled transformers the first row of the rule is implemented: a null on a required pin or a failed conversion leaves the transformer `blocked` with `tf.exception` `None`.
- **A compiled Stage 1 failure reports `blocked` with `block_reason == {}`**, instead of `failed` with `None`. The diagnostic is already stored as `tf.exception`.
- **The node barrier raises for the outcome.** `ctx.a.compute()` on a named Cell or Transformer re-raises the recorded exception on `failed` and raises `NodeError` on `unwired`, `miswired` or `blocked`, instead of returning `None`. `run()` already raises both. This gap is pinned by plain tests, not xfails (ruled 2026-09-28; *States as seen through barriers and handles*).
- **`NodeError` does not name what to repair.** On a miswired node it reads `"Node is miswired: None"`, without the edge and its celltypes, and on an unwired transformer `"Node is unwired: None"`, without the missing pin.
- **The three hold cases are not implemented as three.** Every supersession gets the same fixed window of case (b), and that window is **15 seconds** (`Scheduler.self_edit_hold_seconds`), not 30. The event-driven upstream-confirmation hold (a) and the completed-downstream retention (c) do not exist yet, and the five-minute figure appears only as a ceiling on the expiry timer. What *is* implemented: the cap of three superseded in-flight runs, eviction by softcancel, reinstatement by re-latching, and `prune` at both scopes.

**Deferred features and cost properties.** These are not contract gaps, and no test pins them:

- **Future-wiring is not implemented; the runtime is checksum-wired only.** A node leaves `waiting` for `computing` exactly when all of its inputs are concrete checksums. A `waiting` node therefore holds no submitted continuation, and fire-and-forget is deferred (`contracts/workflow-context.md`).
- **Derivation re-derives the whole graph, topologically, on every turn**, rather than only the invalidated cone. This is a cost property, not a semantic one: the outcome is identical, and the design's cone-bounded cost is the target.

**Unspecified.** Do not depend on any answer:

- the exception class for refusing a root edge combined with sub-path edges (deferred);
- whether a null checksum on a compiled pin counts as "valid for its celltype", and so whether a compiled pin rejected for null makes the transformer `blocked` or `failed` (deferred; `contracts/compiled-pins.md`, section 5);
- whether every `.exception` string carries the exception class name (`<Class>: <message>`), as ruled for compiled pins (deferred);
- the `block_reason` of a cell with no input at all (an `unwired` cell with no producer and no edge): the rulings cover a cell with a root input or with one-level inputs, not a cell with none;
- the state an anonymous or projection handle reports when its parent is `unwired` (deferred; `contracts/cells.md`).

## Non-goals

- **A transient-failure state.** `failed` is one state, and the block-reason enumeration has exactly three members (`blocked-by-unwired`, `blocked-by-error`, `blocked-by-miswiring`). Retry classification is a Transformation or backend concern, not Context logic.
- **Mandatory preemption** of a superseded run's slot in favour of a current run elsewhere; `prune` is the supported control.
- **Epoch-stamping of the invalidation cone.** The cone is marked **eagerly**; a generation or epoch scheme was considered and rejected.
- **A "constructing" state**, and any state whose derivation depends on a backend reporting start-of-execution.
- **A single `status` string** folding `waiting` and `computing` into one "pending": removed in favour of the seven-state vocabulary plus `block_reason`.
- **Cycles**, and **automatic retry** of any kind.
