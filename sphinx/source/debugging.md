### Debugging

To debug your code, you can use either print statements, or a debugging session with breakpoints.

#### Debugging with print statements

Seamless transformations can be executed anywhere. Therefore, they do not print their stdout or stderr to any terminal while they execute. Stdout and stderr are only captured when the transformation has finished.

For Python transformers, the transformation is aborted if an exception is raised. `Transformer.exception` will then contain the exception traceback, stdout and stderr.
If no exception is raised, stdout and stderr can be retrieved using `Transformer.logs`

For bash/Docker transformers, if any launched process returns with a non-zero error code, the transformation is aborted. `Transformer.exception` will then contain the bash error message, stdout and stderr. Else, stdout/stderr will be discarded. Therefore, if you want to debug with print statements, exit with a non-zero exit code (`exit 1`).

For compiled transformers (i.e. written in C/C++/Fortran/...), you should *not* do `exit(...)` with a non-zero exit code: this kills the transformation process immediately, including the machinery to capture stdout and stderr. Instead, make the main `int transform(...)` function return a non-zero value.

#### Debugging sessions

THE FOLLOWING IS OUTDATED
Visual Studio Code and other IDEs do not yet support Seamless transformers.

***Python transformers***

To debug a Python transformer, you can use a slightly modified version of the pdb debugger. Add the following to your transformation code:
```python
from seamless.pdb import set_trace
set_trace()
```

NOTE: unfortunately, the pdb debugger only works if you execute Seamless with `python`,
not with `ipython` or Jupyter.


***Compiled transformers***

Compiled transformers can be debugged with a debugger such as gdb.

For this, set `Transformer.debug` to `True` and re-translate the graph.
(You may have to make a minimal change in the source code or input. Remind that Seamless does not re-execute transformations that have already been performed,
debug or not).

Once the transformer executes, you will see a Process ID printed.

Start a separate shell in the same Docker container using `seamless-shell-existing`
You will be root in this shell.

Type "gdb" to start a GDB terminal.

In the GDB terminal, type the following (where XXX is the process ID):
```
(gdb) attach XXX
(gdb) break main.cpp:transform
(gdb) signal SIGUSR1
```
and gdb will break when your main `transform` function starts.

If your transformer is written in C, the main file will be "main.c" instead of "main.cpp".

Whenever the transformer re-executes (due to changed source code or inputs), you will have to re-attach, but your breakpoints normally remain active.

NOTE: integration with Visual Studio code is currently in progress.

/OUTDATED

TODO: debugging modules (link to modules)