# seamless-core

`seamless-core` is the foundational data layer of the [Seamless](https://github.com/sjdv1982/seamless) ecosystem. It provides a content-addressed data model built around two core abstractions — `Checksum` and `Buffer` — together with a cell type system for serializing and converting structured data, and a smart in-memory buffer cache.

While `seamless-core` underpins higher-level Seamless packages (`seamless-config`, `seamless-remote`, `seamless-transformer`, `seamless-dask`), it is also usable on its own as a content-addressed data serialization and caching library.

## Core concepts

### Checksum

`Checksum` wraps a SHA-256 hash as a first-class Python object. Beyond simple identity, it supports:

- Construction from hex strings, raw bytes, or other `Checksum` instances.
- `resolve()` — retrieve the corresponding buffer from the local cache or a remote server.
- `fingertip()` — resolve with fallback to recomputation (if a transformation produced this checksum).
- `incref()` / `decref()` / `tempref()` — reference counting to keep buffers alive in the cache.
- `load()` / `save()` — file I/O (auto-appends `.CHECKSUM` extension).

### Buffer

`Buffer` represents raw content (bytes) paired with an optional checksum. It bridges Python values and content-addressed storage:

- Construct from raw bytes, or from a Python value plus a cell type: `Buffer(value, celltype="plain")`.
- `get_value(celltype)` — deserialize the buffer back to a Python object.
- `get_checksum()` — compute the SHA-256 checksum (lazily, cached).
- `incref()` / `decref()` / `tempref()` — manage buffer lifetime in the cache.
- `load()` / `save()` — file I/O.

### Cell types and conversions

Seamless defines 13 cell types that govern how Python values are serialized into buffers and deserialized back:

| Cell type | Serialized form |
|-----------|----------------|
| `plain` | JSON (2-space indent, sorted keys) |
| `text`, `python`, `ipython` | UTF-8 text (with AST/syntax validation for code types) |
| `yaml` | UTF-8 YAML text |
| `str`, `int`, `float`, `bool` | JSON scalar + newline |
| `binary` | NumPy `.npy` format |
| `bytes` | Raw bytes |
| `mixed` | Umbrella format for heterogeneous data (nested dicts/lists containing numpy arrays, scalars, and strings).  "plain" and "binary" are special cases of "mixed" |
| `checksum` | Hex-encoded SHA-256 strings (or dicts/lists thereof) |

A complete **conversion matrix** classifies every possible type-pair conversion:

- **Trivial** — checksum-preserving, always safe (e.g. `text` → `bytes`).
- **Reinterpret** — checksum-preserving, may fail (reverse of trivial).
- **Reformat** — may change checksum, always safe (e.g. `bytes` → `binary`).
- **Possible** — may change checksum, may fail (e.g. `mixed` → `int`).
- **Forbidden** — requires value-level evaluation or is disallowed.

This conversion system ensures that type coercions across the Seamless ecosystem are well-defined and reproducible.

### Buffer cache

The buffer cache is a dual weak/strong in-memory store:

- **Weak cache** — buffers registered without references; eligible for garbage collection.
- **Strong cache** — buffers with active references (`incref` or `tempref`); kept alive.

Temporary references (`tempref`) model decaying interest — useful for intermediate results that may or may not be needed again. When memory usage exceeds configurable soft/hard caps (default 5 GB / 50 GB), the cache evicts buffers in cost-aware order, considering download cost, recomputation cost, and buffer size.

## Installation

```bash
pip install seamless-core
```

## CLI scripts

Installing `seamless-core` also provides:

- `seamless-checksum` — compute the SHA-256 checksum of a file.
- `seamless-checksum-file` — compute and write a `.CHECKSUM` sidecar file.
- `seamless-checksum-index` — build checksum indices for directories.

## Development build

```bash
python -m pip install --upgrade build
python -m build
```
