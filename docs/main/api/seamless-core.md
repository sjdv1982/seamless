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

The canonical null checksum prints as `NULL` with `str(checksum)` for readability;
use `checksum.hex()` (and not the display form) in serialized data, URLs, and other
machine-readable formats. `repr(checksum)` remains the hexadecimal digest, and
`Checksum("NULL")` is invalid.

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

### HashType and expressions

`HashType` is the checksum metadata surface for new code. It replaces the old
`BufferInfo` decision layer for deserialization, expression path validation, and
celltype conversion feasibility. A HashType is a complete packed integer for a
checksum; it is cached locally and can be shared through `seamless-database`.

Expressions are immutable structural references keyed by exactly:

```text
(input_checksum, path, input_celltype, celltype)
```

Validator fields are deliberately excluded from this cache identity. Empty-path
expressions own checksum-changing celltype conversions; conversion-result
checksums are not recreated as BufferInfo side fields.

`Cell` is a mutable expression builder. `celltype` always describes the produced
checksum/value; retyping converts the stored input. The read-only `input_celltype`
follows a typed source live, or records the type used when a literal/checksum was
assigned. New cells copy a typed source's output type once; otherwise they default
to `mixed`. Existing cells keep their output type when rewired.

```python
from seamless import Buffer, Cell, Expression

cell = Cell("str", checksum=Buffer(42, "int").get_checksum(), input_celltype="int")
assert cell.run() == "42"
cell.celltype = "text"
assert cell.run() == "42"
expression = Expression(cell)  # freezes the input recipe and its type now
```

The constructor accepts either `checksum=` or `source=`, never both. A typed
source's input type cannot be overridden with a conflicting declaration.
`cell.source` reports the typed upstream reference, or None for a literal;
`cell.checksum`, `.buffer`, and `.value` report the produced value. `build()` and
calling a Cell return an immutable Expression. `with_input()` derives a builder
with a replacement reference. Public `input_ref` and `target_celltype` are retired
and raise a replacement-directed error; `_input_ref` is a private recipe field.

Standalone reads do not start an upstream Transformation. `.checksum` uses an
already-produced source result and evaluates the Cell's own projection or
conversion; `.compute()` is the explicit operation that starts missing upstream
work. `.buffer` and `.value` resolve the resulting checksum without fingertipping.
An expression-evaluation failure is retained as `.exception` until
`clear_exception()`; an unavailable result buffer instead raises `CacheMissError`
while the Cell remains complete.

At the root, assigning `.value`, `.buffer`, or `.checksum` declares a new input
and detaches a source. Their ownership-checking counterparts are `.set()`,
`.set_buffer()`, and `.set_checksum(cs, input_celltype=...)`; these raise
`AuthorityError` on a connected input. `.set()` and `.value =` take values only: a
Checksum goes through `.set_checksum()`, and a source is connected by assignment or
with `Cell(source=...)`. Passing a reference raises `TypeError`.

Celltype `checksum` holds a checksum as its value: `.value` is a `Checksum`, and the
buffer is the bare 64-character hex digest, which the cell doesn't hold. For this
celltype alone, a `Checksum` or its hex string is a value in `.set()`, `.value =`,
assignment, `tf.pins.x =` and `tf(x=...)`. For every other celltype, assignment and
call-time arguments read a `Checksum` as a declared reference. A 64-character string
is always a value. Buffer writes validate and deposit bytes;
checksum writes declare an interpretation without resolving bytes. Sub-path
writes retain ownership checks.

`None` is a value for every Cell type, serialized as `b"null\n"` with checksum
`38e0b9de817f645c4bec37c0d4a3e58baecccb040f5718dc069a72c7385a0bed`.
This buffer is trivial and resolves without cache residency. Null converts to
itself for every type pair; resolving as `bytes` gives `b""`, otherwise None.
Empty bytes canonicalize to the same checksum. `.value = None` stores null;
`.checksum = None`, `.buffer = None`, and the corresponding set methods clear
input. `del` remains deletion.

`CellBase` provides the shared value/type/evaluation API for Cell and the
transformer's sister class Pin. Cell alone adds projection, validators, mounts,
derivation, and source protocols. A Pin cannot be used as an input reference.

Transformations can now accept expression handles as inputs, alongside concrete
checksums and transformation futures. Dask submissions represent these as
`kind="expression"` input specs and resolve them before the downstream
transformation runs.

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
