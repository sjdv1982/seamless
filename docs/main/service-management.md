# Service management

Seamless services (hashserver, database, jobserver, daskserver) are launched and
supervised by `remote-http-launcher`, a separate package that manages process
lifecycle, SSH tunnels, and state files. This guide covers how to inspect, stop,
restart, and clear services during normal development and debugging.

## Two-layer design

Service management is split across two layers:

- **`rhl-*` helpers** (from `remote-http-launcher`): operate on raw _keys_ —
  opaque identifiers that `remote-http-launcher` uses for its JSON state files.
  They run on whichever machine holds the state (server-side for `rhl-stop`,
  `rhl-logs`, etc.; client or server for `rhl-rm`). They have no knowledge of
  Seamless clusters, projects, or stages.

- **`seamless-service-*` wrappers** (from `seamless-config`): accept
  Seamless-level arguments (`--service`, `--cluster`, `--project`, `--stage`)
  and translate them to `rhl-*` calls. They run client-side and dispatch to the
  right host over SSH.

As a Seamless user, you typically use only the `seamless-service-*` layer. The
`rhl-*` helpers are available for lower-level access when you already know the
key (e.g., from `seamless-service-resolve`).

---

## Viewing service state: seamless-service-ps

```bash
# List client-side connection state (fast, no SSH):
seamless-service-ps

# List server-side process state for a cluster:
seamless-service-ps --server --cluster MYCLUSTER

# Include persistent data state (buffer dirs, seamless.db):
seamless-service-ps --server --persistent --cluster MYCLUSTER

# Filter by project or status:
seamless-service-ps --server --project myproject --status stale
```

Example output with `--persistent`:

```
SERVICE      PROJECT      STAGE       PROCESS    PORT     PERSISTENT  SIZE
hashserver   myproject    -           running    10501    populated   42 MB
hashserver   myproject    fingertip   stale      -        populated   17 MB
database     myproject    -           running    10502    populated   3 MB
jobserver    myproject    fingertip   failed     -        n/a         -
```

Process states: `running` | `starting` | `failed` | `stale` | `absent`

Persistent states: `populated` | `empty` | `absent` | `n/a` (non-persistent
services such as jobserver and daskserver use `/tmp` and have no durable data)

---

## Stopping and restarting services

```bash
# Stop a specific service (reads defaults from seamless.yaml + seamless.profile.yaml):
seamless-service-stop --service hashserver

# Stop with explicit args:
seamless-service-stop --service hashserver --cluster MYCLUSTER --project myproject

# Stop all services for a cluster:
seamless-service-stop --cluster MYCLUSTER
```

`seamless-service-stop` sends SIGINT → SIGTERM → SIGKILL with short polling
intervals between escalations. It does **not** remove state JSON files — the
`stale` state is preserved so you can inspect logs afterwards.

To remove JSON state after stopping:

```bash
seamless-service-rm --service hashserver
seamless-service-rm --cluster MYCLUSTER     # cluster-wide
```

To restart: stop, remove, then re-run your script or `seamless.config.init()`.
`remote-http-launcher` will start the service fresh.

---

## Reading logs

```bash
# Stream full log (from project directory — reads seamless.yaml for defaults):
seamless-service-logs --service hashserver

# Last 50 lines only:
seamless-service-logs --service hashserver --tail 50
```

Note: for non-persistent services (jobserver, daskserver, pure-daskserver), read
the log **before** removing state with `seamless-service-rm`. The log file
survives JSON removal but becomes unreachable through the helper once the JSON
is gone.

---

## Inspecting service state JSON

```bash
seamless-service-inspect --service hashserver
```

Prints the full server-side state JSON: PID, port, status, workdir, command,
and the `meta` block containing service/cluster/project/stage identifiers.

---

## Clearing cached data

Seamless caches transformation results in two places:

- **Buffer directory** (hashserver): stores actual data bytes, indexed by checksum
- **Database** (database): stores transformation → result checksum mappings in `seamless.db`

Both must be cleared for a true cold-cache re-execution:

```bash
# From the project directory:
seamless-service-clear --service hashserver
seamless-service-clear --service database

# With explicit args:
seamless-service-clear --service hashserver --cluster MYCLUSTER --project myproject --stage fingertip
seamless-service-clear --service database  --cluster MYCLUSTER --project myproject --stage fingertip
```

`seamless-service-clear` errors cleanly for non-persistent services (jobserver,
daskserver, pure-daskserver), which use `/tmp` and have no data directory to
clear.

---

## Debugging false-pass test results

**A test can pass even when the underlying code is broken**, because Seamless
returns a cached result from a prior successful run. This is the most common
source of incorrect "fixes" — the test passes, the developer commits, and the
problem resurfaces later.

Signs of a false pass:
- Test passes immediately after a service restart
- Test passes after changes that should have affected results
- `seamless-service-ps --persistent` shows `populated` after all processes stopped

Protocol for ruling out a false pass:

```bash
# 1. Check what persistent data is present:
seamless-service-ps --server --persistent --project myproject --cluster MYCLUSTER

# 2. Stop and clean services:
seamless-service-stop --cluster MYCLUSTER
seamless-service-rm --cluster MYCLUSTER

# 3. Clear cached data:
seamless-service-clear --service hashserver --project myproject
seamless-service-clear --service database  --project myproject

# 4. Restart services and re-run the test on a cold cache.
```

Only a pass on a cold cache is meaningful.

---

## Service lifecycle reference

| State | Meaning | What to do |
|-------|---------|------------|
| `absent` | No JSON or data exists | — |
| `starting` | Process launched, waiting for port | Wait; if it hangs, read log |
| `running` | Service healthy, port known | — |
| `failed` | Startup failed or timed out | Read log, fix, restart |
| `stale` | JSON exists but process is dead | Read log, then `seamless-service-rm` |
| `persistent` | Data directory populated, no process | Inspect with `--persistent`; clear if needed |

For the full `rhl-*` helper reference and the JSON state file schema, see the
[remote-http-launcher README](https://github.com/sjdv1982/remote-http-launcher).
