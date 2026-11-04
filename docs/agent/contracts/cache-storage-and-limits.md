# Cache Storage & Practical Limits (Contract)

This page defines what an agent may assume about Seamless caching/storage at a high level, and what to flag as practical limits.

## What is cached (conceptual)

- Seamless uses content identities (checksums) to represent:
  - code (transformation definitions)
  - inputs
  - outputs
- Caching means: if the same identity is requested again and the output is already present, Seamless can reuse it instead of recomputing.

## What “scratch” means (operational)

- If a result is marked scratch, Seamless may keep only the **result checksum** and not retain the bytes needed to materialize the value later.
- Scratch is appropriate for bulky intermediates that are cheap to recompute.
- Scratch is not only a storage policy. With input fingertipping, a missing scratch input is recomputed at the consumer's execution location, so scratch can keep large producer-consumer edges local to the consuming work.
- Input fingertipping must be enabled per consumer transformation. Use `allow_input_fingertip = True` on the downstream Python transformer/core before constructing the transformation, or `--fingertip` when executing a transformation checksum from the CLI. Without it, the consumer's pins hold their inputs non-scratch, which publishes a scratch producer's result (`contracts/pins.md`, *Scratch at the pin*).
- Do not scratch meaning-bearing “witness” artifacts that you may need for audit/falsification or cross-environment comparison.

## Buffer cache (local memory pressure)

Agents should assume there is a local buffer cache with:
- a weak/strong caching strategy
- soft/hard memory caps (eviction pressure)

Practical implication: large runs can evict in-memory buffers; a local buffer source, a remote fetch or recomputation may be needed to materialize values again.

## Local buffer sources (outside the buffer cache)

Besides the buffer cache, a process can have **local buffer sources**: stores on this process's file system that supply a buffer by checksum. They are kept in one process-wide registry in `seamless-core` (`seamless.caching.buffer_source`), which is internal: it is not an extension point. Two kinds are registered:

- the **read-buffer directories** configured through `seamless-remote`, including the directory of a hashserver that this process launched locally;
- for a workflow Context, the **leaf files of an active `w`/`rw` directory mount** (`contracts/mounts.md`, *Directory mounts*).

Both are resolved in the same way. They differ only in lifetime: a read-buffer directory stays registered for as long as the `seamless-remote` activation that configured it, while a mount's leaf files are registered only while the mount is registered and its delivered index names them. Neither holds a reference claim.

**Mount leaf files are an exception to where buffers ordinarily live.** Ordinarily a buffer is resolvable from the buffer cache or from a hashserver, whether over HTTP or through the hashserver's directory used as a read-buffer directory. A directory write mount's leaf files are an extra source beside these: process-local, claim-free, and bounded by the mount's registration. **Their use case is a configuration without a hashserver.** There, the files of a `w`/`rw` directory mount are the only on-disk copy of the leaf buffers of the deep value it delivered, and serving them back to resolution keeps a leaf that was evicted from the buffer cache resolvable for as long as the mount lasts. The source is active with a hashserver configured too, and is then consulted before it. It originates in Context mounts, but it serves every resolution in the process, for standalone Cells and Expressions as well as for the Context.

What an agent may assume:

- **Resolution order.** `Checksum.resolve()` and `Checksum.resolution()` try the buffer cache, then the local buffer sources, then the remote buffer read servers, and raise `CacheMissError` when none has the buffer. The order among local buffer sources is unspecified. This holds for standalone Cells and Expressions and for a Context alike: a source registered by a Context's mount serves any resolution in the process.
- **Bytes are validated.** A source serves a buffer only if its bytes hash to the requested checksum. A changed or missing file is a miss, and the next source is tried.
- **A source is not a claim.** Registering one takes no reference claim, keeps nothing in memory, protects nothing from eviction and publishes nothing.
- **A source is process-local.** Another process, including a jobserver or a Dask worker, does not see it.
- **Placement counts a source as local** (`contracts/expressions.md`, *Placement*), and a value request counts a buffer in a source as reachable.

Practical implication: after eviction, a buffer that a local buffer source still holds is read back from it, with no recomputation and no remote fetch.

## Remote/persistent storage (where bytes live)

In remote/persistent setups, bytes/checksums are typically stored in dedicated services (e.g. hashserver/database layers), and the local process may:
- push buffers it produces (unless scratch)
- fetch buffers it needs (materialization/fingertip), subject to availability
- regenerate missing scratch inputs by fingertipping them where the consumer is executing

## Agent checklist

- Always ask which artifacts must remain materializable (witness outputs).
- If results are huge, distinguish final artifacts from generated intermediates. For intermediates, plan for scratch + input fingertipping before proposing invasive rewrites.
- Expect I/O bottlenecks for materialized artifacts, but remember that scratch can avoid durable buffer traffic for bulky generated edges by recomputing them next to consumers.
