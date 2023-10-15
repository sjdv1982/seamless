import os
import sys
from ..core.protocol.serialize import serialize_sync as serialize
from ..calculate_checksum import calculate_checksum
from ..core.cache.buffer_remote import write_buffer as remote_write_buffer, can_read_buffer
from ..core.direct.run import run_transformation_dict, register_transformation_dict
from ..core.cache.transformation_cache import transformation_cache
from seamless.cmd.register import register_dict

def prepare_bash_code(
    code: str,
    *,
    make_executables: list[str],
    result_targets: dict | None,
    capture_stdout: bool,
):

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
) -> str:
    """Prepared a bash transformation for execution.

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

    bashcode = prepare_bash_code(
        code,
        make_executables = make_executables,
        result_targets = result_targets,
        capture_stdout = capture_stdout
    )

    new_args = {
        "code": ("text", None, bashcode),
    }
    assert "bashcode" not in checksum_dict  # TODO: workaround
    assert "pins_" not in checksum_dict  # TODO: workaround
    
    transformation_dict = {
        "__language__": "bash"
    }

    if not result_targets:
        transformation_dict["__output__"] = ("result", "bytes", None)
    else:
        transformation_dict["__output__"] = ("result", "mixed", None, {"*": "##"})

    if meta:
        transformation_dict["__meta__"] = meta
    if environment:
        env_checksum = register_dict(environment)
        transformation_dict["__env__"] = env_checksum
    format = {}
    for k,v in checksum_dict.items():
        if k in directories:
            fmt = {
                "filesystem": {
                    "optional": True,
                    "mode": "directory"
                },
                "hash_pattern": {"*": "##"}
            }
            transformation_dict[k] = "mixed", None, v
        else:
            fmt = {
                "filesystem": {
                    "optional": True,
                    "mode": "file"
                }
            }
            transformation_dict[k] = "bytes", None, v
        format[k] = fmt

    if format:
        transformation_dict["__format__"] = format
    if variables:
        for k, (v, celltype) in variables.items():
            if celltype in ("int", "float", "bool", "str"):
                value = eval(celltype)(v)
            else:
                raise TypeError(celltype)
            new_args[k] = celltype, None, value

    for k,v in new_args.items():
        celltype, subcelltype, value = v
        buffer = serialize(value, celltype)
        checksum = calculate_checksum(buffer)
        remote_write_buffer(checksum, buffer)
        vv = celltype, subcelltype, checksum.hex()
        transformation_dict[k] = vv

    _, transformation_checksum = register_transformation_dict(transformation_dict)
 
    # TODO: add support for filesystem __format__ annotation
    return Checksum(transformation_checksum), transformation_dict

def run_transformation(transformation_dict, *, undo, fingertip=False):
    if not fingertip:
        fingertip = False
    transformation_dict_py = unbashify(transformation_dict, {}, {})
    _, transformation_checksum_py = register_transformation_dict(transformation_dict_py)
    result_py = database.get_transformation_result(transformation_checksum_py)
    if result_py is not None:
        if not fingertip or can_read_buffer(result_py):
            return Checksum(result_py)
    _, transformation_checksum = register_transformation_dict(transformation_dict)
    if undo:
        try:
            result = transformation_cache.undo(transformation_checksum)
        except RuntimeError as exc:
            result = "Cannot undo: " + " ".join(exc.args)
        if isinstance(result, str):
            msg(0, result)
            return None
        elif isinstance(result, bytes):
            msg(2, f"Undo transformation {transformation_checksum.hex()} => {result.hex()}")
            return Checksum(result)
    else:
        result_checksum = run_transformation_dict(transformation_dict, fingertip=fingertip)
        if result_checksum is not None:
            database.set_transformation_result(transformation_checksum_py, result_checksum)
        return Checksum(result_checksum)


from seamless.cmd.message import message as msg
from seamless.highlevel import Checksum
from seamless.metalevel.unbashify import unbashify
from seamless.config import database