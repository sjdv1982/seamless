"""
Seamless: framework for data-driven and live programming
Copyright 2016-2018, Sjoerd de Vries
"""

import sys
import time
import functools
import traceback

import nest_asyncio
nest_asyncio.apply()
import asyncio
# Extra patch...
_loop = asyncio.get_event_loop()
from collections import deque
class FakeHandle:
    _cancelled = True
class Deque2(deque):
    def popleft(self):
        try:
            return super().popleft()
        except IndexError:
            return FakeHandle()
_loop._ready = Deque2(_loop._ready)

from abc import abstractmethod
class Wrapper:
    @abstractmethod
    def _unwrap(self):
        pass

#Dependencies of seamless

# 1. hard dependencies; without these, "import seamless" will fail.
# Still, if necessary, some of these dependencies could be removed, but seamless would have to be more minimalist in loading its lib

import numpy as np

if np.dtype(np.object).itemsize != 8:
    raise ImportError("Seamless requires a 64-bit system")

#silk must be imported before mixed
from . import silk
from . import mixed

ipython_instance = None
ipy_error = "Seamless was not imported inside IPython"

def inputhook_terminal(context):
    while not context.input_is_ready():
        """
        for manager in _toplevel_managers:            
            try:
                manager.taskmanager.run_synctasks()
            except Exception:
                import traceback
                traceback.print_exc()
        """
        try:            
            asyncio.get_event_loop().run_until_complete(asyncio.sleep(0))
        except IndexError: # nested event loop trouble
            pass

if "get_ipython" in sys.modules["__main__"].__dict__:
    try:
        from IPython import get_ipython
        from IPython.core.error import UsageError
        from IPython.terminal.pt_inputhooks import register as _register_integration_terminal
        from ipykernel.eventloops import register_integration as _register_integration_kernel
    except ImportError:
        ipy_error = "Cannot find IPython"
    else:
        ipython_instance = get_ipython()
        if ipython_instance is None:
            ipy_error = "Seamless was not imported inside IPython"
        else:
            TerminalInteractiveShell = type(None)
            try:
                from IPython.terminal.interactiveshell import TerminalInteractiveShell
            except ImportError:
                pass
            if isinstance(ipython_instance, TerminalInteractiveShell):
                from .core.macro_mode import _toplevel_managers
                _register_integration_terminal("seamless", inputhook_terminal)
                ipython_instance.enable_gui("seamless")


if ipy_error is None:
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

else:
    pass

from .silk import Silk
from .debugger import pdb
from .shareserver import shareserver
# TODO # livegraph branch
"""
from .communionserver import communionserver
from .core.events.jobscheduler import set_ncores
"""
from .get_hash import get_hash, get_dict_hash
from .core.cache.redis_client import RedisSink, RedisCache
from . import pandeval
from .pandeval.core.computation.eval import eval
pandeval.eval = eval
del eval