import weakref

class ReactorInput:
    def __init__(self, parent, dtype, name):
        self._parent = weakref.ref(parent)
        self._dtype = dtype
        self._name = name
        self._value = None
        self.updated = False
        self.defined = False
    def get(self):
        return self._value

class ReactorInputSignal:
    def __init__(self, parent, name):
        self._parent = weakref.ref(parent)
        self._name = name
        self.updated = False

class ReactorOutput:
    def __init__(self, parent, dtype, name):
        self._parent = weakref.ref(parent)
        self._dtype = dtype
        self._name = name
    def set(self, value):
        p = self._parent()
        if p is None:
            return
        p.output_update(self._name, value)

class ReactorOutputSignal:
    def __init__(self, parent, name):
        self._parent = weakref.ref(parent)
        self._name = name
    def set(self):
        p = self._parent()
        if p is None:
            return
        p.output_update(self._name, None)

class ReactorEdit:
    def __init__(self, parent, dtype, name):
        self._parent = weakref.ref(parent)
        self._dtype = dtype
        self._name = name
        self._value = None
        self.updated = False
        self.defined = False
    def get(self):
        return self._value
    def set(self, value):
        self._value = value
        self.defined = True
        p = self._parent()
        if p is None:
            return
        if p.values[self._name] is None:
            p.values[self._name] = p.inputs[self._name]
        p.values[self._name].data = value
        p.output_update(self._name, value)
