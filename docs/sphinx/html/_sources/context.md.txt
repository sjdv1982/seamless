Contexts
========

The seamless.highlevel.Context class is a wrapper around a *workflow graph*, that contains of
cells, connections, and workers (primarily transformers). By convention, a Context is called `ctx`.

If `ctx.a` does not exist yet, then `ctx.a = X` :

- will create a new cell `ctx.a` if X is a constant. `ctx.a` will be bound to `ctx` and have the value X. The celltype will be "mixed". This means that X must be either JSON-serializable, or a Numpy array, or a mixture of both.
- will create a new transformer `ctx.a` if X is a Python function. The transformer will copy the source code and function signature of X (see the documentation of the Transformer class for more details).
- will bind X to `ctx.a` if X is a cell, transformer or context that is not bound to a context.
- will create a new cell `ctx.a` if X is a cell, subcell, transformer outputpin etc. that is already bound to `ctx`. Then, a connection from X to `ctx.a` is created.
- will create a new cell `ctx.a` if X is a transformer that is already bound to `ctx`. Then, a new connection from ```X.result```  to `ctx.a` is created.

Cell values (and the workers' input and output values) are stored as the *checksums* of their data buffers. Therefore, the workflow graph is always well-defined, yet small in size.

Seamless maintains a checksum-to-buffer cache, either in memory or in a database. It can also query remotely connected Seamless instances.

The Context class can launch a *translation* of the workflow graph to
a low-level representation that can be evaluated.

The workflow graph consists of *dependent* and *independent* checksums. Independent checksums correspond to the code and the input parameters that have been directly defined by the programmer or the user. *dependent* checksums are the result of a computation, such as a transformer, a subcell expression, or a cell conversion. Parts of the graph that are under macro control (this includes the library instances of much of the stdlib) are also dependent.

During evaluation, all dependent checksums of the workflow are computed. In principle, the independent checksums are constant, i.e. immutable: modification of the workflow via the Context class creates a *new* workflow that is re-translated and re-computed. However, the low-level representation also supports the modification of independent checksums, as it is capable of canceling the downstream dependent checksums and re-launching their computations. This means that independent checksums can be modified without re-translation. Any changes in the topology (cell types, new cells, new transformers, new connections, etc.) do require translation. If this is not desired (for example in a web interface), the topology generation must be under macro control.

In the graph, each transformer performs a transformation from input + code to result. Seamless keeps a result cache of all transformations. Just like the checksum-to-buffer cache, databases or remote Seamless instances can also be queried. Because of this, the only transformations that are performed are those that have never been performed anywhere before, or where the result value is no longer accessible.

Before any computation starts, a context has to be translated (using
`ctx.translate()` or `await ctx.translation`). Implicit translation is done if
`ctx.compute()` is invoked.
Changing the topology of the graph (e.g. adding a cell) or changing the cell types
only takes effect upon re-translation. The modification of cell *values* does not
require re-translation. This is because translation creates a low-level context
that does the work and holds the data. Most of the methods and properties of the
Seamless high-level classes (Cell, Transformer, etc.) are wrappers that interact
with their low-level counterparts. Seamless low-level contexts accept value changes
but not modifications in topology.

See `http://sjdv1982.github.io/seamless/sphinx/html/reference.html#context-class` for more documentation.