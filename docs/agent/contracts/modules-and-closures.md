# Modules and Closures (Contract)

Seamless aims for “code is data”: what executes should be bound by content, not by location.

## Imported modules (project code)

Goal: avoid “whatever version happens to be on that machine”.

Preferred patterns:
- **Embed** helper modules/packages into the transformation/module mechanism (content-bound).
- Or **install immutable artifacts** (wheel/image) pinned by version+hash (also content-bound).

Anti-pattern:
- “Copy your repo/module onto the worker/server” (location-bound, non-auditable drift).

## System/compiled dependencies

For dependencies like NumPy/BLAS/GPU stacks:
- treat them as part of the environment envelope
- record an environment signature for provenance
- if determinism requirements are strict, pin versions/backends and relevant determinism knobs

## Closures

Closures are implicit inputs.

Rules:
- Do not rely on captured outer-scope values unless you intentionally make them explicit.
- Prefer passing configuration as explicit arguments, or injecting small constants via explicit, content-bound mechanisms.
- If a closure value changes but is not part of the declared inputs, caching/identity can become incorrect.

## Dynamic imports and package data

If embedding is used:
- ensure the required submodules are actually included (dynamic imports can escape embedding-by-inspection)
- ensure required non-`.py` package data is accounted for (if the embedding mechanism doesn’t capture it automatically)
