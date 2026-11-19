## Where Seamless is a poor fit, and where it only looks like one

Use this to keep an assessment honest in both directions. Seamless is a computation and caching engine for deterministic work. Its strength is identity: it knows when a result is still valid and can prove that two results came from the same computation. Where that has no value, or where something else carries the value, say so.

### The benefit equation

Benefit is roughly **re-run frequency x reuse surface**, plus provenance where provenance is a deliverable, minus **port cost** and **fork-maintenance cost**. Reuse surface includes parameter sweeps over fixed upstream steps, shared reference data (indexes, databases) across projects, template pipelines instantiated many times, and collaborators sharing a cache. A clean DAG with no reuse is easy to port and still not worth it.

### Genuine misfits

1. **Effectful or orchestration-shaped work.** When the job is to download, upload, delete, notify, write to a live database or manage cloud disk, Seamless is the wrong layer: it is an engine, not a workflow manager. Port the deterministic core (if any) and keep the effects in a script or an orchestrator around it. Scratch plus fingertipping can replace some download-use-delete bookkeeping, but not uploads, notifications or cohort tracking.
2. **One-pass work.** A frozen paper artifact, a single evaluation run, a pipeline run once per dataset with nothing shared. Caching is never hit, yet you pay for hashing, a content store and running services (`seamless-run` needs persistent caching, which launches a hashserver and database).
3. **Exploration where the code is still being thrown away.** Reuse has no value yet, and the discipline Seamless enforces (no hidden inputs inside cached steps) costs effort on code you will delete. If exploration must live inside a Seamless project, a per-run nonce input (`seamless-run --var NONCE=$(uuidgen) ...`) forces recomputation and `--scratch` keeps single-use results out of the store; this gives "Seamless with reuse switched off", not a benefit.
4. **Someone else maintains the pipeline.** Porting an nf-core pipeline or one built on snakemake-wrappers forks it away from community maintenance and its tests. In practice ownership decides more often than DAG shape: a lab-owned or frozen pipeline has no fork cost; a community one usually makes a port net-negative.
5. **Ecosystem value.** Snakemake wrappers, `report:` HTML, `script:`/`notebook:` calling conventions, executor breadth for many schedulers and clouds, Nextflow's container and executor integration. These are accumulated conveniences, but they are real losses for a project that leans on them.
6. **Non-canonical containers at step boundaries.** HDF5, bigwig, `.npz` (per-entry timestamps), pickle, BAM files with version or command-line headers: the same logical content gives different bytes. Two harms: caching misses (safe but wasteful: everything downstream reruns) and audits fail bitwise comparison even when the science is identical. Disposition: inside one transformation, leave it; for opaque upstream inputs, accept them as blobs keyed by their bytes or convert on ingest to `mixed`; for artifacts the pipeline emits, canonicalize (this is reproducibility cleanup any framework would need once someone runs `sha256sum`). `.gz` and `.zst` are not a problem: Seamless checksums the decompressed bytes.
7. **Bitwise-nondeterministic tools on the critical path.** Multithreaded assemblers, aligners with unordered output, GPU reductions. Either pin threads (costing parallelism) or compare a witness (metrics, sorted output) instead of the raw artifact (`env-null-hypothesis.md`).
8. **Live state** (control loops, trading, "latest" data) and **inherently non-reproducible measurements** with no seed or witness that makes the claim testable.

### Workflow-face specific

If the user wants the workflow face (reactive notebook, file-synced cells, web API) check these before recommending it: no macros, stdlib or Silk; no sub-contexts; no authentication or TLS on HTTP shares (and the default bind is all interfaces); widgets are not saved; very large graphs must be loaded in one `set_graph()`; saved graphs need a persistent buffer store to reopen. See `faces.md`.

### Things that look like misfits but are not

Do not raise these as disadvantages without checking:

- **Data-dependent DAGs** (Snakemake checkpoints, Nextflow channel operators). A driver transformation iterates a deep checksum (for example a `folder` index) and launches one sub-transformation per member, without materializing the members.
- **Loops and iteration.** A driver loop, cached per iteration.
- **Live in-process objects shared between steps.** Hold them inside one driver body; they cannot cross processes in any framework.
- **Inspecting intermediate files.** Non-scratch results stay retrievable; in a Context, mount a cell to a file.
- **Hidden-state "sloppiness" during development.** A nonce switches reuse off for the steps being hacked; Seamless only forbids the combination "hidden input and silently reused result", which is the stale-result bug of mtime-based tools.
- **Hashing cost.** Hashing runs at GB/s; for most scientific steps compute dominates. It matters only for huge data that is processed once.

### A real wart worth naming

Mixing faces inside one pipeline is clumsy: a Python driver that wants to launch `seamless-run` command steps either shells out or builds a `Transformer("bash")` step over values, and the two have different identities (file names count on the Unix face). Plan the boundary between faces deliberately.
