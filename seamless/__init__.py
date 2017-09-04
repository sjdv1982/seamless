"""
Seamless: framework for data-driven and live programming
Copyright 2016-2017, Sjoerd de Vries
"""

#Dependencies of seamless

# 1. hard dependencies; without these, "import seamless" will fail.
# Still, if necessary, some of these dependencies could be removed, but seamless would have to be more minimalist in loading its lib

import numpy
#import PyOpenGL before PyQt5 to prevent the loading of the wrong OpenGL library that can happen on some systems. Introduces a hard dependency on PyOpenGL, TODO look into later"
from OpenGL import GL
import PyQt5, PyQt5.QtWebEngineWidgets
from cson import loads as _
del _

# 2. Soft dependencies: transformers may use these libraries
"""
#as of seamless 0.1, scipy is not yet used in libraries...
try:
    import scipy
except ImportError:
    print("WARNING: scipy not found, some seamless library constructs may fail")
"""
try:
    import pandas
except ImportError:
    print("WARNING: pandas not found, some seamless library constructs may fail")

try:
    import websockets
except ImportError:
    print("WARNING: websockets not found, some seamless library constructs may fail")

from .core.macro import macro
from .core.context import context
from .core.cell import cell, pythoncell, csoncell, arraycell, signal
from .core.transformer import transformer
from .core.reactor import reactor
from .core.fromfile import fromfile

import time
from collections import deque
import threading
import asyncio
import atexit
import contextlib

FAILSAFE_WORK_LATENCY = 50 #latency of run_work in ms

_work = deque()
_priority_work = deque()
def add_work(work, priority=False):
    if priority:
        _priority_work.append(work)
    else:
        _work.append(work)

_running_work = False
def run_work():
    global _running_work
    if threading.current_thread() is not threading.main_thread():
        return
    if _running_work:
        return
    from .core.macro import get_activation_mode
    if not get_activation_mode():
        return
    _running_work = True
    #print("WORKING", len(_priority_work), len(_work))
    work_count = 0
    for w in (_priority_work, _work):
        while len(w):
            work = w.popleft()
            try:
                work()
            except Exception:
                traceback.print_exc()
            if work_count == 100:
                run_qt() # Necessary to prevent freezes in glwindow
                work_count = 0

    #Whenever work is done, do an asyncio flush
    loop = asyncio.get_event_loop()
    loop.call_soon(lambda loop: loop.stop(), loop)
    loop.run_forever()

    run_qt() # Necessary to prevent freezes in glwindow
    _running_work = False

def asyncio_finish():
    try:
        loop = asyncio.get_event_loop()
        loop.stop()
        loop.run_forever()
    except RuntimeError:
        pass
atexit.register(asyncio_finish)

import sys
import traceback
qt_error = None

class SeamlessMock:
    def __init__(self, name, path, *args, **kwargs):
        self.__name__ = name
        self.__path__ = path
    def __call__(self, *args, **kwargs):
        return self
    def __getattr__(self, attr):
        if attr in ("__cached__"):
            raise AttributeError
        return self
    def __setattr__(self, attr, value):
        if attr in ("__name__", "__path__"):
            object.__setattr__(self, attr, value)
        else:
          return self
    def __getitem__(self, item):
        return self
    def __str__(self):
        return "SeamlessMock"
    def __nonzero__(self):
        return True


class SeamlessMockImporter:
    def __init__(self, name, path=None):
        self.name = name
        self.path = path
    def find_module(self, fullname, path):
        if fullname.startswith(self.name):
            return SeamlessMockImporter(self.name, path)
        else:
            return None
    def load_module(self, fullname):
        mock = SeamlessMock(fullname, self.path)
        sys.modules[fullname] = mock
        return mock

ipython = None
try:
    from IPython import get_ipython
    from IPython.core.error import UsageError
except ImportError:
    qt_error = "Cannot find IPython"
else:
    ipython = get_ipython()
    if ipython is None:
        qt_error = "Seamless was not imported inside IPython"
    else:
        try:
            ipython.enable_gui("qt5")
        except UsageError:
            qt_error = "Your IPython is too old to support qt5"
        except ImportError:
            qt_error = "Cannot find PyQt5 (requires PyQt5.QtCore, .QtGui, .QtSvg, .QtWidgets)"


if qt_error is None:
    import PyQt5.QtWidgets
    import PyQt5.QtWebEngineWidgets
    from PyQt5 import QtGui, QtCore
    from PyQt5.QtCore import QTimer
    QtCore.Qt.AA_ShareOpenGLContexts = True
    qt_app = PyQt5.QtWidgets.QApplication(["  "])
    event_loop = QtCore.QEventLoop(qt_app)
    for _m in list(sys.modules.keys()):
        if _m.startswith("PyQt5"):
            _m2 = _m.replace("PyQt5", "seamless.qt")
            sys.modules[_m2] = sys.modules[_m]

    timer = QTimer()
    #Failsafe: run accumulated work every 50 ms, should not be necessary at all
    timer.timeout.connect(run_work)
    timer.start(FAILSAFE_WORK_LATENCY)

    import sys
    import traceback

    last_exception = None
    def new_except_hook(etype, evalue, tb):
        global last_exception
        exc = traceback.format_exception(etype, evalue, tb)
        if exc != last_exception:
            last_exception = exc
            print("".join(exc))

    def patch_excepthook():
        sys.excepthook = new_except_hook
    timer2 = QtCore.QTimer()
    timer2.setSingleShot(True)
    timer2.timeout.connect(patch_excepthook)
    timer2.start()
    patch_excepthook()

    def mainloop():
        raise RuntimeError("Cannot run seamless.mainloop() in IPython mode")

else:
    sys.stderr.write("    " + qt_error + "\n")
    sys.stderr.write("    All GUI in seamless.qt has been disabled\n")
    sys.stderr.write("    Call seamless.mainloop() to process cell updates\n")
    sys.meta_path.append(SeamlessMockImporter("seamless.qt"))

    def mainloop():
        while 1:
            run_work()
            time.sleep(FAILSAFE_WORK_LATENCY/1000)

## GL related stuff... put this into its own file as soon as the API is stable
_opengl_contexts = []
_opengl_destructors = {}
def add_opengl_context(context):
    assert context not in _opengl_contexts
    _opengl_contexts.append(context)
    _opengl_destructors[context] = []

def remove_opengl_context(context):
    #print("REMOVE", context in _opengl_contexts)
    if context in _opengl_contexts:
        _opengl_contexts.remove(context)
        for destructor in _opengl_destructors[context]:
            destructor()
        _opengl_destructors.pop(context)

def add_opengl_destructor(context, destructor):
    assert context in _opengl_destructors
    assert callable(destructor)
    _opengl_destructors[context].append(destructor)

_opengl_active = True
def activate_opengl():
    global _opengl_active
    _opengl_active = True

def deactivate_opengl():
    global _opengl_active
    _opengl_active = False

def opengl():
    return qt_error is None and _opengl_active


_running_qt = False
def run_qt():
    global _running_qt
    if _running_qt:
        return
    if qt_error is None:
        #Whenever work is done, let Qt flush its event queue
        # If you don't, segfaults happen (see test-gl-BUG.py)
        _running_qt = True
        event_loop.processEvents()
        _running_qt = False

def export(pin, dtype=None):
    """Exports a pin from a worker or subcontext into the active context.

    For a pin named subcontext.pinname, a cell called ctx.pinname is created.
    The dtype of the created cell is the pin's dtype, unless `dtype`
    is explicitly provided as argument.
    If the cell already exists, it is checked that it is of the correct dtype.

    Finally, the cell and the pin are connected.
    """
    from .core.context import get_active_context
    ctx = get_active_context()
    assert ctx is not None
    from .core.worker import PinBase, InputPinBase, OutputPinBase, EditPinBase
    from .core.cell import cell
    assert isinstance(pin, PinBase)
    if not hasattr(ctx, pin.name):
        if dtype is None:
            dtype = pin.dtype
        assert dtype is not None
        c = cell(dtype)
        setattr(ctx, pin.name, c)
    else:
        c = getattr(ctx, pin.name)
        if dtype is not None:
            cdtype = c.dtype
            if isinstance(cdtype, str) and isinstance(dtype, tuple):
                cdtype = (cdtype,)
            elif isinstance(cdtype, tuple) and isinstance(dtype, str):
                cdtype = cdtype[0]
            if dtype != cdtype:
                msg = """Cell %s already exists, but it is of the wrong dtype:
                %s, should be %s""" % (c, c.dtype, dtype)
                raise TypeError(msg)
    if isinstance(pin, (InputPinBase, EditPinBase)):
        c.connect(pin)
    else: #OutputPinBase
        pin.connect(c)
    return c


from . import qt
from .gui import shell
from . import lib
from .core.worker import InputPin, OutputPin, EditPin
from .core.observer import observer
__all__ = (
    context,
    cell, pythoncell, csoncell, arraycell, signal,
    transformer,
    InputPin, OutputPin, EditPin,
    reactor,
    export,
    macro,
    observer,
    shell
)
