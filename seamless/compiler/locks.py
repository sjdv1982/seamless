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
                        with open(self._lock_file_path, "w") as f:
                            f.write(ident)
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
        self._touch_lock = threading.Lock()
        self._touch_thread = threading.Thread(target=self._touch_loop, daemon=True)
        self._touch_thread.start()

    def __exit__(self, exc_type, exc_val, exc_tb):
        lock_file_path = self._lock_file_path
        self._running = False  # stops the touch thread      
        self._touch_thread.join(timeout=60)
        if self._touch_thread.is_alive():
            pathlib.Path(lock_file_path).unlink(missing_ok=True)
            raise RuntimeError(f"Failed to release global dirlock: {lock_file_path}")

    def _touch(self):
        lock_file_path = self._lock_file_path
        if lock_file_path is None:
            return
        p = pathlib.Path(lock_file_path)
        p.touch()
    
    def _touch_loop(self):
        counter = 0
        while self._running:
            if counter == 0:
                self._touch()            
            time.sleep(1)
            counter += 1
            if counter == 10:
                counter = 0

        lock_file_path = self._lock_file_path
        assert lock_file_path is not None
        p = pathlib.Path(lock_file_path)
        assert p.exists()
        p.unlink()


def dirlock(directory):
    return DirLock(directory)