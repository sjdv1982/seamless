# The A1→A4 retarget of the `computing` assertions — the case against

**For:** Codex, implementing §15 of `attachments-and-mount-design.md`
**About:** the six `@pytest.mark.a1` → `@pytest.mark.a4` changes in
`seamless-workflow/tests/`, justified as *"the three submission-state assertions
were labelled A1 but require an actual running submission; retargeted to A4
rather than reporting fictitious computation during limbo."*
**Measured against:** the working tree as of the A3 claim.

---

## 0. Summary

The premise is half right and the remedy misses the cause.

There **is** an actual running submission — you built one, and it works. What
does not exist is a *state that reports it*, because `computing` is published
only after the transformation identity round-trips back from the side loop, not
when the work is dispatched. That is a two-line semantic choice, not a
consequence of limbo, and it is the choice §24.5 explicitly warns must not be
made by accident.

Retargeting also does not make the tests pass at A4. The measurement below shows
their actual blocker is something else entirely: **`.value` is a blocking read**
that waits for the computation. That fails an `a1` test which is *not* part of
the retarget, and it will keep failing at A4, so the marker change defers a red
test rather than classifying it.

Three requests, in priority order:

1. publish `computing` at **dispatch**, not at identity-arrival (2 lines);
2. treat blocking `.value` as the real defect — it is a §7/class-4 violation, and
   it is what actually breaks these tests;
3. revert the six markers; if a test is still racy after (1) and (2), **split**
   it rather than move it whole.

---

## 1. What I measured

All numbers from the working tree, `conda activate seamless1`, from one run of
each reproducer in the appendix.

### 1.1 The submission is real, and setting the last pin no longer blocks

```
set last pin returned in 0.002s, state=waiting
```

A 3-second body, and the public call returns in 2 ms. Compare §15 A0's baseline:
*"setting the last pin blocks the caller 2.0 s and returns `complete`"*. **This
is A1's headline defect, fixed and measurable.** `_derive_transformer` creates a
`RunRecord`, appends an effect, and the effect submits `execute()` to the side
loop; completion returns as a class-5 `_transformation_finished`. That is a
submission by any reading — leases held, work queued, notification wired.

So *"require an actual running submission"* is not the obstacle. The submission
is there.

### 1.2 `computing` is never observable

```
immediately after last pin : {'tf': 'waiting'}
after 0.05s                : {'tf': 'complete'}
distinct states observed   : ['waiting', 'complete']
```

An eligible transformer goes `waiting` → `complete`. `computing` is never seen,
for any duration, even though the work genuinely ran asynchronously on the side
loop. Not a limbo artifact — this is the A3 tree with the reactive continuation
in place.

The cause is one expression in `reactive.py`:

```python
node.state, ... = ('computing' if record.identity_checksum is not None else 'waiting'), ...
```

plus the sibling line at record creation, which also writes `'waiting'`.
`identity_checksum` is set by `_transformation_started`, which only fires after
`await tf.construction()` completes on the side loop *and* the resulting class-5
message is processed. So the entire dispatch window — from "we submitted this" to
"the backend told us its identity" — is reported as `waiting`.

### 1.3 `.value` is a blocking read

```
set last pin returned in 0.002s, state=waiting
.checksum read in 0.004s -> None
.value    read in 3.032s -> 42  state=complete
```

`.checksum` is a snapshot and returns immediately. `.value` waits 3.03 s — the
whole body — and returns the result. This is the finding that reframes the
marker question, and §2.3 below is about it.

---

## 2. The argument

### 2.1 `computing` is not fictitious; it is unpublished

§26.2 pins reading **(a)**: *"`waiting` means the node's inputs are not all
concrete checksums; `computing` means they are and the work has been submitted,
queued or running."*

At the moment `_derive_transformer` creates the `RunRecord`, both halves hold:
every pin resolved to a concrete checksum (the function returns early otherwise),
and the work is being submitted in the same turn. Reporting `computing` there
states two facts that are true. Reporting `waiting` states one that is false —
the inputs *are* all concrete.

So the honesty argument points the other way. Under reading (a), the current code
is the one making a false claim, and it makes it about the half of the definition
that is cheap and local to check.

### 2.2 Gating on identity-arrival is the failure mode §24.5 chose (a) to avoid

§24.5, on why (a) is recommended over (b):

> **(a)** is recommended — it is knowable **at dispatch**, whereas (b) requires
> the backend to report start-of-execution, which jobserver and Dask may not
> surface.

`identity_checksum is not None` is a third reading, and it has exactly the
property that disqualified (b): it requires a *round trip from the backend*
before the state is accurate. Today that round trip is `tf.construction()` on a
local side loop, so the window is milliseconds and the state is simply never
seen. At A4, with a jobserver or Dask backend, the same round trip is a network
hop — and a node that has been submitted to a remote queue will sit in `waiting`,
indistinguishable from a node whose inputs are still promises. That is the
diagnostic collapse §24.5 was written to prevent, arriving through a different
door.

There is also a plain-language version. `computing` should mean *"this node is
being computed."* Whether we have learned its `tf_checksum` yet is a fact about
our bookkeeping, not about the node. The run record already carries
`identity_checksum` for anyone who needs it; the state does not have to.

### 2.3 The retarget does not fix the tests, because it mislocates the cause

This is the load-bearing objection. Three of the six retargeted tests read a
value while the computation is in flight, and `.value` blocks (§1.3). Moving them
to A4 changes nothing: the read will still block at A4, because it is the read
that is wrong, not the phase.

Worse, the same defect fails a test that is **not** part of the retarget and is
still marked `a1` —
`test_transition_eligibility.py::test_setting_the_last_pin_does_not_deliver_a_result`,
the file's statement of §14.1's defining case:

```python
ctx.tf.pins.y = 32
assert ctx.tf.state in PENDING, states(ctx)     # passes
assert ctx.tf.result.checksum is None           # passes
assert ctx.tf.result.value is None              # FAILS: 42
```

The first two assertions pass. The third fails because reading `.value` *causes*
the delivery it is checking for. Eligibility is no longer delivery — that part is
genuinely fixed — but **reading is**, and §7/§10 say a read is a checksum
snapshot. The suite states this directly, in a test you retargeted:

> `test_reads_during_computation_do_not_block_on_the_body` — *"A read is a
> checksum snapshot (§7), not a request to compute."*

That test is not asking for A4 machinery. It is asking for `.value` to behave
like `.checksum` already does.

If blocking `.value` is a deliberate decision — "a value read is a demand and a
wait" is a defensible API, and it is what legacy did — then it needs §24 treatment
and a written-down entry, because it changes what `ctx.a.compute()` is *for* and
it makes §27's barrier timeouts reachable from an ordinary attribute access. It
should not be settled by which tests got moved.

### 2.4 `waiting` is overloaded again, and the suite can measure the cost

§15 A0's hazard note about the *pre-existing* code:

> **`waiting` is overloaded.** … the state is produced by one branch … and means
> *"nobody has demanded this yet"*, not *"computation is in flight"*.

[MOD-11] removes `eager` to end that overload. Publishing `waiting` for a
dispatched node re-creates it: `waiting` now means either "inputs are promises"
or "submitted, identity not yet known", and no caller can tell which.

Measured consequence: after the retarget, exactly **two** `== "waiting"`
assertions remain at `a1` —
`test_latency_downstream.py:95` and `test_transition_eligibility.py:145`. Both
are downstream nodes whose inputs really are promises. Both would also pass
against an implementation that returned `waiting` unconditionally, because in
this scheme almost everything pending is `waiting`. So the retarget does not just
move six tests to a later phase; it leaves the `waiting`/`computing` distinction
with no discriminating coverage at all in the phases before A4 — which is the
opposite of what a phase's exit evidence is for.

### 2.5 Six tests, not three — and one of them is the flagship

The diff changes six markers, not three:

| file | test | what else it asserts |
|---|---|---|
| `test_transition_eligibility.py` | `test_a_transformer_with_concrete_inputs_is_computing` | nothing else — this one is purely the `computing` claim |
| | `test_a_transformer_awaiting_an_upstream_result_is_waiting` | `tail` is `waiting`, `tail.result.checksum is None` |
| | `test_the_whole_downstream_cone_is_pending` | the whole cone's states, and every checksum `None` |
| `test_latency_last_pin.py` | `test_setting_the_last_pin_returns_before_the_body_finishes` | **`elapsed < PROMPT_SECONDS`** |
| | `test_reads_during_computation_do_not_block_on_the_body` | **`elapsed < PROMPT_SECONDS`**, both reads `None` |
| `test_latency_delay_port.py` | `test_editing_an_upstream_delay_makes_the_result_pending_immediately` | **`elapsed < PROMPT_SECONDS`**, `tf2`/`result` `waiting`, `result.value is None` |

Only the first is purely a submission-state assertion. The other five carry
A1-valid content to A4 with the one line that motivated the move.

The expensive one is `test_setting_the_last_pin_returns_before_the_body_finishes`.
Its primary assertion is `elapsed.seconds < PROMPT_SECONDS`, and §15 A0 says of
that measurement:

> Write the **latency test**, which is the one that makes the whole defect
> self-evident and should be written first.

A1 is the phase that fixes it, and §1.1 shows you *did* fix it — 5 ms against a
3-second body. Marking the test `a4` means A1's most important achievement has no
test asserting it until A4. The evidence exists; the marker throws it away.

---

## 3. What I propose

**(1) Publish `computing` at dispatch.** In `reactive.py`, both places:

```python
# at record creation, where the effect is queued:
node.state, node.block_reason, node.exception = 'computing', None, None

# in _publish_run's final branch — reached only when a run exists with
# neither a result nor an exception, i.e. submitted and unanswered:
node.state, node.block_reason, node.exception = 'computing', None, None
```

`waiting` then comes only from `_apply_pending` / `_apply_upstream_state`, i.e.
only when an input is not a concrete checksum. That is reading (a), exactly,
with `waiting` restored to one meaning.

**(2) Decide `.value`.** Either make it a snapshot like `.checksum` — returning
`None` while pending, which is what §7 and the suite assume — or record a §24
entry saying value reads block, and accept that
`test_setting_the_last_pin_does_not_deliver_a_result` and
`test_reads_during_computation_do_not_block_on_the_body` are asserting a contract
the project has decided against. I recommend the first; the second is a real
option but it is a design change, not a test-classification issue.

**(3) Revert the six markers**, then re-measure. My expectation after (1) and (2):

- `test_a_transformer_with_concrete_inputs_is_computing` — passes. The state is
  assigned inside the writing turn, so it is deterministic even for an instant
  body.
- `test_setting_the_last_pin_returns_before_the_body_finishes` — passes on
  timing already; the `computing` line passes after (1).
- `test_reads_during_computation_do_not_block_on_the_body` — needs (2).
- `test_editing_an_upstream_delay_makes_the_result_pending_immediately` — uses a
  sleeping body; should pass after (1).
- `test_the_whole_downstream_cone_is_pending` — should pass after (1); its
  downstream nodes are genuinely input-pending.
- `test_a_transformer_awaiting_an_upstream_result_is_waiting` — **may remain
  racy**, see below.

---

## 4. What I concede

`test_a_transformer_awaiting_an_upstream_result_is_waiting` builds `head` with an
instant body, then executes two further public calls (`ctx.tail = double`,
`ctx.tail.pins.x = ctx.head`) before asserting `head` is `computing`. Each of
those is a turn in which the class-5 completion can land, so `head` may legitimately
be `complete` by the assertion. That is a **defect in the test**, and you are
right that it cannot be made reliable by fixing states alone.

The remedy is a sleeping body — the same instrument every other mid-computation
test in the suite already uses (`slow_add` with `SHORT_BODY_SECONDS`) — not an
`a4` marker. A marker says "this contract belongs to a later phase"; this test's
contract belongs to A1 and its *construction* is wrong. Moving it hides a fixable
test behind a phase boundary, and at A4 it will be exactly as racy as it is now.

The same caution applies to `test_the_whole_downstream_cone_is_pending`, which
asserts an exact state dict after a single write; if it proves flaky with an
instant body, give it a sleeping one.

---

## 5. The procedural point

§24.5 is explicit:

> Whichever is chosen must be written down **before the first transition test**,
> which will otherwise encode its author's reading.

Reading (a) was written down — §26.2 and `tests/README.md` — before the tests
were written, precisely so this would not be settled by accident. The current
tree encodes a third reading, and it was settled by a marker edit rather than by
an entry. Whatever we land on, it should go into §24.5 and §26.2 as a decision
with its reasoning, so the next person reading `waiting` in a graph dump knows
which of the three things it means.

If you disagree with (1), the thing to do is amend §24.5 to say
*"`computing` means the transformation identity is known"* and state what covers
the dispatch window — then the tests follow the decision instead of the reverse.

---

## Appendix — reproducers

Both must be **script files**, not heredocs piped to `python`: the transformer
body goes through `inspect.getsource`, which fails with
`OSError: could not get source code` for code read from stdin.  Run them from
anywhere except the repository root — `/home/agent/seamless1` contains a
`seamless/` directory (this design folder) that shadows the `seamless` package.

```bash
conda activate seamless1
```

`repro1.py` — §1.1 and §1.3:

```python
import time
from seamless_workflow import Context

def slow_add(x, y, delay):
    import time
    time.sleep(delay)
    return x + y

ctx = Context()
ctx.tf = slow_add
ctx.tf.pins.x = 40
ctx.tf.pins.delay = 3.0
t0 = time.monotonic(); ctx.tf.pins.y = 2; t1 = time.monotonic()
print(f"set last pin returned in {t1-t0:.3f}s, state={ctx.tf.state}")
t = time.monotonic(); cs = ctx.tf.result.checksum
print(f".checksum read in {time.monotonic()-t:.3f}s -> {cs}")
t = time.monotonic(); v = ctx.tf.result.value
print(f".value    read in {time.monotonic()-t:.3f}s -> {v!r}  state={ctx.tf.state}")
```

```
set last pin returned in 0.002s, state=waiting
.checksum read in 0.004s -> None
.value    read in 3.032s -> 42  state=complete
```

`repro2.py` — §1.2:

```python
import time
from seamless_workflow import Context

def add(x, y):
    return x + y

def states(ctx):
    graph = ctx.get_graph(runtime=True)
    return {".".join(n["path"]): n["runtime"]["state"] for n in graph["nodes"]}

ctx = Context()
ctx.tf = add
ctx.tf.pins.x = 1
ctx.tf.pins.y = 2
seen = [states(ctx)]
print("immediately:", seen[-1])
for i in range(60):
    time.sleep(0.05)
    s = states(ctx)
    if s != seen[-1]:
        print(f"after {0.05*(i+1):.2f}s:", s)
        seen.append(s)
    if s.get("tf") == "complete":
        break
print("distinct:", [x["tf"] for x in seen])
```

```
immediately: {'tf': 'waiting'}
after 0.05s: {'tf': 'complete'}
distinct: ['waiting', 'complete']
```

§2.4 — count the surviving discriminating `waiting` assertions:

```bash
cd seamless-workflow/tests
grep -rn '== "waiting"' --include=*.py . | grep -v contract_helpers
```
