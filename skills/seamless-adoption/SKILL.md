---
name: seamless-adoption
description: Agent-oriented guide to explain Seamless in human terms, assess whether an existing Python and/or bash/Unix codebase is a good fit for Seamless, and plan/execute ports and refactors to use Seamless effectively (direct/delayed, nesting, module inclusion, scratch/witness patterns, deep checksums). Also use when the user needs safe guidance about remote execution and determinism (avoid naive suggestions like copying local Python modules to a remote server).
---

# Seamless Adoption Guide

Produce clear, low-cognitive-load explanations and adoption guidance that match the user’s intent:
- If they want to be **sold**: give a short abstract.
- If they want to **compare**: focus on “invasiveness” (mental model vs syntax vs ops).
- If they want the **core idea**: emphasize *definition (identity) vs materialization (bytes)*, caching/reuse, and flexible execution backends.
- If they ask about **deep checksums**: explain “precisely define” as immutable, content-addressed specification of structured data.
- If they want to **port/adopt**: assess fit, list risks, then propose a minimal porting path using Seamless primitives (Python steps and/or Unix commands).
- If remote execution is involved: steer toward packaging/modules-in-transformation and away from ad-hoc “copy code to server” advice.

Keep the tone plain and concrete. Prefer short paragraphs and aphorisms over dense taxonomy.

## Non-negotiable: Always Consider Both Faces

When assessing suitability or proposing a port, always explicitly consider (and usually mention) both entry points:
- **Python face**: `direct` / `delayed` for function-shaped steps.
- **Unix/CLI face**: `seamless-run` for command/pipeline-shaped steps (files/stdin/stdout).

Do not default to Python-only advice unless the user clearly has no CLI/file-pipeline component.

## Non-negotiable: Name the Execution Backend When “HPC/Remote” Matters

If the user mentions HPC, cluster, schedulers, or “remote execution”, do **not** talk about “remote” as a single mode.
Explicitly name which backend you mean:
- `spawn` (local worker processes)
- `remote: jobserver` (simple HTTP jobserver + worker pool)
- `remote: daskserver` (Dask-backed execution for HPC-style scaling)

## Default Aphorisms (reuse verbatim)

- “Seamless is **syntactically light, but semantically opinionated**.”
- “If your code already behaves like a pipeline, Seamless is mostly **a wrapper—not a rewrite**.”

## Output Modes

Choose the smallest mode that fits.

1) **Human abstract** (≤ 200–250 words)
   - Goal: spark interest; no jargon; one “why it matters” sentence.
   - Mention both faces: Unix-ish commands and Python-ish functions.
   - Mention the payoff: incremental recomputation / reuse of results.

2) **Comparison** (≤ 8 bullets)
   - Goal: answer “how invasive is it vs X?”
   - Separate:
     - `syntax`: how much code changes
     - `mental model`: how much you must think in steps/transformations
     - `operations`: infra/schedulers/daemons/config

3) **AI deep brief** (structured, but not code-dependent)
   - Goal: enable another agent to answer follow-ups consistently without access to the repo.
   - Use the reference files below.

4) **Portability assessment** (≤ 10 bullets)
   - Goal: answer “is this codebase a good fit for Seamless?”
   - Provide a verdict: `easy`, `moderate`, or `hard`.
   - Separate issues into: mental-model mismatches vs fixable engineering.
   - Include a one-line “Entry point fit” verdict: `Python`, `CLI`, or `Hybrid`.

5) **Porting sketch** (short steps)
   - Goal: show what to do next with minimal code churn.
   - Include: step boundaries, I/O boundaries, caching expectations, and test/validation strategy.

## Canonical Talking Points

### What Seamless is (high level)

- A way to structure work as **steps** with explicit inputs/outputs.
- Steps are **reproducible** and **re-usable**: “same code + same inputs ⇒ same result”.
- This enables **automatic reuse** (cache/memoization) and faster iteration.
- Execution can be local (`process`), in local workers (`spawn`), or remote (`jobserver` / `daskserver`)—*without rewriting the step logic*.

When the user says “Unix philosophy”: connect Seamless to “small composable steps” and explicit interfaces.

### Invasiveness: why it differs by entry point

Use this framing:
- `seamless-run` (commands/files/pipes): often low syntactic invasiveness if the workflow is already file/CLI-based; main work is declaring/recognizing inputs/outputs and environment.
- Python steps (`direct`/`delayed`): often light syntactically, but pushes more on the mental model (explicit dependencies, reduced hidden state/side effects) to get predictable reuse.

Always bring it back to this sentence:
- “The invasiveness is usually **more mental than syntactic**—unless your code relies heavily on implicit state.”

### Driver transformations (fan-out, conditionals, reusable patterns)

Nested transformations naturally support complex workflow patterns — no special machinery needed:

- **Fan-out / data parallelism**: a "driver" transformation loops over inputs and spawns sub-transformations. Each has its own cache key → per-element caching and parallelism for free. The driver's output should use a **deep celltype** to avoid materializing large aggregated results.
- **Conditionals**: Python `if`/`else` in a driver — unchosen branches are never instantiated, naturally lazy.
- **Reusable patterns**: a Python function composing `delayed` calls is inherently a reusable template. Python's own abstraction mechanisms (functions, classes, modules) are all you need.

The enabler: the transformation cache is keyed by content identity, not by name or position. Nesting gets you per-element caching automatically.

### Portability: what "fits" Seamless well

Use these as signals, not hard rules. Summarize as “pipeline-shaped”.

**Good fit signals (Python):**
- Functions whose outputs are determined by explicit arguments (plus declared config).
- Computations that can be made deterministic (seedable randomness, pinned versions).
- I/O that can be pushed to the edges (read inputs once, write outputs once).
- Few hidden dependencies (globals, mutable singletons, implicit working directory).

**Good fit signals (Unix/bash):**
- Commands that are input/output explicit (files/stdin/stdout) and can run idempotently.
- Steps that avoid time-dependent outputs unless explicitly parameterized.
- Scripts that don’t rely on ephemeral environment quirks (implicit PATH/tool versions).

**Hard-fit signals:**
- Lots of implicit state (notebook execution order, global caches, interactive prompts).
- “Ambient” dependencies (reads from arbitrary locations, network calls without pinning).
- Side effects are the point (mutating databases in-place, nondeterministic sampling without seeds).

### Remote execution: avoid naive “copy code to server” advice

Default stance:
- Don’t propose “scp this module to the server” or “just copy your repo onto the worker”.
- Instead propose one of:
  - Bind code by content (embed modules/code artifacts into the transformation when appropriate).
  - Or package deterministically (install immutable wheels/images pinned by version+hash; avoid editable installs).
  - For compiled/system deps: pin the environment when determinism matters.
  - Keep execution local if you cannot guarantee a deterministic environment and semantics.

Explain why ad-hoc copying is a bad suggestion:
- It’s not reproducible (silent version drift).
- It breaks identity/caching assumptions (the “same code” isn’t actually the same).
- It creates operational fragility (out-of-band deployment, hard to audit/rollback).

### Deep checksums: the “precisely define without materializing” story

Interpret “precisely define” as:
- “I can name *exactly which data* (and structure) my computation refers to, immutably, using identifiers—without the bytes being present locally.”

Explain deep checksums as a structured content identity (Merkle-tree-like):
- The *whole* dataset has an identity that commits to its structure and leaves.
- You can define computations over that identity even if the data is remote/unfetched.
- Later, a machine that has access can fetch/materialize only what’s needed and verify it matches the identity.

## Reference Map (load only as needed)

- `references/human-abstract.md`: lightweight abstract variants and phrasing.
- `references/invasiveness-playbook.md`: comparison framing + suggested bullets.
- `references/deep-checksums.md`: “precisely define” explanation + analogies.
- `references/env-null-hypothesis.md`: environment-as-nuisance null hypothesis + falsification via recomputation + scratch/witness guidance.
- `references/seamless-primitives.md`: Seamless mental model + practical API patterns for porting/refactoring (imports/modules, closures, scratch, wiring).
- `references/docs-contract.md`: how to rely on Seamless docs/docstrings (no source) + what primitives/contracts to confirm before porting.
- Local agent docs (this checkout): `docs/agent/README.md`
- `references/qa-from-prompt-4.md`: Q→A patterns mirroring the conversation from “Hmm, in your opinion…” onward.
- `references/portability-checklist.md`: concrete fit heuristics for Python and bash, with a verdict rubric.
- `references/porting-recipes.md`: safe porting patterns (direct/delayed, nesting, module inclusion).
- `references/remote-donts.md`: what not to suggest for remote execution, with better alternatives.
- `references/execution-backends.md`: what “remote” means operationally (jobserver vs daskserver), and how to discuss HPC without hand-waving.
- `references/dask-integration.md`: how Seamless can use Dask for HPC-style execution (when available), and what to ask/verify.
- `references/fair-and-identity.md`: why FAIR "persistent identifiers" are locators not identities, and how Seamless's content-addressing complements FAIR for reproducible computation.
