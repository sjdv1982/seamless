#BLAAT
if __name__ == "__main__":
    #test with ipython -i
    import sys, os
    class EditPin:
        def __init__(self, value):
            self.value = value
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

    value = EditPin("test")

    directory = sys.argv[1]
    filename = sys.argv[2]
    filepath = Getter(os.path.join(directory, filename))
    latency = Getter(float(sys.argv[3]))
    def serializer(v):
        return str(v.get())
    print("Edit in " + filepath.get())
else:
    from seamless.dtypes import serialize
    def serializer(v):
        return serialize(v._dtype, v.get())


import os, time, functools
from seamless import add_work
from threading import Thread, RLock
last_value = None

def write_file(fpath):
    global last_mtime, last_value
    val = serializer(value)
    if last_value == val:
        return
    with lock:
        if last_value != val:
            with open(fpath, "w") as f:
                f.write(val)
                last_value = val
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
                        w = functools.partial(value.set, data)
                        add_work(w)
                        last_value = data
                    last_mtime = stat.st_mtime

t = Thread(target=poll)
t.setDaemon(True)
lock = RLock()
val = serializer(value)
write_file(filepath.get())
t.start()
