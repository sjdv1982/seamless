# Identity and Caching (Contract)

Seamless is a checksum-driven system. It treats a computation step as “defined” when it has:

- code identity
- explicit inputs (values and/or checksum identifiers)
- relevant metadata that affects execution/meaning

The core contract is referential transparency with respect to the declared inputs:
“same step definition ⇒ same result”.

## Transformation identity

At minimum, assume transformation identity is determined by:

- the executed code (or code checksum)
- the set of input pins and their content identities (checksums)
- any metadata that changes execution semantics (e.g. “local vs remote”, scratch policy, module definitions)

If the platform allows environment-dependent semantics, it should also record an **environment signature** as provenance (see `contracts/scratch-witness-audit.md`).

## Caching

Caching is valid only to the extent that the step is referentially transparent under the identity definition above.

Practical rules:

- The cache may store “transformation checksum → result checksum” mappings.
- A result checksum can be reused without re-executing code only when it is resolvable/materializable (or recomputable, if scratch).
- Content-addressed reads are not semantic side effects: resolving a pre-declared checksum is materialization, not “reading whatever is on disk”.
- Compression (`.zst`, `.gz`) is a materialization detail — it does not affect identity or caching. A compressed and uncompressed form of the same buffer have the same checksum and are cache-equivalent. See `contracts/compression.md`.

## Plain keys vs dunder keys in a transformation dict

Internally, a transformation is represented as a dict. Its keys fall into two categories:

**Plain keys** (e.g. `code`, `arg1`, `objects`) — these are **determinant**: their content is included in the transformation checksum (the cache key). Changing any plain-key value produces a different transformation identity and bypasses the cache.

**Dunder keys** (double-underscore names, e.g. `__language__`, `__env__`, `__meta__`, `__compiled__`) — these are **execution-only**: they are excluded from the transformation checksum and do not affect caching, but they are still forwarded to workers so that execution can use them.

Practical consequence: two transformations that differ only in dunder values are considered cache-equivalent. For example:

- Compiler flags live in `__compilation__` (a dunder) → switching from `-O3` to `-g` does not invalidate the cache.
- The conda environment name lives in `__env__` (a dunder) → activating a different environment reuses a cached result if the code and inputs are unchanged.
- Source code lives in the plain key `code` → any source change is a cache miss.

This split is load-bearing: dunders capture the "how to run" envelope, while plain keys capture the "what to run" identity. An agent should not move determinant data into dunders to avoid cache misses — doing so would corrupt the identity model.

## Forcing recomputation / auditing

An agent should assume there is (or should be) a way to:

- bypass transformation-result caches for a specific computation
- recompute the step
- compare results bitwise (checksum equality), and if not equal, compare a user-provided witness output (see `contracts/scratch-witness-audit.md`)

If docs do not specify audit/recompute controls, ask the user; don’t guess.
