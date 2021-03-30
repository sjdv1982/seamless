Transformers
============

Transformers perform a data transformation (computation), with cells as input, and one cell as the output. The source code of the transformation is an additional input. In principle, transformations can be in any programming language. Currently, transformations in Python, IPython, bash/docker,or a compiled language (C, C++ or Fortran) are supported.

Transformers must be bound to a context. `ctx.tf = Transformer()` creates a new
transformer `ctx.tf`, bound to context `ctx`.

## Pins

The inputs of a transformer are declared as *pins*. If `ctx.tf` does not have a pin `x`,
then `ctx.tf.x = 10` creates a new pin `x` with the value 10. If it does have a pin `x`, it assigns the value 10 to it. A pin can also be connected to a cell `ctx.c` using `ctx.tf.x = ctx.c`.

There is one special pin that always exists: `ctx.tf.code`. This pin defined the source code of the transformer, in the programming language defined by `ctx.tf.language`. Depending on the programming language, other special pins may exist as well (see below).

Pins can be accessed using `ctx.tf.pins.x`. The celltype of a pin can be changed using `ctx.tf.pins.celltype` . Pins can be deleted using `del ctx.tf.pins.x` (the next version of Seamless will support `del ctx.tf.x`).

Pins can be mounted to files, just like cells can. The same restrictions apply regarding dependent values and celltype. See the documentation of Cell for more details.

Newly created/deleted/connected/mounted pins require a re-translation of the context to take effect. This is also the case for a change in pin celltype.

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
The value of the result is available as `ctx.tf.result.value`
The celltype of the result is always "structured". Use `ctx.tf.result.value.unsilk` to get it as "mixed" (i.e. a JSON-encodable Python object, a Numpy array, or a mix of both).

The execution status of the transformater can be retrieved using `ctx.tf.status`. If it is "error", the error message can be retrieved using `ctx.tf.exception`.

Transformers can print to stdout or stderr during execution.
The printed output will be part of the error message if the transformation fails.
If it succeeds, the printed output will be in `ctx.tf.logs`.

## Python transformers

Python transformers have `ctx.tf.language = "python"`, which is the default. Python transformers can also be directly created from a Python function:
```python
def func(a, b):
    return a + b
ctx.tf = func
```
This sets `ctx.tf.code` to the source code of `func`. You may want to mount `ctx.tf.code` to a `.py` file and edit that file in a text editor.
When `ctx.tf` is first created, Seamless inspects the function signature of `func`
to create two pins, `ctx.tf.a` and `ctx.tf.b`, with undefined value.

Note that during execution, the Python transformer has no access to the scope/namespace of ctx.
For example, the following will not work:

```python
import numpy as np
def func(a, b):
    return np.arange(a, b)
ctx.tf = func
```

This is because `np` is not defined inside of `func`, but outside of it,
so the transformer will not have access to it.

TODO: document preliminary and progress

## Bash/docker transformers

Bash and Docker transformers have `ctx.tf.language` set to "bash" and "docker".

In both cases, `ctx.tf.code` is written in bash. The bash script will have access to every input pin stored as a file of the same name. Small inputs are also available as a bash variable of the same name. The bash code is literally executed under bash, Seamless does not perform parsing or substitution of any kind. After execution, Seamless expects that a file with the name `RESULT` has been created. This file must contain the result of the transformation. If multiple files are created (NOTE: for the next version of Seamless, `RESULT` may be a directory as well).
After execution, all files are deleted.

Docker transformers are identical to bash transformers, except for the extra pin `ctx.tf.docker_image`. Note that to execute Docker transformer under standard Seamless
(i.e. without configuring job servants to delegate the work), you will need to expose the Docker socket to Seamless, e.g using `seamless-bash-trusted` or `seamless-jupyter-trusted`.

An example of a bash transformer is [here](https://github.com/sjdv1982/seamless/blob/stable/tests/highlevel/bash.py). An example of a Docker transformer is [here](https://github.com/sjdv1982/seamless/blob/stable/tests/highlevel/docker_.py).

Note that bash/docker transformer are executed in a separate execution directory, they have no access to the file system available to `ctx`. The execution directory is deleted after execution.
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
echo $name4 > x
seq $name4 > y
cat name4 name4 > z
tar --mtime=1970-01-01 -czf RESULT x y z
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

TODO