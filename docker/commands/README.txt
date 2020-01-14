This file contains useful commands that invoke Seamless Docker images.
It is recommended to use Seamless through these commands, rather than installing it as a Python package

Requirements:
- Availability of Docker
- Installation of the "seamless" Docker image
- Creation of a directory ~/.seamless for mounting (~/.seamless/mount) and redis (~/.seamless/redis)
- It is assumed that these commands are only run on a host machine with the following conditions:
    - The Redis port (6379) is not used for another Redis instance than seamless
      Installation of redis-cli is recommended to control Redis from the host machine.
    - It is appropriate to use host networking.

Some individual commands may have additional requirements.

If the requirements are inappropriate for your system, you are encouraged to edit the commands.
Examples of possible edits:
- Using singularity or docker-compose instead of docker
- Changing the networking mode, binding only certain ports
- Using different ports for Redis
- Mounting different folders and volumes
- Additional Docker options: CPU/memory limits, linking to more containers, etc.
