# Jupyter widgets (Contract)

A **widget attachment** is the attachment whose external resource is a traitlets object in this process: an ipywidgets slider, a text box, any `HasTraits` instance. **The attachment contract of `contracts/attachments.md` applies in full** — direction, scope, spec versus session, the sense and actuate disciplines, the three-way error model, the detector mechanism, the cut barrier and the lifecycle. This page specializes it for values held by a widget. It does not restate a rule from that page; each section says where the widget driver makes a generic rule concrete.

Widget attachments exist on the **workflow Context** only. A standalone `Cell`, a `direct`/`delayed` transformer and the command-line face have no widget integration.

Code locations:

| Concern | Module / symbol |
|---|---|
| Public functions | `seamless_workflow.jupyter` (`traitlet`, `output`) |
| The hub and its links | `seamless_workflow.attachments.traitlet` (`CellTraitlet`, `Link`) |
| Output display | `seamless_workflow.attachments.output_widget` (`OutputWidget`) |
| Transport | `seamless_workflow.attachments.widget.WidgetDriver` — internal; it borrows the file service's I/O pool (`contracts/attachments.md`, *Current limitations*) |
| Session protocol, policy, barrier | as in `contracts/attachments.md` |
| Errors | `seamless_workflow.attachments.session` (`MountError`, `ConflictError`); `seamless_workflow.errors` (`AuthorityError`, `NodeError`, `ReentrantContextError`, `ClosedContextError`) |

## The API

```python
from seamless_workflow.jupyter import traitlet, output

t = traitlet(ctx.a)                    # the cell's hub; blocking; created on first use
t.link(widget, target_attr="value")    # bidirectional: cell <-> widget
t.connect(widget, target_attr="value") # one way: cell -> widget
t.observe(handler, names="value")      # traitlets observe, plus an immediate first call
t.value                                # the cell's last delivered value, or None

t.status                               # the status dict
t.error                                # delivery or conflict error, or None
t.clear_error()
t.destroy()                            # detach, and drop every link

out = output(ctx.c, layout=None, mimetype=None)   # an OutputWidget; display(out)
```

- **These are functions, not `Cell` members.** `Cell` has no `traitlet` or `output` attribute, so `ctx.a.traitlet` and `ctx.a.output` remain ordinary sub-path projections (`contracts/cells.md`, *API-name arbitration*).
- **`traitlet(cell)` returns the same hub on every call** while the attachment exists: `traitlet(ctx.a) is traitlet(ctx.a)`.
- **`traitlets` and `ipywidgets` are optional dependencies** (`seamless-workflow[jupyter]`), imported on first use. `traitlet()` needs only `traitlets`; `output()` needs `ipywidgets` and IPython.
- **Nothing here requires a running kernel.** A hub links to any `HasTraits` object, in a script or a test as in a notebook.

## The hub: one attachment, any number of widgets

**The attached resource is the hub, never a widget.** `CellTraitlet` is a `traitlets.HasTraits` object with one trait, `value`. It occupies the node's single widget slot and may coexist with its single file slot (`contracts/attachments.md`, *Scope*). Widgets are tied to it by ordinary in-process links that the attachment layer never sees.

- **Several widgets on one cell are several links on one hub.** A slider and a text box linked to the same hub stay in step with each other and with the cell.
- **The session keeps the hub alive, the hub keeps its links alive, and a link keeps its widget alive.** The return values of `traitlet()`, `link()` and `connect()` may be dropped.
- **`link()` and `connect()` return the `Link`;** `Link.unlink()` removes that one link and leaves the attachment in place.
- **`observe` calls the handler once immediately** when the hub has a value, and then on every change.
- **Assign, do not mutate.** A change is detected when `value` is assigned. Mutating a list or an array held in `value` in place is not observed, as with any traitlet.

## Modes: `w`, and the upgrade to `rw`

The widget driver uses the `mode` and `authority` fields of the generic spec (`contracts/mounts.md`, *Spec validation and normalization*), but the user never passes them.

- **A hub is created in mode `w`.** `traitlet()`, `connect()`, `observe()` and `output()` only read the cell, so they are legal on a **connected** cell — that is how a computed value is displayed.
- **The first `link()` upgrades the hub to mode `rw`.** A sensing attachment is the node's producer, so the upgrade is refused with `AuthorityError("Sensing mount cannot have incoming edges; unmount first")` when the cell has an incoming edge. **A refused upgrade changes nothing:** the hub stays attached in `w`, and its existing links and observers keep working.
- **The upgrade is a detach followed by an attach in the widget slot**, so it opens a new widget session; the hub and its links are carried over. A file session on the same node is preserved.
- **There is no downgrade.** A hub that has been linked stays in `rw` after its last bidirectional link is removed, until it is destroyed. While it is in `rw`, adding an incoming edge to the cell raises `AuthorityError("Sensing mount is the producer; unmount first")`; call `traitlet(cell).destroy()` first.
- **The `authority` field is always `"cell"`.**
- **Every sensing slot protects the node's topology.** Destroying the hub releases its own guard; an `r` or `rw` file mount still refuses incoming edges until it is unmounted too.

## The initial decision

The initial decision is the table of `contracts/mounts.md`, *The initial decision table*, read with **the hub's value in the place of the file**, with `authority="cell"`, and with **a hub value of `None` as an absent file**. Its outcomes for the two attach points:

**At `traitlet(cell)`** (mode `w`, hub value `None`): if the cell is `complete`, its value is delivered to the hub before the call returns; otherwise nothing happens until it completes.

**At the first `link(widget)`** (upgrade to `rw`). If the hub's value is `None` and the widget's is not, `link()` first copies the widget's value into the hub. Then:

| Cell | Widget value | Result |
|---|---|---|
| `complete`, value *N* | any | **the cell wins:** the widget is set to *N* |
| no complete value | *V*, not `None` | **the empty cell takes the widget's value:** cell ← *V* |
| no complete value | `None` | cell ← null |

The last row is row 4 of the no-value table and not a widget rule: an absent resource attached in a sensing mode to a cell without a value installs null. The cell is then `complete` with value `None`, and counts as in sync with the `None`-valued hub.

**A later `link()` on a hub that is already `rw`** applies the same direction rule without a new attach: a hub with a value sets the widget; a hub without one takes the widget's value as an ordinary change.

## Cell to widget

Delivery follows `contracts/attachments.md`, *Actuate*, without exception. What that means for a widget:

- **A widget shows `complete` values only.** While the cell is `waiting`, `blocked` or `failed`, nothing is delivered and **the widget keeps the last value it showed**. There is no "pending" or "failed" rendering; read `ctx.a.state` and `ctx.a.exception` for that.
- **Intermediate values are not queued.** A rapid series of cell changes reaches the widget as its last value. Cell-to-attachment delivery starts are spaced by at least **2/3 second per session**. The first delivery is immediate, later pending values coalesce to the latest, and file and widget slots have independent delivery clocks. `ctx.mounts.sync()` waits for throttled pending deliveries, subject to its timeout.
- **The value is the cell's value as its own `celltype`**: the same object `.value` would return, resolved from the checksum by the transport. Resolution never computes (*A delivery resolves; it never computes*).
- **A null cell value sets `hub.value` to `None`**, which links do not forward (*`None` is absence*): linked widgets keep what they showed.

## Widget to cell

A change to a bidirectionally linked widget is sensed as in `contracts/attachments.md`, *Sense*: a non-detaching authoritative write with no privilege over a user assignment, and none under it.

When the same cell has both a sensing file mount and a bidirectional widget hub, **the newest accepted write wins**. An actual valid write from either resource or from the user clears every sense error on that node. Merely observing unchanged valid content from the other resource does not recover a failed sensor. The delivery interval does not delay sensing.

- **The value is serialized as the cell's celltype, exactly as an assignment of the same value would be.** A value that an assignment would reject is a **sense error**: the cell is `failed`, monitoring continues, and the next valid widget value recovers it with no user action. A `Text` widget linked to an `int` cell fails the cell while the text is not a number.
- **Changes are debounced.** The cell is written once, after the widget has been quiet for the debounce interval (*Limits*), with the widget's value at that moment. Dragging a slider produces one write, not one per step.
- **The handler returns before the cell is written.** `slider.value = 5` followed at once by `ctx.a.value` may still read the old value.
- **`ctx.mounts.sync()` is the barrier**, and it does not wait for the debounce: a cut observes the hub's value as it is and reports only after that observation is processed (`contracts/attachments.md`, *The cut barrier*). **`ctx.compute()` is graph-only** and does not see a widget change that has not been sensed yet. A script that sets a widget and then computes must call `ctx.mounts.sync()` in between.
- **A pending widget change beats an incoming delivery.** If the cell changes while a widget change is still inside its debounce interval, the widget's change is observed first, the delivery acknowledges `conflict`, and the cell takes the widget's value.

### `None` is absence

**A hub value of `None` is the absent resource** (`absent` in `contracts/mounts.md`, *Observation classification*). It never clears and never overwrites a cell after the initial decision: disappearance does not clear the node.

- A `Link` forwards `None` in neither direction.
- A widget cannot be used to clear a cell. Clearing an attached cell is refused in any case (`contracts/attachments.md`, *The topology rules an attachment imposes*).

### Values a widget cannot hold

A widget may coerce what it is given — an `IntSlider` clamps to its range — or refuse it with a `TraitError`.

- **Through `link()`, a coerced value flows back.** The hub takes the widget's coerced value, it is sensed, and the cell converges on what the widget can represent. A slider with `max=30` linked to a cell holding 50 sets the cell to 30.
- **Through `connect()`, nothing flows back.** A one-way link never writes to the hub: the widget shows its coerced value, and the cell is unaffected.
- **A link whose target refuses the value is logged, and only that link is skipped.** The delivery succeeds for the hub and for every other link; it is not a delivery error.

### Writing to the hub of an output

Assigning `t.value` on a hub in mode `w` is a foreign change to an output the Context owns. It is **reasserted**: the cell's value is delivered again. Repeating it trips the oscillation detector, which latches a `ConflictError` on `t.error` and stops delivery until `t.clear_error()` (`contracts/attachments.md`, *The oscillation detector*). To set a cell from code, assign the cell.

## Threads and blocking

- **Every public call is an ordinary public Context operation.** `traitlet()`, `link()` when it upgrades, `destroy()`, `output()` and `clear_error()` block the caller, raise `ReentrantContextError` from the controller thread and `ClosedContextError` after `close()`.
- **Delivery callbacks to hub observers, and delivery updates of linked widgets, run on a transport worker thread** — not on the thread that created the widget, and not on the Jupyter kernel's event loop. The immediate initial call from `observe()` runs on its caller's thread, as do notifications from a direct hub assignment and the initial update in `link()` or `connect()`. Setting an ipywidgets value from a worker thread is supported by ipywidgets; a handler that needs the kernel loop must hand over to it itself.
- **A delivery handler must not wait for its own attachment.** It runs inside the delivery it was called for, so `ctx.mounts.sync()`, destroying that hub, or upgrading its link can wait on the same delivery and block until their timeout. Reading and assigning cells from a handler is fine.
- **Widget-side change handlers do no Seamless work.** They arm the debounce and return, so a kernel that is busy in a blocking Context call still loses no widget change.

## Errors

The error model is that of `contracts/attachments.md`, *The three-way error model*. For a widget attachment:

| Error | Where | When |
|---|---|---|
| sense error | the **cell**: `failed`, `ctx.a.exception` a string | the widget's value cannot be serialized as the cell's celltype |
| delivery error | `t.error` | the cell's value cannot be resolved or deserialized — typically a result whose checksum arrived without its bytes |
| conflict error | `t.error`, latched | the detector tripped (*Writing to the hub of an output*) |

The `"<path>: <reason>"` prefix of a `MountError` carries the session's synthetic path, `widget-<hex>`. The hex part is not stable across sessions; match the `widget-` prefix only.

Raised at the call:

| Error | Raised when |
|---|---|
| `AttributeError("Widgets attach to whole Context cell nodes")` | a standalone `Cell`; a sub-path projection (`ctx.a.b`); a read-only handle, **including a transformer's result, `ctx.tf.result`** |
| `NodeError("Mounts require an existing whole cell node")` | the node does not exist or is not a cell |
| `ValueError("Cell is already mounted; unmount first")` | the widget slot is occupied by a different widget transport; an existing public hub is returned instead |
| `TypeError("Celltype '<ct>' is not mountable")` | `checksum`, `deepcell`, `module` |
| `AuthorityError` | `link()` on a cell with an incoming edge; an incoming edge into a linked cell; clearing an attached cell |
| `ImportError` | `traitlets`, or for `output()` `ipywidgets`, is not installed |

The remedy for every scope refusal is the usual one: **attach a cell and connect it.** `ctx.out = ctx.tf.result; display(output(ctx.out))` shows a transformer's result.

## Lifecycle

- **A widget attachment is never serialized.** `get_graph()` writes no entry for it, and `set_graph()` restores none. After loading a graph, call `traitlet(...).link(...)` again.
- **Every detach destroys the hub.** `t.destroy()`, deleting the node, an empty same-celltype builder, `set_graph()` and `ctx.close()` all end in the same detach (`contracts/attachments.md`, *Attach, detach, close*). The hub then drops all its links and becomes inert; its widgets keep the values they last showed and are no longer tied to anything.
- **Slot detach is independent.** `t.destroy()` removes only the widget slot, and `del ctx.a.mount` removes only the file slot. Node deletion, an empty same-celltype builder, graph replacement and Context close detach all slots.
- **A later `traitlet(cell)` creates a fresh hub**, in mode `w`, with no links.
- **A detached hub does not address a replacement attachment.** Its `status` and `error` are `None`; repeating `destroy()` or `clear_error()` leaves any new hub or file mount alone.
- **The celltype is frozen and clearing is refused** while the hub exists, as for any attachment.

## The output widget

`output(cell, layout=None, mimetype=None)` returns an `OutputWidget`: an `ipywidgets.Output` that redraws whenever the cell's hub delivers a value. It attaches nothing of its own; it calls `traitlet(cell)` and observes it, so it works on a connected cell and coexists with links on the same hub.

- **Each delivery replaces the content;** nothing is appended.
- **Nothing is drawn until the cell is `complete`,** and the last rendering stays while the cell recomputes or fails (*Cell to widget*).
- `display(out)` shows the underlying `Output`, available as `out.output_instance`; `layout` is passed to it.

The display class follows the cell's celltype, unless `mimetype` names one:

| Celltype | Rendering |
|---|---|
| `text`, `str`, `int`, `float`, `bool`, `yaml` | plain text |
| `plain` | the value as JSON text |
| `python`, `ipython` | syntax-highlighted code |
| `bytes`, `binary`, `mixed` | the `repr` of the value |

| `mimetype` | Rendering |
|---|---|
| `"text/plain"` | plain text |
| `"text/html"` | HTML |
| `"application/json"` | the value as JSON text |
| `"image/png"` | an image; the cell holds the PNG bytes |

Any other `mimetype` raises `ValueError`. Cells carry no mimetype of their own, so the argument is the only way to select one.

## Limits

**The numbers are current defaults, not contract:**

| Knob | Current default |
|---|---|
| debounce interval, widget to cell | 0.1 s |
| delivery timeout | 60 s |
| oscillation detector | 3 reasserts in 20 s (`contracts/mounts.md`, *Limits*) |

## Porting notes

Stated as current behaviour, with no claim about what any earlier version did:

- **The entry points are `traitlet(cell)` and `output(cell)`.** There are no `Cell.traitlet()` and `Cell.output()` methods.
- **Only settled values are shown.** A widget never sees a preliminary or intermediate value.
- **Connecting an upstream into a linked cell is refused** with `AuthorityError`. A link is never dropped silently; destroy the hub first.
- **Handlers run on a worker thread.**
- **Links are runtime state.** They are not in the graph and must be re-created after a load.
- **There is no polling `observe` on `Cell` or `Context`.** Observe the hub.
- **`ctx.compute()` does not wait for widgets.** Use `ctx.mounts.sync()`.

## Current limitations

- **One file slot and one widget hub slot per node.** Several widgets share the same hub; additional file mounts are refused.
- **`ctx.a.mount` addresses only the file slot.** `.mount.spec`, `.mount.status` and `.mount.error` are `None` when no file slot exists, and `del ctx.a.mount` is then a no-op. Use `t.status`, `t.error`, `t.clear_error()` and `t.destroy()` for the widget slot.
- **The barrier is spelled `ctx.mounts`.** `ctx.mounts.sync()` cuts every session, and its `SyncReport` and `ctx.mounts.errors` use `(node_path, driver)` keys for all entries, including file-only and widget-only nodes. A hub's key is `(("a",), "widget")` for `ctx.a`, in the `status` shape of `contracts/mounts.md`.
- **Idle delivery wakeups are Context-owned.** A deadline timer wakes pending throttled deliveries and due retries without a user call.
- **The oscillation detector is per session.** Cross-attachment loops are not detected as a node-wide loop.
- **The debounce interval is not a public parameter.**
- **Directory celltypes are unspecified.** `folder` passes celltype admission and its hub value is the index; `deepfolder` is refused, because a hub attaches in mode `w`. Do not depend on either.

## Non-goals

- **Sub-path, pin, code and standalone attachments.** As for every attachment (`contracts/attachments.md`, *Non-goals*).
- **Showing node state in a widget.** A widget shows values. `waiting`, `blocked` and `failed` are read from the cell handle.
- **Persisting links in the graph.** A widget is a live object of one process; there is nothing to serialize it as.
- **Marshalling onto the kernel's event loop.** The blocking Context calls wait for delivery acknowledgements, so a delivery that needed the kernel loop would deadlock every one of them when called from a notebook cell.
- **Clearing a cell from a widget.** `None` is absence.
