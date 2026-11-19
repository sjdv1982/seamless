## Environment as a nuisance parameter (working null)

Use this stance when judging whether Seamless suits a project whose computations are naturally transformations. It is the practical side of the positioning paper's "Popperian" treatment of determinism.

### Working null hypothesis

For a given computation, treat the execution environment as a **nuisance parameter**: time, host, PID; hardware (CPU/GPU); numerical libraries (NumPy, BLAS, libm); tool versions inside a container.

Null (optimistic) claim: the scientifically meaningful result is invariant under such variation.

This is not "prove the environment never matters". It is a falsifiable working assumption that recomputation can attack. That is why Seamless keeps the environment **outside** a transformation's identity (`identity-and-caching.md`): results computed in two environments are two observations of one claim, and can be compared. Keying identity on the environment (the Bazel position) would make every environment a different computation and remove the comparison.

### Falsification needs a recomputation, and caching suppresses it

A transformation is computed once; every later request for the same `tf_checksum` is a cache hit and runs nothing. **A cache hit is not evidence of determinism** (`identity-and-caching.md`, *Caching masks accidental nondeterminism*). Divergence surfaces only when something is recomputed:

- **fingertipping**: a requested buffer is absent (evicted, or `scratch` and never stored), so its producer runs again in the process that wants it;
- **independent computation**: another site or worker computes the same transformation and records a different result;
- **deliberate audit**: Seamless 1.5 has no documented recompute-and-compare command (`identity-and-caching.md`, *Forcing recomputation / auditing*: ask the user). `seamless-run --undo` was meant to quarantine a cached result, but in 1.5 it fails ("Transformation could not be declared irreproducible"). Practical routes: recompute in a fresh project or stage (an empty cache) and compare result checksums, or quarantine through the database's manual `PUT irreproducible` mode.

When a recomputation gives a different result and a database is configured, Seamless keeps the original forward result and adds an **automatic irreproducible observation** (`execution-records.md`). Without a database it only logs a warning. A fingertip that hits this reports `fingertip_category == "irreproducible_transformation"` on the `CacheMissError`.

Practical rule: **any buffer that may be fingertipped (every `scratch` producer, and in principle any evictable buffer) must come from a reproducible producer** (`scratch-witness-audit.md`).

### Recording the environment

Every successful transformation persists a minimal execution record (timing, memory, execution mode) in `seamless.db`. With `record: true` (`- record: true` in `seamless.profile.yaml`, or `seamless_config.select.select_record(True)`) the record adds environment fingerprints and compilation context. Probes are manual and cached per bucket; Seamless does not re-probe on suspicion of drift. The record does not say which container image ran. Use full records when the user is debugging environment drift, auditing, or publishing a `seamless.db`.

### What to compare

- Best case: **bitwise identity** of the meaning-bearing result.
- Otherwise, a **witness**: a small, non-scratched output that encodes the scientific meaning, often with diagnostics (classifier: `(label, margin)`; physics: `(dE, uncertainty)`). State the acceptance test (byte-identical, tolerance, invariants, distributional).

### Scratch policy: never scratch witnesses

Scratch bulky intermediates freely, but not the witness used for cross-environment comparison or the diagnostics needed to interpret a mismatch. Over-scratching reduces falsification to "recompute and hope".

### When this philosophy does not fit

- Outputs are extremely environment-sensitive and no robust witness or comparison rule exists.
- Recomputation is infeasible (no access to inputs or compute) and referential transparency cannot be argued from first principles.
- Hidden external state (network "latest", user config, a mutable database) is part of the computation and cannot be made an explicit input.
- Step boundaries carry non-canonical containers (HDF5, `.npz`, pickle): every recomputation looks irreproducible. See `poor-fit.md`.

### When referential transparency is predictable from first principles

High-confidence cases: integer or exact computation; pure text or byte processing; parallelism that only changes ordering, if you canonicalize (sort records) before checksumming. Set and record locale knobs (`LC_ALL`) for Unix tools. Even then, keep the environment record; it makes a surprising mismatch investigable.
