import os
import threading
from concurrent.futures import ThreadPoolExecutor

from seamless.cmd.exceptions import SeamlessSystemExit
from seamless.cmd.confirm import confirm_yna
from seamless.highlevel import Checksum
from seamless.core.cache.database_client import database
from seamless.core.cache.buffer_cache import buffer_cache
from seamless.cmd.message import message as msg, message_and_exit as err
from seamless.cmd.bytes2human import bytes2human
from seamless import CacheMissError

stdout_lock = threading.Lock()


def get_buffer_length(checksum):
    buffer_info = database.get_buffer_info(checksum)
    if buffer_info is None:
        return None
    return buffer_info.get("length", None)


def download_file(filename, file_checksum):
    file_checksum = Checksum(file_checksum)
    if file_checksum.value is None:
        return
    try:
        file_buffer = buffer_cache.get_buffer(file_checksum.bytes())
        if file_buffer is None:
            raise CacheMissError(file_checksum)
        buffer_cache.cache_buffer(file_checksum.bytes(), file_buffer)
    except CacheMissError:
        with stdout_lock:
            msg(
                0,
                f"Cannot download contents of file '{filename}, checksum {file_checksum}'",
            )
    try:
        with open(filename, "wb") as f:
            f.write(file_buffer)
    except Exception:
        with stdout_lock:
            msg(0, f"Cannot write to file '{filename}'")
        return


def download(
    files,
    directories,
    *,
    checksum_dict,
    max_download_size,
    max_download_files,
    auto_confirm,
    index_checksums = None,
):
    checksums = set(checksum_dict.values())
    with ThreadPoolExecutor(max_workers=100) as executor:
        buffer_lengths = {
            k: v
            for k, v in zip(
                checksums,
                executor.map(get_buffer_length, checksums),
            )
        }

    size_load_per_file = 100000
    size_load_per_unknown_file = 10000000000
    processed_downloads = {}

    for download_target in files:
        buffer_length = buffer_lengths[checksum_dict[download_target]]
        if buffer_length is None:
            size_load = size_load_per_unknown_file
            buffer_length = 0
            unknown = 1
        else:
            size_load = size_load_per_file + buffer_length
            unknown = 0
        curr_download = checksum_dict[download_target]
        processed_downloads[download_target] = size_load, buffer_length, curr_download, unknown

    for download_target in directories:
        curr_files = [f for f in checksum_dict if f.startswith(download_target + "/")]
        if not curr_files:
            continue
        buffer_length = 0
        unknown_buffer_lengths = 0
        for f in curr_files:
            bl = buffer_lengths[checksum_dict[f]]
            if bl is None:
                unknown_buffer_lengths += 1
            else:
                buffer_length += bl
        size_load = size_load_per_file * len(curr_files) + buffer_length
        size_load += size_load_per_unknown_file * unknown_buffer_lengths
        striplen = len(download_target) + 1
        curr_download = {f[striplen:]: checksum_dict[f] for f in curr_files}
        processed_downloads[download_target] = size_load, buffer_length, curr_download, unknown_buffer_lengths

    def write_checksum(filename, file_checksum):
        file_checksum = Checksum(file_checksum)
        if file_checksum.value is None:
            return
        try:
            with open(filename + ".CHECKSUM", "w") as f:
                f.write(file_checksum.hex() + "\n")
        except Exception:
            msg(0, f"Cannot write checksum to file '{filename}.CHECKSUM'")
            return

    confirm_all = False
    if auto_confirm == "yes":
        confirm_all = True
    for download_target in sorted(
        processed_downloads, key=lambda k: -processed_downloads[k][0]
    ):
        size_load, buffer_length, curr_download, unknown = processed_downloads[download_target]
        buffer_length_str = bytes2human(buffer_length)
        need_confirm = False
        if buffer_length + size_load_per_unknown_file * unknown > max_download_size:
            need_confirm = True
        if isinstance(curr_download, dict):
            nfiles = len(curr_download)
            if unknown:
                download_msg = f"'{download_target}', {nfiles} files, {buffer_length_str}, {unknown} files of length unknown"
            else:
                download_msg = f"'{download_target}', {nfiles} files, {buffer_length_str}"
        else:
            nfiles = 1
            if unknown:
                download_msg = f"'{download_target}', length unknown"
            else:
                download_msg = f"'{download_target}', {buffer_length_str}"
        if nfiles > max_download_files:
            need_confirm = True
        if confirm_all:
            need_confirm = False
        if need_confirm:
            if auto_confirm == "no":
                msg(1, f"Skip download of {download_msg}")
                continue
            try:
                confirmation = confirm_yna(f"Confirm download of {download_msg}?")
            except SeamlessSystemExit as exc:
                err(*exc.args)
            if confirmation == "no":
                msg(1, f"Skip download of {download_target}")
                continue
            if confirmation == "all":
                confirm_all = True
        if isinstance(curr_download, dict):
            os.makedirs(download_target, exist_ok=True)
            subdirs = {os.path.dirname(k) for k in curr_download}
            for subdir in subdirs:
                os.makedirs(os.path.join(download_target, subdir), exist_ok=True)
            curr_checksum_dict = {
                os.path.join(download_target, k): v for k, v in curr_download.items()
            }
            with ThreadPoolExecutor(max_workers=20) as executor:
                executor.map(
                    download_file,
                    curr_checksum_dict.keys(),
                    curr_checksum_dict.values(),
                )
            if index_checksums is not None:
                write_checksum(download_target, index_checksums[download_target])
        else:
            download_file(download_target, curr_download)
