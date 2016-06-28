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
        self.inputs = inputs
        self.input_queue = deque()
        self.semaphore = semaphore_cls(0)
        self.finish = event_cls()     # command to finish
        self.finished = event_cls()   # report that we have finished
        self.values = {name: None for name in inputs.keys()}
        self.exception = None
        self.updated = set()

        self._pending_inputs = {name for name in inputs.keys()}

    def run(self):
        try:
            while True:
                self.semaphore.acquire()

                # Consume queue and break when asked to finish
                if self.finish.is_set() and not self.input_queue:
                    break

                name, data = self.input_queue.popleft()# QueueItem instance

                # It's cheaper to look-ahead for updates and wait until we process them instead
                for new_name, new_update in list(self.input_queue):
                    if new_name == name:
                        break

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
                        self.update(self.updated)
                        self.updated = set()

        finally:
            self.finished.set()

    @abstractmethod
    def update(self, updated):
        pass
