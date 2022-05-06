This directory contains useful commands that invoke Seamless Docker images.
It is recommended to use Seamless through these commands, rather than installing it as a Python package

Requirements:
- bash and a POSIX environment (Linux, OSX, MSYS2)
- Availability of Docker
- Installation of the "rpbs/seamless" Docker image. 
  The Docker image name can be changed using SEAMLESS_DOCKER_IMAGE.
  Notably, setting it to "seamless-devel" makes it mount an external Seamless source directory 
  (defined as $SEAMLESSDIR)
- A few more dependencies. These are installed together with the commands in the seamless-cli conda package (channel rpbs)

The seamless-conda-env-XXX commands instead use the rpbs/seamless-minimal Docker image.
This image relies on an *external* conda environment, mounted into the Docker image.
This allows the user to install conda packages and then run a transformation