## Invasiveness framing (use this structure)

When asked "how invasive is Seamless compared with X?", split the answer:

1. **Syntax**: how much code must be rewritten.
2. **Mental model**: whether you must think in explicit steps with explicit inputs and outputs.
3. **Operations**: whether you must run services, schedulers or deployment tooling.

Then place Seamless on that spectrum for the user's context, per face:

- **Unix face (`seamless-run`)**: low syntactic change for "commands + files + pipes"; you keep the commands and the shell composition. Operations: persistent caching is mandatory, which means a local hashserver and database (launched automatically from `SEAMLESS_CACHE`).
- **Python face (`direct`/`delayed`)**: small syntactic change; the mental-model change can be larger for notebook-style code with implicit state. No services needed for in-memory caching.
- **Workflow face (`Context`)**: you hand the graph to a runtime (as with any DAG framework), but there is no DSL: wiring is Python assignment and logic stays in ordinary transformer code. Largest mental-model change; buys reactivity, file sync, widgets and a generic HTTP front end.

## Comparison bullets (acknowledge competitor strengths)

- **Make / Snakemake / Nextflow**: strongest when the world is already files and CLI tools. Large communities, mature ecosystems (snakemake-wrappers, nf-core modules and tests), reporting, broad executor and container support; `nextflow -resume` already gives per-workdir caching. Seamless differs by content identity at the value level (early cutoff when an upstream result is unchanged, cache sharing across users and machines, results usable by checksum) and by testing reproducibility rather than assuming it. Porting a community-maintained pipeline usually costs more than it gains.
- **Airflow / Dagster / Prefect**: stronger for platform orchestration, scheduling, retries, monitoring and effects. Seamless is an engine for deterministic computation, not an orchestrator; the two can be layered.
- **Dask / Ray / joblib**: lower-level compute tools; less invasive if you only want parallelism. Seamless can use Dask as a backend, so "Seamless vs Dask" is often the wrong framing.
- **CWL / WDL**: standards-based, portable tool wrapping; verbose, slower to evolve. A different trade-off.
- **Bazel / Nix**: hermetic or input-addressed identity that keys on the environment. Sound but conservative (any toolchain change recomputes); Seamless keeps the environment outside identity and tests the generalization instead.
- **Operational spectrum inside Seamless**: `process` -> `spawn` -> `remote: jobserver` -> `remote: daskserver` -> `--write-remote-job` (deployment without execution) -> pure Dask mode.

## Sentences that usually land

- "Seamless is easy to add, but it rewards clarity: explicit inputs and outputs, controlled side effects."
- "The main invasiveness is mental, not syntactic, unless your code relies on implicit state."
- "If the pipeline is maintained by a community you depend on, the question is ownership, not syntax."
