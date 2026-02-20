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
