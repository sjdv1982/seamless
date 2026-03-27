# Caching, identity, and sharing

## What constitutes a cache key

Every Seamless transformation has a **transformation checksum** — a SHA-256 hash of everything that defines the computation:

- The code (function body for Python, command string for bash), identified by its checksum.
- All declared input pins: their names, values (identified by checksum), and cell types.
- Metadata that changes execution semantics: the language (`python` or `bash`), module definitions, the scratch flag, and similar.

Two transformations with the same transformation checksum are *identical computations*: the same code, the same inputs, the same semantics. The database records the mapping `transformation checksum → result checksum`. On the next call with the same code and inputs, Seamless computes the same transformation checksum, looks it up in the database, finds the cached result checksum, and returns the result from the hashserver — without re-executing any code.

Changing anything in the above list (code, inputs, metadata) produces a different transformation checksum and triggers re-execution:

```bash
seamless-run 'paste data/a.txt data/b.txt && sleep 5'    # executes, result cached
seamless-run 'paste data/a.txt data/b.txt && sleep 5'    # cache hit, instant

# edit data/a.txt
#   =>
seamless-run 'paste data/a.txt data/b.txt && sleep 5'    # different input checksum, re-executes
```

## Persistent vs in-memory caching

By default, Seamless caches results in memory for the duration of the Python session. This is useful for exploration and development: calling `direct`-wrapped functions twice with the same arguments skips the second execution. But the cache is lost when the process exits.

With persistent caching, the transformation-to-result mapping is stored in `seamless.db` and the result bytes are stored in a buffer directory. Subsequent Python sessions, separate `seamless-run` invocations, and other users with access to the same local machine can all use the same persistent caching.

The simplest way to enable persistent caching is `SEAMLESS_CACHE`:

```bash
export SEAMLESS_CACHE=~/.seamless/cache
```

The cache directory stores both the buffers and the `seamless.db` database.

For more control, see [Setting up a local cluster](cluster.md). A cluster YAML file configures the caching services (`hashserver` for buffers and `database` for `seamless.db`) as well as backends for remote execution (e.g. Dask). Instead of a single, global cache, it allows per-project and per-stage caching and execution.

## `Checksum` and `Buffer` as user-facing objects

The two core types in `seamless-core` are:

- **`Checksum`** — the identity of a piece of data. A thin wrapper around a SHA-256 hex string
- **`Buffer`** — raw bytes paired with an optional checksum.

```python
from seamless import Checksum

cs = Checksum("a3f2...")           # construct from hex string
cs = Buffer(b"hello", "text").get_checksum()  # compute from bytes
value = cs.resolve()               # retrieve the buffer from cache/hashserver
```

`Checksum.resolve()` retrieves the corresponding buffer. If the buffer is not in the local cache or hashserver, it returns `None` (or raises `CacheMissError`). The advanced variant `Checksum.fingertip()` also triggers recomputation if the buffer is missing but a transformation that produced this checksum is known.

```python
from seamless import Buffer

buf = Buffer(b"hello world", "text")
cs = buf.get_checksum()            # compute SHA-256 identity
value = buf.get_value("text")      # deserialize to Python string
buf.write()                        # push bytes to the configured hashserver
```

In normal usage, you don't construct `Checksum` and `Buffer` directly — `direct` and `delayed` handle this internally. They become relevant when you need to inspect transformation results, work with remote data, or implement sharing workflows.

## The `.CHECKSUM` sidecar convention

On the filesystem, Seamless uses `.CHECKSUM` sidecar files: a file `data/input.txt` is accompanied by `data/input.txt.CHECKSUM`, which contains the 64-character hex SHA-256 of `input.txt`.

When `seamless-run` encounters a file argument `data/input.txt`, it first looks for `data/input.txt.CHECKSUM`. If the sidecar exists, Seamless reads the checksum from it — **and the original file does not need to be present locally**. This is the basis of remote workflows: upload inputs once, keep only the checksums, and run without the original files.

`seamless-upload` pushes the file bytes to the hashserver and writes the sidecar:

```bash
seamless-upload data/large-input.h5
# uploads bytes to the hashserver
# writes data/large-input.h5.CHECKSUM
# data/large-input.h5 can now be deleted or archived locally
```

Subsequent `seamless-run` invocations read the checksum from the sidecar without touching the original file:

```bash
seamless-run python analyze.py data/large-input.h5
# data/large-input.h5 need not exist locally — the sidecar supplies its checksum
```

`seamless-download` uses sidecars written by `seamless-run` to fetch result bytes from the hashserver:

```bash
seamless-download data/result.txt
# reads data/result.txt.CHECKSUM, fetches bytes from hashserver
```

The `seamless-checksum` CLI tool computes and prints the checksum of a file without writing it. `seamless-checksum-file` computes and writes the sidecar. `seamless-checksum-index` builds a directory-level checksum index.

## Why sharing follows from content-addressing

Because every piece of data is identified by its checksum, and the transformation cache maps transformation identity to result identity, the following property holds: **if two parties have computed the same transformation, they have the same result** — regardless of when or where they ran it.

Sharing therefore has two modes:

1. **Checksum exchange**: tell a colleague the result checksum. If they have already computed the same transformation (or have the hashserver buffer), they already have the result. No data transfer required.

2. **Database sharing**: copy `seamless.db` to a colleague or a shared location. The database file contains all the (transformation checksum → result checksum) mappings your session has recorded. The recipient can immediately look up any of those results. If they also have access to the same hashserver (or a copy of it), they can retrieve the actual result bytes.

Combining both: copy `seamless.db` between machines, and use `seamless-resolve` to fetch the buffer bytes for any checksum that appears in the database.

For sharing the underlying buffers — input data, result data, or both — see [Sharing in depth](sharing.md).

## Cell types

Every input pin in a Seamless transformation has a *cell type* that governs how the Python value is serialized into bytes (and therefore what checksum it gets). The default type is `mixed`, which handles Python scalars, dicts, lists, and numpy arrays.

For performance-sensitive cases, override the cell type explicitly:

```python
@delayed
def process(matrix):
    import numpy as np
    return np.linalg.norm(matrix)

process.celltypes.matrix = "binary"  # numpy array → .npy format
```

Common overrides:

| Value type | Cell type to use |
|---|---|
| NumPy array | `binary` |
| Raw bytes | `bytes` |
| Python source code | `python` or `text` |
| Checksum identifier | `checksum` |
| Everything else | `mixed` (default) |

The full conversion matrix and all 13 cell types are documented in the [seamless-core reference](api/seamless-core.md).
