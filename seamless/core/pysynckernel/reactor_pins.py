import weakref

class ReactorInput:
    def __init__(self, parent, name):
        self._parent = weakref.ref(parent)
        self._name = name
        self._value = None
        self.updated = False
        self.defined = False
    def get(self):
        return self._value
    @property
    def value(self):
        return self.get()

class ReactorInputSignal:
    def __init__(self, parent, name):
        self._parent = weakref.ref(parent)
        self._name = name
        self._clear = True
        self.updated = False
        self.updated_now = False
    def unclear(self):
        self._clear = False

class ReactorOutput:
    def __init__(self, parent, name):
        self._parent = weakref.ref(parent)
        self._name = name
    def _set(self, value, preliminary):
        p = self._parent()
        if p is None:
            return
        p.output_update(self._name, value, preliminary)
    def set(self, value):
        return self._set(value, False)
    def set_preliminary(self, value):
        return self._set(value, True)

class ReactorOutputSignal:
    def __init__(self, parent, name):
        self._parent = weakref.ref(parent)
        self._name = name
    def set(self):
        p = self._parent()
        if p is None:
            return
        p.output_update(self._name, None, priority=True)

class ReactorEdit:
    _store = None
    def __init__(self, parent, name):
        self._parent = weakref.ref(parent)
        self._name = name
        self._value = None
        self.updated = False
        self.defined = False
    def get(self):
        return self._value
    @property
    def value(self):
        return self.get()
    def _set(self, value, preliminary):
        self._value = value
        self.defined = True
        p = self._parent()
        if p is None:
            return
        if p.values[self._name] is None:
            p.values[self._name] = p.inputs[self._name]
        p.values[self._name].data = value
        p.output_update(self._name, value, preliminary)
    def set(self, value):
        return self._set(value, False)
    def set_preliminary(self, value):
        return self._set(value, True)
