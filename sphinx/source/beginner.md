# Beginner's guide

If you are beginner in programming, you focus on one thing at a time. However, Seamless is very non-linear: you can change anything at any time, interactively. If that makes you feel lost, this guide can give you a sense of direction.

The most important guidelines for beginners are: "learn the basics", "keep it simple", and "one thing after another". The guide consists of one section for each guideline, followed by general guidelines and troubleshooting.

***Disclaimer**: this guide is by definition a rather patronizing document. If you are an experienced developer, you can skim or skip it altogether: the [next section](http://sjdv1982.github.io/seamless/sphinx/html/explained.html) will be more useful to you. In any case, feel free to ignore every guideline that doesn't apply to you. If you believe that the guide contains bad advice (i.e. guidelines that shouldn't apply to **anyone**), you are very welcome to propose improvements*.

## Learning the basics

### Basic Seamless features

***IMPORTANT: This documentation section is a draft. The preliminary text is shown below***

The basic Seamless features are contexts, cells and transformers. See the [basic example](http://sjdv1982.github.io/seamless/sphinx/html/introduction.html#basic-example) for a demonstration.

Contexts contain cells, transformers and other contexts. The whole Seamless workflow is a context.

Cells contain data or code.

Transformers perform a data transformation (computation), with cells as input, and one cell as the output. One of the input cells must be a code cell.

Seamless workflows are created in Python. This can be done in a Python script, but normally it is done interactively, in IPython or Jupyter. Here, new cells, transformers and their connections are created. The workflow remains running all the time.

You can save the entire workflow to a file, and then load it back. Workflows (`.seamless` files) are very small, because they contain only checksums. The underlying code data must be stored elsewhere. By default, it is stored as files inside the `vault/` folder.

### Mounting a cell to the file system

***IMPORTANT: This documentation section is a stub.***

<!-- This is just an aide to make it easier for you to edit a cell's data or code. It doesn't play any role in the execution of the workflow.
(block vs function (object))
-->

### Programming in two places

With Seamless, there is programming in two places. First, there is the "outside": the Jupyter or IPython shell where the Seamless workflow is being created interactively. Here you enter Python code that does something with the workflow, for example: adding a new Seamless cell, changing a value, creating a connection, printing a status or a result, etc.

In addition, there is code on the "inside", code that is part of the workflow. This code is executed by Seamless, in reaction to changes in one of its inputs. In the example below, the inside code is written in an R file.

#### Example 1

##### asPercent.R: "inside" code

```R
asPercent <- function(x){
 percent <- round(x * 100, digits = 1)
 result <- paste(percent, "%", sep = "")
 return(result)
}

frac = a / b
result <- asPercent(frac)
```

##### example.ipynb: "outside" code

```python
ctx.asPercent = Transformer()
ctx.asPercent.a = 22
ctx.asPercent.b = 7
ctx.asPercent.language = "r"
ctx.asPercent.code.mount("asPercent.R")

await ctx.computation()
print(ctx.asPercent.result.value)
```

```text
<Silk: 314.3% >
```

Concretely, what this means in the example above is that the pins (`a`, `b` and `result`) are the only way that the "inside" and the "outside" code can communicate. For the rest, the "inside" code has no access to "outside" code variables such as `ctx`. And the "outside" code has no access to "inside" code variables such as `frac` and `percent`. This is not difficult to see: after all, the inside code is in a different file, and written in a different language (R for the inside, Python for the outside). But now, consider a second example that does exactly the same thing:

#### Example 2

##### example.ipynb: both "outside" and "inside" code

```python

# inside code
def asPercent(a, b):
    frac = a / b
    percent = round(frac * 100, 1)
    return "{}%".format(percent)

# outside code
ctx.asPercent = asPercent
ctx.asPercent.a = 22
ctx.asPercent.b = 7

await ctx.computation()
print(ctx.asPercent.result.value)
```

```text
<Silk: 314.3% >
```

The exact same boundaries between inside and outside code as in the first example apply: inside and outside code can't access each other's variables, the only thing that is shared are `a`, `b` and `result`. The *reason* why is that inside code must be reproducible, giving always the same result no matter what the outside code is. But it is much less obvious here than in the first example, because of the single-file single-language implementation. Seamless gives you the choice if you want to mount your code to an external file or not. Regarding language, "outside" code is always in Python (or IPython). However, "inside" code *can* be in Python, but it doesn't have to be. Seamless supports many programming languages: bash, Python, and C/C++ are well-tested. Other languages such as R, Cython, Fortran or Go are also supported, but less well-tested (and may require a bit more setup). As a beginner, it is recommended to stick to transformers written in Python or bash. Or perhaps simple R code, as the first example shows.

### Sharing a cell over HTTP

***IMPORTANT: This documentation section is a stub.***

### Dependency graphs

***IMPORTANT: This documentation section is an outline. The outline is shown below***

Seamless workflows are dependency graphs.
<!--

- *Dependency graph*. Which data depends on which transformation? Which transformation depends on which data?

- *Topology*. The full dependency graph including connections, cell types, formats, programming languages, and other details that are necessary to make the flow of the data well-defined.
NOTE TO SELF: to make sense of "programming in two places" and "new-project".

- *Code and input parameters*. Together, ... TODO ... these are the inputs that are not user-defined, i.e. their content must be specified.
-->

Transformations depend on cells, and some cells depend on transformations. Other cells are *independent*, they just contain a parameter or a piece of code.Independent cells can be modified, dependent cells cannot.

<!--

- The *topology* corresponds to the concrete dependency graph of the previous section. It is defined by modifying the Seamless graph. This is done from IPython and/or Jupyter, as shown in the [basic example](http://sjdv1982.github.io/seamless/sphinx/html/introduction.html#basic-example).

- *Code and parameters* are defined as cell checksums in the Seamless graph. However, during development it is common to link them to files, and let the files have priority over the graph in case of a conflict. The files should be under version control (Git).

- *Deployment*. Where will each transformation run? What are the resource limits? Where is the data stored, and for how long?
-->

<!--
- *Monitoring*. Execution status, progress, error messages.

- *User experience (UX)*. Web forms/widgets for the input. Visualization of the output.


-->

## Dividing the work into phases

If you like to explore first and make design decisions later, Seamless may suit your style, even if you are a beginner. However, if you feel lost, it is recommended to plan ahead, and divide the work into phases that you complete one after another. This gives you an idea of what you should do at the moment. But don't hesitate to go back to a previous phase at any time when you feel that it needs to be corrected.

The following phases are recommended: design, implementation, visualization, validation, deployment. For validation, see the [validation documentation](http://sjdv1982.github.io/seamless/sphinx/html/validation.html); you can choose to skip it for simple projects.

### Design phase

Designing a workflow must be done outside of Seamless, as Seamless does not (yet) support any kind of visual programming. It involves drawing a dependency graph, first in an abstract sense, then concretely.

#### Abstract dependency graph

The goal of this phase is to describe your entire computation as a workflow in an abstract way. First, divide your computation into different steps. Put the steps in order. Such a linear sequence of steps is the simplest possible workflow. Most of the time, your workflow is non-linear: for example, step 3 may not require step 2 to be complete, only step 1. In other words, step 3 depends on step 1, and step 2 depends on step 1, but step 3 does not depend on step 2. Draw a flowchart, consisting of all of the steps and their dependencies. Give names to the steps, and also enumerate their inputs and outputs. If step 3 depends on step 1, indicate if step 3 needs the entire output or only part of it. Once you have done this, your flowchart is now essentially a *dependency graph*.

You must avoid cyclic dependencies in your graph, i.e. computations that (directly or indirectly) have their own output as input. This happens if your workflow has several iterations where the same steps are being performed with the output of the previous iteration. Seamless has support for cyclic dependencies, but such workflows are not for beginners.

#### Concrete dependency graph

Once you have a dependency graph, try to make it as concrete as possible. Formulate every computation as a block with one code input, several data/parameter inputs, and one data output. (You can have multiple data outputs, although the implementation will then be a little bit more complex, using Seamless structured cells). Decide the programming language for each block. Choose names for each input. These computation blocks will later become Seamless transformers. The inputs and outputs will become cells.

Seamless is very strict about dependencies. If your computation consists of shell commands, make sure that you understand their inputs and outputs. Normal shell commands may implicitly assume that a certain package is installed, or that certain files are present. In contrast, Seamless transformations are executed in isolation: if there is any implicit dependency, they will loudly fail. This is considered a good thing, because it detects problems in reproducibility. For reproducible computations, all inputs and outputs (no matter if they are files or Seamless cells) must be carefully enumerated. If not, your workflow may work on your computer, but nowhere else. With Seamless, it will probably work not at all.

If you can avoid the above problem, and if you are porting an existing workflow (bash, Jupyter, Snakemake) that is not too complex, you could skip the concrete dependency graph and move straight to the implementation.

### Implementation phase

Here, the design is implemented in Seamless.

#### Creating an new project

***IMPORTANT: This documentation section is an outline. The outline is shown below***

... TODO ... (choose PROJDIR and PROJNAME, bash snippet)

```bash
conda activate seamless
...
```

#### Starting the implementation

***IMPORTANT: This documentation section is a stub.***
<!--
... (seamless-jupyter-trusted) ...
-->

#### Examples of porting existing workflows

If you are a beginner, the implementation phase is much simpler if you are starting from an existing workflow. There are two examples of how to do that for a workflow that has been already defined in a Jupyter notebook. In both cases, an interactive web interface is built as well.

- The [webserver-example](https://github.com/sjdv1982/seamless/tree/stable/examples/webserver-example) starts from an existing workflow that is mixed, with some steps in bash and others in Python. A new Seamless project has already been created.

- The [webserver-demo](https://github.com/sjdv1982/seamless/tree/stable/examples/webserver-demo) shows how to port a pure-Python workflow to Seamless. NOTE: This is a self-contained notebook that creates a new Seamless project by itself. You should not do that, instead you should create a new Seamless project yourself (see above).

#### Porting an existing command line workflow

Dependency graphs are most straightforward if you are starting from an existing workflow consisting of command line tools, where all inputs and outputs are files. In many cases, such a workflow will have been implemented as a linear bash script. However, there several frameworks that specialize in such workflows, such as Snakemake and NextFlow. You could implement your workflow initially using one of these frameworks, and then port it to Seamless to add an interactive web interface, monitoring and visualization. For Snakemake, there is an automatic converter (see [example](https://github.com/sjdv1982/seamless/tree/stable/examples/snakemake-tutorial)), although it doesn't support all Snakemake features.

Each computation wraps a single bash command that invokes a single command line tool, or a small list of commands. In Seamless, such a computation will be a bash transformer ([example](https://github.com/sjdv1982/seamless/blob/stable/tests/highlevel/bash.py)) that may have a Docker image ([example](https://github.com/sjdv1982/seamless/blob/stable/tests/highlevel/docker_.py)). In this case, the transformer will have a code cell written in bash, and the result must be written to the file `RESULT`. For multiple outputs, create a directory `RESULT` instead. Within a bash transformer, every input pin X is available as file X. Small inputs are also accessible as a variable $X. After execution, all files are deleted.

There are two strategies to define a command-line transformation.

1. The best way is use a bash transformer where you include the source code of every command line tool that is being used (except standard UNIX commands). This will make the transformation reproducible. There are two limitations:

    - The command line tool must not have any hard-coded "magic files" where it depends on, unless the content of such a file can be included as one of the transformer inputs.

    - If the command line tool is written in a compiled language, things become quite difficult. Seamless has compiled transformers, but they assume that data is exchanged as function arguments, and not via the file system. As a beginner, you are not recommended to use compiled transformers.

2. The alternative is to treat a command line tool as part of the environment. In that case, define a Docker image, where the command line tool must be installed. This is appropriate if the command line tool is immutable over the course of the project. You may also be forced to go this route if you run into the limitations above. Any magic files must be installed in the Docker container.

#### Monitoring / debugging

***IMPORTANT: This documentation section is a draft. The preliminary text is shown below***

- *Monitoring* is not part of the graph. In IPython/Jupyter, you can interactively access `Context.status` ,  `Cell.status` and `Transformer.status` , as well as `Cell.exception` and `Transformer.exception`. You can monitor this in the browser... TODO

In addition, you can get the stdout and stderr of a transformer using `Transformer.logs`.

Use the monitor graph, inspect error messages.
Same message can be obtained by:
`Transformer.status` (i.e. typing `ctx.tf.status` in Jupyter for a transformer named `ctx.tf`), `Transformer.exception`, or `Transformer.log`. You can also link it to a Jupyter output cell (TODO).

`Transformer.result.value.unsilk` ...

Use simple print statements to debug.

ADVANCED: Environment => install package => clear_exception

## How to keep it simple

***IMPORTANT: This documentation section is an outline. The outline is shown below***

TODO: merging the next section into here...

- Keep it simple (link): create a new project, use Jupyter
- Children, tab completion.
- Link to web status (point out: if using project)
- Translate and compute and asynchronous. `await ctx.translation()` and `await ctx.computation()`.
- `await load()` and `save()`

### Keep it simple

Do simple things that run fast.

Don't worry about deployment. Use seamless-new-project, no database, no jobless.

Use Jupyter

Status graph is your friend

Else you have to rely on:

- The .status attribute
- .exception
- logs


<!--
### Getting help

(TODO when the help system has more entries)

help(...) and .?
Again, status graph is your friend
 TODO: add more .help, especially to graph / stdlib
!-->

### Simple cells

***IMPORTANT: This documentation section is a stub.***
<!--
STUB. Discuss structured cells and celltype.

#### Structured cells

Subcell access. ...
(multiple outputs)
(example with attribute access, then example with numeric index)
The other major feature is that you can add schemas for data validation, but this is more advanced.
...
-->

### Simple web interfaces

***IMPORTANT: This documentation section is a stub.***

<!-- TODO:  Discuss browser URL vs web form. Discuss making it work vs making it pretty. Link to visualization, recommend to read it. -->

### Simple deployment

***IMPORTANT: This documentation section is a stub.***

<!-- TODO (based on serve-graph, sharing the .seamless and zip). -->

### Simple features

Seamless is more than just cells, transformers and contexts. But as a beginner, you are recommended to stick to them. Once you feel comfortable, you could then learn [validation](http://sjdv1982.github.io/seamless/sphinx/html/validation.html), using [libraries](http://sjdv1982.github.io/seamless/sphinx/html/libraries.html), or [debugging](http://sjdv1982.github.io/seamless/sphinx/html/debugging.html). Other Seamless features are better suited for experienced programmers. In particular, as a beginner, you should stay away from macros and the low level. In addition, [deep cells](http://sjdv1982.github.io/seamless/sphinx/html/deepcell.html) must be used with caution, as mistakes may lead to massive use of memory, disk space and/or download bandwidth. In the future, it may be possible to configure Seamless such that manual confirmation is required before massive resources are being claimed via deep cells.

## Do's and don'ts

### Do write reproducible code

***IMPORTANT: This documentation section is a stub.***

<!--
Intro:
- Deterministic code
- Import inside code. No variable dependencies.
- Transformers perfect isolation. Imagine being executed on a different computer (sometimes they are!). The Jupyter notebook is not there to write plots to. Don't rely on external files that exist only on your computer. Files that you create will no longer be there after the transformation has ended, unless you write it to the RESULT folder.
- Seamless dislikes files:
    - Filename in bash transformer
    - Filename in share
    - Filename in mount
-->

### Don't confuse files and cell names

***IMPORTANT: This documentation section is an outline. The outline is shown below***
...
Don't confuse "inside" files and "outside" files.
"outside" files: mounted.
"inside" files: alternative syntax for cells or for pins (good idea for bash transformers).
Finally, .share as "file.txt" is clean but does not have any effect.
Set mimetype!

### Don't rely on file names or URLs

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

## Troubleshooting

- *Problem: I changed something in the workflow, but nothing seems to happen*.

    Solution: try to re-translate your workflow. This is necessary after e.g. adding a new cell. Re-translation is done with `await ctx.translation()`.

- *Problem: error message "cannot mount structured cells"*. 

    Solution: declare a celltype first. For mounting, celltype "text" is often a good choice.

    ```python
    ctx.c = Cell("text")
    # or:
    ctx.c = "somevalue"
    ctx.c.celltype = "text"
    
    ctx.c.mount("somefile.txt")
    ```

    Don't forget to translate after declaring a celltype, with `await ctx.translation()`.

- *Problem: I am using a cell's value in other Python code, with strange errors.* 

    Solution: by default, cells are "structured", which wraps the cell value in a "Silk" structure. You can do nice things with a Silk structure, but often you want the raw value instead. In that case, do `.value.unsilk` on a cell. Alternative solution: declare a celltype (see the previous problem). Celltype  "plain" (list, dict, int, float) or `"binary"` (Numpy) does usually what you want. In that case, don't forget to translate with `await ctx.translation()`.

- *Problem: Variables and imports missing ...* .

    ***IMPORTANT: This documentation section is a stub.***
    <!-- Each step runs in isolation. ... -->

- *Problem*: (https://github.com/sjdv1982/seamless/issues/128)
    
    ***IMPORTANT: This documentation section is a stub.***

- *Problem*: (https://github.com/sjdv1982/seamless/issues/56)
    
    ***IMPORTANT: This documentation section is a stub.***

- *Problem*: [error message not kept]
    
    ***IMPORTANT: This documentation section is an early draft. The raw text material is shown below***
    
    ...
    
    If Seamless says that an error message was not kept, simply make
    a trivial change to the code (e.g. in Python, adding the word `pass` at the end. In bash, simply add a comment #).

- *Problem*: [cachemiss error]

    ***IMPORTANT: This documentation section is an early draft. The raw text material is shown below***
    
    ... (Misconfiguration. Save and load... first git commit. vault/*/<name of checksum> in earlier versions)
