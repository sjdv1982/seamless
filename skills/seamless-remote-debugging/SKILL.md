---
name: seamless-remote-debugging
description: Guides AI agents through debugging failures in Seamless remote execution (hashserver, database, jobserver, daskserver). Covers the multi-service topology, error propagation across repos, finding server-side logs and PID files, restarting services cleanly, and clearing caches to prevent false passes. Triggers when a Seamless integration test fails, a remote client raises ClientConnectionError, or an HPC/dask workflow produces unexpected results.
license: MIT
---

# Seamless Remote Debugging Guide

## The Cardinal Rule

**When a remote operation fails, always consider the possibility that the bug is on the server side, not the client side.**

Seamless remote clients talk to separate server processes (hashserver, database, jobserver, daskserver) that may run on different machines, in different repos, with their own dependencies. A `ClientConnectionError` in `buffer_client.py` might mean the hashserver crashed due to a Starlette API change — a completely different codebase. If you only look at the client code, you might "fix" the problem at the wrong level of the stack (e.g., adding error handling in the client when the server needs patching).

When you see a remote failure related to connection or resource retrieval, **dig up the server-side logs** before attempting any fix. The logs will tell you whether the error originates on the server, which changes the diagnosis entirely.

## Two-layer service management: `seamless-service-*` and `rhl-*`

Service inspection and management is split across two layers. **Prefer the `seamless-service-*` layer** — it understands cluster/project/stage and dispatches to the right host. Drop down to `rhl-*` only when you already know the raw key (e.g., from `seamless-service-resolve`) or you are operating on the server directly.

### `seamless-service-*` (from `seamless-config`)

Run client-side, from a project directory (reads `seamless.yaml` + `seamless.profile.yaml`) or with explicit flags:

| Command | Purpose |
|---------|---------|
| `seamless-service-ps [--server] [--persistent] [--cluster C] [--project P] [--stage S]` | Process state and (optionally) persistent buffer/DB state |
| `seamless-service-logs --service hashserver [--tail N]` | Read service log (no key needed) |
| `seamless-service-inspect --service hashserver` | Print the server state JSON |
| `seamless-service-stop [--service S \| --cluster C]` | SIGINT → SIGTERM → SIGKILL escalation; preserves JSON for post-mortem |
| `seamless-service-rm [--service S \| --cluster C]` | Remove JSON state; logs survive |
| `seamless-service-clear --service hashserver --project P [--stage S]` | Wipe persistent buffer or database data |
| `seamless-service-resolve --service hashserver --cluster C --project P [--stage S]` | Translate Seamless-level args → raw `key`, `ssh_hostname`, `workdir`, `log_path` (JSON, no side effects) |

`seamless-service-resolve` is the agent's bridge between Seamless semantics and the raw `rhl-*` layer. It is an **extractor**, not a synthesizer: it reports what the currently-installed runtime would compute, using the same code path as `seamless-run`. **Never construct keys by hand** — formats may change between Seamless versions.

### `rhl-*` helpers (from `remote-http-launcher`)

Operate on raw keys. Run server-side over SSH (or locally for `--client` operations):

| Command | Purpose |
|---------|---------|
| `rhl-ps [--client] [--json]` | List process state; `--json` emits NDJSON with a `meta` block |
| `rhl-ps-persistent <path> [--marker NAME] [--json]` | Report absent / empty / populated state of buffer/DB directories |
| `rhl-logs <key> [--tail N]` | Read service log |
| `rhl-inspect <key>` | Pretty-print the server state JSON (PID, port, status, workdir, command) |
| `rhl-stop <key>` | SIGINT → SIGTERM → SIGKILL; preserves JSON state |
| `rhl-rm <key> [--client] [--server]` | Remove JSON state files; logs are preserved |
| `rhl-clear <path>` | Remove direct children of a validated persistent directory |
| `rhl-pid-alive PID`, `rhl-verify-port HOST PORT`, `rhl-handshake URL` | Liveness checks |
| `rhl-cache-conda` | Prime conda discovery cache (run once after guard installation) |

### SSH Guard

When configured in `authorized_keys`, `rhl-guard` restricts the service account to the `rhl-*` helpers above. Naked shell commands (`pkill`, `rm`, `kill`, `bash -lc`, `python3 -c`) are rejected.

```
# Recommended: explicit allowlist of paths the guard will let helpers touch
command="rhl-guard --data-roots /home/svc/.config/rhl/data-roots" ssh-rsa AAAA... user@host

# Alternative: marker-based policy for Seamless deployments (no allowlist file)
command="rhl-guard --clear-policy seamless" ssh-rsa AAAA... user@host
```

The path policy applies to the three helpers that accept client-chosen paths: `rhl-clear`, `rhl-ps-persistent`, and `rhl-launch-service --workdir`. With `--clear-policy seamless`, the guard accepts only directories containing a `seamless.db` or `.HASHSERVER_PREFIX` marker. With `--data-roots <file>`, paths must (after `~`-expansion and symlink resolution) live under one of the listed roots. If no policy is declared, those three helpers refuse to dispatch.

Always-on heuristics apply in every mode: paths must be absolute, must not equal or be ancestors of `$HOME`, must not contain dotfile segments, and must not resolve to system roots (`/`, `/etc`, `/usr`, …).

After installing the guard, prime the conda cache once per remote host:
```bash
ssh <ssh_hostname> rhl-cache-conda
```
Re-run if the conda installation changes. No-op on servers without a guard.

### Server-side install of `rhl-*` (deployment gotcha)

`seamless-service-*` has **no inline fallback** — every operation dispatches via `rhl-*` over SSH. If `ssh <host> rhl-ps` exits with `command not found`, the failure is a deployment problem, not a Seamless bug:

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `bash: rhl-ps: command not found` over SSH, but `rhl-ps` works in an interactive shell on the same host | conda base env install + early non-interactive guard in `~/.bashrc` | Comment out or move the `case $- in *i*) ;; *) return;; esac` block so the conda activation hook runs for non-login shells. Or switch to `rhl-guard` (no `.bashrc` edit needed). |
| `command not found` even in an interactive shell | `remote-http-launcher` not installed at all | `pip install remote-http-launcher` into the system Python (root) **or** the conda base env on the host |
| Works manually but `seamless-service-*` says the host is unreachable | client-side host/SSH config mismatch | Check `frontends[].ssh_hostname` (vs `hostname`) in the cluster YAML |

`remote-http-launcher` carries its own inline-heredoc fallback for conda discovery, but **only for the launcher's bootstrap** — it does not extend to `seamless-service-*`, `rhl-ps`, `rhl-logs`, or any other consumer of the helpers. Verify reachability up front:

```bash
ssh <ssh_hostname> rhl-ps        # should list services or print an empty table, not "command not found"
```

If this fails, do not start patching client code — fix the server-side install first.

## The Service Topology

A single Seamless test can exercise code across multiple repos and multiple processes on multiple machines. Understanding this topology is the first step in any debugging session.

```
Test code (local)
  |
  v
seamless-config          Reads seamless.yaml + seamless.profile.yaml + cluster YAML.
  |                      Selects cluster, queue, execution mode.
  |                      Calls configure_hashserver/database/daskserver/jobserver.
  v
remote-http-launcher     SSHes to frontend (or runs locally). Activates conda env.
  |                      Launches server process. Writes PID/status JSON + log file.
  |                      Establishes SSH tunnel if configured. Performs healthcheck.
  v
+----------------------------------------------------------+
| Services (on frontend or local machine)                  |
|                                                          |
| hashserver         Buffer read/write (FastAPI/Starlette) |
| seamless-database  Transformation result cache           |
| seamless-dask-wrapper  Dask scheduler + SLURM/OAR jobs   |
| seamless-jobserver     Simple job dispatch + workers      |
+----------------------------------------------------------+
  |
  v (daskserver only)
SLURM/OAR worker nodes
  Each worker is also a client of hashserver + database
```

### Which repo owns which service

| Service | Repo/package | Framework | Key dependencies |
|---------|-------------|-----------|------------------|
| hashserver | `hashserver` | FastAPI/Starlette/uvicorn | `starlette.responses.FileResponse` |
| seamless-database | `seamless-database` | FastAPI | - |
| seamless-jobserver | `seamless-transformer` | FastAPI | `seamless-transformer` |
| seamless-dask-wrapper | `seamless-dask` | Dask distributed | `dask`, `dask-jobqueue` |
| Client library | `seamless-remote` | aiohttp | - |
| Configuration | `seamless-config` | - | PyYAML |
| Process launcher | `remote-http-launcher` | subprocess/SSH | - |

**Critical implication**: a `ClientConnectionError` raised in `seamless-remote/buffer_client.py` does *not* mean the bug is in `buffer_client.py` or `seamless-remote`. It means the hashserver (a different repo, running as a separate process, possibly on a different machine) returned an error or refused the connection. **Follow the error to its source.**

## Error Propagation Path

Errors lose context at each boundary. Understanding the propagation path tells you where to look:

```
Root cause (e.g., Starlette API removal in hashserver)
  -> Server process crashes or returns HTTP 4xx/5xx
    -> aiohttp receives error response or connection refused
      -> buffer_client.py raises ClientConnectionError
        -> _retry_operation retries 5 times, all fail
          -> Test sees ClientConnectionError after retries exhausted
```

### What each layer tells you

| Symptom | What it means | Where to look |
|---------|---------------|---------------|
| `ClientConnectionError` with HTTP status | Server received the request but rejected it | Server logs |
| `ClientConnectionError` (connection refused) | Server process is not running | Server JSON (did it start?), server logs (did it crash?) |
| `asyncio.TimeoutError` | Server is alive but slow or hung | Server logs, check for deadlocks or resource exhaustion |
| `ClientPayloadError` | Response was truncated or malformed | Server logs, network issues |
| Retries exhausted (5 attempts) | This is not transient - it's a real bug | Don't treat as flaky |

### The retry decorator masks the distinction between transient and persistent failures

`_retry_operation` in `seamless-remote/client.py` retries up to 5 times on `ClientConnectionError`, `ClientPayloadError`, `asyncio.TimeoutError`, and `FileNotFoundError`. If a request fails through all retries, **it is almost certainly not a transient network blip** - it is a real bug in the server, a dependency incompatibility, or a configuration problem. Do not treat it as flaky.

## Finding Server-Side Logs

This is the most important debugging step. Client-side errors tell you *that* something failed; server logs tell you *why*.

### Discover the service first

From a project directory, the easiest path is the Seamless-aware layer:

```bash
seamless-service-ps                   # client connection state (fast, no SSH)
seamless-service-ps --server --cluster MYCLUSTER
seamless-service-logs --service hashserver --tail 100
seamless-service-inspect --service hashserver    # PID, port, status, workdir
```

If you need the raw key for some reason (e.g., to script `rhl-*` directly), use the resolver:

```bash
seamless-service-resolve --service hashserver --cluster MYCLUSTER --project myproject [--stage fingertip]
# → JSON: {key, ssh_hostname, workdir, log_path, service, cluster, mode, project, ...}
```

**Do not construct keys by hand.** Key formats may change between Seamless versions; always go through `seamless-service-resolve`.

### File locations

All managed by `remote-http-launcher`:

**Server-side files** (on the machine running the service — the frontend for remote clusters, local for local clusters):
```
~/.remote-http-launcher/server/{key}.json    # PID, status, port, workdir, meta
~/.remote-http-launcher/server/{key}.log     # stdout+stderr of the server process
```

**Client-side files** (on your local machine):
```
~/.remote-http-launcher/client/{key}.json    # hostname, port (connection info)
```

The server JSON now carries a `meta` block populated by `seamless-config` with `(service, cluster, mode, project, subproject, stage, substage, queue)`. Older state files predate this and may have no `meta`; readers must treat it as optional.

### How to read server logs

**Preferred (Seamless-aware, dispatches to the right host automatically):**
```bash
seamless-service-logs --service hashserver
seamless-service-logs --service hashserver --tail 50
seamless-service-inspect --service hashserver
```

**Raw `rhl-*` (if you already have the key, e.g., from `seamless-service-resolve`):**
```bash
ssh <ssh_hostname> rhl-logs <key> --tail 100
ssh <ssh_hostname> rhl-inspect <key>
```

The `ssh_hostname` to use is in the cluster YAML (under `frontends[].ssh_hostname`, falling back to `frontends[].hostname` if not set). The cluster YAML is at `~/.seamless/clusters/{clustername}.yaml` or defined inline in `~/.seamless/clusters.yaml`.

**Read logs before removing state.** For non-persistent services (jobserver, daskserver, pure-daskserver), the log file is the only post-mortem artefact. It is reachable through the helper only while the server JSON exists; once you run `rhl-rm` / `seamless-service-rm`, the log file survives on disk but becomes unreachable by key.

### What to look for in server logs

- **Python tracebacks**: the server crashed. Read the traceback to find the root cause. Common: dependency API changes (e.g., Starlette removing a parameter), import errors from wrong conda env, missing files.
- **No log file at all**: the server never started. Check the JSON status file - if `status` is `starting` and never became `running`, the launch script itself failed. Check conda activation, SSH connectivity.

## Restarting Services

### The server JSON contains the PID and status

`seamless-service-inspect --service hashserver` (or `rhl-inspect <key>` if you have the key) prints:
```json
{
  "workdir": "<bufferdir>/<project>",
  "log": "<home>/.remote-http-launcher/server/<key>.log",
  "command": "hashserver --port-range <start> <end> ...",
  "uid": 1000,
  "pid": 12345,
  "status": "running",
  "port": 60757,
  "meta": {"service": "hashserver", "cluster": "MYCLUSTER", "project": "myproject", ...}
}
```

### Clean restart procedure

**Stop is a separate step from remove.** `rhl-stop` / `seamless-service-stop` sends SIGINT → SIGTERM → SIGKILL but **preserves the JSON state** so logs remain reachable for post-mortem. Run `rhl-rm` / `seamless-service-rm` afterwards to clean up.

**1. Stop the service**:
```bash
# Seamless-aware (dispatches to the right host):
seamless-service-stop --service hashserver
# or for everything on a cluster:
seamless-service-stop --cluster MYCLUSTER

# Raw (when you have the key):
ssh <ssh_hostname> rhl-stop <key>
```

**2. Read the log if you suspect a crash** — do this before step 3 (after `rhl-rm`, the log file remains on disk but is no longer reachable through `rhl-logs <key>`).

**3. Remove JSON state** (server and/or client):
```bash
seamless-service-rm --service hashserver
seamless-service-rm --cluster MYCLUSTER         # cluster-wide

# Raw equivalents:
ssh <ssh_hostname> rhl-rm --server <key>
rhl-rm --client <key>
```

**4. Kill any stale SSH tunnel** (locally):
If the cluster uses tunneling (`tunnel: true` in cluster YAML), an SSH tunnel forwards a local port to the remote service port. Find and kill stale ones to avoid port conflicts on reconnection:
```bash
ps aux | grep "ssh.*-L.*<remote_port>"
ps aux | grep "ssh.*-N.*<ssh_hostname>"
```

**5. Re-run the test** — `remote-http-launcher` will re-launch the service automatically.

There is no longer a single "restart cluster" command in the helper layer; cluster-wide actions live in `seamless-service-stop --cluster ...` and `seamless-service-rm --cluster ...`. The launcher repo intentionally keeps `rhl-*` per-key — cluster semantics belong on the Seamless side, not in `remote-http-launcher`.

## Clearing Cache to Prevent False Passes

**This is critical.** Seamless caches transformation results. A test can pass even when the underlying service is broken, because the result was cached from a previous successful run. The test never actually exercises the broken code path.

### When to clear cache

- After fixing a server-side bug, before declaring the fix works
- When a test unexpectedly passes after changes that shouldn't affect it
- When you need to verify that a computation actually runs end-to-end
- Whenever you suspect a false pass

### What to clear

There are two caches, both must be cleared for a true re-execution:

**1. Buffer directory** (stores actual data, identified by checksum):
- Location: `{bufferdir}/{project}/{stage}/` on the host running the hashserver
- The `bufferdir` is in the cluster YAML under `frontends[].hashserver.bufferdir`

**2. Database file** (stores transformation→result mappings):
- Location: `{database_dir}/{project}/{stage}/seamless.db` on the host running the database
- The `database_dir` is in the cluster YAML under `frontends[].database.database_dir`

### How to derive the paths

1. Read the cluster YAML (`~/.seamless/clusters/{clustername}.yaml` or `~/.seamless/clusters.yaml`)
2. Find `frontends[].hashserver.bufferdir` and `frontends[].database.database_dir`
3. Append the project name (from `seamless.yaml`) and stage (if any) as subdirectories
4. The database file is `seamless.db` inside the database workdir (see the `command_template` in `seamless-config/seamless_config/tools.yaml`)

### How to clear

**Preferred (Seamless-aware, no path derivation needed):**
```bash
# Stop the service first (clearing requires the directory not be in use by a writer):
seamless-service-stop --service hashserver --project myproject
seamless-service-stop --service database  --project myproject

seamless-service-clear --service hashserver --project myproject [--stage fingertip]
seamless-service-clear --service database  --project myproject [--stage fingertip]
```

`seamless-service-clear` errors cleanly for non-persistent services (jobserver, daskserver, pure-daskserver), which use `/tmp` and have no data directory to clear.

**Raw (when you have the path):**
```bash
ssh <ssh_hostname> rhl-clear <bufferdir>/<project>/STAGE-<stage>
ssh <ssh_hostname> rhl-clear <database_dir>/<project>/STAGE-<stage>
```

`rhl-clear` removes the direct children of the given directory (the directory itself is preserved). When dispatched through `rhl-guard`, the path must satisfy the configured path policy (`--data-roots` allowlist, `--clear-policy seamless` marker, etc.) — otherwise the guard refuses to dispatch.

To inspect persistent state without clearing:
```bash
seamless-service-ps --persistent --project myproject
# or raw:
ssh <ssh_hostname> rhl-ps-persistent <bufferdir>/<project> --json
```

**Always derive the actual paths from the cluster YAML for the specific cluster in use.** Do not hardcode paths — they differ per cluster, per project, and per stage. `seamless-service-clear` does this for you.

After clearing, restart the hashserver and database (see above), then re-run the test.

## Cross-Repo Debugging

When you've identified which service is failing (from logs or error messages), you need to find and fix the bug in the correct repo.

### Tracing to the right repo

1. **Read the server log** to get the actual error (traceback, HTTP error, etc.)
2. **Identify the failing code** - is it in the service itself, or in a dependency?
3. **Check the service's dependencies** - version mismatches with FastAPI, Starlette, Dask, etc. are a common source of breakage
4. **Check recent changes** - `git log` in the relevant repo. Use `git diff HEAD~1` to see what changed

### Common cross-repo failure patterns

| Error in server log | Likely cause | Where to fix |
|---------------------|-------------|--------------|
| `TypeError: __init__() got an unexpected keyword argument` | Dependency API change (e.g., Starlette removed a parameter) | The server repo (hashserver, seamless-database, etc.) |
| `ImportError: cannot import name ...` | Package version mismatch or missing install | conda environment on the frontend |
| `OSError: [Errno 98] Address already in use` | Previous instance still running | Kill the old process (see PID files above) |
| Dask worker errors | Wrong conda env on worker nodes, or worker can't reach hashserver/database | Check worker logs via Dask dashboard, check network connectivity |

### The dependency chain matters

The hashserver depends on Starlette/FastAPI. If Starlette removes an API parameter (as happened with `FileResponse.method`), the hashserver crashes - but the error shows up as a `ClientConnectionError` in the test. The fix is in the hashserver, not in the test or the client library.

**Always ask: "Is this a Seamless bug, or a dependency bug that Seamless surfaces?"**

### Local fix != live fix (remote clusters)

On remote clusters, services run inside a conda environment on the remote host. The running server process uses the *installed* version of its packages. Patching a source file in your local checkout of e.g. `seamless-transformer` does **not** fix the `seamless-jobserver` or Dask workers that are already running on the remote — they are using whatever was installed into their conda env.

After fixing the source:
1. **Re-install** the patched package into the conda environment on the remote host (see `conda` field in the cluster YAML's frontend or queue config)
2. **Restart the service** (kill PID, clean up state — see "Restarting Services" above) so it picks up the new code
3. **Clear the cache** if needed, to avoid false passes from previously cached results

### Local clusters: verify editable installs

For local clusters, this is normally not a problem — provided that the same conda environment (with `pip install -e` editable installs of the Seamless packages) is used both client-side (where the test/script runs) and server-side (the `conda` field in the cluster YAML). When this is the case, source changes take effect immediately after restarting the service.

If a local fix doesn't seem to take effect, verify:
1. That the conda env you are running in matches the one configured in the cluster YAML for the service
2. That the relevant package is installed as editable in that env:
```bash
conda activate <conda_env>
pip show <package> | grep "Editable project location"
```
If the editable location points to your source checkout, the fix is live after a service restart. If the envs don't match, or the install is not editable, the running service won't see your local changes.

## Environment Variables for Diagnostics

| Variable | Effect |
|----------|--------|
| `SEAMLESS_CLIENT_DEBUG=1` | Logs session lifecycle events (creation, close) in the client |
| `SEAMLESS_DEBUG_REMOTE_DB=1` | Debug logging for database remote operations |
| `SEAMLESS_REMOTE_CONNECT_TIMEOUT` | TCP connect timeout (default: 10s) |
| `SEAMLESS_REMOTE_READ_TIMEOUT` | Socket read timeout (default: 1200s) |
| `SEAMLESS_REMOTE_TOTAL_TIMEOUT` | Overall request timeout (default: unlimited) |
| `SEAMLESS_REMOTE_HEALTHCHECK_TIMEOUT` | Healthcheck timeout (default: 10s) |
| `SEAMLESS_DATABASE_MAX_INFLIGHT` | Max concurrent database requests (default: 30) |
| `REMOTE_HTTP_LAUNCHER_DIR` | Override `~/.remote-http-launcher` base directory |

## Debugging Checklist

When a Seamless integration/remote test fails:

1. **Read the full traceback.** Identify which client method failed and what exception was raised.
2. **Identify the service.** `buffer_client.py` → hashserver. `database_client.py` → seamless-database. `jobserver_client.py` → seamless-jobserver. Dask errors → seamless-dask-wrapper or worker nodes.
3. **Read the server log.** Use `seamless-service-logs --service <name>` (or `seamless-service-inspect` for status). For raw access, `seamless-service-resolve` → `ssh <ssh_hostname> rhl-logs <key>`.
4. **Find the root cause.** Is it a code bug? A dependency incompatibility? A stale process? A network issue?
5. **Fix in the right repo.** Don't patch the test or the client. Fix the server, the dependency, or the configuration.
6. **Clear the cache.** `seamless-service-clear --service hashserver --project ...` and `--service database --project ...` so you test actual re-execution, not cached results.
7. **Restart the service.** `seamless-service-stop` → (read log) → `seamless-service-rm` → re-run.
8. **Verify the fix.** The test must pass on a cold cache. A pass on a warm cache proves nothing — see "Clearing Cache to Prevent False Passes".

## Reference Map (load only as needed)

- `references/key-derivation.md`: how tool keys are constructed from cluster/project/stage, with concrete examples.
- `references/launcher-lifecycle.md`: the full remote-http-launcher lifecycle (launch, monitor, handshake, tunnel, teardown).
