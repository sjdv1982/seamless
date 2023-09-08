from concurrent.futures import ThreadPoolExecutor

from ..calculate_checksum import calculate_checksum
from .message import message as msg
from ..core.cache.buffer_remote import write_buffer as remote_write_buffer, can_read_buffer as remote_can_read

def calculate_file_checksum(filename: str) -> str:
    """Calculate a file checksum"""
    with open(filename, "rb") as f:
        buffer = f.read()
    checksum = calculate_checksum(buffer, hex=True)
    return checksum


def register_file(filename: str) -> str:
    """Calculate a file checksum and register its contents."""
    with open(filename, "rb") as f:
        buffer = f.read()
    checksum = calculate_checksum(buffer)
    remote_write_buffer(checksum, buffer)
    return checksum.hex()


def check_file(filename: str) -> tuple[bool, int]:
    """Check if a file needs to be written remotely
    Return the result, the checksum, and the length of the file buffer"""
    with open(filename, "rb") as f:
        buffer = f.read()
    checksum = calculate_checksum(buffer)
    result = remote_can_read(checksum)
    return result, checksum.hex(), len(buffer)


def files_to_checksums(
    filelist: list[str],
    *,
    directories = list[str],
    max_files: int | None,
    max_datasize: int | None,
    nparallel: int = 20
):
    """Convert a list of filenames to a dict of filename-to-checksum items
    In addition, each file buffer is added to the database.

    max_files: the maximum number of files to send to the database.
    max_datasize: the maximum data size (in bytes) to send to the database.
    nparallel: number of files to process simultaneously
    directories: entries in filelist that are directories instead of files
    """

    db_put = True

    if len(directories):
        raise NotImplementedError

    """
    OUTDATED
    TODO: if the database has been started locally, set db_put to false
    we can then add the filenames directly.
    This is done using a "filenames" request to the DB
    See the seamless-tools Git branch "database-filenames" 
    /OUTDATED
    """

    result = {}
    if db_put:
        with ThreadPoolExecutor(max_workers=nparallel) as executor:
            filelist2 = []
            datasize = 0
            func = check_file
            for filename, curr_result in zip(filelist, executor.map(func, filelist)):
                has_buffer, checksum, buffer_length = curr_result
                result[filename] = checksum
                if not has_buffer:
                    msg(
                        2,
                        "Not in remote storage: '{}', checksum {}, length {}".format(
                            filename, checksum, buffer_length
                        ),
                    )
                    filelist2.append(filename)
                    datasize += buffer_length
                else:
                    msg(
                        2,
                        "Already in remote storage: '{}', checksum {}, length {}".format(
                            filename, checksum, buffer_length
                        ),
                    )
        if not len(filelist2):
            return result
        if datasize > 10**9:
            size = "{:.2f} GiB".format(datasize / 10**9)
        elif datasize > 10**6:
            size = "{:.2f} MiB".format(datasize / 10**6)
        elif datasize > 10**4:
            size = "{:.2f} KiB".format(datasize / 10**3)
        else:
            size = "{} bytes".format(datasize)
        msg(0, "Upload {} files, total {}".format(len(filelist2), size))
        # TODO: confirmation from terminal, if available.
        if max_files is not None and len(filelist2) > max_files:
            raise ValueError(
                """Too many files to be uploaded without confirmation.
If you want to proceed, repeat the seamless command with '-y'."""
            )
        if max_datasize is not None and datasize > max_datasize:
            raise ValueError(
                """Too many files to be uploaded without confirmation.
If you want to proceed, repeat the seamless command with '-y'."""
            )
        filelist = filelist2
        func = register_file
    else:
        func = calculate_file_checksum
        result = {}

    with ThreadPoolExecutor(max_workers=nparallel) as executor:
        for filename, checksum in zip(filelist, executor.map(func, filelist)):
            result[filename] = checksum
    return result
