"""Seamless configuration"""

import os
import sys
import inspect
from urllib.parse import urlparse
from abc import ABC, abstractmethod
from traceback import print_exc
import logging
import warnings
import requests

from seamless.checksum.database_client import database
from seamless.checksum.buffer_remote import (
    set_read_buffer_folders,
    set_read_buffer_servers,
    set_write_buffer_server,
    add_read_buffer_folder,
    add_read_buffer_server,
)

logger = logging.getLogger(__name__)


_assistant = None


def get_assistant():
    """Return the Seamless assistant, if there is one.
    The setup of an assistant requires full delegation (level 4)"""
    return _assistant


class ConfigurationError(Exception):
    """Seamless configuration error"""


class AssistantConnectionError(ConnectionError, ConfigurationError):
    """Error in connecting to the Seamless assistant"""


class BufferServerConnectionError(ConnectionError, ConfigurationError):
    """Error in connecting to a Seamless buffer server"""


class DatabaseConnectionError(ConnectionError, ConfigurationError):
    """Error in connecting to the Seamless database"""


def _contact_assistant(agent):
    global _assistant, _delegation_level
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
        response = requests.get(
            assistant + "/config", params={"agent": agent}, timeout=3
        )
    except requests.exceptions.ConnectionError:
        raise AssistantConnectionError(
            f"Cannot contact delegation assistant: host {host}, port {port}"
        ) from None
    assert response.status_code == 200

    _assistant = assistant
    _delegation_level = 4
    if response.content:
        raise NotImplementedError
    else:
        _init_buffer_remote_from_env(only_level_1=False)
        _init_database_from_env()


_delegating = False
_delegation_level = None


def get_delegation_level():
    """Get current Seamless delegation level. See .delegate() for more information."""
    return _delegation_level


def _init_database_from_env():
    """Configure database based on environment variables"""
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
        raise TypeError(
            "environment variable SEAMLESS_DATABASE_PORT must be integer"
        ) from None
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
                    assert urlparse(item, scheme="").scheme in (
                        "http",
                        "https",
                        "ftp",
                    ), var
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
        assert urlparse(write_buffer_server, scheme="").scheme in (
            "http",
            "https",
            "ftp",
        ), write_buffer_server

    set_read_buffer_folders(read_buffer_folders)
    set_read_buffer_servers(read_buffer_servers)
    if not only_level_1:
        try:
            set_write_buffer_server(write_buffer_server)
        except (ConnectionError, requests.exceptions.ConnectionError):
            raise BufferServerConnectionError(
                f"Cannot connect to write buffer server {write_buffer_server}"
            ) from None


def block_local():
    """Block local execution of transformations.
    All transformations must be delegated."""
    from seamless.workflow.config import block_local as inner_block_local

    inner_block_local()


def unblock_local():
    """Unblock local execution of transformations."""
    from seamless.workflow.config import unblock_local as inner_unblock_local

    inner_unblock_local()


def delegate(level=4, *, raise_exceptions=False, force_database=False, agent=None):
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
    If you want to catch or print the error as a full Python exception,
    set raise_exceptions to True.

    - force_database: This option is only meaningful for delegation level 0 or 1.
    With this option, store computation result checksums in a database, as if the delegation level
    was 3 or 4, without delegating the storage of the underlying buffers.
    You are now responsible yourself for persistent buffer storage, e.g. using ctx.save_vault(...) .
    Failure to do so will lead to CacheMissErrors when you try to get the value of a previously
    calculated result.

    - agent: This option is only meaningful for full delegation.
    The agent name under which this Seamless instance identifies itself with the assistant.
    May affect the level 1-3 configuration returned by the assistant.
    If not specified, the full-path __file__ attribute of the script that calls .delegate() is used.
    If there is no __file__, the current working directory is used instead.

    Return value: True if an error occurred, False if delegation was successful
    """

    global _delegation_level, _delegating
    if _delegation_level is not None and _delegation_level != level:
        raise NotImplementedError(
            "Changing delegation dynamically is currently not supported"
        )

    if level not in (0, 1, 2, 3, 4):
        raise ValueError("Delegation level must be 0-4")
    if level > 1 and force_database:
        raise ValueError(
            "force_database is only meaningful for delegation level 0 or 1"
        )
    _delegating = True
    try:
        if level == 4:
            if agent is None:
                calling_script = inspect.currentframe().f_back.f_globals
                agent = calling_script.get("__file__")
                if agent is not None:
                    try:
                        agent = os.path.abspath(agent)
                    except Exception:
                        pass
                else:
                    agent = os.getcwd() + os.sep
            _contact_assistant(agent)
            assert _assistant is not None  # will have been checked above
            block_local()
            return False
        if level >= 1:
            _init_buffer_remote_from_env(
                only_level_1=(level == 1)
            )  # pylint: disable=superfluous-parens
        if level == 3 or force_database:
            _init_database_from_env()
    except ConfigurationError as exc:
        if raise_exceptions:
            raise exc from None
        print_exc(limit=0, file=sys.stderr)
        return True
    finally:
        _delegating = False

    _delegation_level = level
    return False


_checked_delegation = False


def check_delegation():
    """Check that Seamless delegation level has been set.
    If it is not, a warning is printed and delegation is set to
    False (level 0)."""
    global _checked_delegation
    if _checked_delegation:
        return
    if _delegation_level is None:
        msg = """WARNING: Seamless delegation level was not set.

Use seamless.delegate() to enable delegation, or seamless.delegate(False)
to disable it. Continuing without delegation.
"""
        print(msg, file=sys.stderr)
    _checked_delegation = True


def add_buffer_folder(folder):
    """Add Seamless buffer folder.
    Note that buffer folders are always read-only."""
    min_level = 1
    if _delegation_level is None or _delegation_level < min_level:
        raise RuntimeError(f"Delegation level {min_level} is required")
    add_read_buffer_folder(folder)


def add_buffer_server(url, read_only=True):
    """Adds a Seamless buffer server URL.
    If read_only, add a read buffer server.
    Else, add it as both read buffer server and write buffer server.
    Note that there can only be one write buffer server."""
    if read_only:
        min_level = 1
    else:
        min_level = 2
    if _delegation_level is None or _delegation_level < min_level:
        raise RuntimeError(f"Delegation level {min_level} is required")
    add_read_buffer_server(url)
    if not read_only:
        set_write_buffer_server(url)


class InProcessAssistant(ABC):
    """Abstract base class for in-process assistants.
    These are for nested/remote transformations that still need to report
    back to an assistant.

    WIP (see wip/dask-test.py, wip/dask-use-cluster.py):
    NOT BEING USED"""

    remote = False

    @abstractmethod
    async def run_job(self, checksum, tf_dunder, *, fingertip, scratch):
        """Run a transformation job"""
        raise NotImplementedError


def set_inprocess_assistant(assistant: InProcessAssistant):
    """Set an in-process Seamless assistant"""
    global _assistant, _delegation_level
    assert _delegation_level in (3, 4)
    if not isinstance(assistant, InProcessAssistant):
        raise TypeError(type(assistant))
    _assistant = assistant
    _delegation_level = 4


def set_ncores(ncores):
    """Define the number of cores.
    This affects the number of transformations that can run in parallel.
    Unless defined otherwise, a transformation claims one core.

    This imports seamless.workflow"""
    from seamless.workflow.core.transformation import _set_ncores

    if ncores == 0:
        warnings.warn(
            "set_ncores(0) is deprecated. Use seamless.config.block_local() instead.",
            DeprecationWarning,
            2,
        )

    return _set_ncores(ncores)


def add_download_urls(download_url_dict):
    """A dict where the keys are checksums and the values are (a single or a list of) url infos.
    An url info can be a URL string, or a dict containing 'url' and optionally
    'celltype', 'compression'
    """
    from seamless.util.fair import add_direct_urls

    return add_direct_urls(download_url_dict)

# Fingertip all inputs of transformations.
#  Use case: database + transformation with scratch inputs
fingertip_all: bool = False