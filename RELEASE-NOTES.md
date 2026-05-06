# Seamless Release Notes

## version 1.3

### Service management: rhl-* helper redesign and seamless-service-* layer

The `remote-http-launcher` helper commands have been renamed and redesigned for
both human and agent use, and a new `seamless-service-*` CLI layer has been
added to `seamless-config` that translates Seamless-level arguments (cluster,
project, stage, service) into the appropriate `rhl-*` operations.

**New `rhl-*` helpers** (replaces the old `rhl-ls-services`, `rhl-kill-service`,
`rhl-rm-state`, `rhl-cat-log`, `rhl-cat-json`, `rhl-clear-buffer`,
`rhl-clear-db`, and `rhl-restart-cluster`):

- `rhl-ps` — list process state with live PID checks; `--client` for local
  connection state, `--json` for NDJSON (includes structured `meta` block)
- `rhl-ps-persistent` — report absent/empty/populated state of buffer
  directories and database directories; used for false-pass debugging
- `rhl-stop` — stop service processes via SIGINT → SIGTERM → SIGKILL
  escalation; preserves the JSON state for post-mortem inspection
- `rhl-rm` — remove JSON state files; log files are intentionally preserved
- `rhl-logs` — stream or tail the service log
- `rhl-inspect` — pretty-print the server state JSON
- `rhl-clear` — remove all direct children of a validated persistent directory

**New `seamless-service-*` commands** (from `seamless-config`):

- `seamless-service-ps` — unified view of process state and persistent data
  state, with per-row `(service, project, stage)` columns derived from the
  `meta` block; `--persistent` adds buffer/DB directory state
- `seamless-service-stop`, `seamless-service-rm` — stop and remove services by
  Seamless-level args or cluster-wide with `--cluster`
- `seamless-service-logs`, `seamless-service-inspect` — log and state access
  without knowing the raw key
- `seamless-service-clear` — clear hashserver or database persistent data by
  project/stage; errors cleanly for non-persistent service types
- `seamless-service-resolve` — agent-friendly resolver: translates
  service/cluster/project/stage into the raw key, ssh\_hostname, workdir, and
  log path that `rhl-*` expects; no side effects, JSON output

The launcher now writes a `meta` block into every state JSON, carrying
structured `(service, cluster, mode, project, subproject, stage, substage,
queue)` fields. Readers must treat `meta` as optional for backwards
compatibility with state files written by older versions.

See [docs/main/service-management.md](docs/main/service-management.md) for the
user guide and
[docs/agent/contracts/service-management.md](docs/agent/contracts/service-management.md)
for the agent contract including the `seamless-service-resolve` extractor
disclaimer.
