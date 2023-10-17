from ..calculate_checksum import calculate_checksum
from seamless.core.protocol.json import json_dumps
from ..core.cache.buffer_remote import write_buffer as remote_write_buffer, can_read_buffer as remote_can_read
from ..core.cache.database_client import database
from ..core.buffer_info import BufferInfo

def calculate_file_checksum(filename: str) -> str:
    """Calculate a file checksum"""
    # TODO: streaming?
    with open(filename, "rb") as f:
        buffer = f.read()
    checksum = calculate_checksum(buffer, hex=True)
    return checksum

def register_buffer_length(buffer: bytes, checksum: bytes) -> str:
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

def register_buffer(buffer: bytes) -> str:
    checksum = calculate_checksum(buffer)
    register_buffer_length(buffer, checksum)
    remote_write_buffer(checksum, buffer)
    return checksum.hex()

def register_dict(data: dict) -> str:
    buffer = json_dumps(data, as_bytes=True) + b"\n"
    return register_buffer(buffer)

def check_file(filename: str) -> tuple[bool, str, int]:
    """Check if a file needs to be written remotely
    Return the result and the checksum, and the length of the file buffer"""
    with open(filename, "rb") as f:
        buffer = f.read()
    result, checksum = check_buffer(buffer)
    return result, checksum, len(buffer)

def register_file(filename: str) -> str:
    """Calculate a file checksum and register its contents."""
    with open(filename, "rb") as f:
        buffer = f.read()
    return register_buffer(buffer)

def check_buffer(buffer: bytes) -> tuple[bool, str]:
    """Check if a buffer is present remotely
    If so, make sure its length is in the database
    Return the result and the checksum"""
    checksum = calculate_checksum(buffer)
    result = remote_can_read(checksum)
    if result:
        register_buffer_length(buffer, checksum)
    return result, checksum.hex()
