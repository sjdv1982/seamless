This document describes the high-level design choices of Seamless, 
and how it interacts with the outside world (HTTP synchronization, buffer
caching, transformations) with a focus on deployment. 

# Overall purpose and design

First, Seamless is a framework for *interactive* programming/scripting. 
There are essentially two ways that you can do this. The first is file-based,
like the bash shell. The second is cell-based, such as IPython, Jupyter, 
or a spreadsheet. Seamless follows the cell-based approach.

Second, Seamless is a framework for building *workflows* 
(dataflow programming), i.e. dependency graphs. 
There are essentially three ways you can do this: stream-based (NoFlo),
file-based (NextFlow, Snakemake) or cell-based (Jupyter, Excel). Again, 
Seamless follows the cell-based approach. 
 
Most of Seamless revolves around ***cells***, that hold the data, 
and ***transformers***, that do the computation. Transformers take cells as
input and have a single cell as output.

## Why checksums?

Cells are based on checksums, not on values or identifiers (more details below).
This means that you can replace a computation with its result, and replace a 
result with its computation (referential transparency).
This is good for reproducibility, and it provides *reactivity*: after cell 
updates, it is always obvious which computations need to be re-executed. 
No need for manual re-execution (Jupyter) or reliance on file modification 
times (SnakeMake). More details are in the transformation section.

Reactivity helps a lot for interactivity. You can essentially re-run the entire
workflow continuously, and recomputation only happens if something changes.

## Interactivity

On top of this reactivity, Seamless has two mechanisms for interactivity. 

First, during development, you can always modify the workflow in 
IPython/Jupyter, while the workflow remains running. 
Both the topology of the workflow and the cell values can be modified.

Second, Seamless allows cells to be *synchronized*. There are two mechanisms
for this. During development, cells can be synchronized to the file system. 
In this way, you can define a code cell initially in a Jupyter Notebook, 
but then link it to a source code file under Git version control that 
you can edit with a standard text editor or IDE. The synchronization is two-way,
which means that the file contains the cell buffer, and that the cell
contains the file checksum. During deployment, the file is no longer needed,
as long as the cell buffer can be retrieved from somewhere.

The second way of synchronization is over HTTP. You can expose cells as read-only,
allowing their value to be read in the browser (HTTP GET), or as read-write,
so that they can be modified (HTTP PUT). There is also a websocket port where you 
can receive notifications from Seamless when a cell has been updated. 
Seamless includes a simple javascript client that uses all of this to 
synchronize cell values bidirectionally between Seamless and the browser.
This is how you build web interfaces that are fundamentally interactive. 

For Seamless, all sources of interactivity are the same: change of a cell 
over HTTP, change of a cell linked to the file system, or modification of the 
entire workflow via IPython. From Seamless's point of view, they are all acts
of programming, although the user of a web interface normally has a very 
limited API at his disposition. You *can* allow actual programming via the web 
interface, by exposing code cells in read-write mode and link them to textarea editor elements in your HTML page. If you really want to.

In all cases, you never have to write webserver code that handles dynamic change, 
while this is required if you use Django or React or Flask or any of those web frameworks.
***Seamless workflows don't handle dynamic change, because there is none***.
Whenever something changes, Seamless effectively discards the old workflow and 
replaces it with a new workflow. All computations of the old workflow 
(or of any previous workflow!!) are re-used if they are present in the new 
workflow. In that sense, Seamless is more similar to a traditional static CGI web server, which doesn't require any dynamic change either.

However, the big difference with a static web server is that a dynamic, interactive
web server must always be live: there must always a Seamless process that listens
for HTTP updates. You can't simply wait until the user submits a static webform 
with all the parameters and then fire up your workflow. Likewise, the browser 
must be live too, and listen from continuous updates from the server, but this is 
easy to do nowadays (web sockets).

**Deployment role: live web servers**

# Cells

A cell is essentially a container that holds a *checksum* (a SHA3-256 hash). 
A checksum corresponds to a *buffer* (the raw bytes). This correspondence is 
one-to-one: each buffer has a unique checksum and vice versa. Finally, the 
*celltype* describes how the buffer is to be interpreted (*deserialized*) 
into a *value*. For example, celltype "plain" means a conversion to a Python 
string (which means UTF-8 decoding) followed by loading the string as JSON. 
Likewise, to go from value to buffer (*serialization*), a value of celltype 
"plain" is first converted to a JSON string, and then encoded (using UTF-8) 
into a byte buffer.

Concretely, the byte buffer `42\n` corresponds to the value `42` for celltype 
"plain", and vice versa. 

There is also a celltype "python", which means that a cell can contain not 
only data, but also code.

Using the Seamless API in Python gives the *illusion* that Seamless cells
are containers of *values*, just like: 

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


## Demonstration

Define a cell with a value "testvalue"
```
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

## Cells and deployment

In Seamless, all of these operations are being cached for performance. However, 
the checksum-to-buffer conversion cache is more than just for performance. The 
correspondence between checksum and buffer is one-to-one, but you can only compute 
the checksum from a buffer, not the other way around. Therefore,
it is essential that for each checksum, the corresponding buffer is available 
where needed. 

In addition, sometimes very large buffers must be converted between different cell 
types, e.g. from text to JSON. Caching the conversion will avoid the loading of 
the source buffer from wherever it is stored. Seamless also caches the length of
buffers and other info statistics, to reason if a conversion is a priori impossible
or trivial.

Finally, Seamless has a last-resort function to go from checksum to buffer. It 
is possible to define a list of buffer servers (\$SEAMLESS_BUFFER_SERVERS) and
Seamless will try to contact them. By default, it contains 
the RPBS buffer server, so that `https://buffer.rpbs.univ-paris-diderot.fr/<checksum>` will be contacted.

**Deployment role: checksum-to-buffer service**

**Deployment role: buffer info service**.

**Deployment role: buffer server**.

# Transformations

Large scale computing means the deployment of computations to remote systems.
In principle, there are five ways to do that:

- Remote Procedure Call (RPC). There are many frameworks that can do this, for 
example ipycluster and execnet. In essence, everything is packaged into a single 
command message that is sent to the remote service. All of the input values and 
code are serialized (pickled) and the remote service is asked to execute the 
command. This is reproducible, since the result is completely defined by the 
command message. But the command message can be extremely big, since it embeds all 
input values.

- Remote execution using file names. This is what Slurm does for single 
computations, and NextFlow/Snakemake for workflows. The command messages are 
small, but they rely on a shared file system. Organizing files into inputs, 
outputs, versioned banks etc. requires mental effort and discipline. 
Reproducibility is an issue: there is no guarantee that a file name always refers 
to the same value. File modification time is used to detect this, but this only 
works within the same file system. Federation is therefore not easily possible: 
sharing files is difficult (files can be big) and fragile in terms of 
reproducibility (need to preserve modification times). If command line tools are 
sloppy (creating hidden output files that are implicitly needed by downstream 
tools), some very strange errors can happen.

- Remote execution using URLs. This is essentially the same as file names, but 
using the Internet as a global file system. Federation is much easier, but 
reproducibility (already hard) is now much harder (no control over remote sites, 
cannot use modification times). Requires immense discipline in using globally 
unique identifiers for URLs (discipline that the PDB and UniProt do not have).

- Remote execution inside an environment (conda, Docker container). This works 
well if the environment is popular and stable, i.e. you can re-use the same 
environment over and over again. If the environment itself is under active 
development, this method is a disaster.

- The fifth method is how Seamless does it. Remote execution is done by providing 
the checksums of the inputs and of the code. This is what Seamless call a 
*transformation*. The remote service is then responsible to retrieve the 
corresponding buffers/values. This means that a computation is always 
well-defined, but not always executable: it may fail if one or more buffers cannot 
be found. In contrast, in the first three methods, a computation becomes only 
well-defined when it becomes executable. 

## Transformers vs. transformations

A transformer is essentially a container that holds a transformation. A 
transformer has cells as input, whereas a transformation has the checksums 
of those cells as input.
A transformation describes a unique computation that transforms the input
checksums (including the code checksum) into a result checksum. Each input 
checksum has a name and a celltype. When the transformation is executed, each 
input checksum is converted to a variable with the same name, and whose value is 
obtained in the same way as for cells.

### Types of transformations

Seamless allows a transformation to contain an *environment*: as a 
Docker image, a conda environment definition, or a list of command line tools 
that must be available. This is a bit informal and should be used with care when 
it comes to reproducibility.

In addition, Seamless transformers can in principle be written in any language.
Python/IPython transformers are executed directly. Interpreted languages (e.g. R)
are executed via a bridge to IPython (e.g. using rpy). 
Bash transformers are executed using a special Python function. So are compiled
transformers (e.g. in C++) after compilation. 

The following combinations of language and environment are currently possible
for Seamless transformations:

- Transformers written in bash, with no environment (pure UNIX commands)
- Transformers written in bash, with a Docker image environment.
- Generic transformers (Python, compiled, etc.), with no environment
- Generic transformers, with a conda environment.

### Deployment of transformations

Each Seamless instance is able to do its own computation, but during deployment, 
this is normally not very efficient. So Seamless has a protocol (communion 
protocol) where a Seamless instance can delegate transformation 
requests (jobs) to another Seamless instance (a jobslave) or to a dedicated 
job manager (jobless). Transformation requests can then be delegated further, 
e.g. to a job slave on a HPC cluster. 

Then, from a computing viewpoint, a Seamless instance can be seen as a 
black box, where cell values come in (via HTTP) and a stream of transformation 
requests come out. The transformation requests are small, as they contain only
checksums.

The communion protocol can also exchange buffers, but it is easier if both the 
Seamless instance and the job slave have access to the same Seamless database
(see below for more details on the Seamless database).
In that case, the buffers corresponding to the input checksums will have been
pre-deposited by the Seamless instance, so only the transformation needs to be
sent. After computation, the jobslave will deposit the result checksum for that transformation, and the corresponding buffer. The Seamless instance needs to interrogate only the database to retrieve the results

**Deployment role: transformation job service**. Needs to support as many types of 
transformations as possible. It must also support the cancellation of jobs.

**Deployment role: transformation result service**. Store transformation-to-result mapping.

**Deployment role: compilation service**. Store mapping of source code (C/C++) to compiled binary.
 

# Deep structures

A transformation is in fact a "deep structure". Its checksum corresponds to a dictionary, where each value is itself a checksum (of the input cells).

Seamless has support for two other kinds of deep structures: deep cells and
deep folders. In both cases, the deep structure is again a dictionary, where
the keys are strings and the values are checksums. The difference is the cell
type of the checksums. For deep cells, the cell type is "mixed" 
(Seamless's default cell type), which means that you can easily access an 
individual element and convert it trivially to a normal Seamless cell.
In contrast, for deep folders, the cell type is "bytes", which means that
buffer and value are the same. This allows a one-to-one mapping with a
folder on the file system.


# Other Seamless features

- Cells that support attribute access (both set and get) (structured cells).
- Exceptions (error messages) and validation (schemas).
- Syntactic sugar, making it easier to construct graphs through Python. High level and low level, graph translation.
- Dynamic graphs that build and connect cells and transformers from cell data (macros).
- Self-editing graphs (reactors). Note that a cell only has a single value. Seamless has no concept of cell history, modification events, or streaming. 
- "Batteries included": web interface generator, status web page, graph-to-checksum tools, serve-graph.

These features are important for the development of interactive workflows,
but they do not impact deployment. Therefore, they are discussed in the architecture document (/docs/developer/architecture.txt, mostly TODO).

What does impact deployment is the following.
Typically, a web service consists of two graphs (.seamless files). 
The first graph contains the main workflow. The second graph contains a status 
graph. The status graph can be bound by Seamless to the main graph
(`seamless.metalevel.bind_status_graph`; this function is automatically invoked by
`seamless-serve-graph` if you provide two graph files).
In that case, the status graph receives the current value and status of the 
main workflow graph as its input, and normally visualizes it as a web page.
Manually-coded web interfaces are normally added to the main workflow graph.
In contrast, the automatic web interface generator is part of the status graph, 
as it generates the web interface HTML by taking the main workflow graph as an
input. During development, both graphs are developed, which is made possible
by `seamless-new-project` and `seamless-load-project`.

# Deployment roles

## Seamless database

**Deployment role: checksum-to-buffer service**

**Deployment role: buffer info service**

**Deployment role: transformation result service**

**Deployment role: compilation service**

These roles are normally taken by the ***Seamless database***. A Seamless instance
connected to the database does not maintain its own checksum-to-buffer cache,
and therefore uses a lot less memory.

You can start the database with the command `seamless-database`. By default, 
it loads  /seamless-tools/tools/default-database.yaml, which maintains the
database dir in  \$HOME/.seamless/database, but you can supply your own
configuration file. Primarily, the database dir contains /buffers, containing one file per buffer (the filename is the checksum, e.g. 
/buffers/93237a60bf6417104795ed085c074d52f7ae99b5ec773004311ce665eddb4880).
The other stores (buffer info, transformation result, compilation, and a few
specialized others) map a checksum to either another checksum or something other that is very small. Therefore, each of those stores is organized as JSON files that
are split in buckets as they grow larger. 

### Using the database

Seamless reads the database IP from the SEAMLESS_DATABASE_IP environment 
variable, which defaults your Docker host IP. The default Seamless database port
(SEAMLESS_DATABASE_PORT) is 5522.

### Database cleanup

The buckets do not take up much space, there is little reason to delete them. 
In contrast, buffers/ can get very large. You can freely delete the contents of /
buffers while the database is running, this will not cause any crash. The database 
has a memory cache that may continue to hold the buffer for a while.
To cleanly remove any kind of database entry, create a file with a format like
`/seamless-tools/tools/jobless/tests/jobless-test-dblog-ORIGINAL.txt` and then
run `seamless-delete-database-from-log <filename>`.

Note that any workflow or transformation job slave 
that needs the buffer but can't find it will report a CacheMissError. 
This will happen for sure if the buffer is *independent*, i.e. is not the result
of some kind of computation (transformation, conversion, cell expression etc.).
If it *is* the result of a computation, and the computation is part of the workflow
that is loaded by the Seamless instance, Seamless may try to repeat the computation
in order to regenerate the buffer (this is called "fingertipping"). So you can be
a bit more aggressive in deleting buffers of intermediate results (or even 
final results), especially if they are large and/or quick to compute.

### Multiple database directories 

It is possible to set up multiple database directories with Seamless database.
Only one will be written to, the other ones are read-only. The purpose can be:
setting up specialized databases (e.g. the PDB), backup, or having them in
different file zones.

### File zones

The Seamless database has a special request where you can ask directly for the 
filename that corresponds to the buffer. With the request, you can specify a
file zone (or multiple file zones). 
If the Seamless database directory is in the same file zone (or in one of the file
zones), the file name (i.e. `/buffers/<checksum>`) is assumed to be accessible by the requesting instance, and is returned. In other words, "same file zone" means "same file system".
This is very efficient in case of bash transformers,
leading to a hard link instead of load-buffer-from-database + write-buffer-to-
file-in-temp-directory.
In case of a deep folder, the special request is for a folder. 
Seamless has a tool called `database-share-deepfolder-directory`. It takes a
deep folder checksum (or its collection name, see below), reads the deep folder dict, creates a folder `/shared-directories/<deep checksum>/`, and creates a hard link `/shared-directories/<deep checksum>/key` to `/buffers/<checksum>` for every key:checksum pair in the dict. Therefore, `/shared-directories/<deep checksum>`i
is an exact mirror of the deep folder mounted to disk, without taking any disk
space whatsoever. Therefore, bash transformers that take a deep folder as input
(e.g. a database search tool) get a soft link to `/shared-directories/<deep checksum>` instead of copying the entire database every time. Of course, this does
require that the file zone is the same. 

### Buffer server

**Deployment role: buffer server**

The easiest way to set up a buffer server is to simply share the /buffers 
directory of a Seamless database directory over HTTP, e.g. using NGINX.
The RPBS buffer server works like this.

# collections and FAIR databases
Seamless has some facilities for maintaining and sharing 
deep cells and deep folders.

The `database-run-actions` tool revolves around the concept of "collection",
which is essentially a deep structure with a name. 
The tool does things like:
- Index an external directory (i.e. a directory under rsync control)
  into a "collection".
- Copy each entry in a collection into /buffers, or hard-link each entry
  to the external directory.
- Build a deep folder buffer for a collection
- Convert a deep folder collection to a deep cell collection
- Unzip each file in a collection
- Build a download index for a collection, i.e. a list of URLs where
  each item in a collection might be found for download.

In addition, there is a tool called `fair-add-distribution` that
copies the "collection" deep structure buffers and their download indices, 
but NOT their underlying buffers, into a dataset "distribution", 
marked with metadata such as dataset name, version, format and date. 
While a collection can change, a distribution should not. 
Run this repeatedly whenever a collection changes, to create snapshots of
the current collection state.
There is an experimental tool "fairserver.py" that allows querying
of datasets, distributions, etc. This is organized using the FAIR
principles, i.e. "/access" will retrieve a list of download URLs from
the download index. More work is needed to achieve FAIR compliance.

An RPBS FAIR server is running at fair.rpbs.univ-paris-diderot.fr.
Seamless itself has DeepFolder and DeepCell classes that integrate with the FAIR
server. For example, 
`DeepCell.find_distribution("pdb", date="2022-02-18", format="mmcif")`
by default contacts the RPBS FAIR server to retrieve the checksum of the
distribution. A distribution also has a keyorder, which is important if you just
ran a tool on each chunk of an old version of the database, and then update the 
new database, and you want to re-use the results of the old chunks.

## Cloudless

**Deployment role: live web servers**

This role is normally taken by ***Cloudless***. 
Note that Seamless embeds its own HTTP server. Thus, Cloudless is a rather
simple program that does the following:
- It has a directory "graphs" with Seamless graph files.
- It listens on port 3124. It has an admin interface on /admin.
- It can take requests to launch an instance of a particular Seamless graph.
  This launches a new Docker container with Seamless serving the graph
  (the `seamless-serve-graph --database` command).
  With this, the instance connects itself to Seamless DB.
  In addition, the instance connects itself to jobless if configured (see below).
- HTTP traffic `from /instances/<instanceID>/` is redirected to/from the HTTP
  server ports of the Seamless instance.
- The graph of the Seamless instance is initially identical to that of
  the original graph. This changes whenever an input cell is changed
  over HTTP or a computation finishes. Every few seconds, the graph is
  stored in the "instances" directory. Note that the graph files are small
  as they contain only checksums. The underlying buffers are stored in the
  Seamless database.
- After 10 minutes of no HTTP traffic, the Seamless instance is killed. 
  Whenever new traffic arrives, the Seamless instance is re-instantiated,
  not from the "graphs" directory, but from its graph file in the
  "instances" directory.

## Jobless

**Deployment role: transformation job service**

**Deployment role: compilation service**

These roles are normally taken by ***jobless***. 

Jobless works by configuring a jobless .yaml file and define "jobhandlers".
A jobhandler is a combination of a job plugin and a backend. 

Job plugins can be for bash transformations with Docker, bash transformations
without Docker, or generic transformations with conda environments. 
(See the section "Types of transformations" for more detail).

Backends can be:
- Local shell execution with seamless-cli (i.e. using Docker containers)
- Local shell execution with Singularity
- Slurm shell execution with Singulariy
- Local generic execution with seamless-cli
- Local generic execution with Singularity
- Slurm generic execution with Singularity

Jobless requires connection to the Seamless database for itself.
Generic jobhandlers also need connection to the Seamless database.

Shell execution with Singularity requires a Singularity image for every Docker
image that is being used.
In contrast, generic execution only requires the "rpbs/seamless-minimal"
Docker/Singularity image. This image contains only the Seamless source code, and
relies on an *external* conda environment directory to provide the dependencies.
Using seamless-cli commands, jobless exports, copies and updates these environment
directories and provides them to the `seamless-minimal` container, in which the
`seamless-conda-env-run-transformation` tool is run.

Jobless is part of the seamless-tools repo. See that repo for more details.
The example

### Using jobless

Seamless reads the jobless IP from the SEAMLESS_COMMUNION_IP environment 
variable, which defaults your Docker host IP. The default jobless port
(SEAMLESS_COMMUNION_PORT) is 5533.
