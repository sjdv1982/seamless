# Transformers (Contract)

**A Transformer is a mutable builder for immutable `Transformation` snapshots.** A Transformer holds code and the configuration around that code; building it closes the current configuration and inputs into a `Transformation`. The builder may then change without changing anything already built.

That is the same builder/snapshot distinction as Cell and Expression, but not an assertion that the two pairs have identical structure. A Cell recipe may span a chain of Expressions. One Transformer build produces one Transformation, whose inputs may themselves be Expressions or Transformations.

This page owns the Transformer as a **builder and workflow handle**. Pin behavior belongs to `contracts/pins.md`; execution and the immutable Transformation handle belong to `contracts/direct-delayed-and-transformation.md`; Context assignment and reactive scheduling belong to `contracts/workflow-context.md`; compiled-language additions belong to `contracts/compiled-transformers.md`.

**The `direct` and `delayed` decorators both return a Python Transformer.** They accept no language argument, do not return a Transformation and do not execute the decorated function at decoration time. The difference between them is the call mode installed on the returned Transformer: calling a delayed Transformer returns a Transformation, while calling a direct Transformer executes the built Transformation and returns its value.

## Canonical construction API

There are three canonical ways to construct a Transformer in Python:

- outside a workflow, `direct(function)` and `delayed(function)` construct Python Transformers;
- in a workflow, assigning a Python function (`ctx.tf = function`) constructs a bound Python Transformer;
- in any scenario, `Transformer(language="python", compiled=False, direct=False)` constructs a code-less builder that can be configured and optionally bound later.

`Transformer` is a factory class. With `compiled=False`, `language` must be `"python"` or `"bash"`; the factory selects the delayed or direct Python/Bash implementation from `direct`. With `compiled=True`, the factory forwards `language` to the delayed or direct compiled implementation. The concrete implementation classes are not public constructors.

The factory is importable from `seamless_transformer`, `seamless.transformer`, and `seamless.workflow`. The last namespace also exports `Context` and `Cell`:

```python
from seamless.workflow import Cell, Context, Transformer

tf = Transformer("bash", direct=True)
tf.code = "cat input > RESULT"
```

For Python and Bash builders, `language` is fixed by the selected class and is read-only. Compiled builders likewise have a read-only language chosen at construction.

## The two modes

A Transformer exists in one of two modes:

- **standalone** — its builder state is private to the Python object;
- **bound** — its builder state is owned by a workflow Context node, and the Transformer is a view onto that node.

The same public builder surface is used in both modes. What changes is ownership and liveness: a standalone Transformer describes a reusable family of snapshots, while a bound Transformer describes a live node that the Context continually re-snapshots as its inputs change.

## Builder state

The common builder state comprises:

- code and language;
- the pin declarations, pin celltypes, optional-pin set and pre-bound pin inputs;
- the result celltype;
- modules and globals where the language supports them;
- metadata, environment, scratch, direct-print and placement settings;
- the call mode: delayed or direct.

Compiled Transformers add schema, header-derived state, compilation configuration, metavariables and additional objects. Those additions, including which parts affect transformation identity, are specified only in `contracts/compiled-transformers.md`.

Pin names, values, connections, conversion, nulls and optionality are specified only in `contracts/pins.md`. The Transformer owns the pin collection, but this page does not redefine pin behavior.

Builder state is mutable until a snapshot is built. Mutating the builder after a build affects later snapshots only.

## Building a Transformation

```python
tr = tf.build(*args, **kwargs)
tr2 = tf.transformation(*args, **kwargs)  # exact alias
```

`build()` and `transformation()` always return an immutable `Transformation`, for ordinary, compiled, delayed, direct, standalone and bound Transformers alike. `get_transformation()` is the compatibility alias and has the same meaning. These operations do not execute the Transformation.

A build:

1. snapshots the current builder configuration;
2. combines pre-bound pin inputs with the call arguments;
3. serializes concrete inputs to checksums and performs the validation required at construction time;
4. retains typed dependency inputs as explicit dependencies, in the forms admitted by `contracts/pins.md`;
5. returns a frozen Transformation definition with its own execution promise.

Consequently, building can raise for malformed arguments or concrete inputs even though it does not execute transformation code. Mutating the builder, its original input objects or its configuration after the build does not alter the returned Transformation.

For a bound Transformer, an explicit build snapshots the node's current builder configuration and input bindings into a detached Transformation. It does not return the Context's transient run object and does not make that snapshot the node's new durable state.

### Contract change: a mode-independent build operation

**Contract ahead of code.** The pre-contract implementation has no `build()` method. Its inherited `transformation()` is implemented as `self()`, so a direct Transformer's `transformation()` follows the direct `__call__` override and returns a value rather than a Transformation; it also accepts no call arguments. `get_transformation()` inherits the same problem.

The contract changes this:

- add `build(*args, **kwargs)` as the canonical snapshot operation;
- make `transformation(*args, **kwargs)` and `get_transformation(*args, **kwargs)` exact aliases;
- make all three return a Transformation without executing it, regardless of call mode;
- implement named standalone launch methods from `build()`, not from `self()`, so directness cannot change their meaning through dynamic dispatch.

`build()` is the semantic boundary. `__call__` is convenience syntax layered on top of it.

## Delayed and direct calls

Delayed and direct Transformers are the same kind of builder. They differ only in `__call__`:

```python
delayed_tf(*args, **kwargs)  # delayed_tf.build(*args, **kwargs)
direct_tf(*args, **kwargs)   # direct_tf.build(*args, **kwargs).run()
```

Directness does not change builder state, binding, pins, snapshot identity or the meaning of named methods. The decorators and call-time behavior are specified in `contracts/direct-delayed-and-transformation.md`.

## Named work methods

The named methods do not inherit direct-call sugar:

| Operation | Standalone Transformer | Bound Transformer |
|---|---|---|
| `build()` / `transformation()` | return a detached immutable Transformation | return a detached immutable snapshot of the current node definition |
| `compute()` | build, execute and return the result checksum | demand the live node and wait on its Context barrier |
| `computation()` | asynchronous form of standalone computation | asynchronous Context barrier for the live node |
| `run()` | build, execute and materialize the result | demand the live node and materialize its result |
| `task()` | build and return the Transformation's async task | operate through the live node |
| `prune()` | unavailable (`AttributeError`) | reclaim superseded work in the node's downstream cone |
| `clear_exception()` | unavailable (`AttributeError`) | clear the node failure according to the workflow lifecycle |

Exact execution, cancellation and error behavior remains in the Transformation, Context and node-lifecycle contracts. This table fixes only whether an operation targets a detached snapshot or the live bound node.

`result`, `state`, `block_reason` and `exception` likewise describe a live workflow node and are bound-only. The corresponding facts for a detached computation live on the Transformation returned by `build()`.

## Binding

Assigning a standalone Transformer to a Context binds it:

```python
ctx.tf = tf
```

**Binding is a move, not a copy.** The builder state moves into the transformer node and the standalone private shadow is abandoned. The node becomes the single source of truth; there is no interval in which mutations must be mirrored between two owners.

Every later `ctx.tf` returns a fresh Transformer view onto that node. Handle identity carries no meaning: two views are interchangeable, and dependencies are recorded by node path and content rather than Python object identity. Deletion and Context closure make existing views stale or closed as specified in `contracts/workflow-context.md`.

The Context stores the node and its builder configuration, **not a persistent Transformation object**. When an input changes, the Context builds a fresh immutable Transformation from the new snapshot and submits it. The snapshots it fires are private runtime artifacts; an explicit `ctx.tf.build()` is a detached user snapshot.

## Pins and result

`tf.pins` exposes the Transformer's input slots. The pin collection is part of builder state, but Pin is its own handle with its own contract; see `contracts/pins.md`.

`tf.celltypes.result` configures the Transformation's result celltype. A bound Transformer additionally exposes `tf.result`, a read-only view of the node's output. A standalone Transformer has no live result endpoint: its output belongs to each Transformation it builds, so accessing `tf.result` raises `AttributeError`.

A producer operation may target a pin but may not target a bound Transformer's result. Context wiring and the resulting error are specified in `contracts/workflow-context.md`.

## Ordinary and compiled Transformers

The factory's Python and Bash results provide ordinary callable or text-source builders. `Transformer(language, compiled=True, direct=...)` extends the same builder contract with compiled-language configuration.

The common rules on modes, binding, pins, snapshots and named work methods do not vary by language. The compiled contract owns schemas, native source, generated headers, marshalling, compilation, compiled objects and compiled result packaging; none of those rules are repeated here. See `contracts/compiled-transformers.md`.

## Non-goals

- **Transformation execution.** Building freezes a definition; execution backends, result promises, immutability after construction and cancellation belong to `contracts/direct-delayed-and-transformation.md` and its linked execution contracts.
- **Pin semantics.** This page names pins as builder state but does not own their declarations, writes, conversions, null rules or failures (`contracts/pins.md`).
- **Context scheduling.** Reactive invalidation, barriers, speculation and graph serialization belong to `contracts/workflow-context.md` and `contracts/node-state-lifecycle.md`.
- **Compiled-language semantics.** They belong to `contracts/compiled-transformers.md` and its linked schema and compiled-pin contracts.
