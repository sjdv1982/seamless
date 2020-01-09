"""
Seamless: framework for data-driven and live programming
Copyright 2016-2019, Sjoerd de Vries
"""

import sys
import time
import functools
import traceback

import asyncio

nest_asyncio = None
"""
# Jupyter notebook; DISABLED, as it does not work properly!

if asyncio.get_event_loop().is_running(): 
    import nest_asyncio
    nest_asyncio.apply()
"""

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

if np.dtype(np.object).itemsize != 8:
    raise ImportError("Seamless requires a 64-bit system")

#silk must be imported before mixed
from . import silk
from . import mixed

ipython_instance = None
ipy_error = "Seamless was not imported inside IPython"

def inputhook_terminal(context):
    while not context.input_is_ready():
        #asyncio.get_event_loop().run_until_complete(asyncio.sleep(0))
        pass

running_in_jupyter = False
if "get_ipython" in sys.modules["__main__"].__dict__:
    try:
        from IPython import get_ipython
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
                ipython_instance.enable_gui("asyncio")
            elif asyncio.get_event_loop().is_running(): # Jupyter notebook
                running_in_jupyter = True
                if nest_asyncio is not None: 
                    ipython_instance.magic("autoawait False")

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

def deactivate_transformations():
    from .core.cache.transformation_cache import transformation_cache
    transformation_cache.active = False

def activate_transformations():
    from .core.cache.transformation_cache import transformation_cache
    transformation_cache.active = True

def run_transformation(checksum):
    from .core.cache.transformation_cache import transformation_cache
    return transformation_cache.run_transformation(checksum)


from .silk import Silk
from .shareserver import shareserver
from .communion_server import communion_server
from .core.transformation import set_ncores
from .get_hash import get_hash, get_dict_hash
from .core.cache.redis_client import RedisSink, RedisCache
from . import debugger
"""
from . import pandeval
from .pandeval.core.computation.eval import eval
pandeval.eval = eval
del eval
"""