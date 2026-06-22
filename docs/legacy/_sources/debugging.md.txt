# Debugging

The goal of debugging is to get rid of errors in the code inside your workflow, i.e. transformer code.

To debug your transformer code, you can use either print statements, or a debugging session with breakpoints.

## Debugging with print statements

This the easiest form of debugging: add print statements (or `echo`/`cat`/`cout`/`printf`/...) to your transformer code.

For Python transformers, the transformation is aborted if an exception is raised. `Transformer.exception` will then contain the exception traceback, stdout and stderr. If no exception is raised, stdout and stderr can be retrieved using `Transformer.logs`

For bash/Docker transformers, if any launched process returns with a non-zero error code, the transformation is aborted. `Transformer.exception` will then contain the bash error message, stdout and stderr. If there is no non-zero error code, stdout and stderr can be retrieved using `Transformer.logs`.

For compiled transformers (i.e. written in C/C++/Fortran/...), you must *not* do `exit(...)` with a non-zero exit code: this kills the transformation process immediately, including the machinery to capture stdout and stderr. Instead, make the main `int transform(...)` function return a non-zero value.

Seamless transformations can be executed anywhere. Therefore, by default, *they do not print their `stdout` or `stderr` to any terminal while they execute*. `stdout` and `stderr` are only captured when the transformation has finished. You can overrule this behavior with `Transformer.debug.direct_print = True`. This will force local evaluation (transformation jobs will not be forwarded to e.g. jobless), and the result of print statements are printed directly to `stdout`/`stderr`, or to a file specified in `Transformer.debug.direct_print_file`. See [this test](https://github.com/sjdv1982/seamless/tree/stable/tests/highlevel/delay-direct-print-file.py) for a demonstration.

**Relevant test examples:**

- [simpler-tf-print.py](https://github.com/sjdv1982/seamless/tree/stable/tests/highlevel/simpler-tf-print.py)

- [bash-debug.py](https://github.com/sjdv1982/seamless/tree/stable/tests/highlevel/bash-debug.py)

- [docker-debug.py](https://github.com/sjdv1982/seamless/tree/stable/tests/highlevel/docker-debug.py)

See [Running tests](https://sjdv1982.github.io/seamless/sphinx/html/getting-started.html#running-tests-locally) on how to execute tests.

## Debugging sessions

Debugging sessions with breakpoints are directly supported, but only in Visual Studio Code. Other IDEs are currently not supported, but they should be in the future. If you are willing to help, see [this GitHub issue](https://github.com/sjdv1982/seamless/issues/132).

Debugging sessions with Seamless is best learned by running some of the Seamless tests below. Open a terminal within Visual Studio Code. Start a Seamless container with `seamless-bash`, the  do `cd ~/seamless-tests/highlevel`, and run any test with `ipython -i` (any test) or `python` (any test that doesn't end with "-shell.py"). Follow the instructions printed on screen.

NOTE: `seamless-bash` is needed because its exposes ports 5679-5785 for use by `debugpy`. If you get a "connection refused" error in Visual Studio Code, you probably used `seamless-bash-safe` instead.

### Debug mode: light or sandbox

***IMPORTANT: This documentation section is a stub.***
(shells can be opened only in sandbox mode. Not for compiled transformers)

### Debugging Python transformers

***IMPORTANT: This documentation section is a stub.***

**Relevant test examples:**

- [debugmode-py-light.py](https://github.com/sjdv1982/seamless/tree/stable/tests/highlevel/debugmode-py-light.py)

- [debugmode-py-sandbox.py](https://github.com/sjdv1982/seamless/tree/stable/tests/highlevel/debugmode-py-sandbox.py)

- [debugmode-py-shell.py](https://github.com/sjdv1982/seamless/tree/stable/tests/highlevel/debugmode-py-shell.py)

### Debugging bash transformers

***IMPORTANT: This documentation section is a stub.***

**Relevant test examples:**

- [debugmode-bash-shell.py](https://github.com/sjdv1982/seamless/tree/stable/tests/highlevel/debugmode-bash-shell.py)

- [debugmode-docker-shell.py](https://github.com/sjdv1982/seamless/tree/stable/tests/highlevel/debugmode-docker-shell.py)

### Debugging compiled transformers

***IMPORTANT: This documentation section is a stub.***

**Relevant test examples:**

- [debugmode-compiled-light.py](https://github.com/sjdv1982/seamless/tree/stable/tests/highlevel/debugmode-compiled-light.py)

- [debugmode-compiled-sandbox.py](https://github.com/sjdv1982/seamless/tree/stable/tests/highlevel/debugmode-compiled-sandbox.py)

<!--
THE FOLLOWING IS OUTDATED
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
-->

### Debugging modules

See the [modules documentation](http://sjdv1982.github.io/seamless/sphinx/html/modules.html) for more information about modules.

***IMPORTANT: This documentation section is a stub.***

#### Debugging Python modules

**Relevant test examples:**

- [debugmode-pymodule-light.py](https://github.com/sjdv1982/seamless/tree/stable/tests/highlevel/debugmode-pymodule-light.py)

- [debugmode-pymodule-sandbox.py](https://github.com/sjdv1982/seamless/tree/stable/tests/highlevel/debugmode-pymodule-sandbox.py)

- [debugmode-pypackage-light.py](https://github.com/sjdv1982/seamless/tree/stable/tests/highlevel/debugmode-pypackage-light.py)

#### Debugging compiled modules

**Relevant test examples:**

- [debugmode-compiledmodule-light.py](https://github.com/sjdv1982/seamless/tree/stable/tests/highlevel/debugmode-compiledmodule-light.py)

- [debugmode-compiledmodule-sandbox.py](https://github.com/sjdv1982/seamless/tree/stable/tests/highlevel/debugmode-compiledmodule-sandbox.py)
