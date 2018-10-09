import traceback
from .. import Worker
import functools
import time
from threading import Thread, Event

from ..mixed

def encode(value, content_type):
    #skip array for now...

def execute(server, values, content_type, kill_event, callback):
    assert values.keys() == content_type.keys()
    data = {}
    for k in values:
        content_type = content_types[k]
        data[k] = {
            "value": encode(values[k], content_type),
            "content_type": content_type
        }
        #TODO: SHA-512 checksums
    response = server.post(server, data=data, timeout=10000)
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

class Transformer(Worker):
    name = "transformer"
    injector = dummy_injector
    def __init__(self, parent, inputs,
                 output_name, output_queue, output_semaphore,
                 *, in_equilibrium = False, **kwargs):
        import requests
        self.output_name = output_name
        self.output_queue = output_queue
        self.output_semaphore = output_semaphore
        self.in_equilibrium = in_equilibrium
        self.content_types = {}
        self.kill = Event()
        self.server = None
        super(Transformer, self).__init__(parent, inputs, **kwargs)

    def process_message(self, message_id, name, data, content_type):
        self.content_types[name] = content_type
        #TODO: SHA-512 checksums

    def send_message(self, tag, message):
        #print("send_message", tag, message, hex(id(self.output_queue)))
        self.output_queue.append((tag, message))
        self.output_semaphore.release()

    def update(self, updated, semaphore):
        self.send_message("@START", None)
        ok = False
        assert self.server is not None
        self.kill.clear()
        try:
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
        if ok:
            self.last_result = result
            self.send_message(self.output_name, result)
