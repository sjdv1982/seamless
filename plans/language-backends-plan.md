# Language backends: follow-up plan

Written 2026-10-12, revised 2026-10-13 after three more rounds of rulings by
the author. Paths are relative to `/home/agent/seamless1`.

## Current status (2026-10-14)

The `deepfolder` input pin rule changed after this plan: outside bash it now
uses the same dict-of-checksum-objects form as `deepcell`, and bash refuses
both pin types. Earlier path and bash-directory rulings below are historical;
the current contract is in
[`contracts/deep-celltypes.md`](../docs/agent/contracts/deep-celltypes.md).

This plan follows two plans and cuts across both:

- [bash-docker-conda-transformers-plan.md](bash-docker-conda-transformers-plan.md),
  "the bash plan", implemented on the branch `bash-docker-support`;
- [julia-r-support.md](julia-r-support.md), "the handler plan", implemented on
  the branch `julia-r-support`.

It starts with the merge of both branches onto `main` (§3). After that it
generalizes one idea of the handler plan to every language. The code of a
transformation is run by a **language backend**. A language backend is either
a **CLI backend** or an **in-memory backend**, and what it does with an
`environment` follows from which of the two it is.

- "Language backend" is what the handler plan calls a backend. It is not an
  execution backend (`process`, `spawn`, `remote`).
- A ruling of a parent plan is cited with its plan: "bash D9", "handler R12".
- Line numbers are those of the branch tips on 2026-10-12.

Whoever implements this plan should read §10 first.

## 0. Summary

The languages and their backends after this plan:

| Language | CLI backend | In-memory backend | `tf.metavars.BACKEND` |
|---|---|---|---|
| `bash` | the only one | none | none |
| `python` | **new**: a Python process per run | today's execution | `"mem"` (default), `"cli"` |
| compiled | none | the only one | none |
| `r` | an `Rscript` process per run | R embedded through `ryp` | `"cli"` (default), `"mem"` |
| `julia` | a `julia` process per run | Julia embedded through `juliacall` | `"cli"` (default), `"mem"` |

What a backend does with the transformer's `environment`:

| The environment has | CLI backend | In-memory backend |
|---|---|---|
| nothing | runs | runs |
| a conda environment | enters it, as bash does (`conda run`) | runs only when its process is already in exactly that environment; fails otherwise |
| a Docker image | runs in a container, as bash does | fails |
| both | refused at dispatch (bash D2, G14) | refused at dispatch (bash D2, G14) |

### What is ruled

By the author, on 2026-10-12.

- **G1 — Comparing conda environments.** The suggestion of the handler plan,
  §3.6, is accepted. A specification that contains `/` is a path and is
  compared with `CONDA_PREFIX`. Any other specification is a name and is
  compared with `CONDA_DEFAULT_ENV`.
- **G2 — The double backend idea is generalized.** This is the essence of the
  plan.
- **G3 — The in-memory rule is generic.** Handler R12, with G1, holds for
  every in-memory backend: it cannot enter an environment, it raises for a
  Docker specification, and for a conda specification it runs only when its
  process is already in exactly that environment.
- **G4 — Compiled transformers and today's Python transformers are in-memory
  backends.**
- **G5 — Python transformers gain a CLI backend.**
- **G6 — A CLI backend wraps conda and Docker specifications properly.** This
  holds for the bash, R, Julia and Python CLI backends alike.
- **G7 — The Python CLI backend does not refuse properly mixed values.** A
  properly mixed value is a `mixed` value that does not reduce to plain or to
  binary. It is written to a `.mixed` file and deserialized in a helper file
  that uses seamless-core. seamless-core must then be installed where the code
  runs. This is not checked earlier.
- **G8 — The backend names are `"mem"` and `"cli"`, in every language.**
  The tool names of the handler branch (`"Rscript"`, `"ryp"`, `"julia"`,
  `"juliacall"`) go. The author first ruled `"in-memory"` and renamed it to
  `"mem"` on 2026-10-13. "In-memory backend" stays the prose term for the
  kind of backend whose value is `"mem"`.
- **G9 — Every backend rule is triggered only when the transformation runs.**
  A cached result does not know which backend produced it. All rules about
  conda, Docker, `which` and properly mixed pins apply at run time and at no
  other moment.
- **G10 — Deep celltypes under a CLI backend are harmonized with the current
  bash transformer.** Folders are supported, as input and as output, because
  they are meant to be materialized. The author recalls that a deepfolder is
  allowed as input only when every member is found in a buffer read
  directory, and is disallowed as output. §1.6 gives what the code does
  today. It differs on the first point, and G13 rules that point. G17
  replaces the harmonization for R, Julia and Python.
- **G11 — Drivers work normally under the Python CLI backend** (2026-10-13;
  the author's words were "I think they should"). They work as they do for
  bash transformations, which today is under Dask only. §1.7 gives the facts
  and §4.5 what follows.
- **G12 — `seamless-run` declares a result that has result targets as
  `folder`**, not as `deepfolder` (2026-10-13).
- **G13 — A deepfolder input pin never resolves its members through the
  hashserver** (2026-10-13). The author recalls that such a pin carried a
  `filesystem` entry with `optional` false, and a folder pin one with
  `optional` true. §1.8 confirms this for the legacy code and shows that the
  current code lost it.
- **G14 — A specification that could never work is refused at dispatch
  time** (2026-10-13): conda together with Docker, and "similar nonsense
  keys". Dispatch is the moment a transformation without a recorded result is
  handed to an execution backend. It is not checked when the specification is
  set, nor when the Transformation is built.
- **G15 — A deepcell input pin is forbidden in a bash transformer**
  (2026-10-13). It is refused when the pin's celltype is set, as a
  `deepfolder` result is today, and again before launch for a transformation
  that arrives by another road. The author accepted this plan's suggestion
  for the moment.
- **G16 — A deepcell result of a bash transformer works exactly like a folder
  result, and each file in the `RESULT` directory is verified to parse as
  `mixed`** (2026-10-13). §4.7 gives what changes against today.
- **G17 — Deep input pins follow a matrix with one column for bash and one
  for every other backend, CLI and in-memory alike** (2026-10-13). Outside
  bash, a folder is a dict of contents, a deepfolder is a dict of paths, and a
  deepcell is a dict of checksums that the code resolves itself. §4.6 has the
  matrix. The author confirmed it as ruled, with a fourth row (G20). It
  replaces the
  part of G10 that made the R, Julia and Python CLI backends do with a deep
  celltype what bash does. Folders stay supported as input and as output
  under every CLI backend.
- **G18 — The paths of a deepfolder pin have the format of the hashserver's
  files** (2026-10-13; the author's words were "I would expect"): `<checksum>`,
  `<checksum>.zst` or `<checksum>.gz`. Outside bash, the code gets the paths
  of the buffer files as they are stored. Nothing is made for it.
- **G19 — No Seamless configuration is exported to a job outside Dask**
  (2026-10-13). A deepcell pin is for key filtering, for which the checksums
  are enough, and for big drivers, which belong on Dask. Code in a CLI job
  can therefore resolve a member under `remote: daskserver` only.
- **G20 — The matrix is ruled with four rows** (2026-10-13). The fourth is the
  cast `deepfolder → plain`. A row "deepcell cast to mixed" was considered and
  removed. No conversion between deep celltypes is added.
- **G21 — Compiled transformers stay out of the matrix for the time being**
  (2026-10-13). The obstacle is that a compiled pin cannot be `plain`. Their
  deep pins stay refused, as today.
- **G22 — In bash, a folder or deepfolder pin is a new directory of symlinks
  and resolved buffers** (2026-10-13): a symlink for each member that is on
  disk, and a resolved buffer for each folder member that is not. **A
  deepfolder member is never transcoded.** Its consumer reads the compression
  from the suffix of the path. The author asks for extra care, with tests,
  that this works in a container. §4.7 has the rule.
- **G23 — A folder member that is stored compressed is transcoded where the
  pin's name asks for another form** (2026-10-13). This is what
  `compression.md` says today, and it stays the rule for a folder pin.
- **G24 — `write_bash_job` is refactored so that the code that writes a
  folder pin is shared with the CLI backends** (2026-10-13).
- **G25 — Outside bash, a transformation with a folder or deepcell result
  returns a dict that contains checksums or values** (2026-10-13). A value
  that is a valid 64-hex string was then ambiguous (Q10). G29 rules it.
- **G26 — A `BACKEND` value other than `"mem"` and `"cli"` is refused
  when it is assigned** (2026-10-13), in every language that has the setting.
  On the handler branch a wrong value fails only when the handler runs
  (§1.5). That check stays, for a value that arrives in a transformation
  dict.
- **G27 — A buffer file that the job's container cannot read counts as not
  on disk** (2026-10-13). A buffer file can be a symlink to a file outside
  its read-buffer directory. This is detected where the transformation will
  run in a container that cannot reach the link's target. The member is then
  treated as one that is not on disk: a deepfolder pin fails, and a folder
  member is copied into the job directory. §4.7 has the rule.
- **G28 — A setting that lets a Python or compiled pin arrive as a file is
  out of this plan** (2026-10-13). This answers Q6.
- **G29 — A member of a returned dict is a value unless it is a checksum
  object** (2026-10-13). This answers Q10, for every language. A string of
  64 hex characters is a value like any other string. In Python the checksum
  object is a `seamless.Checksum`. No pickle is used to carry one.
- **G30 — Checksum classes get first-class support in every backend**
  (2026-10-13). The R and the Julia runtime each get a checksum class. A
  deepcell pin is a dict of checksum objects in every language and under
  every backend but bash, which replaces P18. In a Python CLI job,
  seamless-core is needed whenever a checksum crosses into the job.
- **G31 — Checksums and values cross between the code and the host in a wire
  format** (2026-10-13). The author gave its outline: an index with one entry
  for each member, in which a checksum is the dict `{"__checksum__": …}` and a
  value is the name of a file, and one JSON file for many small values. A
  helper A on the side of the code exists for each language, and one helper B
  on the host is shared. The author accepted three changes of this plan: the
  members get a key of their own, a file entry declares its encoding, and the
  in-memory backends of R and Julia use the helpers too. The author asked for
  a rich format and left its design to this plan. §4.9 has it.

### Proposed by this plan and accepted

By the author, on 2026-10-12 and 2026-10-13. §8 gives the reasons.

| | Accepted |
|---|---|
| P1 | Python's backend is selected with `tf.metavars.BACKEND`, as amended by G8. It is stored in `meta["metavars"]`, and only when it is set |
| P2 | Backend parity (handler R11) holds for Python too |
| P3 | The in-memory rule is checked when the transformation runs, and only then. The check at build time goes. Now part of G9 |
| P4 | `which` is looked up where the code runs: in the script for a CLI backend, on the `PATH` of the process for an in-memory backend |
| P5 | Two shared functions carry the two rules, and they are **public**: `check_in_memory_environment` and `execute_cli`. The author answered "public" to the question whether they are, and confirmed on 2026-10-13 that this accepts the two functions. Their names and signatures are this plan's, and the author reads them on the contract page in Phase 1 |
| P6 | The Python CLI command is `python3 -u runner.py` |
| P7 | A properly mixed *result* returns the way a properly mixed pin arrives: through the helper, with seamless-core |
| P8 | The first Python CLI backend refuses modules and globals. Its deep-celltype half is replaced by G17 |
| P9 | A new contract page, `language-backends.md`, owns the two kinds, the environment rule and the Python CLI backend |
| P10 | The container tests build one image per language in a session fixture |
| P11 | The bash branch is merged first, then the handler branch. The parents' contract pages are committed once before this plan edits them |
| P13 | Before the code runs, the Python runner configures its process from `SEAMLESS_REMOTE_CLIENTS`, as `seamless-run` does for itself. G11 needs this under Dask |
| P15 | The rule for a deepfolder pin is enforced where the pin is written into a job directory, by the pin's celltype. `__format__` is not changed, and `optional` is not restored, so no transformation gets a new checksum from it |
| P16 | A `seamless-run` directory argument becomes a `folder` pin. Its transformation checksum changes |
| P17 | Deep results follow the split of G17. Bash writes a `RESULT` directory. Every other backend returns a dict (G25) |
| P18 | Under a CLI backend, a deepcell pin is a dict of 64-hex strings, in Python as in R and Julia. In-memory Python keeps `Checksum` objects. `Checksum(v)` accepts both. **Replaced by G30**: the pin holds checksum objects under every backend |
| P19 | G27 holds for an ordinary pin that is linked from a read-buffer directory too. Where its buffer file is a link that the container cannot follow, the file is copied into the job directory |
| P20 | What a container can reach is judged by what the wrapper itself binds: the job directory and the read-buffer directories. A bind that an operator adds with `SEAMLESS_CONTAINER_ARGS` is not seen |

**Readings of this plan that the author confirmed** on 2026-10-13:

- P5 accepts the two functions, with names and signatures still to be read
  in Phase 1.
- P15 is accepted whole, the part about `__format__` included.
- G14 covers `seamless-run` (C11).
- Handler R9 stays a rule of embedded R and Julia interpreters (§2).
- A deepcell result of a bash transformer keeps its files' bytes, so a member
  can be a buffer that Seamless would not write (§4.7).
- A compression suffix in a deepfolder pin's own name asks for nothing
  (§4.7).

### What follows from the rulings

These are consequences, not new decisions. Each names what it replaces.

- **C1 — Bash D9 is superseded.** D9 made `docker` or `conda_environment` on a
  Python or compiled transformer an error. Under G3 and G4 a conda
  specification on an in-memory backend is a requirement on the process that
  runs it, and only a Docker specification always fails there. Under the
  Python CLI backend both are wrapped (G5, G6).
- **C2 — The open decision of the handler plan, §8, is closed.** An R or Julia
  CLI backend with a Docker specification runs in a container (G6).
- **C3 — "How to compare is not ruled" in the handler plan, §3.6, is closed**
  (G1). Both handlers on `julia-r-support` already compare this way.
- **C4 — Handler R12 stops being a rule of two handlers.** It becomes one rule
  with one implementation, used by Python, compiled, R and Julia.
- **C5 — The first rule of the environments contract goes.** "An environment
  applies to bash transformers only" becomes the table above. The non-goal
  "running Python transformers in a container or in another conda environment"
  goes too. For compiled transformers it stays.
- **C6 — Record probes stay exempt.** A probe is a Python in-memory
  transformation that carries its target's `__env__` (bash plan, §4.12). It
  runs on the host whatever that environment says.
- **C7 — The handler branch is renamed** (G8): the defaults in the two
  registrations, the values the handlers compare, their messages, the test
  parameters and `handler-languages.md`. The old names are not kept as
  aliases: the branch has no remote and was never released.
- **C8 — The R and Julia handlers stop refusing deep celltypes** (G17). Under
  both of their backends, a deep pin follows the second column of the matrix.
- **C9 — G12, G13, G15 and G16 change the bash transformer itself**, and with
  it `seamless-run`, which was out of scope until now (§4.7).
- **C12 — G17 changes what in-memory Python code receives today** (§4.6). A
  deepfolder pin is a dict of `Checksum` objects now, and becomes a dict of
  paths. A folder pin can be a path now, and becomes a dict of contents
  always.
- **C13 — G22 changes what `compression.md` says of a deepfolder pin.** That
  page lets the suffix in the pin's name decide the form of every leaf, and
  transcodes a stored form that does not fit. A deepfolder entry now keeps its
  stored form, with the suffix after the key. G22 also ends the lookup of a
  directory that is named by the index's checksum (§1.8).
- **C10 — G12 changes transformation checksums.** `__output__` is a
  load-bearing key (`transformation_utils.py`), so every `seamless-run`
  command with result targets gets a new checksum, and its cached result is
  computed once more. P16 does the same for commands with a directory
  argument, through `__format__`.
- **C11 — G14 moves the two checks of bash D2 and D5.** Today conda together
  with Docker fails when the Transformation is built
  (`Environment._to_lowlevel`), and an unknown key of the image spec fails
  when the spec is set (`set_docker`). Both move to dispatch. G14 covers
  `seamless-run` too, which today refuses `--docker` with `--conda` while it
  parses its arguments. The check before launch on the executing host stays,
  for a transformation that reaches it by another road.
- **C14 — G26 adds a check to the handler builders.** On `julia-r-support`,
  assigning a metavar checks its name only (`HandlerMetaVars.__setattr__`).
  The value of `BACKEND` is now checked there too, as it is for Python
  (§4.5).
- **C15 — G27 removes a limit of this plan.** Until now the plan listed a
  buffer file that is a symlink out of its read-buffer directory as
  unreadable in a container. A folder pin now works there, and a deepfolder
  pin fails before the job starts, with a message that says why.
- **C16 — G29 changes what in-memory Python does today** (§4.6). A returned
  string of 64 hex characters is read as a checksum now
  (`pack_deep_structure`). It becomes a value in a deepcell result and a
  `TypeError` in a folder result. Code that returns such strings as checksums
  has to wrap them in `Checksum`. `deep-celltypes.md`, *The output side*,
  states the old rule.
- **C17 — G30 makes a `checksum` pin work in R and Julia.** Today it fails
  under all four backends (§1.9).
- **C18 — G30 adds a requirement to the Python CLI backend.** G7 needs
  seamless-core in the job for a properly mixed value. A deepcell pin and a
  `checksum` pin need it too.
- **C19 — Two changes are breaks that the release notes must lead with**
  (2026-10-13). C10 (G12, P16) is the larger: every `seamless-run` command
  with a directory argument or result targets gets a new transformation
  checksum, because a `deepfolder` became a `folder`. C16 (G29) is the one
  that fails nowhere: a naked 64-hex string is no longer wrapped as a
  checksum. §7, *Release notes*, has the entries.

### Still proposed, not ruled

These are this plan's choices inside G30 and G31, which the author left to
it. The plan proceeds on them.

| | Proposal | § |
|---|---|---|
| P21 | Every result of a Python CLI job travels in the wire format, deep or not. An ordinary result of R and Julia keeps the JSON text of today | 4.9 |
| P22 | The names of the checksum classes: `seamless_checksum()` and `is_seamless_checksum()` in R, `Checksum` in Julia. The author reads them on the contract page in Phase 1 | 4.6 |
| P23 | The wire format is not a contract. No contract page describes it, and a handler of a third party does not use it | 4.9 |

P12 is withdrawn: G17 replaces it. P14 is replaced by G18, G22 and G23.

### Open

Nothing. Q1 to Q10 are answered: P5, G11, G13, G17, G14, G28, G15, G19 with
G30, G23, and G29.

Two things reach the author later, by design: the names and signatures of
the public functions, on the contract page of Phase 1 (P5, P22), and the
table of result types after Phase 5.

## 1. Starting state

Read and run on 2026-10-12. §1.1, §1.2 and the line numbers of §1.3 and §1.4
were checked again on 2026-10-13, and §1.1 and §1.2 once more after the last
commits of that day. Re-check before starting.

### 1.1 Branches

| Repository | `main` | `bash-docker-support` | `julia-r-support` | Checked out |
|---|---|---|---|---|
| `seamless-transformer` | `6b034d4` | `e2ba5f7`, 7 commits ahead | `02969fa`, 6 commits ahead | `bash-docker-support` |
| `seamless-workflow` | `38374b1` | `6b1113f`, 2 commits ahead (one test file) | `6112096`, 2 commits ahead (`context.py`, one test file) | `bash-docker-support` |
| `seamless-share` | `1be3f33` | none | `98774d0`, 1 commit ahead (`why_not/diff.py`) | `julia-r-support` |
| `seamless` | `ac496fce` | none | none | `main` |

- In the three code repositories `main` equals `origin/main`, and every plan
  branch forks from that same commit. No plan branch has a remote.
- No other repository has a branch for either plan.
- The process-lock plan is on `main`, the nesting signal included
  (`e4d5834`, `9b24df9`).
- **`bash-docker-support` is finished.** The author confirmed it on
  2026-10-13. Phase 6 of the bash plan is committed: the code (`2666294`),
  `README.md` (`e2ba5f7`, which changes no other file) and its pages in
  `seamless` (`765e0646`).
- **The contract pages of both parents are committed** in `seamless`
  (`e1bf5777`), together with `plans/julia-r-support.md`. The only
  uncommitted file there is this plan, which is untracked. The working trees
  of the three code repositories are clean.

### 1.2 The merge is textually clean

Checked with `git merge-tree --write-tree bash-docker-support julia-r-support`,
which touches no working tree and no ref.

- `seamless-transformer`: no conflict, also against the tip of 2026-10-13
  (`e2ba5f7`).
- `seamless-workflow`: no conflict.
- Files changed on both branches: `seamless_transformer/run.py` and
  `transformer_class.py`. The hunks do not touch.

### 1.3 What a clean merge leaves wrong

Read in the source of both branch tips. None of it was run.

- **S1 — An R or Julia transformation with an environment never reaches its
  handler.** The bash branch refuses every transformation whose language is
  not `bash` and whose environment has `docker` or `conda_environment`
  ([run.py:153-160](../../seamless-transformer/seamless_transformer/run.py#L153-L160)).
  The handler lookup of the handler branch comes after that check. This
  contradicts `handler-languages.md`, *Environments*.
- **S2 — With S1 lifted and nothing else changed, a Docker image is ignored.**
  Both handlers call
  `execute_bash(command, pins, environment.get("conda_environment", ""), …)`
  with the six positional arguments (`julia.py:619`, `r.py:406` on
  `julia-r-support`). They pass no `docker_`, so the interpreter would run on
  the host. They also pass no `which_`, `tf_checksum_` or `should_abort_`:
  - the cleanup is registered under no checksum, so the in-process cancel
    paths, which call `run_cleanups(tf_checksum)`, do not find it;
  - a container would carry no `seamless.tf` label.
- **S3 — `which` is looked up on the host for every language but bash**
  ([run.py:171-184](../../seamless-transformer/seamless_transformer/run.py#L171-L184)),
  also for a CLI backend that then enters a conda environment.
- **S4 — No committed test sees S1 to S3.** The environment tests of the
  handler branch call the handler function directly, never through a
  Transformer (`tests/test_julia_handler.py:282-309`,
  `tests/test_r_handler.py:181-202`). No test runs a CLI backend in a conda
  environment. Both test sets are therefore expected to pass right after the
  merge.

### 1.4 Where bash D9 is written down

C1 removes each of these.

| Where | What |
|---|---|
| `seamless_transformer/run.py:153-160` | the refusal before the body |
| `environment.py`, `Environment._validate_bash_only` | the refusal at build time, called from `TransformerCore._freeze` for Python and from `CompiledMixin._freeze` |
| `tests/test_bash_launch.py`, `test_non_bash_environment_fails_before_body` | expects "bash transformers only" for Python and compiled, with `docker` and with `conda_environment` |
| `tests/test_environment_faces.py`, `test_nonbash_environment_is_refused_when_frozen` | expects the refusal at build time |
| `docs/agent/contracts/environments.md` | "An environment applies to bash transformers only"; "Handler languages are a separate case"; the `which` rule; the first failure class; the first non-goal |
| `docs/agent/contracts/execution-backends.md` | "Python and compiled transformations are never wrapped … is an error" |
| `docs/agent/contracts/compiled-transformers.md`, *Environment* | "fails when its Transformation is built" |
| `docs/agent/contracts/transformers.md` | "for the script of a bash transformer" |

### 1.5 Other facts this plan relies on

Read in the source of `bash-docker-support` unless marked **measured**.

- **`execute_bash`** has the positional signature of `main`:
  `(bashcode, pins_, conda_environment_, PINS, FILESYSTEM, OUTPUTPIN)`. The
  bash branch adds keyword-only `which_`, `docker_`, `container_runtime_`,
  `tf_checksum_` and `should_abort_`. Given a `docker_` and no runtime, it
  selects the runtime itself.
- **The nesting signal** is offered to the child only without a container
  (`execute_bash`, `notify_holder`). A nested submission through the Python
  API writes to it too: `Transformation.start`, `.task`, `.computation` and
  `._compute` call `drop_for_nested_work`.
- **`write_bash_job`** writes a `Buffer` or `bytes` pin raw, writes a pin
  named `META__FILE__<name>` as the file `<name>`, and raises `TypeError` for
  a value whose storage is mixed.
- **`execute_bash` reads a `RESULT` file** as `.npy`, then JSON, then text.
  Bytes that are none of these come back as a `uint8` array. It does not know
  the Seamless-mixed format.
- **The cleanup registry** is keyed by the checksum that `execute_bash`
  receives. `run.py` passes `checksum_hex`, which is the `__code_checksum__`
  of the dict when there is one, and the `tf_checksum` otherwise. Only Python
  transformations carry `__code_checksum__`
  (`pretransformation.py`, `_prepare_code`).
- **Python pins reach the code as `Buffer.get_value(celltype)`**
  (`build_transformation_namespace_sync`; `seamless-core`, `_parse_buffer`):
  - `text`, `python`, `ipython`, `yaml`: the text without its final newlines;
  - `plain`, `str`, `int`, `float`, `bool`: parsed with `orjson`. A comment in
    `_parse_scalar` says that large unquoted JSON integers become floats;
  - `binary`: an array. `mixed`: by what the buffer is;
  - `bytes`: a `seamless.Buffer`, not `bytes` (**measured**);
  - `checksum`: a `Checksum` object.
- **A value is properly mixed exactly when its buffer starts with
  `\x94SEAMLESS-MIXED`.** `seamless.util.mixed.io.serialize` writes that
  format for every storage other than `pure-plain` and `pure-binary`, and
  `deserialize` reads it. Both are in seamless-core, which depends on NumPy,
  orjson, PyYAML and zstandard.
- **How Seamless serializes some results under `mixed`** (**measured**):

  | Value | Buffer |
  |---|---|
  | `np.float64(1.5)`, `np.int64(3)` | plain: `1.5`, `3` |
  | `(1, 2)` | plain: a JSON list |
  | `{1: 2}` | plain: `{"1": 2}` |
  | `float("nan")` | an `.npy` buffer |
  | `{"a": np.arange(3)}`, a list of arrays | Seamless-mixed |
  | a `set` | `TypeError` |

  The standard `json.dumps` accepts `np.float64` and refuses `np.int64`.
- **Python transformers have modules and globals.** They travel as pins of
  celltype `plain` and subcelltype `module`, are built with
  `build_all_modules`, and the globals are copied into the namespace
  (`run.py`, `_inject_main_globals`).
- **Metavars exist for two kinds of builder today**, both under
  `meta["metavars"]`: the output maxima of compiled transformers
  (`compiled_transformer.py`, `MetaVars`) and the handler settings
  (`HandlerMetaVars` on `julia-r-support`). A Python builder has none.
- **Backend names on `julia-r-support`**: `"Rscript"` (default) and `"ryp"`;
  `"julia"` (default) and `"juliacall"`. Each handler raises for any other
  value when it runs. Assigning a metavar checks only that the handler
  declares its name (`HandlerMetaVars.__setattr__`).
- **Conda environments on this machine**: `seamless1` has `python`, `python3`
  and `Rscript`. The base environment has Python 3.13 with NumPy and a stale
  Seamless. docker and podman hold `ubuntu:22.04` and `alpine:3.20`.

### 1.6 Deep celltypes in the bash transformer today

This is what G10 harmonized with, and what G13 and G15 to G17 change. Read in
`pretransformation.py`,
`build_transformation_namespace_sync`, `write_bash_job`, `execute_bash` and
`run.py`. Rows marked * were also run on 2026-10-12, by calling `execute_bash`
directly.

For a bash Transformer, on the Python face and in a Context:

| Celltype | As a pin | As the result |
|---|---|---|
| `folder` | A directory in the job directory. It is a link when a directory named by the index checksum exists in a read-buffer directory. Otherwise the host resolves every member and writes it | `RESULT` is a directory, and each file in it is a member, as bytes * |
| `deepfolder` | A directory, likewise. It is a link when the index's directory exists in a read-buffer directory. Otherwise every member is resolved, **from any buffer source**, and written. A member that cannot be resolved is a `CacheMissError` * | Refused when the celltype is set: `tf.celltypes.result = "deepfolder"` raises `TypeError` |
| `deepcell` | Not materialized. The launch fails with a `TypeError` from `write_bash_job` * | `RESULT` is a directory, and each file is read as `.npy`, JSON or text and becomes a member * |

- **`folder` and `deepfolder` pins carry `{"filesystem": {"mode":
  "directory"}}` in `__format__`, for every language**
  (`direct_transformer_to_pretransformation`). A `deepcell` pin carries
  nothing.
- **The pin variable** is the directory's name in the job directory, or the
  path in the read-buffer directory when the pin is a link.
- **An empty `RESULT` directory is a failure.**
- **Deepcell and folder through a real `Transformer("bash")`**, run on
  2026-10-13:
  - A deepcell pin is accepted when its celltype is set, and the
    Transformation builds. It fails when it runs, with
    `TypeError: <class 'seamless.Checksum'>`. No case works.
  - A deepcell result works. Each file of the `RESULT` directory is parsed
    (`.npy`, then JSON, then text) and serialized again as a `mixed` member.
    A member is therefore not the file's bytes: the file `hello` becomes the
    buffer `"hello"\n`. A `folder` result of the same script keeps each
    file's bytes.
  - A `RESULT` that is one file holding a JSON dict is accepted as a deepcell
    result too, with one member per key. A `RESULT` that is a text file
    fails with "A deep structure must be a flat dict", for `deepcell` and for
    `folder`.
  - The same index, with the pin declared `deepfolder` or `folder`, is
    materialized as a directory. The script sees each member's buffer, which
    is `"hello"\n` for a string member.
  - The same index, with the pin declared `plain`, is one JSON file of keys
    and checksums. Python code gets a dict of 64-hex strings, not of
    `Checksum` objects.
  - No test gives a bash transformer a deepcell pin or a deepcell result, and
    no contract page mentions either.
- **Legacy** (read): a deepcell pin of a bash transformer was the index
  itself, as a file, with `{"mode": "file", "optional": False}`. The script
  got a JSON file of keys and checksums, and only when that file was on
  disk. A deepcell result was read as it is today.
- **The same lookup changes what Python code receives.** For a `folder` or
  `deepfolder` pin of a Python transformer, the code gets the path, as a
  string, when the index's directory exists in a read-buffer directory of the
  executing process. Otherwise it gets a dict: of contents as `bytes` for
  `folder`, of `Checksum` objects for `deepfolder` and `deepcell`
  (`deep-celltypes.md`, *How deep values reach a transformer*, gives only the
  dict).
- **The R and Julia handlers refuse `deepcell`, `deepfolder` and `folder`**,
  as pins and as the result, under both backends.
- **`seamless-run` differs from the builders**
  (`cmd/bash_transformation.py:117`, `:130-133`). A directory argument is a
  pin with the `deepfolder` directory format and `"optional": True`. With
  result targets, the result is declared `deepfolder`. So "deepfolder is
  disallowed as output" holds for the builders and not for `seamless-run`.
  G12 changes the result, and P16 does the same for the argument.

### 1.8 How `filesystem` works today

Read in the source on 2026-10-13: the current code, and the legacy code
(`/home/agent/legacy-seamless`, v0.14) for comparison.

**What it is.** A per-pin entry in `__format__`:
`{"filesystem": {"mode": "file" | "directory", "optional": bool}}`, with the
pin's `celltype` beside it. `__format__` is a load-bearing key, so the entry
is part of the transformation checksum (`transformation_utils.py`).

**Who writes it.**

| Writer | Pins | Entry |
|---|---|---|
| the builders, for every language (`direct_transformer_to_pretransformation`) | `folder`, `deepfolder` | `{"mode": "directory"}`, with no `optional` |
| the same, on `julia-r-support`, for handler languages | `mixed`, `plain`, `text`, `bytes`, `binary` | `{"mode": "file", "optional": True}` |
| `seamless-run` (`cmd/bash_transformation.py`) | a file argument, which is a `bytes` pin | `{"mode": "file", "optional": True}` |
| | a directory argument, which is a `mixed` pin with `"celltype": "deepfolder"` in the format | `{"mode": "directory", "optional": True}` |

Nothing else writes one, and a builder has no setting for it. A Python or
compiled transformer cannot ask for an ordinary pin as a file.

**What the executing process does**
(`build_transformation_namespace_sync`), the same for every language:

1. It looks for the pin's checksum in its read-buffer directories. These are
   the buffer directories that the process can read as files: that of a
   hashserver it launched locally, and that of an extern client that names a
   directory (`buffer_remote.activate`). No server is asked.
   - mode `file`: a file `<dir>/<checksum>` or
     `<dir>/<first two hex digits>/<checksum>`, also with a compression
     suffix;
   - mode `directory`: a directory at those same paths.
2. **Found:** the pin's value is the path. Nothing is read, and
   `FILESYSTEM[pin]["filesystem"]` is true.
3. **Not found:** `FILESYSTEM[pin]["filesystem"]` is false.
   - mode `file` and not `optional`: `CacheMissError`, "could not find file";
   - every other case: the pin is resolved as a value, like a pin without the
     entry. **`optional` is not read for mode `directory`.**

**What happens next.**

- **In a bash job** (`write_bash_job`): a found pin is linked into the job
  directory. A directory pin that was not found is written there. For a
  `folder` pin the host has resolved every member already. For a
  `deepfolder` pin, `write_to_directory(deep=True)` resolves each member with
  `Checksum.resolve()`, which asks the read-buffer directories and then the
  buffer read servers, the hashserver among them
  (`buffer_remote._get_buffer`).
- **In any other language** the code receives what step 2 or 3 gave: the path
  as a string, or the value. Only `folder` and `deepfolder` pins, and the
  five celltypes of a handler language, can be a path. A `deepfolder` pin
  that was not found is a dict of `Checksum` objects, and nothing is
  resolved.

**Nothing stores a deep folder as a directory.** The hashserver stores each
buffer as one file. The directory lookup of step 1 therefore finds something
only where a directory was put there by other means.

**What the legacy code did.**

| | Legacy | Now |
|---|---|---|
| `deepfolder` pin, Python and bash | `{"mode": "directory", "optional": False}` | `{"mode": "directory"}` |
| `folder` pin, Python and bash | `{"mode": "directory", "optional": True}` | `{"mode": "directory"}` |
| `bytes` pin, bash | `{"mode": "file", "optional": True}` | no entry |
| `deepcell` pin, bash | `{"mode": "file", "optional": False}` | no entry |
| a pin that is not found and not `optional` | `CacheMissError`, for both modes | for mode `file` only |
| where a deep folder is looked for | `<read folder>/deployed/<checksum>` (`buffer_remote.get_directory`) | `<read folder>/<checksum>` |
| a bash directory pin that was not found | written from its values, which only an `optional` pin could reach | `deepfolder`: every member resolved, from any source |

- **The author's memory is the legacy rule.** In the port, the builders
  stopped writing `optional` for directories, the reader stopped reading it
  for directories, and the bash launch gained a path that resolves the
  members of a deepfolder.
- `seamless-run` wrote the same two entries in the legacy code as it does
  now.

**Hard links, symlinks and compression** (read on 2026-10-13):

- **A buffer file can be a hard link of the user's own file.**
  `seamless-upload --hardlink` links each source file into the buffer
  directory under its checksum, and a compressed source keeps `.gz` or `.zst`
  (`cmd/register.py`). `seamless-download --hardlink` links the other way.
  The same code has a symlink mode, in which the buffer file is a symlink to
  the source file.
- **A job never gets a hard link.** A pin that is found in a read-buffer
  directory becomes a symlink in the job directory
  ([execute_bash.py:198](../../seamless-transformer/seamless_transformer/execute_bash.py#L198)).
- **`compression.md` has the rule for a bash pin.** A stored form that fits
  the suffix in the pin's name is linked. Any other is transcoded and
  written. For a directory pin, the suffix in the pin's name holds for every
  leaf: the pin `mydata.zst` is the directory `mydata` with leaves such as
  `file.npy.zst`.
- **Outside bash no builder can ask for a stored form.** The page calls the
  Python face of this deferred.

### 1.7 Drivers and nested work from a job, today

This is what G11 compares with. The author supplied a summary of how a nested
`seamless-run` finds its configuration. Its claims were checked in the source,
and what was confirmed is below. Two rows were run and are marked
**measured**.

**What a driver is** (`execution-backends.md`, *Drivers*):

- It never takes the process lock. `seamless-run --driver` sets
  `{"driver": True, "process_lock": False}` in the meta
  (`cmd/api/main.py:690-691`). The lock is decided on the host from the meta,
  before the body starts, whatever the language.
- Its submissions are marked. The mark is thread-local state of the executing
  process (`run.py`, `_DRIVER_CONTEXT`), recorded on each Transformation that
  the body launches. On Dask, a marked submission skips the permission
  routine.

**The mark does not matter in a child process.** `_skip_permission_gate`
(`seamless-dask`, `transformation_mixin.py:597`) also skips the routine for a
process that is neither a worker nor has spawned workers. It calls that a
top-level submission. A nested `seamless-run` is such a process, and so is the
Python process of a CLI job. Their submissions skip the routine whether or not
the parent is a driver.

**How a nested `seamless-run` finds its configuration**
(`cmd/api/main.py:611-617`, `:958-976`). It takes the first that applies:

| | What happens |
|---|---|
| `SEAMLESS_CACHE` is set | a synthetic local cluster is built from that directory, with `execution: process` (`config_files.py`, `_load_seamless_cache_config`) |
| `SEAMLESS_REMOTE_CLIENTS` is set | the buffer and database clients are rebuilt from its JSON, a Dask client is made from `SEAMLESS_DASK_SCHEDULER`, and no configuration file is read (`set_remote_clients_from_env(include_dask=True)`) |
| neither | the working directory must hold a `seamless.yaml` or a `seamless.profile.yaml`, or the command fails. For a job, the working directory is the job directory |

- **Only the Dask worker plugin exports the two variables**
  (`seamless-dask/seamless_dask/worker_setup.py:100`, `:112`). A nested
  `seamless-run` from a bash job therefore works under `remote: daskserver`,
  with no configuration file, and not on the other backends.
- **The Python API does not configure itself from them.**
  `set_remote_clients_from_env` is called by `seamless-run`, by the
  initializer of a worker child (`worker.py`, `_child_initializer`) and by the
  queue, upload and download commands. The Dask mixin reads
  `SEAMLESS_REMOTE_CLIENTS` only when execution is already `remote`
  (`transformation_mixin.py:238`).
- **Measured:** in a fresh Python process, in a directory without a
  configuration file and without the three variables, a `direct` call runs in
  that process. `get_execution()` is `process`, and there is no buffer or
  database write server.
- **Measured:** `direct` on a function whose source file cannot be found
  raises `OSError: could not get source code`.

### 1.9 How R and Julia carry values today

This is what the wire format (§4.9) meets. Read on `julia-r-support`
(`02969fa`) on 2026-10-13 by a subagent. The cited lines of `r.py` and
`julia.py` were read again afterwards, and the rows marked **measured** were
run with seamless-core alone, not through a handler.

- **Neither side has a checksum type.** The R and the Julia runtime define no
  class, attribute or struct for one.
- **Pins travel as one file each, with a manifest.** `pins.json` lists `name`,
  `file` and `celltype` for every pin (`r.py:203-208`, `julia.py:223-235`).
  The runtime picks a decoder from the celltype and from magic bytes. `ryp`
  reads the same files from a temporary directory. `juliacall` gets objects.
- **A result is always one JSON text**, under all four backends. An array or
  bytes travels inside it as a marker dict: `{"__seamless_array__": true,
  "dtype", "shape", "values"}` or `{"__seamless_bytes__": true, "values"}`
  (`r.py:278-312`, `julia.py:424-439`). R also has `__seamless_error__`.
- **The host tests for those markers whatever the result celltype**
  (`r.py:481-492`, `julia.py:745-759`). A `plain` result that is a dict with
  such a key is therefore read as an array, as bytes or as a failure. No
  test covers that.
- **Deep celltypes are refused at the top of both handlers** (`r.py:39-44`,
  `:122-125`; `julia.py:43-48`, `:138-141`). The pin check takes the celltype
  from the pin's `__format__` entry, and takes `mixed` where there is none.
  - A deepcell pin has no such entry (§1.6), so it is not refused. Its dict
    of `Checksum` objects is serialized as `mixed`, which gives a JSON dict
    of 64-hex strings (**measured**).
  - A `checksum` pin has no entry either. Serializing a `Checksum` object as
    `mixed` raises `TypeError` (**measured**), so such a pin fails under all
    four backends. No test and no page says so.

## 2. Scope

**In**

- The merge of both branches onto `main` in `seamless-transformer`,
  `seamless-workflow` and `seamless-share`.
- The backend names of G8, in every language.
- The in-memory rule for Python, compiled, R and Julia.
- Environment wrapping for the R and Julia CLI backends.
- A CLI backend for Python transformers, on the Python face and in a workflow
  Context.
- Deep celltype pins in every backend but compiled (G17), and deep pins and
  results in the bash transformer and in `seamless-run` (G12, G13, G15, G16).
- Checksum objects in every language, and the wire format that carries them
  (G29, G30, G31).
- The moment a specification is checked (G14).
- The contract pages that the two parents wrote, where this plan changes them.

**Out**

- A CLI backend for compiled transformers.
- Any change to the identity of a transformation that a builder makes.
  `__format__` of a Python transformation is not touched, so no ordinary pin
  of a Python CLI job arrives as a file from a read folder (handler R4 stays
  a rule of handler languages). `seamless-run` commands with a directory
  argument or with result targets are the exception: their checksums change
  (C10).
- A new key in the transformation dict, and any change to the graph format.
- `seamless-run`, beyond G12, P16 and G14. It has no handler languages and no
  Python transformers.
- A setting that lets a Python or compiled pin arrive as a file (G28).
- Writing a job directory instead of running it. That stays bash-only.
- Handler R9. It stays a rule of embedded R and Julia interpreters. A Python
  or compiled body runs without the process lock when `process_lock` is
  false, as today.
- Deep celltype pins of compiled transformers. They stay refused.
- A new conversion between deep celltypes (G20).
- The marker dicts in an ordinary result of R and Julia (§1.9). They stay as
  they are.
- Whether the interpreter-thread helper stays (handler plan, §6). That verdict
  is independent of this plan.

## 3. Phase 0 — Merge

**Both conditions for the merge are met** (2026-10-13):

1. The author confirmed that `bash-docker-support` is finished (§1.1). Its
   build-time check, `_validate_bash_only`, is removed again in Phase 2 (C1),
   and its checks of the specification at set and build time move to dispatch
   there (C11).
2. The contract pages of both parents are committed in `seamless`
   (`e1bf5777`, P11). Phase 1 then shows this plan's changes as a diff of
   their own.

**The merge**, in each repository, with nothing pushed until the author asks:

| Repository | Steps |
|---|---|
| `seamless-transformer` | `git switch main`; `git merge --ff-only bash-docker-support`; `git merge --no-ff julia-r-support` |
| `seamless-workflow` | the same three steps |
| `seamless-share` | `git switch main`; `git merge --ff-only julia-r-support` |

- The bash branch goes first because the CLI backends of the handlers stand on
  `execute_bash`. `main` is then first the tested tip of the bash branch, and
  the merge commit shows the handler work against it. The other order gives
  the same tree.
- A conflict is not expected (§1.2). If one appears, stop and report.

**After the merge**

- Run the test files of both branches against `main`, one pytest process per
  file (§10). Run the same files on each branch tip first and keep the
  outcome as the baseline.
  - Bash branch: `test_bash_launch.py`, `test_bash_conda.py`,
    `test_container_spec.py`, `test_container_selection.py`,
    `test_container_docker.py`, `test_container_apptainer.py`,
    `test_container_cancel.py`, `test_contract_bash_output.py`,
    `test_environment.py`, `test_execution_records.py`, the two Phase 6 files,
    and `seamless-workflow/tests/test_contract_bash_environment.py`.
  - Handler branch: `test_language_handlers.py`, `test_interpreter_thread.py`,
    `test_handler_backend_installation.py`, `test_julia_handler.py`,
    `test_r_handler.py`, and
    `seamless-workflow/tests/test_language_handlers_bound.py`.
- **Exit:** every file has the outcome it had on its branch tip. S1 to S3 are
  still wrong at this point. Phases 2 and 3 fix them.

## 4. Design

### 4.1 Two kinds of language backend

- A **CLI backend** starts a process for each run, in a job directory of its
  own, through `execute_bash`. Its command is a script (bash) or an
  interpreter with a runner file (R, Julia, Python).
- An **in-memory backend** runs the code inside the process that runs the
  transformation: the calling process in `process` mode, a worker process
  otherwise.
- A language has one or both (§0). Where it has both, `BACKEND` selects, with
  the values `"cli"` and `"mem"` (G8). `BACKEND` is outside the
  transformation checksum.
- **Any other value is refused when it is assigned (G26)**, on the Python
  face and on a bound node. A value that arrives in a transformation dict is
  not assigned by anyone. It fails when the transformation runs.
- **A rule about a backend applies when the transformation runs, and at no
  other moment (G9).** Building does not check it. A result that is already
  recorded is returned without it. The check of G26 is not such a rule: it
  does not depend on where the transformation runs.

No registry of backends is added. A registered handler that has both kinds
declares `BACKEND` among its metavars and uses the same two values. The
builder checks the value of a metavar with that name for every handler
language.

### 4.2 The in-memory rule (G1, G3, G4)

One function holds the rule (P5):

```python
check_in_memory_environment(environment, language)   # raises, or returns None
```

- With `docker`: it raises. The message names the language and, where the
  language has a CLI backend, says to use `BACKEND="cli"`.
- With `conda_environment`:
  - a specification that contains `/`: the real path of `CONDA_PREFIX` must
    equal the real path of the specification;
  - otherwise: `CONDA_DEFAULT_ENV` must equal the specification;
  - when it does not match, it raises and names both.
- It also looks the names of `which` up on the `PATH` of the process (§4.4).
- It is a function of its arguments and the process environment. It needs no
  running transformation, so a test can call it, and a handler that is called
  directly behaves as before.

Callers:

| Backend | Called from |
|---|---|
| Python in-memory | `run_transformation_dict`, before the body |
| compiled | `run_transformation_dict`, before `call_compiled_transform` |
| R in-memory, Julia in-memory | the handler, in place of its inline copy |

- **A record probe is not checked** (C6).
- **The refusal in `run.py` and `_validate_bash_only` both go** (§1.4). A
  Python or compiled Transformer with an environment builds.
- `docker` together with `conda_environment` is refused at dispatch, for
  every language (§4.8).

### 4.3 The CLI rule (G6)

Every CLI backend launches through one function (P5):

```python
execute_cli(command, pins_, PINS, FILESYSTEM, OUTPUTPIN, environment)
```

- It calls `execute_bash` with `conda_environment_`, `docker_` and `which_`
  taken from `environment`.
- It takes `tf_checksum_` and `should_abort_` from the transformation that is
  running. `run_transformation_dict` puts both in a context variable around
  the body. The checksum is the `tf_checksum` itself, not `checksum_hex`
  (§1.5). Outside a running transformation both are absent, and the launch
  works as `execute_bash` does without them.
- Callers: the R handler, the Julia handler and the Python CLI backend. The
  bash branch of `run.py` may keep its explicit arguments. `execute_bash`
  stays the one place that launches.

What a CLI backend of R, Julia or Python inherits from the bash plan, with no
code of its own:

| From | What |
|---|---|
| bash D1, D3 | `transform.sh` is the launcher, `transform-inner.sh` runs the interpreter command, conda is entered with `conda run` |
| bash D4, D5, D7 | the runtime is chosen on the executing host; the closed image spec; no pull by default |
| bash D6, D8 | the host user; the job directory at `/seamless-job`, which is also `HOME` |
| bash §4.5 | read folders bound read-only at their own path, so a pin that is a link into one resolves in the container |
| bash §4.7 | the failure classes: environment not entered, binary missing, non-zero exit, no `RESULT` |
| bash §4.8 | teardown on cancel, once the launch carries the checksum |
| bash §4.11 | the nesting signal under conda, and none in a container |

What the image or the conda environment must hold:

| CLI backend of | Needs, besides `bash` in an image |
|---|---|
| R | `Rscript`; the R packages `RcppCNPy` and `jsonlite` |
| Julia | `julia`; the Julia packages `NPZ` and `JSON` |
| Python | `python3`; NumPy when an array crosses; seamless-core when a properly mixed value crosses (G7) |

- **In a container the host's environment variables are not inherited** (bash
  plan). `JULIA_PROJECT` of the executing process therefore does not reach a
  containerized Julia job. The image decides the project.

### 4.4 `which` (P4)

`tf.environment.set_which([...])` is looked up where the code runs.

- **CLI backend, every language:** in the script, after the environment is
  entered (bash D10). `execute_cli` passes the names on.
- **In-memory backend:** on the `PATH` of the process, in
  `check_in_memory_environment`.
- The host check in `run_transformation_dict` goes. `run.py` cannot know the
  backend of a handler language, so the check has to sit with the backend.
- A record probe that carries an environment still checks nothing (bash
  plan, §4.7).

### 4.5 The Python CLI backend (G5, G7)

**Selection (P1, G8).**

- Every Python builder has `tf.metavars.BACKEND`: `Transformer("python")`, a
  function decorated with `direct` or `delayed`, and a bound `ctx.tf`.
- The values are `"mem"`, the default, and `"cli"`. Another value is
  refused when it is assigned (G26).
- The value is stored in `meta["metavars"]`, outside the checksum, and only
  when it is set. A Python transformation without it runs in memory. Existing
  Python transformations therefore keep their `__meta__` as it is.
- On a bound node the value belongs to the node, as for a handler language
  (`handler-languages.md`, *Backends*).

**Where it is dispatched.** In `run_transformation_dict`, for
`language == "python"` and `BACKEND == "cli"`, in place of the Python body.
The namespace is built as today, so the pins are parsed on the host by the
same calls as for the in-memory backend.

**The job.** The backend writes these into the job directory and calls
`execute_cli` with the command `python3 -u runner.py` (P6):

| File | Content |
|---|---|
| `runner.py` | the runner, with helper A of the wire format (§4.9). It imports the standard library, NumPy when the job has an array, and Seamless only for the configuration step of P13 |
| the code | the text that `exec_code` would execute: the user code, plus the call for a function or a lambda, or the assignment for an expression |
| a manifest | pin names, their files and encodings, the input names, the output name and the result celltype |
| one file per pin | the pin in a transport encoding (below) |
| the seamless-core helper | the one file that needs seamless-core. It reads and writes the Seamless-mixed format, and it makes the `Checksum` objects of a pin. The runner imports it only when a properly mixed value crosses, or when a checksum crosses into the job |

- The host decides everything that the code can observe: the code mode
  (`analyze_code`), the input names, and the parsed value of each pin. The
  runner rebuilds the namespace that the in-memory backend gives the code
  (the pins as variables, `PINS`, `FILESYSTEM`, `OUTPUTPIN`, `__name__`), runs
  the same text, and encodes the result.
- `-u` makes Python write its output as it is produced. Without it a piped
  Python process buffers, and nothing is relayed while the code runs.

**Pins.** Each pin is carried in an encoding that the runner can decode
without Seamless and that gives back the value the host parsed:

| The host's value | Carried as | The runner needs |
|---|---|---|
| plain data | JSON text | nothing |
| text | the text | nothing |
| an array | `.npy` | NumPy |
| bytes | the bytes | nothing |
| properly mixed | the pin's buffer, in a file whose name ends in `.mixed` (G7) | seamless-core, through its helper |
| a folder: a dict of contents | a directory, which the runner reads back into a dict (§4.6) | nothing |
| a deepfolder: a dict of paths | JSON text | nothing |
| a deepcell: a dict of `Checksum` objects | a wire index of checksums (§4.9) | seamless-core, through its helper (G30) |
| a `checksum` pin: a `Checksum` object | a wire index with one checksum (§4.9) | seamless-core, through its helper (G30) |

**Result.** The runner writes `RESULT` in the wire format (§4.9, P21): a
directory with an index and the files that the index names. Helper B on the
host rebuilds the value that the code returned. The host then serializes it
under the result celltype, as it does for the return value of an in-memory
body.

- An array is a `.npy` file, plain data a `.json` file, and `bytes` a
  `.bytes` file. The suffix says which, so the host never guesses an encoding
  from the content.
- A properly mixed result is a `.mixed` file, written by the seamless-core
  helper (P7) and read by helper B.
- A folder or deepcell result is the dict that the code returns (§4.6, G25),
  with one entry for each member.
- A `Checksum` object is carried as a checksum entry (G29). The runner
  recognizes one without importing Seamless: an object can only be one when
  the code has imported Seamless itself.
- **There is no fallback encoding** (handler R11). A value that the runner
  cannot carry fails the transformation.

**seamless-core is needed in two cases only**: when a properly mixed value
crosses (G7), and when a checksum crosses into the job, which is a deepcell
pin or a `checksum` pin (G30). Nothing checks for it beforehand (G9). When it
is missing, the helper's import fails inside the job, and the failure is the
Python error in the job's stderr. A job with neither runs in an environment
that has no Seamless at all.

**Parity (P2).** Both Python backends give the same result, bit for bit, when
both succeed. A backend may fail where the other succeeds.

- The pin side holds by construction: the host parses, and the transport
  encodings are lossless for what it parsed. Deep pins have the same form
  under both backends (§4.6).
- The result side does not. Seamless classifies a returned value with its own
  rules (§1.5, the measured table), and the runner has no Seamless. Phase 5
  fixes the set of result types the runner accepts, with both backends
  running. A type is accepted only when the two result checksums are equal.
  Every other type fails under the CLI backend.
- A member of a deep result follows the same rule as an ordinary result:
  helper B rebuilds the value, and the host serializes it with the call that
  the in-memory backend uses.
- A known difference that Phase 5 must settle or list: a `bytes` pin is a
  `seamless.Buffer` in memory and cannot be one in the runner. A `checksum`
  pin is a `Checksum` object under both backends (G30).

**Refused by the first version (P8).** A transformation with modules or
globals fails under the CLI backend when it runs. The message says to use
`BACKEND="mem"`.

**The rest is the bash body contract.**

- The run takes the process lock like a bash body and may run without it.
- A cancel tears the job down as it does for bash.
- A failure is the *Bash transformer exception* report. Its command is the
  runner's, and the Python traceback is in the standard error trailer.

**Drivers and nested work (G11).** A Python CLI job is in the position of a
bash job (§1.7), with one difference that P13 removes.

- **A driver never takes the lock**, under either backend. That is decided on
  the host.
- **Code that is not a driver signals its parent at its first nested
  submission**, as a bash body's `seamless-run` does: the Python API writes
  to the same pipe (§1.5). The signal exists without an environment and under
  conda, not in a container.
- **Under `remote: daskserver` the job's process is configured from the
  variables that the Dask worker exports (P13).** Before the code runs, when
  `SEAMLESS_REMOTE_CLIENTS` is set and Seamless can be imported, the runner
  calls `set_remote_clients_from_env(include_dask=True)`. Nested work then
  goes to the same cluster and shares its caches, as a nested `seamless-run`
  does. Without this step the Python API stays unconfigured (§1.7).
- **Its submissions skip the permission routine**, as those of a nested
  `seamless-run` do, driver or not.
- **On the other backends nothing is exported.** A nested call then runs
  inside the job's own Python process, with no cache and no dispatch. A
  nested `seamless-run` in a bash job fails there for lack of a configuration
  file.
- **The code needs Seamless where it runs.** In a container the variables are
  not inherited, and nested work is not supported (bash plan, §4.11).

### 4.6 Deep celltype pins and results (G17)

**Input pins.** Bash has rules of its own. Every other backend, CLI and
in-memory alike, follows one rule:

| Pin | bash | every other backend |
|---|---|---|
| `deepcell` | refused (G15) | not materialized: a dict of checksum objects (G30). The code resolves a member itself, where it can |
| `folder` | materialized on disk: a directory in the job directory (§4.7) | materialized in memory: a dict of contents, each member as bytes |
| `deepfolder` | already on disk: a directory, or the job fails (G13, §4.7) | already on disk: a dict of paths, or the transformation fails |
| `deepfolder` cast to `plain` | the index: a JSON file of keys and checksums | the index: a dict of 64-hex strings |

- **The fourth row is a cast** (G20), and the only one in the matrix. The pin
  is declared `plain`, and the cast `deepfolder → plain` hands it the index
  unchanged. From a folder the cast is `folder → deepfolder → plain`, and from
  a deepcell `deepcell → plain` (*The casts*, below). It keeps what a
  deepfolder pin of in-memory Python is today, with strings where there are
  `Checksum` objects now (C12).
- **Compiled transformers are not in the second column** (G21). A compiled
  pin cannot have a deep celltype (`compiled-pins.md`), and this plan does not
  change that.
- **`Checksum.resolve()` in transformation code** is needed for a deepcell
  pin and for a `checksum` pin, and for nothing else. Only Python code has
  it.
- **A deepfolder pin never asks a buffer server** (G13), in any backend.
  Where its members are not files in a read-buffer directory, the
  transformation fails.

**How each form is made, outside bash.**

- **Folder.** The host resolves the members, from any buffer source.
  - In memory, the code gets the dict, as today.
  - Under a CLI backend, the host writes the members into the job directory
    with the function that bash uses (G24, §4.7), and the runner reads them
    back into a dict before the code runs. The directory is transport, and the
    code does not see it.
- **Deepfolder (G18).** A dict from each key to the path of the member's
  buffer file, as it is stored in a read-buffer directory of the executing
  process.
  - The host looks each member up as it looks a file pin up today
    (`_find_filesystem_path`, §1.8): `<directory>/<checksum>` or
    `<directory>/<first two hex digits>/<checksum>`, and then the same with
    `.zst` and with `.gz`. Where one directory holds a member in several
    forms, the uncompressed one is given.
  - Nothing is made: no directory, no link and no copy. The same string
    reaches the code under both backends.
  - **The code deals with the stored form.** A path that ends in `.zst` or
    `.gz` holds the member's bytes compressed. The file has no name of its
    own and no extension. The key is the name.
  - In a container the paths resolve, because the read-buffer directories are
    bound at their own paths (bash plan, §4.5). A buffer file that is a link
    which the container cannot follow counts as not found there (G27, §4.7),
    and the transformation fails.
  - A member that is not found fails the transformation. The directory that
    is named by the index's checksum, which today's lookup tries for a
    directory pin, is no longer tried, in bash or outside it (§4.7).
- **Deepcell.** A dict of checksum objects under every backend (G30):
  `seamless.Checksum` in Python, and the checksum class of the runtime in R
  and Julia (*Checksum classes*, below).
  - In-memory Python gets the dict as today. Every other backend gets it
    through the wire format (§4.9).
  - Python code can resolve a member in memory, and in a CLI job under
    `remote: daskserver` only (G19). R and Julia code cannot resolve one.
- **In R and Julia**, a dict is a named list and a `Dict` with string keys.
  A member's bytes are a raw vector and a `Vector{UInt8}`, as for a `bytes`
  pin. A path is a string. A checksum is an object of the checksum class.

**What changes in code that works today** (in-memory Python, §1.6):

- **A deepfolder pin** is a dict of `Checksum` objects, which the code can
  resolve from any buffer source. It becomes a dict of paths, and it fails
  where the members are not on disk. Code that wants the checksums declares
  the pin `plain`. It then gets 64-hex strings, not `Checksum` objects.
- **A folder pin** is a path when the index's directory is in a read-buffer
  directory. It becomes a dict of contents always. Code that wants paths
  declares the pin `deepfolder`. It then gets one path for each member, not
  the path of one directory.

**The casts.** A pin gets another form when it is declared with another
celltype than its source. The cast is an Expression that is constructed when
the Transformation is built (`TransformerCore._convert_pin_arguments`), and
the transformation then holds a pin of the target celltype. A backend cannot
tell what a pin was cast from. The rows were run on 2026-10-13, apart from
`folder → deepfolder`, which is from `deep-celltypes.md`:

| From | To | Legal today | The pin is then |
|---|---|---|---|
| `deepcell` | `deepfolder` | yes, free | a deepfolder pin |
| `deepfolder` | `folder` | yes, free | a folder pin |
| `folder` | `deepfolder` | yes, free | a deepfolder pin |
| `deepcell` | `folder` | no. Go through `deepfolder` | |
| `deepcell`, `deepfolder` | `plain` | yes, free | an ordinary `plain` pin that holds the index: a JSON file in bash, a dict of 64-hex strings elsewhere |
| `folder` | `plain` | no. Go through `deepfolder` | |
| `folder` | `mixed` | yes, and it fetches every member | an ordinary `mixed` pin: a dict of byte arrays |
| `deepcell`, `deepfolder` | `mixed` | no. Go through `folder` | |
| `deepfolder` | `deepcell` | no | |

**Results (G25).** The matrix is about input pins. Results follow the same
split:

- **Bash** writes a `RESULT` directory, for `folder` and for `deepcell` (G16,
  §4.7).
- **Every other backend** returns a dict, as an in-memory Python transformer
  does today. Each member is a checksum or a value (G29). In-memory Python
  hands the dict to the host as it is. Every other backend carries it to the
  host in the wire format (§4.9). The host packs it into the index
  (`pack_deep_structure`).
- A `deepfolder` result stays refused by the builder.

**Checksums and values (G29).** A member of the returned dict is a value
unless it is a checksum object. For Python, with what an in-memory
transformer does today (run on 2026-10-13):

| Member | `deepcell` result | `folder` result | Today |
|---|---|---|---|
| a `Checksum` object | a checksum | a checksum | the same |
| a `str` of 64 lowercase hex characters | a value, serialized as `mixed`, like any other string | fails with a `TypeError`, like any other string | **read as a checksum**, for both celltypes. The string goes into the index as it is, and nothing checks that such a buffer exists |
| any other `str` | a value, serialized as `mixed` | fails with a `TypeError` | the same |
| `bytes` | a value | a value: the member's bytes, also when they are 64 hex characters | the same |

- **Today's rule is one branch of one function**: `pack_deep_structure`
  ([transformation_utils.py:311-316](../../seamless-transformer/seamless_transformer/transformation_utils.py#L311-L316)).
  That branch goes (C16). `run.py` calls the function at two places: for a
  compiled result, and for the returned dict of every other language. A
  compiled result holds no checksum objects, so each of its members is a
  value.
- **Code that returns 64-hex strings as checksums has to wrap them**, in
  `Checksum` or in the class of its language. That includes code that takes
  the strings from a `plain` pin (the fourth row of the matrix). Left
  unwrapped, a deepcell result holds the strings as values, and nothing
  fails.
- **A checksum object is a member, or a `checksum` result, and nothing
  else.** Returned under any other result celltype it fails, in every
  language. Python does that today for a `mixed` result: serializing a
  `Checksum` as `mixed` raises a `TypeError` (measured).
- **A `checksum` result accepts a checksum object and a 64-hex string**
  (measured for Python). There the celltype says what the string is.
- **No pickle is used** (G29). The reasons, measured on 2026-10-13:
  - Loading a pickle runs code that its writer chose. Today the host reads
    `RESULT` as data only: `np.load` without `allow_pickle`, JSON and text.
  - A dict with an array, written by NumPy 2.4 under Python 3.14 with the
    default protocol, does not load under NumPy 1.26 and Python 3.12
    (`No module named 'numpy._core.numeric'`). With protocol 4 it loads, and
    the other direction loads. No older NumPy was tried.

**Checksum classes (G30).** Every language has one:

| Language | The class | Where it comes from |
|---|---|---|
| Python | `seamless.Checksum` | seamless-core. In memory it is always there. In a CLI job the seamless-core helper makes the objects of a pin, so seamless-core must be installed there (§4.5) |
| R | an S3 class on a character string of 64 hex characters | the R runtime, under both backends |
| Julia | a struct that holds the hex string | the Julia runtime, under both backends |

- **What the class of R and of Julia does**: it is made from a string of 64
  lowercase hex characters, and anything else is an error. It can be tested
  for, converted to its string, compared and printed. It cannot resolve: the
  class carries the checksum and no access to a buffer.
- **Its names are this plan's** (P22): `seamless_checksum("…")` and
  `is_seamless_checksum(x)` in R, and `Checksum("…")` in Julia. The runtime
  puts them in the scope of the code.
- **A pin that is cast to `plain` holds strings**, not objects (the fourth
  row of the matrix). Plain data holds no objects in any language.
- **Bash and compiled transformers are not touched.** Neither has objects. A
  `checksum` pin of a bash transformer stays what it is today.

Where a checksum object appears, in every language:

| | The code gets or returns |
|---|---|
| a deepcell pin | a dict of checksum objects |
| a `checksum` pin | one checksum object. In R and Julia such a pin fails today (C17) |
| a member of a deepcell or folder result | a checksum object, for a member that is a checksum |
| a `checksum` result | a checksum object, or a 64-hex string |

**Parity.**

- Both backends of a language give a deep pin the same form. Python parity
  needs no exception for folders, and R and Julia need no one-sided failure.
- **A path is observable.** For a deepfolder pin, both backends give the same
  string on one host, and another host gives another. The stored form can
  differ too. Code whose result depends on the string or on the form, and not
  on the member's bytes, is not covered by any guarantee.
- **A deepcell pin has the same type under both backends of a language**
  (G30). Code that filters its keys and returns the rest gives the same
  result under both. Python code that calls `v.resolve()` works in memory,
  and fails in a CLI job outside Dask (G19), which parity allows.

### 4.7 Deep pins and results in the bash transformer (G12, G13, G15, G16, G22)

This is the bash column of the matrix (§4.6). `seamless-run` follows it,
because its commands are bash transformations.

**A folder or deepfolder pin is a new directory in the job directory**, with
the pin's name. The host makes one entry in it for each key of the index:

| The member | `folder` pin | `deepfolder` pin |
|---|---|---|
| is a file in a read-buffer directory | a symlink to that file | a symlink to that file |
| is not | the buffer is resolved, from any buffer source, and written | the job fails with a `CacheMissError` that names the member. No server is asked (G13) |

- **"A file in a read-buffer directory"** is the lookup of G18 (§4.6): the
  checksum as the file's name, plain or with `.zst` or `.gz`.
- **The directory lives as long as the job directory**, which is removed when
  the job ends.
- **Members are handled one at a time.** Today the host loads every member of
  a folder into memory before the job directory is written
  (`unpack_deep_structure`).
- **One rule replaces two code paths of today** (§1.8): the lookup of a
  directory that is named by the index's checksum, which nothing makes, and
  the member-by-member resolving of a deepfolder from any source.

**Compression.**

- **A deepfolder entry is never transcoded** (G22). It is a symlink, and its
  name is the key with the suffix of the stored form. The member `1abc.pdb`
  that is stored as `<checksum>.gz` is the entry `1abc.pdb.gz`. The script
  reads the form from the suffix. A compression suffix in the pin's own name
  asks for nothing.
- **A folder entry has the form that the pin's name asks for** (G23). This is
  what `compression.md` says today of a directory pin: the pin `mydata` gets
  each member's bytes, and the pin `mydata.zst` gets them compressed, with
  `.zst` on each entry. An entry is a symlink where the stored form fits.
  Where it does not, the stored file is read and written out in the form
  that is asked for.

**In a container** (G22, G27).

- A written entry is a file in the job directory, which is mounted at
  `/seamless-job`.
- A symlink points into a read-buffer directory. The wrapper binds every
  read-buffer directory read-only at its own path (bash plan, §4.5), so the
  link resolves in the container as it does on the host.
- **A buffer file that the container cannot read counts as not on disk
  (G27).** A buffer file can itself be a symlink to a file outside the
  read-buffer directory: `seamless-upload` has a symlink mode beside its
  hard-link mode (`cmd/register.py`). The target of such a link is not bound.
  Where the job will run in a container, the host follows each buffer file
  before it links it. A file that ends outside what the container can reach
  is handled as a member that is not on disk:
  - `folder`: the host reads the file through the link and writes a copy
    into the job directory, in the form that the pin's name asks for (G23).
  - `deepfolder`: the job fails with the `CacheMissError` of a member that is
    not on disk. The message says that the buffer file is a link which the
    container cannot follow.
  - Without a container the file is linked like any other, and the script
    reads it through both links.
  - A hard-linked buffer file is an ordinary file, in a container too.
- **What the container can reach** is what the wrapper binds: the job
  directory and the read-buffer directories. A bind that an operator adds
  with `SEAMLESS_CONTAINER_ARGS` is not seen (P20). With such a bind, a
  folder member is copied without need, and a deepfolder pin fails although
  the container could read the member.
- **An ordinary pin that is linked from a read-buffer directory gets the same
  treatment** (P19, §1.8). Today `write_bash_job` links it without following
  it
  ([execute_bash.py:198](../../seamless-transformer/seamless_transformer/execute_bash.py#L198)).
  Where the container cannot follow the link, the file is copied into the job
  directory, in the form that the pin's name asks for.
- The tests run each case on docker, podman and apptainer (§6).

**Where it is done (G24, P15).** One function writes a folder or deepfolder
pin into a job directory. It is taken out of `write_bash_job`, which calls it
for a bash job, and the CLI backends of R, Julia and Python call it to carry a
folder (§4.6).

- It decides by the pin's celltype what happens to a member that is not on
  disk.
- It is told whether the job will run in a container, and which directories
  that container binds, and applies G27.
- It works from the index, so a caller that has only the index does not load
  the members of a folder to write them. That is the case for a bash job and
  for the Python CLI backend. It also takes members that a caller holds in
  memory already, as a handler does.
- `__format__` does not change, so no transformation gets a new checksum from
  this.

**`seamless-run`:**

- **A result with result targets is declared `folder` (G12).** The index and
  the files that `seamless-run` downloads are the same. The declared celltype
  is read nowhere else in `cmd/` (searched, not run).
- **A directory argument becomes a `folder` pin** (P16, accepted). Today it is a
  `mixed` pin whose format says `deepfolder`, and it is materialized on the
  executing host by the path that G13 removes. Left as it is, a job with a
  directory argument would fail on every host that does not see the buffer
  directory. The pin's own celltype has to change with the format: the host
  resolves the contents of a pin by its celltype (§1.8).
- **Both change checksums (C10).**

**Deepcell in the bash transformer (G15, G16):**

- **A deepcell pin is refused.** The message names the pin and says to
  declare it `deepfolder`, `folder` or `plain`. Today the launch fails with a
  bare `TypeError` (§1.6). The refusal happens when the celltype is set, and
  again before launch.
- **A deepcell result is read as a folder result is.** `RESULT` must be a
  directory, and each file in it is a member that holds the file's bytes.
  Each member is then verified to deserialize as `mixed`. One that does not
  fails the transformation, and the message names the file.
- **What changes against today** (§1.6):
  - A member keeps its file's bytes. Today the file is parsed and serialized
    again.
  - A file that is not an `.npy` array, JSON or a Seamless-mixed buffer
    fails. Today plain text became a JSON string. Measured on 2026-10-13:
    `hello`, CSV text, an empty file, `NaN` and JSON with a trailing comma do
    not deserialize as `mixed`.
  - A `RESULT` that is one JSON file is no longer split into members. It
    fails, as it does for `folder`.
- **A member can be a buffer that Seamless would not write.** Measured: the
  files `3` and `{"a":[1,2]}` deserialize as `mixed`, and their bytes differ
  from what Seamless writes for the same values (`3\n`, and JSON with
  indentation). Two scripts that write the same value with different
  whitespace therefore get different member checksums. This follows from
  "exactly like folder results".

**Outside bash**, the same lookup of the members decides whether a deepfolder
pin is on disk, and the code gets the paths that it found (G18, §4.6). A
folder under a non-bash CLI backend travels as the directory that this
section describes for a folder pin, without a suffix in its name, and the
runner reads the entries back. G27 holds there too: in a container, a
deepfolder pin with a member that the container cannot read fails, and such
a folder member is copied.

### 4.8 A specification is checked at dispatch (G14)

**What is checked:** `docker` together with `conda_environment`, and the keys
of the image spec (bash D5: `name`, `gpus`, `shm_size`, and the three legacy
keys with their messages).

**When:** at dispatch, on the submitting side. Dispatch is the moment a
transformation that has no recorded result is handed to an execution backend.

- Setting an environment and building a Transformation check nothing. The
  check in `Environment._to_lowlevel` and the one in `set_docker` go.
- A result that is already recorded is returned without the check, as under
  G9.
- A second submission that latches on to a running one is not checked: it
  dispatches nothing.
- The executing host still validates before launch, as the bash plan has it.
  A transformation that is run from its checksum alone has no other check.

**Where:** every place that dispatches.

- For `process`, `spawn` and `remote: jobserver` that is the uncached path of
  the transformation cache (`TransformationCache._run_uncached_impl`).
- A submission to Dask does not pass there. The comment in that function says
  so. Its dispatch point is to be found in Phase 2.
- `seamless-run` stops refusing `--docker` with `--conda` while it parses its
  arguments (C11).

### 4.9 The wire format (G31)

A value that holds checksum objects cannot cross a process or a language
boundary as JSON, `.npy` or bytes alone. The wire format carries one value,
or the members of a dict, and marks each checksum as one. Two helpers speak
it: **helper A** on the side of the code, one for each language, and
**helper B** on the host, shared by all.

**Where it is used.**

| Crossing | In-memory Python | Python CLI | R, both backends | Julia, both backends |
|---|---|---|---|---|
| a deepcell pin or a `checksum` pin, to the code | not needed | yes | yes | yes |
| a folder or deepcell result, to the host | not needed | yes | yes | yes |
| an ordinary result, to the host | not needed | yes (P21) | no: the JSON text of today (§1.9) | no: likewise |

- In-memory Python hands objects over. Nothing crosses.
- The in-memory backends of R and Julia cross a language boundary, so they
  use the format as their CLI backends do. Each language then has one path
  for a deep result.
- Every other pin travels as it does without this section (§4.5, §4.6).

**The format.** An index, which is JSON, and the files that it names. For a
dict of members:

```json
{
  "members": {
    "1abc": {"__checksum__": "9f86d081…0a08"},
    "2xyz": "m000001.npy",
    "notes/readme.txt": "m000002.bytes"
  },
  "json": "m000000.json"
}
```

For one value:

```json
{"value": "m000000.npy"}
```

- **The top level** has `members` or `value`, never both. The only other key
  is `json`, which goes with `members`.
- **An entry** is one of two things:
  - a dict with the one key `__checksum__`, whose value is 64 lowercase hex
    characters: a checksum;
  - a string: the name of a file. Its suffix declares its encoding (below).
- **`json`** names one file that holds a JSON object. Its keys are members,
  and its values are their values. Helper A puts members there whose values
  JSON can carry, so that many small members do not become many files. A key
  is in `members` or in that file, never in both.
- **No key is reserved.** Member keys stand under `members` and in the `json`
  file, and nowhere else. A member can be called `value`, `json` or
  `__checksum__`.
- **A file name is helper A's**: a counter with a suffix. It is never made
  from a key, which can hold a `/`.

**The encodings.** The suffix of a file name says how the file is read.
Helper B never chooses a decoder from the content.

| Suffix | The file holds | Helper B gives the host | Written by the helper A of |
|---|---|---|---|
| `.json` | one JSON value | the parsed value | every language |
| `.bytes` | raw bytes | `bytes` | every language |
| `.npy` | one array, in NumPy's format | the array, loaded without pickle | Python |
| `.jsonarray` | one array as JSON: its dtype, its shape, and its values in column-major order. This is the payload that R and Julia write today, without its marker key (§1.9) | the array | R and Julia |
| `.mixed` | a Seamless-mixed buffer | the deserialized value | Python, with seamless-core |

**Helper B rebuilds values, never buffers.**

- For `members` it returns a dict. A checksum entry becomes a `Checksum`
  object, and every other member becomes the value that the code returned.
  For `value` it returns that one value.
- The host then does what it does for an in-memory result:
  `pack_deep_structure` for a deep result, and `Buffer(value, celltype)`. No
  rule of serialization exists twice, which is where parity comes from.
- Measured on 2026-10-13: a `bytes` value that is serialized as `mixed`
  becomes an `.npy` buffer with a byte string dtype. A file of raw bytes is
  therefore not the buffer of a deepcell member. Raw bytes can also start
  with the `.npy` magic. Both are why the encoding is declared.
- Helper B writes too: the index of a deepcell pin, which has checksum
  entries only, and that of a `checksum` pin, which is
  `{"value": {"__checksum__": "…"}}`. Such an index needs no files.

**Helper B refuses a malformed index.** The transformation fails, and the
message names the entry:

- a top-level key that is not one of the three; `members` together with
  `value`; neither of them;
- `members` where the result celltype is not deep, or `value` where it is;
- an entry that has neither form; a checksum entry with a second key; a
  checksum that is not 64 lowercase hex characters;
- a file name with a path separator, with an unknown suffix, or without a
  file;
- a `json` file that is not a JSON object; a key that is in both places.

It reads the files that it is handed, and nothing else.

**Helper A**, for each language:

| | Python CLI | R | Julia |
|---|---|---|---|
| Where it lives | in `runner.py`, with the standard library only. The seamless-core helper reads and writes `.mixed` and makes `Checksum` objects (§4.5) | in the R runtime, under both backends | in the Julia runtime, under both backends |
| It reads | the index of a deepcell pin into a dict of `Checksum` objects, and that of a `checksum` pin into one object | the same, into a named list | the same, into a `Dict` with string keys |
| It writes | every result (P21) | a folder or deepcell result | a folder or deepcell result |
| A checksum is | an instance of `seamless.Checksum`, looked up in `sys.modules` without an import | an object of the S3 class | an object of the type |

- **A member that is a value is classified as an ordinary result is in that
  language**: by the rule of a `mixed` result for a deepcell, and by the rule
  of a `bytes` result for a folder. Helper A adds no rule of its own.
- **Helper A refuses** a key that is not a string, and a value that it cannot
  carry. There is no fallback encoding.
- **Helper A and helper B always have the same version.** The host that runs
  helper B writes helper A into the job: the runner of Python, and the
  runtime of R and of Julia. The format therefore has no version number, and
  it is not a contract (P23). A handler of a third party returns a Python
  dict to the host, and carries it there in its own way.

**Where the files are.**

- **Under a CLI backend, `RESULT` is a directory** with `index.json` and the
  files that it names. The backend calls `execute_cli` with the output pin
  `folder`. `execute_bash` then returns the files of that directory as
  bytes, as it does for a folder result of a bash transformer
  ([execute_bash.py:643-653](../../seamless-transformer/seamless_transformer/execute_bash.py#L643-L653)).
  It removes the job directory before it returns, so nothing can be read
  from disk afterwards. Helper B works on those bytes.
- **Under an in-memory backend of R or Julia**, the runtime writes the same
  directory into the temporary directory of the run. The handler reads its
  files before it removes that directory.
- **An ordinary result of R and Julia stays one file**, `RESULT`, with the
  JSON text of today. The handler chooses by the result celltype.
- **The index of a pin** is the content of the pin's file. The manifest gives
  the pin the celltype `deepcell` or `checksum`, and the runtime reads the
  file as an index.

## 5. Phases

Nothing blocks the start: Q10 is ruled (G29), and both conditions for the
merge are met (§3).

Order: 0 → 1 → 2 → 3a → 3b → 3c → 4 → 5 → 6. Phases 2 and 3 both edit the
environment block of `run_transformation_dict`, so they are not done side by
side. Each phase is implemented against the contract pages of Phase 1 and the
tests of §6.

The wire format (§4.9) is built in three steps: helper B on the host in 3b,
the helpers A of R and Julia in 3c, and that of Python in Phase 4. The rule
of G29 for in-memory Python comes before all of them, in 3a.

### Phase 0 — Merge

§3.

### Phase 1 — Contract pages

- The pages of §7, written as the contract of the finished plan.
- **Exit:** no page says that an environment applies to bash transformers
  only, that Docker under a CLI backend is not specified, that how conda
  environments are compared is open, or names a backend `Rscript`, `ryp`,
  `julia` or `juliacall`. No page says that a 64-hex string in a returned
  dict is a checksum. The author has read the pages, with the names of P5
  and P22.

### Phase 2 — Backend names and the in-memory rule

- The rename of C7, in the two handlers, their registrations and their tests.
- `HandlerMetaVars` refuses a `BACKEND` value other than the two when it is
  assigned (G26). The handlers keep their own check.
- `check_in_memory_environment` (§4.2), with the `which` lookup of §4.4.
- `run.py`: the refusal of §1.4 goes. Python in-memory and compiled call the
  function. The record-probe exemption stays.
- `_validate_bash_only` and its two calls go.
- The R and Julia handlers call the function for their in-memory backend.
- The two tests of §1.4 are rewritten to the new rule.
- The checks of the specification move to dispatch (§4.8). The tests that
  expect them at set or build time (`test_container_spec.py`,
  `test_environment.py`, `test_seamless_run_environment.py`) are rewritten to
  that moment.
- **Exit:** `test_in_memory_environment.py` and `test_environment_dispatch.py`
  pass. The files of Phase 0 pass, with the rename and the rewritten tests.

### Phase 3 — Deep pins; the wire format; the CLI backends of R and Julia

**3a — Deep pins in bash (§4.7) and in every other backend (§4.6);
checksums and values in memory (G29).**

- The code that writes a folder or deepfolder pin into a job directory moves
  out of `write_bash_job` into one function, which the CLI backends of R,
  Julia and Python call as well (G24).
- That function: a folder or deepfolder pin is a new directory with one
  entry for each key (G22, P15, §4.7). A member that is on disk is a symlink.
  A folder member that is not is resolved and written, and a deepfolder
  member that is not fails the job (G13). The host hands a bash job the
  index, and no longer resolves the members of a folder beforehand. For a
  job that will run in a container, a buffer file that the container cannot
  read counts as not on disk (G27).
- The namespace that every other language gets
  (`build_transformation_namespace_sync`): a folder pin is a dict of contents
  always, and a deepfolder pin is a dict of paths, or fails (G17).
  `tests/test_contract_deep_pins_and_results.py` expects a dict of `Checksum`
  objects for a deepfolder pin today. It is rewritten.
- `seamless-run`: the result with result targets is `folder` (G12), and a
  directory argument is a `folder` pin (P16).
- Deepcell: a deepcell pin on a bash transformer is refused when its celltype
  is set, and again before launch (G15). A deepcell result is read as a
  folder result and verified (G16).
  `execute_bash` returns the files' bytes for a deepcell result, and the
  members are inserted as buffers, not serialized as values.
- `tests/test_execute_bash_directory_inputs.py` expects today that a
  deepfolder pin is written from members that are not on disk. It is
  rewritten.
- **Checksums and values (G29, C16).** `pack_deep_structure` loses the
  branch that reads a 64-hex string as a checksum. A test, a fixture or an
  example that returns such a string as a checksum wraps it in `Checksum`.
- **Exit:** `test_bash_directory_pins.py` passes, and `test_deep_pins.py`
  passes for in-memory Python, with the cases of G29. The `tests/cmd` files
  that use a directory argument or result targets pass, also against a
  jobserver that does not see the buffer directory.

**3b — The wire format on the host: helper B (§4.9).**

- One module in `seamless-transformer`. It is not public (P23).
- **Reading.** It takes the files of a wire directory as a mapping from
  names to bytes, and returns the value that the code returned: a dict for
  `members`, with a `Checksum` object for each checksum entry, or the one
  value for `value`. It decodes each file by its suffix.
- **Writing.** It writes the index of a deepcell pin and that of a
  `checksum` pin, as JSON text.
- **Refusing.** Every case of §4.9, each with a message that names the
  entry.
- The decoding of an array payload, which both handlers carry today
  (`r.py:483-490`, `julia.py:747-757` on `julia-r-support`), moves into the
  module. It reads a `.jsonarray` file with it. The handlers call it for
  their ordinary results, which do not change.
- **Exit:** `test_wire_format.py` passes. No transformation uses the module
  yet, apart from the array payload of an ordinary R or Julia result, and
  the handler test files of Phase 0 still pass.

**3c — R and Julia: environments under the CLI backend; checksum objects,
deep pins and deep results under both backends.**

- The context variable and `execute_cli` (§4.3). Both handlers launch through
  it.
- The host `which` check goes from `run.py` (§4.4).
- **The checksum class in both runtimes** (G30, §4.6), with the names of
  P22.
- **Helper A in both runtimes** (§4.9). It reads the index of a deepcell pin
  and of a `checksum` pin into checksum objects. It writes a folder or
  deepcell result as a wire directory.
- **The handlers:**
  - stop refusing deep celltypes (C8);
  - recognize a deepcell pin and a `checksum` pin by their value (§10.2),
    write the index with helper B, and name the celltype in the manifest;
  - for a deep result, call `execute_cli` with the output pin `folder` under
    the CLI backend, and read the temporary directory under the in-memory
    backend. They hand the files to helper B and return the dict;
  - leave an ordinary result as it is. A checksum object is then written as
    its 64-hex string under a `checksum` result, and fails under any other
    celltype (§4.6).
- Folder and deepfolder pins under both backends of both languages (§4.6).
  Under the CLI backend a folder travels as a directory, and the runtime
  reads it back into a dict.
- **Exit:** `test_cli_backend_environment.py` passes for R and Julia: in a
  conda environment, and in a container on docker, podman and apptainer, run
  and not skipped. `test_deep_pins.py` passes for both backends of both
  languages, with the cases of G29 and G30. The tests of the checksum class
  in the two handler test files pass. `test_container_cancel.py` passes with
  an R and a Julia job added.

### Phase 4 — The Python CLI backend

- `metavars` on the Python builders, standalone and bound (P1).
- The runner, the manifest, the seamless-core helper and the dispatch in
  `run.py` (§4.5), with the refusal of P8, the deep pins of §4.6 and the
  configuration step of P13.
- **Helper A in the runner** (§4.9). It writes every result as a wire
  directory (P21), and the backend hands the files to helper B. It reads the
  index of a deepcell pin and of a `checksum` pin, and the seamless-core
  helper makes their `Checksum` objects (G30).
- **Exit:** `test_python_cli_backend.py` passes without an environment, in a
  conda environment, and in a container on the three runtimes.
  `test_deep_pins.py` passes for the Python CLI backend, with the cases of
  G29 and G30. `test_python_cli_backend_dask.py` passes on the Dask harness.

### Phase 5 — Python parity

- Run every case of Phase 4 under both backends and compare result checksums.
- Fix the result types the runner accepts (§4.5). The same set holds for a
  member of a deepcell result, which helper A classifies by the same rule
  (§4.9). Write the table of accepted types and of one-sided failures into
  the contract page.
- **Exit:** the parity tests pass. The table goes to the author.

### Phase 6 — Close-out

- Regenerate the agent docs index and the API pages
  (`docs/agent/scripts/gen_agent_docs.py`).
- Both `RELEASE-NOTES.md` files (`seamless/` and the root) and
  `seamless-transformer/README.md`. The notes carry the entries of §7,
  *Release notes*, and the `seamless-run` entry (C10) comes first under its
  own heading, because it changes the transformation checksum of every
  command that has a directory argument or result targets. The entry of C16
  follows it, because nothing fails for a deepcell result that returns naked
  64-hex strings.
- Mark in the two parent plans what this plan supersedes: bash D9 and its
  §4.12; handler R5's backend names, §3.6 ("not ruled"), §8 (the Docker
  decision) and the refusal of deep celltypes in §9.
- **Exit:** the generated pages match the code. No doc states a superseded
  rule. Both release-notes files carry the two leading entries of §7.

## 6. Tests

New files go in `seamless-transformer/tests/`. Run them in the `seamless1`
conda environment, one pytest process per file. Every test that expects a
failure, an environment or a backend uses a fresh nonce pin: the environment
and the backend are outside identity, so a cache hit runs nothing.

| File | Phase | Checks |
|---|---|---|
| the handler test files (changed) | 2 | the backend fixtures use `"cli"` and `"mem"`; an old name (`"ryp"`, `"juliacall"`, `"Rscript"`, `"julia"`) or any other value is refused when it is assigned, on the Python face and on a bound node (G26), and nothing is stored; a transformation dict that carries such a value fails when it runs |
| `test_in_memory_environment.py` | 2 | For a Python and a compiled transformation dict: `docker` fails before the body; a conda name other than `CONDA_DEFAULT_ENV` fails before the body; the name of the process's environment runs; the path of `CONDA_PREFIX` runs, also through a symlink; a record probe that carries either runs. A Python and a compiled Transformer with a Docker image build, and a recorded result is returned without the check (G9). `Transformer("julia")` with `BACKEND="mem"` and the process's conda environment runs, and with another one fails: through the Transformer, not by calling the handler. The same for R. `which`: a missing binary fails an in-memory run |
| `test_environment_dispatch.py` | 2 | A Transformer with a conda environment and a Docker image builds, and so does one with an unknown key in its image spec; each fails when it is dispatched, with the messages of the bash plan, and nothing runs; a recorded result is returned for each without the check; `seamless-run --docker … --conda …` fails at dispatch, not while it parses its arguments; the same holds in `process`, in `spawn` and on a jobserver |
| `test_bash_directory_pins.py` | 3a | With a read-buffer directory configured: a folder pin and a deepfolder pin are each a new directory in the job directory; a member that is a file in the read-buffer directory is a symlink to it, in the flat layout and in the layout with a two-digit prefix directory; a folder member that is only on the hashserver is written; a deepfolder member that is only on the hashserver fails the job with `CacheMissError`, and the hashserver is not asked for it; a deepfolder member that is stored as `.gz` or `.zst` is a symlink with that suffix after the key, and no copy is made; a folder member that is stored compressed is written out decompressed where the pin's name has no suffix, and is a symlink where the pin's name asks for the stored form (G23). In a container on docker, podman and apptainer: a script reads a member through its symlink, and reads a member that was written. For a buffer file that is itself a symlink to a file outside the read-buffer directory (G27): without a container, the entry is a symlink and the script reads it, for both celltypes; in a container, the folder entry is a copy in the job directory and the script reads it, and the deepfolder pin fails the job with `CacheMissError` and no container starts; a buffer file that is a symlink to a file inside a read-buffer directory, and one that is a hard link, are linked and read in the container. `seamless-run` with a directory argument declares a `folder` pin, and with result targets a `folder` result; both run on a host that does not see the buffer directory. Deepcell: a deepcell pin on a bash transformer is refused with its message, and no script runs; for a deepcell result, each member's checksum is that of its file's bytes, also for compact JSON and for an `.npy` file; a text file in `RESULT` fails and the message names it; a `RESULT` that is one JSON file fails; the same script with a `folder` result gives the same index |
| `test_wire_format.py` | 3b | Helper B, without any transformation. Reading: each form and each suffix gives the expected Python value; a checksum entry becomes a `Checksum`; a `.bytes` file that starts with the `.npy` magic stays `bytes`; a `.jsonarray` file gives the array that the handlers' payload decoding gives today, for each dtype and for a matrix; members from the index and from the `json` file come back in one dict; a member that is called `value`, `json`, `members` or `__checksum__` is an ordinary key. Refusing: each case of §4.9 fails with a message that names the entry, also a file name with a `/` or with `..`, and a name that is not among the files. Writing: the index of a deepcell pin and of a `checksum` pin, which helper B reads back to the same objects. No file is opened: the test hands over a mapping |
| the handler test files (extended) | 3c | The checksum class of R and of Julia, under both backends: it is made from a 64-hex string, and any other value is an error; it converts to its string; two with the same string are equal; the test of P22 tells it from a plain string. A `checksum` pin arrives as one. A `checksum` result accepts one and accepts a 64-hex string. A checksum object that is returned under a `mixed` or `plain` result fails |
| `test_cli_backend_environment.py` | 3c | For the R and the Julia CLI backend: the launcher list for conda and for each runtime, without running; in a conda environment the interpreter sees `CONDA_PREFIX`; in a container the code runs, the result returns, and a pin from a read folder resolves; `which` is satisfied by a binary that exists only in the environment; `docker` with `conda_environment` is rejected; with `SEAMLESS_CONTAINER_RUNTIME=none` the job fails and nothing runs on the host; a running container carries `seamless.tf=<tf_checksum>` |
| `test_deep_pins.py` | 3a, 3c, 4 | For Python, R and Julia, each under both of its backends: a folder pin is a dict of contents that holds each member's bytes, also when the index's directory is in a read-buffer directory; a deepfolder pin whose members are files in a read-buffer directory is a dict of paths, and each path is the member's buffer file there, with `.zst` or `.gz` for a member that is stored compressed; nothing is created for it, and both backends give the same strings; a deepfolder pin with a member that is only on the hashserver fails, and the hashserver is not asked for it; a deepcell pin is a dict of checksum objects under every backend (`seamless.Checksum`, the R class, the Julia type), and no member is resolved; code that filters the keys of a deepcell pin and returns the rest as a deepcell result gives the same result checksum under both backends, and that checksum is the one of the filtered index; a deepfolder source on a `plain` pin is a dict of hex strings, and the same source on a `folder` pin is a dict of contents; a folder result and a deepcell result from a returned dict, with members that are values and members that are checksum objects; a member that is a 64-hex string is a value in a deepcell result and fails in a folder result, and the same string in the checksum class is a checksum (G29); a deepfolder source on a `plain` pin whose strings are returned unwrapped gives a deepcell of strings; a deepcell result with an array, with `bytes` that start with the `.npy` magic, and with many small members has the same checksum under both backends; a member whose key holds a `/` or is called `json` or `__checksum__` comes back under that key; code that hashes the members of a folder pin gives the same result checksum under both backends of its language. Under a CLI backend in a container: a folder pin and a deepfolder pin both work; with a member whose buffer file is a symlink out of the read-buffer directory, the folder pin still gives that member's bytes and the deepfolder pin fails (G27). A compiled Transformer still refuses a deep pin |
| `test_container_cancel.py` (extended) | 3c, 4 | a hard cancel of a sleeping R, Julia and Python CLI job removes the process group or the container, in `process` and in `spawn` |
| `test_python_cli_backend.py` | 4 | `metavars.BACKEND` on `Transformer("python")`, on `direct` and on `delayed`; the default; a wrong value is refused; the transformation checksum is the same under both backends; the four code modes; each pin celltype; a properly mixed pin and a properly mixed result with seamless-core present; in an image without seamless-core, a job without mixed values runs, and a job with one fails at the helper's import, as does a job with a deepcell pin or a `checksum` pin (G30); in that image, code that returns a deepcell of values runs; an ordinary `mixed` result that is `bytes` starting with the `.npy` magic has the checksum it has in memory; a conda environment other than the process's (the base environment, by path); output arrives while the code runs; a raised exception gives the traceback in the standard error trailer; block code that never assigns the result fails; `process_lock` false lets two jobs overlap; code that submits a nested transformation makes its parent drop the lock; a driver starts while the lock of its process is held; code that defines and calls a `direct` function inside its body works; without Dask, a nested transformation runs in the job's own process; modules and globals are refused |
| `test_python_cli_backend_dask.py` | 4 | On the `remote: daskserver` harness of the bash plan's Phase 5: a Python CLI job whose code submits a nested transformation, as a driver and as an ordinary body. The nested transformation runs on the cluster, and its result is recorded there: a second run of the job finds it in the cache |
| the parity cases | 5 | every case above under both backends, with equal result checksums where both succeed; the one-sided failures listed and asserted |
| `seamless-workflow/tests/test_python_backend_bound.py` | 4 | `ctx.tf.metavars.BACKEND = "cli"` on a Python node runs; changing it back does not run the code again; the value survives a graph save and load; another value is refused when it is assigned, and the node keeps the value it had |

**Images (P10).** The fixture of the bash tests pulls images once and converts
them for apptainer. It gains one image per language, built once per session:

- Python with NumPy, and a second one with seamless-core installed from the
  local repository;
- R with `RcppCNPy` and `jsonlite`;
- Julia with `NPZ` and `JSON`, in a depot that the job's user can read (§9).

A test skips when its runtime or its image is absent. A phase exits only when
its tests ran, not skipped.

## 7. Docs

All in `seamless/docs/agent/contracts/` unless a path says otherwise.

- **New: `language-backends.md` (P9).** It owns the two kinds and their names,
  the refusal of any other name when it is assigned (G26), the table of
  languages, the environment rule for each kind with the
  comparison of G1, the run-time rule of G9, `which`, and the Python CLI
  backend: selection, the job, what the code receives and returns, the
  `.mixed` rule and seamless-core, the need for seamless-core where a
  checksum crosses into the job (G30), parity, the refusals. For deep pins it
  refers to `deep-celltypes.md`. Register it in `docs/agent/README.md`,
  `docs/agent/index.md` and both `mkdocs.yml` files.
- **`environments.md`** keeps the wrapper: the surface, conda, the image, the
  runtimes, the failures, the job directory. It changes where §1.4 says, and
  "a bash transformation" becomes "a CLI backend" where the statement is
  generic. *Handler languages are a separate case* goes. The two checks of
  the specification are stated for dispatch (§4.8): "when the spec is set",
  "when its Transformation is built" and "`seamless-run` refuses the two
  flags together" go. Where the page says that a pin from a read folder
  resolves in a container, it gains the rule of G27 for a buffer file that is
  a link out of what the container binds.
- **`handler-languages.md`**:
  - *Backends*: the names are `"cli"` and `"mem"`, and another value is
    refused when it is assigned. The tools stay as the description of what
    each one runs, and the table of what a backend needs is keyed by language
    and kind.
  - *Environments* refers to the generic rule. "Not specified" goes, and
    Docker is wrapped. The `which` bullet follows §4.4. The parity table
    gains the Docker row.
  - Deep celltypes are accepted under both backends. *What the code
    receives* and *What the code returns* gain the rows of §4.6, in the R and
    Julia forms.
  - The checksum class of each language, with the names of P22: how it is
    made, what it can do, and that it cannot resolve. A deepcell pin holds
    such objects, a `checksum` pin is one, and a member of a deep result is a
    checksum only as such an object (G29, G30).
  - A note says what a containerized Julia or R job needs from its image.
  - *Writing a handler* gains the two public functions (P5): a handler honours
    its `environment` through one of them, or fails.
- **`deep-celltypes.md`**, *How deep values reach a transformer*: the matrix
  of §4.6 replaces the table of that section, where a deepfolder pin is a dict
  of `Checksum` objects. The page gains the table of casts as the way to get
  another form. The rule of §4.7: in bash, a folder pin may be written from
  any buffer source, and a deepfolder pin is on disk or fails. In a
  container, "on disk" means readable there (G27). For a bash transformer, a
  deepcell pin is refused, and a deepcell result holds the bytes of the files
  in `RESULT`, each verified as `mixed` (G15, G16).
  - *The output side* says today that a member is a checksum when it is "a
    `Checksum` or a 64-hex string". It becomes the rule of G29: a member is
    a value unless it is a checksum object, in every language. A deepcell
    pin holds checksum objects in every language (G30).
- **`compression.md`**, *Directory (deepfolder) pins* and *Read-buffer
  materialization*: a deepfolder pin is never transcoded, and each entry has
  the suffix of its stored form after the key (G22). The rule by the pin's
  name holds for a folder pin (G23). Outside bash, a deepfolder pin gives the
  stored paths (G18).
- **`seamless-run-and-argtyping.md`**: a directory argument is a `folder`
  pin, a result with result targets is a `folder` (§4.7), and the two
  environment flags are refused together at dispatch (§4.8).
- **`pins.md`** and **`identity-and-caching.md`**: the `filesystem` entry of
  `__format__`, which no contract page describes today. What §1.8 says of it
  after §4.7, stated as contract.
- **`transformers.md`**: Python builders have `metavars.BACKEND`. The
  environment sentence loses "of a bash transformer".
- **`compiled-transformers.md`**, *Environment*: a conda environment is a
  requirement on the worker process; a Docker image fails when the
  transformation runs.
- **`execution-backends.md`**: *Environments are entered on the executing
  host* speaks of CLI backends, and "never wrapped" becomes the in-memory
  rule. The section on handler languages covers Python. *Drivers* and *Bash
  bodies* say what nested work from a CLI job gets on each backend (§1.7,
  §4.5).
- **`identity-and-caching.md`**: Python's `BACKEND` among the orthogonal
  settings.
- **`cancellation.md`, `transformation-logs.md`, `streaming.md`**: what they
  say of a bash run holds for every CLI backend.
- **`pins.md`** or **`celltypes-and-conversion.md`**: the `.mixed` rule, by
  reference. A `checksum` pin gives a checksum object in every language that
  has objects.
- **No contract page describes the wire format** (P23). The pages say what
  the code receives and returns, and which package a job needs.
- `docs/main/compiled-transformers.md` and `docs/main/hpc.md`, where they
  repeat a changed rule.

Contract pages state the contract only, with no record of what was fixed or
when.

### Release notes

The release notes are the one place that records what changed, as the contract
pages do not (above). Both `RELEASE-NOTES.md` files get the entries below
under *Unreleased*, in this order. The first two are the ones the author asked
for on 2026-10-13. They are **breaks** and are headed as such, not folded into
a list of changes. The drafts are the plan's wording. Adjust them to what
landed.

**1. `seamless-run`: directory arguments and result targets are `folder`, not
`deepfolder` (G12, P16, C10).** The larger of the two. It comes first, under
its own heading.

> A directory argument of `seamless-run` used to be passed to the command as
> a `deepfolder`, and a result with result targets was declared `deepfolder`.
> Both are now `folder`.
>
> **Every `seamless-run` command with a directory argument or with result
> targets gets a new transformation checksum.** Its cached result is not
> found, so the first run after upgrading computes it again, and later runs
> hit the cache. Nothing fails, and the result index and the downloaded files
> are the same as before. For a command that is expensive, run it once
> before you rely on its cache. Anything that stored the transformation
> checksum of such a command, such as a script that looks up its result, its
> logs or its record, must use the new checksum. Old cache entries stay in
> the database, unused.
>
> A `folder` pin is written from the index and its members on whichever host
> runs the command. A `deepfolder` pin was resolved from buffer files on the
> disk of that host only, so a command with a directory argument failed on
> every host that does not see the buffer directory.

What the implementer must check: the entry says "every command" because
`__output__` and `__format__` are both load-bearing (C10). Verify against
the code that a command with a directory argument and no result targets
changes too (P16), and that one with neither does not. Without both
facts, the entry says more or less than is true.

**2. A naked 64-hex string is no longer wrapped as a checksum (G29, C16).**
It comes second, under its own heading.

> A transformer that returns a dict as a `deepcell` or `folder` result used
> to have every member that is a string of 64 hexadecimal characters read as a
> checksum. It is now a value, like any other string. Only a checksum object
> is a checksum: `seamless.Checksum` in Python, and the checksum classes of R
> and Julia. This holds in every language and under every backend.
>
> **Nothing fails for a `deepcell` result.** The members that were strings
> become values, so the result, and its checksum, is another deepcell than
> before. In a `folder` result such a string raises a `TypeError`. To keep
> the old meaning, wrap the string: `Checksum(s)`.

**Also breaks, listed with a line each** (the plan's own findings, not asked
for separately). Each is stated in the notes, with the section that has the
detail:

- In-memory Python code receives different pins for a deep celltype (C12):
  a deepfolder pin is a dict of paths, no longer a dict of `Checksum`; a
  folder pin is always a dict of contents.
- A bash transformer refuses a deepcell pin, and each file of a deepcell
  `RESULT` must parse as `mixed` (G15, G16). A plain text file in `RESULT`
  was a JSON string before and now fails.
- A conda specification together with Docker, and an unknown key of the image
  spec, are refused at dispatch and no longer when the Transformation is built
  or the spec is set (C11).
- `BACKEND` accepts `"mem"` and `"cli"` only, in every language. The handler
  branch was never released, so no earlier value needs a migration note
  (C7).

New features follow the breaks: the Python CLI backend, `BACKEND` for Python,
checksum classes in R and Julia, environments for every CLI backend.

## 8. The proposals and their reasons

**P1 — `tf.metavars.BACKEND` for Python, `"mem"` by default.** Accepted,
with the names of G8.
- It is handler R5 and A4, applied to Python.
- The default must be in memory: every existing Python transformation runs
  that way, and so must one that arrives without its `__meta__`.
- The default is not written into `__meta__`. The handlers write theirs
  because their defaults live in a registration that the executing process
  may lack. Python's default is known everywhere.

**P2 — Parity for Python.** Accepted.
- `BACKEND` is outside the checksum, so a result computed under one backend
  is served under the other. That is only valid with parity.

**P3 — The in-memory rule is checked at run time only.** Accepted, and
generalized by G9.
- A conda specification can only be judged in the process that runs the code.
- With a check at build time, a cached result cannot even be asked for.

**P4 — `which` where the code runs.** Accepted.
- The reason of bash D10 holds for every CLI backend: the host check fails
  for a binary that exists only in the environment.

**P5 — Two shared functions, public.** Accepted. The author confirmed the
reading of §0.
- A registered handler has no other correct way to honour an environment.
- The in-memory rule has four users, and today two inline copies.
- A handler has neither the transformation checksum nor the abort test. They
  are not among its arguments. The alternative is two more handler arguments,
  which every handler author would then have to pass on.
- `execute_cli` takes the whole `environment`, so a handler cannot wrap conda
  and forget Docker, which is S2.

**P6 — `python3 -u runner.py`.** Accepted.
- `python3` is the name that conda environments, the official Python images
  and Debian-based images all have. `python` is absent from some (from
  memory, not checked).
- `-u`: see §4.5.

**P7 — Properly mixed results through the helper.** Accepted.
- G7 rules the pin direction. Without the result direction, Python code under
  the CLI backend could receive such a value and not return one.

**P8 — Modules and globals are refused in the first version.** Accepted.
- Handler R11 allows a backend to fail where the other succeeds.
- They need the semantics of `build_all_modules` inside the runner. They can
  be added later without a change of identity.

**P9 — A page of its own.** Accepted.
- `environments.md` is about the wrapper and `handler-languages.md` about
  handlers. The rule that spans bash, Python, compiled and handlers belongs
  to neither.
- The alternative keeps the rule in `environments.md` and puts the Python CLI
  backend in `transformers.md`.

**P10 — Images built by the fixture.** Accepted.
- Bash R4: the container phases are tested against real runtimes.
- The cost is the network once per session and some minutes of build time,
  most of it for the R packages.

**P11 — Merge order, and one commit of the pages.** Accepted.
- §3 gives the reason for the order.
- The pages of the two parents share files (§1.1).

**P12 — withdrawn.** It made the code of a non-bash CLI backend name a folder
as a bash script does. G17 replaces it.

**P13 — The runner configures its process from `SEAMLESS_REMOTE_CLIENTS`.**
Accepted.
- G11 wants a driver to work as a bash driver does. A bash driver's nested
  `seamless-run` configures itself from that variable. The Python API does
  not (§1.7), so without this step a nested call would run inside the job's
  process, on a Dask worker, with no cache.
- It is the call that `seamless-run` and every worker child already make.
- The alternative makes the Python API configure itself from the variable at
  its first launch, in any process. That also covers a Python script that a
  bash job starts, and it changes the Python API for every user.

**P14 — replaced by rulings.** Outside bash, the paths are the buffer files
as they are stored (G18). In bash, the pin is a directory of symlinks, with no
transcoding for a deepfolder (G22). What P14 proposed for a compressed member
of a *folder* is ruled as G23.

**P15 — G13 is enforced at materialization, without a format change.**
Accepted, the part about `__format__` included.
- G13 is about a pin that has to become a directory. A deepfolder pin of a
  Python transformer resolves nothing as it is.
- Restoring `optional` in `__format__` changes the checksum of every
  transformation that has a folder or a deepfolder pin.

**P16 — A `seamless-run` directory argument is a `folder` pin.** Accepted.
- A directory argument is uploaded so that it can be materialized where the
  job runs. That is what a folder is for, and G12 already says so for the
  result.
- Without it, G13 breaks `seamless-run` with a directory argument on every
  host that does not see the buffer directory.
- The price is C10: new checksums for those commands.

**P17 — Deep results follow the split of G17.** Accepted (G25). G29 rules
what Q10 left open.
- The matrix that the author ruled is about input pins. Results need a rule
  too, and P12 was that rule before it was withdrawn.
- A returned dict is what an in-memory Python transformer gives today, so
  both backends of a language agree without an exception.
- The alternative keeps the bash convention for every CLI backend: the code
  writes a `RESULT` directory. Python code would then return a folder in two
  different ways under its two backends.

**P19 — G27 for an ordinary pin that is linked.** Accepted.
- G27 as the author gave it names folders and deepfolders. An ordinary pin that
  arrives as a file is found by the same lookup and linked by the same code,
  and it is unreadable in a container for the same reason. Phase 3c tests
  that a pin from a read folder resolves in a container.
- "Not on disk" has one meaning for such a pin: it is resolved and written
  (§1.8, step 3). Every writer of today sets `optional`, so no such pin
  fails.

**P20 — What a container can reach is what the wrapper binds.** Accepted.
- G27 needs a test that the host can make before the job starts. The wrapper
  knows its own binds and nothing else.
- `SEAMLESS_CONTAINER_ARGS` is free text for the runtime. Reading binds out
  of it would tie the check to the option syntax of three runtimes.
- The alternative is a host setting that names more bound directories. It
  can be added when a site needs it.

**The wire format (G31, §4.9): the choices of this plan.**
- **The members have a key of their own.** In the author's outline `__json__`
  stood among the member keys, and a member can have that name. Accepted.
- **A file entry declares its encoding, by its suffix.** Accepted. Helper B
  has to rebuild a value, and the content of a file does not say which value
  it is (§4.9, measured). A suffix keeps the entry a plain string, as the
  author's outline has it, and `.mixed` and `.npy` are suffixes already (G7).
- **`.jsonarray` beside `.npy`.** The in-memory backends of R and Julia have
  no package that writes `.npy`: `RcppCNPy` and `NPZ` belong to the CLI
  backends. Both runtimes already write an array as that JSON payload under
  all four backends, so one encoding serves both backends of a language.
- **`RESULT` is a directory.** `execute_bash` removes the job directory
  before it returns. A folder result is the one form whose files it reads
  into memory first, so the format needs no change there.
- **No version number.** The host writes helper A into each job, so the two
  helpers cannot differ.

**P21 — Every result of a Python CLI job travels in the format.** Not ruled.
- An ordinary result needs a declared encoding for the same reason as a
  member. A `mixed` result that is `bytes` is an `.npy` buffer in memory
  (measured). A host that guessed from the content would read bytes with the
  `.npy` magic as an array, and the two backends would differ.
- The host then has one way to read what a Python CLI job returns.
- An ordinary result of R and Julia is left alone. It works and is tested,
  and its marker dicts are outside this plan (§2).

**P22 — The names of the checksum classes.** Not ruled. The author reads
them in Phase 1.
- `Checksum` in Julia is the name that Python has, and a type name of that
  form is what Julia code expects.
- R code runs with the functions in its scope, so they carry a prefix:
  `seamless_checksum` cannot be taken for a function of another package.

**P23 — The format is not a contract.** Not ruled.
- Both ends are written by Seamless and shipped by one host.
- A handler's contract is what it returns to the host, a Python value. A
  handler of a third party meets G29 by returning `Checksum` objects in that
  value.
- A public format would have to be versioned and kept.

## 9. Risks and unverified points

Unverified:

- **Nothing of §4 was run.** Run today: the merge previews (§1.2), the
  serialization probe (§1.5) and the bash folder probe (§1.6).
- **R and Julia were never run in a container.** In particular, Julia finds
  its packages through its depot, by default under `$HOME/.julia`. In a
  container `HOME` is `/seamless-job` and the user is the host user (bash
  D6), so an image must name a depot with `JULIA_DEPOT_PATH` that this user
  can read, and Julia needs a writable first depot entry (from memory, not
  run).
- **`python3` as the portable command name** is from memory.
- **Version skew.** A properly mixed value is written by the seamless-core of
  the host and read by the one in the environment, and back. Whether two
  versions agree on the format is not checked by anything.
- **Nothing was run on Dask.** §1.7 is read from the source, apart from its
  two measured rows. That a process configured by P13 submits to the cluster
  as a nested `seamless-run` does is expected from the shared call, and
  Phase 4 tests it.
- **Whether the Python API uses `SEAMLESS_CACHE` on its own** in a fresh
  process was not checked.
- **Where Dask dispatches** was not read (§4.8). `seamless-run`'s handling of
  a result was searched for the word `deepfolder` and not run (§4.7).
- **§1.8 was read, not run**, apart from the bash probe of §1.6.
- **The result side of parity** is open until Phase 5 (§4.5).
- **The wire format was not run** (§4.9). In particular: what `jsonlite` and
  `JSON.jl` write for `NaN` and for infinity in a `.json` file, and whether
  Python's `json` reads it back to the same value; and how the scope of R
  and of Julia code treats a pin that has the name of a class function.
- **`execute_bash` follows a symlink inside a `RESULT` directory** (read at
  [execute_bash.py:646-651](../../seamless-transformer/seamless_transformer/execute_bash.py#L646-L651),
  not run). A job in a container could then make the host read a host file
  into its result. That holds today for a folder result of a bash
  transformer, and the wire directory inherits it.

Limits:

- **A third-party handler can still ignore `environment`.** The two functions
  make honouring it easy. Nothing enforces it.
- **A handler that calls neither function gets no `which` check** (§4.4). On
  `julia-r-support` the host check covers it.
- **A folder pin outside bash holds every member in memory at once** (G17).
- **Code with a deepfolder pin reads the stored form itself** (G18, G22): it
  decompresses a `.zst` or `.gz` file. Outside bash it gets no file name
  beyond the checksum.
- **A deepfolder pin fails in a container when the buffer file of a member
  is a symlink out of its read-buffer directory** (G27). `seamless-upload`
  in its symlink mode makes such files. A folder pin copies such a member.
- **Code in a CLI job can resolve the members of a deepcell pin under Dask
  only** (G19).
- **Code that returns 64-hex strings as checksums changes without a
  failure** (C16). A deepcell result then holds the strings as values. A
  folder result fails.
- **R and Julia code cannot resolve a checksum** (§4.6). Their class carries
  the checksum and nothing more, so a deepcell pin serves there to select
  and pass on members.
- **A Python CLI job with a deepcell pin or a `checksum` pin needs
  seamless-core** (G30), also where its code only passes members on.
- **The marker dicts of an ordinary R or Julia result stay**, with their
  collision (§1.9, §2). The wire format can carry an ordinary result, so
  they can move to it in a later plan.
- **A deep result under a CLI backend is in the host's memory at once**:
  `execute_bash` reads every file of `RESULT`. An in-memory Python
  transformer holds its returned dict in the same way.
- **G12 and P16 cost cached results** of `seamless-run` commands (C10). The
  release notes lead with it (§7, *Release notes*).
- **A deepfolder pin works only where the buffer directory can be read as
  files**: on the machine of a locally launched hashserver, or with an extern
  client that names a directory (§1.8). On any other host it fails.
- **Every Python CLI run starts an interpreter**, plus `conda run` (about
  1.3 s with `conda`; bash plan, §3.4) or a container start (not measured).
- **A failure under the Python CLI backend is titled *Bash transformer
  exception***, as under the R and Julia CLI backends.
- **In a container, nested Seamless work is not supported** (bash plan,
  §4.11 and §10).
- **A CLI job holds its process for as long as it runs**, unless
  `process_lock` is false (bash plan, §9).

## 10. Notes for the implementer

### 10.1 Working conditions

The handler plan, §10.1, holds here: the repositories, the test interpreter
and `PYTHONPATH`, one pytest process per file, no whole-suite runs unless the
author asks, the Serena symbol tools for code files, and no commit, merge or
push without the author's word.

**Stop and report** when:

- the merge of §3 conflicts, or a test file changes its outcome across it;
- a test of §6 can only pass by weakening G3, G6, G9, G13, G14, G22, G26,
  G27, G29, G30 or parity;
- an existing test or example outside this plan returns 64-hex strings as
  checksums and cannot simply wrap them (C16);
- an image of P10 cannot be built;
- Phase 5 is complete.

### 10.2 Code mechanics

- **The order in `run_transformation_dict` after the merge**: the environment
  block of the bash branch, then the namespace, then the handler lookup of
  the handler branch, then the bash branch, then the handler dispatch. The
  handler dispatch replaces `code`, `namespace` and `inputs`, and the common
  `_execute` call runs it.
- **The checksum for the cleanup registry** must be the `tf_checksum`
  argument of `run_transformation_dict`. `checksum_hex` in that function is
  the code checksum for a Python transformation (§1.5).
- **Handler tests call the handler function directly**, outside any running
  transformation. Both shared functions must work there.
- **A handler puts extra files in the job directory** as pins named
  `META__FILE__<name>`. Pass every ordinary pin as a `Buffer`, as both
  handlers do. A folder pin travels to a CLI job as a directory: write it
  with the shared function of G24, and let the runner read it back into a
  dict (§4.6).
- **Both handlers refuse deep celltypes whatever the backend**: the result
  celltype near their top (`julia.py:45-48` on `julia-r-support`) and the pin
  celltypes in the pin loop. Both refusals go (G17).
- **A pin cast is an Expression** that `_convert_pin_arguments` constructs
  when the Transformation is built. The transformation dict holds the target
  celltype and the result checksum, and nothing of the source celltype.
- **`exec_code`** ([cached_compile.py](../../seamless-transformer/seamless_transformer/cached_compile.py))
  builds the text it executes from the mode and the sorted inputs, and drops
  input names that end in `_SCHEMA`. Factor that step out, so the Python CLI
  backend writes the same text.
- **The runner compiles the code under the path of the code file in the job
  directory.** `direct` and `delayed` read a function's source with
  `inspect.getsource`, and a function that the body defines has no source
  otherwise (§1.7, measured). The in-memory backend gets this from the
  `linecache` entry that `cached_compile` makes (handler plan, §10.2).
- **`set_remote_clients_from_env` does nothing when `SEAMLESS_CACHE` is set**,
  and its Dask step (`_configure_dask_client_from_env`) returns early for a
  worker. The Python process of a CLI job is not a worker.
- **A bound handle is created without `__init__`** (handler plan, §10.3).
  `metavars` on a Python builder must be a property that reads
  `_workflow_backend`, as `HandlerMetaVars` does.
- **A node's `meta` is updated with a shallow `dict.update`.** Write the whole
  `metavars` mapping every time.
- **A handler gets no celltype for a deepcell pin or a `checksum` pin.**
  Neither has a `__format__` entry, so `filesystem` has nothing for it, and
  the handlers take `mixed` (§1.9). Recognize them by the value that the
  namespace gives: a `Checksum`, or a dict whose values are all `Checksum`
  objects. No other pin value holds one. An empty dict needs no decision:
  it is an empty named list or `Dict` either way. Do not add a `__format__`
  entry for them: `__format__` is part of the transformation checksum
  (§1.8).
- **A `Checksum` object in a Python CLI job** can only exist when the code,
  or the seamless-core helper, has imported Seamless. Helper A therefore
  looks the class up in `sys.modules` and imports nothing.
- **An index is never an empty directory.** `execute_bash` fails for an
  empty `RESULT` directory, and `index.json` is always there.
- **`juliacall` gets pins as bytes with a dict of celltypes**, and `ryp`
  reads pin files from its temporary directory (§1.9). Both end in
  `decode_pin`, which is where the two new celltypes of the manifest are
  read as an index.
- **`pack_deep_structure` is called at two places in `run.py`**: for a
  compiled result, and on the common path. Both get the rule of G29 from the
  one function.
- **`HandlerMetaVars.__setattr__` is the one place a handler metavar is
  assigned**, standalone and bound. The check of G26 goes there, before
  anything is written, and into the `metavars` of the Python builders.
- **"Will run in a container" is "the environment has a Docker image".** Such
  a transformation runs in a container or fails (§0). The namespace builder
  can therefore apply G27 to a deepfolder pin without knowing the backend.
  - The directories that a container binds are those of
    `_get_read_folder_directories()` that exist (`build_container_command`
    skips one that does not), and the job directory.
  - Follow a link chain as the container sees it: every step has to end
    inside a bound directory, at the path under which it is bound.
  - An R or Julia handler checks the in-memory rule after the namespace is
    built. With a Docker image and an in-memory backend, the failure of G27
    can therefore come before the refusal of the image. Both are failures.

### 10.3 Things not to do

- No language name `r` or `julia` in `run.py` (handler plan, §10.4). `python`
  and `bash` are native and are named there already.
- No change to `__format__` of a Python transformation, no new dunder, and no
  change to the graph format.
- No check of a backend rule at build time, and none before a cache lookup
  (G9).
- No alias for an old backend name (C7).
- No code of a backend's own that writes a folder into a job directory: use
  the shared function (G24, §4.7).
- No reading of a string as a checksum in a deep result, in any language
  (G29).
- No decoder that is chosen from the content of a wire file, and no member
  key at the top level of an index (§4.9).
- No `pickle`, and no `allow_pickle`, on anything that a job wrote.
- No file that helper B opens by a name from an index. It works on the
  files that it is handed.
- No change to the marker dicts of an ordinary R or Julia result (§2).
- No rule for a pin that depends on what it was cast from (§4.6, *The
  casts*).
- No transcoding of a deepfolder member, and no copy of one (G22). That
  holds under G27 too: such a deepfolder pin fails.
- No link into a read-buffer directory for a buffer file that the job's
  container cannot read (G27).
- No resolving of a deepfolder member through a buffer server, anywhere
  (G13). Look in the read-buffer directories only
  (`_find_filesystem_path`, `_get_read_folder_directories`).
- No check of a specification when it is set or when a Transformation is
  built (G14).
- No fallback encoding in the Python runner. Raise.
- No import of Seamless in `runner.py` outside the seamless-core helper and the
  configuration step of P13. A job that needs neither runs without Seamless.
- No check for seamless-core before the job runs (G7).
- No extension of handler R9 to Python or compiled bodies.
