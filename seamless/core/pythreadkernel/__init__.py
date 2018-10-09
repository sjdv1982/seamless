from abc import ABCMeta, abstractmethod
from collections import deque
import threading
import weakref
import time

class QueueItem:

    def __init__(self, name, data, **kwargs):
        self.name = name
        self.data = data

        self.__dict__.update(kwargs)

    def __eq__(self, other):
        return self.name == other.name

    def __getitem__(self, index):
        if index == 0:
            return self.name

        elif index == 1:
            return self.data

        else:
            return IndexError


class Worker(metaclass=ABCMeta):
    """Base class for seamless Worker"""
    name = "worker"
    output_queue = None
    output_semaphore = None
    responsive = True
    running = False
    in_equilibrium = False

    def __init__(self, parent, inputs, event_cls=threading.Event, semaphore_cls=threading.Semaphore):
        self.parent = weakref.ref(parent)
        self.namespace = {}
        self.namespace["__name__"] = self.name
        self.inputs = inputs
        self.input_queue = deque()
        self.semaphore = semaphore_cls(0)
        self.finish = event_cls()     # command to finish
        self.finished = event_cls()   # report that we have finished
        self.values = {name: None for name in inputs}
        self.exception = None
        self.updated = set()

        self._pending_inputs = {name for name in inputs}
        self._pending_updates = 0

    def _cleanup(self):
        pass

    def process_message(self, message_id, name, data, content_type):
        pass

    def run(self):
        # TODO: add a mechanism to redirect exception messages to the host transformer
        # instead of printing them to stderr
        assert not self.running
        self.running = True

        def ack(end_of_loop=False):
            #if not end_of_loop and not len(self._pending_inputs):
            #    raise Exception
            updates_processed = self._pending_updates
            self._pending_updates = 0
            self.send_message(None, (updates_processed, self._pending_inputs))

        try:
            while True:
                self.semaphore.acquire()
                self._pending_updates += 1

                # Consume queue and break when asked to finish
                if self.finish.is_set() and not self.input_queue:
                    try:
                        self._cleanup()
                    finally:
                        break

                message_id, name, data, content_type = self.input_queue.popleft()  # QueueItem instance

                if name == "@RESPONSIVE":
                    self.responsive = True
                    ack(True)
                    continue
                elif name == "@TOUCH":
                    pass
                elif name.startswith("@"):
                    print("*********** PROTOCOL ERROR in transformer %s: unknown message name **************" % (self.parent(), name ) )
                    continue

                if not name.startswith("@"):
                    # It's cheaper to look-ahead for updates and wait until we process them instead
                    look_ahead = False
                    for item in list(self.input_queue):
                        new_name = item[1]
                        if new_name == name:
                            look_ahead = True
                            break
                    if look_ahead:
                        ack()
                        continue


                    self.process_message(message_id, name, data, content_type)
                    
                    if self.injected_modules and name in self.injected_modules:
                        language = content_type
                        if content_type == "mixed":
                            language = "binary"
                        mod = self.injector.define_module(self, name, language, data)
                        data = mod


                    # If we have missing values, and this input is currently default, it's no longer missing
                    if self.in_equilibrium and name not in self._pending_inputs:
                        self.in_equilibrium = False
                    if data is not None:
                        if self._pending_inputs and self.values[name] is None:
                            self._pending_inputs.remove(name)
                    else:
                        self._pending_inputs.add(name)

                    self.values[name] = data
                    self.updated.add(name)

                # With all inputs now present, we can issue updates
                time.sleep(0.01)
                if not self._pending_inputs and self.responsive and not self.in_equilibrium:
                    # ...but not if there is still something in the queue for us
                    if self.semaphore.acquire(blocking=False):
                        self.semaphore.release() #undo the acquire
                        ack(True)
                        continue
                    try:
                        self.update(self.updated, self.semaphore)
                        self.updated = set()

                    except Exception as exc:
                        self.exception = exc
                        print("*********** ERROR in transformer %s: execution error **************" % self.parent())
                        import traceback
                        traceback.print_exc(-1)

                    else:
                        self.exception = None

                ack(True)

        finally:
            self.finished.set()
        self.running = False

    @abstractmethod
    def update(self, updated):
        pass

    @abstractmethod
    def send_message(self, tag, message):
        pass

from .transformer import Transformer
