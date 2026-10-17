# Handler languages: R and Julia transformations

Written 2026-10-10, revised 2026-10-12. Paths are relative to
`/home/agent/seamless1`.

This plan adds a public *handler* API to `seamless_transformer.languages`, an
API that lists the accepted transformation languages, and two handlers built on
that API: R (`language="r"`) and Julia (`language="julia"`). A handler is a
Python function that runs a transformation written in another language. No R-
or Julia-specific code goes into Seamless outside the two handlers.

The plan started from a set of sketches (an exported conversation,
`seamless_r_julia_interop_conversation.md`). That file is no longer in the
workspace. What the plan takes from it is in Appendix A.

Whoever implements this plan should read §10 first. It holds the working
conditions and the code mechanics that the design sections assume.

## 0. What is ruled

Ruled by the author (2026-10-10):

- **R1 — Handlers travel as source.** The handler's source is shipped with the
  transformation in a new orthogonal dunder, as `__compilation__` is for
  compiled languages.
- **R2 — The listing reports constructible languages only**: python, bash, the
  compiled languages and the handler-registered ones. `ipython` is not a
  Transformer language today and is not listed.
- **R3 — Two code styles.** *Block*: pins are variables and the code assigns
  the output name. *`transform()`*: the code defines a top-level function
  `transform`.
- **R4 — Neutral filesystem config** for `mixed`, `plain`, `text`, `bytes` and
  `binary` pins: a path when the buffer is on file in a read folder, the value
  otherwise. The handler converts either form.
- **R5 — Each handler has a `BACKEND` metavar.** The default is the CLI and
  the alternative is in-memory. **Superseded backend values:** this draft
  called them `"Rscript"`/`"julia"` and `"ryp"`/`"juliacall"`; the current
  values are `"cli"` and `"mem"` in every handler language, as settled by
  `language-backends-plan.md` §4.1. Those four names are tools, not values.
- **R6 — Isolations are cached inside the embedded interpreter**, not in
  Seamless.
- **R7 — The owner-thread helper is implemented for juliacall**, and a final
  testing phase decides whether it is necessary (§6).
- **R8 — R, ryp and juliacall may be installed** into the `seamless1` conda
  environment for testing.

Ruled by the author (2026-10-12):

- **R9 — An in-memory backend refuses to run without the process lock.**
- **R10 — The CLI backends are built on `execute_bash`.**
- **R11 — Backend parity.** Either backend gives the same bitwise result if it
  succeeds. A backend may fail where the other succeeds. It may not succeed
  with a different result. Accepted with it:
  - JSON-typed values cross as JSON text in both backends, so `jsonlite` and
    `JSON.jl` are dependencies of the in-memory backends too;
  - every handler test runs under both backends and compares result checksums.
- **R12 — An in-memory backend cannot enter an environment.** It raises for a
  Docker specification. For a conda specification it checks that its process
  is already in exactly the specified conda environment, and raises otherwise.

Proposed by this plan and accepted by the author (2026-10-12):

| | Choice |
|---|---|
| A1 | The names `register_language_handler`, `get_language_handler`, `is_handler_language`, `available_languages`, `run_in_interpreter_thread`, and the dunder `__handler__` |
| A2 | A handler receives keyword arguments chosen by its own parameter names, from a fixed set (§3.1) |
| A3 | When `__handler__` is absent, the executor falls back to its own registry |
| A4 | `tf.metavars.BACKEND` is stored in `__meta__["metavars"]`, outside the checksum |
| A5 | A language name is unique across the native, compiled and handler kinds |
| A6 | The `transform()` style is detected by parsing the code in its own language |
| A7 | ryp runs without the helper: unique R names per run, one `r()` call |
| A8 | The CLI backends depend on `RcppCNPy` and `jsonlite` (R) and `NPZ.jl` and `JSON.jl` (Julia) |

This plan's means to R11, not ruled separately: one in-language runtime per
language, shared by both backends (§3.4).

## 1. Dependence on the process lock

[process-lock-implementation-plan.md](process-lock-implementation-plan.md) is being implemented as of 2026-10-12.
This plan is written against that plan's design, not against the working tree.

| This plan uses | From that plan |
|---|---|
| One body per process by default; R9 | R2, §3.3: every transformation claims the process lock around its body unless `process_lock` is false or `driver` is true |
| The `process_lock` handler argument | §3.1: `resolve_lock_meta` |
| `execute_bash` without `chdir` and without a lock; R10 | R1, §3.6 (Phase A) and §3.3 (Phase D) |
| A CLI body that shells out to `seamless-run` | R8 (Phase E), inherited through `execute_bash` |

- Work here starts after that plan's Phase D has landed. Both plans edit
  `run.py`, `transformation_utils.py` and `transformer_class.py`.
- Phase E is not required. Until it lands, an R or Julia CLI body that runs
  `seamless-run` can wait on its own nested job, as a bash body can, and needs
  `process_lock = False`.
- A handler body runs Python code that submits no nested work, so it holds the
  lock for the whole body and never drops it.

State of that plan in the working tree on 2026-10-12. Re-check before starting;
do not rely on this list:

- Phases A, B and C were committed in seamless-transformer (`ec487b7`,
  `c42e897`, `b486ae9`).
- Phase D was present as uncommitted changes: `process_lock.py` existed,
  `run_transformation_dict` wrapped both body call sites in its `scope`, and
  direct attribute access to `global_lock` raised with a pointer to
  `process_lock`; a `from ... import global_lock` statement raised Python's
  generic `ImportError`.
- Phase E was absent: `NOTIFY_ENV` was defined in `process_lock.py` and nothing
  read it.

Phase D has landed when its changes are committed and
`tests/test_contract_process_lock_runtime.py` and
`tests/test_contract_process_lock_scope.py` pass.

## 2. Facts this plan relies on

Read in the source unless marked **measured** or **unverified**.

### 2.1 Where bodies run

- Every body runs inside `run_transformation_dict`
  ([run.py](../../seamless-transformer/seamless_transformer/run.py)). Bash is dispatched there by rewriting the
  code to a Python statement that calls `execute_bash`, which `_execute` then
  runs through `exec_code`.
- Both callers put it on an executor thread: the worker child
  ([worker.py](../../seamless-transformer/seamless_transformer/worker.py), `handle_execute`) and in-process execution
  ([transformation_cache.py](../../seamless-transformer/seamless_transformer/transformation_cache.py)). A body never runs on a main thread, and
  successive bodies in one process land on different threads.
- **Measured** (2026-10-10, before the process lock): in one spawn child,
  successive bodies ran on `asyncio_1, 2, 3, 1, 4, 3`. In-process, each
  synchronous call got a fresh loop and executor, so the thread that ran one
  body no longer exists when the next runs.
- The process lock gives exclusion. It does not fix which thread runs a body.
- The parent pings each spawn child every second and restarts a child that
  misses a ping (`_health_loop` in [process/manager.py](../../seamless-transformer/seamless_transformer/process/manager.py)).
  **Measured** (2026-10-10): a body that held the GIL for 5 s through
  `ctypes.PyDLL(None).sleep` had its worker restarted three times for "ping
  timeout", and the transformation failed. The same body through `ctypes.CDLL`,
  which releases the GIL, and a 1 s hold both completed.

### 2.2 ryp 0.5.0

- `R_CStackLimit` is set to -1 at init (`ryp.py:602`), which removes R's
  thread-affinity check.
- `r()`, `to_r()` and `to_py()` each take one internal `RLock`
  (`ryp.py:1646`, `1921`, `3572`). Init is allowed off the main thread.
- A forked child raises if the parent initialised R. Seamless workers are
  spawned, so this does not arise.
- Requires `cffi`, `pyarrow`, `numpy` and the R package `arrow`. Its README
  says the conda package installs R and `arrow`.
- **Unverified**: that the GIL is released while R runs (cffi releases it
  around C calls by default).

### 2.3 juliacall 0.9.36

- libjulia is loaded with `ctypes.PyDLL` (`juliacall/__init__.py:247`), so the
  GIL is held for every call into Julia. Its docs: "You can use JuliaCall from
  any Python thread, and the GIL will be locked whenever any JuliaCall function
  is used."
- With §2.1 this means a Julia body longer than about 2 s must run with the
  GIL released, under spawn, Dask and jobserver alike. The docs give
  `_jl_call_nogil` for that, and require that such a function "does not
  interact with Python at all".
- The docs warn that a Julia function that yields to Julia's scheduler (their
  example is `sleep`) "will likely hang" when called from a pool thread, unless
  the thread that started Julia keeps calling `jl.yield()`. They state this for
  the `_jl_call_nogil` pattern.
- The docs mark multi-threading experimental and recommend
  `PYTHON_JULIACALL_HANDLE_SIGNALS=yes` with multiple threads.
- **Unverified**: everything about juliacall at run time. It was not installed
  when this plan was written.

### 2.4 Buffer bytes per celltype

**Measured** with `Buffer(value, celltype).content`:

| Celltype | Bytes |
|---|---|
| `text` | the text plus a newline |
| `plain` | JSON |
| `bytes` | raw |
| `binary` | `.npy` |
| `mixed` | `.npy` for an array, JSON for a plain value, a `SEAMLESS-MIXED` container for a value that mixes both |

A read-folder file holds these same bytes, possibly with a compression suffix.

### 2.5 Existing code this plan reuses

- `build_transformation_namespace_sync`
  ([transformation_namespace.py](../../seamless-transformer/seamless_transformer/transformation_namespace.py)): for a pin whose format is
  `{"mode": "file", "optional": True}` it puts the read-folder path in `PINS`
  and sets `FILESYSTEM[pin]["filesystem"]` to true when the file exists, and
  falls back to the in-memory value otherwise.
- `write_bash_job` ([execute_bash.py](../../seamless-transformer/seamless_transformer/execute_bash.py)): symlinks a filesystem pin
  into the job directory, converting between compression suffixes, and writes a
  `bytes` or `Buffer` value raw.
- `execute_bash`: conda activation, process group and cleanup, stdout and
  stderr streaming, and reading `RESULT` as `.npy`, then JSON, then text.
- `direct_transformer_to_pretransformation`
  ([pretransformation.py](../../seamless-transformer/seamless_transformer/pretransformation.py)): the one place that builds the dict for
  standalone and bound builders.
- `TRANSFORMATION_ORTHOGONAL_DUNDER_KEYS`
  ([transformation_utils.py](../../seamless-transformer/seamless_transformer/transformation_utils.py)): membership keeps a key out of the
  checksum (`tf_get_buffer`) and carries it to workers (`extract_tf_dunder`).
- `getsource` ([getsource.py](../../seamless-transformer/seamless_transformer/getsource.py)) and `analyze_code`
  ([cached_compile.py](../../seamless-transformer/seamless_transformer/cached_compile.py)).
- `BoundMetaVars` ([compiled_transformer.py](../../seamless-transformer/seamless_transformer/compiled_transformer.py)): the pattern for
  metavars on a bound Transformer.

## 3. Design

### 3.1 The public API

In [languages/\_\_init\_\_.py](../../seamless-transformer/seamless_transformer/languages/__init__.py):

```python
def register_language_handler(name, handler, *, metavars=None) -> None: ...
def get_language_handler(name): ...
def is_handler_language(name) -> bool: ...
def available_languages() -> dict[str, str]: ...
def run_in_interpreter_thread(name, func, /, *args, **kwargs): ...
```

- `handler` is one self-contained Python function: imports inside the body, no
  closure. This is the discipline of Python transformer code. Registration
  checks with `analyze_code` that its source is in function mode.
- `metavars` maps each metavar the handler understands to its default.
- Registration rejects a name taken by another kind (A5) and a handler
  parameter outside the offered set.
- `available_languages()` maps each accepted `language` value to `"native"`
  (python, bash), `"compiled"` or `"handler"`.
- The handlers package is imported at the bottom of the module, as `native` is.

The handler is called with keyword arguments selected by its parameter names
(A2). The offered set:

| Name | Value |
|---|---|
| `code` | the transformation source text |
| `pins` | pin name to value, or to a read-folder path |
| `filesystem` | pin name to its format entry: `["filesystem"]` true means `pins[name]` is a path; `["celltype"]` is the pin's celltype |
| `output_name`, `output_celltype` | from `__output__` |
| `metavars` | the registered defaults merged with the transformer's values |
| `environment` | the resolved `__env__` dict |
| `process_lock` | whether this body claimed the process lock |

The return value is the result. Seamless serialises it as for any Python body.

### 3.2 Shipping and dispatch

- **Orthogonal dunder.** Add `__handler__` to
  `TRANSFORMATION_ORTHOGONAL_DUNDER_KEYS`. Mirror it in the fallback set in
  [why_not/diff.py](../../seamless-share/seamless_share/why_not/diff.py) and in the tuple of envelope checksums that a
  Transformation holds references on
  ([transformation_class.py](../../seamless-transformer/seamless_transformer/transformation_class.py), next to `__compilation__`).
- **Building**, for a handler language:
  - In `_build_from_frozen_core` ([transformer_class.py](../../seamless-transformer/seamless_transformer/transformer_class.py)): merge the
    registered metavar defaults under `meta["metavars"]` once, and pass that
    one meta to both `direct_transformer_to_pretransformation` and
    `transformation_from_pretransformation`. Today each gets its own
    `deepcopy(frozen.meta)`, and the second overlays the first key by key
    (§10.2), so a merge done in only one of them is lost.
  - In `direct_transformer_to_pretransformation`: set `__handler__` to the
    checksum of the handler source, stored as `text` with
    `_buffer_checksum_hex`.
  - In the same function: give each `mixed`, `plain`, `text`, `bytes` and
    `binary` pin `{"filesystem": {"mode": "file", "optional": True}}` in
    `__format__` (R4). `__format__` is in the checksum; this entry is the same
    for every transformation of a handler language, so identity is stable.
- **Executing.** In `run_transformation_dict`, beside the bash branch:
  - resolve `__handler__`, or look the language up in the local registry (A3);
  - read the handler's parameter names with `ast`;
  - build a fresh namespace that holds only those keyword arguments;
  - set `code` to the handler source and `inputs` to its parameters.

  The existing `_execute` call then runs the handler through `exec_code` in
  function mode, inside the process-lock scope that is already there. `run.py`
  gains no language name and no lock code.
- `transformation_namespace.py` does not change.
- The write-remote-job mode stays bash-only.

### 3.3 Builders

- [transformer_class.py](../../seamless-transformer/seamless_transformer/transformer_class.py): `HandlerTransformer` and
  `DirectHandlerTransformer` beside `BashTransformer`. They are code-less, so
  pins are declared through `tf.pins`. `Transformer.__new__` returns them for a
  handler language, and its error message names the three kinds.
- `tf.metavars` accepts the handler's declared names only (A4). Standalone it
  writes `_meta["metavars"]`. Bound it writes the node's `meta` mapping.
- `process_lock` and `driver` behave as on any builder.
- [context.py](../../seamless-workflow/seamless_workflow/context.py), `_transformer_handle`: select the handler classes when
  `is_handler_language(cfg.language)`.

### 3.4 What both handlers share

Files: `languages/handlers/__init__.py`, `r.py`, `julia.py`. Registration
imports neither R nor Julia; a backend imports its tool inside the handler.

**One runtime per language.** `BACKEND` is outside the checksum, so a result
cached under one backend is served under the other. R11 is what makes that
valid. To meet it, each handler carries one source text in its own language,
the *runtime*, used by both backends. The CLI runner loads it and passes file
paths. The in-memory backend defines it once in the interpreter and passes
values. The runtime does everything whose outcome the user code or the result
can observe:

- detect the code style (A6);
- build or fetch the isolation;
- turn each pin into a native value;
- run the code;
- classify and encode the result.

Only the transport differs between backends. A backend that cannot transport a
value raises. It never substitutes another encoding, because that would be a
success with a different result.

**Code styles (R3).**

| | Block | `transform()` |
|---|---|---|
| Detected by | no top-level definition of `transform` | a top-level definition of a function named `transform` |
| Isolation | fresh for every run | built once per key, with no pins bound |
| Pins | bound as variables | passed as arguments by name |
| Result | the value of the output name; an error if undefined | the return value |

- R detection: `parse(text = code)`, then look for a top-level assignment of a
  `function` to `transform`.
- Julia detection: `Meta.parseall(code)`, then look for a top-level function
  definition named `transform`, in long or short form, through `where`,
  return-type and docstring wrappers.

**Isolation cache (R6).** Inside the interpreter, keyed by a SHA-256 over the
code, the output name and the pin names. Python computes the key and passes it
as a string. There is no Python-side cache. After a worker restart the cache is
empty and is rebuilt on use.

**Values.** JSON-typed values cross as JSON text in both backends and are
parsed by the same call in the runtime. That is what makes the two backends
agree.

| Pin | Native value in R | Native value in Julia |
|---|---|---|
| `text` | character string, final newline removed | `String`, final newline removed |
| `plain`, and `mixed` holding JSON | `jsonlite::fromJSON` | `JSON.parse` |
| `bytes` | raw vector | `Vector{UInt8}` |
| `binary`, and `mixed` holding `.npy` | numeric or integer vector or matrix | `Array` |
| any other celltype (`int`, `float`, `bool`, `str`, …) | as `plain` | as `plain` |

- For a `mixed` pin the handler chooses by the magic bytes.
- A `SEAMLESS-MIXED` container is accepted by the in-memory backends only. Its
  plain parts follow the JSON rule and its arrays the array rule. The CLI
  backends raise for it.

| Result | Returned to Seamless as |
|---|---|
| output celltype `bytes` | raw bytes |
| a numeric array, when the output celltype is `binary` or `mixed` | a C-contiguous NumPy array |
| anything else | the value parsed from the runtime's JSON encoding |

- A length-1 R vector without dimensions is a scalar.
- Where the two tools of a language would hand the code different native
  values for the same pin, or return different arrays for the same result, the
  handler normalises them to one, or one backend refuses. The rule set is fixed
  during Phase 4 with both backends running and is written into the contract
  page.

**Inputs are not writable through to Seamless.** A `.npy` file is opened with
`np.load(mmap_mode="c")`. An in-memory array is passed read-only or as a copy.

### 3.5 CLI backends (R10)

- The handler writes two extra files into the job, the runner and the user
  code, and calls `execute_bash` with the command.
- A pin on file is left as its path; `write_bash_job` symlinks it and handles a
  compressed file. A pin in memory is passed as `Buffer(value, celltype)`, which
  is written raw. Either way the job file holds the canonical buffer bytes, so
  the runner loads by celltype alone.
- The runner writes one `RESULT` file: `.npy`, raw bytes or JSON. Strings are
  JSON-quoted, so `execute_bash` returns exact types.
- Inherited from `execute_bash`: conda activation, the process group and its
  cleanup, output streamed into the transformation logs, and the nesting signal
  once it exists.
- They run one at a time per process under the default process lock, and in
  parallel with `tf.process_lock = False`.

| | R | Julia |
|---|---|---|
| Command | `Rscript --vanilla runner.R` | `julia --startup-file=no runner.jl` |
| `.npy` | `RcppCNPy` | `NPZ.jl` |
| JSON | `jsonlite` | `JSON.jl` |
| Environment | conda environment from `environment` | `JULIA_PROJECT`, and the conda environment |

### 3.6 In-memory backends

- **The process lock is required (R9).** When the `process_lock` argument is
  false the handler raises and names the CLI backend as the alternative. One
  transformation per embedded interpreter is then guaranteed by Seamless.
- A pin on file is read in Python; a pin in memory is used as it is.
- A `SEAMLESS-MIXED` container pin is passed as a JSON text for its plain parts
  plus its arrays, which the runtime puts back in place.
- **Environments (R12).** For an in-memory handler, `docker` is refused and
  `conda_environment` requires the process to already be in that exact
  environment. The comparison is settled by
  `language-backends-plan.md` §4.2: a specification containing `/` is a path
  compared with the real path of `CONDA_PREFIX`; otherwise it is a name
  compared with `CONDA_DEFAULT_ENV`. A CLI handler honours Docker and conda
  through the shared wrapper, as set out in §4.3 of that plan.

**ryp (A7).** No helper.

- Each run uses R names that are unique to it for the inputs, the code and the
  result.
- One `r()` call does all the R-side work through the runtime.
- The result is fetched with one `to_py()` call, and the names are removed.
- Function-style isolations live in a hidden environment in `globalenv()`.

**juliacall (R7).** Everything runs inside
`run_in_interpreter_thread("juliacall", ...)`.

- That thread imports juliacall, so it is also the thread that starts Julia.
- The runtime is one Julia module, defined once in `Main`. It holds the
  isolation `Dict`. Block code gets a fresh `Module` per run.
- Inputs are turned into native Julia values while the GIL is held. An array
  becomes an `Array`: without a copy when it is one-dimensional or
  Fortran-contiguous, with one copy otherwise.
- The user code runs with the GIL released (§2.3).
- The result is copied into plain Python and NumPy objects on the owner thread.
  No juliacall object leaves that thread, because dropping one elsewhere calls
  into Julia from that other thread.
- Julia's stdout and stderr are redirected to temporary files and written to
  `sys.stdout` and `sys.stderr` from the body thread, so they reach the
  transformation logs. It has to be the body thread: output is routed by a
  context variable (§10.2), which the owner thread does not share, and Julia
  writes to the process's file descriptors, not to Python's `sys.stdout`.

### 3.7 The interpreter-thread helper

`run_in_interpreter_thread(name, func, /, *args, **kwargs)`:

- runs `func` on a process-wide, lazily created, single thread and blocks for
  the result or re-raises its exception;
- keys the thread by `(os.getpid(), name)`;
- runs `func` inline when the caller already is that thread;
- takes no lock.

The switch `SEAMLESS_INTERPRETER_THREAD=0`, which ran `func` inline on the
calling thread for §6, was removed after §6 (see §8).

It is language-agnostic: any handler that embeds an interpreter with thread
affinity can use it.

## 4. Phases

| Phase | Depends on | Needs R or Julia? |
|---|---|---|
| 1 — Core | Phase D of the process-lock plan | No |
| 2 — Julia CLI backend | 1 | The `julia` binary (1.12.6 is installed) with `NPZ` and `JSON` |
| 3 — Install | — | — |
| 4 — Rscript, ryp, juliacall | 2, 3 | Yes |
| 5 — Docs | written alongside | — |
| 6 — Is the helper necessary? | 4 | juliacall, ryp |

### Phase 1 — Core

- §3.1, §3.2, §3.3 and §3.7.
- **Exit:** the Phase 1 tests of §5 pass with a toy handler; the existing bash,
  factory, language, metavar and process-lock test files pass unchanged.

### Phase 2 — Julia CLI backend

- The Julia runtime and runner, the `julia` backend, the shared value rules of
  §3.4.
- **Exit:** the Julia handler tests pass for `BACKEND="julia"`.

### Phase 3 — Install

- Into `seamless1`: ryp from conda-forge (which brings R and `arrow`),
  `r-jsonlite`, `r-rcppcnpy`, and `juliacall` from pip.
- `NPZ` and `JSON` in the Julia project that the tests use, and `JSON` in the
  project that juliacall resolves.
- **Exit:** `Rscript`, `import ryp` and `import juliacall` work in the
  environment. If a package has no build for its Python 3.14, stop and report.

### Phase 4 — Rscript, ryp, juliacall

- The R runtime and runner, and the three remaining backends.
- Fix the dtype normalisation rules (§3.4).
- **Exit:** every handler test passes under both backends of its language, and
  the parity tests pass.

### Phase 5 — Docs

The pages of §7.

### Phase 6

§6.

## 5. Tests

Run with `/home/agent/miniforge3/envs/seamless1/bin/python`, `PYTHONPATH` set to
the repositories, one pytest process per file.

Phase 1, `tests/test_language_handlers.py`, with a toy handler:

- registration, a name collision, a parameter outside the offered set;
- `available_languages()` reports each kind;
- the factory returns the handler classes; `language` is read-only;
- `tf.metavars` rejects an undeclared name;
- the transformation checksum is the same for two different handlers and for
  two `BACKEND` values, and differs when a pin's celltype changes;
- with `_get_read_folder_directories` pointed at a temporary folder, a pin
  arrives as a path; without it, the same pin arrives as its value;
- a handler registered only in the driver process runs in-process and under
  `spawn`;
- a dict without `__handler__` runs through the local registry;
- the handler sees `process_lock` true by default and false after
  `tf.process_lock = False`.

Phase 1, `tests/test_interpreter_thread.py`:

- calls from many threads all run on one thread id;
- an exception propagates to the caller;
- a call from the owner thread runs inline;
- the environment switch runs inline on the calling thread.

Phases 2 and 4, `tests/test_r_handler.py` and `tests/test_julia_handler.py`,
skipped when the tool is missing:

- each backend, both code styles;
- each of the five celltypes of R4, in both forms;
- a scalar pin, a script that fails, a result that is never assigned;
- a `transform()` isolation is built once across two runs with different
  inputs;
- an in-memory backend with `process_lock = False` raises (R9);
- an in-memory backend raises for a Docker specification, and for a conda
  specification other than the environment of its process; it runs when the
  specification is the environment of its process (R12);
- a body that mutates an input leaves the pin's checksum unchanged;
- output printed by the code reaches the transformation logs.

Phase 4, parity (R11):

- every case above runs under both backends of its language, and where both
  succeed the result checksums are equal;
- the cases where exactly one backend fails are listed and asserted: a
  `SEAMLESS-MIXED` container pin, and an array that `RcppCNPy` cannot read
  (three dimensions, `float32`), each succeeding in memory and raising under
  the CLI.

Bound mode: one `ctx.tf = Transformer("julia")` test in seamless-workflow, with
`ctx.tf.metavars.BACKEND` set.

## 6. Final testing phase: is the helper necessary?

Run the real juliacall backend twice: with the helper on, and with
`SEAMLESS_INTERPRETER_THREAD=0`. Under R9 every in-memory body holds the
process lock, so both settings are sequential:

| Setting | What it exercises |
|---|---|
| Repeated in-process runs | The thread that started Julia no longer exists |
| Repeated runs in one spawn child | That thread is idle in the pool, and bodies arrive on others |

Julia snippets, each in both settings and both modes:

- pure computation;
- `sleep`;
- `println`;
- `@async` with `fetch`, and `Threads.@spawn` with `fetch`;
- a subprocess;
- an allocation loop that forces garbage collection;
- a body that runs for 10 s.

The inline mode is repeated with `PYTHON_JULIACALL_HANDLE_SIGNALS=yes`.

Each cell is recorded as pass, hang (timeout) or crash. The table and a verdict
go to the author, who decides whether the helper stays. The same two settings
are run for ryp, which uses no helper, to check A7.

## 7. Docs

- New contract page `docs/agent/contracts/handler-languages.md`: the API, the
  handler arguments, the orthogonality of the handler and of `BACKEND`, the
  parity guarantee of R11, the neutral filesystem config, the two code styles,
  the value rules, and R9.
- `transformers.md`: the languages the factory accepts.
- `identity-and-caching.md`: `__handler__` among the orthogonal keys; the
  neutral `__format__` entry.
- `execution-backends.md`: in-memory backends and the process lock.
- `index.md` and `seamless-transformer/README.md`.
- The generated page `docs/agent/api/python/seamless_transformer.languages.md`:
  regenerate with `docs/agent/scripts/gen_agent_docs.py`.
- Contract pages state the contract only. Claims are indexed by face: this is
  the Python API, not `seamless-run`.

## 8. Decisions

- **Resolved later by `language-backends-plan.md` §§4.2–4.3:** an in-memory
  backend refuses a Docker specification; a CLI backend runs in the
  configured container. A Docker image together with `conda_environment` is
  refused at dispatch. The original decision that this was open is historical.
- **Unspecified for the time being** (author, 2026-10-12): what happens when
  the pins do not match the parameters of `transform`.
- **Ruled after §6** (author, 2026-10-17): the helper stays, and
  `SEAMLESS_INTERPRETER_THREAD` is removed. Results and verification:
  [`julia-r-interpreter-thread-results.md`](julia-r-interpreter-thread-results.md).

## 9. Risks and limits

Unverified:

- Nothing in this plan was run against ryp, juliacall or R. §2.2 and §2.3 are
  from source and documentation.
- That Julia can be told to release the GIL around the user code from inside
  the runtime, and that reading a NumPy buffer from Julia is safe while it is
  released.
- That the scheduler warning of §2.3 applies to calls that keep the GIL. §6
  tests it.
- That Julia shuts down cleanly when the process exits and Julia was started
  on the owner thread.
- That the conda and pip packages of Phase 3 exist for the environment's
  Python 3.14.
- The dtype behaviour of `RcppCNPy` and of ryp for integer arrays.

Limits:

- `RcppCNPy` reads numeric and integer vectors and matrices only. The Rscript
  backend reads the `.npy` header and raises for anything else; ryp may accept
  it. R11 allows that difference.
- The CLI backends cannot take a `SEAMLESS-MIXED` container pin.
- Isolation caches are unbounded, and Julia cannot unload a module. A
  long-lived worker that sees many distinct `transform()` codes grows.
- An in-memory body cannot be cancelled in-process. In a worker, a cancel kills
  the child and its interpreter with it.
- A CLI failure carries the "Bash transformer exception" wording of
  `execute_bash`.
- `record_assembly.py` reports `language_kind = "python"` for a language it
  does not know. Left unchanged.
- A frozen transformer for a user-registered language can only be built in a
  process where that handler is registered. The two built-in handlers always
  are.
- **Superseded:** this plan originally excluded `deepcell`, `deepfolder` and
  `folder` pins and results. `language-backends-plan.md` §4.6 adds them for R
  and Julia under both backends; see
  [Deep celltypes](../docs/agent/contracts/deep-celltypes.md) and
  [Handler languages](../docs/agent/contracts/handler-languages.md) for the
  current contract. R and Julia still cannot resolve checksum objects.

## 10. Notes for the implementer

### 10.1 Working conditions

- **Repositories.** `/home/agent/seamless1` is not a git repository. Each
  directory in it is its own repository, on `main`. This plan touches
  `seamless-transformer` (code and tests), `seamless-workflow` (`context.py`
  and one test), `seamless-share` (one set in `why_not/diff.py`) and `seamless`
  (docs and this plan).
- **Other work is in flight in the same trees**: the process lock, and the
  other plans in `seamless/plans/`. Run `git status` in each repository first.
  Do not revert, reformat or commit changes that are not yours. Commit only
  when the author asks.
- **"The author"** in this plan is the owner of Seamless, who gives the
  rulings. A change to the transformation-dict contract beyond `__handler__`,
  or to the graph file format, needs a ruling first.
- **Reading code.** `CLAUDE.md` and `AGENTS.md` at the workspace root ask for
  the Serena symbol tools for code files.
- **Tests.**
  - Interpreter: `/home/agent/miniforge3/envs/seamless1/bin/python`. The base
    Python has stale copies of some Seamless packages.
  - `PYTHONPATH`: the directories `seamless-core`, `seamless-transformer`,
    `seamless-remote`, `seamless-config`, `seamless-dask` and
    `seamless-signature`, as absolute paths.
  - One pytest process per test file. Running several files in one process
    gives spurious failures.
  - Do not launch a whole suite unless the author asks (`AGENTS.md`).
  - Some tests fail independently of this work. Before the first edit, run the
    files named in the Phase 1 exit criterion once and keep the result as the
    baseline.
- **Tools on the machine, 2026-10-10.** `julia` 1.12.6 at
  `~/.juliaup/bin/julia`. No `Rscript`. The `seamless1` environment has Python
  3.14.4 and NumPy, and has neither `pyarrow`, `ryp` nor `juliacall`. The
  versions read for §2 were ryp 0.5.0 and juliacall 0.9.36.
- **Stop and report** when: Phase D of the process-lock plan has not landed; a
  Phase 3 package cannot be installed; a test of §5 can only pass by weakening
  R9 or R11; §6 is complete.

### 10.2 Code mechanics the design assumes

- **How a handler gets called.** `exec_code` ([cached_compile.py](../../seamless-transformer/seamless_transformer/cached_compile.py))
  classifies the code with `analyze_code`. Source that is exactly one top-level
  `def` is in function mode: the definition is executed and then
  `<output> = <name>(<p>=<p>, ...)` for every name in `inputs`, each looked up
  in the namespace. The result is read from `namespace[output_name]`.
  - The handler source must therefore be one `def` and nothing else.
    `getsource` dedents it and strips decorators.
  - `analyze_code` is cached on `(code, identifier)` and the identifier names
    the entry in `linecache`. Give handler runs an identifier that contains the
    handler checksum.
  - A name in `inputs` that ends in `_SCHEMA` is dropped. None of the offered
    names does.
- **Unknown dunders are fatal.** `tf_get_buffer` raises on a dunder key it does
  not know. Add `__handler__` to the orthogonal set before any dict carries it.
- **`__handler__` is a checksum hex string**, like `__env__`. Read it in
  `run.py` with `_get_execution_dunder`, which looks in the dict and then in
  `tf_dunder`, and resolve it with `Checksum(...).resolve().get_value("text")`.
  Store it as `text` and read it back as text.
- **Meta reaches a Transformation twice.** `_build_from_frozen_core` passes
  `deepcopy(frozen.meta)` to `direct_transformer_to_pretransformation`, which
  writes it into the dict's `__meta__`, and again as `meta=` to
  `transformation_from_pretransformation`. There, `_collect_tf_dunder` starts
  from the dict's `__meta__` and applies the second copy with a shallow
  `update`. A `metavars` key in the second copy replaces the first one whole.
- **The namespace builder.** `build_transformation_namespace_sync` returns
  `(code, namespace, modules_to_build)`.
  - For a language other than python, `code` is the text of the `code` pin,
    whose celltype is `text`.
  - `namespace["PINS"]` maps pin names to values or paths.
    `namespace["FILESYSTEM"][pin]` has the keys `mode`, `optional`,
    `filesystem` (true when the path form was used) and `celltype`.
  - Every pin is also a top-level name in `namespace`. The handler must not see
    those, hence the fresh namespace of §3.2.
  - A compressed read-folder file is a valid match, so a path can end in a
    compression suffix (`compression_utils.strip_compression_suffix`).
- **`write_bash_job` and `execute_bash`.**
  - Signature: `execute_bash(bashcode, pins_, conda_environment_, PINS,
    FILESYSTEM, OUTPUTPIN)`. `pins_` is the list of names to materialise.
  - A pin whose `FILESYSTEM` entry has `filesystem` true is symlinked into the
    job directory under the pin's name, and its path is exported as an
    environment variable of that name.
  - A `Buffer` or `bytes` value is written raw.
  - A `str` value is written as text, and also exported as an environment
    variable when the pin name has no dot and the text is at most 1000
    characters. Pass every in-memory value as a `Buffer`, scalars as
    `Buffer(value, "plain")`, to keep the job files uniform.
  - A value whose storage is mixed raises `TypeError`.
  - `RESULT` is read as `.npy`, then as JSON, then as text. With `OUTPUTPIN`
    equal to `bytes` it is returned raw.
- **Output routing.** `sys.stdout` and `sys.stderr` are routing streams
  ([output_routing.py](../../seamless-transformer/seamless_transformer/output_routing.py)) that send each write to the route held in a
  context variable. A write from a thread that does not carry the body's
  context is not part of the transformation's logs.
- **Workers are replaced.** A cancel or a worker failure terminates the spawn
  child and starts a new one. Every in-interpreter cache starts empty again.

### 10.3 Places that branch on the language

Check each one. Most need no change.

| Place | What it does | Change |
|---|---|---|
| `transformer_class.py`, `Transformer.__new__` | Maps `(language, direct)` to a class, else raises | Yes (§3.3) |
| `transformer_class.py`, `PythonMixin._set_code` | Optional pins only for python | No |
| `pretransformation.py`, `direct_transformer_to_pretransformation` | Code celltype is `python` or `text`; filesystem format for folders | Yes (§3.2) |
| `run.py`, `run_transformation_dict` | The bash branch | Yes (§3.2) |
| `module_builder.py` | Languages of *modules* | No |
| `record_assembly.py` | `language_kind` falls back to `python` | No (§9) |
| `seamless-workflow`, `context.py`, `_transformer_handle` | Picks the handle class | Yes (§3.3) |
| `seamless-workflow`, `context.py` and `reactive.py` | Build a `PythonBashBaseTransformer` with `__new__` for internal use | Check |
| `seamless-workflow`, `serialization.py` | Code buffer is `python` or `text` by language | No |
| `seamless-workflow`, `configuration.py` | Optional pins only for python | No |
| `tests/test_transformer_factory.py` | Expects the factory error to match `python.*bash`, for `Transformer("c")` | Keep the new message matching, or update the test |
| `docs/agent/contracts/transformers.md` | States that the language must be python or bash | Yes (§7) |

Bound Transformers:

- A bound handle is created with `bound_cls.__new__(bound_cls)`. `__init__`
  does not run, so `metavars` must be a property that reads
  `_workflow_backend`.
- A node's `meta` is updated with a shallow `dict.update`
  (`configuration.update_config`, field `meta`). Write the full `metavars`
  mapping every time.
- `meta` is part of the node's `config_token`, so changing `BACKEND` changes
  the token. The transformation checksum does not change, so a re-evaluation
  should be a cache hit. Not verified; the bound-mode test of §5 should check
  it.

### 10.4 Things not to do

- No language name and no lock code in `run.py`.
- No Python-side cache of isolations (R6), and no Python-side lock around an
  interpreter (R9 makes the process lock the only one).
- No import of R, ryp, Julia or juliacall at registration or at import of
  `seamless_transformer.languages`.
- No fallback encoding when a backend cannot transport a value (R11). Raise.
- No change to `transformation_namespace.py`.
- No edit to the process-lock plan or to its in-flight files beyond the three
  this plan must touch.

## 11. Notes on ryp and juliacall

From source and documentation. None of it was run.

ryp:

- `r(R_code)`, `to_r(python_object, R_variable_name, *, format=None,
  rownames=None, colnames=None)`, `to_py(R_statement, *, format=None,
  index=None, squeeze=None)`. `to_py` takes an R statement, not only a name.
- The first call initialises R on the calling thread. It raises if R was
  already initialised in the process, for example by rpy2.
- R is found through the `R_HOME` environment variable, or else by running
  `R RHOME`.
- Installed with pip it brings neither R nor the R package `arrow`; installed
  with conda it brings both.

juliacall:

- The first import starts Julia, on the importing thread. Options are read
  from the environment at that moment: `PYTHON_JULIACALL_HANDLE_SIGNALS`
  (`yes` or `no`) and `PYTHON_JULIACALL_THREADS` (default: `JULIA_NUM_THREADS`,
  else 1).
- The first import also resolves a Julia project through `juliapkg`. It needs
  Julia 1.10.3 or later and pins `PythonCall` to its own version. This can
  download packages and take minutes. Do it once before running tests.
- A package is added to that project with
  `juliapkg.add("JSON", "682c06a0-de6a-54ab-a142-c8b1cf79cde6")`, signature
  `add(pkg, uuid=None, target=None, **kwargs)`. The UUID of
  `NPZ`, for the project the CLI tests use, is
  `15e1cf62-19b3-5cfa-8e77-841668bca605`. Both UUIDs were checked against the
  General registry on 2026-10-12.
- `juliacall.newmodule(name)` registers the module under `Main` for the life
  of the process. Use it once, for the runtime. Create per-run modules inside
  Julia with `Module(:SeamlessTF)`.
- `f._jl_call_nogil(*args)` calls a Julia function with the GIL released.
- juliacall registers an exit hook that stops Julia when Python exits.

## Appendix A — Starting points

These are starting points, not specifications. §3 rules where they differ.

### A.1 What the sketches established

- The user writes ordinary R or Julia. Pins are plain variables; the code
  assigns the output name. It contains no file loading, no file writing and no
  mention of Seamless.
- The output name comes from `__output__`. It is not hard-coded as `result`.
- R: run the code in `new.env(parent = globalenv())`, and read the output with
  `exists(..., inherits = FALSE)` and `get(..., inherits = FALSE)`.
- Julia: a module is the unit of isolation. Never evaluate changing code into
  one long-lived module; a new code version gets a new module.
- `RcppCNPy::npyLoad` defaults to double precision. An integer array needs
  `type = "integer"`, so the handler must read the dtype from the `.npy`
  header.
- `NPZ.jl` and `RcppCNPy` may write `.npy` bytes that differ from NumPy's for
  the same array. Never adopt a result file's checksum. Load the result and let
  Seamless serialise it, which is what returning the value from the handler
  does.
- An array on file is opened with `np.load(path, mmap_mode="c",
  allow_pickle=False)`: a copy-on-write mapping.
- An embedded interpreter isolates names, not the process. Loaded packages,
  options and explicit global assignments persist between transformations, and
  compiled Julia code is not reclaimed.

Where this plan departs from the sketches:

| Sketch | This plan |
|---|---|
| A Python lock around each embedded interpreter | The process lock (R9) |
| An `lru_cache` of compiled Julia modules in Python | A cache inside the interpreter (R6) |
| Its own `subprocess.run` per language | `execute_bash` (R10) |
| `elif language == "r"` in `run.py` | Generic handler dispatch (§3.2) |
| Its closing advice to drop juliacall | Both backends are kept (R5) |

### A.2 Julia runtime

Run on Julia 1.12.6 on 2026-10-12 with the block style, the `transform()`
style (long form with a docstring, a `where` clause and a keyword argument;
short form with a return type), a second call on a cached isolation, and a
missing result. It has not been run under juliacall.

```julia
module SeamlessRuntime

const ISOLATIONS = Dict{String,Module}()

function unwrap(ex)
    while ex isa Expr
        if ex.head === :macrocall && length(ex.args) >= 4 &&
           ex.args[1] isa GlobalRef && ex.args[1].name === Symbol("@doc")
            ex = ex.args[end]
        else
            break
        end
    end
    return ex
end

function callname(sig)
    while sig isa Expr && sig.head in (:where, :(::))
        sig = sig.args[1]
    end
    (sig isa Expr && sig.head === :call) ? sig.args[1] : nothing
end

function defines_transform(ex)
    ex = unwrap(ex)
    ex isa Expr || return false
    ex.head in (:function, :(=)) || return false
    return callname(ex.args[1]) === :transform
end

is_transform(code) = any(defines_transform, Meta.parseall(code).args)

function call_by_name(f, pins::Dict{String,Any})
    m = only(methods(f))
    positional = Base.method_argnames(m)[2:end]
    keywords = Base.kwarg_decl(m)
    args = Any[pins[String(n)] for n in positional]
    kwargs = Pair{Symbol,Any}[
        n => pins[String(n)] for n in keywords if haskey(pins, String(n))
    ]
    return f(args...; kwargs...)
end

function run(key::String, code::String, pins::Dict{String,Any}, output::String)
    if is_transform(code)
        mod = get!(ISOLATIONS, key) do
            m = Module(:SeamlessTF)
            Base.include_string(m, code, "transformer.jl")
            m
        end
        f = Base.invokelatest(getfield, mod, :transform)
        return Base.invokelatest(call_by_name, f, pins)
    else
        mod = Module(:SeamlessTF)
        for (name, value) in pins
            Core.eval(mod, :($(Symbol(name)) = $(QuoteNode(value))))
        end
        Base.include_string(mod, code, "transformer.jl")
        Base.invokelatest(isdefined, mod, Symbol(output)) ||
            error("Julia transformer did not define '$output'")
        return Base.invokelatest(getfield, mod, Symbol(output))
    end
end

end # module
```

- The `invokelatest` calls are required. The code is evaluated after `run` was
  compiled, so its definitions live in a later world than `run` itself.
- Still to add: turning each pin into a native value, and classifying and
  encoding the result (§3.4).

The CLI runner, from the sketches, not run:

```julia
using NPZ, JSON
include("runtime.jl")
pins = Dict{String,Any}(
    "a" => npzread("a"),
    "opts" => JSON.parsefile("opts"),
)
result = SeamlessRuntime.run("<key>", read("code.jl", String), pins, "result")
# then write RESULT as .npy, raw bytes or JSON
```

Command: `julia --startup-file=no runner.jl`.

Under juliacall, not run: define the same module once in `Main` behind an
`isdefined(Main, :SeamlessRuntime)` check, and call `SeamlessRuntime.run` from
the owner thread.

### A.3 R runtime

From the sketches. Not run: R was not installed.

```r
.seamless <- new.env()
.seamless$isolations <- new.env()

.seamless$is_transform <- function(code) {
    for (e in as.list(parse(text = code))) {
        if (is.call(e) && is.symbol(e[[1]]) &&
            as.character(e[[1]]) %in% c("<-", "=") &&
            identical(e[[2]], as.name("transform")) &&
            is.call(e[[3]]) && identical(e[[3]][[1]], as.name("function")))
            return(TRUE)
    }
    FALSE
}

.seamless$run <- function(key, code, pins, output_name) {
    if (.seamless$is_transform(code)) {
        iso <- .seamless$isolations[[key]]
        if (is.null(iso)) {
            iso <- new.env(parent = globalenv())
            eval(parse(text = code), envir = iso)
            .seamless$isolations[[key]] <- iso
        }
        do.call(get("transform", envir = iso), pins)
    } else {
        env <- list2env(pins, envir = new.env(parent = globalenv()))
        eval(parse(text = code), envir = env)
        if (!exists(output_name, envir = env, inherits = FALSE))
            stop(sprintf("R transformer did not define '%s'", output_name))
        get(output_name, envir = env, inherits = FALSE)
    }
}
```

The Rscript runner loads each pin and calls it:

```r
source("runtime.R")
pins <- list(
    a    = RcppCNPy::npyLoad("a", type = "numeric"),
    opts = jsonlite::fromJSON("opts"),
    name = sub("\n$", "", readChar("name", file.size("name"))),
    blob = readBin("blob", "raw", n = file.size("blob"))
)
result <- .seamless$run("<key>", readChar("code.R", file.size("code.R")),
                        pins, "result")
# then write RESULT as .npy, raw bytes or JSON
```

Command: `Rscript --vanilla runner.R`.

Under ryp, the sequence of the sketches with the names made unique per run:

```python
from ryp import r, to_r, to_py

tag = uuid.uuid4().hex
to_r(code, f".seamless_{tag}_code")
to_r(array, f".seamless_{tag}_pin_a")          # an array pin
to_r(json_text, f".seamless_{tag}_pin_opts")   # a JSON-typed pin, as text
try:
    r(...)   # one call: build the pin list, run, encode into .seamless_{tag}_out
    result = to_py(f".seamless_{tag}_out", format="numpy", squeeze=False)
finally:
    r(...)   # remove every name that starts with .seamless_{tag}_
```

## Appendix B — The GIL probe

The measurement of §2.1. Run it again after the process lock has landed; the
outcome should not change.

```python
import time
import seamless
from seamless.transformer import direct, spawn

if __name__ == "__main__":
    spawn(1)

    @direct
    def body(seconds, hold_gil):
        import ctypes, os, time
        # PyDLL keeps the GIL during the C call, as juliacall does.
        # CDLL releases it.
        lib = (ctypes.PyDLL if hold_gil else ctypes.CDLL)(None)
        t0 = time.time()
        lib.sleep(int(seconds))
        return (os.getpid(), round(time.time() - t0, 2))

    for hold_gil in (False, True):
        for seconds in (1, 5):
            try:
                # The added fraction keeps the four calls distinct in the cache.
                print(hold_gil, seconds, body(seconds + 0.001 * hold_gil, hold_gil))
            except BaseException as exc:
                print(hold_gil, seconds, "EXC", type(exc).__name__)
    seamless.close()
```

Result on 2026-10-10: the three cases other than `(True, 5)` returned after the
expected time from one worker pid. `(True, 5)` logged "Restarting worker
worker-1 (ping timeout)" three times and raised `TransformationError`.
