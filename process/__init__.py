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

    def __ne__(self, other):
        return self.name != other.name

    def __getitem__(self, index):
        if index == 0:
            return self.name

        elif index == 1:
            return self.data

        else:
            return IndexError


class Process:
    name = "process"

    def __init__(self, inputs):
        self.inputs = inputs
        self.queue = deque()
        self.semaphore = threading.Semaphore(0)
        self.finish = threading.Event()     # command to finish
        self.finished = threading.Event()   # report that we have finished
        self.value = {name:None for name in inputs.keys()}
        self.missing = len(inputs.keys())
        self.exception = None
        self.updated = set()

    def run(self):
        try:
            while 1:
                self.semaphore.acquire()
                if self.finish.is_set():
                    if not self.queue: # Todo check empty method instead (is this process safe?)
                        break

                name, data = self.queue.popleft()# QueueItem instance

                """
                check if there are newer updates to the same item
                if so, skip the current update
                """
                for new_name, new_update in list(self.queue):
                    if new_name == name:
                        continue

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

                if self.missing and self.value[name] is None:
                    self.missing -= 1

                self.value[name] = data_object
                self.updated.add(name)

                if not self.missing:
                    self.update(self.updated)
                    self.updated = set()
        finally:
            self.finished.set()

    def update(self, updated):
        pass
