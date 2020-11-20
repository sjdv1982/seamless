% seamless-jupyter-trusted(1) Version 0.1 | seamless-cli Documentation

NAME
====

**seamless-jupyter-trusted** - Starts a Jupyter Notebook server in a new Seamless Docker container

SYNOPSIS
========

| **seamless-jupyter-trusted** \[_Jupyter notebook server arguments_]
| **seamless-jupyter-trusted** \[**-h**|**--help**]

DESCRIPTION
===========

Starts a Jupyter Notebook server in a new Seamless Docker container

The current directory is mounted to /cwd, and the Jupyter server is executed there

/tmp is mounted as well

Uses the host network for the Docker container. Will only work under Linux.

This variant gives Seamless access to the Docker daemon, so it can launch its own Docker containers via the Docker transformer. This works only under Linux.
**NOTE: THIS IS A BIG SECURITY HOLE, IT CAN GIVE ROOT ACCESS TO YOUR SYSTEM**

All Jupyter passwords are disabled.

By default, only connections from `localhost` are accepted.
Add `--ip='0.0.0.0'` to allow connections from outside.

Options
-------

-h, --help

:   Prints brief usage information.


BUGS
====

See GitHub Issues: <https://github.com/sjdv1982/seamless/issues>

AUTHOR
======

Sjoerd de Vries <sjdv1982@gmail.com>

SEE ALSO
========

**seamless-jupyter(1)**