## Languages, backends, environments and the process lock

Contracts (in `seamless/docs/agent/contracts/`): `handler-languages.md`, `language-backends.md`, `environments.md`, `compiled-transformers.md`, `compiled-pins.md`, `execution-backends.md`, `transformers.md`.

### Which language on which face

| Language | Python face | Unix face | Workflow face |
|---|---|---|---|
| Python | `direct`, `delayed`, `Transformer("python")` | - | `ctx.tf = func` |
| bash | `Transformer("bash")` | `seamless-run` | `ctx.tf = Transformer("bash")` |
| R, Julia (handler languages) | `Transformer("r")`, `Transformer("julia")` | none (`seamless-run Rscript x.R` is a bash command) | `ctx.tf = Transformer("r")` |
| C, C++, Fortran, Rust | `Transformer("c", compiled=True)` | - | bound like any builder |

`seamless_transformer.languages.available_languages()` lists every accepted language and its kind (`native`, `compiled`, `handler`). `register_language_handler` adds a handler language; it must be registered wherever a graph using it is loaded.

### R and Julia

```python
from seamless.transformer import Transformer

tf = Transformer("r", direct=True)
tf.code = "result <- a + b"
tf.pins.a = 2
tf.pins.b = 3
tf()   # 5
```

- Code is source text; pins are declared through `tf.pins` (default celltype `mixed`); the output is `result`.
- No optional pins. R and Julia code cannot resolve checksums; deep pins arrive as the language's checksum classes.
- Backends: `"cli"` (default; an `Rscript` or `julia` process per run) or `"mem"` (embedded via `ryp` / `juliacall`; needs the process lock, so it cannot run as a driver or with `process_lock = False`). Results must agree bit for bit when both backends succeed.
- Known issue: the Julia CLI backend locates `seamless/julia/Project.toml` relative to a source checkout of `seamless-transformer`, so it fails when installed from PyPI. Use `"mem"` or a source install.
- The execution record reports handler languages as `python`; CLI-backend failures are titled "Bash transformer exception".

### Backends (`tf.metavars.BACKEND`)

| Language | values | default |
|---|---|---|
| Python | `"mem"`, `"cli"` | `"mem"` |
| R, Julia | `"cli"`, `"mem"` | `"cli"` |
| bash | none (always a CLI job) | - |
| compiled | none (always in memory) | - |

`BACKEND` is outside identity. The Python CLI backend runs the code in its own process in a job directory, supports no `modules`/`globals`, needs seamless-core inside the job for deep or `checksum` pins, and pays an interpreter start per run.

### Environments

- Surface: `tf.environment.set_conda_env("name")`, `set_docker({"name": "image@sha256:...", "gpus": ..., "shm_size": ...})`, `set_which(["samtools", ...])`; `seamless-run --conda ENV` / `--docker IMAGE`. conda and Docker together are refused at dispatch.
- **Entered** by bash and every CLI backend, on the executing host. The container runtime is chosen there: `SEAMLESS_CONTAINER_RUNTIME` (`docker`, `podman`, `apptainer`, `none`; default first that works), `SEAMLESS_CONTAINER_PULL` (`never`, `missing`), `SEAMLESS_APPTAINER_DIR` (`<image>.sif` files), `SEAMLESS_CONTAINER_ARGS`, `SEAMLESS_CONDA_EXE`.
- **Only asserted** by in-memory backends (default Python, compiled, `"mem"` R/Julia): a conda name must match the worker's own `CONDA_DEFAULT_ENV`/`CONDA_PREFIX`; a Docker image fails the run.
- Never part of identity; a cached result is returned without checking the environment. A job never falls back to the plain host. Seamless does not build environments or images.
- `set_which` binaries are checked where the code runs.
- On a bound workflow node the environment is read-only: set it on the builder before assigning it into the Context.

### Process lock and drivers

| `process_lock` | `driver` | Meaning |
|---|---|---|
| true | false | default: one body per process; the lock is given up at the first nested submission |
| false | true | declared driver: never takes the lock |
| false | false | opt-out for code safe next to other code (I/O-bound) |
| true | true | invalid |

Setting `driver = True` sets `process_lock = False`. CLI: `--driver`, `--no-process-lock` (neither on `seamless-run-transformation`). A nested `seamless-run` inside a bash step releases the outer lock automatically. Neither setting changes the `tf_checksum`.

Bodies at once: `process` 1; `spawn` or jobserver with N workers: N (up to 3N with the lock off); Dask: one per Seamless worker process. A hung body blocks its whole process.

### Logs and streaming

- `tr.logs` (Python), `ctx.tf.logs` (workflow): stdout and stderr of the run plus an execution-time block; the `.exception` text after a failure; `None` after a cache hit. In-memory per process, never persisted. Output written straight to file descriptors 1 and 2 is not captured.
- `tf.streaming = True` / `--streaming`: live output and tqdm bars, Dask only; never changes identity; cached runs stream nothing.
