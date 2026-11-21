## In this documentation

**Getting started**

- [Wrapping Python and bash](getting-started.md) — `direct`/`delayed` hello-world + `seamless-run` basics + pitfalls
- [Setting up a local cluster](cluster.md) — persistent caching, service configuration, `seamless-init`
- [Seamless mode](seamless-mode.md) — interactive shell mode that wraps commands with `seamless-run` automatically

**How-to guides**

- [Running R and Julia transformers](r-and-julia-transformers.md) — install the runtimes and packages for local CLI execution
- [Caching, identity, and sharing](caching.md) — what constitutes a cache key, `Checksum` and `Buffer`, `.CHECKSUM` sidecars, the `persistent` command
- [Composition](composition.md) — driver transformations, fan-out, `.modules` and `.globals`
- [Local parallelism](parallelism.md) — `execution: spawn`, `spawn(N)`, `parallel()`, `TransformationList`, `seamless-queue`
- [Remote execution](remote.md) — jobserver vs daskserver, `set_stage()`, `--local`
- [HPC specifics](hpc.md) — SLURM/OAR queue definitions, adaptive scaling, pure Dask mode
- [Remote job launching](remote-launch.md) — CLI workflow for remote clusters, checksum vs buffer distinction, deep checksums
- [Sharing in depth](sharing.md) — `seamless.db` portability, scratch, fingertipping, replay by checksum
- [Compiled transformers](compiled-transformers.md) — wrap C/C++/Fortran/Rust source code as transformations; open language set
- [Compressed data](compression.md) — `.zst`/`.gz` support that never affects identity
- [Service management](service-management.md) — `seamless-service-*` and `rhl-*` helpers; false-pass debugging

**Reference API**

- [Overview](api/index.md) — full API symbol classification
- [seamless-core](api/seamless-core.md) — `Checksum`, `Buffer`, `Cell`, `Expression`, celltypes
- [seamless-transformer](api/seamless-transformer.md) — `Transformer`, `direct`, `delayed`, `parallel`, `Transformation`, `spawn`
- [seamless-workflow](api/seamless-workflow.md) — reactive `Context`, file mounts, Jupyter widgets, HTTP shares
- [seamless-config](api/seamless-config.md) — `init()`, `set_stage()`, YAML command language, cluster definitions
- [seamless-remote](api/seamless-remote.md) — remote clients, `seamless-resolve`, `seamless-fingertip`
- [seamless-dask](api/seamless-dask.md) — Dask integration, `seamless-dask-wrapper`
- [seamless-jobserver](api/seamless-jobserver.md) — lightweight HTTP job dispatcher
- [seamless-database](api/seamless-database.md) — transformation result cache server
- [hashserver](api/hashserver.md) — content-addressed buffer server over HTTP
- [remote-http-launcher](api/remote-http-launcher.md) — service launcher and lifecycle manager
- [seamless-signature](api/seamless-signature.md) — YAML signature schemas for compiled transformers, with C header generation
