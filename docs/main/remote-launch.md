# Remote job launching

This guide shows how to run `seamless-run` jobs against a remote cluster from your local machine. It covers the full CLI workflow, explains the mental model for working without local file access on the remote, and explains the distinction between checksums and buffers in a distributed setting.

## The mental model: unlearn remote filenames

When running locally, it feels natural to think in terms of file paths: "input.txt goes in, result.csv comes out". In a remote workflow, the remote worker has no access to your local files — and you have no access to its local files. Everything is exchanged via the hashserver, using checksums as identifiers.

The key shift: **think in checksums, not filenames**.

- Before running: your input file `input.txt` gets an identity (its checksum). The bytes are uploaded to the hashserver.
- During running: the worker fetches the input bytes from the hashserver by checksum, runs the command, and pushes the result bytes back to the hashserver.
- After running: you fetch the result bytes from the hashserver by checksum and write them to a local file.

The filename is a local convenience. The checksum is the global identity. The hashserver bridges the two.

---

## The three-step CLI workflow

### Step 1: upload inputs

```bash
seamless-upload data/input.txt data/params.json
```

This uploads the file bytes to the hashserver and writes sidecar files:

- `data/input.txt.CHECKSUM`
- `data/params.json.CHECKSUM`

Uploading is idempotent: re-uploading the same file is a no-op (the hashserver already has the bytes).

### Step 2: run the transformation

```bash
seamless-run mycommand data/input.txt data/params.json --capture result.csv
```

Because `.CHECKSUM` sidecars exist, `seamless-run` reads the input checksums from them rather than re-uploading. It constructs the transformation, looks it up in the database, and either returns the cached result or submits the job to the configured backend (jobserver or daskserver).

If the result is cached, this step completes in milliseconds. If the result is new, the job runs on the remote worker.

When the transformation completes, `seamless-run` writes `result.csv.CHECKSUM` locally.

### Step 3: download results

```bash
seamless-download result.csv
```

This reads `result.csv.CHECKSUM` and fetches the corresponding bytes from the hashserver, writing them to `result.csv`.

---

## Staged execution: separate upload, run, and download

For batch workflows — many runs over the same input with varying parameters — upload once, run many times, download at the end:

```bash
# Upload the shared input once
seamless-upload data/large-dataset.h5

# Run many variants (these can be parallelized with seamless-queue --qsubmit)
seamless-run analyse data/large-dataset.h5 --var threshold=0.1 --capture out-0.1.csv
seamless-run analyse data/large-dataset.h5 --var threshold=0.2 --capture out-0.2.csv
seamless-run analyse data/large-dataset.h5 --var threshold=0.5 --capture out-0.5.csv

# Download all results
seamless-download out-0.1.csv out-0.2.csv out-0.5.csv
```

The `--no-download` (`-nd`) flag runs the transformation and records the result checksum without fetching the result bytes. Use it when you only need the checksum (for sharing, replay, or downstream inputs) and not the bytes themselves.

Note that after uploading, you can remove `large-dataset.h5` from your local machine. Always invoke `seamless-run analyze large-dataset.h5` — Seamless finds `large-dataset.h5.CHECKSUM` automatically, reads the checksum from it, and the `analyze` command receives `large-dataset.h5` as its argument. On the remote worker, the actual dataset bytes are fetched from the hashserver and materialised as `large-dataset.h5` in the working directory.

Do **not** invoke `seamless-run analyze large-dataset.h5.CHECKSUM`: the sidecar path is then treated as a literal input, `analyze` receives `large-dataset.h5.CHECKSUM` as its argument, and the remote worker only materialises the 64-character checksum string — not the dataset. See [The `.CHECKSUM` sidecar convention](caching.md#the-checksum-sidecar-convention) for a full explanation.

Therefore, an alternate "upload" strategy is for the case where the large dataset is already on the remote machine: login to the remote machine, install Seamless, configure the hashserver storage dir, and do something like `cd /tmp; ln -s /data/large-dataset.h5; seamless-upload --hardlink large-dataset.h5`. This will create `large-dataset.h5.CHECKSUM`, which you can copy to your local machine. On the remote machine, '--hardlink' prevents duplication of the dataset.

---

## Checksum vs buffer: what travels where

| Concept | What it is | Where it lives |
|---|---|---|
| Checksum | 64-character hex SHA-256 | `.CHECKSUM` sidecar file, database, Python `Checksum` object |
| Buffer | Raw bytes of a value | Hashserver buffer directory |

Checksums are tiny and can be shared freely — by email, in a config file, in a paper's supplementary material. Buffers are the actual data and can be large.

A result that has been computed is always in the database (the transformation→result checksum mapping). The result bytes may or may not be in the hashserver, depending on whether the transformation used `--scratch` (see [Sharing in depth](sharing.md)).

For ordinary inputs, a remote worker materializes bytes by fetching the buffer from the hashserver. Scratch inputs with fingertipping are different: if the input checksum is known but the buffer is absent, Seamless recomputes the producer transformation where the consuming job needs the bytes. This makes scratch useful for bulky generated intermediates that should not be uploaded or stored as durable buffers; the checksum travels, and the bytes are regenerated co-located with the consumer.

`seamless-resolve` fetches a buffer by checksum:

```bash
seamless-resolve a3f2...  > result.csv
```

`seamless-fingertip` does the same but will also trigger recomputation if the buffer is not in the hashserver:

```bash
seamless-fingertip a3f2...  > result.csv
```

---

## Deep checksums for directories

Directories are not treated as single files. Seamless computes a **deep checksum** (a Merkle-like structure): a structured mapping from relative file paths to file checksums, which itself gets a checksum. This means:

- Changing one file in a large input directory only changes those files' checksums and the directory's deep checksum — not every file's content is re-uploaded.
- Two directory inputs with the same deep checksum are identical, even if they arrived from different machines.

Upload a directory the same way as a file:

```bash
seamless-upload data/my-dataset/
# creates data/my-dataset/.CHECKSUM  (the deep checksum of the directory)
```

`seamless-checksum-index` builds the per-file index under the directory, which `seamless-upload` uses to avoid re-uploading files that are already in the hashserver.
