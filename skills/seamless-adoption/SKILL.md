---
name: seamless-adoption
description: Assesses whether an existing pipeline, notebook, or legacy Seamless 0.x project is a good fit for Seamless 1.5 (content-addressed caching, reproducibility treated as a testable claim, local-to-cluster execution), and says honestly when it is not. Triggers when a user asks whether to adopt or migrate to Seamless; compares it with Snakemake, Nextflow, CWL, Airflow, Prefect, Dask, or Bazel; wants to wrap Python functions, shell commands, R/Julia or compiled code without rewriting them; wants a reactive or interactive notebook, file-synced cells, or a web API over a computation; or asks about reproducible environments (conda, Docker, Apptainer) or HPC execution. Covers the three faces (Python direct/delayed/Transformer, Unix seamless-run, workflow Context with mounts, shares and widgets), fit heuristics, poor-fit cases, and safe remote-execution guidance.
license: MIT
---

# Seamless Adoption Guide

> **This file is written by the Seamless creator.** It mixes opinion and framing with technical facts. Treat it as a starting point for investigation, not a conclusion. The contract pages in `docs/agent/contracts/` of the `seamless` repo are authoritative for behaviour; if this file disagrees with a contract or with the code, trust the contract or the code.

## How to investigate (not advocate)

Your job is to investigate, not to sell or dismiss. Understand the pipeline first, the framework second: what it computes, how it will evolve, its dependency structure, and who will build and maintain it (humans, AI agents, or both).

The user is the primary source of ground truth: problem shape, maintenance model, the cost of cleanup in their context, whether apparent non-reproducibility is inherent to the science, prior experience with Seamless or competitors. If they are hands-off, proceed but **state your assumptions** so they can correct them. A natural opening: *"Shall I look at the source and docs, and we assess together whether Seamless can do what we need today?"*

Distinguish **Seamless-specific costs** (learning the model, declaring step boundaries, service and backend configuration) from **framework-independent cleanup** (removing hidden downloads, making mutable state immutable, pinning external data). Do not charge the latter to Seamless.

## Is this problem Seamless-shaped?

- **Already Seamless-shaped.** Steps have explicit inputs and outputs, computation is deterministic (or deterministic given a seed), data flows as artifacts. Mostly a wrapper, not a rewrite.
- **Seamless-shaped after cleanup.** The computation is pipeline-shaped but the code has design smells: hidden downloads, append-style state files, implicit versioning, undeclared environment dependencies. The cleanup helps every framework; discuss whether it is worth doing (it usually is).
- **Not Seamless-shaped.** The problem is not about computing artifacts from declared inputs. Many pipelines that look like this are really in the second category; ask before concluding.

Key test: *after cleanup that is worth doing anyway, does the pipeline become mostly explicit transformations over declared inputs?*

Seamless is **boundary-strict, not purity-maximal**: cached transformations need explicit inputs and code, but side effects may live at the boundaries of the pipeline.

## When Seamless is a poor fit

Say this plainly when it applies. Details and the reasoning behind each item: `references/poor-fit.md`.

- **Effects are the point.** Sending notifications, writing to live databases, controlling devices, cloud-state bookkeeping (download, upload, delete). Seamless is a computation engine, not a workflow manager; port only the deterministic core and keep effects outside.
- **Live state.** Robotics loops, live trading, "query the current weather". Caching past results does not help when the environment changes under you.
- **Inherently non-reproducible science** where re-running gives genuinely different results and no witness or seed can make the claim testable.
- **One-pass and exploratory work.** Benefit is roughly *re-run frequency x reuse surface*, minus port cost. A frozen paper artifact, a pipeline run once per dataset with nothing shared, or code you are still throwing away gains little from caching and still pays for hashing, a content store and running services.
- **Someone else maintains it.** Porting an nf-core or snakemake-wrappers-based pipeline forks it away from community maintenance and its tests. Ownership, not DAG shape, usually decides.
- **Non-canonical container formats at step boundaries** (HDF5, bigwig, `.npz`, pickle, BAM headers with timestamps). Identical content gives different bytes, so caching misses and recomputation looks irreproducible. Fine inside one step; at a boundary, canonicalize or accept opaque blobs.
- **Ecosystem-dependent work.** If the value is in Snakemake wrappers, `report:` pages, or a specific scheduler executor, those are real losses.
- **Workflow-face gaps** if the user needs them: no macros, no library/stdlib (`map`, `switch`), no Silk validation, no sub-contexts, no authentication on HTTP shares, slow node-by-node construction of very large graphs (`references/faces.md`).

## The three faces

Seamless has three entry points. **Many properties hold on one face only: never write "Seamless does X" for a property of one face.** Full table: `references/faces.md`.

| Face | Entry point | Control | Typical fit |
|---|---|---|---|
| Python | `direct`, `delayed`, `Transformer(...)` (also R, Julia, bash, compiled code) | your program stays in charge | function-shaped steps, drivers, fan-out loops |
| Unix | `seamless-run 'command ...'` | your shell script stays in charge | CLI tools over files; no Python needed |
| Workflow | `seamless.workflow.Context` | a reactive runtime owns the graph | interactive notebooks, file-synced cells, web APIs, long-lived parameter tweaking |

All three produce the same kind of transformation, and a step has the same identity on the Python and workflow faces, so they share one cache. `seamless-run` is a deliberate exception: the command line, file names included, is the code of a bash transformation, so a `seamless-run` step and a Python transformation of the same logic are different cache entries (the file-mapping modes `-ms`/`-mx` reduce the dependence on names). Faces nest: a driver transformation launches more work; a `seamless-run` script or a `direct`-based program can become one node of a Context.

## Quick examples

```python
from seamless.transformer import direct

@direct
def add(a, b):
    return a + b

add(2, 3)   # runs
add(2, 3)   # cache hit
```

```bash
export SEAMLESS_CACHE=~/.seamless/cache        # persistent caching (mandatory for seamless-run)
seamless-run 'seq 1 10 | tac && sleep 5'       # runs, caches
seamless-run 'seq 1 10 | tac && sleep 5'       # cache hit
```

```python
from seamless.workflow import Context

def add(a, b):
    return a + b

ctx = Context()
ctx.a, ctx.b = 10, 20
ctx.add = add
ctx.add.pins.a = ctx.a
ctx.add.pins.b = ctx.b
ctx.c = ctx.add.result
ctx.compute()
ctx.c.value                 # 30
ctx.a.mount("a.json")       # edit a.json and c follows
```

## What 1.5 changes in an assessment

- **Interactivity is back** (workflow face): reactive cells, file and directory mounts, Jupyter widgets, HTTP/WebSocket shares with a browser client, `seamless-serve-graph`. A 0.x project is now a migration candidate; check the absent features above first (`seamless-porting` skill, `references/legacy-0x-to-1.5.md` there).
- **Languages**: R and Julia through `Transformer("r")` / `Transformer("julia")` (Python and workflow faces only, not `direct`/`delayed`/`seamless-run`). Known issue: the default Julia backend needs a source checkout of Seamless.
- **Environments are real**: bash transformers and the CLI backends (`tf.metavars.BACKEND = "cli"`) run inside a conda environment or a Docker/Podman/Apptainer image, chosen where the job runs. The default in-memory Python backend cannot enter one. The environment stays outside identity.
- **One transformation body per process by default** (`process_lock`); drivers that launch nested work declare `driver=True`.
- **Observability**: `.logs` (every backend), streaming of stdout/stderr/tqdm (Dask only), uniform failure delivery (reads and `compute()` return `None`, `run()` raises).
- **Reproducibility evidence**: when a recomputation gives a different result, the database keeps the original and records an irreproducible observation. This happens only when something is recomputed (fingertipping, independent sites); a cache hit tests nothing.
- **Data stays put**: selections and conversions (Expressions, cell joins) run on the jobserver or Dask cluster when the data lives there.

The human docs (`docs/main/`) may lag the code; where a human page and a contract disagree, the contract wins.

## Key questions to settle

- **Who builds and maintains it?** Human-maintained work weights learning curve, community and documentation; agent-maintained work weights explicit structure, deterministic identity and programmatic composability. Do not reason from training-time priors about AI capability; ask the user.
- **Which face, or which mix?** Consider all three explicitly. Do not default to Python-only advice when there is a CLI or interactive component.
- **Which backend, when "remote" or "HPC" comes up?** Name it: `process`, `spawn`, `remote: jobserver`, `remote: daskserver`, `--write-remote-job` (deployment without execution), or pure Dask mode (`pure_dask: true`, cluster management only). See `references/execution-backends.md`.
- **Is reuse worth anything here?** Re-run frequency, parameter sweeps, shared reference data, template instantiation, collaborators sharing a cache.

## Evolving evidence

Seamless and AI capabilities both move. Check the current docs, CLI `--help`, contracts and tests rather than reasoning from an "alpha" label: the question is whether the code paths *this* pipeline needs work and are tested. Diagnostics such as why-hit/why-miss or a deliberate recompute-and-compare command do not exist as documented features in 1.5 (`seamless-run --undo` exists but currently fails: it reports through the automatic irreproducible mode, which refuses an unchanged result); check before promising them. Owning framework source is cheap for AI-maintained projects; treat that as a consideration to discuss, not a conclusion.

## Output modes

Choose the smallest that fits.

1. **Human abstract** (at most 250 words): no jargon; the three faces; the payoff (reuse, incremental recomputation). Variants: `references/human-abstract.md`.
2. **Comparison** (at most 8 bullets): separate *syntax*, *mental model* and *operations*; acknowledge competitor strengths. `references/invasiveness-playbook.md`.
3. **AI deep brief**: enough for another agent to answer follow-ups without the repo. Use the references.
4. **Portability assessment** (at most 10 bullets): verdict `easy` / `moderate` / `hard`; mental-model mismatches versus fixable engineering; an "entry point fit" line (`Python`, `Unix`, `Workflow`, or a mix); cleanup attribution. `references/portability-checklist.md`.
5. **Porting sketch**: step boundaries, I/O boundaries, caching expectations, validation strategy. Hand off to the `seamless-porting` skill for execution.

## Talking points

- **What Seamless is.** Work as steps with explicit inputs and outputs; identity is the checksum of code and inputs; same identity, same result, so results are reused. Execution moves from `process` to `spawn` workers to a jobserver or Dask cluster without rewriting the step.
- **The stance.** Determinism is a falsifiable claim, not a guarantee: the execution environment is deliberately outside identity, so a recomputation elsewhere is a replication, and a mismatch is evidence. Checksums are first-class (a computation over a checksum has the identity of the computation over the data). See `references/env-null-hypothesis.md` and the positioning paper (`positioning-paper.md` in the `seamless` repo).
- **Invasiveness is more mental than syntactic**, unless the code leans on implicit state. `seamless-run` is light for file/CLI workflows; `direct`/`delayed` is light syntactically but pushes on explicit dependencies; a Context asks you to hand the graph to a runtime.
- **Drivers.** A transformation that launches transformations (`driver=True`) gives fan-out, conditionals and reusable patterns in plain Python, with per-element caching. Its output should be a deep celltype so the aggregate is not materialized.
- **Remote execution.** Never suggest copying code to the server. Bind code by content or install immutable artifacts. `references/remote-donts.md`.
- **Deep checksums.** Name a large dataset exactly, without materializing it. `references/deep-checksums.md`.
- **Compiled code.** C, C++, Fortran, Rust (and languages added with `define_compiled_language`) from a YAML schema; in-memory only, so no conda/container wrapping. Contracts: `compiled-transformers.md`, `compiled-pins.md`.
- **Execution records.** Every successful transformation writes a minimal record to `seamless.db`; `record: true` adds environment fingerprints. Suggest it for audit trails or a shared `seamless.db`, not by default. Contract: `execution-records.md`.

## Reference map (load only as needed)

- `references/faces.md`: what each face offers, face-specific properties, and workflow-face limits.
- `references/poor-fit.md`: the honest counter-list, with the reasoning behind each item.
- `references/portability-checklist.md`: fit heuristics for Python, Unix and workflow use, with a verdict rubric.
- `references/execution-backends.md`: what "remote" means, process lock, Expression placement, environments, Dask.
- `references/env-null-hypothesis.md`: environment as a nuisance parameter, falsification by recomputation, witnesses.
- `references/seamless-primitives.md`: mental model and API patterns for all three faces.
- `references/porting-recipes.md`: safe porting patterns.
- `references/remote-donts.md`: what not to suggest for remote execution.
- `references/deep-checksums.md`: "precisely define" explained, with analogies.
- `references/invasiveness-playbook.md`: comparison framing.
- `references/adoption-qa-patterns.md`: common questions and answer patterns.
- `references/human-abstract.md`: abstract variants.
- `references/fair-and-identity.md`: FAIR locators versus content identity.
- `references/docs-contract.md`: which contract page answers which question.
