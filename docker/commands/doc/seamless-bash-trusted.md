% seamless-bash(1) Version 0.1 | seamless-cli Documentation

NAME
====

**seamless-bash-trusted** - Starts a bash shell in a new Seamless Docker container

SYNOPSIS
========

| **seamless-bash-trusted**

DESCRIPTION
===========

Starts a bash shell in a new Seamless Docker container.

**Uses the host network for the Docker container. Will only work under Linux.**

**NOTE: THIS VERSION GIVES THE CONTAINER ACCESS TO THE DOCKER DAEMON. THIS IS A BIG SECURITY HOLE, IT CAN GIVE ROOT ACCESS TO YOUR SYSTEM**

The ID of the Docker container is available to the Docker container itself,
 in the file ~/DOCKER_CONTAINER.

The current directory is mounted to /cwd, and the command is executed there
The name of the current directory is available in the container as $HOSTCWD.

BUGS
====

See GitHub Issues: <https://github.com/sjdv1982/seamless/issues>

AUTHOR
======

Sjoerd de Vries <sjdv1982@gmail.com>

SEE ALSO
========

**seamless(1)**, **seamless-ipython(1)**, **seamless-jupyter(1)**