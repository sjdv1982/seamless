# Execution Records (Contract)

This page defines the agent-facing behavior of execution records: structured metadata that `seamless-database` stores for every successful, non-probe transformation.

## What execution records are

An execution record is a JSON body stored in the `MetaData` table of `seamless.db`, keyed by `tf_checksum`. It captures **what ran, where, and how it performed** — not the result itself, which lives in the normal `Transformation` cache. Records are *write-once per `tf_checksum`*: once a successful execution writes a row, subsequent calls hit the normal cache and never re-enter the record path.

Records exist for three concrete reasons:

1. **Cache lifecycle decisions.** Resource cost (CPU time, memory peak) feeds eviction policy.
2. **Fingertipping diagnosis.** When fingertipping fails or a result migrates to `IrreproducibleTransformation`, the record is the breadcrumb back to the original execution context.
3. **Trust under sharing.** When `seamless.db` is shared, the record lets a recipient inspect *in what context was this result produced* without trusting the publisher unconditionally.

Records are **not consulted for cache hits** in normal operation. They are evidence preserved across the moment of execution.

## Mental model: evidence, not identity

Seamless is a **referential-transparency system, not a database-integrity system**. The cache contract is "same `tf_checksum` ⇒ same result"; the cache key is the `tf_checksum`, and the determinant of identity for a transformation is its declared inputs and code, not its execution context.

Execution records are **evidence about the envelope**, not part of the identity. They exist to make the optimistic null hypothesis (that scientifically meaningful results are invariant under environment variation) falsifiable later. Concretely:

- A metadata conflict is **not** automatically a cache-identity conflict. If two parties have the same `tf_checksum` and same `result_checksum` but different metadata bodies, that is **evidence disagreement about the execution envelope** — informative for audit, but it does not invalidate the cached result.
- A `result_checksum` mismatch for the same `tf_checksum`, on the other hand, *is* a referential-transparency violation. That is what `IrreproducibleTransformation` is for; metadata travels with the result on migration.
- During fingertipping, the goal is to *rematerialize* a checksum, not to author a new canonical execution record. Fingertip retries do not displace the original record.

Treat records as a forensic substrate for human or agent investigators when something has gone wrong; do not treat them as a query target or a synchronization point in the normal cache path.

## When records are written

| Trigger | Record? | Mode |
|---------|---------|------|
| Successful, non-probe execution | Yes (always) | `record: false` → minimal; `record: true` → full |
| Probe execution | No | — |
| Failed execution | No | — |
| Canceled execution | No | — |
| Cache hit on `Transformation` | No | — |
| Already-recorded `tf_checksum` | No (idempotent) | identical body → success; differing body → reject |

The `record` boolean is a `seamless-config` command (`- record: true` in `seamless.profile.yaml`, or `seamless.config.select_record(True)`). It defaults to `false`, meaning the **minimal** record is persisted by default. The `record: true` opt-in adds the full payload.

A successful execution writes **exactly one record** — never minimal first then full. The runtime honors the active `record` mode at the moment the call completes.

Capture is **worker-side**: the record describes the environment in which the transformation actually ran (jobserver worker, Dask worker, spawn child, or local process), not where it was submitted. This is enforced across all backends — `process`, `spawn`, `remote: jobserver`, `remote: daskserver`.

## Minimal record body (default)

The minimal record contains exactly:

```json
{
  "schema_version": 1,
  "tf_checksum": "<hex>",
  "result_checksum": "<hex>",
  "seamless_version": "<string>",
  "execution_mode": "process | spawn | remote",
  "remote_target": null | "jobserver" | "daskserver",
  "wall_time_seconds": <float>,
  "cpu_time_user_seconds": <float>,
  "cpu_time_system_seconds": <float>,
  "memory_peak_bytes": <int|null>,
  "gpu_memory_peak_bytes": <int|null>
}
```

No environment fingerprint, no compilation context, no validation snapshot, no per-job freshness. The hot path pays only timing/memory capture and one database write.

## Full record body (`record: true`)

The full record extends the minimal body with:

- **Environment signature** (content-addressed checksums to sub-buffers):
  - `node` — stable physical properties (CPU, RAM, GPU, OS, kernel, container)
  - `environment` — Python packages + conda env dump + numerics runtime config (BLAS, thread pools, relevant env vars)
  - `node_env` — per-node environment binding
  - `queue` / `queue_node` — scheduler/queue context
- **Compilation context** (`compilation_context`) — checksum to a buffer recording compiler versions, flags, headers, and linked objects. Only for compiled transformers; cached by compiled-module digest.
- **Validation snapshot** (`validation_snapshot`) — checksum to a buffer recording pre-execution validation state.
- **Execution summary/envelope** — load-bearing execution summary such as language kind, plus requested cluster/queue/node, scratch/fingertip flags, resolved `__env__` checksum, and active orthogonal dunder-key set.
- **Freshness** — required bucket labels/checksums, live tokens, bucket tokens.
- **Contract violations** — `bucket_contract_violations`, `job_contract_violations`, `contract_violations` (e.g., `native_link_outside_conda_prefix` for compiled transformers linking outside the conda prefix).
- **Per-run diagnostics** — `started_at`, `finished_at`, `hostname`, `pid`, `process_started_at`, `process_create_time_epoch`, `worker_execution_index`, `compilation_time_seconds`, retry counts.

The `checksum_fields` list at the top of the record names which fields hold checksum pointers to content-addressed sub-buffers (currently `node`, `environment`, `node_env`, `queue`, `queue_node`, `compilation_context`, `validation_snapshot`).

## Database protocol

- **Protocol version: 2.1**
- **`PUT metadata`** (request type): atomically creates `Transformation`, `RevTransformation`, and `MetaData` when missing. Validates identity (`tf_checksum` matches request, `result_checksum` matches request, `schema_version` integer, `checksum_fields` format if present). Identical duplicate is idempotent success; differing duplicate or result mismatch is rejected.
- **`GET metadata`**: returns the canonical record body for a `tf_checksum`.
- **`GET irreproducible`**: returns all rows for a `tf_checksum` (optionally filtered by `result`), each carrying `checksum`, `result`, and `metadata`.
- **`PUT irreproducible`**: moves a normal entry into `IrreproducibleTransformation`, preserving the metadata body unchanged.
- Once `IrreproducibleTransformation` rows exist for a `tf_checksum`, `PUT metadata` for that checksum is **rejected** to avoid silently migrating it back.

Schema upgrade: a fresh database creates the upgraded `meta_data` table directly. An empty legacy two-column table is dropped and recreated. A non-empty legacy table fails loudly (it must be migrated explicitly).

## Remote client API

`seamless-remote/seamless_remote/database_client.py` and `database_remote.py` expose:

- `set_execution_record(tf_checksum, result_checksum, record)` — write a record.
- `get_execution_record(tf_checksum)` — read a record.
- `get_irreproducible_records(tf_checksum, result_checksum=None)` — read irreproducible rows.

Worker-side payloads carrying the record back from jobserver/daskserver are **structured** (typed dicts); the remote client tolerates legacy string responses for backwards compatibility but new code should expect structured payloads.

## What records do not do

- They are **not a query target**. Records are not indexed for reverse lookups (`find all rows with environment = X`); the database stores them as JSON blobs. Audit tooling consumes whole records, not selective columns.
- They are **not a sharing redaction layer**. Hostnames and timestamps stay in the record body; whether to redact on export is a per-share operator decision, not a schema column.
- They are **not produced for failed or canceled executions**. Failed or canceled jobs do not create durable reusable identities; a canceled submission also writes no `result_checksum`, even if its dropped work later completes. They may be tracked elsewhere but not in `MetaData`.
- They are **not the sole source of "how to run"**. The orthogonal execution-only dunder values (`__env__`, `__compilation__`, `__meta__`, `__record_probe__`, …) needed to rerun or audit a transformation are stored by the transformation/replay substrate, not solely in the record. (Load-bearing keys such as `__schema__` live in the checksum-defining payload itself; `__header__` is derived from `__schema__`.)

## Agent guidance

- **Default to minimal records.** Do not enable `record: true` unless the user is explicitly debugging reproducibility, auditing, or measuring environment drift. The full record adds significant per-execution overhead.
- **Records describe the worker environment.** When a record's `hostname` differs from the submitter's host, that is correct, not a bug.
- **Records are write-once per `tf_checksum`.** Re-running a transformation that already has a record is a cache hit; the record is not refreshed. To force a fresh record, the underlying inputs must change (different `tf_checksum`).
- **Don't conflate metadata conflicts with cache-identity conflicts.** A metadata difference for the same `(tf_checksum, result_checksum)` pair is evidence disagreement about the envelope — interesting for audit, but not a referential-transparency violation. Only a differing `result_checksum` for the same `tf_checksum` indicates a real reproducibility problem (and that path goes through `IrreproducibleTransformation`, not metadata rejection).
- **Fingertipping retries do not author new records.** Fingertipping rematerializes a checksum; it does not displace the original record or trigger a new write.
- **For compiled transformers**, the full record's `compilation_context` is cached by compiled-module digest — repeated builds of the same source produce the same context checksum without re-invoking compiler-version subprocesses.
- **Strict-mode failures**: under `record: true`, record-write failures propagate. Under `record: false`, minimal-record write failures are best-effort for narrow transport/storage errors and emit a warning; programmer errors and `RecordBucketError` always propagate.
