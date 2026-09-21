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
| `contracts/celltypes-and-conversion.md` | Layer 1+3 of the stack. The 13 celltypes; celltype hierarchy as a **checksum** hierarchy; canonical null and virtual values; reference parser; the conversion rule table **built on the hierarchy** (`conversion_trivial` *is* the set of hierarchy edges) and `convert_checksum`. The engine is exactly the empty-path case of an Expression |
| `contracts/hashtype.md` | Layer 2. `HashType` checksum classification (replaces `BufferInfo`); the false-negative property — **only a `False` is a proof**; tightening; `hash_type` database table; `deserializable_as`/`capabilities`/`conversion_feasible`; no deep-celltype vocabulary |
| `contracts/deep-celltypes.md` | A **carve-out at layer 4**, not a layer. `deepcell`/`deepfolder`/`folder`: the flat index buffer, member typing, the legal conversion table, the one-step string-item path rule and the fusion barrier (`module` is not deep) |
| `contracts/expressions.md` | Layer 4. Expressions: **project, then convert** (at most one conversion, always last), the 4-tuple identity, the dummy Expression, path syntax, fusion, placement (`execution="auto"`) and the fingertip exemption from it, publishing vs recording identity, the error envelope, uncached failures, dedup and softcancel |
| `contracts/cells.md` | Layer 5. Cells as deferred Expressions, bound or standalone: `celltype` vs read-only `input_celltype`, `.source`/`.checksum`, the two write families and the 3×2 matrix, null and `None`, standalone reads, failures on the handle, projections (project-then-convert on a handle) and connection targets, cell-level joins |
| `contracts/pins.md` | Transformer pins: `tf.pins.x`, the `pin.celltype`/`tf.celltypes.x` link, pins hold checksums, conversion at the pin, optional pins and the null rules, a Pin is not a source |
| `contracts/workflow-context.md` | The reactive workflow `Context`: a DAG of nodes with Cells/Transformers as views, assignment and edges, the controller thread and sequenced ingress, barriers and timeouts, optimistic sub-path commits, `prune()`, `get_graph`/`set_graph` |
| `contracts/node-state-lifecycle.md` | The six node states and how each is derived, connectivity, block reasons and their precedence, the glitch-free cascade, speculative supersession and the three grace holds, `prune`, and states through barriers |
| `contracts/attachments.md` | The attachment framework: sense as an authoritative write and actuate as a post-turn delivery, durable spec vs ephemeral session, the topology rules a sensing attachment imposes, latest delivery discipline, the three-way error model, the oscillation detector, the cut barrier, and the driver roster |
| `contracts/mounts.md` | File mounts: the `ctx.a.mount` API, `mode`/`authority`/`persistent`, the initial decision table, observation classification against one disk belief, canonical bytes and null files, fingerprints and conditional atomic writes, directory mounts (`deepfolder` is sense-only), `ctx.mounts.sync()`, graph serialization and limits |
| `contracts/cancellation.md` | The cancellation substrate: one membership set per deduplication site, `softcancel` = deregister vs hard `cancel` = kill-all, softness cascading to the leaf, no liveness machinery, and the soft-only reactive policy |
| `contracts/service-management.md` | `seamless-service-resolve`, `rhl-*` helpers, false-pass protocol |
| `contracts/execution-records.md` | Per-transformation records in `seamless.db`; minimal vs full mode, write-once semantics |
| `contracts/direct-delayed-and-transformation.md` | Transformation model, `direct`/`delayed` decorators |
| `contracts/scratch-witness-audit.md` | Scratch, witness, and audit trail semantics; fingertipping as recompute-on-absence, where the chain runs, and why neither evaluation nor fingertipping publishes |
| `contracts/seamless-run-and-argtyping.md` | The `seamless-run` CLI: argtyping, `--var` vs `--metavar`, canonicalization, manual remote deployment |
| `contracts/cache-storage-and-limits.md` | What is cached at a high level; the local buffer cache and its memory pressure |
| `contracts/content-addressed-files-and-dirs.md` | Files and directories as checksums; the deep index as a directory identity |
| `contracts/modules-and-closures.md` | Content-bound code: embedding modules, environment envelopes, closures as implicit inputs |
| `contracts/compiled-transformers.md` | C/C++/Fortran/Rust + open language set; identity model and pure-function constraint |
| `contracts/compiled-pins.md` | Compiled transformer input pins: the C ABI rules, schema-derived celltypes and the declaration whitelist, `mixed` as auto, the two validation stages and where they run, scalar and character admission, null, errors |
| `contracts/seamless-signature-schema.md` | Schema YAML format used by compiled transformers; dtype/shape/wildcard rules |
| `contracts/compression.md` | `.zst`/`.gz` support; canonical-checksum invariant |
