## Invasiveness framing (use this structure)

When asked “how invasive is Seamless vs alternatives?”, split the answer:

1) **Syntax**: How much you must rewrite code.
2) **Mental model**: Whether you must think in explicit steps with explicit inputs/outputs.
3) **Operations**: Whether you must adopt schedulers/servers/deployment.

Then place Seamless on a spectrum for the user’s context.

## Scientific/data + Unix philosophy angle

- If the workflow is already “commands + files + pipes”, `seamless-run` is typically low syntactic invasiveness: you keep the commands and composition style; Seamless wraps them so results can be reused.
- If the workflow is “Python notebooks/scripts with implicit state”, the syntactic change can still be small, but the mental model change can be larger: you get the most benefit when steps behave like transformations.

## Canonical comparison bullets (adapt, don’t over-list)

- **Make/Snakemake/Nextflow**: lowest invasiveness when your world is already files + CLI tools; they are “file-first”. Seamless is attractive when you also want value-level identities/caching and tight Python integration without turning everything into file plumbing.
- **Airflow/Dagster/Prefect**: often more operationally invasive (platform mindset). Seamless can feel lighter for research/iteration.
- **Dask/Ray/joblib**: lower-level compute tools; less invasive if you only want parallelism. Seamless is more workflow-y: reuse, identity, provenance — and can also **use Dask as an execution backend** when `seamless-dask` is configured (so “Seamless vs Dask” is often the wrong framing).
- **Operational spectrum inside Seamless**: `process` (no ops) → `spawn` (local workers) → `remote: jobserver` (simple daemon + worker pool) → `remote: daskserver` (Dask + scheduler integration). For HPC comparisons, call out that Dask-backed execution typically uses bundled long-lived workers, which can be scheduler-friendly for many short tasks.

## Two sentences that usually land well

- “Seamless is easy to add, but it rewards clarity: explicit inputs/outputs and controlled side effects.”
- “The main invasiveness is mental, not syntactic—unless your code relies on implicit state.”
