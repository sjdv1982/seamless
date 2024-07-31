import asyncio
import os
import sys
import traceback


SEAMLESS_FRUGAL = bool(os.environ.get("__SEAMLESS_FRUGAL", False))

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
"The asyncio eventloop was changed (e.g. by asyncio.run) since seamless.workflow was imported"
        )

from .highlevel import Context, Transformer, Cell, SimpleDeepCell, FolderCell, DeepCell, DeepFolderCell, Module, load_graph, copy
from .vault import load_vault
from .core.transformation import SeamlessTransformationError

__all__ = [
    "load_vault",
    "check_original_event_loop", 
    "activate_transformations", "deactivate_transformations", "SeamlessTransformationError",
    "Context", "Transformer",
    "Cell", "SimpleDeepCell", "FolderCell", "DeepCell", "DeepFolderCell",
    "Module", "load_graph", "copy"
]
