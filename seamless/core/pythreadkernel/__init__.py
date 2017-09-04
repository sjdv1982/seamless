from abc import ABCMeta, abstractmethod
from collections import deque
import threading
import weakref
import time

def init():
    pass


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

    def __init__(self, parent, inputs, event_cls=threading.Event, semaphore_cls=threading.Semaphore):
        self.parent = weakref.ref(parent)
        self.namespace = {}
        self.registrars = None #to be set by parent
        self.inputs = inputs
        self.input_queue = deque()
        self.semaphore = semaphore_cls(0)
        self.finish = event_cls()     # command to finish
        self.finished = event_cls()   # report that we have finished
        self.values = {name: None for name in inputs.keys()}
        self.exception = None
        self.updated = set()

        self._pending_inputs = {name for name in inputs.keys()}
        self._pending_updates = 0
        self._bumped = set()

    def _cleanup(self):
        pass

    def run(self):
        # TODO: add a mechanism to redirect exception messages (to a cell!)
        # instead of printing them to stderr

        def ack(end_of_loop=False):
            #if not end_of_loop and not len(self._pending_inputs):
            #    raise Exception
            updates_processed = self._pending_updates
            self._pending_updates = 0
            self.output_queue.append((None, (updates_processed, self._pending_inputs)))
            self.output_semaphore.release()

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

                # If there is a registrar update later in the queue, bump it (= move it to the top)
                bump = False
                for message_id, name, data, resource_name in list(self.input_queue)[1:]:
                    if message_id in self._bumped:
                        continue
                    if name == "@REGISTRAR":
                        bump = True
                        self._bumped.add(message_id)
                        break
                else:
                    message_id, name, data, resource_name = self.input_queue.popleft()  # QueueItem instance
                    if message_id in self._bumped:
                        self._bumped.remove(message_id)
                        self._pending_updates -= 1
                        self.semaphore.release()
                        continue

                if name == "@RESPONSIVE":
                    self.responsive = True
                    ack(True)
                    continue

                if name != "@REGISTRAR":
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

                if name == "@REGISTRAR":
                    if self.registrars is None:
                        err = "ERROR: cannot update registrar {0}, registrars have not been set"
                        print(err.format(value))
                    try:
                        registrar_name, key, namespace_name = data
                        registrar = getattr(self.registrars, registrar_name)
                        try:
                            registrar_value = registrar.get(key)
                        except KeyError:
                            raise
                            self._pending_inputs.add(namespace_name)
                        else:
                            self.namespace[namespace_name] = registrar_value
                            if namespace_name in self._pending_inputs:
                                self._pending_inputs.remove(namespace_name)
                    except Exception as exc:
                        self.exception = exc
                        import traceback
                        print("*********** ERROR in transformer %s: registrar error **************" % self.parent())
                        traceback.print_exc()
                        ack()
                        continue
                else:
                    data_object = self.inputs[name]
                    # instance of datatypes.objects.DataObject

                    try:
                        data_object.parse(data, resource_name)
                        data_object.validate()

                    except Exception as exc:
                        self.exception = exc
                        import traceback
                        print("*********** ERROR in transformer %s: parsing error, pin %s **************" % (self.parent(), name))
                        traceback.print_exc()
                        ack()
                        continue

                    # If we have missing values, and this input is currently default, it's no longer missing
                    if self._pending_inputs and self.values[name] is None:
                        self._pending_inputs.remove(name)

                    self.values[name] = data_object
                    self.updated.add(name)

                # With all inputs now present, we can issue updates
                time.sleep(0.01)
                if not self._pending_inputs and self.responsive:
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
                        traceback.print_exc()

                    else:
                        self.exception = None

                ack(True)

        finally:
            self.finished.set()

    @abstractmethod
    def update(self, updated):
        pass


from .transformer import Transformer
