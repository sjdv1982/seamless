# R and Julia transformers

R and Julia transformers run through Seamless's CLI backend by default. Each
run starts `Rscript` or `julia` in a job directory. Seamless does not install
either runtime or the packages your code needs. Install them on the machine
that runs the job, or in the conda environment or container selected by the
transformer.

This guide sets up a local CLI run from the `seamless1` conda environment.
For the backend and environment rules, see the
[Language backends contract](../agent/contracts/language-backends.md) and the
[Handler languages contract](../agent/contracts/handler-languages.md).

## Install Julia

The [official Julia installer](https://julialang.org/downloads/) recommends
Juliaup. On Linux or macOS, install Juliaup and Julia with:

~~~sh
curl -fsSL https://install.julialang.org | sh
~~~

This repository's tracked Julia manifest was generated with Julia **1.12.6**.
Install that release and make it the default `julia` command for this setup:

~~~sh
juliaup add 1.12.6
juliaup default 1.12.6
julia --version
~~~

On Windows, use the install method linked from the official
[Julia installation manual](https://docs.julialang.org/en/v1/manual/installation/).
For an installation other than Juliaup, download an official Julia binary and
make its `bin` directory available on `PATH`.

### Install the CLI project's Julia packages

The Seamless CLI backend requires the tracked files
[`Project.toml`](../../julia/Project.toml) and
[`Manifest.toml`](../../julia/Manifest.toml). The project declares `JSON` and
`NPZ`; its manifest pins their current versions to `JSON` **1.10.0** and
`NPZ` **0.4.3** (and records Julia 1.12.6).

From the repository root, instantiate that project with the `seamless1`
environment's Julia depot first:

~~~sh
conda run --live-stream -n seamless1 bash -c 'export JULIA_DEPOT_PATH="$CONDA_PREFIX/share/julia:$HOME/.julia"; julia --startup-file=no --project=seamless/julia -e "using Pkg; Pkg.instantiate(); using JSON, NPZ; println(\"Julia CLI packages ready\")"'
~~~

`Project.toml` and `Manifest.toml` are tracked with Seamless, so Julia's
package manager restores the locked package graph. `JULIA_DEPOT_PATH` chooses
where Julia stores and finds package sources, artifacts and caches: the first
depot above is under the active `seamless1` prefix, with the user depot as a
fallback. Conda does not own or lock these Julia packages; Julia's `Pkg` and
the tracked manifest do. This is an environment-scoped depot, not a Conda
package-lock entry.

For each CLI job, Seamless stages both project files into the job directory
and invokes Julia with `--project=.`. It also puts a writable job-local depot
first, then adds the configured depots, including
`$CONDA_PREFIX/share/julia` and `$HOME/.julia`. **Do not set a global
`JULIA_PROJECT`**: the handler selects its staged project explicitly, and a
global override is neither needed nor used.

The in-memory `juliacall` backend uses a separate project,
`$CONDA_PREFIX/julia_env`. The tracked CLI project does not install packages
for JuliaCall.

## Install R

For a `seamless1` conda setup, install R and the packages used by the CLI
handler from conda-forge:

~~~sh
conda install -n seamless1 -c conda-forge r-base r-jsonlite r-rcppcnpy
~~~

This provides `Rscript`, `jsonlite` and `RcppCNPy` in that environment. For a
non-conda installation, install R from the official
[CRAN installation resources](https://cran.r-project.org/doc/manuals/r-release/R-admin.html),
then install the R packages into the library used by that `Rscript`:

~~~sh
Rscript --vanilla -e 'install.packages(c("jsonlite", "RcppCNPy"), repos="https://cloud.r-project.org")'
~~~

The R CLI runner uses `jsonlite` for its input and output protocol.
`RcppCNPy` is needed when an array pin or result uses NumPy's `.npy` format.
Install any additional packages imported by your R code into the same R
installation. Seamless does not install R packages for a job.

## Configure and run a basic transformer

Run Python from the activated `seamless1` environment so it can find Seamless,
`Rscript`, and `julia`. From the repository root, change to
`seamless-transformer` before running the Python smoke example; this is the
repository that installs the `seamless` Python package:

~~~sh
conda activate seamless1
cd seamless-transformer
export JULIA_DEPOT_PATH="$CONDA_PREFIX/share/julia:$HOME/.julia"
~~~

`"cli"` is already the default for R and Julia; setting it explicitly makes
the process choice clear. A direct Transformer call runs immediately:

~~~python
from seamless.transformer import Transformer

r = Transformer("r", direct=True)
r.metavars.BACKEND = "cli"
r.code = "result <- value + 1"
r.pins.value = 41
r.celltypes.value = "plain"
r.celltypes.result = "plain"
assert r() == 42

julia = Transformer("julia", direct=True)
julia.metavars.BACKEND = "cli"
julia.code = "result = value + 1"
julia.pins.value = 41
julia.celltypes.value = "plain"
julia.celltypes.result = "plain"
assert julia() == 42
~~~

To have Seamless enter the environment for each CLI run, add
`r.environment.set_conda_env("seamless1")` and
`julia.environment.set_conda_env("seamless1")`. The runtimes must be on `PATH`
after that environment is entered. With no environment set, the CLI process
uses the runtime found on the executing process's `PATH`. A Docker image can be
used instead; it must contain the runtime and package libraries, and Julia
jobs need their depot readable by the host user.

## Smoke checks

Check the runtime and package installs without running a Seamless test suite:

~~~sh
conda run --live-stream -n seamless1 Rscript --vanilla -e 'stopifnot(requireNamespace("jsonlite", quietly=TRUE), requireNamespace("RcppCNPy", quietly=TRUE)); cat("R CLI packages ready\n")'
conda run --live-stream -n seamless1 bash -c 'export JULIA_DEPOT_PATH="$CONDA_PREFIX/share/julia:$HOME/.julia"; julia --startup-file=no --project=seamless/julia -e "using JSON, NPZ; println(\"Julia CLI packages ready\")"'
~~~

The Transformer example above is the end-to-end smoke path: each CLI backend
receives the plain pin `value = 41` and returns `42`.
