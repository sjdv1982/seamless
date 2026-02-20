## Portability checklist (Python)

Score each area as: ✅ already, ⚠️ fixable, ❌ hard.

- **Inputs explicit**: main computation depends on arguments/config, not implicit globals.
- **Determinism**: randomness is seedable; time/hostname/pid not part of results unless parameterized.
- **I/O boundaries**: avoid *ambient* reads (“whatever is on disk/network”). Reads are fine when they are **content-addressed**: if the checksum is an explicit input, resolving it inside the transformer is a caching/materialization operation, not a semantic side effect.
- **Environment strategy**: project code can be bound by content (embed or immutable artifacts); compiled/system deps are controlled enough for your determinism needs.
- **Side effects**: can be made “outputs-only” (produce artifacts) rather than “mutate shared state”.
- **Data size**: can reference data by identity (checksums) and materialize only where executed.
- **Witness outputs**: can persist small meaning-bearing results/diagnostics for cross-run and cross-environment comparison (don’t scratch these).
- **Recompute budget**: recomputation is feasible for falsification (at least for witness outputs) when fingertipping/buffers are unavailable.

Verdict rubric:
- **easy**: mostly ✅, a few ⚠️
- **moderate**: many ⚠️ but few ❌
- **hard**: one or more ❌ in determinism/I/O/side effects

## Entry point fit (don’t skip this)

Decide whether the best Seamless integration is:
- **CLI**: the workflow is mostly Unix commands/pipelines over files/stdin/stdout → emphasize `seamless-run`.
- **Python**: the workflow is mostly Python functions/values → emphasize `direct`/`delayed`.
- **Hybrid**: common in data/science → use both, with explicit boundaries.

## Portability checklist (bash/Unix)

- **Idempotent**: rerunning doesn’t corrupt state; outputs are overwritten/cleaned predictably.
- **Declared inputs/outputs**: script uses explicit file args and/or stdin/stdout; no hidden reads.
- **Stable environment**: tool versions are pinned/known; PATH quirks avoided.
- **No implicit temp state**: avoids relying on random `/tmp` names unless parameterized.
- **Working dir**: uses controlled working directory; relative paths are well-defined.

## Common “looks easy but isn’t”

- Hidden network access (downloads “latest”).
- Reads from `$HOME` or user-specific config.
- Uses current timestamp in output names/content.
- Implicit caches that change behavior across runs.

See also: `env-null-hypothesis.md` for the “environment as nuisance parameter” stance and what must be stored to falsify it.
