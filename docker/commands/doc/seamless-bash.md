% seamless-bash(1) Version 0.1 | seamless-cli Documentation

NAME
====

**seamless-bash** - Starts a bash shell in a new Seamless Docker container

SYNOPSIS
========

| **seamless-bash**

DESCRIPTION
===========

Starts a bash shell in a new Seamless Docker container

The current directory is mounted to /cwd, and the command is executed there

/tmp is mounted as well

Uses the host network for the Docker container. Will only work under Linux.

BUGS
====

See GitHub Issues: <https://github.com/sjdv1982/seamless/issues>

AUTHOR
======

Sjoerd de Vries <sjdv1982@gmail.com>

SEE ALSO
========

**seamless(1)**, **seamless-ipython(1)**, **seamless-jupyter(1)**