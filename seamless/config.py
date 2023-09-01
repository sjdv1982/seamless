import os
from urllib.parse import urlparse

import logging
logger = logging.getLogger("seamless")

_has_assistant = False
def _contact_assistant():
    global _has_assistant
    if _has_assistant:
        return
    communion_server.configure_master(
        transformation_job=True,
        transformation_status=True,
    )

    raise NotImplementedError # receive a message, or invoke init_from_env

    # TODO: this won't work from Jupyter...
    communion_server.start()

def init_from_env():
    """Configure database and buffer remote folders/servers based on environment variables"""
    init_buffer_remote_from_env()

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

def init_buffer_remote_from_env():
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
                    assert urlparse(item,scheme="").scheme in ("http", "https", "ftp")
                result.append(item)
            return result

    env = os.environ
    read_buffer_folders = env.get("SEAMLESS_READ_BUFFER_FOLDERS")
    read_buffer_folders = _split_env(read_buffer_folders, "folder")
    read_buffer_servers = env.get("SEAMLESS_READ_BUFFER_SERVERS")
    read_buffer_servers = _split_env(read_buffer_servers, "url")
    write_buffer_server = env.get("SEAMLESS_WRITE_BUFFER_SERVER")
    if write_buffer_server:
        write_buffer_server = write_buffer_server.strip()
    set_read_buffer_folders(read_buffer_folders)
    set_read_buffer_servers(read_buffer_servers)
    set_write_buffer_server(write_buffer_server)
    

def delegate():
    """Delegate all computation and data storage to remote servers.
Disable all local transformations. Connect to an assistant and get configuration."""
    block_local()
    _contact_assistant()


from .core.cache.database_client import database
from .core.manager import block, unblock, block_local, unblock_local
from .core.manager.tasks import set_parallel_evaluations
from .core.cache.buffer_remote import (
    set_read_buffer_folders, set_read_buffer_servers, set_write_buffer_server
)