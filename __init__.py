"""
Seamless: framework for data-driven and live programming
Copyright 2016-2017, Sjoerd de Vries
"""

debug = False

# pre-import some libraries that will be needed by transformer threads
# better to import them in the main thread
try:
    import numpy
    import scipy
except ImportError:
    pass
try:
    import pandas
except ImportError:
    pass

from . import lib
from .core.macro import macro
from .core.context import context
from .core.cell import cell, pythoncell
from .core.transformer import transformer
from .core.editor import editor
from .core.fromfile import fromfile

import time
from collections import deque
import threading
import asyncio
import atexit
import contextlib

FAILSAFE_WORK_LATENCY = 50  # latency of run_work in ms

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
    _running_work = True
    for w in (_priority_work, _work):
        while len(w):
            work = w.popleft()
            try:
                work()
            except:
                traceback.print_exc()

    # Whenever work is done, do an asyncio flush
    loop = asyncio.get_event_loop()
    loop.call_soon(lambda loop: loop.stop(), loop)
    loop.run_forever()
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
    for _m in list(sys.modules.keys()):
        if _m.startswith("PyQt5"):
            _m2 = _m.replace("PyQt5", "seamless.qt")
            sys.modules[_m2] = sys.modules[_m]

    timer = QTimer()

    # Failsafe: run accumulated work every 50 ms, should not be necessary at all
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
            time.sleep(FAILSAFE_WORK_LATENCY / 1000)

_opengl_contexts = []


def add_opengl_context(context):
    _opengl_contexts.append(context)


def remove_opengl_context(context):
    if context in _opengl_contexts:
        _opengl_contexts.remove(context)


def opengl():
    return qt_error is None and len(_opengl_contexts) > 0


from . import qt

__all__ = (macro, context, cell, pythoncell, transformer, editor, qt)
