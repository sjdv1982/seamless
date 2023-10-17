from concurrent.futures import ThreadPoolExecutor
import os

from .message import message as msg
from .register import register_file, check_file, check_buffer, remote_write_buffer
from .bytes2human import bytes2human
from .confirm import confirm_yn
from .exceptions import SeamlessSystemExit
from ..core.protocol.serialize import serialize_sync as serialize
from ..highlevel import Checksum
from .download import download_index

def strip_textdata(data):
    while 1:
        old_len = len(data)
        data = data.strip("\n")
        data = data.strip()
        if len(data) == old_len:
            break
    lines = [l for l in data.splitlines() if not l.lstrip().startswith("#")]
    return "\n".join(lines)


def read_checksum_file(filename):
    with open(filename) as f:
        checksum = f.read()
    checksum = strip_textdata(checksum)
    try:
        checksum = Checksum(checksum)
        return checksum.hex()
    except Exception:
        return None

def files_to_checksums(
    filelist: list[str],
    *,
    directories = dict[str, str],
    direct_checksum_directories = dict[str, str] | None,
    max_upload_files: int | None,
    max_upload_size: int | None,
    nparallel: int = 20,
    auto_confirm: str | None
):
    """Convert a list of filenames to a dict of filename-to-checksum items
    In addition, each file buffer is added to the database.

    max_upload_files: the maximum number of files to send to the database.
    max_upload_size: the maximum data size (in bytes) to send to the database.
    nparallel: number of files to process simultaneously
    directories: 
      keys are entries in filelist that are directories instead of files.
      values are the mapped directory paths (as they will appear on the server)
    """

    all_filelist = [f for f in filelist if f not in directories]
    if direct_checksum_directories:
        all_filelist = [f for f in all_filelist if f not in direct_checksum_directories]
    directory_files = {}
    for dirname in directories:
        directory_files[dirname] = []
        for dirpath, _, filenames in os.walk(dirname):
            assert dirpath.startswith(dirname), (dirpath, dirname)
            dirtail = dirpath[len(dirname)+1:]
            for filename in filenames:
                full_filename = os.path.join(dirpath, filename)
                mapped_filename = os.path.join(dirtail, filename)
                directory_files[dirname].append((full_filename, mapped_filename))
                all_filelist.append(full_filename)
    
    upload_buffer_lengths = {}
    deepfolder_buffers = {}
    all_result = {}
    direct_result = {}

    if direct_checksum_directories:
        for dirname, key in direct_checksum_directories.items():
            index_checksum, argname = key
            directory_files[dirname] = []
            index_data, index_buffer = download_index(index_checksum, dirname)
            deepfolder_buffers[dirname] = index_buffer
            for filename, checksum in index_data.items():
                full_filename = os.path.join(argname, filename)
                direct_result[full_filename] = checksum
    
    with ThreadPoolExecutor(max_workers=nparallel) as executor:
        upload_filelist = []
        datasize = 0
        for filename, curr_result in zip(all_filelist, executor.map(check_file, all_filelist)):
            has_buffer, checksum, buffer_length = curr_result
            all_result[filename] = checksum
            if not has_buffer:
                if checksum in upload_buffer_lengths:
                    msg(
                        2,
                        "Duplicate file: '{}', checksum {}, length {}".format(
                            filename, checksum, buffer_length
                        ),
                    )
                else:
                    msg(
                        2,
                        "Not in remote storage: '{}', checksum {}, length {}".format(
                            filename, checksum, buffer_length
                        ),
                    )
                    upload_filelist.append(filename)
                    upload_buffer_lengths[checksum] = buffer_length
            else:
                msg(
                    2,
                    "Already in remote storage: '{}', checksum {}, length {}".format(
                        filename, checksum, buffer_length
                    ),
                )
    
    for dirname in directories:
        deepfolder = {d[1]:all_result[d[0]] for d in directory_files[dirname]}
        deepfolder_buffers[dirname] = serialize(deepfolder, "plain")

    directory_indices = {}
    upload_buffers = {}
    if directories:
        with ThreadPoolExecutor(max_workers=nparallel) as executor:
            for dirname, curr_result in zip(deepfolder_buffers.keys(), executor.map(check_buffer, deepfolder_buffers.values())):
                has_buffer, checksum = curr_result
                buffer = deepfolder_buffers[dirname]
                directory_indices[dirname] = buffer, checksum
                buffer_length = len(buffer)
                all_result[dirname] = checksum
                if not has_buffer:
                    if checksum in upload_buffer_lengths:
                        msg(
                            2,
                            "Duplicate directory: Index of '{}', checksum {}, length {}".format(
                                dirname, checksum, buffer_length
                            ),
                        )
                    else:
                        msg(
                            2,
                            "Not in remote storage: index of '{}', checksum {}, length {}".format(
                                dirname, checksum, buffer_length
                            ),
                        )
                        upload_buffers[checksum] = buffer
                        upload_buffer_lengths[checksum] = buffer_length
                else:
                    msg(
                        2,
                        "Already in remote storage: index of '{}', checksum {}, length {}".format(
                            dirname, checksum, buffer_length
                        ),
                    )

    datasize = sum(upload_buffer_lengths.values())
    size = bytes2human(datasize, format='%(value).2f %(symbol)s')
    ask_confirmation = False
    if max_upload_files is not None and len(upload_buffer_lengths) > max_upload_files:
        ask_confirmation = True
    elif max_upload_size is not None and datasize > max_upload_size:
        ask_confirmation = True
    if auto_confirm == "yes":
        ask_confirmation = False
    if ask_confirmation:
        if auto_confirm == "no":
            err = "Cannot confirm upload of {} files, total {}. Exiting.".format(len(upload_buffer_lengths), size)
            raise SeamlessSystemExit(err)
        confirmation = confirm_yn("Confirm upload of {} files, total {}?".format(len(upload_buffer_lengths), size), default="no")
        if not confirmation:
            raise SeamlessSystemExit("Exiting.")
    if len(upload_buffer_lengths):
        msg(0, "Upload {} files, total {}".format(len(upload_buffer_lengths), size))
    else:
        msg(1, "Upload no files")

    if upload_filelist:
        with ThreadPoolExecutor(max_workers=nparallel) as executor:
            for filename, checksum in zip(upload_filelist, executor.map(register_file, upload_filelist)):
                assert all_result[filename] == checksum, (filename, checksum, all_result[filename])

    if upload_buffers:
        with ThreadPoolExecutor(max_workers=nparallel) as executor:
            executor.map(remote_write_buffer, upload_buffers.keys(), upload_buffers.values())

    result = {filename: all_result[filename] for filename in filelist}

    return result, direct_result, directory_indices
