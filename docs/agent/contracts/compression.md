# Native Compression Support (Contract)

Seamless natively supports `.zst` (Zstandard) and `.gz` (gzip) compression for file buffers. Compression is a **materialization detail** — it never participates in identity or caching.

Scientific workflows can produce massive amounts of data, and the hashserver buffer directory often lives on a shared HPC network filesystem where storage pressure is real. Native compression support provides transparent, optional relief: compressed and uncompressed forms coexist under the same checksum identity, so teams can compress buffers at their own pace without coordination.

This also means that common scientific datasets distributed in compressed form (PDB as `.pdb.gz`, array data as `.npy.zst`) can be ingested directly without decompressing to disk — and with `--hardlink`, without any storage overhead at all.

The design is transparent enough that even running `zstd --rm` on the entire buffer directory after the fact will "just work" — the hashserver and all clients (seamless-upload, seamless-download, worker materialization) check for `.zst` and `.gz` variants on every lookup. The only caveat: without `.BUFFERLENGTH` sidecar files, the `/buffer-length` endpoint must decompress each buffer to determine its uncompressed size (correct but expensive). Pre-generating sidecars before compressing avoids this:

```bash
for f in /path/to/buffers/*/*; do
  if [[ -f "$f" && "$f" != *.zst && "$f" != *.gz && "$f" != *.BUFFERLENGTH && "$f" != *.LOCK ]]; then
    stat -c%s "$f" > "${f}.BUFFERLENGTH"
    zstd --rm "$f"
  fi
done
```

## Core invariant

**The canonical checksum is always computed over the *decompressed* bytes.**

`file.npy.zst` and `file.npy` have the same canonical checksum. A compressed and an uncompressed form of the same content are identical artifacts from the caching system's point of view. Uploading a buffer in compressed form does not create a new identity; it adds a new stored form for an existing identity.

## What compression affects and what it does not

| Aspect | Affected by compression? |
| --- | --- |
| Canonical checksum | No — always decompressed bytes |
| Transformation cache key | No |
| `.INDEX` leaf names for deep/directory pins | No — always canonical names |
| Storage path on disk | Yes — `ab/abcd.zst` vs `ab/abcd` |
| HTTP `Content-Encoding` on GET | Yes |
| HTTP `Content-Encoding` on PUT | Yes |
| Pin name in CLI/bash face | Yes — suffix is encoded in the filename |
| `buffer-length` endpoint | No — always returns uncompressed size |

## Supported formats

- `.zst` — Zstandard (preferred: faster decompression)
- `.gz` — gzip

The constant `COMPRESSION_PREFERENCE = (".zst", ".gz")` governs preference order when both forms are present.

## Buffer storage layout

Compressed and uncompressed forms of the same buffer coexist naturally under the same prefix directory:

```text
./ab/abcd          # uncompressed
./ab/abcd.zst      # Zstandard-compressed form
./ab/abcd.gz       # gzip-compressed form
./ab/abcd.BUFFERLENGTH  # sidecar: uncompressed byte count (only when no uncompressed file present)
```

Any or all of these may exist. Their coexistence is safe; having both does not cause inconsistency.

## The `.BUFFERLENGTH` sidecar

When a buffer is stored **only** in compressed form, the hashserver writes a `.BUFFERLENGTH` sidecar file containing the uncompressed byte count as a decimal integer. This lets the `/buffer-length` endpoint return the canonical (uncompressed) size without decompressing on read.

The sidecar is deleted automatically when an uncompressed form of the same buffer is later uploaded, because the size can then be obtained directly via `stat()`.

Agents should not write or read `.BUFFERLENGTH` sidecars directly — they are an internal implementation detail of the hashserver.

## `strip_compression_suffix`

A utility function available in both `hashserver.compression_utils` and `seamless_transformer.compression_utils`:

```python
from seamless_transformer.compression_utils import strip_compression_suffix

base, suffix = strip_compression_suffix("file.npy.zst")
# base = "file.npy", suffix = ".zst"

base, suffix = strip_compression_suffix("file.npy")
# base = "file.npy", suffix = None
```

**Always use `strip_compression_suffix` before calling `os.path.splitext`.** Calling `os.path.splitext("file.npy.zst")` returns `(".zst")` which discards the semantic extension.

## Sidecar files (`.CHECKSUM`, `.INDEX`)

Compression suffixes are stripped before deriving sidecar names:

- `file.npy.zst` → sidecar is `file.npy.CHECKSUM` (not `file.npy.zst.CHECKSUM`)
- `file.npy.gz` → sidecar is `file.npy.CHECKSUM`

`file.npy.zst.CHECKSUM` is **never** a valid sidecar name.

## CLI / bash face

In the CLI and bash transformation face, compression is encoded in the filename and therefore in the pin name:

```bash
# Input: file.npy.zst → pin name becomes file1.npy.zst
seamless-run --input file.npy.zst mycommand
```

Pin names carry the compression suffix. The worker reads the suffix from the pin name and materializes the buffer in the matching compression format.

## Directory (deepfolder) pins

For directory-typed pins, the compression suffix on the **pin name** applies to all leaves:

- Pin `mydata.zst` → directory on disk is `mydata/`, each leaf `file.npy` is materialized as `mydata/file.npy.zst`
- Pin `mydata` → each leaf is materialized uncompressed (or whatever stored form is available)

The `.INDEX` always uses canonical leaf names (no compression suffixes). The directory checksum is unaffected by which compression format is used for leaf storage.

## Read-buffer materialization (worker side)

When materializing a pin from the read buffer folder:

1. **Fast path**: if the stored form matches the requested suffix, create a symlink.
2. **Fallback**: if only a non-matching form is available, read it, transcode (decompress and/or compress), and write the result to the pin path. No symlink.

Agents should not assume that the fast path is always taken, but can assume that the resulting bytes at the pin path will always match what was uploaded (decompressed if needed).

Decompression failures during materialization raise an error — there is no silent fallback to corrupt data.

## Hashserver HTTP protocol

### PUT (upload)

Send `Content-Encoding: zstd` or `Content-Encoding: gzip` with the compressed body. The URL checksum is always the canonical (decompressed) checksum:

```http
PUT /{canonical_checksum}
Content-Encoding: zstd
<compressed body>
```

The hashserver decompresses the body on-the-fly during PUT to verify the canonical checksum and compute the uncompressed size. The compressed bytes are stored as-is.

If the checksum of the decompressed content does not match the URL, the server returns 400.

### GET (download)

The URL remains `/{canonical_checksum}`. The response `Content-Encoding` header tells the client which stored form was served:

```http
GET /{canonical_checksum}
→ Content-Encoding: zstd   (if only compressed form is stored)
→ (no Content-Encoding)    (if uncompressed form is served)
```

The server serves whichever stored form exists, there is only limited client-driven content negotiation (`Accept-Encoding`) — the server will only serve what it has. If you need a specific form, request it from an upload that provided that form.

The client must decompress the body if `Content-Encoding` is set.

### `/has` and `/has-now`

These endpoints answer "do you have this canonical content?", not "do you have it in a specific encoding?". Any stored form (uncompressed, `.zst`, `.gz`) satisfies the query. An agent can rely on `/has` returning true whenever the buffer was uploaded in any form.

### `/buffer-length`

Always returns the **uncompressed** byte count, regardless of what form is stored.

## Agent guidance

- Never include a compression suffix in a URL checksum path — URLs always use the raw 64-hex-char checksum.
- When uploading compressed files, send `Content-Encoding` on PUT; the URL checksum must be the canonical (decompressed) checksum.
- When processing GET responses, check `Content-Encoding` and decompress before use.
- Use `strip_compression_suffix` anywhere a filename may carry a compression suffix before calling `os.path.splitext` or deriving sidecar names.
- Do not assume a specific stored form exists — the client should handle both compressed and uncompressed responses from GET.
- The Python face (`transformer.compression.my_pin`) is deferred and not yet implemented; use the CLI face (suffix in the pin/filename) for now.
