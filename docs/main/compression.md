# Working with compressed data

Seamless natively supports `.zst` (Zstandard) and `.gz` (gzip) compressed files. Compression never affects identity or caching — a compressed file and its uncompressed form have the same checksum, the same cache key, and are interchangeable.

## Uploading compressed datasets

```bash
# Upload a directory of gzip-compressed PDB files with zero-copy hardlinking
seamless-upload --destination /buffers --hardlink /data/pdb/
```

For each compressed file, `seamless-upload` computes the canonical checksum by decompressing in-memory (no decompressed copy on disk), then hard-links the original compressed file into the buffer directory. This is the recommended approach for large compressed datasets: zero storage overhead, one-time decompression cost for checksumming.

## Sidecar convention

The `.CHECKSUM` sidecar always uses the canonical name — compression suffixes are stripped:
- `file.npy.zst` → `file.npy.CHECKSUM` (not `file.npy.zst.CHECKSUM`)
- `file.npy.gz` → `file.npy.CHECKSUM`

## Downloading in compressed form

```bash
seamless-download --destination /buffers --compression zst mydir/
```

`--compression` is all-or-nothing: all output files get the suffix.

## Compressing an existing buffer directory

The design is transparent enough that you can compress an existing hashserver buffer directory after the fact:

```bash
for f in /path/to/buffers/*/*; do
  if [[ -f "$f" && "$f" != *.zst && "$f" != *.gz && "$f" != *.BUFFERLENGTH && "$f" != *.LOCK ]]; then
    stat -c%s "$f" > "${f}.BUFFERLENGTH"
    zstd --rm "$f"
  fi
done
```

The hashserver, seamless-upload, seamless-download, and worker materialization all check for `.zst` and `.gz` variants on every file lookup. The `.BUFFERLENGTH` sidecar ensures `/buffer-length` returns the uncompressed size without decompressing. Pre-generating sidecars before compressing is important: without them, the `/buffer-length` endpoint would need to decompress each buffer to determine its uncompressed size (correct but expensive).

## Python face

A Python-face compression mechanism (`transformer.compression.my_pin`) is planned but not yet implemented. Currently, compression is used through the CLI face (filename suffixes).
