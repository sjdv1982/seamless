# Identity and Caching (Contract)

Seamless is a checksum-driven system. It treats a computation step as “defined” when it has:

- code identity
- explicit inputs (values and/or checksum identifiers)
- relevant metadata that affects execution/meaning

The core contract is referential transparency with respect to the declared inputs:
“same step definition ⇒ same result”.

## Transformation identity

At minimum, assume transformation identity is determined by:

- the executed code (or code checksum), including embedded module definitions
- the set of input pins and their content identities (checksums)
- the **load-bearing** metadata that changes the computation's meaning: code
  language (`__language__`), output type (`__output__`), pin namespace mapping
  (`__as__`), pin materialization format (`__format__`), and compiled function
  schema/ABI (`__schema__`)

Identity is *not* affected by the orthogonal execution envelope — where/how the
computation runs (`__meta__` including local-vs-remote placement, `__env__`,
`__compilation__`, scratch policy, …). Those change execution, not the denoted
result. If the platform allows environment-dependent semantics, it should record
an **environment signature** as provenance (see `contracts/scratch-witness-audit.md`).

## Caching

Caching is valid only to the extent that the step is referentially transparent under the identity definition above.

Practical rules:

- The cache may store “transformation checksum → result checksum” mappings.
- A result checksum can be reused without re-executing code only when it is resolvable/materializable (or recomputable, if scratch).
- Content-addressed reads are not semantic side effects: resolving a pre-declared checksum is materialization, not “reading whatever is on disk”.
- Compression (`.zst`, `.gz`) is a materialization detail — it does not affect identity or caching. A compressed and uncompressed form of the same buffer have the same checksum and are cache-equivalent. See `contracts/compression.md`.

### Concurrent submissions of the same checksum

Because orthogonal-only differences are cache-equivalent, a second submission of an already-running `tf_checksum` under a different orthogonal envelope does not start a second execution. By default it **latches on**: it attaches to the running submission, adopts that submission's envelope, and returns its result *value* (not the latcher's envelope side-effects, e.g. its own direct-print, placement, or record request). A caller that requires its own envelope to execute can opt into `strict` mode (e.g. `--strict` for the CLI), which instead fails while a differently-dundered submission is active — the prior submission must finish or be canceled (`seamless-cancel <tf_checksum>`) first. This reflects a backend limitation — the same `tf_checksum` cannot execute concurrently under two different envelopes — not a property of the identity model.

## Load-bearing vs orthogonal keys in a transformation dict

Internally, a transformation is represented as a dict. A dunder (double-underscore) key is **not** automatically excluded from the checksum — each key is classified as one of three kinds:

**Load-bearing** (determinant) — included in the transformation checksum (the cache key). Changing the value produces a different transformation identity and bypasses the cache. This is every plain pin (`code`, `arg1`, `objects`, …) **and** the load-bearing dunders: `__language__` (code interpretation/execution semantics), `__output__` (output name/celltype), `__as__` (pin namespace mapping, observable by code), `__format__` (pin materialization), and `__schema__` (compiled function ABI/signature; not derivable from `code`).

**Orthogonal** — frozen and carried with the transformation, but excluded from the checksum. Changing the value changes the execution envelope, not identity, and must not change the denoted result value. These include `__meta__` (incl. local-vs-remote placement and compiled `metavars`), `__env__`, `__compilation__`, `__record_probe__`, `__code_checksum__`, `__code_text__`, scratch policy, the legacy `__compilers__`/`__languages__`, and any `META__*` key.

**Derived/eliminable** — not independent identity state; regenerated from load-bearing data, and only validated then discarded if a caller supplies them. These include `__header__` (generated from `__schema__` via `seamless-signature`), `__compiled__` (derived from the presence of compiled definition state), and `__deps__` (derived from the dependency graph).

Practical consequence: two transformations that differ only in orthogonal values are cache-equivalent. For example:

- Compiler flags live in `__compilation__` (orthogonal) → switching from `-O3` to `-g` does not invalidate the cache.
- The conda environment name lives in `__env__` (orthogonal) → activating a different environment reuses a cached result if the code and inputs are unchanged.
- Source code lives in the plain key `code`, and the code language lives in `__language__` (load-bearing) → changing either is a cache miss. The same `code` bytes interpreted as Python versus bash are *different computations* and must not alias to one cache key.

This split is the heart of the identity model: load-bearing keys capture the "what to run" identity, orthogonal keys capture the "how to run" envelope. An agent must not move load-bearing data into the orthogonal set to avoid cache misses — doing so corrupts the identity model by aliasing distinct computations to one key.

## Forcing recomputation / auditing

An agent should assume there is (or should be) a way to:

- bypass transformation-result caches for a specific computation
- recompute the step
- compare results bitwise (checksum equality), and if not equal, compare a user-provided witness output (see `contracts/scratch-witness-audit.md`)

If docs do not specify audit/recompute controls, ask the user; don’t guess.
