import os
import sys
from urllib.parse import urlparse
from abc import ABC, abstractmethod
import requests
from traceback import print_exc

import logging
logger = logging.getLogger("seamless")


_assistant = None
def get_assistant():
    return _assistant

class ConfigurationError(Exception):
    pass

class AssistantConnectionError(ConnectionError, ConfigurationError):
    pass

class BufferServerConnectionError(ConnectionError, ConfigurationError):
    pass

class DatabaseConnectionError(ConnectionError, ConfigurationError):
    pass

def _contact_assistant():
    global _assistant, _delegate_level
    env = os.environ
    host = env.get("SEAMLESS_ASSISTANT_IP")
    if host is None:
        host = env.get("SEAMLESS_DEFAULT_ASSISTANT_IP")
        if host is None:
            raise ValueError("environment variable SEAMLESS_ASSISTANT_IP not defined")
    port = env.get("SEAMLESS_ASSISTANT_PORT")
    if port is None:
        port = env.get("SEAMLESS_DEFAULT_ASSISTANT_PORT")
        if port is None:
            raise ValueError("environment variable SEAMLESS_ASSISTANT_PORT not defined")
    port = int(port)
    if not (host.startswith("http://") or host.startswith("https://")):
        host = "http://" + host
    assistant = host + ":" + str(port)
    try:
        response = requests.get(assistant + "/config", timeout=3)
    except requests.exceptions.ConnectionError:
        raise AssistantConnectionError(f"Cannot contact assistant: host {host}, port {port}") from None
    assert response.status_code == 200
    
    _assistant = assistant
    _delegate_level = 4
    if response.content:
        raise NotImplementedError
    else:
        _init_buffer_remote_from_env(only_level_1=False)
        _init_database_from_env()


_delegating = False
_delegate_level = None

def get_delegate_level():
    return _delegate_level

def _init_database_from_env():
    """Configure database based on environment variables"""
    global _delegate_level
    assert _delegating

    env = os.environ
    host = env.get("SEAMLESS_DATABASE_IP")
    if host is None:
        raise ValueError("environment variable SEAMLESS_DATABASE_IP not defined")
    port = env.get("SEAMLESS_DATABASE_PORT")
    if port is None:
        raise ValueError("environment variable SEAMLESS_DATABASE_PORT not defined")
    try:
        port = int(port)
    except Exception:
        raise TypeError("environment variable SEAMLESS_DATABASE_PORT must be integer") from None
    try:
        database.connect(host, port)
    except requests.exceptions.ConnectionError as exc:
        raise DatabaseConnectionError(*exc.args) from None

def _init_buffer_remote_from_env(only_level_1=False):
    """Configure buffer remote folders/servers based on environment variables"""
    def _split_env(var, mode):
        assert mode in ("folder", "url"), mode
        if var:
            result = []
            for item in var.split(";"):
                item = item.strip()
                if not len(item):
                    continue
                if mode == "folder":
                    if not os.path.isdir(item):
                        logger.warning(f"Folder '{item}' does not exist")
                        continue
                else:
                    assert urlparse(item,scheme="").scheme in ("http", "https", "ftp"), var
                result.append(item)
            return result

    env = os.environ
    read_buffer_folders = env.get("SEAMLESS_READ_BUFFER_FOLDERS")
    read_buffer_folders = _split_env(read_buffer_folders, "folder")
    read_buffer_servers = env.get("SEAMLESS_READ_BUFFER_SERVERS")
    read_buffer_servers = _split_env(read_buffer_servers, "url")
    if not read_buffer_servers and not read_buffer_folders:
        raise ConfigurationError("No read buffer servers or folders defined")
    write_buffer_server = None
    if not only_level_1:
        write_buffer_server = env.get("SEAMLESS_WRITE_BUFFER_SERVER")
    if write_buffer_server:
        write_buffer_server = write_buffer_server.strip()
        assert urlparse(write_buffer_server,scheme="").scheme in ("http", "https", "ftp"), write_buffer_server

    set_read_buffer_folders(read_buffer_folders)
    set_read_buffer_servers(read_buffer_servers)
    try:
        set_write_buffer_server(write_buffer_server)
    except (ConnectionError, requests.exceptions.ConnectionError):
        raise BufferServerConnectionError(f"Cannot connect to write buffer server {write_buffer_server}") from None
    
def delegate(level=4, *, raise_exceptions=False, force_database=False):
    """Delegate computations and/or data to remote servers and folders.

- No delegation (level 0 / False): Don't delegate any computations, buffers or results.    

- Full delegation (level 4): Delegate all computations, buffers and results.

    First, contact the assistant: its URL and port are read from the 
    environment variables: SEAMLESS_ASSISTANT_IP and SEAMLESS_ASSISTANT_PORT.
    The assistant then returns the configuration for the three other levels. 
    If the assistant returns nothing (the default for mini and micro assistants), 
    the other three levels are configured from environment variables 
    (see "partial delegation" below).

    In addition to this, disable all local transformations. 
    All transformation jobs will be submitted to the assistant.

- Partial delegation: Don't delegate any computations. 
Delegate some or all buffers and results.

    Level 1: Configure only buffer read servers and buffer read folders. 
    Their environment variables are: SEAMLESS_READ_BUFFER_FOLDERS and 
    SEAMLESS_READ_BUFFER_SERVERS. Reading a buffer may fail silently.
    Buffers that are available in one of the read folders/buffers are not 
    kept in memory.

    Level 2: In addition to level 1, also configure a buffer write server. 
    The environment variable is SEAMLESS_WRITE_BUFFER_SERVER.
    All buffers that are not available in one of the read folders/buffers are 
    written to the buffer write server. Writing a buffer is an operation that must 
    succeed.
    It is implicitly assumed that a buffer that has been written becomes 
    available for reading. Therefore, the buffer write server should normally
    be included in the buffer read server list as well.

    Level 3: In addition to level 2, also store results in a database as checksums.
    These include the result checksums of: transformations, expressions, 
    syntactic-to-semantic, compilation to machine code, macro elision and
    structured cell joining. Conversion buffer info and generic metadata
    may also be stored.
    The environment variables are: SEAMLESS_DATABASE_IP and 
    SEAMLESS_DATABASE_PORT.

Advanced options    
================

- raise_exceptions: By default, failures in delegation lead to an error message printed out.
If you want to catch or print the error as a full Python exception, set raise_exceptions to True.

- force_database: This option is only meaningful for delegation level 0 or 1.
With this option, store computation result checksums in a database, as if the delegation level 
was 3 or 4, without delegating the storage of the underlying buffers.
You are now responsible yourself for persistent buffer storage, e.g. using ctx.save_vault(...) .
Failure to do so will lead to CacheMissErrors when you try to get the value of a previously
calculated result.
"""

    global _delegate_level, _delegating
    if _delegate_level is not None and _delegate_level != level:
        raise NotImplementedError("Changing delegation dynamically is currently not supported")

    if level not in (0,1,2,3,4):
        raise ValueError("Delegation level must be 0-4")
    if level > 1 and force_database:
        raise ValueError("force_database is only meaningful for delegation level 0 or 1")
    _delegating = True
    try:
        if level == 4:
            _contact_assistant()
            assert _assistant is not None  # will have been checked above
            block_local()
            return False
        if level >= 1:
            _init_buffer_remote_from_env(only_level_1=(level==1))
        if level == 3 or force_database:
            _init_database_from_env()
    except ConfigurationError as exc:
        if raise_exceptions:
            raise exc from None
        print_exc(limit=0,file=sys.stderr)
        return True
    finally:
        _delegating = False

    _delegate_level = level
    return False

_checked_delegation = False
def check_delegation():
    global _checked_delegation
    if _checked_delegation:
        return
    if _delegate_level is None:
        msg = """WARNING: Seamless delegation level was not set.

Use seamless.delegate() to enable delegation, or seamless.delegate(False)
to disable it. Continuing without delegation.
"""
        print(msg, file=sys.stderr)
    _checked_delegation = True

def add_buffer_folder(folder, read_only=True):    
    if read_only:
        min_level = 1
    else:
        min_level = 2
    if _delegate_level is None or _delegate_level < min_level:
        raise RuntimeError(f"Delegation level {min_level} is required")
    add_read_buffer_folder(folder)
    if not read_only:
        set_write_buffer_folder(folder)

def add_buffer_server(url, read_only=True):    
    if read_only:
        min_level = 1
    else:
        min_level = 2
    if _delegate_level is None or _delegate_level < min_level:
        raise RuntimeError(f"Delegation level {min_level} is required")
    add_read_buffer_server(url)
    if not read_only:
        set_write_buffer_server(url)

class InProcessAssistant(ABC):
    remote = False
    @abstractmethod
    async def run_job(self, checksum, tf_dunder, *, fingertip, scratch):
        raise NotImplementedError

def set_inprocess_assistant(assistant: InProcessAssistant):
    global _assistant, _delegate_level
    assert _delegate_level in (3,4)
    if not isinstance(assistant, InProcessAssistant):
        raise TypeError(type(assistant))
    _assistant = assistant
    _delegate_level = 4

from .core.cache.database_client import database
from .core.manager import block, unblock, block_local, unblock_local
from .core.manager.tasks import set_parallel_evaluations
from .core.cache.buffer_remote import (
    set_read_buffer_folders, set_read_buffer_servers, set_write_buffer_server,
    add_read_buffer_folder, add_read_buffer_server
)
from .core.transformation import set_ncores