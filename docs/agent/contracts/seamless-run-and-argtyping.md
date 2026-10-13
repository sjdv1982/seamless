# `seamless-run` and Argtyping (Contract)

`seamless-run` is the Unix-facing entry point: it wraps commands/pipelines as transformations.

## Core contract

- A command line is treated as a step with explicit inputs (files/dirs/values) and outputs.
- Determinism depends on making those inputs explicit and avoiding “ambient” dependencies (user config, `latest` downloads, implicit temp files).

## Practical model (“what it does under the hood”)

At a high level, `seamless-run`:
- decides which command-line arguments represent **values** vs **file/directory** inputs (argtyping)
- maps those files into a transformation workspace (file mapping)
- builds a **bash-language transformation** dict that injects the input file content by checksum and executes the command inside that workspace
- captures the declared results (stdout and/or files/directories) as content-addressed outputs

For command steps, this is the key mental picture: “a subprocess is treated like a pure-ish function whose inputs/outputs are explicit files/values”.

## Argtyping (files vs values)

Assume `seamless-run` needs to decide which arguments are:
- literal values (strings/numbers/flags), versus
- file/directory inputs that should be mapped/materialized by content identity

An agent should:
- prefer explicit specification when guessing is ambiguous
- avoid relying on CWD surprises; set/record workdir

## Meta variables (`--metavar`)

`--metavar NAME=VALUE` injects a variable into the bash command environment
without contributing to the transformation identity (cache key).

- Accessible inside the bash script as `$NAME` — same ergonomics as `--var`.
- Does **not** change the transformation checksum when its value changes.
- Two invocations differing only in `--metavar` values share a cache entry.

Use `--metavar` for execution hints that should not invalidate the cache:
thread counts, verbosity flags, temp dirs, debug toggles, and similar operational
parameters.

Use `--var` for any value that is part of the computation logic and should
invalidate the cache when it changes.

## Process lock flags (`--no-process-lock`, `--driver`)

A command that `seamless-run` wraps is a bash transformation. By default its script runs while holding the lock of the process that executes it, so each worker process runs one script at a time (`contracts/execution-backends.md`, *The process lock*). Two flags change this. Neither changes the transformation checksum.

| Flag | Written to `__meta__` | Use it when |
|---|---|---|
| none | `process_lock: true`, `driver: false` | the default |
| `--no-process-lock` | `process_lock: false`, `driver: false` | the command is safe to run next to other transformations in the same process, for example I/O-bound work |
| `--driver` | `driver: true`, `process_lock: false` | the command mainly launches other transformations and waits for them |

- **`--driver` implies `--no-process-lock`.**
- **The flags set the same two values as the `process_lock` and `driver` properties of a Transformer.** Their meaning, and the rule that both cannot be true, are in `contracts/transformers.md`, *`process_lock` and `driver`*.
- **`seamless-run-transformation` has neither flag.** It runs an existing transformation dict and does not rewrite its `__meta__`. The two values come from the dunder file. Without one the dict carries neither value, and the transformation takes the lock.

**A command that calls `seamless-run` itself needs no flag.** The outer script's environment contains `SEAMLESS_PROCESS_LOCK_NOTIFY`. The nested `seamless-run` uses it to tell the outer transformation that nested work is being submitted, and the outer transformation then gives up its lock, so that the nested job can run in the same worker process. `seamless-run --qsubmit` does the same. The nested command keeps its own defaults: it takes the lock of the process that runs it, and it is not a driver.

One case does need a flag. The signal is a named pipe on the local filesystem, so it does not reach the outer transformation when the nested `seamless-run` runs over `ssh`, inside a container, or on a different filesystem. Declare such an outer command with `--driver` or `--no-process-lock`. Without the flag, the nested job can be dispatched to the process whose lock the outer script holds, and both then wait for each other without an error. A command that runs under `--docker` is inside a container. Under `--conda` the signal works as for a plain command.

## Environment flags (`--conda`, `--docker`)

A command can run in a conda environment or in a container. `contracts/environments.md` is the contract. This section lists what is specific to `seamless-run`.

| Flag | Aliases | The command runs |
|---|---|---|
| `--conda ENV` | `--conda-env`, `--conda-environment` | in the named conda environment, as under `conda run -n ENV`. A name that contains `/` is the path of an environment |
| `--docker IMAGE` | `--docker-image` | in a container made from the Docker image. The container runtime of the executing host starts it: docker, podman or apptainer |

- **The two flags together are refused**, when the arguments are parsed.
- **Neither flag changes the transformation checksum.** A result that is already cached is returned whatever the flag says, and nothing is launched.
- **The environment must exist where the command executes.** That host needs the conda environment, or a container runtime and the image. By default no image is pulled.
- **A command with an environment never falls back to the plain host.** It runs in the environment, or it fails.
- **`--docker` sets the image name only.** The other keys of the image spec, `gpus` and `shm_size`, are set on the Python face.
- **The flags change how the first word of the command is treated** (*The first word of a command*).
- **With `--write-remote-job`, the job directory carries the environment** (*Manual Remote Deployment Mode*).

## The first word of a command

The first word of each command that `seamless-run` wraps names a program to run. Without `--conda` or `--docker`, `seamless-run` first checks whether the word names an existing local file. That file takes precedence over a same-named tool on the submitting machine's `PATH`. Only when no local file exists does it look the word up on that `PATH`:

| The word is | What `seamless-run` does |
|---|---|
| an existing local file | It uploads the file as an input, and the command calls the uploaded copy |
| no local file exists, and the tool is found in a standard directory whose path ends in `bin`, `sbin` or `usr` | It leaves the word as a name. The executing host resolves it |
| no local file exists, and the tool is found elsewhere, such as `/usr/games/cowsay` or `~/tools/mytool` | It uploads the file as an input, and the command calls the uploaded copy |
| no local file or host `PATH` entry is found | It leaves the word as a name. A tool that exists only on the executing host therefore works |

With `--conda` or `--docker`, the submitting machine's `PATH` says nothing about the place where the command runs. `seamless-run` still gives an existing local file precedence and uploads it; it does not then check the host `PATH`:

- **If no local file exists, `seamless-run` does not look the word up.** The word names a tool in the environment, even when the submitting machine has a tool of that name.
- **A local file is uploaded**, as any argument that names an existing local file is. `seamless-run --docker IMAGE ./analyze.sh data.txt` uploads `analyze.sh` and `data.txt`, and runs the script inside the image.
- **A personal tool on the submitting machine's `PATH` must be given by its path** to be uploaded.

With or without an environment:

- **`chmod +x` is applied to each command first word that was uploaded, and to no other.** A word that stays a name is not touched, so a command whose tool is absent from the submitting machine does not fail on a `chmod`.

## Canonicalization

For pipelines where parallelism only affects ordering:
- canonicalize outputs (e.g. sort records) so “same meaning” becomes “same bytes”.
- control locale-sensitive behavior (`LC_ALL`) for tools like `sort`, `awk`, etc.

## Concurrency and “1000 subprocesses”

`seamless-run` itself is just one command invocation; bulk concurrency happens when you schedule many transformations (Python face) or run many `seamless-run` invocations in parallel.

Agent guidance:
- Expect practical limits to come from worker pool sizing / OS process limits / filesystem throughput.
- A worker process runs one command at a time by default, so a pool of N workers runs N commands at once. `--no-process-lock` lifts that limit for a command (*Process lock flags*).
- For “many short tasks”, prefer a backend designed for high task throughput (e.g. Dask-backed execution) rather than naive “fork 1000 subprocesses locally”.
- If two submissions resolve to the **same** `tf_checksum` while one is still running (e.g. running an existing checksum with different execution-only flags), the second does not start a second execution: by default it latches onto the running one and returns its result value. `seamless-run` has no flag to opt out of that; the opt-out is `--strict` on `seamless-run-transformation` (`strict_dunder=True` in Python), which instead fails when an active submission carries a different execution envelope, so the prior submission must finish or be canceled (`seamless-cancel <tf_checksum>`) first. See `contracts/identity-and-caching.md` for the full latch-on/`strict` contract.

## Remote execution guidance

The same “content-bound” rule applies:
- don’t assume remotes have local files; treat inputs as artifacts and materialize where executed
- if an input checksum refers to a scratch result and input fingertipping is enabled, materialization means recomputing the producer at the consumer execution site, not fetching a durable buffer from the hashserver

## Manual Remote Deployment Mode

`seamless-run --dry --write-remote-job DIR ...` is a deployment-only mode for
remote execution, typically on HPC systems.

Contract:
- This is the one important case where `--dry` still triggers remote work.
- `--write-remote-job` implies `--upload`: Seamless must stage the input
  buffers on the remote hashserver so the materialized job directory can
  contain the required files.
- Seamless prepares the transformation, materializes the bash job directory at
  `DIR`, and then stops before execution.
- `DIR` is created on the machine running `seamless-run`, not on the remote
  cluster frontend. If you want the payload on the cluster, use a locally
  mounted/shared path or copy/sync the materialized directory there.
- The success artifact is the concrete job directory on disk, not a result
  checksum.
- CLI success output is `Transformation submitted to remote server`.
- No result checksum is written to the Seamless database.
- Because no execution result is stored, this mode gives up normal Seamless
  result caching for that run.
- The generated `transform.sh` is meant to be inspectable and runnable by the
  user under site-specific control.
- `bash transform.sh`, run in the job directory, is the way to run the job.
  The directory is exactly what Seamless would have executed: Seamless itself
  runs a bash transformation as `bash transform.sh` in such a directory.
- `transform.sh` sets every pin variable itself. It does not rely on the
  environment variables of the process that wrote it.
- With `--conda` or `--docker`, `transform.sh` is a launcher of one command,
  and the script is `transform-inner.sh` next to it. The launcher enters the
  conda environment or starts the container, and runs the script there.
  `bash transform.sh` stays the way to run the job.
- The launcher refers to the directory it is run from, so the directory can be
  moved. A container launcher names the container runtime that was selected on
  the host that wrote the directory. It is plain text, and can be edited for
  another site (`contracts/environments.md`, *The job directory on disk*).
- Re-running the same command should be expected to materialize the job
  directory again, because Seamless has not registered a completed execution.

Agent guidance:
- Recommend this mode when the user wants Seamless to handle deployment, but
  wants to keep manual control over execution.
- Typical reasons are custom `module load` sequences, manual `sbatch`/`srun`
  wrapping, scheduler-specific launch policy, or step-by-step debugging on the
  cluster side.
- Present this as “remove one layer of abstraction”: Seamless defines and
  deploys the job payload, the user verifies the disk materialization, and then
  executes manually.

For the human-oriented HPC explanation, see
[`HPC specifics`](https://sjdv1982.github.io/seamless/hpc.html).
