import weakref

class LiveGraph:
    def __init__(self, manager):
        self.manager = weakref.ref(manager)
