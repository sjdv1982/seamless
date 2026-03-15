# Seamless Command Language

`seamless_config` discovers configuration through two optional files in the
work directory and its parents:

| File | Recommended policy | Purpose |
| --- | --- | --- |
| `seamless.yaml` | Commit to version control | Project-wide, deterministic defaults |
| `.seamless.yaml` | Add to `.gitignore` | Local, developer-specific overrides (e.g. cluster
hostnames or experimental settings) |

Both files use the same command language described below. `load_config_files()`
reads the file pair in the current workdir. If either file contains
`inherit_from_parent`, the loader also inspects the parent directory and
prepends its commands so they run before the child’s entries. This repeats
until a directory without `inherit_from_parent` is reached (or the filesystem
root), which means parent defaults are always applied before the local
overrides.

## Syntax

Each document must be a YAML list. Every list item is either a bare command
name (`inherit_from_parent`) or a single-key mapping (`cluster: newton`). If the
file parses as valid YAML but not a list, the loader raises an error and shows
an example (`- project: myproject`).

### Available commands

| Command | Arguments | Description |
| --- | --- | --- |
| `cluster` | string | Calls `seamless_config.select_cluster(value)` |
| `execution` | string (`process`/`spawn`/`remote`) | Calls `seamless_config.select_execution(value)` |
| `queue` | string | Calls `seamless_config.select_queue(value)` |
| `remote` | null or string (`daskserver`/`jobserver`) | Calls `seamless_config.select_remote(value)` |
| `persistent` | boolean | Calls `seamless_config.select_persistent(value)` |
| `project` | string | Calls `seamless_config.select_project(value)` |
| `subproject` | string | Calls `seamless_config.select_subproject(value)` |
| `inherit_from_parent` | – | Also read commands from the parent directory and prepend them |
| `clusters` | mapping | Updates the local `_clusters` dict and runs before other commands |
| `stage <name>` | list of commands | Executes the nested list only when the current stage equals `<name>` |

The `queue` command requires the current cluster to expose queues in its definition and fails with a `ValueError` when the named queue is missing. The `remote` command accepts only `null`, `daskserver` or `jobserver`. The `persistent` command forces persistent storage on or off; when omitted it defaults to `true` if a cluster is selected and `false` otherwise.

Internally, commands are split into two passes: those with priority (currently
only `clusters`) and the rest. Between the passes the loader calls
`seamless_config.cluster.define_clusters(_clusters)` so the later commands use
the freshest cluster data.

If no `execution` command is encountered, `init()` defaults to `remote` when a
cluster is selected and otherwise falls back to `process`. Clusters only need to
be defined when `execution` is set to `remote`; for other modes, an undefined
cluster triggers a warning that also notes that persistence is unavailable,
while `execution: remote` without a cluster raises an error.

### Stage blocks

Stage-specific configuration uses YAML keys that begin with `stage` and a
literal stage name. For example:

```yaml
- stage build:
  - execution: remote
```

When `seamless_config.select_stage("build")` has been called, the commands
inside the block are executed as if they appeared in the outer list; otherwise
they are skipped.

### Example

```yaml
# seamless.yaml (checked in)
- project: my-shared-project
- inherit_from_parent

# .seamless.yaml (ignored in Git)
- clusters:
    local:
      tunnel: false
      frontends: [...]
    mycluster:
      tunnel: true
      frontends: [...]
- cluster: local
- stage prod:
  - cluster: mycluster
```

The `.seamless.yaml` snippet defines the local and mycluster clusters, selects the `local` entry as the active cluster, and only switches to the
`mycluster` cluster when the current stage equals `prod`.
