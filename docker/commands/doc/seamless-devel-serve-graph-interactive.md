% seamless-devel-serve-graph(1) Version 0.1 | seamless-cli Documentation

NAME
====

**seamless-devel-serve-graph** - Serves a Seamless graph over HTTP under IPython

SYNOPSIS
========

| **seamless-devel-serve-graph-interactive** \[_command_]
| **seamless-devel-serve-graph-interactive** \[**-h**|**--help**]

DESCRIPTION
===========

Serves a Seamless graph over HTTP inside a seamless-devel Docker container.
This requires Seamless to be importable on the host system

The graph is served in an IPython terminal, where the graph can be modified interactively.

The current directory is mounted to /cwd, and the serve-graph script is executed there

/tmp is mounted as well

Uses the host network for the Docker container. Will only work under Linux.

Seamless has access to the Docker daemon, so it can launch its own Docker
containers via the Docker transformer. This works only under Linux.
**NOTE: THIS IS A BIG SECURITY HOLE, IT CAN GIVE ROOT ACCESS TO YOUR SYSTEM**


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

**seamless-devel(1)**, **seamless-devel-serve-graph(1)**,