"""
Seamless: framework for data-driven and live programming
Copyright 2016, Sjoerd de Vries
"""
from collections import deque
import sys
import traceback

from .core.macro import macro
from .core.context import context
from .core.cell import cell, pythoncell
from .core.transformer import transformer
from .core.editor import editor


__all__ = ('macro', 'context', 'cell', 'pythoncell', 'transformer', 'editor')


_work = deque()


def add_work(work):
    _work.append(work)


def run_work():
    count = len(_work)
    for n in range(count):
        work = _work.popleft()
        try:
            work()
        except:
            traceback.print_tb()

qt_error = None


class SeamlessMock:

    def __init__(self, name, path):
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
    qt_app = PyQt5.QtWidgets.QApplication(["  "])

    # Alias QT
    for _mod_name in list(sys.modules.keys()):
        if _mod_name.startswith("PyQt5"):
            _aliased_mod_name = _mod_name.replace("PyQt5", "seamless.qt")
            sys.modules[_aliased_mod_name] = sys.modules[_mod_name]

    from PyQt5.QtCore import QTimer
    timer = QTimer()
    timer.timeout.connect(run_work)
    timer.start(10)

else:
    sys.stderr.write("    " + qt_error + "\n")
    sys.stderr.write("    All GUI in seamless.qt has been disabled\n")
    sys.meta_path.append(SeamlessMockImporter("seamless.qt"))
