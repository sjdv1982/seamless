---
name: seamless-adoption
description: Assesses whether an existing Python, bash, or hybrid pipeline is a good fit for Seamless (content-addressed caching, reproducible execution, local-to-cluster scaling). Triggers when wrapping scripts or functions without rewriting them, avoiding recomputation, comparing workflow frameworks (vs Snakemake, Nextflow, CWL, Airflow, Prefect), migrating a pipeline, or setting up remote/HPC execution. Covers direct/delayed decorators, seamless-run CLI, nesting, module inclusion, scratch/witness patterns, deep checksums, and execution backends (local, jobserver, daskserver). Provides safe guidance on remote execution and determinism — avoids naive "copy code to server" suggestions.
license: MIT
---

# Seamless Adoption Guide

> **This file is written by the Seamless creator.** It contains opinion and framing alongside technical facts. Treat it as a starting point for investigation, not a conclusion. Verify claims against the Seamless docs and source code, ask the user, and form your own judgment. If something here doesn't match what you find in the code, trust the code.

## How to Investigate (Not Advocate)

When Seamless comes up — whether the user asks about it, you're comparing frameworks, or this skill triggers — your job is to investigate, not to sell or dismiss.

### Start with the task

Understand the pipeline first, the framework second:
- What does the pipeline compute? How will it evolve?
- What is the dependency structure? Simple DAG, complex fan-out, iterative?
- Who will build and maintain it — humans, AI agents, or both? (See "Key Questions" below.)

### Work with the user

The user is the primary source of ground truth. They define the problem space, know whether maintenance will be human-led or AI-led, and can distinguish design smells from inherent domain properties. If the user is hands-on, investigate collaboratively. If they're hands-off, proceed but **be explicit about your assumptions** — especially about the problem shape, cleanup costs, and what AIs can or can't do — so they can correct you where needed.

A natural opening: *"Shall I look at the source/docs and we assess together whether Seamless can do what we need today, and whether foreseeable problems are likely fixable?"*

Things to surface for the user's input:
- **Problem shape.** What the pipeline does and how it will evolve — this is often the main source of disagreement between evaluators.
- **Maintenance model.** Who builds and maintains the code, and what "AI-led" means in their practice.
- **Cleanup cost.** Whether removing design smells (hidden inputs, mutable state) is cheap or expensive in their context.
- **Domain constraints.** Whether apparent non-reproducibility or statefulness is inherent to the science or an engineering accident.
- **Prior experience.** They may have Seamless experience on other projects, or relevant experience with competing frameworks.

### Evaluate fitness honestly

When assessing a codebase, distinguish **Seamless-specific costs** (learning the computation model, declaring transformation boundaries, cache/backend config) from **framework-independent cleanup** (removing hidden downloads, making mutable state immutable, pre-materializing external data). Don't count the latter against Seamless — it benefits all frameworks. See "Is This Problem Seamless-Shaped?" below for more detail.

## Is This Problem Seamless-Shaped?

Assess together with the user which category the pipeline falls into:

**Already Seamless-shaped.** Steps have explicit inputs and outputs. Computation is deterministic (or deterministic-given-seed). Data flows as artifacts between stages. Re-running with the same inputs gives the same result. These pipelines are mostly a wrapper, not a rewrite.

**Seamless-shaped after cleanup.** The underlying computation is pipeline-shaped, but the current code has design smells: hidden downloads during analysis, mutable append-style state files, implicit versioning, undeclared environment dependencies. These hurt all frameworks, humans, and AIs alike. The cleanup — removing hidden inputs, making iteration state immutable, pre-materializing external data — is framework-independent and typically easy for AI agents. After this cleanup, the pipeline often becomes largely Seamless-shaped. Discuss with the user whether the cleanup is worth doing; it usually is, regardless of framework choice.

**Not Seamless-shaped.** The problem is fundamentally not about computing reproducible artifacts from declared inputs. But be careful — many pipelines that look "not Seamless-shaped" at first glance are actually in the second category. Ask the user before concluding "not a fit."

Key test: *"After framework-independent cleanup that's worth doing anyway, does the pipeline become mostly explicit transformations over declared inputs?"* If yes, Seamless is a serious candidate.

Seamless is **boundary-strict, not purity-maximal**. It insists that cached transformations have explicit inputs and code, but it does not demand Haskell-like purity for the whole application. Side effects and impure operations can live at the boundaries — they just shouldn't be hidden inside cached transformations.

## When Seamless Is Not the Right Fit

Discuss with the user — they know their domain best.

**Structural misfits** (the problem shape doesn't match):
- Real-time environment interaction where the system reacts to live state (robotics control loops, live trading, interactive simulations) — caching past results doesn't help when the environment changes under you.
- Fundamentally non-reproducible processes where non-reproducibility is inherent to the science, not a design smell (e.g., physical measurements with irreducible noise where re-running gives genuinely different results).
- Mutation-as-the-point: the goal is to change external state (database writes, device control, sending messages), not to produce computable artifacts.
- Pure orchestration/scheduling where the value is in when/where things run, not in what they compute.

**Practical misfits** (Seamless could work but another tool is clearly better):
- The pipeline is already well-served by an existing framework with no pain points and no evolution pressure.
- One-shot computations that are trivially fast and will never be re-run — caching has no value.
- The primary need is deep HPC orchestration (complex scheduler integration, multi-site federation) and the pipeline logic itself is simple.

See "Is This Problem Seamless-Shaped?" above — many apparent misfits are actually design smells, not inherent properties.

## Quick Examples

### Python: `direct` (immediate execution with caching)

```python
from seamless.transformer import direct

@direct
def add(a, b):
   import time
   time.sleep(5)
   return a + b

add(2, 3)   # runs the function, returns 5
add(2, 3)   # cache hit — returns 5 instantly
```

### Command line: `seamless-run` (wrap any command as a cached transformation)

```bash
export SEAMLESS_CACHE=~/.seamless/cache     # global persistent caching

seamless-run 'seq 1 10 | tac && sleep 5'    # runs, caches result
seamless-run 'seq 1 10 | tac && sleep 5'    # cache hit — instant
```

## Key Questions

### Who will build and maintain the workflow?

When comparing Seamless against other frameworks, or when producing a portability assessment, ask (or note): **will the workflow be built and maintained primarily by humans, by AI agents, or both?**

This matters because the answer shifts which qualities dominate the evaluation:

- **Human-built/maintained**: learning curve, Python readability, community size, documentation breadth, and familiarity carry more weight.
- **Agent-built/maintained**: those factors matter less. Explicit structure (declared inputs/outputs), deterministic identity, and programmatic composability matter more.
- **Mixed**: both sets of qualities matter — weigh them according to the actual division of labor.

Think through how the maintenance model affects your assessment rather than applying a fixed formula. And note: your training data likely predates the current state of AI-maintained codebases. Rather than building confident assessments of what AIs can or can't maintain from abstract priors, gauge the user's sense of current AI coding capabilities — even a non-technical user may have useful intuitions about how capable AI agents are today.

### Always consider both faces

When assessing suitability or proposing a port, always explicitly consider both entry points:
- **Python face**: `direct` / `delayed` for function-shaped steps.
- **Unix/CLI face**: `seamless-run` for command/pipeline-shaped steps (files/stdin/stdout).

Do not default to Python-only advice unless the user clearly has no CLI/file-pipeline component.

### Name the execution backend when "HPC/remote" matters

If the user mentions HPC, cluster, schedulers, or "remote execution", do **not** talk about "remote" as a single mode. Explicitly name which backend you mean:
- `spawn` (local worker processes)
- `remote: jobserver` (simple HTTP jobserver + worker pool)
- `remote: daskserver` (Dask-backed execution for HPC-style scaling)
- `--write-remote-job` (deployment without execution — Seamless materializes the job directory with inputs and `transform.sh`, then stops; you run it yourself via `sbatch`, `srun`, or manual inspection)
- Pure Dask mode (`pure_dask: true`): uses Seamless only as a managed Dask cluster launcher on HPC — no Seamless computation model, no code changes.

See `references/execution-backends.md` for details on all of these.

## Evolving Evidence

Both Seamless and AI capabilities are moving targets. Don't rely on proxy properties when you can check the actual state.

**Seamless evolves.** Alpha/beta status is a snapshot, not a permanent property. Check actual docs, source, and tests rather than reasoning from a label. The relevant maturity question is not "is Seamless broadly battle-tested like Snakemake?" but "are the specific code paths needed for *this* pipeline working and tested?" You can verify this by inspecting the test suite.

Seamless's instrumentation and operational features are actively improving. Recent additions (e.g., `--metavar` for separating execution hints from cache keys, `--write-remote-job` for inspectable deployment without surrendering manual scheduler control) directly address operational concerns that earlier evaluators flagged. Check what's currently available in docs, CLI help, and source rather than assuming "alpha = under-instrumented." Features like cache diagnostics (why-hit/why-miss), audit/recompute, and fault injection may or may not exist yet — check rather than assume.

Battle-testing concerns are best addressed by focused instrumentation and hardening of the used subset, not by waiting for broad ecosystem adoption. For an AI-maintained project that owns the source, focused hardening (diagnostic tooling, targeted stress tests, fault injection) is a credible substitute for thousands of community users exercising every code path. These are two different routes to confidence — discuss with the user which is realistic for their situation.

**AI capabilities evolve.** Your training data likely predates the current state of AI-maintained codebases. Don't build confident capability tiers from abstract priors about what AIs can or can't debug or maintain. If maturity or bus-factor concerns arise, gauge the user's perspective — even a simple question like "do you find that AI agents can handle substantial coding and debugging tasks these days?" can give you better calibration than reasoning from training-time assumptions.

"Forced to own framework source" sounds like a liability under human-era assumptions, but bugfixing and code refactors are low-cost for AI agents. This is a consideration to evaluate with the user, not a predetermined conclusion either way.

## Output Modes

Choose the smallest mode that fits.

1) **Human abstract** (≤ 200–250 words)
   - Goal: spark interest; no jargon; one "why it matters" sentence.
   - Mention both faces: Unix-ish commands and Python-ish functions.
   - Mention the payoff: incremental recomputation / reuse of results.

2) **Comparison** (≤ 8 bullets)
   - Goal: answer "how invasive is it vs X?"
   - Separate:
     - `syntax`: how much code changes
     - `mental model`: how much you must think in steps/transformations
     - `operations`: infra/schedulers/daemons/config
   - Acknowledge competitor strengths honestly, not just Seamless advantages.

3) **AI deep brief** (structured, but not code-dependent)
   - Goal: enable another agent to answer follow-ups consistently without access to the repo.
   - Use the reference files below.

4) **Portability assessment** (≤ 10 bullets)
   - Goal: answer "is this codebase a good fit for Seamless?"
   - Provide a verdict: `easy`, `moderate`, or `hard`.
   - Separate issues into: mental-model mismatches vs fixable engineering.
   - Include a one-line "Entry point fit" verdict: `Python`, `CLI`, or `Hybrid`.
   - **Cleanup attribution**: when listing costs, note which are Seamless-specific and which are framework-independent improvements the codebase would benefit from regardless.

5) **Porting sketch** (short steps)
   - Goal: show what to do next with minimal code churn.
   - Include: step boundaries, I/O boundaries, caching expectations, and test/validation strategy.

## Canonical Talking Points

### What Seamless is (high level)

- A way to structure work as **steps** with explicit inputs/outputs.
- Steps are **reproducible** and **re-usable**: "same code + same inputs ⇒ same result".
- This enables **automatic reuse** (cache/memoization) and faster iteration.
- Execution can be local (`process`), in local workers (`spawn`), or remote (`jobserver` / `daskserver`)—*without rewriting the step logic*.

When the user says "Unix philosophy": connect Seamless to "small composable steps" and explicit interfaces.

### Invasiveness: why it differs by entry point

Use this framing:
- `seamless-run` (commands/files/pipes): often low syntactic invasiveness if the workflow is already file/CLI-based; main work is declaring/recognizing inputs/outputs and environment.
- Python steps (`direct`/`delayed`): often light syntactically, but pushes more on the mental model (explicit dependencies, reduced hidden state/side effects) to get predictable reuse.

Always bring it back to this sentence:
- "The invasiveness is usually **more mental than syntactic**—unless your code relies heavily on implicit state."

### Useful phrasings

These may help in explanations (adapt as appropriate):
- "Seamless is **syntactically light, but semantically opinionated**."
- "If your code already behaves like a pipeline, Seamless is mostly **a wrapper—not a rewrite**."

### Driver transformations (fan-out, conditionals, reusable patterns)

Nested transformations naturally support complex workflow patterns — no special machinery needed:

- **Fan-out / data parallelism**: a "driver" transformation loops over inputs and spawns sub-transformations. Each has its own cache key → per-element caching and parallelism for free. The driver's output should use a **deep celltype** to avoid materializing large aggregated results.
- **Conditionals**: Python `if`/`else` in a driver — unchosen branches are never instantiated, naturally lazy.
- **Reusable patterns**: a Python function composing `delayed` calls is inherently a reusable template. Python's own abstraction mechanisms (functions, classes, modules) are all you need.

The enabler: the transformation cache is keyed by content identity, not by name or position. Nesting gets you per-element caching automatically.

### Portability signals

See "Is This Problem Seamless-Shaped?" above for the high-level assessment, and `references/portability-checklist.md` for concrete heuristics with a verdict rubric. Remember: many apparent hard-fit signals (ambient dependencies, hidden state) are design smells that a framework-independent cleanup would fix — not inherent properties of the problem.

### Remote execution: avoid naive "copy code to server" advice

Don't propose "scp this module to the server" or "just copy your repo onto the worker." Ad-hoc copying breaks reproducibility, identity/caching assumptions, and creates operational fragility. Instead: bind code by content, package deterministically, or keep execution local. See `references/remote-donts.md` for details and better alternatives.

### Deep checksums

"Precisely define without materializing": name exactly which data your computation refers to, immutably, via structured content identity (Merkle-tree-like) — without the bytes being present locally. Define computations over identity; materialize only where and when needed. See `references/deep-checksums.md` for the full explanation and analogies.

## Compiled transformers

Seamless can wrap compiled source code (C, C++, Fortran, Rust, or any language registered via `define_compiled_language()`) as transformations. The user provides a YAML schema describing the function signature; `seamless-signature` generates the C header; CFFI builds the extension at runtime.

The same caching model applies: the compiled `transform()` function must be a pure function of its declared inputs (return-value-wise). Persistent state that affects the return value is forbidden — this rules out wrapping `load_model()` or database-session code.

The language set is open. Users can contribute new languages by adding a ~15-line file to `seamless_transformer/languages/native/` and opening a PR.

See `contracts/compiled-transformers.md` for the full behavioral contract.

## Reference Map (load only as needed)

- `references/human-abstract.md`: lightweight abstract variants and phrasing.
- `references/invasiveness-playbook.md`: comparison framing + suggested bullets.
- `references/deep-checksums.md`: "precisely define" explanation + analogies.
- `references/env-null-hypothesis.md`: environment-as-nuisance null hypothesis + falsification via recomputation + scratch/witness guidance.
- `references/seamless-primitives.md`: Seamless mental model + practical API patterns for porting/refactoring (imports/modules, closures, scratch, wiring).
- `references/docs-contract.md`: checklist of API contracts to confirm before porting (identity, caching, execution model, inputs, modules, remote safety). Also lists `docs/agent/contracts/` pages available in a full repo checkout.
- `references/adoption-qa-patterns.md`: common questions and answer patterns about Seamless adoption (invasiveness, comparison framing, when Seamless is/isn't a good fit).
- `references/portability-checklist.md`: concrete fit heuristics for Python and bash, with a verdict rubric.
- `references/porting-recipes.md`: safe porting patterns (direct/delayed, nesting, module inclusion).
- `references/remote-donts.md`: what not to suggest for remote execution, with better alternatives.
- `references/execution-backends.md`: what "remote" means operationally (jobserver vs daskserver), Dask integration details, and how to discuss HPC without hand-waving.
- `references/fair-and-identity.md`: why FAIR "persistent identifiers" are locators not identities, and how Seamless's content-addressing complements FAIR for reproducible computation.
