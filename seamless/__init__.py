"""Seamless: a cell-based interactive workflow framework

Author: Sjoerd de Vries
Copyright 2016-2022, INSERM and project contributors
"""
import sys
import traceback
import asyncio
import logging
import subprocess
import sys
import multiprocessing
sys.modules["seamless.subprocess"] = subprocess  # pre-0.7 compat
logger = logging.getLogger("seamless")

from abc import abstractmethod
class Wrapper:
    @abstractmethod
    def _unwrap(self):
        pass
    @abstractmethod
    def set(self, value):
        pass

#Dependencies of seamless

# 1. hard dependencies; without these, "import seamless" will fail.
# Still, if necessary, some of these dependencies could be removed, but seamless would have to be more minimalist in loading its lib

import numpy as np

if np.dtype(object).itemsize != 8:
    raise ImportError("Seamless requires a 64-bit system")

ipython_instance = None
running_in_jupyter = False
try:
    from IPython import get_ipython
except ImportError:
    pass
else:
    ipython_instance = get_ipython()
    if ipython_instance is not None:
        TerminalInteractiveShell = type(None)
        try:
            from IPython.terminal.interactiveshell import TerminalInteractiveShell
        except ImportError:
            pass
        if isinstance(ipython_instance, TerminalInteractiveShell):
            ipython_instance.enable_gui("asyncio")
        elif asyncio.get_event_loop().is_running(): # Jupyter notebook
            running_in_jupyter = True

def verify_sync_translate():
    if running_in_jupyter:
        raise RuntimeError("'ctx.translate()' cannot be called from within Jupyter. Use 'await ctx.translation()' instead")
    elif asyncio.get_event_loop().is_running():
        raise RuntimeError("'ctx.translate()' cannot be called from within a coroutine. Use 'await ctx.translation()' instead")

def verify_sync_compute():
    if running_in_jupyter:
        raise RuntimeError("'ctx.compute()' cannot be called from within Jupyter. Use 'await ctx.computation()' instead")
    elif asyncio.get_event_loop().is_running():
        raise RuntimeError("'ctx.compute()' cannot be called from within a coroutine. Use 'await ctx.computation()' instead")

if ipython_instance is not None:
    last_exception = None
    def new_except_hook(etype, evalue, tb):
        global last_exception
        exc = traceback.format_exception(etype, evalue, tb)
        if exc != last_exception:
            last_exception = exc
            print("".join(exc))

    def patch_excepthook():
        sys.excepthook = new_except_hook
    patch_excepthook()

def deactivate_transformations():
    from .core.cache.transformation_cache import transformation_cache
    transformation_cache.active = False

def activate_transformations():
    from .core.cache.transformation_cache import transformation_cache
    transformation_cache.active = True

def run_transformation(checksum, metalike=None, new_event_loop=False):
    if running_in_jupyter and not new_event_loop:
        raise RuntimeError("'run_transformation' cannot be called from within Jupyter. Use 'await run_transformation_async' instead")
    elif asyncio.get_event_loop().is_running():
        if multiprocessing.current_process().name != "MainProcess":
            # Allow it for forked processes (a new event loop will be launched)
            pass
        elif new_event_loop:
            # a new event loop will be launched anyway
            pass
        else:
            raise RuntimeError("'run_transformation' cannot be called from within a coroutine. Use 'await run_transformation_async' instead")

    from .core.cache.transformation_cache import transformation_cache
    checksum = parse_checksum(checksum, as_bytes=True)
    return transformation_cache.run_transformation(checksum, metalike=metalike, new_event_loop=new_event_loop)

async def run_transformation_async(checksum, metalike=None):
    from .core.cache.transformation_cache import transformation_cache
    checksum = parse_checksum(checksum, as_bytes=True)
    transformation_cache.transformation_exceptions.pop(checksum, None)
    return await transformation_cache.run_transformation_async(checksum,metalike=metalike)

_original_event_loop = asyncio.get_event_loop()
def check_original_event_loop():
    event_loop = asyncio.get_event_loop()
    if event_loop is not _original_event_loop:
        raise Exception(
"The asyncio eventloop was changed (e.g. by asyncio.run) since Seamless was started"
        )

from silk import Silk
from .shareserver import shareserver
from .communion_server import communion_server
from .core.transformation import set_ncores
from .calculate_checksum import calculate_checksum, calculate_dict_checksum
from .core.cache.database_client import database_sink, database_cache
from .util import parse_checksum
from .vault import load_vault
from . import config
from .core.cache import CacheMissError