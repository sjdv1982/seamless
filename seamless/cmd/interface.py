import json
import os
import sys
from pathlib import Path
import subprocess
import ruamel.yaml
yaml = ruamel.yaml.YAML(typ='safe')
from seamless.cmd.message import message as msg

def load(yamlfile):
    with open(yamlfile) as f:
        data = yaml.load(f)
    if not isinstance(data, dict):
        raise TypeError("Must be dict, not {}".format(type(data)))
    # TODO: validation!
    return data
    
def locate_files(command):
    interface_file = None
    interface_py_file = None
    interface_argindex = None
    mapped_execarg = None

    args1 = [Path(command[0]), Path(command[0]).expanduser()]
    for arg1 in args1:
        if not arg1.exists():
            execarg1 = subprocess.getoutput("which {}".format(arg1.as_posix())).strip()
            if execarg1:
                msg(
                    2,
                    "first argument '{}' is in PATH, map to '{}'".format(
                        arg1.as_posix(), execarg1
                    ),
                )
                if not execarg1.startswith("/bin") and not execarg1.startswith("/sbin") and not execarg1.startswith("/usr"):
                    msg(
                        1,
                        "first argument '{}' does not seem a POSIX tool. Explicitly upload it as '{}'".format(
                            arg1.as_posix(), execarg1
                        ),
                    )
                    mapped_execarg = execarg1

                arg1 = Path(execarg1)
        if arg1.exists():
            interface_file0 = Path(arg1.as_posix() + ".SEAMLESS.yaml")
            interface_file = interface_file0 if interface_file0.exists() else None
            if interface_file is None:
                msg(2, "first argument '{}' has no .SEAMLESS.yaml file".format(arg1.as_posix()))
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

    if interface_file is None and len(command) > 1 and not arg1.suffix:
        msg(3, "first argument has no suffix, considering second argument for .SEAMLESS.yaml file")
        arg2 = None
        for n in range(1, len(command)):
            arg = command[n]
            if arg.startswith("-"):
                continue
            args2 = [Path(arg), Path(arg).expanduser()]
            for arg2 in args2:
                if len(arg2.suffix):
                    msg(
                        3,
                        "second argument '{}' has a suffix, look for .SEAMLESS.yaml file".format(
                            arg2.as_posix()
                        ),
                    )
                    if arg2.exists():
                        interface_file0 = Path(arg2.as_posix() + ".SEAMLESS.yaml")
                
                        interface_file = interface_file0 if interface_file0.exists() else None
                        interface_argindex = n
                        if interface_file is None:
                            msg(2, "second argument '{}' has no .SEAMLESS.yaml file".format(arg2.as_posix()))
                        else:
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
    if interface_file is None:
        msg(2, "no .SEAMLESS.yaml file found")
    else:    
        interface_py_file0 = Path(os.path.splitext(interface_file)[0] + ".py")
        interface_py_file = interface_py_file0 if interface_py_file0.exists() else None
        if interface_py_file:
            msg(
                1,
                "found interface Python file '{}'".format(
                    interface_py_file
                ),
            )

    return interface_argindex, interface_file, interface_py_file, mapped_execarg

def _execute_py_file(command, interface_argindex, interface_py_file):
    interface_py_cmd = f'{sys.executable} {interface_py_file} {" ".join(command[interface_argindex+1:])}'
    interface_py_cmd = [sys.executable,  interface_py_file.as_posix()] + command[interface_argindex+1:]
    msg(2, f"running .SEAMLESS.py command:\n  {' '.join(interface_py_cmd)}" )
    proc = subprocess.run(interface_py_cmd, shell=False, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    err = proc.returncode
    interface_py_data = proc.stdout.decode()
    if err != 0:
        msg(-1, f'{interface_py_file} resulted in an exception:\n\n' + "command: " +  " ".join(interface_py_cmd) + "\n\n" + interface_py_data)
        exit(1)
    try:
        interface_py_data = json.loads(interface_py_data)
        assert isinstance(interface_py_data, dict)
    except (json.JSONDecodeError, AssertionError):
        msg(-1, f'{interface_py_file} results cannot be parsed:\n\n' + "command: " + " ".join(interface_py_cmd) + "\n\n" + interface_py_data)
        exit(1)
    return interface_py_data

def argtypes_from_py_file(command, interface_argindex, interface_py_file):
    interface_py_data = _execute_py_file(command, interface_argindex, interface_py_file)
    # TODO: validation
    order = []
    order[:] = command
    argtypes = interface_py_data.get("argtypes", {}).copy()
    argtypes["@order"] = order
    files = interface_py_data.get("files", [])
    directories = interface_py_data.get("directories", [])
    shim = interface_py_data.get("shim")
    for flist, ftype in ((files, "file"), (directories, "directory")):
        for f in flist:
            mapping = None
            if isinstance(f, dict):
                fname = f["name"]
                mapping = f.get("mapping")
            else:
                fname = f
                f2 = os.path.expanduser(f)
                if f2 != f:
                    mapping = f2
            pos = order.index(fname)
            order[pos] = fname
            if mapping:
                mapping = os.path.expanduser(mapping)
                argtypes[fname] = {"type": ftype, "mapping": mapping}
            else:
                argtypes[fname] = ftype
    if shim is not None:
        argtypes["@shim"] = shim
    return argtypes
5
def interface_from_py_file(interface_py_file, arguments):
    interface_py_data = _execute_py_file(arguments, -1, interface_py_file)
    # TODO: validation
    return interface_py_data

