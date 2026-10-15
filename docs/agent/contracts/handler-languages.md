# Handler languages (Contract)

A **handler language** is a transformation language whose code is run by a
**handler**: a Python function that receives the code and the pins, runs the
code in the other language, and returns the result. R (`language="r"`) and
Julia (`language="julia"`) are the two built-in handler languages. The set is
open: `register_language_handler` adds a language, and Seamless itself does
not change for it.

**This page is about the Python face and the workflow Context.** A handler
language is used through the `Transformer` factory. `direct` and `delayed`
decorate Python functions only, and `seamless-run` wraps commands, as before
(*Faces*).

This page owns the handler API, what a handler receives, what R and Julia code
sees and returns, what each backend of each language runs and needs and their
parity, the checksum classes of R and Julia, and where the handler and the
backend sit in transformation identity. Other pages own the rest:

- the two kinds of language backend, `BACKEND`, the environment rule and the
  two public functions that carry it: [Language
  backends](language-backends.md);
- deep pins and deep results: [Deep celltypes](deep-celltypes.md);

- builder modes, building, binding and the named work methods:
  [Transformers](transformers.md);
- pin declarations, pin celltypes and the null rules: [Pins](pins.md);
- the identity model: [Identity and caching](identity-and-caching.md);
- the process lock: [Execution backends](execution-backends.md), *The process
  lock*.

The [implementation plan](../../../plans/julia-r-support.md) describes the
mechanics and the phases.

## The three kinds of language

| Kind | Languages | Constructed with | The code is run by |
|---|---|---|---|
| native | `python`, `bash` | `Transformer(language)`. For Python also `direct`, `delayed` and `ctx.tf = function` | Seamless itself |
| compiled | the languages registered with `define_compiled_language`, such as `c`, `cpp`, `fortran` and `rust` | `Transformer(language, compiled=True)` | a native call of the compiled `transform()` ([Compiled transformers](compiled-transformers.md)) |
| handler | `r`, `julia`, and what `register_language_handler` adds | `Transformer(language)` | the handler of the language |

```python
from seamless_transformer.languages import available_languages

available_languages()
# {"python": "native", "bash": "native", "c": "compiled", ...,
#  "r": "handler", "julia": "handler"}
```

- **`available_languages()` maps every accepted `language` value to its
  kind**: `"native"`, `"compiled"` or `"handler"`. It lists the languages that
  the factory can construct, and nothing else. A name that the factory does
  not accept, such as `ipython`, is not in it.
- **A language name belongs to one kind.** Registering a handler under a
  native or compiled name raises.
- `is_handler_language(name)` says whether a name has a handler.
  `get_language_handler(name)` returns the registration of a handler language,
  and raises for any other name.
- **The two built-in handlers are always registered.**
  `seamless_transformer.languages` registers them when it is imported. That
  import loads neither R nor Julia, and neither `ryp` nor `juliacall`.

## Faces

| Face | Handler languages |
|---|---|
| Python: the `Transformer` factory | `Transformer("r")`, `Transformer("julia")`, with `direct=True` for an immediate call |
| Python: `direct`, `delayed` | none. Both decorate Python functions only |
| Workflow Context | a handler-language builder is bound like any other: `ctx.tf = Transformer("julia")` |
| Unix: `seamless-run` | none |

`seamless-run Rscript analysis.R data.csv` remains what it was: a bash
transformation of a command that happens to start R. The script is an input
file, the identity is that of the command and its files, and the result is a
file or the command's output. Nothing on this page applies to it: there are no
pins as variables, no `BACKEND` and no parity guarantee.

## R and Julia transformers

The code is ordinary R or Julia. It loads no input files, writes no result
file and does not mention Seamless.

```python
from seamless.transformer import Transformer

tf = Transformer("r", direct=True)
tf.code = "result <- a + b"
tf.pins.a = 2
tf.pins.b = 3
tf()          # -> 5
```

```python
tf = Transformer("julia", direct=True)
tf.code = """
function transform(a, b)
    return a + b
end
"""
tf.pins.a = 2
tf.pins.b = 3
tf()          # -> 5
```

- **The code is source text.** `tf.code` takes a string. A new builder has no
  code.
- **The pins are declared by the user**, by writing through `tf.pins` or
  `tf.celltypes`, as for Bash ([Pins](pins.md), *Which pins exist*). Seamless
  does not read a signature from R or Julia code, not even from a `transform`
  function. A declared pin has celltype `mixed` until it is given another.
- **There are no optional pins.** They exist for Python only.
- **The output name is `result`**, and its celltype is `tf.celltypes.result`,
  which is `mixed` by default.
- **Everything else is the common builder contract**
  ([Transformers](transformers.md)): standalone and bound modes, `build()`,
  the named work methods, `scratch`, `process_lock` and `driver`. A builder's
  `language` is fixed at construction and read-only.
- **A handler-language builder also has `tf.metavars`**, which holds the
  settings of its handler (*Backends*).

## The two code styles

The R and the Julia handler accept code in two styles.

| | Block | `transform()` |
|---|---|---|
| The code is | statements that run from top to bottom | a definition of a function named `transform`, with whatever else it needs |
| Recognized by | no top-level definition of `transform` | a top-level definition of a function named `transform` |
| Pins | each pin is a variable of its name | each pin is passed as the argument of its name |
| Result | the value of the variable `result` when the code ends | the return value of `transform` |
| Isolation | a new one for every run | built once, and reused (*Isolation and persistent state*) |

- **The style is recognized by parsing the code in its own language**, when
  the transformation runs.
  - R: a top-level assignment, with `<-` or `=`, of a `function` to the name
    `transform`.
  - Julia: a top-level definition of a function named `transform`, in the long
    form or the short form (`transform(a, b) = …`), also with a `where`
    clause, a return type or a docstring.
- **Only the top level counts.** A definition inside a block, or one that the
  code produces by `source`, `include` or `eval`, does not make the code
  `transform()` style.
- **Block code cannot have a top-level function named `transform`.** It would
  be read as the other style.
- **In the block style, the code must assign `result`.** A run whose code ends
  without it fails. A variable of that name outside the code's own isolation
  does not count.
- **In the `transform()` style, the top-level code runs with no pins bound.**
  It defines things. Only `transform` receives the pins.
- **What happens when the pins and the parameters of `transform` do not match
  is not specified.** Declare one pin for each parameter.

## Isolation and persistent state

An **isolation** is the scope in which the code runs: an environment in R, a
module in Julia.

- **Block code gets a new isolation for every run.**
- **`transform()` code gets one isolation per interpreter**, for each
  combination of code, output name and pin names. It is built at first use and
  kept inside the interpreter. Later runs in that interpreter call the
  function that is already defined.
- **Seamless keeps no cache of isolations.** A worker process that is
  restarted starts with none. Under a CLI backend every run starts a new
  interpreter, so nothing is reused there.

**An isolation separates names, not the process.** Under an in-memory backend
(*Backends*), these outlive a transformation and are seen by the next one in
the same process:

- loaded packages and their state;
- options;
- explicit assignments to the global scope;
- in the `transform()` style, the top-level variables of the isolation;
- compiled Julia code.

**The result must not depend on any of that.** The constraint is the one that
holds for compiled transformers
([Compiled transformers](compiled-transformers.md), *Referential transparency
constraint*): code whose return value depends on state from an earlier call
cannot be wrapped. Seamless does not detect a violation. The consequence is a
cached result that is silently wrong, and a result that differs between the
two backends.

**Inputs are never writable through to Seamless.** Code may modify a pin's
value in place. The change stays inside that run, and the pin's checksum is
unchanged.

## Backends

Each of the two languages has two **backends**: a CLI backend and an
in-memory backend ([Language backends](language-backends.md)). The
metavariable `BACKEND` selects one, with the values `"cli"` and `"mem"`.

| Language | `"cli"`, the default | `"mem"` |
|---|---|---|
| `r` | an `Rscript` process per run | R embedded in the Python process, through `ryp` |
| `julia` | a `julia` process per run | Julia embedded in the Python process, through `juliacall` |

```python
tf = Transformer("r")
tf.metavars.BACKEND          # "cli"
tf.metavars.BACKEND = "mem"
```

- **`tf.metavars` has the names that the handler declared.** Reading one gives
  the value that was set, or else the handler's default. Any other name
  raises, on read and on write. The exception class is not specified.
- **`BACKEND` accepts `"cli"` and `"mem"`, and nothing else.** Any other value
  is refused when it is assigned, and nothing is stored. The names of the
  tools, such as `"Rscript"` or `"juliacall"`, are not values. A value that
  arrives in a transformation dict fails when the transformation runs.
- **A build writes every metavar into the Transformation**, defaults included,
  under `meta["metavars"]`.
- **The backend is not part of the transformation's identity** (*Identity and
  caching*).
- **Bound Transformers.** `ctx.tf.metavars` behaves the same. The values
  belong to the workflow Context node: every view of `ctx.tf` reads and writes
  the one mapping, the node keeps it in its `meta`, and `ctx.get_graph()`
  saves it. A node whose result is recorded does not run its code again after
  a change of `BACKEND`, because its `tf_checksum` is the same.

What a backend needs on the machine that runs the transformation:

| Language | `"cli"` needs | `"mem"` needs |
|---|---|---|
| `r` | `Rscript` on the `PATH`; the R packages `RcppCNPy` and `jsonlite` | the Python package `ryp`, with R and the R package `arrow`; the R package `jsonlite` |
| `julia` | `julia` on the `PATH`; the Julia packages `NPZ` and `JSON` in the active project | the Python package `juliacall`; the Julia package `JSON` in the project that `juliacall` uses |

- **Seamless installs none of these.** A tool or a package that is missing is
  a failure of the transformation.
- **The machine that runs the transformation needs them, not the one that
  builds it**, unless they are the same. Which machine runs it follows from
  the execution backend ([Execution backends](execution-backends.md)).
- **Under a CLI backend with a Docker image, the image needs them.** A
  conda environment needs them too, where the transformer has one
  (*Environments*).

### CLI backends

- **Every run starts a new interpreter process**, in a job directory of its
  own, on the machinery of bash transformations. What
  [Execution backends](execution-backends.md), *Bash bodies*, says of a bash
  body holds for it: the process that runs the transformation keeps its
  working directory, and a nested `seamless-run` that the code starts is
  signalled.
- **The interpreter does not read the user's startup files.** The commands are
  `Rscript --vanilla` and `julia --startup-file=no`.
- **The transformer's environment is entered first**, when it has one: its
  conda environment is activated, or the interpreter is started in a container
  made from its Docker image (*Environments*).
- **One run at a time per process, by default**, because the run takes the
  process lock. With `tf.process_lock = False`, several run side by side in
  one process. Each has its own interpreter process, so they share no
  interpreter state.

### In-memory backends

- **The interpreter is embedded in the process that runs the transformation.**
  That is the calling process in `process` mode, and a worker process
  otherwise. It starts at its first use and lives until the process ends.
- **There is one embedded interpreter per process**, and one transformation
  uses it at a time (*The process lock*).
- **`transform()` isolations are reused** from one run to the next (*Isolation
  and persistent state*). That is what an in-memory backend is for: the
  interpreter starts once, and definitions are evaluated once.
- **It cannot enter an environment.** A conda environment must already be the
  one of the process, and a Docker image is refused (*Environments*).

## The process lock

A handler-language transformation takes the process lock like any other
([Execution backends](execution-backends.md), *The process lock*). The handler
receives whether it did (*Writing a handler*, *The arguments*).

**An in-memory backend refuses to run without the process lock.** A
transformation that has `process_lock` false and an in-memory backend fails
when it runs. The message names the CLI backend as the alternative.

- **A driver is refused too**, because `driver` true means `process_lock`
  false ([Transformers](transformers.md), *`process_lock` and `driver`*).
- **The process lock is the only lock around an embedded interpreter.** Among
  transformations that hold it, one runs at a time in a process, and that is
  what keeps two transformations out of one interpreter.
- **The refusal happens when the transformation runs.** Building succeeds. A
  result that is already recorded is returned without the check.
- **An in-memory body holds the lock from its start to its end.** The code has
  no way to give it up: the nesting signal of a bash body does not exist here.
  Code that submits nested work, for example by running `seamless-run`,
  belongs under the CLI backend.
- **A transformation that arrives without its `__meta__` takes the lock and
  runs under the default backend**, which is the CLI
  ([Transformers](transformers.md), *Absent keys in a transformation dict*).

## Backend parity

**Both backends of a language give the same result, bit for bit, when both
succeed.**

- **A backend may fail where the other succeeds. It may not succeed with a
  different result.**
- **This is what lets the backend stay outside identity.** A result that was
  computed under one backend is served, from the cache, to a transformation
  that names the other.
- **How it holds.** Each language has one runtime, written in that language,
  and both backends use it. The runtime recognizes the code style, builds the
  isolation, turns each pin into a native value, runs the code, and classifies
  and encodes the result. The backends differ only in how bytes travel.
- **JSON values cross as JSON text under both backends**, and are parsed and
  written by the same call. That is why `jsonlite` and `JSON` are needed by
  the in-memory backends too.
- **There is no fallback encoding.** A backend that cannot carry a value fails.
  It never substitutes another representation.
- **A deep pin has the same form under both backends**, and a deep result has
  the same member rule (*Deep celltypes and checksum objects*). Code that
  filters the keys of a `deepcell` pin and returns the rest gives the same
  result under both.
- **A `deepfolder` pin is a dict of checksum objects under both backends.**
  Its form does not depend on where the member buffers are stored.

Cases where one backend fails and the other succeeds:

| Case | CLI backend | In-memory backend |
|---|---|---|
| A `mixed` pin whose value combines arrays and plain data: a buffer in the Seamless-mixed format ([Celltypes and conversion](celltypes-and-conversion.md)) | fails | accepted |
| R: a `float32` array, or an array with more than two dimensions (*Array rules*) | fails | accepts supported element types |
| A conda environment that is not the one of the process that runs the transformation (*Environments*) | runs, in that environment | fails |
| A Docker image (*Environments*) | runs, in a container | fails |

**The guarantee is about the handler, not about the code.** Code that is not
a pure function of its pins is not made reproducible by it (*Isolation and
persistent state*). The text of a failure is not covered either: the two
backends report the same failure in different words.

## What the code receives

| Pin celltype | Native value in R | Native value in Julia |
|---|---|---|
| `text` | a character string, without the final newline | a `String`, without the final newline |
| `plain`, and `mixed` whose buffer is JSON | what `jsonlite::fromJSON` returns | what `JSON.parse` returns |
| `bytes` | a raw vector | a `Vector{UInt8}` |
| `binary`, and `mixed` whose buffer is an array | a double or logical vector or array (*Array rules*) | an `Array` (*Array rules*) |
| `int`, `float`, `bool`, `str`, and every other celltype that is neither deep nor `checksum` | as `plain` | as `plain` |
| `folder` | a named list of raw vectors, one for each member's bytes | a `Dict{String, Vector{UInt8}}` |
| `deepfolder` | a named list of checksum objects | a `Dict{String, Checksum}` |
| `deepcell` | a named list of checksum objects | a `Dict{String, Checksum}` |
| `checksum` | a checksum object | a `Checksum` |

- **A `mixed` pin is read by what its buffer is**: an array, JSON, or a
  Seamless-mixed buffer that holds both. The handler looks at the first
  bytes of the buffer.
- **A Seamless-mixed buffer is accepted by the in-memory backends only.**
  Its plain parts follow the JSON rule, and its arrays the array rule.
- **`text` and `str` differ.** A `text` pin is the text itself. A `str` pin is
  a JSON string, and reaches the code through the JSON parser.
- **A deep pin has the same form under both backends** (*Deep celltypes and
  checksum objects*). The code never sees a directory or a file for a `folder`
  pin.
- **The value is the same whether the pin arrived as a value or as a file**
  (*Pins on file*).

## What the code returns

| Result | Returned to Seamless as |
|---|---|
| anything, when the result celltype is `bytes` | raw bytes |
| a numeric array, when the result celltype is `binary` or `mixed` | a C-contiguous NumPy array |
| a named list or a `Dict` with string keys, when the result celltype is `deepcell` or `folder` | that dict, each member a value or a checksum object (*Deep celltypes and checksum objects*) |
| a checksum object or a string of 64 hexadecimal characters, when the result celltype is `checksum` | that checksum |
| anything else | the value that Python parses from the runtime's JSON encoding of it |

- **Seamless serializes the returned value under the result celltype**, as it
  does for the return value of a Python transformer. The null rules for
  results apply ([Pins](pins.md), *Null, required pins, optional pins*).
- **In R, a vector of length one without dimensions is a scalar.** It is not
  an array of one element.
- **Arrays inside a list or a dictionary become nested JSON lists.** Only a
  result that is itself an array is returned as an array. The R and the Julia
  handler never return a value that combines arrays and plain data.
- **A value that the runtime cannot encode fails the transformation.**
- **A checksum object is returned only as a member of a `deepcell` or `folder`
  result, or as a `checksum` result.** Returned under any other result
  celltype it fails the transformation.
- **A `deepfolder` result is refused**, as for every transformer
  ([Deep celltypes](deep-celltypes.md), *The output side*).

## Deep celltypes and checksum objects

Deep pins and deep results are accepted under both backends. Their forms are
those that every non-bash backend gives
([Deep celltypes](deep-celltypes.md), *How deep values reach a transformer*), in
the forms of R and Julia:

| Pin | R | Julia |
|---|---|---|
| `folder` | a named list of raw vectors | a `Dict{String, Vector{UInt8}}` |
| `deepfolder` | a named list of checksum objects | a `Dict{String, Checksum}` |
| `deepcell` | a named list of checksum objects | a `Dict{String, Checksum}` |
| a `deepfolder` or `deepcell` source, declared `plain` | a named list of 64-hex strings | a `Dict{String, String}` of 64-hex strings |

- **The keys are the keys of the index**, which may contain `/`. An empty index
  is an empty named list or `Dict`.
- **A `folder` pin holds every member's bytes in memory.** The process that
  runs the transformation resolves the members, from any buffer source, before
  the code runs.
- **A `deepfolder` or `deepcell` pin resolves no member.** Each is a dict of
  checksum objects. The class of R and of Julia carries a checksum and has no
  access to a buffer. These pins serve to select members and pass them on, for
  example in a `deepcell` result.
- **Declaring the pin `plain`** hands the code the index as data: strings, not
  objects. A string that is returned from it is a value (*Results*, below).

**Results.** The code returns the dict itself, and Seamless packs it into an
index ([Deep celltypes](deep-celltypes.md), *The output side*).

- **A member is a value unless it is a checksum object.** A string of 64
  hexadecimal characters is a value, like any other string. Code that wants to
  return a checksum wraps the string in the checksum class.
- **A member that is a value is classified as an ordinary result is** in that
  language: by the rule of a `mixed` result for a `deepcell`, and by the rule
  of a `bytes` result for a `folder`.
- **A member that is a checksum object is inserted into the index as it is.**
  Nothing checks that the buffer exists.

### Checksum classes

Each language has a class that holds a checksum. It exists under both
backends, and the runtime puts its functions in the scope of the code.

| | R | Julia |
|---|---|---|
| Make one from a string | `seamless_checksum("…")` | `Checksum("…")` |
| Test for one | `is_seamless_checksum(x)` | `x isa Checksum` |

- **It is made from a string of 64 lowercase hexadecimal characters.** Any
  other value is an error.
- **It can be tested for, converted to its string, compared and printed.** Two
  objects with the same string are equal. It can be told from a plain string.
- **It cannot resolve.** The class carries the checksum and no access to a
  buffer. Python code has `Checksum.resolve()`, and R and Julia code has
  nothing like it.
- **A `checksum` pin is one such object**, and a `checksum` result accepts one,
  or a string of 64 hexadecimal characters.
- **Plain data holds no objects.** A `plain` pin that is a dict of checksums
  holds strings.

## Array rules

**Array element types are normalized before the user code runs**, including
arrays inside an embedded Seamless-mixed pin:

| NumPy input dtype | Native R element type | Native Julia element type |
|---|---|---|
| boolean | logical | `Bool` |
| signed integer | double | `Int64` |
| unsigned integer | double | `UInt64` |
| floating point | double | `Float64` |

Other input array dtypes are refused. Integer values in R are subject to the
precision of double: integers beyond the exact range of a double may be
rounded. Both R backends apply the same conversion.

- **R dimensions:** a one-dimensional input becomes a vector; an input with
  two or more dimensions retains those dimensions. A returned vector of
  length one without dimensions is a scalar.
- **R CLI backend restrictions:** `float32` inputs and arrays with more than
  two dimensions are refused. The R in-memory backend accepts them under the
  normalization above.
- **Returned arrays:** R numeric and integer arrays become NumPy `float64`,
  and logical arrays become NumPy `bool`. Julia boolean, signed integer,
  unsigned integer and floating arrays become NumPy `bool`, `int64`,
  `uint64` and `float64`, respectively. Other array element types are refused
  when an array result is required.
- **Shape and layout:** returned arrays retain their shape and are
  C-contiguous NumPy arrays. Input memory layout does not change their values.
- **Parity remains fixed:** both backends of one language give the same
  result when they succeed; a backend that cannot transport a value refuses
  it.

## Pins on file

**A handler-language pin of celltype `mixed`, `plain`, `text`, `bytes` or
`binary` reaches the handler as a file when one exists, and as a value
otherwise.** This holds for every handler language, the registered ones
included.

- **As a file:** when the pin's buffer is on file in a read-buffer directory
  that is configured for the process that runs the transformation. The handler
  receives the path, and nothing is read into memory for it.
- **As a value:** in every other case. The handler receives the value, parsed
  under the pin's celltype, as a Python transformer would.

The file holds the buffer, byte for byte:

| Celltype | Bytes of the buffer |
|---|---|
| `text` | the text and a final newline |
| `plain` | JSON |
| `bytes` | the bytes |
| `binary` | a NumPy `.npy` array |
| `mixed` | `.npy` for an array, JSON for a plain value, the Seamless-mixed format for a value that combines both |

- **The file can be compressed.** Its path then ends in `.zst` or `.gz`, and
  the handler decompresses ([Compression](compression.md)).
- **Which form arrives is not part of identity.** The transformation says that
  the pin *may* be a file. That statement is the same for every transformation
  of a handler language, and it does not depend on any machine (*Identity and
  caching*).
- **The R and the Julia handler convert either form.** The code sees the same
  native value, and cannot tell the forms apart.
- **Other pins always arrive as values.** `deepcell`, `deepfolder` and `folder`
  pins arrive in the forms of *Deep celltypes and checksum objects*
  ([Deep celltypes](deep-celltypes.md), *How deep values reach a
  transformer*).

## Identity and caching

| Part of the transformation | Where it is carried | In the checksum |
|---|---|---|
| the language name | `__language__` | yes |
| the code text; each pin's checksum and celltype; the result celltype | the pins, `__output__` | yes |
| "this pin may be a file", for each pin of *Pins on file* | `__format__` | yes, and the same for every transformation of a handler language |
| the handler's source | `__handler__` | no |
| the metavars, `BACKEND` included | `__meta__`, under `metavars` | no |
| the conda environment | `__env__` | no |

The split is the one of [Identity and caching](identity-and-caching.md),
*Load-bearing vs orthogonal keys*.

- **The same code text under `r` and under `julia` is two transformations.**
- **A cached result is returned whatever the backend and whatever the
  handler.** Nothing is launched, and neither R nor Julia needs to be
  installed for a cache hit.
- **Two submissions of one transformation with different backends latch on to
  each other**, unless `strict_dunder` is used
  ([Identity and caching](identity-and-caching.md), *Concurrent submissions of
  the same checksum*).
- **A fingertip runs the code where the buffer is wanted.** A fingertip is
  never dispatched ([Scratch, witness, audit](scratch-witness-audit.md),
  *Fingertipping*). The machine that asks needs the language's tools. When it
  recomputes from the checksum alone, it uses its own registered handler and
  the default backend.
- **A handler defines what its language name means.** Because the handler is
  outside the checksum, two handlers that are registered under one name must
  give the same result for the same code and pins. A new version of a handler
  is such a second handler. Seamless does not detect a violation, and the
  cache then serves results of the old meaning.
- **A metavar must not change the result.** It selects how the code is run.
  The rule is the one for the metavars of a compiled transformer
  ([Compiled transformers](compiled-transformers.md), *Output-only
  wildcards*).

## Writing a handler

```python
from seamless.transformer import Transformer
from seamless_transformer.languages import register_language_handler

def template_handler(code, pins, filesystem):
    import json                           # imports go inside the function

    values = {}
    for name, value in pins.items():
        if filesystem.get(name, {}).get("filesystem"):
            with open(value) as f:        # a path: the file holds the buffer
                value = json.load(f)      # (not handled here: .zst and .gz)
        values[name] = value              # otherwise: the pin's value
    return code.strip().format(**values)

register_language_handler("template", template_handler)

tf = Transformer("template", direct=True)
tf.code = "Hello, {who}!"
tf.celltypes.who = "plain"
tf.pins.who = "world"
tf()                                      # -> "Hello, world!"
```

`register_language_handler(name, handler, *, metavars=None)`:

- **`handler` is one self-contained Python function.** It is defined with
  `def`. Its imports are inside its body. It has no closure and uses no global
  of the module that defines it. This is the discipline of Python transformer
  code, and for the same reason: the function travels as source text.
  Decorators are not part of that source.
- **Its parameters choose what it receives.** Each parameter name must be one
  of the names under *The arguments*, and the handler is called with exactly
  those, by keyword. A parameter of another name, a positional-only parameter,
  `*args` and `**kwargs` are refused at registration.
- **`metavars` maps each metavar that the handler understands to its
  default.** These names are the ones that `tf.metavars` accepts. A handler
  that has both a CLI and an in-memory backend declares `BACKEND` among them,
  with the default `"cli"` or `"mem"`. The builder refuses any other value of a
  metavar of that name when it is assigned ([Language
  backends](language-backends.md), *Selecting a backend*).
- **`name` must not be a native or a compiled language.**
- **Registering a name again replaces its handler.** Transformations that are
  built afterwards carry the new one.
- A registration that is refused raises. The exception class is not specified.

### The arguments

| Parameter | Value |
|---|---|
| `code` | the source text of the transformation |
| `pins` | a dict: pin name to the pin's value, or to the path of a file (*Pins on file*) |
| `filesystem` | a dict: pin name to an entry, for the pins that may arrive as a file. `entry["filesystem"]` is true when `pins[name]` is a path. `entry["celltype"]` is the pin's celltype |
| `output_name` | the name of the result. For a Transformer it is `result` |
| `output_celltype` | the result celltype |
| `metavars` | a dict of every declared metavar: the transformer's value, or else the registered default |
| `environment` | the transformer's environment, as a dict, with keys such as `conda_environment` and `docker`. It is empty when none is set. A handler honours it through one of the two public functions (*Honouring the environment*) |
| `process_lock` | a bool: whether this run took the process lock |

- **`pins` holds the input pins only.** The code is not in it.
- **The handler runs in a namespace that holds its arguments and nothing
  else.** The pins are not visible as global variables.
- **The return value is the result.** Seamless serializes it under the result
  celltype, as it does for a Python transformer.
- **An exception that the handler raises is the failure of the
  transformation.**

### Honouring the environment

A handler honours its `environment` argument, or the transformation does not
honour it. Seamless offers two public functions, in
`seamless_transformer.languages`
([Language backends](language-backends.md), *The two public functions*):

| The handler runs the code | It calls |
|---|---|
| in the Python process that runs the transformation, as an embedded interpreter | `check_in_memory_environment(environment, language)` before it runs the code |
| as a process of its own | `execute_cli(command, pins_, PINS, FILESYSTEM, OUTPUTPIN, environment)` in place of starting the process itself |

- **`check_in_memory_environment` raises** for a Docker image, and for a conda
  environment that is not the one of the process. It also looks the names of
  `set_which` up on the process's `PATH`.
- **`execute_cli` wraps** a conda environment and a Docker image, looks
  `set_which` up inside the environment, and is cancelled and torn down with
  the transformation. A handler that starts a process itself gets none of it.
- **A handler returns a Python value.** For a deep result that is a dict whose
  members are values or `seamless.Checksum` objects. Nothing else is asked of
  it.
- **Both functions can be called outside a running transformation**, for
  example when a test calls the handler directly.
- **Nothing enforces it.** A handler that calls neither function ignores the
  environment, and gets no `which` check.

### The handler travels with the transformation

- **A build puts the handler's source into the Transformation.** It is carried
  in `__handler__`, outside the checksum.
- **The process that runs the transformation needs no registration.** A
  handler that is registered only in the script that builds the transformation
  also runs in a worker process, on a jobserver and on a Dask worker. What the
  handler imports, and the tools it starts, must exist there.
- **A transformation without `__handler__` uses the registry of the process
  that runs it.** This happens when a transformation is run from its checksum
  alone: by a fingertip, or by `seamless-run-transformation` without a dunder
  file. When that process has no handler for the language, the transformation
  fails.
- **Building needs the registration.** A builder for a registered language can
  be constructed, and a Transformation can be built from it, only in a process
  where that handler is registered. The two built-in handlers always are.

### Threads, and `run_in_interpreter_thread`

- **The process lock gives exclusion, not a fixed thread.** A handler never
  runs on the main thread of its process, and successive runs in one process
  may run on different threads. In `process` mode the thread that ran one handler
  may no longer exist when the next one runs.
- **`run_in_interpreter_thread(name, func, /, *args, **kwargs)` gives a fixed
  thread.** It runs `func(*args, **kwargs)` on one thread per process and per
  `name`, waits, and returns the result. An exception in `func` is raised in
  the caller.
  - The thread is created at the first call and lives until the process ends.
  - A call from that thread itself runs `func` at once, on that thread.
  - It takes no lock. Exclusion comes from the process lock.
  - With the environment variable `SEAMLESS_INTERPRETER_THREAD=0`, `func` runs
    on the calling thread.
- **Output that `func` prints on the interpreter thread is not in the
  transformation's log.** Capture belongs to the thread that runs the handler
  ([Transformation logs](transformation-logs.md), *What is captured*). Return
  the text, and write it from the handler.
- **A handler must not hold Python's GIL for seconds.** A worker pool checks
  each of its processes about once a second, and restarts one that does not
  answer. A call into an embedded interpreter that keeps the GIL for several
  seconds makes the process miss that check: the worker is restarted, and the
  transformation fails. The Julia in-memory backend (`juliacall`) runs the
  Julia code with the GIL released.
- **Whether `run_in_interpreter_thread` stays has not been ruled.** The
  Julia in-memory backend uses it, and the R in-memory backend does not. Do
  not rely on which thread runs R or Julia code.

## Logs, failures and cancellation

- **Output that the code prints is in the transformation's log, under both
  backends** ([Transformation logs](transformation-logs.md)).
  - CLI backend: stdout and stderr are two streams, relayed while the code
    runs, as for a bash transformation. On `remote: daskserver` they can be
    streamed ([Streaming](streaming.md)).
  - In-memory backend: the output may arrive only when the code has finished.
- **A failure of the code is a failure of the transformation**, and failures
  are not cached. The common ones: the code raises an error; block code never
  assigns `result`; a tool or a package is missing; a value cannot be carried
  by the backend; an in-memory backend runs without the process lock, or with
  an environment that it cannot honour.
- **The failure text depends on the backend.**
  - CLI backend: the *Bash transformer exception* report
    ([Transformation logs](transformation-logs.md), *The failure text*). Its
    command is the one that starts the interpreter, not the user's code. The
    language's own error message is in the standard error trailer.
  - In-memory backend: a Python traceback that carries the language's error
    message.
- **Cancellation** ([Cancellation](cancellation.md)). A run under a CLI
  backend is cancelled as a bash transformation is. Under an in-memory
  backend, a cancel in a worker pool terminates the worker process, and its
  interpreter with it. In `process` mode a cancel does not interrupt code that
  is running in the embedded interpreter, as it does not interrupt Python
  code.

## Environments

A transformer's environment ([Environments](environments.md)) is honoured, or
the transformation fails. It is never ignored. [Language
backends](language-backends.md), *Environments*, has the rule. For R and
Julia:

| The transformer has | CLI backend | In-memory backend |
|---|---|---|
| a conda environment | activates it, and starts the interpreter in it | runs only when its process is already in exactly that environment. Otherwise the transformation fails |
| a Docker image | starts the interpreter in a container made from the image | the transformation fails |
| both | refused at dispatch | refused at dispatch |

- **A CLI backend runs in the transformer's conda environment**, when
  `tf.environment.set_conda_env(...)` names one. The environment is activated
  before the interpreter starts, as for a bash transformation. This is how a
  transformer chooses its R or Julia installation.
- **A CLI backend runs in a container**, when `tf.environment.set_docker(...)`
  names an image. The image must hold the interpreter and the packages of the
  backend (*What a backend needs*). The host does not need R or Julia. The
  runtime, the image pull policy and the other settings are those of bash
  transformations ([Environments](environments.md), *The runtime is chosen
  where the job runs*).
- **An in-memory backend cannot enter an environment.** Its interpreter is the
  one embedded in the process that runs the transformation. A conda
  environment is therefore a requirement on that process: the process must
  already be running in exactly the environment that the transformer names. A
  specification that contains `/` is a path, compared with the process's
  `CONDA_PREFIX`. Any other specification is a name, compared with its
  `CONDA_DEFAULT_ENV`. The calling process must be in it in `process` mode,
  and the worker processes otherwise. When it is not, the transformation
  fails.
- **An in-memory backend fails for a Docker image**, always. The message names
  `BACKEND="cli"` as the alternative.
- **The checks run when the transformation runs.** A result that is already
  recorded is returned without them, and building never fails for an
  environment.
- **The Julia project of a CLI job** is the tracked Seamless Julia project.
  Seamless stages its `Project.toml` and `Manifest.toml` in the job directory
  and starts Julia with `--project=.`. `JULIA_PROJECT` does not select another
  project. The job uses a writable depot in its own directory first, followed
  by the depots named by `JULIA_DEPOT_PATH`, the conda installation's packaged
  depot when present, and the user's depot. In a container the image must name
  its packaged depot with `JULIA_DEPOT_PATH`, readable by the host user who
  runs the job. Its precompiled packages must be compatible with the executing
  CPU. For `juliacall` the project is the one that `juliacall` uses in the
  process.
- **The environment is not part of identity**, here as everywhere.
- **`tf.environment.set_which([...])` lists binaries that must exist.** They
  are looked up where the code runs. For a CLI backend that is inside the
  environment, after it is entered: a binary that exists only in the
  environment satisfies the check, and one that exists only on the host does
  not. For an in-memory backend it is the `PATH` of the process that runs the
  transformation.

## Current limitations

- **R and Julia code cannot resolve a checksum.** A `deepcell` pin serves to
  select and pass on members.
- **A `folder` pin holds every member in memory at once**, under both
  backends.
- **The CLI backends cannot take a Seamless-mixed pin.** The R CLI backend
  also refuses `float32` arrays and arrays with more than two dimensions
  (*Array rules*).
- **Isolations are never dropped.** An embedded interpreter keeps every
  `transform()` isolation it has built, and Julia cannot unload a module. A
  worker process that lives long and sees many different `transform()` codes
  grows.
- **A failure under a CLI backend is titled *Bash transformer exception***,
  although the code is R or Julia.
- **The execution record reports the language kind of a handler-language
  transformation as `python`** ([Execution records](execution-records.md)).
- **A user-registered language cannot be built where it is not registered**
  (*The handler travels with the transformation*). A process that loads a
  workflow graph with a node of that language must register the handler
  first.
- **Writing a job directory instead of running it** is for bash
  transformations only.

## Non-goals

- R or Julia through `seamless-run`, `direct` or `delayed` (*Faces*).
- Reading pin declarations from an R or a Julia signature, and optional pins.
- Installing R, Julia, their packages, `ryp` or `juliacall`.
- Compiled code. A language that compiles to a C-ABI `transform()` is a
  compiled language ([Compiled transformers](compiled-transformers.md)).

## Code locations

| Concern | Module / symbol |
|---|---|
| The handler API and the registry | `seamless_transformer.languages` (`register_language_handler`, `get_language_handler`, `is_handler_language`, `available_languages`, `run_in_interpreter_thread`) |
| The two functions that honour an environment | `seamless_transformer.languages` (`check_in_memory_environment`, `execute_cli`) |
| The R and the Julia handler | `seamless_transformer.languages.handlers` (`r`, `julia`) |
| Builders | `seamless_transformer.transformer_class` (`HandlerTransformer`, `DirectHandlerTransformer`); they are not public constructors |
| `__handler__` and the `__format__` entries | `seamless_transformer.pretransformation.direct_transformer_to_pretransformation` |
| Dispatch to the handler | `seamless_transformer.run.run_transformation_dict` |
| Bound builders | `seamless_workflow.context.Context._transformer_handle` |
