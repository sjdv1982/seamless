"""Register buffers:
- Write them remotely
- Write their buffer length"""

import os
from seamless.checksum.calculate_checksum import calculate_checksum
from seamless.checksum.json import json_dumps
from seamless.checksum.buffer_remote import (
    write_buffer as remote_write_buffer,
    can_read_buffer as remote_can_read,
)
from seamless.checksum.buffer_cache import buffer_cache
from seamless.checksum.database_client import database
from seamless.checksum.buffer_info import BufferInfo


def register_buffer_length(buffer: bytes, checksum: bytes) -> str:
    """Write the buffer length of a known buffer into a remote database"""
    buffer_info = database.get_buffer_info(checksum)
    write_buffer_info = False
    if buffer_info is None:
        buffer_info = BufferInfo(checksum)
        write_buffer_info = True
    if buffer_info.length != len(buffer):
        buffer_info.length = len(buffer)
        write_buffer_info = True
    if write_buffer_info:
        database.set_buffer_info(checksum, buffer_info)


def _register_buffer(
    checksum: bytes, buffer: bytes, destination_folder, dry_run: bool = False
):
    if dry_run:
        buffer_cache.cache_buffer(checksum, buffer)
    elif destination_folder is not None:
        filename = os.path.join(destination_folder, checksum.hex())
        with open(filename, "wb") as f:
            f.write(buffer)
    else:
        remote_write_buffer(checksum, buffer)


def register_buffer(
    buffer: bytes, destination_folder: str | None = None, dry_run: bool = False
) -> str:
    """Register a buffer:
    - Write the buffer remotely
    - Write the buffer length into a remote database"""
    checksum = calculate_checksum(buffer)
    register_buffer_length(buffer, checksum)
    _register_buffer(checksum, buffer, destination_folder, dry_run=dry_run)
    return checksum.hex()


def register_dict(
    data: dict, destination_folder: str | None = None, dry_run: bool = False
) -> str:
    """Register the buffer underlying a dict
    The dict is serialized to a celltype="plain" buffer (JSON serialization)
    """
    buffer = json_dumps(data, as_bytes=True) + b"\n"
    return register_buffer(
        buffer, destination_folder=destination_folder, dry_run=dry_run
    )


def check_file(filename: str) -> tuple[bool, str, int]:
    """Check if a file needs to be written remotely
    Return the result and the checksum, and the length of the file buffer
    """
    with open(filename, "rb") as f:
        buffer = f.read()
    result, checksum = check_buffer(buffer)
    return result, checksum, len(buffer)


def register_file(filename: str, destination_folder: str | None = None, hardlink: bool = False) -> str:
    """Calculate a file checksum and register its contents.

    destination_folder: instead of uploading to a buffer server, write to this folder
    """
    with open(filename, "rb") as f:
        buffer = f.read()
        
    if hardlink and destination_folder is not None:
        checksum = calculate_checksum(buffer)
        destlink = os.path.join(destination_folder, checksum.hex())
        os.link(filename, destlink)
        return checksum.hex()
    else:
        return register_buffer(buffer, destination_folder=destination_folder)


def check_buffer(buffer: bytes) -> tuple[bool, str]:
    """Check if a buffer is present remotely
    If so, make sure its length is in the database
    Return the result and the checksum"""
    checksum = calculate_checksum(buffer)
    result = remote_can_read(checksum)
    if result:
        register_buffer_length(buffer, checksum)
    return result, checksum.hex()
