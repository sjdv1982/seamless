# Reference API

This section documents the user-facing API of the Seamless suite.

## Python API summary

The table below classifies every user-facing Python symbol by how central it is to day-to-day use. **Core** symbols are needed for basic usage; **Advanced** symbols unlock important capabilities; **Specialized/utility** symbols are for diagnostics, edge cases, and internal plumbing.

### From `seamless` (seamless-core)

| Symbol | Classification |
|---|---|
| `Checksum` | **Core** |
| `Buffer` | **Core** |
| `Checksum.resolve()` / `.resolution()` | **Core** |
| `Buffer.get_checksum()` | **Core** |
| `Buffer.get_value(celltype)` | **Core** |
| `Checksum.fingertip()` / `.fingertip_sync()` | **Advanced** |
| `Checksum.load()` / `.save()` | Specialized/utility |
| `Checksum.incref()` / `.decref()` / `.tempref()` | Specialized/utility |
| `Checksum.find()` | Specialized/utility |
| `Buffer.load()` / `.save()` | Specialized/utility |
| `Buffer.write()` | Specialized/utility |
| `Buffer.incref()` / `.decref()` / `.tempref()` | Specialized/utility |
| `CacheMissError` | Specialized/utility |
| `seamless.close()` | Specialized/utility |

### From `seamless.transformer` (seamless-transformer)

| Symbol | Classification |
|---|---|
| `direct` | **Core** |
| `delayed` | **Core** |
| `Transformation.run()` | **Core** |
| `Transformation.compute()` | **Core** |
| `Transformation.start()` | **Core** |
| `spawn()` / `has_spawned()` | **Core** |
| `Transformation.task()` | Core |
| `Transformation.transformation_checksum` | **Advanced** |
| `Transformation.result_checksum` | **Advanced** |
| `Transformation.construct()` | Specialized/utility |
| `Transformation.value` / `.buffer` | Specialized/utility |
| `Transformation.status` / `.exception` / `.logs` | Specialized/utility |

### Transformer properties

| Property | Classification |
|---|---|
| `.celltypes` | **Advanced** |
| `.modules` | **Advanced** |
| `.globals` | **Advanced** |
| `.scratch` | **Advanced** |
| `.local` | **Advanced** |
| `.driver` | **Advanced** |
| `.environment` | **Advanced** |
| `.allow_input_fingertip` | Specialized/utility |
| `.direct_print` | Specialized/utility |
| `.meta` | Specialized/utility |

### From `seamless.config` (seamless-config)

| Symbol | Classification |
|---|---|
| `init()` | **Core** |
| `set_stage()` | **Advanced** |
| `set_substage()` | Specialized/utility |
| `set_workdir()` | Specialized/utility |
| `collect_remote_clients()` / `set_remote_clients()` | Specialized/utility |

---

## CLI API summary

### Core CLI tools

| Tool | Purpose |
|---|---|
| `seamless-run` | Wrap a bash command as a Seamless transformation |
| `seamless-upload` | Stage input files for `seamless-run` |
| `seamless-download` | Retrieve result files after `seamless-run` |
| `seamless-init` | Initialize configuration from the command line |

### Advanced CLI tools

| Tool | Purpose |
|---|---|
| `seamless-run-transformation` | Execute any transformation by checksum |
| `seamless-queue` / `seamless-queue-finish` | Parallelization for `--qsubmit` jobs |
| `seamless-resolve` | Fetch a buffer by checksum |
| `seamless-fingertip` | Resolve-or-recompute by checksum |

### Specialized/utility CLI tools

| Tool | Purpose |
|---|---|
| `seamless-checksum` | Compute the Seamless checksum of a file |
| `seamless-checksum-file` | Write a `.CHECKSUM` sidecar file |
| `seamless-checksum-index` | Build directory checksum indices |
| `hashserver` | Run a buffer store server |
| `seamless-database` | Run a transformation result cache server |
| `seamless-jobserver` | Run a job dispatch server |
| `seamless-dask-wrapper` | Run a Dask cluster |
| `remote-http-launcher` | Launch/reconnect to HTTP services |

---

## Per-package reference

- [seamless-core](seamless-core.md) — `Checksum`, `Buffer`, cell types, buffer cache
- [seamless-transformer](seamless-transformer.md) — `direct`, `delayed`, `Transformation`, `spawn`, `seamless-run`
- [seamless-config](seamless-config.md) — `init()`, `set_stage()`, YAML command language, cluster definitions
- [seamless-remote](seamless-remote.md) — remote clients, `seamless-resolve`, `seamless-fingertip`
- [seamless-dask](seamless-dask.md) — Dask integration, `seamless-dask-wrapper`
- [seamless-jobserver](seamless-jobserver.md) — lightweight HTTP job dispatcher
- [seamless-database](seamless-database.md) — transformation result cache server
- [remote-http-launcher](remote-http-launcher.md) — service launcher and lifecycle manager
