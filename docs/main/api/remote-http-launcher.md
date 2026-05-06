# remote-http-launcher

`remote-http-launcher` is a command-line tool and Python library for launching, supervising, and reconnecting to long-running HTTP services — either locally or on remote hosts via SSH. It is driven by a single YAML configuration file that describes the service to launch, and it manages all process lifecycle state through JSON files on the client and server side.

Although it originated in the [Seamless](https://github.com/sjdv1982/seamless) scientific-workflow framework, `remote-http-launcher` is fully generic: it can launch any HTTP service that follows its status-file protocol.

## How it works

Given a YAML config, the launcher follows a deterministic sequence:

1. **Check for an existing local connection file** (`~/.remote-http-launcher/client/<key>.json`). If one exists and the service responds to the configured handshake, the launcher exits immediately — the service is already running.

2. **Check the remote (or local) server directory** (`~/.remote-http-launcher/server/<key>.json`):
   - If the remote JSON shows `"status": "running"`, the launcher verifies the port and handshake, then writes the local connection file.
   - If it shows `"status": "starting"`, the launcher monitors until the service comes up (or times out).
   - If the JSON file is absent or stale, the launcher starts the service.

3. **Launch the service** as a daemonic subprocess (locally or over SSH), writing a server-side JSON file with the PID, workdir, and `"status": "starting"`. The path to this JSON file is passed to the service via the `{status_file}` template variable in the `command` field.

4. **Optionally create an SSH tunnel** forwarding the remote port to a local port, with a background monitor that tears down the tunnel when the remote process exits.

5. **Write the local connection file** containing the hostname and port (local or tunneled) for consumption by client code.

## Status-file protocol

`remote-http-launcher` imposes a specific contract on any service it launches. The service **must**:

1. Read the JSON status file whose path was passed to it (via the `{status_file}` template variable in the command).
2. Acquire a free port and start listening on it.
3. Update that same JSON file: set `"status"` to `"running"` and add a `"port"` field with the chosen port number.

If the service fails to start, it should set `"status"` to `"failed"`.

The launcher monitors the status file after starting the process. If the file is not updated within roughly one minute (and the process has exited), the launcher treats the launch as failed.

This is the only requirement `remote-http-launcher` places on the launched service — beyond this protocol, the service can be anything that speaks HTTP.

## Configuration

The YAML configuration file supports the following fields:

| Field | Required | Description |
|-------|----------|-------------|
| `workdir` | yes | Working directory on the (remote) host |
| `key` | yes | Template string evaluated to a filename used for the JSON state files |
| `command` | yes | Template string for the bash command to launch the service |
| `hostname` | no | Target HTTP hostname or IP; omit to run locally |
| `ssh_hostname` | no | SSH host to connect to (defaults to `hostname`) |
| `network_interface` | no | Interface the service binds to (default: `localhost`) |
| `tunnel` | no | Create an SSH tunnel for the service port (default: `false`) |
| `handshake` | no | HTTP path (and optional query parameters) for a health-check GET request |
| `conda` | no | Conda environment to activate before launching the command |
| `file_parameters` | no | Arbitrary parameters written into the server-side JSON file |
| `meta` | no | Opaque caller-provided JSON metadata copied into client/server state |

The `key` and `command` fields are Python f-string templates evaluated against the full config namespace.

### Example

```yaml
workdir: /home/user/my-service-data
hostname: my-server.example.com
key: 'myservice-{workdir.strip("/").replace("/", "--")}'
command: >-
  myservice --port-range {port_start} {port_end}
  --status-file {status_file}
  --host {config['network_interface']}
  --timeout {timeout}
  {workdir}
network_interface: "0.0.0.0"
handshake: healthcheck
conda: myservice-env
timeout: 600
port_start: 10000
port_end: 19999
```

A JSON schema is included at [config.schema.yaml](https://github.com/sjdv1982/seamless/blob/main/remote-http-launcher/config.schema.yaml) for validation and editor support.

## Installation

```bash
pip install remote-http-launcher
```

The only runtime dependency is PyYAML.

## Usage

```bash
# Launch (or reconnect to) the service described in config.yaml
remote-http-launcher config.yaml

# Override the client connection directory
remote-http-launcher config.yaml --connection-dir /tmp/my-connections

# Print the evaluated command without launching
remote-http-launcher config.yaml --dry-run
```

### Python API

```python
from remote_http_launcher import run

result = run({
    "workdir": "/home/user/data",
    "key": "my-service",
    "command": "myservice --port-range 10000 19999 --status-file {status_file} {workdir}",
    "handshake": "healthcheck",
})
print(result["hostname"], result["port"])
```

## SSH Guard

`remote-http-launcher` ships an SSH guard (`rhl-guard`) that restricts what commands can be run on the remote server under the service user account. When installed, only named `rhl-*` helper programs are permitted — naked shell commands such as `pkill`, `rm -rf`, `bash -lc ...`, or arbitrary `python3 -c` are rejected.

### How it works

The SSH `command=` option in `authorized_keys` forces every incoming SSH session through `rhl-guard`. The guard reads `SSH_ORIGINAL_COMMAND`, validates it against a whitelist, and either `exec`s the command or exits with an error. Interactive sessions (no `SSH_ORIGINAL_COMMAND`) are always rejected.

The guard whitelist covers only top-level `rhl-*` helper commands installed by this package (see below). The helpers perform state inspection, process checks, HTTP handshakes, port verification, conda cache reads, and service launch using structured argv/data instead of remote shell or Python source.

The guard silently strips any leading `VAR=value` shell variable assignments before the whitelist check. This means the standard client PATH prepend (`PATH=$HOME/miniforge3/bin:$HOME/miniconda3/bin:$PATH rhl-ps`) passes through `rhl-guard` unchanged — the assignments are dropped and only the `rhl-*` command and its arguments are exec'd.

Direct process-management commands such as `kill -1 <pid>` are rejected by
the guard. Use helpers such as `rhl-stop <key>` instead.

### Path policy

Three of the helpers — `rhl-clear`, `rhl-ps-persistent`, and
`rhl-launch-service` (the `--workdir` argument) — accept filesystem paths
chosen by the SSH client. Without bounding which paths the client may
supply, a stolen SSH key with `command="rhl-guard"` would still reach
helpers that destroy or probe arbitrary directories.

> **Path policy is enforced entirely by `rhl-guard`. The `rhl-*` helpers
> are not modified.** They behave identically to previous versions when
> invoked directly — locally on the server, via tests, or in any
> client-side context (`rhl-ps`, `rhl-rm --client`, etc.). The guard is
> the single point that parses `SSH_ORIGINAL_COMMAND`, identifies any
> path arguments destined for the three helpers above, validates those
> paths against the configured policy, and only then `exec`s the helper.
> Direct invocations bypass `rhl-guard` entirely and are *unaffected*
> by the policy.

The policy is declared via one of the following mutually-exclusive flags
on `rhl-guard` in the `authorized_keys` `command=` directive:

| Flag | Effect | When to use |
|------|--------|-------------|
| `--data-roots /path/to/roots-file` | **Strict allowlist.** Each path the guard extracts from the SSH command must, after `~`-expansion and symlink resolution, equal or live under one of the absolute paths listed in the file. One path per line; blank lines and `#` comments are ignored. The same list governs `rhl-clear`, `rhl-ps-persistent`, and `rhl-launch-service --workdir`. | Recommended for production. Fully explicit; no heuristics. |
| `--clear-policy seamless` | **Marker preset for Seamless.** The guard accepts a target directory for `rhl-clear` and `rhl-ps-persistent` only if it contains either a `seamless.db` file or a `.HASHSERVER_PREFIX` file. `rhl-launch-service --workdir` is checked against the always-on heuristics only (since a workdir that has not yet been created cannot contain a marker). No allowlist file required. | Seamless deployments. |
| `--clear-policy marker:NAME` | **Generic marker.** Same shape as the `seamless` preset, but the marker filename is configurable. Drop `touch <dir>/<NAME>` into each directory you wish to authorise. | Non-Seamless deployments that prefer per-directory markers over a central allowlist. |
| `--permissive-paths` | **Disables the policy.** The guard accepts any path that passes the always-on heuristics below. | Compatibility for deployments that cannot configure any of the modes above. **Not recommended.** Mutually exclusive with `--data-roots` and `--clear-policy`; combining them is a fatal `rhl-guard` configuration error. |

If none of these flags is present, **`rhl-guard` refuses to dispatch
`rhl-clear`, `rhl-ps-persistent`, or `rhl-launch-service`** (any
invocation of those three, not only those that include a path argument)
and exits with an error pointing the operator at this section. The
other `rhl-*` helpers do not accept client-chosen paths and continue
to be dispatched normally.

#### Always-on heuristics

In every mode (including `--permissive-paths`), `rhl-guard` rejects the
dispatch if any path it extracts from the SSH command is:

- not absolute after `~` expansion;
- equal to `$HOME`, or an ancestor of `$HOME` (e.g. `/`, `/home`);
- containing any segment that begins with `.` (e.g. `~/.ssh`,
  `/tmp/.cache/foo`); or
- resolved to one of the system-root directories (`/`, `/etc`, `/usr`,
  `/bin`, `/sbin`, `/lib`, `/lib64`, `/boot`, `/sys`, `/proc`, `/run`,
  `/var`, `/opt`).

These are guard-side checks applied *before* the helper is `exec`'d.
They are independent of, and additional to, the helper's own existing
checks; nothing in the helper changes.

### Installation

On the remote server, add to `~/.ssh/authorized_keys` a `command=` directive
that includes one of the [path-policy flags](#path-policy). The recommended
form pins an explicit allowlist file:

```
command="rhl-guard --data-roots /home/svc/.config/rhl/data-roots" ssh-rsa AAAA... your-key-comment
```

with `~/.config/rhl/data-roots` containing, e.g.:

```
# Persistent workdirs mirroring clusters.yaml
~/seamless-buffers
~/hashserver-bufferdir
~/seamless-databasedir
```

Alternative forms for deployments that prefer markers over a central
allowlist:

```
# Seamless preset — no allowlist file needed
command="rhl-guard --clear-policy seamless" ssh-rsa AAAA... your-key-comment

# Generic marker — drop ".rhl-clearable" into each authorised workdir
command="rhl-guard --clear-policy marker:.rhl-clearable" ssh-rsa AAAA... your-key-comment
```

Compatibility form for deployments that cannot configure either of the
above (not recommended):

```
command="rhl-guard --permissive-paths" ssh-rsa AAAA... your-key-comment
```

Running `rhl-guard` directly prints an installation-oriented error explaining
that it must be invoked by SSH. To test one guarded command locally on the
server:

```bash
SSH_ORIGINAL_COMMAND="rhl-ps" rhl-guard
```

### Conda cache

The launcher reads conda configuration via `rhl-conda-info` automatically. Prime the cache once on the remote server before using conda environments:

```bash
ssh <remote_host> rhl-cache-conda
```

Re-run this if the conda installation or environments change. On hosts where no `rhl-*` helpers are installed, the launcher falls back to inline heredoc probes automatically.

### Reaching the `rhl-*` helpers over SSH

The launcher's fallback covers only its own conda discovery — anything that depends directly on the helpers (the `seamless-service-*` layer in `seamless-config`, agents shelling out to `rhl-ps` / `rhl-stop` / `rhl-logs`, etc.) requires `remote-http-launcher` to be installed on the remote server. Two supported install paths:

- **System-wide install** (recommended when you have root): `pip install remote-http-launcher` into the system Python. The helpers land under `/usr/local/bin`.
- **Conda base env install** (no root): `pip install remote-http-launcher` into the conda base environment on the remote host. The helpers land in `$HOME/miniforge3/bin` or `$HOME/miniconda3/bin`.

Clients (`seamless-service-*` and agents) must prepend `$HOME/miniforge3/bin:$HOME/miniconda3/bin` to PATH on every SSH invocation of an `rhl-*` helper, which covers conda-base installs without any shell startup changes:

```bash
ssh <host> 'PATH=$HOME/miniforge3/bin:$HOME/miniconda3/bin:$PATH' rhl-ps --json
```

Use the command above to verify reachability. If it still returns `command not found`, `remote-http-launcher` is not installed on the server.

## Lifecycle States

Launcher state normally moves through these states:

| State | Meaning | Next action |
|-------|---------|-------------|
| `absent` | No launcher state or persistent directory exists | — |
| `starting` | Process launched, waiting for it to report a port | Wait, or check logs if it hangs |
| `running` | Service healthy and port known | — |
| `failed` | Startup failed or timed out | Read log with `rhl-logs`, fix, restart |
| `stale` | Server JSON exists but process is dead | Read log with `rhl-logs`, then `rhl-rm` to clear |
| `persistent` | Workdir contains data even when no process is running | `rhl-ps-persistent` to inspect; `rhl-clear` to wipe |

**Persistent state causes false-pass test results.** A service launched against
a populated buffer directory or `seamless.db` returns cached results without
exercising the underlying computation. When a test passes suspiciously after
changes that should affect results, use `rhl-ps-persistent` (or
`seamless-service-ps --persistent` from `seamless-config`) to inspect cached
data, and `rhl-clear` (or `seamless-service-clear`) to wipe it before
re-testing on a cold cache.

**The `stale` state is the post-mortem window for non-persistent services.**
`jobserver`, `daskserver`, and `pure-daskserver` have no persistent data; the
log file is the only post-mortem artefact, and it is reachable via `rhl-logs`
only while the server JSON exists. Read the log *before* running `rhl-rm` — the
log file itself survives JSON removal but is no longer addressable by key
through the helper.

## JSON State Schema

Server JSON files live under `~/.remote-http-launcher/server/<key>.json` and
client files under `~/.remote-http-launcher/client/<key>.json`. Readers must
tolerate rows without `meta` — older launcher versions and callers that do not
populate it still write valid state files.

When written by `seamless-config`, the `meta` block contains:

```json
{
  "meta": {
    "service":    "hashserver",
    "cluster":    "MYCLUSTER",
    "mode":       "rw",
    "project":    "myproject",
    "subproject": null,
    "stage":      "fingertip",
    "substage":   null,
    "queue":      null
  }
}
```

`rhl-ps --json` emits this block verbatim alongside the process-state fields
(`key`, `status`, `port`, `pid`, `workdir`, `log`). The launcher treats `meta`
as opaque and does not validate its contents — Seamless-specific semantics live
entirely in `seamless-config`, not in `remote-http-launcher`.

## Helper commands (`rhl-*`)

Installing `remote-http-launcher` adds a set of server-side helper programs that perform specific, safe operations on launcher state. These are the commands agents and operators should use instead of raw `kill`, `rm`, or shell loops.

| Command | Runs on | Purpose |
|---------|---------|---------|
| `rhl-guard` | server | SSH guard entry point; validates `SSH_ORIGINAL_COMMAND` before exec |
| `rhl-cache-conda` | server | Discover conda setup and write `~/.remote-http-launcher/conda-setup.json` |
| `rhl-conda-info` | server | Print the cached conda-setup JSON; exit 1 if cache is absent |
| `rhl-launch-service --key K --workdir D [--conda-env E] [--network-interface I] [--parameters J] [--meta J] -- BINARY ARG...` | server | Launch a whitelisted service binary as a daemon; write server-side JSON |
| `rhl-inspect <key> [--with-mtime]` | server | Pretty-print the server state JSON; `--with-mtime` emits `{"mtime": …, "data": …}` |
| `rhl-logs <key> [--tail N]` | server | Print the stdout/stderr log for a service |
| `rhl-stop <key>` | server | Stop service processes without deleting JSON state |
| `rhl-pid-alive PID` | server | Exit 0 if the process is alive, 1 if it is not |
| `rhl-verify-port HOST PORT` | server | TCP-connect to HOST:PORT (3 retries); exit 0 on success, 1 on failure |
| `rhl-handshake URL` | server | GET URL; exit 0 on 2xx, 1 on network error, 2 on non-2xx status |
| `rhl-ps [--client]` | client/server | List process state rows; client mode lists local connection state |
| `rhl-ps-persistent <path> [--marker FILENAME]` | server | Report absent, empty, or populated filesystem-backed state; optionally report only directories containing a marker file |
| `rhl-rm <key> [--client] [--server]` | client/server | Remove launcher JSON state files while leaving logs on disk |
| `rhl-clear <path>` | server | Remove direct children of a validated persistent directory |

When dispatched through `rhl-guard`, calls to `rhl-clear`,
`rhl-ps-persistent`, and `rhl-launch-service` are subject to the path
policy declared on the guard itself (see [Path policy](#path-policy));
the guard validates the SSH-supplied paths and refuses to dispatch if
no policy was declared. The helpers themselves are not modified —
direct local invocation (e.g. on the server, in tests, or for
client-side helpers such as `rhl-ps` and `rhl-rm --client`) bypasses
the guard and behaves exactly as in earlier versions.

All state-file helpers respect the `REMOTE_HTTP_LAUNCHER_DIR` environment variable (same as the launcher).

Cluster-wide Seamless operations are intentionally not implemented by `rhl-*`
helpers. Use `seamless-service-stop`, `seamless-service-rm`, and
`seamless-service-ps` from `seamless-config`; those tools resolve Seamless
cluster/project/stage semantics on the client side and then dispatch safe
`rhl-*` operations.

## CLI scripts

Installing `remote-http-launcher` also provides:

- `remote-http-launcher` — main launcher CLI
- All `rhl-*` helpers listed in the table above
