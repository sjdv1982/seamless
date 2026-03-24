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

## CLI scripts

Installing `remote-http-launcher` also provides:

- `remote-http-launcher`
