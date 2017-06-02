if __name__ == "__main__":
    #test with ipython -i
    import sys, os

    class dummy:
        pass

    class EditPin:
        def __init__(self, value):
            self.value = value
            self.defined = True
        def set(self, value):
            print("SET", value)
            self.value = value
        def get(self):
            return self.value

    class Getter:
        def __init__(self, arg):
            self.arg = arg
        def get(self):
            return self.arg
    PINS = dummy()
    PINS.value = EditPin("test")
    directory = sys.argv[1]
    filename = sys.argv[2]
    PINS.filepath = Getter(os.path.join(directory, filename))
    PINS.latency = Getter(float(sys.argv[3]))
    def serializer(v):
        return str(v.get())
    print("Edit in " + filepath.get())
else:
    from seamless.dtypes import serialize
    def serializer(v):
        return serialize(v._dtype, v.get())


import os, time, functools, traceback
from threading import Thread, RLock, Event
last_value = None
last_serialized_value = None
last_exc = None
last_mtime = None

def write_file(fpath):
    global last_mtime, last_value, last_serialized_value
    if not PINS.value.defined:
        last_mtime = -1 #will trigger a file read
        return
    if last_value == PINS.value.get():
        return
    val = serializer(PINS.value)
    if last_serialized_value == val:
        return
    with lock:
        if last_serialized_value != val:
            #print("WRITE", val)
            if PINS.value._dtype == "object":
                with open(fpath, "wb") as f:
                    f.write(val)
                    last_value = PINS.value.get()
                    last_serialized_value = val
            else:
                with open(fpath, "w", encoding="utf-8") as f:
                    f.write(val)
                    last_value = PINS.value.get()
                    last_serialized_value = val
            last_time = time.time()
            try:
                stat = os.stat(fpath)
                last_mtime = stat.st_mtime
            except Exception:
                pass

sleeptime = 0.01

def poll():
    global last_time, last_mtime, last_value, last_serialized_value, last_exc
    fpath = PINS.filepath.get()
    while 1:
        sleeps = int(PINS.latency.get() / sleeptime + 0.9999)
        for n in range(sleeps):
            time.sleep(sleeptime)
            if terminate.is_set():
                break
        if terminate.is_set():
            break
        curr_time = time.time()
        last_time = curr_time
        if not os.path.exists(fpath):
            try:
                write_file(fpath)
            except Exception:
                exc = traceback.format_exc()
                if exc != last_exc:
                    print(exc)
                    last_exc = exc
        else:
            with lock:
                stat = os.stat(fpath)
                try:
                    if last_mtime is None or stat.st_mtime > last_mtime:
                        data = None
                        if PINS.value._dtype == "object":
                            with open(fpath, "rb") as f:
                                data = f.read()
                        else:
                            with open(fpath, encoding="utf-8") as f:
                                data = f.read()
                        if data is not None:
                            if last_serialized_value != data:
                                #print("LOAD")
                                PINS.value.set(data)
                                last_value = None
                                last_serialized_value = data
                        last_mtime = stat.st_mtime
                except Exception:
                    exc = traceback.format_exc()
                    if exc != last_exc:
                        print(exc)
                        last_exc = exc

terminate = Event()
t = Thread(target=poll)
t.setDaemon(True)
lock = RLock()
write_file(PINS.filepath.get())
t.start()
