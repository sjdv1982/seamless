"""
Seamless: framework for data-driven and live programming
Copyright 2016, Sjoerd de Vries
"""

from .core.macro import macro
from .core.context import context
from .core.cell import cell, pythoncell
from .core.transformer import transformer
from .core.editor import editor
from .core.fromfile import fromfile
from . import lib

__all__ = (macro, context, cell, pythoncell, transformer, editor)

import time
from collections import deque
import threading

_work = deque()
_priority_work = deque()
def add_work(work, priority=False):
    if priority:
        _priority_work.append(work)
    else:
        _work.append(work)
def run_work():
    if threading.current_thread() is not threading.main_thread():
        return
    for w in (_priority_work, _work):
        while len(w):
            work = w.popleft()
            try:
                work()
            except:
                traceback.print_exc()

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
            qt_error = "Cannot find PyQt5 (requires QtCore, QtGui, QtSvg, QtWidgets)"


if qt_error is None:
    import PyQt5.QtWidgets
    import PyQt5.QtWebEngineWidgets
    qt_app = PyQt5.QtWidgets.QApplication(["  "])
    for _m in list(sys.modules.keys()):
        if _m.startswith("PyQt5"):
            _m2 = _m.replace("PyQt5", "seamless.qt")
            sys.modules[_m2] = sys.modules[_m]

    from PyQt5.QtCore import QTimer
    timer = QTimer()
    timer.timeout.connect(run_work)
    timer.start(10)
else:
    sys.stderr.write("    " + qt_error + "\n")
    sys.stderr.write("    All GUI in seamless.qt has been disabled\n")
    sys.meta_path.append(SeamlessMockImporter("seamless.qt"))
