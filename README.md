# seamless-suite

`seamless-suite` is the umbrella meta-package for [Seamless](https://github.com/sjdv1982/seamless). Installing it pulls in all standard Seamless components so you don't have to manage them individually.

## Installation

```bash
pip install seamless-suite
```

## What's inside

### User-facing packages

These are the packages your code imports directly:

| Package | Import | Provides |
| --- | --- | --- |
| `seamless-core` | `import seamless` | `Checksum`, `Buffer`, cell types, buffer cache |
| `seamless-transformer` | `from seamless_transformer import direct, delayed` | Transformation definition and execution (Python and bash) |
| `seamless-config` | `import seamless.config` | Configuration, stage management, `init()` / `set_stage()` |

### Internal libraries

These are imported behind the scenes by the user-facing packages, not by user code:

| Package | Role |
| --- | --- |
| `seamless-remote` | Async HTTP clients for buffer, database, jobserver, and daskserver services; launch-aware wrappers. Provides the `seamless-resolve` and `seamless-fingertip` CLI tools. |
| `seamless-dask` | Dask integration for distributed execution on HPC clusters |

### Services

Standalone servers, normally launched by `seamless-config` via `remote-http-launcher`. Communication is over HTTP, not Python import:

| Package | Role |
| --- | --- |
| `seamless-database` | SQLite-backed transformation result cache server |
| `seamless-jobserver` | Lightweight HTTP job dispatcher (primarily a testing tool; Dask is the production path for remote execution) |

### Middleware

| Package | Role |
| --- | --- |
| `remote-http-launcher` | Seamless-independent tool for launching and managing long-running HTTP services, locally or over SSH |
