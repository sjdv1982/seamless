import traceback
from ... import Worker
import functools
import time
from threading import Thread, Event
from ..encode import encode
from ....cell import celltypes
celltypes_rev = {v:k for k,v in celltypes.items()}

def execute(server, rqdata, kill_event, callback):
    response = server.post(server, data=rqdata, timeout=10000)
    if response.status_code != requests.codes.ok:
        print("Server error: %s, %s" % response.status_code, response.text)
        callback(False, None)
    else:
        if kill_event.set():
            callback(False, None)
        else:
            callback(True, result)

class DummyInjector:
    def define_module(self, parent, name, language, data):
        return data
dummy_injector = DummyInjector()

class JobTransformer(Worker):
    name = "transformer"
    injector = dummy_injector
    injected_modules = None
    def __init__(self, parent, inputs,
                 output_name, output_queue, output_semaphore,
                 *, in_equilibrium = False, **kwargs):
        import requests
        self.output_name = output_name
        self.output_queue = output_queue
        self.output_semaphore = output_semaphore
        self.in_equilibrium = in_equilibrium
        self.access_modes = {}
        self.content_types = {}
        self.kill = Event()
        self.server = None
        super().__init__(parent, inputs, **kwargs)

    def process_message(self, message_id, name, data, access_mode, content_type):
        self.access_modes[name] = access_mode
        self.content_types[name] = content_type
        #TODO: git-style SHA-256 checksums

    def send_message(self, tag, message):
        #print("send_message", tag, message, hex(id(self.output_queue)))
        self.output_queue.append((tag, message))
        self.output_semaphore.release()

    def update(self, updated, semaphore):
        self.send_message("@START", None)
        parent = self.parent()
        transformer_params = parent._transformer_params
        outputpin = parent._pins[parent._output_name]
        output_cells = outputpin.cells()
        output_signature = [celltypes_rev[type(c)] for c in output_cells]
        if not len(output_signature):
            output_signature = ["mixed"]
        rqdata = encode(transformer_params, output_signature, self.values, self.access_modes, self.content_types)
        try:
            server = self.server
            assert server is not None
            if server.startswith("file://"):
                filename = server[len("file://"):]
                with open(filename, "wb") as f:
                    f.write(rqdata)
            else:
                self.kill.clear()

                #run request in separate executor thread...
                while 1:
                    time.sleep(0.01)
                    if semaphore.acquire(blocking=False):
                        semaphore.release()
                        self.kill.set()
                        break
        finally:
            assert self.parent().output_queue is self.output_queue
            self.send_message("@END", None)
        self.send_message(self.output_name, None)
