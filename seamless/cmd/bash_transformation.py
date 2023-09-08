from ..core.protocol.serialize import serialize_sync as serialize
from ..calculate_checksum import calculate_checksum
from ..core.cache.buffer_remote import write_buffer as remote_write_buffer
from ..core.direct.run import run_transformation_dict

def run_bash_transformation(
    code: str,
    checksum_dict: dict[str, str],
    *,
    directories: list[str],
    result_mode: str
) -> str:
    """Runs a bash transformation.

    Input:

    - code: bash code to execute inside a workspace. The code must write its result:
        - to /dev/stdout if result_mode is "stdout"
        - or: to a file called RESULT, if result_mode is "file"
        - or: to a directory called RESULT, if result_mode is "directory"
    - checksum_dict: checksums of the files/directories to be injected in the workspace
    - directories: list of the keys in checksum_dict that are directories
    """
    if result_mode not in ("file", "directory", "stdout"):
        raise TypeError(result_mode)

    if result_mode == "directory":
        raise NotImplementedError

    if len(directories):
        raise NotImplementedError

    if result_mode == "stdout":
        bashcode = "(\n" + code + "\n) > RESULT"
    else:
        raise NotImplementedError

    new_args = {
        "code": ("text", None, bashcode),
    }
    assert "bashcode" not in checksum_dict  # TODO: workaround
    assert "pins_" not in checksum_dict  # TODO: workaround

    transformation_dict = {
        "__language__": "bash",
        "__output__": ("result", "bytes", None)
    }
    for k,v in checksum_dict.items():
        transformation_dict[k] = "bytes", None, v

    for k,v in new_args.items():
        celltype, subcelltype, value = v
        buffer = serialize(value, celltype)
        checksum = calculate_checksum(buffer)
        remote_write_buffer(checksum, buffer)
        vv = celltype, subcelltype, checksum.hex()
        transformation_dict[k] = vv

    result_checksum = run_transformation_dict(transformation_dict, fingertip=False)
    return result_checksum

    # TODO: add support for filesystem __format__ annotation
