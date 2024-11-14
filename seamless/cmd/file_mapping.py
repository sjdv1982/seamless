"""Map files inside the transformation to files on disk."""

from typing import Any
import os
from pathlib import Path

from seamless import Checksum

from .message import message as msg


def get_file_mapping(
    argtypes: dict[str, Any],
    mapping_mode: str,
    working_directory: str,
) -> tuple[dict[str, str], dict[str, str]]:
    """Map files inside the transformation to files on disk.

    Arguments:

    - argtypes:
    A dict of argument names and their types ("file" or "directory")
      obtained using `guess_arguments` or from interface files.

    - mapping_mode:
    Must be one of:
    "literal": Files are mapped to their relative paths within the current working directory.
    "strip": Strip directory names. After stripping, all files must be unique.
    "extension": Rename and keep only the file extensions (file1.py, file2.txt. ...).

    - working_directory
    The current working directory for "literal" mapping

    Returns:

    Updated argtypes dict where every "file" entry has been replaced.
    The new key will be the filename/dirname (pin name) inside the transformation,
     which will also be the target file name on the server.
    The filename to be read from disk becomes the "mapping" field in the entry value.
    The "@order" field is updated accordingly.
    """

    if mapping_mode not in ("literal", "strip", "extension"):
        raise ValueError(mapping_mode)

    order = []
    if argtypes:
        order = argtypes["@order"]
    new_order = []
    result = {"@order": new_order}
    nfiles = 0
    ndirectories = 0
    cwd = Path(working_directory).resolve().as_posix()
    if cwd != os.sep:
        cwd = cwd.rstrip(os.sep)

    def get_argdescr(argname):
        argdescr = "'{}'".format(argname)
        try:
            pos = order.index(argname) + 1
        except ValueError:
            return argname
        else:
            argdescr = "#{} '{}'".format(pos, argname)
        return argdescr

    order_map = {}
    for argname, argtype in argtypes.items():
        path = argname
        if argname == "@order":
            continue
        argdescr = get_argdescr(argname)

        fixed_mapping = False
        checksum = None
        if isinstance(argtype, dict):
            if argtype.get("type") not in ("file", "directory"):
                raise TypeError((argname, argtype))
            if argtype.get("mapping"):
                path = argtype["mapping"]
                fixed_mapping = argtype.get("fixed_mapping")
            checksum = Checksum(argtype.get("checksum"))
            argtype = argtype["type"]

        if argtype == "value":
            order_map[argname] = argname
            result[argname] = argtype

        elif argtype in ("file", "directory"):
            if argtype == "file":
                nfiles += 1
            else:
                ndirectories += 1
            if fixed_mapping:
                new_path = path
                new_entry = {"type": argtype, "mapping": path}
            else:
                fullpath = Path(path).absolute().as_posix()
                if mapping_mode == "literal":
                    path2 = path
                    cwd0 = "" if cwd == os.sep else cwd
                    if not fullpath.startswith(cwd0 + os.sep):
                        errmsg = """Argument {} is not under the current working directory.
This is required under 'literal' file mapping. 
To solve this problem:
- Select a different file mapping mode (-ms or -mx)
or:
- Specify a different working directory (-w or -W)
"""
                        raise ValueError(errmsg.format(argdescr))
                    if fullpath == cwd:
                        relpath = "."
                    elif cwd == os.sep:
                        relpath = fullpath[1:]
                    else:
                        relpath = fullpath[len(cwd) + 1 :]
                    if path != relpath:
                        msg(
                            3,
                            "Resolve {} to relative path '{}'".format(
                                argdescr, relpath
                            ),
                        )
                    new_path = relpath
                    new_entry = {"type": argtype, "mapping": fullpath}

                elif mapping_mode == "strip":
                    spath = path
                    path2 = os.path.split(spath)[1]
                    if not path2:
                        assert argtype == "directory", (argdescr, argtype)
                        # Take the last element of the parent directory as name
                        path2 = os.path.split(path)[0].split(os.sep)[-1]
                    assert len(path2), (argdescr, path)

                    msg(3, "Resolve {} to '{}'".format(argdescr, fullpath))
                    msg(2, "Map {} to '{}'".format(argdescr, path2))

                    new_path = path2
                    new_entry = {"type": argtype, "mapping": fullpath}

                else:  # extension
                    if argtype == "file":
                        path2 = f"file{nfiles}"
                        extension = os.path.splitext(path)[1]
                        if len(extension):
                            path2 += extension
                    else:
                        path2 = path
                        cwd0 = "" if cwd == os.sep else cwd
                        if not fullpath.startswith(cwd0 + os.sep):
                            errmsg = """Argument {} is not under the current working directory.
This is required under 'extension' file mapping for directories. 
To solve this problem:
- Specify a different working directory (-w or -W)
"""
                            raise ValueError(errmsg.format(argdescr))

                    msg(3, "Resolve {} to '{}'".format(argdescr, fullpath))
                    msg(2, "Map {} to '{}'".format(argdescr, path2))
                    new_path = path2
                    new_entry = {"type": argtype, "mapping": fullpath}

            if new_path in result and result[new_path] != new_entry:
                errmsg = f"""Two different mappings for argument "{new_path}":
{result[new_path]} and {new_entry}"""
                raise ValueError(errmsg)

            if checksum:
                new_entry["checksum"] = checksum

            if fixed_mapping:
                result[argname] = new_entry
            else:
                order_map[argname] = new_path
                result[new_path] = new_entry

        else:
            raise TypeError((path, argtype))

    for arg in order:
        if arg in order_map:
            new_order.append(order_map[arg])
        else:
            new_order.append(arg)
    return result
