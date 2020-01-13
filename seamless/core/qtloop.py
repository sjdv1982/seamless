import sys, os
import asyncio
import multiprocessing
from multiprocessing import Process

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
    This is because forking has been disabled.
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
        msg = "Qt could not be started. Qt widgets will not work" #TODO: some kind of env variable to enable this warning
        ###print(msg,file=sys.stderr)
        return

    while 1:
        qt_app.processEvents()
        await asyncio.sleep(0.005)

if os.environ.get("SEAMLESS_USE_QT", True) not in (False, "false", 0, "0"):
    qtloop_future = asyncio.ensure_future(qtloop())
