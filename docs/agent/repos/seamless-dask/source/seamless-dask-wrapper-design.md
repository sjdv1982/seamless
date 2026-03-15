# seamless-dask-wrapper

The wrapper is designed to hold a Dask cluster (dask.distributed.Cluster) instance.

Although it can wrap LocalCluster, it is primarily designed to wrap dask-jobqueue Cluster classes.

In a nutshell, it reads parameters and sets them as Dask config.

Then it reads a "cluster string", evaluating it into a Dask cluster object.

It waits until a status file is available and writes certain port/host/pid information in there.

Finally, this cluster object is kept alive as long as it has running jobs and for a while longer.

## Concepts and definitions

### Propagation into dask-jobqueue

First, there is the concept of "propagating PARAMETER into dask-jobqueue". This is done as
follows:

```
dask.config.set({
    "jobqueue": {
        "XXX": {
            PARAMETER: VALUE,
        }
    }
})
```

which is repeated for XXX=slurm, XXX=oar, and every other value understood by dask-jobqueue

### Propagation as env var

In addition, there is the concept of "propagating as env var". The purpose is to have an env var available to each Dask worker process. The mechanism of that is as follows:

The env var VAR is encoded by the wrapper as a text string "export VAR=VALUE",
with the proper bash quoting.

A list of text strings represents all propagated env vars.

Eventually, the list of text strings is propagated into dask-jobqueue's "job-script-prologue" parameter.

### Propagation of Dask config

Finally, there is the concept of "setting + propagating Dask config".

The wrapper will set certain parameters as Dask config in the normal way,
e.g. `dask.config.set({"distributed.worker.daemon": False})` .

In addition, those parameters that correspond to Dask config for scheduler, worker and nanny are propagated as env vars. For example,
"distributed.worker.daemon=False" becomes "export DASK_DISTRIBUTED__WORKER__DAEMON=False".

It is important to observe order here.

- In HPC environments, the wrapper runs on the same file system as the scheduler and Dask workers.
Therefore, system-wide Dask config (/etc/dask, ~/.config/dask) is in principle accessible from the wrapper.
- Only specific parameters are propagated into env vars. The parameters to propagate are *not*
read from Dask config. In fact, when the env var text strings are synthesized, Dask has not been imported yet. Therefore, system-wide Dask config cannot pollute the env vars.
- After env var propagation, the wrapper imports Dask, loads the system-wide config, and then sets (overules) Dask config in the normal way. The cluster string sees this config. Therefore, the
config set by the wrapper takes precedence.
- A launched Dask worker imports Dask, loading the system-wide config, AND it has the propagated env vars. The way Dask works, the env vars take precedence.
- In summary, system-wide Dask config is taken into account, but config set by the wrapper always takes precedence.

## Command line arguments

The wrapper has one required positional argument, "cluster"

This is a string of the format "MODULE::SYMBOL"

This cluster string will eventually be executed under Python as "from MODULE import SYMBOL"

For the rest, the wrapper takes more or less the same arguments as jobserver:

- port-range
- host
- status-file
- timeout

## Mechanics

### 1. Wait for status file

The wrapper waits until the status file exists, and reads "parameters" from it, the same way jobserver does.

### 2. Propagation

Note that in this step, only data-that-will-be-propagated is generated.

Import of Dask and of the cluster string will happen later!

#### A

The following constant parameters are propagated into dask-jobqueue:  

- processes: 1
- python: "python"

The following constant parameters are propagated into Dask:

- distributed.worker.daemon: False

#### B

The following parameters are read from the status file "parameters" dict,
and propagated into jobqueue. If marked as "optional", propagation only takes place if defined.

Otherwise, if no default is specified, they are mandatory.

- walltime
- cores
- memory
- tmpdir. Propagated into both "local-directory" and "temp-directory". Default: /tmp
- partition, propagated into "queue". Optional
- job_extra_directives: Optional, but must be a list if defined. Example: ["-p grappe"]
- project. Optional (e.g. "capsid")
- memory_per_core_property_name. Optional.
- job_script_prologue: Optional, but must be a list if defined.

For SLURMCluster instances,  "export PYTHON_CPU_COUNT=SLURM_JOB_CPUS_PER_NODE" is
added to "job_script_prologue", so that multiprocessing doesn't try to use all cores.

Note that worker_extra_args is not supported, since it is superfluous with "propagate as env var".

The wrapper uses worker_extra_args internally to overrule jobqueue's invocation of the "dask worker" command.

#### C

The following parameters are read from the status file "parameters" dict,
and propagated into Dask. If marked as "optional", propagation only takes place if defined.

Otherwise, if no default is specified, they are mandatory.

- unknown-task-duration => distributed.scheduler.unknown-task-duration. Default: 1m

- target-duration => distributed.scheduler.target-duration. Default: 10m

- internal-port-range => distributed.worker.port and distributed.nanny.port. Default: port-range command-line parameter

- lifetime-stagger => distributed.worker.lifetime.stagger. Default: 4m

- lifetime => distributed.worker.lifetime.duration. Default: walltime minus lifetime-stagger minus 1m

In case of default: Note that "walltime" is in hh:mm:ss format. All three values (walltime, lifetime-stagger and 1m) are understood by `dask.utils.parse_timedelta`. The subtraction result `td` can be converted to string using f"{int(td.total_seconds())}s"

- dask-resources => distributed.worker.resources. Optional.

#### D. Worker threads

Next, the number of threads-per-worker is set up by the wrapper.

"transformation_throttle" is read from the status file "parameters" dict,
as an int with a default of 3.

This controls how many Seamless transformations are allowed per spawned Seamless worker.
It is propagated as env var SEAMLESS_WORKER_TRANSFORMATION_THROTTLE

Then the wrapper computes the number of threads per worker as `T = cores * transformation_throttle`.

In particular, this overrides the formula of one-thread-per-reserved-core imposed by all dask-jobqueue Cluster subclasses (*) .

The override is done by propagating `[f"--nthreads {T}"]` into jobqueue's "worker_extra_args" config parameter.

#### E. extra_dask_config

If present, "extra_dask_config" is read from the status file "parameters" dict.

This must be a dict where the keys are Dask config keys and the values are strings.

These are propagated into Dask config, including as env vars if the keys start with the right prefix.

#### F. Scheduler ports

Finally, within "port-range", two random free ports are selected.

These ports are propagated to jobqueue's "scheduler-options" dict as "port" and "dashboard_address".
"host" is also propagated to jobqueue's "scheduler-options" dict.

### 3. Configuration

Dask (including `distributed`) is imported, and all propagations are merged into the existing config.

### 4. Cluster string evaluation

The cluster string is now executed under Python as "from MODULE import SYMBOL"

The result can be:

- A Dask cluster instance. We can use this directly.

- A class. In that case, it must be a subclass of Dask cluster.
    An instance will be created by calling the class without arguments.

- A function, i.e. an instance of FunctionType.
    The function will be called without arguments, which must give a Dask cluster instance

After this step, we have now a Dask cluster instance.
If it is an instance of OARCluster, it is now verified that the `memory_per_core_property_name` is present in the status file parameter dict.

### 5. Launching the cluster

The parameters "interactive" (bool, default False) and "maximum_jobs" are now read from the status file "parameters" dict.

The cluster is then launched as  `cluster.adapt(minimum_jobs=int(interactive), maximum_jobs=maximum_jobs)

### 6. Writing the status file

If any of step 2. - 6. has failed, the wrapper writes "failed" in the status file and exits by (re-)raising an exception, or by writing to stderr and by exiting with status code 1.

If it has succeeded, the wrapper writes the Dask scheduler port under "port" and the dashboard port under
"dashboard_port.

### 7. Keeping the cluster alive

A "last activity time" is kept, initially None. Every second, it is checked:

- That the scheduler has running jobs OR connected clients.

    If this is true, "last activity time" is set to None.

    Else, if "last activity time" is None, it is set to the current time

- That the "last activity time" is either None or no more than X seconds in the past,

    where X is the "timeout" parameter.

    Else, the wrapper exists normally.

## Runtime configuration by Seamless

Seamless will submit Dask tasks that require 1 "S resource" each.

Every worker needs database and hashserver config, and its S resources set, but Seamless will do this.

## Seamless .YAML level

The `seamless-dask-wrapper` command, including parameters, is ultimately synthesized by `seamless.config`.

They are read from `clusters.yaml` (or a yaml file in `clusters/`).

`cluster.yaml` parameters can be overridden in `seamless.yaml` at the substage level (**).

## Footnotes

(*) = other than SLURM, which has a job_cpu override for the reserved number of cores.

(**): Note that there is `seamless.yaml` under version control, and `.seamless.yaml`
which is not under version control, containing system-specific configuration.
The default usage is simply to define "queue" in `.seamless.yaml`, selecting a pre-defined queue.
