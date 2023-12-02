import threading
import os
import time
import pathlib

class DirLock:
    LOCK_TIMEOUT = 120
    def __init__(self, directory):
        self.directory = directory        
        self._lock_file_path = None
        self._running = False

    def __enter__(self):
        ident = f"{os.getpid()}-{threading.get_ident()}"
        self._lock_file_path = os.path.join(self.directory, "LOCK")
        while 1:
            os.makedirs(self.directory,exist_ok=True)
            ok = False
            try:
                with open(self._lock_file_path, "x") as f:
                    f.write(ident)
                    ok = True
            except FileExistsError:
                try:
                    lock_stat_result = os.stat(self._lock_file_path)
                except FileNotFoundError:
                    ok = True
                if not ok:
                    lock_mtime = lock_stat_result.st_mtime
                    if time.time() - lock_mtime > self.LOCK_TIMEOUT:
                        ok = True

            if not ok:
                time.sleep(1)
                continue
            
            try:
                with open(self._lock_file_path, "r") as f:
                    content = f.read()
                    if content != ident:
                        ok = False
            except FileNotFoundError:
                ok = False

            if not ok:
                time.sleep(1)
                continue

            break
        self._running = True
        self._touch_thread = threading.Thread(target=self._touch_loop, daemon=True)
        self._touch_thread.start()

    def __exit__(self, exc_type, exc_val, exc_tb):
        lock_file_path = self._lock_file_path
        self._lock_file_path = None  # stops the touch thread
        self._running = False
        self._touch_thread.join(5)
        pathlib.Path(lock_file_path).unlink()

    def touch(self):
        pname = self._lock_file_path
        p = pathlib.Path(pname)
        if pname is None or not p.exists():
            return
        p.touch()
    
    def _touch_loop(self):
        while self._running:
            self.touch()
            time.sleep(10)

def dirlock(directory):
    return DirLock(directory)