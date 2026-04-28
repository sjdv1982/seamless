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

## SSH Guard and Helper Commands

`remote-http-launcher` installs a set of helper commands (`rhl-*`) on the remote server. When the SSH guard is configured, **only these helpers and the specific command patterns sent by the launcher itself are permitted** — naked shell commands like `pkill`, `rm`, or `kill` are rejected.

### Guard installation

On the remote server, add to `~/.ssh/authorized_keys`:
```
command="rhl-guard" ssh-rsa AAAA... your-key-comment
```

`rhl-guard` reads `ssh_guard/tools.yaml` (bundled with `remote-http-launcher`) to determine which service binaries are allowed inside launcher scripts. Override with `RHL_TOOLS_YAML=/path/to/tools.yaml` if needed.

### First-time conda setup (guarded servers only)

Run once per remote server after installing the guard (conda discovery is cached so the launcher never sends raw probe commands):
```bash
ssh <ssh_hostname> rhl-cache-conda
```
Re-run if the conda environment changes. This is a no-op on servers without a guard.

### Quick reference: rhl-* helpers

| Command | What it does |
|---------|-------------|
| `rhl-cat-log <key>` | Print the service log |
| `rhl-cat-json <key>` | Pretty-print the service state JSON (PID, port, status) |
| `rhl-ls-services [--client]` | List service keys (server-side by default) |
| `rhl-kill-service <key>` | SIGHUP the service PID and remove its state JSON |
| `rhl-rm-state <key> [--client] [--server]` | Remove state JSON(s); default: both |
| `rhl-restart-cluster <cluster>` | Kill all services for a cluster and clean up |
| `rhl-clear-buffer <path>` | Remove files inside a buffer directory |
| `rhl-clear-db <path>` | Remove `seamless.db` from a database directory |
| `rhl-cache-conda` | Prime the conda discovery cache |

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

### File locations

All managed by `remote-http-launcher`. The key is derived from `tools.yaml` templates:

**Key pattern**: `{tool}-{cluster}-{mode}-{project-path}`

Examples for a cluster named `MYCLUSTER`, project `myproject`, no stage:
- `hashserver-MYCLUSTER-rw-myproject`
- `database-MYCLUSTER-rw-myproject`
- `daskserver-MYCLUSTER-rw-myproject`

With a stage (e.g., `fingertip`):
- `hashserver-MYCLUSTER-rw-myproject--STAGE-fingertip`

To determine the actual key for your situation:
1. Read `seamless.yaml` for the project name and stage
2. Read `seamless.profile.yaml` for the cluster name
3. The mode is `rw` for read-write clients, `ro` for read-only

**Server-side files** (on the machine running the service — the frontend for remote clusters, local for local clusters):
```
~/.remote-http-launcher/server/{key}.json    # PID, status, port, workdir
~/.remote-http-launcher/server/{key}.log     # stdout+stderr of the server process
```

**Client-side files** (on your local machine):
```
~/.remote-http-launcher/client/{key}.json    # hostname, port (connection info)
```

You can also discover keys empirically using the helper commands:
```bash
rhl-ls-services --client          # local — shows all known connections
ssh FRONTEND rhl-ls-services      # remote — shows all running services
```

### How to read server logs

**For a local cluster**:
```bash
rhl-cat-log <key>
rhl-cat-json <key>    # PID, port, status
```

**For a remote cluster**: the logs live on the frontend host:
```bash
ssh <ssh_hostname> rhl-cat-log <key>
ssh <ssh_hostname> rhl-cat-json <key>
```

The `ssh_hostname` to use is in the cluster YAML (under `frontends[].ssh_hostname`, falling back to `frontends[].hostname` if not set). The cluster YAML is at `~/.seamless/clusters/{clustername}.yaml` or defined inline in `~/.seamless/clusters.yaml`.

### What to look for in server logs

- **Python tracebacks**: the server crashed. Read the traceback to find the root cause. Common: dependency API changes (e.g., Starlette removing a parameter), import errors from wrong conda env, missing files.
- **No log file at all**: the server never started. Check the JSON status file - if `status` is `starting` and never became `running`, the launch script itself failed. Check conda activation, SSH connectivity.

## Finding PID Files and Restarting Services

### The server JSON contains the PID

Read `~/.remote-http-launcher/server/{key}.json` (on the host running the service):
```json
{
  "workdir": "<bufferdir>/<project>",
  "log": "<home>/.remote-http-launcher/server/<key>.log",
  "command": "hashserver --port-range <start> <end> ...",
  "uid": 1000,
  "pid": 12345,
  "status": "running",
  "port": 60757
}
```

### Clean restart procedure

To fully restart a service:

**1. Kill the server process and clean its state file**:
```bash
# For a remote cluster:
ssh <ssh_hostname> rhl-kill-service <key>

# For a local cluster (same machine):
rhl-kill-service <key>
```
`rhl-kill-service` reads the PID from the server JSON, sends SIGHUP, and removes the JSON file in one step.

**2. Kill any SSH tunnel** (locally):
If the cluster uses tunneling (`tunnel: true` in cluster YAML), there will be an SSH tunnel process forwarding a local port to the remote service port. Find and kill it:
```bash
# Find tunnel processes for this service
ps aux | grep "ssh.*-L.*<remote_port>"
# Or more broadly for a given frontend:
ps aux | grep "ssh.*-N.*<ssh_hostname>"
```
Killing stale tunnels avoids port conflicts on reconnection.

**3. Clean up client state** (optional but recommended):
```bash
# Local client state (always local, no SSH needed)
rhl-rm-state --client <key>
```

**4. Re-run the test** — `remote-http-launcher` will re-launch the service automatically.

### Bulk restart (all services for a cluster)

```bash
# Kill and clean server state for all services in a cluster (on the frontend)
ssh <ssh_hostname> rhl-restart-cluster <CLUSTERNAME>

# Remove local client state for the same cluster
rhl-ls-services --client | grep -- -<CLUSTERNAME>- | xargs -I{} rhl-rm-state --client {}
```

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

```bash
# On the host running the services (SSH for remote, direct for local):

# Clear database
ssh <ssh_hostname> rhl-clear-db <database_dir>/<project>/<stage>      # remote
rhl-clear-db <database_dir>/<project>/<stage>                          # local

# Clear buffers — deletes all cached data for this project/stage
ssh <ssh_hostname> rhl-clear-buffer <bufferdir>/<project>/<stage>      # remote
rhl-clear-buffer <bufferdir>/<project>/<stage>                         # local
```

`rhl-clear-buffer` removes all files directly inside the given directory (the project/stage buffer tree itself is preserved). `rhl-clear-db` removes `seamless.db` from the given directory.

**Always derive the actual paths from the cluster YAML for the specific cluster in use.** Do not hardcode paths — they differ per cluster, per project, and per stage.

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
3. **Read the server log.** SSH to the frontend if needed. The log file path is `~/.remote-http-launcher/server/{key}.log`.
4. **Find the root cause.** Is it a code bug? A dependency incompatibility? A stale process? A network issue?
5. **Fix in the right repo.** Don't patch the test or the client. Fix the server, the dependency, or the configuration.
6. **Clear the cache.** Delete both the bufferdir contents and seamless.db for the project, so you test actual re-execution, not cached results.
7. **Restart the service.** Kill the PID, clean up JSON state and tunnels, then re-run.
8. **Verify the fix.** The test must pass on a cold cache. A pass on a warm cache proves nothing.

## Reference Map (load only as needed)

- `references/key-derivation.md`: how tool keys are constructed from cluster/project/stage, with concrete examples.
- `references/launcher-lifecycle.md`: the full remote-http-launcher lifecycle (launch, monitor, handshake, tunnel, teardown).
