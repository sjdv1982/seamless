# Seamless Release Notes

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
