# seamless-database

`seamless-database` is the checksum-based metadata and caching service for the [Seamless](https://github.com/sjdv1982/seamless) framework. It acts as the distributed computation cache that allows Seamless workflows to avoid recomputing identical transformations, both within a single session and across the entire cluster.

## How it works

Seamless uses content-addressed storage: every piece of data (buffers, code, parameters) is identified by its checksum. When a transformation (computation) is submitted, its inputs are hashed into a transformation checksum. Before executing the computation, Seamless components (such as `seamless-dask`) query the database: *"has this transformation been computed before?"* If a cached result is found, the result checksum is returned immediately, skipping the computation entirely.

The database stores the following kinds of records:

| Table | Purpose |
|-------|---------|
| **Transformation** | Maps a transformation checksum to its result checksum |
| **RevTransformation** | Reverse lookup: finds which transformations produced a given result |
| **BufferInfo** | Stores buffer metadata (length, dtype, encoding, etc.) for a checksum |
| **SyntacticToSemantic** | Maps between syntactic and semantic checksums per celltype |
| **Expression** | Caches expression evaluation results (input checksum + path + celltype → result checksum) |
| **MetaData** | Stores a canonical execution record for each successful, non-probe transformation |
| **IrreproducibleTransformation** | Records transformations whose results are not reproducible; metadata is preserved on migration |

All data is persisted in a single SQLite file (typically `seamless.db`). The current protocol version is **2.1**.

## Execution records

`MetaData` stores one canonical execution record per successful, non-probe transformation, keyed by `tf_checksum`. Records are **write-once**: subsequent calls to a recorded transformation hit the normal `Transformation` cache and do not re-enter the record path.

Two record sizes coexist under the same schema:

- **Minimal record (default)** — `schema_version`, `tf_checksum`, `result_checksum`, `seamless_version`, `execution_mode`, `remote_target`, `wall_time_seconds`, `cpu_time_user_seconds`, `cpu_time_system_seconds`, `memory_peak_bytes`, `gpu_memory_peak_bytes`. The hot path pays only timing/memory capture and one write.
- **Full record (`record: true` in `seamless.profile.yaml`)** — adds environment fingerprints (content-addressed `node`, `environment`, `queue` sub-buffer checksums), compilation context, validation snapshots, contract-violation lists, execution envelope (requested cluster/queue/node, scratch/fingertip flags, resolved `__env__`), and per-job freshness/retry/worker fields.

The validator on `PUT metadata` checks identity only — record syntax (integer `schema_version`, body `tf_checksum`/`result_checksum` matching the request, sane `checksum_fields` if present) — not the full payload schema. Identical duplicates are idempotent successes; differing bodies are rejected. Once `IrreproducibleTransformation` rows exist for a `tf_checksum`, `PUT metadata` for that checksum is rejected to avoid silently migrating it back into the normal cache.

When a normal entry moves to `IrreproducibleTransformation`, its metadata body travels with it unchanged.

### Schema upgrade from legacy

The legacy `meta_data` table had two columns (`checksum PRIMARY KEY`, `metadata JSON`). On startup, `seamless-database`:

- creates the upgraded table fresh if absent,
- drops and recreates the legacy table if it is empty,
- preserves an already-upgraded table on subsequent starts,
- and **fails loudly** if a non-empty legacy table is present (it must be migrated explicitly).

### Endpoints (request types)

- `PUT metadata` — atomically creates missing `Transformation` and `RevTransformation` rows alongside the `MetaData` row. Body: `{type: "metadata", checksum: <tf>, result: <result>, value: <record>}`.
- `GET metadata` — return the canonical record body for a `tf_checksum`.
- `GET irreproducible` — return all rows for a `tf_checksum`, optionally filtered by `result`. Each row includes `checksum`, `result`, and `metadata`.
- `PUT irreproducible` — move a normal entry into `IrreproducibleTransformation`, preserving metadata.

The remote-client equivalents are `set_execution_record`, `get_execution_record`, and `get_irreproducible_records` in `seamless-remote`.

See the [agent contract](https://github.com/sjdv1982/seamless/blob/main/docs/agent/contracts/execution-records.md) for the full behavioral spec.

## Role in the Seamless ecosystem

Other Seamless components interact with the database over HTTP:

- **seamless-dask** checks the database cache before scheduling a transformation on the Dask cluster, and writes results back after computation.
- **seamless-remote** provides the `DatabaseClient` / `DatabaseLaunchedClient` classes that other components use to communicate with the database server.
- **seamless-config** defines the launch template for the database server (port range, host, timeout, read/write mode).

The server exposes a JSON-over-HTTP protocol: clients send `{"type": "<record_type>", "checksum": "<hex>", ...}` via GET (read) or PUT (write) requests.

## Installation

```bash
pip install seamless-database
```

## Usage

```bash
# Start a writable database server on a random port
seamless-database seamless.db --port-range 5520 5530 --writable

# Start a read-only server on a fixed port
seamless-database seamless.db --port 5522
```

If `--port` and `--port-range` are both omitted, `seamless-database` picks a random free port in the dynamic/private range (`49152-65535`).

### Status-file protocol

`seamless-database` does not require a status file. If `--status-file` is omitted, it runs independently.

If `--status-file` is provided, the file is used for two things:

1. Report the chosen port, especially when `--port-range` is used.
2. Report whether startup succeeded (`"running"`) or failed (`"failed"`).

The status-file protocol is simple:

1. Wait for the status file to exist and parse it as JSON.
2. Reuse the existing JSON object as the base payload. An empty JSON object `{}` is sufficient.
3. Choose or validate its listening port.
4. Once the HTTP server is up, rewrite the same file with `"status": "running"` and the selected `"port"`.
5. If startup fails before the server is running, rewrite the file with `"status": "failed"` instead.

If `remote-http-launcher` is used, it may pre-populate the JSON with fields such as the PID, workdir, or `"status": "starting"`. `seamless-database` preserves such fields when it writes back the final status.

### CLI options

| Option | Description |
|--------|-------------|
| `database_file` | Path to the SQLite file (created if it doesn't exist and `--writable` is set) |
| `--port PORT` | Fixed network port |
| `--port-range START END` | Pick a random free port from an inclusive range |
| `--host HOST` | Bind address (default: `0.0.0.0`) |
| `--writable` | Allow PUT requests; opens the database in read/write mode |
| `--status-file FILE` | JSON file used to report server status (for process managers) |
| `--timeout SECONDS` | Stop the server after this many seconds of inactivity |

## CLI scripts

Installing `seamless-database` also provides:

- `seamless-database`
