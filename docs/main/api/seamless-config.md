# seamless-config

`seamless-config` is the configuration and infrastructure-selection layer for
[Seamless](https://github.com/sjdv1982/seamless) projects.

Seamless models work as pipelines of cacheable steps. `seamless-config` answers
the question *"where does this pipeline run, and against which storage?"* —
locally in-process, in local worker processes, or on a remote cluster — without
touching the step code. It reads plain YAML files, resolves cluster topology,
and wires the right remote backends (buffer store, database, jobserver, dask
scheduler) into the Seamless runtime before the first transformation runs.

## Installation

```bash
pip install seamless-config
```

## Quick start

```python
import seamless.config

seamless.config.init()          # reads seamless.yaml / seamless.profile.yaml
                                # from the caller's directory upward
# … build and run your workflow …
```

From the command line, `seamless-init` performs the same initialisation and
verifies that the configured remote services are reachable:

```bash
seamless-init                   # default stage
seamless-init --stage prod      # named stage
seamless-init --stage prod:gpu  # named stage + substage
```

---

## Configuration files

`seamless-config` discovers two optional YAML files in the work directory (and
optionally its parents):

| File | Commit to VCS? | Purpose |
| --- | --- | --- |
| `seamless.yaml` | Yes | Project-wide, deterministic defaults (project name, stage name, `inherit_from_parent`) |
| `seamless.profile.yaml` | No (add to `.gitignore`) | Developer-specific overrides — cluster hostnames, experimental settings, local credentials |

Both files use the same command language. When a file contains
`inherit_from_parent`, the loader also reads the parent directory and prepends
its commands, repeating until a directory without that flag is reached (or the
filesystem root). Parent defaults always run before child overrides.

### Command language

Each file must be a YAML list. Every item is either a bare string command or a
single-key mapping:

```yaml
# seamless.yaml
- project: my-project
- inherit_from_parent
```

| Command | Argument | Effect |
| --- | --- | --- |
| `project` | string | Sets the project name (used as the storage path component) |
| `subproject` | string | Sets an optional sub-path inside the project |
| `cluster` | string | Selects the active cluster by name |
| `execution` | `process` / `spawn` / `remote` | Sets the execution mode |
| `queue` | string | Selects a named queue on the current cluster |
| `remote` | `null` / `daskserver` / `jobserver` | Pins the remote backend when a cluster exposes both |
| `persistent` | boolean | Forces persistent storage on or off; defaults to `true` when a cluster is set |
| `clusters` | mapping | Defines cluster objects inline (runs before other commands) |
| `inherit_from_parent` | — | Also reads commands from the parent directory, prepended |
| `stage <name>` | list of commands | Runs the nested commands only when the current stage matches `<name>` |

If no `execution` command is encountered, the loader defaults to `remote` when
a cluster is selected and `process` otherwise.

See [COMMAND_LANGUAGE.md](https://github.com/sjdv1982/seamless/blob/main/seamless-config/COMMAND_LANGUAGE.md) for the full specification.

### Stage blocks

Use a `stage <name>:` key to activate commands only in a specific stage:

```yaml
# seamless.profile.yaml
- clusters:
    local:
      tunnel: false
      type: local
      frontends:
        - hostname: localhost
          hashserver:
            bufferdir: /data/buffers
            conda: hashserver
            network_interface: 127.0.0.1
            port_start: 55100
            port_end: 55199
          database:
            database_dir: /data/db
            conda: seamless-database
            network_interface: 127.0.0.1
            port_start: 55200
            port_end: 55299
          jobserver:
            conda: seamless-jobserver
            network_interface: 127.0.0.1
            port_start: 55300
            port_end: 55399

- cluster: local

- stage prod:
    - cluster: hpc-cluster
    - execution: remote
    - remote: daskserver
```

---

## Cluster definitions

Clusters are defined in `~/.seamless/clusters.yaml` and/or individual files
under `~/.seamless/clusters/*.yaml`. They can also be inlined in
`seamless.profile.yaml` via the `clusters` command (useful for portable
projects).

A cluster definition describes the *topology* of its frontend nodes and the
services each one can host:

```yaml
# ~/.seamless/clusters.yaml

mycluster:
  tunnel: true                # connect via SSH tunnel
  type: slurm                 # local | slurm | oar
  workers: 4                  # for 'spawn' / 'jobserver' mode
  frontends:
    - hostname: login.mycluster.example
      ssh_hostname: login.mycluster.example   # optional SSH override
      hashserver:
        bufferdir: /scratch/seamless/buffers
        conda: hashserver
        network_interface: 0.0.0.0
        port_start: 60100
        port_end: 60199
      database:
        database_dir: /scratch/seamless/db
        conda: seamless-database
        network_interface: 0.0.0.0
        port_start: 60200
        port_end: 60299
      daskserver:
        network_interface: 0.0.0.0
        port_start: 60300
        port_end: 60399

  default_queue: default
  queues:
    default:
      conda: seamless-dask
      walltime: "01:00:00"
      cores: 16
      memory: 32000MB
      tmpdir: /tmp
      maximum_jobs: 20
      unknown_task_duration: 1m
      target_duration: 10m
      lifetime_stagger: 4m

    highmem:
      TEMPLATE: default         # inherit all fields from 'default', then override
      cores: 4
      memory: 128000MB
```

### Frontend services

Each frontend entry can expose any subset of:

| Service | Role |
| --- | --- |
| `hashserver` | Stores and serves content-addressed buffers (the raw bytes of cell values) |
| `database` | Stores transformation results (maps input checksum → result checksum, backed by SQLite) |
| `jobserver` | HTTP job dispatch — accepts serialised transformations and returns results |
| `daskserver` | Dask-backed HPC scheduler — submits jobs to SLURM/OAR via `dask-jobqueue` |

When both `jobserver` and `daskserver` are present on the same cluster,
`remote: jobserver` or `remote: daskserver` must be specified explicitly in
`seamless.profile.yaml`.

### Queue templates

A queue entry with a `TEMPLATE` key inherits all fields from the named queue
(which must be defined earlier in the same cluster), then overrides only the
explicitly provided fields:

```yaml
queues:
  base:
    conda: seamless-dask
    walltime: "02:00:00"
    cores: 8
    memory: 16000MB
    maximum_jobs: 10
    tmpdir: /tmp
    unknown_task_duration: 1m
    target_duration: 10m

  gpu:
    TEMPLATE: base
    memory: 32000MB
    job_extra_directives: ["--gres=gpu:1"]
    dask_resources: {GPU: 1}
```

---

## Execution modes

| Mode | `execution:` value | Description |
| --- | --- | --- |
| In-process | `process` | Transformations run in the client Python process. Default when no cluster is defined. |
| Local workers | `spawn` | Transformations are dispatched to a local worker pool (uses `workers` from the cluster definition). |
| Remote (jobserver) | `remote` + `remote: jobserver` | Lightweight HTTP jobserver with a fixed worker pool. Typically used as a test setup or for simple local-cluster scenarios. |
| Remote (daskserver) | `remote` + `remote: daskserver` | Delegates to a Dask cluster with persistent storage. Any Dask `Cluster` subclass is supported; current cluster definitions cover SLURM and OAR via `dask-jobqueue`. |
| Pure Dask | `remote` + `remote: daskserver` + `persistent: false` | Dask execution without Seamless persistence (no hashserver/database). For batch jobs that don't need incremental caching. |

The three `remote` backends (`jobserver`, `daskserver`, pure Dask) are mutually
exclusive — a cluster frontend must expose exactly one, or you must pin the
choice with `remote: jobserver` or `remote: daskserver` in
`seamless.profile.yaml`.

`remote_http_launcher` handles two scheduler-placement topologies automatically:
when `hostname` is set it SSHes into the frontend and runs the Dask wrapper as a
daemon there (scheduler lives on the HPC frontend node); when `hostname` is absent
it runs the wrapper as a local daemon (Cluster object lives on the client, scheduler
lives wherever the provider puts it — suitable for cloud backends). The configuration
schema currently covers HPC schedulers (SLURM, OAR); cloud provider support would
require extending the cluster definition vocabulary, not the launcher or wrapper.

### Persistence

When a cluster is selected and `persistent: true` (the default), `seamless-config`
activates:

- `seamless_remote.buffer_remote` — writes/reads buffers via the cluster's `hashserver`
- `seamless_remote.database_remote` — checks and records transformation results via the cluster's `database`

In `execution: remote` mode it also activates the chosen job delegation backend
(`jobserver_remote` or `daskserver_remote`).

---

## Stages and substages

A *stage* is an independent execution and storage context. Each stage gets its
own subdirectory under the project path:

```text
<bufferdir>/<project>[/<subproject>][/STAGE-<stage>]
<database_dir>/<project>[/<subproject>][/STAGE-<stage>]
```

Stages are useful when the same project has multiple phases — e.g. `build`,
`test`, `prod` — that must not share cached results.

A *substage* further subdivides the job-dispatch scope (one jobserver/daskserver
per substage) without splitting storage. Substages are useful when different
substages within the same stage need different hardware (CPU vs GPU queues).

---

## Python API

```python
import seamless.config

# Simple initialization (no named stage)
seamless.config.init()

# Named stage (re-evaluates config with 'stage prod:' blocks active)
seamless.config.set_stage("prod")

# Named stage + substage
seamless.config.set_stage("prod", "gpu")

# Change substage without changing stage
seamless.config.set_substage("cpu")

# Override the directory used for config file lookup
seamless.config.set_workdir("/path/to/project")
```

`init()` is a no-op if already initialised. `set_stage()` deactivates any
previously active remote clients before re-configuring.

### Forwarding remote clients to worker processes

When a job runs inside the cluster, it may need to connect back to the same
remote services. `collect_remote_clients` / `set_remote_clients` serialise and
restore the active client configuration.

*Note: this API is already used by the daskserver. There is no need to do this from user code.*

```python
# On the client, before submitting a job:
clients = seamless_config.collect_remote_clients("mycluster")
# Pass 'clients' to the worker via job parameters or environment variable

# Inside the worker (or set SEAMLESS_REMOTE_CLIENTS=<json> in the environment):
seamless_config.set_remote_clients(clients, in_remote=True)
```

`set_remote_clients` must be called before `init()`. Worker bootstrap code can
also call `set_remote_clients_from_env()` to pick up the JSON from the
`SEAMLESS_REMOTE_CLIENTS` environment variable automatically.

---

## `seamless-init` CLI

`seamless-init` is a convenience script that calls `seamless_config.init()` (or
`set_stage`), then calls `ensure_initialized()` on each active remote backend
to verify that the servers are reachable before the workflow starts.

```text
usage: seamless-init [--stage STAGE[:SUBSTAGE]]
```

It exits immediately (success) when the `SEAMLESS_REMOTE_CLIENTS` environment
variable is present, so that worker processes that bootstrap themselves with
`set_remote_clients` are not affected.

---

## Tool launch configuration

`seamless-config` ships an internal `tools.yaml` that describes how to
construct the launch parameters for each server type (`hashserver`, `database`,
`jobserver`, `daskserver`, `pure_daskserver`). These are consumed by
`remote-http-launcher`, which starts the servers on the cluster frontend (via
SSH tunnel if needed) and returns a live port.

The `configure_hashserver`, `configure_database`, `configure_jobserver`,
`configure_daskserver`, and `configure_pure_daskserver` functions in
`seamless_config.tools` assemble the final launch dict from the cluster
definition and the current project/stage context. These functions are called
internally by `seamless-config` and by launcher scripts in other packages;
direct use is only needed when writing custom launch tooling.

---

## Relation to the Seamless ecosystem

```text
seamless-core          ← the computation engine (cells, transformers, caching)
    ↑
seamless-config        ← this package: reads YAML, wires backends, provides CLI
    ↑                 ↗ seamless-remote    (buffer + database + job clients)
    └── activates   ─── seamless-dask      (Dask scheduler integration)
                     ↘ seamless-jobserver  (HTTP jobserver)
                      ↘ seamless-database  (SQLite result store)
                       ↘ hashserver        (content-addressed buffer server)
                        ↘ remote-http-launcher (SSH + process launcher)
```

`seamless-config` is the only package in this stack that a Seamless workflow
script typically imports directly (besides `seamless` itself). All other
packages are implementation details activated by `init()` / `set_stage()`.
