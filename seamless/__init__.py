"""
Seamless: framework for data-driven and live programming
Copyright 2016-2017, Sjoerd de Vries
"""

#Dependencies of seamless

# 1. hard dependencies; without these, "import seamless" will fail.
# Still, if necessary, some of these dependencies could be removed, but seamless would have to be more minimalist in loading its lib

import numpy
"""
#import PyOpenGL before PyQt5 to prevent the loading of the wrong OpenGL library that can happen on some systems. Introduces a hard dependency on PyOpenGL, TODO look into later"
from OpenGL import GL
import PyQt5, PyQt5.QtWebEngineWidgets
from cson import loads as _
del _
"""



# 2. Soft dependencies: transformers may use these libraries
# TODO: should be in the "imports" section of code cells!
"""
#as of seamless 0.1, scipy is not yet used in libraries...
try:
    import scipy
except ImportError:
    print("WARNING: scipy not found, some seamless library constructs may fail")
try:
    import pandas
except ImportError:
    print("WARNING: pandas not found, some seamless library constructs may fail")

try:
    import websockets
except ImportError:
    print("WARNING: websockets not found, some seamless library constructs may fail")
"""

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
## /GL related stuff

import sys
import traceback
import atexit
from . import _mainloop
from ._mainloop import mainloop, asyncio_finish, run_work
atexit.register(asyncio_finish)

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
            qt_error = None
        except UsageError:
            qt_error = "Your IPython is too old to support qt5"
        except ImportError:
            qt_error = "Cannot find PyQt5 (requires PyQt5.QtCore, .QtGui, .QtSvg, .QtWidgets)"

if qt_error is None:
    import PyQt5.QtWidgets
    import PyQt5.QtWebEngineWidgets
    from PyQt5 import QtGui, QtCore
    from PyQt5.QtCore import QTimer
    #QtCore.Qt.AA_ShareOpenGLContexts = True
    qt_app = PyQt5.QtWidgets.QApplication(["  "])
    _mainloop.event_loop = QtCore.QEventLoop(qt_app)

    timer = QTimer()
    #Failsafe: run accumulated work every 50 ms, should not be necessary at all
    timer.timeout.connect(run_work)
    timer.start(_mainloop.FAILSAFE_WORK_LATENCY)

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
    _mainloop._run_qt = True
else:
    sys.stderr.write("    " + qt_error + "\n")
    sys.stderr.write("    Call seamless.mainloop() to process cell updates\n")
