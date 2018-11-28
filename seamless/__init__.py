"""
Seamless: framework for data-driven and live programming
Copyright 2016-2018, Sjoerd de Vries
"""

import sys
import time
import functools
import traceback
import atexit

from abc import abstractmethod
class Wrapper:
    @abstractmethod
    def _unwrap(self):
        pass

from . import silk
from . import mixed

#Dependencies of seamless

# 1. hard dependencies; without these, "import seamless" will fail.
# Still, if necessary, some of these dependencies could be removed, but seamless would have to be more minimalist in loading its lib

import numpy as np

if np.dtype(np.object).itemsize != 8:
    raise ImportError("Seamless requires a 64-bit system")

#silk must be imported before mixed
from . import silk
from . import mixed

from .core import mainloop as _mainloop
from .core.mainloop import mainloop, mainloop_one_iteration, asyncio_finish, workqueue
atexit.register(asyncio_finish)

ipython = None
ipy_error = None
try:
    from IPython import get_ipython
    from IPython.core.error import UsageError
    from IPython.terminal.pt_inputhooks import register as _register_integration_terminal
    from ipykernel.eventloops import register_integration as _register_integration_kernel
except ImportError:
    raise
    ipy_error = "Cannot find IPython"
else:
    ipython = get_ipython()
    if ipython is None:
        ipy_error = "Seamless was not imported inside IPython"

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

    def mainloop():
        raise RuntimeError("Cannot run seamless.mainloop() in IPython mode")

    def inputhook_terminal(context):
        while not context.input_is_ready():
            mainloop_one_iteration()
    _register_integration_terminal("seamless", inputhook_terminal)

    @_register_integration_kernel('seamless')
    def inputhook_kernel(kernel):
        while 1:
            t = time.time()
            while time.time() - t < kernel._poll_interval:
                mainloop_one_iteration()        
            kernel.do_one_iteration()

    _register_integration_terminal("seamless", inputhook_terminal)
    
    ipython.enable_gui("seamless")
    
else:
    sys.stderr.write("    " + ipy_error + "\n")
    sys.stderr.write("    Call seamless.mainloop(), seamless.flush() or context.equilibrate() to process cell updates\n")

def flush():
    from .core.mainloop import workqueue
    workqueue.flush()

from .highlevel import *
from .silk import Silk
from .debugger import pdb
