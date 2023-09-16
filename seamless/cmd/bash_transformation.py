import os
import sys
from ..core.protocol.serialize import serialize_sync as serialize
from ..calculate_checksum import calculate_checksum
from ..core.cache.buffer_remote import write_buffer as remote_write_buffer
from ..core.direct.run import run_transformation_dict, register_transformation_dict
from ..core.cache.transformation_cache import transformation_cache
from seamless.cmd.register import register_dict

def prepare_bash_transformation(
    code: str,
    checksum_dict: dict[str, str],
    *,
    directories: list[str],
    result_targets: list[str] | None,
    capture_stdout: bool,
    environment: dict
) -> str:
    """Prepared a bash transformation for execution.

    Input:

    - code: bash code to execute inside a workspace. The code must write its result:
        - to /dev/stdout if result_mode is "stdout"
        - or: to a file called RESULT, if result_mode is "file"
        - or: to a directory called RESULT, if result_mode is "directory"
    - checksum_dict: checksums of the files/directories to be injected in the workspace
    - directories: list of the keys in checksum_dict that are directories
    - capture_stdout
    - result_targets: server files containing results
    - environment

    Returns: transformation checksum, transformation dict
    """
    if len(directories):
        raise NotImplementedError

    if capture_stdout:
        assert not result_targets
        bashcode = "(\n" + code + "\n) > RESULT"
    else:
        assert len(result_targets)
        if len(result_targets) == 1:
            bashcode = code + f"; mv -f {result_targets[0]} RESULT"
        else:
            mvcode = ""
            result_target_dirs = []
            for tar in result_targets:
                tardir = os.path.join("RESULT", os.path.dirname(tar))
                mvcode += f"mv {tar} {tardir}; "
                if tardir not in result_target_dirs:
                    result_target_dirs.append(tardir)                 
            bashcode = f"mkdir -p {' '.join(result_target_dirs)}\n"
            bashcode += code + "\n"
            bashcode += mvcode[:-2]

    new_args = {
        "code": ("text", None, bashcode),
    }
    assert "bashcode" not in checksum_dict  # TODO: workaround
    assert "pins_" not in checksum_dict  # TODO: workaround
    
    transformation_dict = {
        "__language__": "bash"
    }
    if capture_stdout or len(result_targets) == 1:
        transformation_dict["__output__"] = ("result", "bytes", None)
    else:
        transformation_dict["__output__"] = ("result", "mixed", None, {"*": "##"})
    if environment:
        env_checksum = register_dict(environment)
        transformation_dict["__env__"] = env_checksum
    for k,v in checksum_dict.items():
        transformation_dict[k] = "bytes", None, v

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

def run_transformation(transformation_dict, *, undo):
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
        result_checksum = run_transformation_dict(transformation_dict, fingertip=False)
        return Checksum(result_checksum)


from seamless.cmd.message import message as msg
from seamless.highlevel import Checksum