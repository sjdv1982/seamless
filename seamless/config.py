import os
from urllib.parse import urlparse

import logging
logger = logging.getLogger("seamless")

import requests

_assistant = None
def get_assistant():
    return _assistant

def _contact_assistant():
    global _assistant, _delegate_level
    env = os.environ
    host = env.get("SEAMLESS_ASSISTANT_IP")
    if host is None:
        raise ValueError("environment variable SEAMLESS_ASSISTANT_IP not defined")
    port = env.get("SEAMLESS_ASSISTANT_PORT")
    if port is None:
        raise ValueError("environment variable SEAMLESS_ASSISTANT_PORT not defined")
    port = int(port)
    if not (host.startswith("http://") or host.startswith("https://")):
        host = "http://" + host
    assistant = host + ":" + str(port)
    response = requests.get(assistant + "/config")
    assert response.status_code == 200
    
    _assistant = assistant
    block_local()
    _delegate_level = 4
    if response.content:
        raise NotImplementedError
    else:
        _init_buffer_remote_from_env(only_level_1=False)
        _init_database_from_env()


_delegate_level = None

def get_delegate_level():
    return _delegate_level

def _init_database_from_env():
    """Configure database and buffer remote folders/servers based on environment variables"""
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
    database.connect(host, port)

def _init_buffer_remote_from_env(only_level_1=False):
    def _split_env(var, mode):
        assert mode in ("folder", "url"), mode
        if var:
            result = []
            for item in var.split(";"):
                item = item.strip()
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
    write_buffer_server = None
    if not only_level_1:
        write_buffer_server = env.get("SEAMLESS_WRITE_BUFFER_SERVER")
    if write_buffer_server:
        write_buffer_server = write_buffer_server.strip()
        assert urlparse(write_buffer_server,scheme="").scheme in ("http", "https", "ftp"), write_buffer_server

    set_read_buffer_folders(read_buffer_folders)
    set_read_buffer_servers(read_buffer_servers)
    set_write_buffer_server(write_buffer_server)
    

def delegate(level=4):
    """Delegate computations and/or data to remote servers and folders.

Full delegation (level 4): Delegate all computations, buffers and results.

    First, contact the assistant: its URL and port are read from the 
    environment  variables: SEAMLESS_ASSISTANT_IP and SEAMLESS_ASSISTANT_PORT.
    The assistant then returns the configuration for the three other levels. 
    If the assistant returns nothing, the other three levels are configured 
    from environment variables.

    In addition to this, disable all local transformations. 
    All transformation jobs will be submitted to the assistant.

Partial delegation: Don't delegate any computations. 
Delegate some or all buffers and results.

    Level 1: Configure only buffer read servers and buffer read folders. 
    Their environment variables are: SEAMLESS_READ_BUFFER_FOLDERS and 
    SEAMLESS_READ_BUFFER_SERVERS. Reading a buffer may fail silently.
    Buffers that are available in one of the read folders/buffers are not 
    kept in memory.

    Level 2: In addition to level 1, also configure a buffer write server. 
    The environment variable is SEAMLESS_WRITE_BUFFER_SERVER.
    All buffers that are not available in one of the read folders/buffers are 
    written to the buffer server. Writing a buffer is an operation that must 
    succeed.
    It is implicitly assumed that a buffer that has been written becomes 
    available for reading. Therefore, the buffer write server should normally
    be included in the buffer read server list as well.

    Level 3: In addition to level 2, also store results to a database.
    These include the result checksums of: transformations, expressions, 
    syntactic-to-semantic, compilation to machine code, macro elision and
    structured cell joining. Conversion buffer info and generic metadata
    can also be stored.
    The environment variables are: SEAMLESS_DATABASE_IP and 
    SEAMLESS_DATABASE_PORT."""

    global _delegate_level
    if _delegate_level is not None:
        raise NotImplementedError

    assert level in (0,1,2,3,4), level
    if level == 4:
        _contact_assistant()
        return
    if level >= 1:
        _init_buffer_remote_from_env(only_level_1=(level==1))
    if level == 3:
        _init_database_from_env()
    _delegate_level = level

from .core.cache.database_client import database
from .core.manager import block, unblock, block_local, unblock_local
from .core.manager.tasks import set_parallel_evaluations
from .core.cache.buffer_remote import (
    set_read_buffer_folders, set_read_buffer_servers, set_write_buffer_server
)