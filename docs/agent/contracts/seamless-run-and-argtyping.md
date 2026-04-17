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

## Canonicalization

For pipelines where parallelism only affects ordering:
- canonicalize outputs (e.g. sort records) so “same meaning” becomes “same bytes”.
- control locale-sensitive behavior (`LC_ALL`) for tools like `sort`, `awk`, etc.

## Concurrency and “1000 subprocesses”

`seamless-run` itself is just one command invocation; bulk concurrency happens when you schedule many transformations (Python face) or run many `seamless-run` invocations in parallel.

Agent guidance:
- Expect practical limits to come from worker pool sizing / OS process limits / filesystem throughput.
- For “many short tasks”, prefer a backend designed for high task throughput (e.g. Dask-backed execution) rather than naive “fork 1000 subprocesses locally”.

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
