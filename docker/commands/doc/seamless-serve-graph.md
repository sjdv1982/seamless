% seamless-serve-graph(1) Version 0.1 | seamless-cli Documentation

NAME
====

**seamless-serve-graph** - Serves a Seamless graph over HTTP

SYNOPSIS
========

| **seamless-serve-graph** \[_command_]
| **seamless-serve-graph** \[**-h**|**--help**|

DESCRIPTION
===========

Serves a Seamless graph over HTTP inside a seamless Docker container.
This requires Seamless to be importable on the host system

The current directory is mounted to /cwd, and the serve-graph script is executed there

/tmp is mounted as well

Uses the host network for the Docker container. Will only work under Linux.

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

**seamless(1)**, **seamless-serve-graph-interactive(1)**,