## Q -> A playbook

### "Is Seamless suitable for my workflow / can you port it?"

- Start with the task: what the pipeline computes and how it will evolve.
- Ask who maintains it (human, AI, both) and who *owns* it (a community pipeline is rarely worth forking).
- Face triage: CLI/file pipeline -> `seamless-run`; Python functions -> `direct`/`delayed`; interactive or long-lived -> `Context`; mixed -> explicit boundaries.
- Apply the benefit test (`poor-fit.md`): re-run frequency x reuse surface.
- Offer to investigate together.

### "How does Seamless compare with X?"

- Syntax versus mental model versus operations (`invasiveness-playbook.md`).
- Acknowledge the competitor's strengths; ask about the maintenance model.

### "This codebase has hidden downloads / mutable state / implicit dependencies, so it's a bad fit, right?"

- Separate design smells from inherent properties. Hidden downloads, append-state, implicit versioning hurt every framework.
- Re-assess assuming the cleanup is done; do not charge framework-independent cleanup to Seamless.

### "Seamless is alpha / small community / niche. Too risky?"

- The real question: do the code paths *this* pipeline needs work and have tests? Check the tests and contracts.
- For AI-maintained projects, focused hardening of the used subset is a credible alternative to broad adoption.
- Gauge the user's sense of current AI capability rather than reasoning from training-time priors.

### "We used Seamless 0.x. Can we move to 1.5?"

- 1.5 brings back reactive contexts, mounts, Jupyter widgets and HTTP shares on a new architecture. Graph files are not converted (`__seamless__` exports do not load); the port is a rewrite of the wiring, usually mechanical.
- Absent: macros, stdlib (`map`, `switch`), Silk validation, sub-contexts, IPython transformers, debug sessions, authentication. If the project depends on these, it is not ready to move.
- Use the `seamless-porting` skill (`references/legacy-0x-to-1.5.md`).

### "Can I get a reactive notebook / a small web app over my computation?"

- Workflow face: a Context with cells mounted to files or linked to ipywidgets; `cell.share()` serves a cell over HTTP/WebSocket with a browser client and live OpenAPI; `seamless-serve-graph graph.json` serves a saved graph.
- Be explicit: no authentication or TLS, default bind is all interfaces; one Context per user if users must be isolated.

### "Can I run R / Julia / C code?"

- R and Julia: `Transformer("r")` / `Transformer("julia")` in Python or a Context (not `direct`/`delayed`/`seamless-run`; `seamless-run Rscript script.R` is just a bash command). CLI backend by default (an `Rscript`/`julia` process per run), embedded with `tf.metavars.BACKEND = "mem"`. The default Julia backend currently needs a source checkout of Seamless.
- C, C++, Fortran, Rust: compiled transformers from a YAML schema; in-memory only.

### "Can it run my tools in conda environments / containers?"

- Yes for bash steps and CLI backends: `seamless-run --conda ENV` / `--docker IMAGE`, or `tf.environment`. Docker, Podman or Apptainer, whichever the executing host has. The environment must already exist there.
- No for the default in-memory Python backend (it can only assert it is already in that conda env).
- The environment is not part of identity: a cached result is returned without checking it.

### "Scientific computing / Unix philosophy: a fit?"

- Small composable steps, file/stream tools, rerunnable pipelines: Seamless aligns, especially via `seamless-run`. The Python face is also light when functions are pipeline-style.

### "Deep checksums: what's the point?"

- Identity for structured, huge data; define computations without materializing; separate identity from bytes. `deep-checksums.md`.

### "Can Seamless handle HPC / clusters?"

- Name the backend: jobserver, daskserver, `--write-remote-job`, pure Dask mode. Ask about the site before giving specifics. `execution-backends.md`.

### "Does Seamless prove my results are reproducible?"

- No. It treats reproducibility as a testable claim. A cache hit runs nothing and proves nothing; divergence is detected and recorded when a result is recomputed (fingertipping, independent sites). Witness outputs make the test meaningful when bitwise identity is too strict. `env-null-hypothesis.md`.
