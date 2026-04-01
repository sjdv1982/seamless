## Remote HTTP Launcher Lifecycle

### Overview

`remote-http-launcher` manages the full lifecycle of Seamless services: launch, monitor, healthcheck, tunnel, and teardown. It is invoked by `seamless-config` (via `BufferLaunchedClient`, `DatabaseLaunchedClient`, etc.) and runs the service as a detached process.

Source: `remote-http-launcher/remote_http_launcher.py`

### Execution flow (`_execute`)

1. **Check for existing local connection**: reads `~/.remote-http-launcher/client/{key}.json`. If a valid connection exists (service still responding), returns immediately — no relaunch.

2. **Check remote state**: reads `~/.remote-http-launcher/server/{key}.json` on the target host.
   - `status: "running"` + port reachable → reuse existing service
   - `status: "starting"` → wait (up to timeout) for it to become `"running"`
   - Missing or stale (process dead) → proceed to launch

3. **Launch process**: generates a Python script that:
   - Creates the remote directory (`~/.remote-http-launcher/server/`)
   - Deletes any previous log file
   - Opens a new log file in append mode (`{key}.log`)
   - Starts the service command via `subprocess.Popen` with:
     - `shell=True`, `executable='/bin/bash'`
     - `cwd=workdir` (e.g., the bufferdir for hashserver)
     - stdout+stderr piped to the log file
     - `start_new_session=True` (detaches from launcher)
   - Writes the server JSON with PID, status `"starting"`, workdir, command, etc.

4. **Wait for status file**: polls up to 20 seconds for the JSON to appear and status to change.

5. **Monitor startup**: polls the JSON up to 15 times (1s apart). The service itself is expected to update the JSON from `"starting"` to `"running"` (with port number) once it binds a port.

6. **Establish SSH tunnel** (if `tunnel: true`):
   - Creates `ssh -N -L <local_port>:<remote_host>:<remote_port> <ssh_host>`
   - Spawns a tunnel monitor script in a separate session
   - The monitor watches the remote PID and kills the tunnel if the service dies
   - Writes a temporary status file to signal readiness (timeout: 15s)

7. **Perform healthcheck**: HTTP GET to the handshake URL (e.g., `/healthcheck` for hashserver/database, `/health` on dashboard port for daskserver).
   - Local: up to 5 trials, 3s apart
   - Remote: up to 15 trials, 1s apart

8. **Write client JSON**: saves `{hostname, port}` (and `ssh_hostname` if tunneled) to `~/.remote-http-launcher/client/{key}.json` for fast reconnection.

### Execution models

- **Local clusters** (`type: local`): uses `LocalExecutor` — runs commands via local subprocess
- **Remote clusters**: uses `SSHExecutor` — runs commands via `ssh <host> bash -lc '<command>'`

The executor is chosen based on whether `hostname` is present in the tool config (removed for local clusters by `_configure_tool`).

### Process management

- **Processes run in a new session** (`start_new_session=True`): they survive if the launcher exits
- **Kill signal**: `kill -1 <pid>` (SIGHUP) — sent via the executor (SSH or local)
- **Stale detection**: if the JSON exists but the PID is dead (`ps -p <pid>` fails), the launcher treats it as stale and relaunches
- **Tolerance for stale JSON**: the launcher handles stale state gracefully but wastes time on SSH roundtrips to check dead PIDs. Cleaning up JSON files after killing processes speeds up subsequent launches.

### Tunnel management

Tunnels are SSH port-forwarding processes (`ssh -N -L ...`) running locally. They are monitored by a background script that:
- Periodically checks if the remote service PID is still alive (via SSH `kill -0`)
- Kills the tunnel if the remote process exits
- Handles SIGTERM/SIGINT for clean shutdown

Stale tunnels (where the remote process died but the tunnel wasn't cleaned up) will cause port conflicts on relaunch. Kill them manually if needed:
```bash
ps aux | grep "ssh.*-N.*-L"
```

### Handshake configuration (from tools.yaml)

| Tool | Handshake type | Details |
|------|---------------|---------|
| hashserver | `healthcheck` | HTTP GET to `/healthcheck` on the service port |
| database | `healthcheck` | HTTP GET to `/healthcheck` on the service port |
| jobserver | `healthcheck` | HTTP GET to `/healthcheck` on the service port |
| daskserver | `path: health, port_name: dashboard_port` | HTTP GET to `/health` on the Dask dashboard port (not the scheduler port) |

### Environment variable

`REMOTE_HTTP_LAUNCHER_DIR`: overrides `~/.remote-http-launcher` as the base directory for both client and server state.
