# Language backends (Contract)

The code of a transformation is run by a **language backend**. A language backend is either a **CLI backend** or an **in-memory backend**, and what it does with the transformer's `environment` follows from which of the two it is.

- **A language backend is not an execution backend.** `process`, `spawn` and `remote` decide where a transformation runs ([Execution backends](execution-backends.md)). A language backend decides how the code is run once the transformation is there. The two axes are independent.
- **A CLI backend** starts a process for each run, in a job directory of its own, on the machinery of bash transformations. Its command is a script (bash) or an interpreter with a runner file (R, Julia, Python).
- **An in-memory backend** runs the code inside the process that runs the transformation: the calling process in `process` mode, a worker process otherwise.

This page owns the two kinds, their names, the setting that selects one, the environment rule of each kind, the rule that these rules apply when the transformation runs, the lookup of required binaries, the two public functions that carry the rules, and the Python CLI backend. Other pages own the rest:

- the wrapper that a CLI backend uses (conda, containers, the failure classes, the job directory): [Environments](environments.md);
- R, Julia and the handler API: [Handler languages](handler-languages.md);
- deep pins and deep results: [Deep celltypes](deep-celltypes.md);
- compiled transformers: [Compiled transformers](compiled-transformers.md);
- the builder, `process_lock` and `driver`: [Transformers](transformers.md);
- the process lock and nested work: [Execution backends](execution-backends.md).

The [implementation plan](../../../plans/language-backends-plan.md) describes the mechanics and the phases.

## The languages and their backends

| Language | CLI backend | In-memory backend | `tf.metavars.BACKEND` |
|---|---|---|---|
| `bash` | the only one | none | none |
| `python` | a Python process per run | today's execution, in the process | `"mem"` (default), `"cli"` |
| compiled (`c`, `cpp`, `fortran`, `rust`, …) | none | the only one | none |
| `r` | an `Rscript` process per run | R embedded in the Python process | `"cli"` (default), `"mem"` |
| `julia` | a `julia` process per run | Julia embedded in the Python process | `"cli"` (default), `"mem"` |
| a language added with `register_language_handler` | what its handler does | what its handler does | what its handler declares (*Selecting a backend*) |

- **"In-memory backend" is the term for the kind whose `BACKEND` value is `"mem"`**, and "CLI backend" for the kind whose value is `"cli"`.
- **A language with one kind has no setting.** A bash transformation always runs as a CLI job, and a compiled transformation always runs in memory.
- **`seamless-run` makes bash transformations.** It has no `BACKEND`, and it never runs a command in memory.
- **Compiled transformers have no CLI backend.** A compiled call cannot be wrapped.

## Selecting a backend

`BACKEND` is a metavariable of the transformer, on the Python face and on a bound node.

```python
tf = Transformer("python", direct=True)
tf.metavars.BACKEND            # "mem"
tf.metavars.BACKEND = "cli"
```

- **The values are `"mem"` and `"cli"`, in every language.** The names of the tools that a backend runs, such as `"Rscript"` or `"juliacall"`, are not values.
- **Any other value is refused when it is assigned**, on the Python face and on a bound node. The refusal happens before anything is stored, and the builder keeps the value it had. The exception class is not specified.
- **A value that arrives in a transformation dict is not assigned by anyone.** Such a transformation fails when it runs.
- **Every Python builder has `tf.metavars.BACKEND`**: `Transformer("python")`, a function decorated with `direct` or `delayed`, and a bound `ctx.tf`. The default is `"mem"`.
- **`tf.metavars` of a Python builder has the one name `BACKEND`.** Reading or writing any other name raises.
- **Bound Transformers.** `ctx.tf.metavars.BACKEND` behaves the same. The value belongs to the workflow Context node: every view of `ctx.tf` reads and writes it, the node keeps it in its `meta`, and `ctx.get_graph()` saves it. A node whose result is recorded does not run its code again after a change of `BACKEND`.
- **Where the value is stored.** A Python build writes `BACKEND` into the Transformation's `meta["metavars"]` only when it was set. A Python transformation without it runs in memory. A handler language writes every metavar, defaults included ([Handler languages](handler-languages.md), *Backends*).
- **A handler that has both kinds declares `BACKEND` among its metavars and uses the same two values.** The builder checks the value of a metavar with that name for every handler language.
- **A compiled builder has no `BACKEND`.** Its `tf.metavars` holds its output maxima ([Compiled transformers](compiled-transformers.md)), and assigning `BACKEND` raises.

## Backend and identity

**`BACKEND` is not part of the transformation's identity.** It is carried in `__meta__`, under `metavars`, which is outside the checksum ([Identity and caching](identity-and-caching.md), *Load-bearing vs orthogonal keys*).

- **A result computed under one backend is served, from the cache, to a transformation that names the other.** That is valid only because of parity (*Parity*).
- **Two submissions of one transformation with different backends latch on to each other**, unless `strict_dunder` is used.
- **A transformation that arrives without its `__meta__` runs under the default backend of its language.** That is the in-memory backend for Python and the CLI backend for R and Julia.
- **A fingertip recomputes under the default backend**, in the process that wants the buffer.

## Every backend rule applies when the transformation runs

**A rule about a backend is checked when the transformation runs, and at no other moment.** Building a Transformation checks none of them, and neither does setting an environment. A result that is already recorded is returned without any of them, so a recorded result is served on a machine that has neither the environment nor the interpreter.

This holds for the rules about conda, Docker, required binaries, properly mixed pins and seamless-core in this page and in [Environments](environments.md).

- **The reason is that a result does not know which backend produced it.** The environment and the backend are outside identity, so a cache hit runs nothing and needs nothing.
- **The check of `BACKEND` itself is not such a rule.** It does not depend on where the transformation runs, and it happens at assignment (*Selecting a backend*).
- **A specification that could never work is refused at dispatch**, not when it is set and not when the Transformation is built (*Environments*, below).

## Environments

A transformer's environment ([Environments](environments.md)) is honoured, or the transformation fails. It is never ignored. What a backend can honour depends on its kind:

| The environment has | CLI backend | In-memory backend |
|---|---|---|
| nothing | runs | runs |
| a conda environment | enters it, as a bash transformation does (`conda run`) | runs only when its process is already in exactly that environment. Otherwise it fails |
| a Docker image | runs in a container, as a bash transformation does | fails |
| both | refused at dispatch | refused at dispatch |

### The in-memory rule

The rule is one rule for every in-memory backend: compiled transformers, Python in memory, and the in-memory backends of R, Julia and any other handler language.

- **An in-memory backend cannot enter an environment.** The code runs in the process that runs the transformation. That process is the calling process in `process` mode, and a worker process of the pool, the jobserver or the Dask worker otherwise.
- **A Docker image always fails.** The message names the language and, where the language has a CLI backend, says to use `BACKEND="cli"`.
- **A conda environment is a requirement on the process.** The process must already be running in exactly that environment:
  - a specification that contains `/` is a path. The real path of the process's `CONDA_PREFIX` must equal the real path of the specification, so a symlink to the environment matches;
  - any other specification is a name. The process's `CONDA_DEFAULT_ENV` must equal it.
- **When they do not match, the transformation fails**, and the message names both: what the transformer asks for and what the process has.
- **The requirement is on every process that can run the transformation.** In a worker pool that means the pool's own processes, which have the environment that the pool was started in. Which process that is follows from the execution backend ([Execution backends](execution-backends.md)).
- **The check happens before the body**, so no code has run when it fails.

### The CLI rule

- **A CLI backend wraps both specifications properly**, for every language: conda as `conda run`, and a Docker image as a container run by docker, podman or apptainer, chosen by the executing host. The bash, R, Julia and Python CLI backends do the same thing, on the same machinery ([Environments](environments.md)).
- **What an environment needs from the executing host and from the image** is in [Environments](environments.md), *A conda environment*, *A Docker image* and *The runtime is chosen where the job runs*.
- **A CLI backend inherits the bash transformer's behaviour for everything else**:
  - the interpreter runs after the environment is entered, from the launcher `transform.sh`;
  - the executing host chooses the container runtime, and no image is pulled by default;
  - in a container the job runs as the host user, in the job directory mounted at `/seamless-job`, which is also `HOME`;
  - read-buffer directories are bound read-only at their own paths;
  - the failure classes, and the teardown of a cancelled job and its container;
  - the nesting signal under conda, and none in a container.

What the image or the conda environment must hold, besides `bash` in an image:

| CLI backend of | Needs |
|---|---|
| R | `Rscript`; the R packages `RcppCNPy` and `jsonlite` |
| Julia | `julia`; the Julia packages `NPZ` and `JSON` |
| Python | `python3`; NumPy when an array crosses; seamless-core when a properly mixed value or a checksum crosses (*The Python CLI backend*) |

- **Seamless does not install any of these.** Something that is missing is a failure of the transformation.
- **In a container the host's environment variables are not inherited.** The image supplies library and package depot paths. The Julia CLI backend uses the tracked Seamless Julia project staged in the job directory, regardless of `JULIA_PROJECT` ([Handler languages](handler-languages.md), *Environments*).

### Docker together with conda

**A conda environment together with a Docker image is refused, for every language and both kinds of backend.** A script that needs a conda environment inside an image activates it itself.

### The check happens at dispatch

**Two things are checked at dispatch:** a conda environment together with a Docker image, and the keys of the image spec ([Environments](environments.md), *The image spec*). Dispatch is the moment at which a transformation that has no recorded result is handed to an execution backend.

- **Setting an environment, and building a Transformation, check nothing.** A Transformer that has both a conda environment and an image builds, and so does one whose image spec has an unknown key.
- **A recorded result is returned without the check.** A submission that latches on to a running one dispatches nothing, and is not checked either.
- **The executing host validates again before launch.** A transformation that is run from its checksum alone, or that arrives by another road, has no other check.
- **`seamless-run` is covered**: `--docker` together with `--conda` fails when the command is dispatched, not while its arguments are parsed.
- **Dispatch happens on the submitting side** for `process`, `spawn`, `remote: jobserver` and `remote: daskserver` alike.

### Required binaries

`tf.environment.set_which([...])` lists binaries that must exist. They are looked up where the code runs.

| Backend | Looked up |
|---|---|
| CLI backend, every language | in the script, after the conda environment is entered or inside the image. A binary that exists only in the environment satisfies the check, and one that exists only on the host does not |
| in-memory backend | on the `PATH` of the process that runs the code |

- **A record probe checks nothing.**
- **The look-up is not done on the submitting machine** for any language.

### A record probe is exempt

A record probe is a Python in-memory transformation that carries the `__env__` of the job whose surroundings it captures ([Execution records](execution-records.md)). It runs on the host and is not checked against the environment that it carries: it does not fail for the conda environment or the image, and it does not check `which`.

## The two public functions

The two rules are carried by two functions of `seamless_transformer.languages`. They are public: a handler of any language honours its `environment` through one of them, or fails.

```python
from seamless_transformer.languages import (
    check_in_memory_environment,
    execute_cli,
)

check_in_memory_environment(environment, language)    # raises, or returns None
execute_cli(command, pins_, PINS, FILESYSTEM, OUTPUTPIN, environment)
```

**`check_in_memory_environment(environment, language)`** applies *The in-memory rule* and looks the names of `which` up on the `PATH` of the process.

- `environment` is the transformer's environment as a dict, as the handler receives it (*Handler languages*, *The arguments*). It may be empty.
- `language` is the language name. It is used in the message.
- It returns `None`, or raises. The exception class is not specified.
- It is a function of its arguments and of the process's environment. It needs no running transformation, so it can be called outside one.

**`execute_cli(command, pins_, PINS, FILESYSTEM, OUTPUTPIN, environment)`** runs a command as a CLI job and applies *The CLI rule*.

| Parameter | Meaning |
|---|---|
| `command` | the command that starts the interpreter, run by bash in the job directory |
| `pins_` | the names of the files and directories to write into the job directory |
| `PINS` | a dict from each of those names to its content: a `Buffer`, bytes, or the path of a file that exists on the executing host |
| `FILESYSTEM` | a dict from each name to its entry, as for a pin on file (*Handler languages*, *The arguments*) |
| `OUTPUTPIN` | the celltype in which the content of `RESULT` is read |
| `environment` | the transformer's environment, as a dict |

- **It returns the content of `RESULT`.** For `bytes`, `folder` and `deepfolder` as `OUTPUTPIN` the bytes. For any other celltype the file is parsed as an `.npy` array, then as JSON, then as text, and a content that is none of these is returned as a `uint8` array. A `RESULT` that is a directory gives a dict from each file's path in it to its content, in the same form.
- **It takes the transformation's checksum and its abort test from the running transformation.** Inside one, a cancel finds the job and tears it down, and a docker or podman container carries the label `seamless.tf=<tf_checksum>`. Outside one, the launch works without them.
- **It wraps conda and Docker from `environment`.** A handler cannot wrap one and forget the other.
- **It looks `which` up in the script.**
- **A handler passes `environment` as it received it.** A handler that calls neither function gets no environment handling and no `which` check from Seamless. Nothing enforces it.

## The Python CLI backend

`BACKEND = "cli"` makes a Python transformation run as a CLI job: the code runs in a `python3` process of its own, in a job directory, on the machinery of bash transformations.

**Faces.** The Python face (`Transformer("python")`, `direct`, `delayed`) and the workflow Context (`ctx.tf = function`, a bound `ctx.tf`). `seamless-run` has no such setting.

### What stays the same

The code is the same code. The in-memory backend and the CLI backend give it the same names with the same values:

- **The code modes are the same**: a block, a function, a lambda and an expression, recognized in the same way.
- **The pins are the same values.** The process that runs the transformation parses each pin as the in-memory backend does, and the job gets it back unchanged. Plain data, text, arrays and `bytes` cross without Seamless in the job. A deep pin has the form of *How deep values reach a transformer* ([Deep celltypes](deep-celltypes.md)) under both backends.
- **One pin type differs.** A `bytes` pin is a `seamless.Buffer` under the in-memory backend and `bytes` under the CLI backend. Code that depends on that type is not covered by parity.
- **The result is what the code returns**, or the variable of the output name for block code, serialized under the result celltype as the in-memory backend does it.
- **`print` and the standard streams** are relayed while the code runs, as two streams ([Transformation logs](transformation-logs.md), [Streaming](streaming.md)).
- **The code is self-contained, as it always is** ([Modules and closures](modules-and-closures.md)).

### What differs

- **The code runs in another process**, with its own interpreter. Imports, global state and open files are not shared with the process that runs the transformation. Every run starts an interpreter, plus `conda run` or a container start.
- **The interpreter is `python3`** on the `PATH` where the job runs: in the conda environment or the image when there is one, otherwise the `PATH` of the executing process. It is not the interpreter of the submitting process.
- **The job needs what the code imports.** The submitting process's packages do not exist there.
- **A transformation with modules or globals fails when it runs.** The message says to use `BACKEND="mem"`.

### Packages the job needs

| When | The job needs |
|---|---|
| always | `python3` |
| an array is a pin or a result | NumPy |
| a properly mixed value is a pin or a result | seamless-core, installed where the code runs |
| a deepcell pin or a `checksum` pin | seamless-core |
| the code itself uses Seamless, for example for nested work | Seamless |

- **A properly mixed value** is a `mixed` value whose buffer is in the Seamless-mixed format, which is a value that does not reduce to plain data or to an array ([Celltypes and conversion](celltypes-and-conversion.md)). A pin or a result of that kind is carried to and from the job through seamless-core.
- **A checksum crossing into the job** also needs seamless-core, whether the code only passes its members on or resolves them.
- **A job with none of these runs in an environment that has no Seamless.**
- **Nothing checks for seamless-core beforehand** (*Every backend rule applies when the transformation runs*). When it is missing, the import fails inside the job, and the failure is the Python error in the standard error trailer.

### Results

- **A returned value is carried as plain data, an array, `bytes`, a properly mixed value, or, as a member of a deep result, a checksum object.** The process that runs the transformation then serializes it under the result celltype, with the calls that the in-memory backend uses. No serialization rule exists twice.
- **There is no fallback encoding.** A value that cannot be carried fails the transformation, and it never travels in a different representation.
- **A folder or deepcell result is the dict that the code returns.** Each member is a value or a checksum object ([Deep celltypes](deep-celltypes.md), *The output side*).
- **Nothing that a job wrote is loaded as a pickle.** The process that runs the transformation reads a job's result as data only.

### Parity

**Both Python backends give the same result, bit for bit, when both succeed.** A backend may fail where the other succeeds. It may not succeed with a different result.

- **This is what lets the backend stay outside identity.**
- **A result type is accepted by the CLI backend only when both backends give it the same result checksum.** Every other type fails under the CLI backend.
- **One-sided failures**:

| Case | CLI backend | In-memory backend |
|---|---|---|
| modules or globals | fails | accepted |
| a properly mixed or checksum value, with no seamless-core in the job | fails | accepted |
| a conda environment other than the process's, or a Docker image | runs, in that environment | fails |
| a result type that the runner cannot carry | fails | accepted |
| `Checksum.resolve()` in the code, for a member of a deepcell pin | works under `remote: daskserver` only | works |

- **The guarantee is about the backend, not about the code.** Code that depends on the interpreter's state, the working directory, an environment variable or a file outside its pins is not covered, as for any transformation.
- **The text of a failure is not covered**: the two backends report the same failure in different words.

### The process lock, cancellation and failures

- **The run takes the process lock like a bash body**, and may run without it (`process_lock` false, or a driver) ([Execution backends](execution-backends.md), *The process lock*).
- **A cancel tears the job down as it does for bash**, and a container is removed ([Cancellation](cancellation.md), *A bash run that is cancelled*).
- **A failure is the *Bash transformer exception* report** ([Transformation logs](transformation-logs.md), *The failure text*). Its command is the interpreter's, and the Python traceback is in the standard error trailer.
- **An in-memory Python body may run without the process lock**, as it always has. The rule that an in-memory body must hold the lock is that of embedded interpreters ([Handler languages](handler-languages.md), *The process lock*), and it does not extend to Python or compiled bodies.

### Drivers and nested work

A Python CLI job is in the position of a bash job.

- **A driver never takes the lock**, under either backend. That is decided before the body starts.
- **Code that is not a driver signals its parent at its first nested submission**, as a bash body's `seamless-run` does, and the parent then gives the lock up ([Execution backends](execution-backends.md), *Bash bodies*). The signal exists without an environment and under conda. It does not cross a container boundary.
- **The job's process is configured from `SEAMLESS_REMOTE_CLIENTS`**, before the code runs, when that variable is set in the job's environment and Seamless can be imported there. Nested work then goes to the same cluster and shares its caches, as a nested `seamless-run` does.
- **Only the Dask worker exports the variable.** Under `remote: daskserver` nested work therefore goes to the cluster. On the other execution backends nothing is exported, and a nested transformation runs inside the job's own process, with no cache and no dispatch. A nested `seamless-run` in a bash job fails there, for lack of a configuration, unless `SEAMLESS_CACHE` or `SEAMLESS_REMOTE_CLIENTS` is in the environment that the job inherits.
- **Submissions from the job's process skip the permission routine of Dask**, driver or not. The mark of a driver is not what decides it ([Execution backends](execution-backends.md), *Drivers*).
- **The code needs Seamless where it runs**, and inside a container nested work is not supported.

## Deep pins and results

Deep celltypes follow the matrix of [Deep celltypes](deep-celltypes.md), *How deep values reach a transformer*. Bash has a column of its own, and every other backend, CLI and in-memory alike, follows the other.

- **A folder pin is a dict of contents under every backend but bash**, and a deepfolder pin is a dict of paths. Under a CLI backend a folder travels to the job as a directory that the runtime reads back into a dict. The code does not see that directory.
- **A deepcell pin is a dict of checksum objects under every backend but bash**: `seamless.Checksum` in Python, and the checksum class of the language in R and Julia ([Handler languages](handler-languages.md), *Checksum classes*).
- **A deep result is a dict under every backend but bash**, and the `RESULT` directory in bash.
- **Both backends of a language give a deep pin the same form.**
- **A compiled transformer refuses a deep pin**, as before.

## Failures

Each of the following is a failure of the transformation, and failures are not cached:

- an in-memory backend with a Docker image, or with a conda environment that is not its process's;
- a conda environment together with a Docker image, and an invalid image spec, at dispatch;
- a required binary that is missing where the code runs;
- a Python CLI job with modules or globals, with a value that it cannot carry, or without a package that it needs;
- every failure class of a CLI job ([Environments](environments.md), *Failures*).

## Current limitations

- **A third-party handler can ignore `environment`.** The two functions make honouring it easy. Nothing enforces it.
- **A Python CLI job with a deepcell pin or a `checksum` pin needs seamless-core**, also where its code only passes members on.
- **Code in a CLI job can resolve the members of a deepcell pin under `remote: daskserver` only.** No Seamless configuration is exported to a job outside Dask. R and Julia code cannot resolve a checksum at all.
- **A properly mixed value is written by the seamless-core of the process that runs the transformation, and read by the one in the job**, and back. Nothing checks that two versions agree on the format.
- **Every Python CLI run starts an interpreter**, plus `conda run` (in the order of a second with `conda`) or a container start.
- **A failure under a CLI backend is titled *Bash transformer exception***, whatever the language.
- **A job holds its process for as long as it runs**, unless `process_lock` is false.
- **In a container, nested Seamless work is not supported.**
- **Writing a job directory instead of running it** is for bash transformations only.

## Non-goals

- A CLI backend for compiled transformers.
- A setting that lets a Python or compiled pin arrive as a file.
- Modules and globals under the Python CLI backend.
- Seamless installing an interpreter, a package or an environment on the executing host or in an image.
- A public format for what travels between a job and the process that runs the transformation. A handler returns a Python value to Seamless.

## Code locations

| Concern | Module / symbol |
|---|---|
| The two public functions | `seamless_transformer.languages` (`check_in_memory_environment`, `execute_cli`) |
| The CLI job launcher | `seamless_transformer.execute_bash` (`execute_bash`) |
| Dispatch to a backend | `seamless_transformer.run.run_transformation_dict` |
| `metavars` of Python builders | `seamless_transformer.transformer_class` |
| The check of the specification at dispatch | `seamless_transformer.transformation_cache` |
