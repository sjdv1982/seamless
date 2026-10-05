# Hashserver

A lightweight, content-addressed file server over HTTP.

Hashserver stores and serves opaque binary buffers keyed by their cryptographic checksum. You PUT a buffer with its checksum in the URL; you GET it back by the same checksum. There are no filenames, no directories, no metadata — just content and its hash.

The hash algorithm is configurable: SHA-256 (default) or SHA3-256.

## Why content-addressed storage?

Content-addressed storage (CAS) is a well-established pattern used by Git, IPFS, Docker registries, and many other systems. Identifying data by its cryptographic hash gives you automatic deduplication, trivially verifiable integrity, and strong reproducibility guarantees.

Hashserver brings these benefits to any project that needs a simple HTTP-based buffer store. It is intentionally minimal: a single ASGI application backed by a directory of files, designed to be easy to deploy, easy to integrate, and easy to reason about.

## Relationship to Seamless

Hashserver was originally developed as the buffer-serving component of [Seamless](https://github.com/sjdv1982/seamless), a framework for reproducible, reactive computational workflows. In Seamless, all data — inputs, source code, and results — is represented as a tree of checksums, and hashserver provides the storage layer that maps those checksums back to actual data.

However, **hashserver has no dependency on Seamless** and no knowledge of it. It is a generic content-addressed file server that is useful in any context where you need to store and retrieve buffers by hash — caching layers, artifact stores, reproducible pipelines, or your own CAS-backed application. It is published as an independent PyPI package for exactly this reason.

## Features

- **Content-addressed**: buffers are stored and retrieved by their cryptographic checksum.
- **Configurable hash algorithm**: SHA-256 (default) or SHA3-256, selected at startup.
- **Integrity-verified reads**: every buffer (if not compressed) is re-checksummed on GET to detect corruption.
- **Prefix directory layout**: by default, buffers are stored under a two-character prefix subdirectory (e.g. `ab/ab3f7c...`) to avoid filesystem performance problems with large flat directories. A flat layout is also supported.
- **Extra read-only directories**: additional buffer directories can be mounted as fallback read sources.
- **Promises**: a client can announce that a buffer will be uploaded soon via `PUT /promise/{checksum}`. Other clients reading that checksum will wait for the upload rather than getting a 404.
- **Concurrent-safe**: in-flight PUT requests are tracked so concurrent GETs and batch queries return consistent results. Lock files are respected for external writers.
- **Multiple instances**: several hashserver processes can safely share the same buffer directory.
- **Lightweight**: built on FastAPI/Starlette — no database, no external services.
- **Flexible deployment**: run as a CLI tool, under any ASGI server, or via Docker Compose.

## Installation

```bash
pip install hashserver
```

Or with conda:

```bash
mamba env create --file environment.yml
conda activate hashserver
```

## Quick start

Serve buffers from a local directory:

```bash
hashserver ./my-buffers
```

This starts the server under uvicorn on a random free port in the dynamic/private range (`49152-65535`). Run `hashserver -h` for all options.

### Storing and retrieving a buffer

```bash
# Start a writable server
hashserver ./my-buffers --writable --port 8000

# Compute the SHA-256 checksum and upload
CHECKSUM=$(python3 -c "
import hashlib, sys
print(hashlib.sha256(open(sys.argv[1],'rb').read()).hexdigest())
" myfile.bin)
curl -X PUT --data-binary @myfile.bin http://localhost:8000/$CHECKSUM

# Download
curl -O http://localhost:8000/$CHECKSUM
```

To use SHA3-256 instead, start the server with `--hash-algorithm sha3-256` and hash your files with `hashlib.sha3_256`.

### Status-file protocol

`hashserver` does not require a status file. If `--status-file` is omitted, it runs independently.

If `--status-file` is provided, the file is used for two things:

1. Report the chosen port, especially when `--port-range` is used.
2. Report whether startup succeeded (`"running"`) or failed (`"failed"`).

The status-file protocol is as follows:

1. Wait for the status file to exist and parse it as JSON.
2. Reuse the existing JSON object as the base payload. An empty JSON object `{}` is sufficient.
3. Pick or validate its listening port.
4. On ASGI startup, rewrite the same file with `"status": "running"` and the chosen `"port"`.
5. If startup fails before that point, rewrite the file with `"status": "failed"`.

If `remote-http-launcher` is used, it may pre-populate the JSON with fields such as the PID, workdir, or `"status": "starting"`. `hashserver` preserves such fields when it writes back the final status.

## API

### Retrieving buffers

**`GET /{checksum}`** — Retrieve a buffer by its hex checksum. The server verifies the checksum before sending the response. Returns the raw buffer (200), or 404 if not found.

### Storing buffers

Requires `--writable`.

**`PUT /{checksum}`** — Upload a buffer. The request body is the raw data; the server verifies that its checksum matches the URL. Returns 200 on success, 201 if the buffer already existed, or 400 on checksum mismatch.

**`PUT /promise/{checksum}`** — Announce that a buffer will be uploaded soon. Returns 202 with the promise TTL. While a promise is active, GET requests for that checksum will wait rather than returning 404, and `/has` queries will report the checksum as present.

### Querying availability

**`GET /has`** — Batch existence check. Send a JSON list of checksums in the request body. Returns a JSON list of booleans. Includes both on-disk buffers and active promises.

**`GET /has-now`** — Same as `/has`, but excludes promises — only reports buffers that are already on disk.

**`GET /buffer-length`** — Batch size query. Send a JSON list of checksums in the request body. Returns a JSON list of integers: the buffer size in bytes, or 0 if not present. Promised checksums are reported as `true`.

### Health

**`GET /healthcheck`** — Returns "OK". Useful for load balancer probes.

## Configuration

### CLI flags

| Flag | Description | Default |
|------|-------------|---------|
| `directory` | Buffer storage directory (positional, required) | — |
| `--writable` | Enable PUT endpoints | off |
| `--hash-algorithm` | Hash algorithm: `sha3-256` or `sha-256` | `sha-256` |
| `--layout` | Directory layout: `prefix` or `flat` | `prefix` |
| `--extra-dirs` | Semicolon-separated list of extra read-only buffer directories | — |
| `--host` | Listen address | `127.0.0.1` |
| `--port` | Listen port | random free port in `49152-65535` |
| `--port-range START END` | Pick a random free port in range (mutually exclusive with `--port`) | — |
| `--status-file` | JSON file for reporting server status | — |
| `--timeout` | Shut down after this many seconds of inactivity | — |

### Environment variables

When running under an external ASGI server (e.g. `uvicorn hashserver:app`), configure via environment variables instead:

| Variable | Equivalent flag |
|----------|----------------|
| `HASHSERVER_DIRECTORY` | `directory` |
| `HASHSERVER_WRITABLE` | `--writable` (set to `1` or `true`) |
| `HASHSERVER_HASH_ALGORITHM` | `--hash-algorithm` |
| `HASHSERVER_LAYOUT` | `--layout` |
| `HASHSERVER_EXTRA_DIRS` | `--extra-dirs` |

### Docker Compose

```bash
export HASHSERVER_PORT=8000
export HASHSERVER_HOST=0.0.0.0
export HASHSERVER_DIRECTORY=./buffers
export HASHSERVER_WRITABLE=1
docker compose up -d
```

Container user/group ID can be set with `HASHSERVER_USER_ID` and `HASHSERVER_GROUP_ID` (both default to 0).

## Directory layouts

In **prefix** layout (the default), a buffer with checksum `ab3f7c...` is stored as `<directory>/ab/ab3f7c...`. A sentinel file `.HASHSERVER_PREFIX` is written to the directory. This avoids performance issues when storing large numbers of buffers.

In **flat** layout, the same buffer is stored as `<directory>/ab3f7c...`.

Extra directories auto-detect their layout by checking for the `.HASHSERVER_PREFIX` sentinel.

## Compression

Hashserver supports transparent compression for stored buffers. Supported formats: Zstandard (`.zst`) and gzip (`.gz`).

**Core invariant:** The URL checksum is always the canonical checksum of the *decompressed* bytes. A compressed upload of the same content produces the same URL as an uncompressed upload.

**Uploading compressed buffers:** Send `Content-Encoding: zstd` (or `gzip`) on PUT. The server streams the compressed body to disk while simultaneously decompressing to verify the canonical checksum. The compressed bytes are stored at `{dir}/{cs}.zst` (or `.gz`).

**Downloading:** GET always uses the canonical checksum URL. If the stored form is compressed, the response includes `Content-Encoding: zstd` (or `gzip`). The client must check this header and decompress if present. The server tries to honor `Accept-Encoding` when a matching on-disk form exists; otherwise it falls back to the uncompressed file or the server's normal on-disk preference order.

**Coexistence:** Compressed and uncompressed forms of the same buffer coexist safely: `{cs}`, `{cs}.zst`, `{cs}.gz` can all be present.

**`/has` and `/has-now`:** Any stored form satisfies the existence check.

**`/buffer-length`:** Always returns the *uncompressed* byte count. When only a compressed form exists, this is read from a `.BUFFERLENGTH` sidecar file written during the compressed PUT.

## Running tests

```bash
pip install requests
pytest tests/
```

## License

MIT. See [LICENSE.txt](https://github.com/sjdv1982/seamless/blob/main/hashserver/LICENSE.txt).
