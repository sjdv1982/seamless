# Seamless

**Seamless: define your computation once — cache it, scale it, share it.**

Most computational pipelines are already reproducible — the same inputs produce the same outputs. Wrap your code as a step with declared inputs and outputs, and Seamless gives you caching (never recompute what you've already computed) and remote deployment (run on a cluster without changing your code). Remote execution also acts as a reproducibility test: if your wrapped code runs on a clean worker and produces the same result, it is reproducible. If not, Seamless has helped you find the problem — whether it's a missing input, an undeclared dependency, or a sensitivity to platform or library versions.

Seamless wraps both Python and command-line code. In Python, `direct` runs a function immediately; `delayed` records the function for deferred or remote execution. From the shell, `seamless-run` wraps any command as a Seamless transformation — no Python required. In both cases, the transformation is identified by the checksum of its code and inputs: identical work always produces the same identity.

Sharing works at two levels. The lightweight path is to exchange checksums: if two researchers have computed the same transformation, they already have the same result — no data transfer needed. The concrete path is to share the `seamless.db` file, a portable SQLite database that maps transformation checksums to result checksums. Copy it to a colleague, a cluster, or a publication archive, and every cached result travels with it. Combined, these two paths let a lab build up a shared computation cache that grows over time and never recomputes what anyone has already computed.

## What about interactivity?

This is Seamless 1.x, running on a new code architecture. Seamless 0.x offered an interactive, notebook-first workflow experience with reactive cells, Jupyter widget integration, filesystem mounting, and collaborative web interfaces. These
features are being ported to the new architecture. If your work is primarily
interactive/exploratory, you can use the [legacy version](https://sjdv1982.github.io/seamless/legacy/)
today, or watch this space for updates.

## Installation

```bash
pip install seamless-suite
```

This installs all standard Seamless components. For a minimal install, the core user-facing packages are:

| Package | Import | Provides |
| --- | --- | --- |
| `seamless-core` | `import seamless` | `Checksum`, `Buffer`, cell types, buffer cache |
| `seamless-transformer` | `from seamless.transformer import direct, delayed` | `direct`, `delayed`, `seamless-run`, `seamless-upload`, `seamless-download` |
| `seamless-config` | `import seamless.config` | `seamless.config.init()`, `seamless-init` |

---

## In this documentation

**Getting started**

- [Wrapping Python and bash](getting-started.md) — `direct`/`delayed` hello-world + `seamless-run` basics + pitfalls
- [Setting up a local cluster](cluster.md) — persistent caching, service configuration, `seamless-init`

**How-to guides**

- [Caching, identity, and sharing](caching.md) — what constitutes a cache key, `Checksum` and `Buffer`, `.CHECKSUM` sidecars, the `persistent` command
- [Composition](composition.md) — driver transformations, fan-out, `.modules` and `.globals`
- [Local parallelism](parallelism.md) — `execution: spawn`, `spawn(N)` in Python, `seamless-queue`
- [Remote execution](remote.md) — jobserver vs daskserver, `set_stage()`, `--local`
- [HPC specifics](hpc.md) — SLURM/OAR queue definitions, adaptive scaling, pure Dask mode
- [Remote job launching](remote-launch.md) — CLI workflow for remote clusters, checksum vs buffer distinction, deep checksums
- [Sharing in depth](sharing.md) — `seamless.db` portability, scratch, fingertipping, replay by checksum

**Reference API**

- [Overview](api/index.md) — full API symbol classification
- [seamless-core](api/seamless-core.md) — `Checksum`, `Buffer`, cell types
- [seamless-transformer](api/seamless-transformer.md) — `direct`, `delayed`, `Transformation`, `spawn`
- [seamless-config](api/seamless-config.md) — `init()`, `set_stage()`, YAML command language, cluster definitions
- [seamless-remote](api/seamless-remote.md) — remote clients, `seamless-resolve`, `seamless-fingertip`
- [seamless-dask](api/seamless-dask.md) — Dask integration, `seamless-dask-wrapper`
- [seamless-jobserver](api/seamless-jobserver.md) — lightweight HTTP job dispatcher
- [seamless-database](api/seamless-database.md) — transformation result cache server
- [remote-http-launcher](api/remote-http-launcher.md) — service launcher and lifecycle manager
