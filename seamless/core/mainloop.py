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

    def flush(self):
        if threading.current_thread() is not threading.main_thread():
            return
        if self._flushing:
            return
        self._flushing = True
        #print("WORKING", len(self._priority_work), len(self._work))
        #work_count = 0
        works = (self._priority_work, self._work)
        if self._signal_processing > 0:
            works = (self._priority_work,)
        for w in works:
            while len(w):
                work = w.popleft()
                try:
                    work()
                    #work_count += 1
                except Exception:
                    traceback.print_exc()
                #if work_count == 100 and not _signal_processing:
                #    run_qt() # Necessary to prevent freezes in glwindow
                #    work_count = 0

        #Whenever work is done, do an asyncio flush
        loop = asyncio.get_event_loop()
        loop.call_soon(lambda loop: loop.stop(), loop)
        loop.run_forever()

        if self._signal_processing == 0 and _run_qt:
            run_qt() # Necessary to prevent freezes in glwindow
        self._flushing = False

def asyncio_finish():
    try:
        loop = asyncio.get_event_loop()
        loop.stop()
        loop.run_forever()
    except RuntimeError:
        pass

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

workqueue = WorkQueue()
def mainloop():
    """Only run in non-IPython mode"""
    while 1:
        workqueue.flush()
        time.sleep(workqueue.FAILSAFE_FLUSH_LATENCY/1000)
