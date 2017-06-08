import os, time, traceback, hashlib
from threading import Thread, RLock, Event
last_filehash = None
last_mtime = None
last_exc = None
warned = False

def read(fpath):
    global last_time, last_mtime, last_filehash, last_exc, warned
    curr_time = time.time()
    last_time = curr_time
    try:
        if not os.path.exists(fpath):
            if last_filehash is not None:
                PINS.filehash.set(None)
                last_filehash = None
            if not warned:
                print("WARNING: File does not exist: '%s'" % fpath)
                warned = True
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
    except Exception:
        exc = traceback.format_exc()
        if exc != last_exc:
            print(exc)
            last_exc = exc

sleeptime = 0.01
def poll():
    fpath = PINS.filepath.get()
    fpath = os.path.expanduser(fpath)
    while 1:
        sleeps = int(PINS.latency.get() / sleeptime + 0.9999)
        for n in range(sleeps):
            time.sleep(sleeptime)
            if terminate.is_set():
                break
        if terminate.is_set():
            break
        time.sleep(PINS.latency.get())
        read(fpath)

terminate = Event()
t = Thread(target=poll)
t.setDaemon(True)
lock = RLock()
t.start()

fpath = PINS.filepath.get()
fpath = os.path.expanduser(fpath)
read(fpath)
