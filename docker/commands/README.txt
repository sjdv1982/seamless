This directory contains useful commands that invoke Seamless Docker images.
It is recommended to use Seamless through these commands, rather than installing it as a Python package

Requirements:
- Availability of Docker
- Installation of the "seamless" Docker image

Some individual commands may have additional requirements.

If the requirements are inappropriate for your system, you are encouraged to edit the commands.
Examples of possible edits:
- Using singularity or docker-compose instead of docker
- Changing the networking mode, binding only certain ports
- Using different ports for Redis
- Mounting different folders and volumes
- Additional Docker options: CPU/memory limits, linking to more containers, etc.
