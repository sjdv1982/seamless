import sys
from contextlib import contextmanager
from argparse import ArgumentParser
from tempfile import mkstemp
from os import remove, write, close
from pathlib import Path


@contextmanager
def temp_file():
    fd, temp_file_path = mkstemp()
    yield temp_file_path
    close(fd)
    remove(temp_file_path)


SCRIPT_FILE_TEMPLATE = """ctx = context()
__file__ = '{file_path}'
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
    parser.add_argument("file_path", type=Path, default=None, nargs='?')
    args = parser.parse_args()
    file_path = args.file_path

    if file_path is None:
        program = SCRIPT_TEMPLATE.format(body="ctx = context()")

    else:
        if file_path.suffix == ".seamless":
            program = SCRIPT_TEMPLATE.format(body="ctx = seamless.fromfile('{}')".format(file_path.as_posix()))

        else:
            with open(file_path) as fd:
                file_contents = fd.read()

            program = SCRIPT_TEMPLATE.format(
                body=SCRIPT_FILE_TEMPLATE.format(file_path=file_path.as_posix(), file_contents=file_contents)
            )

    with temp_file() as temp_file_path:
        with open(temp_file_path, "w") as f:
            f.write(program)

        argv = [temp_file_path, "-i"]
        from IPython import start_ipython
        sys.exit(start_ipython(argv))



if __name__ == "__main__":
    main()
