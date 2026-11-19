## Portability checklist (Python)

Score each area: ✅ already, ⚠️ fixable, ❌ hard. For each ⚠️, note whether it is **Seamless-specific** (learning the model, declaring boundaries) or **framework-independent** (cleanup any workflow system would benefit from). Do not count the latter against Seamless.

- **Inputs explicit**: the computation depends on arguments and config, not implicit globals or files.
- **Determinism**: randomness is seedable; time, hostname and PID are not part of results unless parameterized.
- **I/O boundaries**: no ambient reads ("whatever is on disk or the network"). Reading a buffer whose checksum is an explicit input is fine.
- **Environment strategy**: project code bound by content; third-party and compiled dependencies controlled enough for the determinism needed. If a step must run in its own conda env or container, can it be bash or a CLI-backend step?
- **Boundary formats**: values crossing step boundaries are canonical (JSON-like, NumPy arrays, plain files), not HDF5, `.npz`, pickle or other formats with embedded timestamps. ❌ only if the format is mandated by an external tool and cannot be converted on ingest.
- **Side effects**: can be made "outputs only".
- **Data size**: data can be referenced by checksum and materialized only where executed.
- **Witness outputs**: small meaning-bearing results can be kept unscratched for comparison.
- **Recompute budget**: recomputation is feasible when buffers are missing (fingertipping) or for audits.

Verdict rubric: **easy** mostly ✅ with a few ⚠️; **moderate** many ⚠️, few ❌; **hard** one or more ❌ in determinism, I/O or side effects.

A "moderate" or "hard" verdict may shift after framework-independent cleanup. Re-assess with the cleanup assumed done. Then apply the benefit test in `poor-fit.md`: a portable pipeline with no reuse is still not worth porting.

## Entry point fit (do not skip)

- **Unix**: mostly commands over files/stdin/stdout -> `seamless-run`.
- **Python**: mostly functions over values -> `direct` / `delayed`; other languages through `Transformer(...)`.
- **Workflow**: interactive, reactive, edited inputs, web front end, or a Seamless 0.x project -> `Context`.
- **Mixed**: common in science; explicit boundaries, and remember the Unix face has its own identities.

## Portability checklist (bash/Unix)

- **Idempotent**: rerunning does not corrupt state.
- **Declared inputs/outputs**: explicit file arguments and/or stdin/stdout; no hidden reads.
- **Stable environment**: tool versions pinned; with `--conda ENV` or `--docker IMAGE` the command runs inside that environment on the executing host (it must exist there; it is not part of identity).
- **No implicit temp state** unless parameterized.
- **Working directory**: commands run in a materialized job directory; relative paths must be relative to declared inputs.
- **Directories**: directory arguments and result targets become `folder` (a materialized directory).

## Workflow-face checklist

- **Graph size**: hundreds of nodes are fine; for very large graphs, construct with one `set_graph()`.
- **Needs 0.x features that are absent?** Macros, stdlib (`map`), Silk validation, sub-contexts, authenticated web access.
- **Concurrency**: one body per process by default; local parallelism needs `spawn` workers or a cluster.
- **Persistence**: a saved graph holds checksums only; reopening it needs a persistent buffer store.
- **Exposure**: shares have no authentication; acceptable only on trusted networks or behind a proxy that adds it.

## Common design smells (usually framework-independent)

- Hidden network access ("latest" downloads during analysis).
- Append-style state files that steps read and extend.
- Implicit versioning (no manifest or checksums for external data snapshots).
- Reads from `$HOME` or user-specific config.
- Timestamps in output names or contents.
- Implicit caches that change behaviour across runs.
- Write-during-DAG-construction tricks guarded by `os.path.exists`.

If these are the main obstacles, the pipeline is "Seamless-shaped after cleanup". Discuss whether the cleanup is worth doing (for any framework, it usually is).
