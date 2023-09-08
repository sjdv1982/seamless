from typing import Any
import glob
import os
from pathlib import Path

from .message import message as msg


def get_file_mapping(
    argdict: dict[str, Any],
    mapping_mode: str,
    working_directory: str,
) -> tuple[dict[str, str], dict[str, str]]:
    """Map files inside the transformation to files on disk.
    Also evaluates file patterns

    Arguments:

    - argdict:
    A dict of argument names and their types ("file", "directory", ...)
      obtained using `guess_arguments` or using an rprodfile.

    - mapping_mode:
    Must be one of:
    "literal": Files are mapped to their relative paths within the current working directory.
    "strip": Strip directory names. After stripping, all files must be unique.
    "rename": Rename to file1, file2, ...
    "rename_with_ext": Same, but add the file extensions (file1.py, file2.txt. ...).

    - working_directory
    The current working directory for "literal" mapping

    Returns:

    - Arg mapping dict:
    Maps the files and file patterns in argdict to the files and file patterns that
    are to be provided to the transformation command

    - File mapping dict:
    a dict where the key is the filename/dirname (pin name)
    inside the transformation and the value is the filename to be read from disk

    """

    if mapping_mode not in ("literal", "strip", "rename", "rename_with_ext"):
        raise ValueError(mapping_mode)

    arg_mapping = {}
    file_mapping = {}
    nfiles = 0
    ndirectories = 0
    nfilepatterns = 0
    cwd = Path(working_directory).resolve().as_posix()
    if cwd != os.sep:
        cwd = cwd.rstrip(os.sep)

    def get_argdescr(argname):
        argdescr = "'{}'".format(argname)
        try:
            pos = argdict.get("@order", []).index(argname) + 1
        except IndexError:
            pass
        else:
            argdescr = "#{} '{}'".format(pos, argname)
        return argdescr

    for argname, argtype in argdict.items():
        if argname == "@order":
            continue
        argdescr = get_argdescr(argname)

        if argtype == "value":
            continue

        elif argtype in ("file", "directory"):
            if argtype == "file":
                nfiles += 1
            else:
                ndirectories += 1
            fullpath = Path(argname).resolve().as_posix()
            if mapping_mode == "literal":
                argname2 = argname
                if not fullpath.startswith(cwd):
                    errmsg = """Argument {} is not under the current working directory.
This is required under 'literal' file mapping. 
To solve this problem:
- Select a different file mapping mode (-ms, -mr, or -mx)
or:
- Specify a different working directory (-w or -W)
"""
                    raise ValueError(errmsg.format(argdescr))
                if fullpath == cwd:
                    relpath = "."
                elif cwd == os.sep:
                    relpath = fullpath
                    argname2 = fullpath[1:]
                elif cwd == os.getcwd():
                    relpath = fullpath[len(cwd) + 1 :]
                else:
                    relpath = fullpath
                    argname2 = fullpath[len(cwd) + 1 :]
                if argname != relpath:
                    msg(
                        3,
                        "Resolve {} to relative path '{}'".format(argdescr, relpath),
                    )
                arg_mapping[argname] = argname2
                file_mapping[argname2] = relpath

            elif mapping_mode == "strip":
                path = argname
                pin_name = os.path.split(path)[1]
                if not pin_name:
                    assert argtype == "directory", (argdescr, argtype)
                    # Take the last element of the parent directory as name
                    pin_name = os.path.split(path)[0].split(os.sep)[-1]
                assert len(pin_name), (argdescr, path)
                if pin_name in arg_mapping:
                    errmsg = "Argument {} argument {} are both mapped to {}"
                    raise ValueError(
                        argdescr, get_argdescr(arg_mapping[pin_name]), pin_name
                    )

                msg(3, "Resolve {} to '{}'".format(argdescr, fullpath))
                msg(2, "Map {} to '{}'".format(argdescr, pin_name))
                arg_mapping[argname] = pin_name
                file_mapping[pin_name] = fullpath

            else:  # rename, rename_with_ext
                if argtype == "file":
                    pin_name = f"file{nfiles}"
                    if mapping_mode == "rename_with_ext":
                        extension = os.path.splitext(argname)[1]
                        if len(extension):
                            pin_name += extension
                else:
                    pin_name = f"file{ndirectories}"
                msg(3, "Resolve {} to '{}'".format(argdescr, fullpath))
                msg(2, "Map {} to '{}'".format(argdescr, pin_name))
                arg_mapping[argname] = pin_name
                file_mapping[pin_name] = fullpath

        elif argtype == "filepattern":
            # glob.glob...
            raise NotImplementedError
        else:
            # TODO: nicer error message, either here or at the end of the rprodfile interpretation
            raise TypeError((argname, argtype))

    return arg_mapping, file_mapping
