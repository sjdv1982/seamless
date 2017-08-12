import sys
from argparse import ArgumentParser


SCRIPT_FILE_TEMPLATE = """ctx = context()
__file__ = {file_path!r}
{file_contents}
"""

SCRIPT_TEMPLATE = """import seamless
from seamless import context, cell, pythoncell, transformer, reactor, \
 macro, export
from seamless.lib import link, edit, display
from seamless.gui import shell

{body}
"""

def main():
    parser = ArgumentParser()
    parser.add_argument("file_path", default=None, nargs='?')
    args = parser.parse_args()
    file_path = args.file_path

    if file_path is None:
        program = SCRIPT_TEMPLATE.format(body="ctx = context()")

    else:
        if file_path.endswith(".seamless"):
            program = SCRIPT_TEMPLATE.format(body="ctx = seamless.fromfile('{}')".format(file_path))

        else:
            with open(file_path) as f:
                file_contents = f.read()

            program = SCRIPT_TEMPLATE.format(
                body=SCRIPT_FILE_TEMPLATE.format(file_path=file_path, file_contents=file_contents)
            )

    argv = [sys.argv[0], "-c", program, "-i"]
    # TODO use tempfile
    from IPython import start_ipython
    sys.exit(start_ipython(argv))


if __name__ == "__main__":
    main()
