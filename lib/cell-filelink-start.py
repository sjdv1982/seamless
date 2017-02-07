if __name__ == "__main__":
    #test with ipython -i
    import sys, os
    class OutputPin:
        def __init__(self, value):
            self.value = value
        def set(self, value):
            print("SET", value)
            self.value = value

    class Getter:
        def __init__(self, arg):
            self.arg = arg
        def get(self):
            return self.arg

    _pin = OutputPin("test")

    directory = sys.argv[1]
    filename = sys.argv[2]
    filepath = Getter(os.path.join(directory, filename))
    latency = Getter(float(sys.argv[3]))
    inp = Getter(_pin.value)
    outp = _pin
    print("Edit in " + filepath.get())

import os, time, functools
from seamless import add_work
from threading import Thread, RLock
last_value = None

def write_file(fpath):
    global last_mtime, last_value
    value = str(inp.get())
    if last_value == value:
        return
    with lock:
        if last_value != value:
            with open(fpath, "w") as f:
                f.write(value)
                last_value = value
            last_time = time.time()
            try:
                stat = os.stat(fpath)
                last_mtime = stat.st_mtime
            except:
                pass

def poll():
    global last_time, last_mtime, last_value
    fpath = filepath.get()
    while 1:
        time.sleep(latency.get())
        curr_time = time.time()
        last_time = curr_time
        if not os.path.exists(fpath):
            write_file(fpath)
        else:
            with lock:
                stat = os.stat(fpath)
                if stat.st_mtime > last_mtime:
                    data = None
                    with open(fpath) as f:
                        data = f.read()
                    if data is not None:
                        w = functools.partial(outp.set, data)
                        add_work(w)
                        last_value = data
                    last_mtime = stat.st_mtime

t = Thread(target=poll)
t.setDaemon(True)
lock = RLock()
write_file(filepath.get())
t.start()
