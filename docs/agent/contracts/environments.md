# Environments (Contract)

An **environment** says where the script of a bash transformation runs: in a
named conda environment, or in a container made from a Docker image. The
script, its inputs and its result stay the same. Only the place changes.

The [implementation plan](../../../plans/bash-docker-conda-transformers-plan.md)
describes the launch mechanics and the phases.

## The surface

**Python face.** Every Transformer has an `environment` object:

```python
tf = Transformer("bash", direct=True)
tf.code = "samtools --version > RESULT"

tf.environment.set_conda_env("bio")                     # a named conda environment
tf.environment.set_docker({"name": "ubuntu:22.04"})     # or a Docker image
```

`get_conda_env()` and `get_docker()` read the values back. Passing `None`
clears one.

**Unix face.** `seamless-run --conda ENV …` and `seamless-run --docker IMAGE …`.
`--conda-env` and `--conda-environment` are aliases of the first,
`--docker-image` of the second.

**Workflow Context.** A bash node that is bound from a Transformer carries that
Transformer's environment, and the graph file saves it. On the bound node,
`environment` is a read-only copy.

**Transformation dict.** The environment travels as `__env__`. In it, the conda
environment is the string `conda_environment` and the image is the mapping
`docker` (*The image spec*).

These rules hold on every face:

- **An environment applies to bash transformers only.** A Python or compiled
  transformation that carries a conda environment or a Docker image is an
  error. It fails when the Transformation is built, and a transformation dict
  that carries one fails before its code runs. The message says that the two
  settings apply to bash transformers only.
- **A record probe is exempt.** The probe that captures a job's surroundings
  for a full execution record is a Python transformation that carries the
  job's `__env__` ([Execution records](execution-records.md), *Probing is
  manual*). It runs on the host and it does not fail for the conda environment
  or the image that it carries. A full record can therefore be made for a bash
  job that has an environment.
- **A conda environment and a Docker image together are an error.**
  `seamless-run` refuses the two flags together. A Transformer that has both
  fails when its Transformation is built, and a transformation dict that
  carries both fails before its script runs. The message says to pick one. A
  script that needs a conda environment inside an image activates it itself.
- **Neither is ever ignored.** A bash transformation with an environment runs
  in that environment or fails. It does not fall back to the plain host.

## What an environment changes, and what it does not

Unchanged, with or without an environment
([seamless-run and argtyping](seamless-run-and-argtyping.md),
[Pins](pins.md)):

- the job directory: one file, link or directory per pin, and the script's
  working directory;
- the pin variables that the script sees;
- the header `set -u -e`;
- the result: the file or directory `RESULT`;
- stdout and stderr: two separate streams, relayed while the script runs
  ([Transformation logs](transformation-logs.md), [Streaming](streaming.md)).

### A conda environment

The script runs as under `conda run -n NAME`.

- **A name that contains `/` is the path of an environment**, as for
  `conda run -p`.
- **Activation happens before the script and outside its `set -u -e`.** An
  activation script that reads an unset variable does not abort the job.
- **The script inherits the environment variables of the process that runs
  it**, as a plain bash transformation does, plus what activation adds.
- **The environment must exist on the executing host**, and so must a conda
  launcher (*The runtime is chosen where the job runs*). Seamless does not
  create environments.
- **Entering the environment takes time on every job.** With `conda` as the
  launcher that is in the order of a second. `mamba` and `micromamba` are much
  faster. A site that runs many short jobs sets `SEAMLESS_CONDA_EXE`.

### A Docker image

The script runs inside a container made from the image.

- **The image must contain `bash`.** Nothing else is required of it. Seamless
  does not need to be installed in it.
- **The image's ENTRYPOINT is not used.**
- **The job directory is the working directory, at `/seamless-job`.** That path
  is the same on every run, so `$PWD` is too.
- **The container sees the job directory and nothing else of the host**, with
  one exception: the read-buffer directories of the executing process are
  visible at their own paths, read-only. An input that Seamless provides as a
  link into such a directory therefore resolves. Every other buffer in those
  directories is readable by the image as well.
- **The host's environment variables are not inherited.** The pin variables
  are set.
- **`HOME` is `/seamless-job`, the working directory.** It is a writable
  directory owned by the user running the job, including when the image has no
  passwd entry for that user. Apptainer maps the job directory there with
  `--home`; its `--env` option cannot override `HOME`.
- **The script runs as the user that runs the job on the host.** Files it
  writes belong to that user. An image that only works as root or as a named
  user of its own may fail.
- **Background processes of the script end with the container.**
- **The container is removed when the script ends**, however it ends. Nothing
  is kept from one job to the next, and what the script writes outside the job
  directory is lost.

## Identity and caching

**The environment is not part of the transformation's identity.** It is carried
in `__env__`, an orthogonal key
([Identity and caching](identity-and-caching.md), *Load-bearing vs orthogonal
keys*). Two transformations that differ only in their conda environment or
their image have the same checksum.

- **A result that is cached is returned whatever the environment says.**
  Nothing is launched, and none of the checks on this page run.
- **A tag that moves still gets a cache hit.** `ubuntu:22.04` rebuilt upstream
  changes nothing for a transformation that already has a result. Seamless
  does not police mutable tags. For work that must be reproducible, name the
  image by digest: `name@sha256:…`.
- **The container runtimes share one cache.** A result computed under docker
  is a cache hit for the same transformation on an apptainer host.
- **Fingertipping runs the environment where the buffer is wanted.** A
  fingertip is never dispatched
  ([Scratch, witness, audit](scratch-witness-audit.md), *Fingertipping*). The
  machine that asks needs the conda environment, or a container runtime and
  the image. What the tag points to there decides what is recomputed.
- **Two submissions of one transformation with different environments latch on
  to each other**, unless `strict_dunder` is used
  ([Identity and caching](identity-and-caching.md), *Concurrent submissions of
  the same checksum*).

## The image spec

`set_docker` takes a mapping. `seamless-run --docker` sets `name` only.

| Key | Type | Meaning |
|---|---|---|
| `name` | str, required | A Docker image reference. A digest reference is allowed |
| `gpus` | bool, default false | Give the container access to the host's NVIDIA GPUs |
| `shm_size` | str, such as `"1g"` | Size of `/dev/shm`. Ignored under apptainer |

Every other key is an error, when the spec is set and again before launch.
For three legacy keys the message names the replacement:

- `options`: use `gpus` and `shm_size`;
- `version`, `checksum`: use `name@sha256:<digest>`.

`gpus` gives access to GPUs on the machine where the job runs, and it needs
the runtime's NVIDIA support there. It does not send the job to a machine that
has a GPU. That is done by choosing the stage
([Execution backends](execution-backends.md)).

## The runtime is chosen where the job runs

A Docker image can be run by three container runtimes: **docker**, **podman**
and **apptainer**. Which one runs a job is a property of the executing host,
never of the transformation.

| Setting on the executing host | Values | Default |
|---|---|---|
| `SEAMLESS_CONTAINER_RUNTIME` | `docker`, `podman`, `apptainer`, `none` | the first that works, in that order |
| `SEAMLESS_CONTAINER_PULL` | `never`, `missing` | `never` |
| `SEAMLESS_APPTAINER_DIR` | a directory of SIF files | none |
| `SEAMLESS_CONTAINER_ARGS` | extra arguments for the runtime's run command | none |
| `SEAMLESS_CONDA_EXE` | the conda launcher: `conda`, `mamba` or `micromamba`, or a path to one | `$CONDA_EXE`, else `$CONDA_ROOT/bin/conda`, else `conda` on `PATH` |

- **Without the setting, the runtime is detected.** docker is taken when its
  daemon answers, else podman, else apptainer. A process detects once and
  keeps the answer.
- **`none` refuses container jobs.** An operator uses it on a host that has a
  runtime installed but must not run containers. The failure says that the
  host does not allow them.
- **With no working runtime the job fails.** The failure names the image, the
  host and the runtimes that were tried.
- **The runtime is chosen before the job directory is written.** A host that
  cannot run a container job refuses it in the same way on every backend.
- **By default nothing is pulled.** An image that is not present on the
  executing host is a failure. With `missing`, the runtime fetches it.
- **apptainer looks for `<SEAMLESS_APPTAINER_DIR>/<name>.sif`**, with the image
  name used literally: `ubuntu:22.04` is the file `ubuntu:22.04.sif`, and
  `biocontainers/samtools:1.19` is `samtools:1.19.sif` in the subdirectory
  `biocontainers`. When the file is missing, the failure prints the
  `apptainer pull` command that creates it. With `missing`, apptainer runs
  `docker://<name>` from its own cache instead.
- **`SEAMLESS_CONTAINER_ARGS` is the only way to pass further options to the
  runtime**, and it is per host. It is split into words as a shell does. A
  site puts its SELinux label option, a network flag or an extra bind there.
- **A submitter chooses the image and nothing else.** A transformation cannot
  choose mounts, privileges, networks or limits.
- **With no conda launcher the job fails**, and the failure says so.
- **The product that is still called Singularity is not supported.** A
  `singularity` command is not looked for, and the legacy variables
  `SEAMLESS_SINGULARITY_DIR` and `SEAMLESS_DOCKER_DISABLED` and the legacy
  `.simg` files are not read.

Where the settings are read, per backend:

| Backend | Executing host | Settings come from |
|---|---|---|
| `process`, `spawn` | the submitting machine | the environment of the submitting process |
| `remote: jobserver` | the jobserver host | the environment the jobserver was started in |
| `remote: daskserver` | the Dask worker nodes | the queue's `job_script_prologue` |

**What a shared executing host exposes.** Whoever can submit a bash
transformation to it can run any image that is present there, with GPUs if the
spec asks for them, and that image can read the read-buffer directories. This
adds little to a plain bash transformation, which already runs arbitrary code
as the user of that host. With the pull policy `never`, the operator decides
which images are present. `SEAMLESS_CONTAINER_RUNTIME=none` switches
containers off.

## Required binaries

`tf.environment.set_which([...])` lists binaries that must exist.

- **For a bash transformation they are looked up where the script runs**:
  after conda activation, or inside the image. A binary that exists only in
  the environment satisfies the check, and one that exists only on the host
  does not.
- **For every other language they are looked up on the `PATH` of the process
  that runs the code.**
- **A record probe that carries a conda environment or an image does not check
  them.** The probe runs on the host, where a binary of the environment need
  not exist.

## Failures

Each of the following is a failure of the transformation, and failures are not
cached.

**Before anything is launched**, a job is refused when:

- its spec is invalid: an unknown key in the image spec, a conda environment
  together with an image, or an environment on a transformer that is not bash;
- the executing host cannot run it: `SEAMLESS_CONTAINER_RUNTIME=none`, no
  working runtime, no conda launcher, or a Docker daemon that is not local
  (*Current limitations*).

**After the launched process has exited**, the outcome is classified in this
order:

1. **The environment was not entered.** The script did not start: the conda
   environment does not exist, the image is absent, or the image has no
   `bash`. The failure names the environment (the conda environment, or the
   runtime and the image), the exit code and the command that was run. What
   the launcher printed is in the stdout and stderr trailers.
   - Docker reported 125 for a runtime error, such as an absent image under
     the pull policy `never`, and 127 when its init process could not find
     `bash` in the image. Podman 4.9.3 reported 125 for a runtime error and 1
     when catatonit could not exec `bash`; its stderr identifies that case.
     The start marker distinguishes it from a script that itself exits 1.
     Preserve the runtime's exit code rather than treating 1 alone as proof
     that the environment was not entered.
   - apptainer exits 255 in both cases. Only its stderr tells them apart.
   - This class is what separates a missing conda environment, for which
     `conda run` exits 1, from a script that exits 1.
   - Without an environment, this class means that the script itself could not
     be started.
2. **A required binary is missing** where the script runs. The text is
   `Required environment binaries are unavailable: …`, followed by where they
   were looked for.
3. **The script exits with a non-zero code.** This is the *Bash transformer
   exception* report ([Transformation logs](transformation-logs.md), *The
   failure text*), with one more line that names the environment. For a
   container, exit code 137 adds a hint that the job was killed, possibly for
   exceeding a memory limit.
4. **`RESULT` is missing or empty**, as for a plain bash transformation.

After a failing script, `conda run` adds a line of its own to stderr. It is
part of the captured stderr.

## The job directory on disk

Seamless materializes a job directory for every bash transformation and runs
`bash transform.sh` in it. `seamless-run --dry --write-remote-job DIR` writes
that directory without running it
([seamless-run and argtyping](seamless-run-and-argtyping.md)).

- **`bash transform.sh` is the way to run it, with or without an environment.**
  What is written is what Seamless itself would have run.
- **Without an environment, `transform.sh` is the script.**
- **With an environment, `transform.sh` is a launcher** of one command, and the
  script is `transform-inner.sh` next to it. The launcher enters the conda
  environment or starts the container, and runs the script there.
- **The script sets every pin variable itself.** It does not rely on the
  environment variables of the process that wrote it.
- **The script is run as a file.** Its length is not limited by the size of a
  command-line argument, `$0` is its file name, and bash's own error messages
  start with `transform.sh: line N:` or `transform-inner.sh: line N:`.
- **The directory can be moved.** The launcher refers to the directory it is
  run from.
- **A container launcher names the runtime of the host that wrote the
  directory.** It is plain text and can be edited for another site.
- **File names that start with `.seamless-` are reserved** in a job directory.
  Seamless's part of the script writes two of them: `.seamless-started` when
  the script starts, and `.seamless-missing` when a required binary is absent.
  User code does not create or remove such files.

## The first word of a `seamless-run` command

Without an environment, `seamless-run` looks the first word of a command up on
the submitting machine's `PATH`, and uploads the program when it is found
outside the standard tool directories
([seamless-run and argtyping](seamless-run-and-argtyping.md), *The first word
of a command*). With `--conda` or `--docker`:

- **`seamless-run` does not look.** The first word is the name of a tool in
  the environment, even when the submitting machine has a tool of that name.
- **A local file is still uploaded.** `seamless-run --docker IMAGE ./analyze.sh
  data.txt` uploads `analyze.sh`, as it uploads `data.txt`, and runs it inside
  the image.
- A personal tool that is on the submitting machine's `PATH` must be given by
  its path to be uploaded.

## The process lock, nesting and cancellation

**A job with an environment is a bash body.** It takes the process lock of the
process that runs it, like any other body, and holds it until the script ends
([Execution backends](execution-backends.md), *The process lock*). A long
container job occupies its process for that time. `process_lock` false, or
`seamless-run --no-process-lock`, lets it run next to others.

- **Under a conda environment, nested work is signalled as for plain bash.**
  A `seamless-run` that the script starts tells the body, and the body gives
  the lock up ([Execution backends](execution-backends.md), *Bash bodies*).
- **Inside a container it is not.** The signal does not cross the container
  boundary. A containerized script that submits nested work must be declared a
  driver, or have `process_lock` false.

**A cancel that stops the run ends the environment too**
([Cancellation](cancellation.md), *A bash run that is cancelled*).

- **The script is killed, with the processes it started.** Under a conda
  environment that includes `conda run`.
- **A container is removed.** It does not keep running after its job was
  cancelled.
- **There is no grace period.** The script is not given time to clean up.
- **Hard cancellation tears down the environment in `process`, `spawn` and
  `remote: jobserver`.** It also did so in `remote: daskserver` in the measured
  local harness; see [Cancellation](cancellation.md), *A bash run that is
  cancelled*. A softcancel never stops a Dask run.
- **A docker or podman container that Seamless starts carries the label
  `seamless.tf=<tf_checksum>`** for as long as it exists.
  `docker ps --filter label=seamless.tf=<tf_checksum>` lists the container of a
  running job, and nothing once the job has ended or was cancelled.

## Current limitations

- **A bound node's environment cannot be changed.** It is set on the
  Transformer before binding.
- **The execution record does not say which image ran.** It identifies the
  spec text, and a probe looks the image name up when the probe runs
  ([Execution records](execution-records.md)). A moved tag is not visible in
  it afterwards. The record's `environment` bucket describes the process that
  ran the job, not the conda environment or the image of the script.
- **A remote Docker daemon is not supported.** A job fails before launch when
  `DOCKER_HOST` or `CONTAINER_HOST` names anything but a local `unix://`
  socket.
- **The daemon must see the job directory at the path Seamless sees it.** A
  Seamless process that itself runs in a container and uses the host's daemon
  works only when those paths are shared. Otherwise the environment is not
  entered, and the failure says what to suspect.
- **Under docker and podman, a path that contains a comma cannot be mounted.**
  A job whose job directory or read-buffer directory has such a path is
  refused with a message.
- **docker and podman need their init helper on the executing host.** Without
  it the container does not start.
- **apptainer must be able to create mount points inside the image**, which is
  its default. A site that has disabled this cannot run container jobs under
  apptainer.
- **Nested Seamless commands inside a container** need Seamless in the image
  and a route to the services. Neither is provided.

## Non-goals

- Running Python or compiled transformers in a container or in another conda
  environment.
- Creating a conda environment from a specification. `set_conda` stores one,
  and execution does not act on it.
- Building images, or converting them to SIF files.
- Per-transformation container options beyond the image spec, and a
  per-transformation choice of runtime.
- An allowlist of images.
