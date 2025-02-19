"""Interface files for cmd-seamless"""

import json
import os
import sys
from pathlib import Path
import subprocess
from typing import Any
import ruamel.yaml
from .parsing import fill_checksum_arguments

from seamless.cmd.message import message as msg

yaml = ruamel.yaml.YAML(typ="safe")


def load(yamlfile):
    """Load interface from YAML file"""
    with open(yamlfile) as f:
        data = yaml.load(f)
    if data is None:
        msg(1, f"{yamlfile} is empty")
        return {}
    if not isinstance(data, dict):
        raise TypeError("Must be dict, not {}".format(type(data)))
    # TODO: validation!
    return data


def locate_files(command):
    """Locate interface files:
    - YAML
    - Python

    Returns:
     the argument index of the tool with the interface file(s),
     the YAML interface file,
     the Python interface file,
     the (mapped) execution argument
    """
    interface_file = None
    interface_py_file = None
    interface_argindex = None
    mapped_execarg = None

    args1 = [Path(command[0]), Path(command[0]).expanduser()]
    for arg1 in args1:
        execarg1 = subprocess.getoutput("which {}".format(arg1.as_posix())).strip()
        if execarg1:
            msg(
                2,
                "first argument '{}' is in PATH, map to '{}'".format(
                    arg1.as_posix(), execarg1
                ),
            )
            execarg1dir = os.path.split(execarg1)[0]
            if (
                not execarg1dir.endswith("/bin")
                and not execarg1dir.endswith("/sbin")
                and not execarg1dir.endswith("/usr")
            ):
                msg(
                    1,
                    "first argument '{}' does not seem a POSIX tool. Explicitly upload it as '{}'".format(  # pylint: disable=line-too-long
                        arg1.as_posix(), execarg1
                    ),
                )
                mapped_execarg = execarg1

            arg1 = Path(execarg1)
        else:
            mapped_execarg = arg1.as_posix()

        if arg1.exists():
            interface_file0 = Path(arg1.as_posix() + ".SEAMLESS.yaml")
            interface_file = interface_file0 if interface_file0.exists() else None
            if interface_file is None:
                msg(
                    2,
                    "first argument '{}' has no .SEAMLESS.yaml file".format(
                        arg1.as_posix()
                    ),
                )
            else:
                interface_argindex = 0
                msg(
                    1,
                    "found interface YAML file '{}' for first argument '{}'".format(
                        interface_file, arg1.as_posix()
                    ),
                )
            break
    else:
        msg(1, "first argument '{}' is not a file".format(arg1.as_posix()))
        mapped_execarg = None

    arg2 = None
    if interface_file is None and len(command) > 1 and not arg1.suffix:
        msg(
            3,
            "first argument has no suffix, considering second argument for .SEAMLESS.yaml file",
        )
        for n in range(1, len(command)):
            arg = command[n]
            if arg.startswith("-"):
                continue
            args2 = [Path(arg), Path(arg).expanduser()]
            for arg2 in args2:
                if arg2.exists():
                    interface_argindex2 = n
                if len(arg2.suffix):
                    msg(
                        3,
                        "second argument '{}' has a suffix, look for .SEAMLESS.yaml file".format(
                            arg2.as_posix()
                        ),
                    )
                    if arg2.exists():
                        interface_file0 = Path(arg2.as_posix() + ".SEAMLESS.yaml")

                        interface_file = (
                            interface_file0 if interface_file0.exists() else None
                        )
                        if interface_file is None:
                            msg(
                                2,
                                "second argument '{}' has no .SEAMLESS.yaml file".format(
                                    arg2.as_posix()
                                ),
                            )
                        else:
                            interface_argindex = interface_argindex2
                            msg(
                                1,
                                "found interface YAML file '{}' for second argument '{}'".format(
                                    interface_file, arg2.as_posix()
                                ),
                            )
                        break
            else:
                continue
            break

    interface_py_file0 = None
    if interface_file is None:
        msg(2, "no .SEAMLESS.yaml file found")
        if arg1.exists():
            interface_argindex = 0
            interface_py_file0 = Path(
                os.path.splitext(arg1.as_posix())[0] + ".SEAMLESS.py"
            )
        elif arg2 and arg2.exists():
            interface_argindex = interface_argindex2
            interface_py_file0 = Path(
                os.path.splitext(arg2.as_posix())[0] + ".SEAMLESS.py"
            )
    else:
        interface_py_file0 = Path(os.path.splitext(interface_file)[0] + ".py")
    interface_py_file = (
        interface_py_file0
        if interface_py_file0 and interface_py_file0.exists()
        else None
    )
    if interface_py_file:
        msg(
            1,
            "found interface Python file '{}'".format(interface_py_file),
        )
    else:
        msg(2, "no .SEAMLESS.py file found")

    return interface_argindex, interface_file, interface_py_file, mapped_execarg


def _execute_py_file(command, interface_argindex, interface_py_file):
    interface_py_cmd = [sys.executable, interface_py_file.as_posix()] + command[
        interface_argindex + 1 :
    ]
    msg(2, f"running .SEAMLESS.py command:\n  {' '.join(interface_py_cmd)}")
    proc = subprocess.run(
        interface_py_cmd,
        shell=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    err = proc.returncode
    interface_py_data = proc.stdout.decode()
    if err != 0:
        msg(
            -1,
            f"{interface_py_file} resulted in an exception:\n\n"
            + "command: "
            + " ".join(interface_py_cmd)
            + "\n\n"
            + interface_py_data,
        )
        exit(1)
    try:
        interface_py_data = json.loads(interface_py_data)
        assert isinstance(interface_py_data, dict)
    except (json.JSONDecodeError, AssertionError):
        msg(
            -1,
            f"{interface_py_file} results cannot be parsed:\n\n"
            + "command: "
            + " ".join(interface_py_cmd)
            + "\n\n"
            + interface_py_data,
        )
        exit(1)
    return interface_py_data


def get_argtypes_and_results(
    interface_file, interface_py_file, interface_argindex, command, original_binary
) -> tuple[None, None] | tuple[dict[str, Any] | dict]:
    """Parse a command into argument types and results, using the interface file(s)"""
    interface_data = None
    if interface_file is not None:
        msg(2, "Try to obtain argtypes from interface YAML file...")
        interface_data = load(interface_file)

    interface_py_data = {}
    if interface_py_file is not None:
        msg(2, "Try to obtain argtypes from interface py file...")
        interface_py_data = _execute_py_file(
            command, interface_argindex, interface_py_file
        )
        if interface_py_data is not None:
            msg(2, "...success")
        else:
            msg(2, "...failure")
            interface_py_data = {}

    if not interface_data and not interface_py_data:
        return None, None

    order = []
    order[:] = [original_binary] + command[1:]
    argtype_original_binary = True
    if "@order" in interface_py_data:
        order = interface_py_data["@order"]
        if len(order) and original_binary != order[0]:
            argtype_original_binary = False
    argtypes = {"@order": order}
    argtypes.update(interface_data.get("argtypes", {}))
    argtypes.update(interface_py_data.get("argtypes", {}))
    if argtype_original_binary:
        argtypes[original_binary] = {
            "type": "file",
            "mapping": command[0],
        }

    def resolve_dot(f, fdir):
        if f.startswith("." + os.sep):
            if not fdir:
                f = f[2:]
            else:
                f = fdir + f[1:]
        return f

    initial_results = {}
    for if_data, if_filename in (
        (interface_data, interface_file),
        (interface_py_data, interface_py_file),
    ):
        files = if_data.get("files", [])
        if files:
            msg(3, f"Read 'files' from {if_filename}:\n  {files}")
        directories = if_data.get("directories", [])
        values = if_data.get("values", [])
        if values:
            msg(3, f"Read 'values' from {if_filename}:\n  {values}")
        shim = if_data.get("shim")
        fdir = os.path.split(command[0])[0]
        results = if_data.get("results", [])
        if results:
            msg(3, f"Read 'results' from {if_filename}:\n  {results}")
            if isinstance(results, dict):
                resolved_results = {}
                for k, v in results.items():
                    kk = resolve_dot(k, fdir)
                    resolved_results[kk] = v
                if resolved_results != results:
                    msg(3, f"Resolved results:\n  {resolved_results}")
            else:
                resolved_results = {resolve_dot(f, fdir): None for f in results}
                if resolved_results != {f: None for f in results}:
                    msg(3, f"Resolved results:\n  {resolved_results}")
            initial_results.update(resolved_results)

        fill_checksum_arguments(files, order)
        for flist, ftype in ((files, "file"), (directories, "directory")):
            for f in flist:
                mapping = None
                checksum = None
                if isinstance(f, dict):
                    fname = f["name"]
                    mapping = f.get("mapping")
                    fixed_mapping = True
                    checksum = f.get("checksum")
                else:
                    fname = f
                    f2 = os.path.expanduser(f)
                    fixed_mapping = True
                    if f2 != f:
                        mapping = f2
                        fixed_mapping = False
                fname = resolve_dot(fname, fdir)
                try:
                    pos = order.index(fname)
                    order[pos] = fname
                except ValueError:
                    pass
                if mapping or checksum:
                    if mapping:
                        try:
                            pos = order.index(mapping)
                            order[pos] = fname
                        except ValueError:
                            pass
                        mapping = os.path.expanduser(mapping)
                        argtypes[fname] = {
                            "type": ftype,
                            "mapping": mapping,
                            "fixed_mapping": fixed_mapping,
                        }
                    else:
                        argtypes[fname] = {
                            "type": ftype,
                        }
                    if checksum:
                        argtypes[fname]["checksum"] = checksum
                else:
                    argtypes[fname] = ftype
        for val in values:
            argtypes[val] = "value"
        if shim is not None:
            argtypes["@shim"] = shim
    return argtypes, initial_results


def interface_from_py_file(interface_py_file, arguments):
    """Load an interface from a .py file"""
    interface_py_data = _execute_py_file(arguments, -1, interface_py_file)
    # TODO: validation
    return interface_py_data
