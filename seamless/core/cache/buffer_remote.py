import requests
from typing import Optional
from seamless.util import parse_checksum
import os
import time
import traceback
from requests.exceptions import ConnectionError

_read_servers:Optional[list[str]] = None
_read_folders:Optional[list[str]] = None
_write_server:Optional[str] = None

_known_buffers = set()
_written_buffers = set()

session = requests.Session()

def get_file_buffer(directory, checksum, timeout=10):
    from seamless import calculate_checksum
    checksum = parse_checksum(checksum, as_bytes=True)

    filename = os.path.join(directory, checksum.hex())
    if os.path.exists(filename):
        with open(filename, "rb") as f:
            buf = f.read()
        buf_checksum = calculate_checksum(buf)
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
    buf_checksum = calculate_checksum(buf)
    if buf_checksum != checksum:
        #print("WARNING: '{}' has the wrong checksum".format(filename))
        return
    return buf

def get_buffer(checksum):
    checksum = parse_checksum(checksum, as_bytes=True)
    if checksum is None:
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

def get_filename(checksum):
    checksum = parse_checksum(checksum, as_bytes=True)
    if checksum is None:
        return None
    if _read_folders is None:
        return None
    raise NotImplementedError

def get_directory(checksum):
    checksum = parse_checksum(checksum, as_bytes=True)
    if checksum is None:
        return None
    if _read_folders is None:
        return None
    raise NotImplementedError

def write_buffer(checksum, buffer):
    checksum = parse_checksum(checksum, as_bytes=True)
    if checksum is None:
        return None
    if _write_server is None:
        return
    if checksum in _written_buffers:
        return
    _written_buffers.add(checksum)
    if buffer_write_client.has(session, _write_server, checksum):
        return
    buffer_write_client.write(session, _write_server, checksum, buffer)

def is_known(checksum):
    checksum = parse_checksum(checksum, as_bytes=True)
    if checksum is None:
        return True
    return checksum in _known_buffers or checksum in _written_buffers
    
def _has_checksum(checksum):
    checksum = parse_checksum(checksum, as_bytes=True)
    if _read_folders is not None:
        for folder in _read_folders:
            filename = os.path.join(folder, checksum.hex())
            if os.path.exists(filename):
                return True
    if _read_servers is not None:
        for server in _read_servers:
            if buffer_read_client.has(session, server, checksum):
                return True
    return False

def can_read_buffer(checksum):
    checksum = parse_checksum(checksum, as_bytes=True)
    if is_known(checksum):
        return True
    return _has_checksum(checksum)

def can_write():
    return _write_server is not None

def set_read_buffer_folders(read_buffer_folders):
    global _read_folders
    if read_buffer_folders:
        _read_folders = read_buffer_folders
    else:
        _read_folders = None

def set_read_buffer_servers(read_buffer_servers):
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

def set_write_buffer_server(write_buffer_server):
    global _write_server
    if write_buffer_server:
        try:
            buffer_write_client.has(session, write_buffer_server, b'0' * 32)
        except ValueError:
            pass
        except ConnectionError:
            raise ConnectionError(write_buffer_server) from None
        if _write_server is not None:
            _written_buffers.clear()
        _write_server = write_buffer_server
    else:
        write_buffer_server = None

def has_readwrite_servers():
    return _write_server is not None and len(_read_servers)

from . import buffer_read_client, buffer_write_client