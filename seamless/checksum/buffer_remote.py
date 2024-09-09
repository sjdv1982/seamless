"""Module to obtain buffers from remote sources:
- Buffer read servers
- Buffer read folders
"""

import os
import time
import traceback
import requests
from requests.exceptions import (  # pylint: disable=redefined-builtin
    ConnectionError,
    ReadTimeout,
)
from seamless import Buffer, Checksum
from seamless.checksum import buffer_read_client, buffer_write_client

_read_servers: list[str] | None = None
_read_folders: list[str] | None = None
_write_server: str | None = None

_known_buffers = set()
_written_buffers = set()

session = requests.Session()


def get_file_buffer(directory, checksum: Checksum, timeout=10) -> bytes | None:
    """Read a buffer from a buffer folder directory.
    Its filename must be equal to its checksum."""
    checksum = Checksum(checksum)

    filename = os.path.join(directory, checksum.hex())
    if os.path.exists(filename):
        with open(filename, "rb") as f:
            buf = f.read()
        buf_checksum = Buffer(buf).get_checksum().value
        if buf_checksum == checksum:
            return buf

    global_lockfile = os.path.join(directory, ".LOCK")
    lockfile = filename + ".LOCK"
    start_time = time.time()
    while 1:
        for lockf in [global_lockfile, lockfile]:
            if os.path.exists(lockf):
                break
        else:
            break
        time.sleep(0.5)
        if time.time() - start_time > timeout:
            return
    if not os.path.exists(filename):
        return
    with open(filename, "rb") as f:
        buf = f.read()
    buf_checksum = Buffer(buf).get_checksum()
    if buf_checksum != checksum:
        # print("WARNING: '{}' has the wrong checksum".format(filename))
        return
    return buf


def get_buffer(checksum: Checksum) -> bytes | None:
    """Retrieve the buffer from remote sources.
    First all buffer read folders are queried.
    Then all buffer read servers are queried."""
    checksum = Checksum(checksum)
    if not checksum:
        return None
    if _read_servers is None and _read_folders is None:
        return None
    if _read_folders is not None:
        for folder in _read_folders:
            try:
                buf = get_file_buffer(folder, checksum)
                if buf is not None:
                    return buf
            except Exception:
                traceback.print_exc()
                return

    for server in _read_servers:
        result = buffer_read_client.get(session, server, checksum.hex())
        if result is not None:
            _known_buffers.add(checksum)
            return result


def get_filename(checksum: Checksum) -> str | None:
    """Get the filename where a buffer is stored.
    This can only be provided by a buffer read folder.
    All buffer read folders are queried in order."""
    checksum = Checksum(checksum)
    if not checksum:
        return None
    if _read_folders is None:
        return None
    for folder in _read_folders:
        filename = os.path.join(folder, checksum.hex())
        if os.path.exists(filename):
            return filename
    return None


def get_directory(checksum: Checksum) -> str | None:
    """Get the directory where a deep buffer is deployed.
    This can only be provided by a buffer read folder.
    Deployed deep buffers are assumed to be in:
      <buffer_read_folder>/deployed/<checksum>.
    All buffer read folders are queried in order."""

    checksum = Checksum(checksum)
    if not checksum:
        return None
    if _read_folders is None:
        return None
    for folder in _read_folders:
        dirname = os.path.join(folder, "deployed", checksum.hex())
        if os.path.exists(dirname):
            return dirname
    return None


def write_buffer(checksum: Checksum, buffer: bytes) -> None:
    """Write the buffer to the buffer write server, if one exists."""
    checksum = Checksum(checksum)
    if not checksum:
        return None
    if _write_server is None:
        return
    if checksum in _written_buffers:
        return
    _written_buffers.add(checksum)
    # print("WRITE BUFFER", checksum.hex())
    if buffer_write_client.has(session, _write_server, checksum):
        return
    buffer_write_client.write(session, _write_server, checksum, buffer)


def is_known(checksum: Checksum) -> bool:
    """Returns if a buffer is known to be known remotely, from cache."""
    checksum = Checksum(checksum)
    if not checksum:
        return True
    return checksum in _known_buffers or checksum in _written_buffers


def remote_has_checksum(checksum: Checksum) -> bool:
    """Returns if a buffer is known remotely. This is queried directly."""
    checksum = Checksum(checksum)
    if _read_folders is not None:
        for folder in _read_folders:
            filename = os.path.join(folder, checksum.hex())
            if os.path.exists(filename):
                _known_buffers.add(checksum)
                return True
    if _read_servers is not None:
        for server in _read_servers:
            if buffer_read_client.has(session, server, checksum):
                _known_buffers.add(checksum)
                return True
    return False


def can_read_buffer(checksum: Checksum) -> bool:
    """Returns if a buffer is known remotely.
    A local cache of buffers that are known to be known remotely
     is also queried."""
    checksum = Checksum(checksum)
    if is_known(checksum):
        return True
    return remote_has_checksum(checksum)


def can_write() -> bool:
    """Returns if it is possible to write buffers remotely"""
    return _write_server is not None


def set_read_buffer_folders(read_buffer_folders):
    """Set all read buffer folders"""
    global _read_folders
    if read_buffer_folders:
        if _read_folders:
            for old_folder in _read_servers:
                if old_folder not in read_buffer_folders:
                    _known_buffers.clear()
                    break
        _read_folders = [os.path.abspath(f) for f in read_buffer_folders]
    else:
        _read_folders = None


def add_read_buffer_folder(read_buffer_folder):
    """Add a read buffer folder"""
    global _read_folders
    f = os.path.abspath(read_buffer_folder)
    if _read_folders:
        _read_folders.append(f)
    else:
        _read_folders = [f]


def set_read_buffer_servers(read_buffer_servers):
    """Set all read buffer servers"""
    global _read_servers
    if read_buffer_servers:
        if _read_servers:
            for old_server in _read_servers:
                if old_server not in read_buffer_servers:
                    _known_buffers.clear()
                    break
        _read_servers = read_buffer_servers
    else:
        _known_buffers.clear()
        _read_servers = None


def add_read_buffer_server(read_buffer_server):
    """Add a read buffer server"""
    global _read_servers
    if _read_servers:
        _read_servers.append(read_buffer_server)
    else:
        _read_servers = [read_buffer_server]


def set_write_buffer_server(write_buffer_server):
    """Set the write buffer server.
    There can only be one."""
    global _write_server
    if write_buffer_server == _write_server:
        return

    if write_buffer_server:
        ntrials = 5
        for trials in range(ntrials):
            try:
                buffer_write_client.has(
                    session, write_buffer_server, b"0" * 32, timeout=3
                )
            except ValueError:
                pass
            except (ConnectionError, ReadTimeout):
                if trials < ntrials - 1:
                    continue
                raise ConnectionError(write_buffer_server) from None
            break
        if _write_server is not None:
            _written_buffers.clear()
        _write_server = write_buffer_server
    else:
        write_buffer_server = None


def has_readwrite_servers() -> bool:
    """Check if there is a write buffer server and at least one read buffer server"""
    return _write_server is not None and len(_read_servers)
