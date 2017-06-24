import weakref

class ReactorInput:
    _store = None
    def __init__(self, parent, dtype, name):
        self._parent = weakref.ref(parent)
        self._dtype = dtype
        self._name = name
        self._value = None
        self.updated = False
        self.defined = False
    def get(self):
        return self._value
    @property
    def value(self):
        return self.get()
    @property
    def store(self):
        return self._store

class ReactorInputSignal:
    def __init__(self, parent, name):
        self._parent = weakref.ref(parent)
        self._name = name
        self._clear = True
        self.updated = False
    def unclear(self):
        self._clear = False

class ReactorOutput:
    _store = None
    def __init__(self, parent, dtype, name):
        self._parent = weakref.ref(parent)
        self._dtype = dtype
        self._name = name
    def set(self, value):
        p = self._parent()
        if p is None:
            return
        p.output_update(self._name, value)
    @property
    def store(self):
        return self._store

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
    _store = None
    def __init__(self, parent, dtype, name):
        self._parent = weakref.ref(parent)
        self._dtype = dtype
        self._name = name
        self._value = None
        self.updated = False
        self.defined = False
    def get(self):
        return self._value
    @property
    def value(self):
        return self.get()
    def set(self, value):
        #print("SET",self._parent().parent(), self._name)
        self._value = value
        self.defined = True
        p = self._parent()
        if p is None:
            return
        if p.values[self._name] is None:
            p.values[self._name] = p.inputs[self._name]
        p.values[self._name].data = value
        p.output_update(self._name, value)
    @property
    def store(self):
        return self._store
