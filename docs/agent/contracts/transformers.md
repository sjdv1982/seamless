# Transformers (Contract)

**A Transformer is a mutable builder for immutable `Transformation` snapshots.** A Transformer holds code and the configuration around that code. Building it closes the current configuration and inputs into a `Transformation`. The builder may then change without changing anything already built.

Cell/Expression makes the same builder/snapshot distinction, but the two pairs are not structurally identical. A Cell recipe may span a chain of Expressions. One Transformer build produces exactly one Transformation, whose inputs may themselves be Expressions or Transformations.

This page owns the Transformer as a **builder and workflow handle**. Other pages own the rest:

- pin behavior: `contracts/pins.md`;
- execution and the immutable Transformation handle: `contracts/direct-delayed-and-transformation.md`;
- Context assignment and reactive scheduling: `contracts/workflow-context.md`;
- compiled-language additions: `contracts/compiled-transformers.md`.

## Canonical construction API

There are three canonical ways to construct a Transformer in Python:

- outside a workflow, `direct(function)` and `delayed(function)` construct Python Transformers;
- in a workflow, assigning a Python function (`ctx.tf = function`) constructs a bound Python Transformer;
- in any scenario, `Transformer(language="python", compiled=False, direct=False)` constructs a code-less builder that can be configured and optionally bound later.

**`direct` and `delayed` both return a Python Transformer.** They take no `language` argument, do not return a Transformation and do not run the decorated function at decoration time. They differ only in the call mode they install (*Delayed and direct calls*). Their full contract is `contracts/direct-delayed-and-transformation.md`.

`Transformer` is a factory class:

- With `compiled=False`, `language` must be `"python"` or `"bash"`. The factory picks the delayed or direct Python/Bash implementation according to `direct`.
- With `compiled=True`, the factory forwards `language` to the delayed or direct compiled implementation.

The concrete implementation classes are not public constructors. A builder's `language` is fixed at construction and read-only, for Python, Bash and compiled builders alike.

The factory is importable from `seamless_transformer`, `seamless.transformer` and `seamless.workflow`; all three names are the same class. `seamless.workflow` also exports `Context` and `Cell`.

A code-less Bash builder declares its pins itself, because Bash code has no signature (`contracts/pins.md`, *Which pins exist*). Declare a pin by writing it through `tf.pins`:

```python
from seamless.workflow import Transformer

tf = Transformer("bash", direct=True)
tf.code = "cat input > RESULT"
tf.pins.input = "hi"   # declares the pin "input" and sets its value
tf()                   # -> "hi\n"
```

A call-time keyword argument does not declare a pin: `tf(input="hi")` on a builder with no `input` pin does not feed `input` to the Bash code. What happens to such an argument is specified in `contracts/pins.md`.

## The two modes

A Transformer exists in one of two modes:

- **standalone**: its builder state is private to the Python object;
- **bound**: a workflow Context node owns its builder state, and the Transformer is a view onto that node.

Both modes share one public builder surface. They differ in ownership and liveness. A standalone Transformer describes a reusable family of snapshots. A bound Transformer describes a live node that the Context re-snapshots whenever its inputs change.

## Builder state

The common builder state comprises:

- code and language;
- the pin declarations, pin celltypes, optional-pin set and pre-bound pin inputs;
- the result celltype;
- modules and globals, where the language supports them;
- metadata, environment, scratch and placement settings;
- the `process_lock` and `driver` flags, which are part of the metadata (*`process_lock` and `driver`*);
- the streaming flag, which is an interaction feature: it is copied onto each built Transformation, is never part of a snapshot's identity, and is not stored in the durable graph (`contracts/streaming.md`);
- the call mode: delayed or direct.

Compiled Transformers add schema, header-derived state, compilation configuration, metavariables and additional objects. `contracts/compiled-transformers.md` alone specifies those additions, including which of them affect transformation identity.

The Transformer owns the pin collection, but `contracts/pins.md` alone specifies pin names, values, connections, conversion, nulls and optionality.

Builder state is mutable. Mutating the builder after a build affects later snapshots only.

## Building a Transformation

```python
tr = tf.build(*args, **kwargs)
tr2 = tf.transformation(*args, **kwargs)      # alias of build()
tr3 = tf.get_transformation(*args, **kwargs)  # alias of build()
```

**`build()` is the canonical snapshot operation, and it exists on every builder**: ordinary and compiled, delayed and direct, standalone and bound. `transformation()` and `get_transformation()` are exact aliases. They take the same call arguments and have the same meaning. All three return an immutable `Transformation` and never execute it, whatever the call mode.

A build:

1. snapshots the current builder configuration;
2. combines pre-bound pin inputs with the call arguments;
3. serializes concrete inputs to checksums and performs the validation required at construction time;
4. retains typed dependency inputs (Expressions, Transformations) as explicit dependencies, in the forms `contracts/pins.md` admits;
5. returns a frozen Transformation definition with its own execution promise.

So a build can raise for malformed call arguments or concrete inputs even though it runs no transformation code. The exception class for malformed arguments is unspecified (*Unspecified exception classes*). Mutating the builder, its configuration or the original input objects after the build does not alter the returned Transformation.

For a bound Transformer, `build()` snapshots the node's current builder configuration and input bindings into a detached Transformation. It does not return the Context's transient run object, and it does not make that snapshot the node's new durable state.

**Detached means detached in definition, not in lifetime.** The detached Transformation claims what it was given directly, which is its code and modules. Its pins arrive as Expressions over the node's checksums, so they are dependencies, and it claims them only when it runs. It stays runnable only while the Context, or the hashserver, keeps those checksums. After replacement plus `prune()`, or after `close()`, and with no hashserver, `run()` raises `TransformationError`. To keep an input past its Context, capture its checksum into an owner. The rule is in `contracts/internal/checksum-reference-lifecycle.md`, §7, *One rule for owners*.

**`build()` is the semantic boundary.** `__call__` and the standalone named work methods are layered on top of `build()`, never on `self()`, so a Transformer's call mode cannot change what they mean.

## Delayed and direct calls

Delayed and direct Transformers are the same kind of builder. They differ only in `__call__`:

```python
delayed_tf(*args, **kwargs)  # == delayed_tf.build(*args, **kwargs)
direct_tf(*args, **kwargs)   # == direct_tf.build(*args, **kwargs).run()
```

Directness changes nothing else: not the builder state, the binding, the pins, the snapshot identity, or the meaning of `build()` and the named work methods. Call-time behavior is specified in `contracts/direct-delayed-and-transformation.md`.

## Named work methods

The named methods never inherit direct-call sugar. A standalone Transformer applies them to a fresh `build()`. A bound Transformer applies them to the live node.

| Operation | Standalone Transformer | Bound Transformer |
|---|---|---|
| `build()` / `transformation()` / `get_transformation()` | return a detached immutable Transformation | return a detached immutable snapshot of the current node definition |
| `compute()` | build, execute and return the result checksum | demand the live node and wait on its Context barrier |
| `computation()` | asynchronous form of `compute()` | asynchronous Context barrier for the live node |
| `run()` | build, execute and materialize the result | demand the live node and materialize its result |
| `task()` | build, and return an `asyncio.Task` for the Transformation | return an `asyncio.Task` that operates through the live node |
| `prune()` | the attribute exists; calling it raises `AttributeError` | reclaim superseded work in the node's downstream cone |
| `clear_exception()` | the attribute exists; calling it raises `AttributeError` | clear the node failure according to the workflow lifecycle |

This table fixes only whether an operation targets a detached snapshot or the live bound node. Execution, cancellation and error behavior are specified by the Transformation, Context and node-lifecycle contracts.

**`compute()` reports a failure, and `run()` raises it** (ruled 2026-09-28; `contracts/cells.md`, *Failures*, *How a failure is delivered*). In both modes `compute()` / `computation()` return the result checksum, or `None` when there is none, and never raise for a failure or a node state. Standalone, that is `Transformation.compute()`, which sets `.exception` on the Transformation; `Transformation.run()` raises `TransformationError` (`contracts/direct-delayed-and-transformation.md`). Bound, `compute()` is the node barrier: it returns `None` when the node settles in `failed`, `unwired`, `miswired` or `blocked`, and `run()` re-raises the node's recorded exception or raises `NodeError` (`contracts/node-state-lifecycle.md`, *States as seen through barriers and handles*). A direct Transformer's call is `build().run()`, so it raises.

The table holds for direct Transformers exactly as for delayed ones. On a direct Transformer, `build()` returns a Transformation, not a value, and `compute()`, `computation()`, `run()` and `task()` work in both modes. *Verified against code (2026-09-26):* `TransformerCore.build`, `.compute`, `.run`, `.task` and `.computation` use `self.build()`.

## Live-node members

`result`, `state`, `block_reason`, `exception` and `logs` describe a live workflow node, so only a bound Transformer has them. **On a standalone Transformer, reading any of the five raises `AttributeError`.** The corresponding facts for a detached computation live on the Transformation that `build()` returns.

`logs` is the node's failure text, or the captured output and execution time of its current run. Its contract is `contracts/transformation-logs.md`, *Bound Transformers*.

`prune()` and `clear_exception()` are different: they exist as attributes on a standalone Transformer, and only calling them raises `AttributeError` (*Named work methods*). So `hasattr(tf, "prune")` is `True` in both modes and cannot tell the modes apart.

## Binding

Assigning a standalone Transformer to a Context binds it:

```python
ctx.tf = tf
```

**Binding is a move, not a copy.** The builder state moves into the transformer node, and the standalone private copy is abandoned. The node becomes the single source of truth, so mutations never need to be mirrored between two owners.

Every later read of `ctx.tf` returns a fresh Transformer view onto that node. Handle identity carries no meaning: two views are interchangeable, and dependencies are recorded by node path and content, not by Python object identity. Deleting the node or closing the Context makes existing views stale or closed, as specified in `contracts/workflow-context.md`.

The Context stores the node and its builder configuration, **not a persistent Transformation object**. When an input changes, the Context freezes the node's configuration into a private `FrozenTransformer`, builds a fresh immutable Transformation from it and submits it. The FrozenTransformers and the Transformations the Context fires are private runtime artifacts. An explicit `ctx.tf.build()` is a detached user snapshot (*Building a Transformation*).

## Pins and result

`tf.pins` exposes the Transformer's input slots. The pin collection is part of builder state, but a Pin is a handle with its own contract: `contracts/pins.md`.

`tf.celltypes.result` configures the result celltype of every Transformation the builder produces.

A bound Transformer also exposes `tf.result`, a read-only view of the node's output. A standalone Transformer has no live result endpoint, since its output belongs to each Transformation it builds; reading `tf.result` raises `AttributeError` (*Live-node members*).

**A bound Transformer's result is never a producer target.** A producer operation may target a pin but never the result. Any producer operation aimed at the result raises `ReadOnlyEndpointError`, and attribute assignment `ctx.tf.result = …` is one such operation. Context wiring is specified in `contracts/workflow-context.md`.

## `process_lock` and `driver`

Two boolean settings say how a transformation's code shares the process that runs it. Both are part of the Transformer's `meta`. A build copies them into the `__meta__` of the Transformation, which is outside transformation identity (`contracts/identity-and-caching.md`), so neither setting changes a `tf_checksum`.

- **`process_lock`**, true by default. The transformation's code runs while holding the lock of its process, so that no two such transformations run their code at the same time in one process.
- **`driver`**, false by default. It declares that the code mainly launches other transformations and waits for them. A driver never takes the lock.

This page specifies the two settings: their values, how they are coupled, and where they are stored. What the lock does while a transformation runs is `contracts/execution-backends.md`, *The process lock*. That section also says when a transformation gives the lock up, what a driver's launches get, and how many transformations each backend runs at once.

| `process_lock` | `driver` | Meaning |
|---|---|---|
| true | false | The default. The code waits for the lock, runs while holding it, and gives it up at its first nested submission |
| false | true | A declared driver. The code never takes the lock |
| false | false | Opt-out, for code that is safe to run next to other code in the same process, such as I/O-bound work |
| true | true | Invalid |

**Setting `driver` to true sets `process_lock` to false. Only an explicit assignment sets it back to true.**

```python
tf.process_lock          # True
tf.driver                # False

tf.driver = True         # process_lock is now False
tf.process_lock = True   # raises: a driver does not take the lock

tf.driver = False        # process_lock stays False
tf.process_lock = True   # accepted
```

The two values can be written through three routes: the `driver` property, the `process_lock` property, and an assignment to `meta`. One rule covers all three:

| Write | Effect |
|---|---|
| `driver = True`, or `meta = {"driver": True}` | `driver` becomes true and `process_lock` becomes false |
| `driver = False` or `None`, or the same through `meta` | `driver` is cleared, and `process_lock` keeps its value |
| `process_lock = False`, or `meta = {"process_lock": False}` | `process_lock` becomes false |
| `process_lock = True` while `driver` is true, by either route | raises |
| `meta = {"driver": True, "process_lock": True}` | raises |
| `meta = {"driver": False, "process_lock": True}` on a driver | accepted: one assignment clears `driver` and sets `process_lock` |
| a value that is not a boolean, by any route (`driver` also accepts `None`) | raises |

A refused write changes nothing: an assignment to `meta` that carries a refused value is refused as a whole.

- **A new Transformer has neither key in `meta`.** `tf.process_lock` and `tf.driver` then report `True` and `False`, by the rule for absent keys below.
- **A build writes both values.** Every Transformation that a Transformer builds carries `driver` and `process_lock` explicitly in its `meta`, whatever the Transformer's `meta` contained.
- **On a Transformation both values are read-only.** They are read through `tr.meta`, which is immutable like the rest of the definition (`contracts/direct-delayed-and-transformation.md`, *Immutability*).
- **`driver` is not inherited.** A transformation that is built while a driver's code runs does not get `driver` in its own `meta`. In a transformation's `meta`, `driver` means that this transformation was itself declared a driver.

### Absent keys in a transformation dict

A transformation dict can lack one or both keys in its `__meta__`, and it can run with no `__meta__` at all, because `__meta__` is not part of the checksummed dict. This happens when:

- a fingertip recomputes a transformation from its checksum, in a process that holds no `__meta__` for it;
- `seamless-run-transformation` runs a checksum without a dunder file;
- the dict or the workflow graph was written before these keys existed.

Every reader of a dict applies one rule:

- an absent `driver` is false;
- an absent `process_lock` is the opposite of `driver`.

So a dict that says only `driver: true` is a driver that does not take the lock. A transformation that arrives without `__meta__` takes the lock, even if it was built as a driver or with the lock off. That reading is safe: a transformation that holds the lock and then submits nested work gives the lock up (`contracts/execution-backends.md`, *The process lock*).

Both values true, or a value that is not a boolean, makes the transformation invalid. A builder refuses to build it. An executor that receives such a dict fails the transformation before its code runs, with an error that names both keys.

Code that passes an existing dict on, such as `seamless-run-transformation`, does not rewrite its `__meta__`.

### Bound Transformers

`ctx.tf.process_lock`, `ctx.tf.driver` and `ctx.tf.meta` follow the rules above, with the same coupling. The two values belong to the workflow Context node:

- every view of `ctx.tf` reads and writes the one pair of values;
- binding a standalone Transformer moves its values into the node with the rest of its `meta` (*Binding*);
- the node keeps them in its `meta` mapping, and `ctx.get_graph()` saves that mapping. A graph whose transformer entry lacks a key loads by the rule for absent keys;
- a bound and a standalone Transformer with the same settings build Transformations with the same two values.

**`process_lock`, `driver` and `scratch` are operational features, and `streaming` is an interaction feature.** A bound node treats the two kinds differently:

| | Operational: `process_lock`, `driver`, `scratch` | Interaction: `streaming` |
|---|---|---|
| What it configures | how the node's transformation is executed | what this session sees of a run while it is in flight |
| Saved by `ctx.get_graph()` | yes | no |
| Assigning it on a bound node | changes the node's configuration, so the Context demands the node again | never re-runs the node; it applies from the node's next run (`contracts/streaming.md`) |

A change of `process_lock` or `driver` does not run the node's code again when its result is recorded. The node's `tf_checksum` is the same, so the recorded result answers the new demand from the cache. A run of that `tf_checksum` that is still in flight is latched onto, and it keeps the settings it started with (`contracts/identity-and-caching.md`, *Concurrent submissions of the same checksum*). The rules for `scratch` are in `contracts/scratch-witness-audit.md`, *Scratch*.

## Ordinary and compiled Transformers

For Python and Bash, the factory returns ordinary builders: a Python builder takes a callable, a Bash builder takes source text. `Transformer(language, compiled=True, direct=...)` extends the same builder contract with compiled-language configuration.

The rules on this page (modes, binding, pins, snapshots and named work methods) do not vary by language. The compiled contract owns schemas, native source, generated headers, marshalling, compilation, compiled objects and compiled result packaging, and this page does not repeat them. See `contracts/compiled-transformers.md`.

## Unspecified exception classes

The contract says that each of the following raises. It does not say which exception class, and the author has deferred the question. Tests assert only that an exception is raised. Do not rely on the class.

- passing a `language` to `direct()` or `delayed()`, as in `direct(f, language="bash")`;
- building with malformed call arguments: an unknown keyword, a missing required argument, or too many positional arguments;
- setting `language` on a builder.

For information only, not contract: today these raise, respectively, `TypeError` (unexpected keyword argument), `TypeError`, and `AttributeError("transformer language is read-only")`.

The refused writes of *`process_lock` and `driver`* are in the same position: setting `process_lock` to true on a driver, writing both values as true in one `meta` assignment, and writing a value that is not a boolean. Each raises, and the exception class is not specified. For information only, not contract: today the first two raise `ValueError` and the third raises `TypeError`.

## Implementation status and current limitations

The former bound task, read-only result assignment and signature-less call-time keyword gaps now satisfy the contract. Focused plain tests in `seamless-workflow/tests/test_contract_transformer_bound.py` and `seamless-transformer/tests/test_contract_transformer_builder.py` cover them.

## Non-goals

- **Transformation execution.** Building freezes a definition. Execution backends, result promises, immutability after construction and cancellation belong to `contracts/direct-delayed-and-transformation.md` and its linked execution contracts.
- **The process lock at run time.** This page owns the `process_lock` and `driver` settings. When the lock is taken and given up, what a driver's launches get, and how many transformations a backend runs at once belong to `contracts/execution-backends.md`.
- **Pin semantics.** This page names pins as builder state but does not own their declarations, writes, conversions, null rules or failures (`contracts/pins.md`).
- **Context scheduling.** Reactive invalidation, barriers, speculation and graph serialization belong to `contracts/workflow-context.md` and `contracts/node-state-lifecycle.md`.
- **Compiled-language semantics.** They belong to `contracts/compiled-transformers.md` and its linked schema and compiled-pin contracts.
