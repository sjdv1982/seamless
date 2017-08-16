#!/usr/bin/env python3

import os.path
import sys


def main():
    cmd = """import seamless
from seamless import context, cell, pythoncell, transformer, reactor, \
 macro, export
from seamless.lib import link, edit, display
from seamless.gui import shell
"""
    if len(sys.argv) == 1:
        cmd += "ctx = context()"

    else:
        assert len(sys.argv) == 2  # syntax: seamless file.seamless
        f = os.path.abspath(sys.argv[1])

        if f.endswith(".seamless"):
            cmd += "ctx = seamless.fromfile('{0}')".format(f)
        else:
            cmd += "ctx = context()\n"
            cmd += "__file__ = {!r}\n".format(f)
            cmd += open(f).read()
    sys.argv = [sys.argv[0], "-c", cmd, "-i"]

    from IPython import start_ipython
    sys.exit(start_ipython())


if __name__ == "__main__":
    main()
