# Seamless explained

This document is for experienced developers. If you are a beginner in programming, you are recommended to read [the beginner's guide](http://sjdv1982.github.io/seamless/sphinx/html/beginner.html) instead.

## Core concepts

First, Seamless is a framework for *interactive* programming and scripting. There are essentially two ways that you can do this. The first is file-based, like the bash shell. The second is cell-based, such as IPython, Jupyter, or a spreadsheet. Seamless follows the cell-based approach.

Second, Seamless is a framework for building *workflows* (dataflow programming), i.e. dependency graphs. There are essentially three ways you can do this: stream-based (NoFlo), file-based (NextFlow, Snakemake) or cell-based (Jupyter, Excel). Again, Seamless follows the cell-based approach.

In a nutshell, most of Seamless revolves around ***cells***, that hold the data and code, and ***transformers***, that do the computation. Transformers take cells (including code cells) as input and have a single cell as output.

### Checksums

What makes Seamless special is that cells don't hold values or filenames, but ***checksums*** (aka hashes, aka content-addressed storage). This has several implications. First, unlike e.g. NextFlow, you aren't tied to a hierarchy of files, carefully named and accessible on a mounted file system. Although in Seamless you *can* mount a cell to a file, it just means that the cell's checksum tracks the file content when it changes (and vice versa). Computations can be executed anywhere, without copying over any files first. Second, it means that copying a cell is always free in terms of space, in the same way that a hardlink to a file is always free (but copying a file or value is not). Third, although they give the illusion of wrapping an in-memory value, Seamless cells do no such thing. They just contain checksums, and data values are obtained only when they are needed. Checksums are small, and a workflow description with checksums is small, but their underlying data can be much larger than what fits in memory, or on disk. In other words, big data is possible with Seamless.

On the flip side, you can't automatically assume that you have a cell's data at your fingertips. By default, Seamless sets up some simple checksum-to-data stores, but that reintroduces some of the problems (potential memory issues, file copying) of using files and values instead of checksums. These problems can be minimized by manually configuring your data storage.

The final implication is that since transformers are also based on checksums, and since these checksums fully describe the computation (parameters *and* code *and* result), you can replace a computation with its result, and replace a result with its computation (referential transparency). This is very beneficial for ***reproducibility***, and it provides ***reactivity***: after cell updates, it is always obvious which computations need to be re-executed. No need for manual re-execution (Jupyter) or reliance on file modification times (Snakemake). Finally, it means that computations are small to describe, and can run anywhere, as long as they can locate the data of their input checksums. More details are in the transformation section.

### Interactivity

Seamless has three features that contribute to interactivity.

First, based on the reactivity explained above. You can essentially re-run the entire workflow continuously without much cost, because recomputation only happens if something changes.

Second, while the workflow remains running, you can always modify it in IPython/Jupyter. Both the topology of the workflow and the parameters can be modified.

Third, Seamless allows cells to be ***synchronized***. There are two mechanisms for this. The first mechanism is that during development, cells can be synchronized (mounted) to the file system. In this way, you can define a code cell initially in a Jupyter Notebook, but then link it to a source code file under Git version control that you can edit with a standard text editor or IDE. The synchronization is two-way, which means that the file contains the cell buffer, and that the cell contains the file checksum. During deployment, the file is no longer needed (or used), although the cell buffer must be retrievable from somewhere.

The other mechanism of synchronization is over HTTP. You can expose cells as read-only, allowing their value to be read in the browser (HTTP GET), or as read-write, so that they can be modified (HTTP PUT). There is also a websocket port where you can receive notifications from Seamless when a cell has been updated. Seamless includes a simple javascript client that uses all of this to synchronize cell values bidirectionally between Seamless and the browser. This is how you build web interfaces that are fundamentally interactive.

In Seamless, there is no sharp difference between user and programmer. All sources of interactivity are treated the same: change of a cell over HTTP, change of a cell linked to the file system, or modification of the entire workflow via IPython. From Seamless's point of view, they are all acts of programming, although the user of a web interface normally has a very limited "API" at their disposition. You *can* allow actual programming via the web interface, by exposing code cells in read-write mode and link them to textarea editor elements in your HTML page. If you really want to.

### Using Seamless as a reactive web framework

Seamless's automatic reactivity and interactivity makes it very convenient to make a certain type of web services. No matter what, you don't have to write server code that explicitly handles dynamic change, while this is required if you use Django or React or Flask or any of those web frameworks. ***Seamless workflows don't handle dynamic change, because there is none***. Whenever something changes, Seamless effectively discards the old workflow and replaces it with a new workflow. All computations that were excuted before by the old workflow (or that were ever executed by any workflow at all!) can be re-used. In that sense, Seamless is more similar to a traditional static CGI web server, which doesn't require any dynamic change either.

However, the big difference with a static web server is that a dynamic, reactive web server must always be live: there must always a Seamless process that listens for HTTP updates. You can't simply wait until the user submits a static webform with all the parameters and then fire up your workflow. Likewise, the browser must be live too, and listen from continuous updates from the server, but this is easy to do nowadays (web sockets).

### Cells

A cell is essentially a container that holds a *checksum* (a SHA3-256 hash). A checksum corresponds to a *buffer* (the raw bytes). This correspondence is one-to-one: each buffer has a unique checksum and vice versa. Finally, the *celltype* describes how the buffer is to be interpreted (*deserialized*) into a *value*. For example, celltype "plain" means a conversion to a Python string (which means UTF-8 decoding) followed by loading the string as JSON. Likewise, to go from value to buffer (*serialization*), a value of celltype "plain" is first converted to a JSON string, and then encoded (using UTF-8) into a byte buffer.

Concretely, the byte buffer `42\n` corresponds to the value `42` for celltype "plain", and vice versa.

There is also a celltype "python", which means that a cell can contain not only data, but also code.

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

### Dependent and independent data

***IMPORTANT: This documentation section is an early draft. The raw text material is shown below***

TODO: merge with the corresponding paragraph in context.md
...
By default, Seamless maintains a checksum-to-data cache in-memory that distinguish between *dependent* (computed) and *independent* data. Dependent data may get evicted ... TODO

- Independent vs dependent: history doesn't matter, creating a new workflow... syntax...
Deeper:
- Fingertipping, cache misses and irreproducibility (link to transformer)
- Resolving cycles...
- bidirectional link
- Async tasks (link to low_level.md)

### Caching

***IMPORTANT: This documentation section is a draft. The preliminary text is shown below***

TODO

- Various kinds of caches in Seamless

The checksum-to-buffer conversion cache is more than just for performance. The 
correspondence between checksum and buffer is one-to-one, but you can only compute 
the checksum from a buffer, not the other way around. Therefore,
it is essential that for each checksum, the corresponding buffer is available 
where needed. 

In addition, sometimes very large buffers must be converted between different cell 
types, e.g. from text to JSON. Caching the conversion will avoid the loading of 
the source buffer from wherever it is stored. Seamless also caches the length of
buffers and other info statistics, to reason if a conversion is a priori impossible
or trivial.

Finally, Seamless has a last-resort function to go from checksum to buffer. It is possible to define a list of buffer servers (\$SEAMLESS_BUFFER_SERVERS) and Seamless will try to contact them. By default, it contains the RPBS buffer server, so that `https://buffer.rpbs.univ-paris-diderot.fr/<checksum>` will be contacted.

### Transformations

Large scale computing means the deployment of computations to remote systems.

In principle, there are five ways to do that:

- Remote Procedure Call (RPC). There are many frameworks that can do this, for example ipycluster and execnet. In essence, everything is packaged into a single command message that is sent to the remote service. All of the input values and code are serialized (pickled) and the remote service is asked to execute the command. This is reproducible, since the result is completely defined by the command message. But the command message can be extremely big, since it embeds all input values.

- Remote execution using file names. This is what Slurm does for single computations, and NextFlow/Snakemake for workflows. The command messages are small, but they rely on a shared file system. Organizing files into inputs, outputs, versioned banks etc. requires mental effort and discipline. Reproducibility is an issue: there is no guarantee that a file name always refers to the same value. File modification time is used to detect this, but this only works within the same file system. Federation is therefore not easily possible: sharing files is difficult (files can be big) and fragile in terms of reproducibility (need to preserve modification times). If command line tools are sloppy (creating hidden output files that are implicitly needed by downstream tools, or having implicit file dependencies), some very strange errors can happen. See "Don't rely on file names" for an example where this can go wrong.

- Remote execution using URLs. This is essentially the same as file names, but using the Internet as a global file system. Federation is much easier, but reproducibility (already hard) is now much harder (no control over remote sites,  cannot use modification times). Requires immense discipline in using globally unique identifiers for URLs (discipline that the PDB and UniProt do not have).

- Remote execution inside an environment (conda, Docker container). This works well if the environment is popular and stable, i.e. you can re-use the same environment over and over again. If the environment itself is under active development, this method is a disaster.

- The fifth method is how Seamless does it. Remote execution is done by providing the checksums of the inputs and of the code. This is what Seamless call a *transformation*. The remote service is then responsible to retrieve the corresponding buffers/values. This means that a computation is always well-defined, but not always executable: it may fail if one or more buffers cannot be found. In contrast, in the first three methods, a computation becomes only well-defined when it becomes executable.

#### Transformers vs. transformations

A transformer is essentially a container that holds a transformation. A transformer has cells as input, whereas a transformation has the checksums of those cells as input.

A transformation describes a unique computation that transforms the input checksums (including the code checksum) into a result checksum. Each input checksum has a name and a celltype. When the transformation is executed, each input checksum is converted to a variable with the same name, and whose value is obtained in the same way as for cells.

#### Types of transformations

Seamless allows a transformation to contain an *environment*: as a Docker image, a conda environment definition, or a list of command line tools that must be available. This is a bit informal and should be used with care when it comes to reproducibility. See the [documentation of environments](http://sjdv1982.github.io/seamless/sphinx/html/environments.html) for more details.

In addition, Seamless transformers can in principle be written in any language. Python/IPython transformers are executed directly. Interpreted languages (e.g. R) are executed via a bridge to IPython (e.g. using rpy). Bash transformers are executed using a special Python function. So are compiled transformers (e.g. in C++) after compilation.

The following combinations of language and environment are currently possible for Seamless transformations:

- Transformers written in bash, with no environment (pure UNIX commands)
- Transformers written in bash, with a Docker image environment.
- Generic transformers (Python, compiled, etc.), with no environment
- Generic transformers, with a conda environment.

#### Deployment of transformations

Each Seamless instance is able to do its own computation, but during deployment, this is normally not very efficient. So Seamless has a protocol (communion protocol) where a Seamless instance can delegate transformation requests (jobs) to another Seamless instance (a jobslave)or to a dedicated job manager (jobless). Transformation requests can then be delegated further, e.g. to a job slave on a HPC cluster.

Then, from a computing viewpoint, a Seamless instance can be seen as a black box, where cell values come in (via HTTP) and a stream of transformation requests come out. The transformation requests are small, as they contain only checksums.

The communion protocol can also exchange buffers, but it is easier if both the Seamless instance and the job slave have access to the same Seamless database (see [documentation](http://sjdv1982.github.io/seamless/sphinx/html/data_storage.html)).
In that case, the buffers corresponding to the input checksums will have beenpre-deposited by the Seamless instance, so only the transformation needs to be sent. After computation, the jobslave will deposit the result checksum for that transformation, and the corresponding buffer. The Seamless instance needs to interrogate only the database to retrieve the results.

### Deep structures

***IMPORTANT: This documentation section is an early draft. The raw text material is shown below***

TODO: move/clone into deepcell.md

A transformation is in fact a "deep structure". Its checksum corresponds to a dictionary, where each value is itself a checksum (of the input cells).

Seamless has support for two other kinds of deep structures: deep cells and deep folders. In both cases, the deep structure is again a dictionary, where the keys are strings and the values are checksums. The difference is the cell type of the checksums. For deep cells, the cell type is "mixed" (Seamless's default cell type), which means that you can easily access an individual element and convert it trivially to a normal Seamless cell. In contrast, for deep folders, the cell type is "bytes", which means that buffer and value are the same. This allows a one-to-one mapping with a
folder on the file system.

### Visualization and monitoring

***IMPORTANT: This documentation section is an early draft. The raw text material is shown below***

TODO: integrate/merge with visualization.md

Typically, a web service consists of two graphs (.seamless files).
The first graph contains the main workflow. The second graph contains a status graph. The status graph can be bound by Seamless to the main graph (`seamless.metalevel.bind_status_graph`; this function is automatically invoked by `seamless-serve-graph` if you provide two graph files). In that case, the status graph receives the current value and status of the  main workflow graph as its input, and normally visualizes it as a web page. Manually-coded web interfaces are normally added to the main workflow graph. In contrast, the automatic web interface generator is part of the status graph, as it generates the web interface HTML by taking the main workflow graph as an input. During development, both graphs are developed, which is made possible by `seamless-new-project` and `seamless-load-project`.

### Understanding Seamless dependency graphs

***IMPORTANT: This documentation section is an outline. The outline is shown below***

- Topology vs parameters.
- Seamless translation machinery (midlevel), metalevel. How the high level wraps the graph data structure
- Discussion of the limitations of workflows (dependency graphs): if statements, for loops, cyclic dependencies.
  Dummy solution: for loop and if statement inside transformer code.
  Proper duration of a transformer: seconds to minutes.
  Alternative solution: move away from dependency graph, launch jobs imperatively (Prefect 2.0).
- Ways to work around these limitations:
  libraries, macros and reactors.
  Note that library instances require translation, macros do not. Translation is in fact a macro.
- Always keep a test where you maintain interactivity.

Practical:

- Scatter transformers
- stdlib.map
- Elision and incremental computing
- Hacking the midlevel

## Guidelines for experienced developers

### Keep it simple, while you can

The beginner's guide's section on "how to keep it simple" contains good advice for a small, young project. With Jupyter, you can quickly set something up, adding Seamless's interactivity to Jupyter's own. This works best for workflows that are non-linear but with not too many steps, where the data is rather small, and the code too.

When the code gets more complex, you should move away from Jupyter by mounting your code cells to files. Code that modifies the workflow becomes throw-away code. See "Moving away from Jupyter" for more details.

When the data gets bigger, or execution becomes time-consuming, you should start thinking about [data storage](http://sjdv1982.github.io/seamless/sphinx/html/data_storage.html) and [job management](http://sjdv1982.github.io/seamless/sphinx/html/job_management.html). With default settings, Seamless transformations are parallelized on your local machine and cached in memory, and you may want to change that. If the data gets really big, you should bring the computation where the data is. But even in that case, try to have a small-data version of your workflow that executes fast, so that you can modify the code easily and interactively. Whitelists work very well for this [see deep cells](http://sjdv1982.github.io/seamless/sphinx/html/deep_cells.html).

If either the code or the data gets bigger, you should start thinking about version control, and whether or not to use `seamless-new-project`. See [the documentation for creating a Seamless project](http://sjdv1982.github.io/seamless/sphinx/html/new-project.html) for more details.

### Programming in two places

Clearly distinguish between the "outside" code that *creates* the workflow, and the "inside" code (mostly within transformers) that is executed as part of the workflow. Inside codes are polyglot and executed in isolation (from each other, and from the outside). Outside code is written in Python, and you run it inside IPython or Jupyter. You don't need to keep outside code, because you can store the entire workflow as data. The "Programming in two places" section in the beginner's guide explains it in slightly more detail.

The "Moving away from Jupyter" section below explains that you should mount your code cells to the file system, and then remove their code from the notebook. Once it has thus become part of your workflow, Seamless will store the code (at least its checksum, and normally its content too), and you can also store it under Git version control as a file. Note that this applies only to "inside" code. In contrast, in a mature project, "outside" code that inspects or modifies the workflow should be considered ***throw-away code***. If you have moved away completely from Jupyter, you can simply use `seamless-ipython` to enter such code. Else, you can enter it in a temporary notebook cell, or use `seamless-jupyter-connect` to connect an IPython-like console to Jupyter. In all cases, you execute the code, but you don't keep it: instead, you simply save the state of the workflow in a `.seamless` file.

There is one use case where "outside" code may be kept. When it comes to describing the topology of the workflow (the steps and connections), you should normally rely on the status visualization web page (which you can modify, see "Edit the editor") or create your own flowcharts. But if that is not to your satisfaction, you do have the option to define your workflow topology from code. In that case, modify the Seamless project's `define_graph` function in `load-project.py`. If you do so, `await load()` will execute that code instead of loading the `.seamless` file, assuming that it will build the connections and cell mounts of the workflow. If you don't use a Seamless project at all, simply store the "outside" code in a script and run it.

### Moving away from Jupyter

Seamless gives the illusion of being like Jupyter, but with non-linear execution. The **web server demo**( [open on GitHub](https://github.com/sjdv1982/seamless/tree/stable/examples/webserver-demo), or [run on mybinder.org](https://mybinder.org/v2/gh/sjdv1982/seamless-binder-demo/main?labpath=webserver.ipynb)) gives an example where you start from a simple notebook and port it to Seamless, gaining an interactive web interface in the process. It is also about as far as you can push a Seamless workflow that is defined purely in Jupyter. Why is this? At the end of the demo, the next step would be to mount each code cell to a Python file, so that you can start modifying the calculation code of the workflow using a normal text editor or IDE. Whenever you save the file, the cell value is updated and the workflow recalculated. Each Python file can be put under Git version control, something that `seamless-new-project` sets up by default. However, the original unmodified code is still in the notebook! So if you re-run the notebook, and you re-mount the Python files, Seamless has to choose which version is correct: the one in the Python file, or the one in the notebook. In other words, either all of your modifications in the Python file get lost, or the code in the Python file supersedes the code of the notebook. By default, Seamless does the second thing (and gives you a warning), but it's ugly to have your notebook telling lies. It goes against the spirit of a notebook that tells a linear story on how you started from scratch and arrived at a result. And if then further modify the code also in the notebook, there will be no end of trouble. So in that case, the correct thing to do is to give up on the linear story and remove the now-outdated code from the notebook.

Another case is the web interface generator, which is all based on files (`webform.json`, `index.html`, `index.js`) that are being auto-generated but that can be modified. In fact, these files are Seamless cells of a secondary context `webctx` that are mounted to the file system (also see "Edit the editor"). Re-loading the notebook, executing cells that re-build the workflow bit-by-bit, is bound to give merge conflicts with a file that contains the modified web interface for the entire workflow in its final state.

In summary, ***once you start offloading your workflow to edited files, the time for linear notebook storytelling is over***. Does that mean that you should abandon Jupyter altogether? Not necessarily. You can keep Jupyter around as a dashboard, linking Seamless `Cell.traitlet` and `Cell.output` with ipywidgets. Or you can still use it as a scratch pad where you can quickly try out code, then incorporate it into your workflow when it seems to work, deleting it from the notebook.

Note that all of this applies primarily to "inside" code. In contrast, "outside" code is normally throw-away code. See "Programming in two places" for detail.

### Edit the editor

***IMPORTANT: This documentation section is an early draft. The raw text material is shown below***

TODO: perhaps merge with "visualization and monitoring".
(Status graph is your friend)
Don't be afraid to modify it (Link to last paragraph in visualization). If you have HTML/JS skills, you can organize the cells and transformers into cleaner flowcharts. Beyond that, there is nothing to stop you from extending the webctx further into a full visual programming interface.
Light-weight experience: don't use seamless-new-project at all

### Environments

The beginner's guide's documentation recommends to install packages in the running Docker container. Don't do that. Study the [documentation of environments](http://sjdv1982.github.io/seamless/sphinx/html/environments.html) instead.

### Don't confuse files and cell names

See the beginner's guide on "Don't confuse files and cell names". In addition, note that file mounting is something that happens only during development. When you save a workflow, the file's checksum gets incorporated into it. When you deploy a workflow (e.g. with `seamless-serve-graph`, Cloudless, or loading a .seamless file yourself), mounts are not needed to make the workflow run.

### Don't rely on file names or URLs

If you need external files or directories, add their *checksums* explicitly to the workflow (inside a normal cell for files, and inside a FolderCell or DeepFolderCell for directories). Else, reproducibility will be broken. The same applies for other external data sources, such as URLs or databases. In other words, reading an external data source must be *outside* code (see "Programming in two places"), it must be done inside IPython or Jupyter, and *not* inside transformer code. See the beginner's guide on "Don't rely on file names or URLs" for more details.

There is one exception to this rule: you may choose to embed external data sources in the environment, by installing them inside a Docker image. In that case, reproducibility is guaranteed by the checksum of the Docker image, and you are highly recommended to include it in the Docker image name in `Transformer.docker_image` (e.g "jupyter/scipy-notebook@sha256:a891adee079e8c3eee54fef732cd282fe6b06c5fabe1948b9b11e07144526865" for a specific version of Jupyter). In that case, it is fine to refer to the file name of the data source inside transformer code. Of course, when your external data source changes, you must rebuild the Docker image and change `Transformer.docker_image` to reflect the new Docker image checksum.

### Use celltypes

By default, every cell is a structured cell, which is normally overkill. Structured cells are great for subcell access and for schemas, but not every cell needs those features. Setting the celltype to something simpler may clarify the workflow.

All celltypes and their conversions are described in the [cell documentation](http://sjdv1982.github.io/seamless/sphinx/html/cell.html). Note that transformer pins have celltypes too. Their default celltype is "mixed".

### Use schemas

***IMPORTANT: This documentation section is an early draft. The raw text material is shown below***

Transformer code is not the correct place for validation. Use schemas instead.

### Use structured cells

***IMPORTANT: This documentation section is an early draft. The raw text material is shown below***

Because of subcell access and schemas, and integration of independent (auth) and dependent (inchannel) data, and cyclic dependencies, and object oriented programming. Same reason why beginners should avoid them. Keep them small, else use DeepCells. At odds with "use celltypes".
