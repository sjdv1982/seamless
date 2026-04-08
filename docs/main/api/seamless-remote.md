# seamless-remote

`seamless-remote` is the client connectivity layer of the [Seamless](https://github.com/sjdv1982/seamless) ecosystem. It provides async HTTP clients for every remote service that a Seamless workflow can talk to — buffer storage, transformation cache, jobserver, and Dask scheduler — together with launch-aware wrappers that start those services on demand via `remote-http-launcher`. When `seamless-config` calls `init()` or `set_stage()`, it is `seamless-remote` that opens the actual connections and keeps them alive.

**This is an internal infrastructure package.** User workflow code never imports `seamless-remote` directly — it is activated behind the scenes by `seamless-config` and consumed by `seamless-core`, `seamless-transformer`, and `seamless-dask`. The only user-facing entry points are the two CLI scripts described below.

## Core concepts

### Client hierarchy

Every remote service is accessed through a pair of classes:

| Base client | Launched wrapper | Service |
| --- | --- | --- |
| `BufferClient` | `BufferLaunchedClient` | Content-addressed buffer store (`hashserver`) |
| `DatabaseClient` | `DatabaseLaunchedClient` | Transformation result cache (`seamless-database`) |
| `JobserverClient` | `JobserverLaunchedClient` | HTTP job dispatcher (`seamless-jobserver`) |
| — | `DaskserverLaunchedHandle` | Dask scheduler (`seamless-dask-wrapper`) |

**Base clients** (`BufferClient`, `DatabaseClient`, `JobserverClient`) perform async HTTP against a known host and port. They inherit from a shared `Client` base that manages per-thread `aiohttp` sessions, a retry decorator for transient failures, and a background keepalive thread that healthchecks open connections.

**Launched wrappers** extend the base clients with auto-launch: they call `seamless_config.tools.configure_*()` to build a launch dict, pass it to `remote_http_launcher.run()`, and cache the resulting server address. If the server is already running, the cache returns the existing connection. `DaskserverLaunchedHandle` follows the same pattern but is fully synchronous — it constructs a `distributed.Client` and wraps it in a `SeamlessDaskClient`.

### Activation modules

Each service type has an *activation module* that manages the active set of clients and exposes the async functions consumed by the rest of the Seamless stack:

| Module | Key functions | Used by |
| --- | --- | --- |
| `buffer_remote` | `get_buffer()`, `write_buffer()`, `get_buffer_lengths()`, `promise()` | `seamless-core` (`Checksum.resolve`, `Buffer.write`) |
| `database_remote` | `get_transformation_result()`, `set_transformation_result()`, `get_rev_transformations()` | `seamless-transformer` (cache lookup/store) |
| `jobserver_remote` | `run_transformation()` | `seamless-transformer` (remote job dispatch) |
| `daskserver_remote` | `activate()`, `deactivate()` | `seamless-config` (stage changes) |

Each module maintains separate lists of read and write clients (or a single launched handle for the daskserver). `activate()` is called by `seamless-config` during stage transitions; it instantiates the appropriate clients from the cluster definition and makes them available to downstream consumers.

### Client types: launched vs extern

Clients can be registered in two ways:

- **Launched** — `seamless-remote` starts the service itself (via `remote-http-launcher`). Configuration comes from the cluster definition in `seamless.yaml` / `seamless.profile.yaml`.
- **Extern** — the service is already running and a URL (or local directory, for buffer folders) is provided directly. Useful for shared infrastructure or debugging.

Both are registered through `define_launched_client()` and `define_extern_client()` on the activation module and are selected during `activate()`.

---

## Relation to the Seamless ecosystem

```text
    Seamless runtime                   (Buffer/Checksum, direct/delayed, stages)
        │
        │  resolve/write buffers, check/store cached results,
        │  activate backends and delegate jobs to jobserver or daskserver
        ▼
    seamless-remote                    ◄── this package
        │
        │  async HTTP (aiohttp)
        ▼
    ┌──────────────┐  ┌──────────────────┐  ┌─────────────────┐  ┌────────────────────────┐
    │  hashserver   │  │ seamless-database │  │ seamless-jobserver│  │ seamless-dask-wrapper   │
    │  (buffers)    │  │  (result cache)   │  │  (job dispatch)  │  │  (Dask scheduler)       │
    └──────────────┘  └──────────────────┘  └─────────────────┘  └────────────────────────┘
                                                                          │
                                                          Dask workers run seamless-transformer,
                                                          which calls seamless-remote again
                                                          for nested transformations
```

The Seamless runtime above this layer consists mainly of `seamless-core`, `seamless-transformer`, and `seamless-config`. `seamless-core` uses `seamless-remote` for buffer resolution and writes, `seamless-transformer` uses it for buffer access, cache lookup/store, and job delegation, and `seamless-config` activates the appropriate backends during stage changes. `seamless-remote` in turn talks to four remote services: `hashserver` for buffers, `seamless-database` for transformation results, `seamless-jobserver` for lightweight job dispatch, and `seamless-dask-wrapper` (part of `seamless-dask`) for Dask-based execution. Inside Dask workers, the same path repeats — `seamless-transformer` runs again and calls `seamless-remote` for buffer/cache operations on nested transformations.

`seamless-config` is the only package that calls `activate()` / `deactivate()` directly. All other packages interact with `seamless-remote` through the module-level async functions (`get_buffer`, `run_transformation`, etc.).

---

## Delegation levels

`seamless-remote` enables the tiered delegation model defined by `seamless-config` stages:

| Level | What `seamless-remote` provides |
| --- | --- |
| 0 — in-process | Nothing; all buffers are held in the client. |
| 1 — persistent storage | `buffer_remote` writes/reads buffers via the cluster's hashserver. |
| 2 — cached execution | Additionally, `database_remote` checks and records transformation results. |
| 3 — remote execution | Additionally, `jobserver_remote` or `daskserver_remote` delegates computation. |

Moving between levels is a configuration change (`seamless.yaml` / `seamless.profile.yaml`), not a code change.

---

## CLI scripts

Installing `seamless-remote` provides two utilities for working with content-addressed data from the command line:

| Command | Description |
| --- | --- |
| `seamless-resolve` | Resolve a buffer from its SHA-256 checksum and write it to stdout or a file. |
| `seamless-fingertip` | Like `seamless-resolve`, but uses fingertip resolution (with fallback to recomputation). |

Both accept a `--project` and `--stage` flag to select the storage context, and read remote client configuration from environment variables or config files.

```bash
# Resolve a checksum to a file
seamless-resolve abc123...def --output result.bin

# Resolve with project/stage context
seamless-resolve abc123...def --project myproject --stage prod --output result.bin

# Fingertip (resolve with recomputation fallback)
seamless-fingertip abc123...def --output result.bin
```

---

## Environment variables

| Variable | Default | Effect |
| --- | --- | --- |
| `SEAMLESS_REMOTE_CONNECT_TIMEOUT` | `10` | HTTP connect timeout (seconds) |
| `SEAMLESS_REMOTE_READ_TIMEOUT` | `1200` | HTTP read timeout (seconds) — set high to accommodate hashserver integrity checks on large buffers |
| `SEAMLESS_REMOTE_TOTAL_TIMEOUT` | none | Total request timeout (seconds) |
| `SEAMLESS_REMOTE_HEALTHCHECK_TIMEOUT` | `10` | Keepalive healthcheck timeout (seconds) |
| `SEAMLESS_DATABASE_MAX_INFLIGHT` | `30` | Maximum concurrent in-flight database requests (semaphore) |
| `SEAMLESS_ALLOW_REMOTE_CLIENTS_IN_WORKER` | `false` | Allow remote clients in child worker processes |
| `SEAMLESS_DEBUG_REMOTE_DB` | — | Enable debug logging for `database_remote` |
| `SEAMLESS_CLIENT_DEBUG` | — | Enable debug logging for client session lifecycle |

---

## Installation

```bash
pip install seamless-remote
```

Requires Python >= 3.10. Dependencies: `seamless-core`, `seamless-config`, `aiohttp`, `aiofiles`, `frozendict`.

Optional (activated at runtime when needed): `remote-http-launcher` (for launched clients), `seamless-dask` and `distributed` (for daskserver integration).
