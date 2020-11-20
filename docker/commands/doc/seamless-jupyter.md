% seamless-jupyter(1) Version 0.1 | seamless-cli Documentation

NAME
====

**seamless-jupyter** - Starts a Jupyter Notebook server in a new Seamless Docker container

SYNOPSIS
========

| **seamless-jupyter** \[_Jupyter notebook server arguments_]
| **seamless-jupyter** \[**-h**|**--help**]

DESCRIPTION
===========

Starts a Jupyter Notebook server in a new Seamless Docker container

The current directory is mounted to /cwd, and the Jupyter server is executed there

/tmp is mounted as well

Uses the host network for the Docker container. Will only work under Linux.

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

**seamless(1)**, **seamless-bash(1)**, **seamless-ipython(1)**