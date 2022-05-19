TODO: merge this with architecture.

The majority of Seamless revolves around ***cells*** and ***transformers***. 

Cells
=====

A cell is essentially a wrapper around a *checksum* (a SHA3-256 hash). A checksum corresponds to a *buffer* (the raw bytes). This correspondence is one-to-one: each buffer has a unique checksum and vice versa. Finally, the *celltype* describes how the buffer is to be interpreted (*deserialized*) into a *value*. For example, celltype "plain" means a conversion to a Python string (which means UTF-8 decoding) followed by loading the string as JSON. Likewise, to go from value to buffer (*serialization*), a value of celltype "plain" is first converted to a JSON string, and then encoded (using UTF-8) into a byte buffer.
Concretely, the byte buffer `42\n` corresponds to the value `42` for celltype "plain", and vice versa. 

There is also a celltype "python", which means that a cell can contain not only data, but also code.

Using the Seamless library in Python gives the *illusion* that Seamless cells contain values, just like: 

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
- Define a cell with a value "testvalue"
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
    "str"
))
testvalue
```

Transformers and transformations
================================

Large scale computing means the deployment of computations to remote systems.
In principle, there are five ways to do that:

- Remote Procedure Call (RPC). There are many frameworks that can do this, for example ipycluster and execnet. In essence, everything is packaged into a single command message that is sent to the remote service. All of the input values and code are serialized (pickled) and the remote service is asked to execute the command. This is reproducible, since the result is completely defined by the command message. But the command message can be extremely big, since it embeds all input values.

- Remote execution using file names. This is what Slurm does for single computations, and NextFlow/Snakemake for workflows. The command messages are small, but they rely on a shared file system. Organizing files into inputs, outputs, versioned banks etc. requires mental effort and discipline. Reproducibility is an issue: there is no guarantee that a file name always refers to the same value. File modification time is used to detect this, but this only works within the same file system. Federation is therefore not easily possible: sharing files is difficult (files can be big) and fragile in terms of reproducibility (need to preserve modification times). If command line tools are sloppy (creating hidden output files that are implicitly needed by downstream tools), some very strange errors can happen.

- Remote execution using URLs. This is essentially the same as file names, but using the Internet as a global file system. Federation is much easier, but reproducibility (already hard) is now much harder (no control over remote sites, cannot use modification times). Requires immense discipline in using globally unique identifiers for URLs (discipline that the PDB and UniProt do not have).

- Remote execution inside an environment (conda, Docker container). This works well if the environment is popular and stable, i.e. you can re-use the same environment over and over again. If the environment itself is under active development, this method is a disaster.

- The fifth method is how Seamless does it. Remote execution is done by providing the checksums of the inputs and of the code. The remote service is then responsible to retrieve the corresponding buffers/values. This means that a computation is always well-defined, but not always executable: it may fail if one or more buffers cannot be found. It is also possible to design a well-defined definition of an environment. But in the first three methods, a computation becomes only well-defined when it becomes executable. 

## Transformations

A transformer is a wrapper around a transformation. A transformation describes a unique computation that transforms the input checksums (including the code checksum) into a result checksum. Each input checksum is has a name and a celltype. When the transformation is executed, each input checksum is converted to a variable with the same name, and whose value is obtained by: finding the buffer cio
A transformation is represented as a simple dict where the keys are the names and the values are lists of (celltype, subcelltype, checksum).

...

## Demonstration

...

Transformation is a "deep structure".


Other features
==============

The core of Seamless is a (directed acyclic) graph of cells and transformers. 
- Reproducibility, interactivity, incremental computing.


## Other features

- Synchronization of cells: over HTTP (shareserver), to/from files (only during development), to/from Jupyter widgets.
- Cells that support attribute access (both set and get) (structured cells).
- Exceptions (error messages) and validation (schemas).
- Syntactic sugar, making it easier to construct graphs through Python. High level and low level, graph translation.
- Dynamic graphs that build and connect cells and transformers from cell data (macros).
- Self-editing graphs (reactors). Note that a cell only has a single value. Seamless has no concept of cell history, modification events, or streaming. 
- "Batteries included": web interface generator, status web page, graph-to-checksum tools, serve-graph.

These are in principle *development* features. What touches deployment:
- Graph can be stored as data, and deployed as such 
- HTTP synchronization
- Error messages and status web page
- Web interface generator
Cloudless takes care of all these things.

Communication and deployment
============================

The operations to convert between checksum, buffer and value have been discussed above.
In Seamless, all of these operations are being cached for performance. However, the checksum-to-buffer conversion cache is more than just performance. The correspondence between checksum and buffer is one-to-one, but you can only compute the checksum from a buffer, not the other way around. 

=> database

Transformation is a deep structure. ...
Transformation has a unique result ... => database
More features of a database: bufferinfo (length, conversion), semantic to/from syntactic (only Python, YAML/CSON), elision, compilation.
...
(Wider ecosystem: Seamless database, jobslave, jobless, cloudless, database actions, FAIR server)

## Cloudless
What touches deployment: instance management, local computation (?). Help requests...