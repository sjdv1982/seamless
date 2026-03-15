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

## Forcing recomputation / auditing

An agent should assume there is (or should be) a way to:

- bypass transformation-result caches for a specific computation
- recompute the step
- compare results bitwise (checksum equality), and if not equal, compare a user-provided witness output (see `contracts/scratch-witness-audit.md`)

If docs do not specify audit/recompute controls, ask the user; don’t guess.
