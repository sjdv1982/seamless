---
name: seamless-porting
description: Use when creating, porting, or debugging Seamless pipelines from Python, bash, or existing workflow systems; selecting the active concern in a staged non-linear Seamless port; designing referentially transparent DAGs; wrapping steps with direct/delayed transformers or seamless-run; validating Seamless contract compliance; activating capabilities such as persistent caching and local-cluster remote execution; or optimizing parallelism, incremental computation, and dataflow.
---

# Seamless Porting

Essential: treat Seamless pipeline work as a staged, non-linear progression. Seamless wrapping syntax is deceptively small: a minor syntactic change can have large semantic and operational effects. Agents mispredict Seamless behavior when they change wrapping, wiring, capability activation, execution placement, and optimization at the same time.

The purpose of this skill is attention routing. Consider exactly one active concern at a time, but do not treat the active concern as a physical edit boundary. Seamless changes often touch several surfaces at once: step code, wrapper syntax, wiring, data movement, cache policy, backend configuration, and granularity. The active concern governs why the edit is being made, what evidence is relevant, and which exit check must pass.

## Operating Model

Stages have a normal order, but the active concern is chosen by user intent, failure evidence, failed prerequisites, or the earliest unfinished concern.

Before nontrivial edits, state or infer:

- Active concern:
- Why this concern:
- Touched surfaces:
- Exit check:

Concern selection priority:

1. User-named concern.
2. Symptom-implied concern.
3. Failed prerequisite of the selected concern.
4. Earliest unfinished concern.

Default stage order:

1. DAG design.
2. Plain step behavior.
3. Minimal wrapping.
4. Seamless contract.
5. Scaling and realism.
6. Capability activation.
7. Optimization.

Move to another concern when the exit check passes, when the user explicitly changes focus, or when a failure proves that a different concern is active.

## Required Returns

Return to Seamless contract after any semantic change to wrapper syntax, wiring, data movement, cache policy, materialization strategy, execution backend, parallelization, or granularity.

Return to scaling and realism, then contract, after any significant move from toy data toward real inputs, real environments, or restored production steps.

If optimization fails because result semantics are unclear, return to DAG design or plain step behavior. If remote execution differs from local execution, return to contract first, then capability activation or optimization.

## Hard Rules

- Do not start with Seamless syntax. First design or recover the DAG and step boundaries.
- Do not add remote execution, parallelization, incremental computation, or optimization before a small wrapped pipeline passes contract checks.
- Do not fix a failed small pipeline by adding wiring complexity until the plain step and individual wrapper have both been smoke-tested.
- Do not pass Python class instances across Seamless boundaries. Convert to supported structured values or buffers.
- For large data, do not materialize values by default. Decide explicitly between value, checksum, and handle wiring.
- When remote or HPC execution matters, name the backend explicitly: `process`, `spawn`, `remote: jobserver`, or `remote: daskserver`.
- For substantive ports, implement persistent caching and local-cluster remote execution by default after the small wrapped pipeline passes contract checks, unless explicitly out of scope or blocked by missing local cluster configuration.
- If scratch plus fingertip is used, enable input fingertipping on each consumer transformation that may receive missing scratch inputs. In Python, set the downstream transformer/core's `allow_input_fingertip = True` before constructing the transformation; for CLI execution of a transformation checksum, use `--fingertip`. Scratch on the producer is not enough.
- In the final response, list the Seamless capabilities implemented and briefly list relevant capabilities left for follow-up, including blocked or intentionally omitted ones.

## Contract References

Load the relevant contract before changing the associated semantics:

- Python wrapper behavior: `seamless/docs/agent/contracts/direct-delayed-and-transformation.md`
- CLI command wrapping and arg/file typing: `seamless/docs/agent/contracts/seamless-run-and-argtyping.md`
- Transformation identity and caching: `seamless/docs/agent/contracts/identity-and-caching.md`
- Imports, modules, project code, and closures: `seamless/docs/agent/contracts/modules-and-closures.md`
- Compiled transformers: `seamless/docs/agent/contracts/compiled-transformers.md`
- Execution backend selection: `seamless/docs/agent/contracts/execution-backends.md`
- Scratch, fingertip, witnesses, and audit: `seamless/docs/agent/contracts/scratch-witness-audit.md`
- Cache storage and scratch limits: `seamless/docs/agent/contracts/cache-storage-and-limits.md`
- Input fingertip API details: `seamless/docs/agent/api/python/seamless_transformer.transformation_class.md`

## 1. DAG Design

Entry triggers:

- New port, unclear structure, or de novo pipeline.
- Existing code is implicit, notebook-shaped, or side-effect-heavy.
- Optimization or contract work fails because step meaning is unclear.

Start without Seamless syntax or implementation details.

For a de novo pipeline, design an abstract DAG of functionally pure, referentially transparent steps with I/O pushed to the boundaries. For existing step code, check purity first, then focus on wiring. For an implicit pipeline-shaped implementation, isolate the steps and rewire them as an explicit DAG. For an existing explicit pipeline such as Snakemake, quickly verify that the steps do not grossly violate purity, then move on.

Exit check: each step has explicit inputs and outputs, and hidden dependencies or side effects are either removed, parameterized, or recorded as risks.

## 2. Plain Step Behavior

Entry triggers:

- A step gives the wrong result before Seamless is involved.
- The step boundary is known, but its plain behavior has not been smoke-tested.
- A wrapper failure may actually be ordinary Python, bash, tool, or environment failure.

Before wrapping, make each step concrete and smoke-tested as plain Python or bash.

For Python, prefer ordinary function-shaped steps. For bash or Unix pipelines, prefer command-shaped steps with explicit file, stdin, stdout, and environment boundaries.

Exit check: the unwrapped step passes a small smoke test with representative input and produces the expected output.

## 3. Minimal Wrapping

Entry triggers:

- Plain step behavior passes and the next task is Seamless wrapping.
- First wrapper attempt fails.
- The code uses Seamless syntax before there is a small wrapped proof.

Add minimal Seamless wrapping to individual steps. Prefer the simplest syntax first: `seamless.transformer.direct` for individual Python step smoke tests and direct `seamless-run` wrapping for bash commands. Reuse the plain smoke tests against the wrapped code.

For Python pipeline wiring, prefer `delayed` / `Transformation` handles once individual step wrappers work and the goal is to build an explicit graph.

Then wire a small linear pipeline of 2-5 Seamless-wrapped steps. Use the simplest possible wiring: concrete materialized Python values, or files for the CLI face, as inputs and outputs.

If this does not work, revisit plain step behavior and individual wrapping before assuming the wiring is the problem. One known exception is Python class instances as inputs, which Seamless does not support. Prefer numpy values, lists, dicts, or combinations of those. As a last resort, use pickle to pass raw buffers between Seamless-wrapped steps.

If the simplest wrapper is inappropriate, for example for compiled transformers, skip that step temporarily or choose the specialized wrapper only after the smaller pipeline works.

Exit check: one wrapped step and one small wrapped pipeline both pass smoke tests.

## 4. Seamless Contract

Entry triggers:

- Unexpected cache hit, cache miss, or result reuse.
- Same apparent inputs give different results.
- Local and remote execution disagree.
- Hidden files, imports, closures, working directory, environment variables, RNG, network, or class instances are suspected.
- Wrapper syntax, wiring, backend, materialization, cache policy, parallelization, or granularity changed.

Assess compliance by inspecting the pipeline code and relating it to the exact Seamless wrapper semantics in use. If in doubt, run tests. Simple non-determinism is often detectable by repeated test runs, but other contract violations may require careful inspection.

Check at least:

- Inputs and outputs are explicit.
- Hidden filesystem, network, global state, working directory, and environment dependencies are eliminated or deliberately modeled.
- Boundary values use supported types, buffers, files, checksums, or handles.
- Large data is not accidentally materialized.
- Code identity, imported modules, closures, compiled code, and command environments match the wrapper contract.
- Repeated runs with the same code and inputs have the same result, or intentional non-determinism is parameterized.
- Cache identity expectations match the chosen granularity and wiring.

Re-check the contract after each material change to wrapping, data movement, caching, parallelization, or remote execution.

Exit check: the contract has been checked against the wrappers in use and the small wrapped pipeline still passes.

## 5. Scaling And Realism

Entry triggers:

- Small wrapped example works and the next step is real data, real tools, or restored production steps.
- A failure appears only at larger size or in the real environment.
- Simplifications made earlier may no longer be valid.

Progressively move from simplified small-data examples toward real usage. Add back steps that were removed for simplification. Increase input sizes gradually.

Each move toward realism can change the correct Seamless design. Re-evaluate the DAG, contract, selected capability, and optimization choices after every significant scaling step.

Exit check: the next larger or more realistic case passes, or the failure is traced back to a specific earlier concern.

## 6. Capability Activation

Entry triggers:

- User asks for persistent caching, local-cluster remote execution, HPC execution, parallelization, incremental computing, or operational behavior.
- A small wrapped pipeline passes and the next goal requires a Seamless capability.
- Operational behavior, not step semantics, is now the active issue.

Simple direct Seamless wrappers in Python are almost a no-op. As more Seamless capabilities are activated, more semantic and operational complexity comes into play.

Default capabilities for substantive ports:

1. Persistent caching. It is already active by default for the CLI face; for Python-facing ports, make sure the pipeline uses persistent Seamless caching rather than only ephemeral local values.
2. Local-cluster remote execution. Use `remote: jobserver` or `remote: daskserver` on a local or nearby configured Seamless service when available. This is common enough to implement by default after the small wrapped pipeline passes.

Keep local-cluster remote execution distinct from HPC execution:

- `process`: local in-process execution, no remote service.
- `spawn`: local worker processes, useful parallelism but not remote execution.
- Local-cluster remote: `remote: jobserver` or `remote: daskserver` against a local/nearby configured service, usually a default capability.
- HPC remote: scheduler/site-managed `remote: daskserver` or manual remote job deployment with queue, module, container, credential, filesystem, and policy constraints. Do not silently configure this unless requested or already clearly configured; list it as follow-up when relevant.

Other common capability concerns are parallelization and incremental computing, including data-incremental and code-incremental computation. Add these when they serve the user's goal or a clear performance/scaling need.

When debugging operational complexity, use Seamless diagnostics/instrumentation, and use the `seamless-remote-debugging` skill when the failure is remote/backend-related.

Exit check: the capability works on a small wrapped pipeline and the contract has been rechecked.

## 7. Optimization

Entry triggers:

- User asks about performance, remote execution optimization, HPC placement, data movement, cache pressure, large intermediates, parallelism, or incremental recomputation.
- Small pipeline works, but real usage materializes too much data, moves data poorly, recomputes poorly, or underuses parallel execution.

Seamless is primarily about wrapping. Its syntax is small enough to explicitly enumerate plausible wrapping choices and compare their effects when optimizing.

Ask these questions first:

- Are edges values, checksums, handles, files, or deep checksums?
- Which outputs are meaning-bearing and must remain materializable?
- Which bulky intermediates can be scratch?
- Would scratch plus fingertip improve data colocalization, and which consumer transformations need input fingertipping enabled?
- Is transformation granularity appropriate for both caching and execution placement?
- Which execution backend is active?

Then consider these choices explicitly:

1. Carefully consider scratch plus fingertip. Not only can they reduce cache pressure, they can also enforce data colocalization. Enable input fingertipping per consumer transformation; do not assume a global switch.
2. Wiring can use values, checksums, or handles. Concrete materialization is simple and inspectable, but it can hurt performance. Materialize large datasets only when necessary.
3. Parallel execution can use delayed transformers, spawn, `multi.parallel`, or `seamless-queue`.
4. Granularity matters because a transformation is both a caching unit and an execution or parallelization unit. Granularity can be nested: transformations can be defined inside another transformation, including heterogeneous nesting such as `seamless-run` wrapping a Python script that launches Python transformations. Nested granularity can create multi-level caching and improve colocalization of compute, data, and caching services.

For remote execution dataflow optimization, prioritize wiring type, scratch plus fingertip, and granularity. For parallelization optimization, prioritize execution mechanisms and granularity.

Exit check: the optimization is justified by observed or expected dataflow, cache, or parallel execution behavior, and contract compliance still holds.

## Capability Report

End every porting or debugging task with a concise capability report:

- Implemented capabilities: name what is actually active, for example minimal wrapping, persistent caching, local-cluster remote execution, parallel execution, scratch/fingertip, incremental computation, or HPC execution.
- Relevant follow-ups: name capabilities not implemented but plausibly useful next, with a short reason or blocker.
- If a default capability was not implemented, state why.

## Example Transitions

Common forward path:

DAG design => plain step behavior => minimal wrapping => contract => scaling and realism => capability activation => contract => optimization

Common non-linear returns:

- Wrapper or wiring changed => contract.
- Cache, materialization, backend, parallelism, or granularity changed => contract.
- Realism increased => scaling and realism => contract.
- Remote differs from local => contract => capability activation or optimization.
- Optimization exposes unclear result semantics => DAG design or plain step behavior.
