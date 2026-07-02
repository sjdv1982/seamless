# Seamless Release Notes

## version 1.4

- A `Transformation` is now explicitly an **immutable computation definition
plus a mutable execution promise**, with a public **checksum-addressed
cancellation** API. For Python and bash transformations, the identity contract is
unchanged; v1.4 fixes the checksum implementation to honor the
load-bearing/orthogonal split. Compiled-transformer `__schema__` is now part of
identity. Some pre-1.4 cache entries will be re-keyed and recomputed (see below).

- seamless-core ships an
independent fix for checksumming compressed files.

### Transformation immutability and dunder separation

A `Transformation` now freezes its definition at construction: the
checksum-defining payload, the orthogonal dunder envelope, scratch policy, result
celltype, and the dependency graph edges are all copy-owned and read-only.
Execution state (transformation/result checksums, futures, status, exception)
stays mutable.

### Checksum-addressed cancellation

An active submission can now be moved to an observable terminal `canceled` state
across all backends (local asyncio, thread/executor, Dask, spawn/delegation,
jobserver). Use `seamless-cancel <tf_checksum>` or `Ctrl-C` / SIGTERM during a
`seamless-run*` command; in Python, `Transformation.cancel(recursive=False)` /
`await cancel_async(...)`. Afterwards `status` is `"Status: canceled"`,
`result_checksum` raises, the state is terminal (`clear_exception()` will not
revive it), and **no execution record or result checksum is written**.
Cancellation of already-running native code is best-effort — only the Seamless
promise is guaranteed inactive.

### Latch-on vs. strict re-submission

When the same `tf_checksum` is re-submitted with a *different* orthogonal dunder
envelope while the first is still running, the default is now **latch-on**: the
second submission attaches to the running one and returns its result, with the
active envelope authoritative. Pass `--strict` (`seamless-run-transformation`) or
`strict_dunder=True` (Python / Dask / jobserver) to require your own envelope
instead — it is rejected while another submission is active and may proceed only
once that one is done, failed, or canceled. CLI flags like `--direct-print`,
`--fingertip`, and `--scratch` affect the envelope only, never the checksum.

### seamless-core: transparent checksumming of compressed files

`seamless-checksum`, `seamless-checksum-file`, and `seamless-checksum-index` now
treat `.zst` and `.gz` files transparently — they decompress before checksumming,
so a buffer and its compressed form yield the **same** checksum, and the
compression suffix is stripped from written `.CHECKSUM`/index names. Fixes a bug
where compressed files were checksummed by their compressed bytes.

### Details: transformation checksum changes

The transformation cache key now follows the load-bearing/orthogonal dunder
split:

- `__meta__` and `__env__` are no longer part of transformation identity.
- `__schema__` is now part of identity for compiled transformers.
- `__compilation__`, compiler flags, headers, environment declarations, and
  metavars remain execution/provenance metadata.

There are no legacy aliases. Affected pre-1.4 cache entries will be recomputed;
results that must be preserved need external/manual migration. Most Python
`direct`/`delayed` transformer entries are affected because they carry `__meta__`
by default. Bash/manual transformations are affected only if their transformation
dict contains one of the changed fields.

The `__schema__` change supersedes the v1.3 compiled-transformer statement that
the schema was execution-only metadata. As of 1.4, compiled-transformer schema is
part of the cache key because it contributes to call-time marshalling and
pin-to-argument binding, not only to compilation.

Environment declarations remain outside identity. A fresh `Environment()`
contributes nothing, and the ambient conda/shell environment is not
auto-captured. `__env__` is written only for a non-empty explicit environment: a
conda spec, a conda env name, a Docker image, a required-binaries `which` list, or
`powers` (`tf.environment.set_*`, or CLI `--conda` / `--docker-image`).

If a result truly depends on the runtime environment, declare that dependency
explicitly as an input. With `__env__` outside the cache key, identical code and
inputs can share a `tf_checksum` across environments; an environment-dependent
result can therefore be reused unless the transformation is recomputed. Full
execution records (`record: true`, or `seamless.config.select_record(True)`) can
capture environment fingerprints for audit; default records do not.

## version 1.3

Three large changes since v1.2:

1. **Database execution records** — every successful transformation now leaves a structured record in `seamless.db`.
2. **SSH guard + redesigned `rhl-*` helpers** — `remote-http-launcher` ships an `authorized_keys` guard and a tighter helper surface; `seamless-config` adds a `seamless-service-*` layer on top.
3. **Compiled transformers** — `direct`/`delayed` for compiled source code (C, C++, Fortran, Rust) with an open language set.

### Database execution records

`seamless-database` now stores a canonical execution record in `MetaData` for every successful, non-probe transformation. Records are written **once per `tf_checksum`** and travel with the database when it is shared.

- **Default (minimal record)**: `schema_version`, `tf_checksum`, `result_checksum`, `seamless_version`, `execution_mode`, `remote_target`, `wall_time_seconds`, `cpu_time_user_seconds`, `cpu_time_system_seconds`, `memory_peak_bytes`, `gpu_memory_peak_bytes`. The hot path pays only timing/memory capture and one database write.
- **Full record (opt-in)**: add `- record: true` to `seamless.profile.yaml` (or call `seamless.config.select_record(True)`). Adds environment fingerprints (hardware, conda env, Python packages, runtime config), compilation context, validation snapshots, and per-job freshness/retry/worker fields.
- **Irreproducible cache**: when a transformation moves from the normal cache to `IrreproducibleTransformation`, its record body is preserved unchanged. The new `GET irreproducible` endpoint returns all rows for a `tf_checksum`.

Database protocol bumped to **2.1**. The schema upgrade is automatic for empty legacy `meta_data` tables; non-empty legacy tables fail loudly so they can be migrated explicitly.

New `seamless-remote` client APIs: `set_execution_record`, `get_execution_record`, `get_irreproducible_records`. The transformer, jobserver, and dask backends all populate records from the worker side, so capture reflects where the job actually ran — not where it was submitted.

See [docs/agent/contracts/execution-records.md](docs/agent/contracts/execution-records.md) for the agent contract.

### Service management: SSH guard + redesigned helpers

The `remote-http-launcher` helpers have been redesigned for both human and agent use, and `seamless-config` adds a Seamless-aware `seamless-service-*` wrapper layer.

**SSH guard (`rhl-guard`)**: an SSH `command="..."` entry point that restricts the service account to a fixed whitelist of `rhl-*` helpers. Naked shell commands (`pkill`, `rm`, `bash -lc`, `python3 -c`) are rejected. Three of the helpers (`rhl-clear`, `rhl-ps-persistent`, `rhl-launch-service --workdir`) accept client-chosen filesystem paths; their reachable paths are constrained by a path policy declared on the guard:

- `--data-roots <file>` — strict allowlist (recommended for production)
- `--clear-policy seamless` — accepts only directories with a `seamless.db` or `.HASHSERVER_PREFIX` marker
- `--clear-policy marker:NAME` — generic marker variant
- `--permissive-paths` — disables the policy (compatibility only)

If no policy is declared, the three path-accepting helpers refuse to dispatch. Always-on heuristics still apply in every mode (no system roots, no `~/.ssh`, no `$HOME` ancestors).

**New `rhl-*` helpers** (replaces `rhl-ls-services`, `rhl-kill-service`, `rhl-rm-state`, `rhl-cat-log`, `rhl-cat-json`, `rhl-clear-buffer`, `rhl-clear-db`, `rhl-restart-cluster`):

- `rhl-ps` — list process state with live PID checks; `--client` for connection state, `--json` for NDJSON (each row carries a structured `meta` block)
- `rhl-ps-persistent` — report absent/empty/populated state of buffer/database directories; used for false-pass debugging
- `rhl-stop` — SIGINT → SIGTERM → SIGKILL escalation; preserves the JSON state for post-mortem
- `rhl-rm` — remove JSON state files; log files are intentionally preserved
- `rhl-logs` — stream or tail the service log
- `rhl-inspect` — pretty-print the server state JSON
- `rhl-clear` — remove direct children of a validated persistent directory

**New `seamless-service-*` commands** (from `seamless-config`):

- `seamless-service-ps` — unified view of process and persistent data state, with per-row `(service, project, stage)` derived from the `meta` block; `--persistent` adds buffer/DB directory state
- `seamless-service-stop`, `seamless-service-rm` — stop and remove services by Seamless-level args or cluster-wide with `--cluster`
- `seamless-service-logs`, `seamless-service-inspect` — log and state access without knowing the raw key
- `seamless-service-clear` — clear hashserver or database persistent data by project/stage
- `seamless-service-resolve` — agent-friendly resolver: translates service/cluster/project/stage into the raw key, ssh\_hostname, workdir, and log path; no side effects, JSON output

The launcher now writes a `meta` block into every state JSON, carrying `(service, cluster, mode, project, subproject, stage, substage, queue)`. Readers must treat `meta` as optional — older state files do not have it.

See [docs/main/service-management.md](docs/main/service-management.md) for the user guide and [docs/agent/contracts/service-management.md](docs/agent/contracts/service-management.md) for the agent contract.

### Compiled transformers

`seamless-transformer` can now wrap compiled source code as Seamless transformations, in the same `direct`/`delayed` style as Python.

```python
from seamless_transformer import DirectCompiledTransformer

tf = DirectCompiledTransformer("c")
tf.schema = """
inputs:  [{name: a, dtype: int32}, {name: b, dtype: int32}]
outputs: [{name: result, dtype: int32}]
"""
tf.code = '#include "transformer.h"\nint transform(int a, int b, int *r){*r=a+b;return 0;}'
tf(3, 4)  # => 7
```

- **Built-in languages**: C, C++, Fortran, Rust. **The set is open** — any language that produces a C-ABI `transform()` symbol works. Register at runtime with `define_compiled_language()`, or add a ~15-line file in `seamless_transformer/languages/native/` for permanent support.
- **Schema → header**: `seamless-signature` (a new package) parses a YAML schema and generates a C header (`tf.header`). CFFI uses the header to build the `.so` extension. For Fortran/Rust/C++, derive the function declaration from the schema or generated header (paste it into an AI for cross-language translation).
- **Multi-language linking**: `tf.objects` accepts `CompiledObject` instances in any registered language; they are linked alongside the main source.
- **Identity**: source code and input values are part of the cache key. Compiler flags, schema, header, and environment are dunder-keys (execution-only metadata, **not** part of the checksum). Two runs with the same code and inputs but different `-O` flags are cache-equivalent.
- **Referential transparency is not policed**: the `.so` runs natively, with no sandbox. Persistent state that affects the return value (`static` accumulators, `SAVE` variables, cached models, database sessions) is forbidden — the runtime cannot detect violations and the consequence is silently incorrect caching.

Install with the optional dependency group:

```bash
pip install seamless-transformer[compiled]
```

See [docs/main/compiled-transformers.md](docs/main/compiled-transformers.md) for the user guide, [docs/agent/contracts/compiled-transformers.md](docs/agent/contracts/compiled-transformers.md) for the behavioral contract, and [docs/agent/contracts/seamless-signature-schema.md](docs/agent/contracts/seamless-signature-schema.md) for the schema reference.
