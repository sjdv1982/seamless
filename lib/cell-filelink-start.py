if __name__ == "__main__":
    #test with ipython -i
    import sys, os
    class OutputPin:
        def __init__(self, value):
            self.value = value
        def set(self, value):
            print("SET", value)
            self.value = value
    _pin = OutputPin("test")

    directory = sys.argv[1]
    filename = sys.argv[2]
    filepath = os.path.join(directory, filename)
    latency = float(sys.argv[3])
    inp = _pin.value
    outp = _pin

import os, time, functools
from seamless import add_work
from threading import Thread, RLock
last_value = None

def write_file():
    global last_mtime, last_value
    value = str(inp)
    if last_value == value:
        return
    with lock:
        if last_value != value:
            with open(filepath, "w") as f:
                f.write(value)
                last_value = value
            last_time = time.time()
            try:
                stat = os.stat(filepath)
                last_mtime = stat.st_mtime
            except:
                pass

def poll():
    global last_time, last_mtime, last_value
    while 1:
        time.sleep(latency)
        curr_time = time.time()
        last_time = curr_time
        if not os.path.exists(filepath):
            write_file()
        else:
            with lock:
                stat = os.stat(filepath)
                if stat.st_mtime > last_mtime:
                    data = None
                    with open(filepath) as f:
                        data = f.read()
                    if data is not None:
                        w = functools.partial(outp.set, data)
                        add_work(w)
                        last_value = data
                    last_mtime = stat.st_mtime

t = Thread(target=poll)
t.setDaemon(True)
lock = RLock()
write_file()
t.start()
