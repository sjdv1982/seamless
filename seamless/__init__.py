"""Seamless: a framework for reproducible computing and interactive workflows

Author: Sjoerd de Vries
Copyright 2016-2023, INSERM, CNRS and project contributors
"""

__version__ = "0.12"

import sys
import traceback
import asyncio
import logging
import subprocess
import os

SEAMLESS_FRUGAL = bool(os.environ.get("__SEAMLESS_FRUGAL", False))

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

if not SEAMLESS_FRUGAL:
    import numpy as np
    if np.dtype(object).itemsize != 8:
        raise ImportError("Seamless requires a 64-bit system")

ipython_instance = None
running_in_jupyter = False
if not SEAMLESS_FRUGAL:
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

def run_transformation(checksum, *, fingertip=False, scratch=False, tf_dunder=None, new_event_loop=False, manager=None):
    from seamless.config import check_delegation
    from seamless.util import is_forked
    from .core.cache.transformation_cache import transformation_cache
    check_delegation()
    if running_in_jupyter and not new_event_loop:
        raise RuntimeError("'run_transformation' cannot be called from within Jupyter. Use 'await run_transformation_async' instead")
    elif asyncio.get_event_loop().is_running():
        if is_forked():
            # Allow it for forked processes (a new event loop will be launched)
            pass
        elif new_event_loop:
            # a new event loop will be launched anyway
            pass
        else:
            raise RuntimeError("'run_transformation' cannot be called from within a coroutine. Use 'await run_transformation_async' instead")

    if manager is None:
        tf_cache = transformation_cache
    else:
        tf_cache = manager.cachemanager.transformation_cache
    checksum = parse_checksum(checksum, as_bytes=True)
    tf_cache.transformation_exceptions.pop(checksum, None)
    return tf_cache.run_transformation(checksum, fingertip=fingertip, scratch=scratch, tf_dunder=tf_dunder, new_event_loop=new_event_loop, manager=manager)

async def run_transformation_async(checksum, *, fingertip, scratch, tf_dunder=None, manager=None, cache_only=False):
    from seamless.config import check_delegation
    from .core.cache.transformation_cache import transformation_cache
    check_delegation()
    checksum = parse_checksum(checksum, as_bytes=True)
    if manager is None:
        tf_cache = transformation_cache
    else:
        tf_cache = manager.cachemanager.transformation_cache
    checksum = parse_checksum(checksum, as_bytes=True)
    tf_cache.transformation_exceptions.pop(checksum, None)
    return await tf_cache.run_transformation_async(checksum, fingertip=fingertip, scratch=scratch, tf_dunder=tf_dunder, manager=manager, cache_only=cache_only)

try:
    _original_event_loop = asyncio.get_event_loop()
except RuntimeError:
    _original_event_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_original_event_loop)

def check_original_event_loop():
    try:
        event_loop = asyncio.get_event_loop()
    except RuntimeError:
        return
    if _original_event_loop is not None and event_loop is not _original_event_loop:
        #import traceback; traceback.print_stack()
        raise Exception(
"The asyncio eventloop was changed (e.g. by asyncio.run) since Seamless was started"
        )

from silk import Silk
from .core.transformation import set_ncores
from .calculate_checksum import calculate_checksum, calculate_dict_checksum
from .vault import load_vault
from . import config
from .core.cache import CacheMissError
from .highlevel.direct import transformer
from .highlevel.Checksum import Checksum
from .util import parse_checksum
from .config import delegate
from .core.transformation import SeamlessTransformationError
from . import multi
from . import fair
__all__ = [
    "Checksum",
    "calculate_checksum", "calculate_dict_checksum", "load_vault", "config", 
    "CacheMissError", "transformer", "delegate",
    "check_original_event_loop", "run_transformation", "run_transformation_async",
    "activate_transformations", "deactivate_transformations", "SeamlessTransformationError"
]