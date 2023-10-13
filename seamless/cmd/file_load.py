from concurrent.futures import ThreadPoolExecutor

from .message import message as msg
from .register import register_file, check_file, calculate_file_checksum
from .bytes2human import bytes2human
from .confirm import confirm_yn
from .exceptions import SeamlessSystemExit

def files_to_checksums(
    filelist: list[str],
    *,
    directories = list[str],
    max_upload_files: int | None,
    max_upload_size: int | None,
    nparallel: int = 20,
    always_yes : bool = False
):
    """Convert a list of filenames to a dict of filename-to-checksum items
    In addition, each file buffer is added to the database.

    max_upload_files: the maximum number of files to send to the database.
    max_upload_size: the maximum data size (in bytes) to send to the database.
    nparallel: number of files to process simultaneously
    directories: entries in filelist that are directories instead of files
    """

    db_put = True

    if len(directories):
        raise NotImplementedError

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
        size = bytes2human(datasize, format='%(value).2f %(symbol)s')
        ask_confirmation = False
        if max_upload_files is not None and len(filelist2) > max_upload_files:
            ask_confirmation = True
        elif max_upload_size is not None and datasize > max_upload_size:
            ask_confirmation = True
        if always_yes:
            ask_confirmation = False
        if ask_confirmation:
            confirmation = confirm_yn("Confirm upload of {} files, total {}?".format(len(filelist2), size), default="no")
            if not confirmation:
                raise SeamlessSystemExit("Exiting.")
        msg(0, "Upload {} files, total {}".format(len(filelist2), size))
        func = register_file
    else:
        func = calculate_file_checksum

    with ThreadPoolExecutor(max_workers=nparallel) as executor:
        for filename, checksum in zip(filelist, executor.map(func, filelist)):
            if filename in result:
                continue
            result[filename] = checksum
    return result
