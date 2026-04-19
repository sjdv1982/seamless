# Content-Addressed Files & Directories (Contract)

This page defines what an agent may assume about how Seamless treats **files** and **directories** as inputs/outputs, especially for CLI/subprocess steps.

## Files

- A file can be represented by a **checksum** of its bytes.
- When the checksum is known, the file content is treated as an immutable artifact identified by that checksum.
- “Reading by checksum” is not treated as a semantic side effect in the Seamless model; it is a cache/materialization operation. Therefore, *materialization configuration* (paths or URLs where to find artifacts) can be made available to atransformation without breaking referential transparency, as long as the checksum of each artifact is passed as explicit argument.

## Directories (deep identity)

- A directory can be represented by a *structured* identity: a mapping from relative paths to file checksums.
- This acts like a “directory index” that commits to the directory’s contents.
- Treat it as a deep checksum / Merkle-ish identity: you can refer to the whole directory without materializing every file immediately (depending on how execution/materialization is implemented).

## Practical limitations to keep in mind

- Some tooling will checksum inputs by reading them from disk; if a file is very large, the checksum pass is real I/O work.
- Depending on implementation, checksum calculation may read whole files into memory; for very large files, agents should consider streaming-friendly paths or avoid re-checksumming by reusing known checksums where possible.

## Compression

Files may be stored in compressed form (`.zst` or `.gz`). Compression is a materialization detail — the canonical checksum is always computed over the **decompressed** bytes. A compressed and an uncompressed form of the same content share the same checksum and are interchangeable from the identity model's point of view.

For a full treatment, see `contracts/compression.md`.

## Porting guidance (agent)

- Prefer “pass a checksum identifier as an explicit input” over “read an ambient path”.
- If a transformation must do its own I/O, make the I/O target an explicit content identity (checksum/deep checksum), not an implicit location.
- When filenames may carry compression suffixes (`.npy.zst`, `.csv.gz`), use `strip_compression_suffix` before `os.path.splitext` or sidecar derivation.
