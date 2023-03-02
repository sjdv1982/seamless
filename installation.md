# Installation

## Quick installation (for the impatient)

First, [install Docker](https://docs.docker.com/get-docker/)
and [miniconda](https://docs.conda.io/en/latest/miniconda.html).

```bash
docker pull rpbs/seamless
conda create -n seamless -c rpbs -c conda-forge seamless-cli -y
conda activate seamless
```

***These three lines are sufficient to get Seamless working***

## Comparison between installation methods

This paragraph is in case the quick installation does not work for you, or if you want to know first what you are doing.

There are three methods to run Seamless. Below, each of the three methods is briefly explained. The section after provides installation instructions for each of the methods.

1. The easiest method is to run Seamless inside Docker containers (the quick installation above). With command-line tools such as `seamless-jupyter`, `seamless-bash` and `seamless-ipython` you can create new Docker containers where you can import Seamless into Jupyter, IPython, etc.

    This method will work under any platform where you can install Docker, conda and bash. It has been tested under macOS and Linux. It should also work under Windows with MSYS2.

2. Alternatively, you can create a conda environment to install Seamless directly, without using Docker. Then, instead of `seamless-jupyter` or `seamless-ipython`, you activate the conda environment and launch Jupyter or IPython yourself. This will work out-of-the-box for many use cases, but sometimes you will have to define some environment variables, especially to connect to a Seamless database or a job servant. Features like live debugging are also harder to set up. Therefore, this is recommended only for advanced users.

    This method has been tested under macOS and Linux. As it relies on `os.fork()`, it will not work under Windows.

    You will have the choice between several conda environment definitions, on a spectrum between minimalist and maximum compatibility with the Seamless Docker image.

3. Finally, there is also the seamless-minimal installation method. This is not a real Seamless installation. The aim of seamless-minimal is to act as a *service* to execute reproducible computations (transformations) inside arbitrary conda environments. These transformations are generated elsewhere, by a full Seamless installation, or by a different reproducible computation framework.

## Installation instructions

### 1. Installation of Seamless running inside Docker containers

- First, you must [install Docker](https://docs.docker.com/get-docker/)
and [(mini)conda](https://docs.conda.io/en/latest/miniconda.html).

- Pull the Docker image with `docker pull rpbs/seamless`

- Install the Seamless command line tools.

    It is best to create a new environment "seamless", and do `conda activate seamless` whenever you are using Seamless. This is done as follows: `conda create -n seamless -c rpbs -c conda-forge seamless-cli`.

    Or you can install the Seamless command line tools into your current conda environment: `conda install -c rpbs -c conda-forge seamless-cli`

- The command ```seamless-ipython``` launches an IPython terminal inside a Seamless Docker container.

```seamless-jupyter``` does the same for Jupyter Notebook. Inside the notebook file tree, browse `seamless-examples`, or `cwd` for the current directory.

### 2. Installation of Seamless running directly in a conda environment

First, you must [install (mini)conda](https://docs.conda.io/en/latest/miniconda.html).

Then, you must install `mamba` in the base environment. `mamba` is a fast, drop-in replacement for the `conda` command. The Seamless conda environments are big and the default `conda env create` command does not handle their dependencies very well.

Then, create a `seamless-framework` conda environment with the following command:

`mamba env create --force --file https://raw.githubusercontent.com/sjdv1982/seamless/stable/conda/<file>.yml`

where `<file>.yml` has one of the values below.

In all cases, a conda environment `seamless-framework` is created. If you want to rename it (e.g. to compare different installations), you can do so with `conda rename -n seamless-framework ...`

#### Possible conda installations

`<file>.yml` can have the following values:

- `seamless-exact-environment.yml`. This is the most compatible installation. This specifies the versions of Python and all packages to be exactly the same as in the Docker image. (For Seamless 0.11, this is Python 3.10.9). Note that Seamless is tested only with these package versions. The environment is 1.9 GB in size.

- `seamless-framework-environment.yml`. This installs Python and all packages in the Docker image, but does not specify their versions. As of early 2023, this will install Python 3.11. Note that Seamless is *not* extensively tested with these Python/package versions: if you encounter a bug, switching to `seamless-exact-environment.yml` may solve it (a bug report is still welcome). The environment is ~2.1 GB in size.

- `seamless-mini-environment.yml`. Same as above, but will omit some packages. Not all Seamless tests and examples will work. Jupyter is no longer installed, and neither are packages such as scikit-learn, scipy, matplotlib or pandas. If you need those packages, you must install them yourself. The environment is ~410 MB in size.

- `seamless-micro-environment.yml`. Same as above, but this will install only the absolute minimum to run (most of) Seamless. As of early 2023, the environment contains 82 packages and is ~330 MB in size.

#### Post-installation

Even with the most compatible installation, making it fully working requires some manual steps.

- When running compiled transformers, Seamless assumes that gcc (for C), g++ (for C++) and gfortran are available. These are not installed by default. If you wish to run transformers written in these languages, you must install these compilers yourself.

- Most likely, you will want to checkout the [seamless-tools Git repo](https://github.com/sjdv1982/seamless-tools). Almost all Seamless commands are wrappers around Python scripts, either in `seamless-tools/scripts` (these scripts heavily rely on Seamless) or `seamless-tools/tools` (these scripts are mostly independent of Seamless). For example, the command `seamless-new-project` (which can be found in `seamless-tools/seamless-cli/seamless-new-project`) is a wrapper around `seamless-tools/scripts/new-project.py` . You will have to set up (some of) the variables that are normally set up by `source seamless-tools/seamless-cli/seamless-fill-environment-variables`. For example, you may need to change SEAMLESS_COMMUNION_IP or SEAMLESS_DATABASE_IP from the Docker host IP into "localhost". Other tools (e.g. the Seamless database) assume a Docker-mapped directory in their default configurations, this needs to be changed as well.

### 3. Installation of minimal Seamless

Installation is as follows:

```bash
docker pull rpbs/seamless-minimal
conda create -n seamless -c rpbs -c conda-forge seamless-cli -y
conda activate seamless
```

- Export the main conda environment to an external location with `seamless-conda-env-export SOMEDIR`

- You can update the external conda environment using an environment file (normally, the same file used for Transformer.environment.set_conda) with `seamless-conda-env-modify SOMEDIR someenv.yml`

- Execute a transformation using `seamless-conda-env-run-transformation SOMEDIR transformation-checksum`. The transformation checksum can be obtained using `Transformer.get_transformation()`. This requires a Seamless database to be connected.

#### Alternative installation using Singularity

You can run seamless-minimal also under Singularity instead of Docker.

In that case, checkout the [seamless-tools Git repo](https://github.com/sjdv1982/seamless-tools) and follow the instructions in `/seamless-tools/seamless-cli-singularity/README.md`
