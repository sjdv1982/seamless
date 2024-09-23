"""Canonical commands from interface files"""

from copy import copy
import os
import sys

from . import interface
from .bash_transformation import prepare_bash_code


def build_transformer_dict(tool, *, command=None):
    """Build transformer dict using canonical command"""
    _, interface_yaml, interface_py_file, _ = interface.locate_files([tool])
    if interface_yaml is None:
        raise ValueError(f"Cannot find .SEAMLESS.yaml file for '{tool}'")
    interface_data = interface.load(interface_yaml)
    canonical = interface_data.get("canonical")
    if not canonical:
        raise ValueError("'{tool}' has an interface file, but no canonical commands")
    canonical_commands = [c["command"] for c in canonical]
    if command is None and len(canonical) > 1:
        raise ValueError(
            """Multiple canonical commands available.
Please choose one and provide it as the "command" argument.
                         
    {}                         
""".format(
                "\n    ".join(canonical_commands)
            )
        )
    if command not in canonical_commands:
        raise ValueError(
            """'command' must be one of the tool's canonical commands:
                         
    {}                         
""".format(
                "\n    ".join(canonical_commands)
            )
        )

    for canon in canonical:
        if canon["command"] == command:
            break
    else:
        raise AssertionError
    old_path = copy(sys.path)
    tool_path = os.path.dirname(os.path.abspath(tool))
    try:
        if canon.get("executable"):
            sys.path.append(tool_path)
            argindex = 0
        else:
            argindex = 1

        cmd = canon.get("dummy_command", command).split()
        argtypes, result_targets = interface.get_argtypes_and_results(
            interface_yaml, interface_py_file, argindex, cmd, original_binary=cmd[0]
        )
    finally:
        sys.path[:] = old_path
    order = argtypes["@order"]

    buffers = {}
    result_celltype = (
        "folder" if result_targets and len(result_targets) > 1 else "bytes"
    )
    tf_dict = {}

    for k, v in argtypes.items():
        if k == "@order":
            continue
        if v["type"] != "file":  # pylint: disable=E1126  # bug in pylint?
            raise NotImplementedError
        if k not in order or order.index(k) == argindex:
            fname = v.get("mapping", k)
            with open(fname, "rb") as f:
                buf = f.read()
            buffers[k] = buf
        else:
            tf_dict[k] = "bytes"
    for var in canon.get("variables"):
        tf_dict[var["name"]] = var["celltype"]

    make_executables = []
    if canon.get("executable"):
        make_executables.append(cmd[0])

    bashcode = prepare_bash_code(
        code=command,
        make_executables=make_executables,
        result_targets=result_targets,
        capture_stdout=not result_targets,
    )
    return tf_dict, result_celltype, buffers, bashcode
