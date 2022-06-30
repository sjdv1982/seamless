# Installation

There are three methods to run Seamless.

1. The easiest method is to run Seamless inside Docker containers. With command-line tools such as
`seamless-jupyter`, `seamless-bash` and `seamless-ipython` you can create new Docker containers where you can import Seamless into Jupyter, IPython, etc.
This method will work under any platform where you can install Docker, conda and bash. It has been tested under macOS and Linux. It should also work under Windows with MSYS2.

2. Alternatively, you can create a conda environment to install Seamless directly, without using Docker. Then, instead of `seamless-jupyter` or `seamless-ipython`, you activate the conda environment and launch Jupyter or IPython yourself. This will work out-of-the-box for many use cases, but sometimes you will have to define some environment variables, especially to connect to a Seamless database or a job servant. Features like live debugging are also harder to set up. Therefore, this is recommended only for advanced users.
This method has been tested under macOS and Linux. As it relies on os.fork(), it will not work under Windows.
Note that Seamless is tested only with the Python version inside its Docker image
(For Seamless 0.8, this is Python 3.8). Currently, Seamless uses Python syntax
that requires at least Python 3.7.

3. Finally, there is also the seamless-minimal installation method. This is not a full Seamless installation, since Jupyter and IPython are missing. Instead, the aim of seamless-minimal is to run
Seamless computations inside arbitrary conda environments.

## Installation of Seamless running inside Docker containers

- First, you must [install Docker](https://docs.docker.com/get-docker/)
and [(mini)conda](https://docs.conda.io/en/latest/miniconda.html).

- Pull the Docker image with `docker pull rpbs/seamless`

- Install the Seamless command line tools.

    It is best to create a new environment "seamless", and do `conda activate seamless` whenever you are using Seamless. This is done as follows:
    `conda create -n seamless -c rpbs -c conda-forge seamless-cli`
    Or you can install the Seamless command tools into your current conda environment: `conda install -c rpbs -c conda-forge seamless-cli`

- The command ```seamless-ipython``` launches an IPython terminal inside a
Seamless Docker container.

```seamless-jupyter``` does the same for Jupyter Notebook. Inside the notebook file tree,
browse `seamless-examples`, or `cwd` for the current directory.

## Installation of Seamless running directly in a conda environment

*NOTE: with older conda versions (4.9 or earlier) you must download the .yml file first.*

First, you must [install (mini)conda](https://docs.conda.io/en/latest/miniconda.html).

`conda env create --force --file https://raw.githubusercontent.com/sjdv1982/seamless/stable/conda/seamless-framework-environment.yml`

Solving the environment typically takes a few minutes.
However, it can take very much longer (i.e. forever) if your conda channel priority is not strict. Run the following commands to enforce strict channel priority during installation:

```bash
conda create --no-default-packages --no-pin --force -n seamless-framework -y
conda activate seamless-framework
conda config --env --set channel_priority strict
conda env update --file https://raw.githubusercontent.com/sjdv1982/seamless/stable/conda/seamless-framework-environment.yml
```

The seamless-framework conda environment is big and installing additional packages
may take a lot of time, even with strict channel priority.
Therefore, it has `mamba` installed as a fast, drop-in replacement for the `conda` command.

When running compiled transformers, Seamless assumes that gcc (for C), g++ (for C++) and gfortran are
available. If you wish to run transformers written in these languages, you must install these compilers yourself.

Most likely, you will want to checkout the [seamless-tools Git repo](https://github.com/sjdv1982/seamless-tools). Almost all Seamless commands are wrappers around Python scripts, either in `seamless-tools/scripts` (these scripts heavily rely on Seamless) or `seamless-tools/tools` (these scripts are mostly independent of Seamless). For example, the command `seamless-new-project` (which can be found in `seamless-tools/seamless-cli/seamless-new-project`) is a wrapper around `seamless-tools/scripts/new-project.py`

## Installation of minimal Seamless

Installation is as follows:

```bash
docker pull rpbs/seamless-minimal
conda create -n seamless -c rpbs -c conda-forge seamless-cli -y
conda activate seamless
```

- Export the main conda environment to an external location with `seamless-conda-env-export SOMEDIR`

- You can update the external conda environment using an environment file (normally, the same file used for Transformer.environment.set_conda)
with `seamless-conda-env-modify SOMEDIR someenv.yml`

- Execute a transformation using `seamless-conda-env-run-transformation SOMEDIR transformation-checksum`. The transformation checksum can be obtained using `Transformer.get_transformation()`. This requires a Seamless database to be connected.

## Alternative installation of minimal Seamless using Singularity

You can run seamless-minimal also under Singularity instead of Docker.
In that case, checkout the [seamless-tools Git repo](https://github.com/sjdv1982/seamless-tools) and follow the instructions in `/seamless-tools/seamless-cli-singularity/README.md`
