# Setting up a local cluster

A "cluster" in Seamless terminology is a named configuration that specifies where buffers are stored (hashserver), where transformation results are recorded (database), and optionally where computation is delegated (jobserver or daskserver). Even for local, single-machine use, this configuration is needed to get persistent caching and to use the CLI tools.

## Defining the cluster

Cluster definitions live in `~/.seamless/clusters.yaml`. A simple local cluster looks like this:

```yaml
local:
  type: local
  frontends:
    - hashserver:
        bufferdir: /path/to/seamless-buffers
        conda: hashserver
        network_interface: 127.0.0.1
        port_start: 55100
        port_end: 55199
      database:
        database_dir: /path/to/seamless-db
        conda: seamless-database
        network_interface: 127.0.0.1
        port_start: 55200
        port_end: 55299
```

This defines a cluster named `local` with two services: a hashserver that stores buffers on disk under `bufferdir`, and a database that stores transformation-to-result mappings in a SQLite file under `database_dir`. Both services bind to localhost and pick a free port from their respective ranges. The `conda` fields name the conda environments in which each service should run (each Seamless service is installable as a separate package).

The hashserver stores data permanently — there is no eviction. The database likewise retains all records. Together, they ensure that any computation you have performed can be looked up by its identity without re-execution.

## Activating the cluster

In your project directory, create `seamless.profile.yaml` (which should be in `.gitignore`, since it contains local paths and preferences):

```yaml
- cluster: local
```

And a `seamless.yaml` (which can be committed to version control):

```yaml
- project: my-project
- execution: process
```

The `execution: process` line is important. When a cluster is defined, Seamless defaults to `execution: remote`, which expects a jobserver or daskserver — services that a minimal local cluster does not include. Setting `execution: process` tells Seamless to run transformations in the current process while still using the cluster's hashserver and database for persistent storage.

Then, in Python:

```python
import seamless.config
seamless.config.init()
```

Or from the command line:

```bash
seamless-init
```

This reads the YAML files, starts the configured services (if not already running), and connects to them. From this point on, transformations are cached persistently: results survive across sessions, and `seamless-run` can upload inputs and download results through the hashserver.

## What changes with a cluster

Without a cluster, Seamless operates entirely in-process and in-memory. With a local cluster:

- **Buffers are stored on disk** via the hashserver. Input data, code, and results are all content-addressed files that persist across sessions.
- **Transformation results are recorded** in the database. The mapping from "this code applied to these inputs" to "this result checksum" is durable.
- **`seamless-run` can function fully**, uploading input files to the hashserver and downloading result files after execution.
- **Fingertipping becomes possible**: if a result buffer is missing from the hashserver (e.g. it was marked as `scratch`), Seamless can look up which transformation produced it and re-execute that transformation to recover the result.

The step logic — your Python functions and bash commands — does not change. Only the storage and execution backend configuration changes.

## Execution modes

The cluster's execution mode controls where transformations run. This is set via `seamless.yaml` or `seamless.profile.yaml`:

```yaml
- execution: process     # in the current Python process
- execution: spawn       # in local worker processes
- execution: remote      # on the cluster (requires jobserver or daskserver)
```

When a cluster is defined and no `execution` command is given, Seamless defaults to `remote`. For local development without a jobserver or daskserver, you must explicitly set `execution: process` or `execution: spawn`. `spawn` gives you parallelism across CPU cores without any remote infrastructure. The `remote` modes (jobserver for simple dispatch, daskserver for HPC-scale scheduling) are covered in [Remote execution](remote.md).
