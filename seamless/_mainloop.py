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

FAILSAFE_WORK_LATENCY = 50 #latency of run_work in ms

_work = deque()
_priority_work = deque()
def add_work(work, priority=False):
    if priority:
        _priority_work.append(work)
    else:
        _work.append(work)

_running_work = False
_signal_processing = 0
def run_work():
    global _running_work
    if threading.current_thread() is not threading.main_thread():
        return
    if _running_work:
        return
    _running_work = True
    #print("WORKING", len(_priority_work), len(_work))
    #work_count = 0
    works = (_priority_work, _work)
    if _signal_processing > 0:
        works = (_priority_work,)
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

    if _signal_processing == 0 and _run_qt:
        run_qt() # Necessary to prevent freezes in glwindow
    _running_work = False

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

def mainloop():
    """Only run in non-IPython mode"""
    while 1:
        run_work()
        time.sleep(FAILSAFE_WORK_LATENCY/1000)
