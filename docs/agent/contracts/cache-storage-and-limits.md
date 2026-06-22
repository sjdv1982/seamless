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
- Input fingertipping must be enabled per consumer transformation. Use `allow_input_fingertip = True` on the downstream Python transformer/core before constructing the transformation, or `--fingertip` when executing a transformation checksum from the CLI.
- Do not scratch meaning-bearing “witness” artifacts that you may need for audit/falsification or cross-environment comparison.

## Buffer cache (local memory pressure)

Agents should assume there is a local buffer cache with:
- a weak/strong caching strategy
- soft/hard memory caps (eviction pressure)

Practical implication: large runs can evict in-memory buffers; recomputation or remote fetch may be needed to materialize values again.

## Remote/persistent storage (where bytes live)

In remote/persistent setups, bytes/checksums are typically stored in dedicated services (e.g. hashserver/database layers), and the local process may:
- push buffers it produces (unless scratch)
- fetch buffers it needs (materialization/fingertip), subject to availability
- regenerate missing scratch inputs by fingertipping them where the consumer is executing

## Agent checklist

- Always ask which artifacts must remain materializable (witness outputs).
- If results are huge, distinguish final artifacts from generated intermediates. For intermediates, plan for scratch + input fingertipping before proposing invasive rewrites.
- Expect I/O bottlenecks for materialized artifacts, but remember that scratch can avoid durable buffer traffic for bulky generated edges by recomputing them next to consumers.
