---
name: pure-dask-mode
description: Implement pure Dask mode via persistent command and remote defaults
---

# Plan

Implement pure Dask mode via the command language by adding a `persistent` flag and defaulting execution to remote when a cluster is selected. The pure-Dask path launches only a Dask server, avoids Seamless imports, and keeps the existing Seamless Dask behavior unchanged when persistence is enabled.

## Requirements
- Add a `persistent` command; default is false, but becomes true by default when a cluster is selected (explicit command overrides).
- Default `execution` to `remote` when a cluster is selected; keep `process` otherwise.
- Pure Dask mode triggers when `execution: remote` + cluster has a daskserver (or `remote: daskserver` if both) + `persistent: false`.
- Pure Dask launches only a Dask server; no hashserver/database, no SeamlessDaskClient, no Seamless base classes.
- Pure Dask tool key template uses the queue name (no project/stage in key).
- Dask wrapper supports configurable worker threads and processes; existing Seamless defaults unchanged when new params are unset.
- Pure Dask bypasses Seamless transformation behavior in the wrapper (no Seamless throttle, no worker thread override derived from transformation throttle).
- Tests: transformers forbidden in pure Dask mode; importing `seamless_config` does not auto-import `seamless_remote`, `seamless_transformer`, or `seamless`.

## Scope
- In:
  - Command language and selection defaults (`persistent`, execution default, remote selection).
  - Pure Dask server configuration/launch path.
  - Wrapper configurability for worker threads/processes.
  - Tests for pure Dask constraints and import hygiene.
- Out:
  - Changes to the existing Seamless Dask client semantics when persistence is enabled.

## Files and entry points
- `seamless-config/seamless_config/config_files.py`
- `seamless-config/seamless_config/select.py`
- `seamless-config/seamless_config/tools.py`
- `seamless-config/seamless_config/tools.yaml`
- `seamless-config/seamless_config/__init__.py`
- `seamless-remote/seamless_remote/daskserver_remote.py` (or new pure-dask module)
- `seamless-dask/seamless_dask/wrapper.py`
- `seamless-transformer/seamless_transformer/transformation_class.py`
- Duplicates under `seamless-dask/` and `seamless-jobserver/`

## Data model / API changes
- New command: `persistent` (boolean) in `COMMAND_LANGUAGE.md` and config parsing.
- New selection state: `get_persistent()` with source tracking; defaults derived from cluster presence.
- New tool entry: `pure_daskserver` (queue-based key template, no project/stage injection) and `configure_pure_daskserver(...)`.
- Pure Dask activation path that returns a plain `distributed.Client` and sets a guard flag to forbid transformers.
- New wrapper parameters (optional) for worker threads and processes, passed via `file_parameters`.

## Action items
[ ] Add `persistent` handling in config parsing and selection state (incl. reset logic and defaults).
[ ] Update execution default logic to `remote` when cluster is selected (explicit command overrides).
[ ] Add `pure_daskserver` tool config and `configure_pure_daskserver` with queue-based key template.
[ ] Implement pure-Dask launcher/client handle that uses `remote_http_launcher` + `distributed.Client` without Seamless imports.
[ ] Update `seamless_config.set_stage` to pick persistent vs. pure Dask activation paths without importing `seamless_remote` in pure mode.
[ ] Add wrapper overrides for worker threads/processes while preserving current defaults when unset.
[ ] Ensure pure Dask mode does not apply Seamless transformation throttling or `--nthreads` overrides unless explicitly configured.
[ ] Add transformer guard for pure Dask mode and surface a clear error.
[ ] Mirror changes in duplicated repos under `seamless-dask/` and `seamless-jobserver/`.
[ ] Add tests for transformer prohibition, import hygiene, and pure-Dask config generation.

## Testing and validation
- `pytest` in `seamless-config/tests`, `seamless-dask/tests`, and `seamless-transformer/tests` as relevant.
- New tests asserting `seamless_remote`, `seamless_transformer`, `seamless` not in `sys.modules` after `import seamless_config`.
- New tests asserting transformer usage fails when pure Dask mode is active.

## Risks and edge cases
- Defaulting to `remote` when a cluster is selected may change behavior for existing users; ensure explicit `execution` remains authoritative.
- `persistent` defaulting to true with cluster selection must not override explicit `persistent: false`.
- Queue-based key template must remain unique across clusters/queues.

## Open questions
- None.
