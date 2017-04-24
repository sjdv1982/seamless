import os, time
from threading import Thread, RLock
last_filehash = None
last_mtime = None

def poll():
    global last_time, last_mtime, last_filehash
    fpath = PINS.filepath.get()
    if fpath.startswith("~/"):
        fpath = os.environ["HOME"] + fpath[1:]
    while 1:
        time.sleep(PINS.latency.get())
        curr_time = time.time()
        last_time = curr_time
        if not os.path.exists(fpath):
            if last_filehash is not None:
                PINS.filehash.set(None)
                last_filehash = None
        else:
            with lock:
                stat = os.stat(fpath)
                try:
                    if last_mtime is None or stat.st_mtime > last_mtime:
                        data = None
                        with open(fpath, encoding="utf-8") as f:
                            data = f.read()
                        if data is not None:
                            filehash = hashlib.md5(data).hexdigest()
                            PINS.filehash.set(filehash)
                            last_filehash = filehash
                        last_mtime = stat.st_mtime
                except:
                    exc = traceback.format_exc()
                    print(exc)

def start():
    t = Thread(target=poll)
    t.setDaemon(True)
    lock = RLock()
    t.start()
