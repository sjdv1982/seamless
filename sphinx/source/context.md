Contexts
========

The seamless.highlevel.Context class is a wrapper around a *dependency graph*, that contains of
cells, connections, and workers (primarily transformers). By convention, a Context is called `ctx`.

If `ctx.a` does not exist yet, then `ctx.a = X` :
- will create a new cell `ctx.a` if X is a constant. `ctx.a` will be bound to `ctx` and have the value X. All cell values must be either JSON-serializable, or a Numpy array, or a mixture of both.
- will create a new transformer `ctx.a` if X is a Python function. The transformer will copy the source code and function signature of X (see the documentation of the Transformer class for more details).
- will bind X to `ctx.a` if X is a cell, transformer or context that is not bound to a context.
- will create a new cell `ctx.a` if X is a cell or transformer that is bound to a context. Then, a connection from X to `ctx.a` is created.
- will create a new cell `ctx.a` if X is a transformer. Then, a new connection from ```X.result```  to `ctx.a` is created.

Cell values (and the workers' input and output values) are stored as the *checksums* of their data buffers. Therefore, the dependency graph is always well-defined, yet small in size.

Seamless maintains a checksum-to-buffer cache, either in memory or in a database. It can also query remotely connected Seamless instances.

The Context class can launch a *translation* of the dependency graph to
a low-level representation that can be evaluated.

During evaluation, the dependency graph is in principle constant, i.e. immutable.
Modification of the graph via the Context class creates a *new* graph that is re-translated and re-computed.

In the graph, each transformer performs a transformation from input + code to result. Seamless keeps a result cache of all transformations. Just like the checksum-to-buffer cache, databases or remote Seamless instances can also be queried. Because of this, the only transformations that are performed are those that have never been performed anywhere before, or where the result value is no longer accessible.

Before any computation starts, a context has to be translated (using `ctx.translate()` or `await ctx.translation`). Changing the topology of the graph (e.g. adding a cell) or changing the cell types only takes effect upon re-translation. The modification of cell *values* does not require re-translation.

See `http://sjdv1982.github.io/seamless/sphinx/html/reference.html#context-class` for more documentation.