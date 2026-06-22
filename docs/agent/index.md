# Seamless documentation

This is the documentation home for the new Seamless.

Looking for legacy Seamless (0.x)? Use the legacy docs at `/legacy/`.

## Start here

- Read the contract-oriented overview in `README.md`.
- Browse behavior and cache contracts under `contracts/`.
- See generated API reference under `api/`.

## Contracts quick index

| Contract | What it defines |
|----------|----------------|
| `contracts/execution-backends.md` | `process`, `spawn`, `remote: jobserver/daskserver` semantics |
| `contracts/identity-and-caching.md` | Content-addressing, checksum stability, cache invalidation |
| `contracts/service-management.md` | `seamless-service-resolve`, `rhl-*` helpers, false-pass protocol |
| `contracts/execution-records.md` | Per-transformation records in `seamless.db`; minimal vs full mode, write-once semantics |
| `contracts/direct-delayed-and-transformation.md` | Transformation model, `direct`/`delayed` decorators |
| `contracts/scratch-witness-audit.md` | Scratch, witness, and audit trail semantics |
| `contracts/compiled-transformers.md` | C/C++/Fortran/Rust + open language set; identity model and pure-function constraint |
| `contracts/seamless-signature-schema.md` | Schema YAML format used by compiled transformers; dtype/shape/wildcard rules |
| `contracts/compression.md` | `.zst`/`.gz` support; canonical-checksum invariant |
