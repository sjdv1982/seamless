import requests
from seamless.util import parse_checksum
import os
import time
import traceback
from seamless import Buffer
from requests.exceptions import ConnectionError, ReadTimeout

_read_servers:list[str]|None = None
_read_folders:list[str]|None = None
_write_server:str|None = None

_known_buffers = set()
_written_buffers = set()

session = requests.Session()

def get_file_buffer(directory, checksum, timeout=10):
    checksum = parse_checksum(checksum, as_bytes=True)

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
    for folder in _read_folders:
        filename = os.path.join(folder, checksum.hex())
        if os.path.exists(filename):
            return filename
    return None

def get_directory(checksum):
    checksum = parse_checksum(checksum, as_bytes=True)
    if checksum is None:
        return None
    if _read_folders is None:
        return None
    for folder in _read_folders:
        dirname = os.path.join(folder, "deployed", checksum.hex())
        if os.path.exists(dirname):
            return dirname
    return None

def write_buffer(checksum, buffer):
    checksum = parse_checksum(checksum, as_bytes=True)
    if checksum is None:
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

def is_known(checksum):
    checksum = parse_checksum(checksum, as_bytes=True)
    if checksum is None:
        return True
    return checksum in _known_buffers or checksum in _written_buffers
    
def remote_has_checksum(checksum):
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
    return remote_has_checksum(checksum)

def can_write():
    return _write_server is not None

def set_read_buffer_folders(read_buffer_folders):
    global _read_folders
    if read_buffer_folders:
        _read_folders = [os.path.abspath(f) for f in read_buffer_folders]
    else:
        _read_folders = None

def add_read_buffer_folder(read_buffer_folder):
    global _read_folders
    f = os.path.abspath(read_buffer_folder)
    if _read_folders:
        _read_folders.append(f)
    else:
        _read_folders = [f]

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

def add_read_buffer_server(read_buffer_server):
    global _read_servers
    if _read_servers:
        _read_servers.append(read_buffer_server)
    else:
        _read_servers = [read_buffer_server]


def set_write_buffer_server(write_buffer_server):
    global _write_server
    if write_buffer_server:
        ntrials = 5
        for trials in range(ntrials):
            try:
                buffer_write_client.has(session, write_buffer_server, b'0' * 32, timeout=3)
            except ValueError:
                pass
            except (ConnectionError, ReadTimeout):
                if trials < ntrials - 1:
                    continue
                raise ConnectionError(write_buffer_server) from None
        if _write_server is not None:
            _written_buffers.clear()
        _write_server = write_buffer_server
    else:
        write_buffer_server = None

def has_readwrite_servers():
    return _write_server is not None and len(_read_servers)

from . import buffer_read_client, buffer_write_client