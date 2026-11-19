## Which contract answers which question

The contract pages in `docs/agent/contracts/` of the `seamless` repo are authoritative for 1.5 behaviour; the human docs (`docs/main/`) may lag behind, and had no workflow-face guide at the 1.5 cut. In a full checkout, start from `docs/agent/README.md` and `docs/agent/index.json`. If no checkout is available, ask the user for one or for the published agent docs before making claims about details.

### Map

| Question | Contract |
|---|---|
| What defines identity; what is cached; why a cache hit hides nondeterminism | `identity-and-caching.md` |
| `direct`, `delayed`, `Transformation` handles, failure delivery for Transformations | `direct-delayed-and-transformation.md` |
| The `Transformer` factory, builder state, `build()`, `process_lock`/`driver` | `transformers.md` |
| Pins, optional pins, null at the boundary, conversion at the pin | `pins.md` |
| Cells (standalone and bound), writes, reads, failures, joins | `cells.md` |
| Expressions, placement, deduplication | `expressions.md` |
| Celltypes, conversions, canonical null | `celltypes-and-conversion.md` |
| `deepcell`, `deepfolder`, `folder` | `deep-celltypes.md`, `content-addressed-files-and-dirs.md` |
| HashType (impossible readings rejected before fetching) | `hashtype.md` |
| `seamless-run`, argtyping, directories, flags | `seamless-run-and-argtyping.md` |
| Modules, closures, project code | `modules-and-closures.md` |
| Backends, process lock, environments on the executing host | `execution-backends.md` |
| conda, Docker, Podman, Apptainer | `environments.md` |
| `BACKEND = "cli"`/`"mem"`, Python CLI backend | `language-backends.md` |
| R, Julia, adding a language | `handler-languages.md` |
| Compiled transformers and pins, the schema | `compiled-transformers.md`, `compiled-pins.md`, `seamless-signature-schema.md` |
| Logs, streaming | `transformation-logs.md`, `streaming.md` |
| Cancellation | `cancellation.md` |
| Scratch, fingertipping, witnesses, provenance | `scratch-witness-audit.md` |
| Storage, eviction, local buffer sources | `cache-storage-and-limits.md`, `compression.md` |
| Execution records, irreproducible observations | `execution-records.md` |
| Services (`seamless-service-*`, `rhl-*`) | `service-management.md` |
| Workflow Context, graph save/load | `workflow-context.md` |
| Node states and block reasons | `node-state-lifecycle.md` |
| Mounts, shares, widgets, the attachment framework | `mounts.md`, `shares.md`, `widgets.md`, `attachments.md` |
| Serving cells as a web API | `guides/seamless-web-server.md` (agent guide) |

### Minimal contracts to confirm before proposing a port

- **Identity/caching**: what enters the `tf_checksum` (code, inputs and their celltypes, language, modules; not scratch, environment, backend, `process_lock`, streaming); which caches are local or shared.
- **Execution model**: `direct` raises on failure; `delayed` handles report `None` from `compute()` and raise from `run()`; `start()`/`task()` for concurrency; nested transformations release the process lock.
- **Inputs and celltypes**: values are serialized by celltype; a `bytes` pin arrives as `bytes`; a required pin accepts null only for `plain`, `mixed`, `bytes`; how to pass a checksum (a `Checksum` object, or a deep celltype) instead of a value.
- **Modules and closures**: closures are not captured; embed modules.
- **Remote execution**: what the worker needs installed; which environments are entered and which only asserted.

### What to ask the user if the contracts do not answer

- Target backends and constraints (no Docker? pinned conda? which scheduler?).
- Whether bitwise reproducibility is required, or a witness plus comparison step.
- Which artifacts may be scratch and which witnesses must stay available.

### Guardrail

If a contract is unclear: conservative local execution, explicit inputs (no closures), content-bound helper code, unscratched witness outputs.
