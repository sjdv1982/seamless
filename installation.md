# Installation

## Quick installation (for the impatient)

First, install [Docker](https://docs.docker.com/get-docker/)
and [miniconda](https://docs.conda.io/en/latest/miniconda.html).

Then:

```bash
docker pull rpbs/seamless
conda install -c rpbs -c conda-forge seamless-cli
```

## Docker-based installation

The easiest method is to run Seamless inside Docker containers (the quick installation above). The `seamless-cli` package contains command-line tools such as `seamless-jupyter`, `seamless-bash` and `seamless-ipython` you can launch new Docker containers where you can use Seamless with Jupyter, IPython, etc.

This method will work under any platform where you can install Docker, conda and bash. It has been tested under macOS and Linux. It should also work under Windows if bash is installed (e.g. using MSYS2) but this has not been tested.

### How to do this

See "Quick installation" above. Alternatively, you can create a new environment "seamless", and do `conda activate seamless` whenever you are using Seamless. This is done as follows:

```bash
docker pull rpbs/seamless
conda create -n seamless -c rpbs -c conda-forge seamless-cli
```

#### Installing a specific Seamless version

By default, the Seamless CLI creates `rpbs/seamless` Docker containers.
To specifically install e.g. Seamless 0.12, you can do:

```bash
docker pull rpbs/seamless:0.12
docker tag rpbs/seamless:0.12 rpbs/seamless
```

Alternatively, you can set the `SEAMLESS_DOCKER_IMAGE` variable:
`export SEAMLESS_DOCKER_IMAGE=rpbs/seamless:0.12`

Likewise, you can install a specific version of `seamless-cli`, e.g.
`conda create -n seamless -c rpbs -c conda-forge seamless-cli=0.12`

### After installation

The command ```seamless-ipython``` launches an IPython terminal inside a Seamless Docker container. ```seamless-jupyter``` does the same for Jupyter Notebook. Inside the notebook file tree, browse `seamless-examples`, or `cwd` for the current directory.

## Conda-only installation

Alternatively, you can create a conda environment to install Seamless directly, without using Docker. Instead of `seamless-jupyter` or `seamless-ipython`, you activate the conda environment and launch Jupyter or IPython yourself. In addition, many `seamless-cli` commands (e.g. `seamless-serve-graph`) are installed as alternative versions that do not launch a Docker container, but run directly inside the conda environment. However, the `rpbs/seamless` Docker image is still needed by some other `seamless-cli` commands, notably `seamless-delegate`.

This method has been tested under macOS and Linux. As it relies on `os.fork()`, it will not work under Windows.

### How to do this

First, install [miniconda](https://docs.conda.io/en/latest/miniconda.html).

You will have the choice between several conda environment definitions, on a spectrum between minimalist and maximum compatibility with the Seamless Docker image.

The command is:

`conda env create --file https://raw.githubusercontent.com/sjdv1982/seamless/stable/conda/<environment>-environment.yml`

where `<environment>` can have the following values:

- `seamless-exact`. This is the most compatible installation. This specifies the versions of Python and all packages to be exactly the same as in the Docker image. (For Seamless 0.13, this is Python 3.10). Note that Seamless is tested only with these package versions. The environment is 1.9 GB in size.

- `seamless-framework`. This works like `seamless-exact`, but does not specify package versions unless necessary. As of mid 2024, this will install Python 3.12. Note that Seamless is *not* extensively tested with these Python/package versions: if you encounter a bug, switching to `seamless-exact` may solve it (a bug report is still welcome).

- `seamless-mini`. Same as above, but will omit some packages. Not all Seamless tests and examples will work. Jupyter is no longer installed, and neither are packages such as scikit-learn, scipy, matplotlib or pandas. If you need those packages, you must install them yourself. The environment is ~500 MB in size.

- `seamless-micro`. Same as above, but this will install only the absolute minimum to run (most of) Seamless. As of mid 2024, the environment contains 109 packages and is ~400 MB in size.

NOTE: When running compiled transformers, Seamless assumes that gcc (for C), g++ (for C++) and/or gfortran are available. These are not installed by default. If you wish to run transformers written in these languages, you must install these compilers yourself, either using conda or from system packages.
