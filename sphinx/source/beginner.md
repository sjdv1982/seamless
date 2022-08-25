
# Beginner's guide

If you are beginner in programming, you focus on one thing at a time. However, Seamless is very non-linear: you can change anything at any time, interactively. If that makes you feel lost, this document contains an explanation of the basic concepts, and some beginner's guidelines, to give you a sense of direction.

## Basic Seamless features

The basic Seamless features are contexts, cells and transformers. See the [basic example](http://sjdv1982.github.io/seamless/sphinx/html/introduction.html#basic-example) for a demonstration.

Contexts contain cells and transformers and other contexts. The whole Seamless workflow is a context.

Cells contain data or code.

Transformers perform a data transformation (computation), with cells as input, and one cell as the output. One of the input cells must be a code cell.

Seamless workflows are created in Python. This can be done in a Python script, but normally it is done interactively, in IPython or Jupyter. Here, new cells, transformers and their connections are created. The workflow remains running all the time.

## Working with Seamless

- Keep it simple (link): create a new project, use Jupyter
- Children, tab completion.
- Link to web status (point out: if using project)
- Translate and compute and asynchronous
- `await load()` and `save()`
- Point to beginner's gotchas



## Programming in two places

With Seamless, there is programming in two places. First, there is the "outside": the Jupyter or IPython shell where the Seamless workflow is being created interactively. In addition, there is the "inside": 

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

...

# Guidelines

## Keep it simple

Status graph is your friend
Else you have to rely on:
- The .status attribute
- .exception
- logs

# Beginner's gotcha's
- Don't forget to translate 
- Each step runs in isolation. ...

- Don't confuse files
Don't confuse "inside" files and "outside" files.
"outside" files: mounted.
"inside" files: alternative syntax for cells or for pins (good idea for bash transformers).
Finally, .share as "file.txt" is clean but does not have any effect.
Set mimetype!

<!--

- *Dependency graph*. Which data depends on which transformation? Which transformation depends on which data?

- *Topology*. The full dependency graph including connections, cell types, formats, programming languages, and other details that are necessary to make the flow of the data well-defined.

- *Code and input parameters*. Together, ... TODO ... these are the inputs that are not user-defined, i.e. their content must be specified.
-->



<!--
If you like to explore first and make design decisions later, Seamless may suit your style.

If you feel lost, it is recommended to plan ahead, and roughly divide the creation of a project into the following phases: design, implementation, visualization, validation, deployment.
Validation and deployment 
-->

<!--
Do simple things that run fast. 

- *Deployment*. Where will each transformation run? What are the resource limits? Where is the data stored, and for how long?

Don't worry about deployment. Use seamless-new-project, no database, no jobless.
-->

<!--
- *Monitoring*. Execution status, progress, error messages.

- *User experience (UX)*. Web forms/widgets for the input. Visualization of the output.
-->


### Design phase

Desiging a workflow must be done outside of Seamless, as Seamless does not (yet) support visual programming.

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

TODO: beyond here, move some from "new-project"


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
