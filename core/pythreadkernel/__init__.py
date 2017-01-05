from abc import ABCMeta, abstractmethod
from collections import deque
import threading


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


class Process(metaclass=ABCMeta):
    """Base class for seamless Process"""
    name = "process"

    def __init__(self, inputs, event_cls=threading.Event, semaphore_cls=threading.Semaphore):
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
        self._bumped_registrar_updates = 0

    def _cleanup(self):
        pass

    def run(self):
        # TODO: add a mechanism to redirect exception messages (to a cell!)
        # instead of printing them to stderr
        import time
        time.sleep(0.001) # To allow registrar connections to be made
        try:
            while True:
                self.semaphore.acquire()

                # Consume queue and break when asked to finish
                if self.finish.is_set() and not self.input_queue:
                    try:
                        self._cleanup()
                    finally:
                        break

                # If there is a registrar update later in the queue, bump it (= move it to the top)
                curr_registrar_update = 0
                bump = False
                for name, data in list(self.input_queue)[1:]:
                    if name == "@REGISTRAR":
                        curr_registrar_update += 1
                        if curr_registrar_update > self._bumped_registrar_updates:
                            self._bumped_registrar_updates += 1
                            bump = True
                            break
                else:
                    name, data = self.input_queue.popleft()  # QueueItem instance

                if name == "@REGISTRAR":
                    if not bump and self._bumped_registrar_updates > 0:
                        self._bumped_registrar_updates -= 1
                        self.semaphore.release()
                        continue
                else:
                    # It's cheaper to look-ahead for updates and wait until we process them instead
                    look_ahead = False
                    for new_name, new_update in list(self.input_queue):
                        if new_name == name:
                            look_ahead = True
                            break
                    if look_ahead:
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
                            self._pending_inputs.add(namespace_name)
                        else:
                            self.namespace[namespace_name] = registrar_value
                        if namespace_name in self._pending_inputs:
                            self._pending_inputs.remove(namespace_name)
                    except Exception as exc:
                        self.exception = exc
                        import traceback
                        traceback.print_exc()
                        continue
                else:
                    data_object = self.inputs[name]
                    # instance of datatypes.objects.DataObject

                    try:
                        data_object.parse(data)
                        data_object.validate()

                    except Exception as exc:
                        self.exception = exc
                        import traceback
                        traceback.print_exc()
                        continue

                    # If we have missing values, and this input is currently default, it's no longer missing
                    if self._pending_inputs and self.values[name] is None:
                        self._pending_inputs.remove(name)

                    self.values[name] = data_object
                    self.updated.add(name)

                # With all inputs now present, we can issue updates
                if not self._pending_inputs:
                    try:
                        self.update(self.updated)
                        self.updated = set()

                    except Exception as exc:
                        self.exception = exc
                        import traceback
                        traceback.print_exc()


        finally:
            self.finished.set()

    @abstractmethod
    def update(self, updated):
        pass


from .transformer import Transformer
#from .editor import Editor
