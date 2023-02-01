# Seamless explained

This document is for experienced developers. If you are a beginner in programming, you are recommended to read [the beginner's guide](http://sjdv1982.github.io/seamless/sphinx/html/beginner.html) instead.

## Core concepts

First, Seamless is a framework for *interactive* programming and scripting. There are essentially two ways that you can do this. The first is file-based, like the bash shell. The second is cell-based, such as IPython, Jupyter, or a spreadsheet. Seamless follows the cell-based approach.

Second, Seamless is a framework for building *workflows* (dataflow programming), i.e. dependency graphs. There are essentially three ways you can do this: stream-based (NoFlo), file-based (NextFlow, Snakemake) or cell-based (Jupyter, Excel). Again, Seamless follows the cell-based approach.

Third, Seamless is a framework for *reproducible* computation.
The idea is that by following some simple rules in your code, you gain reproducibility and interactivity for free. Unlike interactivity, which is everywhere in Seamless, reproducibility is mostly hidden from the user.

In a nutshell, most of Seamless revolves around ***cells***, that hold the data and code, and ***transformers***, that do reproducible computation. Transformers take cells (including code cells) as input and have a single cell as output.

### Checksums

What makes Seamless special is that cells don't hold values or filenames, but ***checksums*** (aka hashes, aka content-addressed storage). This has several implications. First, unlike e.g. NextFlow, you aren't tied to a complex hierarchy of files. Although in Seamless you *can* mount a cell to a file, it just means that the cell's checksum tracks the file content when it changes (and vice versa). Computations can be executed anywhere, without copying over any files first. Second, it means that copying a cell is always free in terms of space, in the same way that a hardlink to a file is always free (but copying a file or value is not). Third, although they give the illusion of wrapping an in-memory value, Seamless cells do no such thing. They just contain checksums, and data values are obtained only when they are needed. Checksums are small, and a workflow description with checksums is small, but their underlying data can be much larger than what fits in memory, or on disk. In other words, big data is possible with Seamless.

On the flip side, you can't automatically assume that you have a cell's data at your fingertips. By default, Seamless sets up a simple in-memory checksum-to-data store, but that reintroduces some of the problems (potential memory issues, file copying) of using files and values instead of checksums. These problems can be reduced or eliminated by manually configuring your data storage.

The final implication is that since transformers are also based on checksums, and since these checksums fully describe the computation (input *and* code *and* result), you can replace a computation with its result, and replace a result with its computation (referential transparency). This is very beneficial for ***reproducibility***, and it provides ***reactivity***: after cell updates, it is always obvious which computations need to be re-executed. No need for manual re-execution (Jupyter) or reliance on file modification times (Snakemake). Finally, it means that computations are small to describe, and can run anywhere, as long as they can locate the data of their input checksums. More details are in the transformation section.

### Interactivity

Seamless has four features that contribute to interactivity.

First, based on the reactivity explained above. You can essentially re-run the entire workflow continuously without much cost, because recomputation only happens if something changes.

Second, while the workflow remains running, you can always modify it in IPython/Jupyter. Both the topology of the workflow and the inputs can be modified (see "How interactive modification is treated" for details).

Third, Seamless allows cells to be ***synchronized***. There are two mechanisms for this. The first mechanism is that during development, cells can be synchronized (mounted) to the file system. In this way, you can define a code cell initially in a Jupyter Notebook, but then link it to a source code file under Git version control that you can edit with a standard text editor or IDE. The synchronization is two-way, which means that the file contains the cell buffer, and that the cell contains the file checksum. During deployment, the file is no longer needed (or used), although the cell buffer must be retrievable from somewhere.

The other mechanism of synchronization is over HTTP. You can expose cells as read-only, allowing their value to be read in the browser (HTTP GET), or as read-write, so that they can be modified (HTTP PUT). There is also a websocket port where you can receive notifications from Seamless when a cell has been updated. Seamless includes a simple Javascript client that uses all of this to synchronize cell values bidirectionally between Seamless and the browser. This is how you build web interfaces that are fundamentally interactive.

In Seamless, there is no sharp difference between user and programmer. All sources of interactivity are treated the same: change of a cell over HTTP, change of a cell linked to the file system, or modification of the entire workflow via IPython. From Seamless's point of view, they are all acts of programming, although the user of a web interface normally has a very limited "API" at their disposition. You *can* allow actual programming via the web interface, by exposing code cells in read-write mode and link them to textarea editor elements in your HTML page. If you really want to.

Fourth, Seamless aims to be very modifiable. For example, you can add support for a new programming language dynamically, while the workflow remains running. For another example, there is a web interface generator that you can completely customize or rewrite, again while the workflow remains running. Seamless workflows are stored in one or two checksum graph files that define every modification, including these two examples.

### Using Seamless as a reactive web framework

Seamless's automatic reactivity and interactivity makes it very convenient to make a certain type of web services. No matter what, you don't have to write server code that explicitly handles dynamic change, while this is required if you use Django or Flask or any of those web frameworks. ***Seamless workflows don't handle dynamic change, because there is none***. Whenever something changes, Seamless effectively discards the old workflow and replaces it with a new workflow. All computations that were excuted before by the old workflow (or that were ever executed by any workflow at all!) are automatically re-used. In that sense, Seamless is more similar to a traditional static CGI web server, which doesn't require any dynamic change either.

However, the big difference with a static web server is that a dynamic, reactive web server must always be live: there must always a Seamless process that listens for HTTP updates. You can't simply wait until the user submits a static webform with all the parameters and then fire up your workflow. Likewise, the browser must be live too, and listen from continuous updates from the server, but this is easy to do nowadays (web sockets).

### Cells

A cell is essentially a container that holds a *checksum* (a SHA3-256 hash). A checksum corresponds to a *buffer* (the raw bytes). This correspondence is one-to-one: each buffer has a unique checksum and vice versa. Finally, the *celltype* describes how the buffer is to be interpreted (*deserialized*) into a *value*.

For example, celltype "plain" means a conversion to a Python string (which means UTF-8 decoding) followed by loading the string as JSON. Likewise, to go from value to buffer (*serialization*), a value of celltype "plain" is first converted to a JSON string, and then encoded (using UTF-8) into a buffer.

Concretely, the buffer `b'42\n'` corresponds to the value `42` for celltype "plain", and vice versa.

There are about a dozen celltypes in Seamless. For example, celltype "binary" is for structured binary data, which is deserialized into Numpy arrays (or C/C++ structs). Celltype "bytes" is for raw binary data; Seamless does not (de)serialize it at all, it is up to the transformer to parse it (example: a PNG image). There is also a celltype "code" for transformer code.

Using the Seamless API in Python gives the *illusion* that Seamless cells are containers of *values*, just like:

- variables in Python

- code cells in Jupyter

- value cells and formula cells in Microsoft Excel.

However, internally, whenever you *set* the value of a cell:

- Seamless serializes the value to a buffer, using the celltype.

- Seamless calculates the checksum of the buffer.

- Seamless stores the checksum in the cell. The cell does not store the value or buffer.

Likewise, when you *ask* for the value of the cell:

- Seamless reads the cell's checksum.

- Seamless retrieves the buffer corresponding to the checksum.

- Seamless deserializes the buffer into a value, using the celltype.

#### Demonstration

Define a cell with a value "testvalue"

```python
from seamless.highlevel import Context, Cell
ctx = Context()
ctx.a = Cell("plain").set("testvalue")
ctx.translate()
```

The checksum, buffer and value can then be obtained as:

```
>>> print(ctx.a.checksum)
93237a60bf6417104795ed085c074d52f7ae99b5ec773004311ce665eddb4880

>>> print(ctx.a.buffer)
b'"testvalue"\n'

>>> print(ctx.a.value)
testvalue
```

With `ctx.resolve`, buffers and values can be obtained in a generic way:

```
>>> print(ctx.resolve(
    "93237a60bf6417104795ed085c074d52f7ae99b5ec773004311ce665eddb4880"
))
b'"testvalue"\n'

>>> print(ctx.resolve(
    "93237a60bf6417104795ed085c074d52f7ae99b5ec773004311ce665eddb4880",
    "plain"
))
testvalue
```

#### Subcells

Another important feature of Seamless is support for subcells, which correspond to *partial checksums*, i.e. the checksum of a part of the cell data. This part is defined by an *attribute path*: this can refer to a single attribute (e.g. `Cell.x`), but indices (`Cell[0]`) and attributes-of-attributes (`Cell.x.y` or `Cell.a[0].z`) are also supported. See [the cell documentation](http://sjdv1982.github.io/seamless/sphinx/html/cell.html) for a demonstration).

### Transformations

Computation in Seamless is delocalized. You can run it locally on your machine, but when your data or computation grows large, you can configure Seamless to delegate computations to a remote location.

In principle, there are five ways to do that:

- Remote Procedure Call (RPC). There are many frameworks that can do this, for example ipycluster and execnet. In essence, everything is packaged into a single command message that is sent to the remote service. All of the input values and code are serialized (pickled) and the remote service is asked to execute the command. This is reproducible, since the result is completely defined by the command message. But the command message can be extremely big, since it embeds all input values.

- Remote execution using file names. This is what Slurm does for single computations, and NextFlow/Snakemake for workflows. The command messages are small, but they rely on a shared file system. Organizing files into inputs, outputs, versioned banks etc. requires mental effort and discipline. Reproducibility is an issue: there is no guarantee that a file name always refers to the same value. File modification time is used to detect this, but this only works within the same file system. Federation is therefore not easily possible: sharing files is difficult (files can be big) and fragile in terms of reproducibility (need to preserve modification times). If command line tools are sloppy (creating hidden output files that are implicitly needed by downstream tools, or having implicit file dependencies), some very strange errors can happen. See "Don't rely on file names" for an example where this can go wrong.

- Remote execution using URLs. This is essentially the same as file names, but using the Internet as a global file system. Federation is much easier, but reproducibility (already hard) is now much harder (no control over remote sites, cannot use modification times). Requires immense discipline in using globally unique identifiers for URLs.

- Remote execution inside an environment (conda, Docker container). This works well if the environment is popular and stable, i.e. you can re-use the same environment over and over again. If the environment itself is under active development, this method is a disaster.

- The fifth method is how Seamless does it. Remote execution is done by providing the checksums of the inputs and of the code. This is what Seamless call a *transformation*. The remote service is then responsible to retrieve the corresponding input buffers. This means that a computation is always well-defined, but not always executable: it may fail if one or more buffers cannot be found. In contrast, in the first three methods, a computation becomes only well-defined when it becomes executable.

#### Transformers vs. transformations

A transformer is essentially a container that holds a transformation. A transformer has cells as input, whereas a transformation has the checksums of those cells as input.

A transformation describes a unique computation that transforms the input checksums (including the code checksum) into a result checksum. Each input checksum has a name and a celltype. When the transformation is executed, each input checksum is converted to a variable with the same name, and whose value is obtained in the same way as for cells. Likewise, after the transformation has finished, the result variable is retrieved, serialized and checksummed.

#### Types of transformations

Seamless allows a transformation to contain an *environment*: as a Docker image, a conda environment definition, or a list of command line tools that must be available. This is a bit informal and should be used with care when it comes to reproducibility. See the [documentation of environments](http://sjdv1982.github.io/seamless/sphinx/html/environments.html) for more details.

In addition, Seamless transformers can in principle be written in any language. Python/IPython transformers are executed directly. Interpreted languages (e.g. R) are executed via a bridge to IPython (e.g. using rpy). Bash transformers are executed using a special Python function. So are compiled transformers (e.g. in C++) after compilation.

The following combinations of language and environment are currently possible for Seamless transformations:

- Transformers written in bash, with no environment (pure UNIX commands)
- Transformers written in bash, with a Docker image environment.
- Generic transformers (Python, compiled, bash, etc.), with no environment
- Generic transformers, with a conda environment.

#### Deployment of transformations

Each Seamless instance is able to do its own computation, but during deployment, this is normally not very efficient. So Seamless has a protocol (communion protocol) where a Seamless instance can delegate transformation requests (jobs) to another Seamless instance (a jobslave) or to a dedicated job manager (jobless). Transformation requests can then be delegated further, e.g. to a job slave on a HPC cluster. See [job management](http://sjdv1982.github.io/seamless/sphinx/html/job_management.html) for more details.

Then, from a deployment viewpoint, a Seamless instance can be seen as a black box, where cell values come in (e.g. via HTTP) and a stream of transformation requests come out. The transformation requests are small, as they contain only checksums.

The communion protocol can also exchange buffers, but it is easier if both the Seamless instance and the job slave have access to the same Seamless database (see [documentation](http://sjdv1982.github.io/seamless/sphinx/html/data_storage.html)).
In that case, the buffers corresponding to the input checksums will have been pre-deposited by the Seamless instance, so only the transformation needs to be sent. After computation, the jobslave will deposit the result checksum for that transformation, and the corresponding buffer. The Seamless instance needs to interrogate only the database to retrieve the results.

## Essential mechanics

### Asynchronous tasks

As shown in the "Cells" section above, `Cell.set(value)` is implemented in Seamless as three tasks: serialization, checksum calculation, and update of the cell's checksum. As a user, you don't work with tasks directly, but understanding them is important to predict the performance of a workflow.

All tasks in Seamless are ***asynchronous***. See [the cell documentation](http://sjdv1982.github.io/seamless/sphinx/html/cell.html) for a demonstration. When an "update" task gets executed, all downstream dependencies get canceled and become pending. Tasks get re-executed when their input changes. Tasks are executed concurrently within the main Seamless process. However, transformation tasks are executed in parallel, either inside a forked subprocess (default) or by remote execution.

Altogether, Seamless has the following tasks (*):

- Serialization (value to buffer)
- Deserialization (buffer to value)
- Checksum calculation (buffer to checksum)
- Updating a cell checksum
- Conversion between cell types
- Updating an "accessor", which describes a dependency/connection.
- Evaluating an "expression", which is the attribute path to derive a partial checksum from a full checksum (see "Subcells" above), followed by a cell type conversion.
- Joining partial checksums into a full checksum (for structured cells), and validating the result.
- Macro/reactor execution (advanced features, mostly hidden from the user)
- Transformer execution

<!--
Seamless has support for preliminary outputs ...
(Need to fix eager cells before this is useful? or not?)
-->

(*) To be complete, `Cell.set` and `Cell.set_buffer` are also wrapped in their own tasks (that invoke the other tasks). This is so that they can be cancelled by another `Cell.set` (or if the cell is destroyed) during execution.

### Reproducibility and pure functions

To be reproducible, transformer code must have the following requirements:

1. It must run in isolation from the rest of the workflow, communicating only via inputs and outputs. This requirement is already enforced by Seamless.

2. It must be deterministic. Given the inputs, a transformation must either fail (e.g. lack of resources) or give a constant result that is independent of hardware. Code that uses a random generator must take an explicit random seed as an input. Within a transformer, you are free to create threads or subprocesses for parallel execution, but take care, parallel code is not always deterministic.

3. No side effects are allowed. More precisely: the *result* may not depend on side effects (e.g. writing to a log is okay). Side effects include reading from arbitrary files, URLs or databases. This can be relaxed a little bit by including files (or databases) inside the environment. Since these files are constant, reading from them does not count as side effects. See "Don't rely on file names or URLs" for details.

These requirements roughly correspond to the definition of "pure functions". They apply primarily to transformer code; other Seamless tasks (such as deserialization and checksum calculation) are pure functions by themselves. Transformer code is nearly (*) the only case where custom code is executed.

Seamless workflows as a whole are also pure functions. Notably, interactive modifications are *not* treated as a source of side effects. Therefore, there is no need for monads or event streams or other complex mechanisms to deal with side effects in a purely functional context. Each interactive modification simply creates a completely new workflow, that just happens to be very similar to previous workflows. History doesn't matter.

You are *not* required to write transformer code in a purely functional language. Seamless is polyglot, you can in principle use any programming language for your transformers.

(*) The other cases are: macro code, library constructor code, ipy templates and Python bridges. These are all uncommon special cases where the purpose is syntax rewriting, which is naturally pure.

### How interactive modification is treated

In theory, every interactive modification results in a brand new workflow. In practice, for technical reasons, Seamless distinguishes between two kinds of modifications: topology and inputs. This is because Seamless workflows exist at two levels: the high level and the low level.

#### High level versus low level

The Seamless high level is primarily a wrapper around the workflow graph: simple, inert data. `ctx.get_graph` returns this almost exactly in its internal representation. Most properties and methods of the high level classes, such as `Cell.celltype`, simply access and manipulate this data.

In between the levels is the Seamless translation machinery, invoked by `ctx.translate`. This operates on the workflow graph and generates a low-level representation: for each high-level Cell, there will be a low-level Cell. As above, so below. It is on this low-level workflow (the "livegraph") that all the Seamless tasks operate.

The high-level and low-level workflows are connected in two ways:

- The top high-level Context `ctx` contains a reference to its low-level counterpart `gen_context`. Paths within the two contexts are the same: if there is a high-level Cell `ctx.subctx.a`, the low-level Cell will also be `gen_context.subctx.a`. Each high-level instance knows its own path, so it knows how to access its low-level counterpart. Property getters such as `Cell.value` and `Context.status` are directly forwarded to the low level.

- High-level cells, transformers etc. are registered as observers of their low-level counterparts. Whenever the checksum at the low-level changes, the high level is informed and the checksum is stored in the workflow graph.

#### Changes in topology

A modification in the *topology* is: creation or deletion of elements (cells, transformers, etc.) or their connections, or changes in their types (including cell types and transformer languages). Such modifications result in a brand new workflow, but not automatically. The reason is that it is mildly expensive (in the order of tenths of seconds) to destroy the old low-level workflow and to build a new one. Therefore, this is done explicitly using `ctx.translate`.

At the low level, topology is constant and must be pre-declared. If you wish, you can write low-level syntax directly, see [the documentation on the low level](http://sjdv1982.github.io/seamless/sphinx/html/low_level.html) for details.

#### Changes in inputs

The workflow *inputs* consist of all cell checksums that are *independent*, i.e. that have been directly defined by the programmer or the user. In contrast, *dependent* cell checksums are the result of a computation, such as a transformer, a subcell expression, or a cell conversion.

The low-level workflow supports the interactive modification of independent checksums, as it is capable of canceling the downstream dependent checksums and re-launching their computations. This means that independent checksums can be modified without re-translation. Methods that do so, such as `Cell.set`, are directly passed on from the high level to the low level.

#### Special cases: libraries and macros

Seamless has two graph-rewriting classes: libraries and macros. Both of them synthesize new workflow topology based on the values of their inputs. Libraries work at the high level, and macros work at the low level.

Library instances take value parameters as inputs, and do their graph rewriting during translation: when you modify a parameter, the change is only taken into account at `ctx.translate`. In addition, some libraries also have cells as input, these are statically connected to the generated topology. Changes in the values of those cells do not require translation, but do not change the topology either, unless the library contains macros.

Macros take cells as input, and generate a low-level subcontext based on the input cell values. Like transformers, they get re-executed whenever an input changes. Therefore, macros are used to dynamically generate topology based on variable input values, without the need for re-translation. Macros are an advanced low-level feature, not often used directly, but libraries such as `stdlib.map` use them heavily. See [the documentation on the low level](http://sjdv1982.github.io/seamless/sphinx/html/low_level.html) for more details on macros.

All topology generated by library instances and macros is read-only. All their cell checksums are dependent and cannot be modified.

### Caching and performance

Many tasks in Seamless have some kind of caching. For e.g. deserialization, this is a small LRU cache to increase performance. As a user, you don't interact with caches directly, and they can be disabled to save memory. However, just like tasks themselves, it can still be useful to learn about caches, so that you can predict the performance of a workflow. Of the four caches that impact performance the most, three are discussed below. The fourth one, the elision cache, is discussed in [the deepcell documentation](http://sjdv1982.github.io/seamless/sphinx/html/deepcell.html). That documentation also discusses other performance considerations related to very large workflows and incremental computing.

#### Checksum-to-buffer cache

There are is one cache that is absolutely essential for understanding the running of your workflow: the checksum-to-buffer cache. This cache is not just there for performance reasons. The correspondence between checksum and buffer is one-to-one, but you can only compute the checksum from a buffer, not the other way around. Therefore, it is critical that for each checksum, the corresponding buffer is available where needed. If not, a CacheMissError for that checksum will be raised and the task aborted.

By default, Seamless keeps an in-memory checksum-to-buffer cache (with refcounting) for all *independent* checksums in the workflow. Dependent checksums are also in this cache, but they get regularly evicted. Since buffers can be rather large and numerous, the checksum-to-buffer cache can easily consume a lot of memory.

Besides this cache, there are three other ways to retrieve a checksum's buffer.

- It is possible to set up a Seamless database with the `seamless-database` command. The database stores buffers on disk and makes them available over HTTP. If a database is found, the in-memory checksum-to-buffer cache is disabled. Therefore, setting up a database is an easy way to reduce the memory footprint of a Seamless workflow. Under certain circumstances, a Seamless database may also provide Seamless with file names, which may avoid a buffer to be loaded into memory at all. See [data storage](http://sjdv1982.github.io/seamless/sphinx/html/data_storage.html) for more details.  

- Buffers of dependent checksums can also be computed on-the-fly ("fingertipping", see below).

- Finally, it is possible to define a list of last-resort buffer servers (\$SEAMLESS_BUFFER_SERVERS). By default, it contains the RPBS buffer server, so that `https://buffer.rpbs.univ-paris-diderot.fr/<checksum>` will be contacted.

#### Buffer info cache

Sometimes very large buffers must be converted between different cell types. In many cases, Seamless can reason that a conversion is trivial (e.g. from plain to mixed) or impossible (e.g. from binary to plain). In other cases, conversion can be done from the buffer alone, without deserializing into a value.

The buffer info cache contains buffer characteristics that help with conversion: for example, any buffer that is not UTF-8 cannot be deserialized as text or plain. The buffer info cache may also contain the length of the buffer and the actual checksums of known conversions.

Buffer info caches are small, and Seamless holds a local in-memory cache for every locally known buffer checksum. In addition, if there is a Seamless database, it too is contacted with buffer info requests and updates.

#### Transformation cache

A transformation can be represented as a single checksum (of the JSON serialization of a dict of input checksums). Its result is also a single checksum. Therefore, transformations can be cached with a small checksum-to-checksum dict, and Seamless maintains a local in-memory cache for all locally known transformations.

In addition, if there is a Seamless database, it too is contacted with transformation cache requests and updates.

Upon changes in inputs, Seamless cancels and re-executes only the downstream transformations of the affected inputs. Re-executed transformations are looked up in the transformation cache. For example, given the following workflow:

```python
ctx.ab = 2, 3

def add(a, b):
  return a + b

ctx.tf1 = add
ctx.tf1.a = ctx.ab[0]
ctx.tf1.b = ctx.ab[1]
ctx.result = ctx.tf1

ctx.tf2 = add
ctx.tf2.a = ctx.result
ctx.b2 = 3 
ctx.tf2.b = ctx.b2
ctx.compute()

ctx.ab.set([3, 2])
ctx.b2.set(3)
```

Here, after `ctx.ab.set([3, 2])`, both tf1 and tf2 will be marked for re-execution. However, once tf1 has been executed, tf2 gives a transformation cache hit, because its inputs are still a=5, b=3.

`ctx.b2.set(3)` will only mark tf2 for re-execution. Once the checksum of `3` has been computed, tf2 will give a cache hit since nothing has changed.

Note that the transformation cache is universal, in the sense that a) the *name* of the transformer is not part of the cache, and b) it's not just the previous version of the workflow that may give a cache hit, but *any* known transformation. For example, after a new modification `ctx.ab.set([5, 3])`, it is now tf1 that gives a cache hit, re-using the previous result of tf2. Then, upon `ctx.ab.set([1, 1])`, it is tf2 that gives a cache hit, re-using the initial (not the previous) result (a=2, b=3) for tf1.

What happens when the workflow graph gets re-translated? In the above example, no topology changes have taken place, so adding a `ctx.translate()` at the end would do nothing. However, translation can be forced with `ctx.translate(force=True)`, or the topology can be modified first with e.g. `ctx.result.celltype = "int"`, followed by `ctx.translate()`. If you do this, a new workflow gets built, and all of its tasks are executed. *The old workflow gets completely destroyed, nothing is explicitly re-used*. However, both tf1 and tf2 give a transformation cache hit, so very little computation is actually re-done.

In the above examples, all cache hits come from earlier computations in the same IPython/Jupyter session. However, when a database is available, transformation cache hits may come from computations performed much longer ago, by other people. Such universal federation of computation results is not easy to set up with other workflow systems than Seamless.

#### Fingertipping

"Fingertipping" means the recomputation of *dependent* cells for which the checksum is known, but the buffer cannot be found. Local transformation cache is inspected to detect transformations that have the desired checksum as a result. Local and remote buffer info caches are inspected for known conversions into the desired checksum. Expression caches and the caches of joining tasks are likewise inspected. If there are hits, the input checksums of the transformation, expression, etc. are themselves fingertipped, and re-computation of the transformation, expression, etc. is performed. In short, Seamless tries to do every possible thing to make a buffer locally available, "at your fingertips".

If possible, fingertipping is automatically performed by e.g. `Cell.value`. Fingertipping is an asynchronous operation: invocation by blocking, synchronous code such as `Cell.value` can only work if there is no running event loop, so it will normally be skipped inside Jupyter. You can trigger it manually using `await Cell.fingertip()`.

Non-deterministic transformations can give a lot of trouble in Seamless. Because result checksums are dependent and can be fingertipped, large result buffers will quickly be evicted from checksum-to-buffer cache to save space (or from a database; databases do not delete buffers automatically, but they do mark them as dependent, so an external maintenance tool could certainly target these buffers for deletion). When recomputed, a non-deterministic transformation will however not give the desired result buffer, but a new one. There is a [GitHub issue](https://github.com/sjdv1982/seamless/issues/56) that could mitigate the problem, but the superior solution is to not write non-deterministic transformer code in the first place.

### Limitations of workflow graphs

Like other workflow systems, Seamless workflows are directed acyclic graphs (DAGs), which have certain limitations. In particular, DAGs are declarative and can't have cyclic dependencies, i.e. an output cannot depend on itself. This means that you can't use `if` statements or `for` or `while` loops to describe a Seamless workflow. You *can* use `if`, `for` and `while` (in any programming language) inside your transformers. Also, you could mix them in with "outside" Python code to create the workflow (See the "Programming in two places" section). But you can't dynamically launch transformations in Seamless the way you can e.g. in Prefect 2.0 (or to a lesser extent, in NextFlow). There is a [GitHub issue](https://github.com/sjdv1982/seamless/issues/130) to add this feature to Seamless, if it is needed.

In addition, Seamless has a number of features to work around this limitation. Using the standard library, you can use `stdlib.switch` and `stdlib.select` to emulate if statements, and `stdlib.map` to emulate for loops (dynamic data parallelism). In advanced cases, you could write your own libraries and macros to rewrite the graph, or use reactors to create self-modifying graphs. See also the "Special cases: libraries and macros" section above. [The documentation on the low level](http://sjdv1982.github.io/seamless/sphinx/html/low_level.html) contains more details on macros and reactors.

## Guidelines for experienced developers

### Keep it simple, while you can

The beginner's guide's section on "how to keep it simple" contains good advice for a small, young project. With Jupyter, you can quickly set something up, adding Seamless's interactivity to Jupyter's own. This works best for workflows that don't have too many steps, where the data is rather small, and the code too.

When the code gets more complex, you should move away from Jupyter by mounting your code cells to files. Code that modifies the workflow becomes throw-away code. See "Moving away from Jupyter" for more details.

When the data gets bigger, or execution becomes time-consuming, you should start thinking about [data storage](http://sjdv1982.github.io/seamless/sphinx/html/data_storage.html) and [job management](http://sjdv1982.github.io/seamless/sphinx/html/job_management.html). With default settings, Seamless transformations are parallelized on your local machine and cached in memory, and you may want to change that. If the data gets really big, you should bring the computation where the data is. But even in that case, try to have a small-data version of your workflow that executes fast, so that you can modify the code easily and interactively. Whitelists work very well for this ([see deep cells](http://sjdv1982.github.io/seamless/sphinx/html/deep_cells.html) for more details).

If either the code or the data gets bigger, you should start thinking about version control, and whether or not to use `seamless-new-project`. See [the documentation for creating a Seamless project](http://sjdv1982.github.io/seamless/sphinx/html/new-project.html) for more details.

### Programming in two places

Clearly distinguish between the "outside" code that *creates* the workflow, and the "inside" code (mostly within transformers) that is executed as part of the workflow. Inside codes are polyglot and executed in isolation (from each other, and from the outside). Outside code is written in Python, and you run it inside IPython or Jupyter. You don't need to keep outside code, because you can store the entire workflow as data. The "Programming in two places" section in the beginner's guide explains it in slightly more detail.

The "Moving away from Jupyter" section below explains that you should mount your code cells to the file system, and then remove their code from the notebook. Once it has thus become part of your workflow, Seamless will store the code (at least its checksum, and normally its content too), and you can also store it under Git version control as a file. Note that this applies only to "inside" code. In contrast, in a mature project, "outside" code that inspects or modifies the workflow should be considered ***throw-away code***. If you have moved away completely from Jupyter, you can simply use `seamless-ipython` to enter such code. Else, you can enter it in a temporary notebook cell, or use `seamless-jupyter-connect` to connect an IPython-like console to Jupyter. In all cases, you execute the code, but you don't keep it: instead, you simply save the state of the workflow in a `.seamless` file.

There is one use case where "outside" code may be kept. When it comes to describing the topology of the workflow (the steps and connections), you should normally rely on the status visualization web page (which you can modify, see "Edit the editor") or create your own flowcharts. But if that is not to your satisfaction, you do have the option to define your workflow topology from code. In that case, modify the Seamless project's `define_graph` function in `load-project.py`. If you do so, `await load()` will execute that code instead of loading the `.seamless` file, assuming that it will build the connections and cell mounts of the workflow. If you don't use a Seamless project at all, simply store the "outside" code in a script and run it.

### Moving away from Jupyter

Seamless gives the illusion of being like Jupyter, but with non-linear execution. The **web server demo** ([open on GitHub](https://github.com/sjdv1982/seamless/tree/stable/examples/webserver-demo), or [run on mybinder.org](https://mybinder.org/v2/gh/sjdv1982/seamless-binder-demo/main?labpath=webserver/webserver.ipynb)) gives an example where you start from a simple notebook and port it to Seamless, gaining an interactive web interface in the process. It is also about as far as you can push a Seamless workflow that is defined purely in Jupyter. Why is this? At the end of the demo, the next step would be to mount each code cell to a Python file, so that you can start modifying the calculation code of the workflow using a normal text editor or IDE. Whenever you save the file, the cell value is updated and the workflow recalculated. Each Python file can be put under Git version control, something that `seamless-new-project` sets up by default. However, the original unmodified code is still in the notebook! So if you re-run the notebook, and you re-mount the Python files, Seamless has to choose which version is correct: the one in the Python file, or the one in the notebook. In other words, either all of your modifications in the Python file get lost, or the code in the Python file supersedes the code of the notebook. By default, Seamless does the second thing (and gives you a warning), but it's ugly to have your notebook telling lies. It goes against the spirit of a notebook that tells a linear story on how you started from scratch and arrived at a result. And if then further modify the code also in the notebook, there will be no end of trouble. So in that case, the correct thing to do is to give up on the linear story and remove the now-outdated code from the notebook.

Another case is the web interface generator, which is all based on files (`webform.json`, `index.html`, `index.js`) that are being auto-generated but that can be modified. In fact, these files are Seamless cells of a secondary context `webctx` that are mounted to the file system (also see "Edit the editor"). Re-loading the notebook, executing cells that re-build the workflow bit-by-bit, is bound to give merge conflicts with a file that contains the modified web interface for the entire workflow in its final state.

In summary, ***once you start offloading your workflow to edited files, the time for linear notebook storytelling is over***. Does that mean that you should abandon Jupyter altogether? Not necessarily. You can keep Jupyter around as a dashboard, linking Seamless `Cell.traitlet` and `Cell.output` with ipywidgets. Or you can still use it as a scratch pad where you can quickly try out code, then incorporate it into your workflow when it seems to work, deleting it from the notebook.

Note that all of this applies primarily to "inside" code. In contrast, "outside" code is normally throw-away code. See "Programming in two places" for detail.

### Edit the editor

Seamless is meant to be very modifiable and malleable. Many features that one might expect to be built-in are in fact defined as a (piece of) workflow that can be interactively modified, while it remains running.

The best example of this is probably the web interface generator. Typically, a web service consists of two graphs (.seamless files). The first graph `ctx` contains the main workflow. The secondary graph contains the web interface generator. During development, both graphs are developed, which is made possible by `seamless-new-project` and `seamless-load-project`. See the [documentation of projects](http://sjdv1982.github.io/seamless/sphinx/html/new-project.md) and [of visualization](http://sjdv1982.github.io/seamless/sphinx/html/visualization.html). As described there, you edit the web interface at the level of parameters (webform.json), or by editing the web components, or by editing the generated HTML/JS web page by hand.

But you can edit the entire secondary workflow to your liking. You can modify the code to completely change the representation it generates. Since it is shared over HTTP, and could be consumed by a completely different program, e.g. a local GUI. Or, you could share the cell containing the original graph over HTTP with readonly=False, modify `load-project.py` to connect an observer (`Cell.traitlet().observe(...)`), and let the observer do `ctx.set_graph`. In that way, you can *control* the main workflow graph from a web interface (or the local GUI, or any other program), allowing visual programming.

### Environments

The beginner's guide's documentation recommends to install packages in the running Docker container. For mature projects, don't do that. Study the [documentation of environments](http://sjdv1982.github.io/seamless/sphinx/html/environments.html) instead.

### Don't confuse files and cell names

See the beginner's guide on "Don't confuse files and cell names". In addition, note that file mounting is something that happens only during development. When you save a workflow, the file's checksum gets incorporated into it. When you deploy a workflow (e.g. with `seamless-serve-graph`, Cloudless, or loading a .seamless file yourself), mounts are not needed to make the workflow run.

### Don't rely on file names or URLs

If you need external files or directories, add their *checksums* explicitly to the workflow (inside a normal cell for files, and inside a FolderCell or DeepFolderCell for directories). Else, reproducibility will be broken. The same applies for other external data sources, such as URLs or databases. In other words, reading an external data source must be *outside* code (see "Programming in two places") where you define a cell's value, and Seamless converts it internally to a checksum that becomes part of the workflow. This must be done inside IPython or Jupyter, and *not* inside transformer code. The transformer code never uses the original file name or URL, but operates directly on the content (retrieved by Seamless using the stored checksum). See the beginner's guide on "Don't rely on file names or URLs" for more details.

There is one exception to this rule: you may choose to embed external data sources in the environment, by installing them inside a Docker image. In that case, it is fine to refer to the file name of the data source inside transformer code. Reproducibility is guaranteed by the checksum of the Docker image, and you are highly recommended to include it in the Docker image name in `Transformer.docker_image` (e.g "jupyter/scipy-notebook@sha256:a891adee079e8c3eee54fef732cd282fe6b06c5fabe1948b9b11e07144526865" for a specific version of Jupyter). Of course, when your external data source changes, you must rebuild the Docker image and change `Transformer.docker_image` to reflect the new Docker image checksum.

### Use celltypes judiciously

By default, every cell is a structured cell. These are rich in features, in particular subcells and schemas. Schemas are good to use as much as possible. In particular, transformer code is not the correct place for validation, use schemas instead (see [validation](http://sjdv1982.github.io/seamless/sphinx/html/validation.html). You have the choice between adding a schema to Transformer.inp or to cells.

If you don't use a schema and don't need subcell access for a particular cell, then the "structured" celltype is overkill. Setting the celltype to something simpler may clarify the workflow. If many copies of the cell are created (e.g. inside a `stdlib.map` mapping context), a simple cell will be better for performance, especially if you can avoid conversions. For cells that hold very large buffers, consider a [deep cell](http://sjdv1982.github.io/seamless/sphinx/html/deep_cells.html.

All celltypes and their conversions are described in the [cell documentation](http://sjdv1982.github.io/seamless/sphinx/html/cell.html). Note that transformer pins have celltypes too. Their default celltype is "mixed", but they adopt the cell type of the first cell that they are connected to.
