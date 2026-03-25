# Sharing in depth

## `seamless.db` portability

The database file `seamless.db` is a plain SQLite file. It contains all the transformation-to-result checksum mappings recorded in your sessions. It does not contain the result bytes — only the identities.

To share your computation history with a colleague:

1. Copy `seamless.db` to them (email, shared storage, publication archive — any method works).
2. They add it as a read-only database source in their cluster configuration.
3. Any transformation they run that matches a checksum in your `seamless.db` will be a cache hit — they get the result without re-executing, provided they can also resolve the result checksum (i.e., they have access to the hashserver, or you've shared the buffers too).

For a fully self-contained sharing package: copy both `seamless.db` and a snapshot of the hashserver buffer directory. The buffer directory is already content-addressed: any file with checksum `abc123...` is at `buffers/ab/c1/23...` (or equivalent). You can rsync just the relevant buffer files if you know which checksums you need. Depending on the use case, you may rsync a transformation's input buffers, the result buffer, or both.

`seamless.db` is also useful as a **reproducibility record**: it proves that your results were produced by transformations with known checksums. Attach it to a paper or dataset (with the necessary buffer files) and anyone with Seamless can verify or replay your computations.

Because Seamless uses plain SHA-256 for all checksums, its buffers are compatible with any content-addressed storage system that speaks SHA-256. Common choices for distributing buffers externally:

- **Git LFS**: uses SHA-256 object identifiers. Push Seamless buffer files as LFS objects and version them alongside your code.
- **Zenodo / data repositories**: upload buffer files (or a tar of the buffer directory) to a data archive. Publish the checksum alongside the DOI so recipients can verify integrity after download.
- **Direct rsync / object storage**: rsync exactly the files you need using a manifest of checksums, or push them to an S3 bucket with checksum-derived keys.

For input buffers, `seamless-upload` is the most convenient path: it pushes bytes to the hashserver and writes `.CHECKSUM` sidecars (see [Caching, identity, and sharing](caching.md#the-checksum-sidecar-convention)).

---

## Scratch: trade storage for recomputation

Some transformations produce large intermediate results that you don't need to keep permanently — as long as you can recompute them on demand. The `scratch` flag embeds this policy into the transformation: results are recorded in the database (checksum mapping is durable) but the result bytes are not stored in the hashserver.

This is the producer side of the scratch/fingertipping duality: mark the transformation as scratch so the large buffer is never stored. On the consumer side, fingertipping re-executes the transformation to recover the bytes when needed (see [Fingertipping](#fingertipping-resolve-or-recompute) below).

**In Python:**

```python
@delayed
def compute_intermediate(data):
    ...

compute_intermediate.scratch = True
```

**In bash:**

```bash
seamless-run --scratch expensive-step input.txt --capture intermediate.bin
```

A scratch transformation's result checksum is known and addressable — you can pass it to downstream transformations as a `checksum`-typed input — but you cannot materialize it (fetch its bytes) directly. If a downstream step needs the bytes, Seamless will fingertip them: look up which transformation produced that checksum and re-execute it.

**When to use scratch**: large binary intermediates that are cheap to recompute relative to their storage cost. The result checksum is real, durable, and participates in downstream caching — only the bytes are transient.

**When not to use scratch**: any result you want to inspect directly, or that is expensive to recompute but cheap to store.

---

## Fingertipping: resolve-or-recompute

**Fingertipping** is the consumer side of the scratch/fingertipping duality. When a checksum's buffer is not in the hashserver — because the transformation was marked `scratch`, or because the buffer was never shared — fingertipping looks up which transformation produced that checksum (via the database's reverse lookup) and re-executes it to recover the bytes.

This is particularly useful when **recomputation is cheaper than sharing the result buffer** — for example, when the result is large and the computation is fast, or when storing and distributing large outputs is impractical. The workflow is:
.

1. Run the computation with `scratch` enabled, so the large result buffer is never stored.
2. Share the input buffers and `seamless.db`, and the result checksum.
3. The recipient does not need the result buffer. When they request the result, Seamless looks up the transformation, fetches the inputs, and recomputes — producing the same result checksum, confirming reproducibility.

### From Python

```python
from seamless import Checksum

cs = Checksum("a3f2...")
buf = cs.fingertip()         # resolve or recompute; returns Buffer or raises
value = buf.get_value("text")
```

`fingertip()` is synchronous. `fingertip_sync()` is an alias. Both block until the result is materialized (which may involve re-executing a computation).

### From the CLI

```bash
# Fetch the buffer by checksum, triggering recomputation if needed
seamless-fingertip a3f2...  > result.txt
```

`seamless-fingertip` is similar to `seamless-resolve` but with the recomputation fallback.

### On `seamless-run`

The `--fingertip` flag on `seamless-run` enables fingertipping for the transformation's inputs: if an input checksum is known but its buffer is missing from the hashserver, Seamless will fingertip it before running the transformation.

```bash
seamless-run --fingertip mycommand input.txt
```

Without `--fingertip`, a missing input buffer raises a `CacheMissError`.

---

## Replay by checksum: `seamless-run-transformation`

`seamless-run-transformation` is the universal transformation executor. It accepts a **transformation checksum** (not input arguments) and executes the corresponding transformation, returning the result checksum.

```bash
# Run a transformation by its checksum
seamless-run-transformation b7e4...
# prints: result checksum e9a1...
```

This is the "give someone a checksum and they re-run it" sharing path. If you publish a transformation checksum alongside your `seamless.db`, anyone with Seamless — and with the exact same inputs that you used — can re-execute your exact computation and verify that they get the same result checksum.

The transformation dict (inputs, code, language) is identified by the checksum. As long as the transformation dict's buffer is available (in the hashserver or resolvable via fingertipping), `seamless-run-transformation` can execute it.

This is also useful for debugging: if a transformation in your database produced an unexpected result, re-execute it by checksum to confirm the result is reproducible, and compare with the stored result.

---

## The full sharing picture

| Scenario | Tool |
|---|---|
| "We've both computed this; you have the result" | Exchange checksums; no data transfer |
| "Share my computation history" | Copy `seamless.db` |
| "Share my computation history + results" | Copy `seamless.db` + hashserver buffer dir |
| "Fetch a result buffer by checksum" | `seamless-resolve` |
| "Fetch a result buffer, recomputing if missing" | `seamless-fingertip` / `Checksum.fingertip()` |
| "Re-execute a specific computation by identity" | `seamless-run-transformation` |
| "Store identity but not bytes (large intermediate)" | `.scratch = True` / `seamless-run --scratch` |
