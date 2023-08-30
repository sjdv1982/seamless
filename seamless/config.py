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

    communion_server.start()

def init_from_env():
    """Configure database and buffer remote folders/servers based on environment variables"""
    init_buffer_remote_from_env()
    raise NotImplementedError # read database env vars here, not in database.py
    database.connect()


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
    block()
    _contact_assistant()


from .core.cache.database_client import database
from .core.manager import block, unblock
from .core.manager.tasks import set_parallel_evaluations
from .core.cache.buffer_remote import (
    set_read_buffer_folders, set_read_buffer_servers, set_write_buffer_server
)