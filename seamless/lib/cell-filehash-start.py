import os, time, traceback, hashlib
from threading import Thread, RLock
last_filehash = None
last_mtime = None
last_exc = None

def poll():
    global last_time, last_mtime, last_filehash, last_exc
    fpath = PINS.filepath.get()
    if fpath.startswith("~/"):
        fpath = os.environ["HOME"] + fpath[1:]
    print("FILEHASH PATH", fpath, os.path.exists(fpath))
    while 1:
        time.sleep(PINS.latency.get())
        curr_time = time.time()
        last_time = curr_time
        try:
            if not os.path.exists(fpath):
                if last_filehash is not None:
                    PINS.filehash.set(None)
                    last_filehash = None
                raise Exception("File does not exist: '%s'" % fpath)
            else:
                with lock:
                    stat = os.stat(fpath)

                    if last_mtime is None or stat.st_mtime > last_mtime:
                        data = None
                        with open(fpath, "rb") as f:
                            data = f.read()
                        if data is not None:
                            filehash = hashlib.md5(data).hexdigest()
                            PINS.filehash.set(filehash)
                            last_filehash = filehash
                        last_mtime = stat.st_mtime
        except:
            exc = traceback.format_exc()
            if exc != last_exc:
                print(exc)
                last_exc = exc

t = Thread(target=poll)
t.setDaemon(True)
lock = RLock()
t.start()
