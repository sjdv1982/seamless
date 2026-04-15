# Native Compression Support — Implementation Plan

## Design Principles

- **Canonical checksum**: always computed over decompressed bytes. `file.npy.zst` and `file.npy` share the same checksum.
- **Supported suffixes**: `.zst` and `.gz` only.
- **Compression is a materialization detail**: it never participates in identity.
- **Hashserver stays dumb**: no decompression on GET; decompression only on PUT (to compute the canonical checksum).
- **Storage layout**: compressed form lives alongside the uncompressed form, e.g. `./ab/abcd.zst` and `./ab/abcd`.
- **CLI face**: compression is encoded in the filename, therefore in the pin name — no alternative without semantic redefinition.
- **Python face**: a `compression` parameter is added to cell/pin declaration; pin names remain Python identifiers.
- **Sidecar files**: the compression suffix is stripped before deriving the sidecar name — `file.npy.zst` → `file.npy.CHECKSUM`, not `file.npy.zst.CHECKSUM`.
- **Symlink preference**: at the read buffer folder level, a symlink to the matching stored form is always preferred; materializing a converted copy is the fallback.
- **Client-side verification**: a config option (not a fixed policy).
- **`/has` endpoint**: deferred.

---

## Shared Utility

Before touching any level, introduce a small shared module (e.g. `compression_utils.py`) that all levels import:

```python
COMPRESSION_SUFFIXES = (".zst", ".gz")

def strip_compression_suffix(name: str) -> tuple[str, str | None]:
    """Return (base_name, suffix) where suffix is '.zst', '.gz', or None."""
    for suffix in COMPRESSION_SUFFIXES:
        if name.endswith(suffix):
            return name[: -len(suffix)], suffix
    return name, None

def decompress_bytes(data: bytes, suffix: str) -> bytes:
    """Decompress bytes given a compression suffix."""
    if suffix == ".zst":
        import zstandard
        return zstandard.ZstdDecompressor().decompress(data)
    elif suffix == ".gz":
        import gzip
        return gzip.decompress(data)
    raise ValueError(suffix)

def compress_bytes(data: bytes, suffix: str) -> bytes:
    """Compress bytes to the given compression format."""
    if suffix == ".zst":
        import zstandard
        return zstandard.ZstdCompressor().compress(data)
    elif suffix == ".gz":
        import gzip
        return gzip.compress(data)
    raise ValueError(suffix)
```

Place this in both the hashserver package and the seamless-transformer package (or in a shared dependency if one exists).

---

## Level 4 — Hashserver (`hashserver/hashserver.py`, `hashserver/hash_file_response.py`)

### PUT handler (`put_file()`, lines 721–806)

Current behaviour: client provides canonical checksum in the URL. Hashserver streams received bytes, computes checksum, verifies against the URL checksum, stores at `./ab/abcd`.

Changes:

1. Read the `Content-Encoding` request header. If `zstd` or `gzip`:
   - Set `path = ./ab/abcd.zst` (or `.gz`) as the storage target.
   - During streaming: write compressed chunks to the temp file **and simultaneously** feed decompressed chunks to `cs_stream` (the checksum stream). This requires a streaming decompressor running in parallel:
     - zstd: `zstandard.ZstdDecompressor().decompressobj()`
     - gzip: wrap an in-memory buffer with `gzip.GzipFile`
   - Verify `cs_stream.hexdigest() == checksum_str` (the canonical checksum of decompressed content).
   - Store compressed bytes at `./ab/abcd.zst`.
2. If no `Content-Encoding`: existing behaviour unchanged (store at `./ab/abcd`).
3. Existence check (line 738): also check for the complementary forms. If `./ab/abcd` already exists when a `.zst` PUT arrives (or vice versa), still store the new form — both can coexist.

The hashserver does **not** decompress on GET. Decompression cost on PUT is acceptable: PUT requests are rare (one per job completion) and throughput is ~10⁸–10⁹ uncompressed bytes/sec.

### GET handler / `HashFileResponse` (`hash_file_response.py`, lines 59–189)

Current behaviour: serves `./ab/abcd` as-is.

Changes:

1. Parse the `Accept-Encoding` request header.
2. Determine which stored forms exist for the requested checksum.
3. Match the client's preference against available forms and serve accordingly, setting the `Content-Encoding` response header.
4. If the preferred form is not available: return 404 for that encoding. No conversion. The client must request a form that was uploaded.

The URL remains `/{checksum}` (the canonical checksum). A URL like `/{checksum}.zst` would fail `parse_checksum` validation, so `Accept-Encoding` is the correct mechanism — not a suffix in the URL.

### `/has` and `/has-now` endpoints (`_has()`, lines 508–570)

Current behaviour: checks only `./ab/abcd`.

Changes: for each canonical checksum, also check `./ab/abcd.zst` and `./ab/abcd.gz`. Any stored form satisfies the query — the endpoint answers "do you have this canonical content?" not "do you have it in this specific encoding?".

### `/buffer-length` endpoint (lines 462–505)

Current behaviour: returns the size of `./ab/abcd`.

Changes: always return the **canonical (uncompressed) size**.

- If `./ab/abcd` exists: `stat()` it directly as before.
- If only a compressed form exists (`./ab/abcd.zst` or `.gz`): read the size from a sidecar file `./ab/abcd.BUFFERLENGTH` (a plain text file containing the uncompressed byte count as a decimal integer).

The sidecar is managed by the PUT handler:

- On compressed PUT: after verifying the canonical checksum, record the decompressed byte count and write `./ab/abcd.BUFFERLENGTH`.
- When an uncompressed PUT for the same checksum arrives later: store `./ab/abcd` as normal, then delete `./ab/abcd.BUFFERLENGTH` (no longer needed).

### Storage layout

No schema migration needed. `./ab/abcd`, `./ab/abcd.zst`, `./ab/abcd.gz` coexist naturally under the same prefix directory.

---

## Level 3 — Read Buffer Folder (`transformation_namespace.py`, `execute_bash.py`)

### `_buffer_path_candidates` (lines 19–23)

Current behaviour: returns `directory/abcd` and `directory/ab/abcd`.

Changes: also return compressed variants, guided by the **requested** compression suffix (derived from the pin name):

```python
def _buffer_path_candidates(
    directory: str, checksum_hex: str, compression_suffix: str | None = None
) -> tuple[str, ...]:
    bases = (
        os.path.join(directory, checksum_hex),
        os.path.join(directory, checksum_hex[:2], checksum_hex),
    )
    if compression_suffix:
        # Preferred: matching compressed form first, then uncompressed fallback
        return (
            bases[0] + compression_suffix,
            bases[1] + compression_suffix,
            bases[0],
            bases[1],
        )
    else:
        # Preferred: uncompressed first, then compressed fallback
        return bases + tuple(b + s for b in bases for s in COMPRESSION_SUFFIXES)
```

### `_find_filesystem_path` (lines 50–67)

Changes:

1. Accept `pin_name` (or `compression_suffix`) so it can pass it to `_buffer_path_candidates`.
2. Return both the found path **and** whether it required a compression conversion (i.e. the found suffix does not match the requested suffix).

### Symlink / copy logic in `execute_bash.py` (lines 76–83)

Current behaviour: `os.symlink(v, pin)` where `v` is the found path.

Changes:

1. Extract the compression suffix from the pin name using `strip_compression_suffix`.
2. Find the candidate path (from `_find_filesystem_path`), noting whether a conversion is needed.
3. **Fast path** (suffix matches): create symlink as before.
4. **Fallback** (suffix mismatch): read the found file, convert (decompress or compress), write the result to the pin name. No symlink.

```python
pin_base, pin_suffix = strip_compression_suffix(pin)
found_path, found_suffix = _find_filesystem_path(checksum, "file", directories, pin_suffix)
if found_path:
    if found_suffix == pin_suffix:
        os.symlink(found_path, pin)
    else:
        data = open(found_path, "rb").read()
        if found_suffix:
            data = decompress_bytes(data, found_suffix)
        if pin_suffix:
            data = compress_bytes(data, pin_suffix)
        with open(pin, "wb") as f:
            f.write(data)
```

---

## Level 2 — Named Pins

No structural changes required. The compression suffix is carried naturally in the pin name. The level 3 logic reads the suffix from the pin name and acts accordingly.

---

## Level 1 — CLI / Bash Transformer Ecosystem

### `file_mapping.py` — `extension` mapping mode (lines 144–165)

Current behaviour: `os.path.splitext("file.npy.zst")` returns `(".zst")`, producing pin name `file1.zst` instead of `file1.npy.zst`.

Fix: use `strip_compression_suffix` to peel the compression suffix first, then apply `os.path.splitext` to the remainder, then reattach:

```python
base, comp_suffix = strip_compression_suffix(path)
semantic_ext = os.path.splitext(base)[1]
extension = semantic_ext + (comp_suffix or "")
```

This yields `file1.npy.zst` for `file.npy.zst` and `file1.npy` for `file.npy`.

### `parsing.py` — sidecar file handling

When resolving `.CHECKSUM` or `.INDEX` sidecar names for a compressed file, strip the compression suffix first:

```python
base, _ = strip_compression_suffix(filename)
sidecar = base + ".CHECKSUM"
```

`file.npy.zst.CHECKSUM` is **never** a valid sidecar name.

### `register.py` — `_resolve_destination_path()` (lines 46–56)

Extend to resolve `./ab/abcd.zst` and `./ab/abcd.gz` as valid destination paths alongside `./ab/abcd`. The compression suffix is preserved in the destination path.

Also update `_buffers_exist_remote()` (lines 189–199) to check for compressed variants when testing buffer existence.

### `upload.py` / `download.py`

**Upload**: when the source file has a compression suffix, compute the canonical checksum by decompressing locally (or trust the hashserver to do so on PUT — prefer the latter to keep upload simple). Send `Content-Encoding` header on PUT.

**Download**: send `Accept-Encoding` header expressing the preferred compression format (derived from the requested filename suffix). If the server returns a different encoding than requested, either accept it or materialize a converted copy locally.

### `seamless-run` suffix wrangling

Audit all existing suffix-handling code in `cmd/api/main.py` and related files. Any `os.path.splitext` call on a filename that may carry a compression suffix must be updated to use `strip_compression_suffix` first.

---

## Python Face

### `transformer_class.py` — `CelltypesWrapper` / `ArgsWrapper`

Add a `compression` parameter alongside `celltype`:

```python
transformer.compression.my_pin = "zst"   # or "gz" or None
```

This is stored as metadata on the pin. At pretransformation time it is encoded into the `__format__` section for the pin (see below).

### `pretransformation.py` — `__format__` section (lines 203–235)

When a pin has a `compression` value, add it to the format dict:

```python
format_section[pinname]["compression"] = "zst"  # or "gz"
```

At execution time, the `execute_bash.py` level 3 logic reads `compression` from the format section to determine which stored form to look for, independent of the pin name (since Python-face pin names are Python identifiers, not filenames).

---

## Cross-Cutting: Client-Side Verification

Add a config option (e.g. `SEAMLESS_VERIFY_BUFFERS=true`) that, when set, causes the client to:

1. After reading a file from the read buffer folder (whether by symlink or copy), decompress if needed and compute the canonical checksum.
2. Compare against the expected checksum.
3. Raise an error on mismatch.

This is off by default (performance-sensitive HPC deployments trust the hashserver). The verification path must exist and be tested, but the policy is the user's.

---

## Testing Strategy

1. **Unit tests** for `compression_utils.py`: round-trip compress/decompress for both `.zst` and `.gz`.
2. **Hashserver tests**: PUT compressed file → correct canonical checksum returned; GET with `Accept-Encoding` → correct form served; GET unavailable form → 404.
3. **Level 3 tests**: symlink fast path (matching form on disk); conversion fallback (only non-matching form on disk).
4. **`file_mapping.py` tests**: `extension` mode with `.npy.zst`, `.npy.gz`, `.npy` inputs.
5. **Sidecar tests**: verify `.CHECKSUM` sidecar is resolved to `file.npy.CHECKSUM` for `file.npy.zst` input.
6. **End-to-end test**: upload `file.npy.zst`, run bash transformation expecting `file.npy`, verify correct bytes received.

---

## Deferred

- `/has` endpoint compression awareness
- Cross-format conversion at the hashserver (e.g. client has `.gz`, requests `.zst`) — currently: 404, client materializes locally
- Compression support for directory-typed pins
- Compression support in deep cells / deep checksums
