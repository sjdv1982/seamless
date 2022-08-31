
# Beginner's guide

If you are beginner in programming, you focus on one thing at a time. However, Seamless is very non-linear: you can change anything at any time, interactively. If that makes you feel lost, this document contains an explanation of the basic concepts, and some beginner's guidelines, to give you a sense of direction.

## Basic Seamless features

The basic Seamless features are contexts, cells and transformers. See the [basic example](http://sjdv1982.github.io/seamless/sphinx/html/introduction.html#basic-example) for a demonstration.

Contexts contain cells and transformers and other contexts. The whole Seamless workflow is a context.

Cells contain data or code.

Transformers perform a data transformation (computation), with cells as input, and one cell as the output. One of the input cells must be a code cell.

Seamless workflows are created in Python. This can be done in a Python script, but normally it is done interactively, in IPython or Jupyter. Here, new cells, transformers and their connections are created. The workflow remains running all the time.

## Working with Seamless

UPDATE: maybe make a generic "Keep it simple" section, merging the section farther down into here...

- Keep it simple (link): create a new project, use Jupyter
- Children, tab completion.
- Link to web status (point out: if using project)
- Translate and compute and asynchronous
- `await load()` and `save()`
- Point to beginner's gotchas

## Simple deployment recipe
(based on serve-graph, sharing the .seamless and zip).

## Programming in two places

With Seamless, there is programming in two places. First, there is the "outside": the Jupyter or IPython shell where the Seamless workflow is being created interactively. In addition, there is the "inside": 

==>

and Seamless supports many programming languages: bash, Python, and C/C++ are well-tested. Other languages such as R, Cython, Fortran or Go are also supported, but less tested. As a beginner, it is recommended to stick to transformers written in Python or bash.

## Reproducibility

... (each cell )

Intro:
- Deterministic code
- Import inside code. No variable dependencies.
- Transformers perfect isolation. Imagine being executed on a different computer (sometimes they are!). The Jupyter notebook is not there to write plots to. Don't rely on external files that exist only on your computer. Files that you create will no longer be there after the transformation has ended, unless you write it to the RESULT folder.
- Seamless dislikes files:
    - Filename in bash transformer
    - Filename in share
    - Filename in mount

## Dependency graphs

Seamless workflows are dependency graphs. Transformations depend on cells, and some cells depend on transformations. Other cells are *independent*, they just contain a parameter or a piece of code.Independent cells can be modified, dependent cells cannot.

## Structured cells

Subcell access. ...
(example with attribute access, then example with numeric index)
The other major feature is that you can add schemas for data validation, but this is more advanced.
...

## Visualization

TODO: simplified summary of visualization.md


# Guidelines

## Keep it simple

Do simple things that run fast.

Don't worry about deployment. Use seamless-new-project, no database, no jobless.

Use Jupyter

Status graph is your friend

Else you have to rely on:
- The .status attribute
- .exception
- logs

Stick to Python and bash transformers. You can use R once it is better tested in Seamless.

## Don't confuse files and cell names
...
Don't confuse "inside" files and "outside" files.
"outside" files: mounted.
"inside" files: alternative syntax for cells or for pins (good idea for bash transformers).
Finally, .share as "file.txt" is clean but does not have any effect.
Set mimetype!


## Don't rely on files or URLs

Don't put file names as strings inside cells, and don't use file names in transformation code. Doing so makes your workflow non-reproducible. For example:

```python
# Non-reproducible code!
ctx.tf = Transformer()
ctx.tf.language = "bash"
ctx.tf.inputfile = "/home/user/file.txt"
ctx.tf.code = "wc -l $inputfile"
```

Here, whenever someone or something changes the content of `/home/user/file.txt`, the result of `ctx.tf` will change. However, since the value of the input is still the same (it is still "/home/user/file.txt"), Seamless will never re-run the transformation, and re-use the previously computed result. Therefore, your workflow has become non-reproducible. And even if `/home/user/file.txt` would never change, your workflow is non-reproducible because it is now unportable between one computer and another.
The correct way to set it up is as follows:

```python
ctx.tf = Transformer()
ctx.tf.language = "bash"
ctx.c = Cell("text")

ctx.c.set(open("/home/user/file.txt").read())
# or:
ctx.c.mount("/home/user/file.txt", "r")

ctx.tf.input = ctx.c
ctx.tf.code = "wc -l input"  # note that there is no $
```

Now the workflow will contain the checksum of "/home/user/file.txt", but not its file name, and reproducibility is maintained.

The same applies for URLs. Code that downloads from an URL must not be part of transformer code. It should be executed manually in Jupyter, assigning the downloaded data to a cell.

# Beginner's gotchas

- *Problem: I changed something in the workflow, but nothing seems to happen*. Solution: try to re-translate your workflow. This is necessary after e.g. adding a new cell. Re-translation is done with `await ctx.translation()`.

- *Problem: error message "cannot mount structured cells"*. Solution: declare a celltype first. For mounting, celltype "text" is often a good choice.

    ```python
    ctx.c = Cell("text")
    # or:
    ctx.c = "somevalue"
    ctx.c.celltype = "text"
    ctx.c.mount(...)
    ```

    Don't forget to translate after declaring a celltype, with `await ctx.translation()`.

- *Problem: I am using a cell's value in other Python code, with strange errors.* Solution: by default, cells are "structured", which wraps the cell value in a "Silk" structure. You can do nice things with a Silk structure, but often you want the raw value instead. In that case, do `.value.unsilk` on a cell. Alternative solution: declare a celltype (see the previous problem). Celltype  "plain" (list, dict, int, float) or `"binary"` (Numpy) does usually what you want. In that case, don't forget to translate with `await ctx.translation()`.

- *Problem: Variables and imports missing ...* . Each step runs in isolation. ...


- *Problem*: (https://github.com/sjdv1982/seamless/issues/128)
...

- *Problem*: (https://github.com/sjdv1982/seamless/issues/56)
...


######################

<!--

- *Dependency graph*. Which data depends on which transformation? Which transformation depends on which data?

- *Topology*. The full dependency graph including connections, cell types, formats, programming languages, and other details that are necessary to make the flow of the data well-defined.
NOTE TO SELF: to make sense of "programming in two places" and "new-project".

- *Code and input parameters*. Together, ... TODO ... these are the inputs that are not user-defined, i.e. their content must be specified.
-->



<!--
If you like to explore first and make design decisions later, Seamless may suit your style.

If you feel lost, it is recommended to plan ahead, and roughly divide the creation of a project into the following phases: design, implementation, visualization, validation, deployment.
Validation and deployment 
NOTE: validation is more advanced
-->

<!--

- *Deployment*. Where will each transformation run? What are the resource limits? Where is the data stored, and for how long?
-->

<!--
- *Monitoring*. Execution status, progress, error messages.

- *User experience (UX)*. Web forms/widgets for the input. Visualization of the output.
-->


### Design phase

Designing a workflow must be done outside of Seamless, as Seamless does not (yet) support visual programming.

#### Abstract dependency graph

You should start with thinking of dependencies in an abstract way. Think of your program as a set of processes with well-defined inputs and outputs. Draw some flowcharts.

Seamless is very strict about dependencies. Normal shell commands may implicitly assume that a certain package is installed, or that certain files are present. In contrast, Seamless transformations are executed in isolation: if there is any implicit dependency, they will loudly fail. This is considered a good thing.

#### Concrete dependency graph

Once you have an abstract dependency graph, try to make it more concrete. Formulate every process as a transformation with one code input, several data/parameter inputs, and one data output. Decide the programming language for each transformation. Choose names for each input.

#### Command line workflows

Dependency graphs are most straightforward if you are porting a workflow of command line tools, where all inputs and outputs are files. There several tools that specialize in such workflows, such as SnakeMake and NextFlow. You could define your concrete dependency graph using one of these tools, and then convert it to Seamless to add monitoring and visualization. For SnakeMake, there is an automatic converter (see [example](https://github.com/sjdv1982/seamless/tree/stable/examples/snakemake-tutorial)).

A transformation may wrap a single bash command that invokes a single command line tool, or a small block of commands. In Seamless, such a transformation will be a bash transformer ([example](https://github.com/sjdv1982/seamless/blob/stable/tests/highlevel/bash.py)) that may have a Docker image ([example](https://github.com/sjdv1982/seamless/blob/stable/tests/highlevel/docker_.py)). In this case, the transformer will have a code cell written in bash, and the result must be written to the file `RESULT`. For multiple outputs, create a directory `RESULT` instead. Within a bash transformer, every input pin X is available as file X. Small inputs are also accessible as a variable $X. After execution, all files are deleted.

There are two strategies to define a command-line transformation.

1. The best way is use a bash transformer where you include the source code of every command line tool (except standard UNIX commands). This will make the transformation reproducible. The command line tool must not have any hard-coded "magic files" where it depends on. Also, if it is written in a compiled language, things become quite difficult. Seamless has compiled transformers, but they assume that data is exchanged as function arguments, and not via the file system.

2. The alternative is to treat a command line tool as part of the environment. In that case, define a Docker image, where the command line tool must be installed. This is appropriate if the command line tool is immutable over the course of the project. You may also be forced to go this route if the assumptions above are violated. Any magic files must be installed in the Docker container.


### Implementation phase

Here, the design is implemented in Seamless.

- The *topology* corresponds to the concrete dependency graph of the previous section. It is defined by modifying the Seamless graph. This is done from IPython and/or Jupyter, as shown in the [basic example](http://sjdv1982.github.io/seamless/sphinx/html/introduction.html#basic-example).

- *Code and parameters* are defined as cell checksums in the Seamless graph. However, during development it is common to link them to files, and let the files have priority over the graph in case of a conflict. The files should be under version control (Git).

- *Monitoring* is not part of the graph. In IPython/Jupyter, you can interactively access `Context.status` ,  `Cell.status` and `Transformer.status` , as well as `Cell.exception` and `Transformer.exception`. You can monitor this in the browser by setting up a poller that assigns the statuses to the cells of a second Seamless context (see the Recipe below).

In addition, you can get the stdout and stderr of a transformer using `Transformer.logs`.


### Monitoring / debugging

Use the monitor graph, inspect error messages.
Same message can be obtained by:
`Transformer.status` (i.e. typing `ctx.tf.status` in Jupyter for a transformer named `ctx.tf`), `Transformer.exception`, or `Transformer.log`. You can also link it to a Jupyter output cell (TODO).

Use simple print statements to debug.

If Seamless says that an error message was not kept, simply make
a trivial change to the code (e.g. adding the word `pass` at the end).

ADVANCED: Environment => install package => clear_exception

# Getting help

help(...) and .?
Again, status graph is your friend
<!-- TODO: add more .help, especially to graph / stdlib
