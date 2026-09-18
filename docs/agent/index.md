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
| `contracts/celltypes-and-conversion.md` | The 13 celltypes; celltype hierarchy as a checksum hierarchy; canonical null and virtual values; reference parser; conversion rule table and `convert_checksum` |
| `contracts/hashtype.md` | `HashType` checksum classification (replaces `BufferInfo`); false-negative property; tightening; `hash_type` database table; `deserializable_as`/`capabilities`/`conversion_feasible` |
| `contracts/deep-celltypes.md` | `deepcell`/`deepfolder`/`folder`: the flat index buffer, member typing, legal conversions and the one-step path rule (`module` is not deep) |
| `contracts/expressions.md` | Expressions: the 4-tuple identity, the dummy Expression, path syntax, placement (`execution="auto"`), the error envelope, uncached failures, dedup and softcancel |
| `contracts/cells.md` | Cells as deferred Expressions, bound or standalone: `celltype` vs read-only `input_celltype`, `.source`/`.checksum`, the two write families and the 3×2 matrix, null and `None`, standalone reads, failures on the handle, projections and connection targets, cell-level joins |
| `contracts/pins.md` | Transformer pins: `tf.pins.x`, the `pin.celltype`/`tf.celltypes.x` link, pins hold checksums, conversion at the pin, optional pins and the null rules, a Pin is not a source |
| `contracts/workflow-context.md` | The reactive workflow `Context`: a DAG of nodes with Cells/Transformers as views, assignment and edges, the controller thread and sequenced ingress, barriers and timeouts, optimistic sub-path commits, `prune()`, `get_graph`/`set_graph` |
| `contracts/node-state-lifecycle.md` | The six node states and how each is derived, connectivity, block reasons and their precedence, the glitch-free cascade, speculative supersession and the three grace holds, `prune`, and states through barriers |
| `contracts/cancellation.md` | The cancellation substrate: one membership set per deduplication site, `softcancel` = deregister vs hard `cancel` = kill-all, softness cascading to the leaf, no liveness machinery, and the soft-only reactive policy |
| `contracts/service-management.md` | `seamless-service-resolve`, `rhl-*` helpers, false-pass protocol |
| `contracts/execution-records.md` | Per-transformation records in `seamless.db`; minimal vs full mode, write-once semantics |
| `contracts/direct-delayed-and-transformation.md` | Transformation model, `direct`/`delayed` decorators |
| `contracts/scratch-witness-audit.md` | Scratch, witness, and audit trail semantics |
| `contracts/compiled-transformers.md` | C/C++/Fortran/Rust + open language set; identity model and pure-function constraint |
| `contracts/compiled-pins.md` | Compiled transformer input pins: the C ABI rules, schema-derived celltypes and the declaration whitelist, `mixed` as auto, the two validation stages and where they run, scalar and character admission, null, errors |
| `contracts/seamless-signature-schema.md` | Schema YAML format used by compiled transformers; dtype/shape/wildcard rules |
| `contracts/compression.md` | `.zst`/`.gz` support; canonical-checksum invariant |
