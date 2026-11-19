# Seamless Release Notes

## version 1.5 (pre-release)

Seamless 1.5 is the first 1.x release on feature parity with legacy Seamless
0.x. The reactive, interactive workflow layer is back, on the new
architecture. Transformers can now be written in R and Julia, and bash
transformers and the new command-line backends run inside real conda
environments and containers.

If you used 1.4, read *Breaking changes* below; most have a one-line fix.
[CHANGELOG.md](CHANGELOG.md) has the details.

The human documentation does not cover the workflow face yet. See the
README's *Documentation* section for where to start; the contract pages under
`docs/agent/contracts/` are authoritative. `pip install seamless-suite`
includes everything: there are no `[jupyter]` or `[share]` extras.

### Reactive workflows are back

`seamless.workflow.Context` holds a graph of cells and transformers and keeps it
up to date as values change, like a spreadsheet. Only what changed is
recomputed. The rest comes from the cache.

- **Cells and transformers.** Assign values, functions and connections to
  `ctx`. Transformers can be written in Python, bash, R, Julia or a compiled
  language. `ctx.compute()` waits for the graph to finish. Each node reports
  its `.state` and `.exception`.
- **File mounts.** `cell.mount("data.json")` keeps a cell and a file in
  sync, in either direction. Directories mount as `folder` cells.
- **Jupyter widgets.** `traitlet(cell).link(widget)` links a cell to an
  ipywidget; `output(cell)` displays it (both from `seamless_workflow.jupyter`).
- **Web interfaces.** `cell.share()` serves a cell over HTTP and WebSocket,
  read-only or writable. The server publishes a live OpenAPI description and a
  small browser client (`seamless-client.js`). It can also offer cells as a
  download archive and publish the state of the graph. `seamless-serve-graph`
  serves a saved graph without writing any Python.
- **Saving.** `ctx.get_graph()` and `ctx.set_graph()` save and load a workflow
  as JSON. The graph stores checksums, not data: to reload it in another
  process, use persistent storage (`seamless.config.init()` with a hashserver
  or database). Loading a graph can write files and open HTTP ports; load
  graphs of unknown origin with `set_graph(graph, mounts=False, shares=False)`.
  Build large graphs with one `set_graph()` call; adding nodes one by one
  re-derives the whole graph each time.

Not carried over from 0.x: macros, libraries and the standard library, Silk
validation (a cell with a validator fails with `NotImplementedError`),
sub-contexts with their own runtime, and debug sessions.

Shares have no authentication or TLS, and the server listens on all network
interfaces (`0.0.0.0:5813`) unless you call
`seamless_workflow.shareserver.configure(host="127.0.0.1")` or set
`SEAMLESS_SHARE_HOST`. The state of the graph, including error messages, is
visible to anyone who can reach the server. Serve only on trusted networks.

### Cells and Expressions in Python

`seamless.Cell` and `seamless.Expression` also work outside a Context. A
standalone Cell is evaluated when you read it. Selecting part of a value
(`cell["key"]`) or converting it (`cell.as_celltype("text")`) is an Expression,
identified and cached like a transformation.

Cells, Pins, Transformers and Transformation handles share one failure rule: a
read (`.value`, `.checksum`) or `.compute()` returns `None` and keeps the error
on `.exception`; `.run()` raises, and so does a call to a `direct` function. A
result that exists but cannot be fetched raises on every read.

### More languages, real environments

- **R and Julia** transformers, through `Transformer("r")` / `Transformer("julia")`
  in Python or in a Context. They run as separate `Rscript`/`julia` processes by
  default, or embedded in the Python process with `tf.metavars.BACKEND = "mem"`.
  Not available through `direct`/`delayed` or `seamless-run`.
- **Python in its own process** with `tf.metavars.BACKEND = "cli"`.
- **Conda environments and containers are now entered**, not just recorded.
  Bash transformers and the command-line backends run inside the requested
  conda environment or container image (Docker, Podman or Apptainer, whichever
  the executing host has), and check required binaries where the code runs.
  Use `tf.environment` or `seamless-run --conda` / `--docker`. A Python
  transformer on the default in-memory backend does not enter an environment:
  a conda name is checked against the running process, and a Docker image is
  refused. As before, the environment is not part of a transformation's
  identity, and a cached result is returned without checking it.

### Running and observing

- **Logs.** `Transformation.logs` (and `ctx.tf.logs`) returns the stdout and
  stderr of a run, with its execution time. Logs work on every backend. A
  result that came from the cache has no log, and logs are kept in memory only.
- **Streaming.** `--streaming` (replacing `--direct-print`) and
  `Transformer.streaming` show output while a transformation runs, including
  tqdm progress bars. Dask backend only.
- **Notebooks.** `direct` calls, `tf.run()` and `tf.compute()` work inside
  Jupyter and other running event loops.
- **One body per process.** By default a process runs one transformation body
  at a time. A body that submits nested work releases its slot. Mark a
  transformer as a `driver` (`seamless-run --driver`) when it mainly launches
  other work, or switch the lock off (`process_lock = False`,
  `--no-process-lock`). `global_lock` is gone. For parallel local execution,
  start worker processes (`spawn`, or a local cluster).
- **Cancellation.** `Transformation.cancel()` now cancels your interest in a
  run. The run itself continues as long as someone else is waiting for it.
  `seamless-cancel <checksum>` remains the hard kill. A Context only ever
  cancels softly; `ctx.prune()` releases superseded runs early.
- **Irreproducible results are recorded.** When recomputing a transformation
  gives a different result than the one in the database, the database records
  the observation and keeps the original result.
- **Selections and conversions run where the data is.** When the data lives
  on the cluster, they are evaluated on the jobserver or Dask cluster instead of
  being downloaded first.

### Breaking changes

- `seamless-run` passes directory arguments, and returns results with result
  targets, as `folder` instead of `deepfolder`. Such commands get a new
  checksum and are recomputed once. As a bonus, they now also run on hosts that
  cannot see the submitter's buffer directory.
- A 64-character hex string inside a `deepcell` result is now a string, not a
  checksum; in a `folder` result it raises `TypeError`. Wrap real checksums
  with `Checksum(s)`.
- Deep pins: outside bash, `deepcell` and `deepfolder` pins are dicts of
  checksum objects and a `folder` pin is a dict of contents. Bash refuses
  `deepcell` and `deepfolder` pins, and every file of a deepcell `RESULT` must
  parse as `mixed`.
- A `bytes` pin reaches Python code as `bytes`, not as a `seamless.Buffer`.
- `--direct-print` and `direct_print` are replaced by `--streaming` and
  `streaming`.
- `global_lock` is replaced by `process_lock` and `driver` (see above).
- Pins are set through `tf.pins.x`; the shortcuts `tf.x` and `tf["x"]` are gone.
- `CompiledTransformer` is gone: use `Transformer("c", compiled=True)`.
- Compiled transformers: a schema `char` is now C `unsigned char`; null inputs
  and optional pins are refused; scalar pins are checked by kind and range.
  Recheck existing kernels against the compiled-pins contract.
- `seamless-run` no longer reads `.SEAMLESS.yaml` / `.SEAMLESS.py` interface
  files: declare extra inputs with `-i`, `-I` or `--metafile`.
- Environments: `set_powers` is removed; a conda environment together with a
  Docker image, and unknown image keys, are refused when the job is dispatched.
- Null: a required pin accepts null only for the `plain`, `mixed` and `bytes`
  celltypes. A function may now return `None` for those three result
  celltypes (1.4 refused every `None` result).
- The conversion engine was rewritten. Some conversions of non-canonical data
  now give different checksums (for example, `text` to `plain` always writes
  canonical JSON).
- `BACKEND` accepts `"cli"` and `"mem"` only.
- The database protocol is now 2.3 (`seamless-database` 2.2.0): upgrade the
  database server together with the clients.

### Known issues

- The Julia command-line backend (the default for Julia) needs a source
  checkout of Seamless; it fails when installed from PyPI. Use
  `tf.metavars.BACKEND = "mem"` (requires `juliacall`) or a source install.
- `seamless-run --undo` fails with "Transformation could not be declared
  irreproducible".

## version 1.4

- A `Transformation` is now explicitly an **immutable computation definition
plus a mutable execution promise**, with a public **checksum-addressed
cancellation** API. This refactor also updates the transformation identity
contract. Affected pre-1.4 cache entries will be recomputed; most Python
`direct`/`delayed` transformer entries are affected (see below).

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
once that one is done, failed, or canceled. CLI flags like `--fingertip` and
`--scratch` affect the envelope only, never the checksum.

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
conda spec, a conda env name, a Docker image, or a required-binaries `which` list
(`tf.environment.set_*`, or CLI `--conda` / `--docker-image`).

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
from seamless_transformer import Transformer

tf = Transformer("c", compiled=True, direct=True)
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
