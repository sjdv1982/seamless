"""Build a Seamless bash transformation from a parsed cmd-seamless command line"""

import os
import builtins
from seamless import Checksum
from seamless.cmd.message import message as msg
from seamless.config import database
from seamless.checksum.buffer_cache import buffer_cache
from seamless.checksum.serialize import serialize_sync as serialize
from seamless.checksum.calculate_checksum import calculate_checksum
from seamless.checksum.buffer_remote import (
    write_buffer as remote_write_buffer,
    can_read_buffer,
)
from seamless.cmd.register import register_dict


def prepare_bash_code(
    code: str,
    *,
    make_executables: list[str],
    result_targets: dict | None,
    capture_stdout: bool,
):
    """Adapt cmd-seamless bash command into bash code for a bash transformation.
    Deals with:
    - If the command word refers to a file, make it executable
    - Add current directory to PATH
    - Handle stdout/stderr capture
    - Handle result capture
    """

    bashcode = ""
    if make_executables:
        has_cwd_executable = False
        make_executables_str = ""
        for make_executable in make_executables:
            if not os.path.dirname(make_executable):
                has_cwd_executable = True
            make_executables_str += f" '{make_executable}'"
        if has_cwd_executable:
            bashcode += "export PATH=./:$PATH\n"
        bashcode += f"chmod +x{make_executables_str}\n"

    if not result_targets:
        assert capture_stdout
        bashcode += "(\n" + code + "\n) > RESULT"
    else:
        code2 = code
        if capture_stdout:
            code2 = "(\n" + code + "\n) > STDOUT"
        mvcode = ""
        result_target_dirs = []
        for tar in result_targets:
            tardir = os.path.join("RESULT", os.path.dirname(tar))
            mvcode += f"mv {tar} {tardir}\n"
            if tardir not in result_target_dirs:
                result_target_dirs.append(tardir)
        bashcode += f"mkdir -p {' '.join(result_target_dirs)}\n"
        bashcode += code2 + "\n"
        bashcode += mvcode
    return bashcode


def prepare_bash_transformation(
    code: str,
    checksum_dict: dict[str, str],
    *,
    directories: list[str],
    make_executables: list[str],
    result_targets: dict | None,
    capture_stdout: bool,
    environment: dict,
    meta: dict,
    variables: dict,
    dry_run: bool = False,
) -> str:
    """Prepare a bash transformation for execution.

    Input:

    - code: bash code to execute inside a workspace. The code must write its result:
        - to /dev/stdout if result_mode is "stdout"
        - or: to a file called RESULT, if result_mode is "file"
        - or: to a directory called RESULT, if result_mode is "directory"
    - checksum_dict: checksums of the files/directories to be injected in the workspace
    - directories: list of the keys in checksum_dict that are directories
    - make_executables: list of paths where the executable bit must be set
    - capture_stdout
    - result_targets: server files containing results
    - environment
    - meta
    - variables: ....

    Returns: transformation checksum, transformation dict
    """
    from seamless.workflow.core.direct.run import register_transformation_dict

    bashcode = prepare_bash_code(
        code,
        make_executables=make_executables,
        result_targets=result_targets,
        capture_stdout=capture_stdout,
    )

    new_args = {
        "code": ("text", None, bashcode),
    }
    for attr in ("bashcode", "pins_"):
        if attr in checksum_dict:
            msg(0, f"'{attr}' cannot be in checksum dict")
            exit(1)

    transformation_dict = {"__language__": "bash"}

    if not result_targets:
        transformation_dict["__output__"] = ("result", "bytes", None)
    else:
        transformation_dict["__output__"] = ("result", "mixed", None, {"*": "##"})

    if meta:
        transformation_dict["__meta__"] = meta
    if environment:
        env_checksum = register_dict(environment, dry_run=dry_run)
        transformation_dict["__env__"] = env_checksum
    format_ = {}
    for k, v in checksum_dict.items():
        if k in directories:
            fmt = {
                "filesystem": {"optional": True, "mode": "directory"},
                "hash_pattern": {"*": "##"},
            }
            transformation_dict[k] = "mixed", None, v
        else:
            fmt = {"filesystem": {"optional": True, "mode": "file"}}
            transformation_dict[k] = "bytes", None, v
        format_[k] = fmt

    if format_:
        transformation_dict["__format__"] = format_
    if variables:
        for k, (v, celltype) in variables.items():
            if celltype in ("int", "float", "bool", "str"):
                value = getattr(builtins, celltype)(v)
            else:
                raise TypeError(celltype)
            new_args[k] = celltype, None, value

    for k, v in new_args.items():
        celltype, subcelltype, value = v
        buffer = serialize(value, celltype)
        checksum = calculate_checksum(buffer)
        if dry_run:
            buffer_cache.cache_buffer(checksum, buffer)
        else:
            remote_write_buffer(checksum, buffer)
        vv = celltype, subcelltype, checksum.hex()
        transformation_dict[k] = vv

    _, transformation_checksum = register_transformation_dict(
        transformation_dict, dry_run=dry_run
    )

    return Checksum(transformation_checksum), transformation_dict


def _run_transformation0(transformation_dict: dict, *, undo: bool, fingertip=False):
    from seamless.workflow.metalevel.unbashify import unbashify
    from seamless.workflow.core.direct.run import register_transformation_dict
    from seamless.workflow.core.cache.transformation_cache import transformation_cache

    if not fingertip:
        fingertip = False
    for k in transformation_dict:
        assert not k.startswith("SPECIAL__")
    # for caching...
    transformation_dict_py = unbashify(transformation_dict, {}, {})
    _, transformation_checksum_py = register_transformation_dict(transformation_dict_py)
    result_py = database.get_transformation_result(transformation_checksum_py)
    result_py = Checksum(result_py)
    if result_py:
        if not undo and (not fingertip or can_read_buffer(result_py)):
            return Checksum(result_py)
    # /for caching
    _, transformation_checksum = register_transformation_dict(transformation_dict)
    if undo:
        has_err = False
        if not result_py:
            try:
                result = transformation_cache.undo(transformation_checksum)
            except RuntimeError as exc:
                result = "Cannot undo: " + " ".join(exc.args)
                has_err = True
        else:
            result_checksum = result_py
            database.contest(transformation_checksum, result_checksum)
            status, response = database.contest(
                transformation_checksum_py, result_checksum
            )
            if status == 200:
                result = result_checksum
            else:
                result = response

        if has_err:
            msg(0, result)
            return None
        else:
            msg(
                2,
                f"Undo transformation {transformation_checksum.hex()} => {result.hex()}",
            )
            return Checksum(result)
    else:
        return transformation_checksum_py


def run_transformation(
    transformation_dict: dict, *, undo: bool, fingertip=False, scratch=False
):
    """Run a cmd-seamless transformation dict.
    First convert it into a bash transformation."""

    from seamless.workflow.core.direct.run import run_transformation_dict

    result0 = _run_transformation0(transformation_dict, undo=undo, fingertip=fingertip)
    if undo:
        return result0
    else:
        transformation_checksum_py = result0
        result_checksum = run_transformation_dict(
            transformation_dict, fingertip=fingertip, scratch=scratch
        )
        result_checksum = Checksum(result_checksum)
        if result_checksum:
            # while https://github.com/sjdv1982/seamless/issues/247 is open:
            database.set_transformation_result(
                transformation_checksum_py, result_checksum
            )
        return Checksum(result_checksum)


async def run_transformation_async(
    transformation_dict: dict, *, undo: bool, fingertip=False, scratch=False
):
    """Run a cmd-seamless transformation dict.
    First convert it into a bash transformation."""

    from seamless.workflow.core.direct.run import run_transformation_dict_async

    result0 = _run_transformation0(transformation_dict, undo=undo, fingertip=fingertip)
    if undo:
        return result0
    else:
        transformation_checksum_py = result0
        result_checksum = await run_transformation_dict_async(
            transformation_dict, fingertip=fingertip, scratch=scratch
        )
        result_checksum = Checksum(result_checksum)
        if result_checksum:
            # while https://github.com/sjdv1982/seamless/issues/247 is open:
            database.set_transformation_result(
                transformation_checksum_py, result_checksum
            )
        return Checksum(result_checksum)
