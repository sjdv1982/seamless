import os
import pathlib
import threading
import time

from seamless import Checksum, CacheMissError
from seamless.checksum.buffer_cache import buffer_cache
from seamless.checksum.deserialize import deserialize_sync as deserialize
from seamless.cmd.download import download
from seamless.checksum.json import json_dumps
from seamless.checksum.calculate_checksum import calculate_checksum

stdout_lock = threading.Lock()


def write_future(
    workdir, transformation_checksum, filename, result_target, *, msg_func
):
    filename = os.path.join(workdir, filename)
    try:
        with open(filename + ".FUTURE", "w") as f:
            f.write(f"{transformation_checksum}.{result_target}\n")
    except Exception:
        msg_func(0, f"Cannot write future file '{filename}.FUTURE'")
        return


def touch_future(workdir, filename, *, msg_func):
    filename = os.path.join(workdir, filename)
    try:
        pathlib.Path(filename + ".FUTURE").touch()
    except Exception:
        msg_func(0, f"Cannot touch future file '{filename}.FUTURE'")
        return


def remove_future(workdir, filename, *, msg_func):
    filename = os.path.join(workdir, filename)
    try:
        os.unlink(filename + ".FUTURE")
    except Exception:
        msg_func(0, f"Cannot remove future file '{filename}.FUTURE'")
        return


def maintain_futures(
    workdir, transformation_checksum, result_targets, *, delete_futures_event, msg_func
):
    for result_target, download_target in result_targets.items():
        if download_target is None:
            download_target = result_target
        write_future(
            workdir,
            transformation_checksum,
            download_target,
            result_target,
            msg_func=msg_func,
        )

    count = 0
    while not delete_futures_event.is_set():
        time.sleep(1)
        count += 1
        if count == 30:
            count = 0
            for result_target, download_target in result_targets.items():
                if download_target is None:
                    download_target = result_target
                touch_future(workdir, download_target, msg_func=msg_func)

    for result_target, download_target in result_targets.items():
        if download_target is None:
            download_target = result_target
        remove_future(workdir, download_target, msg_func=msg_func)


def write_result_index(workdir, dirname, index, *, msg_func):
    dirname = os.path.join(workdir, dirname)
    try:
        index_buffer = json_dumps(index, as_bytes=True) + b"\n"
        with open(dirname + ".INDEX", "wb") as f:
            f.write(index_buffer)
    except Exception:
        msg_func(0, f"Cannot write directory result index to file '{dirname}.INDEX'")
        return
    index_checksum = calculate_checksum(index_buffer)
    return index_checksum


def write_result_checksum(workdir, filename, file_checksum, *, msg_func):
    file_checksum = Checksum(file_checksum)
    if file_checksum.value is None:
        return
    filename = os.path.join(workdir, filename)
    try:
        with open(filename + ".CHECKSUM", "w") as f:
            f.write(file_checksum.hex() + "\n")
    except Exception:
        msg_func(0, f"Cannot write checksum to result file '{filename}.CHECKSUM'")
        return


def download_result(filename, file_checksum, *, msg_func):
    file_checksum = Checksum(file_checksum)
    if file_checksum.value is None:
        return
    try:
        file_buffer = buffer_cache.get_buffer(file_checksum.bytes())
        if file_buffer is None:
            raise CacheMissError(file_checksum)
    except CacheMissError:
        with stdout_lock:
            msg_func(
                0, f"Cannot obtain contents of result file '{filename}', CacheMissError"
            )
    try:
        with open(filename, "wb") as f:
            f.write(file_buffer)
    except Exception:
        with stdout_lock:
            msg_func(0, f"Cannot write to result file '{filename}'")
        return


def get_result_buffer(
    result_checksum, *, do_fingertip, do_scratch, has_result_targets, err_func
):
    from seamless.workflow.core.direct.run import fingertip

    try:
        if do_fingertip or do_scratch:
            result_buffer = fingertip(result_checksum.bytes())
        else:
            result_buffer = buffer_cache.get_buffer(result_checksum.bytes())
        if result_buffer is None:
            raise CacheMissError(result_checksum)
        cannot_download = False
    except CacheMissError:
        # traceback.print_exc(limit=1)
        # exit(1)
        cannot_download = True

    if has_result_targets and cannot_download:
        err_func(
            "Cannot download result. Cannot write checksum for one or more result targets"
        )
        return None
    return result_buffer


async def get_result_buffer_async(
    result_checksum, *, do_fingertip, do_scratch, has_result_targets, err_func
):
    from seamless.workflow.core.direct.run import fingertip_async

    try:
        if do_fingertip or do_scratch:
            result_buffer = await fingertip_async(result_checksum.bytes())
        else:
            result_buffer = await buffer_cache.get_buffer_async(result_checksum.bytes())
        if result_buffer is None:
            raise CacheMissError(result_checksum)
        cannot_download = False
    except CacheMissError:
        # traceback.print_exc(limit=1)
        # exit(1)
        cannot_download = True

    if cannot_download:
        if has_result_targets:
            err_func(
                "Cannot download result. Cannot write checksum for one or more result targets"
            )
        else:
            err_func("Cannot download result")
        return None
    return result_buffer


def get_results(
    result_targets,
    result_checksum,
    result_buffer,
    *,
    workdir,
    do_scratch,
    do_download,
    do_capture_stdout,
    max_download_size,
    max_download_files,
    do_auto_confirm,
    msg_func,
):
    if result_targets:

        result_checksum_dict = deserialize(
            result_buffer, result_checksum.bytes(), "plain", copy=False
        )

        files_to_download = []
        directories_to_download = []
        download_checksum_dict = {}

        for _result_target, _download_target in result_targets.items():
            if _download_target is None:
                _download_target = _result_target
            if _result_target in result_checksum_dict:  # file
                _result = result_checksum_dict[_result_target]
                download_checksum_dict[_download_target] = _result
                write_result_checksum(
                    workdir, _download_target, _result, msg_func=msg_func
                )
                files_to_download.append(_download_target)
            else:
                curr_files = [
                    f
                    for f in result_checksum_dict
                    if f.startswith(_result_target + "/")
                ]
                if not len(curr_files):
                    msg_func(0, f"No result for '{_download_target}' was returned")
                    continue
                striplen = len(_result_target) + 1
                result = {f[striplen:]: result_checksum_dict[f] for f in curr_files}

                _index_checksum = write_result_index(
                    workdir, _download_target, result, msg_func=msg_func
                )
                if _index_checksum is not None:
                    write_result_checksum(
                        workdir, _download_target, _index_checksum, msg_func=msg_func
                    )

                for _f in result:
                    _ff = _download_target + "/" + _f
                    download_checksum_dict[_ff] = result[_f]
                directories_to_download.append(_download_target)

        if do_download and not do_scratch:
            download(
                files_to_download,
                directories_to_download,
                checksum_dict=download_checksum_dict,
                max_download_size=max_download_size,
                max_download_files=max_download_files,
                auto_confirm=do_auto_confirm,
            )
        return None
    else:
        assert do_capture_stdout

        try:
            result = result_buffer.decode()
        except UnicodeDecodeError:
            result = result_buffer
        return result
