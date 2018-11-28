"""
Seamless mainloop routines

Status:
For now, the mainloop is controlled by Qt timers
An overhaul to put it under asyncio control is most welcome.
"""

import time
from collections import deque
import threading
import asyncio
import contextlib
import traceback

MAINLOOP_FLUSH_TIMEOUT = 30 #maximum duration of a mainloop flush in ms

class WorkQueue:
    FAILSAFE_FLUSH_LATENCY = 50 #latency of flush in ms
    def __init__(self):
        self._work = deque()
        self._priority_work = deque()
        self._flushing = False
        self._signal_processing = 0
        self._append_lock = threading.Lock()

    def append(self, work, priority=False):
        with self._append_lock:
            if priority:
                self._priority_work.append(work)
            else:
                self._work.append(work)

    def flush(self, timeout=None):
        if threading.current_thread() is not threading.main_thread():
            return
        ### NOTE: disabled the code below to avoid the hanging
        #    of equilibrate() inside work
        #   It remains to be seen if this has any negative effects
        #if self._flushing:
        #    return
        ### /NOTE
        if timeout is not None:
            timeout_time = time.time() + timeout/1000
        self._flushing = True
        #print("WORKING", len(self._priority_work), len(self._work))
        #work_count = 0
        works = (self._priority_work, self._work)
        if self._signal_processing > 0:
            works = (self._priority_work,)
        for w in works:
            while len(w):
                if timeout is not None:
                    if time.time() > timeout_time:
                        break
                work = w.popleft()
                try:
                    #work_count += 1
                    work()
                except Exception:
                    traceback.print_exc()
                #if work_count == 100 and not _signal_processing:
                #    run_qt() # Necessary to prevent freezes in glwindow
                #    work_count = 0

        #Whenever work is done, do an asyncio flush
        loop = asyncio.get_event_loop()
        loop.call_soon(lambda loop: loop.stop(), loop)
        if not loop.is_running():
            loop.run_forever()

        """
        if self._signal_processing == 0 and _run_qt:
            run_qt() # Necessary to prevent freezes in glwindow
        """
        self._flushing = False

    def __len__(self):
        return len(self._work) + len(self._priority_work)

def asyncio_finish():
    try:
        loop = asyncio.get_event_loop()
        loop.stop()
        loop.run_forever()
    except RuntimeError:
        pass

"""
_run_qt = True  #set by __init__.py
event_loop = None #set by __init__.py

_qt_is_running = False
def run_qt():
    global _qt_is_running
    if _qt_is_running:
        return
    #Whenever work is done, let Qt flush its event queue
    # If you don't, segfaults happen (see test-gl-BUG.py)
    _qt_is_running = True
    event_loop.processEvents()
    _qt_is_running = False
"""

workqueue = WorkQueue()
def mainloop():
    """Only run in non-IPython mode"""
    while 1:
        mainloop_one_iteration()

def mainloop_one_iteration(timeout=MAINLOOP_FLUSH_TIMEOUT/1000):
    workqueue.flush(timeout)
    time.sleep(workqueue.FAILSAFE_FLUSH_LATENCY/1000)


