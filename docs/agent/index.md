# Seamless documentation

This is the documentation home for the new Seamless.

Looking for legacy Seamless (0.x)? Use the legacy docs at `/legacy/`.

## Start here

- Read the contract-oriented overview in `README.md`.
- Browse behavior and cache contracts under `contracts/`.
- Follow how-to guides under `guides/`.
- See generated API reference under `api/`.

## Guides

| Guide | What it covers |
|-------|----------------|
| `guides/seamless-web-server.md` | Making a web server from a workflow Context: shared cells as the whole REST API, the development stage (dev server in front, interactive Context behind; live edit, `%run -i` reload and `authority="file"` mounts; a hardened client) and the deployment stage (script-served, or a built front end packed into a graph and served from a hashserver by a generic server) |

## Contracts quick index

| Contract | What it defines |
|----------|----------------|
| `contracts/execution-backends.md` | `process`, `spawn`, `remote: jobserver/daskserver` semantics; the process lock (one transformation runs its code at a time per process, and gives the lock up when it submits nested work), drivers, the bash nesting signal, handler languages and embedded interpreters, and concurrency per backend; which host must provide the conda environment or the container runtime of a bash transformation |
| `contracts/identity-and-caching.md` | Content-addressing, checksum stability, cache invalidation; load-bearing versus orthogonal keys of a transformation dict, including `__handler__` and the neutral `__format__` entry of handler languages |
| `contracts/celltypes-and-conversion.md` | Layer 1+3 of the stack. The 13 celltypes; celltype hierarchy as a **checksum** hierarchy; canonical null and virtual values; reference parser; the conversion rule table **built on the hierarchy** (`conversion_trivial` *is* the set of hierarchy edges) and `convert_checksum`. The engine is exactly the empty-path case of an Expression |
| `contracts/hashtype.md` | Layer 2. `HashType` checksum classification (replaces `BufferInfo`); the false-negative property (**every `False` is a proof**) and the positive property (**a `True` from `deserializable_as` is a proof**); tightening; `hash_type` database table; `deserializable_as`/`capabilities`/`conversion_feasible`; no deep-celltype vocabulary |
| `contracts/deep-celltypes.md` | A **carve-out at layer 4**, not a layer. `deepcell`/`deepfolder`/`folder`: the flat index buffer, member typing, the legal conversion table, the one-step string-item path rule and the fusion barrier (`module` is not deep) |
| `contracts/expressions.md` | Layer 4. Expressions: **project, then convert** (at most one conversion, always last), the 4-tuple identity, the dummy Expression, path syntax, fusion, placement (`execution="auto"`) and the fingertip exemption from it, publishing vs recording identity, the error envelope, uncached failures, dedup and softcancel, and cell joins (the many-input Expression behind a cell-level join: its JSON, identity, database rows and placement) |
| `contracts/cells.md` | Layer 5. Cells as deferred Expressions, bound or standalone: `celltype` vs read-only `input_celltype`, `.source`/`.checksum`, the two write families and the 3×2 matrix, null and `None`, standalone reads, failures on the handle, projections (project-then-convert on a handle) and connection targets, cell-level joins |
| `contracts/pins.md` | Transformer pins: `tf.pins.x`, the `pin.celltype`/`tf.celltypes.x` link, pins hold checksums, conversion at the pin, optional pins and the null rules, a Pin is not a source |
| `contracts/transformers.md` | Transformers as mutable builders for immutable Transformation snapshots: the factory and the three kinds of language it accepts (native, handler, compiled), standalone and bound modes, binding as a move, mode-independent `build()` / `transformation()`, direct call sugar, named work methods and the result endpoint; the `process_lock` and `driver` settings, their coupling, the rule for absent keys, and operational versus interaction features |
| `contracts/workflow-context.md` | The reactive workflow `Context`: a DAG of nodes with Cells/Transformers as views, assignment and edges, the controller thread and sequenced ingress, barriers and timeouts, optimistic sub-path commits, `prune()`, `get_graph`/`set_graph` |
| `contracts/node-state-lifecycle.md` | The seven node states and how each is derived, connectivity, block reasons and their precedence, the glitch-free cascade, speculative supersession and the three grace holds, `prune`, and states through barriers |
| `contracts/attachments.md` | The attachment framework: sense as an authoritative write and actuate as a post-turn delivery, durable spec vs ephemeral session, the topology rules a sensing attachment imposes, latest delivery discipline, the three-way error model, the oscillation detector, the cut barrier, and the driver roster |
| `contracts/mounts.md` | File mounts: the `ctx.a.mount` API, `mode`/`authority`/`persistent`, the initial decision table, observation classification against one disk belief, canonical bytes and null files, fingerprints and conditional atomic writes, directory mounts (`deepfolder` is sense-only), `ctx.mounts.sync()`, graph serialization and limits |
| `contracts/shares.md` | HTTP shares: `Cell.share`, REST and websocket behavior, marker-based conditional writes, live OpenAPI, the browser client, and graph persistence |
| `contracts/widgets.md` | Jupyter widget attachments: traitlet hubs and links, widget-to-cell sensing, cell-to-widget delivery, `ctx.mounts.sync()`, lifecycle and output widgets |
| `contracts/streaming.md` | Opt-in streaming for `remote: daskserver` transformations and how Transformer and Transformation flags affect submitted work |
| `contracts/transformation-logs.md` | `Transformation.logs` and bound `ctx.tf.logs`: the captured stdout and stderr of a successful run plus its execution time, the failure text, the per-process store keyed by `tf_checksum` (a cache hit has no log), the exact layout and truncation, and what each backend captures, including bash and compiled output |
| `contracts/cancellation.md` | The cancellation substrate: one membership set per deduplication site, `softcancel` = deregister vs hard `cancel` = kill-all, softness cascading to the leaf, no liveness machinery, the soft-only reactive policy, a run that is cancelled while it waits for the process lock, and the teardown of a cancelled bash script and its container |
| `contracts/service-management.md` | `seamless-service-resolve`, `rhl-*` helpers, false-pass protocol |
| `contracts/environments.md` | Environments of CLI jobs, which are bash transformers and the CLI backends of Python, R and Julia: a conda environment (`conda run`) or a Docker image run by docker, podman or apptainer. The closed image spec and its check at dispatch, the runtime chosen on the executing host and its settings, the environment as outside identity, required binaries checked inside the environment, the failure classes, the job directory with its `transform.sh` launcher, and the limits on nesting and cancellation |
| `contracts/language-backends.md` | Language backends: the CLI and in-memory kinds, `BACKEND` (`"cli"` and `"mem"`) for Python, R and Julia, the environment rule of each kind (the in-memory rule and the CLI rule), the checks at run time and at dispatch, required binaries, the public functions `check_in_memory_environment` and `execute_cli`, and the Python CLI backend: what stays the same, what the job needs, results, parity, drivers and nested work |
| `contracts/execution-records.md` | Per-transformation records in `seamless.db`; minimal vs full mode, write-once semantics |
| `contracts/direct-delayed-and-transformation.md` | Immutable Transformation handles and the `direct`/`delayed` Transformer call modes |
| `contracts/scratch-witness-audit.md` | Scratch, witness, and audit trail semantics; fingertipping as recompute-on-absence, where the chain runs, and why neither evaluation nor fingertipping publishes; provenance as the derivation graph, what a walk of the database recovers, coverage gaps and federation |
| `contracts/seamless-run-and-argtyping.md` | The `seamless-run` CLI: argtyping, `--var` vs `--metavar`, `--no-process-lock` and `--driver`, `--conda` and `--docker`, how the first word of a command is resolved, canonicalization, manual remote deployment and the `transform.sh` launcher |
| `contracts/cache-storage-and-limits.md` | What is cached at a high level; the local buffer cache and its memory pressure |
| `contracts/content-addressed-files-and-dirs.md` | Files and directories as checksums; the deep index as a directory identity |
| `contracts/modules-and-closures.md` | Content-bound code: embedding modules, environment envelopes, closures as implicit inputs |
| `contracts/compiled-transformers.md` | C/C++/Fortran/Rust + open language set; identity model and pure-function constraint |
| `contracts/compiled-pins.md` | Compiled transformer input pins: the C ABI rules, schema-derived celltypes and the declaration whitelist, `mixed` as auto, the two validation stages and where they run, scalar and character admission, null, errors |
| `contracts/handler-languages.md` | Handler languages: R, Julia and languages added with `register_language_handler`. The three kinds of language and `available_languages()`, the handler API and its arguments, the block and `transform()` code styles, what the CLI and in-memory backends run and need and their bitwise parity, the value rules for pins and results, deep pins and results, the checksum classes of R and Julia, pins as files, `__handler__` and the backend as orthogonal, honouring an environment through the two public functions, and the in-memory backends' need for the process lock |
| `contracts/seamless-signature-schema.md` | Schema YAML format used by compiled transformers; dtype/shape/wildcard rules |
| `contracts/compression.md` | `.zst`/`.gz` support; canonical-checksum invariant |
