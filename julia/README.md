# Julia CLI project setup

The Julia CLI handler uses the tracked `Project.toml` and `Manifest.toml` in
this directory. The manifest was generated with Julia 1.12.6 and pins `JSON`
1.10.0 and `NPZ` 0.4.3. Install the matching Julia runtime using the
[official Juliaup installer](https://julialang.org/downloads/), then run
`juliaup add 1.12.6` and `juliaup default 1.12.6`.

From the repository root, instantiate the locked project into the `seamless1`
environment's Julia depot:

```sh
conda run --live-stream -n seamless1 bash -c 'export JULIA_DEPOT_PATH="$CONDA_PREFIX/share/julia:$HOME/.julia"; julia --startup-file=no --project=seamless/julia -e "using Pkg; Pkg.instantiate(); using JSON, NPZ"'
```

`Project.toml` and `Manifest.toml` lock the Julia package graph. Julia's `Pkg`
stores the downloaded packages and artifacts in the first depot named by
`JULIA_DEPOT_PATH` (`$CONDA_PREFIX/share/julia` here), falling back to
`$HOME/.julia`. This keeps package files under the active conda prefix, but
Conda does not own or lock them: the Julia project and manifest do. It is not
equivalent to Conda recording those dependencies in its environment lock.

Each Julia CLI job stages these two files in its job directory and starts Julia
with `--project=.`. It uses a writable job-local depot first, followed by the
configured Julia depots and `$CONDA_PREFIX/share/julia`. Do not set a global
`JULIA_PROJECT`; Seamless selects the staged project explicitly.

The JuliaCall in-memory backend uses the separate
`$CONDA_PREFIX/julia_env` project. Instantiating this CLI project does not set
up JuliaCall.

To check the CLI project packages directly:

```sh
conda run --live-stream -n seamless1 bash -c 'export JULIA_DEPOT_PATH="$CONDA_PREFIX/share/julia:$HOME/.julia"; julia --startup-file=no --project=seamless/julia -e "using JSON, NPZ"'
```
