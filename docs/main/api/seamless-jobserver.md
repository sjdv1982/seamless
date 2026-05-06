# seamless-jobserver

`seamless-jobserver` is a lightweight async HTTP service in the [Seamless](https://github.com/sjdv1982/seamless) ecosystem. It receives transformation jobs over HTTP, dispatches them to spawned Seamless worker processes, and returns the results. It is one of the four backend services that `seamless-remote` connects to.

**This is a standalone service, not a library.** User workflow code never imports `seamless-jobserver` — it runs as an independent process, normally launched by `seamless-config` via `remote-http-launcher`. The only user-facing entry point is the `seamless-jobserver` CLI command.

## How it works

The jobserver is a single-module (`jobserver.py`) aiohttp server. On startup it spawns a pool of Seamless worker processes (via `seamless-transformer`). Incoming transformation requests arrive over HTTP, are dispatched to the worker pool, and results are returned to the caller — which is always `seamless-remote`'s `jobserver_remote` module, never user code directly.

### HTTP endpoints

| Endpoint | Method | Description |
| --- | --- | --- |
| `/` | GET | Welcome / version check |
| `/healthcheck` | GET | Liveness probe |
| `/run-transformation` | GET | Execute a transformation and return a structured success payload (result checksum + worker-side metadata for the execution record) |

The `/run-transformation` response is a structured JSON payload carrying the result checksum together with fields needed for execution-record assembly: worker freshness, GPU memory peak, compiled-module digest and compilation times, retry counts, and probe context. Older callers that only consumed the bare checksum string still work — `seamless-remote` parses both shapes.

### Lifecycle

1. `seamless-config` writes a status file and launches `seamless-jobserver` (via `remote-http-launcher` or directly).
2. The jobserver picks a port (fixed or random from a range), spawns worker processes, and starts listening.
3. It writes its port and status back to the status file so `seamless-remote` can discover it.
4. If no requests arrive within the inactivity timeout, the jobserver shuts down automatically.

---

## Relation to the Seamless ecosystem

```text
    seamless-transformer                (user-facing API: direct, delayed)
        │
        │  delegate job
        ▼
    seamless-remote
        │  jobserver_remote
        │  async HTTP
        ▼
    seamless-jobserver                 ◄── this package
        │
        │  dispatches to worker pool
        ▼
    seamless-transformer worker        (spawned child processes)
```

The jobserver sits between `seamless-remote` (which sends it work) and `seamless-transformer` (whose worker processes do the actual computation). It is a simpler, single-machine alternative to the Dask-based execution path provided by `seamless-dask`.

---

## CLI

```bash
seamless-jobserver [options]
```

| Flag | Default | Description |
| --- | --- | --- |
| `--port PORT` | — | Listen on a specific port (mutually exclusive with `--port-range`) |
| `--port-range START END` | — | Pick a random free port from a range |
| `--host HOST` | `0.0.0.0` | Listening address |
| `--status-file PATH` | — | JSON file for reporting port and status |
| `--timeout SECONDS` | — | Auto-shutdown after this many seconds of inactivity |
| `--workers N` | `1` | Number of worker processes to spawn |

---

## Installation

```bash
pip install seamless-jobserver
```

Requires Python >= 3.10. Dependencies: `aiohttp`, `seamless-core`, `seamless-transformer`. Also imports `seamless-remote` and `seamless-config` at runtime for client cleanup and remote-client configuration respectively.
