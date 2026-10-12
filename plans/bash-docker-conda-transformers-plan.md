# Bash-docker-conda transformers: implementation plan

Written 2026-10-11. Paths are relative to `/home/agent/seamless1`; legacy paths
are relative to `/home/agent/legacy-seamless` and prefixed `legacy:`.

**This plan is implemented after
[process-lock-implementation-plan.md](process-lock-implementation-plan.md).**
Line numbers are those of the working trees on 2026-10-11, before that plan,
and will have moved. §3.8 lists what that plan changes underneath this one.

Every decision in this plan is ruled. §0 ends with the list; §8 gives each
ruling with its reason.

## 0. Summary

A bash transformation is executed by materializing a job directory and running
a script in it. This plan keeps that and turns the environment into a
**wrapper around the script**. One code path serves every case:

| `environment` has | The job directory is entered with |
|---|---|
| nothing | `bash transform.sh` |
| `conda_environment` | `conda run -n ENV --no-capture-output bash …` |
| `docker` | `docker run … IMAGE bash …`, or the `podman` or `apptainer` equivalent, chosen on the executing host |
| both | rejected: pick one, or activate the conda environment in the script (D2) |

Three runtimes: `docker` and `podman` (same flags; a daemon or `conmon` owns
the container), and `apptainer` (no daemon, a SIF file per image). Apptainer is
what Singularity was renamed to. The product that is still called Singularity
is not supported, and no `singularity` binary is looked for (author,
2026-10-11).

**Relation to `docker-singularity-bash-transformers-porting-plan.md`
(2026-10-10, unruled).** This plan replaces that plan's design. The differences:

- conda becomes a wrapper too (`conda run`), where the old plan left conda
  activation in the script header;
- the wrapper is written into the job directory as the launcher, so
  `--write-remote-job` gets environments without a second mechanism;
- run-time image capture in records (D14) and a writable environment on a
  bound Context node (§10) are left to later changes.

The old plan's code facts were re-checked where this plan uses them. Two are
out of date: the selectors-based output reader has landed
([execute_bash.py:249-286](../../seamless-transformer/seamless_transformer/execute_bash.py#L249-L286)), and this machine now has a `docker` CLI (§3.6).

### What is ruled

All by the author, on 2026-10-11.

- **R1 — Wrappers.** A bash transformation with an environment is the same
  script, wrapped in `conda run` or in a container runtime's run command.
- **R2 — The command line, not an SDK.** Containers are started through the
  runtime's CLI. The Docker SDK is not used.
- **R3 — Runtimes.** `docker`, `podman` and `apptainer`. No `singularity`.
- **R4 — Real runtimes.** The three are assumed to be installed and working
  when this plan is implemented, and it is tested against them.
- **R5 — `powers` is removed** from the code base as part of this plan.
- **R6 — Order.** The process-lock plan is implemented first.

The design decisions, in one line each (§8 has the reasons):

| | Ruling |
|---|---|
| D1 | conda is entered with `conda run`; `SEAMLESS_CONDA_EXE` may name `mamba` or `micromamba` |
| D2 | `docker` together with `conda_environment` is rejected |
| D3 | `transform.sh` stays the entry point and becomes a launcher when there is an environment |
| D4 | the runtime is chosen on the executing host: a setting, else detection |
| D5 | the image spec is closed: `name`, `gpus`, `shm_size` |
| D6 | the job runs as the host user |
| D7 | no pull by default; SIF files come from `$SEAMLESS_APPTAINER_DIR` |
| D8 | the job directory is mounted at `/seamless-job` |
| D9 | `docker` or `conda_environment` on a Python or compiled transformer is an error |
| D10 | `which` for bash is checked inside the environment |
| D11 | under `--docker` or `--conda`, `seamless-run` does not look the first word up on the host `PATH` |
| D13 | the image is not part of the transformation identity |
| D14 | recording which image ran is a later change |

D12 was closed by R6 and D15 by R5.

## 1. Scope

**In**

- Bash transformers on all three faces: `Transformer("bash")`,
  `seamless-run --docker/--conda`, and a bash node in a workflow Context.
- All backends: `process`, `spawn`, `remote: jobserver`, `remote: daskserver`.
- `docker`, `podman`, `apptainer`; named conda environments.
- Removing the unused `powers` API (R5).

**Out**

- Python and compiled transformers in a container or a conda environment. They
  run inside the worker process and cannot be wrapped. `docker` or
  `conda_environment` on such a transformer is an error (D9).
- Creating conda environments from a spec (`Environment.set_conda`). Legacy
  never did this either (`check_conda_power` always returned False).
- Building or converting images. Seamless uses images that exist.
- A remote Docker daemon, and Seamless itself running inside a container while
  using the host's daemon (§4.5).

## 2. Legacy behaviour

Read in `legacy-seamless` (v0.14) by a subagent. Rows marked ✓ were
checked against the source afterwards; the rest are as reported.

### 2.1 Docker

| Legacy | Where (legacy:) | Here |
|---|---|---|
| ✓ Docker Python SDK: `docker.from_env().containers.create(image, cmd, **options)`, then `start`, `logs(stream=True)`, `wait` | `seamless/workflow/graphs/bashdocker_transformer/executor.py:333-365` | CLI (R2) |
| ✓ Job directory (mode 0700) bound read-write at `/run`, which is also the working directory; read folders bound read-only at their own path | `executor.py:336-342` | Ported; mount point is D8 |
| ✓ Script written as `DOCKER-COMMAND` with `set -u -e` and `trap 'chmod -R 777 /run' EXIT`; the kill-jobs trap deliberately left out ("gives serious problems") | `executor.py:343-350` | `set -u -e` kept, kill-jobs trap left out in containers, chmod trap replaced by user mapping (D6) |
| ✓ Runs as the image's user; a UID-readability check exits 126 | `executor.py:352-359` | D6 |
| ✓ `options.update(docker_options)` after volumes and environment are set, so a user `volumes` key replaces the job mount | `executor.py:351` | Closed schema (D5) |
| Pins passed as container environment variables | `executor.py:273-321` | Pins are exported by the script instead (§4.2) |
| No `entrypoint` override: an image ENTRYPOINT receives the command as arguments | report A5 | `--entrypoint ""` |
| No image pull ("unlike `docker run`, Seamless does not pull any Docker images for you") | `sphinx/source/transformer.md:162` | D7 |
| Container unnamed, not `--rm`; a SIGTERM handler in the executor stops and removes it; the parent waits 15 s | `executor.py:47-67`; `workflow/core/transformation.py:41-58` | §4.8 |
| Single-file `RESULT` first tried as a tar archive (docker mode only) | `executor.py:467-477` | Dropped. It is a leftover from 2019, when the result travelled on stdout as a tar archive, and it misreads a genuine tar result |
| ✓ Docker is used only if the image name differs from `$DOCKER_IMAGE` (default `rpbs/seamless`, even outside a container) and the local conda spec is not satisfied | `seamless/util/environment.py:8, 57-74`; `workflow/midlevel/translate_bash_transformer.py:20-25` | Dropped: the wrapper applies whenever `docker` is set |
| `version` and `checksum` keys: accepted, "Not implemented" | `util/environment.py:67-68` | Rejected (D5) |
| Identity: on the workflow face the image name and options were checksummed pins; on the command-line face they were in `__env__`, outside the checksum | `translate_bashdocker_transformer.py:53-55`; `util/transformation.py:7-27`; `workflow/metalevel/unbashify.py:51-103` | §4.9 |
| Docker-in-Docker: a warning only | `executor.py:322-332` | §4.5 |

### 2.2 Singularity

Implemented in the same executor. It was a fallback, not a choice. It is
ported to `apptainer` only:

- ✓ **Selection.** Used only when the Docker socket was unusable (or
  `SEAMLESS_DOCKER_DISABLED` was set) and `which singularity` succeeded
  (`executor.py:86-113`; `util/environment.py:11-20, 47-54`).
- ✓ **Image.** `$SEAMLESS_SINGULARITY_DIR/<docker image name>.sif`, then
  `.simg`. The name is used literally, so `rpbs/seamless:0.12` is the file
  `<dir>/rpbs/seamless:0.12.sif`. A miss is an error. No conversion tooling in
  the tree.
- ✓ **Command** (`executor.py:168-192`):

  ```
  singularity exec --containall --no-init --no-umask --no-eval \
    --env-file __env__ --bind $(pwd):/run <sif> bash -c 'cd /run; bash ./__BASHCODE__'
  ```

- **Defects**, all fixed by the design in §4:
  - `set -u -e` ran on the host command line, not inside the container;
  - the host shell ran with only the pin variables, so no `PATH`;
  - read folders were not bound, so FILESYSTEM pins dangled;
  - `docker_options` was ignored (no GPU);
  - the SIGTERM handler referenced an undefined `container`.
- No mention of Apptainer anywhere.

### 2.3 Podman

None. No occurrence of `podman` in the tree.

### 2.4 Conda

- ✓ Bash only, and not in docker mode: the script header got
  `source $CONDA_ROOT/etc/profile.d/conda.sh` and `conda activate <name>`
  (`seamless/workflow/graphs/bash_transformer/executor.py:110-118`). With
  `CONDA_ROOT` unset it wrote `source None/etc/…`. There was no `conda run`.
- conda and docker were never combined. In docker mode the conda environment
  name stayed in `__env__` and was not activated.
- `which` was validated on the host even for docker transformers, so a legacy
  test clears it before switching to an image (`tests/workflow/pin-filesystem.py`).

### 2.5 Legacy tests worth porting

`tests/workflow/docker_.py`, `docker2.py`, `docker_gpu.py`,
`docker-singularity.py`, `docker-kill.py`,
`tests/workflow-core/transformation-raw-bashdocker.py`,
`tests/cmd/cowsay-docker.sh`, `tests/cmd/cowsay-conda.sh`.

## 3. Current code facts

Read on 2026-10-11. "(run)" marks a fact confirmed by running it here.

### 3.1 Declaration and transport

- `Environment.set_docker` accepts any dict with a `"name"` key, and
  `set_conda_env` any string
  ([environment.py](../../seamless-transformer/seamless_transformer/environment.py)). `_to_lowlevel` emits `docker` and
  `conda_environment`.
- `seamless-run` has `--docker IMAGE` and `--conda ENV`
  ([main.py:433-444](../../seamless-transformer/seamless_transformer/cmd/api/main.py#L433-L444), 899-907).
- The environment travels as `__env__`, the checksum of the lowlevel dict. It
  is an orthogonal key: outside the transformation checksum
  ([transformation_utils.py:21](../../seamless-transformer/seamless_transformer/transformation_utils.py#L21); `contracts/identity-and-caching.md`, which
  uses the conda environment name as its example).
- Context: binding copies the environment into the node config
  ([context.py:838](../../seamless-workflow/seamless_workflow/context.py#L838)) and the runtime passes it on
  ([runtime_api.py:220](../../seamless-workflow/seamless_workflow/runtime_api.py#L220)). On a bound node the property is a read-only
  dict copy ([builder_state.py:1015](../../seamless-workflow/seamless_workflow/builder_state.py#L1015)).

### 3.2 Execution

- Every face and backend reaches `run_transformation_dict` on the host that
  executes the job ([run.py:85](../../seamless-transformer/seamless_transformer/run.py#L85)). It resolves `__env__` into `env_dict`.
- `which` is checked there, on the host `PATH`, for every language
  ([run.py:142](../../seamless-transformer/seamless_transformer/run.py#L142)). For a conda bash job this happens before activation, so a
  binary that exists only in the named environment fails the check.
- The bash branch reads only `conda_environment` ([run.py:197-217](../../seamless-transformer/seamless_transformer/run.py#L197-L217)). **Nothing
  reads `docker`**: a bash transformer with a Docker image runs on the host,
  silently.
- `write_bash_job` ([execute_bash.py:52](../../seamless-transformer/seamless_transformer/execute_bash.py#L52)) materializes pins in the current
  directory (in an explicit `directory` after the process-lock plan) and
  writes `transform.sh`:
  - FILESYSTEM pins are symlinks to **host paths** inside a read folder (line
    84), and the pin variable holds that path;
  - the header is `set -u -e` plus `trap 'jobs -p | xargs -r kill' EXIT`
    (132-134);
  - with a conda environment the header continues with
    `source <conda root>/etc/profile.d/conda.sh` and `conda activate`, the root
    coming from `$CONDA_ROOT` or `conda info --base` **on the materializing
    host** (135-157);
  - `transform.sh` exports only the pin variables whose value differs from the
    current process environment (163).
- `execute_bash` ([execute_bash.py:176](../../seamless-transformer/seamless_transformer/execute_bash.py#L176)):
  - takes `global_lock` and `chdir`s the process into a fresh temporary
    directory (223-227). The process-lock plan removes both (§3.8);
  - **does not run `transform.sh`**. It runs the header-plus-code string with
    `bash -c` and `env=` (237-245), in a new session;
  - installs its SIGTERM handler only on the main thread (229);
  - reads `RESULT` as a file or a directory.
- `write_remote_job` materializes the same directory and stops
  ([run.py:198-207](../../seamless-transformer/seamless_transformer/run.py#L198-L207), 282). The contract calls `transform.sh` "inspectable and
  runnable by the user" (`contracts/seamless-run-and-argtyping.md:88`), and
  `tests/cmd/test_write_remote_job.py:165` runs `bash transform.sh` by hand.
- Read folders: `_get_read_folder_directories()`
  ([transformation_namespace.py:38](../../seamless-transformer/seamless_transformer/transformation_namespace.py#L38)).

### 3.3 Cancellation

- A hard cancel restarts the worker child: SIGTERM, 2 s, SIGKILL
  ([worker.py:1884](../../seamless-transformer/seamless_transformer/worker.py#L1884); [manager.py:198-199](../../seamless-transformer/seamless_transformer/process/manager.py#L198-L199)).
- Worker children install no signal handler (no `signal.signal` in
  `worker.py` or `process/*.py`). The bash process is in its own session.
  When the child is terminated, the bash process group survives (inferred
  from the code; not run).

### 3.4 `conda run` on this machine (run, conda 26.3.2)

| | Wall time for a no-op job |
|---|---|
| `source conda.sh; conda activate E` (today) | 0.46 s |
| `conda run -n E --no-capture-output bash -c true` | 1.8 s |
| `mamba run -n E bash -c true` (mamba 2.5.0) | 0.15 s |

- The script's exit code is passed through (7 → 7).
- On a non-zero exit `conda run` adds one line to stderr:
  ``ERROR conda.cli.main_run:execute(148): `conda run bash t.sh` failed. (See above for error)``.
- A missing environment exits 1 with `EnvironmentLocationNotFound` on stderr.
  The exit code alone cannot tell it from a script that exits 1.
- `-p PREFIX` works. Activation scripts (`etc/conda/activate.d`) run, under
  `mamba run` too.
- `conda run` and its children stay in the caller's process group, so
  `killpg` ends all of them.
- `mamba run` rejects `--no-capture-output` (exit 2).

### 3.5 Records

- `_docker_image_digest` runs `docker|podman inspect` at probe time, not at run
  time ([probe_capture.py:758](../../seamless-transformer/seamless_transformer/probe_capture.py#L758)).
- The record probe is a Python transformation that copies the target's
  `__env__` ([probe_capture.py:1341-1351](../../seamless-transformer/seamless_transformer/probe_capture.py#L1341-L1351)), so it passes through the host
  `which` check.

### 3.6 Runtimes on this machine

Today (run): conda works (`~/miniforge3`, environment `seamless1`). `podman`
4.9.3 (rootless) and `apptainer` 1.5.4 are installed and work.
`/usr/bin/singularity` is a link to `apptainer`. The `docker` CLI 29.9.0 is
installed, but `docker info` exits 1 because user `agent` is not in group
`docker`.

**The plan assumes that `docker`, `podman` and `apptainer` are installed and
working when it is implemented** (author, 2026-10-11). The container phases
are developed and tested against the real runtimes (§6).

### 3.7 Checked on podman 4.9.3 and apptainer 1.5.4 (run)

With the image `bash:5.2`, which declares an ENTRYPOINT.

**podman, rootless**

- `--entrypoint ""` bypasses the image's ENTRYPOINT.
- `--mount type=bind,src=…,dst=/seamless-job -w /seamless-job` works. The exit
  code passes through, stdout and stderr stay separate, and the host
  environment is not inherited.
- A missing bind source exits 125 and creates nothing, with `--mount` and
  with `-v`.
- An absent image under `--pull=never` exits 125 ("image not known"). A
  command that is not in the image exits 127.
- User:
  - no flag: root inside; files in the job directory belong to the host user;
  - `--user <uid>:<gid>`: the job directory is not writable ("Permission
    denied");
  - `--userns=keep-id`: the host uid inside, `HOME` is the working directory,
    files belong to the host user.
- `--gpus all` is not in `podman run --help`, yet it is accepted and exits 0.
  On this version it is a silent no-op.
- Teardown of a `sleep` job:

  | | Time until the container is gone |
  |---|---|
  | `rm -f` | 10.3 s: it waits the stop timeout, because bash as PID 1 ignores SIGTERM |
  | `rm -f -t 0` | 0.2 s |
  | with `--init`: `rm -f` | 0.2 s |
  | with `--init`: SIGTERM to the client's process group | 0.3 s |
  | without `--init`: SIGTERM to the client's process group | never; the client does not exit either |

- `/run` in the container holds `.containerenv` and `lock`. With the job
  directory bound at `/run` they are hidden, and nothing is written into the
  job directory.
- `podman image inspect --format '{{.Id}} {{.RepoDigests}}'` gives both.

**apptainer**

- A SIF file with a colon in its name (`bash:5.2.sif`) works as the image
  argument.
- `--containall --pwd /seamless-job --bind JOB:/seamless-job` creates the
  mount point. The exit code passes through, the streams stay separate, the
  uid is the host uid, the host environment is not inherited, and files belong
  to the host user. `--cwd` is the documented spelling; `--pwd` is accepted.
- A read folder bound `:ro` at its own path resolves a symlinked pin and
  refuses writes.
- A missing SIF and a command that is not in the image both exit 255.
- `docker://bash:5.2` works as the image argument of `exec`.
- SIGTERM to the process group ends every process of the job in 0.5 s.

Docker itself was not run (§3.6).

### 3.8 What the process-lock plan changes first

This plan starts from the code as
[process-lock-implementation-plan.md](process-lock-implementation-plan.md)
leaves it. What matters here:

- **No `chdir`.** `write_bash_job` has a keyword-only `directory`.
  `execute_bash` and `_write_remote_bash_job` pass it, the process is started
  with `cwd=` the job directory, and the result is read at
  `<job directory>/RESULT`.
- **`global_lock` is gone.** Every transformation claims a per-process lock by
  default (`process_lock` in `__meta__`). It is taken in
  `run_transformation_dict` around the body; `execute_bash` takes no lock
  itself.
- **One body per process.** A bash job therefore runs one at a time per
  process, wrapped or not. `spawn(N)` and a jobserver with N workers run N at
  once. A transformation with `process_lock` off (`tf.process_lock = False`,
  `seamless-run --no-process-lock`) may overlap with others.
- **The nesting signal.** While a bash body holds the lock, `execute_bash`
  creates a FIFO next to the job directory, puts its path in
  `SEAMLESS_PROCESS_LOCK_NOTIFY` in the child's environment, and watches it
  in its output loop. A nested `seamless-run` writes to it and the parent
  drops its lock. Without a holder the variable is removed from the child's
  environment.
- **Tests.** That plan rewrites `test_contract_bash_output.py` and
  `test_remote_job_paths.py`. The test names and mocks cited below are
  today's.

## 4. Design

### 4.1 One launch path

`execute_bash` runs **`bash transform.sh` in the job directory, in every
mode**. Today it runs a string that it never wrote to disk.

- `transform.sh` exports every pin variable, not only those that differ from
  the materializing process. A container does not inherit that process's
  environment.
- What is written is what runs. `--write-remote-job` hands the user exactly
  the directory that Seamless would have executed.
- A side effect: code longer than 128 KiB works. Today `bash -c <code>` fails
  above that size with "Argument list too long" (run: 140 000 characters), the
  kernel's limit for one argument.
- Visible change for plain bash: `$0` is `transform.sh`, and bash's own error
  messages are prefixed `transform.sh: line N:` instead of
  `/bin/bash: line N:`.

The job directory is explicit and the lock is the process lock (§3.8). For
this plan that means:

- **The child's environment** is the one `execute_bash` prepares: the process
  environment, with `SEAMLESS_PROCESS_LOCK_NOTIFY` set or removed. Pin
  variables no longer travel in it; the script exports them.
- **The output loop is not touched.** The launch changes its command and its
  environment. The FIFO handling stays as the process-lock plan left it.
- **A wrapped job holds the process lock like any other body.** A long
  container job occupies its process. That is the process-lock plan's default,
  and this plan does not change it.

Existing tests call `execute_bash` and `write_bash_job` positionally, so every
parameter this plan adds to them is keyword-only with a default.

No backend code changes. Every backend already runs `run_transformation_dict`
on the executing host and resolves `__env__` there (§3.2).

### 4.2 The job directory with an environment (D3)

Without an environment the directory is as today:

```
JOB/  <pin files>  transform.sh
```

With an environment, `transform.sh` becomes a one-command **launcher** and the
script moves to `transform-inner.sh`:

```
JOB/  <pin files>  transform.sh  transform-inner.sh
```

```bash
#!/bin/bash
# transform.sh, conda
exec /home/me/miniforge3/bin/conda run -n myenv --no-capture-output bash transform-inner.sh
```

```bash
#!/bin/bash
# transform.sh, docker
exec docker run --rm --init --entrypoint "" --pull=never \
  --name seamless-3f9c2a17b4e0 --label seamless.pid=41822 --label seamless.tf=<tf_checksum> \
  --user 1001:1001 \
  --mount type=bind,src="$PWD",dst=/seamless-job -w /seamless-job \
  --env HOME=/seamless-job \
  --mount type=bind,src=/data/buffers,dst=/data/buffers,readonly \
  ubuntu:22.04 bash transform-inner.sh
```

The script (`transform.sh` without an environment, `transform-inner.sh` with
one) is:

```bash
#!/bin/bash
export <pin>=<value>            # every pin variable
: > .seamless-started           # start marker (§4.7)
<`which` check>                 # only if `which` is set (§4.7)
set -u -e
trap 'jobs -p | xargs -r kill' EXIT    # not in a container (§2.1)
<user code>
```

Consequences:

- The launcher is built in Python as an argument list and written with
  `shlex.join`. Tests assert on the list.
- conda activation leaves the script. It no longer runs under `set -u -e`, and
  no conda root is baked into the script.
- `bash transform.sh` stays the one entry point for a `--write-remote-job`
  directory, so the contract sentence and `hpc.md` keep holding, now with a
  container too. The launcher uses `"$PWD"`, so the directory can be moved.
  In that mode the launcher carries the runtime selected on the host that
  materialized the directory, and no `--name`.

### 4.3 The conda wrapper (D1)

```
<conda> run -n <name> --no-capture-output      # `-p <name>` if the name contains "/"
```

- `<conda>` on the host: `$SEAMLESS_CONDA_EXE`, else `$CONDA_EXE`, else
  `$CONDA_ROOT/bin/conda`, else `conda` on `PATH`. None found is a failure
  that says so.
- `--no-capture-output` is required: without it `conda run` buffers stdout and
  stderr until exit, which breaks streaming. The flag exists since conda 4.9
  (from memory, not checked).
- If the launcher's basename is `mamba` or `micromamba`, the flag is left out
  (§3.4).
- Cost and noise are in §3.4: about 1.3 s more per job than today with
  `conda`, and one extra stderr line on failure. The line is left in the log.

### 4.4 Container spec and runtime selection (D4, D5, D7)

**Spec.** `environment.docker` keeps its name for every runtime, because a
Docker image reference is the portable identifier.

| Key | Type | docker, podman | apptainer |
|---|---|---|---|
| `name` | str, required | image reference; `@sha256:` allowed | SIF lookup (§4.6) |
| `gpus` | bool, default false | docker `--gpus all`; podman `--device nvidia.com/gpu=all` | `--nv` |
| `shm_size` | str such as `"1g"` | `--shm-size` | accepted, no flag |

Anything else is rejected with a message, at `set_docker` and again before
launch (the Unix face and raw dicts build `__env__` elsewhere):

- `options` (legacy Docker-SDK kwargs): the message names `shm_size` and
  `gpus` as the replacements;
- `version`, `checksum`: the message says to use `name@sha256:<digest>`;
- any unknown key.

**`docker` together with `conda_environment` is rejected** (D2): in
`seamless-run` argument parsing, when a bash Transformer is frozen, and again
before launch. The message says to pick one, or to activate the conda
environment in the script itself.

**Selection** is a property of the executing host, never of the transformation:

- `SEAMLESS_CONTAINER_RUNTIME=docker|podman|apptainer|none`. With `none` an
  operator refuses container jobs on a host that has a runtime installed; the
  failure says that this host does not allow them;
- unset: the first usable of `docker` (`docker info` exits 0), `podman`,
  `apptainer`. The result is cached per process;
- none usable: the job fails, naming the image, the host and what was tried.
  It never falls back to the host;
- selection happens before the job directory is written, so a refusal looks
  the same on every backend.

Two more host settings:

- `SEAMLESS_CONTAINER_PULL=never|missing`, default `never` (D7);
- `SEAMLESS_CONTAINER_ARGS`: extra arguments, split with `shlex`, placed just
  before the image. This is where a site puts `--security-opt label=disable`,
  a network flag or an extra bind.

Where the settings come from per backend:

| Backend | Executing host | Settings come from |
|---|---|---|
| `process`, `spawn` | the caller's machine | the caller's environment |
| `remote: jobserver` | the jobserver host | the jobserver's launch environment. `clusters.yaml` has no field for it, so in practice the activation scripts of the jobserver's conda environment |
| `remote: daskserver` | the Dask worker nodes | the queue's `job_script_prologue` ([cluster.py:103](../../seamless-config/seamless_config/cluster.py#L103)), for example `module load apptainer` and the two `export`s |

### 4.5 The docker and podman wrapper

```
<docker|podman> run --rm --init --entrypoint "" --pull=<never|missing>
    --name seamless-<12 hex> --label seamless.pid=<pid> --label seamless.tf=<tf_checksum>
    <user flags (D6)>
    --mount type=bind,src="$PWD",dst=<mnt> -w <mnt>
    --mount type=bind,src=<read folder>,dst=<read folder>,readonly   # once per read folder
    [<gpu flag>] [--shm-size N] [SEAMLESS_CONTAINER_ARGS]
    <image>  bash transform-inner.sh
```

- **`--entrypoint ""`** makes the arguments the command, whatever the image
  declares. Legacy did not do this.
- **`--mount`, not `-v`.** With `-v`, docker creates a missing source
  directory on the daemon's host, owned by root. `--mount` fails instead
  (Docker documentation; not run here). A path that contains a comma cannot
  be written in `--mount` syntax and is rejected with a message.
- **Mount point** `<mnt>` is fixed (D8). A fixed path makes `$PWD` the same on
  every run, which matters for tools that write their working directory into
  their output.
- **Read folders** are bound read-only at their own path, so FILESYSTEM
  symlinks and path variables resolve. Legacy did the same.
- **User** (D6): the job runs as the host user, so `RESULT` is readable and
  the directory deletable.
  - rootful docker or podman: `--user <uid>:<gid>`;
  - rootless podman: `--userns=keep-id`. The uid inside is then the host uid,
    as on the other runtimes. `--user` must not be given there: the job
    directory is then not writable (§3.7);
  - rootless docker: no flag. Root in the container is the host user (from
    memory; docker has no `keep-id`).

  One `info` call per process decides which case applies.
- **`HOME=/seamless-job`** for docker and podman. On this host rootful Docker
  leaves `HOME=/` when `--user` names a uid without a passwd entry; that path
  is not writable. The job directory is writable, and rootless podman with
  `--userns=keep-id` already uses it as `HOME`. Apptainer will use the same
  value in Phase 4.
- **`--init`.** Without it bash is PID 1 and ignores SIGTERM: a signal to the
  client then does nothing, and `podman rm -f` waits 10 s (§3.7). With it, the
  process-group kill that ends every other kind of job also ends the
  container. `--init` needs the runtime's init binary on the host; without
  one the launch fails.
- **GPU.** docker: `--gpus all`. podman: `--device nvidia.com/gpu=all` (CDI;
  from memory), because podman 4.9.3 silently ignores `--gpus` (§3.7).
- **The image must contain `bash`.**
- **Not supported:** a remote daemon. `DOCKER_HOST` or `CONTAINER_HOST` that is
  not a local `unix://` socket fails before launch. If Seamless itself runs in
  a container and talks to the host daemon, the daemon cannot see the job
  directory. `--mount` then fails with exit 125, and the failure text says
  what to suspect (§4.7). The earlier plan refused this case by detecting that
  Seamless runs in a container; that also refuses a setup where the paths are
  shared with the host, which was the normal legacy deployment.

### 4.6 The apptainer wrapper

```
apptainer exec --containall --cwd <mnt>
    --home "$PWD":<mnt> --bind "$PWD":<mnt>
    --bind <read folder>:<read folder>:ro
    [--nv] [SEAMLESS_CONTAINER_ARGS]
    <sif>  bash transform-inner.sh
```

- **Image** (D7): `$SEAMLESS_APPTAINER_DIR/<name>.sif`, with the name used
  literally, which is the legacy rule. The legacy variable
  `SEAMLESS_SINGULARITY_DIR` and the legacy `.simg` extension are not read.
  - A miss with pull policy `never` fails and prints the exact command:
    `apptainer pull <dir>/<name>.sif docker://<name>`.
  - With `missing`, the image argument is `docker://<name>` and the runtime's
    own cache is used.
- `--containall` is kept from legacy: own PID and IPC namespaces, no host
  environment, no host home. It makes the run comparable to the docker one.
- `--home "$PWD":<mnt>` mounts the job directory as `/seamless-job` and sets
  `HOME` to that path. Apptainer 1.5.4 refuses to override `HOME` with
  `--env`; the explicit bind keeps the job mount in the same form as the
  Docker and Podman launchers.
- Legacy `--no-init --no-umask --no-eval --env-file` are dropped. They served
  the environment file, which the exported pins replace.
- `--cwd` is the documented flag. Older releases call it `--pwd`, which 1.5.4
  still accepts.
- The user is always the host user. `shm_size` has no flag.
- No daemon: the process group is the container, so teardown is `killpg`.

### 4.7 Failures and `which` (D10)

After the process exits, in this order:

1. **`.seamless-started` is missing: the environment was not entered.** The
   failure names the wrapper (conda environment, or runtime and image), the
   exit code and the launcher line. Docker reported 125 for a runtime error
   such as an absent image under `--pull=never`, and 127 when its init process
   could not find `bash` in the image. Podman 4.9.3 reported 125 for a runtime
   error and 1 when catatonit could not exec `bash`; its stderr identifies the
   latter. Do not infer this class from exit 1 alone: a script may also exit 1.
   Apptainer exits 255 for both, so there the reader has only the stderr text.
   The output is in the logs as usual. This is what separates a missing conda environment
   (exit 1) from a script that exits 1.
2. **`.seamless-missing` exists:** "Required environment binaries are
   unavailable: …", the text of [run.py:142](../../seamless-transformer/seamless_transformer/run.py#L142), plus where it was checked.
3. **Non-zero exit:** today's *Bash transformer exception* report, plus one
   line naming the environment. Exit 137 from a container adds a hint: the
   job was killed, possibly for exceeding a memory limit.
4. `RESULT` missing or empty: as today.

**`which` for bash moves into the script.** The prelude runs `command -v` for
each name, writes the missing ones to `.seamless-missing` and exits. The check
therefore sees the `PATH` that the code will see: after conda activation,
inside the image. The host check in `run.py` stays for other languages and is
skipped for bash. It is also skipped for a record probe whose environment has
`docker` or `conda_environment`: the probe is Python on the host and would
fail on binaries that exist only inside the environment.

All of these are transformation failures, and failures are not cached.

### 4.8 Cancellation and cleanup

A container breaks the assumption that killing a process stops the work: the
`docker run` client does not own the container.

There is no grace period: a cancelled job is killed. Legacy gave
`docker stop` 10 s, which a script running as PID 1 could not use.

1. **Registry, keyed by `tf_checksum`.** `run_transformation_dict` passes the
   checksum to `execute_bash`, which registers a cleanup for each running
   launch and always runs it in `finally`:
   - process group kill, for every mode (it exists today);
   - `docker rm -f <name>` or `podman rm -f -t 0 <name>`. Without `-t 0`
     podman waits its stop timeout first (§3.7).
2. **Worker children get a SIGTERM handler**, installed in
   `_child_initializer` ([worker.py:1065](../../seamless-transformer/seamless_transformer/worker.py#L1065)). It runs the registered cleanups and
   exits. `rm -f` is started detached and not waited for, so the handler stays
   well inside the 2 s that `restart_worker` allows. This also ends the
   orphaned host-bash process group of §3.3.
3. **Backstop for SIGKILL.** After `restart_worker` kills a child, remove
   `<runtime> ps -q --filter label=seamless.pid=<pid>`. Only when a docker or
   podman runtime is selected on that host.
4. **In-process.** Both cancel paths, `_softcancel_leaf` and
   `cancel_by_checksum`, already call `worker.cancel_by_checksum`
   ([transformation_cache.py:651](../../seamless-transformer/seamless_transformer/transformation_cache.py#L651), 761). They
   also run the registry's cleanup for that checksum. Without this a cancelled
   `execution: process` container runs to completion and keeps the process
   lock until then. The executor thread itself still cannot be stopped, but
   it returns as soon as its job is gone.
5. **Dask.** Whether a hard cancel reaches the worker child on a Dask worker
   is not known. The phase measures it and records the answer. This is the
   backend that apptainer on a cluster will use.

The first step of the phase is a probe that confirms §3.3 by running it.

### 4.9 Identity (D13)

The image and the conda environment live in `__env__`, which is orthogonal:
they do not change the transformation checksum. This is the current contract
and the legacy command-line behaviour; the legacy workflow face differed
(§2.1). The author confirmed it for images (D13).
Consequences that the contract page must state:

- A tag that moves still gets a cache hit. For reproducible work the docs
  recommend `name@sha256:<digest>`.
- docker and apptainer runs of the same image share cache entries.
- Fingertipping is never dispatched. It recomputes on the machine that wants
  the buffer, with whatever the tag points to there, and needs a runtime and
  the image (or the conda environment) on that machine.
- Two submissions with the same checksum and different images latch on to
  each other, unless `strict_dunder` is used.

### 4.10 Faces

| Face | Work |
|---|---|
| Python | spec validation in `set_docker`; docstrings |
| Unix | `--docker` help text; first-word handling under `--docker` and `--conda` (D11) |
| Context | none. A node bound from a Transformer with an environment already carries it (§3.1) |

### 4.11 Nested work under a wrapper

The nesting signal of §3.8 is an environment variable that holds a host path.

- **conda.** `conda run` passes the environment through, so a nested
  `seamless-run` in a conda-wrapped script signals its parent as in a plain
  bash job.
- **Container.** The variable is not passed in and the FIFO is not visible
  inside. A containerized script cannot signal. The process-lock plan's rule
  applies: a body that nests across a container boundary must be declared
  with `--driver` or `--no-process-lock`. Beyond that, nested Seamless calls
  from inside a container are not supported by this plan (§10).

### 4.12 Transformers that are not bash (D9)

A Python or compiled transformation whose environment has `docker` or
`conda_environment` fails before it runs. The message says that these two keys
apply to bash transformers only.

- It is checked in `run_transformation_dict`, which every face and backend
  reaches, and earlier, when a Python or compiled Transformer is frozen.
- **A record probe is exempt.** It is a Python transformation that carries
  its target's `__env__` (§3.5), so it would otherwise fail for every bash
  job that has an environment.
- `which` is not affected. For these languages it stays a check on the host.

### 4.13 The first word of a `seamless-run` command (D11)

Today `seamless-run` looks the first word of each command up on the
submitting host's `PATH` (`resolve_executable`, [main.py:64](../../seamless-transformer/seamless_transformer/cmd/api/main.py#L64);
`make_executables`, main.py:840-867) and does one of three things (run):

1. Found in a directory that ends in `bin`, `sbin` or `usr`: left as a name.
   The executing side resolves it.
2. Found anywhere else (`/usr/games/cowsay`, `~/tools/mytool`): the file is
   uploaded as an input, the command is rewritten to call the uploaded copy,
   and `chmod +x` is added.
3. Not found: left as a name, but `chmod +x <name>` is still added, for a
   local script named without a path. When no such file exists the job fails
   at the `chmod`. `seamless-run --conda seamless1 dask --version`, with
   `dask` absent from the host `PATH`, ends in "chmod: cannot access 'dask'".

The rule after this plan:

- **Under `--docker` or `--conda` the host `PATH` is not consulted.** The first
  word is uploaded only when it names an existing local file, as any other
  argument is. A local script given as `./analyze.sh` is therefore still
  uploaded and runs inside the environment. A personal tool on the host
  `PATH` must be named by its path.
- **`chmod +x` is added only for words that were uploaded**, with or without
  an environment. The failure of case 3 also hits a tool that exists on the
  cluster and not on the submitting machine.

## 5. Phases

Order: 1 → 2 → 3 → (4 ∥ 5) → 6. Each phase is implemented against the
contract page of §7 and the tests of §6. Run tests in the `seamless1` conda
environment, one pytest process per file.

### Phase 1 — One launch path

- `write_bash_job` exports every pin variable and writes the start marker
  line. `execute_bash` runs `bash transform.sh` (§4.1).
- Failure classification step 1 of §4.7, which for plain bash can only mean
  that the script could not be started.
- **Stopgap:** a transformation whose environment has `docker` fails before
  execution with "container execution is not implemented yet; refusing to run
  on the host". Bash loses this in Phase 3.
- The D9 error in `run_transformation_dict` (§4.12), for `docker` and for
  `conda_environment`, with record probes exempt.
- Existing tests to adapt: the `write_bash_job` mocks in
  `test_contract_bash_output.py` return a code string and write no script.
  `execute_bash` now runs the file, so the mocks must write `transform.sh`.
- **Exit:** every existing bash test file passes
  (`test_bash_transformer.py`, `test_contract_bash_output.py`,
  `test_execute_bash_directory_inputs.py`, `test_bash_pretransformation.py`,
  `test_meta_variables.py`, `test_metafile.py`, `test_remote_job_paths.py`,
  `test_write_remote_job_mode.py`, and `tests/cmd/test_write_remote_job.py`
  where SSH is available), plus `test_bash_launch.py`.

### Phase 2 — conda as a wrapper

- Launcher and `transform-inner.sh` (§4.2); the conda wrapper (§4.3); the
  activation header is removed from `write_bash_job`.
- `which` in the script, the `.seamless-missing` path, and the probe exemption
  (§4.7).
- `write_remote_job` with `--conda` writes the launcher.
- **Exit:** `test_bash_conda.py` passes against the real `seamless1`
  environment in `process` and `spawn` mode.

### Phase 3 — Container spec, runtime selection, docker and podman

- First step: confirm the docker points of §9 on real docker, and correct
  §4.5 where they differ.
- New module `seamless_transformer/container.py`: spec validation, runtime
  selection, the docker-family argument builder.
- `run.py` passes the validated spec to `execute_bash`; the Phase 1 stopgap
  goes away for bash.
- `finally` cleanup with `rm -f` (the registry itself is Phase 5).
- **Exit:** the Phase 3 tests pass against real `docker` and real `podman`,
  run and not skipped. With no usable runtime the job fails and nothing runs
  on the host.

### Phase 4 — apptainer

- The apptainer argument builder and SIF resolution (§4.6).
- **Exit:** `test_container_apptainer.py` passes against real `apptainer`, run
  and not skipped, including SIF lookup, the miss message and the `docker://`
  case.

### Phase 5 — Cancellation and cleanup

- The probe, the registry, the worker-child handler, the backstop and the
  in-process hook (§4.8).
- **Exit:** after a hard cancel of a `sleep` job in `spawn` mode,
  `<runtime> ps --filter label=seamless.tf=<tf_checksum>` is empty for docker
  and for podman, and the process group is gone for apptainer and for plain
  bash, all within 5 s. The same on the jobserver and in `process` mode. The
  Dask behaviour is measured and written into the contract page.

### Phase 6 — Faces and docs

- `seamless-run`: first-word handling (§4.13), help text.
- **Remove `powers` (R5):**
  - in `environment.py`: `_powers` in `_props` and in `__init__`, the two
    lines in `_to_lowlevel`, `set_powers`, `get_powers`, and the two docstring
    lines that describe it;
  - the docstring at `compiled_transformer.py:605`;
  - `tests/test_environment.py:17`, which sets one;
  - both `RELEASE-NOTES.md` files, which list `powers` among the environment
    keys;
  - the generated API page and `docs/agent/index.json`.

  A saved state or an `__env__` that still has the key keeps loading: `_load`
  reads only the known properties, and nothing reads the key from `__env__`.
- The early D9 check when a Python or compiled Transformer is frozen (§4.12).
- The doc changes of §7 other than the contract page.
- **Exit:** `tests/cmd/test_seamless_run_environment.py` passes; no doc says a
  non-bash transformer runs in a container or a conda environment; `powers`
  no longer occurs in `seamless_transformer/` or in the docs.

## 6. Tests

New files go in `seamless-transformer/tests/`.

**Real runtimes.** The container tests run against real `docker`, `podman`
and `apptainer` (§3.6). A test skips when its runtime is absent, but a phase
exits only when its tests ran, not skipped, on every runtime it covers.

- **Images**, pinned by digest and fetched once by a session fixture:
  - one with `bash` (`ubuntu:22.04`);
  - one without (`alpine`);
  - one built by the fixture from the first, with `ENTRYPOINT ["/bin/false"]`.

  The fixture pulls them into docker and into podman, and converts them into
  a temporary `SEAMLESS_APPTAINER_DIR`. It needs the network once.
- Tests that cover both docker and podman are parametrized and set
  `SEAMLESS_CONTAINER_RUNTIME` explicitly.
- **Stubs only for runtime selection.** The detection order and the "nothing
  usable" case need a runtime that is absent or broken. Those tests build a
  `PATH` of stub scripts whose `info` succeeds or fails.
- Launcher arguments are asserted on the generated list, without running it.

| File | Phase | Checks |
|---|---|---|
| `test_bash_launch.py` | 1 | a pin whose value equals a host variable is still exported; code over 128 KiB runs; start marker; stopgap error for bash with `docker`; a Python transformation with `docker` or with `conda_environment` fails, and a record probe that carries either does not; two jobs with `process_lock` off overlap in one process without disturbing each other; a script that writes to `$SEAMLESS_PROCESS_LOCK_NOTIFY` still gets its parent's lock dropped |
| `test_bash_conda.py` | 2 | runs in the named environment (`$CONDA_PREFIX`); stdout arrives while the job runs; exit code passes through; missing environment gives the "not entered" failure; `-p` form; `which` is satisfied by a binary that exists only in the environment; launcher text; `write_remote_job` directory runs with `bash transform.sh`; `SEAMLESS_PROCESS_LOCK_NOTIFY` reaches the script |
| `test_container_spec.py` | 3 | accept and reject table of §4.4, with the messages; `docker` with `conda_environment` is rejected on each face |
| `test_container_selection.py` | 3 | with stubs: explicit setting; detection order; `none` refuses; nothing usable is a failure and the host is untouched; remote `DOCKER_HOST` refused |
| `test_container_docker.py` | 3 | launcher arguments for docker and podman (mount, read folders read-only, user flags, `--entrypoint`, pull policy, `gpus`, `shm_size`, extra args); end to end on both runtimes with string, file, directory and FILESYSTEM pins; `RESULT` file and directory; files in the job directory end up owned by the host user; the ENTRYPOINT image still runs the script; an absent image (exit 125) and the image without bash (Docker exit 127, Podman 4.9.3 exit 1) give their texts; `__env__` supplied through `tf_dunder` on a raw transformation dict; `.logs` holds the job's stdout and stderr separately; `SEAMLESS_PROCESS_LOCK_NOTIFY` does not reach the script |
| `test_container_apptainer.py` | 4 | launcher arguments; SIF resolution, miss message, `docker://` under `missing`; end to end with the same pin and `RESULT` cases, read folders bound read-only |
| `test_container_cancel.py` | 5 | §4.8 exit criteria in `spawn` and `process` |
| `seamless-workflow/tests/test_contract_bash_environment.py` | 2, 3 | a bash node bound from a Transformer with `conda_environment` runs in that environment; the same with `docker`; the environment survives a graph save and load |
| `tests/cmd/test_seamless_run_environment.py` | 6 | `--docker` and `--conda` through the CLI; a tool that exists only in the environment runs; a host tool outside `bin` is not uploaded; a local script given by path is uploaded and runs inside the environment |

Every test that expects a failure or a wrapper uses a fresh nonce pin. The
environment is outside identity, so a cache hit returns the old result and
runs none of the checks.

Three existing files build an `__env__` with `conda_environment` or `docker`
around transformations that are not bash: `test_execution_records.py`,
`test_probe_index.py` and `test_probe_capture.py`. Check them against the D9
error in Phase 1.

The suite itself runs inside `seamless1`. A test that needs a binary to be
absent from the host `PATH` removes the environment's `bin` directory from
`PATH` before it launches the job.

**Legacy ports.** `docker_.py` and `transformation-raw-bashdocker.py` go into
`test_container_docker.py`, `docker-singularity.py` into
`test_container_apptainer.py`, `docker-kill.py` into
`test_container_cancel.py`, and `cowsay-docker.sh` and `cowsay-conda.sh` into
`tests/cmd/test_seamless_run_environment.py`. `docker_gpu.py` is ported with a
skip unless `nvidia-smi` exists.

## 7. Docs

**The contract page is written.** [environments.md](../docs/agent/contracts/environments.md)
is the contract that the phases implement and that their tests are written
from. It is listed in `docs/agent/README.md`; `docs/agent/index.json` is
regenerated in Phase 6. Two of its statements wait for a phase:

- Phase 5 measures the Dask cancel behaviour and replaces the "not specified"
  line under *Current limitations*.
- Phase 3 confirms the docker points of §9. A difference is corrected in the
  page and in §4.5 together.

Other pages:

- `contracts/identity-and-caching.md`: a container example next to the conda
  one.
- `contracts/seamless-run-and-argtyping.md`: `--docker`, `--conda`, the
  launcher in a `--write-remote-job` directory, D11.
- `contracts/execution-backends.md`: the runtime must exist on the executing
  host.
- `contracts/cancellation.md`: container teardown at the leaf.
- `contracts/transformation-logs.md:102`: the bash failure report gains the
  environment line and the "environment not entered" class.
- `contracts/streaming.md:96`: output of a wrapped job streams like host bash.
- `docs/agent/index.json`: register the new contract page.
- `contracts/compiled-transformers.md:209-211` promises conda activation and
  a Docker container for compiled transformers, and
  `docs/main/compiled-transformers.md:145` promises conda activation. Nothing
  implements either.
- `docs/main/hpc.md`: apptainer through `job_script_prologue`.
- Docstrings in `environment.py`, `--docker` help in `main.py`, both
  `RELEASE-NOTES.md` files, and the generated API pages.

## 8. The rulings and their reasons

Ruled by the author on 2026-10-11. D12 and D15 were closed earlier (§0).

**D1 — The conda launcher: `conda run`.** `$SEAMLESS_CONDA_EXE` may name
`mamba` or `micromamba`.
- It needs no conda root, and activation no longer runs under the script's
  `set -u -e`.
- The price is about 1.3 s per job with `conda` (§3.4) and one stderr line on
  failure. A site with many small jobs sets `SEAMLESS_CONDA_EXE=mamba`.

**D2 — `docker` together with `conda_environment`: rejected.**
- The pair has two plausible readings. Legacy treated the two as alternatives
  (§2.1); composing reads them as nested. An error surprises nobody.
- Composing needs a conda launcher inside the image, and images differ: some
  have `conda` on `PATH`, some only `micromamba`, some neither.
- A script that needs an environment inside the image can activate it itself,
  where that is visible and part of the code.

**D3 — Job directory layout: `transform.sh` is always the entry point.** It
becomes a launcher when there is an environment (§4.2), containers included.
- The documented entry point of a `--write-remote-job` directory keeps
  working, and Seamless runs the same file the user would.

**D4 — Runtime selection: on the executing host.** A setting, else detection
in the order docker, podman, apptainer (§4.4). Not a per-transformation key.
- The runtime belongs to the site. A key in `__env__` would travel to sites
  that lack that runtime. Detection keeps a laptop zero-configuration.
- Legacy `SEAMLESS_DOCKER_DISABLED` is not kept; `none` replaces it.

**D5 — Image spec: closed.** `name`, `gpus`, `shm_size`, plus the host-level
`SEAMLESS_CONTAINER_ARGS`. Legacy `options` are rejected.
- `options` are Docker-SDK keywords. They mean nothing to a CLI or to
  apptainer, and in legacy they could replace the job mount.
- On a rootful docker daemon they are a privilege hole: whoever can submit a
  transformation could mount any host path or ask for a privileged container.
  With the closed schema the submitter chooses the image and nothing else.

**D6 — User inside docker and podman: the host user** (§4.5).
- The legacy `chmod -R 777` trap does not run on a kill, and root-owned
  leftovers then leak silently.
- Cost: an image that must run as root or as a named user does not work under
  rootful docker, and `HOME` may not be writable. A `user: "image"` key can be
  added later if that turns out to matter.
- Rootless podman: plain root-in-container also leaves files owned by the
  host user (§3.7). `keep-id` is used so that the uid inside is the same on
  all three runtimes, and because some tools refuse to run as root.

**D7 — Pulling: never by default.** `SEAMLESS_CONTAINER_PULL=missing` opts in.
SIF files come from `$SEAMLESS_APPTAINER_DIR` with the literal naming rule.
- Implicit pulls make a moved tag take effect on some workers and not on
  others, hit registry rate limits, and fail on compute nodes without network.

**D8 — Mount point of the job directory: `/seamless-job`.**
- The host path would put a random temporary name into `$PWD`, which then
  differs per run.
- Against legacy `/run` the difference is small. `/run` hides what the image
  and the runtime keep there (podman: `.containerenv` and `lock`), though
  nothing breaks (§3.7), and it keeps a legacy script that hard-codes `/run`
  working. `/seamless-job` cannot collide with anything, and apptainer creates
  the mount point without trouble (§3.7).

**D9 — `docker` or `conda_environment` on a Python or compiled transformer:
an error** (§4.12). The author extended it to `conda_environment`.
- Today such a result is attributed to an environment that was never used.
- Record probes are exempt, or recording would fail for every bash job that
  has an environment.

**D10 — `which` for bash: checked inside the environment**, by the script
(§4.7).
- The host check fails for a binary that exists only in the conda environment
  or the image, and passes for one that exists only on the host.

**D11 — The first word of a `seamless-run` command** (§4.13). Under `--docker`
or `--conda` the host `PATH` is not consulted, and `chmod +x` is added only
for uploaded words, with or without an environment.
- With an environment flag the user has said where the tools are.
- Today a tool that exists only in the environment fails at the `chmod`.

**D13 — The image is not part of the transformation identity** (§4.9). No
policing of mutable tags either.
- It matches the ruled conda precedent, and docker and apptainer hosts then
  share a cache, which a digest would prevent because a SIF has no Docker
  digest.

**D14 — Recording which image actually ran: a later change.**
- Nothing records it today. The record has the checksum of the spec text and
  a probe-time `inspect` of the name (§3.5). In-process and spawn runs have no
  channel for per-run facts, so the transport has to be designed first.

## 9. Risks and unverified points

- **A wrapped job holds its process for as long as it runs** (§3.8). A site
  that wants several container jobs in one worker process must switch
  `process_lock` off for them.

- **Docker 29.9 was probed on 2026-10-12.** `--mount` failed on a missing
  source with exit 125 and did not create it; `--entrypoint ""` bypassed a
  custom image ENTRYPOINT; `--init` started successfully; and `docker rm -f`
  removed an initialized long-running container in 0.304 s. The daemon is
  rootful, so the rootless Docker no-user-flag case was unavailable here.
- **Rootless Podman 4.9.3 was probed on 2026-10-12.** With `--userns=keep-id`
  and no `--user` flag, the script ran as the host uid/gid, `HOME` was
  `/seamless-job`, and files written in the mounted job directory were owned
  by the host user. With `--init`, an image without `bash` exited 1 and
  catatonit's stderr said `failed to exec pid1: No such file or directory`;
  Docker 29.9 reported 127 for the same image. Preserve the runtime exit code
  and use stderr to recognize this Podman environment-entry failure.
- **No GPU flag was run on any runtime**: `--gpus all`,
  `--device nvidia.com/gpu=all`, `--nv`.
- **`--userns=keep-id` start-up cost** for a large image is not measured. On
  some storage setups podman copies the image for the mapping.
- **`--init` needs an init binary on the host.** It is present here for
  podman. A host without one cannot run container jobs until it is
  installed.
- **SELinux hosts** need a label option on bind mounts. That is what
  `SEAMLESS_CONTAINER_ARGS` is for; the default command does not set one.
- **apptainer needs to create the mount point** `/seamless-job` and the read
  folder paths inside the image. That requires overlay or underlay support,
  which is the default but can be disabled by a site.
- **Apptainer sets `HOME` to `/seamless-job` with `--home`.** On Apptainer
  1.5.4, `--env HOME=...` is rejected; the `--home` mapping also mounts the
  writable job directory at that path.
- **Docker Desktop** shares only some host paths with its VM. Whether the
  temporary directory is among them is unverified; a setting for the job
  directory's parent may be needed.
- **Start-up cost.** `conda run` is measured (§3.4). Container start-up is
  not.
- **Exposure.** Binding read folders shows the whole buffer store, read-only,
  to the image. On a shared jobserver a tenant can run any image that is
  present there, with GPUs if it asks. That adds little to what a plain bash
  transformation already allows, which is arbitrary code as the jobserver
  user. `SEAMLESS_CONTAINER_RUNTIME=none` is the operator's off switch. An
  image allowlist is not in the plan. With pull policy `never` the operator
  already decides which images exist: exactly so for apptainer (the SIF
  directory) and rootless podman (the user's own image store), loosely for a
  docker daemon that other users share.
- **The worker-child SIGTERM handler** must not swallow termination or outlive
  the 2 s grace.

## 10. Noticed, not in this plan

- **The record's environment bucket describes the worker's Python**, not the
  conda environment or the image that the job ran in. Which image ran is not
  recorded either; that is a later change (D14).
- **`gpus: true` does not send the job to a GPU node.** It only adds the GPU
  flag. A Dask task requests one resource, the throttle `S`
  (`seamless-dask/seamless_dask/client.py:1168`); a queue's `dask_resources`
  is never requested per transformation. The caller reaches a GPU queue by
  choosing the stage, as today.
- **Nested `seamless-run` inside a container is not addressed**, here or in the
  earlier plan. A nested client reads state that the worker passes through
  environment variables (for example `SEAMLESS_ALLOW_REMOTE_CLIENTS_IN_WORKER`,
  `seamless-remote/seamless_remote/client.py:87`). A container does not
  inherit them, and the image would need Seamless installed. Under the conda
  wrapper they are inherited. With the process lock there is a second
  obstacle: an undeclared nested call from a container cannot signal its
  parent (§4.11).
- Record memory is `RUSAGE_SELF` (`record_utils.py:18`). It excludes bash
  subprocesses today and will exclude wrapped jobs too.
- **A bound Context node cannot change its environment** (§3.1). The graph
  format already carries the field, so a setter needs no format change, but it
  is a Context contract change.
- `Environment.set_conda` (the YAML spec) is consumed nowhere at execution.
- `execute_bash` drops blank stdout lines ([execute_bash.py:258](../../seamless-transformer/seamless_transformer/execute_bash.py#L258)).
- `seamless-transformer/environment-porting-plan.md` is stale: it says `which`
  is not consumed.
- The contract says a `--write-remote-job` directory is created on the machine
  that runs `seamless-run`; the code creates it on the executing host
  ([run.py:282](../../seamless-transformer/seamless_transformer/run.py#L282), and its own error message says so).
