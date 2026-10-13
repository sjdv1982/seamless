# Julia CLI test environment

The Julia command-line handler uses the tracked `Project.toml` and `Manifest.toml` in this directory. Install its locked dependencies in the `seamless1` conda depot from the repository root with:

```sh
conda run --live-stream -n seamless1 bash -c 'export JULIA_DEPOT_PATH="$CONDA_PREFIX/share/julia"; julia --startup-file=no --project=seamless/julia -e "using Pkg; Pkg.instantiate()"'
```

To run the CLI project with the conda depot first and the user depot as a fallback:

```sh
conda run --live-stream -n seamless1 bash -c 'export JULIA_DEPOT_PATH="$CONDA_PREFIX/share/julia:$HOME/.julia"; julia --startup-file=no --project=seamless/julia -e "using JSON, NPZ"'
```

The JuliaCall backend continues to use its separate project at `$CONDA_PREFIX/julia_env`.
