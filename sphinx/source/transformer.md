# Transformers

Transformers perform a data transformation (computation), with cells as input, and one cell as the output. The source code of the transformation is an additional input. In principle, transformations can be in any programming language.

Transformers must be bound to a context. `ctx.tf = Transformer()` creates a new transformer `ctx.tf`, bound to context `ctx`.

***In the documentation below, `ctx.tf = Transformer()` is assumed.***

## Pins

The inputs of a transformer are declared as *pins*. If `ctx.tf` does not have a pin `x`, then `ctx.tf.x = 10` creates a new pin `x` with the value 10. If it does have a pin `x`, it assigns the value 10 to it. A pin can also be connected to a cell `ctx.c` using `ctx.tf.x = ctx.c`.

Pin *values* can be accessed with e.g. `ctx.tf.x.value` for pin `x`.

Pin *attributes* can be accessed using `ctx.tf.pins`, e.g `ctx.tf.pins.x` for pin `x`. The celltype of a pin `x` can be changed using `ctx.tf.pins.x.celltype` . Pin `x` can be deleted using `del ctx.tf.pins.x` or `del ctx.tf.x`.

Pins can be mounted to files, just like cells can, e.g `ctx.tf.x.mount(...)` for pin x. The same restrictions apply as for cells regarding dependent values and celltype. See the documentation of Cell for more details.

Newly created/deleted/connected/mounted pins require a re-translation of the context to take effect. This is also the case for a change in pin celltype.

### Alternative pin syntax

As an alternative pin syntax, you can also use `ctx.tf["x"] = 10`.
This allows pins with names that are not valid Python attributes, such as `ctx.tf["file.txt"] = 10`.

### Code pin

There is one special pin that always exists: `ctx.tf.code`. This pin defines the source code of the transformer, in the programming language defined by `ctx.tf.language`. Depending on the programming language, other special pins may exist as well (see below).

## Transformer execution

Transformers (re-)execute whenever any of their pins change in value. If any pin is None, the transformer result is None as well. Transformers execute in perfect isolation:

- Concurrently, without blocking the ipython shell, file mounting, HTTP sharing, or other transformers.
- With no access to any variables other than the values of the pins.
- In a separate directory, with no access to the directory where Seamless is running.

Transformers that are being executed are canceled when any of their pins change.
Seamless keeps track of the (checksum of) a transformation result, as a function of (the checksums of) the input value. If the result of a transformation is already known, it is not re-executed.

## Transformer result

The result of a transformer is None until the transformation has completed successfully.
It is available as the *result pin* `ctx.tf.result`.
The value of the result is available as `ctx.tf.result.value`.

The celltype of the result is always "structured". Use `ctx.tf.result.value.unsilk` to get it as "mixed" (i.e. a JSON-encodable Python object, a Numpy array, or a mix of both).

The execution status of the transformer can be retrieved using `ctx.tf.status`. If it is "error", the error message can be retrieved using `ctx.tf.exception`.

Transformers can print to stdout or stderr during execution. The printed output will be in `ctx.tf.logs`, together with the execution time and result.

`ctx.tf.logs` is only available after execution has finished. It is possible to put a transformer in debug mode in order to get more immediate feedback (see the "debugging" documentation section).

To assign a transformer result to a cell `ctx.c`, do `ctx.c = ctx.tf`, or `ctx.c = ctx.tf.result` (preferred syntax).

## Transformer programming languages

In principle, Seamless transformers can be in any programming language.
The language is set in the `Transformer.language` field.

The following languages are supported directly:

- "python" (default)
- "bash"
- "ipython"
- "r"
- compiled languages:
  - "c"
  - "cpp"
  - "fortran"

Cython is also bundled with the Seamless Docker image. Within an IPython transformer, you can use %%cython magics to embed Cython code.

Seamless has an API to dynamically add support for new programming languages. See the section "Adding new transformer languages" below.

## Python transformers

Python transformers have `ctx.tf.language = "python"`, which is the default. Python transformers can also be directly created from a Python function:

```python
def func(a, b):
    return a + b
ctx.tf = func
```

The last statement creates the transformer `ctx.tf`. Seamless inspects the function signature of `func` to create two pins, `ctx.tf.a` and `ctx.tf.b`, with undefined value.
In addition, `ctx.tf.code` is set to the source code of `func`.
You may want to mount `ctx.tf.code` to a `.py` file and edit that file in a text editor.

Note that during execution, the Python transformer has no access to the scope/namespace of ctx.
For example, the following will not work:

```python
import numpy as np
def func(a, b):
    return np.arange(a, b)
ctx.tf = func
```

This is because `np` is not defined inside of `func`, but outside of it, so the transformer will not have access to it. The solution is to put imports inside the transformer code:

```python
def func(a, b):
    import numpy as np
    return np.arange(a, b)
ctx.tf = func
```

Python source code can be an expression, a function, or simply a block of code. For an expression or a function, the return value is the result value. A code block must define a variable named "result".

## Preliminary results and progress

***IMPORTANT: This documentation section is a stub.***

## Bash transformers

Bash transformers have `ctx.tf.language` set to "bash".

In both cases, `ctx.tf.code` is written in bash.
The bash code will have access to every input pin stored as a file of the same name.
Small inputs are also available as a bash variable of the same name.
You can use the alternative pin syntax to specify input pins that will be stored as a file with an extension: `ctx.tf["inputfile.txt"] = ctx.inputfile`, where `ctx.inputfile` is a cell.

Execution takes place in a temporary directory, that is cleaned up afterwards. The bash code is literally executed under bash, Seamless does not perform parsing or variable substitution of any kind.

After execution, Seamless expects that a file or directory with the name `RESULT` has been created.
This file/directory must contain the result of the transformation. This result will be assigned to the result pin (`ctx.tf.result`). In case of a result directory, the result will be a dict where the keys are the original file names within the `RESULT` directory and the values are the contents of those files. To get the individual result file values, use subcells (see the Cell documentation for more details). For example:

```python
ctx.tf = Transformer()
ctx.tf.language = "bash"
ctx.tf.a = 5
ctx.tf["file.txt"] = "test"
ctx.tf.code = """
mkdir RESULT
seq $a > RESULT/a.list
mv file.txt RESULT
"""
ctx.result = ctx.tf.result
ctx.alist = ctx.result["a.list"]
ctx.alist.celltype = "text"
ctx.filetxt = ctx.result["file.txt"]
ctx.filetxt.celltype = "text"
await ctx.computation()
print(ctx.alist.value)
print()
print(ctx.filetxt.value)
```

```text
1
2
3
4
5

test
```

Bash transformers with a `docker_image` attribute have their bash script executed inside a Docker container.
Note that to execute a such transformer under standard Seamless (i.e. without configuring job servants to delegate the work), you will need to expose the Docker socket to Seamless, e.g using `seamless-bash-trusted` or `seamless-jupyter-trusted`. Also, unlike `docker run`, Seamless does not pull any Docker images for you.

An example of a bash transformer is [here](https://github.com/sjdv1982/seamless/blob/stable/tests/highlevel/bash.py). An example of a bash transformer with Docker image is [here](https://github.com/sjdv1982/seamless/blob/stable/tests/highlevel/docker_.py).

Note that bash transformers are executed in a separate temporary execution directory, they have no access to the file system available to `ctx`. The execution directory is deleted after execution.
Also, the files inside this directory have file names that correspond only to the name of the transformer pins. There is also absolutely no relation with the cells to which these are connected. There is also no relation between these file names and the file names under which cells/pins are mounted or shared. This is demonstrated using the following example code:

```python
ctx.name1 = 12
ctx.name1.celltype = "int"
ctx.name1.mount("name2.txt")
ctx.name1.share("name3.txt")
ctx.tf = Transformer()
ctx.tf.language = "bash"
ctx.tf.name4 = ctx.name1
ctx.tf.code = """
# name2.txt or name3.txt do NOT exist ...
mkdir RESULT
echo $name4 > RESULT/x
seq $name4 > RESULT/y
cat name4 name4 > RESULT/z
"""
ctx.result = ctx.tf
ctx.x = ctx.result.x
ctx.y = ctx.result.y
ctx.z = ctx.result.z
ctx.x.celltype = "int"
ctx.x.mount("name5.txt")
ctx.x.share("name6.txt")
ctx.compute()
```

## Compiled transformers

***IMPORTANT: This documentation section is a stub.***

**Relevant examples:**
- [BC](https://github.com/sjdv1982/seamless/tree/stable/examples/BC)

See [Running examples](https://sjdv1982.github.io/seamless/sphinx/html/getting-started.html#running-examples-locally) on how to run examples.

**Relevant test examples:**

- [transformer-compiled.py](https://github.com/sjdv1982/seamless/tree/stable/tests/highlevel/transformer-compiled.py)

- [transformer-compiled-error.py](https://github.com/sjdv1982/seamless/tree/stable/tests/highlevel/transformer-compiled-error.py)

See [Running tests](https://sjdv1982.github.io/seamless/sphinx/html/getting-started.html#running-tests-locally) on how to execute tests.

<!--

TODO: link to validation:schemas
TODO: link to modules
...
TODO: from tutorial:
- Compiled transformers:
    - header, integrator, executor
    - main_module multiple files (link to module)
-->

## Adding new transformer languages

***IMPORTANT: This documentation section is a stub.***

(integrate or delegate to [documentation on environments](https://sjdv1982.github.io/seamless/sphinx/html/environments))

**Relevant test examples:**

- [environment.py](https://github.com/sjdv1982/seamless/tree/stable/tests/highlevel/environment.py). At the end of this test, it is shown how to add Rust support. First, Rust must be installed in the container using "mamba install rust".

- [environment2.py](https://github.com/sjdv1982/seamless/tree/stable/tests/highlevel/environment2.py). This test shows how to add Go support. First, Go must be installed in the container using "mamba install go-cgo".

- [environment3.py](https://github.com/sjdv1982/seamless/tree/stable/tests/highlevel/environment3.py). This test shows how to add direct Cython support (without IPython magics).

- [environment6.py](https://github.com/sjdv1982/seamless/tree/stable/tests/highlevel/environment6.py). This test shows how to add PHP support. First, install php7.4-cli with apt and python-bond with pip.

See [Running tests](https://sjdv1982.github.io/seamless/sphinx/html/getting-started.html#running-tests-locally) on how to execute tests.

<!--
Is Advanced topic
...

...

TODO: 
- Pin celltypes: link to cell
- Pin "as_" attribute

TODO: from tutorial:

Intro:

- Python transformers
- .inp and .result (link to structured cells)
- Bash transformers

    - RESULT file or directory
    - filedict/filelist subcelltype TODO

- Transformers in IPython and R

Intermediate:

- Docker (link to environments)
- Meta parameters (computation times etc.)
- Transformations and checksums (link to "Seamless explained")

In-depth:

- Hacking on bash/compiled transformers (not interactively)
- Changing the translation machinery (not interactively)
- Irreproducible transformers (link to determinism)

- cancel, clearing exceptions
-->
