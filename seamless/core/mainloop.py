"""
Seamless mainloop routines
"""

import sys
import time
from collections import deque
import threading
import asyncio
import contextlib
import traceback
import asyncio
import multiprocessing
from multiprocessing import Process

ipython = None
try:
    import IPython
    ipython = IPython.get_ipython()
except ImportError:
    pass

class WorkQueue:
    _ipython_registered = False
    def __init__(self):
        self._work = deque()
        self._priority_work = deque()
        self._flushing = False
        self._append_lock = threading.Lock()

    def append(self, work, priority=False):
        with self._append_lock:
            if priority:
                self._priority_work.append(work)
            else:
                self._work.append(work)

    async def flush(self, timeout=None):
        if threading.current_thread() is not threading.main_thread():
            return

        if timeout is not None:
            timeout_time = time.time() + timeout/1000
        self._flushing = True
        works = (self._priority_work, self._work)
        for w in works:
            while len(w):
                if timeout is not None:
                    if time.time() > timeout_time:
                        break
                work = w.popleft()
                try:
                    work()
                except Exception:
                    traceback.print_exc()
                yield

        self._flushing = False

    def __len__(self):
        return len(self._work) + len(self._priority_work)


workqueue = WorkQueue()

def test_qt():
    import PyQt5.QtCore, PyQt5.QtWidgets
    PyQt5.QtWidgets.QApplication(["  "])
    return True

async def qtloop():
    qt_app = None
    qtimport = False
    try:
        import PyQt5.QtCore, PyQt5.QtWidgets
        qtimport = True
    except ImportError:
        pass
    if qtimport:
        if multiprocessing.get_start_method() != "fork":
            print("""Cannot test if Qt can be started
    This is because forking is not possible, you are probably running under Windows
    Starting Qt blindly is not supported, as it may result in segfaults
    """,
            file=sys.stderr)
        else:
            p = Process(target=test_qt)
            p.start()
            p.join()
            if not p.exitcode:
                qt_app = PyQt5.QtWidgets.QApplication(["  "])
    if qt_app is None:
        msg = "Qt could not be started. Qt widgets will not work" #TODO: some kind of env variable to disable this warning
        print(msg,file=sys.stderr)
        return

    while 1:
        qt_app.processEvents()
        await asyncio.sleep(0.01)

asyncio.ensure_future(qtloop())
